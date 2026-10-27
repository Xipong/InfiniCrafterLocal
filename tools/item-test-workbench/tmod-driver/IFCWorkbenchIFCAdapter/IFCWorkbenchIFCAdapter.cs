#nullable enable
using System;
using System.IO;
using InfiniCrafterLocal;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

namespace IFCWorkbenchIFCAdapter;

// Test-only optional adapter. The generic workbench driver has no dependency
// on IFC internals; tModLoader loads IFC and its hooks normally from .tmod.
public sealed class IFCWorkbenchIFCAdapter : Mod
{
    public override object Call(params object[] args)
    {
        if (args is not ["PrepareItem", Item item, string json, bool isLocalCache])
            throw new ArgumentException("Expected PrepareItem, Item, JSON string, isLocalCache boolean");
        if (string.IsNullOrWhiteSpace(json)) throw new InvalidDataException("Item JSON is empty");

        // Choose the exact requested production boundary; never retry using the
        // other reader or convert a rejected definition into a placeholder.
        string boundary = isLocalCache ? "GeneratedItemData.FromLocalCacheJson" : "GeneratedItemData.FromJson";
        GeneratedItemData? data = isLocalCache
            ? GeneratedItemData.FromLocalCacheJson(json)
            : GeneratedItemData.FromJson(json);
        if (data is null) {
            ContractJsonDiagnostics.TryGet(boundary, out ContractJsonError? error);
            throw new InvalidDataException(boundary + " rejected item: " + (error?.Message ?? "no parsed item"));
        }
        if (GeneratedItemData.IsPlayerSaveReferenceOnly(data))
            throw new InvalidDataException("Player-save reference is not an executable item definition");
        string sandbox = Environment.GetEnvironmentVariable("IFC_WORKBENCH_SANDBOX") ?? "";
        if (Environment.GetEnvironmentVariable("IFC_WORKBENCH_ENABLED") != "1"
            || !Path.IsPathFullyQualified(sandbox) || !Directory.Exists(sandbox))
            throw new InvalidOperationException("Generated item adapter requires the explicitly enabled isolated workbench sandbox");
        sandbox = Path.GetFullPath(sandbox);
        VerifyNoLinks(sandbox);
        if (string.IsNullOrWhiteSpace(Main.SavePath))
            throw new InvalidOperationException("tModLoader save path is not configured");
        VerifyInsideSandbox(sandbox, Main.SavePath, directory: true);
        ValidateAssets(data, sandbox);
        if (!GeneratedItemRegistryService.IsCurrentWorldData(data))
            throw new InvalidDataException("Definition worldId does not match the active isolated world; it was not rewritten");

        // Actual SetDefaults creates the registered ModItem instance; SetData
        // is the public production path, including registry/assets behavior.
        int nativeItemType = GeneratedArmorItemTypes.CanRepresent(data)
            ? GeneratedArmorItemTypes.ItemTypeFor(data)
            : ModContent.ItemType<GeneratedItem>();
        item.SetDefaults(nativeItemType);
        if (item.ModItem is not GeneratedItem generated)
            throw new InvalidOperationException("Native item defaults did not create GeneratedItem");
        generated.SetData(data);
        // Production SetData catches projection errors and substitutes a
        // placeholder. The stand must report that refusal, not a false PASS.
        if (!ReferenceEquals(generated.Data, data))
            throw new InvalidDataException("GeneratedItem.SetData replaced the definition with a placeholder");
        if (InfiniCrafterLocalMod.GeneratedItems is null
            || !InfiniCrafterLocalMod.GeneratedItems.TryGet(data.Id, out GeneratedItemData registered)
            || !ReferenceEquals(registered, data))
            throw new InvalidOperationException("GeneratedItem.SetData did not register the supplied definition in the active world");
        return true;
    }

    // The runtime asset sync owner consumes these exact typed fields. Debug
    // metadata, URL captions, and other inert historical fields do not control
    // what is read here. No authored path is rewritten or resolved relative to
    // the tModLoader installation's working directory.
    private static void ValidateAssets(GeneratedItemData data, string sandbox)
    {
        if (string.Equals(data.RecipeMeta?.AssetTransport, "http", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("HTTP asset transport is not admitted by this isolated workbench adapter");
        void CheckPath(string? path) {
            if (!string.IsNullOrWhiteSpace(path)) VerifyInsideSandbox(sandbox, path, directory: false);
        }
        CheckPath(data.Visual?.SpritePath);
        CheckPath(data.Visual?.EquipOverlayPath);
        foreach (var asset in data.VfxManifest.Assets ?? Array.Empty<VfxAssetSpec>())
            CheckPath(asset.SpritePath);
        foreach (var entity in data.RuntimeProgram.Entities) {
            CheckPath(entity.Visual?.SpritePath);
            CheckPath(entity.Visual?.ImpactSpritePath);
        }
    }

    private static void VerifyInsideSandbox(string sandbox, string path, bool directory)
    {
        if (!Path.IsPathFullyQualified(path))
            throw new InvalidDataException("Sandbox paths must be absolute: " + path);
        string full = Path.GetFullPath(path);
        string relative = Path.GetRelativePath(sandbox, full);
        if (relative == ".." || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            || Path.IsPathFullyQualified(relative))
            throw new InvalidDataException("Path is outside the isolated sandbox: " + path);
        if (directory ? !Directory.Exists(full) : !File.Exists(full))
            throw new FileNotFoundException("Sandbox path does not exist", full);
        VerifyNoLinks(full);
    }

    // Reject links in every existing path component, including the sandbox and
    // its parents. The launcher owns this private sandbox during execution.
    private static void VerifyNoLinks(string path)
    {
        string? current = Path.GetFullPath(path);
        while (!string.IsNullOrEmpty(current)) {
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Links are not permitted in sandbox paths: " + current);
            current = Path.GetDirectoryName(current);
        }
    }
}
