#nullable enable
using System;
using System.Linq;
using Terraria;
using Terraria.ID;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void ExplorationSurvival()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            var generated = NativeUtilityItem("\"potionCooldown\":true,\"autoManaPotion\":true,\"restingRecovery\":true,\"extendedInvulnerability\":true");
            ExplorationPresentation(generated, "potionCooldown", "autoManaPotion", "restingRecovery", "extendedInvulnerability");
            generated.UpdateAccessory(player, true);
            Equal(true, player.pStone && player.manaFlower && player.shinyStone && player.longInvince, "independent native grants");
            int local = Terraria.Main.myPlayer; Terraria.Main.myPlayer = -1;
            try { player.ShadowDodge(); Equal(120, player.immuneTime, "native extended immunity consumer"); }
            finally { Terraria.Main.myPlayer = local; }
            player.ResetEffects();
            Equal(false, player.pStone || player.manaFlower || player.shinyStone || player.longInvince, "native reset removes unequipped grants");
            var absent = NativeUtilityItem("\"defense\":1").Data.ToNetworkJson();
            Equal(false, absent.Contains("potionCooldown", StringComparison.Ordinal), "old wire preserves omission potionCooldown");
            Equal(false, absent.Contains("autoManaPotion", StringComparison.Ordinal), "old wire preserves omission autoManaPotion");
            Equal(false, absent.Contains("restingRecovery", StringComparison.Ordinal), "old wire preserves omission restingRecovery");
            Equal(false, absent.Contains("extendedInvulnerability", StringComparison.Ordinal), "old wire preserves omission extendedInvulnerability");
        });
    }
}
