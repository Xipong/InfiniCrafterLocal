#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks { private static void StationCraftHistory() {
WithPlayer((player, owner) => {
            var type = owner.GetType();
            var record = type.GetMethod("RecordCraftHistory", TestInstance)!;
            for (int i = 0; i < 70; i++) record.Invoke(owner, new object[] { 0,
                new InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.CraftLaneOutcome(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.CraftLaneOutcomeKind.Failed, "failure " + i) });
            Equal(64, owner.CraftHistory.Count, "history bounded");
            Equal("failure 69", owner.CraftHistory[0].Outcome.Message, "newest first");
            var tag = new Terraria.ModLoader.IO.TagCompound();
            type.GetMethod("SaveCraftHistory", TestInstance)!.Invoke(owner, new object[] { tag });
            type.GetMethod("LoadCraftHistory", TestInstance)!.Invoke(owner, new object[] { tag });
            Equal(64, owner.CraftHistory.Count, "durable history roundtrip");
            tag["infiniCraftHistoryV1"] = "corrupt optional history";
            type.GetMethod("LoadCraftHistory", TestInstance)!.Invoke(owner, new object[] { tag });
            Equal(0, owner.CraftHistory.Count, "malformed presentation collection cannot block item recovery load");
            Equal(true, !owner.HasAnyInput && !owner.HasAnyCraftLanePending, "history has no escrow or craft authority");
        });
} }
