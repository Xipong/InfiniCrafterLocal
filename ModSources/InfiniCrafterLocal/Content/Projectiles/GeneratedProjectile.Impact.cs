#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Audio;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Projectiles;

// AGENT MAP: collision, on-hit effects, AOE, mobility-on-impact and child
// projectile execution. Child projectiles must stay bounded by explicit
// MaxChildProjectiles/MaxChildDepth and must not inherit prose or nested
// generated item authoring.
public sealed partial class GeneratedProjectile
{
// =============================================================================
// NAV: PROJECTILE_COLLISION_AND_HIT
// =============================================================================
    public override bool? Colliding(Rectangle projHitbox, Rectangle targetHitbox)
    {
        if (IsThrustDelivery() || IsWhipDelivery())
        {
            Vector2 start, end, dir;
            if (IsWhipDelivery()) WhipLine(out start, out end, out dir);
            else HeldThrustLine(out start, out end, out dir);
            float collisionPoint = 0f;
            float lineWidth = Math.Max(8f, Math.Max(Projectile.width, Projectile.height) * Math.Max(0.8f, Projectile.scale) * Math.Max(0.75f, _spec.HitboxScale));
            return Collision.CheckAABBvLineCollision(
                new Vector2(targetHitbox.Left, targetHitbox.Top),
                new Vector2(targetHitbox.Width, targetHitbox.Height),
                start,
                end,
                lineWidth,
                ref collisionPoint
            );
        }
        return base.Colliding(projHitbox, targetHitbox);
    }


    private int ProjectileHitboxRadiusBonus()
    {
        if (_spec.ContactForgivenessPx > 0)
            return Math.Clamp(_spec.ContactForgivenessPx, 0, 32);
        if (_spec.AoeDamageRadiusPx > 0)
            return Math.Clamp(_spec.AoeDamageRadiusPx / 4, 0, 32);
        return 0;
    }

    public override void ModifyDamageHitbox(ref Rectangle hitbox)
    {
        float scale = Math.Clamp(Math.Max(1f, _spec.HitboxScale), 1f, 2.25f);
        int radiusBonus = ProjectileHitboxRadiusBonus();
        int inflateX = (int)(hitbox.Width * (scale - 1f) * 0.5f) + radiusBonus;
        int inflateY = (int)(hitbox.Height * (scale - 1f) * 0.5f) + radiusBonus;
        if (inflateX > 0 || inflateY > 0) hitbox.Inflate(inflateX, inflateY);
    }

    private void TryRunImpactMobility(Vector2 impactCenter)
    {
        if (_impactMobilityUsed) return;
        string mode = (_spec.MobilityMode ?? "").Trim().ToLowerInvariant();
        if (mode != "blink_to_projectile_impact") return;
        if (!InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) return;
        if (Projectile.owner < 0 || Projectile.owner >= Main.maxPlayers) return;
        Player owner = Main.player[Projectile.owner];
        if (owner is null || !owner.active || owner.dead) return;

        int rangeTiles = Math.Clamp(_spec.MobilityRangeTiles <= 0 ? 24 : _spec.MobilityRangeTiles, 1, 80);
        Vector2 target = impactCenter;
        Vector2 delta = target - owner.Center;
        float max = rangeTiles * 16f;
        if (delta.Length() > max)
            target = owner.Center + delta.SafeNormalize(Vector2.UnitX * owner.direction) * max;
        Vector2 destination = new(target.X - owner.width / 2f, target.Y - owner.height / 2f);
        if (_spec.MobilitySafeTileOnly && !IsSafeOwnerTeleportDestination(owner, destination))
            return;

        var modPlayer = owner.GetModPlayer<InfiniCraftPlayer>();
        if (!modPlayer.TryReserveGeneratedMobilityCooldown(_spec.MobilityCooldownTicks))
            return;

        _impactMobilityUsed = true;
        owner.Teleport(destination, 0);
        InfiniRuntimeAuthority.SyncTeleport(owner, destination);
    }

