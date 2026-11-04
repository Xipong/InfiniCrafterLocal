#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed partial class InfiniDumpCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinidump";
    public override string Description => "Dump loaded Terraria/tModLoader item and projectile runtime snapshots for InfiniCrafter analysis.";

    public override string Usage => "/infinidump [textures|status|cancel]";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        string option = args.Length == 0 ? "" : args[0].ToLowerInvariant();
        if (args.Length > 1 || option is not ("" or "textures" or "status" or "cancel"))
        { caller.Reply(Usage); return; }
        if (option == "cancel") { CancelExport(notify: true); return; }
        if (activeExport is not null)
        { caller.Reply("InfiniCraft dump: " + activeExport.Progress + ". /infinidump cancel to stop."); return; }
        if (option == "status") { caller.Reply("InfiniCraft: no dump is running."); return; }

        bool textures = option == "textures";
        string dir = Path.Combine(Main.SavePath, "InfiniCrafterLocal");
        // Capture identity metadata now, but hash files only on the writer thread.
        JsonObject environment = CaptureDumpEnvironmentCore(includeFileHash: false);
        activeExport = new RuntimeDumpExport(dir, ItemLoader.ItemCount, ProjectileLoader.ProjectileCount,
            type =>
            {
                Item item = new();
                item.SetDefaults(type);
                return item.IsAir || string.IsNullOrWhiteSpace(item.Name) ? null : CaptureItemSnapshotForExport(item, textures);
            }, type => CaptureProjectileSnapshotForExport(type, textures), environment);
        nextProgressAt = DateTime.UtcNow.AddSeconds(5);
        caller.Reply("InfiniCraft dump started in small steps. /infinidump status or /infinidump cancel."
            + (textures ? " Texture diagnostics enabled; individual GPU reads may pause a frame." : " Texture diagnostics skipped; use /infinidump textures to include them."));
    }

    internal static void WriteSnapshot(TextWriter writer, int type, Func<JsonObject?> capture, JsonSerializerOptions options)
    {
        JsonObject? snapshot;
        try { snapshot = capture(); }
        catch (Exception error)
        {
            // Absence of a row must not masquerade as absence of mechanics.
            // I/O errors remain terminal; only definition capture is isolated.
            snapshot = new JsonObject { ["type"] = type, ["unavailable"] = true, ["captureError"] = error.GetType().Name };
        }
        if (snapshot is not null) writer.WriteLine(snapshot.ToJsonString(options));
    }

    // Dump rows are the same complete source observations used by live crafting.
    // Only dump-specific identity aliases, flags and graphics metrics are added here.
    internal static JsonObject CaptureItemSnapshot(Item item) => CaptureItemSnapshotForExport(item, true);

    private static JsonObject CaptureItemSnapshotForExport(Item item, bool textures)
    {
        JsonObject snapshot = GeneratorClient.ToWireItem(item);
        snapshot["type"] = item.type;
        snapshot["questItem"] = item.questItem;
        snapshot["expert"] = item.expert;
        snapshot["master"] = item.master;
        snapshot["textureMetrics"] = JsonSerializer.SerializeToNode(textures ? TryItemTextureMetrics(item.type) : SkippedTextureMetrics());
        if (snapshot["directProjectileRaw"] is JsonObject projectile)
            projectile["textureMetrics"] = JsonSerializer.SerializeToNode(textures ? TryProjectileTextureMetrics(item.shoot) : SkippedTextureMetrics());
        return snapshot;
    }

    internal static JsonObject CaptureProjectileSnapshot(int type) => CaptureProjectileSnapshotForExport(type, true);

    private static JsonObject CaptureProjectileSnapshotForExport(int type, bool textures)
    {
        object? facts = GeneratorClient.ProjectileRawSnapshot(type, 0f, "runtime_dump", null, -1);
        JsonObject snapshot = JsonSerializer.SerializeToNode(facts) as JsonObject
            ?? throw new InvalidOperationException("Projectile capture was unavailable");
        snapshot["textureMetrics"] = JsonSerializer.SerializeToNode(textures ? TryProjectileTextureMetrics(type) : SkippedTextureMetrics());
        return snapshot;
    }

    private static TextureMetrics SkippedTextureMetrics() => new() { unavailable = true, note = "not_requested; use /infinidump textures" };

    private sealed class TextureMetrics
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
    }

    private static object? TryItemTextureMetrics(int type)
    {
        try
        {
            if (Main.dedServ || type <= ItemID.None || type >= ItemLoader.ItemCount) return null;
            Main.instance.LoadItem(type);
            Texture2D texture = TextureAssets.Item[type].Value;
            return TextureMetricsForTexture(texture, 1);
        }
        catch (Exception e)
        {
            return new TextureMetrics { unavailable = true, note = e.GetType().Name };
        }
    }

    private static object? TryProjectileTextureMetrics(int type)
    {
        try
        {
            if (Main.dedServ || type <= ProjectileID.None || type >= ProjectileLoader.ProjectileCount) return null;
            Main.instance.LoadProjectile(type);
            Texture2D texture = TextureAssets.Projectile[type].Value;
            return TextureMetricsForTexture(texture, SafeProjFrames(type));
        }
        catch (Exception e)
        {
            return new TextureMetrics { unavailable = true, note = e.GetType().Name };
        }
    }

    private static TextureMetrics TextureMetricsForTexture(Texture2D texture, int frameCount)
    {
        const int alphaThreshold = 8;
        var m = new TextureMetrics { unavailable = true, note = "empty_texture", alphaThreshold = alphaThreshold };
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

    private static int SafeProjFrames(int projectileType)
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
