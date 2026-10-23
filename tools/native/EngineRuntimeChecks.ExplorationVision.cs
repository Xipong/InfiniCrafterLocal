#nullable enable
using System;
using System.Linq;
using Terraria;
using Terraria.ID;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void ExplorationVision()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            var generated = NativeUtilityItem("\"treasureVision\":true,\"dangerVision\":true,\"creatureVision\":true,\"nightVision\":true");
            ExplorationPresentation(generated, "treasureVision", "dangerVision", "creatureVision", "nightVision");
            generated.UpdateAccessory(player, true);
            Equal(true, player.findTreasure && player.dangerSense && player.detectCreature && player.nightVision, "independent native grants");
            player.ResetEffects();
            Equal(false, player.findTreasure || player.dangerSense || player.detectCreature || player.nightVision, "native reset removes unequipped grants");
            var absent = NativeUtilityItem("\"defense\":1").Data.ToNetworkJson();
            Equal(false, absent.Contains("treasureVision", StringComparison.Ordinal), "old wire preserves omission treasureVision");
            Equal(false, absent.Contains("dangerVision", StringComparison.Ordinal), "old wire preserves omission dangerVision");
            Equal(false, absent.Contains("creatureVision", StringComparison.Ordinal), "old wire preserves omission creatureVision");
            Equal(false, absent.Contains("nightVision", StringComparison.Ordinal), "old wire preserves omission nightVision");
        });
    }
}
