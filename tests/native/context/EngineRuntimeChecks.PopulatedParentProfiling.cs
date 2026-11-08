using System;
using System.IO;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.Localization;

internal static partial class EngineRuntimeChecks
{
    // Native defaults/localization are fixture input, not source analysis. Use
    // this same setup for synchronous or deferred captures so a missing sample
    // cannot make a supposedly faster request silently omit source-graph bodies.
    private static void InitializePopulatedParentCapture()
    {
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.myPlayer = 0;
        Terraria.Main.player[0] = new Player();
        LanguageManager.Instance.SetLanguage(GameCulture.FromName("en-US"));
        Lang.InitializeLegacyLocalization();
        for (int id = 0; id < ItemID.Count; id++) ContentSamples.ItemsByType[id] = new Item(id);
        for (int id = 0; id < ProjectileID.Count; id++)
        {
            var projectile = new Projectile();
            projectile.SetDefaults(id);
            ContentSamples.ProjectilesByType[id] = projectile;
        }
    }

    private static Player PopulatedParentCapturePlayer(string inventory)
    {
        if (inventory is not ("empty" or "mixed_ammo"))
            throw new ArgumentException("Unsupported explicit inventory fixture: " + inventory);
        var player = new Player { name = "offline-panel40" };
        Terraria.Main.player[0] = player;
        if (inventory == "mixed_ammo")
        {
            player.inventory[0] = new Item(ItemID.WoodenArrow, 17);
            player.inventory[54] = new Item(ItemID.FlamingArrow, 9);
            player.inventory[55] = new Item(ItemID.HolyArrow, 5);
            player.inventory[56] = new Item(ItemID.MusketBall, 19);
            player.inventory[57] = new Item(ItemID.RocketI, 7);
        }
        return player;
    }

    private static JsonObject ParentSourceCacheState()
    {
        const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
        const BindingFlags instances = BindingFlags.Instance | BindingFlags.NonPublic;
        object? Field(string name) => typeof(GeneratorClient).GetField(name, statics)!.GetValue(null);
        int Count(object value) => (int)value.GetType().GetProperty("Count")!.GetValue(value)!;
        int Entries(object owner, string name) => Count(owner.GetType().GetField(name, instances)!.GetValue(owner)!);
        object graph = Field("SharedParentSourceGraphCache")!;
        return new JsonObject
        {
            ["sourceMethods"] = Entries(graph, "entries"),
            ["sourceProjections"] = Entries(graph, "projections"),
            ["attackIlMethods"] = Count(Field("AttackSourceCode")!),
            ["attackPrograms"] = Entries(Field("AttackSourcePrograms")!, "entries"),
            ["csharpDocuments"] = Count(Field("nativeCSharpDocuments")!),
            ["stableCsharpRefusals"] = Count(Field("nativeCSharpStableRefusals")!),
            ["nativeModuleOpened"] = Field("nativeCSharpModule") is not null,
            ["sourcePackReadAttempted"] = (bool)Field("nativeSourcePackReadAttempted")!,
            ["sourcePackOpened"] = Field("nativeSourcePackReader") is not null,
            ["activeAnalysis"] = Field("currentParentAnalysis") is not null,
            ["activeSourceScope"] = Field("activeParentSourceGraphCache") is not null,
        };
    }

    private static JsonObject RequirePristineParentSourceCaches()
    {
        var state = ParentSourceCacheState();
        bool pristine = state.All(pair => pair.Value is JsonValue value
            && (value.TryGetValue<int>(out int count) && count == 0
                || value.TryGetValue<bool>(out bool active) && !active));
        if (!pristine) throw new InvalidOperationException("Benchmark source caches were primed before the first request: " + state.ToJsonString());
        state["pristine"] = true;
        return state;
    }

    private static void ProfilePopulatedParentPanel(string manifest, string outputDirectory)
    {
        byte[] bytes = File.ReadAllBytes(manifest);
        var cases = ReadParentCapturePanel(bytes);
        CaptureParentCases(outputDirectory, cases, bytes, deferred: true);
    }

    // A canonical regression must not leave catalog localization in later checks.
    // Use a private manager and preserve Lang's array identity and contents even
    // when the previous manager has not selected a culture yet.
    private sealed class ParentProfileLocalizationState : IDisposable
    {
        private readonly LanguageManager manager = LanguageManager.Instance;
        private readonly GameCulture? activeCulture = Language.ActiveCulture;
        private readonly CultureInfo culture = CultureInfo.CurrentCulture;
        private readonly CultureInfo uiCulture = CultureInfo.CurrentUICulture;
        private readonly (FieldInfo Field, object? Value, Array? Contents)[] fields = typeof(Lang)
            .GetFields(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
            .Where(field => !field.IsLiteral)
            .Select(field => { object? value = field.GetValue(null); return (field, value, value is Array array ? (Array)array.Clone() : null); })
            .ToArray();

        internal ParentProfileLocalizationState()
            => LanguageManager.Instance = (LanguageManager)Activator.CreateInstance(typeof(LanguageManager), nonPublic: true)!;

        public void Dispose()
        {
            LanguageManager.Instance = manager;
            foreach (var entry in fields)
            {
                if (entry.Value is Array array && entry.Contents is Array contents)
                    Array.Copy(contents, array, array.Length);
                if (!entry.Field.IsInitOnly) entry.Field.SetValue(null, entry.Value);
            }
            CultureInfo.CurrentCulture = culture;
            CultureInfo.CurrentUICulture = uiCulture;
            Equal(true, ReferenceEquals(manager, LanguageManager.Instance), "profiling regression restores manager identity");
            Equal(true, ReferenceEquals(activeCulture, Language.ActiveCulture), "profiling regression restores prior culture, including null");
            foreach (var entry in fields)
            {
                Equal(entry.Value, entry.Field.GetValue(null), "profiling regression restores Lang field: " + entry.Field.Name);
                if (entry.Value is Array array && entry.Contents is Array contents)
                    Equal(true, array.Cast<object?>().SequenceEqual(contents.Cast<object?>()), "profiling regression restores Lang array contents: " + entry.Field.Name);
            }
        }
    }

