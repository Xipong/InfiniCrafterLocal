using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using ReLogic.Content;
using ReLogic.Content.Readers;
using ReLogic.Content.Sources;
using Terraria;
using Terraria.GameContent;
using Terraria.ModLoader;
using Main = Terraria.Main;

// Diagnostic draw observer of the actual loader scene, not a second simulation.
// The isolated loader still updates in dedicated mode; this does not run client
// mod loading, Main.Update, or Main.Draw. Missing resources remain hard failures.
internal sealed class WNativeLoaderRenderer : IDisposable
{
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
    const int Size = 640;
    readonly string output, playerRoot;
    readonly List<(Mod Mod, IAssetRepository Previous, AssetRepository Current)> repositories = new();
    readonly Dictionary<string, Asset<Texture2D>> textures = new(StringComparer.Ordinal);
    readonly JsonArray frames = new(), receipts = new();
    WorkbenchGraphicsContext? graphics;
    WNativePlayerAssets? playerAssets;
    SpriteBatch? batch;
    RenderTarget2D? target;
    Asset<Texture2D>[]? oldItems, oldProjectiles;
    bool disposed;
    Action? applyRenderBindings;
    delegate bool DrawOriginal(Projectile projectile, ref Color lightColor);
    delegate bool DrawObserver(DrawOriginal orig, Projectile projectile, ref Color lightColor);
    Hook? drawObserver;
    JsonArray? currentDraws;
    Player? currentOwner;
    public JsonObject Report { get; }

    public WNativeLoaderRenderer(string output, string playerRoot)
    {
        this.output = Path.GetFullPath(output); this.playerRoot = Path.GetFullPath(playerRoot);
        if (Directory.Exists(this.output) && Directory.EnumerateFileSystemEntries(this.output).Any())
            throw new IOException("Loader render output must be a new or empty directory; existing evidence is never overwritten: " + this.output);
        Directory.CreateDirectory(this.output);
        Report = new JsonObject {
            ["backend"] = "loader-post-update-native-draw", ["fullGameParity"] = false,
            ["scope"] = "Actual post-update loader timeline; Main.DrawProj and PlayerRenderer.DrawPlayers on neutral background; no pose or AI replay",
            ["simulationMode"] = "Dedicated-mode loader updates; client drawing only during observation",
            ["drawHookSideEffectsIsolated"] = false,
            ["cpuOnlyEquivalenceGuaranteed"] = false,
            ["drawHookScope"] = "Real mod draw hooks may consume RNG or change state; only host-owned temporary render bindings and native player draw geometry are restored",
            ["camera"] = "640x640, centered on actual player, zoom 1", ["lighting"] = "Diagnostic white lighting, not world lighting parity",
            ["unsupported"] = new JsonArray("Generated JSON items and vanilla texture aliases", "Client mod lifecycle, custom effects and equipment", "Hidden non-held and specially ordered projectile passes", "NPC, tile, dust, gore, world and detached VFX drawing", "Complete Main.Update/Main.Draw and networking"),
            ["frames"] = frames, ["frameCount"] = 0, ["textures"] = receipts
        };
    }

