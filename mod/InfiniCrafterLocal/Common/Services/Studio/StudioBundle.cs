#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace InfiniCrafterLocal.Common.Services;

internal sealed record StudioBundleSpec(string Archive, string Sha256, string Python, string EntryPoint);

// No Terraria dependencies: installation is also checked by the linked-source CPU runner.
internal static class StudioBundle
{
    private const string CompleteMarker = ".complete";
    private const string OwnedFiles = ".owned-files.json";
    private const string InstallingMarker = ".installing";

    internal static StudioBundleSpec ReadManifest(byte[] manifest, string platform)
    {
        using JsonDocument document = JsonDocument.Parse(manifest);
        JsonElement root = document.RootElement;
        if (root.GetProperty("schemaVersion").GetInt32() != 1)
            throw new InvalidDataException("Unsupported bundled Studio manifest version.");
        if (!root.GetProperty("platforms").TryGetProperty(platform, out JsonElement payload))
            throw new PlatformNotSupportedException($"This mod does not contain Studio for {platform}. Use the external Studio launcher.");

        string archive = RequiredString(payload, "archive");
        string digest = RequiredString(payload, "sha256").ToLowerInvariant();
        string python = RequiredString(payload, "python");
        string entryPoint = RequiredString(payload, "entryPoint");
        ValidateRelativePath(archive);
        ValidateRelativePath(python);
        ValidateRelativePath(entryPoint);
        if (!archive.StartsWith("Studio/", StringComparison.Ordinal) || !archive.EndsWith(".zip", StringComparison.Ordinal))
            throw new InvalidDataException("The Studio archive must be a ZIP resource under Studio/.");
        if (digest.Length != 64 || !Array.TrueForAll(digest.ToCharArray(), Uri.IsHexDigit))
            throw new InvalidDataException("The bundled Studio manifest has an invalid SHA-256 digest.");
        return new StudioBundleSpec(archive, digest, python, entryPoint);
    }

    internal static string Install(byte[] payload, StudioBundleSpec spec, string runtimesDirectory, CancellationToken cancellationToken)
    {
        PrepareRuntimeDirectory(runtimesDirectory);
        using FileStream installationLock = AcquireInstallationLock(runtimesDirectory, cancellationToken);
        return InstallLocked(payload, spec, runtimesDirectory, cancellationToken);
    }

