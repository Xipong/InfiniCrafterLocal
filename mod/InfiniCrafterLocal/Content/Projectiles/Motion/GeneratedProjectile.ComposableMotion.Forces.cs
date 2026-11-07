#nullable enable
using System;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private void MultiplyVelocityCapped(float multiplier, float maximum)
    {
        RetainVelocity(multiplier);
        float magnitude = Projectile.velocity.Length();
        if (magnitude <= maximum) return;
        Projectile.velocity *= maximum / magnitude;
    }
    private static void ApplyNpcImpulseKernel(Vector2 center, float radius, float strength, string falloff,
        int maximumTargets, Projectile chaseSource)
    {
        if (!InfiniRuntimeAuthority.ShouldRunNpcGameplay() || radius <= 0f || strength <= 0f) return;
        int applied = 0;
        for (int i = 0; i < Main.maxNPCs; i++) {
            NPC? npc = Main.npc[i];
            if (npc is null || !npc.active || !npc.CanBeChasedBy(chaseSource) || npc.knockBackResist <= 0f) continue;
            Vector2 toward = center - npc.Center;
            float distance = toward.Length();
            if (!float.IsFinite(distance) || distance <= 0f || distance > radius) continue;
            float factor = falloff == "linear" ? Math.Max(0f, 1f - distance / radius) : 1f;
            if (factor <= 0f) continue;
            npc.velocity += toward / distance * strength * factor * Math.Clamp(npc.knockBackResist, 0.1f, 1f);
            npc.netUpdate = true;
            if (++applied >= maximumTargets) break;
        }
    }
}
