#nullable enable
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.VFX;

public readonly record struct InfiniVfxSlotEmissionKey(
    int ProjectileIdentity,
    string EntityId,
    string EventName,
    string SlotId);

/// <summary>Per-projectile presentation state. It never contains gameplay state.</summary>
public sealed class InfiniVfxState
{
    public int Tick;
    public int LocalSeed;
    public int ParticlesThisTick;
    public int ParticlesTotal;
    public int DrawCallsThisFrame;
    public ulong LastGameUpdate = ulong.MaxValue;
    public Dictionary<InfiniVfxSlotEmissionKey, ulong> LastSlotEmission { get; } = new();
    public Vector2[] CenterHistory = Array.Empty<Vector2>();

    public void Push(Vector2 center)
    {
        if (CenterHistory.Length != 20) CenterHistory = new Vector2[20];
        for (int i = CenterHistory.Length - 1; i > 0; i--) CenterHistory[i] = CenterHistory[i - 1];
        CenterHistory[0] = center;
    }
}

public enum InfiniVfxDrawPass { All, UnderProjectile, OverProjectile }

/// <summary>
/// Bounded renderer for exact ``entityId + event`` slots.  It is presentation
/// only and cannot mutate damage, velocity, collision, ownership, or lifecycle.
/// </summary>
public static class InfiniVfxRuntime
{
    public static void OnTick(Projectile projectile, string entityId, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return;
        BeginWorldTick(projectile, ref state);
        if (state.LocalSeed == 0) state.LocalSeed = manifest.Seed == 0 ? projectile.identity + 1337 : manifest.Seed;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, RuntimeEventKind.Periodic) || !Cadence(slot, state.Tick)) continue;
            if (!TryMarkSlotEmission(projectile, entityId, RuntimeEventKind.Periodic, slot, ref state)) continue;
            EmitSlot(projectile.Center, projectile.velocity, slot, manifest, ref state);
        }
    }

    public static bool OnEvent(Projectile projectile, string entityId, string eventName, VfxManifestSpec manifest, ref InfiniVfxState state, Vector2 center)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return false;
        BeginWorldTick(projectile, ref state);
        if (state.LocalSeed == 0) state.LocalSeed = manifest.Seed == 0 ? projectile.identity + 1337 : manifest.Seed;
        bool emitted = false;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, eventName)) continue;
            if (!TryMarkSlotEmission(projectile, entityId, eventName, slot, ref state)) continue;
            emitted = true;
            EmitSlot(center, projectile.velocity, slot, manifest, ref state);
        }
        return emitted;
    }

    private static void BeginWorldTick(Projectile projectile, ref InfiniVfxState state)
    {
        if (state.LastGameUpdate == Main.GameUpdateCount) return;
        state.LastGameUpdate = Main.GameUpdateCount;
        state.Tick++;
        state.ParticlesThisTick = 0;
        state.DrawCallsThisFrame = 0;
        state.Push(projectile.Center);
    }

    private static bool TryMarkSlotEmission(
        Projectile projectile,
        string entityId,
        string eventName,
        VfxSlotSpec slot,
        ref InfiniVfxState state)
    {
        var key = new InfiniVfxSlotEmissionKey(projectile.identity, entityId, eventName, slot.Id);
        ulong gameUpdate = Main.GameUpdateCount;
        if (state.LastSlotEmission.TryGetValue(key, out ulong previous) && previous == gameUpdate)
            return false;
        state.LastSlotEmission[key] = gameUpdate;
        return true;
    }

    public static void Draw(Projectile projectile, string entityId, VfxManifestSpec manifest, ref InfiniVfxState state, Color lightColor, InfiniVfxDrawPass pass = InfiniVfxDrawPass.All)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return;
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!string.Equals(slot.EntityId, entityId, StringComparison.Ordinal)) continue;
            if (slot.Event != RuntimeEventKind.Periodic && slot.Event != RuntimeEventKind.OnSpawn) continue;
            bool over = slot.Layer == "AfterProjectiles";
            if (pass == InfiniVfxDrawPass.UnderProjectile && over) continue;
            if (pass == InfiniVfxDrawPass.OverProjectile && !over) continue;
            if (!SpendDraw(manifest, ref state, 1)) continue;
            Color color = PresentationColor(manifest, lightColor) * slot.Alpha;
            switch (VfxRendererRegistry.Resolve(slot))
            {
                case InfiniVfxRendererKind.ProjectileAfterimage:
                case InfiniVfxRendererKind.SpriteStampTrail:
                case InfiniVfxRendererKind.HistoryRibbon:
                case InfiniVfxRendererKind.TipTrail:
                    DrawTrail(pixel, state, color, Math.Max(1f, slot.Scale * 2f));
                    break;
                case InfiniVfxRendererKind.BeamLine:
                case InfiniVfxRendererKind.WavyStrip:
                    DrawLine(pixel, projectile.Center - Main.screenPosition, projectile.Center - Main.screenPosition + projectile.velocity.SafeNormalize(Vector2.UnitX) * Math.Max(20f, slot.Scale * 48f), color, Math.Max(1f, slot.Scale * 2f));
                    break;
                case InfiniVfxRendererKind.FieldPulse:
                case InfiniVfxRendererKind.OrbitingMotes:
                case InfiniVfxRendererKind.GhostArc:
                    DrawCross(pixel, projectile.Center - Main.screenPosition, color, Math.Max(4f, slot.Scale * 9f));
                    break;
            }
        }
    }

    private static bool Matches(VfxSlotSpec slot, string entityId, string eventName)
        => slot is not null
            && string.Equals(slot.EntityId, entityId, StringComparison.Ordinal)
            && string.Equals(slot.Event, eventName, StringComparison.Ordinal);

    private static bool Cadence(VfxSlotSpec slot, int tick)
    {
        int repeat = slot.RepeatEvery > 0 ? slot.RepeatEvery : Math.Clamp(14 - (int)MathF.Round(slot.Density * 8f), 4, 18);
        return tick >= slot.StartTick && (tick - slot.StartTick + slot.SlotSeed) % Math.Max(1, repeat) == 0;
    }

    private static void EmitSlot(Vector2 center, Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        Color color = PresentationColor(manifest, Color.White);
        if (kind == InfiniVfxRendererKind.LightCue)
        {
            float strength = Math.Clamp(slot.Scale * 0.22f, 0.04f, 1.2f);
            Lighting.AddLight(center, color.ToVector3() * strength);
            return;
        }
        if (kind == InfiniVfxRendererKind.SoundCue)
        {
            SoundEngine.PlaySound(SoundID.Item1 with { Volume = Math.Clamp(slot.Alpha, 0.05f, 1f), Pitch = Math.Clamp(slot.PhaseOffset * 0.25f, -0.5f, 0.5f) }, center);
            return;
        }
        int count = kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ChildMotes or InfiniVfxRendererKind.ImpactSprite
            ? Math.Clamp(2 + (int)MathF.Round(slot.Density * 8f), 2, 10)
            : 1;
        for (int i = 0; i < count; i++)
        {
            if (!SpendParticle(manifest, ref state)) break;
            float angle = count == 1 ? Main.rand.NextFloat(MathHelper.TwoPi) : MathHelper.TwoPi * i / count;
            float speed = Math.Clamp(0.35f + slot.Spread * 1.7f, 0.2f, 4f);
            Vector2 velocity = angle.ToRotationVector2() * speed + inheritedVelocity * 0.08f;
            Dust dust = Dust.NewDustPerfect(center, DustId(slot), velocity, 100, color, Math.Clamp(slot.Scale, 0.2f, 3f));
            dust.noGravity = slot.ParticleSystemId is not "pl:smoke";
        }
    }

    private static int DustId(VfxSlotSpec slot) => slot.ParticleSystemId switch
    {
        "pl:smoke" => DustID.Smoke,
        "pl:shard" => DustID.Glass,
        "pl:spark" => DustID.Electric,
        "pl:glow" => DustID.TintableDustLighted,
        _ => DustID.GemDiamond,
    };

    private static Color PresentationColor(VfxManifestSpec manifest, Color fallback)
        => manifest.Motif.Element.ToLowerInvariant() switch
        {
            "fire" or "heat" => Color.OrangeRed,
            "ice" or "water" => Color.Cyan,
            "poison" or "nature" => Color.LimeGreen,
            "shadow" or "void" => Color.MediumPurple,
            "electric" or "lightning" => Color.Yellow,
            "blood" => Color.Crimson,
            _ => fallback == default ? Color.White : fallback,
        };

    private static bool SpendParticle(VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (state.ParticlesThisTick >= manifest.Budget.MaxParticlesPerTick || state.ParticlesTotal >= manifest.Budget.MaxParticlesTotal) return false;
        state.ParticlesThisTick++; state.ParticlesTotal++; return true;
    }

    private static bool SpendDraw(VfxManifestSpec manifest, ref InfiniVfxState state, int cost)
    {
        if (state.DrawCallsThisFrame + cost > manifest.Budget.MaxDrawCalls) return false;
        state.DrawCallsThisFrame += cost; return true;
    }

    private static void DrawTrail(Texture2D pixel, InfiniVfxState state, Color color, float width)
    {
        for (int i = 1; i < state.CenterHistory.Length; i++)
        {
            Vector2 a = state.CenterHistory[i - 1]; Vector2 b = state.CenterHistory[i];
            if (a == Vector2.Zero || b == Vector2.Zero) continue;
            DrawLine(pixel, a - Main.screenPosition, b - Main.screenPosition, color * (1f - i / (float)state.CenterHistory.Length), width);
        }
    }

    private static void DrawCross(Texture2D pixel, Vector2 center, Color color, float radius)
    {
        DrawLine(pixel, center - Vector2.UnitX * radius, center + Vector2.UnitX * radius, color, 2f);
        DrawLine(pixel, center - Vector2.UnitY * radius, center + Vector2.UnitY * radius, color, 2f);
    }

    private static void DrawLine(Texture2D pixel, Vector2 start, Vector2 end, Color color, float width)
    {
        Vector2 delta = end - start;
        if (delta.LengthSquared() <= 0.01f) return;
        Main.spriteBatch.Draw(pixel, start, null, color, delta.ToRotation(), Vector2.Zero, new Vector2(delta.Length(), Math.Max(1f, width)), SpriteEffects.None, 0f);
    }
}
