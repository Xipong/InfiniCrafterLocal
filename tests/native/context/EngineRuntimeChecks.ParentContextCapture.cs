using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.Localization;

internal static partial class EngineRuntimeChecks
{
    private sealed record ParentCaptureCase(string Name, int First, int Second, string Inventory);

    // One capture owner for the legacy small panel and explicit offline panels.
    // This invokes Prepare only, never a provider, world update or gameplay hook.
    private static void CaptureParentContext(string outputDirectory)
        => CaptureParentCases(outputDirectory, new[] {
            new ParentCaptureCase("LastPrism", ItemID.LastPrism, ItemID.WoodenSword, "empty"),
            new ParentCaptureCase("TerraBlade", ItemID.TerraBlade, ItemID.WoodenSword, "empty"),
            new ParentCaptureCase("SpaceGun", ItemID.SpaceGun, ItemID.WoodenSword, "empty"),
            new ParentCaptureCase("MoltenFury", ItemID.MoltenFury, ItemID.WoodenSword, "empty"),
            new ParentCaptureCase("StateConditionalBow", ItemID.FairyQueenRangedItem, ItemID.DirtBlock, "empty"),
            new ParentCaptureCase("DaedalusStormbow", ItemID.DaedalusStormbow, ItemID.WoodenSword, "empty"),
            new ParentCaptureCase("WoodenArrow", ItemID.WoodenArrow, ItemID.WoodenSword, "empty"),
            new ParentCaptureCase("PlainMaterials", ItemID.Wood, ItemID.StoneBlock, "empty"),
        }, null);

