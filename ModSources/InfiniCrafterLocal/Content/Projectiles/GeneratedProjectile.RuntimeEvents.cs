#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using System;
using System.Linq;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private void RunRuntimeEvent(string eventName, NPC? target, int damageDone)
    {
        if (_data is null || _entity is null) return;
        Vector2 direction = Projectile.velocity.SafeNormalize(_initialDirection);
        foreach (RuntimeEventActionSpec action in _entity.ActionsFor(eventName))
        {
            if (action.DelayTicks > 0)
            {
                if (RuntimeDelayedActionScheduler.TrySchedule(
                    _data,
                    _entity,
                    action,
                    Owner(),
                    Projectile.GetSource_FromThis(),
                    target?.Center ?? Projectile.Center,
                    direction,
                    target,
                    damageDone,
                    _childDepth,
                    _activationSpawnBudget ?? new RuntimeSpawnBudget(0))
                    && action.ActionCode is RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.SelectTargetsAndEmit)
                    Projectile.netUpdate = true;
                continue;
            }
            RuntimeProgramExecutor.ExecuteAction(_data, _entity, action, Owner(), Projectile.GetSource_FromThis(), target?.Center ?? Projectile.Center, direction, target, damageDone, _childDepth, _activationSpawnBudget ?? new RuntimeSpawnBudget(0));
        }
    }

    private void EmitAndSyncVfxEvent(string eventName, Vector2 center)
    {
        if (_data is null || _entity is null) return;
        if (Main.netMode == Terraria.ID.NetmodeID.Server)
        {
            BroadcastAuthoritativeVfxEvent(eventName, center);
            return;
        }
        // Nonowner element events have one producer: the validated server relay.
        // Keep local legacy callbacks and live path registration independent.
        InfiniVfxRuntime.OnEvent(Projectile, _data, _entity.Id, eventName, _data.VfxManifest, ref _vfxState, center,
            includeMaterialElements: Main.netMode != Terraria.ID.NetmodeID.MultiplayerClient || Projectile.owner == Main.myPlayer);
        SendOwnerHitVfxEvent(eventName,center);
    }

    private void RunPeriodicActions()
    {
        if (_data is null || _entity is null) return;
        int dueActions = 0;
        // Periodic VFX is owned by OnTick/Draw and each VFX slot cadence,
        // not by the independent gameplay action periods below.
        foreach (RuntimeEventActionSpec action in _entity.ActionsFor(RuntimeEventKind.Periodic))
        {
            int period = AuthoredTicksToProjectileUpdates(Math.Max(6, action.PeriodTicks));
            if (_age % period != 0) continue;
            if (dueActions++ >= InfiniRuntimeLimits.MaxRuntimePeriodicActionsPerTick)
                break;
            Vector2 direction = Projectile.velocity.SafeNormalize(_initialDirection);
            if (action.DelayTicks > 0)
            {
                if (RuntimeDelayedActionScheduler.TrySchedule(
                    _data,
                    _entity,
                    action,
                    Owner(),
                    Projectile.GetSource_FromThis(),
                    Projectile.Center,
                    direction,
                    null,
                    Projectile.damage,
                    _childDepth,
                    _activationSpawnBudget ?? new RuntimeSpawnBudget(0))
                    && action.ActionCode is RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.SelectTargetsAndEmit)
                    Projectile.netUpdate = true;
            }
            else
                RuntimeProgramExecutor.ExecuteAction(_data, _entity, action, Owner(), Projectile.GetSource_FromThis(), Projectile.Center, direction, null, Projectile.damage, _childDepth, _activationSpawnBudget ?? new RuntimeSpawnBudget(0));
        }
    }

    public override bool? Colliding(Rectangle projHitbox, Rectangle targetHitbox)
    {
        if (!_configured || _entity is null || _activationDelayTicks > 0) return false;
        if (_entity.Controller.Code == RuntimeControllerCode.ChannelBeam)
        {
            GetChannelBeamGeometry(out Vector2 start, out Vector2 end, out float width);
            if ((end - start).LengthSquared() <= 0.01f) return false;
            float collisionPoint = 0f;
            return Collision.CheckAABBvLineCollision(targetHitbox.TopLeft(), targetHitbox.Size(), start, end, width, ref collisionPoint);
        }
        if (_entity.Movement.Code == 18 && _whipPoints.Count > 1)
        {
            float width = WhipCollisionWidth();
            for (int i = 1; i < _whipPoints.Count; i++)
            {
                float collisionPoint = 0f;
                if (Collision.CheckAABBvLineCollision(targetHitbox.TopLeft(), targetHitbox.Size(), _whipPoints[i - 1], _whipPoints[i], width, ref collisionPoint))
                    return true;
            }
            return false;
        }
        return null;
    }

    // Shared by collision and runtime_geometry presentation; no sprite scale or pose offsets.
    private void GetChannelBeamGeometry(out Vector2 start, out Vector2 end, out float width)
    {
        Player owner = Owner();
        RuntimeParamsSpec p = _entity!.Controller.Params;
        Vector2 direction = Projectile.velocity.SafeNormalize(_initialDirection);
        start = owner.MountedCenter + direction * 18f;
        double initialWidth = p.InitialWidthMultiplier ?? 1d;
        width = (float)(Math.Max(2f, p.WidthPx) * (initialWidth + (1d - initialWidth) * ChannelBeamWarmupProgress()));
        float length = Math.Max(16f, p.RangeTiles * 16f);
        if (p.RaycastTiles == true)
        {
            Collision.LaserScan(start, direction, width, length, _beamScanSamples);
            foreach (float sample in _beamScanSamples)
            {
                if (!float.IsFinite(sample))
                    throw new InvalidOperationException("native beam LaserScan returned a non-finite distance");
                // The explicit tile-raycast contract uses the shortest of three
                // width samples. No interpolation may extend past a current wall.
                length = Math.Min(length, Math.Max(0f, sample));
            }
        }
        end = start + direction * length;
    }

    public override void ModifyHitNPC(NPC target, ref NPC.HitModifiers modifiers)
    {
        if (!_configured || _entity?.Controller.Code != RuntimeControllerCode.ChannelBeam) return;
        double initial = _entity.Controller.Params.InitialDamageMultiplier ?? 1d;
        modifiers.SourceDamage *= (float)(initial + (1d - initial) * ChannelBeamWarmupProgress());
    }

    private float WhipCollisionWidth()
        => Math.Max(4f, _entity!.Hitbox.WidthPx * _entity.Hitbox.HitboxScale * 0.5f);

    public override void ModifyDamageHitbox(ref Rectangle hitbox)
    {
        if (_entity is null) return;
        float scale = _entity.Hitbox.HitboxScale;
        if (Math.Abs(scale - 1f) < 0.001f) return;
        int width = Math.Max(2, (int)MathF.Round(hitbox.Width * scale));
        int height = Math.Max(2, (int)MathF.Round(hitbox.Height * scale));
        hitbox = new Rectangle(hitbox.Center.X - width / 2, hitbox.Center.Y - height / 2, width, height);
    }

    public override bool? CanHitNPC(NPC target)
        => !_configured || _activationDelayTicks > 0 || _entity?.Damage.Enabled != true
            || _initialNpcExclusion.AppliesTo(target) ? false : null;

    public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (_data is null || _entity is null) return;
        RuntimeHitPullBridge.SendProjectileHit(Projectile, target, hit.Crit);
        if (IsGeneratedWhipTagSource && target.active && InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)
            && Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers
            && Main.player[Projectile.owner] is { active: true })
            target.GetGlobalNPC<Common.Players.GeneratedWhipTagGlobalNPC>().Mark(Projectile.owner);
        RunRuntimeEvent(RuntimeEventKind.OnHit, target, damageDone);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnHit, target.Center);
        if (hit.Crit)
        {
            RunRuntimeEvent(RuntimeEventKind.OnCrit, target, damageDone);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnCrit, target.Center);
        }
    }

    public override bool OnTileCollide(Vector2 oldVelocity)
    {
        if (_data is null || _entity is null) return true;
        RunRuntimeEvent(RuntimeEventKind.OnTileCollision, null, Projectile.damage);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnTileCollision, Projectile.Center);
        if (_entity.Movement.Code is 5 or 14 or 16)
        {
            _returning = true;
            Projectile.tileCollide = false;
            Projectile.velocity = -oldVelocity * 0.25f;
            Projectile.netUpdate = true;
            return false;
        }
        if (_remainingBounces <= 0) return true;
        _remainingBounces--;
        if (Math.Abs(Projectile.velocity.X - oldVelocity.X) > 0.01f) Projectile.velocity.X = -oldVelocity.X * 0.78f;
        if (Math.Abs(Projectile.velocity.Y - oldVelocity.Y) > 0.01f) Projectile.velocity.Y = -oldVelocity.Y * 0.78f;
        Projectile.netUpdate = true;
        return false;
    }

    public override void OnKill(int timeLeft)
    {
        if (_data is null || _entity is null) return;
        RuntimeHitPullBridge.RememberRetired(Projectile);
        if (!_expireEventRan && timeLeft <= 1)
        {
            _expireEventRan = true;
            RunRuntimeEvent(RuntimeEventKind.OnExpire, null, Projectile.damage);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
        }
        RunRuntimeEvent(RuntimeEventKind.OnKill, null, Projectile.damage);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnKill, Projectile.Center);
        _presentationRetired=true;
    }
}
