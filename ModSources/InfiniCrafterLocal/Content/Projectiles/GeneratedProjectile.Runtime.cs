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

// AGENT MAP: generated projectile runtime entrypoint/defaults.
// ApplyGeneratedSpec() is the only path that turns AttackSpec/VfxManifest into
// an active projectile. It rejects non-runtime-authored or unsupported opcode
// specs instead of falling back to legacy prose/script behavior.
public sealed partial class GeneratedProjectile
{
// =============================================================================
// NAV: PROJECTILE_DEFAULTS_AND_NETWORK
// =============================================================================
    public override void SetStaticDefaults()
    {
        // tModLoader keeps projectile trail samples in oldPos/oldRot only when the cache is enabled.
        // VFX runtime treats these samples as the authoritative Terraria-style trail history.
        ProjectileID.Sets.TrailCacheLength[Type] = 24;
        ProjectileID.Sets.TrailingMode[Type] = 2;
    }

    public void ApplyGeneratedSpec(AttackSpec spec, VfxManifestSpec? vfxManifest = null, string generatedItemId = "")
    {
        _generatedItemId = generatedItemId ?? "";
        _pendingNetworkSpecTicks = 0;
        _spec = spec ?? new AttackSpec();
        SanitizeRuntimeSize(_spec);
        _vfxManifest = vfxManifest ?? VfxManifestSpec.FromJson(_spec.VfxManifestJson);
        _vfxManifest.Normalize();
        _spec.VfxManifestJson = _vfxManifest.HasSlots ? _vfxManifest.ToJson() : (_spec.VfxManifestJson ?? "");
        _vfxState = new InfiniVfxState { LocalSeed = _vfxManifest.Seed };
        _configured = true;
        if (!_spec.RuntimePlanAuthored)
        {
            DisableUnsupportedProjectile("Legacy non-runtime-authored generated projectile is no longer supported.");
            return;
        }
        if (!RuntimeCodesSupported())
        {
            DisableUnsupportedProjectile($"Unsupported generated runtime opcode/family: movement={_spec.MovementCode}, effect={_spec.EffectCode}, onHit={_spec.OnHitCode}.");
            return;
        }
        _statsApplied = false;
        _remainingBounces = InitialBounceBudget(_spec);
        _stuckToTile = false;
        _impactMobilityUsed = false;
        _lastImpactSoundLocalTick = -9999;
        _visualSyncRebroadcastsSent = 0;
        ApplyConfiguredStats();
    }


    public override void SetDefaults()
    {
        Projectile.width = 14;
        Projectile.height = 14;
        Projectile.friendly = true;
        Projectile.hostile = false;
        Projectile.penetrate = 1;
        Projectile.timeLeft = 90;
        Projectile.tileCollide = true;
        Projectile.ignoreWater = false;
        Projectile.DamageType = DamageClass.Generic;
        Projectile.scale = 1f;
        Projectile.usesLocalNPCImmunity = true;
        Projectile.localNPCHitCooldown = 10;
        _statsApplied = false;
        _stuckToTile = false;
        _impactMobilityUsed = false;
    }


    private void DisableUnsupportedProjectile(string reason)
    {
        LogProjectileWarning(reason);
        ResetRuntimeSpecState(deactivateProjectile: true);
    }

    private static void LogProjectileWarning(string message, Exception? ex = null)
    {
        try
        {
            string key = (message ?? "").Length > 140 ? (message ?? "")[..140] : (message ?? "");
            int now = (int)Main.GameUpdateCount;
            lock (WarningLogTicks)
            {
                if (WarningLogTicks.TryGetValue(key, out int last) && now - last < 30 * 60)
                    return;
                WarningLogTicks[key] = now;
            }
            string suffix = ex is null ? "" : $" ({ex.GetType().Name}: {ex.Message})";
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn("[InfiniCrafter] " + message + suffix);
        }
        catch { }
    }

