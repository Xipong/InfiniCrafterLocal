#nullable enable
using System;
using System.Globalization;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.UI;

// Read-only presentation lookup, not an ingredient reconstruction or ID migration.
// Call when rebuilding the lineage view, and cache the returned hover item there.
internal static class RecipeNativeItemResolver
{
    internal static Item? Resolve(string identity)
    {
        if (!TryGetStableName(identity, out string stable)) return null;
        int slash = stable.IndexOf('/');
        string source = stable.Substring(0, slash), name = stable.Substring(slash + 1);

        int type;
        if (source == "Terraria")
        {
            if (!ItemID.Search.TryGetId(name, out type) || type <= 0 || type >= ItemID.Count
                || !string.Equals(ItemID.Search.GetName(type), name, StringComparison.Ordinal)) return null;
        }
        else
        {
            if (!ModContent.TryFind<ModItem>(source, name, out var registered)
                || registered is GeneratedItem || !string.Equals(registered.FullName, stable, StringComparison.Ordinal)) return null;
            type = registered.Type;
        }

        // Runtime IDs can move when mods change. Require the currently loaded sample
        // to agree with the stable identity; never use recordedType as a fallback.
        if (!ContentSamples.ItemsByType.TryGetValue(type, out var sample) || sample.IsAir || sample.type != type
            || sample.ModItem is GeneratedItem) return null;
        if (source == "Terraria" ? sample.ModItem is not null
            : !string.Equals(sample.ModItem?.FullName, stable, StringComparison.Ordinal)) return null;
        return sample.Clone();
    }

    // Syntax-only key for graph de-duplication. Unknown registered content remains
    // unknown; this only identifies the same exact stable name across saved IDs.
    internal static bool TryGetStableName(string identity, out string fullName)
    {
        fullName = "";
        if (string.IsNullOrEmpty(identity) || identity.Length > 1024 || !identity.StartsWith("item:", StringComparison.Ordinal))
            return false;
        int last = identity.LastIndexOf(':');
        if (last <= 5 || !int.TryParse(identity.AsSpan(last + 1), NumberStyles.None, CultureInfo.InvariantCulture, out int recordedType)
            || recordedType <= 0) return false;

        // The producer emits fullName first, or sourceMod:internalName when absent.
        // Neither display-name slugs nor the historical numeric suffix identify a type.
        string stable = identity.Substring(5, last - 5);
        int colon = stable.IndexOf(':');
        if (colon >= 0)
        {
            if (stable.IndexOf(':', colon + 1) >= 0 || stable.Contains('/')) return false;
            stable = stable.Substring(0, colon) + "/" + stable.Substring(colon + 1);
        }
        int slash = stable.IndexOf('/');
        if (slash <= 0 || slash == stable.Length - 1 || stable.IndexOf('/', slash + 1) >= 0) return false;
        fullName = stable;
        return true;
    }

}
