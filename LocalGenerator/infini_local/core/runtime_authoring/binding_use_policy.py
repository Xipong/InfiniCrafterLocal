from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping


ACTIVE_USE_INPUTS = frozenset({"primary_use", "alternate_use"})
PLACE_ITEM_ACTION = "place_item"
ITEM_BODY_ACTION = "use_item_body"



def use_policy(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read current Author lanes only; saved wire has explicit separate readers."""
    return binding


def action(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    value = binding.get("action")
    return value if isinstance(value, Mapping) else {}


def wire_action(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    policy = binding.get("usePolicy")
    value = policy.get("action") if isinstance(policy, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def wire_action_kind(binding: Mapping[str, Any]) -> str:
    return str(wire_action(binding).get("kind") or "")


def wire_target_id(binding: Mapping[str, Any]) -> str:
    return str(wire_action(binding).get("targetId") or "")


def wire_stack_cost(binding: Mapping[str, Any]) -> int:
    policy = binding.get("usePolicy")
    value = policy.get("stackCost") if isinstance(policy, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def wire_contact_damage(binding: Mapping[str, Any]) -> bool:
    policy = binding.get("usePolicy")
    return isinstance(policy, Mapping) and policy.get("contactDamage") is True


def action_kind(binding: Mapping[str, Any]) -> str:
    from infini_local.core.runtime_authoring.capability_registry import INPUT_KIND_REGISTRY
    explicit = action(binding).get("kind")
    if explicit is not None:
        return str(explicit)
    inp = INPUT_KIND_REGISTRY.get(binding.get("input")) if isinstance(binding.get("input"), str) else None
    return inp.allowed_actions[0] if inp is not None and len(inp.allowed_actions) == 1 else ""


def target_id(binding: Mapping[str, Any]) -> str:
    return str(action(binding).get("targetId") or "")


def placement_call_id(binding: Mapping[str, Any]) -> str:
    return str(action(binding).get("placementCallId") or "")


def stack_cost(binding: Mapping[str, Any]) -> int:
    if "stackCost" not in binding:
        return 1 if action_kind(binding) == PLACE_ITEM_ACTION else 0 if binding.get("input") not in ACTIVE_USE_INPUTS else -1
    value = use_policy(binding).get("stackCost")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def stack_chance_error(binding: Mapping[str, Any]) -> str:
    """The same explicit optional policy contract is used at Author and wire boundaries."""
    policy = use_policy(binding)
    if "stackConsumeChancePercent" not in policy:
        return ""
    value = policy["stackConsumeChancePercent"]
    if type(value) is not int or not 0 <= value <= 100:
        return "stackConsumeChancePercent must be an integer 0..100."
    input_name = binding.get("input")
    if (not isinstance(input_name, str) or input_name not in ACTIVE_USE_INPUTS or stack_cost(binding) != 1
            or action_kind(binding) == PLACE_ITEM_ACTION):
        return "stackConsumeChancePercent requires an active non-placement binding with stackCost=1."
    return ""


def may_retain_stack(binding: Mapping[str, Any]) -> bool:
    policy = use_policy(binding)
    chance = policy.get("stackConsumeChancePercent", 100)
    return stack_cost(binding) == 0 or (type(chance) is int and chance < 100)


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
    from infini_local.core.runtime_authoring.capability_registry import INPUT_KIND_REGISTRY, BINDING_ACTION_REGISTRY
    if BINDING_ACTION_REGISTRY[action_name].target_kinds == ("item_body",):
        action_row.pop("targetId")
    if len(INPUT_KIND_REGISTRY[input_name].allowed_actions) == 1:
        action_row.pop("kind")
    row: dict[str, Any] = {"input": input_name}
    if action_row:
        row["action"] = action_row
    if input_name in ACTIVE_USE_INPUTS and action_name != PLACE_ITEM_ACTION:
        row["stackCost"] = stack_cost_value
        row["contactDamage"] = contact_damage_value
    return row


def project_to_wire(
    binding: Mapping[str, Any],
    *,
    placement_calls_by_id: Mapping[str, Mapping[str, Any]],
    placement_literals_by_fn: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Losslessly lower one validated authored transaction to its wire row."""
    policy = use_policy(binding)
    authored_action = action(binding)
    kind = str(authored_action["kind"])
    wire_action: dict[str, Any] = {
        "kind": kind,
        "targetId": str(authored_action["targetId"]),
    }
    if "effectGroupId" in authored_action:
        wire_action["effectGroupId"] = str(authored_action["effectGroupId"])
    if kind == PLACE_ITEM_ACTION:
        call_id = str(authored_action["placementCallId"])
        call = placement_calls_by_id[call_id]
        wire_action["placement"] = {**copy.deepcopy(dict(call["params"])),
                                    **placement_literals_by_fn[str(call["fn"])]}
    wire_policy = {
        "action": wire_action,
        "stackCost": int(policy["stackCost"]),
        "contactDamage": bool(policy["contactDamage"]),
    }
    if "stackConsumeChancePercent" in policy:
        wire_policy["stackConsumeChancePercent"] = policy["stackConsumeChancePercent"]
    return {
        "id": str(binding["id"]),
        "input": str(binding["input"]),
        "usePolicy": wire_policy,
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
    "complete_transaction",
    "contact_damage",
    "expected_placeable_input",
    "placeable_input_contract",
    "placement_call_id",
    "placed_body_binding_ids",
    "project_to_wire",
    "stack_cost",
    "stack_chance_error",
    "may_retain_stack",
    "target_id",
    "use_policy",
]