    private bool RuntimeCodesSupported()
        => RuntimeFamily() != "none"
        && _spec.MovementCode >= 0 && _spec.MovementCode <= MaxSupportedMovementCode
        && _spec.EffectCode >= 0 && _spec.EffectCode <= MaxSupportedEffectCode
        && _spec.OnHitCode >= 0 && _spec.OnHitCode <= MaxSupportedOnHitCode;


    private AttackSpec ChildSpec(int movement = 0, int onHit = 0, float scale = 0.75f)
    {
        AttackSpec child = new AttackSpec
        {
            Enabled = _spec.Enabled,
            MovementCode = movement,
            EffectCode = _spec.EffectCode,
            OnHitCode = onHit,
            ProjectileWidth = Math.Max(8, (int)(_spec.ProjectileWidth * scale)),
            ProjectileHeight = Math.Max(8, (int)(_spec.ProjectileHeight * scale)),
            ProjectileScale = Math.Max(0.45f, _spec.ProjectileScale * scale),
            HitboxScale = 1f,
            ExplosionRadius = 0,
            Lifetime = Math.Min(80, Math.Max(24, _spec.Lifetime / 2)),
            Pierce = 1,
            ExtraUpdates = Math.Min(1, _spec.ExtraUpdates),
            TileCollide = true,
            BounceCount = 0,
            SplitCount = 0,
            ChainCount = 0,
            ImmunityCooldown = 18,
            ProcMode = 0,
            RuntimePlanAuthored = _spec.RuntimePlanAuthored,
            SecondarySpreadRadians = _spec.SecondarySpreadRadians,
            SecondaryDamageMultiplier = _spec.SecondaryDamageMultiplier,
            SecondaryLifetimeTicks = _spec.SecondaryLifetimeTicks,
            SameTargetBias = _spec.SameTargetBias,
            DebuffHint = "",
            DebuffTime = 0,
            RuntimeFamily = "shoot",
            Delivery = "shoot",
            WeaponFamily = "child_projectile",
            WeaponSubfamily = _spec.WeaponSubfamily,
            AttackPatternTags = _spec.AttackPatternTags ?? Array.Empty<string>(),
            ProjectileFamily = string.IsNullOrWhiteSpace(_spec.SecondaryProjectileShape) ? "child_projectile" : "secondary_projectile",
            AmmoKind = "",
            SecondaryMaterial = _spec.SecondaryMaterial,
            SecondaryProjectileShape = _spec.SecondaryProjectileShape,
            Pattern = "basic",
            MaxChildProjectiles = Math.Max(4, _spec.MaxChildProjectiles / 2),
            MaxChildDepth = Math.Max(0, _spec.MaxChildDepth - 1),
            DustSpawnDenom = Math.Max(3, _spec.DustSpawnDenom + 1),
            BurstDustCap = Math.Max(6, _spec.BurstDustCap / 2),
            VisualMode = _spec.VisualMode,
            TrailStyle = _spec.TrailStyle,
            ImpactStyle = _spec.ImpactStyle,
            PrimaryColorName = _spec.PrimaryColorName,
            ImpactSoundProfile = _spec.ImpactSoundProfile,
            SoundPitch = _spec.SoundPitch,
            SoundVolume = _spec.SoundVolume,
            ProjectileShape = _spec.ProjectileShape,
            ProjectileMotion = _spec.ProjectileMotion,
            ProjectileRotation = _spec.ProjectileRotation,
            ProjectileTrail = _spec.ProjectileTrail,
            ProjectileImpact = _spec.ProjectileImpact,
            SoundUse = _spec.SoundUse,
            SoundImpact = _spec.SoundImpact,
            SoundUseSearchQuery = _spec.SoundUseSearchQuery,
            SoundImpactSearchQuery = _spec.SoundImpactSearchQuery,
            SoundUseCatalogId = _spec.SoundUseCatalogId,
            SoundImpactCatalogId = _spec.SoundImpactCatalogId,
            SoundUseCatalogPath = _spec.SoundUseCatalogPath,
            SoundImpactCatalogPath = _spec.SoundImpactCatalogPath,
            SoundCatalogSource = _spec.SoundCatalogSource,
            ProjectileSpritePath = _spec.ProjectileSpritePath,
            ProjectileSpriteUrl = _spec.ProjectileSpriteUrl,
            ProjectileSpriteStatus = _spec.ProjectileSpriteStatus,
            ProjectileSpritePrompt = _spec.ProjectileSpritePrompt,
            ProjectileSpriteScore = _spec.ProjectileSpriteScore,
            ImpactSpritePath = _spec.ImpactSpritePath,
            ImpactSpriteUrl = _spec.ImpactSpriteUrl,
            ImpactSpriteStatus = _spec.ImpactSpriteStatus,
            ImpactSpritePrompt = _spec.ImpactSpritePrompt,
            ImpactSpriteScore = _spec.ImpactSpriteScore,
            ChildSpritePath = _spec.ChildSpritePath,
            ChildSpriteUrl = _spec.ChildSpriteUrl,
            ChildSpriteStatus = _spec.ChildSpriteStatus,
            ChildSpritePrompt = _spec.ChildSpritePrompt,
            ChildSpriteScore = _spec.ChildSpriteScore,
            FieldSpritePath = _spec.FieldSpritePath,
            FieldSpriteUrl = _spec.FieldSpriteUrl,
            FieldSpriteStatus = _spec.FieldSpriteStatus,
            FieldSpritePrompt = _spec.FieldSpritePrompt,
            FieldSpriteScore = _spec.FieldSpriteScore,
            VisualAnimationPlan = _spec.VisualAnimationPlan,
            VfxManifestJson = _spec.VfxManifestJson
        };
        SanitizeRuntimePlanChildSpec(child);
        return child;
    }

