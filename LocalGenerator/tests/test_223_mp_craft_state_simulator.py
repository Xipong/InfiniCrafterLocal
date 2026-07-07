"""Stage 7 — MP craft state simulator tests.

These run a Python MODEL (mp_craft_state_simulator.py) that mirrors the
server-authoritative craft logic in
ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs. The goal is to
probe server-authority invariants (cancel/timeout/dedup/refund-once) without a real
Terraria MP session. Method names reference the C# concepts they model.
"""
from __future__ import annotations

from csharp_partial_reader import read_text_with_partial_bundles
from tests.mp_craft_state_simulator import (
    CraftStateSimulator,
    Slot,
    CraftItemRef,
)


def _inv(*slots: Slot) -> list[Slot]:
    return list(slots) + [Slot() for _ in range(50 - len(slots))]


def _slot(type_: int, stack: int = 1, **kw) -> Slot:
    kw.setdefault("valid_ingredient", True)
    kw.setdefault("is_air", False)
    return Slot(type=type_, stack=stack, **kw)


def test_success_grants_item_once():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75, 3), _slot(43, 2)))  # Wood 75, Copper 43
    rid = sim.begin_client_craft_request(0)
    ok, name, msg = sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    assert ok is True, msg
    # server actually debited one of each
    player = sim.get_player(0)
    assert player.inventory[0].stack == 2  # 3-1
    assert player.inventory[1].stack == 1  # 2-1
    # server commits success result; client reveals item exactly once
    sim.server_commit_craft_result(0, rid, True, "Merged Blade", "")
    assert sim.get_player(0).revealed_item == "Merged Blade"
    assert sim.get_player(0).server_has_pending is False


def test_timeout_cancel_then_late_response_does_not_grant():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75), _slot(43)))
    rid = sim.begin_client_craft_request(0)
    sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    # client times out → sends cancel
    ok, name, msg = sim.handle_cancel_server_craft(0, rid, "client_timeout")
    assert ok is False
    ingredients_returned = len(sim.get_player(0).refunded_slots)
    assert ingredients_returned == 2, "cancel after server-side debit must refund both"
    # late server response must NOT grant an item (request was cancelled)
    sim.server_commit_craft_result(0, rid, True, "Late Item", "")
    assert sim.get_player(0).revealed_item is None


def test_cancel_after_server_debit_refunds_ingredients_once():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75), _slot(43)))
    rid = sim.begin_client_craft_request(0)
    sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    player = sim.get_player(0)
    assert player.inventory[0].stack == 0 and player.inventory[1].stack == 0
    # cancel -> refund once
    sim.handle_cancel_server_craft(0, rid, "client_cancel")
    assert len(player.refunded_slots) == 2
    # second cancel must NOT refund again
    sim.handle_cancel_server_craft(0, rid, "again")
    assert len(player.refunded_slots) == 2, "ingredients must be refunded exactly once"


def test_old_late_response_does_not_mix_with_new_request():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75), _slot(43), _slot(9), _slot(71)))  # 2 pairs
    rid1 = sim.begin_client_craft_request(0)
    sim.handle_request_server_craft(0, rid1, CraftItemRef(75), CraftItemRef(43))
    sim.handle_cancel_server_craft(0, rid1, "timeout1")
    # second craft on a NEW request id
    rid2 = sim.begin_client_craft_request(0)
    ok, name, msg = sim.handle_request_server_craft(0, rid2, CraftItemRef(9), CraftItemRef(71))
    assert ok is True
    # late response for rid1 must not be applied to rid2
    sim.server_commit_craft_result(0, rid1, True, "Old Item", "")
    player = sim.get_player(0)
    assert player.revealed_item is None or player.revealed_item != "Old Item"
    sim.server_commit_craft_result(0, rid2, True, "New Item", "")
    assert player.revealed_item == "New Item"


def test_second_craft_after_timeout_works():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75, 2), _slot(43, 2)))
    rid1 = sim.begin_client_craft_request(0)
    sim.handle_request_server_craft(0, rid1, CraftItemRef(75), CraftItemRef(43))
    sim.handle_cancel_server_craft(0, rid1, "timeout")
    assert sim.get_player(0).server_has_pending is False
    # new craft should succeed
    rid2 = sim.begin_client_craft_request(0)
    ok, name, msg = sim.handle_request_server_craft(0, rid2, CraftItemRef(75), CraftItemRef(43))
    assert ok is True, msg
    sim.server_commit_craft_result(0, rid2, True, "Second Item", "")
    assert sim.get_player(0).revealed_item == "Second Item"


def test_invalid_client_packet_cannot_craft_from_nonexistent_slots():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv())  # empty inventory
    rid = sim.begin_client_craft_request(0)
    ok, name, msg = sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    assert ok is False
    assert "первый ингредиент" in msg
    # nothing debited, nothing refunded
    assert all(s.is_air for s in sim.get_player(0).inventory)
    assert sim.get_player(0).refunded_slots == []


def test_favorited_items_are_not_spent():
    sim = CraftStateSimulator()
    fav = _slot(75, 1, favorited=True)
    ok_slot = _slot(75, 2)
    sim.set_inventory(0, _inv(fav, ok_slot, _slot(43)))
    rid = sim.begin_client_craft_request(0)
    ok, name, msg = sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    # the favorite slot must survive; the non-fav matching slot was spent instead
    assert ok is True
    inv = sim.get_player(0).inventory
    assert inv[0].favorited is True and inv[0].stack == 1  # favorite untouched
    assert inv[1].stack == 1  # 2-1 spent


def test_server_invalid_generated_items_are_not_spent():
    """A slot with valid_ingredient=False (InfiniCore.IsValidIngredient false) must not be spent."""
    sim = CraftStateSimulator()
    invalid = _slot(75, 1, valid_ingredient=False)
    valid = _slot(75, 2)
    sim.set_inventory(0, _inv(invalid, valid, _slot(43)))
    rid = sim.begin_client_craft_request(0)
    ok, name, msg = sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    assert ok is True
    inv = sim.get_player(0).inventory
    assert inv[0].stack == 1 and inv[0].valid_ingredient is False  # invalid untouched
    assert inv[1].stack == 1  # valid spent


def test_duplicate_request_returns_committed_name():
    """Re-sending the same request id after success returns a duplicate ack, no new craft."""
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75, 2), _slot(43, 2)))
    rid = sim.begin_client_craft_request(0)
    sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    sim.server_commit_craft_result(0, rid, True, "First Item", "")
    # duplicate
    ok, name, msg = sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    assert ok is True
    assert msg == "duplicate ack"
    assert name == "First Item"
    # no extra debit
    inv = sim.get_player(0).inventory
    assert inv[0].stack == 1 and inv[1].stack == 1


def test_pending_craft_blocks_new_request():
    sim = CraftStateSimulator()
    sim.set_inventory(0, _inv(_slot(75, 2), _slot(43, 2)))
    rid1 = sim.begin_client_craft_request(0)
    sim.handle_request_server_craft(0, rid1, CraftItemRef(75), CraftItemRef(43))
    # while first is pending, second request (same player) must be rejected
    rid2 = "deadbeef"
    sim.get_player(0).server_has_pending = True  # simulate server-side pending
    ok, name, msg = sim.handle_request_server_craft(0, rid2, CraftItemRef(75), CraftItemRef(43))
    assert ok is False
    assert "уже есть активный" in msg
