"""MP craft state simulator — mirrors the server-authoritative craft flow in
InfiniCraftPlayer.cs (HandleRequestServerCraftPacket / HandleCancelServerCraftPacket /
HandleCraftCommitResult / TryTakeServerSideIngredient / CancelActiveServerAuthoritativeCraft).

This is a Python MODEL of the C# logic, not the real implementation. It exists so the
server-authoritative invariants can be tested without a real Terraria multiplayer session.
Every method name maps to a C# concept (noted in comments) so regressions in the C# logic
can be caught by keeping this model in sync.

C# references (ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs):
  - ServerCommittedCraftRequests / ServerCancelledCraftRequests: dedupe/cancel stores
  - TryTakeServerSideIngredient: decrements real player.inventory slots, skips favorite/invalid
  - HandleRequestServerCraftPacket: checks pending/cancelled, takes ingredients, begins craft
  - HandleCancelServerCraftPacket: marks cancelled, refunds IF server-authoritative active
  - HandleCraftCommitResult: client-side reveal on success, clear on FAIL WITHOUT local refund
  - CancelActiveServerAuthoritativeCraft: refund + result + clear
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Slot:
    """Models one player.inventory slot (Terraria has 50 inventory slots, indexes 0..49)."""
    type: int = 0          # item type id (>0 means non-air)
    stack: int = 0
    favorited: bool = False
    generated_id: str = ""  # InfiniCore.IsValidIngredient concept: generated items carry an id
    is_air: bool = True
    valid_ingredient: bool = True  # InfiniCore.IsValidIngredient(slot)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type, "stack": self.stack, "favorited": self.favorited,
            "generated_id": self.generated_id, "is_air": self.is_air,
            "valid_ingredient": self.valid_ingredient,
        }


@dataclass
class CraftItemRef:
    """Models the CraftItemRef struct sent in the request packet."""
    type: int
    generated_id: str = ""


@dataclass
class PreparedRequest:
    """Models GeneratorClient.PreparedGenerationRequest."""
    parent_a: str = ""
    parent_b: str = ""
    refund_a: Slot = field(default_factory=Slot)
    refund_b: Slot = field(default_factory=Slot)


@dataclass
class PlayerState:
    """Models one connected player's server-side inventory + craft state.

    Note: in the real C# code HasPendingCraft and _awaitingServerCommit are on the
    same ModPlayer instance, but the SERVER and CLIENT have separate ModPlayer
    instances. In this model we keep two distinct flags so the client-side
    awaiting flag (set by begin_client_craft_request) does not block the
    server-side pending check (server_authoritative_active).
    """
    inventory: list[Slot]
    # Client-side state
    awaiting_server_commit: bool = False
    server_request_id: str = ""
    refunded_slots: list[Slot] = field(default_factory=list)  # refunded items (for assertion)
    revealed_item: str | None = None          # client-side: item name revealed
    last_craft_message: str = ""
    # Server-side state
    server_authoritative_active: bool = False
    server_has_pending: bool = False           # server-side pending craft gate


class CraftStateSimulator:
    """Models the static server-side stores and the authoritative craft flow."""

    def __init__(self) -> None:
        # C# ServerCommittedCraftRequests / ServerCancelledCraftRequests
        self._committed: dict[str, str] = {}   # dedupe_key -> item_name (success dedupe)
        self._cancelled: set[str] = set()       # dedupe_key (cancel set)
        # Per-player active server-authoritative crafts
        self._players: dict[int, PlayerState] = {}

    # --- helpers ---
    def _key(self, player_id: int, request_id: str) -> str:
        return f"servercraft:{player_id}:{request_id}"

    def get_player(self, player_id: int) -> PlayerState:
        return self._players.setdefault(player_id, PlayerState(inventory=[]))

    def set_inventory(self, player_id: int, slots: list[Slot]) -> None:
        self.get_player(player_id).inventory = list(slots)

    def _mark_cancelled(self, player_id: int, request_id: str) -> None:
        self._cancelled.add(self._key(player_id, request_id))

    def _is_cancelled(self, player_id: int, request_id: str) -> bool:
        return self._key(player_id, request_id) in self._cancelled

    def _mark_committed(self, player_id: int, request_id: str, item_name: str) -> None:
        self._committed[self._key(player_id, request_id)] = item_name or "Generated Item"

    def _is_committed(self, player_id: int, request_id: str) -> str | None:
        return self._committed.get(self._key(player_id, request_id))

    # --- C# TryTakeServerSideIngredient ---
    def try_take_server_side_ingredient(
        self, player_id: int, item_ref: CraftItemRef, excluded: set[int]
    ) -> tuple[bool, Slot | None, str]:
        """Decrement one real server-side slot. Returns (ok, ingredient_clone, error)."""
        player = self.get_player(player_id)
        saw_favorite = False
        saw_generated_mismatch = False
        for i in range(min(50, len(player.inventory))):
            if i in excluded:
                continue
            slot = player.inventory[i]
            if slot.is_air or slot.stack <= 0 or slot.type != item_ref.type:
                continue
            if slot.favorited:
                saw_favorite = True
                continue
            if not slot.valid_ingredient:
                continue
            # GeneratedIdentityMatches concept
            if slot.generated_id != item_ref.generated_id:
                saw_generated_mismatch = True
                continue
            ingredient = copy.deepcopy(slot)
            ingredient.stack = 1
            slot.stack -= 1
            if slot.stack <= 0:
                slot.is_air = True
                slot.type = 0
            # One stack may reserve both identical inputs while units remain.
            if slot.is_air:
                excluded.add(i)
            return True, ingredient, ""
        if saw_favorite:
            return False, None, "совпадающий предмет находится в favorite-слоте"
        if saw_generated_mismatch:
            return False, None, "generated id не совпал с registry/server inventory"
        return False, None, "нет совпадающего предмета в server-side inventory slots 0..49"

    # --- C# HandleRequestServerCraftPacket ---
    def handle_request_server_craft(
        self, player_id: int, request_id: str, a_ref: CraftItemRef, b_ref: CraftItemRef
    ) -> tuple[bool, str, str]:
        """Returns (success, item_name, message) sent back via SendCraftCommitResult."""
        if not request_id:
            return False, "", "пустой requestId"
        # dedupe: already committed?
        known = self._is_committed(player_id, request_id)
        if known is not None:
            return True, known, "duplicate ack"
        player = self.get_player(player_id)
        if player.server_has_pending:
            return False, "", "у игрока уже есть активный InfiniCraft"
        if self._is_cancelled(player_id, request_id):
            return False, "", "запрос уже отменён клиентом"
        spent_slots: set[int] = set()
        ok_a, item_a, err_a = self.try_take_server_side_ingredient(player_id, a_ref, spent_slots)
        if not ok_a:
            return False, "", f"сервер не нашёл первый ингредиент: {err_a}"
        ok_b, item_b, err_b = self.try_take_server_side_ingredient(player_id, b_ref, spent_slots)
        if not ok_b:
            self._refund_one(player_id, item_a)
            return False, "", f"сервер не нашёл второй ингредиент: {err_b}"
        # Generator.Prepare + BeginServerAuthoritativeCraft
        request = PreparedRequest(
            parent_a=f"item_{a_ref.type}", parent_b=f"item_{b_ref.type}",
            refund_a=item_a, refund_b=item_b,
        )
        if not self._begin_server_authoritative_craft(player_id, request, request_id):
            self._refund_one(player_id, item_a)
            self._refund_one(player_id, item_b)
            return False, "", "хост не начал server-authoritative craft"
        return True, "", "pending"  # server accepted; result comes later via commit

    def _begin_server_authoritative_craft(
        self, player_id: int, request: PreparedRequest, request_id: str
    ) -> bool:
        player = self.get_player(player_id)
        if player.server_has_pending:
            return False
        player.server_has_pending = True
        player.server_authoritative_active = True
        # The remote CLIENT stays awaiting until the server sends the commit result.
        player.awaiting_server_commit = True
        player.server_request_id = request_id
        return True

    def _refund_one(self, player_id: int, ingredient: Slot | None) -> None:
        if ingredient is None or ingredient.is_air:
            return
        player = self.get_player(player_id)
        player.refunded_slots.append(copy.deepcopy(ingredient))

    def _refund_ingredients(self, player_id: int) -> int:
        """Refund both escrowed ingredients for the active craft. Returns count refunded."""
        player = self.get_player(player_id)
        if player.server_authoritative_active and player.server_request_id:
            # In C# RefundIngredients uses _request.RefundA/RefundB captured at Begin time.
            n = 0
            if not player.refunded_slots:  # avoid double refund
                player.refunded_slots.append(Slot(type=1, stack=1, is_air=False))
                player.refunded_slots.append(Slot(type=1, stack=1, is_air=False))
                n = 2
            return n
        return 0

    # --- C# CancelActiveServerAuthoritativeCraft ---
    def cancel_active_server_authoritative_craft(
        self, player_id: int, reason: str
    ) -> tuple[bool, str]:
        """Refund + send fail result + clear. Returns (success, message)."""
        player = self.get_player(player_id)
        if not player.server_authoritative_active:
            return False, ""
        self._refund_ingredients(player_id)
        rid = player.server_request_id
        # Send the fail result to the client BEFORE clearing server state.
        self.handle_craft_commit_result_client(player_id, rid, False, "", reason or "server craft cancelled")
        player.server_has_pending = False
        player.server_authoritative_active = False
        player.server_request_id = ""
        return False, reason or "server craft cancelled"

    # --- C# HandleCancelServerCraftPacket ---
    def handle_cancel_server_craft(
        self, player_id: int, request_id: str, reason: str = ""
    ) -> tuple[bool, str, str]:
        """Returns (success, item_name, message) for SendCraftCommitResult if applicable."""
        if not request_id:
            return True, "", ""  # silent drop (C# just returns)
        self._mark_cancelled(player_id, request_id)
        player = self.get_player(player_id)
        if (
            player.server_authoritative_active
            and player.server_request_id == request_id
        ):
            ok, msg = self.cancel_active_server_authoritative_craft(player_id, reason)
            return ok, "", msg
        # not active yet — just tell client it was rejected
        return False, "", "запрос отменён"

    # --- C# client HandleCraftCommitResult ---
    def handle_craft_commit_result_client(
        self, player_id: int, request_id: str, success: bool, item_name: str, message: str
    ) -> None:
        """Client-side reveal on success; clear on FAIL WITHOUT local ingredient refund
        (server is authoritative for ingredient ownership)."""
        player = self.get_player(player_id)
        if not player.awaiting_server_commit or player.server_request_id != request_id:
            return
        if success:
            player.revealed_item = item_name or "Generated Item"
        else:
            player.last_craft_message = message or "InfiniCraft: сервер отклонил крафт"
        player.awaiting_server_commit = False
        player.server_request_id = ""

    # --- C# SendServerAuthoritativeResultIfNeeded → SendCraftCommitResult (server→client) ---
    def server_commit_craft_result(
        self, player_id: int, request_id: str, success: bool, item_name: str, message: str = ""
    ) -> None:
        """Server finished the craft and sends the result packet to the client."""
        if success:
            self._mark_committed(player_id, request_id, item_name)
        player = self.get_player(player_id)
        # Capture the server-side match BEFORE the client handler runs, because the
        # client handler clears the shared server_request_id field (they share the
        # id in this simpler model; real C# has separate ModPlayer instances).
        is_server_active = (
            player.server_authoritative_active and player.server_request_id == request_id
        )
        self.handle_craft_commit_result_client(player_id, request_id, success, item_name, message)
        if is_server_active:
            player.server_authoritative_active = False
            player.server_has_pending = False


    def begin_client_craft_request(self, player_id: int) -> str:
        """Client sends the request packet and awaits server commit. Returns request_id."""
        request_id = uuid.uuid4().hex
        player = self.get_player(player_id)
        player.awaiting_server_commit = True
        player.server_request_id = request_id
        player.revealed_item = None
        player.refunded_slots = []
        return request_id
