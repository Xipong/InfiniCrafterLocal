#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

// AGENT MAP: explicit two-slot station UI/inventory transfer logic.
// The slots own one-item escrows in every net mode. Multiplayer deposits move one
// unit through Terraria's synchronized mouse slot 58 into matching server-owned
// A/B state before crafting can start.
public sealed partial class InfiniCraftPlayer
{

    private static Item NewAirItem()
    {
        var item = new Item();
        item.TurnToAir();
        return item;
    }

    public bool TryPutMouseItemIntoInput(int index)
    {
        if (HasPendingCraft || HasPendingStationEscrowOperation || Main.mouseItem is null || Main.mouseItem.IsAir || !InfiniCore.IsValidIngredient(Main.mouseItem))
            return false;

        ref Item target = ref InputSlot(index);
        if (target is not null && !target.IsAir)
            return false;

        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            // Whether the item came from normal inventory or an open Void Bag,
            // Terraria exposes it through mouse slot 58. Send that exact vanilla
            // slot state first; the following mod packet atomically moves one unit
            // into the server-owned A/B escrow.
            if (Player.inventory.Length <= 58)
                return false;
            Player.inventory[58] = Main.mouseItem.Clone();
            Player.inventory[58].NetStateChanged();
            NetMessage.SendData(MessageID.SyncEquipment, -1, -1, null, Player.whoAmI, 58);
            target = Main.mouseItem.Clone();
            target.stack = 1;
            Main.mouseItem.stack--;
            if (Main.mouseItem.stack <= 0)
                Main.mouseItem.TurnToAir();
            Player.inventory[58] = Main.mouseItem.Clone();
            if (!SendStationEscrowRequest(StationEscrowAction.Deposit, index, target))
            {
                RestoreRejectedLocalDeposit(index);
                return false;
            }
            return true;
        }

        target = Main.mouseItem.Clone();
        target.stack = 1;
        Main.mouseItem.stack--;
        if (Main.mouseItem.stack <= 0)
            Main.mouseItem.TurnToAir();
        return true;
    }

    public bool TryTakeInputToMouse(int index)
    {
        if (HasPendingCraft || HasPendingStationEscrowOperation || Main.mouseItem is null || !Main.mouseItem.IsAir)
            return false;

        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir)
            return false;

        if (Main.netMode == NetmodeID.MultiplayerClient)
            return SendStationEscrowRequest(StationEscrowAction.TakeToMouse, index, slot);

        Main.mouseItem = slot.Clone();
        slot.TurnToAir();
        return true;
    }

    public bool TryClearInputToInventory(int index)
    {
        if (HasPendingCraft || HasPendingStationEscrowOperation)
            return false;
        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir)
            return false;
        if (Main.netMode == NetmodeID.MultiplayerClient)
            return SendStationEscrowRequest(StationEscrowAction.ReturnOne, index, slot);
        RefundOne(slot);
        slot.TurnToAir();
        return true;
    }

    public bool TryClearAllInputsToInventory()
    {
        if (HasPendingCraft || HasPendingStationEscrowOperation)
            return false;
        if (Main.netMode == NetmodeID.MultiplayerClient)
            return HasAnyInput && SendStationEscrowRequest(StationEscrowAction.ReturnAll, -1, NewAirItem());
        bool changed = false;
        if (TryClearInputToInventory(0)) changed = true;
        if (TryClearInputToInventory(1)) changed = true;
        return changed;
    }

    public bool TryStartCraftFromStation()
    {
        if (!CanStartStationCraft)
            return false;

        Item a = InputA.Clone();
        Item b = InputB.Clone();

        // Multiplayer clients do not run LocalGenerator/LLM/Z-Image locally.
        // They only send a compact craft intent to the Terraria host/server; the
        // host reconstructs the parent Items and performs the actual item dump +
        // generation on its own LocalGenerator, then spawns the finished item back.
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            if (!BeginRemoteServerCraft(a, b))
                return false;
            InputA.TurnToAir();
            InputB.TurnToAir();
            return true;
        }

        InputA.TurnToAir();
        InputB.TurnToAir();

        GeneratorClient.PreparedGenerationRequest request;
        try
        {
            request = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.Prepare(a, b, Player);
        }
        catch
        {
            RefundOne(a);
            RefundOne(b);
            return false;
        }

        if (!BeginCraft(request, $"{request.ParentA} + {request.ParentB}"))
        {
            RefundOne(a);
            RefundOne(b);
            return false;
        }
        return true;
    }

    private ref Item InputSlot(int index)
    {
        if (index == 0) return ref InputA;
        return ref InputB;
    }


    public void ReturnStationInputs()
    {
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            if (HasAnyInput && !HasPendingStationEscrowOperation)
                SendStationEscrowRequest(StationEscrowAction.ReturnAll, -1, NewAirItem());
            return;
        }
        if (HasInputA)
        {
            RefundOne(InputA);
            InputA.TurnToAir();
        }
        if (HasInputB)
        {
            RefundOne(InputB);
            InputB.TurnToAir();
        }
    }

    private void RefundIngredients()
    {
        if (_request is null)
            return;

        RefundOne(_request.RefundA);
        RefundOne(_request.RefundB);
    }


    private void RefundOne(Item original)
    {
        if (original is null || original.IsAir || original.stack <= 0)
            return;

        Item refund = original.Clone();
        refund.stack = 1;

        // Prefer exact inventory return. First merge into compatible stacks, then use
        // an empty slot. Dropping into the world is last-resort only; during world exit
        // the SaveData refund backup protects the item from vanishing.
        for (int i = 0; i < 58; i++)
        {
            Item slot = Player.inventory[i];
            if (slot is null || slot.IsAir || slot.type != refund.type || slot.stack >= slot.maxStack)
                continue;
            // Only merge plain vanilla stacks. Generated/modded items may share a type
            // while carrying different serialized data, so they must keep exact slots.
            if (slot.ModItem is not null || refund.ModItem is not null)
                continue;

            int move = Math.Min(refund.stack, slot.maxStack - slot.stack);
            if (move <= 0)
                continue;
            slot.stack += move;
            refund.stack -= move;
            SyncRefundedInventorySlot(i);
            if (refund.stack <= 0)
                return;
        }

        for (int i = 0; i < 58; i++)
        {
            if (Player.inventory[i].IsAir)
            {
                Player.inventory[i] = refund;
                SyncRefundedInventorySlot(i);
                return;
            }
        }

        int index = Item.NewItem(Player.GetSource_Misc("InfiniCraftRefund"), Player.Hitbox, refund.type, refund.stack);
        if (index >= 0)
        {
            Main.item[index] = refund;
            Main.item[index].position = Player.Center;
            Main.item[index].active = true;
            if (Main.netMode != NetmodeID.SinglePlayer)
                NetMessage.SendData(MessageID.SyncItem, -1, -1, null, index);
        }
    }

    private void SyncRefundedInventorySlot(int slotIndex)
    {
        if (slotIndex < 0 || slotIndex >= Player.inventory.Length)
            return;
        Player.inventory[slotIndex].NetStateChanged();
        if (Main.netMode == NetmodeID.Server)
            NetMessage.SendData(MessageID.SyncEquipment, -1, -1, null, Player.whoAmI, slotIndex);
    }

}
