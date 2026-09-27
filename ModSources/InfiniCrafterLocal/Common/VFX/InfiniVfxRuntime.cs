#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
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
    public string SourceKey = "";
    public Dictionary<InfiniVfxSlotEmissionKey, ulong> LastSlotEmission { get; } = new();
    public Vector2[] CenterHistory = Array.Empty<Vector2>();
    public int HistoryCount;
    public Vector2[] TipHistory = Array.Empty<Vector2>();
    public int TipHistoryCount;

    public void PushTip(Vector2 tip)
    {
        if (TipHistory.Length != 20) { TipHistory = new Vector2[20]; TipHistoryCount = 0; }
        for (int i = TipHistory.Length - 1; i > 0; i--) TipHistory[i] = TipHistory[i - 1];
        TipHistory[0] = tip;
        TipHistoryCount = Math.Min(TipHistoryCount + 1, TipHistory.Length);
    }

    public void Push(Vector2 center)
    {
        if (CenterHistory.Length != 20) { CenterHistory = new Vector2[20]; HistoryCount = 0; }
        for (int i = CenterHistory.Length - 1; i > 0; i--) CenterHistory[i] = CenterHistory[i - 1];
        CenterHistory[0] = center;
        HistoryCount = Math.Min(HistoryCount + 1, CenterHistory.Length);
    }
}

internal readonly record struct InfiniVfxSpritePose(float Rotation, float Scale, SpriteEffects Effects, float GfxOffY);

// Fixed-size presentation facts captured while the source still exists. No live
// entity references or gameplay authority cross the detached/network boundary.
internal readonly record struct InfiniVfxProjectileSnapshot(
    Vector2 Center, Vector2 Tip, Vector2 Forward, Vector2? OwnerCenter, InfiniVfxSpritePose Pose)
{
    internal static InfiniVfxProjectileSnapshot Capture(Projectile projectile, GeneratedItemData data, string entityId)
    {
        Vector2? ownerCenter = projectile.owner >= 0 && projectile.owner < Main.player.Length
            && Main.player[projectile.owner] is { active: true } owner ? owner.Center : null;
        return new(projectile.Center, InfiniVfxRuntime.ForwardTip(projectile, data, entityId),
            InfiniVfxRuntime.ForwardAxis(projectile, data, entityId), ownerCenter,
            new(projectile.rotation, Math.Clamp(projectile.scale, 0.1f, 8f),
                projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None, projectile.gfxOffY));
    }

    internal bool IsValid => Finite(Center) && Finite(Tip) && Finite(Forward)
        && Math.Abs(Forward.LengthSquared() - 1f) < 0.001f
        && (!OwnerCenter.HasValue || Finite(OwnerCenter.Value))
        && float.IsFinite(Pose.Rotation) && float.IsFinite(Pose.Scale) && Pose.Scale is >= 0.1f and <= 8f
        && float.IsFinite(Pose.GfxOffY) && Pose.Effects is SpriteEffects.None or SpriteEffects.FlipHorizontally;

    private static bool Finite(Vector2 value) => float.IsFinite(value.X) && float.IsFinite(value.Y);

    internal bool TryAnchor(string anchor, Vector2 eventPoint, out Vector2 position)
    {
        position = Center;
        switch (anchor)
        {
            case "self": case "field": case "velocity": return true;
            case "hitPoint": position = eventPoint; return true;
            case "tip": case "tipHistory": position = Tip; return true;
            case "owner" when OwnerCenter.HasValue: position = OwnerCenter.Value; return true;
            default: return false;
        }
    }
}


public enum InfiniVfxDrawPass { All, UnderProjectile, OverProjectile }

