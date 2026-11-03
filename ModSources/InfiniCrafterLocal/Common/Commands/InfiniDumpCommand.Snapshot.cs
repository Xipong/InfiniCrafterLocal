#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed partial class InfiniDumpCommand
{
    internal const string DumpManifestName = "runtime_dump_manifest.json";
    internal const long DumpFileByteLimit = 512L * 1024 * 1024;
    internal const int DumpRowLimit = 100_000;
    private static readonly JsonSerializerOptions DumpJsonOptions = new() { WriteIndented = false };

    // One atomic pointer selects an immutable pair. Never overwrite the pair
    // selected by the previous manifest; a crash/failed capture cannot mix it.
    internal static JsonObject PublishSnapshot(string root, Action<TextWriter> writeItems,
        Action<TextWriter> writeProjectiles, JsonObject environment)
    {
        Directory.CreateDirectory(root);
        string id = Guid.NewGuid().ToString("N");
        string relative = "runtime_dump_snapshots/" + id;
        string directory = Path.Combine(root, relative);
        Directory.CreateDirectory(directory);
        string pending = Path.Combine(root, ".runtime_dump_manifest." + id + ".tmp");
        bool published = false;
        try
        {
            JsonObject Write(string name, Action<TextWriter> capture)
            {
                string path = Path.Combine(directory, name);
                using (var writer = new BoundedDumpWriter(path))
                { capture(writer); writer.Flush(); ((FileStream)writer.BaseStream).Flush(flushToDisk: true); }
                int rows = 0, unavailable = 0;
                foreach (string line in File.ReadLines(path))
                {
                    using var row = JsonDocument.Parse(line);
                    if (row.RootElement.ValueKind != JsonValueKind.Object)
                        throw new InvalidDataException("Dump record must be an object");
                    rows++;
                    if (row.RootElement.TryGetProperty("unavailable", out var value)
                        && value.ValueKind == JsonValueKind.True) unavailable++;
                }
                using var stream = File.OpenRead(path);
                return new JsonObject { ["path"] = relative + "/" + name,
                    ["bytes"] = stream.Length, ["rows"] = rows, ["unavailableRows"] = unavailable,
                    ["sha256"] = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant() };
            }
            var manifest = new JsonObject
            {
                ["schema"] = "infini.runtime-dump.v1", ["snapshotId"] = id,
                ["capturedAtUtc"] = DateTimeOffset.UtcNow.ToString("O"),
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
            File.Move(pending, Path.Combine(root, DumpManifestName), overwrite: true);
            published = true;
            return manifest;
        }
        finally
        {
            // Only this attempt's unpublished files can be removed. A previous
            // successful snapshot is never cleaned up by this command.
            if (!published)
            {
                if (File.Exists(pending)) File.Delete(pending);
                if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true);
            }
        }
    }

    private static JsonObject CaptureDumpEnvironment()
    {
        var mods = new JsonArray();
        foreach (Mod mod in (ModLoader.Mods ?? Array.Empty<Mod>()).OrderBy(m => m.Name, StringComparer.Ordinal))
            mods.Add(new JsonObject { ["name"] = mod.Name, ["version"] = mod.Version.ToString(),
                ["module"] = DescribeAssembly(mod.GetType().Assembly) });
        return new JsonObject
        {
            ["gameVersion"] = Main.versionNumber,
            ["tModLoader"] = DescribeAssembly(typeof(ModLoader).Assembly),
            ["exporter"] = DescribeAssembly(typeof(InfiniDumpCommand).Assembly),
            ["mods"] = mods, ["modSetStatus"] = ModLoader.Mods is null ? "unavailable" : "observed",
            // A reproducible roster fingerprint, not a claim that another
            // process has the same runtime mods or that this dump is current.
            ["modSetSha256"] = Convert.ToHexString(SHA256.HashData(
                Encoding.UTF8.GetBytes(mods.ToJsonString(DumpJsonOptions)))).ToLowerInvariant()
        };
    }

    private static JsonObject DescribeAssembly(Assembly assembly)
    {
        string? hash = null;
        try
        {
            if (!string.IsNullOrEmpty(assembly.Location) && File.Exists(assembly.Location))
            { using var stream = File.OpenRead(assembly.Location); hash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant(); }
        }
        catch (IOException) { } // In-memory/unreadable module: retain observed MVID, never invent a build hash.
        catch (UnauthorizedAccessException) { }
        return new JsonObject { ["assembly"] = assembly.GetName().Name,
            ["version"] = assembly.GetName().Version?.ToString(),
            ["mvid"] = assembly.ManifestModule.ModuleVersionId.ToString(), ["fileSha256"] = hash,
            ["informationalVersion"] = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion };
    }

    private sealed class BoundedDumpWriter : StreamWriter
    {
        private long bytes;
        private int rows;
        internal BoundedDumpWriter(string path) : base(path, append: false, new UTF8Encoding(false)) { }
        public override void WriteLine(string? value)
        {
            long next = bytes + Encoding.UTF8.GetByteCount(value ?? "") + Encoding.UTF8.GetByteCount(NewLine);
            if (next > DumpFileByteLimit || rows >= DumpRowLimit)
                throw new InvalidDataException("Dump file byte or row bound");
            base.WriteLine(value); bytes = next; rows++;
        }
    }
}
