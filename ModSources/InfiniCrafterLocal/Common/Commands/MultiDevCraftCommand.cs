#nullable enable
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using System;
using Terraria;
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
    public override string Description => "Unlock 2 or 3 independent InfiniCraft windows pinned to LLM 1/2/3.";

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
            Main.NewText("Usage: /multidevcraft [2|3|off]", 255, 180, 90);
            return;
        }
        if (!craftPlayer.TrySetMultiDevWindowCount(requested))
        {
            Main.NewText("Multi-dev: сначала заверши крафт/забери предметы из скрываемого окна.", 255, 160, 90);
            return;
        }

        if (requested == 1)
        {
            Main.NewText("Multi-dev выключен: одно обычное окно крафта.", 160, 210, 255);
            return;
        }
        Main.NewText($"Multi-dev разблокирован: {requested} независимых окна · LLM 1..{requested}.", 90, 235, 255);
        Main.NewText("Каждому окну нужны свои два предмета. LLM 2/3 настраиваются во вкладке Multi-dev GUI.", 170, 210, 255);
        CombatText.NewText(caller.Player.Hitbox, Color.Cyan, $"MULTI-DEV ×{requested}");
    }
}
