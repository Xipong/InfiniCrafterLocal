#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private GeneratedProjectile? FindMotionPoseWriter(Player owner)
    {
        GeneratedProjectile? selected = null;
        void Consider(GeneratedProjectile candidate) {
            if (!candidate._configured || !candidate.Projectile.active || candidate.Projectile.owner != owner.whoAmI
                || candidate._generatedItemId != _generatedItemId || candidate._entity?.ArmPose is not { } pose
                || !candidate.IsPrimaryRuntimeEntity || candidate._activationDelayTicks > 0
                || !candidate.MotionWindowActive(pose.Window)) return;
            if (selected is null || candidate.Projectile.identity < selected.Projectile.identity
                || candidate.Projectile.identity == selected.Projectile.identity && candidate.Projectile.whoAmI < selected.Projectile.whoAmI)
                selected = candidate;
        }
        Consider(this);
        foreach (var body in Main.projectile)
            if (body?.ModProjectile is GeneratedProjectile candidate) Consider(candidate);
        return selected;
    }

    private static float TriangleReach(float progress) => 1f - Math.Abs(progress * 2f - 1f);
    private void BuildLashPoints(Vector2 anchor, Vector2 axis, float progress, float reachPx, int segments,
        float sweepStart, float sweepEnd, float bendRatio, float gravity, int facing, float rangeMultiplier)
    {
        _whipPoints.Clear();
        float extension = MathF.Sin(progress * MathHelper.Pi);
        Vector2 direction = axis.RotatedBy(MathHelper.Lerp(sweepStart, sweepEnd, progress) * facing * gravity);
        Vector2 normal = direction.RotatedBy(MathHelper.PiOver2);
        float reach = reachPx * rangeMultiplier * extension;
        for (int i = 0; i <= segments; i++) {
            float t = i / (float)segments;
            float bend = MathF.Sin(t * MathHelper.Pi) * MathF.Sin(progress * MathHelper.TwoPi) * reach * bendRatio * gravity;
            _whipPoints.Add(anchor + direction * reach * t + normal * bend);
        }
    }
    private void CalculateMotionFrontHand(Player owner, Vector2 axis, int durationTicks, string startStretch,
        string peakStretch, string endStretch, double peakProgress,
        out Player.CompositeArmStretchAmount stretch, out float localArmRotation, out Vector2 hand,
        bool legacyClock = false)
    {
        // Legacy code20 intentionally used integer world-tick age; retain it.
        double ticks = legacyClock ? _age / Math.Max(1, Projectile.extraUpdates + 1)
            : _age / (double)Math.Max(1, Projectile.extraUpdates + 1);
        double t = Math.Clamp(ticks / durationTicks, 0d, 1d);
        int start = RuntimeParamsSpec.FrontHandStretchRank(startStretch);
        int peak = RuntimeParamsSpec.FrontHandStretchRank(peakStretch);
        int end = RuntimeParamsSpec.FrontHandStretchRank(endStretch);
        double rankValue = legacyClock ? start + (peak - start) * (1d - Math.Abs(2d * t - 1d))
            : MotionCurve(t, start, peak, end, peakProgress);
        double length = 4d + 2d * rankValue;
        int nearest = 0; double distance = double.PositiveInfinity;
        for (int rank = 0; rank <= 3; rank++) {
            double candidate = Math.Abs(4d + 2d * rank - length);
            if (candidate < distance) { nearest = rank; distance = candidate; }
        } // ties choose shorter native length, independent of extension direction
        stretch = nearest switch {
            0 => Player.CompositeArmStretchAmount.None,
            1 => Player.CompositeArmStretchAmount.Quarter,
            2 => Player.CompositeArmStretchAmount.ThreeQuarters,
            3 => Player.CompositeArmStretchAmount.Full,
            _ => throw new InvalidOperationException("invalid admitted native front-arm stretch"),
        };
        localArmRotation = axis.ToRotation() - owner.fullRotation - MathHelper.PiOver2;
        hand = owner.RotatedRelativePoint(owner.GetFrontHandPosition(stretch, localArmRotation), addGfxOffY: false);
    }

    // Shared adapter for external sprite/VFX owners. No draw-time mutation or
    // texture-dependent physics; parent can route old hand grip selection here.
    internal bool TryGetMotionPresentationAxis(out Vector2 axis)
    {
        axis = _initialDirection;
        if (!_configured || _entity?.Aim is null) return false;
        axis = MotionAxis(Owner(), publish: false); return true;
    }
    internal static float MotionSpriteRotation(RuntimeEntitySpec entity, SpritePresentationSelection selected,
        float rotation, Microsoft.Xna.Framework.Graphics.SpriteEffects effects)
        => !selected.ImpactTexture && entity.Rotation is not null
            ? SpritePresentation.AlignForward(rotation, SpritePresentation.RequireForwardAngle(selected.ForwardAngleDegrees), effects)
            : selected.ProjectileRotation(entity, rotation, effects);

    internal static Vector2 MotionSpriteOrigin(RuntimeEntitySpec entity, SpritePresentationSelection selected,
        int width, int height, float scale, Microsoft.Xna.Framework.Graphics.SpriteEffects effects,
        float drawRotation, Vector2 axis)
    {
        var anchor = MotionSpriteAnchor(entity, selected, drawRotation, effects, axis);
        return anchor?.Origin(width, height, scale, effects)
            ?? selected.ProjectileOrigin(entity, width, height, scale, effects);
    }
    internal static InfiniCrafterLocal.Common.VFX.InfiniVfxSpriteAnchor? MotionSpriteAnchor(RuntimeEntitySpec entity,
        SpritePresentationSelection selected, float drawRotation, Microsoft.Xna.Framework.Graphics.SpriteEffects effects, Vector2 axis)
    {
        if (selected.ImpactTexture) return null;
        if (entity.Attachment is not { Anchor: "front_hand" } attachment) {
            if (selected.FrontHandBody && entity.Movement.Code == 20 && selected.Grip is { } oldGrip
                && selected.ForwardAngleDegrees is { } oldAngle)
                return new((float)oldGrip.NormalizedX, (float)oldGrip.NormalizedY, oldAngle, entity.Movement.Params.HitboxOffsetPx!.Value);
            return null;
        }
        var grip = selected.Grip ?? throw new InvalidOperationException("front-hand body requires selected authored grip");
        grip.Validate();
        Vector2 offset = axis * attachment.AxisOffsetPx + axis.RotatedBy(MathHelper.PiOver2) * attachment.NormalOffsetPx;
        Vector2 local = offset.RotatedBy(-drawRotation);
        if ((effects & Microsoft.Xna.Framework.Graphics.SpriteEffects.FlipHorizontally) != 0) local.X = -local.X;
        if ((effects & Microsoft.Xna.Framework.Graphics.SpriteEffects.FlipVertically) != 0) local.Y = -local.Y;
        // Reuse the immutable sprite-anchor kernel even for a normal offset and
        // independently rotated body. This exact anchor can be frozen by VFX.
        // Reach is real rigid-body translation and is never canceled here.
        return new((float)grip.NormalizedX, (float)grip.NormalizedY,
            local.ToRotation() * (180f / MathHelper.Pi), local.Length());
    }

    internal bool HasFrontHandAttachment => _entity?.Attachment is { Anchor: "front_hand" } a && MotionWindowActive(a.Window);
    internal Vector2 FrontHandAttachmentOffset => _entity?.Attachment is { } a
        ? MotionAxis(Owner(), publish: false) * a.AxisOffsetPx
            + MotionAxis(Owner(), publish: false).RotatedBy(MathHelper.PiOver2) * a.NormalOffsetPx
        : Vector2.Zero;
}
