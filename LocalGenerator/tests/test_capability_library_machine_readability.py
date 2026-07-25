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


def test_no_capability_hides_delivery_behind_broad_wildcard() -> None:
    assert not [
        (cap.name, path)
        for cap in CAPABILITY_REGISTRY.values()
        for path in cap.final_wire_paths
        if "*" in path
    ]
