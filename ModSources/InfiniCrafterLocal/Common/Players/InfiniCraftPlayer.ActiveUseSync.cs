#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Snapshot = InfiniCrafterLocal.Content.Items.GeneratedItem.NativeUseSnapshot;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    // One revision fence per native player, not an inventory/definition cache.
    private ulong _nativeUseRevision;
    private Snapshot? _acceptedNativeUse;
    private GeneratedItem? _localProjectedItem;

    private void ClearNativeUseSync()
    {
        _nativeUseRevision = 0;
        _acceptedNativeUse = null;
        _localProjectedItem = null;
    }

    public override void PlayerConnect() => ClearNativeUseSync();
    public override void PlayerDisconnect() => ClearNativeUseSync();

    internal void PublishNativeUseProjection(GeneratedItem item, string input, bool reset = false)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || Player.whoAmI != Main.myPlayer
            || !item.HasResolvedNativeUseDefinition) return;
        int slot = Array.FindIndex(Player.inventory, 0, Math.Min(GeneratedItem.NativeUseInventorySlotCount, Player.inventory.Length), value => ReferenceEquals(value, item.Item));
        if (slot < 0 || input is not (RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse)) return;
        byte code = (byte)(input == RuntimeInputKind.AlternateUse ? 1 : 0);
        string definition = item.NativeUseDefinition;
        if (item.NativeUseProjection is Snapshot current && current.Owner == Player.whoAmI
            && current.Slot == slot && current.Token == item.PresentationToken
            && current.Input == code && current.Definition == definition
            && _acceptedNativeUse is Snapshot accepted && accepted == current) {
            if (!reset) _localProjectedItem = item;
            return;
        }
        if (item.NativeUseProjection is Snapshot prior && prior.Owner == Player.whoAmI)
            _nativeUseRevision = Math.Max(_nativeUseRevision, prior.Revision);
        var next = new Snapshot((byte)Player.whoAmI, (byte)slot, item.PresentationToken,
            checked(++_nativeUseRevision), code, definition);
        item.SetNativeUseProjection(next);
        _acceptedNativeUse = next;
        if (!reset) _localProjectedItem = item;
        // Existing owner inventory transport and relay; ordered before native Shoot.
        // This snapshot does not claim successful use, and its receiver runs no effects.
        NetMessage.SendData(MessageID.SyncEquipment, number: Player.whoAmI,
            number2: PlayerItemSlotID.Inventory0 + slot, number3: item.Item.prefix);
    }

    internal RuntimeBindingSpec? ResolveNativeUseProjection(GeneratedItem item)
    {
        if (item.InvalidNativeUseProjection || !item.HasResolvedNativeUseDefinition) return null;
        Snapshot? incoming = item.NativeUseProjection;
        if (incoming is not Snapshot value)
        {
            if (_acceptedNativeUse is Snapshot retained && retained.Owner == Player.whoAmI
                && retained.Slot == Player.selectedItem && retained.Token == item.PresentationToken
                && retained.Definition == item.NativeUseDefinition)
                value = retained;
            else return item.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse);
        }
        if (!value.Valid || value.Owner != Player.whoAmI || value.Slot != Player.selectedItem
            || value.Token != item.PresentationToken || value.Definition != item.NativeUseDefinition) return null;
        if (_acceptedNativeUse is Snapshot accepted && value.Revision <= accepted.Revision)
        {
            // Message5 reconstructs Item before NetReceive. Retain the accepted selector
            // across an older replacement of the SAME physical definition, not its data.
            if (accepted.Owner != value.Owner || accepted.Slot != value.Slot || accepted.Token != value.Token
                || accepted.Definition != value.Definition) return null;
            value = accepted;
        }
        RuntimeBindingSpec? binding = item.Data.RuntimeProgram.BindingForInput(value.InputName);
        if (binding is null) return null;
        _acceptedNativeUse = value;
        _nativeUseRevision = Math.Max(_nativeUseRevision, value.Revision);
        item.SetNativeUseProjection(value);
        item.ApplySynchronizedUseProjection(binding);
        return binding;
    }

    private void ResetDepartedNativeUseProjection()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || Player.whoAmI != Main.myPlayer) return;
        if (_localProjectedItem is not GeneratedItem previous) return;
        if (!Player.dead && ReferenceEquals(Player.HeldItem, previous.Item)) return;
        RuntimeBindingSpec? primary = previous.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse);
        if (primary is not null) {
            previous.ApplySynchronizedUseProjection(primary);
            PublishNativeUseProjection(previous, RuntimeInputKind.PrimaryUse, reset: true);
        }
        _localProjectedItem = null;
    }

    private void RefreshNativeUseProjectionBeforeItemCheck()
    {
        ResetDepartedNativeUseProjection();
        if (Main.netMode != NetmodeID.SinglePlayer && Player.whoAmI != Main.myPlayer
            && Player.HeldItem.ModItem is GeneratedItem item)
            ResolveNativeUseProjection(item);
    }
}
