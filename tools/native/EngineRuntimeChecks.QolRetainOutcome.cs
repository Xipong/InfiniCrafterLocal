using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolRetainOutcome()
    {
        WithPlayer((player, owner) => {
            bool inventory = Terraria.Main.playerInventory, focus = Terraria.Main.hasFocus;
            int mode = Terraria.Main.netMode;
            try {
                Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
                Terraria.Main.playerInventory = false; Terraria.Main.hasFocus = true;
                var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
                typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("SetCraftLaneOutcome", flags)!.Invoke(owner, new object[] {
                    0, InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded, "result",
                    InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.CraftLaneMaterialDisposition.Unobserved });
                var tick = typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("TickCraftLanePresentation", flags)!;
                for (int i = 0; i < 2000; i++) tick.Invoke(owner, null);
                Equal("result", owner.GetCraftLaneOutcome(0).Message, "unread outcome survives combat time");
            } finally { Terraria.Main.playerInventory = inventory; Terraria.Main.hasFocus = focus; Terraria.Main.netMode = mode; }
        });
    }
}
