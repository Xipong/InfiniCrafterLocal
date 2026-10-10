#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private bool ModifierPhaseActive(int delayTicks, int durationTicks)
        => RuntimeModifierClock.Active(_age, Projectile.extraUpdates + 1, delayTicks, durationTicks);

    private void ApplyActiveModifiers()
    {
        if (!Projectile.active || _entity is null) return;
        if (_entity.TurnModifier is { } turn && ModifierPhaseActive(turn.StartDelayTicks, turn.DurationTicks))
            Projectile.velocity = Projectile.velocity.RotatedBy(turn.TurnRadiansPerUpdate);
        if (_entity.SpeedModifier is { } speed && ModifierPhaseActive(speed.StartDelayTicks, speed.DurationTicks))
        {
            Projectile.velocity *= speed.SpeedMultiplierPerUpdate;
            float magnitude = Projectile.velocity.Length();
            if (magnitude > speed.MaxSpeed)
                Projectile.velocity *= speed.MaxSpeed / magnitude;
        }
        ApplyHomingModifier();
    }

    private void ApplyHomingModifier()
    {
        if (_entity?.HomingModifier is not { } homing
            || !ModifierPhaseActive(homing.StartDelayTicks, homing.DurationTicks)
            || !InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) return;
        float speed = Projectile.velocity.Length();
        if (speed <= 0f || !float.IsFinite(speed)) return;
        float radius = homing.RangeTiles * 16f;
        float bestDistanceSquared = radius * radius;
        NPC? target = null;
        for (int i = 0; i < Main.maxNPCs; i++)
        {
            NPC? npc = Main.npc[i];
            if (npc is null || !npc.active || !npc.CanBeChasedBy(Projectile)) continue;
            float distanceSquared = Vector2.DistanceSquared(Projectile.Center, npc.Center);
            if (!float.IsFinite(distanceSquared) || distanceSquared > bestDistanceSquared
                || distanceSquared == bestDistanceSquared && target is not null) continue;
            if (homing.RequireLineOfSight && !Collision.CanHitLine(Projectile.position, Projectile.width, Projectile.height,
                                                                   npc.position, npc.width, npc.height)) continue;
            bestDistanceSquared = distanceSquared;
            target = npc;
        }
        if (target is null || bestDistanceSquared <= 0f) return;
        float angle = MathHelper.WrapAngle((target.Center - Projectile.Center).ToRotation() - Projectile.velocity.ToRotation());
        float turn = Math.Clamp(angle, -homing.MaxTurnRadiansPerUpdate, homing.MaxTurnRadiansPerUpdate);
        Projectile.velocity = Projectile.velocity.RotatedBy(turn);
        if (turn != 0f) Projectile.netUpdate = true;
    }

    private void ApplyNpcAttraction()
    {
        if (!Projectile.active || _entity?.NpcAttraction is not { } pull
            || !ModifierPhaseActive(pull.StartDelayTicks, pull.DurationTicks)
            || !InfiniRuntimeAuthority.ShouldRunNpcGameplay()) return;
        float radius = pull.RangeTiles * 16f;
        int applied = 0;
        for (int i = 0; i < Main.maxNPCs; i++)
        {
            NPC? npc = Main.npc[i];
            if (npc is null || !npc.active || !npc.CanBeChasedBy(Projectile) || npc.knockBackResist <= 0f) continue;
            Vector2 toward = Projectile.Center - npc.Center;
            float distance = toward.Length();
            if (!float.IsFinite(distance) || distance <= 0f || distance > radius) continue;
            float falloff = pull.Falloff == "linear" ? Math.Max(0f, 1f - distance / radius) : 1f;
            if (falloff <= 0f) continue;
            npc.velocity += toward / distance * pull.StrengthPerUpdate * falloff * Math.Clamp(npc.knockBackResist, 0.1f, 1f);
            npc.netUpdate = true;
            if (++applied >= pull.MaxTargets) break;
        }
    }

    private void ApplyVisualScaleCurve()
    {
        if (_entity?.VisualScaleCurve is { } curve)
            Projectile.scale = _entity.Hitbox.DrawScale * _entity.Visual.Scale * curve.ScaleAt(_age, Projectile.extraUpdates + 1);
    }
}
