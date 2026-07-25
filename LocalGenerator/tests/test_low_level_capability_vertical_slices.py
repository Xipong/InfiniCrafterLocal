from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

import infini_local.core.runtime_authoring.capability_registry as registry_module
import infini_local.core.runtime_authoring.program_schema as schema_module
import infini_local.core.runtime_authoring.validator as validator_module
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import runtime_program_author_schema
from infini_local.qa.capability_witnesses import capability_vertical_slice_report
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def test_every_public_capability_has_author_to_wire_witness() -> None:
    report = capability_vertical_slice_report()
    assert report["capabilityCount"] == len(CAPABILITY_REGISTRY)
    assert report["ok"], [row for row in report["rows"] if not row["ok"]]
    assert all(row["receiptCount"] > 0 for row in report["rows"])


def test_registry_mutation_updates_schema_but_missing_executor_stays_red(monkeypatch: pytest.MonkeyPatch) -> None:
    source = CAPABILITY_REGISTRY["emit_light_while_active"]
    synthetic = replace(
        source,
        name="emit_test_light",
        summary="Synthetic mutation witness over an existing parameter surface.",
        compiler_owner="synthetic.missing.vertical.slice",
        csharp_owner="SyntheticMissingExecutor.cs",
        provenance="mutation test",
    )
    mutated = dict(CAPABILITY_REGISTRY)
    mutated[synthetic.name] = synthetic
    frozen = MappingProxyType(mutated)
    monkeypatch.setattr(registry_module, "CAPABILITY_REGISTRY", frozen)
    monkeypatch.setattr(validator_module, "CAPABILITY_REGISTRY", frozen)
    schema = runtime_program_author_schema()
    variants = schema["properties"]["calls"]["items"]["oneOf"]
    assert any(row["properties"]["fn"].get("const") == synthetic.name for row in variants)

    authored = build_runtime_fixture("door_on_chain")
    authored["runtimeProgram"]["calls"].append({
        "id": "synthetic_light", "fn": synthetic.name, "role": "primary", "target": "chained_door",
        "params": {"strength": 0.5, "color": "white"},
    })
    with pytest.raises(AssertionError, match="unhandled runtime entity capability"):
        compile_runtime_program(authored)


def test_provider_schema_is_mechanically_built_from_registry() -> None:
    variants = runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"]
    names = {row["properties"]["fn"]["const"] for row in variants}
    assert names == set(CAPABILITY_REGISTRY)
