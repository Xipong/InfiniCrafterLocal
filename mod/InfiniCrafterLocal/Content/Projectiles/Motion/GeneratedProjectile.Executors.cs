#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    public override bool ShouldUpdatePosition()
        // Pending definitions suspend native position integration without destroying
        // the latest SyncProjectile velocity that hydration will resume.
        => _configured && !AbsoluteMotionActive();

    public override void AI()
    {
        if (!TryHydrate() || _data is null || _entity is null)
            return;

        _initialNpcExclusion = _initialNpcExclusion.AfterUpdate();

        if (_activationDelayTicks > 0)
        {
            _activationDelayTicks--;
            Projectile.friendly = false;
            Projectile.alpha = 220;
            Projectile.velocity = Vector2.Zero;
            // Native collision follows this AI call. The final waiting update
            // must remain harmless until on_spawn and the controller run below.
            return;
        }

        // Arming follows the active-age clock, not the one-shot event flag:
        // a peer can receive a waiting snapshot after observing on_spawn.
        if (_age == 0 && _entity.Spawn.OverTarget.DelayTicks > 0)
        {
            Projectile.alpha = 0;
            Projectile.friendly = _entity.Damage.Enabled && Projectile.damage > 0;
            Projectile.netUpdate = true;
        }

        // Cancellation and recurring payment admit the whole active update,
        // including on_spawn and periodic actions, not only motion/contact.
        if (!AdmitControlledGameplayBeforeEvents())
            return;

        if (!_spawnEventRan)
        {
            // Waiting suppresses movement, not the authored launch. Replay its
            // exact sampled/native-shot vector (or authored constant) only at first activation;
            // later hydration must not reset an already moving projectile.
            if (_age == 0 && _entity.Spawn.OverTarget.DelayTicks > 0
                && _entity.UsesInitialVelocity)
                Projectile.velocity = _sampledInitialVelocity ?? _nativeShotInitialVelocity
                    ?? (_entity.Spawn.Aim != "none" ? _initialDirection * _entity.Spawn.SpeedPxPerTick : Vector2.Zero);
            EmitSpawnEvent();
        }

        _age++;
        RunPeriodicActions();

        RunResolvedMotion();
        ApplyActiveModifiers();
        if (Projectile.active && _entity.Controller.Code == RuntimeControllerCode.TargetAndFire)
            ApplyTargetAndFire();
        ApplyNpcAttraction();
        ApplyHitboxCurveVisual();
        ApplyVisualScaleCurve();

        if (_entity.Light.Strength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(_entity.Light.Color, Color.White);
            float s = _entity.Light.Strength;
            Lighting.AddLight(Projectile.Center, c.R / 255f * s, c.G / 255f * s, c.B / 255f * s);
        }
        InfiniVfxRuntime.OnTick(Projectile, _data, _entity.Id, _data.VfxManifest, ref _vfxState);

        if (_entity.Rotation is null && Projectile.velocity.LengthSquared() > 0.01f)
            Projectile.rotation = SpritePresentation.ProjectileNativeRotation(_entity!, Projectile.velocity.ToRotation());

        ApplyMotionRotation();

        // Terraria decrements timeLeft after AI; 2 is still a live update and
        // is also the keep-alive value used by held/channelled controllers.
        if (Projectile.timeLeft <= 1 && !_expireEventRan)
        {
            _expireEventRan = true;
            RunRuntimeEvent(RuntimeEventKind.OnExpire, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
        }
    }

    private bool AdmitControlledGameplayBeforeEvents()
    {
        RuntimeEntitySpec entity = _entity!;
        var control = entity.OwnerControl;
        bool sustain = entity.ManaSustain is not null;
        if (control is null && !sustain)
            return true; // Free projectiles never acquire implicit held-input cancellation.

        Player owner = Owner();
        bool cancelled = control is not null && InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)
            && (!OwnerCanControl(owner) || control.RequireHeldItem && !HoldingGeneratedItem(owner)
                || control.RequireChannel && !owner.channel
                || control.RequireItemAnimation && owner.itemAnimation <= 0);
        // PaySustainedMana owns authority, native item cost and world-tick cadence.
        // Its later motion/controller call cannot debit the same tick again.
        if (cancelled || sustain && !PaySustainedMana(owner))
        {
            Projectile.friendly = false;
            Projectile.Kill();
            return false;
        }
        return true;
    }

    private void EmitSpawnEvent()
    {
        if (_spawnEventRan) return;
        _spawnEventRan = true;
        RunRuntimeEvent(RuntimeEventKind.OnSpawn, null, 0);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnSpawn, Projectile.Center);
    }

    private float HitboxCurveScale()
        => _entity?.HitboxCurve?.ScaleAt(_age, Projectile.extraUpdates + 1) ?? 1f;

    private void ApplyHitboxCurveVisual()
    {
        if (_entity?.HitboxCurve?.MirrorToSprite == true)
            Projectile.scale = _entity.Hitbox.DrawScale * _entity.Visual.Scale * HitboxCurveScale();
    }

    private void ApplyTargetAndFire()
    {
        if (!_entity!.Movement.IsConfigured && !HasComposableMotion) Projectile.velocity = Vector2.Zero;
        if (_entity.Targeting.IntervalTicks <= 0) return;
        _controllerTimer++;
        int interval = AuthoredTicksToProjectileUpdates(Math.Max(6, _entity.Targeting.IntervalTicks));
        if (_controllerTimer < interval || !InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile))
            return;
        _controllerTimer = 0;
        float range = Math.Max(16f, _entity.Targeting.RangeTiles * 16f);
        NPC? target = FindFiringTarget(range, _entity.Targeting);
        if (target is null) return;
        _lastTarget = target.whoAmI;
        string shotId = _entity.Targeting.ShotEntityId;
        Vector2 direction = Projectile.DirectionTo(target.Center);
        RuntimeSpawnBudget budget = _activationSpawnBudget ?? new RuntimeSpawnBudget(0);
        if (_entity.Targeting.DamageMultiplier is not float damageMultiplier)
            return;
        if (!RuntimeChildCombat.TryResolve(_entity.Targeting.DamageBasis, _entity.Targeting.KnockbackBasis,
            damageMultiplier, RuntimeParentCombat.Capture(Projectile.GetSource_FromThis(), Owner()),
            out int? damageOverride, out float? knockbackOverride))
            return;
        int requested = _entity.Targeting.Count ?? 1;
        int granted = budget.Reserve(requested);
        int spawned = granted == requested ? SpawnRuntimeEntity(_data!, shotId, Owner(), Projectile.GetSource_FromThis(),
            Projectile.Center, direction, _childDepth + 1, granted, requestedCount: requested,
            spreadOverride: (float)(_entity.Targeting.SpreadRadians ?? 0d),
            damageMultiplier: damageMultiplier, activationBudget: budget,
            rootDamageOverride: damageOverride, rootKnockbackOverride: knockbackOverride) : 0;
        budget.Return(granted - spawned);
        Projectile.netUpdate = true;
    }

    private NPC? FindFiringTarget(float range, RuntimeTargetingSpec targeting)
    {
        bool Admitted(NPC npc, out float score)
        {
            score = float.PositiveInfinity;
            if (!npc.CanBeChasedBy(Projectile)) return false;
            float distance = Vector2.Distance(Projectile.Center, npc.Center);
            // Geometric admission precedes the preference discount. A previous
            // or assigned target cannot turn a hard radius into a score radius.
            if (targeting.HardRange == true && distance > range) return false;
            score = npc.whoAmI == _lastTarget
                ? distance * (1f - Math.Clamp(targeting.SameTargetBias, 0f, 0.9f))
                : distance;
            if (targeting.HardRange != true && score >= range) return false;
            return targeting.RequireLineOfSight != true || Collision.CanHit(
                Projectile.position, Projectile.width, Projectile.height, npc.position, npc.width, npc.height);
        }

        if (targeting.TargetPolicy == "player_assigned_first")
        {
            NPC? assigned = Projectile.OwnerMinionAttackTargetNPC;
            if (assigned is not null && Admitted(assigned, out _)) return assigned;
        }
        NPC? selected = null;
        float best = float.PositiveInfinity;
        foreach (NPC npc in Main.ActiveNPCs)
            if (Admitted(npc, out float score) && score < best)
            {
                selected = npc;
                best = score;
            }
        return selected;
    }

    private Player Owner()
        => Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers ? Main.player[Projectile.owner] : Main.player[0];

    private static bool OwnerCanControl(Player owner)
        => owner is not null && owner.active && !owner.dead && !owner.noItems && !owner.CCed;

    private bool HoldingGeneratedItem(Player owner)
        => owner.HeldItem?.ModItem is GeneratedItem item && string.Equals(item.Data.Id, _generatedItemId, StringComparison.Ordinal);

}