    private void SanitizeRuntimePlanChildSpec(AttackSpec child)
    {
        // Real gameplay children must not inherit parent prompts/prose/VFX-manifest state.
        // They carry only executable movement/effect/on-hit numbers plus a small authored presentation contract.
        child.RuntimePlanAuthored = true;
        child.Pattern = "basic";
        child.VisualMode = "projectile";
        child.VisualAnimationPlan = "";
        child.TrailStyle = "none";
        child.ImpactStyle = "none";
        child.ProjectileMotion = "";
        child.ProjectileRotation = "";
        child.ProjectileTrail = "";
        child.ProjectileImpact = "";
        child.ProjectileSpritePath = "";
        child.ProjectileSpriteUrl = "";
        child.ProjectileSpriteStatus = "";
        child.ProjectileSpritePrompt = "";
        child.ProjectileSpriteScore = 0f;
        child.ImpactSpritePath = "";
        child.ImpactSpriteUrl = "";
        child.ImpactSpriteStatus = "";
        child.ImpactSpritePrompt = "";
        child.ImpactSpriteScore = 0f;
        child.ChildSpritePath = "";
        child.ChildSpriteUrl = "";
        child.ChildSpriteStatus = "";
        child.ChildSpritePrompt = "";
        child.ChildSpriteScore = 0f;
        child.FieldSpritePath = "";
        child.FieldSpriteUrl = "";
        child.FieldSpriteStatus = "";
        child.FieldSpritePrompt = "";
        child.FieldSpriteScore = 0f;
        child.VfxManifestJson = "";
        child.MaxChildProjectiles = 0;
        child.MaxChildDepth = 0;
        child.SplitCount = 0;
        child.ChainCount = 0;
        child.ProcMode = 0;
        child.ExplosionRadius = 0;
        child.BurstDustCap = 0;
        child.DustSpawnDenom = 0;
        ApplyAuthoredChildPresentation(child, _spec);
    }


    private void ResizeProjectilePreserveCenter(int width, int height)
    {
        Vector2 center = Projectile.Center;
        Projectile.Resize(Math.Max(2, width), Math.Max(2, height));
        Projectile.Center = center;
    }

    private string RuntimeFamily()
    {
        string r = (_spec.RuntimeFamily ?? "").Trim().ToLowerInvariant();
        return r is "swing" or "thrust" or "returning" or "flail" or "yoyo" or "whip" or "shoot" or "cast" or "throw" or "summon" ? r : "none";
    }

