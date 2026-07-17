#nullable enable
using InfiniCrafterLocal.Common.Models;
using System;

namespace InfiniCrafterLocal.Content.Projectiles;

public enum GeneratedProjectileRuntimeVariant : byte
{
    Root = 0,
    StraightSecondary = 1,
    ChainSecondary = 2,
    RadialSecondary = 3,
    OverheadSecondary = 4,
    SporeSecondary = 5,
    MiniMissileSecondary = 6,
    VortexSecondary = 7,
    SentryShot = 8,
    ChargeReleasedShot = 9,
    SwingSecondary = 10,
    SwingOverheadSecondary = 11,
}

/// <summary>
/// Canonical transformations from an authored root AttackSpec to bounded runtime
/// child specs.  This class does not invent mechanics: it centralizes the resets
/// that already existed in projectile executors so parity/mutation tests can prove
/// that a sentry shot is not a sentry root and a released shot is not a holdout.
/// </summary>
internal static class GeneratedChildSpecPolicy
{
    public static bool IsKnownVariant(GeneratedProjectileRuntimeVariant variant)
    {
        return (byte)variant <= (byte)GeneratedProjectileRuntimeVariant.SwingOverheadSecondary;
    }

    public static bool UsesGenericChildPresentation(GeneratedProjectileRuntimeVariant variant)
        => variant is GeneratedProjectileRuntimeVariant.StraightSecondary
            or GeneratedProjectileRuntimeVariant.ChainSecondary
            or GeneratedProjectileRuntimeVariant.RadialSecondary
            or GeneratedProjectileRuntimeVariant.OverheadSecondary
            or GeneratedProjectileRuntimeVariant.SporeSecondary
            or GeneratedProjectileRuntimeVariant.MiniMissileSecondary
            or GeneratedProjectileRuntimeVariant.VortexSecondary;

    public static bool UsesRootVfxManifest(GeneratedProjectileRuntimeVariant variant)
        => variant is GeneratedProjectileRuntimeVariant.Root
            or GeneratedProjectileRuntimeVariant.ChargeReleasedShot;

    public static bool IsVariantAllowedForParent(AttackSpec? parent, GeneratedProjectileRuntimeVariant variant)
    {
        if (parent is null || !parent.Enabled || !parent.RuntimePlanAuthored || !IsKnownVariant(variant))
            return false;
        if (variant == GeneratedProjectileRuntimeVariant.Root)
            return true;

        string family = GeneratedRuntimeFamilyPolicy.Normalize(parent.RuntimeFamily);
        bool boundedChild = parent.MaxChildProjectiles > 0 && parent.MaxChildDepth > 0;
        bool damagingChild = boundedChild && parent.SecondaryDamageMultiplier > 0f;
        return variant switch
        {
            GeneratedProjectileRuntimeVariant.StraightSecondary => damagingChild
                && (parent.SplitCount > 0
                    || GeneratedSecondaryTriggerPolicy.Is(parent.SecondaryTrigger, GeneratedSecondaryTriggerPolicy.OnExpire)),
            GeneratedProjectileRuntimeVariant.ChainSecondary => damagingChild
                && parent.ChainCount > 0 && parent.OnHitCode is 3 or 16,
            GeneratedProjectileRuntimeVariant.RadialSecondary => damagingChild
                && parent.SplitCount > 0 && parent.OnHitCode is 8 or 15,
            GeneratedProjectileRuntimeVariant.OverheadSecondary => damagingChild
                && (GeneratedRuntimeFamilyPolicy.Is(family, GeneratedRuntimeFamilyPolicy.OverheadBarrage)
                    || (parent.OnHitCode == 18 && parent.SplitCount > 0)),
            GeneratedProjectileRuntimeVariant.SporeSecondary => damagingChild
                && parent.OnHitCode == 11 && parent.SplitCount > 0,
            GeneratedProjectileRuntimeVariant.MiniMissileSecondary => damagingChild
                && parent.OnHitCode == 12 && parent.SplitCount > 0,
            GeneratedProjectileRuntimeVariant.VortexSecondary => damagingChild
                && parent.OnHitCode == 13 && parent.SplitCount > 0,
            GeneratedProjectileRuntimeVariant.SentryShot => boundedChild
                && GeneratedRuntimeFamilyPolicy.Is(family, GeneratedRuntimeFamilyPolicy.Sentry),
            GeneratedProjectileRuntimeVariant.ChargeReleasedShot => GeneratedRuntimeFamilyPolicy.Is(family, GeneratedRuntimeFamilyPolicy.ChargeRelease),
            GeneratedProjectileRuntimeVariant.SwingSecondary => damagingChild
                && GeneratedRuntimeFamilyPolicy.Is(family, GeneratedRuntimeFamilyPolicy.Swing)
                && (parent.SplitCount > 0 || parent.MaxChildProjectiles > 0) && HasExplicitSecondaryBody(parent),
            GeneratedProjectileRuntimeVariant.SwingOverheadSecondary => damagingChild
                && GeneratedRuntimeFamilyPolicy.Is(family, GeneratedRuntimeFamilyPolicy.Swing)
                && parent.OnHitCode == 18 && parent.SplitCount > 0 && HasExplicitSecondaryBody(parent),
            _ => false,
        };
    }

