#nullable enable
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.Localization;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

/// <summary>
/// Session-local admin/dev unlock for independent craft lanes. It does not grant
/// ingredients, bypass validation, or author an item; every lane still spends its
/// own A+B pair and uses the normal server-authoritative commit/refund path.
/// </summary>
public sealed class MultiDevCraftCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "multidevcraft";
    public override string Usage => "/multidevcraft [2|3|off]";
    private static string ForgeText(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.StationUI." + key, args);
    public override string Description => ForgeText("CommandDescription");

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        if (caller.Player is null)
            return;
        var craftPlayer = caller.Player.GetModPlayer<InfiniCraftPlayer>();
        int requested;
        if (args.Length == 0)
        {
            requested = craftPlayer.MultiDevWindowCount switch
            {
                1 => 2,
                2 => 3,
                _ => 1,
            };
        }
        else
        {
            string value = (args[0] ?? "").Trim().ToLowerInvariant();
            requested = value switch
            {
                "off" or "0" or "1" => 1,
                "2" => 2,
                "3" => 3,
                _ => -1,
            };
        }

        if (requested < 1)
        {
            Main.NewText(ForgeText("CommandUsage"), 255, 180, 90);
            return;
        }
        if (!craftPlayer.TrySetMultiDevWindowCount(requested))
        {
            Main.NewText(ForgeText("CommandBlocked"), 255, 160, 90);
            return;
        }

        if (requested == 1)
        {
            Main.NewText(ForgeText("CommandSingle"), 160, 210, 255);
            return;
        }
        Main.NewText(ForgeText("CommandMultiple", requested), 90, 235, 255);
        Main.NewText(ForgeText("CommandPairs"), 170, 210, 255);
        CombatText.NewText(caller.Player.Hitbox, Color.Cyan, ForgeText("HearthsOpened", requested));
    }
}
