#nullable enable
using InfiniCrafterLocal.Common.Models;
using System;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

/// <summary>
/// Dedicated armor proxies for generated JSON-backed armor.
///
/// tModLoader armor visuals/equip routing are tied to the static ModItem type and its
/// AutoloadEquip texture slot, not to per-instance JSON.  The ordinary GeneratedItem
/// remains the generic item/weapon container; these three proxy item types provide the
/// fixed Head/Body/Legs equip slots while preserving the same GeneratedItemData payload.
/// </summary>
[AutoloadEquip(EquipType.Head)]
public sealed class GeneratedHeadArmor : GeneratedItem
{
    public static bool CanRepresent(GeneratedItemData? data) => GeneratedArmorItemTypes.IsArmorSlot(data, "head");
}

[AutoloadEquip(EquipType.Body)]
public sealed class GeneratedBodyArmor : GeneratedItem
{
    public static bool CanRepresent(GeneratedItemData? data) => GeneratedArmorItemTypes.IsArmorSlot(data, "body");
}

[AutoloadEquip(EquipType.Legs)]
public sealed class GeneratedLegsArmor : GeneratedItem
{
    public static bool CanRepresent(GeneratedItemData? data) => GeneratedArmorItemTypes.IsArmorSlot(data, "legs");
}

public static class GeneratedArmorItemTypes
{
    public static bool CanRepresent(GeneratedItemData? data)
        => GeneratedHeadArmor.CanRepresent(data)
        || GeneratedBodyArmor.CanRepresent(data)
        || GeneratedLegsArmor.CanRepresent(data);

    public static int ItemTypeFor(GeneratedItemData data)
    {
        string slot = (data?.Armor?.Slot ?? "").Trim().ToLowerInvariant();
        return slot switch
        {
            "head" => ModContent.ItemType<GeneratedHeadArmor>(),
            "legs" => ModContent.ItemType<GeneratedLegsArmor>(),
            _ => ModContent.ItemType<GeneratedBodyArmor>(),
        };
    }

    public static bool IsArmorSlot(GeneratedItemData? data, string slot)
    {
        var armor = data?.Armor;
        if (armor is null || !armor.Enabled)
            return false;
        return string.Equals((armor.Slot ?? "body").Trim(), slot, StringComparison.OrdinalIgnoreCase);
    }
}
