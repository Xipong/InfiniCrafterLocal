#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
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
                if (_pendingActions.Count < 32)
                    _pendingActions.Add(new PendingRuntimeAction(action, action.DelayTicks, target?.whoAmI ?? -1, target?.Center ?? Projectile.Center, direction, damageDone));
                continue;
            }
            RuntimeProgramExecutor.ExecuteAction(_data, action, Owner(), Projectile.GetSource_FromThis(), target?.Center ?? Projectile.Center, direction, target, damageDone, _childDepth, ref _remainingSpawnBudget);
        }
    }

    private void ProcessPendingActions()
    {
        if (_data is null || _pendingActions.Count == 0) return;
        for (int i = _pendingActions.Count - 1; i >= 0; i--)
        {
            PendingRuntimeAction pending = _pendingActions[i];
            int ticks = pending.Ticks - 1;
            if (ticks > 0)
            {
                _pendingActions[i] = pending with { Ticks = ticks };
                continue;
            }
            NPC? target = pending.NpcId >= 0 && pending.NpcId < Main.maxNPCs && Main.npc[pending.NpcId].active ? Main.npc[pending.NpcId] : null;
            RuntimeProgramExecutor.ExecuteAction(_data, pending.Action, Owner(), Projectile.GetSource_FromThis(), pending.Position, pending.Direction, target, pending.DamageDone, _childDepth, ref _remainingSpawnBudget);
            _pendingActions.RemoveAt(i);
        }
    }

    private void RunPeriodicActions()
    {
        if (_data is null || _entity is null) return;
        foreach (RuntimeEventActionSpec action in _entity.ActionsFor(RuntimeEventKind.Periodic))
        {
            int period = Math.Max(6, action.PeriodTicks);
            if (_age % period != 0) continue;
            RuntimeProgramExecutor.ExecuteAction(_data, action, Owner(), Projectile.GetSource_FromThis(), Projectile.Center, Projectile.velocity.SafeNormalize(_initialDirection), null, Projectile.damage, _childDepth, ref _remainingSpawnBudget);
            InfiniVfxRuntime.OnEvent(Projectile, _entity.Id, RuntimeEventKind.Periodic, _data.VfxManifest, ref _vfxState, Projectile.Center);
        }
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
        RunRuntimeEvent(RuntimeEventKind.OnHit, target, damageDone);
        InfiniVfxRuntime.OnEvent(Projectile, _entity.Id, RuntimeEventKind.OnHit, _data.VfxManifest, ref _vfxState, target.Center);
        if (hit.Crit)
        {
            RunRuntimeEvent(RuntimeEventKind.OnCrit, target, damageDone);
            InfiniVfxRuntime.OnEvent(Projectile, _entity.Id, RuntimeEventKind.OnCrit, _data.VfxManifest, ref _vfxState, target.Center);
        }
    }

    public override bool OnTileCollide(Vector2 oldVelocity)
    {
        if (_data is null || _entity is null) return true;
        RunRuntimeEvent(RuntimeEventKind.OnTileCollision, null, Projectile.damage);
        InfiniVfxRuntime.OnEvent(Projectile, _entity.Id, RuntimeEventKind.OnTileCollision, _data.VfxManifest, ref _vfxState, Projectile.Center);
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
            InfiniVfxRuntime.OnEvent(Projectile, _entity.Id, RuntimeEventKind.OnExpire, _data.VfxManifest, ref _vfxState, Projectile.Center);
        }
        RunRuntimeEvent(RuntimeEventKind.OnKill, null, Projectile.damage);
        InfiniVfxRuntime.OnEvent(Projectile, _entity.Id, RuntimeEventKind.OnKill, _data.VfxManifest, ref _vfxState, Projectile.Center);
    }
}
