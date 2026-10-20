#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.DataStructures;

namespace InfiniCrafterLocal.Content.Items;

// Item event cadence, shared spawn budgets and delayed action dispatch.
public partial class GeneratedItem
{
    // Stable across process/host restarts, unlike string.GetHashCode(). Keep
    // independent action phases without making all equipment proc at once.
    internal static uint PeriodicActionOffset(string id)
    {
        uint hash = 2166136261u;
        unchecked
        {
            foreach (char c in id ?? string.Empty)
            {
                hash = (hash ^ (byte)c) * 16777619u;
                hash = (hash ^ (byte)(c >> 8)) * 16777619u;
            }
        }
        return hash;
    }

    internal void ExecuteEquipmentReaction(Player player, RuntimeEntitySpec body, RuntimeEventActionSpec action,
        Vector2 position, RuntimeSpawnBudget budget)
        => QueueOrExecuteItemAction(player, body, action, null, position, new Vector2(player.direction, 0f),
            0, budget, player.GetSource_Misc("InfiniRuntimeEquipmentReaction"));

    private void RunPeriodicItemEvents(Player player, RuntimeEntitySpec entity)
    {
        // Native held/equipment hooks can visit the same instance in one tick.
        // One emission keeps the authored cadence and shared sibling budget;
        // distinct physical items and owners remain independent.
        var previous = _periodicItemEvents;
        uint tick = Main.GameUpdateCount;
        if (ReferenceEquals(previous.Player, player) && ReferenceEquals(previous.Item, Item)
            && ReferenceEquals(previous.Data, Data) && previous.Tick == tick)
            return;
        _periodicItemEvents = (player, Item, Data, tick);
        var budget = new RuntimeSpawnBudget(Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
        foreach (RuntimeEventActionSpec action in entity.ActionsFor(RuntimeEventKind.Periodic))
        {
            int period = Math.Max(6, action.PeriodTicks);
            if ((Main.GameUpdateCount + PeriodicActionOffset(action.Id)) % (ulong)period != 0) continue;
            QueueOrExecuteItemAction(
                player,
                entity,
                action,
                null,
                player.Center,
                new Vector2(player.direction, 0f),
                Data.Gameplay.Damage,
                budget,
                player.GetSource_Misc("InfiniRuntimePeriodic"));
        }
    }

    private void RunItemEvent(Player player, RuntimeEntitySpec entity, string eventName, NPC? target, int damageDone)
    {
        Vector2 position = target?.Center ?? player.Center;
        Vector2 direction = new(player.direction, 0f);
        foreach (RuntimeEventActionSpec action in entity.ActionsFor(eventName))
            QueueOrExecuteItemAction(
                player,
                entity,
                action,
                target,
                position,
                direction,
                damageDone,
                _itemEventBudget,
                player.GetSource_ItemUse(Item));
    }

    private void QueueOrExecuteItemAction(
        Player player,
        RuntimeEntitySpec entity,
        RuntimeEventActionSpec action,
        NPC? target,
        Vector2 position,
        Vector2 direction,
        int damageDone,
        RuntimeSpawnBudget budget,
        IEntitySource source)
    {
        if (action.DelayTicks > 0)
        {
            RuntimeDelayedActionScheduler.TrySchedule(
                Data,
                entity,
                action,
                player,
                source,
                position,
                direction,
                target,
                damageDone,
                0,
                budget);
            return;
        }
        RuntimeProgramExecutor.ExecuteAction(
            Data,
            entity,
            action,
            player,
            source,
            position,
            direction,
            target,
            damageDone,
            0,
            budget);
    }
}
