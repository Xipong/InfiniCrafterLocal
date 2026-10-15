#!/usr/bin/env python3
"""Mutation witnesses for registry locality, duplicate writers, lowerers and final wire."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
sys.path.insert(0, str(ROOT / "tools"))

import infini_local.core.runtime_authoring.capability_registry as registry_module
import infini_local.core.runtime_authoring.validator as validator_module
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import runtime_program_author_schema
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def build_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    source = CAPABILITY_REGISTRY["emit_light_while_active"]
    synthetic = replace(
        source,
        name="emit_mutation_light",
        compiler_owner="missing.vertical.slice",
        csharp_owner="MissingExecutor.cs",
    )
    mutated = MappingProxyType({**dict(CAPABILITY_REGISTRY), synthetic.name: synthetic})
    old_registry = registry_module.CAPABILITY_REGISTRY
    old_validator_registry = validator_module.CAPABILITY_REGISTRY
    try:
        registry_module.CAPABILITY_REGISTRY = mutated
        validator_module.CAPABILITY_REGISTRY = mutated
        visible = any(
            row["properties"]["fn"].get("const") == synthetic.name
            for row in runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"]
        )
        document = build_runtime_fixture("door_on_chain")
        document["runtimeProgram"]["calls"].append(
            {
                "id": "mutation_light",
                "fn": synthetic.name,
                "target": "chained_door",
                "params": {"strength": 0.5, "color": "white"},
            }
        )
        try:
            compile_runtime_program(document)
            stayed_red = False
        except AssertionError:
            stayed_red = True
    finally:
        registry_module.CAPABILITY_REGISTRY = old_registry
        validator_module.CAPABILITY_REGISTRY = old_validator_registry
    rows.append(
        {"mutation": "new_capability_missing_executor", "caught": visible and stayed_red}
    )

    duplicate = build_runtime_fixture("workbench_blade")
    call = deepcopy(duplicate["runtimeProgram"]["calls"][0])
    call["id"] = "duplicate_writer"
    duplicate["runtimeProgram"]["calls"].append(call)
    rows.append(
        {
            "mutation": "second_writer_existing_component",
            "caught": any(
                row.get("code") == "duplicate_single_component"
                for row in validate_runtime_program(duplicate)["errors"]
            ),
        }
    )

    bad_receipt = audit_compiler_receipts(
        [
            {
                "callId": "alias",
                "fn": "emit_light_while_active",
                "authoredPath": "x",
                "finalPath": "runtimeProgram.entities[].movement.code",
                "value": 1,
                "status": "delivered",
            }
        ]
    )
    rows.append(
        {
            "mutation": "technical_alias_undeclared_output",
            "caught": not bad_receipt["ok"],
        }
    )

    wire = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    wire["runtimeProgram"]["entities"][0]["newFinalWireField"] = {}
    rows.append(
        {
            "mutation": "new_final_wire_field_without_dto",
            "caught": any(
                row.get("code") == "unknown_final_wire_field"
                for row in validate_runtime_wire(wire)["errors"]
            ),
        }
    )

    return {
        "schema": "infini.low-level-mutation-gate.v1",
        "ok": all(bool(row["caught"]) for row in rows),
        "rows": rows,
    }


if __name__ == "__main__":
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if report["ok"] else 1)
