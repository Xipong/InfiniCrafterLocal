#nullable enable
using InfiniCrafterLocal.Common.Audio;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.Audio;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Projectiles;

// Exact charge-release vertical slice. This file owns only charge holdout state
// and conversion into ordinary authored primary projectiles on release.
public sealed partial class GeneratedProjectile
{
    public override bool? CanDamage()
        => IsChargeReleaseDelivery() || IsSentryDelivery() ? false : base.CanDamage();

    private bool ApplyChargeReleaseAI()
    {
        if (Projectile.owner < 0 || Projectile.owner >= Main.maxPlayers)
        {
            Projectile.Kill();
            return false;
        }
        Player owner = Main.player[Projectile.owner];
        Projectile.friendly = false;
        Projectile.damage = 0;
        Projectile.timeLeft = 2;
        Projectile.tileCollide = false;

        bool ownsGameplay = InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile);
        bool sameGeneratedItem = owner.HeldItem?.ModItem is GeneratedItem held
            && string.Equals(held.Data?.Id, _generatedItemId, StringComparison.Ordinal);
        bool validOwnerState = owner.active && !owner.dead && !owner.noItems && !owner.CCed && sameGeneratedItem;
        if (ownsGameplay && !validOwnerState)
        {
            Projectile.Kill();
            return false;
        }

        Vector2 hand = owner.MountedCenter;
        Vector2 direction = Projectile.velocity.SafeNormalize(Vector2.UnitX * owner.direction);
        if (Projectile.owner == Main.myPlayer)
        {
            Vector2 aimed = (Main.MouseWorld - hand).SafeNormalize(direction);
            if (Vector2.DistanceSquared(aimed, direction) > 0.0001f)
            {
                direction = aimed;
                Projectile.netUpdate = true;
            }
        }
        Projectile.Center = hand + direction * 18f;
        Projectile.velocity = direction;
        Projectile.rotation = direction.ToRotation();
        Projectile.direction = Projectile.spriteDirection = direction.X >= 0f ? 1 : -1;
        owner.ChangeDir(Projectile.direction);
        owner.heldProj = Projectile.whoAmI;
        owner.itemTime = 2;
        owner.itemAnimation = 2;
        owner.itemRotation = (direction * owner.direction).ToRotation();
        owner.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, direction.ToRotation() - MathHelper.PiOver2);

        if (!ownsGameplay)
            return true;
        if (owner.channel)
        {
            _chargeTicksAccumulated = Math.Min(_spec.ChargeTicks, _chargeTicksAccumulated + 1);
            return true;
        }
        if (!_chargeReleaseFired)
        {
            _chargeReleaseFired = true;
            FireChargedPrimaryShots(direction);
        }
        Projectile.Kill();
        return false;
    }

    private void FireChargedPrimaryShots(Vector2 direction)
    {
        if (Main.netMode != Terraria.ID.NetmodeID.Server)
        {
            SoundStyle releaseSound = InfiniSoundLibrary.ForUse(
                _spec.RuntimeFamily, _spec.Delivery, _spec.Effect,
                _spec.SoundVolume, _spec.SoundPitch, _spec.SoundPitchVariance,
                _spec.SoundUseCatalogId, _spec.SoundUseCatalogPath, _spec.SoundCatalogSource);
            SoundEngine.PlaySound(releaseSound, Projectile.Center);
        }
        int count = Math.Clamp(_spec.ShotCount, 1, 8);
        float ratio = Math.Clamp(_chargeTicksAccumulated / Math.Max(1f, _spec.ChargeTicks), 0f, 1f);
        float power = MathHelper.Lerp(1f, Math.Clamp(_spec.ChargePowerMultiplier, 1f, 3f), ratio);
        int damage = Math.Max(0, (int)Math.Round(Math.Max(0, Projectile.originalDamage) * power));
        float knockback = Projectile.knockBack * power;
        float spread = Math.Clamp(_spec.SpreadRadians, 0f, 0.75f);
        float speed = Math.Max(3f, _spec.Speed);
        AttackSpec released = _spec.CloneForRuntimeSpawn();
        GeneratedChildSpecPolicy.ConfigureChargeReleasedShot(released, _spec);

        for (int i = 0; i < count; i++)
        {
            float offset = count == 1 ? 0f : MathHelper.Lerp(-spread * 0.5f, spread * 0.5f, i / (float)(count - 1));
            Vector2 velocity = direction.RotatedBy(offset) * speed;
            int idx = Projectile.NewProjectile(Projectile.GetSource_FromThis(), Projectile.Center + direction * 12f, velocity, Type, damage, knockback, Projectile.owner, released.MovementCode, released.EffectCode, released.OnHitCode);
            if (idx >= 0 && idx < Main.maxProjectiles && Main.projectile[idx].ModProjectile is GeneratedProjectile generated)
            {
                generated.ApplyGeneratedSpec(released.CloneForRuntimeSpawn(), _vfxManifest, _generatedItemId);
                Main.projectile[idx].netUpdate = true;
                generated.BroadcastVisualSync();
            }
        }
    }
}
