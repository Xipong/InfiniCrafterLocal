#nullable enable
using System;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private void MultiplyVelocityCapped(float multiplier, float maximum, bool onlyBelowCap, bool legacyNormalize)
    {
        if (!onlyBelowCap || Projectile.velocity.Length() < maximum) RetainVelocity(multiplier);
        float magnitude = Projectile.velocity.Length();
        if (magnitude <= maximum) return;
        // Old accelerate used SafeNormalize()*cap; PR148 used v*=cap/|v|.
        // Both exact native arithmetic variants belong to this shared kernel.
        if (legacyNormalize) Projectile.velocity = Projectile.velocity.SafeNormalize(_initialDirection) * maximum;
        else Projectile.velocity *= maximum / magnitude;
    }
    private static void ApplyNpcImpulseKernel(Vector2 center, float radius, float strength, string falloff,
        int maximumTargets, bool synchronize, bool legacyDirection, Projectile? chaseSource)
    {
        if (!InfiniRuntimeAuthority.ShouldRunNpcGameplay() || radius <= 0f || strength <= 0f) return;
        int applied = 0;
        for (int i = 0; i < Main.maxNPCs; i++) {
            NPC? npc = Main.npc[i];
            if (npc is null || !npc.active || !npc.CanBeChasedBy(chaseSource) || npc.knockBackResist <= 0f) continue;
            Vector2 toward = center - npc.Center;
            if (legacyDirection) {
                if (Vector2.DistanceSquared(npc.Center, center) > radius * radius) continue;
                npc.velocity += npc.DirectionTo(center) * strength * Math.Clamp(npc.knockBackResist, 0.1f, 1f);
            }
            else {
                float distance = toward.Length();
                if (!float.IsFinite(distance) || distance <= 0f || distance > radius) continue;
                float factor = falloff == "linear" ? Math.Max(0f, 1f - distance / radius) : 1f;
                if (factor <= 0f) continue;
                npc.velocity += toward / distance * strength * factor * Math.Clamp(npc.knockBackResist, 0.1f, 1f);
            }
            if (synchronize) npc.netUpdate = true;
            if (++applied >= maximumTargets) break;
        }
    }
}
