#nullable enable
using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

/// <summary>Shared texture diagnostics for /infinidump and /infinidumppicture.</summary>
internal sealed class RuntimeDumpTextureMetrics
{
    public int textureWidth { get; set; }
    public int textureHeight { get; set; }
    public int frames { get; set; }
    public int frameWidth { get; set; }
    public int frameHeight { get; set; }
    // [left, top, width, height] in per-frame coordinates, unioned over non-empty frames.
    public int[] visibleBBox { get; set; } = Array.Empty<int>();
    public int visibleWidth { get; set; }
    public int visibleHeight { get; set; }
    public int visibleMajorAxis { get; set; }
    public int visibleMinorAxis { get; set; }
    public int visibleAreaPixels { get; set; }
    public int nonEmptyFrames { get; set; }
    public double occupancyX { get; set; }
    public double occupancyY { get; set; }
    public double alphaCoverageInFrame { get; set; }
    public double fillRatioInBBox { get; set; }
    public int alphaThreshold { get; set; } = 8;
    public bool unavailable { get; set; }
    public string note { get; set; } = "";

    internal static RuntimeDumpTextureMetrics? TryItem(int type)
    {
        try
        {
            if (Main.dedServ || type <= ItemID.None || type >= ItemLoader.ItemCount) return null;
            Main.instance.LoadItem(type);
            Texture2D texture = TextureAssets.Item[type].Value;
            return Capture(texture, 1);
        }
        catch (Exception e)
        {
            return new RuntimeDumpTextureMetrics { unavailable = true, note = e.GetType().Name };
        }
    }

    internal static RuntimeDumpTextureMetrics? TryProjectile(int type)
    {
        try
        {
            if (Main.dedServ || type <= ProjectileID.None || type >= ProjectileLoader.ProjectileCount) return null;
            Main.instance.LoadProjectile(type);
            Texture2D texture = TextureAssets.Projectile[type].Value;
            return Capture(texture, ProjectileFrames(type));
        }
        catch (Exception e)
        {
            return new RuntimeDumpTextureMetrics { unavailable = true, note = e.GetType().Name };
        }
    }

    internal static RuntimeDumpTextureMetrics Capture(Texture2D texture, int frameCount)
    {
        const int alphaThreshold = 8;
        var m = new RuntimeDumpTextureMetrics { unavailable = true, note = "empty_texture", alphaThreshold = alphaThreshold };
        if (texture is null || texture.Width <= 0 || texture.Height <= 0)
            return m;

        int textureWidth = texture.Width;
        int textureHeight = texture.Height;
        int frames = Math.Clamp(frameCount <= 0 ? 1 : frameCount, 1, Math.Max(1, textureHeight));
        int frameWidth = textureWidth;
        int frameHeight = Math.Max(1, textureHeight / frames);
        m.textureWidth = textureWidth;
        m.textureHeight = textureHeight;
        m.frames = frames;
        m.frameWidth = frameWidth;
        m.frameHeight = frameHeight;
        m.visibleBBox = new[] { 0, 0, 0, 0 };
        m.unavailable = false;
        m.note = "";

        // Keep /infinidump cheap and safe for unusual huge modded textures.
        if ((long)textureWidth * textureHeight > 1_048_576L)
        {
            m.unavailable = true;
            m.note = "texture_too_large_for_metrics";
            return m;
        }

        var pixels = new Color[textureWidth * textureHeight];
        texture.GetData(pixels);

        int minX = frameWidth, minY = frameHeight, maxX = -1, maxY = -1;
        int visible = 0;
        int nonEmptyFrames = 0;

        for (int f = 0; f < frames; f++)
        {
            int top = f * frameHeight;
            if (top >= textureHeight) break;
            int thisFrameVisible = 0;
            int yLimit = Math.Min(frameHeight, textureHeight - top);
            for (int y = 0; y < yLimit; y++)
            {
                int row = (top + y) * textureWidth;
                for (int x = 0; x < frameWidth; x++)
                {
                    if (pixels[row + x].A <= alphaThreshold) continue;
                    thisFrameVisible++;
                    if (x < minX) minX = x;
                    if (y < minY) minY = y;
                    if (x > maxX) maxX = x;
                    if (y > maxY) maxY = y;
                }
            }
            if (thisFrameVisible > 0)
            {
                nonEmptyFrames++;
                visible += thisFrameVisible;
            }
        }

        m.visibleAreaPixels = visible;
        m.nonEmptyFrames = nonEmptyFrames;
        if (visible <= 0 || maxX < minX || maxY < minY)
        {
            m.visibleBBox = new[] { 0, 0, 0, 0 };
            return m;
        }

        int visibleWidth = maxX - minX + 1;
        int visibleHeight = maxY - minY + 1;
        int bboxArea = Math.Max(1, visibleWidth * visibleHeight);
        int frameArea = Math.Max(1, frameWidth * frameHeight);
        int coverageDenom = Math.Max(1, frameArea * Math.Max(1, nonEmptyFrames));
        int fillDenom = Math.Max(1, bboxArea * Math.Max(1, nonEmptyFrames));

        m.visibleBBox = new[] { minX, minY, visibleWidth, visibleHeight };
        m.visibleWidth = visibleWidth;
        m.visibleHeight = visibleHeight;
        m.visibleMajorAxis = Math.Max(visibleWidth, visibleHeight);
        m.visibleMinorAxis = Math.Min(visibleWidth, visibleHeight);
        m.occupancyX = Math.Round(visibleWidth / (double)Math.Max(1, frameWidth), 4);
        m.occupancyY = Math.Round(visibleHeight / (double)Math.Max(1, frameHeight), 4);
        m.alphaCoverageInFrame = Math.Round(visible / (double)coverageDenom, 4);
        m.fillRatioInBBox = Math.Round(visible / (double)fillDenom, 4);
        return m;
    }

    internal static int ProjectileFrames(int projectileType)
    {
        try
        {
            if (projectileType >= ProjectileID.None && projectileType < Main.projFrames.Length)
                return Main.projFrames[projectileType];
        }
        catch { }
        return 0;
    }
}