    void Initialize()
    {
        graphics = new WorkbenchGraphicsContext(Path.Combine(AppContext.BaseDirectory, "native-assets", "GeneratedItem.png"));
        batch = new SpriteBatch(graphics.Device);
        target = new RenderTarget2D(graphics.Device, Size, Size);
        playerAssets = new WNativePlayerAssets(graphics, playerRoot);
        oldItems = TextureAssets.Item; oldProjectiles = TextureAssets.Projectile;
        TextureAssets.Item = (Asset<Texture2D>[])oldItems.Clone();
        TextureAssets.Projectile = (Asset<Texture2D>[])oldProjectiles.Clone();
        TextureAssets.Item[0] = graphics.LoadEmptyItemTexture(playerRoot);
        var readers = new AssetReaderCollection(); readers.RegisterReader(new PngReader(graphics.Device), ".png");
        foreach (var mod in ModLoader.Mods) {
            var source = (IContentSource?)typeof(Mod).GetProperty("RootContentSource", All)!.GetValue(mod);
            if (source is null) continue;
            var repository = new AssetRepository(readers, new[] { source });
            repositories.Add((mod, mod.Assets, repository));
            typeof(Mod).GetProperty(nameof(Mod.Assets), All)!.SetValue(mod, repository);
        }
        typeof(PlayerDrawLayerLoader).GetMethod("ResizeArrays", All)!.Invoke(null, null);
        // Both the world and native held-player path enter this real tML
        // dispatcher. Main.DrawProj(int) alone misses the player's direct path.
        drawObserver = new Hook(typeof(ProjectileLoader).GetMethod(nameof(ProjectileLoader.PreDraw),
            new[] { typeof(Projectile), typeof(Color).MakeByRefType() })!,
            (DrawObserver)((DrawOriginal orig, Projectile projectile, ref Color lightColor) => {
                currentDraws?.Add(new JsonObject { ["slot"] = projectile.whoAmI, ["identity"] = projectile.identity,
                    ["type"] = projectile.type, ["activeAtDraw"] = projectile.active,
                    ["entrypoint"] = "ProjectileLoader.PreDraw",
                    ["pass"] = currentOwner?.heldProj == projectile.whoAmI ? "native_player_held" : "world" });
                return orig(projectile, ref lightColor);
            }));
        TimeLogger.Initialize(); Lighting.Initialize();
        Directory.CreateDirectory(Path.Combine(output, "frames"));
        Report["graphics"] = graphics.Provenance.DeepClone();
        Report["playerAssets"] = playerAssets.Report.DeepClone();
    }

    Asset<Texture2D> Texture(string name)
    {
        if (name.StartsWith("Terraria/", StringComparison.Ordinal) || !name.Contains('/'))
            throw new NotSupportedException("Loader draw requires an explicitly supplied mod PNG texture: " + name);
        if (textures.TryGetValue(name, out var loaded)) return loaded;
        var asset = ModContent.Request<Texture2D>(name, AssetRequestMode.ImmediateLoad);
        if (asset.State != AssetState.Loaded) throw new InvalidDataException("Native mod texture did not load: " + name);
        var pixels = new Color[checked(asset.Value.Width * asset.Value.Height)]; asset.Value.GetData(pixels);
        var bytes = new byte[checked(pixels.Length * 4)];
        for (int i = 0; i < pixels.Length; i++) { bytes[i*4] = pixels[i].R; bytes[i*4+1] = pixels[i].G; bytes[i*4+2] = pixels[i].B; bytes[i*4+3] = pixels[i].A; }
        receipts.Add(new JsonObject { ["texture"] = name, ["width"] = asset.Value.Width, ["height"] = asset.Value.Height,
            ["gpuPremultipliedRgbaSha256"] = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            ["source"] = "Original supplied Mod.RootContentSource via native PngReader; no fallback texture" });
        textures.Add(name, asset); return asset;
    }

    // Keep graphics resources alive across frames without exposing client asset
    // bindings to the following dedicated simulation tick.
    static Action SnapshotBindings()
    {
        var assets = Main.Assets; var players = TextureAssets.Players;
        var hair = TextureAssets.PlayerHair; var hairAlt = TextureAssets.PlayerHairAlt;
        var backpacks = TextureAssets.BackPack; var pixel = TextureAssets.MagicPixel;
        var dust = TextureAssets.Dust; var shader = Main.PixelShaderRef.Value;
        var items = TextureAssets.Item; var projectiles = TextureAssets.Projectile;
        return () => {
            Main.Assets = assets; TextureAssets.Players = players;
            TextureAssets.PlayerHair = hair; TextureAssets.PlayerHairAlt = hairAlt;
            TextureAssets.BackPack = backpacks; TextureAssets.MagicPixel = pixel;
            TextureAssets.Dust = dust; Main.PixelShaderRef.Value = shader;
            TextureAssets.Item = items; TextureAssets.Projectile = projectiles;
        };
    }

