#nullable enable
using System.IO;
using InfiniCrafterLocal.Content.Items;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    // Keep the literal NBT value, including a malformed noncompound. A bad prefix
    // must not erase material ownership or be silently converted to prefix zero.
    private static TagCompound? ReadPlacementPrefixEnvelope(TagCompound row)
        => row.ContainsKey("nativePrefix")
            ? new TagCompound { ["nativePrefix"] = ((TagCompound)row.Clone())["nativePrefix"] }
            : null;

    private static void WritePlacementPrefixEnvelope(TagCompound row, TagCompound? envelope)
    {
        if (envelope is not null)
            row["nativePrefix"] = ((TagCompound)envelope.Clone())["nativePrefix"];
    }

    private static int ResolvePlacementPrefixEnvelope(TagCompound? envelope)
    {
        if (envelope is null) return GeneratedItem.ResolvePlacementPrefix(null);
        if (envelope["nativePrefix"] is not TagCompound prefix)
            throw new InvalidDataException("Placement prefix must be a compound identity");
        return GeneratedItem.ResolvePlacementPrefix(prefix);
    }
}