    private bool IsThrustDelivery() => RuntimeFamily() == "thrust";
    private bool IsFlailDelivery() => RuntimeFamily() == "flail";
    private bool IsYoyoDelivery() => RuntimeFamily() == "yoyo";
    private bool IsWhipDelivery() => RuntimeFamily() == "whip";

    private static float SideOnGeneratedSpriteRotation(Vector2 direction)
    {
        // Runtime-generated projectile assets are authored by the local visual pipeline
        // as side-on sprites pointing left-to-right (+X).  Vanilla Terraria projectile
        // textures often point upward and therefore use +Pi/2, but applying that offset
        // here makes arrows/bolts fly sideways.
        Vector2 safe = direction.SafeNormalize(Vector2.UnitX);
        return safe.ToRotation();
    }

    private void HeldThrustLine(out Vector2 start, out Vector2 end, out Vector2 dir)
    {
        Player owner = Main.player[Projectile.owner];
        dir = Projectile.velocity.SafeNormalize(new Vector2(owner.direction == 0 ? 1 : owner.direction, 0f));
        float animMax = Math.Max(1f, owner.itemAnimationMax > 0 ? owner.itemAnimationMax : Math.Max(1, _spec.Lifetime));
        float remaining = Math.Clamp(owner.itemAnimation, 0f, animMax);
        float progress = 1f - remaining / animMax;
        float thrust = (float)Math.Sin(MathHelper.Clamp(progress, 0f, 1f) * MathHelper.Pi);
        float maxReach = Math.Clamp(_spec.Speed * Math.Max(8f, Math.Min(42f, _spec.Lifetime)) * 0.42f, 38f, 112f);
        float reach = MathHelper.Lerp(22f, maxReach, thrust);
        start = owner.MountedCenter + dir * 10f;
        end = owner.MountedCenter + dir * reach;
    }

    private bool ApplyHeldThrustAI()
    {
        Player owner = Main.player[Projectile.owner];
        if (!owner.active || owner.dead || owner.itemAnimation <= 0)
        {
            Projectile.Kill();
            return false;
        }

        Vector2 start, end, dir;
        HeldThrustLine(out start, out end, out dir);
        int facing = dir.X >= 0f ? 1 : -1;
        owner.ChangeDir(facing);
        owner.heldProj = Projectile.whoAmI;
        owner.itemTime = Math.Max(owner.itemTime, 2);

        Projectile.direction = facing;
        Projectile.spriteDirection = facing;
        Projectile.velocity = dir;
        Projectile.Center = (start + end) * 0.5f;
        Projectile.rotation = SideOnGeneratedSpriteRotation(dir);
        Projectile.timeLeft = 2;
        Projectile.tileCollide = false;
        Projectile.netImportant = false;
        return true;
    }

    private bool ApplyFlailTetherAI()
    {
        Player owner = Main.player[Projectile.owner];
        if (!owner.active || owner.dead) { Projectile.Kill(); return false; }
        Vector2 toOwner = owner.MountedCenter - Projectile.Center;
        float maxRange = Math.Clamp(Math.Max(6f, _spec.Speed * Math.Max(8f, _spec.Lifetime) * 0.18f), 80f, 520f);
        if (Projectile.localAI[0] > Math.Max(12, _spec.Lifetime * 0.45f) || toOwner.Length() > maxRange)
        {
            Projectile.velocity = Vector2.Lerp(Projectile.velocity, toOwner.SafeNormalize(Vector2.Zero) * Math.Max(8f, _spec.Speed), 0.13f);
        }
        else
        {
            Projectile.velocity *= 0.982f;
        }
        if (Projectile.localAI[0] > 8f && toOwner.Length() < 24f) Projectile.Kill();
        Projectile.rotation += 0.34f * Math.Sign(Projectile.velocity.X == 0f ? owner.direction : Projectile.velocity.X);
        Projectile.tileCollide = true;
        return true;
    }

