from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeSlot:
    item_id: int
    stack: int = 1
    favorited: bool = False
    valid: bool = True


@dataclass
class PendingCraft:
    request_id: int
    slots: tuple[int, int]
    debited: list[tuple[int, FakeSlot]]
    canceled: bool = False
    completed: bool = False


class ServerCraftStateModel:
    """Python model of InfiniCraftPlayer server-authoritative craft concepts.

    Mirrors names from C#: pending request id, server-side inventory slots,
    cancel/timeout refund, and late HTTP response rejection.
    """

    concepts = (
        "TryTakeServerSideIngredient",
        "HandleCancelServerCraftPacket",
        "_awaitingServerCommit",
        "player.inventory",
        "GeneratedItem parents",
    )

    def __init__(self) -> None:
        self.inventory: dict[int, FakeSlot] = {}
        self.pending: PendingCraft | None = None
        self.generated: list[str] = []
        self.refund_count = 0

    def add_slot(self, index: int, item_id: int, stack: int = 1, *, favorited: bool = False, valid: bool = True) -> None:
        self.inventory[index] = FakeSlot(item_id=item_id, stack=stack, favorited=favorited, valid=valid)

    def start_craft(self, request_id: int, slot_a: int, slot_b: int) -> bool:
        if self.pending is not None:
            return False
        debited: list[tuple[int, FakeSlot]] = []
        for slot in (slot_a, slot_b):
            item = self.inventory.get(slot)
            if item is None or not item.valid or item.favorited or item.stack <= 0:
                self._refund(debited)
                return False
            debited.append((slot, FakeSlot(item.item_id, 1, item.favorited, item.valid)))
            item.stack -= 1
        self.pending = PendingCraft(request_id=request_id, slots=(slot_a, slot_b), debited=debited)
        return True

    def cancel(self, request_id: int) -> None:
        if self.pending is None or self.pending.request_id != request_id or self.pending.canceled:
            return
        self.pending.canceled = True
        self._refund(self.pending.debited)
        self.pending = None

    def disconnect(self) -> None:
        if self.pending is not None:
            self._refund(self.pending.debited)
            self.pending = None

    def late_response(self, request_id: int, item_name: str) -> bool:
        pending = self.pending
        if pending is None or pending.request_id != request_id or pending.canceled or pending.completed:
            return False
        pending.completed = True
        self.generated.append(item_name)
        self.pending = None
        return True

    def _refund(self, debited: list[tuple[int, FakeSlot]]) -> None:
        for slot, old_item in debited:
            current = self.inventory.setdefault(slot, FakeSlot(old_item.item_id, 0))
            if current.item_id == old_item.item_id:
                current.stack += old_item.stack
        if debited:
            self.refund_count += 1


def test_success_item_issued_once() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10)
    state.add_slot(1, 20)
    assert state.start_craft(1, 0, 1)
    assert state.late_response(1, "Comet Blade")
    assert not state.late_response(1, "Duplicate")
    assert state.generated == ["Comet Blade"]


def test_timeout_cancel_late_response_does_not_issue_item() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10)
    state.add_slot(1, 20)
    assert state.start_craft(7, 0, 1)
    state.cancel(7)
    assert not state.late_response(7, "Too Late")
    assert state.generated == []


def test_cancel_after_debit_returns_ingredients_once() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10)
    state.add_slot(1, 20)
    assert state.start_craft(3, 0, 1)
    state.cancel(3)
    state.cancel(3)
    assert state.inventory[0].stack == 1
    assert state.inventory[1].stack == 1
    assert state.refund_count == 1


def test_old_late_response_does_not_mix_with_new_request() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10, 2)
    state.add_slot(1, 20, 2)
    assert state.start_craft(1, 0, 1)
    state.cancel(1)
    assert state.start_craft(2, 0, 1)
    assert not state.late_response(1, "Old")
    assert state.late_response(2, "New")
    assert state.generated == ["New"]


def test_second_craft_after_first_timeout_works() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10, 2)
    state.add_slot(1, 20, 2)
    assert state.start_craft(100, 0, 1)
    state.cancel(100)
    assert state.start_craft(101, 0, 1)
    assert state.late_response(101, "Second")


def test_invalid_client_packet_cannot_craft_nonexistent_server_slots() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10)
    assert not state.start_craft(9, 0, 99)
    assert state.generated == []
    assert state.inventory[0].stack == 1


def test_favorited_or_server_invalid_items_not_debited() -> None:
    state = ServerCraftStateModel()
    state.add_slot(0, 10, favorited=True)
    state.add_slot(1, 20, valid=False)
    assert not state.start_craft(11, 0, 1)
    assert state.inventory[0].stack == 1
    assert state.inventory[1].stack == 1