/// <summary>
/// Bounded renderer for exact ``entityId + event`` slots.  It is presentation
/// only and cannot mutate damage, velocity, collision, ownership, or lifecycle.
/// </summary>
public static class InfiniVfxRuntime
{
    public static void OnTick(Projectile projectile, GeneratedItemData data, string entityId, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return;
        BeginPresentationTick(projectile, data, entityId, ref state);
        if (state.LocalSeed == 0) state.LocalSeed = manifest.Seed == 0 ? projectile.identity + 1337 : manifest.Seed;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, RuntimeEventKind.Periodic) || !Cadence(slot, state.Tick)) continue;
            if (!TryAnchor(projectile, data, entityId, slot.Anchor, projectile.Center, out Vector2 anchor)) continue;
            if (!TryMarkSlotEmission(projectile, entityId, RuntimeEventKind.Periodic, slot, ref state)) continue;
            EmitSlot(data, entityId, anchor, projectile.velocity, slot, manifest, ref state, state.SourceKey);
        }
    }

    public static bool OnEvent(Projectile projectile, GeneratedItemData data, string entityId, string eventName, VfxManifestSpec manifest, ref InfiniVfxState state, Vector2 center)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return false;
        BeginPresentationTick(projectile, data, entityId, ref state);
        if (state.LocalSeed == 0) state.LocalSeed = manifest.Seed == 0 ? projectile.identity + 1337 : manifest.Seed;
        InfiniVfxProjectileSnapshot snapshot = InfiniVfxProjectileSnapshot.Capture(projectile, data, entityId);
        if (!snapshot.IsValid) return false;
        bool emitted = false;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, eventName)) continue;
            if (!snapshot.TryAnchor(slot.Anchor, center, out Vector2 anchor)) continue;
            if (!TryMarkSlotEmission(projectile, entityId, eventName, slot, ref state)) continue;
            emitted = true;
            EmitPrimitive(data, anchor, slot.Anchor == "velocity" ? projectile.velocity : snapshot.Forward, slot, manifest, state.SourceKey);
            if (VfxRendererRegistry.Resolve(slot) != InfiniVfxRendererKind.ImpactSprite)
                EmitEventSprite(data, entityId, anchor, projectile.velocity, slot, manifest, state.SourceKey,
                    snapshot.Pose);
            EmitSlot(data, entityId, anchor, projectile.velocity, slot, manifest, ref state, state.SourceKey);
        }
        return emitted;
    }

    private static void BeginPresentationTick(Projectile projectile, GeneratedItemData data, string entityId, ref InfiniVfxState state)
    {
        if (state.LastGameUpdate == Main.GameUpdateCount) return;
        BeginWorldTick(projectile, ref state);
        // Capture the actual world tip now, not center history with today's aim.
        state.PushTip(ForwardTip(projectile, data, entityId));
    }

    private static void BeginWorldTick(Projectile projectile, ref InfiniVfxState state)
    {
        if (state.LastGameUpdate == Main.GameUpdateCount) return;
        state.LastGameUpdate = Main.GameUpdateCount;
        state.Tick++;
        state.ParticlesThisTick = 0;
        if (state.SourceKey.Length == 0) state.SourceKey = Guid.NewGuid().ToString("N");
        state.Push(projectile.Center);
    }

    // Spatial anchors are exact; an unavailable owner is not replaced by self.
    // A history renderer still consumes its own sampled center/tip trajectory,
    // not a newly translated history at the current anchor.
    internal static bool TryAnchor(Projectile projectile, GeneratedItemData data, string entityId,
        string anchor, Vector2 eventPoint, out Vector2 position)
    {
        position = projectile.Center;
        switch (anchor)
        {
            case "self": case "field": case "velocity": return true;
            case "hitPoint": position = eventPoint; return true;
            case "tip": case "tipHistory": position = ForwardTip(projectile, data, entityId); return true;
            case "owner":
                if (projectile.owner < 0 || projectile.owner >= Main.player.Length) return false;
                Player? owner = Main.player[projectile.owner];
                if (owner is null || !owner.active) return false;
                position = owner.Center;
                return true;
            default: return false;
        }
    }

    internal static Vector2 ForwardTip(Projectile projectile, GeneratedItemData data, string entityId)
        => projectile.Center + ForwardAxis(projectile, data, entityId) * (projectile.width * projectile.scale * 0.5f);

    internal static Vector2 ForwardAxis(Projectile projectile, GeneratedItemData data, string entityId)
    {
        foreach (RuntimeEntitySpec entity in data.RuntimeProgram.Entities)
            if (entity.Id == entityId && entity.Movement.Code is 14 or 16 or 17)
                return projectile.rotation.ToRotationVector2();
        return projectile.velocity.SafeNormalize(projectile.rotation.ToRotationVector2());
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

    public static void Draw(Projectile projectile, GeneratedItemData data, string entityId, VfxManifestSpec manifest, ref InfiniVfxState state, Color lightColor, InfiniVfxDrawPass pass = InfiniVfxDrawPass.All)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return;
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!string.Equals(slot.EntityId, entityId, StringComparison.Ordinal)) continue;
            // Nonperiodic procedural/sprite effects have detached event lifetimes.
            // History renderers need live samples; retain their on_spawn trail path.
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            if (slot.Event != RuntimeEventKind.Periodic
                && !(slot.Event == RuntimeEventKind.OnSpawn && kind is InfiniVfxRendererKind.HistoryRibbon or InfiniVfxRendererKind.TipTrail)) continue;
            bool over = slot.Layer == "AfterProjectiles";
            if (pass == InfiniVfxDrawPass.UnderProjectile && over) continue;
            if (pass == InfiniVfxDrawPass.OverProjectile && !over) continue;
            if (!TryAnchor(projectile, data, entityId, slot.Anchor, projectile.Center, out Vector2 anchor)) continue;
            Vector2 forward = slot.Anchor == "velocity"
                ? projectile.velocity.SafeNormalize(projectile.rotation.ToRotationVector2()) : ForwardAxis(projectile, data, entityId);
            Color color = ApplyBlend(PresentationColor(data, LegacyPresentationColor(manifest, lightColor)) * slot.Alpha, slot.Blend);
            switch (VfxRendererRegistry.Resolve(slot))
            {
                case InfiniVfxRendererKind.ProjectileAfterimage:
                case InfiniVfxRendererKind.SpriteStampTrail:
                case InfiniVfxRendererKind.ActorAfterimage:
                    string texturePath = ResolveTexturePath(data, entityId, slot.TextureRole);
                    Texture2D? texture = InfiniCrafterLocalMod.Sprites.TryGet(texturePath);
                    if (texture is not null)
                        DrawSpriteTrail(texture, projectile, manifest, ref state, color, slot.Scale);
                    break;
                case InfiniVfxRendererKind.TipTrail:
                    DrawHistory(pixel, manifest, ref state, state.TipHistory, state.TipHistoryCount, color, Math.Max(1f, slot.Scale * 2f));
                    break;
                case InfiniVfxRendererKind.HistoryRibbon:
                    DrawTrail(pixel, manifest, ref state, color, Math.Max(1f, slot.Scale * 2f));
                    break;
                case InfiniVfxRendererKind.BeamLine:
                    if (SpendDraw(manifest, ref state, 1))
                        DrawLine(pixel, anchor - Main.screenPosition, anchor - Main.screenPosition + forward * Math.Max(20f, slot.Scale * 48f), color, Math.Max(1f, slot.Scale * 2f));
                    break;
                case InfiniVfxRendererKind.WavyStrip:
                case InfiniVfxRendererKind.ImpactRing:
                case InfiniVfxRendererKind.FieldPulse:
                case InfiniVfxRendererKind.OrbitingMotes:
                case InfiniVfxRendererKind.GhostArc:
                    DrawActivePrimitive(pixel, anchor, forward, slot, manifest, ref state, color);
                    break;

            }
        }
    }

    // AlphaBlend uses One / InverseSourceAlpha. Zero alpha therefore preserves
    // destination RGB while retaining the already opacity-scaled source RGB.
    internal static Color ApplyBlend(Color color, string blend)
    {
        if (blend == "additive") color.A = 0;
        return color;
    }

    internal static string ResolveTexturePath(GeneratedItemData data, string entityId, string textureRole)
    {
        string role = (textureRole ?? "").Trim().ToLowerInvariant();
        if (role == "none" || data is null) return "";
        if (role == "item") return data.Visual.SpritePath ?? "";

        RuntimeEntitySpec? entity = null;
        foreach (RuntimeEntitySpec candidate in data.RuntimeProgram.Entities)
        {
            if (string.Equals(candidate.Id, entityId, StringComparison.Ordinal))
            {
                entity = candidate;
                break;
            }
        }
        if (entity is null) return "";
        if (role == "impact") return entity.Visual.ImpactSpritePath ?? "";
        if (role != "entity" && !string.Equals(entity.VisualRole, role, StringComparison.Ordinal)) return "";
        return entity.Visual.AssetMode switch
        {
            "reuse_item_icon" => data.Visual.SpritePath ?? "",
            "baked_sprite" => entity.Visual.SpritePath ?? "",
            _ => "",
        };
    }

    public static bool OnDetachedEvent(
        GeneratedItemData data,
        string entityId,
        string eventName,
        VfxManifestSpec manifest,
        Vector2 center,
        Vector2 inheritedVelocity,
        string sourceKey)
        => OnDetachedEvent(data, entityId, eventName, manifest, center, inheritedVelocity, sourceKey, null);

    internal static bool OnDetachedEvent(GeneratedItemData data, string entityId, string eventName,
        VfxManifestSpec manifest, Vector2 center, Vector2 inheritedVelocity, string sourceKey,
        InfiniVfxProjectileSnapshot? snapshot)
    {
        if (snapshot.HasValue && !snapshot.Value.IsValid) return false;
        if (Main.dedServ || data is null || manifest is null || !manifest.HasSlots || string.IsNullOrWhiteSpace(sourceKey))
            return false;
        var state = new InfiniVfxState { Tick = (int)Main.GameUpdateCount, SourceKey = sourceKey };
        bool emitted = false;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, eventName)) continue;
            Vector2 anchor = center;
            if (snapshot is { } captured && !captured.TryAnchor(slot.Anchor, center, out anchor)) continue;
            emitted = true;
            EmitPrimitive(data, anchor, snapshot.HasValue && slot.Anchor != "velocity" ? snapshot.Value.Forward : inheritedVelocity,
                slot, manifest, sourceKey);
            if (snapshot.HasValue && VfxRendererRegistry.Resolve(slot) != InfiniVfxRendererKind.ImpactSprite)
                EmitEventSprite(data, entityId, anchor, inheritedVelocity, slot, manifest, sourceKey, snapshot.Value.Pose);
            // The old velocity-only API cannot fabricate a source body snapshot.
            // Directional impactSprite and old cue/particle API calls remain intact.
            EmitSlot(data, entityId, anchor, inheritedVelocity, slot, manifest, ref state, sourceKey, detachedParticleBudget: true);
        }
        return emitted;
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

    private static void EmitSlot(GeneratedItemData data, string entityId, Vector2 center, Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, ref InfiniVfxState state, string sourceKey, bool detachedParticleBudget = false)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        Color color = PresentationColor(data, LegacyPresentationColor(manifest, Color.White));
        if (kind == InfiniVfxRendererKind.LightCue)
        {
            float strength = Math.Clamp(slot.Scale * 0.22f, 0.04f, 1.2f) * InfiniVfxClientOptions.PresentationLightMultiplier;
            if (strength > 0f)
                Lighting.AddLight(center, color.ToVector3() * strength);
            return;
        }
        if (kind == InfiniVfxRendererKind.SoundCue)
        {
            SoundEngine.PlaySound(SoundID.Item1 with { Volume = Math.Clamp(slot.Alpha, 0.05f, 1f), Pitch = Math.Clamp(slot.PhaseOffset * 0.25f, -0.5f, 0.5f) }, center);
            return;
        }
        if (kind == InfiniVfxRendererKind.ImpactSprite)
        {
            EmitImpactSprite(data, entityId, center, inheritedVelocity, slot, manifest, sourceKey);
            return;
        }
        // An explicit absence of particles is not a request for diamond dust.
        // Keep sprite/light/sound execution above independent of this selector.
        if (slot.ParticleSystemId == "none") return;
        int count = kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ChildMotes
            ? Math.Clamp(2 + (int)MathF.Round(slot.Density * 8f), 2, 10)
            : 1;
        count = InfiniVfxClientOptions.ScaleParticleCount(count);
        for (int i = 0; i < count; i++)
        {
            bool accepted = detachedParticleBudget
                ? InfiniDetachedVfxSystem.TrySpendDetachedParticle(sourceKey, manifest.Budget.MaxParticlesPerTick, manifest.Budget.MaxParticlesTotal)
                : SpendParticle(manifest, ref state);
            if (!accepted) break;
            float angle = count == 1 ? Main.rand.NextFloat(MathHelper.TwoPi) : MathHelper.TwoPi * i / count;
            float speed = Math.Clamp(0.35f + slot.Spread * 1.7f, 0.2f, 4f);
            Vector2 velocity = angle.ToRotationVector2() * speed + inheritedVelocity * 0.08f;
            Dust dust = Dust.NewDustPerfect(center, DustId(slot), velocity, 100, color, Math.Clamp(slot.Scale, 0.2f, 3f));
            dust.noGravity = slot.ParticleSystemId is not "pl:smoke";
        }
    }

    // Event form of a sprite trail is one fading texture snapshot, not invented
    // trajectory samples. Dust remains an independent choice at the caller.
    internal static bool EmitEventSprite(GeneratedItemData data, string entityId, Vector2 center,
        Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, string sourceKey,
        InfiniVfxSpritePose? pose = null)
    {
        if (VfxRendererRegistry.Resolve(slot) is not (InfiniVfxRendererKind.ImpactSprite
            or InfiniVfxRendererKind.ProjectileAfterimage or InfiniVfxRendererKind.SpriteStampTrail
            or InfiniVfxRendererKind.ActorAfterimage)) return false;
        if (pose is { } captured && VfxRendererRegistry.Resolve(slot) != InfiniVfxRendererKind.ImpactSprite)
        {
            string path = ResolveTexturePath(data, entityId, slot.TextureRole);
            if (string.IsNullOrWhiteSpace(path)) return false;
            InfiniDetachedVfxSystem.Enqueue(sourceKey, path, slot.Layer, center + new Vector2(0, captured.GfxOffY),
                captured.Rotation, captured.Scale * slot.Scale, slot.Alpha,
                ApplyBlend(PresentationColor(data, LegacyPresentationColor(manifest, Color.White)), slot.Blend),
                slot.Duration, manifest.Budget.MaxDrawCalls, captured);
        }
        else // Existing item callers retain their directional presentation convention.
            EmitImpactSprite(data, entityId, center, inheritedVelocity, slot, manifest, sourceKey);
        return true;
    }

    internal static bool EmitPrimitive(GeneratedItemData data, Vector2 center, Vector2 inheritedVelocity,
        VfxSlotSpec slot, VfxManifestSpec manifest, string sourceKey, Color? legacyColor = null)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        if (kind is not (InfiniVfxRendererKind.WavyStrip or InfiniVfxRendererKind.FieldPulse
            or InfiniVfxRendererKind.OrbitingMotes or InfiniVfxRendererKind.GhostArc
            or InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.BeamLine)) return false;
        InfiniDetachedVfxSystem.EnqueuePrimitive(sourceKey, kind, slot.Layer, center,
            inheritedVelocity.SafeNormalize(Vector2.UnitX), slot.Scale, slot.Density, slot.PhaseOffset,
            slot.RepeatEvery, slot.Duration, ApplyBlend(PresentationColor(data, legacyColor ?? LegacyPresentationColor(manifest, Color.White)) * slot.Alpha, slot.Blend),
            manifest.Budget.MaxDrawCalls);
        return true;
    }

    // Shared by projectile and item event producers. Missing assets stay silent;
    // an authored sprite must never be replaced by an unrelated particle effect.
    internal static void EmitImpactSprite(GeneratedItemData data, string entityId, Vector2 center,
        Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, string sourceKey)
    {
        string texturePath = ResolveTexturePath(data, entityId, slot.TextureRole);
        if (string.IsNullOrWhiteSpace(texturePath)) return;
        InfiniDetachedVfxSystem.Enqueue(
            sourceKey, texturePath, slot.Layer, center,
            inheritedVelocity.LengthSquared() > 0.01f ? inheritedVelocity.ToRotation() : 0f,
            slot.Scale, slot.Alpha, ApplyBlend(PresentationColor(data, LegacyPresentationColor(manifest, Color.White)), slot.Blend),
            slot.Duration, manifest.Budget.MaxDrawCalls);
    }

    private static int DustId(VfxSlotSpec slot) => slot.ParticleSystemId switch
    {
        "pl:smoke" => DustID.Smoke,
        "pl:shard" => DustID.Glass,
        "pl:spark" => DustID.Electric,
        "pl:glow" => DustID.TintableDustLighted,
        _ => DustID.GemDiamond,
    };

    // Explicit Visual color wins. The caller supplies its exact historical
    // color for old definitions without EffectColor; palette prose is not parsed.
    internal static Color PresentationColor(GeneratedItemData? data, Color fallback)
        => RuntimeColorPolicy.Resolve(data?.Visual?.EffectColor, fallback);

    private static Color LegacyPresentationColor(VfxManifestSpec manifest, Color fallback)
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
        if (state.DrawCallsThisFrame + cost > InfiniVfxClientOptions.EffectiveDrawBudget(manifest.Budget.MaxDrawCalls)) return false;
        state.DrawCallsThisFrame += cost; return true;
    }

    private static void DrawSpriteTrail(Texture2D texture, Projectile projectile, VfxManifestSpec manifest, ref InfiniVfxState state, Color color, float scale)
    {
        // Match the live sprite consumer, including authored spinning motion.
        // Re-aiming only the afterimage by velocity produces a different pose.
        float rotation = projectile.rotation;
        Vector2 origin = new(texture.Width * 0.5f, texture.Height * 0.5f);
        for (int i = 2; i < state.HistoryCount; i += 3)
        {
            Vector2 center = state.CenterHistory[i];
            if (!SpendDraw(manifest, ref state, 1)) break;
            float fade = 1f - i / (float)state.CenterHistory.Length;
            Main.spriteBatch.Draw(
                texture,
                center - Main.screenPosition + new Vector2(0f, projectile.gfxOffY),
                null,
                color * fade,
                rotation,
                origin,
                Math.Max(0.05f, projectile.scale * scale),
                projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None,
                0f);
        }
    }

    private static void DrawTrail(Texture2D pixel, VfxManifestSpec manifest, ref InfiniVfxState state, Color color, float width)
        => DrawHistory(pixel, manifest, ref state, state.CenterHistory, state.HistoryCount, color, width);

    private static void DrawHistory(Texture2D pixel, VfxManifestSpec manifest, ref InfiniVfxState state,
        Vector2[] history, int count, Color color, float width)
    {
        for (int i = 1; i < count; i++)
        {
            Vector2 a = history[i - 1]; Vector2 b = history[i];
            // Repeated stationary samples queue no quad and must not starve later segments.
            if (Vector2.DistanceSquared(a, b) <= 0.01f) continue;
            if (!SpendDraw(manifest, ref state, 1)) break;
            DrawLine(pixel, a - Main.screenPosition, b - Main.screenPosition, color * (1f - i / (float)history.Length), width);
        }
    }

    private static void DrawActivePrimitive(Texture2D pixel, Vector2 center, Vector2 forward, VfxSlotSpec slot, VfxManifestSpec manifest, ref InfiniVfxState state, Color color)
    {
        if (!ShapePhase(slot, state.Tick, out float phase)) return;
        InfiniVfxState budgetState = state;
        DrawPrimitive(pixel, VfxRendererRegistry.Resolve(slot), center - Main.screenPosition,
            forward, slot.Scale, slot.Density, phase, color,
            () => SpendDraw(manifest, ref budgetState, 1));
    }

    // CPU SpriteBatch geometry shared by active and detached consumers. Each
    // segment/mote costs one quad; budget rejection stops rather than downgrades.
    internal static void DrawPrimitive(Texture2D pixel, InfiniVfxRendererKind kind, Vector2 center, Vector2 forward,
        float scale, float density, float phase, Color color, Func<bool> spend)
    {
        if (kind == InfiniVfxRendererKind.WavyStrip)
        {
            // One full sine wave, fixed amplitude 6*scale px, length 48*scale px.
            // Density buys tessellation (8..24 segments), never another renderer.
            int segments = 8 + (int)MathF.Round(density * 16f);
            Vector2 normal = new(-forward.Y, forward.X);
            Vector2 origin = center;
            Vector2 Point(float t) => origin + forward * (48f * scale * t)
                + normal * (6f * scale * MathF.Sin(MathHelper.TwoPi * (t - phase)));
            Vector2 previous = Point(0f);
            for (int i = 1; i <= segments; i++)
            {
                Vector2 next = Point(i / (float)segments);
                if (!spend()) break;
                DrawLine(pixel, previous, next, color, scale * 2f);
                previous = next;
            }
        }
        else if (kind == InfiniVfxRendererKind.BeamLine)
        {
            if (spend()) DrawLine(pixel, center, center + forward * Math.Max(20f, scale * 48f), color, scale * 2f);
        }
        else if (kind == InfiniVfxRendererKind.OrbitingMotes)
        {
            // 2..8 evenly spaced 3*scale px motes on an 18*scale px circle.
            int motes = 2 + (int)MathF.Round(density * 6f);
            for (int i = 0; i < motes; i++)
            {
                if (!spend()) break;
                Vector2 point = center + (MathHelper.TwoPi * (phase + i / (float)motes)).ToRotationVector2() * (18f * scale);
                Main.spriteBatch.Draw(pixel, point, null, color, 0f,
                    new Vector2(pixel.Width, pixel.Height) * 0.5f,
                    new Vector2(3f * scale / pixel.Width, 3f * scale / pixel.Height), SpriteEffects.None, 0f);
            }
        }
        else if (kind == InfiniVfxRendererKind.GhostArc)
        {
            // 120 degree sweep, radius 24*scale, 8..20 segments. Its tail fades.
            int segments = 8 + (int)MathF.Round(density * 12f);
            float head = forward.ToRotation() + phase * MathHelper.TwoPi;
            float sweep = MathHelper.TwoPi / 3f;
            for (int i = 0; i < segments; i++)
            {
                if (!spend()) break;
                Vector2 a = center + (head - sweep + sweep * i / segments).ToRotationVector2() * (24f * scale);
                Vector2 b = center + (head - sweep + sweep * (i + 1) / segments).ToRotationVector2() * (24f * scale);
                DrawLine(pixel, a, b, color * ((i + 1f) / segments), scale * 2f);
            }
        }
        else if (kind is InfiniVfxRendererKind.FieldPulse or InfiniVfxRendererKind.ImpactRing)
        {
            int segments = 12 + (int)MathF.Round(density * 20f);
            float radius = scale * (kind == InfiniVfxRendererKind.ImpactRing ? 4f + 28f * phase : 6f + 18f * phase);
            Color tint = color * (1f - phase);
            for (int i = 0; i < segments; i++)
            {
                if (!spend()) break;
                Vector2 a = center + (MathHelper.TwoPi * i / segments).ToRotationVector2() * radius;
                Vector2 b = center + (MathHelper.TwoPi * (i + 1) / segments).ToRotationVector2() * radius;
                DrawLine(pixel, a, b, tint, scale * 2f);
            }
        }
    }

    // Procedural shape clock: phaseOffset is turns; repeatEvery > 0 is the
    // animation period in world ticks, otherwise duration is the period.
    // startTick delays periodic visibility; event shapes use detached duration.
    // Periodic shapes remain live; this clock does not change Dust cadence.
    private static bool ShapePhase(VfxSlotSpec slot, int tick, out float phase)
    {
        int age = tick - slot.StartTick;
        phase = 0f;
        if (age < 0) return false;
        float turns = age / (float)Math.Max(1, slot.RepeatEvery > 0 ? slot.RepeatEvery : slot.Duration) + slot.PhaseOffset;
        phase = turns - MathF.Floor(turns);
        return true;
    }

    internal static void DrawLine(Texture2D pixel, Vector2 start, Vector2 end, Color color, float width)
    {
        Vector2 delta = end - start;
        if (delta.LengthSquared() <= 0.01f) return;
        // SpriteBatch scale is per source texel, not a destination pixel size.
        // Center the width on the segment so reversing it preserves its footprint.
        Main.spriteBatch.Draw(pixel, start, null, color, delta.ToRotation(),
            new Vector2(0f, pixel.Height * 0.5f),
            new Vector2(delta.Length() / pixel.Width, Math.Max(1f, width) / pixel.Height), SpriteEffects.None, 0f);
    }
}
