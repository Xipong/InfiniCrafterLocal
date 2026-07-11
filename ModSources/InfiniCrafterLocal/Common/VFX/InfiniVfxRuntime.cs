#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Audio;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Terraria;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.VFX;

// AGENT MAP: VfxManifest executor/presentation runtime.
// This consumes normalized VFX slots for dust/particles/ribbons/lights/sounds under
// budget. Keep it presentation-only: no item stat changes, no hidden projectile
// authoring, no prose-to-gameplay bridge.
// =============================================================================
// NAV TOC: InfiniVfxRuntime.cs
// =============================================================================
// NAV: VFX_RUNTIME_STATE              per-projectile VFX counters, histories, timers
// NAV: VFX_RUNTIME_ENTRYPOINTS        OnTick / OnHit / OnKill / Draw public API
// NAV: VFX_RUNTIME_SLOT_COMPOSER      slot selection, channels, lanes, scoring, budgets
// NAV: VFX_RUNTIME_TEXTURES_COLORS    role texture lookup and presentation colors
// NAV: VFX_RUNTIME_DRAW_RENDERERS     afterimages, ribbons, beams, rings, sprites, actors
// NAV: VFX_RUNTIME_BAKED_AND_PARTICLES baked commands and ParticleLibrary/vanilla backend emission
// NAV: VFX_RUNTIME_LIGHT_SOUND        light and sound cue helpers
// =============================================================================


// =============================================================================
// NAV: VFX_RUNTIME_STATE
// =============================================================================
public sealed class InfiniVfxState
{
    public int Tick;
    public int HitTimer;
    public Vector2 HitCenter;
    public int KillBurstTimer;
    public int HitAge;
    public int KillAge;
    public int LocalSeed;
    public int ParticlesThisTick;
    public int ParticlesTotal;
    public int DrawCallsThisFrame;

    public Vector2[] CenterHistory = Array.Empty<Vector2>();
    public Vector2[] TipHistory = Array.Empty<Vector2>();
    public float[] RotationHistory = Array.Empty<float>();

    public void EnsureHistory(int length = 28)
    {
        length = Math.Clamp(length, 8, 64);
        if (CenterHistory.Length == length && TipHistory.Length == length && RotationHistory.Length == length)
            return;
        CenterHistory = new Vector2[length];
        TipHistory = new Vector2[length];
        RotationHistory = new float[length];
    }

    public void PushMotion(Vector2 center, Vector2 tip, float rotation)
    {
        EnsureHistory();
        for (int i = CenterHistory.Length - 1; i > 0; i--)
        {
            CenterHistory[i] = CenterHistory[i - 1];
            TipHistory[i] = TipHistory[i - 1];
            RotationHistory[i] = RotationHistory[i - 1];
        }
        CenterHistory[0] = center;
        TipHistory[0] = tip;
        RotationHistory[0] = rotation;
    }
}


// =============================================================================
// NAV: VFX_RUNTIME_ENTRYPOINTS
// =============================================================================
public enum InfiniVfxDrawPass
{
    All,
    UnderProjectile,
    OverProjectile
}

public static class InfiniVfxRuntime
{
    public static void OnTick(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (manifest is null || !manifest.HasSlots)
            return;
        manifest.Normalize();
        if (state.LocalSeed == 0)
            state.LocalSeed = manifest.Seed == 0 ? projectile.identity + 1337 : manifest.Seed;
        state.Tick++;
        state.ParticlesThisTick = 0;

        Vector2 motionDir = MotionDirection(projectile);
        Vector2 tip = projectile.Center + motionDir * Math.Max(projectile.width, projectile.height) * projectile.scale * 0.72f;
        state.PushMotion(projectile.Center, tip, projectile.rotation);

        if (state.HitTimer > 0)
        {
            PlayTimedEventSlots(projectile, spec, manifest, ref state, state.HitCenter, state.HitAge, "hit");
            state.HitTimer--;
            state.HitAge++;
        }
        if (state.KillBurstTimer > 0)
        {
            PlayTimedEventSlots(projectile, spec, manifest, ref state, projectile.Center, state.KillAge, "kill");
            state.KillBurstTimer--;
            state.KillAge++;
        }

        foreach (var slot in SelectSlotsForGroup(manifest, "live"))
        {
            var kind = VfxRendererRegistry.Resolve(slot);
            if (slot.BakedCommands is { Length: > 0 } && state.Tick >= slot.StartTick)
                PlayBakedCommands(projectile, spec, manifest, slot, ref state, projectile.Center, state.Tick - slot.StartTick);
            if (!SlotTickAllowed(slot, state.Tick))
                continue;
            if (IsLightSlot(slot, kind))
                AddSlotLight(projectile, spec, slot);
            if (IsSoundSlot(slot, kind))
            {
                if (InfiniLuminanceSoundBridge.TryUpdateLiveSoundCue(projectile, spec, slot))
                    continue;
                if (SoundSlotTickAllowed(slot, state.Tick))
                    PlaySlotSound(projectile.Center, spec, slot, false);
            }
            if (EmitsLiveParticles(slot, kind))
                EmitAmbientDust(projectile, spec, manifest, slot, ref state);
            if (EmitsMotionTrailAccent(slot, kind))
                EmitTrailAccent(projectile, spec, manifest, slot, ref state);
        }
    }

    public static void OnHit(Projectile projectile, Vector2 hitCenter, AttackSpec spec, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (manifest is null || !manifest.HasSlots)
            return;
        manifest.Normalize();
        state.HitCenter = hitCenter;
        state.HitAge = 0;
        foreach (var slot in SelectSlotsForGroup(manifest, "hit"))
        {
            state.HitTimer = Math.Max(state.HitTimer, Math.Clamp(slot.Duration, 4, 72));
            PlayBakedCommands(projectile, spec, manifest, slot, ref state, hitCenter, 0);
            state.HitAge = Math.Max(state.HitAge, 1);
            var kind = VfxRendererRegistry.Resolve(slot);
            if (IsSoundSlot(slot, kind))
                PlaySlotSound(hitCenter, spec, slot, true);
            // v0.4.117: impact light flashes looked like intermittent blinking/merged light.
            // Keep steady live projectile light, but do not emit hit/kill world-light pulses here.
            if (EmitsImpactParticles(slot, kind))
                EmitBurstDust(projectile, spec, manifest, slot, hitCenter, ref state);
        }
    }

    public static void OnKill(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (manifest is null || !manifest.HasSlots)
            return;
        manifest.Normalize();
        foreach (var slot in SelectSlotsForGroup(manifest, "kill"))
        {
            state.KillAge = 0;
            state.KillBurstTimer = Math.Max(state.KillBurstTimer, Math.Clamp(slot.Duration, 4, 72));
            PlayBakedCommands(projectile, spec, manifest, slot, ref state, projectile.Center, 0);
            state.KillAge = Math.Max(state.KillAge, 1);
            var kind = VfxRendererRegistry.Resolve(slot);
            if (IsSoundSlot(slot, kind))
                PlaySlotSound(projectile.Center, spec, slot, true);
            if (EmitsImpactParticles(slot, kind))
                EmitBurstDust(projectile, spec, manifest, slot, projectile.Center, ref state);
        }
    }

    public static void Draw(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, ref InfiniVfxState state, Color lightColor, InfiniVfxDrawPass drawPass = InfiniVfxDrawPass.All)
    {
        if (manifest is null || !manifest.HasSlots)
            return;
        manifest.Normalize();
        state.EnsureHistory();
        SyncStateHistoryFromProjectileOldPos(projectile, ref state);
        if (drawPass is InfiniVfxDrawPass.All or InfiniVfxDrawPass.UnderProjectile)
            state.DrawCallsThisFrame = 0;

        Texture2D px = TextureAssets.MagicPixel.Value;
        foreach (var slot in SelectSlotsForGroup(manifest, "live"))
            TryDrawLiveRenderer(projectile, spec, manifest, slot, px, ref state, lightColor, drawPass);
        if (state.HitTimer > 0)
        {
            foreach (var slot in SelectSlotsForGroup(manifest, "hit"))
                TryDrawTimedRenderer(projectile, spec, manifest, slot, px, ref state, lightColor, state.HitCenter, state.HitTimer, drawPass);
        }
        if (state.KillBurstTimer > 0)
        {
            foreach (var slot in SelectSlotsForGroup(manifest, "kill"))
                TryDrawTimedRenderer(projectile, spec, manifest, slot, px, ref state, lightColor, projectile.Center, state.KillBurstTimer, drawPass);
        }
    }

