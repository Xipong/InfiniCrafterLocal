"""Exercise construction facts in the actual serialized Author request."""
from __future__ import annotations

import json

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compact_capability_catalog
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.llm_authoring_prompt import PLANNER_PROMPT_MIN_HEADROOM_CHARS, PLANNER_PROMPT_LIMIT_CHARS


def _request(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    blade = {"id": "blade", "name": "Blade", "damage": 7, "useTime": 20}
    bench = {"id": "bench", "name": "Workbench", "createTile": 18, "useTime": 15}
    request, user, _ = build_initial_author_request(blade, bench, blade, bench, "blade+bench", model_name="gemini-2.5-flash")
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"][1]["content"] == user
    assert len(user) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    return json.loads(user)


def test_binding_contact_placement_and_events_are_local(monkeypatch) -> None:
    payload = _request(monkeypatch)
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    guide = catalog["fieldGuide"]
    body = guide["bindingTarget"]
    assert all(term in body for term in (
        "contactDamage=true", "spawn_entity", "disableMeleeHitbox=false", "Item.noMelee",
        "on_hit/on_crit", "set_projectile_damage", "configure_item_stats.damage", "primaryEntityId",
    ))
    placement = next(row["constructionMeaning"] for row in catalog["bindingActions"] if row["action"] == "place_item")
    assert all(term in placement for term in (
        "primary_use", "alternate_use", "placementCallId", "stackCost=1", "contactDamage=false",
        "placeStyle", "returned", "escrows", "item_body.on_use",
    ))
    assert "whole generated item" in guide["stackCost"]
    assert "stackCost=0" in guide["stackCost"]
    event = {row["event"]: row for row in catalog["events"]}
    assert "spawned entity" in event["on_use"]["constructionMeaning"]
    assert "placement emits none" in event["on_use"]["constructionMeaning"]
    assert "enabled body hitbox" in event["on_hit"]["constructionMeaning"]
    assert "HoldItem" in event["periodic"]["constructionMeaning"]
    assert "source" in guide["eventSource"] and "binding action target" in guide["eventSource"]
    assert "meaningByToken" in guide["damageClass"]


def test_reference_budgets_and_complete_calls_use_registry_cards(monkeypatch) -> None:
    payload = _request(monkeypatch)
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    cards = {card["fn"]: card for card in catalog["capabilities"]}
    canonical = {card["fn"]: card for card in compact_capability_catalog()}
    assert set(cards) == set(CAPABILITY_REGISTRY)
    assert {fn: {key: value for key, value in card.items() if key != "constructionMeaning"}
            for fn, card in cards.items()} == canonical
    guide = catalog["fieldGuide"]["referenceRules"] + " " + payload["runtimeProgramInvariants"]["graphAndSpawnBudget"]
    assert all(term in guide for term in ("targetKinds", "compatible", "cycle", "depth", "static sum", "spawn_entity_on_event counts", "runtime activation budget"))
    assert catalog["limits"]["childDepth"] == 3
    assert catalog["limits"]["eventSpawnsPerActivation"] == 32
    for fn, param in (("spawn_entity_on_event", "entity"), ("target_and_fire", "shotEntity")):
        ref = cards[fn]["params"][param]["reference"]
        assert ref["targetKinds"] and "item_body" not in ref["targetKinds"]
        assert ref["allowSelf"] is False and ref["graphEdge"] is True
    assert cards["spawn_entity_on_event"]["params"]["count"]["max"] == 12
    assert "required unless marked optional" in catalog["fieldGuide"]["paramNotation"]
    for card in cards.values():
        for name, param in card["params"].items():
            assert param.get("optional", False) is not CAPABILITY_REGISTRY[card["fn"]].params[name].required
    assert "periodTicks" in cards["spawn_entity_on_event"]["params"]
    assert "requires" in cards["spawn_entity_on_event"]


def test_use_hold_charge_equipment_and_topology_are_at_owners(monkeypatch) -> None:
    payload = _request(monkeypatch)
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    cards = {card["fn"]: card for card in catalog["capabilities"]}
    inputs = {row["input"]: row for row in catalog["inputs"]}
    entities = {row["kind"]: row for row in catalog["entityKinds"]}
    use = cards["configure_item_use"]["constructionMeaning"]
    assert all(term in use for term in ("useTimeTicks", "useAnimationTicks", "autoReuse", "channel"))
    charge = cards["charge_then_release"]["constructionMeaning"]
    assert all(term in charge for term in ("channel=true", "charged entity", "chargeTicks", "heldSpriteVisibilityHint", "presentation"))
    assert "While-selected HoldItem" in inputs["hold"]["constructionMeaning"]
    assert all(term in inputs["equipped"]["constructionMeaning"].lower() for term in ("passive", "runtime uses the first", "head only", "head/body/legs"))
    assert "requiredComponents" in entities["item_body"] and "configure_item_stats" in entities["item_body"]["requiredComponents"]
    assert "target_and_fire" in entities["stationary_projectile"]["constructionMeaning"]
    assert "per-owner cap" in entities["free_projectile"]["constructionMeaning"]
    assert "maxStack=1" in cards["configure_item_stats"]["constructionMeaning"]
    assert "category" in " ".join(payload["priorityHeader"])
    assert "runtimeFamily" not in json.dumps(payload)
