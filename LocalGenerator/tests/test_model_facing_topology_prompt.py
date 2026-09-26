"""Exercise topology guidance in the actual serialized Author request, not a helper alone."""

from __future__ import annotations

import json

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compact_capability_catalog
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.llm_authoring_prompt import PLANNER_PROMPT_MIN_HEADROOM_CHARS, PLANNER_PROMPT_LIMIT_CHARS


def _request(monkeypatch):
    # The transport resolves this at import time; patch the effective mode.
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    blade = {"id": "blade", "name": "Blade", "damage": 7, "useTime": 20}
    bench = {"id": "bench", "name": "Workbench", "createTile": 18, "useTime": 15}
    request, user_content, _ = build_initial_author_request(
        blade, bench, blade, bench, "blade+bench", model_name="gemini-2.5-flash"
    )
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"][1]["content"] == user_content
    assert len(user_content) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    return json.loads(user_content)


def test_serialized_topology_explains_binding_roles_contact_and_realized_events(monkeypatch) -> None:
    payload = _request(monkeypatch)
    invariants = payload["runtimeProgramInvariants"]
    transaction = invariants["bindingUseTransactions"]
    body = transaction["bodyDamageLane"]
    assert all(term in body for term in (
        "contactDamage=true", "spawn_entity", "disableMeleeHitbox=false", "Item.noMelee",
        "on_hit/on_crit", "set_projectile_damage", "configure_item_stats.damage",
    ))
    placement = payload["runtimeCapabilityContract"]["catalog"]["placementInputRoles"]
    assert all(term in placement for term in (
        "place_item on primary_use", "non-placement primary_use and place_item on alternate_use",
        "placementCallId", "stackCost=1", "contactDamage=false", "placeStyle",
    ))
    assert "stackCost=0" in invariants["realizationExecutionTruth"]["durablePlacedForm"]
    assert "one-shot" in invariants["realizationExecutionTruth"]["durablePlacedForm"]
    events = invariants["structureCheck"]["eventSources"]
    assert all(term in events for term in (
        "item_body", "on_use", "spawned entity", "placement emits no on_use",
        "actual enabled body hitbox", "HoldItem", "not just while equipped",
        "event source", "not necessarily the binding action's target",
    ))
    assert "multiple equipped bindings" in invariants["structureCheck"]["useAndEquipment"]
    assert "runtime looks up the first" in invariants["structureCheck"]["useAndEquipment"]
    assert "meaningByToken" in invariants["damageClass"]  # preserve parallel parent work


def test_serialized_reference_budget_and_required_keys_stay_anchored_in_cards(monkeypatch) -> None:
    payload = _request(monkeypatch)
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    assert catalog["capabilities"] == compact_capability_catalog()
    cards = {card["fn"]: card for card in catalog["capabilities"]}
    assert set(cards) == set(CAPABILITY_REGISTRY)
    structure = payload["runtimeProgramInvariants"]["structureCheck"]
    guide = structure["referencesAndBudgets"]
    assert all(term in guide for term in (
        "reference.targetKinds", "cannot be the source itself", "cycle", "depth",
        "static sum", "spawn_entity_on_event counts", "runtime activation budget",
    ))
    assert catalog["limits"]["childDepth"] == 3
    assert catalog["limits"]["eventSpawnsPerActivation"] == 32
    for fn, param in (("spawn_entity_on_event", "entity"), ("target_and_fire", "shotEntity")):
        ref = cards[fn]["params"][param]["reference"]
        assert ref["targetKinds"]
        assert "item_body" not in ref["targetKinds"]
        assert ref["allowSelf"] is False
        assert ref["graphEdge"] is True
    assert cards["spawn_entity_on_event"]["params"]["count"]["max"] == 12
    completion = structure["completeCalls"]
    assert "EVERY selected call" in completion
    assert "optional:true" in completion
    assert "zero/false/empty" in completion
    assert "not an automatic default" in completion
    for card in cards.values():
        for name, param in card["params"].items():
            assert param.get("optional", False) is not CAPABILITY_REGISTRY[card["fn"]].params[name].required
    assert "periodTicks" in cards["spawn_entity_on_event"]["params"]
    assert "requires" in cards["spawn_entity_on_event"]


def test_serialized_use_hold_charge_and_equipment_are_distinct(monkeypatch) -> None:
    payload = _request(monkeypatch)
    guide = payload["runtimeProgramInvariants"]["structureCheck"]["useAndEquipment"]
    assert all(term in guide for term in (
        "useTimeTicks", "useAnimationTicks", "autoReuse", "channel", "hold",
        "charge_then_release", "chargeTicks", "heldSpriteVisibilityHint", "presentation hint",
        "equipped", "matching head/body/legs", "head only",
    ))
    assert "no second binding" in payload["runtimeProgramInvariants"]["bindingUseTransactions"]["bodyDamageLane"]
    assert "category" in " ".join(payload["priorityHeader"])
    assert "runtimeFamily" not in json.dumps(payload)
