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
    internal static bool PreservesExplicitBodyScale(RuntimeEntitySpec? entity)
        => entity?.HitboxCurve?.MirrorToSprite == true || entity?.VisualScaleCurve is not null || entity?.VisualScaleRate is not null;

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
        if (string.IsNullOrWhiteSpace(path) || !selected.RenderSizePx.HasValue || !selected.ForwardAngleDegrees.HasValue) return; // incomplete selected PNG fails closed; never infer frame metadata.
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(path);
        if (texture is null) return;
        Rectangle source = texture.Bounds;
        // An explicit mirror or visual curve owns the complete bounded product.
        // Ordinary drivers retain the native bounded scale without either curve owner.
        float scale = (PreservesExplicitBodyScale(_entity) ? Projectile.scale : Math.Clamp(Projectile.scale, 0.1f, 8f))
            * selected.FrameScale(source.Width, source.Height);
        SpriteEffects effects = Projectile.spriteDirection < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
        float rotation = MotionSpriteRotation(_entity, selected, Projectile.rotation, effects);
        Vector2 origin = MotionSpriteOrigin(_entity, selected, source.Width, source.Height, scale, effects,
            rotation, _entity.Aim is not null ? MotionAxis(Owner(), publish: false) : _initialDirection);
        Main.spriteBatch.Draw(texture, Projectile.Center - Main.screenPosition + new Vector2(0f, Projectile.gfxOffY), source, Projectile.GetAlpha(lightColor), rotation, origin, scale, effects, 0f);
    }

    private void DrawRuntimeGeometry(Color lightColor)
    {
        if (_entity!.Visual.Geometry is { } authored)
        {
            DrawExplicitBodyGeometry(authored);
            return;
        }
        // Saved items without the new field retain their original presentation.
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        Color color = RuntimeColorPolicy.Resolve(_entity!.Light.Color, Projectile.GetAlpha(lightColor));
        if (HasBeamGeometry)
        {
            GetChannelBeamGeometry(out Vector2 start, out Vector2 end, out float beamWidth);
            InfiniVfxRuntime.DrawLine(pixel, start - Main.screenPosition, end - Main.screenPosition, color, beamWidth, preserveWidth: true);
            return;
        }
        if (HasLashGeometry)
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
        Vector2 direction = _entity.Rotation is not null ? Projectile.rotation.ToRotationVector2()
            : _entity.Aim is not null ? MotionAxis(Owner(), publish: false)
            : _entity.Movement.Code is 14 or 16 or 17
            ? Projectile.rotation.ToRotationVector2()
            : _entity.Movement.Code == 20 ? (Projectile.rotation - MathHelper.PiOver2).ToRotationVector2()
            : Projectile.velocity.SafeNormalize(_initialDirection);
        bool exactScale = PreservesExplicitBodyScale(_entity);
        float length = exactScale ? _entity.Hitbox.WidthPx * Projectile.scale : Math.Max(8f, _entity.Hitbox.WidthPx * Projectile.scale);
        float width = exactScale ? _entity.Hitbox.HeightPx * Projectile.scale * 0.35f : Math.Max(2f, _entity.Hitbox.HeightPx * Projectile.scale * 0.35f);
        Vector2 delta = direction.SafeNormalize(Vector2.UnitX) * length;
        InfiniVfxRuntime.DrawLine(pixel, center - delta * 0.5f, center + delta * 0.5f, color, width, preserveWidth: exactScale);
    }
    private void DrawExplicitBodyGeometry(RuntimeBodyGeometrySpec geometry)
    {
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        Color color = geometry.ToColor();
        void Segment(Vector2 a, Vector2 b) => InfiniVfxRuntime.DrawLine(pixel,
            a - Main.screenPosition, b - Main.screenPosition, color, geometry.WidthPx, preserveWidth: true);
        if (geometry.Source == "collision_path")
        {
            if (HasBeamGeometry) {
                GetChannelBeamGeometry(out Vector2 start, out Vector2 end, out _);
                Segment(start, end);
            } else if (HasLashGeometry) {
                for (int i = 1; i < _whipPoints.Count; i++) Segment(_whipPoints[i - 1], _whipPoints[i]);
            } else throw new System.IO.InvalidDataException("Missing collision path for authored body geometry");
            return;
        }
        if (geometry.Axis == "aim" && _entity!.Aim is null)
            throw new System.IO.InvalidDataException("Body geometry aim axis requires entity aim");
        // Read-only aim: unlike MotionAxis this must never turn the owner during drawing.
        Vector2 aim = _entity!.Aim?.Source switch {
            "cursor" => new Vector2(Projectile.ai[0], Projectile.ai[1]).SafeNormalize(_initialDirection),
            "facing" => new Vector2(Owner().direction, 0f),
            "velocity" => Projectile.velocity.SafeNormalize(_motionAxis.SafeNormalize(_initialDirection)),
            _ => _initialDirection,
        };
        Vector2 axis = geometry.Axis switch {
            "rotation" => Projectile.rotation.ToRotationVector2(),
            "aim" => aim,
            "velocity" => Projectile.velocity.SafeNormalize(_initialDirection),
            _ => throw new System.IO.InvalidDataException("Invalid body geometry axis"),
        };
        Vector2 half = axis * (geometry.LengthPx!.Value * 0.5f);
        Segment(Projectile.Center - half, Projectile.Center + half);
    }

}
