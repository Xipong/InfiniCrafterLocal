#nullable enable
using InfiniCrafterLocal.Common;
using System;
using System.IO;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed class InfiniDumpCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinidump";
    public override string Description => "Dump loaded Terraria/tModLoader item and projectile runtime snapshots for InfiniCrafter analysis.";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        string dir = Path.Combine(Main.SavePath, "InfiniCrafterLocal");
        Directory.CreateDirectory(dir);
        string itemPath = Path.Combine(dir, "items_runtime_dump.jsonl");
        string projectilePath = Path.Combine(dir, "projectiles_runtime_dump.jsonl");

        var options = new JsonSerializerOptions { WriteIndented = false };
        using (var itemWriter = new StreamWriter(itemPath, false))
        {
            for (int type = InfiniTerrariaSentinels.FirstValidItemType; type < ItemLoader.ItemCount; type++)
            {
                try
                {
                    Item item = new();
                    item.SetDefaults(type);
                    if (item.IsAir || string.IsNullOrWhiteSpace(item.Name)) continue;
                    itemWriter.WriteLine(JsonSerializer.Serialize(new
                    {
                        type,
                        name = item.Name,
                        internalName = TryItemName(type),
                        sourceMod = item.ModItem?.Mod?.Name ?? "Terraria",
                        fullName = item.ModItem is not null ? item.ModItem.Mod.Name + "/" + item.ModItem.Name : "Terraria/" + TryItemName(type),
                        textureMetrics = TryItemTextureMetrics(type),
                        damage = item.damage,
                        damageClass = DamageClassName(item),
                        useStyle = item.useStyle,
                        useTime = item.useTime,
                        useAnimation = item.useAnimation,
                        reuseDelay = item.reuseDelay,
                        channel = item.channel,
                        noMelee = item.noMelee,
                        noUseGraphic = item.noUseGraphic,
                        autoReuse = item.autoReuse,
                        rare = item.rare,
                        value = item.value,
                        maxStack = item.maxStack,
                        stack = item.stack,
                        consumable = item.consumable,
                        material = item.material,
                        accessory = item.accessory,
                        questItem = item.questItem,
                        expert = item.expert,
                        master = item.master,
                        defense = item.defense,
                        headSlot = item.headSlot,
                        bodySlot = item.bodySlot,
                        legSlot = item.legSlot,
                        createTile = item.createTile,
                        createWall = item.createWall,
                        placeStyle = item.placeStyle,
                        pickPower = item.pick,
                        axePower = item.axe,
                        hammerPower = item.hammer,
                        bait = item.bait,
                        fishingPole = item.fishingPole,
                        healLife = item.healLife,
                        healMana = item.healMana,
                        manaCost = item.mana,
                        ammo = item.ammo,
                        useAmmo = item.useAmmo,
                        shoot = item.shoot,
                        shootSpeed = item.shootSpeed,
                        directProjectileRaw = item.shoot > ProjectileID.None ? ProjectileRawSnapshot(item.shoot, item.shootSpeed, "item.shoot", item.type, item.Name, TryItemName(item.type), item.ammo, item.useAmmo, item.damage, DamageClassName(item), item.shoot, item.shootSpeed, item.knockBack) : null,
                        knockback = item.knockBack,
                        buffType = item.buffType,
                        buffTime = item.buffTime
                    }, options));
                }
                catch { }
            }
        }

        using (var projectileWriter = new StreamWriter(projectilePath, false))
        {
            for (int type = InfiniTerrariaSentinels.FirstValidProjectileType; type < ProjectileLoader.ProjectileCount; type++)
            {
                try
                {
                    Projectile p = new();
                    p.SetDefaults(type);
                    if (p.width <= 0 && p.height <= 0) continue;
                    projectileWriter.WriteLine(JsonSerializer.Serialize(new
                    {
                        type,
                        internalName = TryProjectileName(type),
                        sourceMod = p.ModProjectile?.Mod?.Name ?? "Terraria",
                        textureMetrics = TryProjectileTextureMetrics(type),
                        width = p.width,
                        height = p.height,
                        scale = p.scale,
                        aiStyle = p.aiStyle,
                        penetrate = p.penetrate,
                        maxPenetrate = p.maxPenetrate,
                        timeLeft = p.timeLeft,
                        extraUpdates = p.extraUpdates,
                        tileCollide = p.tileCollide,
                        ignoreWater = p.ignoreWater,
                        friendly = p.friendly,
                        hostile = p.hostile,
                        arrow = p.arrow,
                        minion = p.minion,
                        sentry = p.sentry,
                        minionSlots = p.minionSlots,
                        ownerHitCheck = p.ownerHitCheck,
                        usesLocalNPCImmunity = p.usesLocalNPCImmunity,
                        localNPCHitCooldown = p.localNPCHitCooldown,
                        usesIDStaticNPCImmunity = p.usesIDStaticNPCImmunity,
                        idStaticNPCHitCooldown = p.idStaticNPCHitCooldown,
                        stopsDealingDamageAfterPenetrateHits = p.stopsDealingDamageAfterPenetrateHits,
                        light = p.light,
                        alpha = p.alpha,
                        netImportant = p.netImportant,
                        framesRaw = SafeProjFrames(type),
                        setsRaw = ProjectileSetsRaw(type),
                        damageClass = p.DamageType == DamageClass.Melee ? "melee" : p.DamageType == DamageClass.Ranged ? "ranged" : p.DamageType == DamageClass.Magic ? "magic" : p.DamageType == DamageClass.Summon ? "summon" : p.DamageType == DamageClass.Generic ? "generic" : "modded"
                    }, options));
                }
                catch { }
            }
        }

        Main.NewText($"InfiniCraft dump written: {itemPath}", 120, 220, 255);
        Main.NewText($"InfiniCraft dump written: {projectilePath}", 120, 220, 255);
    }

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

    private static string TryItemName(int type)
    {
        try { return ItemID.Search.GetName(type) ?? type.ToString(); }
        catch { return type.ToString(); }
    }

    private static string TryProjectileName(int type)
    {
        try { return ProjectileID.Search.GetName(type) ?? type.ToString(); }
        catch { return type.ToString(); }
    }

    private static object ProjectileRawSnapshot(int projectileType, float itemShootSpeed, string source, int sourceItemType, string sourceItemName, string sourceItemInternalName, int sourceItemAmmo, int sourceItemUseAmmo, int sourceItemDamage, string sourceItemDamageClass, int sourceItemShoot, float sourceItemShootSpeed, float sourceItemKnockback)
    {
        try
        {
            Projectile p = new();
            p.SetDefaults(projectileType);
            string sourceMod = p.ModProjectile?.Mod?.Name ?? "Terraria";
            string internalName = TryProjectileName(projectileType);
            return new
            {
                source,
                type = projectileType,
                sourceMod,
                internalName,
                fullName = sourceMod + "/" + internalName,
                textureMetrics = TryProjectileTextureMetrics(projectileType),
                sourceItemType,
                sourceItemName,
                sourceItemInternalName,
                sourceItemAmmo,
                sourceItemUseAmmo,
                sourceItemDamage,
                sourceItemDamageClass,
                sourceItemShoot,
                sourceItemShootSpeed,
                sourceItemKnockback,
                itemShootSpeed,
                ai0 = p.ai.Length > 0 ? p.ai[0] : 0f,
                ai1 = p.ai.Length > 1 ? p.ai[1] : 0f,
                ai2 = p.ai.Length > 2 ? p.ai[2] : 0f,
                localAI0 = p.localAI.Length > 0 ? p.localAI[0] : 0f,
                localAI1 = p.localAI.Length > 1 ? p.localAI[1] : 0f,
                width = p.width,
                height = p.height,
                scale = p.scale,
                aiStyle = p.aiStyle,
                penetrate = p.penetrate,
                maxPenetrate = p.maxPenetrate,
                timeLeft = p.timeLeft,
                extraUpdates = p.extraUpdates,
                tileCollide = p.tileCollide,
                ignoreWater = p.ignoreWater,
                friendly = p.friendly,
                hostile = p.hostile,
                arrow = p.arrow,
                minion = p.minion,
                sentry = p.sentry,
                minionSlots = p.minionSlots,
                ownerHitCheck = p.ownerHitCheck,
                usesLocalNPCImmunity = p.usesLocalNPCImmunity,
                localNPCHitCooldown = p.localNPCHitCooldown,
                usesIDStaticNPCImmunity = p.usesIDStaticNPCImmunity,
                idStaticNPCHitCooldown = p.idStaticNPCHitCooldown,
                stopsDealingDamageAfterPenetrateHits = p.stopsDealingDamageAfterPenetrateHits,
                light = p.light,
                alpha = p.alpha,
                netImportant = p.netImportant,
                framesRaw = SafeProjFrames(projectileType),
                setsRaw = ProjectileSetsRaw(projectileType),
                damageClass = p.DamageType == DamageClass.Melee ? "melee" : p.DamageType == DamageClass.Ranged ? "ranged" : p.DamageType == DamageClass.Magic ? "magic" : p.DamageType == DamageClass.Summon ? "summon" : p.DamageType == DamageClass.Generic ? "generic" : "modded"
            };
        }
        catch
        {
            return new { source, type = projectileType, itemShootSpeed, unavailable = true };
        }
    }

    private static object ProjectileSetsRaw(int projectileType)
    {
        return new
        {
            trailCacheLength = SafeArrayValue(ProjectileID.Sets.TrailCacheLength, projectileType, 0),
            trailingMode = SafeArrayValue(ProjectileID.Sets.TrailingMode, projectileType, 0),
            lightPet = SafeProjectileSetValue("LightPet", projectileType),
            minionSacrificable = SafeProjectileSetValue("MinionSacrificable", projectileType),
            homing = SafeProjectileSetValue("Homing", projectileType),
            dontAttachHideToAlpha = SafeProjectileSetValue("DontAttachHideToAlpha", projectileType),
            usesOldTargeting = SafeProjectileSetValue("UsesOldTargeting", projectileType),
            noLiquidDistortion = SafeProjectileSetValue("NoLiquidDistortion", projectileType)
        };
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

    private static int SafeArrayValue(int[] values, int index, int fallback)
    {
        try
        {
            if (index >= 0 && index < values.Length)
                return values[index];
        }
        catch { }
        return fallback;
    }

    private static object? SafeProjectileSetValue(string fieldName, int index)
    {
        try
        {
            var field = typeof(ProjectileID.Sets).GetField(fieldName, System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
            if (field is null) return null;
            object? value = field.GetValue(null);
            if (value is Array arr && index >= 0 && index < arr.Length)
                return arr.GetValue(index);
        }
        catch { }
        return null;
    }

    private static string DamageClassName(Item item)
    {
        try
        {
            if (item.DamageType == DamageClass.Melee) return "melee";
            if (item.DamageType == DamageClass.Ranged) return "ranged";
            if (item.DamageType == DamageClass.Magic) return "magic";
            if (item.DamageType == DamageClass.Summon) return "summon";
            if (item.damage > 0 && item.DamageType != DamageClass.Default && item.DamageType != DamageClass.Generic) return "modded";
        }
        catch { }
        return item.damage > 0 ? "generic" : "none";
    }
}
