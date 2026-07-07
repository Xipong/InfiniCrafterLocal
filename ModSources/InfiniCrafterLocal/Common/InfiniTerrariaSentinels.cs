#nullable enable
using Terraria.ID;

namespace InfiniCrafterLocal.Common;

/// <summary>
/// Named sentinels for Terraria/tModLoader numeric fields that do not expose a
/// public Terraria.ID None constant. Use Terraria.ID.*.None directly whenever it exists.
/// </summary>
public static class InfiniTerrariaSentinels
{
    // BuffID currently has no BuffID.None, while Item.buffType documents 0 as the empty value.
    public const int NoBuffType = 0;

    // PrefixID starts at real prefix values and has no PrefixID.None; Item.prefix documents 0 as unprefixed.
    public const int NoPrefix = 0;

    public const int FirstValidItemType = ItemID.None + 1;
    public const int FirstValidProjectileType = ProjectileID.None + 1;
    public const int MaxSupportedItemUseStyle = ItemUseStyleID.RaiseLamp;
}