    private bool ApplyYoyoHoverAI()
    {
        Player owner = Main.player[Projectile.owner];
        if (!owner.active || owner.dead || (!owner.channel && Projectile.localAI[0] > 18f))
        {
            Vector2 home = owner.MountedCenter - Projectile.Center;
            Projectile.velocity = Vector2.Lerp(Projectile.velocity, home.SafeNormalize(Vector2.Zero) * Math.Max(9f, _spec.Speed), 0.18f);
            if (home.Length() < 24f) Projectile.Kill();
            return true;
        }

        Vector2 aim = Main.MouseWorld - owner.MountedCenter;
        if (Projectile.owner != Main.myPlayer || aim.LengthSquared() < 16f)
            aim = Projectile.velocity.LengthSquared() > 0.01f ? Projectile.velocity : new Vector2(owner.direction, 0f);
        float maxRange = Math.Clamp(Math.Max(6f, _spec.Speed * Math.Max(8f, _spec.Lifetime) * 0.18f), 96f, 420f);
        Vector2 target = owner.MountedCenter + aim.SafeNormalize(Vector2.UnitX * owner.direction) * maxRange * 0.72f;
        Projectile.Center = Vector2.Lerp(Projectile.Center, target, 0.12f);
        Projectile.velocity = (target - Projectile.Center) * 0.18f;
        Projectile.rotation += 0.42f;
        Projectile.timeLeft = 2;
        Projectile.tileCollide = false;
        owner.heldProj = Projectile.whoAmI;
        return true;
    }

    private void WhipLine(out Vector2 start, out Vector2 end, out Vector2 dir)
    {
        Player owner = Main.player[Projectile.owner];
        dir = Projectile.velocity.SafeNormalize(new Vector2(owner.direction == 0 ? 1 : owner.direction, 0f));
        float animMax = Math.Max(1f, owner.itemAnimationMax > 0 ? owner.itemAnimationMax : Math.Max(1, _spec.Lifetime));
        float progress = 1f - Math.Clamp(owner.itemAnimation, 0f, animMax) / animMax;
        float sweep = MathHelper.Lerp(-0.62f, 0.62f, MathHelper.Clamp(progress, 0f, 1f));
        if (owner.direction < 0) sweep = -sweep;
        dir = dir.RotatedBy(sweep);
        float reach = Math.Clamp(Math.Max(6f, _spec.Speed * Math.Max(8f, _spec.Lifetime) * 0.18f), 58f, 260f);
        start = owner.MountedCenter + dir * 12f;
        end = owner.MountedCenter + dir * reach;
    }

    private bool ApplyWhipLashAI()
    {
        Player owner = Main.player[Projectile.owner];
        if (!owner.active || owner.dead || owner.itemAnimation <= 0) { Projectile.Kill(); return false; }
        Vector2 start, end, dir;
        WhipLine(out start, out end, out dir);
        owner.ChangeDir(dir.X >= 0f ? 1 : -1);
        owner.heldProj = Projectile.whoAmI;
        Projectile.velocity = dir;
        Projectile.Center = (start + end) * 0.5f;
        Projectile.rotation = SideOnGeneratedSpriteRotation(dir);
        Projectile.timeLeft = 2;
        Projectile.tileCollide = false;
        Projectile.penetrate = -1;
        return true;
    }

    private static void SanitizeRuntimeSize(AttackSpec spec)
    {
        if (spec is null) return;
        spec.ProjectileWidth = Math.Clamp(spec.ProjectileWidth <= 0 ? 14 : spec.ProjectileWidth, 4, 96);
        spec.ProjectileHeight = Math.Clamp(spec.ProjectileHeight <= 0 ? 14 : spec.ProjectileHeight, 4, 96);
        spec.ProjectileScale = Math.Clamp(spec.ProjectileScale <= 0f ? 1f : spec.ProjectileScale, 0.35f, 2.25f);
        spec.HitboxScale = Math.Clamp(spec.HitboxScale <= 0f ? 1f : spec.HitboxScale, 0.5f, 2.5f);
        spec.ExplosionRadius = Math.Clamp(spec.ExplosionRadius, 0, 128);
        spec.ImpactVfxRadiusPx = Math.Clamp(spec.ImpactVfxRadiusPx <= 0 ? spec.ExplosionRadius : spec.ImpactVfxRadiusPx, 0, 192);
        spec.AoeDamageRadiusPx = Math.Clamp(spec.AoeDamageRadiusPx, 0, 160);
        spec.ContactForgivenessPx = Math.Clamp(spec.ContactForgivenessPx, 0, 32);
        spec.RuntimeLightStrength = Math.Clamp(spec.RuntimeLightStrength, 0f, 2f);
    }

