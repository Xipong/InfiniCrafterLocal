#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.DataStructures;
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
        IEntitySource Source,
        Projectile? SourceProjectile,
        int SourceProjectileSlot,
        int SourceProjectileIdentity,
        int SourceProjectileType,
        ModProjectile? SourceModProjectile,
        int NpcId,
        NPC? Target,
        uint TargetGeneration,
        Vector2 Position,
        Vector2 Direction,
        int DamageDone,
        RuntimeParentCombat ParentCombat,
        RuntimeHitTargetSpawnSnapshot? HitTargetSpawn,
        int ChildDepth,
        uint EnqueuedTick,
        uint DueTick,
        int ReservedSpawnBudget,
        RuntimeSpawnBudget Budget,
        bool OwnerHitReceipt);

    private static readonly List<PendingAction> Pending = new();
    private static uint? DispatchTick;
    private static int ExecutedThisTick;

    public static bool TrySchedule(
        GeneratedItemData data,
        RuntimeEntitySpec sourceEntity,
        RuntimeEventActionSpec action,
        Player owner,
        IEntitySource source,
        Vector2 position,
        Vector2 direction,
        NPC? target,
        int damageDone,
        int childDepth,
        RuntimeSpawnBudget budget,
        bool ownerHitReceipt = false)
    {
        if (data is null || action is null || owner is null || !owner.active || source is null || action.DelayTicks <= 0)
            return false;
        if (!RuntimeProgramExecutor.HasActionAuthority(action, owner))
            return false;
        if (Pending.Count >= InfiniRuntimeLimits.MaxPendingRuntimeActions)
            return false;
        if (ownerHitReceipt)
        {
            int ownerPending = 0;
            foreach (PendingAction pending in Pending)
                if (pending.OwnerHitReceipt && pending.OwnerId == owner.whoAmI
                    && ReferenceEquals(pending.Owner, owner) && ++ownerPending >= 32)
                    return false;
        }

        Projectile? sourceProjectile = null;
        ModProjectile? sourceModProjectile = null;
        int projectileSlot = -1;
        IEntitySource capturedSource;
        if (source is EntitySource_ItemUse itemUse && source.GetType() == typeof(EntitySource_ItemUse_WithAmmo))
        {
            if (!ReferenceEquals(itemUse.Player, owner) || itemUse.Item is null || itemUse.Item.IsAir)
                return false;
            capturedSource = new EntitySource_ItemUse_WithAmmo(owner, itemUse.Item.Clone(),
                ((EntitySource_ItemUse_WithAmmo)itemUse).AmmoItemIdUsed, source.Context);
        }
        else if (source is EntitySource_ItemUse use && source.GetType() == typeof(EntitySource_ItemUse))
        {
            if (!ReferenceEquals(use.Player, owner) || use.Item is null || use.Item.IsAir)
                return false;
            capturedSource = new EntitySource_ItemUse(owner, use.Item.Clone(), source.Context);
        }
        else if (source is EntitySource_Parent { Entity: Projectile projectile }
                 && source.GetType() == typeof(EntitySource_Parent))
        {
            projectileSlot = projectile.whoAmI;
            if (projectileSlot < 0 || projectileSlot >= Main.maxProjectiles
                || projectile.owner != owner.whoAmI)
                return false;
            bool inWorldSlot = ReferenceEquals(Main.projectile[projectileSlot], projectile);
            // The headless hook harness has unattached, type-zero projectiles.
            // A live parent must have a generation token; an unregistered type-zero
            // fixture can only exercise hook dispatch, never an in-world spawn.
            if (projectile.ModProjectile is null && (inWorldSlot || projectile.type != Terraria.ID.ProjectileID.None))
                return false;
            if (!inWorldSlot)
                projectileSlot = -1;
            sourceProjectile = projectile;
            sourceModProjectile = projectile.ModProjectile;
            capturedSource = source;
        }
        else if (source is EntitySource_Misc
                 && source.GetType() == typeof(EntitySource_Misc)
                 && source.Context == "InfiniRuntimePeriodic"
                 && sourceEntity.Kind == RuntimeEntityKind.ItemBody
                 && action.Event == RuntimeEventKind.Periodic)
        {
            // Item-body periodic events have no item-use parent. Preserve their
            // declared Misc source; do not invent an item or another mechanic.
            capturedSource = source;
        }
        else return false; // Never replace an unknown source with a contextless Misc source.

        // Capture before reserving and before later AI/charge changes. Dispatch
        // receives even an empty snapshot; it must never reread a delayed parent.
        RuntimeParentCombat parentCombat = RuntimeParentCombat.Capture(capturedSource, owner);
        if (action.ActionCode == RuntimeEventActionCode.SpawnEntity
            && !RuntimeChildCombat.TryResolve(action.DamageBasis, action.KnockbackBasis,
                RuntimeProgramExecutor.EventSpawnDamageMultiplier(action), parentCombat, out _, out _))
            return false;

        RuntimeHitTargetSpawnSnapshot? hitTargetSpawn = null;
        if (action.HitTargetSpawn is { } geometry)
        {
            if (action.ActionCode != RuntimeEventActionCode.SpawnEntity || !sourceEntity.IsProjectileEntity
                || action.Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                || !RuntimeHitTargetSpawnSnapshot.TryCapture(geometry, target, direction, out var captured))
                return false;
            hitTargetSpawn = captured;
        }

        int reservedSpawnBudget = 0;
        if (action.ActionCode == RuntimeEventActionCode.SpawnEntity)
        {
            reservedSpawnBudget = budget.Reserve(action.Count);
            if (reservedSpawnBudget <= 0)
                return false;
        }

        if (hitTargetSpawn is { } launch)
            hitTargetSpawn = launch with { Seed = Main.rand.Next() };

        uint enqueuedTick = Main.GameUpdateCount;
        uint dueTick = unchecked(enqueuedTick + (uint)Math.Clamp(action.DelayTicks, 1, 600));
        Pending.Add(new PendingAction(
            data, sourceEntity, action, owner.whoAmI, owner,
            capturedSource,
            sourceProjectile, projectileSlot, sourceProjectile?.identity ?? 0,
            sourceProjectile?.type ?? 0, sourceModProjectile,
            target?.whoAmI ?? -1, target, target is null ? 0 : RuntimeHitNpcGeneration.Get(target),
            position, direction, damageDone, parentCombat, hitTargetSpawn,
            childDepth, enqueuedTick, dueTick, reservedSpawnBudget, budget, ownerHitReceipt));
        return true;
    }

    private static bool SourceIsCurrent(PendingAction pending, Player owner)
    {
        if (pending.SourceProjectile is { } projectile)
            // A dying projectile is a valid parent of a terminal event. Identity,
            // object and slot must survive; active need not.
            return (pending.SourceProjectileSlot < 0 || projectile.whoAmI == pending.SourceProjectileSlot)
                && projectile.owner == pending.OwnerId
                && projectile.identity == pending.SourceProjectileIdentity
                && projectile.type == pending.SourceProjectileType
                && ReferenceEquals(projectile.ModProjectile, pending.SourceModProjectile)
                && (pending.SourceProjectileSlot < 0
                    || ReferenceEquals(Main.projectile[pending.SourceProjectileSlot], projectile));
        return true;
    }

    public static void Update()
    {
        uint now = Main.GameUpdateCount;
        if (DispatchTick != now)
        {
            DispatchTick = now;
            ExecutedThisTick = 0;
        }
        for (int i = 0; i < Pending.Count;)
        {
            PendingAction pending = Pending[i];
            // GameUpdateCount is a wrapping uint. Delays are bounded to 600,
            // far below the half-clock horizon of this signed comparison.
            // A post-projectile visit in the enqueue update is not a new tick.
            if (unchecked((int)(now - pending.DueTick)) < 0)
            {
                i++;
                continue;
            }
            if (ExecutedThisTick >= InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick)
            {
                // Pressure defers dispatch, never rewrites the authored due time.
                i++;
                continue;
            }

            Pending.RemoveAt(i);
            if (pending.OwnerId < 0 || pending.OwnerId >= Main.maxPlayers)
            {
                pending.Budget.Return(pending.ReservedSpawnBudget);
                continue;
            }
            Player owner = Main.player[pending.OwnerId];
            // RemoteClient.Reset replaces Player: a reused slot is not the author
            // of this pending action, even if the newcomer is already active.
            if (owner is null || !owner.active || !ReferenceEquals(owner, pending.Owner)
                || !SourceIsCurrent(pending, owner))
            {
                pending.Budget.Return(pending.ReservedSpawnBudget);
                continue;
            }
            NPC? target = pending.NpcId >= 0
                && pending.NpcId < Main.maxNPCs
                && ReferenceEquals(Main.npc[pending.NpcId], pending.Target)
                && Main.npc[pending.NpcId].active
                // MP NPC state reception may SetDefaults on the same object.
                // The existing incarnation token changes on reuse, not Transform.
                && RuntimeHitNpcGeneration.Get(Main.npc[pending.NpcId]) == pending.TargetGeneration
                ? Main.npc[pending.NpcId]
                : null;
            // A direct-hit pull cannot silently become an area pull if its NPC
            // died or the slot was recycled during the authored delay.
            if (pending.Target is not null && target is null
                && pending.Action.ActionCode == RuntimeEventActionCode.Pull
                && pending.Action.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                continue;
            RuntimeProgramExecutor.ExecuteAction(
                pending.Data,
                pending.SourceEntity,
                pending.Action,
                owner,
                pending.Source,
                pending.Position,
                pending.Direction,
                target,
                pending.DamageDone,
                pending.ChildDepth,
                pending.Budget,
                pending.ReservedSpawnBudget,
                parentCombat: pending.ParentCombat, hitTargetSpawn: pending.HitTargetSpawn);
            ExecutedThisTick++;
        }
    }

    public static void Clear()
    {
        foreach (PendingAction pending in Pending)
            pending.Budget.Return(pending.ReservedSpawnBudget);
        Pending.Clear();
        DispatchTick = null;
        ExecutedThisTick = 0;
    }
}

public sealed class RuntimeDelayedActionSystem : ModSystem
{
    public override void PostUpdateEverything() => RuntimeDelayedActionScheduler.Update();
    public override void OnWorldUnload() => RuntimeDelayedActionScheduler.Clear();
    public override void Unload() => RuntimeDelayedActionScheduler.Clear();
}