    private static bool IsSafeOwnerTeleportDestination(Player owner, Vector2 destination)
    {
        Rectangle target = new((int)destination.X, (int)destination.Y, owner.width, owner.height);
        if (target.Left < 16 || target.Top < 16 || target.Right >= (Main.maxTilesX - 1) * 16 || target.Bottom >= (Main.maxTilesY - 1) * 16)
            return false;
        int left = Math.Max(0, target.Left / 16 - 1);
        int right = Math.Min(Main.maxTilesX - 1, target.Right / 16 + 1);
        int top = Math.Max(0, target.Top / 16 - 1);
        int bottom = Math.Min(Main.maxTilesY - 1, target.Bottom / 16 + 1);
        for (int x = left; x <= right; x++)
        for (int y = top; y <= bottom; y++)
        {
            Tile tile = Main.tile[x, y];
            if (tile.HasTile && Main.tileSolid[tile.TileType] && !Main.tileSolidTop[tile.TileType])
            {
                Rectangle block = new(x * 16, y * 16, 16, 16);
                if (target.Intersects(block)) return false;
            }
            if (tile.LiquidAmount > 0 && tile.LiquidType == LiquidID.Lava)
                return false;
        }
        return true;
    }

    public override bool? CanHitNPC(NPC target)
    {
        if (_spawnIgnoreTicks > 0 && target is not null && target.whoAmI == _spawnIgnoreNpc)
            return false;
        return base.CanHitNPC(target);
    }

    public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
    {
        int onHit = _spec.OnHitCode;
        int effect = _spec.EffectCode;
        PlayImpactSound();
        TryRunImpactMobility(target.Center);
        // If an overlay carrier is spawned, it owns the timed hit VFX. Otherwise draw it on this projectile.
        if (!SpawnPersistentVfxOverlay("hit", target.Center, Math.Max(12, VfxEventLifetime("hit")), Projectile.velocity))
            InfiniVfxRuntime.OnHit(Projectile, target.Center, _spec, _vfxManifest, ref _vfxState);
        EmitVanillaImpactPolish(target.Center, false);
        switch (onHit)
        {
            case 1: BurstDust(effect, 16, 2.2f); break;
            case 2: SplitProjectiles(target, _spec.SplitCount); break;
            case 3: ChainProjectiles(target, _spec.ChainCount); target.AddBuff(BuffID.Electrified, DebuffDuration(90)); break;
            case 4: target.AddBuff(BuffID.OnFire, DebuffDuration(240)); break;
            case 5: target.AddBuff(BuffID.Frostburn, DebuffDuration(180)); break;
            case 6: target.AddBuff(BuffID.Poisoned, DebuffDuration(240)); break;
            case 7: target.AddBuff(BuffID.ShadowFlame, DebuffDuration(180)); break;
            case 8: RadialBurst(target.Center, _spec.SplitCount, _spec.SecondaryDamageMultiplier, target.whoAmI); break;
            case 9: target.AddBuff(BuffID.Bleeding, DebuffDuration(180)); break;
            case 10: AuraPulse(target.Center); break;
            case 11: if (_spec.SplitCount > 0) SporeCloud(target.Center, target.whoAmI); if (_spec.SecondaryDamageMultiplier > 0f) target.AddBuff(BuffID.Poisoned, DebuffDuration(180)); break;
            case 12: if (_spec.SplitCount > 0) MiniMissiles(target.Center, target.whoAmI); break;
            case 13: if (_spec.SplitCount > 0) VortexSpawn(target.Center, target.whoAmI); break;
            case 14: BlackholePull(); break;
            case 15: if (_spec.SplitCount > 0) RadialBurst(target.Center, _spec.SplitCount, _spec.SecondaryDamageMultiplier, target.whoAmI); break;
            case 16: if (_spec.ChainCount > 0) ChainProjectiles(target, _spec.ChainCount); target.AddBuff(BuffID.Electrified, DebuffDuration(140)); break;
            case 17: HealOwner(damageDone); BurstDust(effect, 8, 1.2f); break;
            case 18: if (_spec.SplitCount > 0) Starfall(target.Center, _spec.SplitCount, _spec.SecondaryDamageMultiplier, target.whoAmI); break;
        }
    }

    private int DebuffDuration(int fallbackTicks)
    {
        int authored = _spec.DebuffTime;
        if (authored <= 0) return fallbackTicks;
        return Math.Clamp(authored, 30, 600);
    }

