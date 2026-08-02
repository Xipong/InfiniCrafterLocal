"""Behavioral contracts for the server-owned two-slot MP station escrow."""
from __future__ import annotations

from tests.mp_craft_state_simulator import CraftItemRef, CraftStateSimulator, Slot


def _slot(type_: int, stack: int = 1, *, prefix: int = 0, generated_id: str = "", valid: bool = True) -> Slot:
    return Slot(
        type=type_,
        stack=stack,
        prefix=prefix,
        generated_id=generated_id,
        is_air=False,
        valid_ingredient=valid,
    )


def _deposit(sim: CraftStateSimulator, player_id: int, index: int, item: Slot, *, origin: str) -> CraftItemRef:
    ref = CraftItemRef(item.type, item.prefix, item.generated_id)
    sim.set_mouse_item(player_id, item, origin=origin)
    ok, error = sim.deposit_server_mouse_item(player_id, index, ref)
    assert ok, error
    return ref


def _deposit_pair(sim: CraftStateSimulator, player_id: int = 0) -> tuple[CraftItemRef, CraftItemRef]:
    a = _deposit(sim, player_id, 0, _slot(75), origin="inventory")
    b = _deposit(sim, player_id, 1, _slot(43), origin="inventory")
    return a, b


def _contract_check_deposit_moves_exact_mouse_unit_into_server_station() -> None:
    sim = CraftStateSimulator()
    item_ref = _deposit(sim, 0, 0, _slot(75, 3), origin="inventory")
    player = sim.get_player(0)
    assert item_ref == CraftItemRef(75)
    assert player.station[0].type == 75 and player.station[0].stack == 1
    assert player.mouse_slot_58.type == 75 and player.mouse_slot_58.stack == 2


def _contract_check_open_void_bag_uses_same_mouse58_boundary_and_needs_no_inventory_return() -> None:
    sim = CraftStateSimulator()
    player = sim.get_player(0)
    sim.set_mouse_item(0, _slot(166, 3), origin="void_bag_bank4")
    ref = CraftItemRef(166)
    assert sim.deposit_server_mouse_item(0, 0, ref)[0]
    assert sim.deposit_server_mouse_item(0, 1, ref)[0]
    assert player.last_mouse_origin == "void_bag_bank4"
    assert player.mouse_slot_58.stack == 1  # holding the remainder must not block Craft
    rid = sim.begin_client_craft_request(0)
    ok, _, message = sim.handle_request_server_craft(0, rid, ref, ref)
    assert ok, message


def _contract_check_client_ref_cannot_craft_without_matching_server_escrow() -> None:
    sim = CraftStateSimulator()
    rid = sim.begin_client_craft_request(0)
    ok, _, message = sim.handle_request_server_craft(0, rid, CraftItemRef(75), CraftItemRef(43))
    assert not ok
    assert "escrow" in message
    assert sim.get_player(0).refunded_slots == []


def _contract_check_generated_identity_is_validated_at_deposit_and_start() -> None:
    sim = CraftStateSimulator()
    sim.set_mouse_item(0, _slot(999, generated_id="g_real"), origin="void_bag_bank4")
    ok, _ = sim.deposit_server_mouse_item(0, 0, CraftItemRef(999, generated_id="g_fake"))
    assert not ok
    assert sim.get_player(0).station[0].is_air


def _contract_check_success_consumes_station_once_and_reveals_once() -> None:
    sim = CraftStateSimulator()
    a_ref, b_ref = _deposit_pair(sim)
    rid = sim.begin_client_craft_request(0)
    ok, _, message = sim.handle_request_server_craft(0, rid, a_ref, b_ref)
    assert ok, message
    player = sim.get_player(0)
    assert [(slot.type, slot.stack) for slot in player.station] == [(75, 1), (43, 1)]
    assert len(player.active_refunds) == 2
    sim.server_commit_craft_result(0, rid, True, "Merged Blade")
    assert player.revealed_item == "Merged Blade"
    assert all(slot.is_air for slot in player.station)
    assert player.active_refunds == []
    assert player.refunded_slots == []


def _contract_check_cancel_refunds_exact_escrow_once_and_late_commit_is_ignored() -> None:
    sim = CraftStateSimulator()
    a_ref, b_ref = _deposit_pair(sim)
    rid = sim.begin_client_craft_request(0)
    assert sim.handle_request_server_craft(0, rid, a_ref, b_ref)[0]
    sim.handle_cancel_server_craft(0, rid, "client_timeout")
    player = sim.get_player(0)
    assert player.refunded_slots == []
    assert [(item.type, item.stack) for item in player.station] == [(75, 1), (43, 1)]
    sim.handle_cancel_server_craft(0, rid, "again")
    assert player.refunded_slots == []
    sim.server_commit_craft_result(0, rid, True, "Late Item")
    assert player.revealed_item != "Late Item"


def _contract_check_take_to_mouse_and_clear_return_exact_station_items() -> None:
    sim = CraftStateSimulator()
    ref = _deposit(sim, 0, 0, _slot(75), origin="inventory")
    player = sim.get_player(0)
    assert sim.take_server_escrow_to_mouse(0, 0)[0]
    assert player.station[0].is_air and player.mouse_slot_58.type == 75
    assert sim.deposit_server_mouse_item(0, 1, ref)[0]
    assert sim.return_all_server_escrow(0) == 1
    assert [(item.type, item.stack) for item in player.refunded_slots] == [(75, 1)]


