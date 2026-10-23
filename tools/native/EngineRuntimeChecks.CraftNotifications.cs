using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Players;
using Terraria;
using Terraria.ID;
internal static partial class EngineRuntimeChecks
{
    private static void CraftNotifications()
    {
        NotificationInputAndLocalization();
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.dedServ = false;
        WithPlayer((player, owner) => {
            player.whoAmI = Terraria.Main.myPlayer;
            var set = typeof(InfiniCraftPlayer).GetMethod("SetCraftLaneOutcome", BindingFlags.Instance | BindingFlags.NonPublic)!;
            void Notify(int lane, string message) => set.Invoke(owner, new object[] { lane, InfiniCraftPlayer.CraftLaneOutcomeKind.Failed, message, InfiniCraftPlayer.CraftLaneMaterialDisposition.LocalRefund });
            Notify(0, "one"); Notify(0, "one");
            Equal(1, owner.UnreadCraftNotificationCount, "duplicate completion notification suppressed");
            var snapshot = owner.CaptureCraftNotifications();
            Notify(1, "two");
            Equal(1, snapshot.Count, "read snapshot is detached");
            Equal(true, owner.AcknowledgeCraftNotification(snapshot[0].Sequence), "ack exact sequence");
            Equal(false, owner.AcknowledgeCraftNotification(snapshot[0].Sequence), "stale ack cannot dismiss another result");
            for (int i = 0; i < 40; i++) Notify(2, i.ToString());
            Equal(32, owner.UnreadCraftNotificationCount, "notification queue bounded");
            Equal(9, owner.OverflowCraftNotificationCount, "overflow is visible instead of silent");
            owner.AcknowledgeAllCraftNotifications();
            Equal(0, owner.UnreadCraftNotificationCount, "ack all clears queue");
            Equal(0, owner.OverflowCraftNotificationCount, "ack all clears overflow");
            Terraria.Main.netMode = NetmodeID.Server; Notify(0, "server outcome");
            Equal(0, owner.UnreadCraftNotificationCount, "host does not produce local HUD notifications");
        });
    }
}
