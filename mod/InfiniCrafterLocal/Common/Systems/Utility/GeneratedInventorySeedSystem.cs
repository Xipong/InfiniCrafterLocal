#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Extend only the native grass-seed inventory witness, not seed spawning.
/// WorldGen retains RNG, tile admission, nearest-player and multiplayer authority.
/// Never mark the shared GeneratedItem type in DropSeedsIfInInventory.
/// </summary>
public sealed class GeneratedInventorySeedSystem : ModSystem
{
    public override void Load() => On_Player.HasItem_BooleanArray += HasItem;
    public override void Unload() => On_Player.HasItem_BooleanArray -= HasItem;

    private static bool HasItem(On_Player.orig_HasItem_BooleanArray orig, Player player, bool[] types)
    {
        // Preserve all vanilla/earlier-hook positives and every unrelated set.
        if (orig(player, types)) return true;
        if (!ReferenceEquals(types, ItemID.Sets.DropSeedsIfInInventory)) return false;

        // Installed Player.HasItem(bool[]) scans [0,58), requiring stack > 0.
        // It has no player active/dead gate: native owner selection owns that.
        for (int slot = 0; slot < 58; slot++)
        {
            Item item = player.inventory[slot];
            if (item is null || item.IsAir || item.stack <= 0
                || item.ModItem is not GeneratedItem generated
                || generated.Data is not { Gameplay.CollectSeedsFromGrass: true } data
                || string.IsNullOrWhiteSpace(data.Id) || data.Id == "placeholder"
                || GeneratedItemData.IsPlayerSaveReferenceOnly(data)
                || !GeneratedItemRegistryService.IsCurrentWorldData(data)) continue;
            // Data is the instance's accepted full definition. References remain
            // inactive until existing Load/NetReceive/UpdateInventory hydration;
            // this passive query never fetches, registers, consumes or spawns.
            return true;
        }
        return false;
    }
}
