#nullable enable
using System.Collections.Generic;
using System.Reflection;
using Terraria;
using Terraria.GameInput;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    private const string AtlasScrollOwner = "InfiniCrafterLocal: Atlas";
    // tML exposes acquisition but no public release API. Autopause may keep
    // the owner list across frames, so close/coverage must remove our marker.
    private static readonly FieldInfo? NativeScrollOwners = typeof(PlayerInput).GetField(
        "MouseInModdedUI", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);

    private static bool OwnsMouse => IsOpen && Main.playerInventory && !Main.gameMenu
        && Main.LocalPlayer is { active: true, dead: false } player
        && ReferenceEquals(_sessionOwner, player) && _sessionWorld == Main.worldID && !IsCovered();

    internal static bool BlocksItemUse(Player player)
        => ReferenceEquals(player, Main.LocalPlayer) && OwnsMouse;

    private static void UpdateModalMouseOwnership()
    {
        if (!OwnsMouse)
        {
            ReleaseModalMouseOwnership();
            return;
        }
        Main.LocalPlayer.mouseInterface = true;
        PlayerInput.LockVanillaMouseScroll(AtlasScrollOwner);
    }

    private static void ReleaseModalMouseOwnership()
    {
        if (NativeScrollOwners?.GetValue(null) is List<string> owners)
            owners.RemoveAll(name => name == AtlasScrollOwner);
        // Mouse flags and raw buttons also belong to other input consumers.
    }
}