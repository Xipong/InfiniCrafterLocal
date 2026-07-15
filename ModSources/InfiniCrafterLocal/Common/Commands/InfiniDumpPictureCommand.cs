#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

/// <summary>
/// Graphical dump for generated and reference sprites/assets.
///
/// /infinidump is for numeric/spec JSON. /infinidumppicture is for visual calibration.
/// Generated mode copies generated PNGs. Source/ref mode exports real loaded vanilla/modded
/// TextureAssets.Item/Projectile textures to PNG for calibration against Terraria art.
/// </summary>
public sealed class InfiniDumpPictureCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinidumppicture";
    public override string Usage => "/infinidumppicture [all|latest|id-or-name-filter] | /infinidumppicture source [held|active|baseline|item <id/name>|projectile <id/name>]";
    public override string Description => "Dump generated PNGs or original vanilla/modded textures into an HTML picture gallery for visual calibration. Source item dumps also bundle linked projectile textures.";

    private sealed class DumpAsset
    {
        public string Role { get; set; } = "";
        public string OriginalPath { get; set; } = "";
        public string LocalPath { get; set; } = "";
        public string DumpFile { get; set; } = "";
        public bool Exists { get; set; }
        public long Bytes { get; set; }
        public string Status { get; set; } = "";
        public int Canvas { get; set; }
        public float Score { get; set; }
        public string Prompt { get; set; } = "";
    }

    private sealed class DumpEntry
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string Category { get; set; } = "";
        public string ParentA { get; set; } = "";
        public string ParentB { get; set; } = "";
        public int PreferredCanvasSize { get; set; }
        public int ProjectileWidth { get; set; }
        public int ProjectileHeight { get; set; }
        public float ProjectileScale { get; set; }
        public string Delivery { get; set; } = "";
        public string Movement { get; set; } = "";
        public string VisualMode { get; set; } = "";
        public List<DumpAsset> Assets { get; set; } = new();
    }

    private sealed class TextureMetrics
    {
        public int textureWidth { get; set; }
        public int textureHeight { get; set; }
        public int frames { get; set; }
        public int frameWidth { get; set; }
        public int frameHeight { get; set; }
        public int[] visibleBBox { get; set; } = Array.Empty<int>(); // [left, top, width, height]
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

    private sealed class SourceTextureDump
    {
        public string Kind { get; set; } = "";
        public int Type { get; set; }
        public string DisplayName { get; set; } = "";
        public string FullName { get; set; } = "";
        public string SourceMod { get; set; } = "";
        public string DumpFile { get; set; } = "";
        public int Width { get; set; }
        public int Height { get; set; }
        public long Bytes { get; set; }
        public TextureMetrics? TextureMetrics { get; set; }
        public string Notes { get; set; } = "";
    }

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        if (Main.dedServ)
        {
            Main.NewText("InfiniDumpPicture: server has no local GPU textures to export.", 255, 180, 120);
            return;
        }

        if (args.Length > 0 && IsSourceMode(args[0]))
        {
            RunSourceTextureDump(args.Skip(1).ToArray());
            return;
        }

        string mode = args.Length > 0 ? string.Join(" ", args).Trim() : "latest";
        string filter = mode.Equals("all", StringComparison.OrdinalIgnoreCase) || mode.Equals("latest", StringComparison.OrdinalIgnoreCase)
            ? ""
            : mode;

        string root = Path.Combine(Main.SavePath, "InfiniCrafterLocal", "picture_dumps", DateTime.Now.ToString("yyyyMMdd_HHmmss"));
        string assetDir = Path.Combine(root, "assets");
        string jsonDir = Path.Combine(root, "json");
        Directory.CreateDirectory(assetDir);
        Directory.CreateDirectory(jsonDir);

        GeneratedItemData[] all = InfiniCrafterLocalMod.GeneratedItems?.Snapshot() ?? Array.Empty<GeneratedItemData>();
        IEnumerable<GeneratedItemData> selected = all;

        if (!string.IsNullOrWhiteSpace(filter))
        {
            selected = selected.Where(d =>
                Contains(d.Id, filter) ||
                Contains(d.Name, filter) ||
                Contains(d.ParentA, filter) ||
                Contains(d.ParentB, filter) ||
                Contains(d.RecipeKey, filter));
        }
        else if (mode.Equals("latest", StringComparison.OrdinalIgnoreCase))
        {
            selected = all
                .OrderByDescending(d => BestMTimeUtc(d))
                .Take(12);
        }

        var entries = new List<DumpEntry>();
        var copied = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        foreach (var data in selected)
        {
            if (data is null) continue;
            data.Normalize();

            string safeId = SafeFileNamePart(string.IsNullOrWhiteSpace(data.Id) ? data.Name : data.Id);
            if (string.IsNullOrWhiteSpace(safeId)) safeId = "generated_" + entries.Count.ToString("000");

            try
            {
                File.WriteAllText(Path.Combine(jsonDir, safeId + ".full.json"), data.ToJson());
                File.WriteAllText(Path.Combine(jsonDir, safeId + ".network.json"), data.ToNetworkJson());
            }
            catch { }

            var entry = new DumpEntry
            {
                Id = data.Id ?? "",
                Name = data.Name ?? "",
                Category = data.Category ?? "",
                ParentA = data.ParentA ?? "",
                ParentB = data.ParentB ?? "",
                PreferredCanvasSize = data.Visual?.PreferredCanvasSize ?? 0,
                ProjectileWidth = data.Attack?.ProjectileWidth ?? 0,
                ProjectileHeight = data.Attack?.ProjectileHeight ?? 0,
                ProjectileScale = data.Attack?.ProjectileScale ?? 0f,
                Delivery = data.Attack?.Delivery ?? "",
                Movement = data.Attack?.Movement ?? "",
                VisualMode = data.Attack?.VisualMode ?? "",
            };

            AddAsset(entry, copied, assetDir, safeId, "item_final", data.Visual?.SpritePath, data.Visual?.SpriteStatus, data.Visual?.PreferredCanvasSize ?? 0, data.Visual?.SpriteTechnicalScore ?? 0f, data.Visual?.ImagePrompt);
            AddAsset(entry, copied, assetDir, safeId, "item_raw", data.Visual?.SpriteRawPath, "raw", data.Visual?.PreferredCanvasSize ?? 0, 0f, data.Visual?.ImagePrompt);
            AddAsset(entry, copied, assetDir, safeId, "projectile", data.Attack?.ProjectileSpritePath, data.Attack?.ProjectileSpriteStatus, EffectiveProjectileCanvas(data), data.Attack?.ProjectileSpriteScore ?? 0f, data.Attack?.ProjectileSpritePrompt);
            AddAsset(entry, copied, assetDir, safeId, "impact", data.Attack?.ImpactSpritePath, data.Attack?.ImpactSpriteStatus, 0, data.Attack?.ImpactSpriteScore ?? 0f, data.Attack?.ImpactSpritePrompt);
            AddAsset(entry, copied, assetDir, safeId, "child", data.Attack?.ChildSpritePath, data.Attack?.ChildSpriteStatus, 0, data.Attack?.ChildSpriteScore ?? 0f, data.Attack?.ChildSpritePrompt);
            AddAsset(entry, copied, assetDir, safeId, "field", data.Attack?.FieldSpritePath, data.Attack?.FieldSpriteStatus, 0, data.Attack?.FieldSpriteScore ?? 0f, data.Attack?.FieldSpritePrompt);
            AddAsset(entry, copied, assetDir, safeId, "visual_manifest", data.Visual?.AssetManifestPath, "manifest", 0, 0f, "");

            if (entry.Assets.Count > 0)
                entries.Add(entry);
        }

        var activeGeneratedProjectiles = ActiveGeneratedProjectileSnapshots().ToArray();

        var options = new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        };
        File.WriteAllText(Path.Combine(root, "picture_dump_manifest.json"), JsonSerializer.Serialize(new
        {
            schema = "infini.pictureDump.v1",
            createdAt = DateTimeOffset.Now,
            mode,
            filter,
            root,
            count = entries.Count,
            activeGeneratedProjectiles,
            entries
        }, options));

        File.WriteAllText(Path.Combine(root, "index.html"), BuildHtml(entries, activeGeneratedProjectiles, mode));
        File.WriteAllText(Path.Combine(root, "README.txt"),
            "Open index.html in a browser. Zip this folder and upload it to ChatGPT for visual calibration.\n" +
            "Cards show PNGs on checker/dark/light backgrounds. JSON contains paths, prompts and projectile sizing.\n");

        Main.NewText($"InfiniDumpPicture written: {root}", 120, 220, 255);
        Main.NewText($"Open index.html or zip the whole folder for calibration.", 120, 220, 255);
    }

    private static bool IsSourceMode(string value)
    {
        value = (value ?? "").Trim().ToLowerInvariant();
        return value is "source" or "src" or "ref" or "reference" or "original" or "vanilla" or "mod" or "modded";
    }

    private static string EnsureItemBundleDir(string assetDir, int itemType, string displayName)
    {
        string folder = SafeFileNamePart($"item_{itemType}_{displayName}");
        if (string.IsNullOrWhiteSpace(folder)) folder = $"item_{itemType}";
        string path = Path.Combine(assetDir, folder);
        Directory.CreateDirectory(path);
        return path;
    }

    private static void TryDumpItemBundle(int type, string assetDir, string tag, List<SourceTextureDump> dumps, List<string> errors)
    {
        try
        {
            if (type <= ItemID.None || type >= ItemLoader.ItemCount) return;
            var it = new Item();
            it.SetDefaults(type);
            string display = Lang.GetItemNameValue(type) ?? it.Name ?? ($"Item {type}");
            string bundleDir = EnsureItemBundleDir(assetDir, type, display);

            TryDumpItemTexture(type, bundleDir, tag + "_self", dumps, errors);

            if (it.shoot > ProjectileID.None)
                TryDumpProjectileTexture(it.shoot, bundleDir, tag + "_shoot", dumps, errors);

            // If an ammo item or thrown item maps to a distinct projectile via shoot, the branch above already covers it.
            // We also save a tiny metadata file per bundle so calibration has gameplay context next to the PNGs.
            try
            {
                var meta = new
                {
                    type,
                    displayName = display,
                    itemName = it.Name,
                    sourceMod = it.ModItem?.Mod?.Name ?? "Terraria",
                    fullName = it.ModItem is not null ? (it.ModItem.Mod.Name + "/" + it.ModItem.Name) : ($"Terraria/Item_{type}"),
                    itemTextureMetrics = TryItemTextureMetrics(type),
                    projectileTextureMetrics = it.shoot > ProjectileID.None ? TryProjectileTextureMetrics(it.shoot) : null,
                    width = it.width,
                    height = it.height,
                    damage = it.damage,
                    damageClass = it.DamageType?.ToString(),
                    useStyle = it.useStyle,
                    useTime = it.useTime,
                    useAnimation = it.useAnimation,
                    shoot = it.shoot,
                    shootSpeed = it.shootSpeed,
                    noUseGraphic = it.noUseGraphic,
                    noMelee = it.noMelee,
                    channel = it.channel,
                    ammo = it.ammo,
                    useAmmo = it.useAmmo,
                };
                string metaPath = Path.Combine(bundleDir, "bundle_meta.json");
                File.WriteAllText(metaPath, JsonSerializer.Serialize(meta, new JsonSerializerOptions { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
            }
            catch (Exception e)
            {
                errors.Add($"bundle meta {type}: {e.GetType().Name}: {e.Message}");
            }
        }
        catch (Exception e)
        {
            errors.Add($"item bundle {type}: {e.GetType().Name}: {e.Message}");
        }
    }

    private static void RunSourceTextureDump(string[] args)
    {
        string mode = args.Length > 0 ? args[0].Trim().ToLowerInvariant() : "held";
        string query = args.Length > 1 ? string.Join(" ", args.Skip(1)).Trim() : "";

        string root = Path.Combine(Main.SavePath, "InfiniCrafterLocal", "picture_dumps", "source_" + DateTime.Now.ToString("yyyyMMdd_HHmmss"));
        string assetDir = Path.Combine(root, "assets");
        Directory.CreateDirectory(assetDir);

        var dumps = new List<SourceTextureDump>();
        var errors = new List<string>();

        void DumpHeld()
        {
            Item held = Main.LocalPlayer?.HeldItem ?? new Item();
            if (held.IsAir || held.type <= ItemID.None)
            {
                errors.Add("Held item is empty.");
                return;
            }
            TryDumpItemBundle(held.type, assetDir, "held", dumps, errors);
        }

        if (mode is "held" or "current" or "selected")
        {
            DumpHeld();
        }
        else if (mode is "active" or "nearby" or "projectiles")
        {
            var seen = new HashSet<int>();
            for (int i = 0; i < Main.maxProjectiles; i++)
            {
                Projectile p = Main.projectile[i];
                if (p is null || !p.active || p.type <= ProjectileID.None || !seen.Add(p.type)) continue;
                TryDumpProjectileTexture(p.type, assetDir, "active_projectile", dumps, errors);
            }
            DumpHeld();
        }
        else if (mode is "baseline" or "vanilla-baseline" or "starter")
        {
            int[] starterItems = new int[]
            {
                ItemID.CopperShortsword,
                ItemID.WoodenSword,
                ItemID.CopperBroadsword,
                ItemID.WoodenBow,
                ItemID.WoodenBoomerang,
                ItemID.Shuriken,
                ItemID.ThrowingKnife,
            };
            foreach (int type in starterItems)
                TryDumpItemBundle(type, assetDir, "baseline", dumps, errors);
        }
        else if (mode is "item" or "i")
        {
            foreach (int type in ResolveItemTypes(query))
                TryDumpItemBundle(type, assetDir, "item", dumps, errors);
        }
        else if (mode is "projectile" or "proj" or "p")
        {
            foreach (int type in ResolveProjectileTypes(query))
                TryDumpProjectileTexture(type, assetDir, "projectile", dumps, errors);
        }
        else
        {
            // Friendly shorthand: /infinidumppicture source Copper Shortsword
            foreach (int type in ResolveItemTypes(string.Join(" ", args).Trim()))
                TryDumpItemBundle(type, assetDir, "item", dumps, errors);
        }

        var options = new JsonSerializerOptions { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
        File.WriteAllText(Path.Combine(root, "source_texture_manifest.json"), JsonSerializer.Serialize(new
        {
            schema = "infini.sourceTextureDump.v1",
            createdAt = DateTimeOffset.Now,
            mode,
            query,
            count = dumps.Count,
            errors,
            textures = dumps
        }, options));
        File.WriteAllText(Path.Combine(root, "index.html"), BuildSourceHtml(dumps, errors, mode, query));
        File.WriteAllText(Path.Combine(root, "README.txt"),
            "This is a SOURCE texture dump: vanilla/modded TextureAssets.Item and TextureAssets.Projectile saved as PNG by tModLoader.\n" +
            "Use it for calibration against Terraria/mod art. Generated AI sprites are not the target of this mode.\n");

        Main.NewText($"InfiniDumpPicture source textures: {root}", 120, 220, 255);
        Main.NewText($"Dumped {dumps.Count} texture(s). Open index.html.", 120, 220, 255);
        if (errors.Count > 0) Main.NewText($"Warnings: {errors.Count}; see source_texture_manifest.json", 255, 190, 120);
    }

    private static IEnumerable<int> ResolveItemTypes(string query)
    {
        query = (query ?? "").Trim();
        if (string.IsNullOrWhiteSpace(query)) yield break;
        if (int.TryParse(query, out int id) && id > ItemID.None && id < ItemLoader.ItemCount)
        {
            yield return id;
            yield break;
        }
        string norm = NormKey(query);
        var hits = new List<int>();
        for (int type = InfiniTerrariaSentinels.FirstValidItemType; type < ItemLoader.ItemCount; type++)
        {
            try
            {
                var it = new Item();
                it.SetDefaults(type);
                if (it.type <= ItemID.None || it.IsAir) continue;
                string display = Lang.GetItemNameValue(type) ?? it.Name ?? "";
                string internalName = it.ModItem?.Name ?? "";
                string fullName = it.ModItem is not null ? it.ModItem.Mod.Name + "/" + it.ModItem.Name : internalName;
                if (NormKey(display) == norm || NormKey(internalName) == norm || NormKey(fullName) == norm)
                    hits.Add(type);
            }
            catch { }
        }
        foreach (int hit in hits.Take(24)) yield return hit;
    }

    private static IEnumerable<int> ResolveProjectileTypes(string query)
    {
        query = (query ?? "").Trim();
        if (string.IsNullOrWhiteSpace(query)) yield break;
        if (int.TryParse(query, out int id) && id > ProjectileID.None && id < ProjectileLoader.ProjectileCount)
        {
            yield return id;
            yield break;
        }
        string norm = NormKey(query);
        var hits = new List<int>();
        for (int type = InfiniTerrariaSentinels.FirstValidProjectileType; type < ProjectileLoader.ProjectileCount; type++)
        {
            try
            {
                string display = Lang.GetProjectileName(type).Value ?? "";
                string internalName = "";
                string fullName = "";
                ModProjectile? mp = ProjectileLoader.GetProjectile(type);
                if (mp is not null)
                {
                    internalName = mp.Name;
                    fullName = mp.Mod.Name + "/" + mp.Name;
                }
                if (NormKey(display) == norm || NormKey(internalName) == norm || NormKey(fullName) == norm)
                    hits.Add(type);
            }
            catch { }
        }
        foreach (int hit in hits.Take(24)) yield return hit;
    }

    private static string NormKey(string value)
    {
        var sb = new StringBuilder();
        foreach (char c in (value ?? "").Trim().ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(c)) sb.Append(c);
            else if (c == '/' || c == '_' || c == '-' || char.IsWhiteSpace(c)) sb.Append('/');
        }
        return sb.ToString().Replace("//", "/").Trim('/');
    }

    private static void TryDumpItemTexture(int type, string assetDir, string tag, List<SourceTextureDump> dumps, List<string> errors)
    {
        try
        {
            if (type <= ItemID.None || type >= ItemLoader.ItemCount) return;
            Main.instance.LoadItem(type);
            Texture2D texture = TextureAssets.Item[type].Value;
            var it = new Item();
            it.SetDefaults(type);
            string display = Lang.GetItemNameValue(type) ?? it.Name ?? ("Item " + type);
            string sourceMod = it.ModItem?.Mod.Name ?? "Terraria";
            string fullName = it.ModItem is not null ? it.ModItem.Mod.Name + "/" + it.ModItem.Name : "Terraria/Item_" + type;
            string file = SafeFileNamePart($"{tag}_item_{type}_{display}") + ".png";
            if (tag.Contains("_self")) file = "item.png";
            string path = Path.Combine(assetDir, file);
            SaveTexturePng(texture, path);
            TextureMetrics metrics = TextureMetricsForTexture(texture, 1);
            dumps.Add(new SourceTextureDump
            {
                Kind = "item",
                Type = type,
                DisplayName = display,
                FullName = fullName,
                SourceMod = sourceMod,
                DumpFile = DumpRelPath(assetDir, file),
                Width = texture.Width,
                Height = texture.Height,
                Bytes = new FileInfo(path).Length,
                TextureMetrics = metrics,
                Notes = $"damage={it.damage}; useStyle={it.useStyle}; useTime={it.useTime}; shoot={it.shoot}; shootSpeed={it.shootSpeed:0.###}"
            });
        }
        catch (Exception e)
        {
            errors.Add($"item {type}: {e.GetType().Name}: {e.Message}");
        }
    }

    private static void TryDumpProjectileTexture(int type, string assetDir, string tag, List<SourceTextureDump> dumps, List<string> errors)
    {
        try
        {
            if (type <= ProjectileID.None || type >= ProjectileLoader.ProjectileCount) return;
            Main.instance.LoadProjectile(type);
            Texture2D texture = TextureAssets.Projectile[type].Value;
            string display = Lang.GetProjectileName(type).Value ?? ("Projectile " + type);
            ModProjectile? mp = ProjectileLoader.GetProjectile(type);
            string sourceMod = mp?.Mod.Name ?? "Terraria";
            string fullName = mp is not null ? mp.Mod.Name + "/" + mp.Name : "Terraria/Projectile_" + type;
            string file = SafeFileNamePart($"{tag}_projectile_{type}_{display}") + ".png";
            if (tag.Contains("_shoot")) file = "projectile_shoot.png";
            string path = Path.Combine(assetDir, file);
            SaveTexturePng(texture, path);
            TextureMetrics metrics = TextureMetricsForTexture(texture, SafeProjFrames(type));
            dumps.Add(new SourceTextureDump
            {
                Kind = "projectile",
                Type = type,
                DisplayName = display,
                FullName = fullName,
                SourceMod = sourceMod,
                DumpFile = DumpRelPath(assetDir, file),
                Width = texture.Width,
                Height = texture.Height,
                Bytes = new FileInfo(path).Length,
                TextureMetrics = metrics,
                Notes = "TextureAssets.Projectile export"
            });
        }
        catch (Exception e)
        {
            errors.Add($"projectile {type}: {e.GetType().Name}: {e.Message}");
        }
    }

    private static TextureMetrics? TryItemTextureMetrics(int type)
    {
        try
        {
            if (Main.dedServ || type <= ItemID.None || type >= ItemLoader.ItemCount) return null;
            Main.instance.LoadItem(type);
            return TextureMetricsForTexture(TextureAssets.Item[type].Value, 1);
        }
        catch (Exception e)
        {
            return new TextureMetrics { unavailable = true, note = e.GetType().Name };
        }
    }

    private static TextureMetrics? TryProjectileTextureMetrics(int type)
    {
        try
        {
            if (Main.dedServ || type <= ProjectileID.None || type >= ProjectileLoader.ProjectileCount) return null;
            Main.instance.LoadProjectile(type);
            return TextureMetricsForTexture(TextureAssets.Projectile[type].Value, SafeProjFrames(type));
        }
        catch (Exception e)
        {
            return new TextureMetrics { unavailable = true, note = e.GetType().Name };
        }
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

    private static string DumpRelPath(string outputDir, string file)
    {
        try
        {
            string dirName = Path.GetFileName(outputDir.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            string? parent = Path.GetFileName(Path.GetDirectoryName(outputDir));
            return parent == "assets" ? ("assets/" + dirName + "/" + file).Replace('\\', '/') : ("assets/" + file).Replace('\\', '/');
        }
        catch { return ("assets/" + file).Replace('\\', '/'); }
    }

    private static void SaveTexturePng(Texture2D texture, string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ".");
        using var fs = File.Create(path);
        texture.SaveAsPng(fs, texture.Width, texture.Height);
    }

    private static string BuildSourceHtml(List<SourceTextureDump> dumps, List<string> errors, string mode, string query)
    {
        var sb = new StringBuilder();
        sb.AppendLine("<!doctype html><html><head><meta charset=\"utf-8\">");
        sb.AppendLine("<title>InfiniCrafter source texture dump</title>");
        sb.AppendLine("<style>");
        sb.AppendLine("body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#14191b;color:#e8edf0;margin:24px}");
        sb.AppendLine("a{color:#9ad}.muted{color:#9aa}.bad{color:#f99}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}");
        sb.AppendLine(".card{background:#20272a;border:1px solid #334045;border-radius:10px;padding:14px;box-shadow:0 4px 18px #0006}.title{font-size:17px;font-weight:700;margin-bottom:4px}.meta{font-size:12px;color:#aebbc0;line-height:1.45}");
        sb.AppendLine(".previews{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.pane{width:112px;height:112px;display:flex;align-items:center;justify-content:center;border:1px solid #536166;border-radius:6px;overflow:hidden}");
        sb.AppendLine(".checker{background-color:#777;background-image:linear-gradient(45deg,#bbb 25%,transparent 25%),linear-gradient(-45deg,#bbb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#bbb 75%),linear-gradient(-45deg,transparent 75%,#bbb 75%);background-size:16px 16px;background-position:0 0,0 8px,8px -8px,-8px 0}.dark{background:#0b0e10}.light{background:#e4e4e4}");
        sb.AppendLine("img{max-width:104px;max-height:104px;image-rendering:pixelated;object-fit:contain}code{background:#11191c;padding:2px 4px;border-radius:4px}");
        sb.AppendLine("</style></head><body>");
        sb.AppendLine("<h1>InfiniCrafter source texture dump</h1>");
        sb.AppendLine("<p class=\"muted\">Mode: " + H(mode) + " · Query: " + H(query) + " · Textures: " + dumps.Count + "</p>");
        sb.AppendLine("<p>This dump contains original vanilla/modded textures exported from tModLoader TextureAssets, not generated AI cache PNGs.</p>");
        sb.AppendLine("<p class=\"muted\">For item dumps, files are grouped in a dedicated folder per item. If the item has a linked <code>shoot</code> projectile, it is exported into the same folder.</p>");
        if (errors.Count > 0)
        {
            sb.AppendLine("<details open><summary>Warnings</summary><pre class=\"bad\">" + H(string.Join("\n", errors)) + "</pre></details>");
        }
        sb.AppendLine("<div class=\"grid\">");
        foreach (var d in dumps)
        {
            sb.AppendLine("<div class=\"card\">");
            sb.AppendLine("<div class=\"title\">" + H(d.Kind) + " #" + d.Type + " — " + H(d.DisplayName) + "</div>");
            sb.AppendLine("<div class=\"meta\">fullName: <code>" + H(d.FullName) + "</code><br>mod: " + H(d.SourceMod) + " · size: " + d.Width + "x" + d.Height + " · bytes: " + d.Bytes + "<br>" + H(d.Notes) + "</div>");
            sb.AppendLine("<div class=\"previews\">");
            sb.AppendLine("<div class=\"pane checker\"><a href=\"" + H(d.DumpFile) + "\"><img src=\"" + H(d.DumpFile) + "\"></a></div>");
            sb.AppendLine("<div class=\"pane dark\"><a href=\"" + H(d.DumpFile) + "\"><img src=\"" + H(d.DumpFile) + "\"></a></div>");
            sb.AppendLine("<div class=\"pane light\"><a href=\"" + H(d.DumpFile) + "\"><img src=\"" + H(d.DumpFile) + "\"></a></div>");
            sb.AppendLine("</div><div class=\"meta\">file: <a href=\"" + H(d.DumpFile) + "\"><code>" + H(d.DumpFile) + "</code></a></div>");
            sb.AppendLine("</div>");
        }
        sb.AppendLine("</div></body></html>");
        return sb.ToString();
    }

    private static bool Contains(string? value, string needle)
        => !string.IsNullOrWhiteSpace(value) && value.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0;

    private static DateTime BestMTimeUtc(GeneratedItemData data)
    {
        DateTime best = DateTime.MinValue;
        foreach (string? path in new[]
        {
            data.Visual?.SpritePath,
            data.Visual?.SpriteRawPath,
            data.Attack?.ProjectileSpritePath,
            data.Attack?.ImpactSpritePath,
            data.Attack?.ChildSpritePath,
            data.Attack?.FieldSpritePath,
            data.Visual?.AssetManifestPath,
        })
        {
            string? local = ResolveExistingPath(path);
            if (!string.IsNullOrWhiteSpace(local) && File.Exists(local))
            {
                try
                {
                    DateTime t = File.GetLastWriteTimeUtc(local);
                    if (t > best) best = t;
                }
                catch { }
            }
        }
        return best;
    }

    private static int EffectiveProjectileCanvas(GeneratedItemData data)
    {
        int baseCanvas = Math.Clamp(data.Visual?.PreferredCanvasSize ?? 32, 16, 64);
        int major = Math.Max(data.Attack?.ProjectileWidth ?? 0, data.Attack?.ProjectileHeight ?? 0);
        string blob = string.Join(" ", new[]
        {
            data.Attack?.ProjectileShape,
            data.Attack?.ProjectileMotion,
            data.Attack?.ProjectileTrail,
            data.Attack?.Pattern,
            data.Attack?.ProjectileSpritePrompt,
            data.Attack?.VisualMode,
        }).ToLowerInvariant();

        bool meleeReadable = blob.Contains("sword") || blob.Contains("blade") || blob.Contains("slash") ||
            blob.Contains("glaive") || blob.Contains("boomerang") || blob.Contains("spear") ||
            blob.Contains("lance") || blob.Contains("scythe") || blob.Contains("axe");

        if (major >= 21) return Math.Max(baseCanvas, 48);
        if (major >= 16) return Math.Max(48, baseCanvas >= 64 ? 64 : 48);
        if (meleeReadable) return Math.Max(48, baseCanvas);
        return Math.Max(32, baseCanvas >= 64 ? 48 : 32);
    }

    private static void AddAsset(DumpEntry entry, Dictionary<string, string> copied, string assetDir, string safeId, string role, string? originalPath, string? status, int canvas, float score, string? prompt)
    {
        string? local = ResolveExistingPath(originalPath);
        bool exists = !string.IsNullOrWhiteSpace(local) && File.Exists(local);
        string dumpRel = "";
        long bytes = 0;

        if (exists && local is not null)
        {
            try
            {
                string full = Path.GetFullPath(local);
                if (!copied.TryGetValue(full, out string? existingDumpRel))
                {
                    string ext = Path.GetExtension(full);
                    if (string.IsNullOrWhiteSpace(ext)) ext = ".bin";
                    string destName = SafeFileNamePart(safeId) + "__" + SafeFileNamePart(role) + ext.ToLowerInvariant();
                    string dest = Path.Combine(assetDir, destName);
                    int n = 2;
                    while (File.Exists(dest))
                    {
                        destName = SafeFileNamePart(safeId) + "__" + SafeFileNamePart(role) + "_" + n + ext.ToLowerInvariant();
                        dest = Path.Combine(assetDir, destName);
                        n++;
                    }
                    File.Copy(full, dest, true);
                    dumpRel = "assets/" + destName.Replace('\\', '/');
                    copied[full] = dumpRel;
                }
                else
                {
                    dumpRel = existingDumpRel ?? "";
                }
                bytes = new FileInfo(full).Length;
            }
            catch
            {
                exists = false;
            }
        }

        bool mentionEvenIfMissing = !string.IsNullOrWhiteSpace(originalPath) || !string.IsNullOrWhiteSpace(status);
        if (!exists && !mentionEvenIfMissing) return;

        entry.Assets.Add(new DumpAsset
        {
            Role = role,
            OriginalPath = originalPath ?? "",
            LocalPath = local ?? "",
            DumpFile = dumpRel,
            Exists = exists,
            Bytes = bytes,
            Status = status ?? "",
            Canvas = canvas,
            Score = score,
            Prompt = Trunc(prompt, 700)
        });
    }

    private static string? ResolveExistingPath(string? originalPath)
    {
        if (string.IsNullOrWhiteSpace(originalPath)) return null;
        string raw = originalPath.Trim();

        try
        {
            if (File.Exists(raw)) return Path.GetFullPath(raw);
        }
        catch { }

        try
        {
            string? synced = InfiniCrafterLocalMod.AssetSync?.ResolveLocalPath(raw);
            if (!string.IsNullOrWhiteSpace(synced) && File.Exists(synced))
                return Path.GetFullPath(synced);
        }
        catch { }

        try
        {
            string file = GeneratedAssetSyncService.FileNameFromPath(raw);
            if (!string.IsNullOrWhiteSpace(file))
            {
                string save = string.IsNullOrWhiteSpace(Main.SavePath) ? AppContext.BaseDirectory : Main.SavePath;
                foreach (string root in new[]
                {
                    Path.Combine(save, "InfiniCrafterLocal", "asset_cache"),
                    Path.Combine(save, "InfiniCrafterLocal", "generated_items"),
                    Path.Combine(save, "InfiniCrafterLocal", "picture_dumps"),
                    AppContext.BaseDirectory
                })
                {
                    string candidate = Path.Combine(root, file);
                    if (File.Exists(candidate)) return Path.GetFullPath(candidate);
                }
            }
        }
        catch { }

        return null;
    }

    private static IEnumerable<object> ActiveGeneratedProjectileSnapshots()
    {
        for (int i = 0; i < Main.maxProjectiles; i++)
        {
            Projectile p = Main.projectile[i];
            if (p is null || !p.active) continue;
            string modProj = p.ModProjectile?.GetType().FullName ?? "";
            if (!modProj.Contains("GeneratedProjectile", StringComparison.OrdinalIgnoreCase) &&
                !modProj.Contains("GeneratedVfxOverlayProjectile", StringComparison.OrdinalIgnoreCase))
                continue;
            yield return new
            {
                index = i,
                type = p.type,
                modProjectile = modProj,
                width = p.width,
                height = p.height,
                scale = p.scale,
                position = new { x = Math.Round(p.position.X, 2), y = Math.Round(p.position.Y, 2) },
                velocity = new { x = Math.Round(p.velocity.X, 3), y = Math.Round(p.velocity.Y, 3) },
                timeLeft = p.timeLeft,
                alpha = p.alpha,
                friendly = p.friendly,
                hostile = p.hostile,
                owner = p.owner,
                ai0 = p.ai.Length > 0 ? p.ai[0] : 0f,
                ai1 = p.ai.Length > 1 ? p.ai[1] : 0f,
                localAI0 = p.localAI.Length > 0 ? p.localAI[0] : 0f,
                localAI1 = p.localAI.Length > 1 ? p.localAI[1] : 0f
            };
        }
    }

    private static string BuildHtml(List<DumpEntry> entries, object[] activeGeneratedProjectiles, string mode)
    {
        var sb = new StringBuilder();
        sb.AppendLine("<!doctype html><html><head><meta charset=\"utf-8\">");
        sb.AppendLine("<title>InfiniCrafter picture dump</title>");
        sb.AppendLine("<style>");
        sb.AppendLine("body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#14191b;color:#e8edf0;margin:24px}");
        sb.AppendLine("a{color:#9ad} .muted{color:#9aa} .bad{color:#f99} .ok{color:#9f9}");
        sb.AppendLine(".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}");
        sb.AppendLine(".card{background:#20272a;border:1px solid #334045;border-radius:10px;padding:14px;box-shadow:0 4px 18px #0006}");
        sb.AppendLine(".title{font-size:18px;font-weight:700;margin-bottom:4px}.meta{font-size:12px;color:#aebbc0;margin-bottom:10px;line-height:1.45}");
        sb.AppendLine(".asset{border-top:1px solid #39464b;padding-top:10px;margin-top:10px}");
        sb.AppendLine(".role{font-weight:700;color:#d7f0ff}.prompt{font-size:11px;color:#b8c1c5;white-space:pre-wrap;max-height:90px;overflow:auto}");
        sb.AppendLine(".previews{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}");
        sb.AppendLine(".pane{width:104px;height:104px;display:flex;align-items:center;justify-content:center;border:1px solid #536166;border-radius:6px;overflow:hidden}");
        sb.AppendLine(".checker{background-color:#777;background-image:linear-gradient(45deg,#bbb 25%,transparent 25%),linear-gradient(-45deg,#bbb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#bbb 75%),linear-gradient(-45deg,transparent 75%,#bbb 75%);background-size:16px 16px;background-position:0 0,0 8px,8px -8px,-8px 0}");
        sb.AppendLine(".dark{background:#0b0e10}.light{background:#e4e4e4}");
        sb.AppendLine("img{max-width:96px;max-height:96px;image-rendering:pixelated;object-fit:contain}");
        sb.AppendLine("code{background:#11191c;padding:2px 4px;border-radius:4px}");
        sb.AppendLine("</style></head><body>");
        sb.AppendLine("<h1>InfiniCrafter picture dump</h1>");
        sb.AppendLine("<p class=\"muted\">Mode: " + H(mode) + " · Items: " + entries.Count + " · Active generated projectiles: " + activeGeneratedProjectiles.Length + "</p>");
        sb.AppendLine("<p>Upload this whole folder or zip to ChatGPT. Use <code>picture_dump_manifest.json</code> for exact metadata.</p>");

        if (activeGeneratedProjectiles.Length > 0)
        {
            sb.AppendLine("<details open><summary>Active generated projectiles</summary><pre>");
            sb.AppendLine(H(JsonSerializer.Serialize(activeGeneratedProjectiles, new JsonSerializerOptions { WriteIndented = true })));
            sb.AppendLine("</pre></details>");
        }

        sb.AppendLine("<div class=\"grid\">");
        foreach (var entry in entries)
        {
            sb.AppendLine("<div class=\"card\">");
            sb.AppendLine("<div class=\"title\">" + H(entry.Name) + "</div>");
            sb.AppendLine("<div class=\"meta\">");
            sb.AppendLine("id: <code>" + H(entry.Id) + "</code><br>");
            sb.AppendLine("parents: " + H(entry.ParentA) + " + " + H(entry.ParentB) + "<br>");
            sb.AppendLine("category: " + H(entry.Category) + " · itemCanvas: " + entry.PreferredCanvasSize + " · projectile: " + entry.ProjectileWidth + "x" + entry.ProjectileHeight + " scale " + entry.ProjectileScale.ToString("0.###") + "<br>");
            sb.AppendLine("delivery: " + H(entry.Delivery) + " · movement: " + H(entry.Movement) + " · visualMode: " + H(entry.VisualMode));
            sb.AppendLine("</div>");

            foreach (var a in entry.Assets)
            {
                sb.AppendLine("<div class=\"asset\">");
                sb.AppendLine("<div><span class=\"role\">" + H(a.Role) + "</span> · status: " + H(a.Status) + " · canvas: " + a.Canvas + " · bytes: " + a.Bytes + "</div>");
                if (a.Exists && !string.IsNullOrWhiteSpace(a.DumpFile))
                {
                    bool isPng = a.DumpFile.EndsWith(".png", StringComparison.OrdinalIgnoreCase);
                    if (isPng)
                    {
                        sb.AppendLine("<div class=\"previews\">");
                        sb.AppendLine("<div class=\"pane checker\"><a href=\"" + H(a.DumpFile) + "\"><img src=\"" + H(a.DumpFile) + "\"></a></div>");
                        sb.AppendLine("<div class=\"pane dark\"><a href=\"" + H(a.DumpFile) + "\"><img src=\"" + H(a.DumpFile) + "\"></a></div>");
                        sb.AppendLine("<div class=\"pane light\"><a href=\"" + H(a.DumpFile) + "\"><img src=\"" + H(a.DumpFile) + "\"></a></div>");
                        sb.AppendLine("</div>");
                    }
                    sb.AppendLine("<div class=\"meta\">file: <a href=\"" + H(a.DumpFile) + "\"><code>" + H(a.DumpFile) + "</code></a></div>");
                }
                else
                {
                    sb.AppendLine("<div class=\"bad\">missing local file</div>");
                    sb.AppendLine("<div class=\"meta\">original: <code>" + H(a.OriginalPath) + "</code><br>resolved: <code>" + H(a.LocalPath) + "</code></div>");
                }
                if (!string.IsNullOrWhiteSpace(a.Prompt))
                    sb.AppendLine("<div class=\"prompt\">" + H(a.Prompt) + "</div>");
                sb.AppendLine("</div>");
            }
            sb.AppendLine("</div>");
        }
        sb.AppendLine("</div></body></html>");
        return sb.ToString();
    }

    private static string Trunc(string? value, int max)
    {
        if (string.IsNullOrWhiteSpace(value)) return "";
        value = value.Trim().Replace("\r\n", "\n");
        return value.Length <= max ? value : value[..max] + "…";
    }

    private static string SafeFileNamePart(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "";
        var sb = new StringBuilder();
        foreach (char c in raw.Trim())
        {
            if (char.IsLetterOrDigit(c) || c == '_' || c == '-' || c == '.')
                sb.Append(c);
            else if (char.IsWhiteSpace(c))
                sb.Append('_');
        }
        string s = sb.ToString();
        if (s.Length > 64) s = s[..64];
        return s.Trim('.', '_', '-');
    }

    private static string H(string? value)
        => System.Net.WebUtility.HtmlEncode(value ?? "");
}
