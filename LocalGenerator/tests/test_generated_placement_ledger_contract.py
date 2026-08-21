from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: str) -> str:
    return (CS / path).read_text("utf-8", errors="ignore")


def test_placement_debit_requires_an_accepted_placement_receipt() -> None:
    """A place_item binding must not spend the stack on use intent alone.

    Vanilla reaches item consumption even when the placement attempt produced no
    tile, so the debit must be gated on a receipt written by the placement hook.
    """
    item = _read("Content/Items/GeneratedItem.cs")
    consume = item.split("public override bool ConsumeItem(")[1].split("public override")[0]

    assert "RuntimeBindingAction.PlaceItem" in consume
    assert "ConsumeAcceptedPlacementReceipt(player)" in consume
    # The placement branch must require both the authored cost and the receipt.
    assert "StackCost == 1 && ConsumeAcceptedPlacementReceipt(player)" in consume


def test_placement_uses_authored_mana_cost_without_item_effect_leaks() -> None:
    """Every use pays authored mana; only apply_item_effects exposes heal/buff fields."""
    item = _read("Content/Items/GeneratedItem.cs")

    use_item = item.split("public override bool? UseItem(")[1].split("private void ApplyItemEffects")[0]
    assert "Action.Kind != RuntimeBindingAction.PlaceItem" in use_item
    assert "RuntimeEventKind.OnUse" in use_item

    projection = item.split("private void ApplyActiveUseProjection(")[1].split("private static bool")[0]
    assert "Item.mana = Math.Max(0, Data.Gameplay.ManaCost);" in projection
    assert "bool applyingItemEffects = action.Kind == RuntimeBindingAction.ApplyItemEffects;" in projection
    assert "Data.ApplyUseEffectFields(Item, applyingItemEffects);" in projection
    apply = _read("Common/Models/GeneratedItemData.Apply.cs")
    assert "item.healLife = enabled ? Math.Max(0, Gameplay.HealLife) : 0;" in apply
    assert "item.healMana = enabled ? Math.Max(0, Gameplay.HealMana) : 0;" in apply
    assert "item.potion = enabled && Gameplay.Potion;" in apply
    assert "item.buffType = enabled ? Math.Max(0, Gameplay.BuffCode) : 0;" in apply
    assert "item.buffTime = enabled ? Math.Max(0, Gameplay.BuffTime) : 0;" in apply


def test_item_contact_is_owned_by_the_active_use_policy_lane() -> None:
    item = _read("Content/Items/GeneratedItem.cs")
    helper = item.split("private bool BindingUsesItemBodyContact(")[1].split("private bool BaseNoMeleeFor")[0]
    no_melee = item.split("private bool BaseNoMeleeFor(")[1].split("private void ApplyActiveUseProjection")[0]
    hitbox = item.split("public override void UseItemHitbox(")[1].split("public override void OnHitNPC")[0]
    on_hit = item.split("public override void OnHitNPC(")[1].split("public override void UpdateAccessory")[0]

    assert "UsePolicy.ContactDamage" in helper
    assert "RuntimeBindingAction" not in helper
    assert "TargetId" not in helper
    for active_path in (no_melee, hitbox, on_hit):
        assert "BindingUsesItemBodyContact" in active_path
        assert "PrimaryOwner" not in active_path


def test_ammo_items_stay_vanilla_consumable_for_pickammo() -> None:
    """Vanilla PickAmmo only spends ammo when Item.consumable is true.

    Direct-use consumption is separately owned by the binding usePolicy through
    ConsumeItem, so this flag must not be narrowed to the binding alone.
    """
    projection = _read("Content/Items/GeneratedItem.cs")
    apply = _read("Common/Models/GeneratedItemData.Apply.cs")

    assert "AmmoCategory.Length > 0" in projection
    assert "Gameplay.AmmoCategory.Length > 0" in apply


