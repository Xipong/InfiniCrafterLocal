using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Commands;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void RuntimeDumpStreamsPastFormerFileCeiling()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-large-").FullName;
        try
        {
            // Real disk bytes through the production publisher, not a mocked
            // counter. One bounded record is reused; the catalog is never held.
            string source = new('x', 1024 * 1024);
            var manifest = InfiniDumpCommand.PublishSnapshot(root, writer =>
            {
                for (int type = 1; type <= 513; type++)
                    writer.WriteLine("{\"type\":" + type + ",\"source\":\"" + source + "\"}");
            }, writer => writer.WriteLine("{\"type\":1}"), DumpTestEnvironment());
            var descriptor = manifest["files"]!["items"]!;
            using var file = File.OpenRead(Path.Combine(root, descriptor["path"]!.GetValue<string>()));
            Equal(true, file.Length > 512L * 1024 * 1024, "a complete catalog can exceed former 512 MiB ceiling");
            Equal(file.Length, descriptor["bytes"]!.GetValue<long>(), "manifest size describes all persisted bytes");
            Equal(513, descriptor["rows"]!.GetValue<int>(), "all streamed rows survive publication");
            Equal(Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant(), descriptor["sha256"]!.GetValue<string>(), "independent streaming hash matches published file");
            Equal(0, Directory.GetDirectories(Path.Combine(root, InfiniDumpCommand.DumpIncompleteDirectory)).Length, "successful payload is promoted, never duplicated");
        }
        finally { Directory.Delete(root, true); }
    }

    private static void RuntimeDumpFailedPublicationPreservesDiagnosticFiles()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-publish-failure-").FullName;
        try
        {
            // Deliberately obstruct just the final pointer replacement. Both
            // files have already been flushed/hashed/promoted when it fails.
            string target = Path.Combine(root, InfiniDumpCommand.DumpManifestName);
            Directory.CreateDirectory(target);
            File.WriteAllText(Path.Combine(target, "sentinel"), "do not replace");
            string? incompletePath = null;
            bool observedPromotionMarker = false;
            bool refused = false;
            try
            {
                InfiniDumpCommand.PublishSnapshot(root, w => w.WriteLine("{\"type\":1}"),
                    w => w.WriteLine("{\"type\":2}"), DumpTestEnvironment(),
                    reportIncompleteDirectory: path =>
                    {
                        incompletePath = path;
                        if (Path.GetFileName(Path.GetDirectoryName(path)) == "runtime_dump_snapshots")
                            observedPromotionMarker = File.Exists(Path.Combine(path, InfiniDumpCommand.DumpIncompleteStateName));
                    });
            }
            catch (IOException) { refused = true; }
            Equal(true, refused, "pointer replacement error is terminal");
            Equal(true, observedPromotionMarker, "durable incomplete marker survives promotion until pointer publication");
            Equal("do not replace", File.ReadAllText(Path.Combine(target, "sentinel")), "failed pointer replacement does not destroy old target");
            Equal(true, incompletePath is not null && Directory.Exists(incompletePath), "promoted files return to an inspectable incomplete attempt");
            Equal(Path.GetFullPath(Path.Combine(root, InfiniDumpCommand.DumpIncompleteDirectory)), Path.GetFullPath(Path.GetDirectoryName(incompletePath!)!), "failed promotion rolls back to incomplete namespace");
            foreach (string name in new[] { "items_runtime_dump.jsonl", "projectiles_runtime_dump.jsonl" })
                Equal(1, File.ReadLines(Path.Combine(incompletePath!, name)).Count(), "failed publication retains every completed payload row");
            var marker = JsonNode.Parse(File.ReadAllText(Path.Combine(incompletePath!, InfiniDumpCommand.DumpIncompleteStateName)))!;
            Equal(false, marker["complete"]!.GetValue<bool>(), "failed publication never claims a valid snapshot");
            Equal(0, Directory.GetFiles(root, ".runtime_dump_manifest.*.tmp").Length, "only expendable pending pointer is cleaned up");
        }
        finally { Directory.Delete(root, true); }
    }

    private static void RuntimeDumpDiskProbeUsesDestinationFilesystem()
    {
        // Read-only Linux mount fixture: no writes outside the test directory.
        // Other platforms still exercise exact free-space refusal via injection.
        if (!OperatingSystem.IsWindows() && Directory.Exists("/dev/shm"))
        {
            long expected = new DriveInfo("/dev/shm").AvailableFreeSpace;
            long observed = InfiniDumpCommand.AvailableDumpDiskBytes("/dev/shm/ifc-probe.jsonl");
            Equal(true, Math.Abs(expected - observed) < 1024 * 1024,
                "disk probe uses destination mount rather than filesystem root");
        }
    }

    private static void RuntimeDumpCurrentVanillaSampleUsesIncrementalExport()
    {
        using var state = new NativeActorState();
        InitializePopulatedParentCapture();
        string root = Directory.CreateTempSubdirectory("ifc-dump-native-sample-").FullName;
        try
        {
            int[] types = { ItemID.CopperPickaxe, ItemID.WoodenSword, ItemID.Wood, ItemID.StoneBlock,
                ItemID.LastPrism, ItemID.TerraBlade, ItemID.NebulaArcanum, ItemID.RainbowCrystalStaff,
                ItemID.FairyQueenRangedItem, ItemID.DaedalusStormbow };
            MethodInfo capture = typeof(InfiniDumpCommand).GetMethod("CaptureItemSnapshotForExport", BindingFlags.NonPublic | BindingFlags.Static)!;
            var timer = Stopwatch.StartNew();
            var export = new RuntimeDumpExport(root, types.Length + 1, 1, index =>
            {
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                return (JsonObject)capture.Invoke(null, new object[] { new Item(types[index - 1]), false })!;
            }, _ => throw new Exception("no projectiles in sample"), DumpTestEnvironment());
            while (!export.Completion.IsCompleted && timer.Elapsed < TimeSpan.FromSeconds(120))
            { GeneratorClient.ParentAnalysis.Pump(); export.Pump(); Thread.Sleep(1); }
            if (!export.Completion.IsCompleted) export.Cancel();
            Equal(true, export.Completion.IsCompleted, "bounded current vanilla panel completes without game or graphics");
            var manifest = export.Completion.GetAwaiter().GetResult();
            var summaries = new JsonArray();
            string path = Path.Combine(root, manifest["files"]!["items"]!["path"]!.GetValue<string>());
            foreach (string line in File.ReadLines(path))
            {
                JsonObject row = JsonNode.Parse(line)!.AsObject();
                Equal(false, line.Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "all analysis references are resolved before disk");
                Equal("not_requested; use /infinidump textures", row["textureMetrics"]!["note"]!.GetValue<string>(), "sample uses current default non-GPU command");
                var graph = row["parentSourceGraph"];
                int duplicates = new[] { row["runtimeFacts"]?["parentSourceGraph"], row["fingerprint"]?["parentSourceGraph"], row["fingerprint"]?["runtimeFacts"]?["parentSourceGraph"] }
                    .Count(value => graph is not null && JsonNode.DeepEquals(graph, value));
                summaries.Add(new JsonObject { ["type"] = row["type"]!.DeepClone(), ["bytes"] = System.Text.Encoding.UTF8.GetByteCount(line) + 1,
                    ["parentSourceGraphBytes"] = graph is null ? 0 : System.Text.Encoding.UTF8.GetByteCount(graph.ToJsonString()),
                    ["identicalAdditionalGraphCopies"] = duplicates });
            }
            Equal(types.Length, summaries.Count, "every requested native definition was published");
            if (Environment.GetEnvironmentVariable("INFINI_DUMP_SAMPLE_OUTPUT") is string rawOutput)
                File.Copy(path, rawOutput, overwrite: true);
            if (Environment.GetEnvironmentVariable("INFINI_DUMP_SCALE_EVIDENCE") is string output)
                File.WriteAllText(output, new JsonObject { ["scope"] = "current source, populated vanilla defaults, incremental dump path; not full catalog or in-game smoke",
                    ["elapsedMs"] = timer.ElapsedMilliseconds, ["rows"] = summaries }.ToJsonString());
        }
        finally { Directory.Delete(root, true); }
    }
}
