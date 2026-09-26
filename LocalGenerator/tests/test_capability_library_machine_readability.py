from __future__ import annotations

import json

from infini_local.core.runtime_authoring import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    runtime_authoring_registry_manifest,
)
from infini_local.qa.capability_library_audit import capability_library_audit
from infini_local.core.runtime_authoring.capability_registry import (
    compact_capability_catalog,
    runtime_authoring_prompt_field_guide,
)
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_MIN_HEADROOM_CHARS,
    build_llm_author_payload,
    planner_prompt_usability_report,
    realization_execution_truth_for_llm,
)


def test_machine_readable_registry_is_complete_and_runtime_grounded() -> None:
    report = capability_library_audit()
    assert report["score"] == report["scoreMax"], report["issues"]
    assert report["ok"], report["issues"]
    assert report["metrics"]["capabilities"] == 52
    assert report["metrics"]["boundedNumericParameters"] == report["metrics"]["numericParameters"]
    assert report["metrics"]["verticalSliceCount"] == len(CAPABILITY_REGISTRY)
    assert report["metrics"]["typedEntityReferences"] == 2
    assert report["metrics"]["requirements"] >= 10


def test_registry_manifest_contains_composition_grammar_not_only_function_names() -> None:
    manifest = runtime_authoring_registry_manifest()
    assert {row["kind"] for row in manifest["entityKinds"]} == set(ENTITY_KIND_REGISTRY)
    assert {row["input"] for row in manifest["inputs"]} == set(INPUT_KIND_REGISTRY)
    assert {row["action"] for row in manifest["bindingActions"]} == set(BINDING_ACTION_REGISTRY)
    assert {row["event"] for row in manifest["events"]} == set(EVENT_KIND_REGISTRY)
    assert all(row["slot"] for row in manifest["capabilities"])
    assert all("authority" in row and "requires" in row and "positionOwnership" in row for row in manifest["capabilities"])
    assert all("activationSpawnCountParam" in row and "meaningfulForStationary" in row and "multiplicity" in row for row in manifest["capabilities"])


def test_no_capability_hides_delivery_behind_broad_wildcard() -> None:
    assert not [
        (cap.name, path)
        for cap in CAPABILITY_REGISTRY.values()
        for path in cap.final_wire_paths
        if "*" in path
    ]


def test_model_cards_preserve_constraints_while_factoring_shared_notation() -> None:
    guide = runtime_authoring_prompt_field_guide()
    notation = guide["paramNotation"]
    assert "unless marked optional" in notation
    for suffix, unit in (("Ticks", "ticks"), ("Tiles", "tiles"),
                         ("Px", "pixels"), ("Radians", "radians")):
        assert f"{suffix}={unit}" in notation
    for capability in CAPABILITY_REGISTRY.values():
        full = capability.prompt_card()
        compact = capability.author_prompt_card()
        assert {key: value for key, value in compact.items() if key != "params"} == {
            key: value for key, value in full.items() if key != "params"
        }
        assert set(compact["params"]) == set(full["params"])
        for name, spec in capability.params.items():
            original = full["params"][name]
            row = compact["params"][name]
            assert row["type"] == original["type"]
            meaning = row.get("meaning", "")
            if capability.name == "configure_armor" and name.startswith("setBonus"):
                meaning = guide["setBonusParamPrefix"] + meaning
            elif capability.name == "configure_armor" and not meaning:
                meaning = CAPABILITY_REGISTRY["configure_accessory"].params[name].description
            assert meaning == original["meaning"]
            assert row.get("optional", False) is not spec.required
            for constraint in ("min", "max", "enum", "pattern", "reference"):
                assert row.get(constraint) == original.get(constraint)
            if "units" not in row and spec.units:
                assert any(name.endswith(suffix) and spec.units == unit for suffix, unit in (
                    ("Ticks", "ticks"), ("Tiles", "tiles"),
                    ("Px", "pixels"), ("Radians", "radians"),
                ))
            else:
                assert row.get("units") == original.get("units")
            if "neutral" not in row and "neutral" in original:
                assert not spec.required and spec.neutral == 0
            else:
                assert row.get("neutral") == original.get("neutral")
    assert guide["exclusiveGroup"]["scope"] == "per exact target entity"
    assert "authority" not in guide
    assert all(row["authority"] for row in runtime_authoring_registry_manifest()["capabilities"])
    assert set(guide["positionOwnership"]) == {
        capability.position_ownership
        for capability in CAPABILITY_REGISTRY.values()
    }


def test_author_packet_exposes_field_guide_with_configured_headroom() -> None:
    parent_a = {"id": "a", "name": "A", "damage": 10, "useTime": 20}
    parent_b = {"id": "b", "name": "B", "damage": 20, "useTime": 30}
    payload = build_llm_author_payload(parent_a, parent_b, parent_a, parent_b, "a+b")
    guide = payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"]
    canonical = runtime_authoring_prompt_field_guide()
    assert {key: guide[key] for key in canonical if key not in {"stackCost", "bindingTarget"}} == {
        key: value for key, value in canonical.items() if key not in {"stackCost", "bindingTarget"}
    }
    assert guide["bindingTarget"].startswith(canonical["bindingTarget"])
    assert "whole generated item" in guide["stackCost"]
    report = planner_prompt_usability_report(parent_a, parent_b, parent_a, parent_b, "a+b")
    assert report["ok"], report
    assert report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS, report


def test_json_object_request_serializes_every_author_capability_card(monkeypatch) -> None:
    """The local response schema is not sent in this mode: the user JSON must carry the catalog."""
    # Transport reads this configuration at import time, before pytest sets per-test env.
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    parent_a = {"name": "Workbench"}
    parent_b = {"name": "Sword"}
    request, user_content, system = build_initial_author_request(
        parent_a, parent_b, parent_a, parent_b, "workbench+sword", model_name="gemini-2.5-flash"
    )
    catalog = json.loads(user_content)["runtimeCapabilityContract"]["catalog"]
    assert request["response_format"] == {"type": "json_object"}
    assert [row["role"] for row in request["messages"]] == ["system", "user"]
    assert request["messages"][0]["content"] == system
    assert request["messages"][1]["content"] == user_content
    assert system and "paramNotation" in catalog["fieldGuide"]
    assert {row["fn"]: {key: value for key, value in row.items() if key != "constructionMeaning"}
            for row in catalog["capabilities"]} == {row["fn"]: row for row in compact_capability_catalog()}
    assert {row["fn"] for row in catalog["capabilities"]} == set(CAPABILITY_REGISTRY)
    assert sum(len(row["params"]) for row in catalog["capabilities"]) == sum(
        len(cap.params) for cap in CAPABILITY_REGISTRY.values()
    )


def test_proximity_expiration_is_explicit_without_synthetic_hit() -> None:
    movement = CAPABILITY_REGISTRY["move_proximity_missile"].prompt_card()["does"]
    expiration = EVENT_KIND_REGISTRY["on_expire"].prompt_card()["does"]
    author_rule = realization_execution_truth_for_llm()["terminationEvents"]
    for description in (movement, expiration, author_rule):
        assert "proximity" in description.lower()
    assert "on_hit" in movement and "actual hit" in movement.lower()
    assert "natural" in expiration.lower() and "natural" in author_rule.lower()
