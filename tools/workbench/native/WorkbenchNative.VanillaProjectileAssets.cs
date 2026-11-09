using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using Terraria.GameContent;

// Verified resources, not a weapon registry: native Terraria owns AI and drawing.
internal sealed class WNativeVanillaProjectileAssets : IDisposable
{
    static readonly JsonObject Index = JsonNode.Parse(typeof(WNativeVanillaProjectileAssets).Assembly
        .GetManifestResourceStream("Workbench.VanillaDrawAssets.json")
        ?? throw new InvalidDataException("Embedded vanilla draw source index missing"))!.AsObject();
    readonly Dictionary<int, Asset<Texture2D>> loadedProjectiles = new();
    readonly List<(Asset<Texture2D>[] Array, int Id, Asset<Texture2D> Previous, Asset<Texture2D> Loaded)> bindings = new();
    readonly AssetRepository assets;
    Asset<Texture2D>? oldFishingLine, loadedFishingLine;
    bool fishingLineBound;
    public static bool Supports(int id) => id >= 0 && Index["entries"]?["Projectile_" + id + ".png"] is not null;
    internal static byte[] ReadResource(string root, string filename, out JsonObject receipt) {
        var entry = Index["entries"]?[filename]?.AsArray()
            ?? throw new FileNotFoundException("No pinned native draw resource: " + filename);
        return WVanillaItemAssets.ReadIndexed(root, filename, Index, entry, out receipt);
    }
    public void RequireReady(int id)
    {
        if (!Supports(id)) throw new NotSupportedException("Native projectile has no pinned source PNG: " + id);
        if (!loadedProjectiles.ContainsKey(id)) throw new FileNotFoundException("Native projectile draw requires pinned Projectile_" + id + ".png; provision it with fetch_performance_assets.py --projectiles " + id);
    }
    public JsonObject Report { get; } = new() {
        ["entrypoint"] = "Main.DrawProj (original)", ["source"] = "Pinned community Terraria source PNGs, not HD outputs",
        ["officialByteIdentityVerified"] = false, ["textures"] = new JsonArray(),
        ["scope"] = "Supplied verified Projectile/Extra/Glow/BackPack/FishingLine resources; resource availability does not certify arbitrary native draw passes"
    };
    public WNativeVanillaProjectileAssets(WorkbenchGraphicsContext graphics, string root, int[]? itemTextures = null)
    {
        var readers = new AssetReaderCollection(); readers.RegisterReader(new PngReader(graphics.Device), ".png");
        assets = new AssetRepository(readers);
        Report["sourceCommit"] = Index["communityCommit"]!.DeepClone();
        try {
            foreach (int id in itemTextures ?? Array.Empty<int>()) {
                byte[] bytes = WVanillaItemAssets.Read(root, id, out var receipt);
                var texture = Load(bytes, "Item_" + id + ".png");
                bindings.Add((TextureAssets.Item, id, TextureAssets.Item[id], texture)); TextureAssets.Item[id] = texture;
                Report["textures"]!.AsArray().Add(receipt);
            }
            long totalBytes = 0, totalPixels = 0;
            // Only existing explicitly provisioned files are bound. Missing dependencies fail
            // in native drawing; no generated/default texture is inserted for an absent resource.
            foreach (var entry in Index["entries"]!.AsObject().OrderBy(p => p.Key, StringComparer.Ordinal)) {
                string name = entry.Key;
                if (name == "Misc/Ripples.png") continue; // Genuine WaterShader scope owns this resource and its lifecycle.
                if (!File.Exists(Path.Combine(root, "Images", name))) continue;
                Asset<Texture2D>[]? target = null;
                int id = -1;
                if (TryId(name, "Projectile_", out id)) { target = TextureAssets.Projectile; }
                else if (TryId(name, "Extra_", out id)) { target = TextureAssets.Extra; }
                else if (TryId(name, "Glow_", out id)) { target = TextureAssets.GlowMask; }
                else if (TryId(name, "BackPack_", out id)) { target = TextureAssets.BackPack; }
                else if (name != "FishingLine.png") throw new InvalidDataException("Unknown indexed draw resource kind: " + name);
                if (target is not null && (id < 0 || id >= target.Length)) throw new NotSupportedException("Indexed resource is outside loaded Terraria array: " + name);
                byte[] bytes = WVanillaItemAssets.ReadIndexed(root, name, Index, entry.Value!.AsArray(), out var receipt);
                totalBytes += bytes.Length;
                totalPixels += (long)receipt["width"]!.GetValue<uint>() * receipt["height"]!.GetValue<uint>();
                if (totalBytes > 64L * 1024 * 1024 || totalPixels > 64L * 1024 * 1024)
                    throw new InvalidDataException("Supplied native draw resources exceed aggregate 64MiB source/64Mpixel limit");
                var texture = Load(bytes, name);
                if (target is not null) { bindings.Add((target, id, target[id], texture)); target[id] = texture; if (ReferenceEquals(target, TextureAssets.Projectile)) loadedProjectiles.Add(id, texture); }
                else { oldFishingLine = TextureAssets.FishingLine; loadedFishingLine = texture; TextureAssets.FishingLine = texture; fishingLineBound = true; }
                receipt["asset"] = name; receipt["state"] = texture.State.ToString();
                Report["textures"]!.AsArray().Add(receipt);
            }
        } catch { Dispose(); throw; }
    }
    static bool TryId(string name, string prefix, out int id) {
        id = -1;
        return name.StartsWith(prefix, StringComparison.Ordinal) && name.EndsWith(".png", StringComparison.Ordinal)
            && int.TryParse(name.AsSpan(prefix.Length, name.Length - prefix.Length - 4), NumberStyles.None, CultureInfo.InvariantCulture, out id);
    }
    Asset<Texture2D> Load(byte[] bytes, string name) {
        using var input = new MemoryStream(bytes, writable: false);
        var texture = assets.CreateUntracked<Texture2D>(input, name, AssetRequestMode.ImmediateLoad);
        if (texture.State != AssetState.Loaded) throw new InvalidDataException("Native PNG failed to load: " + name);
        return texture;
    }
    public void Dispose() {
        foreach (var b in bindings) { b.Array[b.Id] = b.Previous; b.Loaded.Dispose(); }
        bindings.Clear(); loadedProjectiles.Clear();
        if (fishingLineBound) { TextureAssets.FishingLine = oldFishingLine; fishingLineBound = false; }
        loadedFishingLine?.Dispose(); loadedFishingLine = null;
        assets.Dispose();
    }
}
