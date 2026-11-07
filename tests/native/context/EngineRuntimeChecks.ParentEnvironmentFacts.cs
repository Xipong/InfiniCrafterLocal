using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ObjectData;
using Terraria.GameContent;

internal static partial class EngineRuntimeChecks
{
    private static void ParentEnvironmentReferencesAreConditionalAndFailClosed()
    {
        using var state = new NativeActorState();
        using var metadata = new ParentEnvironmentMetadataScope();
        var campfire = new Item(ItemID.Campfire);
        var facts = GeneratorClient.CaptureNativeEnvironmentReference(campfire)!;
        Equal(true, facts is not null, "exact native module enables certified environment reference");
        var aura = facts!["placedTileAuras"]!.AsArray().OfType<JsonObject>().Single();
        Equal("HasCampfire", aura["sceneFlag"]!.GetValue<string>(), "native scanner sets campfire flag");
        Equal(36, aura["tileFrameConditions"]![0]!["value"]!.GetValue<int>(), "active native frame predicate remains explicit");
        Equal(1, aura["regenerationComponent"]!["add"]!.GetValue<int>(), "one regen counter unit, not promised HP per second");
        Equal(null, GeneratorClient.VerifiedNativeEnvironmentReference(campfire, false), "unverified native assembly declines facts");
        Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(new Item(ItemID.Wood)), "unrelated material has no environment claim");
        var changedStyle = new Item(ItemID.Campfire) { placeStyle = 999 };
        Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(changedStyle), "unknown placement style cannot borrow a certified style-zero aura");
        foreach (var (type, flag) in new[] { (ItemID.HeartLantern, "HasHeartLantern"), (ItemID.StarinaBottle, "HasStarInBottle") })
        {
            var shared = GeneratorClient.CaptureNativeEnvironmentReference(new Item(type));
            Equal(true, shared is not null, "certified placement metadata resolves shared lantern style");
            Equal(flag, shared!["placedTileAuras"]![0]!["sceneFlag"]!.GetValue<string>(), "only exact frame-matching aura is emitted");
        }
        Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(new Item(ItemID.ChineseLantern)), "ordinary shared-tile style has no certified aura");
        var heartData = TileObjectData.GetTileData(new Item(ItemID.HeartLantern).createTile, new Item(ItemID.HeartLantern).placeStyle);
        bool originalCustomPlacement = heartData.UsesCustomCanPlace;
        try
        {
            heartData.UsesCustomCanPlace = false;
            Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(new Item(ItemID.HeartLantern)), "legacy placement dispatch cannot borrow TileObject.Place frame arithmetic");
        }
        finally { heartData.UsesCustomCanPlace = originalCustomPlacement; }
        Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(new Item(ItemID.Wood) { createTile = campfire.createTile, placeStyle = 0 }), "mutated item cannot borrow native default tile/style pair");
        var fakeBanner = new Item(ItemID.Wood) { createTile = TileID.Banners };
        Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(fakeBanner), "banner tile and default strength entry do not prove native banner identity");
        // Nonzero styles are admitted by frames/metadata, not tile family or names.
        foreach (int type in new[] { ItemID.CursedCampfire, ItemID.RainbowCampfire, ItemID.Fireplace, ItemID.CatBast })
        {
            var placedItem = new Item(type);
            var placedFacts = GeneratorClient.CaptureNativeEnvironmentReference(placedItem);
            Equal(true, placedFacts is not null, "native nonzero/alternate placement style retains its frame-matching aura: " + type);
        }
        WithPersistenceTilemap((_, __) =>
        {
            foreach (int type in new[] { ItemID.Campfire, ItemID.CursedCampfire, ItemID.RainbowCampfire,
                ItemID.Fireplace, ItemID.CatBast, ItemID.HeartLantern, ItemID.StarinaBottle })
            {
                var source = new Item(type);
                var reference = GeneratorClient.CaptureNativeEnvironmentReference(source)!;
                foreach (JsonObject row in reference["placedTileAuras"]!.AsArray().OfType<JsonObject>())
                foreach (JsonObject variant in row["placementVariants"]!.AsArray().OfType<JsonObject>())
                {
                    for (int x = 39; x < 50; x++)
                    for (int y = 39; y < 50; y++) { var cell = Terraria.Main.tile[x,y]; cell.HasTile = false; }
                    Equal(true, TileObject.Place(new TileObject { xCoord = 40, yCoord = 40, type = source.createTile,
                        style = source.placeStyle, alternate = variant["alternate"]!.GetValue<int>(), random = -1 }), "actual native Place accepts prepared empty CPU cells");
                    foreach (JsonObject cell in variant["matchingTileCells"]!.AsArray().OfType<JsonObject>())
                    {
                        var native = Terraria.Main.tile[40 + cell["column"]!.GetValue<int>(), 40 + cell["row"]!.GetValue<int>()];
                        Equal(true, native.HasTile, "matching placement cell is actually active");
                        Equal(source.createTile, (int)native.TileType, "matching placement cell has source tile type");
                        Equal(cell["frameX"]!.GetValue<int>(), (int)native.TileFrameX, "certified metadata frameX agrees with actual native placement");
                        Equal(cell["frameY"]!.GetValue<int>(), (int)native.TileFrameY, "certified metadata frameY agrees with actual native placement");
                    }
                }
            }
        });
        Equal(ItemID.Campfire, campfire.type, "observation does not mutate item identity");
        Equal(0, campfire.placeStyle, "observation does not mutate placement style");
        using var request = System.Text.Json.JsonDocument.Parse(new GeneratorClient().Prepare(
            new Item(ItemID.HeartLantern), campfire, new Player()).PayloadJson);
        var lantern = request.RootElement.GetProperty("itemA");
        foreach (var projection in new[] { lantern, lantern.GetProperty("runtimeFacts"), lantern.GetProperty("fingerprint") })
            Equal("HasHeartLantern", projection.GetProperty("nativeEnvironmentReference").GetProperty("placedTileAuras")[0].GetProperty("sceneFlag").GetString(), "proved shared-tile aura reaches every actual request projection");
        var observed = request.RootElement.GetProperty("itemB");
        Equal(true, observed.TryGetProperty("nativeEnvironmentReference", out _), "proven campfire reference reaches actual request");
        string? packetPath = System.Environment.GetEnvironmentVariable("INFINI_PARENT_SOURCE_PACKET");
        if (!string.IsNullOrEmpty(packetPath))
            System.IO.File.WriteAllText(packetPath, new GeneratorClient().Prepare(
                new Item(ItemID.HeartLantern), new Item(ItemID.WizardHat), new Player()).PayloadJson);

    }

    private static void ParentBannerRegistryMatchesConditionalNativeComponents()
    {
        using var state = new NativeActorState();
        var previousScene = Terraria.Main.SceneMetrics;
        int previousMode = Terraria.Main.GameMode;
        try
        {
            Terraria.Main.SceneMetrics = new SceneMetrics();
            var player = new Player();
            var target = new NPC(); target.SetDefaults(NPCID.Zombie);
            var other = new NPC(); other.SetDefaults(NPCID.Skeleton);
            int bannerId = Item.NPCtoBanner(target.BannerID());
            var item = new Item(Item.BannerToItem(bannerId));
            var registry = GeneratorClient.CaptureNativeEnvironmentReference(item)!["bannerRegistry"]!;
            Equal(true, registry["enabled"]!.GetValue<bool>(), "real native banner is enabled");
            foreach (int mode in new[] { 0, 1 })
            {
                Terraria.Main.GameMode = mode;
                string prefix = mode == 0 ? "normal" : "expert";
                foreach (bool enabled in new[] { false, true })
                {
                    Terraria.Main.SceneMetrics.NPCBannerBuff[bannerId] = enabled;
                    foreach (var npc in new[] { target, other })
                    {
                        var offense = npc.GetIncomingStrikeModifiers(DamageClass.Generic, 0, false);
                        var defense = new Player.HurtModifiers { IncomingDamageMultiplier = new MultipliableFloat() };
                        player.ApplyBannerOffenseBuff(npc, ref offense);
                        player.ApplyBannerDefenseBuff(npc, ref defense);
                        bool applies = enabled && npc == target;
                        Equal(applies ? registry[prefix + "DamageDealtMultiplier"]!.GetValue<float>() : 1f,
                            offense.TargetDamageMultiplier.Value, "native banner damage requires matching active opponent banner");
                        Equal(applies ? registry[prefix + "DamageReceivedMultiplier"]!.GetValue<float>() : 1f,
                            defense.IncomingDamageMultiplier.Value, "native banner incoming multiplier requires matching active opponent banner");
                    }
                }
            }
        }
        finally { Terraria.Main.SceneMetrics = previousScene; Terraria.Main.GameMode = previousMode; }
    }

    private sealed class ParentEnvironmentMetadataScope : System.IDisposable
    {
        private readonly System.Collections.Generic.Dictionary<System.Reflection.FieldInfo, object?> metadataFields = typeof(TileObjectData)
            .GetFields(System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public)
            .Where(field => !field.IsInitOnly && !field.IsLiteral).ToDictionary(field => field, field => field.GetValue(null));
        private readonly System.Collections.Generic.Dictionary<int, Item> samples = new(ContentSamples.ItemsByType);
        internal ParentEnvironmentMetadataScope()
        {
            TileObjectData.Initialize();
            foreach (int type in new[] { ItemID.Campfire, ItemID.CursedCampfire, ItemID.RainbowCampfire,
                ItemID.HeartLantern, ItemID.StarinaBottle, ItemID.ChineseLantern, ItemID.CatBast, ItemID.Fireplace })
                ContentSamples.ItemsByType[type] = new Item(type);
        }
        public void Dispose()
        {
            foreach (var pair in metadataFields) pair.Key.SetValue(null, pair.Value);
            ContentSamples.ItemsByType.Clear();
            foreach (var pair in samples) ContentSamples.ItemsByType[pair.Key] = pair.Value;
        }
    }
}