    public void Capture(int tick, Player owner)
    {
        if (disposed) throw new ObjectDisposedException(nameof(WNativeLoaderRenderer));
        bool dedicated = Main.dedServ, map = Main.mapEnabled;
        int width = Main.screenWidth, height = Main.screenHeight;
        var camera = Main.screenPosition; var view = Main.GameViewMatrix;
        var previousGraphics = Main.graphics; var previousBatch = Main.spriteBatch;
        var servicesField = typeof(Game).GetField("<Services>k__BackingField", All)!;
        var services = servicesField.GetValue(Main.instance);
        var position = owner.position; int ownerWidth = owner.width, ownerHeight = owner.height;
        float gfxOffY = owner.gfxOffY, rotation = owner.fullRotation;
        var rotationOrigin = owner.fullRotationOrigin; var body = owner.bodyFrame; var legs = owner.legFrame;
        RenderTargetBinding[]? renderTargets = null;
        var restoreBindings = SnapshotBindings();
        try {
            if (graphics is null) { Initialize(); applyRenderBindings = SnapshotBindings(); }
            applyRenderBindings!();
            foreach (var entry in repositories)
                typeof(Mod).GetProperty(nameof(Mod.Assets), All)!.SetValue(entry.Mod, entry.Current);
            Main.graphics = graphics!.Manager; Main.spriteBatch = batch;
            servicesField.SetValue(Main.instance, graphics.Services);
            Main.dedServ = false; Main.mapEnabled = false;
            Main.screenWidth = Main.screenHeight = Size;
            Main.screenPosition = owner.Center - new Vector2(Size / 2);
            Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(graphics.Device) { Zoom = Vector2.One };
            if (owner.isLockedToATile || owner.skinVariant != 0 || owner.hair != 0 || owner.armor.Any(i => !i.IsAir) || owner.dye.Any(i => !i.IsAir) || owner.miscEquips.Any(i => !i.IsAir) || owner.miscDyes.Any(i => !i.IsAir) || owner.mount.Active)
                throw new NotSupportedException("Loader draw supports only unequipped starter male skin/hair and ordinary player ordering");
            if (!owner.HeldItem.IsAir) {
                if (owner.HeldItem.ModItem is null || owner.HeldItem.ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem)
                    throw new NotSupportedException("Loader draw requires a native mod item, not vanilla or generated content");
                TextureAssets.Item[owner.HeldItem.type] = Texture(owner.HeldItem.ModItem.Texture);
            }
            var active = Main.projectile.Where(p => p.active).ToArray();
            if (owner.heldProj >= Main.maxProjectiles) throw new NotSupportedException("Held projectile slot is outside the native scene");
            // Native player drawing can still reference a just-expired held slot.
            // Preserve that native last frame and validate its actual texture too.
            var candidates = owner.heldProj >= 0 ? active.Append(Main.projectile[owner.heldProj]).Distinct() : active;
            foreach (var p in candidates) {
                if (p.ModProjectile is null || p.ModProjectile is InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile)
                    throw new NotSupportedException("Loader draw requires native mod projectiles");
                if (p.hide && p.whoAmI != owner.heldProj) throw new NotSupportedException("Hidden non-held projectile draw ordering is unsupported");
                // Admission must not execute extra authored callbacks: even an
                // apparently empty DrawBehind can mutate native simulation state.
                if (p.ModProjectile.GetType().GetMethod("DrawBehind", All)?.DeclaringType != typeof(ModProjectile)
                    || ModLoader.Mods.SelectMany(m => m.GetContent<GlobalProjectile>()).Any(g =>
                        g.GetType().GetMethod("DrawBehind", All)?.DeclaringType != typeof(GlobalProjectile)))
                    throw new NotSupportedException("Custom projectile/global DrawBehind overrides require unsupported world ordering");
                TextureAssets.Projectile[p.type] = Texture(p.ModProjectile.Texture);
            }
            int left = Math.Max(1, (int)Main.screenPosition.X / 16 - 2), top = Math.Max(1, (int)Main.screenPosition.Y / 16 - 2);
            int right = Math.Min(Main.maxTilesX - 2, left + Size / 16 + 4), bottom = Math.Min(Main.maxTilesY - 2, top + Size / 16 + 4);
            for (int pass = 0; pass < (tick == 0 ? 4 : 1); pass++) {
                for (int x = left; x < right; x++) for (int y = top; y < bottom; y++) Lighting.AddLight(x, y, 1, 1, 1);
                Lighting.LightTiles(left, right, top, bottom);
            }
            renderTargets = graphics.Device.GetRenderTargets();
            graphics.Device.SetRenderTarget(target); graphics.Device.Clear(new Color(20, 24, 32));
            currentDraws = new JsonArray(); currentOwner = owner;
            Exception? drawError = null;
            EventHandler<System.Runtime.ExceptionServices.FirstChanceExceptionEventArgs> observer = (_, e) => drawError = e.Exception;
            AppDomain.CurrentDomain.FirstChanceException += observer;
            try {
                batch!.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.PointClamp, DepthStencilState.None, RasterizerState.CullNone, null, Main.GameViewMatrix.TransformationMatrix);
                try { foreach (var p in active) if (p.whoAmI != owner.heldProj) Main.instance.DrawProj(p.whoAmI); }
                finally { batch.End(); }
                Main.PlayerRenderer.DrawPlayers(Main.Camera, new[] { owner });
            } finally { AppDomain.CurrentDomain.FirstChanceException -= observer; }
            if (drawError is not null || active.Any(p => !p.active)) throw new InvalidOperationException("Native drawing raised an exception or deactivated a projectile; refusing swallowed draw failure", drawError);
            graphics.Device.SetRenderTargets(renderTargets);
            string file = $"frames/frame-{tick:000}.png";
            using (var stream = File.Create(Path.Combine(output, file))) target!.SaveAsPng(stream, Size, Size);
            frames.Add(new JsonObject { ["tick"] = tick, ["phase"] = "post_update", ["file"] = file,
                ["path"] = Path.Combine(output, file), ["width"] = Size, ["height"] = Size,
                ["sha256"] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(output, file)))).ToLowerInvariant(), ["heldProjectileSlot"] = owner.heldProj,
                ["projectileDrawAttempts"] = currentDraws,
                ["worldProjectileDrawAttempts"] = active.Count(p => p.whoAmI != owner.heldProj), ["playerDrawAttempts"] = 1 });
            Report["frameCount"] = frames.Count;
        } finally {
            foreach (var entry in repositories)
                typeof(Mod).GetProperty(nameof(Mod.Assets), All)!.SetValue(entry.Mod, entry.Previous);
            if (renderTargets is not null) graphics!.Device.SetRenderTargets(renderTargets);
            owner.position = position; owner.width = ownerWidth; owner.height = ownerHeight; owner.gfxOffY = gfxOffY;
            owner.fullRotation = rotation; owner.fullRotationOrigin = rotationOrigin; owner.bodyFrame = body; owner.legFrame = legs;
            Main.dedServ = dedicated; Main.mapEnabled = map; Main.screenWidth = width; Main.screenHeight = height;
            Main.screenPosition = camera; Main.GameViewMatrix = view; Main.graphics = previousGraphics; Main.spriteBatch = previousBatch;
            servicesField.SetValue(Main.instance, services);
            restoreBindings();
            currentDraws = null; currentOwner = null;
        }
    }

    public void Dispose()
    {
        if (disposed) return; disposed = true;
        drawObserver?.Dispose();
        foreach (var entry in repositories.AsEnumerable().Reverse()) {
            typeof(Mod).GetProperty(nameof(Mod.Assets), All)!.SetValue(entry.Mod, entry.Previous); entry.Current.Dispose();
        }
        if (oldItems is not null) TextureAssets.Item = oldItems;
        if (oldProjectiles is not null) TextureAssets.Projectile = oldProjectiles;
        playerAssets?.Dispose(); target?.Dispose(); batch?.Dispose(); graphics?.Dispose();
    }
}
