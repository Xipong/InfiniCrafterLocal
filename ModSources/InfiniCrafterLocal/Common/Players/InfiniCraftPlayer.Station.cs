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
// In singleplayer the slots own one-item escrows. In multiplayer they are
// non-owning selections until the server atomically reserves matching inventory
// units. This keeps ingredient/refund semantics separate from generated authoring
// and prevents vanilla cursor sync from racing a second client-side debit.
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
        if (HasPendingCraft || Main.mouseItem is null || Main.mouseItem.IsAir || !InfiniCore.IsValidIngredient(Main.mouseItem))
            return false;

        ref Item target = ref InputSlot(index);
        if (target is not null && !target.IsAir)
            return false;

        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            // A multiplayer station input is a server-reserved selection, not a
            // second inventory container. Keep the real stack on the cursor until
            // the player returns it to vanilla inventory; the server consumes the
            // authoritative slot only after RequestServerCraft arrives.
            target = Main.mouseItem.Clone();
            target.stack = 1;
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
        if (HasPendingCraft || Main.mouseItem is null || !Main.mouseItem.IsAir)
            return false;

        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir)
            return false;

        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            // Non-owning selection: clearing it must not mint a second item.
            slot.TurnToAir();
            return true;
        }

        Main.mouseItem = slot.Clone();
        slot.TurnToAir();
        return true;
    }

    public bool TryClearInputToInventory(int index)
    {
        if (HasPendingCraft)
            return false;
        ref Item slot = ref InputSlot(index);
        if (slot is null || slot.IsAir)
            return false;
        if (Main.netMode != NetmodeID.MultiplayerClient)
            RefundOne(slot);
        slot.TurnToAir();
        return true;
    }

    public bool TryClearAllInputsToInventory()
    {
        if (HasPendingCraft)
            return false;
        bool changed = false;
        if (TryClearInputToInventory(0)) changed = true;
        if (TryClearInputToInventory(1)) changed = true;
        return changed;
    }

    public bool TryStartCraftFromStation()
    {
        if (!CanStartStationCraft)
            return false;

        if (Main.netMode == NetmodeID.MultiplayerClient && Main.mouseItem is not null && !Main.mouseItem.IsAir)
        {
            Main.NewText("InfiniCraft: сначала верните выбранный предмет с курсора в инвентарь", 255, 190, 90);
            return false;
        }

        Item a = InputA.Clone();
        Item b = InputB.Clone();

        InputA.TurnToAir();
        InputB.TurnToAir();

        // Multiplayer clients do not run LocalGenerator/LLM/Z-Image locally.
        // They only send a compact craft intent to the Terraria host/server; the
        // host reconstructs the parent Items and performs the actual item dump +
        // generation on its own LocalGenerator, then spawns the finished item back.
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            if (!BeginRemoteServerCraft(a, b))
                return false;
            return true;
        }

        var request = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.Prepare(a, b, Player);

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
        if (HasInputA)
        {
            if (Main.netMode != NetmodeID.MultiplayerClient)
                RefundOne(InputA);
            InputA.TurnToAir();
        }
        if (HasInputB)
        {
            if (Main.netMode != NetmodeID.MultiplayerClient)
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
