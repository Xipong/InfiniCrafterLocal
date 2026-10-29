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
internal readonly record struct InfiniVfxSpriteAnchor(float X, float Y, float AxisDegrees, float HitboxOffsetPx)
{
    internal Vector2 Origin(int width, int height, float scale, SpriteEffects effects)
    {
        float x = X, y = Y, a = AxisDegrees * MathF.PI / 180f;
        Vector2 axis = new(MathF.Cos(a), MathF.Sin(a));
        if ((effects & SpriteEffects.FlipHorizontally) != 0) { x = 1 - x; axis.X = -axis.X; }
        if ((effects & SpriteEffects.FlipVertically) != 0) { y = 1 - y; axis.Y = -axis.Y; }
        return new Vector2(x * width, y * height) + axis * (HitboxOffsetPx / scale);
    }
}

// Fixed-size presentation facts captured while the source still exists. No live
// entity references or gameplay authority cross the detached/network boundary.
internal readonly record struct InfiniVfxProjectileSnapshot(
    Vector2 Center, Vector2 Tip, Vector2 Forward, Vector2? OwnerCenter, InfiniVfxSpritePose Pose)
{
    internal Vector2? MaterialTip { get; init; }
    // Owned-element units are pixels per world tick. The event payload also
    // carries raw projectile-update velocity for the simple native consumers.
    // Copy this technical value before source retirement.
    internal Vector2 MaterialVelocity { get; init; }
    internal bool TryMaterialAnchor(string anchor,Vector2 point,out Vector2 result)
    {
        if(anchor is "tip" or "tipHistory" && MaterialTip is {} tip){result=tip;return true;}
        return TryAnchor(anchor,point,out result);
    }
    internal static InfiniVfxProjectileSnapshot Capture(Projectile projectile, GeneratedItemData data, string entityId)
    {
        Vector2? ownerCenter = projectile.owner >= 0 && projectile.owner < Main.player.Length
            && Main.player[projectile.owner] is { active: true } owner ? owner.Center : null;
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(entityId);
        float bodyScale = Content.Projectiles.GeneratedProjectile.PreservesExplicitBodyScale(entity)
            ? projectile.scale : Math.Clamp(projectile.scale, 0.1f, 8f);
        return new(projectile.Center, InfiniVfxRuntime.ForwardTip(projectile, data, entityId),
            InfiniVfxRuntime.ForwardAxis(projectile, data, entityId), ownerCenter,
            new(projectile.rotation, bodyScale,
                projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None, projectile.gfxOffY)) {
            MaterialTip=projectile.ModProjectile is Content.Projectiles.GeneratedProjectile generated
                &&(generated.TryCapturePresentationGeometry("beam",out var points)||generated.TryCapturePresentationGeometry("whip",out points))?points[^1]:null,
            MaterialVelocity=projectile.velocity*projectile.MaxUpdates
        };
    }

    internal bool IsValid => Finite(Center) && Finite(Tip) && Finite(Forward)
        && Math.Abs(Forward.LengthSquared() - 1f) < 0.001f
        && (!OwnerCenter.HasValue || Finite(OwnerCenter.Value)) && (!MaterialTip.HasValue || Finite(MaterialTip.Value))
        && float.IsFinite(Pose.Rotation) && float.IsFinite(Pose.Scale) && Pose.Scale is >= 0.01f and <= 128f
        && float.IsFinite(Pose.GfxOffY) && Pose.Effects is SpriteEffects.None or SpriteEffects.FlipHorizontally;

    // Reuse the existing pose.Scale float on the event wire, not a second
    // scale/anchor payload. Exact bounds are .25*.25*.25 .. 4*4*8.
    // The decoder checks this bounded envelope; the resolved entity below
    // narrows it back to the historical clamp when no explicit scale component owns it.
    internal bool IsValidFor(RuntimeEntitySpec? entity)
        => IsValid && (Content.Projectiles.GeneratedProjectile.PreservesExplicitBodyScale(entity) || Pose.Scale is >= 0.1f and <= 8f);

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
        InfiniDetachedVfxSystem.RegisterPeriodicElements(data,entityId,state.SourceKey,VfxSourceBinding.Capture(projectile));
        InfiniDetachedVfxSystem.RegisterMaterialPaths(data,entityId,state.SourceKey,VfxSourceBinding.Capture(projectile));
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (InfiniDetachedVfxSystem.HasOwnedVfx(slot)) continue;
            if (!Matches(slot, entityId, RuntimeEventKind.Periodic) || !Cadence(slot, state.Tick)) continue;
            if (!TryAnchor(projectile, data, entityId, slot.Anchor, projectile.Center, out Vector2 anchor)) continue;
            if (!TryMarkSlotEmission(projectile, entityId, RuntimeEventKind.Periodic, slot, ref state)) continue;
            EmitSlot(data, entityId, anchor, projectile.velocity, slot, manifest, ref state, state.SourceKey);
        }
    }

    public static bool OnEvent(Projectile projectile, GeneratedItemData data, string entityId, string eventName, VfxManifestSpec manifest, ref InfiniVfxState state, Vector2 center,ulong occurrence=0,bool includeEventEmissions=true)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return false;
        BeginPresentationTick(projectile, data, entityId, ref state);
        InfiniVfxProjectileSnapshot snapshot = InfiniVfxProjectileSnapshot.Capture(projectile, data, entityId);
        if (!snapshot.IsValidFor(data.RuntimeProgram.TryGetEntity(entityId))) return false;
        if(occurrence==0)occurrence=InfiniDetachedVfxSystem.NewMaterialOccurrence();
        bool admitMaterials=includeEventEmissions&&InfiniDetachedVfxSystem.TryAdmitMaterialOccurrence(occurrence,relay:false);
        bool emitted = false;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, eventName)) continue;
            if (!snapshot.TryAnchor(slot.Anchor, center, out Vector2 anchor)) continue;
            if(slot.Path is not null) {
                InfiniDetachedVfxSystem.RegisterMaterialPaths(data,entityId,state.SourceKey,VfxSourceBinding.Capture(projectile));
                continue;
            }
            // A remote native callback registers live paths, but discrete events
            // have one producer: the validated relay (regardless of arrival order).
            if (!includeEventEmissions) continue;
            if (InfiniDetachedVfxSystem.HasSnapshotVfx(slot)) {
                if(!admitMaterials||!snapshot.TryMaterialAnchor(slot.Anchor,center,out anchor))continue;
                emitted |= InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,entityId,slot,state.SourceKey,new(anchor,
                    slot.Anchor=="velocity"?projectile.velocity.SafeNormalize(snapshot.Forward):snapshot.Forward,snapshot.MaterialVelocity){SourceCenter=snapshot.Center},VfxSourceBinding.Capture(projectile));
                continue;
            }
            // An entity can hit several NPCs (or the same NPC more than once)
            // in one world tick. Keep the tick guard for lifecycle callbacks,
            // but each native hit/crit callback owns a separate occurrence.
            bool firstThisTick = TryMarkSlotEmission(projectile, entityId, eventName, slot, ref state);
            bool localHit = eventName is (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                && (Main.netMode != NetmodeID.MultiplayerClient || projectile.owner == Main.myPlayer);
            if (!firstThisTick && !localHit) continue;
            emitted = true;
            EmitPrimitive(data, anchor, slot.Anchor == "velocity" ? projectile.velocity : snapshot.Forward, slot, manifest, state.SourceKey);
            if (VfxRendererRegistry.Resolve(slot) != InfiniVfxRendererKind.ImpactSprite)
                EmitEventSprite(data, entityId, anchor, projectile.velocity, slot, manifest, state.SourceKey,
                    snapshot.Pose, snapshot.Forward);
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
    {
        var entity = data.RuntimeProgram.TryGetEntity(entityId);
        if ((entity?.BeamGeometry is not null || entity?.LashGeometry is not null)
            && projectile.ModProjectile is Content.Projectiles.GeneratedProjectile motion
            && (motion.TryCapturePresentationGeometry("beam", out var points) || motion.TryCapturePresentationGeometry("whip", out points)))
            return points[^1];
        return projectile.Center + ForwardAxis(projectile, data, entityId) * (projectile.width * projectile.scale * 0.5f);
    }

    internal static Vector2 ForwardAxis(Projectile projectile, GeneratedItemData data, string entityId)
    {
        if (projectile.ModProjectile is Content.Projectiles.GeneratedProjectile motion
            && motion.TryGetMotionPresentationAxis(out var motionAxis)) return motionAxis;
        foreach (RuntimeEntitySpec entity in data.RuntimeProgram.Entities)
            if (entity.Id == entityId && entity.Movement.Code is 14 or 16 or 17)
                return projectile.rotation.ToRotationVector2();
        if (data.RuntimeProgram.TryGetEntity(entityId)?.Movement.Code == 20)
            return (projectile.rotation - MathHelper.PiOver2).ToRotationVector2();
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
            if (InfiniDetachedVfxSystem.HasOwnedVfx(slot) || slot.RendererKind is "soundCue" or "lightCue") continue;
            // Nonperiodic procedural/sprite effects have detached event lifetimes.
            // History renderers need live samples; retain their on_spawn trail path.
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            if (slot.Event != RuntimeEventKind.Periodic
                && !(slot.Event == RuntimeEventKind.OnSpawn && kind is InfiniVfxRendererKind.HistoryRibbon or InfiniVfxRendererKind.TipTrail)) continue;
            if (kind is InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.SoundCue or InfiniVfxRendererKind.ChildMotes) continue;
            bool over = slot.Layer == "AfterProjectiles";
            if (pass == InfiniVfxDrawPass.UnderProjectile && over) continue;
            if (pass == InfiniVfxDrawPass.OverProjectile && !over) continue;
            if (!TryAnchor(projectile, data, entityId, slot.Anchor, projectile.Center, out Vector2 anchor)) continue;
            Vector2 forward = slot.Anchor == "velocity"
                ? projectile.velocity.SafeNormalize(projectile.rotation.ToRotationVector2()) : ForwardAxis(projectile, data, entityId);
            Color color = ApplyBlend(slot.Color!.ToColor() * slot.Alpha!.Value, slot.Blend!);
            switch (VfxRendererRegistry.Resolve(slot))
            {
                case InfiniVfxRendererKind.SpriteStampTrail:
                    SpritePresentationSelection selected = SpritePresentation.Resolve(data, entityId, slot.TextureRole!);
                    Texture2D? texture = InfiniCrafterLocalMod.Sprites.TryGet(selected.Path);
                    if (texture is not null)
                        DrawSelectedSpriteTrail(texture, projectile, data.RuntimeProgram.TryGetEntity(entityId), selected, manifest, ref state, color, slot.Scale!.Value);
                    break;
                case InfiniVfxRendererKind.TipTrail:
                    DrawHistory(pixel, manifest, ref state, state.TipHistory, state.TipHistoryCount, color, Math.Max(1f, slot.Scale!.Value * 2f));
                    break;
                case InfiniVfxRendererKind.HistoryRibbon:
                    DrawTrail(pixel, manifest, ref state, color, Math.Max(1f, slot.Scale!.Value * 2f));
                    break;
                case InfiniVfxRendererKind.BeamLine:
                    if (SpendDraw(manifest, ref state, 1))
                        DrawLine(pixel, anchor - Main.screenPosition, anchor - Main.screenPosition + forward * Math.Max(20f, slot.Scale!.Value * 48f), color, Math.Max(1f, slot.Scale!.Value * 2f));
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

    internal static bool OnDetachedEvent(GeneratedItemData data, string entityId, string eventName,
        VfxManifestSpec manifest, Vector2 center, Vector2 inheritedVelocity, string sourceKey,
        InfiniVfxProjectileSnapshot snapshot,VfxSourceBinding? binding=null,ulong occurrence=0)
    {
        if (Main.dedServ || data is null || manifest is null || !manifest.HasSlots || string.IsNullOrWhiteSpace(sourceKey))
            return false;
        if (!snapshot.IsValidFor(data.RuntimeProgram.TryGetEntity(entityId))) return false;
        var state = new InfiniVfxState { Tick = (int)Main.GameUpdateCount, SourceKey = sourceKey };
        bool relay=occurrence!=0;
        if(occurrence==0)occurrence=InfiniDetachedVfxSystem.NewMaterialOccurrence();
        bool admitMaterials=InfiniDetachedVfxSystem.TryAdmitMaterialOccurrence(occurrence,relay);
        bool emitted = false;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, eventName)) continue;
            Vector2 anchor = center;
            if (!snapshot.TryAnchor(slot.Anchor, center, out anchor)) continue;
            if (slot.Path is not null) continue; // live geometry requires its registered source binding
            if (!InfiniDetachedVfxSystem.HasSnapshotVfx(slot)) emitted = true;
            if (InfiniDetachedVfxSystem.HasSnapshotVfx(slot)) {
                if(!admitMaterials||!snapshot.TryMaterialAnchor(slot.Anchor,center,out anchor))continue;
                emitted |= InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,entityId,slot,sourceKey,new(anchor,
                    slot.Anchor=="velocity"?inheritedVelocity.SafeNormalize(snapshot.Forward):snapshot.Forward,snapshot.MaterialVelocity){SourceCenter=snapshot.Center},binding);
                continue;
            }
            EmitPrimitive(data, anchor, slot.Anchor != "velocity" ? snapshot.Forward : inheritedVelocity,
                slot, manifest, sourceKey);
            if (VfxRendererRegistry.Resolve(slot) != InfiniVfxRendererKind.ImpactSprite)
                EmitEventSprite(data, entityId, anchor, inheritedVelocity, slot, manifest, sourceKey, snapshot.Pose, snapshot.Forward);
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
        int repeat = slot.RepeatEvery!.Value > 0 ? slot.RepeatEvery!.Value : Math.Clamp(14 - (int)MathF.Round(slot.Density!.Value * 8f), 4, 18);
        return tick >= slot.StartTick!.Value && (tick - slot.StartTick!.Value + slot.SlotSeed) % Math.Max(1, repeat) == 0;
    }

    private static void EmitSlot(GeneratedItemData data, string entityId, Vector2 center, Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, ref InfiniVfxState state, string sourceKey, bool detachedParticleBudget = false)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        if (kind == InfiniVfxRendererKind.SoundCue)
        {
            SoundStyle sound = slot.ResolveSoundStyle();
            if (sound.Volume > 0f) SoundEngine.PlaySound(sound, center);
            return;
        }
        Color color = slot.Color!.ToColor();
        if (kind == InfiniVfxRendererKind.LightCue)
        {
            float strength = Math.Clamp(slot.Scale!.Value * 0.22f, 0.04f, 1.2f) * InfiniVfxClientOptions.PresentationLightMultiplier;
            if (strength > 0f)
                Lighting.AddLight(center, color.ToVector3() * strength);
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
            ? Math.Clamp(2 + (int)MathF.Round(slot.Density!.Value * 8f), 2, 10)
            : 1;
        count = InfiniVfxClientOptions.ScaleParticleCount(count);
        for (int i = 0; i < count; i++)
        {
            bool accepted = detachedParticleBudget
                ? InfiniDetachedVfxSystem.TrySpendDetachedParticle(sourceKey, manifest.Budget.MaxParticlesPerTick, manifest.Budget.MaxParticlesTotal)
                : SpendParticle(manifest, ref state);
            if (!accepted) break;
            float angle = count == 1 ? Main.rand.NextFloat(MathHelper.TwoPi) : MathHelper.TwoPi * i / count;
            float speed = Math.Clamp(0.35f + slot.Spread!.Value * 1.7f, 0.2f, 4f);
            Vector2 velocity = angle.ToRotationVector2() * speed + inheritedVelocity * 0.08f;
            Dust dust = Dust.NewDustPerfect(center, VfxRendererRegistry.DustId(slot.ParticleSystemId), velocity, 100, color, Math.Clamp(slot.Scale!.Value, 0.2f, 3f));
            dust.noGravity = slot.ParticleSystemId is not "Smoke";
        }
    }

    // Event form of a sprite trail is one fading texture snapshot, not invented
    // trajectory samples. Dust remains an independent choice at the caller.
    internal static bool EmitEventSprite(GeneratedItemData data, string entityId, Vector2 center,
        Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, string sourceKey,
        InfiniVfxSpritePose? pose = null, Vector2? forwardAxis = null)
    {
        if (VfxRendererRegistry.Resolve(slot) is not (InfiniVfxRendererKind.ImpactSprite
            or InfiniVfxRendererKind.SpriteStampTrail)) return false;
        if (VfxRendererRegistry.Resolve(slot) == InfiniVfxRendererKind.ImpactSprite)
        {
            // Dedicated impacts use a directional convention independent of body pose.
            EmitImpactSprite(data, entityId, center, inheritedVelocity, slot, manifest, sourceKey);
            return true;
        }
        SpritePresentationSelection selected = SpritePresentation.Resolve(data, entityId, slot.TextureRole!);
        if (string.IsNullOrWhiteSpace(selected.Path) || !selected.ImpactTexture && (!selected.RenderSizePx.HasValue || !selected.ForwardAngleDegrees.HasValue)) return false;
        Color color = ApplyBlend(slot.Color!.ToColor(), slot.Blend!);
        if (pose is { } captured)
        {
            // Snapshot/network remains raw native pose + dimensionless body scale;
            // Explicit authored scale components preserve the same scale as the body.
            // Capture the selected texture's corrected pose and base size only here.
            var entity = data.RuntimeProgram.TryGetEntity(entityId);
            var selectedPose = captured with { Rotation = entity is not null
                ? Content.Projectiles.GeneratedProjectile.MotionSpriteRotation(entity, selected, captured.Rotation, captured.Effects)
                : selected.ProjectileRotation(entity, captured.Rotation, captured.Effects) };
            InfiniDetachedVfxSystem.Enqueue(sourceKey, selected.Path, slot.Layer!, center + new Vector2(0, captured.GfxOffY),
                selectedPose.Rotation, captured.Scale * slot.Scale!.Value, slot.Alpha!.Value, color,
                slot.Duration!.Value, manifest.Budget.MaxDrawCalls, selectedPose, selected.RenderSizePx,
                entity is not null ? Content.Projectiles.GeneratedProjectile.MotionSpriteAnchor(entity, selected,
                    selectedPose.Rotation, selectedPose.Effects, forwardAxis ?? inheritedVelocity.SafeNormalize(Vector2.UnitX)) : null);
        }
        else
        {
            float rotation = inheritedVelocity.LengthSquared() > 0.01f ? inheritedVelocity.ToRotation() : 0f;
            InfiniVfxSpritePose? selectedPose = null;
            if (selected.ForwardAngleDegrees is { } axis)
            {
                rotation = SpritePresentation.AlignForward(rotation, axis, SpriteEffects.None);
                selectedPose = new(rotation, 1f, SpriteEffects.None, 0f);
            }
            // Item callers provide a direction rather than a projectile body pose.
            // A declared axis aligns the selected image in that frame.
            InfiniDetachedVfxSystem.Enqueue(sourceKey, selected.Path, slot.Layer!, center, rotation,
                Math.Clamp(slot.Scale!.Value, 0.05f, 8f), slot.Alpha!.Value, color, slot.Duration!.Value, manifest.Budget.MaxDrawCalls,
                selectedPose, selected.RenderSizePx);
        }
        return true;
    }

    internal static bool EmitPrimitive(GeneratedItemData data, Vector2 center, Vector2 inheritedVelocity,
        VfxSlotSpec slot, VfxManifestSpec manifest, string sourceKey)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        if (kind is not (InfiniVfxRendererKind.WavyStrip or InfiniVfxRendererKind.FieldPulse
            or InfiniVfxRendererKind.OrbitingMotes or InfiniVfxRendererKind.GhostArc
            or InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.BeamLine)) return false;
        InfiniDetachedVfxSystem.EnqueuePrimitive(sourceKey, kind, slot.Layer!, center,
            inheritedVelocity.SafeNormalize(Vector2.UnitX), slot.Scale!.Value, slot.Density!.Value, slot.PhaseOffset,
            slot.RepeatEvery!.Value, slot.Duration!.Value, ApplyBlend(slot.Color!.ToColor() * slot.Alpha!.Value, slot.Blend!),
            manifest.Budget.MaxDrawCalls);
        return true;
    }

    // Shared by projectile and item event producers. Missing assets stay silent;
    // an authored sprite must never be replaced by an unrelated particle effect.
    internal static void EmitImpactSprite(GeneratedItemData data, string entityId, Vector2 center,
        Vector2 inheritedVelocity, VfxSlotSpec slot, VfxManifestSpec manifest, string sourceKey)
    {
        string texturePath = SpritePresentation.Resolve(data, entityId, slot.TextureRole!).Path;
        if (string.IsNullOrWhiteSpace(texturePath)) return;
        InfiniDetachedVfxSystem.Enqueue(
            sourceKey, texturePath, slot.Layer!, center,
            inheritedVelocity.LengthSquared() > 0.01f ? inheritedVelocity.ToRotation() : 0f,
            slot.Scale!.Value, slot.Alpha!.Value, ApplyBlend(slot.Color!.ToColor(), slot.Blend!),
            slot.Duration!.Value, manifest.Budget.MaxDrawCalls);
    }

    private static bool SpendParticle(VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (state.ParticlesThisTick >= manifest.Budget.MaxParticlesPerTick || state.ParticlesTotal >= manifest.Budget.MaxParticlesTotal) return false;
        if(state.SourceKey.Length>0&&!InfiniDetachedVfxSystem.TrySpendDetachedParticle(state.SourceKey,manifest.Budget.MaxParticlesPerTick,manifest.Budget.MaxParticlesTotal))return false;
        state.ParticlesThisTick++; state.ParticlesTotal++; return true;
    }

    private static bool SpendDraw(VfxManifestSpec manifest, ref InfiniVfxState state, int cost)
    {
        if (state.DrawCallsThisFrame + cost > InfiniVfxClientOptions.EffectiveDrawBudget(manifest.Budget.MaxDrawCalls)) return false;
        if(state.SourceKey.Length>0&&!InfiniDetachedVfxSystem.TrySpendSourceDraw(state.SourceKey,manifest.Budget.MaxDrawCalls,cost))return false;
        state.DrawCallsThisFrame += cost; return true;
    }

    private static void DrawSelectedSpriteTrail(Texture2D texture, Projectile projectile, RuntimeEntitySpec? entity,
        SpritePresentationSelection selected, VfxManifestSpec manifest, ref InfiniVfxState state, Color color, float scale)
    {
        if (!selected.ImpactTexture && (!selected.RenderSizePx.HasValue || !selected.ForwardAngleDegrees.HasValue)) return;
        SpriteEffects effects = projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
        float rotation = entity is not null ? Content.Projectiles.GeneratedProjectile.MotionSpriteRotation(entity, selected, projectile.rotation, effects)
            : selected.ProjectileRotation(entity, projectile.rotation, effects);
        float drawScale = selected.ImpactTexture ? Math.Max(0.05f, projectile.scale * scale)
            : Math.Clamp(projectile.scale, 0.1f, 8f) * scale * selected.FrameScale(texture.Width, texture.Height);
        if (!selected.ImpactTexture && Content.Projectiles.GeneratedProjectile.PreservesExplicitBodyScale(entity))
            drawScale = projectile.scale * scale * selected.FrameScale(texture.Width, texture.Height);
        Vector2 origin = entity is not null ? Content.Projectiles.GeneratedProjectile.MotionSpriteOrigin(entity, selected,
            texture.Width, texture.Height, drawScale, effects, rotation,
            projectile.ModProjectile is Content.Projectiles.GeneratedProjectile source && source.TryGetMotionPresentationAxis(out var poseAxis)
                ? poseAxis : projectile.velocity.SafeNormalize(Vector2.UnitX))
            : selected.ProjectileOrigin(entity, texture.Width, texture.Height, drawScale, effects);
        for (int i = 2; i < state.HistoryCount; i += 3)
        {
            if (!SpendDraw(manifest, ref state, 1)) break;
            float fade = 1f - i / (float)state.CenterHistory.Length;
            Main.spriteBatch.Draw(texture, state.CenterHistory[i] - Main.screenPosition + new Vector2(0f, projectile.gfxOffY),
                null, color * fade, rotation, origin, drawScale, effects, 0f);
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
            forward, slot.Scale!.Value, slot.Density!.Value, phase, color,
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
        int age = tick - slot.StartTick!.Value;
        phase = 0f;
        if (age < 0) return false;
        float turns = age / (float)Math.Max(1, slot.RepeatEvery!.Value > 0 ? slot.RepeatEvery!.Value : slot.Duration!.Value) + slot.PhaseOffset;
        phase = turns - MathF.Floor(turns);
        return true;
    }

    internal static void DrawLine(Texture2D pixel, Vector2 start, Vector2 end, Color color, float width, bool preserveWidth = false)
    {
        Vector2 delta = end - start;
        float lengthSquared = delta.LengthSquared();
        // Explicit physical geometry can be smaller than one pixel; reject only
        // a degenerate/nonfinite segment or nonpositive width on that path.
        // Old visual calls retain their existing length cutoff and width floor.
        if (lengthSquared <= (preserveWidth ? 0f : 0.01f)
            || preserveWidth && (!float.IsFinite(lengthSquared) || !float.IsFinite(width) || width <= 0f)) return;
        // SpriteBatch scale is per source texel, not a destination pixel size.
        // Center the width on the segment so reversing it preserves its footprint.
        Main.spriteBatch.Draw(pixel, start, null, color, delta.ToRotation(),
            new Vector2(0f, pixel.Height * 0.5f),
            new Vector2(delta.Length() / pixel.Width, (preserveWidth ? width : Math.Max(1f, width)) / pixel.Height), SpriteEffects.None, 0f);
    }
}