    private bool RuntimePlanMode => _configured && _spec.RuntimePlanAuthored;


// =============================================================================
// NAV: PROJECTILE_CHILD_AND_OVERLAY
// =============================================================================

    private void HealOwner(int damageDone)
    {
        if (Projectile.owner < 0 || Projectile.owner >= Main.maxPlayers) return;
        Player owner = Main.player[Projectile.owner];
        if (!owner.active || owner.dead) return;
        int heal = Math.Clamp(Math.Max(1, damageDone / 4), 1, 4);
        if (owner.statLife >= owner.statLifeMax2) return;
        owner.statLife = Math.Min(owner.statLifeMax2, owner.statLife + heal);
        owner.HealEffect(heal);
    }


    private int RuntimeChildCount(int requested)
    {
        int cap = Math.Max(0, _spec.MaxChildProjectiles);
        if (cap <= 0 || requested <= 0) return 0;
        return Math.Clamp(requested, 1, cap);
    }

    private bool CanRunChildEffect(bool rootOnly = false)
    {
        if (!InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile))
            return false;
        float depth = Projectile.localAI[1];
        if (rootOnly && depth > 0.001f)
            return false;
        if (Math.Max(0, _spec.MaxChildProjectiles) <= 0)
            return false;
        // SpawnChild receives depth + 1. If current depth already reached the authored
        // root cap, a child would be rejected anyway; keep all on-hit families on the
        // same policy instead of per-effect hidden depth tables.
        return depth < Math.Max(0, _spec.MaxChildDepth);
    }

    private void SplitProjectiles(NPC target, int count)
    {
        if (!CanRunChildEffect() || count <= 0) return;
        count = RuntimeChildCount(count);
        if (count <= 0) return;
        AttackSpec childSpec = ChildSpec(0, 0);
        childSpec.EffectCode = _spec.EffectCode;
        childSpec.Lifetime = _spec.SecondaryLifetimeTicks;
        childSpec.MaxChildProjectiles = 0;
        childSpec.MaxChildDepth = 0;
        float spread = _spec.SecondarySpreadRadians;
        int dmg = Math.Max(0, (int)(Projectile.damage * _spec.SecondaryDamageMultiplier));
        Vector2 baseDir = Projectile.velocity.SafeNormalize(Vector2.UnitY);
        float speed = Math.Max(4f, Projectile.velocity.Length() * 0.78f);
        for (int i = 0; i < count; i++)
        {
            bool sameTarget = _spec.SameTargetBias > 0f && Main.rand.NextFloat() < _spec.SameTargetBias;
            float t = count <= 1 ? 0f : (i / (float)(count - 1) - 0.5f);
            Vector2 velocity;
            Vector2 origin;
            if (sameTarget)
            {
                // Explicit same-target bias is the only mode allowed to route a child
                // back through the target that was already hit.
                origin = target.Center - baseDir * (Math.Max(target.width, target.height) * 0.55f + 18f) + Main.rand.NextVector2Circular(5f, 5f);
                velocity = baseDir.RotatedBy(Main.rand.NextFloat(-spread * 0.18f, spread * 0.18f)) * speed;
            }
            else
            {
                velocity = baseDir.RotatedBy(t * spread) * speed;
                origin = target.Center + velocity.SafeNormalize(baseDir) * (Math.Max(target.width, target.height) * 0.55f + 18f);
            }
            SpawnChild(origin, velocity, dmg, childSpec, Projectile.localAI[1] + 1f, target.whoAmI);
        }
    }

    private void ChainProjectiles(NPC firstTarget, int count)
    {
        if (!CanRunChildEffect() || count <= 0) return;
        count = RuntimeChildCount(count);
        if (count <= 0) return;
        AttackSpec childSpec = ChildSpec(0, 0, 0.65f);
        NPC? last = firstTarget;
        for (int chain = 0; chain < count; chain++)
        {
            NPC? next = FindNearestNPC(last.Center, 360f, last.whoAmI);
            if (next is null) break;
            Vector2 velocity = last.DirectionTo(next.Center).SafeNormalize(Vector2.UnitX) * Math.Max(6f, Projectile.velocity.Length() * 0.9f);
            int chainDamage = Math.Max(0, (int)(Projectile.damage * _spec.SecondaryDamageMultiplier));
            SpawnChild(last.Center, velocity, chainDamage, childSpec, Projectile.localAI[1] + 1f, last.whoAmI);
            last = next;
        }
    }

    private void RadialBurst(Vector2 center, int count, float damageMult, int ignoreNpc = -1)
    {
        if (!CanRunChildEffect()) return;
        count = RuntimeChildCount(count);
        if (count <= 0) return;
        AttackSpec childSpec = ChildSpec(3, 0, 0.55f);
        childSpec.MaxChildProjectiles = 0;
        childSpec.MaxChildDepth = 0;
        childSpec.Lifetime = _spec.SecondaryLifetimeTicks;
        for (int i = 0; i < count; i++)
        {
            Vector2 velocity = Vector2.UnitX.RotatedBy(MathHelper.TwoPi * i / Math.Max(1, count)) * Main.rand.NextFloat(4.5f, 8.5f);
            SpawnChild(center + velocity.SafeNormalize(Vector2.UnitX) * 18f, velocity, Math.Max(0, (int)(Projectile.damage * damageMult)), childSpec, Projectile.localAI[1] + 1f, ignoreNpc);
        }
    }

    private void Starfall(Vector2 center, int count, float damageMult, int ignoreNpc = -1)
    {
        // Starfall is the finite Star Wrath-like primitive: bounded falling star
        // child projectiles spawned above the hit point, not a name/prose router.
        if (!CanRunChildEffect(rootOnly: true) || _procced) return;
        _procced = true;
        count = RuntimeChildCount(count);
        if (count <= 0) return;
        AttackSpec childSpec = ChildSpec(2, 0, 0.62f);
        childSpec.EffectCode = 3; // star
        childSpec.TileCollide = false;
        childSpec.Lifetime = _spec.SecondaryLifetimeTicks > 0 ? _spec.SecondaryLifetimeTicks : Math.Min(120, Math.Max(45, _spec.Lifetime / 2));
        childSpec.ProjectileShape = string.IsNullOrWhiteSpace(_spec.SecondaryProjectileShape) ? "falling star" : _spec.SecondaryProjectileShape;
        childSpec.ProjectileMotion = "falling star";
        int dmg = Math.Max(1, (int)(Projectile.damage * Math.Max(0.12f, damageMult <= 0f ? 0.42f : damageMult)));
        float spacing = count <= 1 ? 0f : MathHelper.Clamp(_spec.SecondarySpreadRadians <= 0f ? 0.44f : _spec.SecondarySpreadRadians, 0.12f, 1.2f);
        for (int i = 0; i < count; i++)
        {
            float t = count <= 1 ? 0f : (i / (float)(count - 1) - 0.5f);
            Vector2 origin = center + new Vector2(t * spacing * 96f + Main.rand.NextFloat(-18f, 18f), -220f - Main.rand.NextFloat(0f, 90f));
            Vector2 toward = (center + Main.rand.NextVector2Circular(36f, 18f) - origin).SafeNormalize(Vector2.UnitY);
            Vector2 velocity = toward * Main.rand.NextFloat(9.5f, 14.5f);
            SpawnChild(origin, velocity, dmg, childSpec, Projectile.localAI[1] + 1f, ignoreNpc);
        }
    }

    private void AuraPulse(Vector2 center)
    {
        int radius = _spec.AoeDamageRadiusPx > 0 ? _spec.AoeDamageRadiusPx : _spec.ImpactVfxRadiusPx;
        if (radius <= 0)
        {
            BurstDust(_spec.EffectCode, Math.Min(_spec.BurstDustCap, 8), 1.0f);
            return;
        }
        Projectile.Center = center;
        ResizeProjectilePreserveCenter(Projectile.width + Math.Max(8, radius), Projectile.height + Math.Max(8, radius));
        Projectile.netUpdate = true;
        BurstDust(_spec.EffectCode, 24, 2.4f);
    }

    private void SporeCloud(Vector2 center, int ignoreNpc = -1)
    {
        if (!CanRunChildEffect()) return;
        AttackSpec childSpec = ChildSpec(3, 0, 0.5f);
        childSpec.Lifetime = _spec.SecondaryLifetimeTicks;
        childSpec.TileCollide = false;
        childSpec.MaxChildProjectiles = 0;
        childSpec.MaxChildDepth = 0;
        int count = RuntimeChildCount(_spec.SplitCount > 0 ? _spec.SplitCount : _spec.MaxChildProjectiles);
        if (count <= 0) return;
        for (int i = 0; i < count; i++)
        {
            Vector2 velocity = Main.rand.NextVector2Circular(3.5f, 3.5f);
            int sporeDamage = Math.Max(0, (int)(Projectile.damage * _spec.SecondaryDamageMultiplier));
            SpawnChild(center + velocity.SafeNormalize(Vector2.UnitX) * 18f, velocity, sporeDamage, childSpec, Projectile.localAI[1] + 1f, ignoreNpc);
        }
    }

    private void MiniMissiles(Vector2 center, int ignoreNpc = -1)
    {
        if (!CanRunChildEffect(rootOnly: true) || _procced) return;
        _procced = true;
        AttackSpec childSpec = ChildSpec(13, 1, 0.55f);
        childSpec.TileCollide = false;
        childSpec.Lifetime = _spec.SecondaryLifetimeTicks;
        int count = RuntimeChildCount(_spec.SplitCount > 0 ? _spec.SplitCount : _spec.MaxChildProjectiles);
        if (count <= 0) return;
        for (int i = 0; i < count; i++)
        {
            Vector2 v = Main.rand.NextVector2Unit() * Main.rand.NextFloat(5f, 10f);
            SpawnChild(center + v.SafeNormalize(Vector2.UnitX) * 18f, v, Math.Max(0, (int)(Projectile.damage * _spec.SecondaryDamageMultiplier)), childSpec, Projectile.localAI[1] + 1f, ignoreNpc);
        }
    }

    private void VortexSpawn(Vector2 center, int ignoreNpc = -1)
    {
        if (!CanRunChildEffect(rootOnly: true) || _procced) return;
        _procced = true;
        AttackSpec childSpec = ChildSpec(11, 1, 0.7f);
        childSpec.TileCollide = false;
        childSpec.Lifetime = _spec.SecondaryLifetimeTicks;
        int count = RuntimeChildCount(_spec.SplitCount > 0 ? _spec.SplitCount : _spec.MaxChildProjectiles);
        if (count <= 0) return;
        for (int i = 0; i < count; i++)
        {
            Vector2 v = Main.rand.NextVector2Unit() * Main.rand.NextFloat(4f, 7f);
            SpawnChild(center + v.SafeNormalize(Vector2.UnitX) * 18f, v, Math.Max(0, (int)(Projectile.damage * _spec.SecondaryDamageMultiplier)), childSpec, Projectile.localAI[1] + 1f, ignoreNpc);
        }
    }

    private void SpawnChild(Vector2 center, Vector2 velocity, int damage, AttackSpec childSpec, float depth, int ignoreNpc = -1)
    {
        if (Projectile.owner != Main.myPlayer) return;
        if (depth > Math.Max(0, _spec.MaxChildDepth)) return;
        float rootId = Projectile.localAI[2] > 0f ? Projectile.localAI[2] : Projectile.identity + 1f;
        if (CountOwnedGeneratedProjectiles(rootId) >= Math.Max(0, _spec.MaxChildProjectiles)) return;
        int idx = Projectile.NewProjectile(Projectile.GetSource_FromThis(), center, velocity, Type, damage, Projectile.knockBack * 0.55f, Projectile.owner, childSpec.MovementCode, childSpec.EffectCode, childSpec.OnHitCode);
        if (idx >= 0 && Main.projectile[idx].ModProjectile is GeneratedProjectile gp)
        {
            Projectile.localAI[2] = rootId;
            Main.projectile[idx].localAI[1] = depth;
            Main.projectile[idx].localAI[2] = rootId;
            gp._spawnIgnoreNpc = ignoreNpc;
            gp._spawnIgnoreTicks = ignoreNpc >= 0 ? 10 : 0;
            gp.ApplyGeneratedSpec(childSpec, new VfxManifestSpec(), _generatedItemId);
            Main.projectile[idx].netUpdate = true;
            gp.BroadcastVisualSync();
        }
    }

    private bool SpawnPersistentVfxOverlay(string eventKind, Vector2 center, int lifetime, Vector2 inheritedVelocity)
    {
        if (Main.dedServ || Projectile.owner != Main.myPlayer || _vfxManifest is null || !_vfxManifest.HasSlots)
            return false;
        bool spawned = GeneratedVfxOverlayProjectile.Spawn(Projectile.GetSource_FromThis(), center, inheritedVelocity, Projectile.owner, _spec, _vfxManifest, eventKind, lifetime);
        if (spawned)
            BroadcastVfxEventSync(eventKind, center, lifetime, inheritedVelocity);
        return spawned;
    }

    private int VfxEventLifetime(string eventKind)
    {
        if (_vfxManifest is null || !_vfxManifest.HasSlots)
            return 24;
        string evNeed = (eventKind ?? "").ToLowerInvariant();
        int life = 12;
        foreach (var slot in _vfxManifest.Slots)
        {
            if (slot is null)
                continue;
            string ev = (slot.Event ?? "").ToLowerInvariant();
            bool match = evNeed.Contains("hit")
                ? (ev == "hit" || ev == "impact" || ev == "onhit")
                : (ev == "kill" || ev == "expire" || ev == "decay");
            if (!match)
                continue;
            int slotLife = Math.Clamp(slot.Duration + slot.StartTick + 8, 8, 180);
            life = Math.Max(life, slotLife);
            if (slot.BakedCommands is { Length: > 0 })
            {
                foreach (var cmd in slot.BakedCommands)
                    if (cmd is not null)
                        life = Math.Max(life, Math.Clamp(cmd.Tick + cmd.Lifespan + 6, 8, 180));
            }
        }
        return Math.Clamp(life, 8, 180);
    }

    private void PlayImpactSound()
    {
        int localTick = (int)Projectile.localAI[0];
        // Piercing/generated children can report several hits in one update. Keep the
        // audio readable without changing damage, VFX, penetration or on-hit gameplay.
        if (localTick - _lastImpactSoundLocalTick < 4)
            return;
        _lastImpactSoundLocalTick = localTick;

        string authoredProfile = string.Join(" ", new[]
        {
            _spec.ImpactSoundProfile,
            _spec.SoundImpact,
            _spec.WeaponSubfamily,
            _spec.ProjectileFamily,
            string.Join(" ", _spec.AttackPatternTags ?? Array.Empty<string>())
        }.Where(x => !string.IsNullOrWhiteSpace(x))).Trim();
        SoundStyle style = InfiniSoundLibrary.ForImpact(
            authoredProfile,
            _spec.Effect,
            _spec.OnHitCode,
            _spec.EffectCode,
            _spec.SoundVolume,
            _spec.SoundPitch,
            _spec.SoundImpactCatalogId,
            _spec.SoundImpactCatalogPath,
            _spec.SoundImpactSearchQuery,
            _spec.SoundCatalogSource);
        SoundEngine.PlaySound(style, Projectile.Center);
    }

// =============================================================================
// NAV: PROJECTILE_KILL_AND_DECAY
// =============================================================================
    public override void OnKill(int timeLeft)
    {
        int effect = _spec.EffectCode;
        InfiniVfxRuntime.OnKill(Projectile, _spec, _vfxManifest, ref _vfxState);
        SpawnPersistentVfxOverlay("kill", Projectile.Center, Math.Max(12, VfxEventLifetime("kill")), Projectile.velocity);
        TryRunImpactMobility(Projectile.Center);
        if (timeLeft > 0) PlayImpactSound();
        int visualRadius = _spec.ImpactVfxRadiusPx > 0 ? _spec.ImpactVfxRadiusPx : _spec.ExplosionRadius;
        int damageRadius = _spec.AoeDamageRadiusPx;
        int burstCount = visualRadius > 0 ? 24 : 0;
        BurstDust(effect, burstCount, visualRadius > 0 ? 2.8f : 1.4f);
        EmitVanillaImpactPolish(Projectile.Center, true);
        if (damageRadius > 0 && Projectile.owner == Main.myPlayer)
        {
            ResizeProjectilePreserveCenter(damageRadius * 2, damageRadius * 2);
            Projectile.netUpdate = true;
            Projectile.Damage();
        }
    }

}
