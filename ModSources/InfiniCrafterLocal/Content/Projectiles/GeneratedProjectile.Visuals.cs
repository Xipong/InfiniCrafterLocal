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
    public override bool PreDraw(ref Color lightColor)
    {
        if (!TryHydrate() || _data is null || _entity is null) return false;
        // One allowance per render invocation, shared by under/over passes.
        // A render need not be preceded by a new simulation tick.
        _vfxState.DrawCallsThisFrame = 0;
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
        string path = mode == "reuse_item_icon" ? _data!.Visual.SpritePath : visual.SpritePath;
        if (string.IsNullOrWhiteSpace(path)) return; // missing required PNG fails closed; never draw a placeholder.
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(path);
        if (texture is null) return;
        Rectangle source = texture.Bounds;
        Vector2 origin = source.Size() * 0.5f;
        float scale = Math.Clamp(Projectile.scale, 0.1f, 8f);
        SpriteEffects effects = Projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
        Main.spriteBatch.Draw(texture, Projectile.Center - Main.screenPosition + new Vector2(0f, Projectile.gfxOffY), source, Projectile.GetAlpha(lightColor), Projectile.rotation, origin, scale, effects, 0f);
    }

    private void DrawRuntimeGeometry(Color lightColor)
    {
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        Color color = RuntimeColorPolicy.Resolve(_entity!.Light.Color, Projectile.GetAlpha(lightColor));
        Vector2 center = Projectile.Center - Main.screenPosition;
        Vector2 direction = Projectile.velocity.SafeNormalize(_initialDirection).RotatedBy(Projectile.rotation - Projectile.velocity.SafeNormalize(_initialDirection).ToRotation());
        float length = Math.Max(8f, _entity.Hitbox.WidthPx * Projectile.scale);
        float width = Math.Max(2f, _entity.Hitbox.HeightPx * Projectile.scale * 0.35f);
        Vector2 delta = direction.SafeNormalize(Vector2.UnitX) * length;
        Main.spriteBatch.Draw(pixel, center - delta * 0.5f, null, color, delta.ToRotation(), Vector2.Zero, new Vector2(delta.Length(), width), SpriteEffects.None, 0f);
    }
}
