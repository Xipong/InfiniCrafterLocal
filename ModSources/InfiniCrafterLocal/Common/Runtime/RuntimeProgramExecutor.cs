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
internal static class RuntimeProgramExecutor
{
    public static void ExecuteAction(
        GeneratedItemData data,
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
        switch (action.ActionCode)
        {
            case RuntimeEventActionCode.SpawnEntity:
                SpawnEntity(data, action, owner, source, eventPosition, direction, childDepth, ref remainingSpawnBudget);
                break;
            case RuntimeEventActionCode.ApplyStatus:
                if (InfiniRuntimeAuthority.ShouldRunNpcGameplay() && directTarget is { active: true })
                    directTarget.AddBuff(action.BuffId, action.DurationTicks);
                break;
            case RuntimeEventActionCode.DamageArea:
                DamageArea(data, action, owner, eventPosition, directTarget);
                break;
            case RuntimeEventActionCode.ChainDamage:
                ChainDamage(data, action, owner, eventPosition, directTarget);
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

    private static void SpawnEntity(
        GeneratedItemData data,
        RuntimeEventActionSpec action,
        Player owner,
        IEntitySource source,
        Vector2 eventPosition,
        Vector2 direction,
        int childDepth,
        ref int remainingSpawnBudget)
    {
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner)
            || childDepth >= data.RuntimeProgram.Limits.MaxChildDepth
            || remainingSpawnBudget <= 0)
            return;
        RuntimeEntitySpec? target = data.RuntimeProgram.TryGetEntity(action.EntityId);
        if (target is null || !target.IsProjectileEntity)
            return;
        int requested = Math.Min(action.Count, remainingSpawnBudget);
        int spawned = GeneratedProjectile.SpawnRuntimeEntity(
            data,
            target.Id,
            owner,
            source,
            eventPosition,
            direction.SafeNormalize(new Vector2(owner.direction, 0f)),
            childDepth + 1,
            remainingSpawnBudget,
            requestedCount: requested,
            spreadOverride: action.SpreadRadians,
            damageMultiplier: action.DamageMultiplier <= 0f ? 1f : action.DamageMultiplier);
        remainingSpawnBudget = Math.Max(0, remainingSpawnBudget - spawned);
    }

    private static void DamageArea(GeneratedItemData data, RuntimeEventActionSpec action, Player owner, Vector2 center, NPC? directTarget)
    {
        if (!InfiniRuntimeAuthority.ShouldRunNpcGameplay() || action.RadiusPx <= 0)
            return;
        int baseDamage = Math.Max(1, data.Gameplay.Damage);
        int damage = Math.Max(1, (int)MathF.Round(baseDamage * Math.Max(0.05f, action.DamageMultiplier)));
        int count = 0;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy() || npc == directTarget || Vector2.DistanceSquared(npc.Center, center) > action.RadiusPx * action.RadiusPx)
                continue;
            int hitDirection = npc.Center.X >= owner.Center.X ? 1 : -1;
            owner.ApplyDamageToNPC(npc, damage, 0f, hitDirection, false, TerrariaRuntimeVocabulary.ResolveDamageClass(data.Gameplay.DamageClass), false);
            if (++count >= 16)
                break;
        }
    }

    private static void ChainDamage(GeneratedItemData data, RuntimeEventActionSpec action, Player owner, Vector2 center, NPC? directTarget)
    {
        if (!InfiniRuntimeAuthority.ShouldRunNpcGameplay())
            return;
        float range = Math.Max(16f, action.RangeTiles * 16f);
        int damage = Math.Max(1, (int)MathF.Round(Math.Max(1, data.Gameplay.Damage) * Math.Max(0.05f, action.DamageMultiplier)));
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
            owner.ApplyDamageToNPC(npc, damage, 0f, hitDirection, false, TerrariaRuntimeVocabulary.ResolveDamageClass(data.Gameplay.DamageClass), false);
        }
    }

    private static void Pull(RuntimeEventActionSpec action, Player owner, Vector2 eventPosition, NPC? directTarget)
    {
        float strength = Math.Clamp(action.Strength, 0f, 4f);
        float radius = Math.Max(16f, action.RadiusTiles * 16f);
        if (action.Mode == "owner_to_target" && directTarget is { active: true } && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner))
        {
            owner.velocity += (directTarget.Center - owner.Center).SafeNormalize(Vector2.Zero) * strength;
            return;
        }
        if (!InfiniRuntimeAuthority.ShouldRunNpcGameplay())
            return;
        Vector2 destination = action.Mode == "target_to_owner" ? owner.Center : eventPosition;
        if (directTarget is { active: true })
        {
            if (directTarget.knockBackResist > 0f)
                directTarget.velocity += (destination - directTarget.Center).SafeNormalize(Vector2.Zero) * strength * directTarget.knockBackResist;
            return;
        }
        int pulled = 0;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy() || npc.knockBackResist <= 0f || Vector2.DistanceSquared(npc.Center, eventPosition) > radius * radius)
                continue;
            npc.velocity += (destination - npc.Center).SafeNormalize(Vector2.Zero) * strength * npc.knockBackResist;
            if (++pulled >= 16)
                break;
        }
    }

    private static void HealOwner(RuntimeEventActionSpec action, Player owner, int damageDone)
    {
        // Lifesteal follows owner-local projectile proc authority. Running it on both
        // the server and owning client applies one authored hit heal twice in multiplayer.
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner) || damageDone <= 0)
            return;
        int heal = Math.Clamp((int)MathF.Round(damageDone * action.DamageFraction), 0, action.MaxHeal);
        if (heal <= 0)
            return;
        if (owner.statLife < owner.statLifeMax2)
            owner.Heal(heal);
    }

    private static void MoveOwner(RuntimeEventActionSpec action, Player owner, Vector2 eventPosition)
    {
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner))
            return;
        Vector2 delta = eventPosition - owner.Center;
        float maxDistance = Math.Max(16f, action.RangeTiles * 16f);
        if (delta.LengthSquared() > maxDistance * maxDistance)
            eventPosition = owner.Center + delta.SafeNormalize(Vector2.UnitX) * maxDistance;
        Vector2 topLeft = eventPosition - owner.Size * 0.5f;
        if (action.SafeTileOnly && Collision.SolidCollision(topLeft, owner.width, owner.height))
            return;
        owner.Teleport(topLeft, 1);
        owner.velocity = Vector2.Zero;
        InfiniRuntimeAuthority.SyncTeleport(owner, topLeft);
    }
}
