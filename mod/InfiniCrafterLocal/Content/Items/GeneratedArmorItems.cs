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
/// EquipFrameEffects is dispatched for the displayed texture after vanilla vanity
/// selection. Only the visual player slot is neutralized: the normal hair, clothes
/// and hands stay visible under the single equip_overlay badge. PlayerFrame rebuilds
/// these visual slots on the next frame; inventory slots, stats and shared ArmorIDs
/// are never changed. Transparent native-sized sheets are registration carriers,
/// not substitutes for the required per-instance artwork.
/// </summary>
[AutoloadEquip(EquipType.Head)]
public sealed class GeneratedHeadArmor : GeneratedItem
{
    public static bool CanRepresent(GeneratedItemData? data) => GeneratedArmorItemTypes.IsArmorSlot(data, "head");

    public override void EquipFrameEffects(Player player, EquipType type)
    {
        if (type == EquipType.Head && Item.headSlot > 0 && player.head == Item.headSlot)
            player.head = 0;
    }
}

[AutoloadEquip(EquipType.Body)]
public sealed class GeneratedBodyArmor : GeneratedItem
{
    public static bool CanRepresent(GeneratedItemData? data) => GeneratedArmorItemTypes.IsArmorSlot(data, "body");

    public override void EquipFrameEffects(Player player, EquipType type)
    {
        if (type == EquipType.Body && Item.bodySlot > 0 && player.body == Item.bodySlot)
            player.body = 0;
    }
}

[AutoloadEquip(EquipType.Legs)]
public sealed class GeneratedLegsArmor : GeneratedItem
{
    public static bool CanRepresent(GeneratedItemData? data) => GeneratedArmorItemTypes.IsArmorSlot(data, "legs");

    public override void EquipFrameEffects(Player player, EquipType type)
    {
        if (type == EquipType.Legs && Item.legSlot > 0 && player.legs == Item.legSlot)
            player.legs = 0;
    }
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
