using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentEnvironmentReferencesAreConditionalAndFailClosed()
    {
        using var state = new NativeActorState();
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
        foreach (int type in new[] { ItemID.HeartLantern, ItemID.StarinaBottle, ItemID.ChineseLantern })
            Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(new Item(type)), "shared lantern tile cannot borrow unrelated style aura");
        var fakeBanner = new Item(ItemID.Wood) { createTile = TileID.Banners };
        Equal(null, GeneratorClient.CaptureNativeEnvironmentReference(fakeBanner), "banner tile and default strength entry do not prove native banner identity");
        Equal(ItemID.Campfire, campfire.type, "observation does not mutate item identity");
        Equal(0, campfire.placeStyle, "observation does not mutate placement style");
        using var request = System.Text.Json.JsonDocument.Parse(new GeneratorClient().Prepare(
            new Item(ItemID.HeartLantern), campfire, new Player()).PayloadJson);
        var lantern = request.RootElement.GetProperty("itemA");
        foreach (var projection in new[] { lantern, lantern.GetProperty("runtimeFacts"), lantern.GetProperty("fingerprint") })
            Equal(false, projection.TryGetProperty("nativeEnvironmentReference", out _), "unproved shared-tile aura absent from actual request");
        var observed = request.RootElement.GetProperty("itemB");
        Equal(true, observed.TryGetProperty("nativeEnvironmentReference", out _), "proven campfire reference reaches actual request");
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
}
