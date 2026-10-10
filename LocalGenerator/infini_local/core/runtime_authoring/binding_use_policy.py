from __future__ import annotations

import copy
from typing import Any, Callable, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import BINDING_ACTION_REGISTRY, INPUT_KIND_REGISTRY


ACTIVE_USE_INPUTS = frozenset({"primary_use", "alternate_use"})
PLACE_ITEM_ACTION = "place_item"
ITEM_BODY_ACTION = "use_item_body"



def use_policy(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read the one flat Author transaction; persisted wire has separate readers."""
    return binding


def authored_transaction(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Exact present Author transaction fields, without defaults or the row id."""
    return {key: copy.deepcopy(binding[key]) for key in ("input", "action", "stackCost", "contactDamage") if key in binding}


def action(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    value = binding.get("action")
    return value if isinstance(value, Mapping) else {}


def action_kind(binding: Mapping[str, Any]) -> str:
    # A singleton input variant chooses this constant in the Author grammar.
    # Invalid explicit fields remain shape errors; this reader never admits them.
    spec = INPUT_KIND_REGISTRY.get(str(binding.get("input") or ""))
    if spec is not None and len(spec.allowed_actions) == 1:
        return spec.allowed_actions[0]
    return str(action(binding).get("kind") or "")


def target_id(binding: Mapping[str, Any], *, item_entity_id: str = "") -> str:
    spec = BINDING_ACTION_REGISTRY.get(action_kind(binding))
    if spec is not None and spec.target_kinds == ("item_body",):
        return item_entity_id
    return str(action(binding).get("targetId") or "")


def placement_call_id(binding: Mapping[str, Any]) -> str:
    return str(action(binding).get("placementCallId") or "")


def stack_cost(binding: Mapping[str, Any]) -> int:
    if action_kind(binding) == PLACE_ITEM_ACTION:
        return 1
    if str(binding.get("input") or "") in {"hold", "equipped"}:
        return 0
    value = binding.get("stackCost")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def contact_damage(binding: Mapping[str, Any]) -> bool:
    if action_kind(binding) == PLACE_ITEM_ACTION or str(binding.get("input") or "") in {"hold", "equipped"}:
        return False
    return binding.get("contactDamage") is True


def wire_use_policy(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read a persisted wire transaction, never an alternative Author grammar."""
    value = binding.get("usePolicy")
    return value if isinstance(value, Mapping) else {}


def wire_action(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    value = wire_use_policy(binding).get("action")
    return value if isinstance(value, Mapping) else {}


def wire_action_kind(binding: Mapping[str, Any]) -> str:
    return str(wire_action(binding).get("kind") or "")


def wire_target_id(binding: Mapping[str, Any]) -> str:
    return str(wire_action(binding).get("targetId") or "")


def wire_placement_call_id(binding: Mapping[str, Any]) -> str:
    return str(wire_action(binding).get("placementCallId") or "")


def wire_stack_cost(binding: Mapping[str, Any]) -> int:
    value = wire_use_policy(binding).get("stackCost")
    return value if type(value) is int else -1


def wire_contact_damage(binding: Mapping[str, Any]) -> bool:
    return wire_use_policy(binding).get("contactDamage") is True


def placeable_input_contract(bindings: Iterable[Mapping[str, Any]]) -> tuple[bool, str]:
    return _placeable_input_contract(bindings, action_kind)


def wire_placeable_input_contract(bindings: Iterable[Mapping[str, Any]]) -> tuple[bool, str]:
    return _placeable_input_contract(bindings, wire_action_kind)


def _placeable_input_contract(
    bindings: Iterable[Mapping[str, Any]], action_reader: Callable[[Mapping[str, Any]], str],
) -> tuple[bool, str]:
    binding_rows = list(bindings)
    place_bindings = [row for row in binding_rows if action_reader(row) == PLACE_ITEM_ACTION]
    if not place_bindings:
        return True, ""
    active_non_place = [
        row for row in binding_rows
        if str(row.get("input") or "") in ACTIVE_USE_INPUTS
        and action_reader(row) != PLACE_ITEM_ACTION
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
    input_spec = INPUT_KIND_REGISTRY.get(input_name)
    action_spec = BINDING_ACTION_REGISTRY.get(action_name)
    if input_spec is None or action_spec is None or action_name not in input_spec.allowed_actions:
        raise ValueError("binding transaction requires an exact registered input/action variant")
    action_row: dict[str, Any] = {}
    if len(input_spec.allowed_actions) != 1:
        action_row["kind"] = action_name
    if action_spec.target_kinds != ("item_body",):
        if not target:
            raise ValueError("binding transaction requires exact targetId")
        action_row["targetId"] = target
    if action_name == PLACE_ITEM_ACTION:
        if not placement_call:
            raise ValueError("place_item transaction requires exact placementCallId")
        action_row["placementCallId"] = placement_call
    elif placement_call:
        raise ValueError("placementCallId is legal only for place_item")
    result: dict[str, Any] = {"input": input_name}
    if action_row:
        result["action"] = action_row
    if input_name in ACTIVE_USE_INPUTS and action_name != PLACE_ITEM_ACTION:
        result["stackCost"] = stack_cost_value
        result["contactDamage"] = contact_damage_value
    elif stack_cost_value != (1 if action_name == PLACE_ITEM_ACTION else 0) or contact_damage_value is not False:
        raise ValueError("binding transaction contradicts its exact variant constants")
    return result


def project_to_wire(
    binding: Mapping[str, Any],
    *,
    placement_calls_by_id: Mapping[str, Mapping[str, Any]],
    item_entity_id: str,
) -> dict[str, Any]:
    """Losslessly lower one validated authored transaction to its wire row."""
    authored_action = action(binding)
    kind = action_kind(binding)
    wire_action: dict[str, Any] = {
        "kind": kind,
        "targetId": target_id(binding, item_entity_id=item_entity_id),
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
            "stackCost": stack_cost(binding),
            "contactDamage": contact_damage(binding),
        },
    }


def placed_body_binding_ids(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Read-only explicit wire consumers of the existing item PNG, never image jobs."""
    runtime = data.get("runtimeProgram")
    if not isinstance(runtime, Mapping):
        return ()
    item_id = runtime.get("itemEntityId")
    return tuple(str(binding.get("id") or "") for binding in runtime.get("bindings", [])
                 if isinstance(binding, Mapping) and wire_action_kind(binding) == PLACE_ITEM_ACTION
                 and wire_target_id(binding) == item_id
                 and isinstance(wire_action(binding).get("placement"), Mapping)
                 and "placedBody" in wire_action(binding)["placement"])


__all__ = [
    "ACTIVE_USE_INPUTS",
    "ITEM_BODY_ACTION",
    "PLACE_ITEM_ACTION",
    "action",
    "action_kind",
    "authored_transaction",
    "complete_transaction",
    "contact_damage",
    "expected_placeable_input",
    "placeable_input_contract",
    "placement_call_id",
    "placed_body_binding_ids",
    "project_to_wire",
    "stack_cost",
    "target_id",
    "use_policy",
    "wire_use_policy",
    "wire_action",
    "wire_action_kind",
    "wire_target_id",
    "wire_stack_cost",
    "wire_contact_damage",
    "wire_placement_call_id",
    "wire_placeable_input_contract",
]
