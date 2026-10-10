#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using Terraria;
using Terraria.GameContent;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private bool PreservesExplicitBodyScale()
        => _entity?.HitboxCurve?.MirrorToSprite == true;

    public override bool PreDraw(ref Color lightColor)
    {
        if (!TryHydrate() || _data is null || _entity is null) return false;
        // One allowance per render invocation, shared by under/over passes.
        // A render need not be preceded by a new simulation tick.
        _vfxState.DrawCallsThisFrame = 0;
        InfiniDetachedVfxSystem.BeginActiveDraw(_vfxState.SourceKey);
        InfiniVfxRuntime.Draw(Projectile, _data, _entity.Id, _data.VfxManifest, ref _vfxState, lightColor, InfiniVfxDrawPass.UnderProjectile);
        DrawAuthoredEntityVisual(lightColor);
        InfiniVfxRuntime.Draw(Projectile, _data, _entity.Id, _data.VfxManifest, ref _vfxState, lightColor, InfiniVfxDrawPass.OverProjectile);
        return false;
    }

    private void DrawAuthoredEntityVisual(Color lightColor)
    {
        RuntimeEntityVisualSpec visual = _entity!.Visual;
        string mode = visual.AssetMode;
        if (mode == "no_asset") return;
        if (mode == "runtime_geometry")
        {
            DrawRuntimeGeometry(lightColor);
            return;
        }
        SpritePresentationSelection selected = SpritePresentation.Entity(_data!, _entity!);
        string path = selected.Path;
        if (string.IsNullOrWhiteSpace(path)) return; // missing required PNG fails closed; never draw a placeholder.
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(path);
        if (texture is null) return;
        Rectangle source = texture.Bounds;
        Vector2 origin = source.Size() * 0.5f;
        // An explicit mirror already owns the complete bounded product. Legacy
        // live sprite scale retains its old clamp when that mirror is absent.
        float scale = (PreservesExplicitBodyScale() ? Projectile.scale : Math.Clamp(Projectile.scale, 0.1f, 8f))
            * selected.FrameScale(source.Width, source.Height);
        SpriteEffects effects = Projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
        Main.spriteBatch.Draw(texture, Projectile.Center - Main.screenPosition + new Vector2(0f, Projectile.gfxOffY), source, Projectile.GetAlpha(lightColor), selected.ProjectileRotation(_entity, Projectile.rotation, effects), origin, scale, effects, 0f);
    }

    private void DrawRuntimeGeometry(Color lightColor)
    {
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        Color color = RuntimeColorPolicy.Resolve(_entity!.Light.Color, Projectile.GetAlpha(lightColor));
        if (_entity.Controller.Code == RuntimeControllerCode.ChannelBeam)
        {
            GetChannelBeamGeometry(out Vector2 start, out Vector2 end, out float beamWidth);
            InfiniVfxRuntime.DrawLine(pixel, start - Main.screenPosition, end - Main.screenPosition, color, beamWidth, preserveWidth: true);
            return;
        }
        if (_entity.Movement.Code == 18)
        {
            float whipWidth = WhipCollisionWidth();
            for (int i = 1; i < _whipPoints.Count; i++)
                InfiniVfxRuntime.DrawLine(pixel, _whipPoints[i - 1] - Main.screenPosition, _whipPoints[i] - Main.screenPosition, color, whipWidth);
            return; // Before movement initializes points there is no authored segment to draw.
        }
        Vector2 center = Projectile.Center - Main.screenPosition;
        // AI adds a quarter-turn for native vertical sprites. A horizontal
        // primitive uses the motion axis directly; retain explicit rotating
        // movement's pose rather than re-aiming a spinning body by velocity.
        Vector2 direction = _entity.Movement.Code is 14 or 16 or 17
            ? Projectile.rotation.ToRotationVector2()
            : Projectile.velocity.SafeNormalize(_initialDirection);
        bool exactScale = PreservesExplicitBodyScale();
        float length = exactScale ? _entity.Hitbox.WidthPx * Projectile.scale : Math.Max(8f, _entity.Hitbox.WidthPx * Projectile.scale);
        float width = exactScale ? _entity.Hitbox.HeightPx * Projectile.scale * 0.35f : Math.Max(2f, _entity.Hitbox.HeightPx * Projectile.scale * 0.35f);
        Vector2 delta = direction.SafeNormalize(Vector2.UnitX) * length;
        InfiniVfxRuntime.DrawLine(pixel, center - delta * 0.5f, center + delta * 0.5f, color, width, preserveWidth: exactScale);
    }
}
