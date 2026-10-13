#nullable enable
using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework.Graphics;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Native cursor preview supplies a type-wide ContentSamples Item, losing the
/// generated instance. Correct only that source argument, plus its redundant
/// static tint tail; do not patch ItemSlot or scan any foreign draw/cache.
/// </summary>
public sealed class GeneratedCursorItemPresentationSystem : ModSystem
{
    private ILHook? _hook;

    public override void Load()
    {
        if (Main.dedServ) return;
        if (_hook is not null) return;
        MethodInfo target = typeof(Main).GetMethod("DrawInterface_40_InteractItemIcon",
            BindingFlags.Instance | BindingFlags.NonPublic)
            ?? throw new NotSupportedException("Native cursor presentation owner is unavailable.");
        _hook = new ILHook(target, PatchCursor);
    }

    public override void Unload()
    {
        _hook?.Dispose();
        _hook = null;
    }

    private static bool TryGetSelectedCursorItem(out Item? selected)
    {
        selected = null;
        if (Main.dedServ || Main.myPlayer < 0 || Main.myPlayer >= Main.player.Length)
            return false;
        Player player = Main.player[Main.myPlayer];
        // Nonzero IDs are native interaction/foreign previews. Disabled icons may
        // be an old cached preview. Neither is owned by the current selected Item.
        if (player is null || !player.cursorItemIconEnabled || player.cursorItemIconID != ItemID.None
            || player.selectedItem < 0 || player.selectedItem >= player.inventory.Length)
            return false;
        Item item = player.inventory[player.selectedItem];
        if (item is null || item.IsAir || item.ModItem is not GeneratedItem generated
            || !generated.HasReadyInventorySprite())
            return false;
        selected = item;
        return true;
    }

    private static Item ResolveCursorIconItem(Item nativeSample)
        => TryGetSelectedCursorItem(out Item? selected) && selected!.type == nativeSample.type
            ? selected : nativeSample;

    private static bool OmitNativeSelectedTint()
        => TryGetSelectedCursorItem(out _);

    private static void PatchCursor(ILContext il)
    {
        var instructions = il.Body.Instructions;
        var icons = instructions.Where(i => i.OpCode == OpCodes.Call
            && i.Operand is MethodReference m && m.DeclaringType.FullName == "Terraria.UI.ItemSlot"
            && m.Name == "DrawItemIcon" && m.Parameters.Count == 7).ToArray();
        var samples = instructions.Where(i => i.OpCode == OpCodes.Callvirt
            && i.Operand is MethodReference m && m.Name == "get_Item"
            && m.DeclaringType.FullName.StartsWith("System.Collections.Generic.Dictionary`2", StringComparison.Ordinal)
            && m.ReturnType is GenericParameter { Position: 1 }).ToArray();
        var draws = instructions.Where(i => i.OpCode == OpCodes.Callvirt
            && i.Operand is MethodReference m && m.DeclaringType.FullName == typeof(SpriteBatch).FullName
            && m.Name == "Draw" && m.ReturnType.FullName == "System.Void"
            && m.Parameters.Count == 9
            && m.Parameters[0].ParameterType.FullName == typeof(Texture2D).FullName
            && m.Parameters[6].ParameterType.FullName == "System.Single").ToArray();
        if (icons.Length != 1 || samples.Length != 1 || draws.Length != 2)
            throw new NotSupportedException("Native cursor draw shape changed; no presentation patch applied.");
        Instruction sample = samples[0], tint = draws[1];
        int sampleIndex = instructions.IndexOf(sample), iconIndex = instructions.IndexOf(icons[0]);
        int tintIndex = instructions.IndexOf(tint);
        // Exact source owner, not a generic dictionary or any arbitrary texture Draw.
        bool sampleOwner = sampleIndex >= 2
            && instructions[sampleIndex - 2].OpCode == OpCodes.Ldsfld
            && instructions[sampleIndex - 2].Operand is FieldReference sf
            && sf.FullName == "System.Collections.Generic.Dictionary`2<System.Int32,Terraria.Item> Terraria.ID.ContentSamples::ItemsByType";
        // Prove the final Draw's own receiver/texture segment. An earlier ammo
        // TextureAssets.Item load must not authorize a foreign final tint array.
        var tintSegment = instructions.Take(tintIndex).Skip(instructions.IndexOf(draws[0]) + 1).ToArray();
        int receiverIndex = Array.FindLastIndex(tintSegment, i => i.OpCode == OpCodes.Ldsfld
            && i.Operand is FieldReference f && f.FullName == "Microsoft.Xna.Framework.Graphics.SpriteBatch Terraria.Main::spriteBatch");
        bool tintOwner = receiverIndex >= 0 && receiverIndex + 1 < tintSegment.Length
            && tintSegment[receiverIndex + 1].OpCode == OpCodes.Ldsfld
            && tintSegment[receiverIndex + 1].Operand is FieldReference texture
            && texture.Name == "Item" && texture.DeclaringType.FullName == "Terraria.GameContent.TextureAssets"
            && tintSegment.Any(i => i.OpCode == OpCodes.Ldfld
                && i.Operand is FieldReference f && f.FullName == "Microsoft.Xna.Framework.Color Terraria.Item::color");
        if (!sampleOwner || sampleIndex >= iconIndex || !tintOwner || tint.Next is null)
            throw new NotSupportedException("Native cursor source/tint ownership changed; no presentation patch applied.");

        // Preserve the evaluated native Item argument until only this caller's
        // exact sample is on top of the stack; all ItemSlot logic stays native.
        var cursor = new ILCursor(il);
        cursor.Goto(sample, MoveType.After);
        cursor.EmitDelegate<Func<Item, Item>>(ResolveCursorIconItem);

        // ItemSlot with the actual GeneratedItem already performs its PNG color
        // overlay. Skip only the cursor owner's extra static TextureAssets tint.
        // Incoming labels target the gate, and original foreign/native Draw remains
        // unchanged with its complete evaluated argument bundle on the false path.
        Instruction afterTint = tint.Next!;
        cursor.Goto(tint, MoveType.AfterLabel);
        cursor.EmitDelegate<Func<bool>>(OmitNativeSelectedTint);
        cursor.Emit(OpCodes.Brfalse, tint);
        for (int i = 0; i < 10; i++) cursor.Emit(OpCodes.Pop); // nine parameters + SpriteBatch receiver
        cursor.Emit(OpCodes.Br, afterTint);
        foreach (Instruction instruction in instructions)
            if (instruction.OpCode.OperandType == OperandType.ShortInlineBrTarget)
                instruction.OpCode = instruction.OpCode.Code switch {
                    Code.Br_S => OpCodes.Br, Code.Brfalse_S => OpCodes.Brfalse, Code.Brtrue_S => OpCodes.Brtrue,
                    Code.Beq_S => OpCodes.Beq, Code.Bne_Un_S => OpCodes.Bne_Un, Code.Bge_S => OpCodes.Bge,
                    Code.Bge_Un_S => OpCodes.Bge_Un, Code.Bgt_S => OpCodes.Bgt, Code.Bgt_Un_S => OpCodes.Bgt_Un,
                    Code.Ble_S => OpCodes.Ble, Code.Ble_Un_S => OpCodes.Ble_Un, Code.Blt_S => OpCodes.Blt,
                    Code.Blt_Un_S => OpCodes.Blt_Un, Code.Leave_S => OpCodes.Leave, _ => instruction.OpCode
                };
    }
}
