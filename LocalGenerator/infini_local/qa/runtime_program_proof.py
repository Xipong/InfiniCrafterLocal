from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    compile_runtime_program,
    runtime_event_inventory,
    runtime_visual_roles,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.vfx_manifest import vfx_director_surface
from infini_local.pipelines.llm_authoring_prompt import planner_prompt_usability_report
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture


def build_runtime_program_proof() -> dict[str, Any]:
    fixture_rows: list[dict[str, Any]] = []
    all_ok = True
    for name in NON_ARCHETYPAL_FIXTURES:
        authored = build_runtime_fixture(name)
        author_report = validate_runtime_program(authored)
        row: dict[str, Any] = {
            "id": name,
            "authorValid": bool(author_report.get("ok")),
            "authorErrors": copy.deepcopy(author_report.get("errors") or []),
        }
        if author_report.get("ok"):
            compiled = compile_runtime_program(authored)
            wire_report = validate_runtime_wire(compiled)
            roles = runtime_visual_roles(compiled)
            events = runtime_event_inventory(compiled)
            surface = vfx_director_surface(compiled)
            row.update({
                "wireValid": bool(wire_report.get("ok")),
                "wireErrors": copy.deepcopy(wire_report.get("errors") or []),
                "entities": len(compiled["runtimeProgram"]["entities"]),
                "bindings": len(compiled["runtimeProgram"]["bindings"]),
                "visualRoles": roles,
                "runtimeEvents": events,
                "vfxPairCount": len(surface["runtimePairs"]),
                "receiptCount": len(compiled["runtimeContract"]["finalWireReceipts"]),
                "technicalLoweringAudit": copy.deepcopy(compiled["runtimeContract"]["technicalLoweringAudit"]),
                "containsFamilyAuthority": any(key in json.dumps(compiled, ensure_ascii=False) for key in ("runtimeFamily", "weaponFamily")),
            })
        else:
            row["wireValid"] = False
        row_ok = bool(row.get("authorValid") and row.get("wireValid") and not row.get("containsFamilyAuthority"))
        row["ok"] = row_ok
        all_ok = all_ok and row_ok
        fixture_rows.append(row)

    parent_a = {"name": "Workbench", "id": "parent_a", "damage": 0, "useTime": 20, "tags": ["furniture"]}
    parent_b = {"name": "Blade", "id": "parent_b", "damage": 18, "useTime": 24, "tags": ["metal"]}
    prompt = planner_prompt_usability_report(parent_a, parent_b, parent_a, parent_b, "proof")
    all_ok = all_ok and bool(prompt.get("ok")) and not bool(prompt.get("containsWeaponMacro")) and not bool(prompt.get("containsFamilyRouter"))
    return {
        "schema": "infini.low-level-runtime-proof.v1",
        "ok": all_ok,
        "runtimeApi": "infini.runtime-program.v5",
        "capabilityCount": len(CAPABILITY_REGISTRY),
        "prompt": prompt,
        "fixtures": fixture_rows,
    }


def assert_runtime_program_proof(report: dict[str, Any] | None = None) -> dict[str, Any]:
    result = report or build_runtime_program_proof()
    if not result.get("ok"):
        failed = [row.get("id") for row in result.get("fixtures") or [] if not row.get("ok")]
        raise AssertionError(f"low-level runtime proof failed: {failed}; prompt={result.get('prompt')}")
    return result


def write_runtime_program_proof(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_runtime_program_proof(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


__all__ = ["assert_runtime_program_proof", "build_runtime_program_proof", "write_runtime_program_proof"]