    private void ApplyConfiguredStats()
    {
        if (_statsApplied) return;
        _pendingNetworkSpecTicks = 0;
        int movement = _spec.MovementCode;
        if (_configured && !_spec.RuntimePlanAuthored)
        {
            DisableUnsupportedProjectile("Legacy non-runtime-authored generated projectile cannot be applied in authored-runtime-only mode.");
            return;
        }
        if (_configured && !RuntimeCodesSupported())
        {
            DisableUnsupportedProjectile($"Unsupported generated runtime opcode/family during stat apply: movement={_spec.MovementCode}, effect={_spec.EffectCode}, onHit={_spec.OnHitCode}.");
            return;
        }
        SanitizeRuntimeSize(_spec);
        ResizeProjectilePreserveCenter(Math.Clamp(_spec.ProjectileWidth, 8, 96), Math.Clamp(_spec.ProjectileHeight, 8, 96));
        bool thrustLike = IsThrustDelivery();
        bool flailLike = IsFlailDelivery();
        bool yoyoLike = IsYoyoDelivery();
        bool whipLike = IsWhipDelivery();
        bool heldLike = thrustLike || yoyoLike || whipLike;
        Projectile.friendly = true;
        Projectile.hostile = false;
        Projectile.scale = Math.Clamp(_spec.ProjectileScale, 0.45f, 2.25f);
        // Pierce semantics are total hit budget for generated runtime projectiles:
        // -1 = explicit infinite/persistent, 0/1 = one hit. Older builds treated 0 as
        // infinite, which made many generated shots poke the same target 2-3 times.
        Projectile.penetrate = heldLike ? -1 : (_spec.Pierce < 0 ? -1 : Math.Max(1, _spec.Pierce));
        Projectile.timeLeft = heldLike ? 2 : Math.Max(20, _spec.Lifetime);
        Projectile.extraUpdates = heldLike ? 0 : Math.Clamp(_spec.ExtraUpdates, 0, 3);
        Projectile.ownerHitCheck = _spec.OwnerHitCheck;
        if (!_stuckToTile)
            Projectile.tileCollide = !heldLike && !flailLike && _spec.TileCollide && movement != 8 && movement != 12 && movement != 16 && movement != 17 && movement != 18;
        Projectile.usesLocalNPCImmunity = true;
        Projectile.localNPCHitCooldown = _spec.ImmunityCooldown <= 0 ? 12 : Math.Clamp(_spec.ImmunityCooldown, 4, 60);
        _spec.MaxChildProjectiles = Math.Clamp(_spec.MaxChildProjectiles <= 0 ? 0 : _spec.MaxChildProjectiles, 0, 48);
        _spec.MaxChildDepth = Math.Clamp(_spec.MaxChildDepth, 0, 3);
        _spec.SecondarySpreadRadians = Math.Clamp(_spec.SecondarySpreadRadians, 0f, 2.2f);
        _spec.SecondaryDamageMultiplier = Math.Clamp(_spec.SecondaryDamageMultiplier, 0f, 1.0f);
        _spec.SecondaryLifetimeTicks = Math.Clamp(_spec.SecondaryLifetimeTicks <= 0 ? 24 : _spec.SecondaryLifetimeTicks, 4, 120);
        _spec.SameTargetBias = Math.Clamp(_spec.SameTargetBias, 0f, 1f);
        _spec.DustSpawnDenom = _spec.DustSpawnDenom <= 0 ? 0 : Math.Clamp(_spec.DustSpawnDenom, 2, 12);
        _spec.BurstDustCap = _spec.BurstDustCap <= 0 ? 0 : Math.Clamp(_spec.BurstDustCap, 0, 40);
        float lightMul = InfiniVfxClientOptions.PresentationLightMultiplier;
        Projectile.light = !AllowsPresentationLight() || lightMul <= 0f ? 0f : Math.Min(0.35f, 0.10f + _spec.PowerBudget * 0.035f) * lightMul;
        _statsApplied = true;
    }