    internal static string InstallLocked(byte[] payload, StudioBundleSpec spec, string runtimesDirectory, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        string digest = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
        if (!string.Equals(digest, spec.Sha256, StringComparison.Ordinal))
            throw new InvalidDataException("The bundled Studio archive is damaged (SHA-256 mismatch). Reinstall the mod.");
        string destination = Path.Combine(runtimesDirectory, digest);
        RejectLinkedDirectory(runtimesDirectory);
        var owned = InspectArchive(payload, cancellationToken);
        if (Directory.Exists(destination))
        {
            VerifyInstalledFiles(destination, owned, cancellationToken);
            if (IsComplete(destination, spec))
                return destination;
        }

        string staging = Path.Combine(runtimesDirectory, ".install-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(staging);
            // A killed extraction can be reclaimed only from this complete ownership
            // inventory and matching remaining bytes, never from its directory name.
            WriteDurable(Path.Combine(staging, OwnedFiles), JsonSerializer.Serialize(owned));
            WriteDurable(Path.Combine(staging, InstallingMarker), digest);
            using (var memory = new MemoryStream(payload, writable: false))
            using (var archive = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    string relative = entry.FullName.TrimEnd('/');
                    string output = Path.Combine(staging, relative.Replace('/', Path.DirectorySeparatorChar));
                    if (entry.FullName.EndsWith("/", StringComparison.Ordinal))
                    {
                        Directory.CreateDirectory(output);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(output)!);
                    using Stream source = entry.Open();
                    using FileStream target = new FileStream(output, FileMode.CreateNew, FileAccess.Write);
                    source.CopyTo(target);
                    target.Close();
                    // The trusted archive was inspected before any cache reuse/extraction.
                }
            }

            if (!HasEntryPoints(staging, spec))
                throw new InvalidDataException("The Studio archive is missing its Python runtime or launcher.");
            cancellationToken.ThrowIfCancellationRequested();
            File.Move(Path.Combine(staging, InstallingMarker), Path.Combine(staging, CompleteMarker));
            // A previous interrupted installation never replaces a complete runtime.
            if (Directory.Exists(destination))
            {
                if (IsComplete(destination, spec))
                    return destination;
                RejectLinkedDirectory(destination);
                throw new IOException($"The Studio runtime is incomplete and was preserved at '{destination}'. Move this directory aside before reinstalling; keep any personal files.");
            }
            Directory.Move(staging, destination);
            return destination;
        }
        finally
        {
            if (Directory.Exists(staging))
                Directory.Delete(staging, recursive: true);
        }
    }

    // Caller holds the installation lock through launch readiness and this best-effort cleanup.
    internal static void RetirePreviousRuntimesLocked(string runtimesDirectory, StudioBundleSpec current)
    {
        RejectLinkedDirectory(runtimesDirectory);
        if (!IsComplete(Path.Combine(runtimesDirectory, current.Sha256), current))
            return;
        foreach (string directory in Directory.GetDirectories(runtimesDirectory))
        {
            string name = Path.GetFileName(directory);
            bool staging = name.StartsWith(".install-", StringComparison.Ordinal)
                && Guid.TryParseExact(name.Substring(9), "N", out _);
            if (name == current.Sha256 || !staging && (name.Length != 64 || !Array.TrueForAll(name.ToCharArray(), Uri.IsHexDigit)))
                continue;
            var handles = new List<FileStream>();
            try
            {
                RejectLinkedDirectory(directory);
                string inventory = Path.Combine(directory, OwnedFiles);
                if (!File.Exists(inventory))
                    continue; // Missing ownership inventory never authorizes deletion.
                var found = new Dictionary<string, FileStream>(StringComparer.Ordinal);
                var folders = new List<string>();
                var pending = new Stack<string>();
                pending.Push(directory);
                while (pending.Count > 0)
                {
                    string folder = pending.Pop();
                    RejectLinkedDirectory(folder);
                    folders.Add(folder);
                    foreach (string entry in Directory.GetFileSystemEntries(folder))
                    {
                        FileAttributes attributes = File.GetAttributes(entry);
                        if ((attributes & FileAttributes.ReparsePoint) != 0)
                            throw new IOException("Linked files are not managed Studio runtime content.");
                        if ((attributes & FileAttributes.Directory) != 0)
                            pending.Push(entry);
                        else
                        {
                            // ReadWrite rejects mapped executables on Windows. Retain handles
                            // until deletion so ordinary opens cannot race the verified bytes.
                            var handle = new FileStream(entry, FileMode.Open, FileAccess.ReadWrite, FileShare.Delete);
                            handles.Add(handle);
                            found.Add(Path.GetRelativePath(directory, entry).Replace('\\', '/'), handle);
                        }
                    }
                }
                string markerName = staging && found.ContainsKey(InstallingMarker) ? InstallingMarker : CompleteMarker;
                if (!found.TryGetValue(markerName, out FileStream? marker)
                    || !found.TryGetValue(OwnedFiles, out FileStream? inventoryHandle))
                    continue;
                var expected = JsonSerializer.Deserialize<Dictionary<string, string>>(inventoryHandle);
                if (expected == null || expected.Count == 0)
                    continue;
                // Resume a partially completed retirement/extraction, but never accept
                // extra files or directories as installer-owned content.
                if (found.Keys.Any(path => path != markerName && path != OwnedFiles && !expected.ContainsKey(path)))
                    continue;
                foreach (string relative in expected.Keys)
                {
                    ValidateRelativePath(relative);
                    if (IsReserved(relative) || expected[relative] == null || expected[relative].Length != 64
                        || !Array.TrueForAll(expected[relative].ToCharArray(), Uri.IsHexDigit))
                        throw new InvalidDataException("Invalid Studio inventory entry.");
                }
                using (var reader = new StreamReader(marker, Encoding.UTF8, true, 1024, leaveOpen: true))
                {
                    string marked = reader.ReadToEnd().Trim();
                    if (staging ? marked.Length != 64 || !Array.TrueForAll(marked.ToCharArray(), Uri.IsHexDigit) : marked != name)
                        continue;
                }
                bool matches = true;
                foreach (var entry in expected)
                    if (found.TryGetValue(entry.Key, out FileStream? file)
                        && Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant() != entry.Value)
                    { matches = false; break; }
                var expectedFolders = new HashSet<string>(StringComparer.Ordinal) { directory };
                foreach (string relative in expected.Keys)
                {
                    string? folder = Path.GetDirectoryName(Path.Combine(directory, relative));
                    while (folder != null && folder != directory)
                    {
                        expectedFolders.Add(folder);
                        folder = Path.GetDirectoryName(folder);
                    }
                }
                if (!matches || folders.Exists(folder => !expectedFolders.Contains(folder)))
                    continue;
                // Never recursively remove an unchecked file that appeared after validation.
                foreach (string relative in expected.Keys)
                    if (found.ContainsKey(relative))
                        File.Delete(Path.Combine(directory, relative));
                // Windows completes delete-pending files when their last handle closes.
                foreach (FileStream handle in handles)
                    if (!ReferenceEquals(handle, marker) && !ReferenceEquals(handle, inventoryHandle))
                        handle.Dispose();
                for (int index = folders.Count - 1; index > 0; index--)
                    Directory.Delete(folders[index], recursive: false);
                // Keep both ownership records until every payload file/subdirectory is gone.
                File.Delete(Path.Combine(directory, markerName));
                File.Delete(inventory);
                marker.Dispose();
                inventoryHandle.Dispose();
                Directory.Delete(directory, recursive: false);
            }
            catch (IOException) { /* Busy or changed: retry on a later successful launch. */ }
            catch (UnauthorizedAccessException) { /* Do not force deletion. */ }
            catch (JsonException) { /* Unknown metadata is not deletion authority. */ }
            catch (InvalidDataException) { /* Invalid paths never authorize cleanup. */ }
            finally
            {
                foreach (FileStream handle in handles)
                    handle.Dispose();
            }
        }
    }

    internal static FileStream AcquireInstallationLock(string runtimesDirectory, CancellationToken cancellationToken, TimeProvider? clock = null)
    {
        RejectLinkedDirectory(runtimesDirectory);
        RejectLinkedPath(runtimesDirectory, ".install.lock");
        string path = Path.Combine(runtimesDirectory, ".install.lock");
        clock ??= TimeProvider.System;
        long started = clock.GetTimestamp();
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                // Keep the empty file after closing: unlinking it could let another process
                // lock a new inode while an existing installer still owns the old one.
                return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            // Includes the first launch's 45-second readiness window and extraction/cleanup.
            catch (IOException) when (clock.GetElapsedTime(started) < TimeSpan.FromSeconds(120))
            {
                cancellationToken.WaitHandle.WaitOne(100);
            }
        }
    }

    internal static void WriteExternalLauncher(string studioDirectory, StudioBundleSpec spec)
    {
        // Relative paths survive a moved Documents directory and avoid embedding a user's
        // name or shell metacharacters. This launcher shares data but has no game lifetime.
        RejectLinkedDirectory(studioDirectory);
        string runtime = "runtimes\\" + spec.Sha256 + "\\";
        string python = (runtime + spec.Python.Replace('/', '\\')).Replace("%", "%%");
        string entryPoint = (runtime + spec.EntryPoint.Replace('/', '\\')).Replace("%", "%%");
        string contents = "@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
            + "set PYTHONNOUSERSITE=1\r\nset PYTHONDONTWRITEBYTECODE=1\r\nset PYTHONIOENCODING=utf-8\r\n"
            + $"\"%~dp0{python}\" -X utf8 -u -B \"%~dp0{entryPoint}\" --data-dir \"%~dp0data\" --tml-save-dir \"%~dp0..\\..\"\r\n"
            + "set \"IFC_STUDIO_EXIT=%ERRORLEVEL%\"\r\nif not \"%IFC_STUDIO_EXIT%\"==\"0\" pause\r\nexit /b %IFC_STUDIO_EXIT%\r\n";
        string destination = Path.Combine(studioDirectory, "OPEN_INFINICRAFT.bat");
        string temporary = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, contents, new UTF8Encoding(false));
            File.Move(temporary, destination, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }

    private static bool IsComplete(string directory, StudioBundleSpec spec)
    {
        if (!Directory.Exists(directory))
            return false;
        RejectLinkedDirectory(directory);
        RejectLinkedPath(directory, CompleteMarker);
        RejectLinkedPath(directory, OwnedFiles);
        RejectLinkedPath(directory, spec.Python);
        RejectLinkedPath(directory, spec.EntryPoint);
        string marker = Path.Combine(directory, CompleteMarker);
        return File.Exists(Path.Combine(directory, OwnedFiles)) && File.Exists(marker)
            && File.ReadAllText(marker).Trim() == spec.Sha256 && HasEntryPoints(directory, spec);
    }

    private static bool HasEntryPoints(string directory, StudioBundleSpec spec) =>
        File.Exists(Path.Combine(directory, spec.Python)) && File.Exists(Path.Combine(directory, spec.EntryPoint));


    internal static void PrepareRuntimeDirectory(string directory)
    {
        string? studio = Path.GetDirectoryName(directory);
        if (studio != null && Directory.Exists(studio)) RejectLinkedDirectory(studio);
        Directory.CreateDirectory(directory);
        RejectLinkedDirectory(directory);
    }

    private static bool IsReserved(string path) => path.Equals(CompleteMarker, StringComparison.OrdinalIgnoreCase)
        || path.Equals(OwnedFiles, StringComparison.OrdinalIgnoreCase) || path.Equals(InstallingMarker, StringComparison.OrdinalIgnoreCase);

    // The package targets Windows; reject path aliases even when checked on Linux.
    private static SortedDictionary<string, string> InspectArchive(byte[] payload, CancellationToken cancellationToken)
    {
        var inventory = new SortedDictionary<string, string>(StringComparer.Ordinal);
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using var memory = new MemoryStream(payload, writable: false);
        using var archive = new ZipArchive(memory, ZipArchiveMode.Read);
        foreach (var entry in archive.Entries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            string relative = entry.FullName.TrimEnd('/');
            ValidateRelativePath(relative);
            if (IsReserved(relative) || !seen.Add(relative) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                throw new InvalidDataException("Invalid or linked path in the Studio archive.");
            if (entry.FullName.EndsWith("/", StringComparison.Ordinal)) continue;
            using Stream source = entry.Open();
            inventory.Add(relative, Convert.ToHexString(SHA256.HashData(source)).ToLowerInvariant());
        }
        return inventory;
    }

    private static void VerifyInstalledFiles(string directory, SortedDictionary<string, string> expected, CancellationToken cancellationToken)
    {
        RejectLinkedDirectory(directory);
        RejectLinkedPath(directory, OwnedFiles);
        string inventory = Path.Combine(directory, OwnedFiles);
        if (!File.Exists(inventory))
            throw new IOException($"Bundled Studio has no current ownership inventory. It was preserved at '{directory}'; move only this runtime aside before reinstalling.");
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(inventory));
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object || root.EnumerateObject().Count() != expected.Count
                || root.EnumerateObject().Select(entry => entry.Name).Distinct(StringComparer.Ordinal).Count() != expected.Count
                || root.EnumerateObject().Any(entry => entry.Value.ValueKind != JsonValueKind.String
                    || !expected.TryGetValue(entry.Name, out string? hash) || entry.Value.GetString() != hash))
                throw new IOException("Bundled Studio ownership inventory does not match its current package; the runtime was preserved.");
        }
        catch (JsonException error)
        { throw new IOException("Bundled Studio ownership inventory is malformed; the runtime was preserved.", error); }
        foreach (var entry in expected)
        {
            cancellationToken.ThrowIfCancellationRequested();
            RejectLinkedPath(directory, entry.Key);
            string path = Path.Combine(directory, entry.Key);
            if (!File.Exists(path))
                throw new IOException($"Bundled Studio is missing '{entry.Key}'. The previous launcher and your data were preserved. Move only runtime '{directory}' aside, then reopen Studio to reinstall it.");
            using FileStream file = File.OpenRead(path);
            if (Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant() != entry.Value)
                throw new IOException($"Bundled Studio file '{entry.Key}' was modified or damaged. It was not overwritten. Move only runtime '{directory}' aside, retaining any personal files, then reopen Studio to reinstall it.");
        }
    }

    private static void RejectLinkedPath(string root, string relative)
    {
        string path = root;
        foreach (string component in relative.Split('/'))
        {
            path = Path.Combine(path, component);
            // GetAttributes also detects links whose targets no longer exist.
            try { if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Linked paths are not managed Studio runtime content."); }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
        }
    }

    private static void WriteDurable(string path, string text)
    {
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        stream.Write(Encoding.UTF8.GetBytes(text));
        stream.Flush(flushToDisk: true);
    }

    private static string RequiredString(JsonElement element, string name)
    {
        string? value = element.GetProperty(name).GetString();
        return !string.IsNullOrWhiteSpace(value) ? value : throw new InvalidDataException($"Missing Studio manifest field: {name}");
    }

    private static void ValidateRelativePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || Path.IsPathRooted(path) || path.IndexOfAny(new[] { '\\', ':', '"', '\0' }) >= 0)
            throw new InvalidDataException("Invalid path in the Studio package.");
        foreach (string part in path.Split('/'))
            if (part.Length == 0 || part == "." || part == ".." || part != part.TrimEnd(' ', '.'))
                throw new InvalidDataException("The Studio package contains a path outside its runtime directory.");
    }

    private static void RejectLinkedDirectory(string path)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("The Studio runtime directory must not be a symbolic link.");
    }
}
