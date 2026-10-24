#nullable enable
using System;
using System.Linq;
using Terraria;
using Terraria.ID;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void ExplorationFishing()
    {
        WithPlayer((player, _) => {
            player.ResetEffects(); player.fishingSkill = 7;
            var generated = NativeUtilityItem("\"fishingPower\":25,\"fishingLine\":true,\"lavaFishing\":true,\"fishingSonar\":true,\"fishingCrates\":true");
            ExplorationPresentation(generated, "fishingPower", "fishingLine", "lavaFishing", "fishingSonar", "fishingCrates");
            generated.UpdateAccessory(player, true);
            Equal(32, player.fishingSkill, "authored fishing points add to native state");
            Equal(true, player.accFishingLine && player.accLavaFishing && player.sonarPotion && player.cratePotion, "independent grants reach native catch consumers");
            Equal(false, player.lavaImmune, "lava fishing never grants lava immunity");
            player.inventory[0] = new Item(ItemID.WoodFishingPole); player.inventory[1] = new Item(ItemID.Worm, 5);
            var conditions = player.GetFishingConditions();
            Equal((int)((conditions.BaitPower + conditions.PolePower + 32) * conditions.LevelMultipliers), conditions.FinalFishingLevel, "native fishing power consumer");
            player.ResetEffects();
            Equal(false, player.accFishingLine || player.accLavaFishing || player.sonarPotion || player.cratePotion, "grants expire on native reset");
            Equal(0, player.fishingSkill, "power bonus does not persist");
            foreach (string invalid in new[] { "null", "true", "101", "-1", "1.5" }) {
                bool refused = false; try { NativeUtilityItem("\"fishingPower\":" + invalid); } catch (InvalidOperationException) { refused = true; }
                Equal(true, refused, "invalid fishing power refuses before native application");
            }
            var absent = NativeUtilityItem("\"defense\":1").Data.ToNetworkJson();
            Equal(false, absent.Contains("fishingPower", StringComparison.Ordinal), "old definitions retain absent optional fields");
        });
    }
}
