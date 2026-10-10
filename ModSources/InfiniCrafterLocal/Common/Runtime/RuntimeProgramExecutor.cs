#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.DataStructures;

namespace InfiniCrafterLocal.Common.Runtime;

/// <summary>
/// Executes exact low-level event actions already present in RuntimeProgramSpec.
/// It never infers an action from item prose/category/name and never substitutes
/// a weapon-family macro. Callers remain responsible for exact lifecycle timing.
/// </summary>
// One owner-local ledger per activation, referenced by every root sibling and
// descendant. Never stored in a process-wide map or reconstructed from peer AI.
internal sealed class RuntimeSpawnBudget
{
    public int Remaining { get; private set; }
    public RuntimeSpawnBudget(int remaining) => Remaining = Math.Max(0, remaining);
    public int Reserve(int count)
    {
        int granted = Math.Min(Math.Max(0, count), Remaining);
        Remaining -= granted;
        return granted;
    }
    public void Return(int count) => Remaining += Math.Max(0, count);
}

internal static class RuntimeProgramExecutor
{
    // tML dispatches owner-hit hooks only on the owner. NPC.AddBuff and
    // Player.ApplyDamageToNPC sync their own changes; server-side replay of
    // these authored actions would duplicate damage/status on other events.
    internal static bool ShouldRunNpcEvent(RuntimeEventActionSpec action, Player owner)
        => action.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit
            ? InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner)
            : InfiniRuntimeAuthority.ShouldRunNpcGameplay();

    // One authority decision for immediate dispatch and delayed admission.
    // Admission does not grant lasting authority: ExecuteAction rechecks it.
    // Effect preconditions (targets, depth, damage, cooldown) stay with consumers.
    internal static bool HasActionAuthority(RuntimeEventActionSpec action, Player owner)
        => action.ActionCode switch
        {
            RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.HealOwner or RuntimeEventActionCode.MoveOwner
                => InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner),
            RuntimeEventActionCode.SelectTargetsAndEmit => InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner),
            RuntimeEventActionCode.ApplyStatus or RuntimeEventActionCode.DamageArea or RuntimeEventActionCode.ChainDamage
                => ShouldRunNpcEvent(action, owner),
            RuntimeEventActionCode.Pull => action.Mode == "owner_to_target"
                ? InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner)
                : InfiniRuntimeAuthority.ShouldRunNpcGameplay(),
            _ => false,
        };

    public static void ExecuteAction(
        GeneratedItemData data,
        RuntimeEntitySpec sourceEntity,
        RuntimeEventActionSpec action,
        Player owner,
        IEntitySource source,
        Vector2 eventPosition,
        Vector2 direction,
        NPC? directTarget,
        int damageDone,
        int childDepth,
        ref int remainingSpawnBudget)
    {
        var budget = new RuntimeSpawnBudget(remainingSpawnBudget);
        ExecuteAction(data, sourceEntity, action, owner, source, eventPosition, direction,
            directTarget, damageDone, childDepth, budget);
        remainingSpawnBudget = budget.Remaining;
    }

    public static void ExecuteAction(
        GeneratedItemData data,
        RuntimeEntitySpec sourceEntity,
        RuntimeEventActionSpec action,
        Player owner,
        IEntitySource source,
        Vector2 eventPosition,
        Vector2 direction,
        NPC? directTarget,
        int damageDone,
        int childDepth,
        RuntimeSpawnBudget budget,
        int reservedSpawnBudget = 0)
    {
        if (!HasActionAuthority(action, owner))
        {
            budget.Return(reservedSpawnBudget);
            return;
        }
        switch (action.ActionCode)
        {
            case RuntimeEventActionCode.SpawnEntity:
                SpawnEntity(data, action, owner, source, eventPosition, direction, childDepth, budget, reservedSpawnBudget);
                break;
            case RuntimeEventActionCode.SelectTargetsAndEmit:
                SelectTargetsAndEmit(data, action, owner, source, directTarget, childDepth, budget, reservedSpawnBudget);
                break;
            case RuntimeEventActionCode.ApplyStatus:
                if (directTarget is { active: true })
                    directTarget.AddBuff(action.BuffId, action.DurationTicks);
                break;
            case RuntimeEventActionCode.DamageArea:
                // A real contact hit has already damaged this NPC. Proximity
                // expiration merely selects a nearby target; its blast must
                // include that target rather than treating it as a prior hit.
                DamageArea(data, sourceEntity, action, owner, eventPosition,
                    action.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit ? directTarget : null);
                break;
            case RuntimeEventActionCode.ChainDamage:
                ChainDamage(data, sourceEntity, action, owner, eventPosition, directTarget);
                break;
            case RuntimeEventActionCode.Pull:
                Pull(action, owner, eventPosition, directTarget);
                break;
            case RuntimeEventActionCode.HealOwner:
                HealOwner(action, owner, damageDone);
                break;
            case RuntimeEventActionCode.MoveOwner:
                MoveOwner(action, owner, eventPosition);
                break;
            default:
                return;
        }
    }

    internal static float EventSpawnDamageMultiplier(RuntimeEventActionSpec action)
        => Math.Clamp(action.DamageMultiplier, 0f, 10f);

    internal readonly record struct TargetEmissionStep(
        int TargetNpcSlot, RuntimeSpawnTransform Transform, RuntimeInitialNpcExclusion Exclusion);

    internal static IReadOnlyList<TargetEmissionStep> PlanTargetEmissions(RuntimeEventActionSpec action, NPC initialTarget, int capacity)
    {
        var steps = new List<TargetEmissionStep>();
        if (action.ActionCode != RuntimeEventActionCode.SelectTargetsAndEmit || action.StepCount is null
            || action.StepRangeTiles is null || action.SelectionAnchor is null || action.RepeatPolicy is null
            || action.RequireLineOfSight is null || action.InitialIgnoreCountdownUpdates is null
            || capacity <= 0 || initialTarget.whoAmI < 0 || initialTarget.whoAmI >= Main.maxNPCs
            || !ReferenceEquals(Main.npc[initialTarget.whoAmI], initialTarget))
            return steps;
        int count = Math.Min(action.StepCount.Value, capacity);
        double radius = action.StepRangeTiles.Value * 16d;
        var visited = new HashSet<NPC> { initialTarget };
        NPC previous = initialTarget;
        for (int step = 0; step < count; step++)
        {
            NPC anchor = action.SelectionAnchor == "previous_target" ? previous : initialTarget;
            Vector2 origin = anchor.Center;
            if (!float.IsFinite(origin.X) || !float.IsFinite(origin.Y)
                || !RuntimeInitialNpcExclusion.TryCapture(anchor, action.InitialIgnoreCountdownUpdates.Value, out var exclusion))
                break;
            NPC? next = null;
            double nearestSquared = double.PositiveInfinity;
            foreach (NPC npc in Main.ActiveNPCs)
            {
                if (!npc.CanBeChasedBy() || ReferenceEquals(npc, anchor)
                    || action.RepeatPolicy == "exclude_visited" && visited.Contains(npc))
                    continue;
                Vector2 center = npc.Center;
                double dx = (double)center.X - origin.X, dy = (double)center.Y - origin.Y;
                double distanceSquared = dx * dx + dy * dy;
                // A coincident center has no authored direction. Do not invent
                // an axis for it or let NaN win a nearest-target comparison.
                if (!double.IsFinite(distanceSquared) || distanceSquared <= 0d || distanceSquared > radius * radius)
                    continue;
                if (action.RequireLineOfSight == true
                    && !Collision.CanHit(anchor.position, anchor.width, anchor.height, npc.position, npc.width, npc.height))
                    continue;
                if (distanceSquared < nearestSquared
                    || distanceSquared == nearestSquared && (next is null || npc.whoAmI < next.whoAmI))
                {
                    next = npc;
                    nearestSquared = distanceSquared;
                }
            }
            if (next is null) break;
            var transform = new RuntimeSpawnTransform(origin, next.Center - origin);
            if (!transform.IsValid) break;
            steps.Add(new(next.whoAmI, transform, exclusion));
            previous = next;
            visited.Add(next);
        }
        return steps;
    }

    private static void SelectTargetsAndEmit(
        GeneratedItemData data, RuntimeEventActionSpec action, Player owner, IEntitySource source,
        NPC? directTarget, int childDepth, RuntimeSpawnBudget budget, int reservedSpawnBudget)
    {
        RuntimeEntitySpec? child = data.RuntimeProgram.TryGetEntity(action.EntityId);
        if (directTarget is null || childDepth >= data.RuntimeProgram.Limits.MaxChildDepth
            || !RuntimeEventActionSpec.SupportsTargetEmission(child) || action.StepCount is null)
        {
            budget.Return(reservedSpawnBudget);
            return;
        }
        int granted = reservedSpawnBudget > 0 ? reservedSpawnBudget : budget.Reserve(action.StepCount.Value);
        int unattempted = granted;
        try
        {
            // Snapshot the complete bounded path in this callback. Later child
            // hits neither move the anchor nor force any planned target to take damage.
            foreach (TargetEmissionStep step in PlanTargetEmissions(action, directTarget, granted))
            {
                // Transfer one reservation to the real spawn boundary. Its
                // exception path owns this one; finally owns only unattempted links.
                unattempted--;
                int spawned = GeneratedProjectile.SpawnRuntimeEntity(data, child!.Id, owner, source,
                    step.Transform.Position, step.Transform.Direction, childDepth + 1, 1,
                    requestedCount: 1, spreadOverride: 0f, activationBudget: budget,
                    initialNpcExclusion: step.Exclusion, initialTransform: step.Transform);
                if (spawned == 0)
                {
                    budget.Return(1);
                    break;
                }
            }
        }
        finally { budget.Return(unattempted); }
    }

    private static void SpawnEntity(
        GeneratedItemData data,
        RuntimeEventActionSpec action,
        Player owner,
        IEntitySource source,
        Vector2 eventPosition,
        Vector2 direction,
        int childDepth,
        RuntimeSpawnBudget budget,
        int reservedSpawnBudget)
    {
        int available = reservedSpawnBudget > 0 ? reservedSpawnBudget : budget.Remaining;
        if (childDepth >= data.RuntimeProgram.Limits.MaxChildDepth
            || available <= 0)
        {
            budget.Return(reservedSpawnBudget);
            return;
        }
        RuntimeEntitySpec? target = data.RuntimeProgram.TryGetEntity(action.EntityId);
        if (target is null || !target.IsProjectileEntity)
        {
            budget.Return(reservedSpawnBudget);
            return;
        }
        int granted = reservedSpawnBudget > 0 ? reservedSpawnBudget : budget.Reserve(action.Count);
        int requested = Math.Min(action.Count, granted);
        int spawned = requested > 0 ? GeneratedProjectile.SpawnRuntimeEntity(
            data,
            target.Id,
            owner,
            source,
            eventPosition,
            direction.SafeNormalize(new Vector2(owner.direction, 0f)),
            childDepth + 1,
            granted,
            requestedCount: requested,
            spreadOverride: action.SpreadRadians,
            damageMultiplier: EventSpawnDamageMultiplier(action),
            activationBudget: budget) : 0;
        budget.Return(granted - spawned);
    }

    // Item stats are projected into Gameplay; projectile stats belong to the exact
    // event-owning entity. Neither live projectile damage nor damageDone is the
    // authored base specified by damage_area_on_event / chain_damage_on_event.
    private static (int Damage, string DamageClass) AuthoredEventDamage(GeneratedItemData data, RuntimeEntitySpec sourceEntity)
        => sourceEntity.Kind == RuntimeEntityKind.ItemBody
            ? (data.Gameplay.Damage, data.Gameplay.DamageClass)
            : (sourceEntity.Damage.Damage, sourceEntity.Damage.DamageClass);

    private static void DamageArea(GeneratedItemData data, RuntimeEntitySpec sourceEntity, RuntimeEventActionSpec action, Player owner, Vector2 center, NPC? directTarget)
    {
        if (action.RadiusPx <= 0)
            return;
        var (baseDamage, damageClass) = AuthoredEventDamage(data, sourceEntity);
        baseDamage = Math.Max(1, baseDamage);
        int damage = Math.Max(1, (int)MathF.Round(baseDamage * Math.Max(0.05f, action.DamageMultiplier)));
        int count = 0;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy() || npc == directTarget || Vector2.DistanceSquared(npc.Center, center) > action.RadiusPx * action.RadiusPx)
                continue;
            int hitDirection = npc.Center.X >= owner.Center.X ? 1 : -1;
            owner.ApplyDamageToNPC(npc, damage, 0f, hitDirection, false, TerrariaRuntimeVocabulary.ResolveDamageClass(damageClass), false);
            if (++count >= 16)
                break;
        }
    }

    private static void ChainDamage(GeneratedItemData data, RuntimeEntitySpec sourceEntity, RuntimeEventActionSpec action, Player owner, Vector2 center, NPC? directTarget)
    {
        float range = Math.Max(16f, action.RangeTiles * 16f);
        var (baseDamage, damageClass) = AuthoredEventDamage(data, sourceEntity);
        int damage = Math.Max(1, (int)MathF.Round(Math.Max(1, baseDamage) * Math.Max(0.05f, action.DamageMultiplier)));
        var candidates = new List<NPC>();
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (npc.CanBeChasedBy() && npc != directTarget && Vector2.DistanceSquared(npc.Center, center) <= range * range)
                candidates.Add(npc);
        }
        candidates.Sort((left, right) =>
            Vector2.DistanceSquared(left.Center, center).CompareTo(Vector2.DistanceSquared(right.Center, center)));
        int candidateCount = Math.Min(candidates.Count, Math.Clamp(action.Count, 1, 12));
        for (int i = 0; i < candidateCount; i++)
        {
            NPC npc = candidates[i];
            int hitDirection = npc.Center.X >= owner.Center.X ? 1 : -1;
            owner.ApplyDamageToNPC(npc, damage, 0f, hitDirection, false, TerrariaRuntimeVocabulary.ResolveDamageClass(damageClass), false);
        }
    }

    private static void Pull(RuntimeEventActionSpec action, Player owner, Vector2 eventPosition, NPC? directTarget)
    {
        float strength = Math.Clamp(action.Strength, 0f, 4f);
        float radius = Math.Max(16f, action.RadiusTiles * 16f);
        if (action.Mode == "owner_to_target")
        {
            if (directTarget is { active: true })
                owner.velocity += (directTarget.Center - owner.Center).SafeNormalize(Vector2.Zero) * strength;
            return;
        }

        Vector2 destination = action.Mode == "target_to_owner" ? owner.Center : eventPosition;
        if (directTarget is { active: true })
        {
            if (directTarget.knockBackResist > 0f)
            {
                directTarget.velocity += (destination - directTarget.Center).SafeNormalize(Vector2.Zero) * strength * directTarget.knockBackResist;
                if (InfiniRuntimeAuthority.IsServer) directTarget.netUpdate = true;
            }
            return;
        }
        int pulled = 0;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy() || npc.knockBackResist <= 0f || Vector2.DistanceSquared(npc.Center, eventPosition) > radius * radius)
                continue;
            npc.velocity += (destination - npc.Center).SafeNormalize(Vector2.Zero) * strength * npc.knockBackResist;
            if (InfiniRuntimeAuthority.IsServer) npc.netUpdate = true;
            if (++pulled >= 16)
                break;
        }
    }

    private static void HealOwner(RuntimeEventActionSpec action, Player owner, int damageDone)
    {
        // Lifesteal follows owner-local projectile proc authority. Running it on both
        // the server and owning client applies one authored hit heal twice in multiplayer.
        if (damageDone <= 0)
            return;
        int heal = Math.Clamp((int)MathF.Round(damageDone * action.DamageFraction), 0, action.MaxHeal);
        if (heal <= 0)
            return;
        if (owner.statLife < owner.statLifeMax2)
            owner.Heal(heal);
    }

    private static void MoveOwner(RuntimeEventActionSpec action, Player owner, Vector2 eventPosition)
    {
        Vector2 delta = eventPosition - owner.Center;
        float maxDistance = Math.Max(16f, action.RangeTiles * 16f);
        if (delta.LengthSquared() > maxDistance * maxDistance)
            eventPosition = owner.Center + delta.SafeNormalize(Vector2.UnitX) * maxDistance;
        Vector2 topLeft = eventPosition - owner.Size * 0.5f;
        if (action.SafeTileOnly && Collision.SolidCollision(topLeft, owner.width, owner.height))
            return;
        if (!owner.GetModPlayer<InfiniCraftPlayer>().TryReserveGeneratedMobilityCooldown(action.CooldownTicks))
            return;
        owner.Teleport(topLeft, 1);
        owner.velocity = Vector2.Zero;
        InfiniRuntimeAuthority.SyncTeleport(owner, topLeft);
    }
}
