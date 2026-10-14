#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    // Publication state belongs only to explicit code20 cursor aim. Keep the
    // historical shared vector helper/old drivers byte-identical.
    private Vector2? _frontHandPublishedAxis;
    private int _frontHandAxisSyncAge = -1000;

    private Vector2 FrontHandCursorDirection(Player owner)
    {
        if (Projectile.owner != Main.myPlayer) return FrontHandAxis();
        Vector2 axis = (Main.MouseWorld - owner.MountedCenter).SafeNormalize(new Vector2(owner.direction, 0f));
        // ai also serves the local UseStyle projection, so it must not lag input.
        Projectile.ai[0] = axis.X; Projectile.ai[1] = axis.Y;
        if (!_frontHandPublishedAxis.HasValue
            || _age - _frontHandAxisSyncAge >= Math.Max(1, AuthoredTicksToProjectileUpdates(6))
                && Vector2.DistanceSquared(_frontHandPublishedAxis.Value, axis) > 0.0004f)
        {
            _frontHandPublishedAxis = axis;
            _frontHandAxisSyncAge = _age;
            Projectile.netUpdate = true;
        }
        return axis;
    }

    // One opt-in native pose owner. Geometry never reads texture/grip/scale.
    private bool CanProjectFrontHand(Player owner)
        => _configured && Projectile.active && _activationDelayTicks <= 0
            && _entity?.Movement.Code == 20 && IsPrimaryRuntimeEntity
            && OwnerCanControl(owner) && HoldingGeneratedItem(owner);

    private Vector2 FrontHandAxis()
    {
        if (_entity!.Movement.Params.AimMode == "initial") return _initialDirection;
        Vector2 synced = new(Projectile.ai[0], Projectile.ai[1]);
        return synced.SafeNormalize(_initialDirection);
    }

    private void CalculateFrontHand(Player owner, Vector2 axis,
        out Player.CompositeArmStretchAmount stretch, out float localArmRotation, out Vector2 hand)
    {
        RuntimeParamsSpec p = _entity!.Movement.Params;
        // _age is the existing serialized active-update clock; delayed activation
        // does not advance it. Whole world-tick age is invariant across extraUpdates.
        double activeTicks = _age / Math.Max(1, Projectile.extraUpdates + 1);
        double t = Math.Clamp(activeTicks / p.DurationTicks, 0d, 1d);
        double q = 1d - Math.Abs(2d * t - 1d);
        int start = RuntimeParamsSpec.FrontHandStretchRank(p.StartStretch);
        int peak = RuntimeParamsSpec.FrontHandStretchRank(p.PeakStretch);
        double length = 4d + 2d * (start + (peak - start) * q);
        int nearest = start; double distance = double.PositiveInfinity;
        for (int rank = start; rank <= peak; rank++)
        {
            double candidate = Math.Abs(4d + 2d * rank - length);
            if (candidate < distance) { nearest = rank; distance = candidate; }
        } // exact ties retain the shorter native arm
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

    private void ProjectFrontHand(Player owner, Vector2 axis,
        Player.CompositeArmStretchAmount stretch, float localArmRotation)
    {
        owner.ChangeDir(axis.X >= 0f ? 1 : -1);
        // SetCompositeArmFront negates its input under reverse gravity; the
        // getter consumes the final stored rotation, not that pre-conversion input.
        owner.SetCompositeArmFront(true, stretch, localArmRotation * owner.gravDir);
        owner.itemRotation = (axis.RotatedBy(-owner.fullRotation) * owner.direction).ToRotation() * owner.gravDir;
    }

    private void MoveFrontHand()
    {
        Player owner = Owner();
        if (!CanProjectFrontHand(owner)) { Projectile.friendly = false; Projectile.Kill(); return; }
        Vector2 axis = _entity!.Movement.Params.AimMode == "cursor" ? FrontHandCursorDirection(owner) : _initialDirection;
        owner.ChangeDir(axis.X >= 0f ? 1 : -1); // native getter's shoulder offset uses facing
        CalculateFrontHand(owner, axis, out var stretch, out float armRotation, out Vector2 hand);
        ProjectFrontHand(owner, axis, stretch, armRotation);
        Projectile.Center = hand + axis * _entity.Movement.Params.HitboxOffsetPx!.Value;
        Projectile.velocity = Vector2.Zero;
        Projectile.rotation = axis.ToRotation() + MathHelper.PiOver2;
        Projectile.spriteDirection = owner.direction;
        ClaimHeldProjectile(owner); // no animation/lifetime extension
    }

    internal static bool TryProjectFrontHandUseStyle(Player owner, GeneratedItem item)
    {
        RuntimeEntitySpec? primary = item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.PrimaryEntityId);
        if (primary?.Movement.Code != 20) return false;
        foreach (Projectile projectile in Main.ActiveProjectiles)
        {
            if (projectile.owner != owner.whoAmI || projectile.ModProjectile is not GeneratedProjectile generated
                || !generated.Matches(item.Data.Id, primary.Id) || !generated.CanProjectFrontHand(owner)) continue;
            Vector2 axis = generated.FrontHandAxis();
            owner.ChangeDir(axis.X >= 0f ? 1 : -1);
            generated.CalculateFrontHand(owner, axis, out var stretch, out float rotation, out _);
            generated.ProjectFrontHand(owner, axis, stretch, rotation);
            return true; // explicit singleton admission: no second arm owner
        }
        return false;
    }
}
