#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Runtime;

/// <summary>
/// World-tick scheduler for exact authored event actions with delayTicks > 0.
/// It preserves terminal on_expire/on_kill actions after the source projectile dies;
/// execution still passes through the single RuntimeProgramExecutor authority boundary.
/// </summary>
internal static class RuntimeDelayedActionScheduler
{
    private readonly record struct PendingAction(
        GeneratedItemData Data,
        RuntimeEntitySpec SourceEntity,
        RuntimeEventActionSpec Action,
        int OwnerId,
        Player Owner,
        int NpcId,
        NPC? Target,
        Vector2 Position,
        Vector2 Direction,
        int DamageDone,
        int ChildDepth,
        int Ticks,
        int ReservedSpawnBudget);

    private static readonly List<PendingAction> Pending = new();

    public static bool TrySchedule(
        GeneratedItemData data,
        RuntimeEntitySpec sourceEntity,
        RuntimeEventActionSpec action,
        Player owner,
        Vector2 position,
        Vector2 direction,
        NPC? target,
        int damageDone,
        int childDepth,
        ref int remainingSpawnBudget)
    {
        if (data is null || action is null || owner is null || !owner.active || action.DelayTicks <= 0)
            return false;
        if (Pending.Count >= InfiniRuntimeLimits.MaxPendingRuntimeActions)
            return false;

        int reservedSpawnBudget = 0;
        if (action.ActionCode == RuntimeEventActionCode.SpawnEntity)
        {
            reservedSpawnBudget = Math.Min(Math.Max(0, action.Count), Math.Max(0, remainingSpawnBudget));
            if (reservedSpawnBudget <= 0)
                return false;
            remainingSpawnBudget -= reservedSpawnBudget;
        }

        Pending.Add(new PendingAction(
            data,
            sourceEntity,
            action,
            owner.whoAmI,
            owner,
            target?.whoAmI ?? -1,
            target,
            position,
            direction,
            damageDone,
            childDepth,
            Math.Clamp(action.DelayTicks, 1, 600),
            reservedSpawnBudget));
        return true;
    }

    public static void Update()
    {
        int executed = 0;
        for (int i = 0; i < Pending.Count;)
        {
            PendingAction pending = Pending[i];
            int ticks = pending.Ticks - 1;
            if (ticks > 0)
            {
                Pending[i] = pending with { Ticks = ticks };
                i++;
                continue;
            }
            if (executed >= InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick)
            {
                Pending[i] = pending with { Ticks = 1 };
                i++;
                continue;
            }

            Pending.RemoveAt(i);
            if (pending.OwnerId < 0 || pending.OwnerId >= Main.maxPlayers)
                continue;
            Player owner = Main.player[pending.OwnerId];
            // RemoteClient.Reset replaces Player: a reused slot is not the author
            // of this pending action, even if the newcomer is already active.
            if (owner is null || !owner.active || !ReferenceEquals(owner, pending.Owner))
                continue;
            NPC? target = pending.NpcId >= 0
                && pending.NpcId < Main.maxNPCs
                && ReferenceEquals(Main.npc[pending.NpcId], pending.Target)
                && Main.npc[pending.NpcId].active
                ? Main.npc[pending.NpcId]
                : null;
            int spawnBudget = pending.ReservedSpawnBudget;
            RuntimeProgramExecutor.ExecuteAction(
                pending.Data,
                pending.SourceEntity,
                pending.Action,
                owner,
                owner.GetSource_Misc("InfiniRuntimeDelayedAction"),
                pending.Position,
                pending.Direction,
                target,
                pending.DamageDone,
                pending.ChildDepth,
                ref spawnBudget);
            executed++;
        }
    }

    public static void Clear() => Pending.Clear();
}

public sealed class RuntimeDelayedActionSystem : ModSystem
{
    public override void PostUpdateEverything() => RuntimeDelayedActionScheduler.Update();
    public override void OnWorldUnload() => RuntimeDelayedActionScheduler.Clear();
    public override void Unload() => RuntimeDelayedActionScheduler.Clear();
}
