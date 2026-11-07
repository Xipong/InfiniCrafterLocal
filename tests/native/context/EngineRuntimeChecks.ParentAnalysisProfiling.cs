using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Reconstructed from retained profiler snippets after workspace recovery.
    // This file is not claimed to be byte-identical to the earlier profiler.
    // Optional headless observations only: no game, HTTP, model or GPU startup.
    // Deliberately unrolled IL models a broad mod hook. It is read, never run.
    private sealed class HeavyGlobalItem : GlobalItem
    {
        public override void UpdateInventory(Item item, Player player)
        {
            if (item.type == 1) player.statDefense += 1;
            if (item.type == 2) player.statDefense += 2;
            if (item.type == 3) player.statDefense += 3;
            if (item.type == 4) player.statDefense += 4;
            if (item.type == 5) player.statDefense += 5;
            if (item.type == 6) player.statDefense += 6;
            if (item.type == 7) player.statDefense += 7;
            if (item.type == 8) player.statDefense += 1;
            if (item.type == 9) player.statDefense += 2;
            if (item.type == 10) player.statDefense += 3;
            if (item.type == 11) player.statDefense += 4;
            if (item.type == 12) player.statDefense += 5;
            if (item.type == 13) player.statDefense += 6;
            if (item.type == 14) player.statDefense += 7;
            if (item.type == 15) player.statDefense += 1;
            if (item.type == 16) player.statDefense += 2;
            if (item.type == 17) player.statDefense += 3;
            if (item.type == 18) player.statDefense += 4;
            if (item.type == 19) player.statDefense += 5;
            if (item.type == 20) player.statDefense += 6;
            if (item.type == 21) player.statDefense += 7;
            if (item.type == 22) player.statDefense += 1;
            if (item.type == 23) player.statDefense += 2;
            if (item.type == 24) player.statDefense += 3;
            if (item.type == 25) player.statDefense += 4;
            if (item.type == 26) player.statDefense += 5;
            if (item.type == 27) player.statDefense += 6;
            if (item.type == 28) player.statDefense += 7;
            if (item.type == 29) player.statDefense += 1;
            if (item.type == 30) player.statDefense += 2;
            if (item.type == 31) player.statDefense += 3;
            if (item.type == 32) player.statDefense += 4;
            if (item.type == 33) player.statDefense += 5;
            if (item.type == 34) player.statDefense += 6;
            if (item.type == 35) player.statDefense += 7;
            if (item.type == 36) player.statDefense += 1;
            if (item.type == 37) player.statDefense += 2;
            if (item.type == 38) player.statDefense += 3;
            if (item.type == 39) player.statDefense += 4;
            if (item.type == 40) player.statDefense += 5;
            if (item.type == 41) player.statDefense += 6;
            if (item.type == 42) player.statDefense += 7;
            if (item.type == 43) player.statDefense += 1;
            if (item.type == 44) player.statDefense += 2;
            if (item.type == 45) player.statDefense += 3;
            if (item.type == 46) player.statDefense += 4;
            if (item.type == 47) player.statDefense += 5;
            if (item.type == 48) player.statDefense += 6;
            if (item.type == 49) player.statDefense += 7;
            if (item.type == 50) player.statDefense += 1;
            if (item.type == 51) player.statDefense += 2;
            if (item.type == 52) player.statDefense += 3;
            if (item.type == 53) player.statDefense += 4;
            if (item.type == 54) player.statDefense += 5;
            if (item.type == 55) player.statDefense += 6;
            if (item.type == 56) player.statDefense += 7;
            if (item.type == 57) player.statDefense += 1;
            if (item.type == 58) player.statDefense += 2;
            if (item.type == 59) player.statDefense += 3;
            if (item.type == 60) player.statDefense += 4;
            if (item.type == 61) player.statDefense += 5;
            if (item.type == 62) player.statDefense += 6;
            if (item.type == 63) player.statDefense += 7;
            if (item.type == 64) player.statDefense += 1;
            if (item.type == 65) player.statDefense += 2;
            if (item.type == 66) player.statDefense += 3;
            if (item.type == 67) player.statDefense += 4;
            if (item.type == 68) player.statDefense += 5;
            if (item.type == 69) player.statDefense += 6;
            if (item.type == 70) player.statDefense += 7;
            if (item.type == 71) player.statDefense += 1;
            if (item.type == 72) player.statDefense += 2;
            if (item.type == 73) player.statDefense += 3;
            if (item.type == 74) player.statDefense += 4;
            if (item.type == 75) player.statDefense += 5;
            if (item.type == 76) player.statDefense += 6;
            if (item.type == 77) player.statDefense += 7;
            if (item.type == 78) player.statDefense += 1;
            if (item.type == 79) player.statDefense += 2;
            if (item.type == 80) player.statDefense += 3;
            if (item.type == 81) player.statDefense += 4;
            if (item.type == 82) player.statDefense += 5;
            if (item.type == 83) player.statDefense += 6;
            if (item.type == 84) player.statDefense += 7;
            if (item.type == 85) player.statDefense += 1;
            if (item.type == 86) player.statDefense += 2;
            if (item.type == 87) player.statDefense += 3;
            if (item.type == 88) player.statDefense += 4;
            if (item.type == 89) player.statDefense += 5;
            if (item.type == 90) player.statDefense += 6;
            if (item.type == 91) player.statDefense += 7;
            if (item.type == 92) player.statDefense += 1;
            if (item.type == 93) player.statDefense += 2;
            if (item.type == 94) player.statDefense += 3;
            if (item.type == 95) player.statDefense += 4;
            if (item.type == 96) player.statDefense += 5;
            if (item.type == 97) player.statDefense += 6;
            if (item.type == 98) player.statDefense += 7;
            if (item.type == 99) player.statDefense += 1;
            if (item.type == 100) player.statDefense += 2;
            if (item.type == 101) player.statDefense += 3;
            if (item.type == 102) player.statDefense += 4;
            if (item.type == 103) player.statDefense += 5;
            if (item.type == 104) player.statDefense += 6;
            if (item.type == 105) player.statDefense += 7;
            if (item.type == 106) player.statDefense += 1;
            if (item.type == 107) player.statDefense += 2;
            if (item.type == 108) player.statDefense += 3;
            if (item.type == 109) player.statDefense += 4;
            if (item.type == 110) player.statDefense += 5;
            if (item.type == 111) player.statDefense += 6;
            if (item.type == 112) player.statDefense += 7;
            if (item.type == 113) player.statDefense += 1;
            if (item.type == 114) player.statDefense += 2;
            if (item.type == 115) player.statDefense += 3;
            if (item.type == 116) player.statDefense += 4;
            if (item.type == 117) player.statDefense += 5;
            if (item.type == 118) player.statDefense += 6;
            if (item.type == 119) player.statDefense += 7;
            if (item.type == 120) player.statDefense += 1;
            if (item.type == 121) player.statDefense += 2;
            if (item.type == 122) player.statDefense += 3;
            if (item.type == 123) player.statDefense += 4;
            if (item.type == 124) player.statDefense += 5;
            if (item.type == 125) player.statDefense += 6;
            if (item.type == 126) player.statDefense += 7;
            if (item.type == 127) player.statDefense += 1;
            if (item.type == 128) player.statDefense += 2;
            if (item.type == 129) player.statDefense += 3;
            if (item.type == 130) player.statDefense += 4;
            if (item.type == 131) player.statDefense += 5;
            if (item.type == 132) player.statDefense += 6;
            if (item.type == 133) player.statDefense += 7;
            if (item.type == 134) player.statDefense += 1;
            if (item.type == 135) player.statDefense += 2;
            if (item.type == 136) player.statDefense += 3;
            if (item.type == 137) player.statDefense += 4;
            if (item.type == 138) player.statDefense += 5;
            if (item.type == 139) player.statDefense += 6;
            if (item.type == 140) player.statDefense += 7;
            if (item.type == 141) player.statDefense += 1;
            if (item.type == 142) player.statDefense += 2;
            if (item.type == 143) player.statDefense += 3;
            if (item.type == 144) player.statDefense += 4;
            if (item.type == 145) player.statDefense += 5;
            if (item.type == 146) player.statDefense += 6;
            if (item.type == 147) player.statDefense += 7;
            if (item.type == 148) player.statDefense += 1;
            if (item.type == 149) player.statDefense += 2;
            if (item.type == 150) player.statDefense += 3;
            if (item.type == 151) player.statDefense += 4;
            if (item.type == 152) player.statDefense += 5;
            if (item.type == 153) player.statDefense += 6;
            if (item.type == 154) player.statDefense += 7;
            if (item.type == 155) player.statDefense += 1;
            if (item.type == 156) player.statDefense += 2;
            if (item.type == 157) player.statDefense += 3;
            if (item.type == 158) player.statDefense += 4;
            if (item.type == 159) player.statDefense += 5;
            if (item.type == 160) player.statDefense += 6;
            if (item.type == 161) player.statDefense += 7;
            if (item.type == 162) player.statDefense += 1;
            if (item.type == 163) player.statDefense += 2;
            if (item.type == 164) player.statDefense += 3;
            if (item.type == 165) player.statDefense += 4;
            if (item.type == 166) player.statDefense += 5;
            if (item.type == 167) player.statDefense += 6;
            if (item.type == 168) player.statDefense += 7;
            if (item.type == 169) player.statDefense += 1;
            if (item.type == 170) player.statDefense += 2;
            if (item.type == 171) player.statDefense += 3;
            if (item.type == 172) player.statDefense += 4;
            if (item.type == 173) player.statDefense += 5;
            if (item.type == 174) player.statDefense += 6;
            if (item.type == 175) player.statDefense += 7;
            if (item.type == 176) player.statDefense += 1;
            if (item.type == 177) player.statDefense += 2;
            if (item.type == 178) player.statDefense += 3;
            if (item.type == 179) player.statDefense += 4;
            if (item.type == 180) player.statDefense += 5;
            if (item.type == 181) player.statDefense += 6;
            if (item.type == 182) player.statDefense += 7;
            if (item.type == 183) player.statDefense += 1;
            if (item.type == 184) player.statDefense += 2;
            if (item.type == 185) player.statDefense += 3;
            if (item.type == 186) player.statDefense += 4;
            if (item.type == 187) player.statDefense += 5;
            if (item.type == 188) player.statDefense += 6;
            if (item.type == 189) player.statDefense += 7;
            if (item.type == 190) player.statDefense += 1;
            if (item.type == 191) player.statDefense += 2;
            if (item.type == 192) player.statDefense += 3;
            if (item.type == 193) player.statDefense += 4;
            if (item.type == 194) player.statDefense += 5;
            if (item.type == 195) player.statDefense += 6;
            if (item.type == 196) player.statDefense += 7;
            if (item.type == 197) player.statDefense += 1;
            if (item.type == 198) player.statDefense += 2;
            if (item.type == 199) player.statDefense += 3;
            if (item.type == 200) player.statDefense += 4;
            if (item.type == 201) player.statDefense += 5;
            if (item.type == 202) player.statDefense += 6;
            if (item.type == 203) player.statDefense += 7;
            if (item.type == 204) player.statDefense += 1;
            if (item.type == 205) player.statDefense += 2;
            if (item.type == 206) player.statDefense += 3;
            if (item.type == 207) player.statDefense += 4;
            if (item.type == 208) player.statDefense += 5;
            if (item.type == 209) player.statDefense += 6;
            if (item.type == 210) player.statDefense += 7;
            if (item.type == 211) player.statDefense += 1;
            if (item.type == 212) player.statDefense += 2;
            if (item.type == 213) player.statDefense += 3;
            if (item.type == 214) player.statDefense += 4;
            if (item.type == 215) player.statDefense += 5;
            if (item.type == 216) player.statDefense += 6;
            if (item.type == 217) player.statDefense += 7;
            if (item.type == 218) player.statDefense += 1;
            if (item.type == 219) player.statDefense += 2;
            if (item.type == 220) player.statDefense += 3;
            if (item.type == 221) player.statDefense += 4;
            if (item.type == 222) player.statDefense += 5;
            if (item.type == 223) player.statDefense += 6;
            if (item.type == 224) player.statDefense += 7;
            if (item.type == 225) player.statDefense += 1;
            if (item.type == 226) player.statDefense += 2;
            if (item.type == 227) player.statDefense += 3;
            if (item.type == 228) player.statDefense += 4;
            if (item.type == 229) player.statDefense += 5;
            if (item.type == 230) player.statDefense += 6;
            if (item.type == 231) player.statDefense += 7;
            if (item.type == 232) player.statDefense += 1;
            if (item.type == 233) player.statDefense += 2;
            if (item.type == 234) player.statDefense += 3;
            if (item.type == 235) player.statDefense += 4;
            if (item.type == 236) player.statDefense += 5;
            if (item.type == 237) player.statDefense += 6;
            if (item.type == 238) player.statDefense += 7;
            if (item.type == 239) player.statDefense += 1;
            if (item.type == 240) player.statDefense += 2;
            if (item.type == 241) player.statDefense += 3;
            if (item.type == 242) player.statDefense += 4;
            if (item.type == 243) player.statDefense += 5;
            if (item.type == 244) player.statDefense += 6;
            if (item.type == 245) player.statDefense += 7;
            if (item.type == 246) player.statDefense += 1;
            if (item.type == 247) player.statDefense += 2;
            if (item.type == 248) player.statDefense += 3;
            if (item.type == 249) player.statDefense += 4;
            if (item.type == 250) player.statDefense += 5;
            if (item.type == 251) player.statDefense += 6;
            if (item.type == 252) player.statDefense += 7;
            if (item.type == 253) player.statDefense += 1;
            if (item.type == 254) player.statDefense += 2;
            if (item.type == 255) player.statDefense += 3;
            if (item.type == 256) player.statDefense += 4;
            if (item.type == 257) player.statDefense += 5;
            if (item.type == 258) player.statDefense += 6;
            if (item.type == 259) player.statDefense += 7;
            if (item.type == 260) player.statDefense += 1;
            if (item.type == 261) player.statDefense += 2;
            if (item.type == 262) player.statDefense += 3;
            if (item.type == 263) player.statDefense += 4;
            if (item.type == 264) player.statDefense += 5;
            if (item.type == 265) player.statDefense += 6;
            if (item.type == 266) player.statDefense += 7;
            if (item.type == 267) player.statDefense += 1;
            if (item.type == 268) player.statDefense += 2;
            if (item.type == 269) player.statDefense += 3;
            if (item.type == 270) player.statDefense += 4;
            if (item.type == 271) player.statDefense += 5;
            if (item.type == 272) player.statDefense += 6;
            if (item.type == 273) player.statDefense += 7;
            if (item.type == 274) player.statDefense += 1;
            if (item.type == 275) player.statDefense += 2;
            if (item.type == 276) player.statDefense += 3;
            if (item.type == 277) player.statDefense += 4;
            if (item.type == 278) player.statDefense += 5;
            if (item.type == 279) player.statDefense += 6;
            if (item.type == 280) player.statDefense += 7;
            if (item.type == 281) player.statDefense += 1;
            if (item.type == 282) player.statDefense += 2;
            if (item.type == 283) player.statDefense += 3;
            if (item.type == 284) player.statDefense += 4;
            if (item.type == 285) player.statDefense += 5;
            if (item.type == 286) player.statDefense += 6;
            if (item.type == 287) player.statDefense += 7;
            if (item.type == 288) player.statDefense += 1;
            if (item.type == 289) player.statDefense += 2;
            if (item.type == 290) player.statDefense += 3;
            if (item.type == 291) player.statDefense += 4;
            if (item.type == 292) player.statDefense += 5;
            if (item.type == 293) player.statDefense += 6;
            if (item.type == 294) player.statDefense += 7;
            if (item.type == 295) player.statDefense += 1;
            if (item.type == 296) player.statDefense += 2;
            if (item.type == 297) player.statDefense += 3;
            if (item.type == 298) player.statDefense += 4;
            if (item.type == 299) player.statDefense += 5;
            if (item.type == 300) player.statDefense += 6;
            if (item.type == 301) player.statDefense += 7;
            if (item.type == 302) player.statDefense += 1;
            if (item.type == 303) player.statDefense += 2;
            if (item.type == 304) player.statDefense += 3;
            if (item.type == 305) player.statDefense += 4;
            if (item.type == 306) player.statDefense += 5;
            if (item.type == 307) player.statDefense += 6;
            if (item.type == 308) player.statDefense += 7;
            if (item.type == 309) player.statDefense += 1;
            if (item.type == 310) player.statDefense += 2;
            if (item.type == 311) player.statDefense += 3;
            if (item.type == 312) player.statDefense += 4;
            if (item.type == 313) player.statDefense += 5;
            if (item.type == 314) player.statDefense += 6;
            if (item.type == 315) player.statDefense += 7;
            if (item.type == 316) player.statDefense += 1;
            if (item.type == 317) player.statDefense += 2;
            if (item.type == 318) player.statDefense += 3;
            if (item.type == 319) player.statDefense += 4;
            if (item.type == 320) player.statDefense += 5;
        }
    }

    // Reconstructed fixture setup for the source-analysis benchmark only.
    // The craft benchmark does not instantiate a catalog before its first craft.
    private sealed class ParentProfileCatalog : IDisposable
    {
        private readonly KeyValuePair<int, Item>[] saved = ContentSamples.ItemsByType.ToArray();
        internal ParentProfileCatalog()
        {
            var timer = Stopwatch.StartNew();
            int unavailable = 0;
            for (int id = 1; id < ItemLoader.ItemCount; id++)
            {
                try { ContentSamples.ItemsByType[id] = new Item(id); }
                catch { unavailable++; }
            }
            Console.WriteLine(FormattableString.Invariant($"PROFILE fixture_catalog setup_ms={timer.Elapsed.TotalMilliseconds:F3} registered={ContentSamples.ItemsByType.Count} unavailable={unavailable}; item defaults are warmed by fixture setup"));
        }
        public void Dispose()
        {
            ContentSamples.ItemsByType.Clear();
            foreach (var pair in saved) ContentSamples.ItemsByType[pair.Key] = pair.Value;
        }
    }

    private readonly record struct ParentProfileTiming(double ResolveMs, double PumpMs, double MaxPumpMs, int Frames);

    private static ParentProfileTiming PumpProfileWorker(Task worker, Action cancel, int interval)
    {
        var timer = Stopwatch.StartNew();
        int frames = 0;
        double pumpMs = 0, maxPump = 0;
        try
        {
            while (!worker.IsCompleted)
            {
                if (timer.Elapsed >= TimeSpan.FromSeconds(90))
                    throw new TimeoutException("Headless parent profiling exceeded its 90-second deadlock guard.");
                var pump = Stopwatch.StartNew();
                GeneratorClient.ParentAnalysis.Pump();
                double ms = pump.Elapsed.TotalMilliseconds;
                pumpMs += ms; maxPump = Math.Max(maxPump, ms); frames++;
                if (!worker.IsCompleted) Thread.Sleep(interval);
            }
            worker.GetAwaiter().GetResult();
            return new(timer.Elapsed.TotalMilliseconds, pumpMs, maxPump, frames);
        }
        finally
        {
            // Cancel before joining: a queued main-thread request must not be
            // left waiting while its analysis or native fixture is disposed.
            if (!worker.IsCompleted)
            {
                cancel();
                try { worker.GetAwaiter().GetResult(); }
                catch (OperationCanceledException) { }
            }
            GeneratorClient.ParentAnalysis.Pump();
        }
    }

    private static string ParentProfileDirectory(string family)
    {
        string directory = Path.GetFullPath(Path.Combine("artifacts", "parent-profiling",
            family + "-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmssfff") + "-" + Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(directory);
        return directory;
    }

    private static JsonObject ParentProfileObservation(string name, double captureMs,
        ParentProfileTiming timing, int interval, string json, string directory)
    {
        Equal(false, json.Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "profile output contains no unresolved transfer marker");
        string path = Path.Combine(directory, name + ".json");
        byte[] bytes = Encoding.UTF8.GetBytes(json);
        File.WriteAllBytes(path, bytes);
        var result = new JsonObject
        {
            ["case"] = name, ["captureMs"] = captureMs, ["resolveMs"] = timing.ResolveMs,
            ["pumpMs"] = timing.PumpMs, ["maxPumpMs"] = timing.MaxPumpMs,
            ["frames"] = timing.Frames, ["pumpIntervalMs"] = interval,
            ["characters"] = json.Length, ["jsonPath"] = path,
            ["utf8Bytes"] = bytes.Length,
            ["sha256"] = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()
        };
        Console.WriteLine("PROFILE " + result.ToJsonString());
        return result;
    }

    private static JsonObject ParentProfileEnvironment(string kind) => new()
    {
        ["kind"] = kind,
        ["scope"] = "Headless native harness only; no Terraria world/game/GPU/HTTP. Native hooks may execute during defaults. Content/mod rosters are those actually available in this harness, not a complete Calamity installation. Pump frames are simulated waits, not measured game FPS.",
        ["runtimeVersion"] = Environment.Version.ToString(),
        ["nativeMvid"] = typeof(Player).Module.ModuleVersionId.ToString(),
        ["harnessMvid"] = typeof(EngineRuntimeChecks).Module.ModuleVersionId.ToString(),
        ["itemCount"] = ItemLoader.ItemCount,
        ["projectileCount"] = ProjectileLoader.ProjectileCount,
        ["itemSampleCount"] = ContentSamples.ItemsByType.Count,
        ["projectileSampleCount"] = ContentSamples.ProjectilesByType.Count,
        ["tooltipContext"] = "headless_dedicated_literal_not_local_client_tooltip_hooks"
    };

    private static void ParentAnalysisFrameProfiling()
    {
        using var state = new NativeActorState();
        using var catalog = new ParentProfileCatalog();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        string directory = ParentProfileDirectory("analysis");
        var report = ParentProfileEnvironment("source-analysis");
        report["fixtureSetup"] = "Registered item defaults were created before timings; this is not a first-craft cold measurement.";
        var measurements = new JsonArray(); report["measurements"] = measurements;
        try
        {
            void Measure(string name, Func<JsonObject> capture, int interval)
            {
                using var cancellation = new CancellationTokenSource();
                using var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token);
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                var timer = Stopwatch.StartNew(); JsonObject root;
                using (analysis.Enter()) root = capture();
                double captureMs = timer.Elapsed.TotalMilliseconds;
                var worker = Task.Run(() => analysis.Resolve(root));
                ParentProfileTiming timing = PumpProfileWorker(worker, cancellation.Cancel, interval);
                string json = worker.GetAwaiter().GetResult()!.ToJsonString();
                measurements.Add(ParentProfileObservation(name + "-" + interval, captureMs, timing, interval, json, directory));
            }
            for (int run = 0; run < 3; run++)
                Measure("heavy-shared-hook-" + run, () => {
                    Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
                    object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
                    var analysis = (GeneratorClient.ParentAnalysis)typeof(GeneratorClient).GetField("currentParentAnalysis", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
                    return analysis.Defer(() => {
                        graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new object[]
                            { typeof(HeavyGlobalItem), typeof(GlobalItem), new HashSet<string> { "UpdateInventory" }, "attached_GlobalItem", "event_signature" });
                        return (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
                    });
                }, 1);
            foreach (int interval in new[] { 1, 16 })
            {
                foreach (int type in new[] { ItemID.Wood, ItemID.MiningPotion, ItemID.TerraBlade, ItemID.Boomstick })
                    Measure("item-" + type, () => GeneratorClient.ToWireItem(new Item(type)), interval);
                foreach (int count in new[] { 1, 32 })
                    Measure("repeated-buff-" + count, () => {
                        var values = new JsonArray();
                        for (int i = 0; i < count; i++) values.Add(new JsonObject { ["buffId"] = BuffID.Poisoned, ["receiver"] = "npc" });
                        return GeneratorClient.CaptureParentSourceGraph(new Item(ItemID.Wood), new JsonObject { ["values"] = values });
                    }, interval);
            }
        }
        finally
        {
            string path = Path.Combine(directory, "report.json");
            File.WriteAllText(path, report.ToJsonString());
            Console.WriteLine("PROFILE report=" + path);
        }
    }

    private static void ParentCraftFrameProfiling(string scenario)
    {
        // One mode per fresh executable invocation. No prior dump, synthetic
        // source projection, or full Item catalog setup warms the first request.
        (int first, int second) = scenario switch
        {
            "plain" => (ItemID.Wood, ItemID.StoneBlock),
            "mixed" => (ItemID.TerraBlade, ItemID.MiningPotion),
            "ammo" => (ItemID.Boomstick, ItemID.MoltenFury),
            "nebula-prism" => (ItemID.NebulaBlaze, ItemID.LastPrism),
            "eventide" => (ItemID.FairyQueenRangedItem, ItemID.WoodenArrow),
            _ => throw new ArgumentException("Expected --profile-parent-craft plain|mixed|ammo|nebula-prism|eventide.")
        };
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        string directory = ParentProfileDirectory("craft-" + scenario);
        var report = ParentProfileEnvironment("actual-deferred-craft");
        report["scenario"] = scenario;
        report["parentTypes"] = new JsonArray(first, second);
        report["parentLabels"] = scenario switch
        {
            "plain" => "Wood + Stone Block (control)",
            "mixed" => "Terra Blade + Mining Potion",
            "ammo" => "Boomstick + Molten Fury",
            "nebula-prism" => "Nebula Blaze + Last Prism",
            "eventide" => "Eventide + Wooden Arrow",
            _ => scenario
        };
        report["allocationScope"] = "GC.GetTotalAllocatedBytes(precise:true) process-wide delta across PrepareDeferred, Task.Run(CompleteAnalysis), 16ms Pump/waits and PayloadJson access; includes worker/main/runtime observer overhead, excludes parent construction, invalidation, parity parsing, hashing and evidence writes. Cumulative managed allocation, not retained/peak RAM. No forced GC.";
        report["gcScope"] = "Process-wide GC.CollectionCount generation deltas over the same pipeline interval; prior-phase garbage can be collected here.";
        report["coldScope"] = "First PrepareDeferred in this executable invocation, after native harness and parent Item/Player construction. Not process startup timing. No dump or full catalog setup.";
        report["resetScope"] = "ParentAnalysis.Invalidate clears shared source/attack caches; native certificate Lazy values and CLR/JIT state remain warm. Source-cache-reset is not a fresh process.";
        var measurements = new JsonArray(); report["measurements"] = measurements;
        var client = new GeneratorClient();
        JsonNode? initial = null;
        const int interval = 16;
        try
        {
            foreach (string phase in new[] { "cold-first-request", "warm-1", "warm-2", "source-cache-reset" })
            {
                if (phase == "source-cache-reset") GeneratorClient.ParentAnalysis.Invalidate();
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                var a = new Item(first); var b = new Item(second);
                var player = new Player { name = "headless-parent-profile" };
                // These real input objects are constructed before the timer,
                // matching a craft whose parent items already exist in inventory.
                int gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2);
                long allocatedBefore = GC.GetTotalAllocatedBytes(precise: true);
                var timer = Stopwatch.StartNew();
                var request = client.PrepareDeferred(a, b, player);
                double captureMs = timer.Elapsed.TotalMilliseconds;
                var worker = Task.Run(request.CompleteAnalysis);
                ParentProfileTiming timing = PumpProfileWorker(worker, request.Cancel, interval);
                string json = request.PayloadJson;
                double wallMs = timer.Elapsed.TotalMilliseconds;
                long allocatedBytes = GC.GetTotalAllocatedBytes(precise: true) - allocatedBefore;
                int collections0 = GC.CollectionCount(0) - gen0;
                int collections1 = GC.CollectionCount(1) - gen1;
                int collections2 = GC.CollectionCount(2) - gen2;
                JsonNode parsed = JsonNode.Parse(json)!;
                initial ??= parsed.DeepClone();
                JsonObject observation = ParentProfileObservation(phase, captureMs, timing, interval, json, directory);
                observation["wallMs"] = wallMs;
                observation["totalAllocatedBytes"] = allocatedBytes;
                observation["gcCollections"] = new JsonArray(collections0, collections1, collections2);
                observation["equalToFirstRequest"] = JsonNode.DeepEquals(initial, parsed);
                measurements.Add(observation);
                // Equality is reported, not forced: if a mod changes defaults or
                // source registration, the full differing payload remains saved.
                Console.WriteLine("PROFILE parity=" + observation["equalToFirstRequest"]!.ToJsonString());
            }
        }
        finally
        {
            string path = Path.Combine(directory, "report.json");
            File.WriteAllText(path, report.ToJsonString());
            Console.WriteLine("PROFILE report=" + path);
        }
    }
}