    private static void PopulatedParentProfilerPreservesSourceAndColdState()
    {
        using var state = new NativeActorState();
        var items = ContentSamples.ItemsByType.ToArray();
        var projectiles = ContentSamples.ProjectilesByType.ToArray();
        using var localization = new ParentProfileLocalizationState();
        try
        {
            Equal<GameCulture?>(null, Language.ActiveCulture, "isolated profiling manager starts without a culture");
            using (var uninitialized = new ParentProfileLocalizationState())
            {
                LanguageManager.Instance.SetLanguage(GameCulture.FromName("en-US"));
                Lang.InitializeLegacyLocalization();
            }
            Equal<GameCulture?>(null, Language.ActiveCulture, "null culture is restored after initialized localization");
            LanguageManager.Instance.SetLanguage(GameCulture.FromName("ru-RU"));
            Lang.InitializeLegacyLocalization();
            var priorCulture = Language.ActiveCulture;
            using (var initialized = new ParentProfileLocalizationState())
            {
                LanguageManager.Instance.SetLanguage(GameCulture.FromName("en-US"));
                Lang.InitializeLegacyLocalization();
            }
            Equal(true, ReferenceEquals(priorCulture, Language.ActiveCulture), "non-null culture is restored after initialized localization");
            GeneratorClient.ParentAnalysis.Invalidate();
            ContentSamples.ItemsByType.Clear();
            ContentSamples.ProjectilesByType.Clear();
            InitializePopulatedParentCapture();
            Equal(ItemID.Count, ContentSamples.ItemsByType.Count, "cold fixture contains every vanilla item sample");
            Equal(ProjectileID.Count, ContentSamples.ProjectilesByType.Count, "cold fixture contains every vanilla projectile sample");
            Equal("en-US", Language.ActiveCulture.Name, "cold fixture has the same explicit language as panel capture");
            Equal(true, RequirePristineParentSourceCaches()["pristine"]!.GetValue<bool>(),
                "native defaults/localization do not prime source caches or open the pack");

            var probes = new[] {
                new ParentCaptureCase("materials", ItemID.Wood, ItemID.StoneBlock, "empty"),
                new ParentCaptureCase("magic", ItemID.NebulaBlaze, ItemID.LastPrism, "mixed_ammo"),
                new ParentCaptureCase("ranged", ItemID.FairyQueenRangedItem, ItemID.DirtBlock, "mixed_ammo"),
                new ParentCaptureCase("summon", ItemID.StardustDragonStaff, ItemID.StardustCellStaff, "mixed_ammo"),
            };
            string Capture(ParentCaptureCase entry, bool deferred)
            {
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                var player = PopulatedParentCapturePlayer(entry.Inventory);
                var first = new Item(entry.First); var second = new Item(entry.Second);
                var client = new GeneratorClient();
                var request = deferred ? client.PrepareDeferred(first, second, player) : client.Prepare(first, second, player);
                if (deferred) PumpProfileWorker(Task.Run(request.CompleteAnalysis), request.Cancel, 16);
                return request.PayloadJson;
            }
            foreach (var entry in probes)
            {
                string synchronous = Capture(entry, false);
                string deferred = Capture(entry, true);
                Equal(synchronous, deferred, "full populated sync/deferred bytes, including source bodies, match: " + entry.Name);
                var packet = JsonNode.Parse(deferred)!;
                Equal(true, packet["itemA"]!["name"]!.GetValue<string>().Length > 0, "localized item name is retained");
                if (entry.Name == "magic")
                    foreach (string parent in new[] { "itemA", "itemB" })
                        Equal(true, packet[parent]!["parentSourceGraph"]!["nodes"]!.AsArray().Count > 0,
                            "populated magic probe cannot pass with an omitted parent graph");
            }
            bool refused = false;
            try { RequirePristineParentSourceCaches(); }
            catch (InvalidOperationException) { refused = true; }
            Equal(true, refused, "benchmark refuses to label already primed source state as cold");
        }
        finally
        {
            GeneratorClient.ParentAnalysis.Invalidate();
            ContentSamples.ItemsByType.Clear();
            foreach (var pair in items) ContentSamples.ItemsByType[pair.Key] = pair.Value;
            ContentSamples.ProjectilesByType.Clear();
            foreach (var pair in projectiles) ContentSamples.ProjectilesByType[pair.Key] = pair.Value;

        }
    }
}
