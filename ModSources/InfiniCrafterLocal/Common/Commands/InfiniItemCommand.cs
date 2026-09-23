// Dev-only applied-vs-authored debug command for generated items.
// Usage: /infiniitem trace        — show LastAppliedTrace for the held item
//        /infiniitem trace <inv>  — show for inventory slot (1-58), 0 = held
//        /infiniitem              — short help
// No gameplay effect. Does not modify items. Only reads LastAppliedTrace
// that ApplyToItem already populated. Non-generated items print "not generated".

using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using System.Text;

namespace InfiniCrafterLocal.Common.Commands;

public sealed class InfiniItemCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infiniitem";
    public override string Usage => "/infiniitem [trace [held|<1-58>]]";
    public override string Description => "Dev-only: show applied-trace for a generated InfiniCraft item.";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        if (args.Length == 0 || args[0] == "help")
        {
            Main.NewText("/infiniitem trace [held|<slot 1-58>]  — show applied vs authored fields", 160, 220, 255);
            return;
        }

        if (args[0] != "trace")
        {
            Main.NewText($"Unknown subcommand '{args[0]}'. Usage: /infiniitem trace [held|<slot>]", 255, 120, 120);
            return;
        }

        // Resolve the item to inspect: held by default, or an inventory slot.
        Player player = Main.LocalPlayer;
        Item item;
        if (args.Length >= 2 && int.TryParse(args[1], out int slotArg) && slotArg >= 1 && slotArg <= 58)
            item = player.inventory[slotArg - 1];
        else
            item = player.HeldItem ?? new Item();

        if (item is null || item.IsAir)
        {
            Main.NewText("No item to inspect.", 255, 200, 120);
            return;
        }

        GeneratedItemData? data = null;
        if (item.ModItem is GeneratedItem generated)
            data = generated.Data;

        if (data is null)
        {
            Main.NewText($"'{item.Name}' is not a generated InfiniCraft item.", 200, 200, 200);
            return;
        }

        var sb = new StringBuilder();
        sb.AppendLine($"[InfiniItem] {data.Id} — {data.Name}");
        sb.AppendLine($"  category={data.Category}  kind={data.Gameplay?.Kind ?? "?"}  damageClass={data.Gameplay?.DamageClass ?? "?"}");

        // Authored numbers (what the Python generator wrote).
        sb.AppendLine("  [authored]");
        sb.AppendLine($"    damage={data.Gameplay?.Damage}  useTime={data.Gameplay?.UseTime}  useAnim={data.Gameplay?.UseAnimation}");
        sb.AppendLine($"    knockback={data.Gameplay?.Knockback}  rare={data.Gameplay?.Rarity}  value={data.Gameplay?.Value}c");
        sb.AppendLine($"    runtime={data.RuntimeProgram.ApiVersion}  entities={data.RuntimeProgram.Entities.Length}  bindings={data.RuntimeProgram.Bindings.Length}");
        foreach (RuntimeEntitySpec entity in data.RuntimeProgram.Entities)
            sb.AppendLine($"    entity {entity.Id}: kind={entity.Kind} move={entity.Movement.Name}/{entity.Movement.Code} controller={entity.Controller.Name}/{entity.Controller.Code} events={entity.Events.Length}");
        foreach (RuntimeBindingSpec binding in data.RuntimeProgram.Bindings)
            sb.AppendLine($"    binding {binding.Id}: {binding.Input} -> {binding.UsePolicy.Action.Kind}({binding.UsePolicy.Action.TargetId}), stackCost={binding.UsePolicy.StackCost}, contactDamage={binding.UsePolicy.ContactDamage}");
        if (data.Armor?.Enabled == true)
            sb.AppendLine($"    armor.defense={data.Armor.Defense}  slot={data.Armor.Slot}");
        if (data.Accessory?.Enabled == true)
        {
            sb.AppendLine($"    acc.genericDamage={data.Accessory.GenericDamage}  genericCrit={data.Accessory.GenericCrit}");
            sb.AppendLine($"    acc.moveSpeed={data.Accessory.MovementSpeed}  endurance={data.Accessory.Endurance}  aggro={data.Accessory.Aggro}");
        }

        // Last successful projection of this definition; not later prefix/global/player changes.
        string? applied = data.LastAppliedTrace;
        sb.AppendLine("  [last ApplyToItem snapshot; before later hooks/prefix]");
        if (string.IsNullOrEmpty(applied))
            sb.AppendLine("    (No ApplyToItem snapshot on this definition; clones/load may not have been applied yet)");
        else
            sb.AppendLine("    " + applied);

        Main.NewTextMultiline(sb.ToString().TrimEnd(), c: new Color(180, 230, 255));
    }
}
