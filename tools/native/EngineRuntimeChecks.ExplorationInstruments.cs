#nullable enable
using System;
using System.Linq;
using Terraria;
using Terraria.ID;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void ExplorationInstruments()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            var generated = NativeUtilityItem("\"fishingInfo\":true,\"weatherInfo\":true,\"moonInfo\":true,\"enemyInfo\":true,\"speedInfo\":true,\"oreInfo\":true,\"rareCreatureInfo\":true,\"killCountInfo\":true");
            ExplorationPresentation(generated, "fishingInfo", "weatherInfo", "moonInfo", "enemyInfo", "speedInfo", "oreInfo", "rareCreatureInfo", "killCountInfo");
            generated.UpdateAccessory(player, true);
            Equal(true, player.accFishFinder && player.accWeatherRadio && player.accCalendar && player.accThirdEye && player.accStopwatch && player.accOreFinder && player.accCritterGuide && player.accDreamCatcher, "independent native grants");
            player.ResetEffects();
            Equal(false, player.accFishFinder || player.accWeatherRadio || player.accCalendar || player.accThirdEye || player.accStopwatch || player.accOreFinder || player.accCritterGuide || player.accDreamCatcher, "native reset removes unequipped grants");
            var absent = NativeUtilityItem("\"defense\":1").Data.ToNetworkJson();
            Equal(false, absent.Contains("fishingInfo", StringComparison.Ordinal), "old wire preserves omission fishingInfo");
            Equal(false, absent.Contains("weatherInfo", StringComparison.Ordinal), "old wire preserves omission weatherInfo");
            Equal(false, absent.Contains("moonInfo", StringComparison.Ordinal), "old wire preserves omission moonInfo");
            Equal(false, absent.Contains("enemyInfo", StringComparison.Ordinal), "old wire preserves omission enemyInfo");
            Equal(false, absent.Contains("speedInfo", StringComparison.Ordinal), "old wire preserves omission speedInfo");
            Equal(false, absent.Contains("oreInfo", StringComparison.Ordinal), "old wire preserves omission oreInfo");
            Equal(false, absent.Contains("rareCreatureInfo", StringComparison.Ordinal), "old wire preserves omission rareCreatureInfo");
            Equal(false, absent.Contains("killCountInfo", StringComparison.Ordinal), "old wire preserves omission killCountInfo");
        });
    }
}