def _contract_check_late_escrow_retry_replays_older_cached_result_without_mutation() -> None:
    sim = CraftStateSimulator()
    item_ref = CraftItemRef(75)
    sim.set_mouse_item(0, _slot(75, 2), origin="inventory")
    assert sim.handle_station_deposit(0, "op1", 0, item_ref)[0]
    assert sim.return_all_server_escrow(0) == 1

    # Complete a newer operation, then make the old input representable again.
    sim.set_mouse_item(0, _slot(75, 2), origin="inventory")
    assert sim.handle_station_deposit(0, "op2", 1, item_ref)[0]
    player = sim.get_player(0)
    before_mouse_stack = player.mouse_slot_58.stack
    assert player.station[0].is_air

    assert sim.handle_station_deposit(0, "op1", 0, item_ref)[0]
    assert player.station[0].is_air
    assert player.mouse_slot_58.stack == before_mouse_stack


def _contract_check_disconnect_reconnect_replays_by_stable_client_token() -> None:
    sim = CraftStateSimulator()
    token = "stable-client-token"
    sim.connect_player(0, token)
    item_ref = CraftItemRef(75)
    sim.set_mouse_item(0, _slot(75, 2), origin="inventory")
    assert sim.handle_station_deposit(0, "op-disconnect", 0, item_ref)[0]
    sim.disconnect_player(0)

    player = sim.connect_player(7, token)
    assert player.station[0].type == 75
    before_station = [(slot.type, slot.stack) for slot in player.station]
    before_mouse = (player.mouse_slot_58.type, player.mouse_slot_58.stack)
    assert sim.handle_station_deposit(7, "op-disconnect", 0, item_ref)[0]
    assert [(slot.type, slot.stack) for slot in player.station] == before_station
    assert (player.mouse_slot_58.type, player.mouse_slot_58.stack) == before_mouse


def _contract_check_dedupe_and_pending_gate_do_not_consume_again() -> None:
    sim = CraftStateSimulator()
    a_ref, b_ref = _deposit_pair(sim)
    rid = sim.begin_client_craft_request(0)
    assert sim.handle_request_server_craft(0, rid, a_ref, b_ref)[0]
    pending_rid = "other"
    ok, _, message = sim.handle_request_server_craft(0, pending_rid, a_ref, b_ref)
    assert not ok and "уже есть активный" in message
    sim.server_commit_craft_result(0, rid, True, "First Item")
    ok, name, message = sim.handle_request_server_craft(0, rid, a_ref, b_ref)
    assert ok and name == "First Item" and message == ""


def _contract_check_commit_ack_loss_reconnect_replays_without_parent_refund() -> None:
    sim = CraftStateSimulator()
    token = "stable-client-token"
    sim.connect_player(0, token)
    a_ref, b_ref = _deposit_pair(sim)
    rid = sim.begin_client_craft_request(0)
    assert sim.handle_request_server_craft(0, rid, a_ref, b_ref)[0]
    sim.server_commit_craft_result(0, rid, True, "Durable Blade", deliver_to_client=False)
    sim.disconnect_player(0)

    player = sim.connect_player(7, token)
    ok, name, _ = sim.reconcile_pending_craft(7, a_ref, b_ref)
    assert ok and name == "Durable Blade"
    assert player.refunded_slots == []
    assert all(slot.is_air for slot in player.station)
    assert not player.awaiting_server_commit


def _contract_check_server_restart_replays_failure_with_inputs_still_in_station() -> None:
    sim = CraftStateSimulator()
    token = "stable-restart-token"
    sim.connect_player(0, token)
    a_ref, b_ref = _deposit_pair(sim)
    rid = sim.begin_client_craft_request(0)
    assert sim.handle_request_server_craft(0, rid, a_ref, b_ref)[0]
    sim.restart_server()
    sim.disconnect_player(0)

    player = sim.connect_player(9, token)
    ok, _, message = sim.reconcile_pending_craft(9, a_ref, b_ref)
    assert not ok and "inputs remain in station" in message
    assert [(item.type, item.stack) for item in player.station] == [(75, 1), (43, 1)]
    assert player.refunded_slots == []
    assert not player.awaiting_server_commit


# One collected item; ordered checks preserve scenario-level tracebacks without pytest noise.
def test_mp_craft_state_simulator_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            "_contract_check_deposit_moves_exact_mouse_unit_into_server_station",
            "_contract_check_open_void_bag_uses_same_mouse58_boundary_and_needs_no_inventory_return",
            "_contract_check_client_ref_cannot_craft_without_matching_server_escrow",
            "_contract_check_generated_identity_is_validated_at_deposit_and_start",
            "_contract_check_success_consumes_station_once_and_reveals_once",
            "_contract_check_cancel_refunds_exact_escrow_once_and_late_commit_is_ignored",
            "_contract_check_take_to_mouse_and_clear_return_exact_station_items",
            "_contract_check_late_escrow_retry_replays_older_cached_result_without_mutation",
            "_contract_check_disconnect_reconnect_replays_by_stable_client_token",
            "_contract_check_dedupe_and_pending_gate_do_not_consume_again",
            "_contract_check_commit_ack_loss_reconnect_replays_without_parent_refund",
            "_contract_check_server_restart_replays_failure_with_inputs_still_in_station",
        ),
    )
