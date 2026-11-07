#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    // Cursor-axis publication is independent of cursor-seek position.
    private Vector2? _frontHandPublishedAxis;
    private int _frontHandAxisSyncAge = -1000;

    private Vector2 FrontHandCursorDirection(Player owner)
    {
        if (Projectile.owner != Main.myPlayer)
            return new Vector2(Projectile.ai[0], Projectile.ai[1]).SafeNormalize(_initialDirection);
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

    private void ProjectFrontHand(Player owner, Vector2 axis,
        Player.CompositeArmStretchAmount stretch, float localArmRotation, bool turnOwner = true)
    {
        if (turnOwner) owner.ChangeDir(axis.X >= 0f ? 1 : -1);
        // SetCompositeArmFront negates its input under reverse gravity; the
        // getter consumes the final stored rotation, not that pre-conversion input.
        owner.SetCompositeArmFront(true, stretch, localArmRotation * owner.gravDir);
        owner.itemRotation = (axis.RotatedBy(-owner.fullRotation) * owner.direction).ToRotation() * owner.gravDir;
    }

    internal static bool TryProjectFrontHandUseStyle(Player owner, GeneratedItem item)
    {
        RuntimeEntitySpec? primary = item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.PrimaryEntityId);
        if (primary?.ArmPose is null) return false;
        foreach (Projectile projectile in Main.ActiveProjectiles)
        {
            if (projectile.owner != owner.whoAmI || projectile.ModProjectile is not GeneratedProjectile generated
                || !generated.Matches(item.Data.Id, primary.Id)) continue;
            if (primary.ArmPose is { } pose && generated._activationDelayTicks <= 0
                && generated.MotionWindowActive(pose.Window) && generated.IsPrimaryRuntimeEntity && OwnerCanControl(owner)
                && ReferenceEquals(generated.FindMotionPoseWriter(owner), generated)) {
                Vector2 motionAxis = generated.MotionAxis(owner, publish: false);
                generated.CalculateMotionFrontHand(owner, motionAxis, pose.DurationTicks, pose.StartStretch, pose.PeakStretch,
                    pose.EndStretch, pose.PeakProgress, out var nativeStretch, out float nativeRotation, out _);
                generated.ProjectFrontHand(owner, motionAxis, nativeStretch, nativeRotation, primary.Aim?.TurnOwner == true);
                return true;
            }

        }
        return false;
    }
}
