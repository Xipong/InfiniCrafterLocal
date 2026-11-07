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
public sealed partial class InfiniVfxState
{
    public int Tick;
    public int DrawCallsThisFrame;
    public ulong LastGameUpdate = ulong.MaxValue;
    public string SourceKey = "";
    public Dictionary<InfiniVfxSlotEmissionKey, ulong> LastSlotEmission { get; } = new();

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
        float bodyScale = Content.Projectiles.GeneratedProjectile.BodyDrawScale(entity, projectile.scale);
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
public static partial class InfiniVfxRuntime
{
    public static void OnTick(Projectile projectile, GeneratedItemData data, string entityId, VfxManifestSpec manifest, ref InfiniVfxState state)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots) return;
        BeginPresentationTick(projectile, data, entityId, ref state);
        InfiniDetachedVfxSystem.RegisterPeriodicElements(data,entityId,state.SourceKey,VfxSourceBinding.Capture(projectile));
        InfiniDetachedVfxSystem.RegisterMaterialPaths(data,entityId,state.SourceKey,VfxSourceBinding.Capture(projectile));
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (InfiniDetachedVfxSystem.HasOwnedVfx(slot) || slot.Trail is not null) continue;
            if (!Matches(slot, entityId, RuntimeEventKind.Periodic) || !Cadence(slot, state.Tick)) continue;
            if (!TryAnchor(projectile, data, entityId, slot.Anchor, projectile.Center, out Vector2 anchor)) continue;
            if (!TryMarkSlotEmission(projectile, entityId, RuntimeEventKind.Periodic, slot, ref state)) continue;
            EmitSound(anchor, slot);
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
            if (!Matches(slot, entityId, eventName) || slot.Trail is not null) continue;
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
            EmitSound(anchor, slot);
        }
        return emitted;
    }

    private static void BeginPresentationTick(Projectile projectile, GeneratedItemData data, string entityId, ref InfiniVfxState state)
    {
        if (state.LastGameUpdate == Main.GameUpdateCount) return;
        BeginWorldTick(projectile, ref state);
        CaptureExplicitTrails(projectile,data,entityId,state);
    }

    private static void BeginWorldTick(Projectile projectile, ref InfiniVfxState state)
    {
        if (state.LastGameUpdate == Main.GameUpdateCount) return;
        state.LastGameUpdate = Main.GameUpdateCount;
        state.Tick++;
        if (state.SourceKey.Length == 0) state.SourceKey = Guid.NewGuid().ToString("N");
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
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(entityId);
        Vector2 bodyForward = SpritePresentation.ProjectileBodyAngle(entity, projectile.rotation).ToRotationVector2();
        return projectile.velocity.SafeNormalize(bodyForward);
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
            if (slot.Trail is null) continue;
            bool over = slot.Layer == "AfterProjectiles";
            if (pass == InfiniVfxDrawPass.UnderProjectile && over || pass == InfiniVfxDrawPass.OverProjectile && !over) continue;
            DrawExplicitTrail(pixel, projectile, data, entityId, slot, manifest, ref state);
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
        bool relay=occurrence!=0;
        if(occurrence==0)occurrence=InfiniDetachedVfxSystem.NewMaterialOccurrence();
        bool admitMaterials=InfiniDetachedVfxSystem.TryAdmitMaterialOccurrence(occurrence,relay);
        bool emitted = false;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (!Matches(slot, entityId, eventName) || slot.Trail is not null) continue;
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
            EmitSound(anchor, slot);
        }
        return emitted;
    }

    private static bool Matches(VfxSlotSpec slot, string entityId, string eventName)
        => slot is not null
            && string.Equals(slot.EntityId, entityId, StringComparison.Ordinal)
            && string.Equals(slot.Event, eventName, StringComparison.Ordinal);

    private static bool Cadence(VfxSlotSpec slot, int tick)
    {
        int repeat = slot.RepeatEvery!.Value;
        return tick >= slot.StartTick!.Value && (tick - slot.StartTick!.Value + slot.SlotSeed) % Math.Max(1, repeat) == 0;
    }

    private static void EmitSound(Vector2 center, VfxSlotSpec slot)
    {
        InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
        if (kind == InfiniVfxRendererKind.SoundCue)
        {
            SoundStyle sound = slot.ResolveSoundStyle();
            if (sound.Volume > 0f) SoundEngine.PlaySound(sound, center);
            return;
        }
    }

    private static bool SpendDraw(VfxManifestSpec manifest, ref InfiniVfxState state, int cost)
    {
        if (state.DrawCallsThisFrame + cost > InfiniVfxClientOptions.EffectiveDrawBudget(manifest.Budget.MaxDrawCalls)) return false;
        if(state.SourceKey.Length>0&&!InfiniDetachedVfxSystem.TrySpendSourceDraw(state.SourceKey,manifest.Budget.MaxDrawCalls,cost))return false;
        state.DrawCallsThisFrame += cost; return true;
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