    public override void AI()
    {
        ApplyPendingProjectileVisualSyncIfAny();
        if (!_configured && _pendingNetworkSpecTicks > 0)
        {
            _pendingNetworkSpecTicks--;
            Projectile.damage = 0;
            Projectile.friendly = false;
            Projectile.velocity *= 0.92f;
            if (_pendingNetworkSpecTicks <= 0)
                Projectile.Kill();
            return;
        }
        if (!RuntimePlanMode)
        {
            DisableUnsupportedProjectile("Generated projectile reached AI without an authored runtime spec.");
            return;
        }
        ApplyConfiguredStats();
        HydratePresentationFromRegistryIfPossible();
        if (!Projectile.active) return;
        Projectile.localAI[0] += 1f;
        MaybeRebroadcastVisualSyncForEarlyRemoteCatchup();
        if (_spawnIgnoreTicks > 0) _spawnIgnoreTicks--;
        int movement = _spec.MovementCode;
        int effect = _spec.EffectCode;

        bool thrustLike = IsThrustDelivery();
        if (thrustLike)
        {
            if (!ApplyHeldThrustAI()) return;
        }
        else if (!_stuckToTile)
        {
            RunMovementExecutor(movement);
        }

        InfiniVfxRuntime.OnTick(Projectile, _spec, _vfxManifest, ref _vfxState);
        SpawnDust(effect);
        EmitVanillaMotionPolish();
        AddPresentationLight();
        if (!thrustLike)
            Projectile.rotation = Projectile.velocity.LengthSquared() > 0.01f
                ? SideOnGeneratedSpriteRotation(Projectile.velocity)
                : Projectile.rotation + 0.18f * Projectile.direction;
    }

    private static int DefaultBounceBudgetForMovement(int movement)
    {
        // Movement can imply a small bounded bounce budget, but never infinite tile
        // ricochet. Authored BounceCount still wins when it is explicitly positive.
        return movement switch
        {
            6 => 3,  // bounce
            14 => 1, // returning_glaive/chakram-style glance
            _ => 0,
        };
    }

    private static int InitialBounceBudget(AttackSpec spec)
    {
        if (spec is null) return 0;
        int authored = Math.Max(0, spec.BounceCount);
        return authored > 0 ? authored : DefaultBounceBudgetForMovement(spec.MovementCode);
    }

    public override bool OnTileCollide(Vector2 oldVelocity)
    {
        if (_remainingBounces <= 0)
            return true;

        _remainingBounces--;
        if (Projectile.velocity.X != oldVelocity.X) Projectile.velocity.X = -oldVelocity.X * 0.78f;
        if (Projectile.velocity.Y != oldVelocity.Y) Projectile.velocity.Y = -oldVelocity.Y * 0.78f;
        BurstDust(_spec.EffectCode, 8, 1.4f);
        Projectile.netUpdate = true;
        return false;
    }

    private int CountOwnedGeneratedProjectiles(float rootId)
    {
        int count = 0;
        for (int i = 0; i < Main.maxProjectiles; i++)
        {
            Projectile p = Main.projectile[i];
            if (!p.active || p.owner != Projectile.owner || p.type != Type || p.whoAmI == Projectile.whoAmI) continue;
            if (rootId <= 0f || Math.Abs(p.localAI[2] - rootId) < 0.5f) count++;
        }
        return count;
    }

    private NPC? FindNearestNPC(Vector2 from, float range, int exclude = -1)
    {
        NPC? target = null;
        float best = range;
        for (int i = 0; i < Main.maxNPCs; i++)
        {
            NPC npc = Main.npc[i];
            if (i == exclude || !npc.CanBeChasedBy(Projectile)) continue;
            float dist = Vector2.Distance(from, npc.Center);
            if (dist < best) { best = dist; target = npc; }
        }
        return target;
    }

