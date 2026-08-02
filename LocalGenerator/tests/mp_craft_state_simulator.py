"""Deterministic model of InfiniCraft's multiplayer station escrow.

The real C# boundary is:
1. Vanilla inventory or an open Void Bag puts an item on synchronized mouse slot 58.
2. RequestStationEscrow moves exactly one validated unit from slot 58 into server A/B.
3. RequestServerCraft consumes only server A/B; it never searches for a similar item.
4. Failure/cancel refunds the exact two escrow units once; success commits once.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field


@dataclass
class Slot:
    type: int = 0
    stack: int = 0
    prefix: int = 0
    generated_id: str = ""
    is_air: bool = True
    valid_ingredient: bool = True

    def one(self) -> "Slot":
        item = copy.deepcopy(self)
        item.stack = 1
        item.is_air = False
        return item

    def clear(self) -> None:
        self.type = 0
        self.stack = 0
        self.prefix = 0
        self.generated_id = ""
        self.is_air = True
        self.valid_ingredient = True


@dataclass(frozen=True)
class CraftItemRef:
    type: int
    prefix: int = 0
    generated_id: str = ""


@dataclass
class PlayerState:
    client_token: str = ""
    mouse_slot_58: Slot = field(default_factory=Slot)
    station: list[Slot] = field(default_factory=lambda: [Slot(), Slot()])
    last_mouse_origin: str = ""
    awaiting_server_commit: bool = False
    server_request_id: str = ""
    server_has_pending: bool = False
    server_authoritative_active: bool = False
    active_refunds: list[Slot] = field(default_factory=list)
    refunded_slots: list[Slot] = field(default_factory=list)
    revealed_item: str | None = None
    last_craft_message: str = ""


class CraftStateSimulator:
    _STATION_ESCROW_RESULT_CACHE_LIMIT = 64

    def __init__(self) -> None:
        self._players: dict[int, PlayerState] = {}
        self._player_tokens: dict[int, str] = {}
        self._durable_station: dict[str, list[Slot]] = {}
        self._craft_outcomes: dict[str, tuple[bool, str, str]] = {}
        self._craft_leases: set[str] = set()
        self._durable_client_pending: dict[str, str] = {}
        self._station_escrow_results: dict[tuple[str, str], tuple[bool, str]] = {}
        self._station_escrow_result_order: list[tuple[str, str]] = []

    def get_player(self, player_id: int) -> PlayerState:
        token = self._player_tokens.setdefault(player_id, f"client-{player_id}")
        if player_id not in self._players:
            player = PlayerState(client_token=token)
            if token in self._durable_station:
                player.station = copy.deepcopy(self._durable_station[token])
            self._players[player_id] = player
        return self._players[player_id]

    def connect_player(self, player_id: int, client_token: str) -> PlayerState:
        self._player_tokens[player_id] = client_token
        self._players.pop(player_id, None)
        player = self.get_player(player_id)
        request_id = self._durable_client_pending.get(client_token, "")
        if request_id:
            player.awaiting_server_commit = True
            player.server_request_id = request_id
        return player

    def disconnect_player(self, player_id: int) -> None:
        player = self.get_player(player_id)
        self._durable_station[player.client_token] = copy.deepcopy(player.station)
        if player.awaiting_server_commit and player.server_request_id:
            self._durable_client_pending[player.client_token] = player.server_request_id
        self._players.pop(player_id, None)
        self._player_tokens.pop(player_id, None)

    def _capture_station(self, player: PlayerState) -> None:
        self._durable_station[player.client_token] = copy.deepcopy(player.station)

    def _key(self, player_id: int, request_id: str) -> str:
        return f"servercraft:{self.get_player(player_id).client_token}:{request_id}"

    @staticmethod
    def _matches(slot: Slot, item_ref: CraftItemRef) -> bool:
        return (
            not slot.is_air
            and slot.stack > 0
            and slot.valid_ingredient
            and slot.type == item_ref.type
            and slot.prefix == item_ref.prefix
            and slot.generated_id == item_ref.generated_id
        )

    def set_mouse_item(self, player_id: int, item: Slot, *, origin: str) -> None:
        """Model vanilla moving an inventory/bank4 item to synchronized slot 58."""
        player = self.get_player(player_id)
        player.mouse_slot_58 = copy.deepcopy(item)
        player.last_mouse_origin = origin

    def deposit_server_mouse_item(self, player_id: int, index: int, item_ref: CraftItemRef) -> tuple[bool, str]:
        player = self.get_player(player_id)
        if index not in (0, 1):
            return False, "invalid escrow index"
        if not player.station[index].is_air:
            return False, "escrow occupied"
        if not self._matches(player.mouse_slot_58, item_ref):
            return False, "server mouse slot 58 mismatch"
        player.station[index] = player.mouse_slot_58.one()
        player.mouse_slot_58.stack -= 1
        if player.mouse_slot_58.stack <= 0:
            player.mouse_slot_58.clear()
        self._capture_station(player)
        return True, ""

    def handle_station_deposit(
        self,
        player_id: int,
        operation_id: str,
        index: int,
        item_ref: CraftItemRef,
    ) -> tuple[bool, str]:
        player = self.get_player(player_id)
        key = (player.client_token, operation_id)
        cached = self._station_escrow_results.get(key)
        if cached is not None:
            return cached
        result = self.deposit_server_mouse_item(player_id, index, item_ref)
        self._station_escrow_results[key] = result
        self._station_escrow_result_order.append(key)
        while len(self._station_escrow_result_order) > self._STATION_ESCROW_RESULT_CACHE_LIMIT:
            expired = self._station_escrow_result_order.pop(0)
            self._station_escrow_results.pop(expired, None)
        return result

    def take_server_escrow_to_mouse(self, player_id: int, index: int) -> tuple[bool, str]:
        player = self.get_player(player_id)
        if index not in (0, 1) or player.station[index].is_air:
            return False, "escrow empty"
        if not player.mouse_slot_58.is_air:
            return False, "mouse occupied"
        player.mouse_slot_58 = copy.deepcopy(player.station[index])
        player.station[index].clear()
        self._capture_station(player)
        return True, ""

    def return_all_server_escrow(self, player_id: int) -> int:
        player = self.get_player(player_id)
        count = 0
        for slot in player.station:
            if slot.is_air:
                continue
            player.refunded_slots.append(slot.one())
            slot.clear()
            count += 1
        self._capture_station(player)
        return count

    def begin_client_craft_request(self, player_id: int) -> str:
        player = self.get_player(player_id)
        request_id = uuid.uuid4().hex
        player.awaiting_server_commit = True
        player.server_request_id = request_id
        player.revealed_item = None
        self._durable_client_pending[player.client_token] = request_id
        return request_id

    def _take_server_escrow_input(self, player_id: int, index: int, item_ref: CraftItemRef) -> tuple[bool, Slot | None, str]:
        player = self.get_player(player_id)
        slot = player.station[index]
        if not self._matches(slot, item_ref):
            return False, None, f"server escrow input {index} mismatch"
        item = slot.one()
        slot.clear()
        return True, item, ""

    def handle_request_server_craft(
        self,
        player_id: int,
        request_id: str,
        a_ref: CraftItemRef,
        b_ref: CraftItemRef,
    ) -> tuple[bool, str, str]:
        if not request_id:
            return False, "", "пустой requestId"
        key = self._key(player_id, request_id)
        outcome = self._craft_outcomes.get(key)
        if outcome is not None:
            return outcome
        player = self.get_player(player_id)
        if key in self._craft_leases:
            if player.server_authoritative_active and player.server_request_id == request_id:
                return True, "", "pending"
            result = (False, "", "server craft interrupted; inputs remain in station")
            self._craft_leases.remove(key)
            self._craft_outcomes[key] = result
            return result
        if player.server_has_pending:
            return False, "", "у игрока уже есть активный InfiniCraft"
        if not self._matches(player.station[0], a_ref):
            return False, "", "сервер не подтвердил первый escrow-ингредиент"
        if not self._matches(player.station[1], b_ref):
            return False, "", "сервер не подтвердил второй escrow-ингредиент"

        item_a = player.station[0].one()
        item_b = player.station[1].one()
        player.active_refunds = [copy.deepcopy(item_a), copy.deepcopy(item_b)]
        player.server_has_pending = True
        player.server_authoritative_active = True
        player.server_request_id = request_id
        self._craft_leases.add(key)
        return True, "", "pending"

    def _refund_active_once(self, player: PlayerState) -> int:
        if not player.active_refunds:
            return 0
        player.refunded_slots.extend(copy.deepcopy(player.active_refunds))
        count = len(player.active_refunds)
        player.active_refunds.clear()
        return count

    def handle_cancel_server_craft(self, player_id: int, request_id: str, reason: str = "") -> tuple[bool, str, str]:
        if not request_id:
            return True, "", ""
        key = self._key(player_id, request_id)
        player = self.get_player(player_id)
        if player.server_authoritative_active and player.server_request_id == request_id:
            result = (False, "", reason or "server craft cancelled; inputs remain in station")
            self._craft_leases.discard(key)
            self._craft_outcomes[key] = result
            player.active_refunds.clear()
            player.server_authoritative_active = False
            player.server_has_pending = False
            self.handle_craft_commit_result_client(player_id, request_id, *result)
            return result
        return False, "", "запрос не активен"

    def handle_craft_commit_result_client(
        self,
        player_id: int,
        request_id: str,
        success: bool,
        item_name: str,
        message: str,
    ) -> None:
        player = self.get_player(player_id)
        if not player.awaiting_server_commit or player.server_request_id != request_id:
            return
        if success:
            player.revealed_item = item_name or "Generated Item"
        else:
            player.last_craft_message = message or "InfiniCraft: сервер отклонил крафт"
        player.awaiting_server_commit = False
        player.server_request_id = ""
        self._durable_client_pending.pop(player.client_token, None)

    def server_commit_craft_result(
        self,
        player_id: int,
        request_id: str,
        success: bool,
        item_name: str,
        message: str = "",
        *,
        deliver_to_client: bool = True,
    ) -> None:
        key = self._key(player_id, request_id)
        if key not in self._craft_leases:
            return
        player = self.get_player(player_id)
        result = (success, item_name or ("Generated Item" if success else ""), message)
        self._craft_leases.remove(key)
        self._craft_outcomes[key] = result
        if success:
            player.station[0].clear()
            player.station[1].clear()
            self._capture_station(player)
        player.active_refunds.clear()
        if deliver_to_client:
            self.handle_craft_commit_result_client(player_id, request_id, *result)
        player.server_authoritative_active = False
        player.server_has_pending = False

    def reconcile_pending_craft(
        self,
        player_id: int,
        a_ref: CraftItemRef,
        b_ref: CraftItemRef,
    ) -> tuple[bool, str, str]:
        player = self.get_player(player_id)
        request_id = player.server_request_id
        result = self.handle_request_server_craft(player_id, request_id, a_ref, b_ref)
        if result[2] != "pending":
            self.handle_craft_commit_result_client(player_id, request_id, *result)
        return result

    def restart_server(self) -> None:
        for key in tuple(self._craft_leases):
            self._craft_outcomes[key] = (False, "", "server restarted; inputs remain in station")
        self._craft_leases.clear()
        for player in self._players.values():
            player.server_authoritative_active = False
            player.server_has_pending = False
            player.active_refunds.clear()