    private static void TryDrawLiveRenderer(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, Texture2D px, ref InfiniVfxState state, Color lightColor, InfiniVfxDrawPass drawPass)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        // Impact-only renderers are handled by timed event draw below.
        if (kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ImpactSprite or InfiniVfxRendererKind.ChildMotes or InfiniVfxRendererKind.None)
            return;
        if (!SlotMatchesDrawPass(slot, kind, drawPass))
            return;
        if (!TrySpendDraw(manifest, ref state, VfxRendererRegistry.EstimateDrawCost(kind, slot)))
            return;

        switch (kind)
        {
            case InfiniVfxRendererKind.ProjectileAfterimage:
                DrawProjectileAfterimage(projectile, spec, slot, lightColor);
                break;
            case InfiniVfxRendererKind.SpriteStampTrail:
                DrawSpriteStampTrail(projectile, spec, slot, lightColor);
                break;
            case InfiniVfxRendererKind.HistoryRibbon:
                DrawHistoryRibbon(projectile, spec, slot, px, state);
                break;
            case InfiniVfxRendererKind.TipTrail:
                DrawTipTrail(projectile, spec, slot, px, state);
                break;
            case InfiniVfxRendererKind.GhostArc:
                DrawGhostArc(projectile, spec, slot, lightColor);
                break;
            case InfiniVfxRendererKind.WavyStrip:
                DrawWavyStrip(projectile, spec, slot, lightColor, state);
                break;
            case InfiniVfxRendererKind.BeamLine:
                DrawBeamLine(projectile, spec, slot, px);
                break;
            case InfiniVfxRendererKind.FieldPulse:
                DrawFieldPulse(projectile, spec, slot, lightColor);
                break;
            case InfiniVfxRendererKind.OrbitingMotes:
                DrawOrbitingMotes(projectile, spec, slot, lightColor, state);
                break;
            case InfiniVfxRendererKind.ActorAfterimage:
                DrawActorAfterimagePlaceholder(projectile, spec, slot, lightColor, state);
                break;
        }
    }

    private static void TryDrawTimedRenderer(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, Texture2D px, ref InfiniVfxState state, Color lightColor, Vector2 worldCenter, int timer, InfiniVfxDrawPass drawPass)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        if (kind is not (InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ImpactSprite or InfiniVfxRendererKind.ChildMotes))
            return;
        if (!SlotMatchesDrawPass(slot, kind, drawPass))
            return;
        if (!TrySpendDraw(manifest, ref state, VfxRendererRegistry.EstimateDrawCost(kind, slot)))
            return;

        switch (kind)
        {
            case InfiniVfxRendererKind.ImpactRing:
                DrawImpactRing(projectile, spec, slot, px, worldCenter, timer);
                break;
            case InfiniVfxRendererKind.ChildMotes:
                DrawChildMotes(projectile, spec, slot, lightColor, worldCenter, timer, state.LocalSeed);
                break;
            case InfiniVfxRendererKind.ImpactSprite:
                DrawImpactSprite(projectile, spec, slot, lightColor, worldCenter, timer);
                break;
        }
    }

    private static bool IsLiveEvent(string? ev) => ev is "tick" or "travel" or "active";

    private static bool IsHitEvent(string? ev) => ev == "hit";

    private static bool IsKillEvent(string? ev) => ev is "kill" or "expire";

    private static bool IsLightSlot(VfxSlotSpec slot, InfiniVfxRendererKind kind)
        => IsLiveEvent(slot.Event) && (slot.Channel == "light" || kind == InfiniVfxRendererKind.LightCue);

    private static bool IsSoundSlot(VfxSlotSpec slot, InfiniVfxRendererKind kind)
        => slot.Channel == "sound" || kind == InfiniVfxRendererKind.SoundCue;

    private static bool EmitsLiveParticles(VfxSlotSpec slot, InfiniVfxRendererKind kind)
        => slot.Channel is "ambientParticles" or "coreGlow"
           || kind is InfiniVfxRendererKind.OrbitingMotes or InfiniVfxRendererKind.ChildMotes;

    private static bool EmitsImpactParticles(VfxSlotSpec slot, InfiniVfxRendererKind kind)
        => slot.Channel is "impactParticles" or "decaySmoke"
           || kind == InfiniVfxRendererKind.ChildMotes;

    private static bool EmitsMotionTrailAccent(VfxSlotSpec slot, InfiniVfxRendererKind kind)
    {
        if (slot.Channel != "motionTrail" && slot.Channel != "coreGlow")
            return false;
        return kind == InfiniVfxRendererKind.ProjectileAfterimage
            || kind == InfiniVfxRendererKind.SpriteStampTrail
            || kind == InfiniVfxRendererKind.HistoryRibbon
            || kind == InfiniVfxRendererKind.TipTrail
            || kind == InfiniVfxRendererKind.GhostArc
            || kind == InfiniVfxRendererKind.WavyStrip
            || kind == InfiniVfxRendererKind.BeamLine;
    }

    private static void PlayTimedEventSlots(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, ref InfiniVfxState state, Vector2 center, int age, string group)
    {
        foreach (var slot in SelectSlotsForGroup(manifest, group))
            PlayBakedCommands(projectile, spec, manifest, slot, ref state, center, age);
    }


