from __future__ import annotations

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
    runtime_authoring_prompt_field_guide,
)
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_MIN_HEADROOM_CHARS,
    build_llm_author_payload,
    planner_prompt_usability_report,
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


def test_model_cards_losslessly_project_patterns_and_shared_field_vocabulary() -> None:
    for capability in CAPABILITY_REGISTRY.values():
        card_params = capability.prompt_card()["params"]
        for name, spec in capability.params.items():
            if spec.pattern:
                assert card_params[name]["pattern"] == spec.pattern

    guide = runtime_authoring_prompt_field_guide()
    expected_semantic_types = {
        spec.semantic_type
        for capability in CAPABILITY_REGISTRY.values()
        for spec in capability.params.values()
        if spec.semantic_type
    }
    assert set(guide["semanticTypes"]) == expected_semantic_types
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
    assert payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"] == (
        runtime_authoring_prompt_field_guide()
    )
    report = planner_prompt_usability_report(parent_a, parent_b, parent_a, parent_b, "a+b")
    assert report["ok"], report
    assert report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS, report
