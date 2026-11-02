#nullable enable
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

// Owns only the process launched by this mod instance. External launchers remain independent.
internal sealed class BundledStudio : IDisposable
{
    private const string ReadyPrefix = "IFC_STUDIO_READY ";
    private readonly object _gate = new();
    private readonly CancellationTokenSource _lifetime = new();
    private readonly Mod _mod;
    private readonly string _saveDirectory;
    private Task<Uri>? _launch;
    private Process? _process;
    private bool _disposed;

    internal static bool IsSupported => OperatingSystem.IsWindows() && RuntimeInformation.ProcessArchitecture == Architecture.X64;

    internal BundledStudio(Mod mod, string saveDirectory)
    {
        _mod = mod;
        _saveDirectory = saveDirectory;
    }

    internal Task<Uri> StartAsync()
    {
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_launch != null && !_launch.IsCompleted)
                return _launch;
            if (_launch?.Status == TaskStatus.RanToCompletion && _process is { HasExited: false })
                return _launch;
            _process?.Dispose();
            _process = null;
            // Extraction and interpreter startup must not stall Terraria's menu thread.
            return _launch = Task.Run(StartCoreAsync);
        }
    }

    private async Task<Uri> StartCoreAsync()
    {
        if (!IsSupported)
            throw new PlatformNotSupportedException("Bundled Studio currently supports Windows x64. Use the external launcher on this platform.");
        CancellationToken cancellationToken = _lifetime.Token;
        StudioBundleSpec spec = StudioBundle.ReadManifest(ReadResource("Studio/manifest.json"), "win-x64");
        string studioDirectory = Path.Combine(_saveDirectory, "InfiniCrafterLocal", "Studio");
        string runtime = StudioBundle.Install(ReadResource(spec.Archive), spec, Path.Combine(studioDirectory, "runtimes"), cancellationToken);
        string dataDirectory = Path.Combine(studioDirectory, "data");
        Directory.CreateDirectory(dataDirectory);
        StudioBundle.WriteExternalLauncher(studioDirectory, spec);

        var start = new ProcessStartInfo
        {
            FileName = Path.Combine(runtime, spec.Python),
            WorkingDirectory = Path.Combine(runtime, "LocalGenerator"),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        start.ArgumentList.Add("-X");
        start.ArgumentList.Add("utf8");
        start.ArgumentList.Add("-u");
        start.ArgumentList.Add("-B");
        start.ArgumentList.Add(Path.Combine(runtime, spec.EntryPoint));
        start.ArgumentList.Add("--data-dir");
        start.ArgumentList.Add(dataDirectory);
        start.ArgumentList.Add("--tml-save-dir");
        start.ArgumentList.Add(_saveDirectory);
        start.ArgumentList.Add("--managed");
        start.Environment["PYTHONNOUSERSITE"] = "1";
        start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        start.Environment["PYTHONIOENCODING"] = "utf-8";

        var process = new Process { StartInfo = start, EnableRaisingEvents = true };
        var ready = new TaskCompletionSource<Uri>(TaskCreationOptions.RunContinuationsAsynchronously);
        var errors = new StringBuilder();
        process.OutputDataReceived += (_, args) =>
        {
            // Ordinary stdout can contain a tokenized browser URL; never copy it to the game log.
            if (args.Data == null || !args.Data.StartsWith(ReadyPrefix, StringComparison.Ordinal))
                return;
            try
            {
                using JsonDocument message = JsonDocument.Parse(args.Data.Substring(ReadyPrefix.Length));
                string? address = message.RootElement.GetProperty("url").GetString();
                if (!Uri.TryCreate(address, UriKind.Absolute, out Uri? url) || url.Scheme != "http" || url.Host != "127.0.0.1" || url.Port <= 0 || url.UserInfo.Length != 0)
                    throw new InvalidDataException("Studio returned an invalid local browser address.");
                ready.TrySetResult(url);
            }
            catch (Exception exception)
            {
                ready.TrySetException(exception);
            }
        };
        process.ErrorDataReceived += (_, args) =>
        {
            if (args.Data == null)
                return;
            lock (errors)
            {
                errors.AppendLine(args.Data);
                if (errors.Length > 4096)
                    errors.Remove(0, errors.Length - 4096);
            }
        };
        process.Exited += (_, _) =>
        {
            lock (errors)
                ready.TrySetException(new IOException("Studio exited before it was ready. " + errors));
        };

        try
        {
            lock (_gate)
            {
                cancellationToken.ThrowIfCancellationRequested();
                ObjectDisposedException.ThrowIf(_disposed, this);
                if (!process.Start())
                    throw new IOException("Could not start the bundled Studio runtime.");
                _process = process;
            }
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            return await ready.Task.WaitAsync(TimeSpan.FromSeconds(45), cancellationToken).ConfigureAwait(false);
        }
        catch
        {
            lock (_gate)
                if (ReferenceEquals(_process, process))
                    _process = null;
            StopProcess(process);
            throw;
        }
    }

    private byte[] ReadResource(string path)
    {
        // Close() must not close the .tmod while an independent package stream is still open.
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (!_mod.FileExists(path))
                throw new FileNotFoundException("Studio is not included in this mod build. Install a packaged release or use the external launcher.", path);
            using Stream source = _mod.GetFileStream(path, newFileStream: true);
            using var destination = new MemoryStream();
            source.CopyTo(destination);
            return destination.ToArray();
        }
    }

    public void Dispose()
    {
        Process? process;
        lock (_gate)
        {
            if (_disposed)
                return;
            _disposed = true;
            _lifetime.Cancel();
            process = _process;
            _process = null;
        }
        if (process != null)
            StopProcess(process);
    }

    private static void StopProcess(Process process)
    {
        lock (process)
        {
            try
            {
                if (!process.HasExited)
                {
                    // EOF is the managed launcher's graceful stop protocol.
                    process.StandardInput.Close();
                    // Python allows up to nine seconds for HTTP and owned-generator cleanup.
                    if (!process.WaitForExit(10_000))
                    {
                        process.Kill(entireProcessTree: true);
                        process.WaitForExit(1000);
                    }
                }
            }
            catch (InvalidOperationException) { }
            catch (System.ComponentModel.Win32Exception) { }
            catch (IOException)
            {
                try
                {
                    if (!process.HasExited)
                        process.Kill(entireProcessTree: true);
                }
                catch (InvalidOperationException) { }
                catch (System.ComponentModel.Win32Exception) { }
            }
            finally
            {
                process.Dispose();
            }
        }
    }
}