// =============================================================================
// NAV: VFX_RUNTIME_SLOT_COMPOSER
// =============================================================================
    private static List<VfxSlotSpec> SelectSlotsForGroup(VfxManifestSpec manifest, string eventGroup)
    {
        List<VfxSlotSpec> ordered = new();
        if (manifest?.Slots is null)
            return ordered;

        // v0.3.30: composer lanes. Calamity-like effects often need a main crescent,
        // a supporting streak/ring and a small particle accent at the same time. The old
        // one-slot-per-channel rule was too sterile. We now arbitrate by channel+lane,
        // while still capping total visual mass per channel.
        Dictionary<string, VfxSlotSpec> selected = new(StringComparer.Ordinal);
        Dictionary<string, int> channelCounts = new(StringComparer.Ordinal);
        HashSet<string> rendererFamilies = new(StringComparer.Ordinal);
        string magnitude = manifest.VisualBudgetClass;

        foreach (var slot in manifest.Slots)
        {
            if (slot is null || !SlotBelongsToGroup(slot, eventGroup))
                continue;

            string channel = string.IsNullOrWhiteSpace(slot.Channel) ? "motionTrail" : slot.Channel;
            string lane = string.IsNullOrWhiteSpace(slot.Lane) ? LaneForSlot(slot) : slot.Lane;
            string channelKey = eventGroup + ":" + channel;
            string laneKey = channelKey + ":" + lane;
            string family = channelKey + ":" + RendererFamily(slot);

            // Do not stack the same renderer family in one channel. Multiple slots are allowed
            // only when they actually have different visual jobs.
            if (rendererFamilies.Contains(family) && channel is not "light" and not "sound")
                continue;

            int maxChannel = MaxChannelCount(eventGroup, channel, magnitude);
            int currentChannelCount = channelCounts.TryGetValue(channelKey, out int n) ? n : 0;

            if (!selected.TryGetValue(laneKey, out var existing))
            {
                if (currentChannelCount >= maxChannel)
                {
                    string weakestKey = WeakestKeyInChannel(selected, channelKey);
                    if (weakestKey.Length == 0 || ScoreSlot(slot) <= ScoreSlot(selected[weakestKey]))
                        continue;
                    selected.Remove(weakestKey);
                    currentChannelCount--;
                }

                selected[laneKey] = slot;
                channelCounts[channelKey] = currentChannelCount + 1;
                rendererFamilies.Add(family);
                continue;
            }

            if (ScoreSlot(slot) > ScoreSlot(existing))
            {
                selected[laneKey] = slot;
                rendererFamilies.Add(family);
            }
        }

        ordered.AddRange(selected.Values);
        ordered.Sort((a, b) => ScoreSlot(b).CompareTo(ScoreSlot(a)));
        return ordered;
    }

    private static string WeakestKeyInChannel(Dictionary<string, VfxSlotSpec> selected, string channelKey)
    {
        string bestKey = string.Empty;
        float bestScore = float.MaxValue;
        foreach (var pair in selected)
        {
            if (!pair.Key.StartsWith(channelKey + ":", StringComparison.Ordinal))
                continue;
            float score = ScoreSlot(pair.Value);
            // Prefer keeping the primary lane; sacrifice support/accent first.
            string lane = pair.Value.Lane;
            if (lane == "primary")
                score += 25f;
            if (score < bestScore)
            {
                bestScore = score;
                bestKey = pair.Key;
            }
        }
        return bestKey;
    }

    private static string LaneForSlot(VfxSlotSpec slot)
    {
        string lane = slot.Lane;
        if (lane is "primary" or "support" or "accent" or "ornament" or "cue")
            return lane;
        if (slot.Channel == "light" || slot.Channel == "sound")
            return "cue";
        return slot.Importance switch
        {
            "core" => "primary",
            "secondary" => "support",
            "luxury" => "ornament",
            "accent" => "accent",
            _ => "support"
        };
    }

    private static bool SlotBelongsToGroup(VfxSlotSpec slot, string group)
    {
        return slot.EventGroup == group;
    }

    private static int MaxChannelCount(string group, string channel, string magnitude)
    {
        if (channel == "light" || channel == "sound")
            return 1;
        bool large = magnitude is "large" or "signature";
        bool signature = magnitude == "signature";
        if (group == "live" && channel == "motionTrail")
            return signature ? 3 : (large ? 2 : 1);
        if (group == "live" && channel == "coreGlow")
            return signature ? 2 : 1;
        if (group == "live" && channel == "ambientParticles")
            return large ? 2 : 1;
        if (group == "hit" && channel == "impactShape")
            return signature ? 3 : (large ? 2 : 1);
        if (group == "hit" && channel == "impactParticles")
            return large ? 2 : 1;
        if (group == "kill" && channel is "decaySmoke" or "impactShape")
            return signature ? 3 : 2;
        return 1;
    }

    private static string RendererFamily(VfxSlotSpec slot)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        return kind.ToString();
    }

    private static float ScoreSlot(VfxSlotSpec slot)
    {
        float score = slot.Importance switch
        {
            "core" => 100f,
            "secondary" => 50f,
            "accent" => 20f,
            "luxury" => 5f,
            _ => 25f
        };
        score += slot.SignatureWeight * 20f;
        score -= slot.VisualCost * 10f;
        score += slot.Density * 3f;
        if (slot.Channel == "light" || slot.Channel == "sound")
            score += 8f;
        return score;
    }


    private static bool SlotTickAllowed(VfxSlotSpec slot, int tick)
    {
        if (tick < slot.StartTick)
            return false;
        if (slot.RepeatEvery <= 0)
            return true;
        return (tick - slot.StartTick) % slot.RepeatEvery == 0;
    }

    private static bool SoundSlotTickAllowed(VfxSlotSpec slot, int tick)
    {
        if (tick < slot.StartTick)
            return false;
        if (tick <= slot.StartTick + 1)
            return true;
        int repeat = slot.RepeatEvery > 0
            ? slot.RepeatEvery
            : Math.Clamp(36 - (int)(slot.Density * 14f), 12, 48);
        return (tick - slot.StartTick) % repeat == 0;
    }

    private static bool SlotMatchesDrawPass(VfxSlotSpec slot, InfiniVfxRendererKind kind, InfiniVfxDrawPass drawPass)
    {
        if (drawPass == InfiniVfxDrawPass.All)
            return true;
        bool under = DrawsUnderProjectile(slot, kind);
        return drawPass == InfiniVfxDrawPass.UnderProjectile ? under : !under;
    }

    private static bool DrawsUnderProjectile(VfxSlotSpec slot, InfiniVfxRendererKind kind)
    {
        string channel = slot.Channel;
        string lane = slot.Lane;
        if (channel == "motionTrail")
            return true;
        if (lane == "support" && channel is "coreGlow" or "impactShape")
            return true;
        return kind is InfiniVfxRendererKind.ProjectileAfterimage
            or InfiniVfxRendererKind.SpriteStampTrail
            or InfiniVfxRendererKind.HistoryRibbon
            or InfiniVfxRendererKind.TipTrail
            or InfiniVfxRendererKind.GhostArc
            or InfiniVfxRendererKind.WavyStrip
            or InfiniVfxRendererKind.BeamLine;
    }

    private static Vector2 MotionDirection(Projectile projectile)
    {
        if (projectile.velocity.LengthSquared() > 0.0001f)
            return projectile.velocity.SafeNormalize(Vector2.UnitX);
        return projectile.rotation.ToRotationVector2().SafeNormalize(Vector2.UnitX);
    }

    private static bool HasProjectileTrailCache(Projectile projectile)
        => projectile.oldPos is { Length: > 2 } && projectile.oldPos.Length > 1 && projectile.oldPos[1] != Vector2.Zero;

    private static Vector2 ProjectileOldCenter(Projectile projectile, int index)
    {
        if (projectile.oldPos is null || index < 0 || index >= projectile.oldPos.Length)
            return Vector2.Zero;
        Vector2 pos = projectile.oldPos[index];
        if (pos == Vector2.Zero)
            return Vector2.Zero;
        return pos + projectile.Size * 0.5f;
    }

    private static float ProjectileOldRotation(Projectile projectile, int index)
    {
        if (projectile.oldRot is { Length: > 0 } && index >= 0 && index < projectile.oldRot.Length)
            return projectile.oldRot[index];
        return projectile.rotation;
    }

    private static Vector2 ProjectileOldTip(Projectile projectile, int index)
    {
        Vector2 center = index == 0 ? projectile.Center : ProjectileOldCenter(projectile, index);
        if (center == Vector2.Zero)
            return Vector2.Zero;
        Vector2 dir = ProjectileOldRotation(projectile, index).ToRotationVector2();
        if (dir.LengthSquared() < 0.0001f)
            dir = MotionDirection(projectile);
        return center + dir.SafeNormalize(Vector2.UnitX) * Math.Max(projectile.width, projectile.height) * projectile.scale * 0.72f;
    }

    private static void SyncStateHistoryFromProjectileOldPos(Projectile projectile, ref InfiniVfxState state)
    {
        // Terraria/tModLoader already maintains oldPos/oldRot for projectile trails when
        // ProjectileID.Sets.TrailCacheLength/TrailingMode are configured. oldPos[0] is the
        // current draw position, so we keep the live sample at index 0 and copy older samples
        // from index 1 onward. Custom history remains a fallback when oldPos is unavailable.
        if (!HasProjectileTrailCache(projectile))
            return;

        int length = Math.Clamp(projectile.oldPos.Length, 8, 64);
        state.EnsureHistory(length);
        state.CenterHistory[0] = projectile.Center;
        state.TipHistory[0] = ProjectileOldTip(projectile, 0);
        state.RotationHistory[0] = projectile.rotation;

        int max = Math.Min(state.CenterHistory.Length, projectile.oldPos.Length);
        for (int i = 1; i < max; i++)
        {
            Vector2 center = ProjectileOldCenter(projectile, i);
            if (center == Vector2.Zero)
                continue;
            state.CenterHistory[i] = center;
            state.TipHistory[i] = ProjectileOldTip(projectile, i);
            state.RotationHistory[i] = ProjectileOldRotation(projectile, i);
        }
    }


