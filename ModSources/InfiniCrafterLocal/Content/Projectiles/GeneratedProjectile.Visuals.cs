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
            if (string.IsNullOrWhiteSpace(_spec.ImpactSoundProfile)) _spec.ImpactSoundProfile = parent.ImpactSoundProfile ?? "";
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

        if (string.IsNullOrWhiteSpace(_spec.ProjectileSpritePath) && HasPngPath(parent.ProjectileSpritePath))
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
        if (_spec.DustSpawnDenom <= 0) return;
        int denom = Math.Clamp(_spec.DustSpawnDenom <= 0 ? 3 : _spec.DustSpawnDenom, 2, 12);
        if (!Main.rand.NextBool(denom)) return;
        int dust = DustForEffect(effect);
        if (dust < 0) return;
        Dust d = Dust.NewDustDirect(Projectile.position, Projectile.width, Projectile.height, dust, Projectile.velocity.X * 0.1f, Projectile.velocity.Y * 0.1f);
        d.noGravity = effect is 1 or 3 or 7 or 12 or 13 or 14;
    }

    private string PresentationIdentityText()
    {
        string tags = string.Join(" ", _spec.AttackPatternTags ?? Array.Empty<string>());
        return ($"{_spec.WeaponFamily} {_spec.WeaponSubfamily} {_spec.ProjectileFamily} {_spec.ProjectileShape} {_spec.Effect} {_spec.PrimaryColorName} {tags}").ToLowerInvariant();
    }

    private bool HasPresentationIdentity(params string[] needles)
    {
        string text = PresentationIdentityText();
        foreach (string needle in needles)
            if (text.Contains(needle, StringComparison.OrdinalIgnoreCase))
                return true;
        return false;
    }

    private int PolishDustForIdentity()
    {
        string text = PresentationIdentityText();
        if (text.Contains("electric") || text.Contains("lightning") || text.Contains("spark")) return DustID.Electric;
        if (text.Contains("star") || text.Contains("holy") || text.Contains("lunar") || text.Contains("bee")) return DustID.YellowStarDust;
        if (text.Contains("fire") || text.Contains("flame") || text.Contains("molten")) return DustID.Torch;
        if (text.Contains("ice") || text.Contains("frost") || text.Contains("snow")) return DustID.Ice;
        if (text.Contains("shadow") || text.Contains("void") || text.Contains("poison") || text.Contains("toxic")) return DustID.Shadowflame;
        if (text.Contains("slime") || text.Contains("honey")) return DustID.t_Slime;
        if (text.Contains("leaf") || text.Contains("nature")) return DustID.Grass;
        if (text.Contains("crystal") || text.Contains("glass") || text.Contains("gem")) return DustID.GemSapphire;
        return DustForEffect(_spec.EffectCode);
    }

    private void EmitVanillaMotionPolish()
    {
        if (Main.netMode == NetmodeID.Server || Main.dedServ) return;
        if (Projectile.localAI[0] < 2f) return;
        bool fastOrIconic = Projectile.velocity.LengthSquared() > 36f
            || AllowsPresentationLight()
            || HasPresentationIdentity("star", "beam", "laser", "bee", "crystal", "magic", "whip", "flail", "spear");
        if (!fastOrIconic) return;
        int denom = HasPresentationIdentity("beam", "laser", "star", "electric") ? 5 : 8;
        if (!Main.rand.NextBool(denom)) return;
        int dust = PolishDustForIdentity();
        if (dust < 0) return;
        Dust d = Dust.NewDustDirect(Projectile.position, Projectile.width, Projectile.height, dust, -Projectile.velocity.X * 0.10f, -Projectile.velocity.Y * 0.10f, 120);
        d.noGravity = true;
        d.scale *= Math.Clamp(0.78f + _spec.ProjectileScale * 0.18f, 0.70f, 1.25f);
    }

    private void EmitVanillaImpactPolish(Vector2 center, bool kill)
    {
        if (Main.netMode == NetmodeID.Server || Main.dedServ) return;
        int dust = PolishDustForIdentity();
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

    private const int OnHitBurst = 1;
    private const int OnHitAuraPulse = 10;
    private const int OnHitLifesteal = 17;

    private static bool OnHitUsesBurstDustFallback(int onHitCode)
    {
        return onHitCode is OnHitBurst or OnHitAuraPulse or OnHitLifesteal;
    }

    private void BurstDust(int effect, int count, float speed)
    {
        int dust = DustForEffect(effect);
        if (dust < 0) return;
        int authoredCap = Math.Clamp(_spec.BurstDustCap, 0, 40);
        int effectiveCap = authoredCap;
        if (effectiveCap <= 0 && count > 0 && OnHitUsesBurstDustFallback(_spec.OnHitCode))
            effectiveCap = Math.Clamp(count, 1, 24);
        count = Math.Clamp(count, 0, effectiveCap);
        for (int i = 0; i < count; i++)
        {
            Dust d = Dust.NewDustDirect(Projectile.position, Projectile.width, Projectile.height, dust, Main.rand.NextFloat(-speed, speed), Main.rand.NextFloat(-speed, speed));
            d.noGravity = true;
        }
    }

    private Color PresentationColor(int alpha = 255)
    {
        Color color = _spec.EffectCode switch
        {
            1 => new Color(80, 235, 255),
            2 => new Color(95, 255, 120),
            3 => new Color(255, 235, 90),
            4 => new Color(255, 150, 45),
            5 => new Color(120, 210, 255),
            6 => new Color(110, 220, 95),
            7 => new Color(190, 80, 255),
            8 => new Color(95, 255, 120),
            9 => new Color(255, 70, 55),
            10 => new Color(255, 210, 110),
            11 => new Color(225, 190, 120),
            12 => new Color(185, 110, 255),
            13 => new Color(120, 255, 190),
            14 => new Color(255, 245, 185),
            _ => new Color(150, 135, 110)
        };
        color.A = (byte)Math.Clamp(alpha, 0, 255);
        return color;
    }


    private bool AllowsPresentationLight()
    {
        return _spec.RuntimeLightStrength > 0.001f || _spec.EffectCode is 1 or 3 or 4 or 5 or 7 or 12 or 13 or 14;
    }

    private static Color ColorFromName(string? raw, Color fallback)
    {
        string name = (raw ?? "").Trim().ToLowerInvariant();
        return name switch
        {
            "white" or "silver" => new Color(235, 235, 235),
            "yellow" or "gold" or "amber" => new Color(255, 220, 110),
            "orange" => new Color(255, 155, 70),
            "red" or "crimson" or "scarlet" => new Color(255, 85, 85),
            "pink" => new Color(255, 145, 215),
            "purple" or "violet" => new Color(190, 110, 255),
            "blue" or "azure" or "cyan" => new Color(110, 210, 255),
            "green" or "lime" or "emerald" => new Color(110, 255, 145),
            "teal" or "aqua" => new Color(90, 255, 215),
            _ => fallback,
        };
    }

    private void AddPresentationLight()
    {
        if (Main.netMode == NetmodeID.Server) return;
        if (!AllowsPresentationLight()) return;
        float lightMul = InfiniVfxClientOptions.PresentationLightMultiplier;
        if (lightMul <= 0f) return;
        Color c = ColorFromName(_spec.PrimaryColorName, PresentationColor());
        float baseStrength = _spec.RuntimeLightStrength > 0.001f
            ? Math.Clamp(_spec.RuntimeLightStrength, 0.04f, 0.75f)
            : Math.Clamp(0.08f + _spec.ProjectileScale * 0.04f + _spec.PowerBudget * 0.015f, 0.04f, 0.32f);
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
        bool executableBeamVisual = _spec.MovementCode == 15;
        bool thrustLike = IsThrustDelivery();
        bool tetherLike = IsFlailDelivery() || IsYoyoDelivery();
        bool whipLike = IsWhipDelivery();
        if (tetherLike && Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers)
        {
            Vector2 ownerCenter = Main.player[Projectile.owner].MountedCenter - Main.screenPosition;
            DrawLine(px, ownerCenter, center, c * 0.45f, Math.Max(1f, width * 0.35f));
        }
        if (whipLike)
        {
            Vector2 ws, we, wd;
            WhipLine(out ws, out we, out wd);
            DrawLine(px, ws - Main.screenPosition, we - Main.screenPosition, c * 0.70f, Math.Max(2f, width * 0.55f));
        }
        bool executableSlashVisual = RuntimeFamily() == "swing";

        VfxManifestSpec? manifest = _vfxManifest;
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
            if (!spriteDrawn)
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

        DrawStockMotionPolish(px, center, dir, c, len, width);

        if (TryDrawGeneratedProjectileSprite(center, lightColor))
            return false;

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

    private void DrawStockMotionPolish(Texture2D px, Vector2 center, Vector2 dir, Color c, float len, float width)
    {
        if (Projectile.oldPos is null || Projectile.oldPos.Length < 3)
            return;
        bool shouldTrail = Projectile.velocity.LengthSquared() > 25f
            || RuntimeFamily() is "shoot" or "cast" or "throw"
            || HasPresentationIdentity("beam", "laser", "star", "crystal", "magic", "electric", "sword_beam");
        if (!shouldTrail)
            return;
        int count = Math.Clamp(3 + (int)(_spec.ProjectileScale * 2f), 3, Math.Min(Projectile.oldPos.Length, 8));
        float baseWidth = Math.Clamp(width * 0.55f, 1f, 5f);
        for (int i = count - 1; i >= 1; i--)
        {
            Vector2 oldCenter = Projectile.oldPos[i] + new Vector2(Projectile.width, Projectile.height) * 0.5f;
            Vector2 nextCenter = Projectile.oldPos[i - 1] + new Vector2(Projectile.width, Projectile.height) * 0.5f;
            if (oldCenter == Vector2.Zero || nextCenter == Vector2.Zero)
                continue;
            float fade = (count - i) / (float)count;
            DrawLine(px, oldCenter - Main.screenPosition, nextCenter - Main.screenPosition, c * fade * 0.42f, baseWidth * fade);
        }
    }

    private void DrawRuntimePlanFallback(Texture2D px, Vector2 center, Vector2 dir, Vector2 perp, Color c, float len, float width)
    {
        if (_spec.MovementCode == 15)
        {
            DrawLine(px, center - dir * 10f, center + dir * len * 1.9f, c * 0.72f, Math.Max(1.5f, width * 0.38f));
            DrawLine(px, center - dir * 4f, center + dir * len * 1.5f, Color.White * 0.65f, Math.Max(1f, width * 0.18f));
            return;
        }
        if (RuntimeFamily() == "swing")
        {
            DrawSlashSmear(px, center, dir, perp, c, len, width);
            return;
        }
        if (_spec.MovementCode is 5 or 14 or 16 or 17)
        {
            DrawLine(px, center - dir * len * 0.42f, center + dir * len * 0.42f, c * 0.78f, Math.Max(1f, width * 0.42f));
            DrawRect(px, center + dir * len * 0.32f - new Vector2(width * 0.55f, width * 0.55f), new Vector2(width * 1.1f, width * 1.1f), Color.White * 0.55f);
            return;
        }
        if (!AllowsPresentationLight())
        {
            DrawLine(px, center - dir * len * 0.55f, center + dir * len * 0.45f, c * 0.72f, Math.Max(1f, width * 0.45f));
            DrawLine(px, center - dir * len * 0.18f - perp * width * 0.45f, center + dir * len * 0.25f, c * 0.50f, Math.Max(1f, width * 0.25f));
            return;
        }
        DrawLine(px, center - dir * len * 0.9f, center, c * 0.75f, Math.Max(2f, width));
        DrawLine(px, center - dir * len * 0.35f, center + dir * 6f, Color.White * 0.85f, Math.Max(1f, width * 0.45f));
    }

    private bool TryDrawGeneratedProjectileSprite(Vector2 center, Color lightColor)
    {
        string spritePath = _spec.ProjectileSpritePath;
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(spritePath);
        if (texture is null)
        {
            RequestProjectileAssetCatchupIfMissing(spritePath, _generatedItemId);
            return false;
        }

        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        Vector2 origin = source.Size() * 0.5f;
        float rotation = Projectile.rotation;

        float basePixels = Math.Max(texture.Width, texture.Height);
        float targetPixels = Math.Max(8f, Math.Max(Projectile.width, Projectile.height) * Projectile.scale * 1.15f);
        if (IsThrustDelivery() || IsFlailDelivery() || IsYoyoDelivery() || IsWhipDelivery())
            targetPixels = Math.Max(targetPixels, 42f * Math.Max(0.75f, _spec.ProjectileScale));
        else if (Projectile.localAI[1] <= 0.001f)
            targetPixels = Math.Max(targetPixels, 28f * Math.Max(0.75f, _spec.ProjectileScale));
        else
            targetPixels = Math.Max(targetPixels, 18f * Math.Max(0.75f, _spec.ProjectileScale));
        float drawScale = Math.Clamp(targetPixels / Math.Max(1f, basePixels), 0.35f, 2.5f);
        Color tint = lightColor;
        SpriteEffects effects = (Projectile.spriteDirection < 0 || (Projectile.spriteDirection == 0 && Projectile.velocity.X < 0f))
            ? SpriteEffects.FlipHorizontally
            : SpriteEffects.None;
        // Optional debug/readability silhouette. Disabled by default because it looks like
        // merged light/glow on both generated and vanilla-looking textures.
        Color backTint = PresentationColor(110) * 0.22f;
        if (drawScale > 0.4f && InfiniVfxClientOptions.EnableGeneratedSpriteSilhouette)
            Main.spriteBatch.Draw(texture, center, source, backTint, rotation, origin, drawScale * 1.08f, effects, 0f);
        Main.spriteBatch.Draw(texture, center, source, tint, rotation, origin, drawScale, effects, 0f);
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