def test_generated_placement_ledger_is_world_persistent_and_authoritative() -> None:
    """Placed generated items must be returnable after a world reload and in MP."""
    ledger = _read("Common/Systems/GeneratedPlacementLedgerSystem.cs")

    # World persistence.
    assert "public override void SaveWorldData(" in ledger
    assert "public override void LoadWorldData(" in ledger
    assert "public override void ClearWorld(" in ledger
    # Joining clients must receive the authoritative ledger.
    assert "public override void NetSend(" in ledger
    assert "public override void NetReceive(" in ledger

    # Tile and wall cells at the same coordinate are distinct keys. Multi-tile
    # objects share one group identity so any segment returns exactly one item.
    assert "enum GeneratedPlacementLayer" in ledger
    assert "record struct GeneratedPlacementKey" in ledger
    assert "GroupId" in ledger
    assert "public override bool CanDrop(int i, int j, int type)" in ledger
    assert "class GeneratedPlacementLedgerWall : GlobalWall" in ledger
    assert "public override bool Drop(int i, int j, int type, ref int dropType)" in ledger

    # Suppressing vanilla drop and queueing the exact return is one decision.
    can_drop = ledger.split("public override bool CanDrop(")[1]
    assert "TryQueueReturn(GeneratedPlacementLayer.Tile, i, j)" in can_drop
    assert "return false;" in can_drop


def test_ledger_persists_exact_definition_and_retries_failed_delivery() -> None:
    """Registry downtime or world-item pressure cannot destroy the return identity."""
    ledger = _read("Common/Systems/GeneratedPlacementLedgerSystem.cs")

    assert "DefinitionJson" in ledger
    assert "data.ToNetworkJson()" in ledger
    assert "GeneratedItemData.FromJson" in ledger
    assert "PendingReturns" in ledger
    assert "public override void PostUpdateWorld()" in ledger
    queue = ledger.split("internal static bool TryQueueReturn(")[1].split("private static bool TrySpawnPendingReturn")[0]
    assert "Placements.Remove" in queue
    assert "PendingReturns" in queue
    spawn = ledger.split("private enum PendingSpawnOutcome")[1].split("public sealed class")[0]
    assert "ItemID." not in spawn
    assert "GeneratedItemRegistryService" in spawn
    assert "GeneratedItemData.FromJson" in spawn


def test_multiplayer_placement_reaches_the_server_ledger() -> None:
    """The client can announce coordinates, but never chooses generated identity."""
    ledger = _read("Common/Systems/GeneratedPlacementLedgerSystem.cs")
    router = _read("InfiniCrafterLocal.cs")
    packet_ids = _read("Common/InfiniNetPacketIds.cs")

    assert "NotifyGeneratedPlacement" in packet_ids
    assert "GeneratedPlacementLedgerSystem.HandlePlacementPacket" in router

    assert "AuthorizePlacement" in ledger
    assert "TryCommitAuthorizedPlacement" in ledger
    sender = ledger.split("private static void SendPlacementToServer(")[1].split("internal static void HandlePlacementPacket")[0]
    assert "generatedItemId" not in sender
    handler = ledger.split("internal static void HandlePlacementPacket(")[1].split("private static")[0]
    # The server is the only acceptor; its pending authorization owns ID/snapshot.
    assert "NetmodeID.Server" in handler
    assert "TryCommitAuthorizedPlacement" in handler
    assert "ReadString" not in handler


def test_capacity_is_reserved_for_all_concurrent_authorizations_before_world_mutation() -> None:
    ledger = _read("Common/Systems/GeneratedPlacementLedgerSystem.cs")
    authorize = ledger.split(
        "internal static bool AuthorizePlacement(\n        Player player,\n        GeneratedItemData data,\n        RuntimePlacementSpec placement,\n        int targetX,\n        int targetY)"
    )[1].split("internal static bool TryCommitAuthorizedPlacement")[0]
    assert "PendingAuthorizations.Count" in authorize
    assert "MaxCellsPerGroup" in authorize
    assert "MaxGroups" in authorize
    commit = ledger.split("private static bool TryCommitAuthorizedPlacement(")[1].split("private static List<GeneratedPlacementKey> FindCommittedCells")[0]
    assert "MaxCells - committedCells.Count" in commit
    assert "Groups.Count >= MaxGroups" in commit
