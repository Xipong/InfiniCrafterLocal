using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // An explicit offline capture, not a test or a weapon-specific production
    // router. Every case uses the canonical Prepare owner and writes its whole
    // request so model-facing projections can be measured independently.
    private static void CaptureParentContext(string outputDirectory)
    {
        string directory = Path.GetFullPath(outputDirectory);
        Directory.CreateDirectory(directory);
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var report = ParentProfileEnvironment("parent-context-capture");
        report["nativeAssemblySha256"] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(typeof(Player).Assembly.Location))).ToLowerInvariant();
        report["captureMethod"] = "GeneratorClient.Prepare";
        report["measurementScope"] = "Sequential native captures in one process; elapsed time and cumulative managed allocations are diagnostic, not independent cold timings or resident memory.";
        report["model"] = "notRun";
        report["cases"] = new JsonArray();
        try
        {
            foreach (var (name, first, second) in new[] {
                ("LastPrism", ItemID.LastPrism, ItemID.WoodenSword),
                ("TerraBlade", ItemID.TerraBlade, ItemID.WoodenSword),
                ("SpaceGun", ItemID.SpaceGun, ItemID.WoodenSword),
                ("MoltenFury", ItemID.MoltenFury, ItemID.WoodenSword),
                ("StateConditionalBow", 4953, ItemID.DirtBlock),
                ("DaedalusStormbow", ItemID.DaedalusStormbow, ItemID.WoodenSword),
                ("WoodenArrow", ItemID.WoodenArrow, ItemID.WoodenSword),
                ("PlainMaterials", ItemID.Wood, ItemID.StoneBlock),
            })
            {
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                var player = new Player { name = "headless-parent-context" };
                var a = new Item(first);
                var b = new Item(second);
                long allocationsBefore = GC.GetTotalAllocatedBytes(precise: true);
                var timer = Stopwatch.StartNew();
                string json = new GeneratorClient().Prepare(a, b, player).PayloadJson;
                timer.Stop();
                long allocated = GC.GetTotalAllocatedBytes(precise: true) - allocationsBefore;
                Equal(false, json.Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "capture contains no unresolved transfer marker");
                _ = JsonNode.Parse(json)!.AsObject();
                string file = name + ".packet.json";
                File.WriteAllText(Path.Combine(directory, file), json);
                var row = new JsonObject {
                    ["name"] = name, ["parentTypes"] = new JsonArray(first, second),
                    ["path"] = file, ["characters"] = json.Length,
                    ["utf8Bytes"] = Encoding.UTF8.GetByteCount(json),
                    ["sha256"] = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(json))).ToLowerInvariant(),
                    ["elapsedMs"] = timer.Elapsed.TotalMilliseconds, ["allocatedBytes"] = allocated,
                };
                report["cases"]!.AsArray().Add(row);
                Console.WriteLine("CAPTURE " + row.ToJsonString());
            }
        }
        finally
        {
            File.WriteAllText(Path.Combine(directory, "report.json"), report.ToJsonString());
            Console.WriteLine("CAPTURE report=" + Path.Combine(directory, "report.json"));
        }
    }
}