// =============================================================================
// NAV: VFX_RUNTIME_TEXTURES_COLORS
// =============================================================================
    private static Texture2D? TextureForRole(AttackSpec spec, string? role)
    {
        string path = role switch
        {
            "impact" => spec.ImpactSpritePath,
            "child" => spec.ChildSpritePath,
            "field" => spec.FieldSpritePath,
            _ => spec.ProjectileSpritePath,
        };
        if (string.IsNullOrWhiteSpace(path) && role == "child")
            path = spec.ImpactSpritePath;
        if (string.IsNullOrWhiteSpace(path) && role == "impact")
            path = spec.ProjectileSpritePath;
        if (string.IsNullOrWhiteSpace(path))
            return null;
        return global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(path);
    }

    private static Color PresentationColor(AttackSpec spec, int alpha = 255)
    {
        Color color = RuntimeColorPolicy.Resolve(spec.PrimaryColorName, Color.White);
        color.A = (byte)Math.Clamp(alpha, 0, 255);
        return color;
    }


// =============================================================================
// NAV: VFX_RUNTIME_DRAW_RENDERERS
// =============================================================================
    private static void DrawProjectileAfterimage(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor)
    {
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
            return;
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        int available = Math.Max(2, Math.Min(projectile.oldPos.Length, Math.Max(ProjectileID.Sets.TrailCacheLength[projectile.type], 6)));
        int count = Math.Clamp((int)MathF.Round(2 + slot.Density * 7), 2, available);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(8f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.15f, 4.0f);
        for (int i = count - 1; i >= 1; i--)
        {
            Vector2 center = ProjectileOldCenter(projectile, i);
            if (center == Vector2.Zero)
                continue;
            Vector2 pos = center - Main.screenPosition;
            float fade = (count - i) / (float)count;
            Color c = Color.Lerp(PresentationColor(spec), Color.White, 0.18f) * (slot.Alpha * fade * 0.75f);
            float rot = ProjectileOldRotation(projectile, i);
            Main.spriteBatch.Draw(texture, pos, src, c, rot, origin, drawScale * (1f - i * 0.035f), SpriteEffects.None, 0f);
        }
    }

    private static void DrawSpriteStampTrail(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor)
    {
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
        {
            DrawTipTrail(projectile, spec, slot, TextureAssets.MagicPixel.Value, new InfiniVfxState());
            return;
        }
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        int available = Math.Max(3, Math.Min(projectile.oldPos.Length, 10));
        int count = Math.Clamp((int)MathF.Round(3 + slot.Density * 9), 3, available);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(6f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale * 0.72f);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.12f, 3.0f);
        for (int i = count - 1; i >= 1; i--)
        {
            Vector2 center = ProjectileOldCenter(projectile, i);
            if (center == Vector2.Zero)
                continue;
            Vector2 pos = center - Main.screenPosition;
            float fade = (count - i) / (float)count;
            Main.spriteBatch.Draw(texture, pos, src, Color.White * slot.Alpha * fade * 0.55f, ProjectileOldRotation(projectile, i), origin, drawScale * (0.7f + fade * 0.35f), SpriteEffects.None, 0f);
        }
    }

    private static void DrawTipTrail(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Texture2D px, InfiniVfxState state)
    {
        state.EnsureHistory();
        Color c = PresentationColor(spec, (int)(255 * slot.Alpha));
        Vector2[] points = state.TipHistory;
        int count = Math.Clamp((int)MathF.Round(3 + slot.Density * 12), 3, Math.Min(points.Length, 22));
        float width = Math.Clamp(projectile.height * projectile.scale * (0.10f + slot.Scale * 0.14f), 1f, 16f);
        for (int i = 1; i < count; i++)
        {
            if (points[i - 1] == Vector2.Zero || points[i] == Vector2.Zero)
                continue;
            Vector2 a = points[i - 1] - Main.screenPosition;
            Vector2 b = points[i] - Main.screenPosition;
            float fade = (count - i) / (float)count;
            DrawLine(px, a, b, c * fade * 0.80f, width * fade);
        }
    }

    private static void DrawHistoryRibbon(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Texture2D px, InfiniVfxState state)
    {
        state.EnsureHistory();
        Vector2[] points = slot.Anchor is "self" or "owner" or "hitPoint" or "field" ? state.CenterHistory : state.TipHistory;
        Color c = PresentationColor(spec, (int)(255 * slot.Alpha));
        int count = Math.Clamp((int)MathF.Round(4 + slot.Density * 18), 4, Math.Min(points.Length, 28));
        for (int i = 1; i < count; i++)
        {
            if (points[i - 1] == Vector2.Zero || points[i] == Vector2.Zero)
                continue;
            float k = i / (float)Math.Max(1, count - 1);
            float width = MathHelper.Lerp(14f * slot.Scale, 1f, k);
            Color color = Color.Lerp(Color.White, c, 0.65f) * slot.Alpha * (1f - k);
            DrawLine(px, points[i - 1] - Main.screenPosition, points[i] - Main.screenPosition, color, width);
        }
    }

    private static void DrawGhostArc(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor)
    {
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
            return;
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        Vector2 center = projectile.Center - Main.screenPosition;
        Vector2 dir = MotionDirection(projectile);
        int count = Math.Clamp((int)MathF.Round(3 + slot.Density * 6), 3, 9);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(8f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.14f, 3.5f);
        for (int i = 0; i < count; i++)
        {
            float k = count == 1 ? 0f : i / (float)(count - 1);
            float side = (k - 0.5f) * 2f;
            Vector2 gdir = dir.RotatedBy(side * (0.22f + slot.Spread * 0.45f));
            Vector2 pos = center - gdir * (8f + 16f * k) + gdir.RotatedBy(MathHelper.PiOver2) * side * 5f;
            Main.spriteBatch.Draw(texture, pos, src, Color.White * slot.Alpha * (1f - k * 0.65f) * 0.42f, gdir.ToRotation() + MathHelper.PiOver2, origin, drawScale, SpriteEffects.None, 0f);
        }
    }

    private static void DrawWavyStrip(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor, InfiniVfxState state)
    {
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
            return;
        int stripW = Math.Clamp((int)MathF.Round(2 + slot.Density * 3), 1, 6);
        Vector2 basePos = projectile.Center - Main.screenPosition;
        float rot = projectile.rotation;
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(8f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.12f, 3.0f);
        for (int x = 0; x < texture.Width; x += stripW)
        {
            int w = Math.Min(stripW, texture.Width - x);
            Rectangle src = new(x, 0, w, texture.Height);
            float localX = x - texture.Width * 0.5f;
            float phase = state.Tick * 0.13f + x * (0.13f + slot.Spread * 0.08f) + slot.Variant;
            float sway = MathF.Sin(phase) * (1.5f + slot.Scale * 2.4f) * slot.Jitter;
            Vector2 local = new Vector2(localX, sway) * drawScale;
            Vector2 drawPos = basePos + local.RotatedBy(rot);
            Main.spriteBatch.Draw(texture, drawPos, src, Color.White * slot.Alpha * 0.72f, rot, new Vector2(w * 0.5f, texture.Height * 0.5f), drawScale, SpriteEffects.None, 0f);
        }
    }

    private static void DrawBeamLine(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Texture2D px)
    {
        Vector2 dir = MotionDirection(projectile);
        Vector2 center = projectile.Center - Main.screenPosition;
        float length = Math.Clamp(projectile.velocity.Length() * 18f + 180f * slot.Scale, 120f, 1600f);
        Color c = PresentationColor(spec, (int)(255 * slot.Alpha));
        DrawLine(px, center - dir * 8f, center + dir * length, c * 0.55f, Math.Clamp(projectile.height * 0.18f * slot.Scale, 2f, 24f));
        DrawLine(px, center, center + dir * length * 0.82f, Color.White * slot.Alpha * 0.45f, Math.Clamp(projectile.height * 0.06f * slot.Scale, 1f, 8f));
    }

    private static void DrawFieldPulse(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor)
    {
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
            return;
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        // v0.4.117: no sine pulse here. Constant glow/light is fine; the reported glitch was blinking.
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(18f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale * 1.4f);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.25f, 5.0f);
        Main.spriteBatch.Draw(texture, projectile.Center - Main.screenPosition, src, Color.White * slot.Alpha * 0.72f, projectile.rotation * 0.2f, origin, drawScale, SpriteEffects.None, 0f);
    }

    private static void DrawOrbitingMotes(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor, InfiniVfxState state)
    {
        Texture2D? texture = TextureForRole(spec, slot.ParticleRole) ?? TextureForRole(spec, slot.TextureRole);
        if (texture is null)
            return;
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        Vector2 center = projectile.Center - Main.screenPosition;
        int count = Math.Clamp((int)MathF.Round(2 + slot.Density * 8), 2, 12);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(4f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale * 0.38f);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.08f, 2.4f);
        float time = (state.Tick + (state.LocalSeed % 97)) * 0.045f * (1f + slot.Variant * 0.12f);
        float radius = Math.Clamp(Math.Max(projectile.width, projectile.height) * (0.55f + slot.Spread * 1.15f), 8f, 96f);
        for (int i = 0; i < count; i++)
        {
            float k = i / (float)count;
            float angle = MathHelper.TwoPi * k + time * ((i % 2 == 0) ? 1f : -0.72f);
            float pulse = 0.82f + MathF.Sin(time * 2.1f + i) * 0.16f;
            Vector2 pos = center + angle.ToRotationVector2() * radius * pulse;
            float alpha = slot.Alpha * (0.35f + 0.35f * MathF.Sin(time * 1.7f + i * 0.6f));
            Main.spriteBatch.Draw(texture, pos, src, Color.White * Math.Clamp(alpha, 0.05f, 0.85f), angle, origin, drawScale, SpriteEffects.None, 0f);
        }
    }


    private static void DrawActorAfterimagePlaceholder(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor, InfiniVfxState state)
    {
        // Safe placeholder for the future VisualActor layer from the master document.
        // It deliberately avoids Main.PlayerRenderer API risk and uses the generated projectile/child texture as an actor echo.
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
            texture = TextureForRole(spec, "projectile");
        if (texture is null)
            return;
        Player owner = Main.player[projectile.owner];
        if (owner is null || !owner.active)
            return;

        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        int count = Math.Clamp((int)MathF.Round(1 + slot.Density * 4), 1, 5);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(10f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale * 0.85f);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.12f, 3.2f);
        float t = (state.Tick + state.LocalSeed % 97) * 0.055f;
        Vector2 dir = MotionDirection(projectile);
        Vector2 normal = dir.RotatedBy(MathHelper.PiOver2);
        for (int i = 0; i < count; i++)
        {
            float k = i / (float)Math.Max(1, count - 1);
            float wave = MathF.Sin(t + i * 1.37f) * (3f + slot.Jitter * 8f);
            Vector2 pos = owner.MountedCenter - dir * (10f + 18f * i) + normal * wave - Main.screenPosition;
            float alpha = slot.Alpha * (0.20f + 0.30f * (1f - k));
            Main.spriteBatch.Draw(texture, pos, src, PresentationColor(spec) * Math.Clamp(alpha, 0.02f, 0.45f), projectile.rotation + wave * 0.01f, origin, drawScale * (1f - k * 0.16f), owner.direction < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None, 0f);
        }
    }

    private static void DrawImpactSprite(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor, Vector2 worldCenter, int timer)
    {
        Texture2D? texture = TextureForRole(spec, slot.TextureRole);
        if (texture is null)
        {
            DrawImpactRing(projectile, spec, slot, TextureAssets.MagicPixel.Value, worldCenter, timer);
            return;
        }
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        float t = 1f - timer / (float)Math.Max(1, slot.Duration);
        t = Math.Clamp(t, 0f, 1f);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(14f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale * MathHelper.Lerp(0.85f, 1.45f, t));
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.25f, 6.0f);
        float rotation = slot.Variant is 1 or 3 ? projectile.rotation + t * MathHelper.PiOver2 : projectile.rotation;
        float env = Envelope01(slot.Duration - timer, slot.Duration, slot.FadeIn, slot.FadeOut, slot.Curve);
        Color c = Color.Lerp(PresentationColor(spec), Color.White, 0.35f) * slot.Alpha * env * (1f - t * 0.55f);
        Main.spriteBatch.Draw(texture, worldCenter - Main.screenPosition, src, c, rotation, origin, drawScale, SpriteEffects.None, 0f);
        if (slot.Variant >= 3)
        {
            for (int i = 0; i < 3; i++)
            {
                Vector2 off = Vector2.UnitX.RotatedBy(MathHelper.TwoPi * i / 3f + t * 1.2f) * (8f + 18f * t) * slot.Scale;
                Main.spriteBatch.Draw(texture, worldCenter + off - Main.screenPosition, src, c * 0.30f, rotation, origin, drawScale * 0.55f, SpriteEffects.None, 0f);
            }
        }
    }

    private static void DrawImpactRing(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Texture2D px, Vector2 worldCenter, int timer)
    {
        float t = 1f - timer / (float)Math.Max(1, slot.Duration);
        t = Math.Clamp(t, 0f, 1f);
        float env = Envelope01(slot.Duration - timer, slot.Duration, slot.FadeIn, slot.FadeOut, slot.Curve);
        Color c = PresentationColor(spec, (int)(255 * slot.Alpha)) * env * (1f - t * 0.35f);
        float r = MathHelper.Lerp(8f, 28f + 36f * slot.Scale, t);
        Vector2 center = worldCenter - Main.screenPosition;
        int segments = Math.Clamp((int)MathF.Round(8 + slot.Density * 12), 8, 24);
        for (int i = 0; i < segments; i++)
        {
            Vector2 a = center + Vector2.UnitX.RotatedBy(MathHelper.TwoPi * i / segments) * r;
            Vector2 b = center + Vector2.UnitX.RotatedBy(MathHelper.TwoPi * (i + 1) / segments) * r;
            DrawLine(px, a, b, c, Math.Clamp(1.2f + slot.Scale * 0.65f, 1f, 6f));
        }
    }

    private static void DrawChildMotes(Projectile projectile, AttackSpec spec, VfxSlotSpec slot, Color lightColor, Vector2 worldCenter, int timer, int seed)
    {
        Texture2D? texture = TextureForRole(spec, slot.ParticleRole);
        if (texture is null)
            return;
        Rectangle src = new(0, 0, texture.Width, texture.Height);
        Vector2 origin = src.Size() * 0.5f;
        float t = 1f - timer / (float)Math.Max(1, slot.Duration);
        t = Math.Clamp(t, 0f, 1f);
        int count = Math.Clamp((int)MathF.Round(2 + slot.Density * 10), 2, 14);
        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(5f, Math.Max(projectile.width, projectile.height) * projectile.scale * slot.Scale * 0.45f);
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.10f, 2.5f);
        for (int i = 0; i < count; i++)
        {
            float angle = MathHelper.TwoPi * i / count + (seed % 628) * 0.01f + t * (slot.Variant + 1) * 0.8f;
            float radius = (8f + 34f * t) * (0.55f + 0.55f * slot.Spread) * (0.75f + (i % 3) * 0.12f);
            Vector2 pos = worldCenter + angle.ToRotationVector2() * radius - Main.screenPosition;
            float env = Envelope01(slot.Duration - timer, slot.Duration, slot.FadeIn, slot.FadeOut, slot.Curve);
            Main.spriteBatch.Draw(texture, pos, src, Color.White * slot.Alpha * env * (1f - t * 0.35f), angle, origin, drawScale * (1f - t * 0.35f), SpriteEffects.None, 0f);
        }
    }


