#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent.Drawing;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

[Autoload(Side = ModSide.Client)]
public sealed class GeneratedPlacedBodyDrawSystem : ModSystem
{
    public override void PostDrawTiles()
    {
        if (Main.dedServ || Main.gameMenu || Main.netMode == NetmodeID.Server || !GeneratedPlacedBodyNativeAdapter.FeatureAvailable) return;
        var cache = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites;
        if (cache is null) return;
        bool began = false;
        try
        {
            foreach (GeneratedPlacedBodyView view in GeneratedPlacementLedgerSystem.VisiblePlacedBodies())
            {
                if (view.Body is null) continue;
                int x = view.Footprint.X / 16, y = view.Footprint.Y / 16;
                Tile tile = Main.tile[x,y];
                if (!TileDrawing.IsVisible(tile)) continue;
                Texture2D? texture = cache.TryGet(view.Data.Visual.SpritePath, out _, out Rectangle? alphaBounds);
                if (texture is null) continue; // Selected missing image is pending, never native fallback.
                if (!IntersectsViewport(texture,view.Body,view.Footprint,Main.screenPosition,Main.screenWidth,Main.screenHeight,alphaBounds)) continue;
                if (!began)
                {
                    // Installed Main.DoDraw ends its batch before SystemLoader.PostDrawTiles.
                    Main.spriteBatch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,
                        Main.DefaultSamplerState,DepthStencilState.None,Main.Rasterizer,null,Main.Transform);
                    began = true;
                }
                Color color = tile.IsTileFullbright ? Color.White : Lighting.GetColor(x,y);
                if (tile.IsActuated) color *= .4f;
                DrawBody(Main.spriteBatch,texture,view.Body,view.Footprint,Main.screenPosition,color,alphaBounds);
            }
        }
        finally { if (began) Main.spriteBatch.End(); }
    }

    private static bool TryResolvePivot(Texture2D texture, RuntimePlacedBodySpec body, Rectangle? alphaBounds,
        out double pivotX, out double pivotY)
    {
        pivotX = pivotY = 0;
        Rectangle basis;
        switch (body.PivotSpace)
        {
            case null:
            case "frame":
                basis = texture.Bounds;
                break;
            case "alpha_bounds":
                if (alphaBounds is not Rectangle bounds || bounds.Width <= 0 || bounds.Height <= 0
                    || bounds.X < 0 || bounds.Y < 0 || bounds.Right > texture.Width || bounds.Bottom > texture.Height)
                    return false;
                basis = bounds;
                break;
            default:
                return false;
        }
        // Pixel edges, not centers. The source frame/size is never cropped.
        pivotX = basis.X + basis.Width * body.ImagePivotX;
        pivotY = basis.Y + basis.Height * body.ImagePivotY;
        return true;
    }

    private static bool DrawBody(SpriteBatch batch, Texture2D texture, RuntimePlacedBodySpec body,
        Rectangle footprint, Vector2 camera, Color color, Rectangle? alphaBounds)
    {
        if (!TryResolvePivot(texture,body,alphaBounds,out double pivotX,out double pivotY)) return false;
        float scale = body.RenderSizePx / (float)Math.Max(texture.Width,texture.Height);
        Vector2 position = new((float)(footprint.X + footprint.Width * body.FootprintAnchorX + body.OffsetXPx),
            (float)(footprint.Y + footprint.Height * body.FootprintAnchorY + body.OffsetYPx));
        Vector2 pivot = new((float)pivotX,(float)pivotY);
        // SpriteEffects reflects UVs around the full frame; adjust its geometric
        // origin so the explicitly selected image pivot remains the reflection center.
        if (body.FlipX) pivot.X = texture.Width - pivot.X;
        if (body.FlipY) pivot.Y = texture.Height - pivot.Y;
        SpriteEffects flip = (body.FlipX ? SpriteEffects.FlipHorizontally : SpriteEffects.None)
            | (body.FlipY ? SpriteEffects.FlipVertically : SpriteEffects.None);
        batch.Draw(texture,position-camera,texture.Bounds,color,(float)(body.RotationDegrees * Math.PI / 180d),
            pivot,scale,flip,0f);
        return true;
    }

    private static bool IntersectsViewport(Texture2D texture, RuntimePlacedBodySpec body,
        Rectangle footprint, Vector2 camera, int width, int height, Rectangle? alphaBounds)
    {
        if (!TryResolvePivot(texture,body,alphaBounds,out double pivotX,out double pivotY)) return false;
        double size = body.RenderSizePx / (double)Math.Max(texture.Width,texture.Height);
        double px = footprint.X + footprint.Width * body.FootprintAnchorX + body.OffsetXPx - camera.X;
        double py = footprint.Y + footprint.Height * body.FootprintAnchorY + body.OffsetYPx - camera.Y;
        double radians = body.RotationDegrees * Math.PI / 180d, cosine = Math.Cos(radians), sine = Math.Sin(radians);
        double minX=double.PositiveInfinity,minY=double.PositiveInfinity,maxX=double.NegativeInfinity,maxY=double.NegativeInfinity;
        foreach ((double x,double y) in new[] { (0d,0d),((double)texture.Width,0d),((double)texture.Width,(double)texture.Height),(0d,(double)texture.Height) })
        {
            double localX = (x-pivotX)*size*(body.FlipX ? -1 : 1);
            double localY = (y-pivotY)*size*(body.FlipY ? -1 : 1);
            double worldX = px+localX*cosine-localY*sine, worldY = py+localX*sine+localY*cosine;
            minX=Math.Min(minX,worldX);maxX=Math.Max(maxX,worldX);minY=Math.Min(minY,worldY);maxY=Math.Max(maxY,worldY);
        }
        return maxX>=0 && maxY>=0 && minX<=width && minY<=height;
    }
}
