#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;
using Terraria.GameContent;
using Terraria.ObjectData;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // A module-wide file certificate covers the property getters and banner
    // helpers as well as the extracted methods. Read once; this certifies the
    // original binary, not in-memory detours or arbitrary mod behavior.
    private static readonly Lazy<bool> NativeSourceModuleVerified = new(() =>
    {
        try
        {
            var assembly = typeof(Player).Assembly;
            if (typeof(Player).Module.ModuleVersionId.ToString() != NativeEnvironmentFactsCatalog.ModuleVersionId)
                return false;
            using var stream = File.OpenRead(assembly.Location);
            return Convert.ToHexString(SHA256.HashData(stream)).Equals(
                NativeEnvironmentFactsCatalog.AssemblySha256, StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    });

    internal static JsonObject? CaptureNativeEnvironmentReference(Item item)
        => VerifiedNativeEnvironmentReference(item, NativeSourceModuleVerified.Value);

    internal static JsonObject? VerifiedNativeEnvironmentReference(Item item, bool moduleVerified)
    {
        if (!moduleVerified || item.ModItem is not null || item.type <= ItemID.None || item.type >= ItemID.Count)
            return null;
        var facts = new JsonObject();
        var auras = new JsonArray();
        var candidates = JsonNode.Parse(NativeEnvironmentFactsCatalog.AuraJson)!.AsArray().OfType<JsonObject>()
            .Where(row => row["tileId"]!.GetValue<int>() == item.createTile).ToArray();
        // Admit only a current vanilla default tile/style pair; a mutated item's
        // arbitrary style cannot borrow another object's certificate. Samples
        // and TileObjectData are read-only snapshots; no defaults/hooks run here.
        if (ContentSamples.ItemsByType.TryGetValue(item.type, out var sample)
            && sample.ModItem is null && sample.createTile == item.createTile && sample.placeStyle == item.placeStyle)
            foreach (var row in candidates)
            {
                var placements = ObserveNativeAuraPlacements(item, row);
                if (placements.Count == 0) continue;
                var copy = row.DeepClone().AsObject();
                copy["placementVariants"] = placements;
                auras.Add(copy);
            }
        if (auras.Count > 0)
        {
            facts["placedTileAuras"] = auras;
            facts["placeStyle"] = item.placeStyle;
            facts["placementMapping"] = JsonNode.Parse(NativeEnvironmentFactsCatalog.PlacementMappingJson);
            facts["activation"] = "Only the listed native metadata placement variants have matching initial tile cells. A successfully placed active tile must be inside the native rectangular buff scan and satisfy the original frame predicates. Item inventory presence is not activation. Placement success, current-world activation, wiring/toggle state and arbitrary mod hooks are not observed. Metadata and default item samples are current registry snapshots, not proof that other mods left them unchanged.";
            facts["buffScanWidthTiles"] = Main.buffScanAreaWidth;
            facts["buffScanHeightTiles"] = Main.buffScanAreaHeight;
            facts["scanBounds"] = "Native rectangle centered on scan center and clamped to world; dimensions are current native settings, not a circular radius.";
        }
        var bannerIds = new JsonArray();
        // These certified native ID mapping getters only read native switch/data
        // tables. No NPC instances or ModItem/ModNPC hooks are invoked. Mapping
        // identity is independent of the BannerStrength array's default entries.
        if (item.createTile == TileID.Banners && item.type < ItemID.Sets.BannerStrength.Length)
        {
            var identities = new System.Collections.Generic.HashSet<int>();
            for (int npcType = 0; npcType < NPCID.Count; npcType++)
            {
                int bannerId = Item.NPCtoBanner(npcType);
                if (bannerId > 0 && Item.BannerToItem(bannerId) == item.type && identities.Add(bannerId))
                    bannerIds.Add(bannerId);
            }
        }
        if (bannerIds.Count > 0)
        {
            var effect = ItemID.Sets.BannerStrength[item.type];
            facts["bannerRegistry"] = new JsonObject
            {
                ["itemId"] = item.type,
                ["nativeBannerIdentities"] = bannerIds,
                ["enabled"] = effect.Enabled,
                ["placementActivation"] = "The native scene scanner requires an enabled registered banner before setting its matching nearby flag. This snapshot does not assert that a banner is currently placed or in range.",
                ["normalDamageDealtMultiplier"] = effect.NormalDamageDealt,
                ["expertDamageDealtMultiplier"] = effect.ExpertDamageDealt,
                ["normalDamageReceivedMultiplier"] = effect.NormalDamageReceived,
                ["expertDamageReceivedMultiplier"] = effect.ExpertDamageReceived,
                ["source"] = "current_ItemID.Sets.BannerStrength_entry_with_native_ID_mapping",
                ["condition"] = "The native matching opponent-banner buff must be present, and Item.BannerToItem for that banner identity must resolve to this item entry. A nearby unrelated banner is not sufficient; inventory possession is not sufficient. Registry presence does not itself prove placement/activation or enumerate matching NPCs.",
                ["operation"] = "ApplyBannerOffenseBuff multiplies TargetDamageMultiplier; ApplyBannerDefenseBuff multiplies IncomingDamageMultiplier. Main.expertMode selects expert values. These are native modifier components, not final damage, final defense, or guaranteed effective health. Other hooks may alter the outcome."
            };
        }
        if (facts.Count == 0) return null;
        facts["source"] = "certified_native_environment_reference";
        facts["sourceAssemblySha256"] = NativeEnvironmentFactsCatalog.AssemblySha256;
        facts["sourceModuleVersionId"] = NativeEnvironmentFactsCatalog.ModuleVersionId;
        facts["scope"] = "Conditional partial native-source reference plus current registry settings, not current-world observation, complete buff semantics, arbitrary mod hooks, or inherited generated execution. Unknown effects remain unknown; Author chooses generated behavior explicitly.";
        return facts;
    }

    private static JsonArray ObserveNativeAuraPlacements(Item item, JsonObject aura)
    {
        var variants = new JsonArray();
        try
        {
            var root = TileObjectData.GetTileData(item.createTile, item.placeStyle, 0);
            if (root is null || !root.UsesCustomCanPlace || root.AlternatesCount > 8) return variants;
            for (int alternate = 0; alternate <= root.AlternatesCount; alternate++)
            {
                var data = TileObjectData.GetTileData(item.createTile, item.placeStyle, alternate);
                if (data is null || data.HookPlaceOverride.hook is not null
                    || data.RandomStyleRange != 0 || data.SpecificRandomStyles is { Length: > 0 }
                    || data.Width <= 0 || data.Width > 8 || data.Height <= 0 || data.Height > 8
                    || data.CoordinateHeights.Length != data.Height || data.StyleWrapLimit < 0
                    || data.CoordinateWidth <= 0 || data.CoordinatePadding < 0
                    || data.CoordinateFullWidth <= 0 || data.CoordinateFullHeight <= 0
                    || data.StyleMultiplier <= 0 || data.StyleLineSkip <= 0) continue;
                // Exact certified TileObject.Place arithmetic, not a tile-name table.
                // Random placements remain unknown; default random=-1 contributes 0.
                int style = checked(item.placeStyle * data.StyleMultiplier + data.Style);
                if (style < 0) continue;
                int line = data.StyleWrapLimit > 0 ? checked(style / data.StyleWrapLimit * data.StyleLineSkip) : 0;
                if (data.StyleWrapLimit > 0) style %= data.StyleWrapLimit;
                int baseX = checked(data.CoordinateFullWidth * (data.StyleHorizontal ? style : line));
                int baseY = checked(data.CoordinateFullHeight * (data.StyleHorizontal ? line : style));
                var cells = new JsonArray();
                for (int column = 0; column < data.Width; column++)
                {
                    int x = checked(baseX + column * (data.CoordinateWidth + data.CoordinatePadding));
                    int y = baseY;
                    for (int row = 0; row < data.Height; row++)
                    {
                        // Native writes Int16 frames; decline overflow instead of
                        // converting a large unsupported style into a false match.
                        if (x < 0 || x > short.MaxValue || y < 0 || y > short.MaxValue) return new JsonArray();
                        bool matches = aura["tileFrameConditions"]!.AsArray().OfType<JsonObject>().All(condition =>
                        {
                            int actual = condition["field"]!.GetValue<string>() switch { "frameX" => x, "frameY" => y, _ => int.MinValue };
                            int bound = condition["value"]!.GetValue<int>();
                            return condition["comparison"]!.GetValue<string>() switch
                            {
                                "less_than" => actual < bound, "less_or_equal" => actual <= bound,
                                "greater_than" => actual > bound, "greater_or_equal" => actual >= bound, _ => false
                            } && actual != int.MinValue;
                        });
                        if (matches) cells.Add(new JsonObject { ["column"] = column, ["row"] = row, ["frameX"] = x, ["frameY"] = y });
                        y = checked(y + data.CoordinateHeights[row] + data.CoordinatePadding);
                    }
                }
                if (cells.Count > 0) variants.Add(new JsonObject
                {
                    ["alternate"] = alternate, ["random"] = -1, ["matchingTileCells"] = cells,
                    ["metadataSource"] = "current_native_TileObjectData_registry",
                    ["styleHorizontal"] = data.StyleHorizontal, ["styleMultiplier"] = data.StyleMultiplier,
                    ["styleOffset"] = data.Style, ["styleWrapLimit"] = data.StyleWrapLimit,
                    ["styleLineSkip"] = data.StyleLineSkip, ["coordinateFullWidth"] = data.CoordinateFullWidth,
                    ["coordinateFullHeight"] = data.CoordinateFullHeight
                });
            }
        }
        catch { return new JsonArray(); }
        return variants;
    }
}