// =============================================================================
// NAV: VFX_RUNTIME_BAKED_AND_PARTICLES
// =============================================================================
    private static void PlayBakedCommands(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, ref InfiniVfxState state, Vector2 origin, int elapsed)
    {
        if (slot.BakedCommands is not { Length: > 0 } || manifest.Budget.MaxParticlesTotal <= 0)
            return;
        foreach (var cmd in slot.BakedCommands)
        {
            if (cmd is null || cmd.Tick != Math.Max(0, elapsed))
                continue;
            EmitBakedCommand(projectile, spec, manifest, slot, cmd, ref state, origin);
        }
    }

    private static void EmitBakedCommand(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, VfxBakedCommandSpec cmd, ref InfiniVfxState state, Vector2 origin)
    {
        IVfxBackend backend = InfiniVfxBackends.BestAvailable();
        if (!backend.Available)
            return;
        if (!IsOnScreen(origin, 220f))
            return;
        if (!CanSpendParticle(manifest, ref state, Math.Max(0.1f, slot.BudgetWeight)))
            return;

        Vector2 forward = MotionDirection(projectile).SafeNormalize(Vector2.UnitX);
        Vector2 normal = forward.RotatedBy(MathHelper.PiOver2);
        float radius = Math.Max(projectile.width, projectile.height) * projectile.scale * Math.Clamp(slot.Scale, 0.05f, 8f) * 0.55f;
        Vector2 local = forward * (cmd.LocalX * radius) + normal * (cmd.LocalY * radius);
        float jitter = Math.Clamp(slot.Jitter, 0f, 2f) * 2.5f;
        if (jitter > 0f)
            local += Main.rand.NextVector2Circular(jitter, jitter);
        Vector2 world = origin + local;
        Vector2 velocity = forward * cmd.VelocityX + normal * cmd.VelocityY + projectile.velocity * 0.06f;

        Color tint = ParseColor(cmd.StartColor, PresentationColor(spec, (int)(255 * cmd.Alpha)));
        Color end = ParseColor(cmd.EndColor, Color.Transparent);
        backend.Emit(new VfxEmitCommand(
            world,
            velocity,
            tint,
            end,
            new Vector2(cmd.ScaleX, cmd.ScaleY),
            cmd.Rotation,
            cmd.Lifespan,
            cmd.Alpha,
            cmd.SeedBucket == 0 ? state.LocalSeed : cmd.SeedBucket,
            VfxParticleAddress.Resolve(cmd.ParticleSystemId, slot.RendererKind, slot.Channel, slot.Event, slot.Blend, slot.EmissionMode)));
    }


    private static float Envelope01(int age, int duration, float fadeIn = 0.15f, float fadeOut = 0.35f, string? curve = "smooth")
    {
        if (duration <= 1)
            return 1f;
        float t = Math.Clamp(age / (float)Math.Max(1, duration), 0f, 1f);
        float a = fadeIn <= 0f ? 1f : Math.Clamp(t / Math.Max(0.001f, fadeIn), 0f, 1f);
        float b = fadeOut <= 0f ? 1f : Math.Clamp((1f - t) / Math.Max(0.001f, fadeOut), 0f, 1f);
        float v = MathF.Min(a, b);
        if (curve == "linear")
            return v;
        if (curve == "sharp")
            return v * v;
        return v * v * (3f - 2f * v);
    }

    private static bool TrySpendDraw(VfxManifestSpec manifest, ref InfiniVfxState state, int cost = 1)
    {
        cost = Math.Max(0, cost);
        int cap = manifest?.Budget?.MaxDrawCalls ?? 0;
        if (cap > 0)
            cap = Math.Max(1, (int)MathF.Round(cap * InfiniVfxClientOptions.DrawBudgetMultiplier));
        if (cap <= 0 || cost <= 0)
            return true;
        if (state.DrawCallsThisFrame + cost > cap)
            return false;
        state.DrawCallsThisFrame += cost;
        return true;
    }

    private static bool CanSpendParticle(VfxManifestSpec manifest, ref InfiniVfxState state, float weight = 1f)
    {
        int cost = Math.Max(1, (int)MathF.Ceiling(weight));
        float scalar = Math.Clamp(InfiniVfxClientOptions.ParticleSpawnMultiplier, 0f, 2f);
        int perTickCap = Math.Max(0, (int)MathF.Round(manifest.Budget.MaxParticlesPerTick * scalar));
        int totalCap = Math.Max(0, (int)MathF.Round(manifest.Budget.MaxParticlesTotal * scalar));
        if (perTickCap <= 0 || totalCap <= 0)
            return false;
        if (state.ParticlesThisTick + cost > perTickCap)
            return false;
        if (state.ParticlesTotal + cost > totalCap)
            return false;
        state.ParticlesThisTick += cost;
        state.ParticlesTotal += cost;
        return true;
    }

    private static Color ParseColor(string? hex, Color fallback)
    {
        string h = (hex ?? "").Trim();
        if (h.StartsWith("#"))
            h = h[1..];
        if (h.Length == 6 && uint.TryParse(h, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out uint rgb))
            return new Color((byte)((rgb >> 16) & 255), (byte)((rgb >> 8) & 255), (byte)(rgb & 255), fallback.A);
        if (h.Length == 8 && uint.TryParse(h, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out uint rgba))
            return new Color((byte)((rgba >> 24) & 255), (byte)((rgba >> 16) & 255), (byte)((rgba >> 8) & 255), (byte)(rgba & 255));
        return fallback;
    }

    private static string ParticleAddressForSlot(VfxSlotSpec slot)
        => VfxParticleAddress.Resolve(slot.ParticleSystemId, slot.RendererKind, slot.Channel, slot.Event, slot.Blend, slot.EmissionMode);

    private static bool IsOnScreen(Vector2 world, float padding = 160f)
    {
        if (!InfiniVfxClientOptions.EnableScreenCulling)
            return true;
        Rectangle box = new((int)(Main.screenPosition.X - padding), (int)(Main.screenPosition.Y - padding), Main.screenWidth + (int)(padding * 2f), Main.screenHeight + (int)(padding * 2f));
        return box.Contains(world.ToPoint());
    }

    private static VfxParticleSystemKind ParticleKindForSlot(VfxSlotSpec slot)
        => VfxParticleAddress.KindFor(ParticleAddressForSlot(slot));

    private static Color ParticleColorForSlot(AttackSpec spec, VfxSlotSpec slot, int alpha)
    {
        Color c = PresentationColor(spec, alpha);
        VfxParticleSystemKind kind = ParticleKindForSlot(slot);
        return kind switch
        {
            VfxParticleSystemKind.Glow => Color.Lerp(c, Color.White, 0.18f),
            VfxParticleSystemKind.Spark => Color.Lerp(c, Color.White, 0.35f),
            VfxParticleSystemKind.Smoke => Color.Lerp(c, Color.Black, 0.38f),
            VfxParticleSystemKind.Shard => Color.Lerp(c, Color.White, 0.10f),
            _ => c
        };
    }

    private static Vector2 SlotAnchorPoint(Projectile projectile, VfxSlotSpec slot, InfiniVfxState state)
    {
        state.EnsureHistory();
        if (slot.Anchor == "owner" && projectile.owner >= 0 && projectile.owner < Main.maxPlayers)
            return Main.player[projectile.owner].MountedCenter;
        if (slot.Anchor == "tip" && state.TipHistory.Length > 0 && state.TipHistory[0] != Vector2.Zero)
            return state.TipHistory[0];
        if (slot.Anchor == "tipHistory" && state.TipHistory.Length > 2 && state.TipHistory[2] != Vector2.Zero)
            return state.TipHistory[2];
        if (slot.Anchor == "velocity")
            return projectile.Center + MotionDirection(projectile).SafeNormalize(Vector2.UnitX) * Math.Max(projectile.width, projectile.height) * projectile.scale * 0.65f;
        return projectile.Center;
    }

    private static Vector2 HistoryPoint(InfiniVfxState state, bool tip, int index)
    {
        state.EnsureHistory();
        Vector2[] history = tip ? state.TipHistory : state.CenterHistory;
        if (history.Length == 0)
            return Vector2.Zero;
        index = Math.Clamp(index, 0, history.Length - 1);
        return history[index];
    }

    private static int AmbientParticleCount(VfxSlotSpec slot, VfxParticleSystemKind kind)
    {
        int baseCount = kind switch
        {
            VfxParticleSystemKind.Spark => 1 + (slot.Density > 0.55f ? 1 : 0),
            VfxParticleSystemKind.Smoke => 1,
            VfxParticleSystemKind.Shard => 1,
            VfxParticleSystemKind.Glow => slot.Density > 0.68f ? 2 : 1,
            _ => 1
        };
        if (slot.Importance == "core" && slot.Density > 0.42f)
            baseCount++;
        return Math.Clamp(baseCount, 1, 3);
    }

    private static int BurstParticleCount(VfxManifestSpec manifest, VfxSlotSpec slot, VfxParticleSystemKind kind)
    {
        int maxCount = Math.Max(4, Math.Min(180, manifest.Budget.MaxParticlesPerTick * 2));
        float role = kind switch
        {
            VfxParticleSystemKind.Smoke => 0.72f,
            VfxParticleSystemKind.Spark => 0.52f,
            VfxParticleSystemKind.Glow => 0.62f,
            _ => 1f
        };
        int count = (int)MathF.Round((6 + slot.Density * 64) * manifest.Budget.SpawnRateMultiplier * InfiniVfxClientOptions.ParticleSpawnMultiplier * role);
        return Math.Clamp(count, 2, maxCount);
    }

    private static void EmitAmbientDust(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, ref InfiniVfxState state)
    {
        if (slot.Density <= 0.02f || !manifest.Budget.EnablePointSparks)
            return;
        IVfxBackend backend = InfiniVfxBackends.BestAvailable();
        if (!backend.Available)
            return;
        if (!IsOnScreen(projectile.Center, 220f))
            return;
        bool dustFallback = backend.Name == "vanillaDust";

        VfxParticleSystemKind kind = ParticleKindForSlot(slot);
        int denomBase = kind switch
        {
            VfxParticleSystemKind.Smoke => 22,
            VfxParticleSystemKind.Shard => 18,
            VfxParticleSystemKind.Spark => 13,
            VfxParticleSystemKind.Glow => 15,
            _ => 16
        };
        float spawnScalar = Math.Max(0.01f, manifest.Budget.SpawnRateMultiplier * InfiniVfxClientOptions.ParticleSpawnMultiplier);
        int denom = Math.Clamp((int)MathF.Round((denomBase - slot.Density * 10f) / spawnScalar), 2, 64);
        // Vanilla Dust is visual-only and capped by Terraria, so the fallback stays sparse and deliberate.
        if (dustFallback)
            denom = Math.Clamp((int)MathF.Round(denom * 1.65f), 4, 48);
        if (!Main.rand.NextBool(denom))
            return;

        Color color = ParticleColorForSlot(spec, slot, kind == VfxParticleSystemKind.Smoke ? 135 : 190);
        Vector2 dir = MotionDirection(projectile).SafeNormalize(Vector2.UnitX);
        Vector2 normal = dir.RotatedBy(MathHelper.PiOver2);
        int seed = slot.SlotSeed == 0 ? state.LocalSeed : state.LocalSeed ^ slot.SlotSeed;
        float phase = (state.Tick + (seed % 101)) * 0.08f + slot.PhaseOffset * MathHelper.TwoPi;
        Vector2 anchor = SlotAnchorPoint(projectile, slot, state);
        int emitCount = AmbientParticleCount(slot, kind);
        if (dustFallback)
            emitCount = Math.Min(emitCount, 1);

        for (int i = 0; i < emitCount; i++)
        {
            if (!CanSpendParticle(manifest, ref state, slot.BudgetWeight))
                break;

            float phaseI = phase + i * MathHelper.TwoPi / Math.Max(1, emitCount);
            Vector2 offset = slot.EmissionMode switch
            {
                "orbit" => phaseI.ToRotationVector2() * MathHelper.Lerp(8f, 42f, Math.Clamp(slot.Spread, 0f, 1.5f)),
                "residue" => Main.rand.NextVector2Circular(projectile.width * 0.42f, projectile.height * 0.42f) - dir * Main.rand.NextFloat(6f, 26f),
                "cone" => dir.RotatedByRandom(0.46f + slot.Jitter * 0.35f) * Main.rand.NextFloat(4f, 30f),
                "ring" => phaseI.ToRotationVector2() * MathHelper.Lerp(6f, 28f, slot.Spread),
                "spiral" => phaseI.ToRotationVector2() * (4f + (state.Tick % 28) * 0.9f),
                "point" => Main.rand.NextVector2Circular(3f + slot.Jitter * 5f, 3f + slot.Jitter * 5f),
                _ => -dir * Main.rand.NextFloat(4f, 20f) + normal * Main.rand.NextFloat(-6f, 6f) + Main.rand.NextVector2Circular(2f, 2f)
            };

            if (kind == VfxParticleSystemKind.Smoke)
                offset += -dir * Main.rand.NextFloat(2f, 12f);
            Vector2 pos = anchor + offset;
            Vector2 vel = slot.EmissionMode switch
            {
                "orbit" => normal * MathF.Sin(phaseI) * 0.25f,
                "residue" => -projectile.velocity * 0.04f + Main.rand.NextVector2Circular(0.30f, 0.30f),
                "cone" => dir.RotatedByRandom(0.35f) * Main.rand.NextFloat(0.35f, 1.65f),
                "ring" => offset.SafeNormalize(Vector2.UnitX) * Main.rand.NextFloat(0.35f, 1.30f),
                "spiral" => offset.SafeNormalize(Vector2.UnitX).RotatedBy(MathHelper.PiOver2) * 0.65f,
                "point" => Main.rand.NextVector2Circular(0.35f, 0.35f),
                _ => projectile.velocity * -0.055f + Main.rand.NextVector2Circular(0.65f, 0.65f)
            };

            float scale = kind switch
            {
                VfxParticleSystemKind.Spark => Math.Clamp(0.38f + slot.Scale * 0.18f, 0.28f, 1.25f),
                VfxParticleSystemKind.Smoke => Math.Clamp(0.70f + slot.Scale * 0.35f, 0.50f, 2.25f),
                VfxParticleSystemKind.Shard => Math.Clamp(0.48f + slot.Scale * 0.28f, 0.35f, 1.70f),
                _ => Math.Clamp(0.55f + slot.Scale * 0.28f, 0.40f, 1.90f)
            };
            int life = kind switch
            {
                VfxParticleSystemKind.Spark => 16,
                VfxParticleSystemKind.Smoke => 48,
                VfxParticleSystemKind.Shard => 28,
                _ => 26
            };
            if (dustFallback)
            {
                scale *= 0.86f;
                life = Math.Max(10, (int)(life * 0.72f));
            }
            backend.Emit(new VfxEmitCommand(pos, vel, color, Color.Transparent, new Vector2(scale), vel.ToRotation(), life, slot.Alpha, seed + i, ParticleAddressForSlot(slot)));
        }
    }

    private static void EmitTrailAccent(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, ref InfiniVfxState state)
    {
        if (slot.Density <= 0.08f || manifest.Budget.MaxParticlesTotal <= 0)
            return;
        IVfxBackend backend = InfiniVfxBackends.BestAvailable();
        if (!backend.Available)
            return;
        if (!IsOnScreen(projectile.Center, 220f))
            return;
        bool dustFallback = backend.Name == "vanillaDust";
        float spawnScalar = Math.Max(0.01f, manifest.Budget.SpawnRateMultiplier * InfiniVfxClientOptions.ParticleSpawnMultiplier);
        int denom = Math.Clamp((int)MathF.Round((18f - slot.Density * 11f) / spawnScalar), 3, 64);
        if (dustFallback)
            denom = Math.Clamp((int)MathF.Round(denom * 1.8f), 5, 56);
        if (!Main.rand.NextBool(denom) || !CanSpendParticle(manifest, ref state, Math.Max(0.5f, slot.BudgetWeight * 0.7f)))
            return;

        state.EnsureHistory();
        int maxIndex = Math.Min(state.TipHistory.Length - 1, 10);
        if (maxIndex <= 1)
            return;
        int idx = Main.rand.Next(1, maxIndex + 1);
        Vector2 p = HistoryPoint(state, true, idx);
        Vector2 prev = HistoryPoint(state, true, Math.Min(idx + 1, maxIndex));
        if (p == Vector2.Zero)
            return;
        Vector2 tangent = (p - prev).SafeNormalize(MotionDirection(projectile).SafeNormalize(Vector2.UnitX));
        float k = 1f - idx / (float)Math.Max(1, maxIndex);
        Color color = Color.Lerp(ParticleColorForSlot(spec, slot, (int)(180 * k)), Color.White, 0.20f);
        float scale = Math.Clamp((0.35f + slot.Scale * 0.20f) * (0.65f + k * 0.65f), 0.25f, 1.55f);
        Vector2 vel = -tangent * Main.rand.NextFloat(0.15f, 0.65f) + Main.rand.NextVector2Circular(0.25f, 0.25f);
        int life = 18 + (int)(12 * k);
        if (dustFallback)
        {
            scale *= 0.82f;
            life = Math.Max(8, (int)(life * 0.70f));
        }
        backend.Emit(new VfxEmitCommand(p + Main.rand.NextVector2Circular(2f, 2f), vel, color, Color.Transparent, new Vector2(scale), tangent.ToRotation(), life, slot.Alpha * 0.75f, state.LocalSeed ^ slot.SlotSeed ^ idx, ParticleAddressForSlot(slot)));
    }


    private static void EmitBurstDust(Projectile projectile, AttackSpec spec, VfxManifestSpec manifest, VfxSlotSpec slot, Vector2 center, ref InfiniVfxState state)
    {
        if (manifest.Budget.MaxParticlesTotal <= 0)
            return;
        IVfxBackend backend = InfiniVfxBackends.BestAvailable();
        if (!backend.Available)
            return;
        if (!IsOnScreen(center, 260f))
            return;
        bool dustFallback = backend.Name == "vanillaDust";

        VfxParticleSystemKind kind = ParticleKindForSlot(slot);
        int count = BurstParticleCount(manifest, slot, kind);
        if (dustFallback)
            count = Math.Clamp((int)MathF.Ceiling(count * 0.58f), 2, 64);
        float speed = Math.Clamp(1.0f + slot.Scale * 2.2f, 0.8f, 9f);
        Color color = ParticleColorForSlot(spec, slot, kind == VfxParticleSystemKind.Smoke ? 150 : 220);
        Vector2 forward = MotionDirection(projectile).SafeNormalize(Vector2.UnitX);
        Vector2 normal = forward.RotatedBy(MathHelper.PiOver2);

        for (int i = 0; i < count; i++)
        {
            if (!CanSpendParticle(manifest, ref state, slot.BudgetWeight))
                break;
            float t = i / (float)Math.Max(1, count);
            float angle = MathHelper.TwoPi * t + Main.rand.NextFloat(-0.20f, 0.20f);
            Vector2 radial = angle.ToRotationVector2();
            Vector2 dir = slot.EmissionMode switch
            {
                "cone" => forward.RotatedByRandom(0.38f + slot.Spread * 0.30f),
                "residue" => (-forward * 0.8f + Main.rand.NextVector2Circular(0.65f, 0.65f)).SafeNormalize(radial),
                "spiral" => radial.RotatedBy(0.7f + t * MathHelper.TwoPi * 0.35f),
                "point" => Main.rand.NextVector2Circular(1f, 1f).SafeNormalize(radial),
                _ => radial
            };
            float speedMul = kind switch
            {
                VfxParticleSystemKind.Smoke => Main.rand.NextFloat(0.16f, 0.58f),
                VfxParticleSystemKind.Spark => Main.rand.NextFloat(0.65f, 1.35f),
                VfxParticleSystemKind.Glow => Main.rand.NextFloat(0.28f, 0.95f),
                _ => Main.rand.NextFloat(0.35f, 1.05f)
            };
            Vector2 v = dir * speed * speedMul;
            if (slot.EmissionMode == "ring")
                v += normal * MathF.Sin(angle) * 0.25f;
            float scale = kind switch
            {
                VfxParticleSystemKind.Spark => Math.Clamp(0.38f + slot.Scale * 0.16f, 0.28f, 1.20f),
                VfxParticleSystemKind.Smoke => Math.Clamp(0.78f + slot.Scale * 0.32f, 0.55f, 2.40f),
                VfxParticleSystemKind.Shard => Math.Clamp(0.55f + slot.Scale * 0.24f, 0.40f, 1.85f),
                _ => Math.Clamp(0.58f + slot.Scale * 0.22f, 0.40f, 1.90f)
            };
            int life = kind switch
            {
                VfxParticleSystemKind.Spark => 14 + Main.rand.Next(0, 10),
                VfxParticleSystemKind.Smoke => 42 + Main.rand.Next(0, 34),
                VfxParticleSystemKind.Shard => 24 + Main.rand.Next(0, 18),
                _ => 24 + Main.rand.Next(0, 20)
            };
            Vector2 spawn = center + (slot.EmissionMode == "ring" ? radial * Main.rand.NextFloat(2f, 8f + slot.Spread * 10f) : Main.rand.NextVector2Circular(3f, 3f));
            Color c = (kind == VfxParticleSystemKind.Spark && i % 2 == 0) ? Color.Lerp(color, Color.White, 0.35f) : color;
            if (dustFallback)
            {
                scale *= 0.88f;
                life = Math.Max(10, (int)(life * 0.72f));
            }
            backend.Emit(new VfxEmitCommand(spawn, v, c, Color.Transparent, new Vector2(scale), v.ToRotation(), life, slot.Alpha, state.LocalSeed + i, ParticleAddressForSlot(slot)));
        }
    }


    private static int DustForColor(AttackSpec spec)
    {
        int effectDust = DustForEffect(spec);
        if (effectDust >= 0)
            return effectDust;
        Color c = PresentationColor(spec);
        if (c.G > c.R && c.G > c.B) return DustID.GreenTorch;
        if (c.R > c.B && c.R > c.G) return DustID.RedTorch;
        if (c.B > c.R && c.B > c.G) return DustID.Ice;
        if (c.R > 200 && c.G > 180) return DustID.YellowTorch;
        return DustID.WhiteTorch;
    }

    private static int DustForEffect(AttackSpec spec)
    {
        int code = spec?.EffectCode ?? -1;
        return code switch
        {
            1 => DustID.Electric,
            2 => DustID.t_Slime,
            3 => DustID.YellowStarDust,
            4 => DustID.Torch,
            5 => DustID.Ice,
            6 => DustID.Grass,
            7 => DustID.Shadowflame,
            8 => DustID.GreenTorch,
            9 => DustID.RedTorch,
            10 => DustID.YellowTorch,
            11 => DustID.Sand,
            12 => DustID.PinkTorch,
            13 => DustID.GemSapphire,
            14 => DustID.PurpleTorch,
            _ => -1,
        };
    }