    private static ParentCaptureCase[] ReadParentCapturePanel(byte[] bytes)
    {
        if (bytes.Length > 1024 * 1024) throw new ArgumentException("Panel manifest exceeds 1 MiB");
        var panel = JsonNode.Parse(bytes)?.AsObject() ?? throw new ArgumentException("Expected panel object");
        var rows = panel["cases"] as JsonArray ?? throw new ArgumentException("Panel requires cases array");
        if (rows.Count is < 1 or > 256) throw new ArgumentException("Panel requires 1..256 cases");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        int Identity(JsonNode? value)
        {
            string name = value?.GetValue<string>() ?? throw new ArgumentException("ItemID field name required");
            var field = typeof(ItemID).GetField(name, BindingFlags.Public | BindingFlags.Static);
            if (field is null || !field.IsLiteral || field.GetRawConstantValue() is not short and not int)
                throw new ArgumentException("Unknown native ItemID field: " + name);
            int id = Convert.ToInt32(field.GetRawConstantValue());
            if (id <= ItemID.None || id >= ItemID.Count) throw new ArgumentException("ItemID outside vanilla item range: " + name);
            return id;
        }
        return rows.Select(row => {
            string name = row?["case"]?.GetValue<string>() ?? throw new ArgumentException("Case name required");
            if (name.Length is < 1 or > 100 || name.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-' && c != '_') || !names.Add(name))
                throw new ArgumentException("Case names must be unique safe filename labels");
            string inventory = row?["inventory"]?.GetValue<string>() ?? "empty";
            if (inventory is not ("empty" or "mixed_ammo")) throw new ArgumentException("Unsupported explicit inventory fixture: " + inventory);
            return new ParentCaptureCase(name, Identity(row?["itemA"]), Identity(row?["itemB"]), inventory);
        }).ToArray();
    }

    private static void CaptureParentPanel(string manifest, string outputDirectory)
    {
        byte[] bytes = File.ReadAllBytes(manifest);
        var cases = ReadParentCapturePanel(bytes); // Validate all inputs before creating output.
        CaptureParentCases(outputDirectory, cases, bytes);
    }

    private static void CaptureParentCases(string outputDirectory, ParentCaptureCase[] cases, byte[]? manifest, bool deferred = false)
    {
        string directory = Path.GetFullPath(outputDirectory);
        if (Directory.Exists(directory) && Directory.EnumerateFileSystemEntries(directory).Any())
            throw new ArgumentException("Capture output directory must be empty; prior evidence is never overwritten");
        Directory.CreateDirectory(directory);
        string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        using var state = new NativeActorState();
        InitializePopulatedParentCapture();
        var report = ParentProfileEnvironment("parent-context-capture");
        report["nativeAssemblySha256"] = Hash(File.ReadAllBytes(typeof(Player).Assembly.Location));
        report["captureAssemblySha256"] = Hash(File.ReadAllBytes(typeof(GeneratorClient).Assembly.Location));
        report["captureMethod"] = deferred ? "GeneratorClient.PrepareDeferred -> CompleteAnalysis -> PayloadJson" : "GeneratorClient.Prepare";
        report["coldScope"] = "First request after native catalog/localization fixture setup; no source analysis or source pack is primed before the timer. Pristine-cache checks are inside the first request interval. Not game or process startup timing.";
        report["requestedCases"] = cases.Length;
        report["status"] = "incomplete";
        report["measurementScope"] = "Sequential headless native captures with shared process caches. Timings/allocations are diagnostic, not independent cold benchmarks. No world, gameplay loop or full loaded mod roster; source predicates are not observed execution. Source bounds/unknowns remain in each packet.";
        report["model"] = "notRun"; report["providerCalls"] = 0;
        report["fixture"] = new JsonObject { ["language"] = "en-US", ["randomSeedPerCase"] = 91,
            ["samples"] = "vanilla_native_Item_and_Projectile_SetDefaults", ["inventory"] = "Per-case empty or mixed_ammo: slot0 WoodenArrow17,54 FlamingArrow9,55 HolyArrow5,56 MusketBall19,57 RocketI7; no ammo use executed" };
        report["cases"] = new JsonArray();
        if (manifest is not null) { File.WriteAllBytes(Path.Combine(directory, "manifest.json"), manifest); report["manifestSha256"] = Hash(manifest); }
        try
        {
            foreach (var entry in cases)
            {
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                var player = PopulatedParentCapturePlayer(entry.Inventory);
                var a = new Item(entry.First); var b = new Item(entry.Second);
                long allocationsBefore = GC.GetTotalAllocatedBytes(precise: true);
                var timer = Stopwatch.StartNew();
                JsonObject? coldState = report["cases"]!.AsArray().Count == 0 ? RequirePristineParentSourceCaches() : null;
                var client = new GeneratorClient();
                var request = deferred ? client.PrepareDeferred(a, b, player) : client.Prepare(a, b, player);
                double captureMs = timer.Elapsed.TotalMilliseconds;
                ParentProfileTiming timing = default;
                if (deferred)
                    timing = PumpProfileWorker(Task.Run(request.CompleteAnalysis), request.Cancel, 16);
                string json = request.PayloadJson;
                timer.Stop();
                long allocated = GC.GetTotalAllocatedBytes(precise: true) - allocationsBefore;
                Equal(false, json.Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "capture contains no unresolved transfer marker");
                _ = JsonNode.Parse(json)!.AsObject();
                string file = entry.Name + ".packet.json";
                File.WriteAllText(Path.Combine(directory, file), json);
                var row = new JsonObject {
                    ["name"] = entry.Name, ["parentTypes"] = new JsonArray(entry.First, entry.Second),
                    ["parentNames"] = new JsonArray(a.Name, b.Name), ["inventory"] = entry.Inventory,
                    ["path"] = file, ["characters"] = json.Length, ["utf8Bytes"] = Encoding.UTF8.GetByteCount(json),
                    ["sha256"] = Hash(Encoding.UTF8.GetBytes(json)), ["elapsedMs"] = timer.Elapsed.TotalMilliseconds, ["allocatedBytes"] = allocated,
                    ["captureMs"] = captureMs, ["resolveMs"] = timing.ResolveMs,
                    ["pumpMs"] = timing.PumpMs, ["maxPumpMs"] = timing.MaxPumpMs, ["frames"] = timing.Frames,
                    ["pumpIntervalMs"] = deferred ? 16 : 0, ["initialSourceCacheState"] = coldState,
                };
                report["cases"]!.AsArray().Add(row); Console.WriteLine("CAPTURE " + row.ToJsonString());
            }
            report["status"] = "complete";
        }
        finally
        {
            File.WriteAllText(Path.Combine(directory, "report.json"), report.ToJsonString());
            Console.WriteLine("CAPTURE report=" + Path.Combine(directory, "report.json"));
        }
    }

    private static void ParentCapturePanelValidation()
    {
        byte[] Json(string name = "safe_case", string first = "Wood", string inventory = "empty") => Encoding.UTF8.GetBytes(
            new JsonObject { ["cases"] = new JsonArray(new JsonObject { ["case"] = name, ["itemA"] = first, ["itemB"] = "StoneBlock", ["inventory"] = inventory }) }.ToJsonString());
        var parsed = ReadParentCapturePanel(Json());
        Equal(ItemID.Wood, parsed[0].First, "manifest uses native field identity");
        Equal("empty", parsed[0].Inventory, "inventory remains explicit");
        foreach (byte[] bad in new[] { Json("../escape"), Json(first: "UnknownItem"), Json(inventory: "guessed"), Encoding.UTF8.GetBytes("{\"cases\":[]}") })
        {
            bool refused = false; try { ReadParentCapturePanel(bad); } catch (ArgumentException) { refused = true; }
            Equal(true, refused, "invalid manifest is refused before capture/output creation");
        }
    }
}