    public static bool TryCreateRuntimeVariant(
        AttackSpec parent,
        GeneratedProjectileRuntimeVariant variant,
        out AttackSpec spec)
    {
        spec = new AttackSpec { Enabled = false, RuntimePlanAuthored = true };
        if (!IsVariantAllowedForParent(parent, variant))
            return false;

        switch (variant)
        {
            case GeneratedProjectileRuntimeVariant.Root:
                spec = parent.CloneForRuntimeSpawn();
                break;
            case GeneratedProjectileRuntimeVariant.StraightSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 0, onHit: 0, scale: 0.75f);
                spec.Lifetime = parent.SecondaryLifetimeTicks;
                break;
            case GeneratedProjectileRuntimeVariant.ChainSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 0, onHit: 0, scale: 0.65f);
                spec.Lifetime = parent.SecondaryLifetimeTicks;
                break;
            case GeneratedProjectileRuntimeVariant.RadialSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 3, onHit: 0, scale: 0.55f);
                spec.Lifetime = parent.SecondaryLifetimeTicks;
                break;
            case GeneratedProjectileRuntimeVariant.OverheadSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 2, onHit: 0, scale: 0.62f);
                ConfigureOverheadChild(spec, parent);
                break;
            case GeneratedProjectileRuntimeVariant.SporeSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 3, onHit: 0, scale: 0.5f);
                spec.Lifetime = parent.SecondaryLifetimeTicks;
                spec.TileCollide = false;
                break;
            case GeneratedProjectileRuntimeVariant.MiniMissileSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 13, onHit: 1, scale: 0.55f);
                spec.Lifetime = parent.SecondaryLifetimeTicks;
                spec.TileCollide = false;
                break;
            case GeneratedProjectileRuntimeVariant.VortexSecondary:
                spec = CreateGenericGameplayChild(parent, movement: 11, onHit: 1, scale: 0.7f);
                spec.Lifetime = parent.SecondaryLifetimeTicks;
                spec.TileCollide = false;
                break;
            case GeneratedProjectileRuntimeVariant.SentryShot:
                spec = parent.CloneForRuntimeSpawn();
                ConfigureSentryShot(spec, parent);
                break;
            case GeneratedProjectileRuntimeVariant.ChargeReleasedShot:
                spec = parent.CloneForRuntimeSpawn();
                ConfigureChargeReleasedShot(spec, parent);
                break;
            case GeneratedProjectileRuntimeVariant.SwingSecondary:
                spec = CreateSwingSecondary(parent);
                break;
            case GeneratedProjectileRuntimeVariant.SwingOverheadSecondary:
                spec = CreateSwingSecondary(parent);
                ConfigureOverheadChild(spec, parent);
                break;
            default:
                return false;
        }
        return true;
    }

    public static AttackSpec CreateGenericGameplayChild(AttackSpec parent, int movement, int onHit, float scale)
    {
        var child = new AttackSpec
        {
            Enabled = parent.Enabled,
            DamageClass = parent.DamageClass,
            MovementCode = movement,
            EffectCode = parent.EffectCode,
            OnHitCode = onHit,
            ProjectileWidth = Math.Max(8, (int)(parent.ProjectileWidth * scale)),
            ProjectileHeight = Math.Max(8, (int)(parent.ProjectileHeight * scale)),
            ProjectileScale = Math.Max(0.45f, parent.ProjectileScale * scale),
            HitboxScale = 1f,
            ExplosionRadius = 0,
            RangeTiles = Math.Clamp(parent.RangeTiles, 4f, 120f),
            HomingStrength = Math.Clamp(parent.HomingStrength, 0f, 1f),
            BeamWidthPx = 14f,
            Lifetime = Math.Min(80, Math.Max(24, parent.Lifetime / 2)),
            Pierce = 1,
            ExtraUpdates = Math.Min(1, parent.ExtraUpdates),
            TileCollide = true,
            BounceCount = 0,
            SplitCount = 0,
            ChainCount = 0,
            ImmunityCooldown = 18,
            ProcMode = 0,
            RuntimePlanAuthored = parent.RuntimePlanAuthored,
            SecondaryTrigger = GeneratedSecondaryTriggerPolicy.OnHit,
            SecondarySpreadRadians = parent.SecondarySpreadRadians,
            SecondaryDamageMultiplier = parent.SecondaryDamageMultiplier,
            SecondaryLifetimeTicks = parent.SecondaryLifetimeTicks,
            SameTargetBias = parent.SameTargetBias,
            DebuffHint = "",
            DebuffTime = 0,
            RuntimeFamily = GeneratedRuntimeFamilyPolicy.Shoot,
            Delivery = "shoot",
            WeaponFamily = "child_projectile",
            ProjectileFamily = string.IsNullOrWhiteSpace(parent.SecondaryProjectileShape) ? "child_projectile" : "secondary_projectile",
            AmmoKind = "",
            SecondaryMaterial = parent.SecondaryMaterial,
            SecondaryProjectileShape = parent.SecondaryProjectileShape,
            Pattern = "basic",
            MaxChildProjectiles = Math.Max(4, parent.MaxChildProjectiles / 2),
            MaxChildDepth = Math.Max(0, parent.MaxChildDepth - 1),
            DustSpawnDenom = Math.Max(3, parent.DustSpawnDenom + 1),
            BurstDustCap = parent.BurstDustCap <= 0 ? 0 : Math.Max(1, parent.BurstDustCap / 2),
            VisualMode = parent.VisualMode,
            TrailStyle = parent.TrailStyle,
            ImpactStyle = parent.ImpactStyle,
            PrimaryColorName = parent.PrimaryColorName,
            SoundPitch = parent.SoundPitch,
            SoundVolume = parent.SoundVolume,
            SoundPitchVariance = parent.SoundPitchVariance,
            ProjectileShape = parent.ProjectileShape,
            ProjectileMotion = parent.ProjectileMotion,
            ProjectileRotation = parent.ProjectileRotation,
            ProjectileTrail = parent.ProjectileTrail,
            ProjectileImpact = parent.ProjectileImpact,
            SoundUseCatalogId = parent.SoundUseCatalogId,
            SoundImpactCatalogId = parent.SoundImpactCatalogId,
            SoundUseCatalogPath = parent.SoundUseCatalogPath,
            SoundImpactCatalogPath = parent.SoundImpactCatalogPath,
            SoundCatalogSource = parent.SoundCatalogSource,
            ProjectileSpritePath = parent.ProjectileSpritePath,
            ProjectileSpriteUrl = parent.ProjectileSpriteUrl,
            ProjectileSpriteStatus = parent.ProjectileSpriteStatus,
            ProjectileSpritePrompt = parent.ProjectileSpritePrompt,
            ProjectileSpriteScore = parent.ProjectileSpriteScore,
            ImpactSpritePath = parent.ImpactSpritePath,
            ImpactSpriteUrl = parent.ImpactSpriteUrl,
            ImpactSpriteStatus = parent.ImpactSpriteStatus,
            ImpactSpritePrompt = parent.ImpactSpritePrompt,
            ImpactSpriteScore = parent.ImpactSpriteScore,
            ChildSpritePath = parent.ChildSpritePath,
            ChildSpriteUrl = parent.ChildSpriteUrl,
            ChildSpriteStatus = parent.ChildSpriteStatus,
            ChildSpritePrompt = parent.ChildSpritePrompt,
            ChildSpriteScore = parent.ChildSpriteScore,
            FieldSpritePath = parent.FieldSpritePath,
            FieldSpriteUrl = parent.FieldSpriteUrl,
            FieldSpriteStatus = parent.FieldSpriteStatus,
            FieldSpritePrompt = parent.FieldSpritePrompt,
            FieldSpriteScore = parent.FieldSpriteScore,
            VisualAnimationPlan = parent.VisualAnimationPlan,
            VfxManifestJson = parent.VfxManifestJson,
        };
        SanitizeGenericGameplayChild(child);
        return child;
    }

    public static AttackSpec CreateSwingSecondary(AttackSpec parent)
    {
        int size = Math.Max(8, (int)Math.Round(Math.Min(parent.ProjectileWidth, parent.ProjectileHeight) * 0.55f));
        string material = string.IsNullOrWhiteSpace(parent.SecondaryMaterial) ? "material" : parent.SecondaryMaterial.Trim();
        string shape = string.IsNullOrWhiteSpace(parent.SecondaryProjectileShape)
            ? material + " shard"
            : parent.SecondaryProjectileShape.Trim();
        return new AttackSpec
        {
            Enabled = true,
            RuntimePlanAuthored = true,
            RuntimeFamily = GeneratedRuntimeFamilyPolicy.Shoot,
            Delivery = "shoot",
            WeaponFamily = "secondary_projectile",
            ProjectileFamily = "secondary_projectile",
            Movement = "straight",
            MovementCode = 0,
            Effect = parent.Effect,
            EffectCode = parent.EffectCode,
            OnHit = "none",
            OnHitCode = 0,
            Speed = Math.Max(3f, parent.Speed * 0.82f),
            Lifetime = Math.Clamp(parent.SecondaryLifetimeTicks, 5, 180),
            Pierce = 1,
            ProjectileWidth = size,
            ProjectileHeight = size,
            ProjectileScale = Math.Clamp(parent.ProjectileScale * 0.58f, 0.45f, 1.15f),
            HitboxScale = 1f,
            TileCollide = true,
            ExtraUpdates = Math.Min(1, parent.ExtraUpdates),
            ShotCount = 1,
            SplitCount = 0,
            MaxChildProjectiles = 0,
            MaxChildDepth = 0,
            DustSpawnDenom = Math.Max(4, parent.DustSpawnDenom + 1),
            BurstDustCap = Math.Max(0, parent.BurstDustCap / 2),
            SecondaryDamageMultiplier = 0f,
            SecondaryMaterial = material,
            SecondaryProjectileShape = shape,
            ProjectileShape = shape,
            ProjectileMotion = "short emitted shard from melee hit",
            ProjectileTrail = parent.ProjectileTrail,
            ProjectileImpact = parent.ProjectileImpact,
            PrimaryColorName = parent.PrimaryColorName,
            SoundUseCatalogId = parent.SoundUseCatalogId,
            SoundImpactCatalogId = parent.SoundImpactCatalogId,
            SoundCatalogSource = parent.SoundCatalogSource,
            SoundPitch = parent.SoundPitch,
            SoundVolume = parent.SoundVolume,
            SoundPitchVariance = parent.SoundPitchVariance,
            ProjectileSpritePath = parent.ChildSpritePath,
            ProjectileSpriteUrl = parent.ChildSpriteUrl,
            ProjectileSpriteStatus = parent.ChildSpriteStatus,
            ProjectileSpritePrompt = "",
            ProjectileSpriteScore = parent.ChildSpriteScore,
            ImpactSpritePath = parent.ImpactSpritePath,
            ImpactSpriteUrl = parent.ImpactSpriteUrl,
            ImpactSpriteStatus = parent.ImpactSpriteStatus,
            ImpactSpritePrompt = "",
            ImpactSpriteScore = parent.ImpactSpriteScore,
        };
    }

    private static bool HasExplicitSecondaryBody(AttackSpec parent)
        => !string.IsNullOrWhiteSpace(parent.SecondaryProjectileShape)
            || !string.IsNullOrWhiteSpace(parent.SecondaryMaterial);

    private static void ConfigureOverheadChild(AttackSpec child, AttackSpec parent)
        => GeneratedOverheadBarragePolicy.ConfigureChild(child, parent);

    public static void SanitizeGenericGameplayChild(AttackSpec child)
    {
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
        child.SecondaryTrigger = GeneratedSecondaryTriggerPolicy.OnHit;
        child.ChainCount = 0;
        child.ProcMode = 0;
        child.ExplosionRadius = 0;
        child.BurstDustCap = 0;
        child.DustSpawnDenom = 0;
        child.VfxParticleDurationTicks = 0;
        child.VfxFieldLifetimeTicks = 0;
        child.VfxFieldRadiusTiles = 0f;
        child.VfxFieldTickRate = 0;
    }

    public static void ConfigureSentryShot(AttackSpec shot, AttackSpec parent)
    {
        shot.RuntimeFamily = GeneratedRuntimeFamilyPolicy.Shoot;
        shot.Delivery = "shoot";
        shot.ChannelUse = false;
        shot.SentryPlacement = "grounded";
        shot.SentryAttackIntervalTicks = 45;
        shot.SentryTargetRangeTiles = 30f;
        shot.SentryLifetimeTicks = 3600;
        shot.ShotCount = 1;
        shot.SplitCount = 0;
        shot.ChainCount = 0;
        shot.SecondaryTrigger = "";
        shot.MaxChildProjectiles = 0;
        shot.MaxChildDepth = 0;
        shot.Lifetime = Math.Clamp(parent.SecondaryLifetimeTicks, 5, 180);
        shot.ProjectileWidth = Math.Clamp(parent.ProjectileWidth / 2, 8, 24);
        shot.ProjectileHeight = Math.Clamp(parent.ProjectileHeight / 2, 8, 24);
        shot.ProjectileShape = string.IsNullOrWhiteSpace(parent.SecondaryProjectileShape) ? "sentry shot" : parent.SecondaryProjectileShape;
        shot.ProjectileFamily = "";
        shot.ProjectileSpritePath = parent.ChildSpritePath;
        shot.ProjectileSpriteUrl = parent.ChildSpriteUrl;
        shot.ProjectileSpriteStatus = parent.ChildSpriteStatus;
        shot.ProjectileSpritePrompt = "";
        shot.ProjectileSpriteScore = parent.ChildSpriteScore;
        shot.ChildSpritePath = "";
        shot.ChildSpriteUrl = "";
        shot.ChildSpriteStatus = "";
        shot.ChildSpritePrompt = "";
        shot.VfxManifestJson = "";
        shot.VfxFieldLifetimeTicks = 0;
        shot.VfxFieldRadiusTiles = 0f;
        shot.VfxFieldTickRate = 0;
    }

    public static void ConfigureChargeReleasedShot(AttackSpec released, AttackSpec parent)
    {
        released.RuntimeFamily = (parent.Delivery ?? "").Trim().ToLowerInvariant() switch
        {
            "cast" => GeneratedRuntimeFamilyPolicy.Cast,
            "throw" => GeneratedRuntimeFamilyPolicy.Throw,
            _ => GeneratedRuntimeFamilyPolicy.Shoot,
        };
        released.ChannelUse = false;
        released.ChargeTicks = 45;
        released.ChargePowerMultiplier = 1f;
        released.ShotCount = 1;
        released.HideUseGraphic = false;
        released.OwnerHitCheck = false;
    }
}
