#nullable enable
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
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
        cancellationToken.ThrowIfCancellationRequested();
        string digest = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
        if (!string.Equals(digest, spec.Sha256, StringComparison.Ordinal))
            throw new InvalidDataException("The bundled Studio archive is damaged (SHA-256 mismatch). Reinstall the mod.");

        Directory.CreateDirectory(runtimesDirectory);
        using FileStream installationLock = AcquireInstallationLock(runtimesDirectory, cancellationToken);
        string destination = Path.Combine(runtimesDirectory, digest);
        if (IsComplete(destination, spec))
            return destination;

        string staging = Path.Combine(runtimesDirectory, ".install-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(staging);
            using (var memory = new MemoryStream(payload, writable: false))
            using (var archive = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                // The package targets Windows; reject aliases even when checked on Linux.
                var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    string relative = entry.FullName.TrimEnd('/');
                    ValidateRelativePath(relative);
                    if (!seen.Add(relative))
                        throw new InvalidDataException($"Duplicate path in the Studio archive: {relative}");
                    if (((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                        throw new InvalidDataException("Symbolic links are not allowed in the Studio archive.");
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
                }
            }

            if (!HasEntryPoints(staging, spec))
                throw new InvalidDataException("The Studio archive is missing its Python runtime or launcher.");
            cancellationToken.ThrowIfCancellationRequested();
            File.WriteAllText(Path.Combine(staging, CompleteMarker), digest, new UTF8Encoding(false));
            // A previous interrupted installation never replaces a complete runtime.
            if (Directory.Exists(destination))
            {
                if (IsComplete(destination, spec))
                    return destination;
                RejectLinkedDirectory(destination);
                Directory.Delete(destination, recursive: true);
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

    private static FileStream AcquireInstallationLock(string runtimesDirectory, CancellationToken cancellationToken)
    {
        string path = Path.Combine(runtimesDirectory, ".install.lock");
        var elapsed = Stopwatch.StartNew();
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                // Keep the empty file after closing: unlinking it could let another process
                // lock a new inode while an existing installer still owns the old one.
                return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            catch (IOException) when (elapsed.Elapsed < TimeSpan.FromSeconds(30))
            {
                cancellationToken.WaitHandle.WaitOne(100);
            }
        }
    }

    internal static void WriteExternalLauncher(string studioDirectory, StudioBundleSpec spec)
    {
        // Relative paths survive a moved Documents directory and avoid embedding a user's
        // name or shell metacharacters. This launcher shares data but has no game lifetime.
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
        string marker = Path.Combine(directory, CompleteMarker);
        return File.Exists(marker) && File.ReadAllText(marker).Trim() == spec.Sha256 && HasEntryPoints(directory, spec);
    }

    private static bool HasEntryPoints(string directory, StudioBundleSpec spec) =>
        File.Exists(Path.Combine(directory, spec.Python)) && File.Exists(Path.Combine(directory, spec.EntryPoint));

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
