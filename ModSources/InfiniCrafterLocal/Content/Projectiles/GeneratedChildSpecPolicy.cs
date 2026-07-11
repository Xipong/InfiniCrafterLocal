#nullable enable
using InfiniCrafterLocal.Common.Models;
using System;

namespace InfiniCrafterLocal.Content.Projectiles;

/// <summary>
/// Canonical transformations from an authored root AttackSpec to bounded runtime
/// child specs.  This class does not invent mechanics: it centralizes the resets
/// that already existed in projectile executors so parity/mutation tests can prove
/// that a sentry shot is not a sentry root and a released shot is not a holdout.
/// </summary>
internal static class GeneratedChildSpecPolicy
{
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
