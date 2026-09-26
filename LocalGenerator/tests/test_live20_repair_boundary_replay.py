from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring import (
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    validate_runtime_program,
)
from infini_local.pipelines.llm_authoring_pipeline import build_gameplay_repair_dossier
from infini_local.pipelines.visual_generation_pipeline import (
    _apply_visual_repair_patch,
    _build_visual_repair_scope,
    _validate_kit,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "live20_repair_boundary_replay.json"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _project_historical_call_names(document: dict[str, Any]) -> dict[str, Any]:
    # Test-only identity projection of this captured pre-rename panel. Preserve
    # the archived provider bytes and all values; do not accept aliases in Author.
    projected = copy.deepcopy(document)
    renames = {
        "configure_item_use": ("releaseTiming", "heldSpriteVisibilityHint"),
        "configure_spawn": ("speedPxPerTick", "speedPxPerUpdate"),
        "set_projectile_collision": ("localNpcHitCooldownTicks", "localNpcHitCooldownEngineUnits"),
    }
    calls = projected.get("runtimeProgram", {}).get("calls", []) + projected.get("callsUpsert", [])
    for call in calls:
        pair = renames.get(call.get("fn"))
        if pair and pair[0] in call.get("params", {}):
            assert pair[1] not in call["params"]
            call["params"][pair[1]] = call["params"].pop(pair[0])
    return projected


def _codes(report: dict[str, Any]) -> set[str]:
    return {str(row.get("code") or "") for row in report.get("errors") or []}


def _assert_no_tooltip_field(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        assert "tooltip" not in value, f"forbidden tooltip field at {path}"
        for key, child in value.items():
            _assert_no_tooltip_field(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_tooltip_field(child, f"{path}[{index}]")


def test_captured_live20_repair_boundaries_close_offline() -> None:
    fixture = _fixture()
    assert fixture["schema"] == "infini.live20-repair-boundary-replay.v1"
    assert fixture["sourceHead"] == "e73db62bde4bfa0254d79444faa4374efe9d15b3"
    _assert_no_tooltip_field(fixture)

    for case, replay in fixture["gameplayApplyCases"].items():
        initial = _project_historical_call_names(replay["initialAuthor"])
        historical_patch = _project_historical_call_names(replay["repairPatch"])
        old_axe: int | None = None
        if case == "obsidian_pickaxe":
            # The archived model response used the earlier internal Item.axe
            # unit. Replay only this frozen witness with the declared, exact
            # inverse projection; this is not a production Author alias.
            tool = next(row for row in initial["runtimeProgram"]["calls"]
                        if row["fn"] == "configure_tool")
            old_axe = tool["params"].pop("axePower")
            assert type(old_axe) is int and 0 <= old_axe <= 100
            tool["params"]["axePowerTooltipPercent"] = old_axe * 5
            for row in historical_patch["callsUpsert"]:
                if row["fn"] == "configure_tool":
                    assert row["params"].pop("axePower") == old_axe
                    row["params"]["axePowerTooltipPercent"] = old_axe * 5
        report = validate_runtime_program(initial)
        assert _codes(report) == set(replay["expectedInitialCodes"]), case
        scope = build_runtime_repair_scope(initial, report["errors"])
        assert historical_patch["realizationReplacement"] is not None, case
        filtered, audit = filter_repair_patch_scope(initial, historical_patch, scope)
        assert audit["ok"], {"case": case, "audit": audit}
        repaired = apply_repair_patch(initial, filtered)
        assert repaired["realization"] == historical_patch["realizationReplacement"], case
        final = validate_runtime_program(repaired)
        assert final["ok"], {"case": case, "errors": final["errors"]}
        if case == "obsidian_pickaxe":
            assert old_axe is not None
            assert compile_runtime_program(repaired)["gameplay"]["axePower"] == old_axe

    for case, replay in fixture["gameplayDiagnosticCases"].items():
        initial = _project_historical_call_names(replay["initialAuthor"])
        report = validate_runtime_program(initial)
        assert _codes(report) == set(replay["expectedInitialCodes"]), case
        scope = build_runtime_repair_scope(initial, report["errors"])
        dossier = build_gameplay_repair_dossier(
            initial,
            {},
            {},
            {},
            {},
            failure_report=report,
        )
        assert dossier["repairScope"] == scope

        expected_paths = replay.get("expectedMutableBindingPaths")
        if expected_paths is not None:
            actual_paths = {
                row["id"]: row["paths"]
                for row in scope["fieldPermissions"]["bindings"]
            }
            # Preserve the archived witness verbatim. Its former diagnostic
            # alias `action` now names the actual authored discriminator leaf;
            # this test-only projection must not broaden any other permission.
            projected_paths = {
                binding_id: sorted("usePolicy.action.kind" if path == "action" else path for path in paths)
                for binding_id, paths in expected_paths.items()
            }
            assert actual_paths == projected_paths, case
            assert all("action" not in paths for paths in actual_paths.values()), case
            assert scope["retarget"]["bindingTargetIds"] == replay["expectedRetargetBindingTargetIds"]

        source_code = replay.get("createAllowedFnsFromErrorCode")
        if source_code is not None:
            source_error = next(row for row in report["errors"] if row["code"] == source_code)
            create_calls = scope["create"]["calls"]
            assert create_calls["allowed"] is True, case
            assert create_calls["allowedTargetIds"] == replay["expectedCreateCallTargetIds"]
            assert set(create_calls["allowedFns"]) == set(source_error["allowed"])
            expected_blockers = set(source_error["allowed"]).union(
                replay.get("expectedAdditionalBlockerCapabilities", [])
            )
            assert {
                row["fn"] for row in dossier["blockerCapabilities"]
            } == expected_blockers

    for case, replay in fixture["visualApplyCases"].items():
        raw = replay["visualRaw"]
        entity_ids = replay["entityIds"]
        item_body_id = replay["itemBodyId"]
        kit, errors = _validate_kit(raw, entity_ids, item_body_id)
        assert kit is None, case
        assert [row["path"] for row in errors] == replay["expectedInitialErrorPaths"]
        scope = _build_visual_repair_scope(raw, errors, entity_ids, item_body_id)
        repaired, audit = _apply_visual_repair_patch(
            raw,
            replay["visualRepairPatch"],
            scope,
            entity_ids,
            return_audit=True,
        )
        assert audit["ok"], {"case": case, "audit": audit}
        final, final_errors = _validate_kit(repaired, entity_ids, item_body_id)
        assert final is not None, {"case": case, "errors": final_errors}