    private void SlowHoming(float strength, float range)
    {
        NPC? target = FindNearestNPC(Projectile.Center, range);
        if (target is null) return;
        Vector2 desired = Projectile.DirectionTo(target.Center) * Projectile.velocity.Length();
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, desired, strength);
    }

    private void SineHoming()
    {
        SlowHoming(0.025f, 520f);
        Projectile.velocity = Projectile.velocity.RotatedBy((float)Math.Sin(Projectile.localAI[0] * 0.18f) * 0.045f);
    }

    private void BoomerangReturn()
    {
        Player owner = Main.player[Projectile.owner];
        if (Projectile.localAI[0] < 24f) return;
        Vector2 desired = Projectile.DirectionTo(owner.Center) * Math.Max(8f, Projectile.velocity.Length());
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, desired, 0.08f);
        if (Projectile.Distance(owner.Center) < 32f) Projectile.Kill();
    }

    private void PhaseDrift()
    {
        Projectile.tileCollide = false;
        Projectile.velocity *= 0.998f;
        if (AllowsPresentationLight() && Main.netMode != NetmodeID.Server)
        {
            float lightMul = InfiniVfxClientOptions.PresentationLightMultiplier;
            if (lightMul > 0f)
                Lighting.AddLight(Projectile.Center, 0.25f * lightMul, 0.1f * lightMul, 0.45f * lightMul);
        }
    }

    private void Accelerate()
    {
        if (Projectile.velocity.Length() < 20f) Projectile.velocity *= 1.014f;
    }

    private void Orbitish()
    {
        Projectile.velocity = Projectile.velocity.RotatedBy(0.045f);
        Projectile.velocity *= 0.995f;
    }

    private void SpiralOut()
    {
        Projectile.velocity = Projectile.velocity.RotatedBy(0.08f);
        if (Projectile.velocity.Length() < 14f) Projectile.velocity *= 1.006f;
    }

    private void VortexOrb()
    {
        Projectile.velocity *= Projectile.localAI[0] < 30f ? 0.98f : 0.995f;
        Projectile.scale = Math.Min(_spec.ProjectileScale * 1.35f, Projectile.scale + 0.004f);
        if (Projectile.localAI[0] > 35f) SlowHoming(0.05f, 850f);
    }

    private void BlackholePull()
    {
        Projectile.tileCollide = false;
        Projectile.velocity *= 0.992f;
        float range = 260f + _spec.PowerBudget * 70f;
        for (int i = 0; i < Main.maxNPCs; i++)
        {
            NPC npc = Main.npc[i];
            if (!npc.CanBeChasedBy(Projectile)) continue;
            float dist = Vector2.Distance(npc.Center, Projectile.Center);
            if (dist < range)
            {
                Vector2 pull = npc.DirectionTo(Projectile.Center) * (0.05f + _spec.PowerBudget * 0.018f) * (1f - dist / range);
                npc.velocity += pull;
            }
        }
    }

    private void ProximityMissile()
    {
        NPC? target = FindNearestNPC(Projectile.Center, 680f);
        if (target is null) { Accelerate(); return; }
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, Projectile.DirectionTo(target.Center) * Math.Max(8f, Projectile.velocity.Length() + 0.4f), 0.075f);
        if (!_procced && Projectile.Distance(target.Center) < 74f)
        {
            _procced = true;
            MiniMissiles(Projectile.Center);
            Projectile.Kill();
        }
    }

    private void ReturningGlaive()
    {
        Projectile.rotation += 0.18f * Projectile.direction;
        if (Projectile.localAI[0] > 42f) BoomerangReturn();
    }

    private void ExpandingWave()
    {
        Projectile.scale = Math.Min(_spec.ProjectileScale * 2.4f, Projectile.scale * 1.018f);
        Projectile.velocity *= 0.985f;
        if (Projectile.localAI[0] > 44f) Projectile.Kill();
    }

}