// =============================================================================
// NAV: VFX_RUNTIME_LIGHT_SOUND
// =============================================================================
    private static void AddSlotLight(Projectile projectile, AttackSpec spec, VfxSlotSpec slot)
    {
        AddSlotLightAt(projectile.Center, spec, slot);
    }

    private static void AddSlotLightAt(Vector2 world, AttackSpec spec, VfxSlotSpec slot)
    {
        if (Main.netMode == NetmodeID.Server)
            return;
        float lightMul = InfiniVfxClientOptions.PresentationLightMultiplier;
        if (lightMul <= 0f)
            return;
        Color c = PresentationColor(spec);
        float strength = Math.Clamp(0.08f + slot.Scale * 0.06f + slot.Density * 0.10f, 0.02f, 0.45f) * lightMul;
        Lighting.AddLight(world, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
    }

    private static void PlaySlotSound(Vector2 world, AttackSpec spec, VfxSlotSpec slot, bool impact)
    {
        if (slot.Density < 0.05f || Main.dedServ)
            return;
        var style = InfiniSoundLibrary.ForVfxCue(
            spec.RuntimeFamily,
            spec.Effect,
            spec.SoundVolume,
            spec.SoundPitch,
            spec.SoundPitchVariance,
            slot.SlotSeed,
            impact,
            impact ? spec.SoundImpactCatalogId : spec.SoundUseCatalogId,
            impact ? spec.SoundImpactCatalogPath : spec.SoundUseCatalogPath,
            spec.SoundCatalogSource);
        float cueVolume = Math.Clamp(style.Volume * (0.22f + slot.Alpha * 0.58f), 0.04f, 0.72f);
        SoundEngine.PlaySound(style with { Volume = cueVolume }, world);
    }

    private static void DrawLine(Texture2D px, Vector2 a, Vector2 b, Color color, float width)
    {
        Vector2 delta = b - a;
        float len = delta.Length();
        if (len <= 0.01f)
            return;
        Main.spriteBatch.Draw(px, a, new Rectangle(0, 0, 1, 1), color, delta.ToRotation(), Vector2.Zero, new Vector2(len, Math.Max(0.5f, width)), SpriteEffects.None, 0f);
    }
}
