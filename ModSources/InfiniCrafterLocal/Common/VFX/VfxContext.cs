#nullable enable
using System;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Lightweight context passed through the VFX foundation layer.
/// v0.3.20 keeps the runtime manifest-driven, but this struct gives future baked/realtime
/// players a single place for phase, hit point, motion and owner data.
/// </summary>
public readonly struct VfxContext
{
    public readonly Vector2 Position;
    public readonly Vector2 Velocity;
    public readonly Vector2 AimDirection;
    public readonly Vector2 WeaponTip;
    public readonly Vector2 WeaponBase;
    public readonly Vector2 HitNormal;
    public readonly Vector2 TargetPosition;
    public readonly bool HasTargetPosition;
    public readonly float Rotation;
    public readonly float Phase01;
    public readonly int Seed;
    public readonly int OwnerWhoAmI;
    public readonly Vector2 HitPoint;
    public readonly bool HasHitPoint;
    public readonly int Time;

    public VfxContext(
        Vector2 position,
        Vector2 velocity,
        Vector2 aimDirection,
        Vector2 weaponTip,
        Vector2 weaponBase,
        Vector2 hitNormal,
        Vector2 targetPosition,
        bool hasTargetPosition,
        float rotation,
        float phase01,
        int seed,
        int ownerWhoAmI,
        Vector2 hitPoint,
        bool hasHitPoint,
        int time)
    {
        Position = position;
        Velocity = velocity;
        AimDirection = aimDirection;
        WeaponTip = weaponTip;
        WeaponBase = weaponBase;
        HitNormal = hitNormal.LengthSquared() > 0.0001f ? hitNormal.SafeNormalize(Vector2.UnitY) : Vector2.UnitY;
        TargetPosition = targetPosition;
        HasTargetPosition = hasTargetPosition;
        Rotation = rotation;
        Phase01 = MathHelper.Clamp(phase01, 0f, 1f);
        Seed = seed;
        OwnerWhoAmI = ownerWhoAmI;
        HitPoint = hitPoint;
        HasHitPoint = hasHitPoint;
        Time = time;
    }

    public static VfxContext FromProjectile(Projectile projectile, InfiniVfxState state, float phase01 = 0f)
    {
        Vector2 velocity = projectile.velocity;
        Vector2 aim = velocity.LengthSquared() > 0.0001f ? velocity.SafeNormalize(Vector2.UnitX) : projectile.rotation.ToRotationVector2().SafeNormalize(Vector2.UnitX);
        Vector2 tip = state.TipHistory.Length > 0 && state.TipHistory[0] != Vector2.Zero
            ? state.TipHistory[0]
            : projectile.Center + aim * Math.Max(projectile.width, projectile.height) * projectile.scale * 0.72f;
        Vector2 hitNormal = state.HitTimer > 0 ? (state.HitCenter - projectile.Center).SafeNormalize(aim) : aim;
        return new VfxContext(projectile.Center, velocity, aim, tip, projectile.Center, hitNormal, state.HitCenter, state.HitTimer > 0, projectile.rotation, phase01, state.LocalSeed, projectile.owner, state.HitCenter, state.HitTimer > 0, state.Tick);
    }
}
