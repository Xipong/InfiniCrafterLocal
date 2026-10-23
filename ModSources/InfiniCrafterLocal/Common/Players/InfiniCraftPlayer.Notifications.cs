#nullable enable
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    public readonly record struct CraftNotification(long Sequence, int Lane, CraftLaneOutcome Outcome);
    private readonly List<CraftNotification> _craftNotifications = new();
    private long _craftNotificationSequence;
    public int UnreadCraftNotificationCount => _craftNotifications.Count;
    public int OverflowCraftNotificationCount { get; private set; }

    public IReadOnlyList<CraftNotification> CaptureCraftNotifications()
        => Array.AsReadOnly(_craftNotifications.ToArray());

    private void EnqueueCraftNotification(int lane, CraftLaneOutcome outcome)
    {
        if (Main.dedServ || Main.netMode == NetmodeID.Server || Player.whoAmI != Main.myPlayer) return;
        if (_craftNotifications.Count == 32)
        {
            _craftNotifications.RemoveAt(0);
            OverflowCraftNotificationCount = Math.Min(int.MaxValue - 1, OverflowCraftNotificationCount) + 1;
        }
        _craftNotifications.Add(new(++_craftNotificationSequence, lane, outcome));
        if (outcome.Kind == CraftLaneOutcomeKind.Succeeded
            && (ModContent.GetInstance<Common.Config.InfiniGameplayQolConfig>()?.PlayCraftCompletionSound ?? true))
            Terraria.Audio.SoundEngine.PlaySound(SoundID.ResearchComplete, Player.Center);
    }

    public bool AcknowledgeCraftNotification(long sequence)
        => _craftNotifications.RemoveAll(row => row.Sequence == sequence) > 0;

    public void AcknowledgeAllCraftNotifications()
    {
        _craftNotifications.Clear(); OverflowCraftNotificationCount = 0;
    }
}
