from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping


ACTIVE_USE_INPUTS = frozenset({"primary_use", "alternate_use"})
PLACE_ITEM_ACTION = "place_item"
ITEM_BODY_ACTION = "use_item_body"
STACK_COST_RULE = (
    "place_item requires stackCost=1 on its own binding; the stack is spent only after accepted placement "
    "and the placed generated item is returned by the placement ledger when broken. "
    "For every other active use, stackCost=1 consumes one generated item; stackCost=0 retains it. "
    "A projectile return does not refund a consumed item: choose stackCost=0 for a reusable throw. "
    "Before answering, compare each active binding with the intended item lifetime: if the generated item "
    "remains in inventory for another activation, choose stackCost=0 even for spawn_entity. "
    "stackCost=1 on spawn_entity consumes the whole generated item, not a projectile or separate ammo."
)


def use_policy(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    value = binding.get("usePolicy")
    return value if isinstance(value, Mapping) else {}


def action(policy_or_binding: Mapping[str, Any]) -> Mapping[str, Any]:
    policy = (
        use_policy(policy_or_binding)
        if "usePolicy" in policy_or_binding
        else policy_or_binding
    )
    value = policy.get("action")
    return value if isinstance(value, Mapping) else {}


def action_kind(binding: Mapping[str, Any]) -> str:
    return str(action(binding).get("kind") or "")


def target_id(binding: Mapping[str, Any]) -> str:
    return str(action(binding).get("targetId") or "")


def placement_call_id(binding: Mapping[str, Any]) -> str:
    return str(action(binding).get("placementCallId") or "")


def stack_cost(binding: Mapping[str, Any]) -> int:
    value = use_policy(binding).get("stackCost")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def contact_damage(binding: Mapping[str, Any]) -> bool:
    return use_policy(binding).get("contactDamage") is True


def placeable_input_contract(bindings: Iterable[Mapping[str, Any]]) -> tuple[bool, str]:
    binding_rows = list(bindings)
    place_bindings = [row for row in binding_rows if action_kind(row) == PLACE_ITEM_ACTION]
    if not place_bindings:
        return True, ""
    active_non_place = [
        row for row in binding_rows
        if str(row.get("input") or "") in ACTIVE_USE_INPUTS
        and action_kind(row) != PLACE_ITEM_ACTION
    ]
    if active_non_place:
        valid = (
            all(str(row.get("input") or "") == "alternate_use" for row in place_bindings)
            and any(str(row.get("input") or "") == "primary_use" for row in active_non_place)
        )
        return valid, (
            "A hybrid placeable must put a non-placement active use on primary_use and every place_item binding "
            "on alternate_use; primary placement is reserved for pure placeables."
        )
    valid = all(str(row.get("input") or "") == "primary_use" for row in place_bindings)
    return valid, "A pure placeable must put its place_item binding on primary_use."


def expected_placeable_input(
    binding: Mapping[str, Any],
    bindings: Iterable[Mapping[str, Any]],
) -> str | None:
    has_non_place_active_use = any(
        str(row.get("input") or "") in ACTIVE_USE_INPUTS
        and action_kind(row) != PLACE_ITEM_ACTION
        for row in bindings
    )
    if action_kind(binding) == PLACE_ITEM_ACTION:
        return "alternate_use" if has_non_place_active_use else "primary_use"
    if has_non_place_active_use and str(binding.get("input") or "") in ACTIVE_USE_INPUTS:
        return "primary_use"
    return None


def complete_transaction(
    *,
    input_name: str,
    action_name: str,
    target: str,
    stack_cost_value: int,
    contact_damage_value: bool,
    placement_call: str = "",
) -> dict[str, Any]:
    action_row: dict[str, Any] = {"kind": action_name, "targetId": target}
    if action_name == PLACE_ITEM_ACTION:
        if not placement_call:
            raise ValueError("place_item transaction requires exact placementCallId")
        action_row["placementCallId"] = placement_call
    elif placement_call:
        raise ValueError("placementCallId is legal only for place_item")
    return {
        "input": input_name,
        "usePolicy": {
            "action": action_row,
            "stackCost": stack_cost_value,
            "contactDamage": contact_damage_value,
        },
    }


def project_to_wire(
    binding: Mapping[str, Any],
    *,
    placement_calls_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Losslessly lower one validated authored transaction to its wire row."""
    policy = use_policy(binding)
    authored_action = action(binding)
    kind = str(authored_action["kind"])
    wire_action: dict[str, Any] = {
        "kind": kind,
        "targetId": str(authored_action["targetId"]),
    }
    if kind == PLACE_ITEM_ACTION:
        call_id = str(authored_action["placementCallId"])
        call = placement_calls_by_id[call_id]
        wire_action["placement"] = copy.deepcopy(dict(call["params"]))
    return {
        "id": str(binding["id"]),
        "input": str(binding["input"]),
        "usePolicy": {
            "action": wire_action,
            "stackCost": int(policy["stackCost"]),
            "contactDamage": bool(policy["contactDamage"]),
        },
    }


__all__ = [
    "ACTIVE_USE_INPUTS",
    "ITEM_BODY_ACTION",
    "PLACE_ITEM_ACTION",
    "action",
    "action_kind",
    "complete_transaction",
    "contact_damage",
    "expected_placeable_input",
    "placeable_input_contract",
    "placement_call_id",
    "project_to_wire",
    "stack_cost",
    "target_id",
    "use_policy",
]
