#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Collections.Generic;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed partial class InfiniDumpCommand
{
    internal const string DumpManifestName = "runtime_dump_manifest.json";
    // Bound a single allocation, not the number/size of loaded definitions.
    internal const int DumpRecordByteLimit = 16 * 1024 * 1024;
    internal const long DumpDiskReserveBytes = 64L * 1024 * 1024;
    internal const string DumpIncompleteDirectory = "runtime_dump_incomplete";
    internal const string DumpIncompleteStateName = "capture.incomplete.json";
    private static readonly JsonSerializerOptions DumpJsonOptions = new() { WriteIndented = false };

    // One atomic pointer selects an immutable pair. Never overwrite the pair
    // selected by the previous manifest; a crash/failed capture cannot mix it.
    internal static JsonObject PublishSnapshot(string root, Action<TextWriter> writeItems,
        Action<TextWriter> writeProjectiles, JsonObject environment, CancellationToken cancellation = default,
        Action<string>? reportIncompleteDirectory = null)
    {
        Directory.CreateDirectory(root);
        string id = Guid.NewGuid().ToString("N");
        string relative = "runtime_dump_snapshots/" + id;
        string completeDirectory = Path.Combine(root, relative);
        string incompleteDirectory = Path.Combine(root, DumpIncompleteDirectory, id);
        string directory = incompleteDirectory;
        string pending = Path.Combine(root, ".runtime_dump_manifest." + id + ".tmp");
        Directory.CreateDirectory(directory);
        reportIncompleteDirectory?.Invoke(directory);
        string capturedAt = DateTimeOffset.UtcNow.ToString("O");
        try
        {
            // Written before the first payload. Even a killed process leaves an
            // explicitly incomplete attempt, never a replacement for the last pair.
            WriteIncompleteState(directory, id, capturedAt, "capturing", null);
            JsonObject Write(string name, Action<TextWriter> capture)
            {
                cancellation.ThrowIfCancellationRequested();
                string path = Path.Combine(directory, name);
                int rows, unavailable;
                using (var writer = new BoundedDumpWriter(path, cancellation))
                {
                    capture(writer);
                    writer.FlushToDisk();
                    rows = writer.Rows; unavailable = writer.UnavailableRows;
                }
                using var stream = File.OpenRead(path);
                using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = stream.Read(buffer)) != 0)
                { cancellation.ThrowIfCancellationRequested(); hash.AppendData(buffer, 0, read); }
                return new JsonObject { ["path"] = relative + "/" + name,
                    ["bytes"] = stream.Length, ["rows"] = rows, ["unavailableRows"] = unavailable,
                    ["sha256"] = Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant() };
            }
            var manifest = new JsonObject
            {
                ["schema"] = "infini.runtime-dump.v1", ["snapshotId"] = id,
                ["capturedAtUtc"] = capturedAt,
                ["capture"] = "loaded_definition_defaults_and_bounded_source_observations; not_AI_execution",
                ["environment"] = environment.DeepClone(),
                ["files"] = new JsonObject
                {
                    ["items"] = Write("items_runtime_dump.jsonl", writeItems),
                    ["projectiles"] = Write("projectiles_runtime_dump.jsonl", writeProjectiles)
                }
            };
            byte[] bytes = Encoding.UTF8.GetBytes(manifest.ToJsonString(DumpJsonOptions));
            if (bytes.Length > 1024 * 1024) throw new InvalidDataException("Dump manifest byte bound");
            using (var file = new FileStream(pending, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { file.Write(bytes); file.Flush(flushToDisk: true); }
            cancellation.ThrowIfCancellationRequested();
            Directory.CreateDirectory(Path.GetDirectoryName(completeDirectory)!);
            Directory.Move(directory, completeDirectory);
            directory = completeDirectory;
            reportIncompleteDirectory?.Invoke(directory);
            cancellation.ThrowIfCancellationRequested();
            File.Move(pending, Path.Combine(root, DumpManifestName), overwrite: true);
            // Publication is committed. A crash before cleanup can leave a
            // stale diagnostic marker, but the verified manifest is authoritative.
            // Cleanup failure must never roll back its now-selected payloads.
            try { File.Delete(Path.Combine(directory, DumpIncompleteStateName)); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            return manifest;
        }
        catch (Exception error)
        {
            // Preserve every byte already written, including a torn final row.
            // Recovery is inspection of the valid prefix, never automatic resume
            // or admission as a complete catalog. Diagnostics must not hide the
            // original disk/cancellation error if the disk is already full.
            if (directory != incompleteDirectory)
            {
                try { Directory.Move(directory, incompleteDirectory); directory = incompleteDirectory; }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
            try { WriteIncompleteState(directory, id, capturedAt,
                error is OperationCanceledException ? "cancelled" : "failed", error.GetType().Name); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            reportIncompleteDirectory?.Invoke(directory);
            throw;
        }
        finally
        {
            // Only a small unpublished pointer is expendable. No payload is
            // deleted after failure/cancellation, and previous pairs stay intact.
            try { if (File.Exists(pending)) File.Delete(pending); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }

    private static void WriteIncompleteState(string directory, string id, string capturedAt, string status, string? error)
    {
        var state = new JsonObject
        {
            ["schema"] = "infini.runtime-dump.incomplete.v1", ["snapshotId"] = id,
            ["capturedAtUtc"] = capturedAt, ["complete"] = false, ["status"] = status,
            ["error"] = error,
            ["recovery"] = "Diagnostic only. JSONL may end with an incomplete row. The last published manifest remains authoritative."
        };
        // The initial marker is durable before any capture. A failed rewrite
        // cannot erase its explicit incomplete status.
        string path = Path.Combine(directory, DumpIncompleteStateName);
        string temporary = path + ".tmp";
        using (var file = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            file.Write(Encoding.UTF8.GetBytes(state.ToJsonString(DumpJsonOptions)));
            file.Flush(flushToDisk: true);
        }
        File.Move(temporary, path, overwrite: true);
    }

    private static JsonObject CaptureDumpEnvironment() => CaptureDumpEnvironmentCore(includeFileHash: true);

    private static JsonObject CaptureDumpEnvironmentCore(bool includeFileHash)
    {
        var mods = new JsonArray();
        foreach (Mod mod in (ModLoader.Mods ?? Array.Empty<Mod>()).OrderBy(m => m.Name, StringComparer.Ordinal))
            mods.Add(new JsonObject { ["name"] = mod.Name, ["version"] = mod.Version.ToString(),
                ["module"] = DescribeAssembly(mod.GetType().Assembly, includeFileHash) });
        return new JsonObject
        {
            ["gameVersion"] = Main.versionNumber,
            ["tModLoader"] = DescribeAssembly(typeof(ModLoader).Assembly, includeFileHash),
            ["exporter"] = DescribeAssembly(typeof(InfiniDumpCommand).Assembly, includeFileHash),
            ["mods"] = mods, ["modSetStatus"] = ModLoader.Mods is null ? "unavailable" : "observed",
            // A reproducible roster fingerprint, not a claim that another
            // process has the same runtime mods or that this dump is current.
            ["modSetSha256"] = Convert.ToHexString(SHA256.HashData(
                Encoding.UTF8.GetBytes(mods.ToJsonString(DumpJsonOptions)))).ToLowerInvariant()
        };
    }

    private static JsonObject DescribeAssembly(Assembly assembly, bool includeFileHash)
    {
        string path = assembly.IsDynamic ? "" : assembly.Location;
        var identity = new JsonObject { ["assembly"] = assembly.GetName().Name,
            ["version"] = assembly.GetName().Version?.ToString(),
            ["mvid"] = assembly.ManifestModule.ModuleVersionId.ToString(),
            ["fileSha256"] = includeFileHash ? TryAssemblyFileHash(path) : null,
            ["informationalVersion"] = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion };
        // Internal transfer field. Removed before serialization/publication.
        if (!includeFileHash) identity["captureFile"] = path;
        return identity;
    }

    private static string? TryAssemblyFileHash(string path)
    {
        try
        {
            if (!string.IsNullOrEmpty(path) && File.Exists(path))
            { using var stream = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant(); }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        return null;
    }

    internal static void CompleteDumpEnvironmentFileHashes(JsonObject environment)
    {
        var hashes = new Dictionary<string, string?>(StringComparer.Ordinal);
        var mods = environment["mods"]!.AsArray();
        var identities = mods.OfType<JsonObject>().Select(mod => mod["module"]!.AsObject())
            .Concat(new[] { environment["tModLoader"]!.AsObject(), environment["exporter"]!.AsObject() });
        foreach (JsonObject identity in identities)
        {
            if (identity["captureFile"] is not JsonValue file) continue;
            string path = file.GetValue<string>();
            identity.Remove("captureFile");
            if (!hashes.TryGetValue(path, out string? hash)) hashes[path] = hash = TryAssemblyFileHash(path);
            identity["fileSha256"] = hash;
        }
        environment["modSetSha256"] = Convert.ToHexString(SHA256.HashData(
            Encoding.UTF8.GetBytes(mods.ToJsonString(DumpJsonOptions)))).ToLowerInvariant();
    }

    internal static long AvailableDumpDiskBytes(string path)
    {
        // On Unix DriveInfo uses statvfs on this directory. Reducing the path
        // to "/" would inspect the wrong disk for /home, /mnt and /Volumes.
        // Windows DriveInfo resolves the supplied directory to its drive.
        var drive = new DriveInfo(Path.GetDirectoryName(Path.GetFullPath(path))!);
        return drive.AvailableFreeSpace;
    }

    private sealed class BoundedDumpWriter : TextWriter
    {
        private readonly CancellationToken cancellation;
        private readonly StreamWriter writer;
        private readonly Func<long> availableBytes;
        public override Encoding Encoding => writer.Encoding;
        private long bytes, nextDiskCheck;
        internal int Rows { get; private set; }
        internal int UnavailableRows { get; private set; }
        internal BoundedDumpWriter(string path, CancellationToken cancellation = default, Func<long>? availableBytes = null)
        {
            this.cancellation = cancellation;
            this.availableBytes = availableBytes ?? (() => AvailableDumpDiskBytes(path));
            writer = new StreamWriter(path, append: false, new UTF8Encoding(false), bufferSize: 64 * 1024) { NewLine = "\n" };
        }
        public override void Write(char value) => throw new InvalidDataException("Dump writes require complete JSONL records.");
        public override void Flush() => writer.Flush();
        internal void FlushToDisk() { writer.Flush(); ((FileStream)writer.BaseStream).Flush(flushToDisk: true); }
        protected override void Dispose(bool disposing)
        {
            if (disposing) writer.Dispose();
            base.Dispose(disposing);
        }
        public override void WriteLine(string? value)
        {
            cancellation.ThrowIfCancellationRequested();
            int size = checked(Encoding.UTF8.GetByteCount(value ?? "") + 1);
            if (size > DumpRecordByteLimit)
                throw new InvalidDataException($"Dump record exceeds {DumpRecordByteLimit} UTF-8 bytes; partial export retained.");
            if (value is null || value.Contains('\n') || value.Contains('\r'))
                throw new InvalidDataException("Dump record must be one JSONL object.");
            using var row = JsonDocument.Parse(value);
            if (row.RootElement.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("Dump record must be an object.");
            int nextRows = checked(Rows + 1);
            long nextBytes = checked(bytes + size);
            if (nextBytes >= nextDiskCheck)
            {
                // Real free space, not a fixed catalog-size ceiling. Recheck at
                // bounded intervals and leave room for the OS/recovery marker.
                FlushToDisk();
                long needed = DumpDiskReserveBytes + DumpRecordByteLimit;
                if (availableBytes() < needed)
                    throw new IOException($"Runtime dump needs at least {needed} bytes of free disk space; partial export retained.");
                nextDiskCheck = bytes + 4 * 1024 * 1024;
            }
            writer.WriteLine(value);
            bytes = nextBytes; Rows = nextRows;
            if (row.RootElement.TryGetProperty("unavailable", out var unavailable)
                && unavailable.ValueKind == JsonValueKind.True) UnavailableRows++;
        }
    }
}
