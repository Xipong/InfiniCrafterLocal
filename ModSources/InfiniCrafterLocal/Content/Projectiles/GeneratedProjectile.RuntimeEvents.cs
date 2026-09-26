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
                    && action.ActionCode == RuntimeEventActionCode.SpawnEntity)
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
        InfiniVfxRuntime.OnEvent(Projectile, _data, _entity.Id, eventName, _data.VfxManifest, ref _vfxState, center);
    }

    private void RunPeriodicActions()
    {
        if (_data is null || _entity is null) return;
        int dueActions = 0;
        bool emitted = false;
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
                    && action.ActionCode == RuntimeEventActionCode.SpawnEntity)
                    Projectile.netUpdate = true;
            }
            else
                RuntimeProgramExecutor.ExecuteAction(_data, _entity, action, Owner(), Projectile.GetSource_FromThis(), Projectile.Center, direction, null, Projectile.damage, _childDepth, _activationSpawnBudget ?? new RuntimeSpawnBudget(0));
            emitted = true;
        }
        if (emitted)
            EmitAndSyncVfxEvent(RuntimeEventKind.Periodic, Projectile.Center);
    }

    public override bool? Colliding(Rectangle projHitbox, Rectangle targetHitbox)
    {
        if (!_configured || _entity is null || _activationDelayTicks > 0) return false;
        if (_entity.Controller.Code == RuntimeControllerCode.ChannelBeam)
        {
            Player owner = Owner();
            Vector2 direction = Projectile.velocity.SafeNormalize(_initialDirection);
            Vector2 start = owner.MountedCenter + direction * 18f;
            Vector2 end = start + direction * Math.Max(16f, _entity.Controller.Params.RangeTiles * 16f);
            float collisionPoint = 0f;
            return Collision.CheckAABBvLineCollision(targetHitbox.TopLeft(), targetHitbox.Size(), start, end, Math.Max(2f, _entity.Controller.Params.WidthPx), ref collisionPoint);
        }
        if (_entity.Movement.Code == 18 && _whipPoints.Count > 1)
        {
            float width = Math.Max(4f, _entity.Hitbox.WidthPx * _entity.Hitbox.HitboxScale * 0.5f);
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
        => !_configured || _activationDelayTicks > 0 || _entity?.Damage.Enabled != true ? false : null;

    public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (_data is null || _entity is null) return;
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
        if (!_expireEventRan && timeLeft <= 1)
        {
            _expireEventRan = true;
            RunRuntimeEvent(RuntimeEventKind.OnExpire, null, Projectile.damage);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
        }
        RunRuntimeEvent(RuntimeEventKind.OnKill, null, Projectile.damage);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnKill, Projectile.Center);
    }
}
