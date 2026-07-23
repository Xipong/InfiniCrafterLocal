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

public sealed partial class GeneratedProjectile
{

    private void RestoreAuthoredChildPresentationFromRegistry()
    {
        if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is null)
            return;
        AttackSpec? parent = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetAttack(_generatedItemId);
        if (parent is null)
            return;
        ApplyAuthoredChildPresentation(_spec, parent);
    }

    private void HydratePresentationFromRegistryIfPossible()
    {
        // Projectile packets intentionally stay lean: they carry runtime numbers + generated id,
        // not PNG paths or manifest bulk. If the registry arrives a tick later than this projectile
        // packet, restore only presentation/asset state from the local registry without touching
        // executable movement/effect/on-hit values. This keeps Terraria net packets small while
        // still allowing first-shot generated sprites/VFX to appear after async registry hydration.
        if (string.IsNullOrWhiteSpace(_generatedItemId) || global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is null)
            return;

        AttackSpec? parent = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetAttack(_generatedItemId);
        if (parent is null)
        {
            RequestOneGeneratedItemForMissingProjectile(_generatedItemId);
        }
        if (parent is not null)
        {
            CopyMissingPresentationPaths(parent);

            if (string.IsNullOrWhiteSpace(_spec.VisualMode)) _spec.VisualMode = parent.VisualMode ?? "";
            if (string.IsNullOrWhiteSpace(_spec.TrailStyle)) _spec.TrailStyle = parent.TrailStyle ?? "";
            if (string.IsNullOrWhiteSpace(_spec.ImpactStyle)) _spec.ImpactStyle = parent.ImpactStyle ?? "";
            if (string.IsNullOrWhiteSpace(_spec.PrimaryColorName)) _spec.PrimaryColorName = parent.PrimaryColorName ?? "";
            if (string.IsNullOrWhiteSpace(_spec.SoundUseCatalogId)) _spec.SoundUseCatalogId = parent.SoundUseCatalogId ?? "";
            if (string.IsNullOrWhiteSpace(_spec.SoundImpactCatalogId)) _spec.SoundImpactCatalogId = parent.SoundImpactCatalogId ?? "";
            if (string.IsNullOrWhiteSpace(_spec.SoundCatalogSource)) _spec.SoundCatalogSource = parent.SoundCatalogSource ?? "";
        }

        if (_vfxManifest is null || !_vfxManifest.HasSlots)
        {
            _vfxManifest = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetVfxManifest(_generatedItemId);
            _vfxManifest.Normalize();
            if (_vfxManifest.HasSlots)
            {
                _spec.VfxManifestJson = _vfxManifest.ToJson();
                _vfxState = new InfiniVfxState { LocalSeed = _vfxManifest.Seed };
            }
        }
    }


    private void CopyMissingPresentationPaths(AttackSpec parent)
    {
        if (parent is null)
            return;

        // Child variants own child/field presentation. Falling back to the root
        // projectile sprite turns a sentry shot into the sentry body (and causes
        // the same role inversion for other authored children). Empty child paths
        // intentionally fall through to procedural shape rendering.
        if (_runtimeVariant == GeneratedProjectileRuntimeVariant.Root
            && string.IsNullOrWhiteSpace(_spec.ProjectileSpritePath)
            && HasPngPath(parent.ProjectileSpritePath))
        {
            _spec.ProjectileSpritePath = parent.ProjectileSpritePath.Trim();
            _spec.ProjectileSpriteStatus = parent.ProjectileSpriteStatus ?? "";
            _spec.ProjectileSpriteScore = parent.ProjectileSpriteScore;
        }
        if (string.IsNullOrWhiteSpace(_spec.ImpactSpritePath) && HasPngPath(parent.ImpactSpritePath))
        {
            _spec.ImpactSpritePath = parent.ImpactSpritePath.Trim();
            _spec.ImpactSpriteStatus = parent.ImpactSpriteStatus ?? "";
            _spec.ImpactSpriteScore = parent.ImpactSpriteScore;
        }
        if (string.IsNullOrWhiteSpace(_spec.ChildSpritePath) && HasPngPath(parent.ChildSpritePath))
        {
            _spec.ChildSpritePath = parent.ChildSpritePath.Trim();
            _spec.ChildSpriteStatus = parent.ChildSpriteStatus ?? "";
            _spec.ChildSpriteScore = parent.ChildSpriteScore;
        }
        if (string.IsNullOrWhiteSpace(_spec.FieldSpritePath) && HasPngPath(parent.FieldSpritePath))
        {
            _spec.FieldSpritePath = parent.FieldSpritePath.Trim();
            _spec.FieldSpriteStatus = parent.FieldSpriteStatus ?? "";
            _spec.FieldSpriteScore = parent.FieldSpriteScore;
        }
    }

    private static void ApplyAuthoredChildPresentation(AttackSpec child, AttackSpec parent)
    {
        if (child is null || parent is null)
            return;

        child.VisualMode = "projectile";
        child.VisualAnimationPlan = "";

        if (HasPngPath(parent.ChildSpritePath))
        {
            child.ProjectileSpritePath = parent.ChildSpritePath.Trim();
            child.ProjectileSpriteStatus = parent.ChildSpriteStatus ?? "";
            child.ProjectileSpriteScore = parent.ChildSpriteScore;
        }

        string secondaryShape = TrimMax(parent.SecondaryProjectileShape, 120);
        string secondaryMaterial = TrimMax(parent.SecondaryMaterial, 80);
        if (!string.IsNullOrWhiteSpace(secondaryShape))
            child.ProjectileShape = secondaryShape;
        else if (!string.IsNullOrWhiteSpace(secondaryMaterial))
            child.ProjectileShape = TrimMax(secondaryMaterial + " shard", 120);
        else
            child.ProjectileShape = TrimMax(child.ProjectileShape, 120);

        child.PrimaryColorName = string.IsNullOrWhiteSpace(parent.PrimaryColorName)
            ? child.PrimaryColorName
            : TrimMax(parent.PrimaryColorName, 48);

        child.TrailStyle = TrimMax(parent.TrailStyle, 80);
        if (string.IsNullOrWhiteSpace(child.TrailStyle))
            child.TrailStyle = "none";
        child.ImpactStyle = TrimMax(parent.ImpactStyle, 80);
        if (string.IsNullOrWhiteSpace(child.ImpactStyle))
            child.ImpactStyle = "none";

        child.DustSpawnDenom = parent.DustSpawnDenom <= 0 ? 0 : Math.Clamp(parent.DustSpawnDenom + 1, 4, 16);
        child.BurstDustCap = parent.BurstDustCap <= 0 ? 0 : Math.Clamp(parent.BurstDustCap / 3, 0, 12);

        // Prompt/local-generator fields stay empty on gameplay children. Runtime may draw
        // the already-authored child asset, but it never asks a child shard to become a
        // second generated mini-item.
        child.ProjectileSpritePrompt = "";
        child.ImpactSpritePath = "";
        child.ImpactSpritePrompt = "";
        child.ChildSpritePath = "";
        child.ChildSpritePrompt = "";
        child.FieldSpritePath = "";
        child.FieldSpritePrompt = "";
        child.VfxManifestJson = "";
    }

    private static bool HasPngPath(string? path)
    {
        string p = path?.Trim() ?? "";
        return p.Length > 0 && p.Length <= 320 && p.EndsWith(".png", StringComparison.OrdinalIgnoreCase);
    }

    private static string TrimMax(string? value, int maxChars)
    {
        string v = value?.Trim() ?? "";
        if (maxChars > 0 && v.Length > maxChars)
            return v[..maxChars];
        return v;
    }

    private AttackSpec VisualChildSpec(string role, int lifetime, float scale = 0.55f)
    {
        AttackSpec child = ChildSpec(3, 0, scale);
        child.Lifetime = lifetime;
        child.TileCollide = false;
        child.Pierce = 1;
        child.ExplosionRadius = 0;
        child.ProjectileShape = role;
        child.ProjectileMotion = "hover visual";
        bool fieldRole = string.Equals(role, "field", StringComparison.OrdinalIgnoreCase);
        bool impactRole = string.Equals(role, "impact", StringComparison.OrdinalIgnoreCase) || string.Equals(role, "hit", StringComparison.OrdinalIgnoreCase);
        child.ProjectileTrail = fieldRole ? "soft field residue" : "short sparkle residue";
        if (impactRole && !string.IsNullOrWhiteSpace(_spec.ImpactSpritePath))
        {
            child.ProjectileSpritePath = _spec.ImpactSpritePath;
            child.ProjectileSpriteStatus = _spec.ImpactSpriteStatus;
            child.ProjectileSpritePrompt = _spec.ImpactSpritePrompt;
        }
        else if (fieldRole && !string.IsNullOrWhiteSpace(_spec.FieldSpritePath))
        {
            child.ProjectileSpritePath = _spec.FieldSpritePath;
            child.ProjectileSpriteStatus = _spec.FieldSpriteStatus;
            child.ProjectileSpritePrompt = _spec.FieldSpritePrompt;
        }
        else if (!string.IsNullOrWhiteSpace(_spec.ChildSpritePath))
        {
            child.ProjectileSpritePath = _spec.ChildSpritePath;
            child.ProjectileSpriteStatus = _spec.ChildSpriteStatus;
            child.ProjectileSpritePrompt = _spec.ChildSpritePrompt;
        }
        return child;
    }

    private void SpawnDust(int effect)
    {
        if (Main.netMode == NetmodeID.Server || !AuthoredParticlesActive()) return;
        if (_spec.DustSpawnDenom <= 0) return;
        int denom = Math.Clamp(_spec.DustSpawnDenom <= 0 ? 3 : _spec.DustSpawnDenom, 2, 12);
        if (!Main.rand.NextBool(denom)) return;
        int dust = DustForAuthoredParticle(effect);
        if (dust < 0) return;
        Dust d = Dust.NewDustDirect(Projectile.position, Projectile.width, Projectile.height, dust, Projectile.velocity.X * 0.1f, Projectile.velocity.Y * 0.1f);
        d.noGravity = effect is 1 or 3 or 7 or 12 or 13 or 14;
        d.scale *= AuthoredParticleScale();
    }

    private bool AllowsVanillaMotionPolish()
    {
        if (_spec.DustSpawnDenom > 0 || _spec.EffectCode != 0 || AllowsPresentationLight())
            return true;
        return GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Beam)
            || GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Thrust)
            || GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Returning)
            || GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Flail)
            || GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Yoyo)
            || GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Whip);
    }

    private int VanillaPolishDust() => DustForEffect(_spec.EffectCode);

    private int VanillaMotionPolishDenominator()
    {
        if (GeneratedRuntimeFamilyPolicy.Is(_spec.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Beam))
            return 5;
        return _spec.EffectCode is 1 or 3 ? 5 : 8;
    }

    private void EmitVanillaMotionPolish()
    {
        if (Main.netMode == NetmodeID.Server || Main.dedServ) return;
        if (_spec.DustSpawnDenom > 0 && !AuthoredParticlesActive()) return;
        if (Projectile.localAI[0] < 2f) return;
        if (Projectile.velocity.LengthSquared() <= 36f && !AllowsVanillaMotionPolish()) return;
        if (!Main.rand.NextBool(VanillaMotionPolishDenominator())) return;
        int dust = VanillaPolishDust();
        if (dust < 0) return;
        Dust d = Dust.NewDustDirect(Projectile.position, Projectile.width, Projectile.height, dust, -Projectile.velocity.X * 0.10f, -Projectile.velocity.Y * 0.10f, 120);
        d.noGravity = true;
        d.scale *= Math.Clamp(0.78f + _spec.ProjectileScale * 0.18f, 0.70f, 1.25f);
    }

    private void EmitVanillaImpactPolish(Vector2 center, bool kill)
    {
        if (Main.netMode == NetmodeID.Server || Main.dedServ) return;
        int dust = VanillaPolishDust();
        if (dust < 0) return;
        bool hasManifest = _vfxManifest is not null && _vfxManifest.HasSlots;
        int count = Math.Clamp((kill ? 7 : 5) + (AllowsPresentationLight() ? 2 : 0) - (hasManifest ? 2 : 0), 2, 10);
        float speed = kill ? 2.2f : 1.45f;
        for (int i = 0; i < count; i++)
        {
            Vector2 v = Main.rand.NextVector2Circular(speed, speed);
            Dust d = Dust.NewDustDirect(center - new Vector2(4f), 8, 8, dust, v.X, v.Y, 120);
            d.noGravity = true;
            d.scale *= kill ? 1.10f : 0.92f;
        }
    }

    private int DustForEffect(int effect) => effect switch
    {
        0 => _spec.DustSpawnDenom <= 0 ? -1 : DustID.Smoke,
        1 => DustID.Electric,
        2 => DustID.t_Slime,
        3 => DustID.YellowStarDust,
        4 => DustID.Torch,
        5 => DustID.Ice,
        6 => DustID.Grass,
        7 => DustID.Shadowflame,
        8 => DustID.GreenTorch,
        9 => DustID.RedTorch,
        10 => DustID.YellowTorch,
        11 => DustID.Sand,
        12 => DustID.PinkTorch,
        13 => DustID.GemSapphire,
        14 => DustID.PurpleTorch,
        15 => DustID.Smoke,
        _ => DustID.Smoke
    };

    private float RuntimeAgeTicks()
        => Projectile.localAI[0] / Math.Max(1f, Projectile.extraUpdates + 1f);

    private bool AuthoredParticlesActive()
        => _spec.VfxParticleDurationTicks <= 0 || RuntimeAgeTicks() <= _spec.VfxParticleDurationTicks;

    private float AuthoredParticleScale()
        => _spec.VfxParticleScale > 0f ? Math.Clamp(_spec.VfxParticleScale, 0.1f, 2f) : 1f;

    private int DustForAuthoredParticle(int effect)
    {
        if (effect != 0 || string.IsNullOrWhiteSpace(_spec.VfxMaterial))
            return DustForEffect(effect);
        return _spec.VfxMaterial.Trim().ToLowerInvariant() switch
        {
            "metal" => DustID.Iron,
            "stone" => DustID.Stone,
            "wood" => DustID.WoodFurniture,
            "slime" => DustID.t_Slime,
            "fire" => DustID.Torch,
            "frost" => DustID.Ice,
            "shadow" => DustID.Shadowflame,
            "magic" => DustID.MagicMirror,
            _ => DustForEffect(effect),
        };
    }

    private void EmitAuthoredVisualField()
    {
        if (Main.netMode == NetmodeID.Server || Main.dedServ) return;
        int lifetime = Math.Clamp(_spec.VfxFieldLifetimeTicks, 0, 240);
        float radiusTiles = Math.Clamp(_spec.VfxFieldRadiusTiles, 0f, 6f);
        int tickRate = Math.Clamp(_spec.VfxFieldTickRate, 0, 60);
        if (lifetime <= 0 || radiusTiles <= 0f || tickRate <= 0) return;
        float age = RuntimeAgeTicks();
        if (age > lifetime) return;
        int maxUpdates = Math.Max(1, Projectile.extraUpdates + 1);
        if ((int)Projectile.localAI[0] % maxUpdates != 0) return;
        int wholeAge = Math.Max(0, (int)Math.Floor(age));
        if (wholeAge % tickRate != 0) return;

        float radiusPx = radiusTiles * 16f;
        int count = Math.Clamp((int)Math.Ceiling(radiusTiles * 2f), 4, 12);
        int dust = DustForAuthoredParticle(_spec.EffectCode);
        if (dust < 0) dust = DustID.Smoke;
        float phase = (Projectile.identity * 0.37f + wholeAge * 0.09f) % MathHelper.TwoPi;
        for (int i = 0; i < count; i++)
        {
            float angle = phase + MathHelper.TwoPi * i / count;
            Vector2 offset = angle.ToRotationVector2() * radiusPx;
            Dust d = Dust.NewDustPerfect(Projectile.Center + offset, dust, angle.ToRotationVector2() * 0.18f, 120);
            d.noGravity = true;
            d.scale *= AuthoredParticleScale();
        }
    }

    private void BurstDust(int effect, int count, float speed)
    {
        if (Main.netMode == NetmodeID.Server || !AuthoredParticlesActive()) return;
        int dust = DustForAuthoredParticle(effect);
        if (dust < 0) return;
        int authoredCap = Math.Clamp(_spec.BurstDustCap, 0, 40);
        count = Math.Clamp(count, 0, authoredCap);
        for (int i = 0; i < count; i++)
        {
            Dust d = Dust.NewDustDirect(Projectile.position, Projectile.width, Projectile.height, dust, Main.rand.NextFloat(-speed, speed), Main.rand.NextFloat(-speed, speed));
            d.noGravity = true;
            d.scale *= AuthoredParticleScale();
        }
    }

    private Color PresentationColor(int alpha = 255)
    {
        Color color = RuntimeColorPolicy.Resolve(_spec.PrimaryColorName, Color.White);
        color.A = (byte)Math.Clamp(alpha, 0, 255);
        return color;
    }


    private bool AllowsPresentationLight()
    {
        return _spec.RuntimeLightStrength > 0.001f
            && (_spec.RuntimeLightDurationTicks <= 0 || RuntimeAgeTicks() <= _spec.RuntimeLightDurationTicks);
    }


    private void AddPresentationLight()
    {
        if (Main.netMode == NetmodeID.Server) return;
        if (!AllowsPresentationLight()) return;
        float lightMul = InfiniVfxClientOptions.PresentationLightMultiplier;
        if (lightMul <= 0f) return;
        Color c = RuntimeColorPolicy.Resolve(_spec.PrimaryColorName, PresentationColor());
        float baseStrength = Math.Clamp(_spec.RuntimeLightStrength, 0.04f, 0.75f);
        float strength = baseStrength * lightMul;
        Lighting.AddLight(Projectile.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
    }

// =============================================================================
// NAV: PROJECTILE_DRAWING
// =============================================================================
    public override bool PreDraw(ref Color lightColor)
    {
        ApplyPendingProjectileVisualSyncIfAny();
        HydratePresentationFromRegistryIfPossible();
        Texture2D px = TextureAssets.MagicPixel.Value;
        Color c = PresentationColor(190);
        Vector2 center = Projectile.Center - Main.screenPosition;
        Vector2 dir = Projectile.velocity.SafeNormalize(Vector2.UnitX);
        Vector2 perp = dir.RotatedBy(MathHelper.PiOver2);
        float len = Math.Clamp(Projectile.velocity.Length() * 2.8f + Projectile.width * Projectile.scale, 14f, 96f);
        float width = Math.Clamp(Projectile.height * Projectile.scale * 0.35f, 2f, 14f);
        bool beamLike = IsBeamDelivery();
        bool executableBeamVisual = beamLike && _spec.MovementCode == 15;
        bool thrustLike = IsThrustDelivery();
        bool tetherLike = IsFlailDelivery()
            || IsYoyoDelivery()
            || (_spec.MovementCode is 5 or 14 && _spec.PullStrength > 0f);
        bool whipLike = IsWhipDelivery();
        if (tetherLike && Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers)
        {
            Vector2 ownerCenter = Main.player[Projectile.owner].MountedCenter - Main.screenPosition;
            DrawLine(px, ownerCenter, center, c * 0.45f, Math.Max(1f, width * 0.35f));
        }
        if (whipLike)
        {
            FillGeneratedWhipControlPoints(_whipControlPoints);
            for (int i = 1; i < _whipControlPoints.Count; i++)
            {
                DrawLine(
                    px,
                    _whipControlPoints[i - 1] - Main.screenPosition,
                    _whipControlPoints[i] - Main.screenPosition,
                    c * 0.70f,
                    Math.Max(2f, width * 0.55f));
            }
        }
        bool executableSlashVisual = GeneratedRuntimeFamilyPolicy.Is(RuntimeFamily(), GeneratedRuntimeFamilyPolicy.Swing);

        VfxManifestSpec? manifest = _vfxManifest;
        if (beamLike)
        {
            BeamLine(out Vector2 beamStart, out Vector2 beamEnd, out _);
            if (manifest is { HasSlots: true })
                InfiniVfxRuntime.Draw(Projectile, _spec, manifest, ref _vfxState, lightColor, InfiniVfxDrawPass.UnderProjectile);
            float beamCharge = BeamChargeRatio();
            float beamWidth = EffectiveBeamWidthPx();
            DrawLine(px, beamStart - Main.screenPosition, beamEnd - Main.screenPosition, c * MathHelper.Lerp(0.32f, 0.88f, beamCharge), beamWidth);
            DrawLine(px, beamStart - Main.screenPosition, beamEnd - Main.screenPosition, Color.White * MathHelper.Lerp(0.18f, 0.82f, beamCharge), Math.Max(1f, beamWidth * 0.28f));
            if (manifest is { HasSlots: true })
                InfiniVfxRuntime.Draw(Projectile, _spec, manifest, ref _vfxState, lightColor, InfiniVfxDrawPass.OverProjectile);
            return false;
        }
        if (manifest is { HasSlots: true })
        {
            // Terraria-style composition: oldPos trails and big support glows first,
            // the actual projectile sprite second, sharp foreground motes/impact cues last.
            InfiniVfxRuntime.Draw(Projectile, _spec, manifest, ref _vfxState, lightColor, InfiniVfxDrawPass.UnderProjectile);
            bool spriteDrawn = TryDrawGeneratedProjectileSprite(center, lightColor);

            // Multiplayer catch-up: remote peers can receive the projectile/VFX manifest before
            // the generated PNG has finished downloading. Do not let the VFX pass suppress the
            // whole projectile in that window; draw the compact runtime-plan silhouette until the
            // real projectile sprite appears from asset sync.
            if (!spriteDrawn && !TryDrawBundledProjectilePlaceholder(center, lightColor))
                DrawRuntimePlanFallback(px, center, dir, perp, c, len, width);

            InfiniVfxRuntime.Draw(Projectile, _spec, manifest, ref _vfxState, lightColor, InfiniVfxDrawPass.OverProjectile);
            return false;
        }

        if (executableBeamVisual)
        {
            DrawLine(px, center - dir * 12f, center + dir * len * 2.2f, c, Math.Max(2f, width * 0.45f));
            DrawLine(px, center - dir * 6f, center + dir * len * 1.8f, Color.White * 0.75f, Math.Max(1f, width * 0.2f));
            return false;
        }
        if (executableSlashVisual)
            DrawSlashSmear(px, center, dir, perp, c, len, width);

        if (TryDrawGeneratedProjectileSprite(center, lightColor))
            return false;

        if (!TryDrawBundledProjectilePlaceholder(center, lightColor))
            DrawRuntimePlanFallback(px, center, dir, perp, c, len, width);
        return false;
    }


    private void DrawSlashSmear(Texture2D px, Vector2 center, Vector2 dir, Vector2 perp, Color c, float len, float width)
    {
        float lifePulse = (float)Math.Sin(MathHelper.Clamp(Projectile.localAI[0] / Math.Max(16f, _spec.Lifetime * 0.35f), 0f, 1f) * MathHelper.Pi);
        float alphaMul = Math.Clamp(0.35f + lifePulse, 0.35f, 1.0f);
        for (int i = -4; i <= 4; i++)
        {
            float t = i / 4f;
            Vector2 a = center - dir * len * 0.18f + perp * t * len * 0.34f;
            Vector2 b = center + dir * len * (0.74f + 0.08f * Math.Abs(t)) - perp * t * len * 0.58f;
            Color lineColor = i == 0 ? Color.White * 0.82f * alphaMul : c * (0.50f - Math.Abs(t) * 0.07f) * alphaMul;
            DrawLine(px, a, b, lineColor, Math.Max(1f, width * (1.55f - Math.Abs(t) * 0.28f)));
        }
    }

    private bool TryDrawBundledProjectilePlaceholder(Vector2 center, Color lightColor)
    {
        try
        {
            Texture2D texture = ModContent.Request<Texture2D>("InfiniCrafterLocal/Assets/GeneratedItem").Value;
            var source = new Rectangle(0, 0, texture.Width, texture.Height);
            Vector2 origin = source.Size() * 0.5f;
            float targetPixels = Math.Clamp(Math.Max(Projectile.width, Projectile.height) * Projectile.scale, 10f, 28f);
            float scale = targetPixels / Math.Max(1f, Math.Max(texture.Width, texture.Height));
            Color tint = Projectile.GetAlpha(lightColor);
            Main.spriteBatch.Draw(texture, center + new Vector2(0f, Projectile.gfxOffY), source, tint, Projectile.rotation, origin, scale, SpriteEffects.None, 0f);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void DrawRuntimePlanFallback(Texture2D px, Vector2 center, Vector2 dir, Vector2 perp, Color c, float len, float width)
    {
        // Missing/catching-up art needs a compact body marker, not an invented beam or
        // trail. Mechanically required beam/tether/whip drawing and authored VFX slots
        // are handled above; this fallback must not author presentation of its own.
        float body = Math.Clamp(Math.Max(Projectile.width, Projectile.height) * Projectile.scale, 6f, 22f);
        Vector2 size = new(body, body);
        DrawRect(px, center - size * 0.5f, size, c * 0.78f);
        Vector2 core = size * 0.42f;
        DrawRect(px, center - core * 0.5f, core, Color.White * 0.62f);
    }

    private bool UsesItemSpriteAsProjectileByDefault()
        => GeneratedRuntimeFamilyPolicy.UsesItemSpriteAsProjectile(_spec.RuntimeFamily);

    private string ResolveProjectileSpritePath()
    {
        if (!string.IsNullOrWhiteSpace(_spec.ProjectileSpritePath))
            return _spec.ProjectileSpritePath;
        if (!UsesItemSpriteAsProjectileByDefault() || string.IsNullOrWhiteSpace(_generatedItemId))
            return "";

        if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is not null
            && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGet(_generatedItemId, out GeneratedItemData registryData))
        {
            return registryData.Visual?.SpritePath ?? "";
        }
        return "";
    }

    private bool TryDrawGeneratedProjectileSprite(Vector2 center, Color lightColor)
    {
        string spritePath = ResolveProjectileSpritePath();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(spritePath, out float localForwardRadians);
        if (texture is null)
        {
            RequestProjectileAssetCatchupIfMissing(spritePath, _generatedItemId);
            return false;
        }

        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        Vector2 origin = source.Size() * 0.5f;
        float rotation = Projectile.rotation - localForwardRadians;
        Vector2 drawPosition = center + new Vector2(0f, Projectile.gfxOffY);

        // Terraria and ExampleMod draw projectile frames at their authored native pixel size,
        // scaled only by the projectile's current presentation scale.  Do not normalize every
        // generated PNG to a hitbox/localAI-derived 18/28/42 px target: 48/64 px weapon bodies
        // are intentional art and their visual dimensions are independent from collision.
        float drawScale = Math.Clamp(Projectile.scale, 0.35f, 2.5f);
        Color tint = Projectile.GetAlpha(lightColor);
        // velocity rotation already carries the full world-space facing through
        // Projectile.rotation. Mirroring here would invert leftward shots a second time and make them fly butt-first.
        SpriteEffects effects = SpriteEffects.None;
        // Optional debug/readability silhouette. Disabled by default because it looks like
        // merged light/glow on both generated and vanilla-looking textures.
        Color backTint = PresentationColor(110) * 0.22f;
        if (drawScale > 0.4f && InfiniVfxClientOptions.EnableGeneratedSpriteSilhouette)
            Main.spriteBatch.Draw(texture, drawPosition, source, backTint, rotation, origin, drawScale * 1.08f, effects, 0f);
        Main.spriteBatch.Draw(texture, drawPosition, source, tint, rotation, origin, drawScale, effects, 0f);
        return true;
    }

    private static void DrawRect(Texture2D px, Vector2 pos, Vector2 size, Color color)
    {
        Main.spriteBatch.Draw(px, pos, new Rectangle(0, 0, 1, 1), color, 0f, Vector2.Zero, size, SpriteEffects.None, 0f);
    }


    private static void DrawLine(Texture2D px, Vector2 a, Vector2 b, Color color, float width)
    {
        Vector2 delta = b - a;
        float len = delta.Length();
        if (len <= 0.01f) return;
        Main.spriteBatch.Draw(px, a, new Rectangle(0, 0, 1, 1), color, delta.ToRotation(), Vector2.Zero, new Vector2(len, width), SpriteEffects.None, 0f);
    }

}
