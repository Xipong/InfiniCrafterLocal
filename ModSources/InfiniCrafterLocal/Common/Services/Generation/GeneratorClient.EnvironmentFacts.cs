#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;

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
        if (!moduleVerified || item.ModItem is not null || item.type <= 0 || item.type >= ItemID.Count)
            return null;
        var facts = new JsonObject();
        var auras = new JsonArray();
        var candidates = JsonNode.Parse(NativeEnvironmentFactsCatalog.AuraJson)!.AsArray().OfType<JsonObject>()
            .Where(row => row["tileId"]!.GetValue<int>() == item.createTile).ToArray();
        // Shared tile types can carry unrelated style-specific mechanics. Until
        // placement frames are certified, decline ambiguous or nonzero styles.
        if (item.placeStyle == 0 && candidates.Select(row => row["sceneFlag"]!.GetValue<string>()).Distinct().Count() == 1)
            foreach (var row in candidates) auras.Add(row.DeepClone());
        if (auras.Count > 0)
        {
            facts["placedTileAuras"] = auras;
            facts["placeStyle"] = item.placeStyle;
            facts["activation"] = "A placed active tile must be inside the native rectangular buff scan and satisfy the stated tile-cell frame predicates. Item inventory presence is not activation. Predicates describe tile cells, not an inferred item placeStyle-to-frame mapping; styles outside them are not asserted to grant the aura.";
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
}
