"""Canonical frozen JSON values, Visual exact locations and captured offline replays."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program,
)
from infini_local.pipelines.llm_authoring_pipeline import build_gameplay_repair_dossier
from infini_local.pipelines import visual_generation_pipeline as visual
from tests.test_visual_presentation_metadata import kit


_TYPE_PAIRS = [(True, 1), (False, 0), (1, True), (0, False), (1.0, 1), (1, 1.0)]
_MERGE_CASES = [pytest.param("typed", old, new, shape, id=f"{shape}-{type(old).__name__}-{old}-to-{type(new).__name__}-{new}")
                for old, new in _TYPE_PAIRS for shape in ("scalar", "object", "nested_array")]
_MERGE_CASES += [pytest.param("descendant", None, None, permission, id="atomic-" + permission) for permission in ("profile[1]", "profile.1")]
_MERGE_CASES += [pytest.param("unchanged", None, None, "", id="same-typed-reordered"), pytest.param("sibling", None, None, "leaf", id="typed-leaf-hostile-sibling")]


@pytest.mark.parametrize("case,old,new,shape", _MERGE_CASES)
def test_frozen_json_type_and_permission_contract(case, old, new, shape):
    if case == "typed":
        if shape == "scalar":
            original, candidate, path = old, new, ""
        elif shape == "object":
            original, candidate, path = {"leaf": old}, {"leaf": new}, "leaf"
        else:
            original, candidate, path = {"nested": [{"leaf": old}]}, {"nested": [{"leaf": new}]}, "nested"
        expected, accepted, ignored_paths = candidate, ["$" + ("." + path if path else "")], []
    elif case == "descendant":
        original, candidate, path = {"profile": [1, True, 0]}, {"profile": [1, 1, 0]}, shape
        expected, accepted, ignored_paths = original, [], ["$.profile"]
    elif case == "unchanged":
        original = {"a": [None, False, 1, 1.0, "1"], "b": {"c": 0}}
        candidate = {"b": {"c": 0}, "a": [None, False, 1, 1.0, "1"]}
        path, expected, accepted, ignored_paths = "", original, [], []
    else:
        original, candidate, path = {"leaf": True, "sibling": "old"}, {"leaf": 1, "sibling": "new"}, "leaf"
        expected, accepted, ignored_paths = {"leaf": 1, "sibling": "old"}, ["$.leaf"], ["$.sibling"]
    before = json.dumps(original), json.dumps(candidate)
    merged, ignored, actual = merge_frozen_subtree(original, candidate, mutable_paths=[path], audit_path="$", allow_additions=False)
    assert json.dumps(merged, sort_keys=True) == json.dumps(expected, sort_keys=True), "schema_type_identity_and_exact_permission"
    assert actual == accepted
    assert [row["path"] for row in ignored] == ignored_paths
    assert all(row["reason"] == "frozen_valid_value" for row in ignored)
    if case == "typed":
        frozen, denied, accepted = merge_frozen_subtree(original, candidate, mutable_paths=[], audit_path="$", allow_additions=False)
        assert json.dumps(frozen) == before[0]
        assert len(denied) == 1 and denied[0]["path"] == "$" + ("." + path if path else "")
        assert denied[0]["reason"] == "frozen_valid_value" and not accepted
    elif case == "unchanged":
        assert merged is not original and merged["a"] is not original["a"]
    assert (json.dumps(original), json.dumps(candidate)) == before


@pytest.mark.parametrize("domain", ["entity", "item_grip"])
def test_visual_literal_member_deletion_is_exact(domain):
    raw = kit()
    if domain == "entity":
        original = raw["entities"][0]
        candidate = copy.deepcopy(original)
        candidate["scale"] = 2.0
        key, relative, patch_edits = "scale.extra", '["scale.extra"]', {"entitiesUpsert": [candidate]}
        original[key] = "foreign"
    else:
        original = raw["item"]
        original["grip"] = {"normalizedX": 0.25, "normalizedY": 0.75}
        key, relative = "normalizedX.extra", 'grip["normalizedX.extra"]'
        original["grip"][key] = "foreign"
        patch_edits = {"itemPatch": {"grip": {"normalizedX": 0.9, "normalizedY": 0.1}}}
    before = copy.deepcopy(raw)
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert errors
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert (scope["fieldPermissions"]["entities"] if domain == "entity" else scope["fieldPermissions"]["itemPaths"]) == ([{"entityId": "opaque_id", "paths": [relative]}] if domain == "entity" else [relative])
    patch = {
        "schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None, "equipOverlayPatch": None,
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [], "animationPlan": None,
        "note": "remove literal member", **patch_edits}
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"], return_audit=True)
    expected = copy.deepcopy(raw)
    (expected["entities"][0] if domain == "entity" else expected["item"]["grip"]).pop(key)
    assert repaired == expected, "visual_literal_member_and_frozen_siblings"
    assert audit["ok"] and audit["ignoredChanges"]
    assert not visual._validate_kit(repaired, ["opaque_id"], "opaque_id", equipment_overlay_required=True)[1]
    assert raw == before


_FIXTURE = Path(__file__).with_name("fixtures") / "live20_repair_boundary_replay.json"
_REPLAY = json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _historical_names(document):
    # Narrow test-only projection; archive and all unrelated values stay intact.
    projected = copy.deepcopy(document)
    renames = {"configure_item_use": ("releaseTiming", "heldSpriteVisibilityHint"),
               "configure_spawn": ("speedPxPerTick", "speedPxPerUpdate"),
               "set_projectile_collision": ("localNpcHitCooldownTicks", "localNpcHitCooldownEngineUnits")}
    for row in projected.get("runtimeProgram", {}).get("calls", []) + projected.get("callsUpsert", []):
        pair = renames.get(row.get("fn"))
        if pair and pair[0] in row.get("params", {}):
            assert pair[1] not in row["params"]
            row["params"][pair[1]] = row["params"].pop(pair[0])
    return projected


def test_replay_frozen_provenance():
    assert _REPLAY["schema"] == "infini.live20-repair-boundary-replay.v1"
    assert _REPLAY["sourceHead"] == "e73db62bde4bfa0254d79444faa4374efe9d15b3"
    pending = [("$", _REPLAY)]
    while pending:
        path, value = pending.pop()
        if isinstance(value, dict):
            assert "tooltip" not in value, f"forbidden tooltip field at {path}"
            pending.extend((path + "." + key, child) for key, child in value.items())
        elif isinstance(value, list):
            pending.extend((f"{path}[{index}]", child) for index, child in enumerate(value))


@pytest.mark.parametrize("section,case", [pytest.param(section, case, id=case) for section in ("gameplayApplyCases", "gameplayDiagnosticCases") for case in _REPLAY[section]])
def test_captured_gameplay_repair_replay(section, case):
    replay = copy.deepcopy(_REPLAY[section][case])
    initial = _historical_names(replay["initialAuthor"])
    historical_patch = _historical_names(replay["repairPatch"]) if section == "gameplayApplyCases" else None
    old_axe = None
    if case == "obsidian_pickaxe":
        tool = next(row for row in initial["runtimeProgram"]["calls"] if row["fn"] == "configure_tool")
        old_axe = tool["params"].pop("axePower")
        assert type(old_axe) is int and 0 <= old_axe <= 100
        tool["params"]["axePowerTooltipPercent"] = old_axe * 5
        for row in historical_patch["callsUpsert"]:
            if row["fn"] == "configure_tool":
                assert row["params"].pop("axePower") == old_axe
                row["params"]["axePowerTooltipPercent"] = old_axe * 5
    report = validate_runtime_program(initial)
    assert {str(row.get("code") or "") for row in report.get("errors") or []} == set(replay["expectedInitialCodes"])
    scope = build_runtime_repair_scope(initial, report["errors"])
    if historical_patch is not None:
        assert historical_patch["realizationReplacement"] is not None
        filtered, audit = filter_repair_patch_scope(initial, historical_patch, scope)
        assert audit["ok"], audit
        repaired = apply_repair_patch(initial, filtered)
        assert repaired["realization"] == historical_patch["realizationReplacement"]
        assert validate_runtime_program(repaired)["ok"], validate_runtime_program(repaired)
        if case == "obsidian_pickaxe":
            assert old_axe is not None
            assert compile_runtime_program(repaired)["gameplay"]["axePower"] == old_axe
    else:
        dossier = build_gameplay_repair_dossier(initial, {}, {}, {}, {}, failure_report=report)
        assert dossier["repairScope"] == scope
        expected_paths = replay.get("expectedMutableBindingPaths")
        if expected_paths is not None:
            actual = {row["id"]: row["paths"] for row in scope["fieldPermissions"]["bindings"]}
            assert actual == {identity: sorted(paths) for identity, paths in expected_paths.items()}
            assert scope["retarget"]["bindingTargetIds"] == replay["expectedRetargetBindingTargetIds"]
        source_code = replay.get("createAllowedFnsFromErrorCode")
        if source_code is not None:
            error = next(row for row in report["errors"] if row["code"] == source_code)
            create = scope["create"]["calls"]
            assert create["allowed"] is True
            assert create["allowedTargetIds"] == replay["expectedCreateCallTargetIds"]
            assert set(create["allowedFns"]) == set(error["allowed"])
            assert {row["fn"] for row in dossier["blockerCapabilities"]} == set(error["allowed"]).union(replay.get("expectedAdditionalBlockerCapabilities", []))


@pytest.mark.parametrize("case", list(_REPLAY["visualApplyCases"]))
def test_captured_visual_repair_replay(case, monkeypatch):
    # Declared test-only historical schema projection, not fresh v1 admission.
    # Saved RAW/patch bytes and all authored choices remain untouched. The v1
    # replay verifies its old frozen deletion only; no new sizing is invented.
    current_item_schema = visual._visual_item_schema
    def historical_item_schema():
        schema = current_item_schema()
        for field in ("renderSizePx", "forwardAngleDegrees"):
            del schema["properties"][field]
            schema["required"].remove(field)
        return schema
    monkeypatch.setattr(visual, "_visual_item_schema", historical_item_schema)
    monkeypatch.setattr(visual, "VISUAL_KIT_SCHEMA", "infini.visual-kit.runtime-entities.v1")
    monkeypatch.setattr(visual, "VISUAL_REPAIR_PATCH_SCHEMA", "infini.visual-kit-repair-patch.runtime-entities.v1")
    replay = copy.deepcopy(_REPLAY["visualApplyCases"][case])
    raw, entity_ids, item_id = replay["visualRaw"], replay["entityIds"], replay["itemBodyId"]
    kit_before, errors = visual._validate_kit(raw, entity_ids, item_id)
    assert kit_before is None
    old_paths = replay["expectedInitialErrorPaths"]
    if "$.item.:palette" in old_paths:
        assert ":palette" in raw["item"]
    expected_paths = ['$.item[":palette"]' if path == "$.item.:palette" else path for path in old_paths]
    assert [row["path"] for row in errors] == expected_paths
    scope = visual._build_visual_repair_scope(raw, errors, entity_ids, item_id)
    repaired, audit = visual._apply_visual_repair_patch(raw, replay["visualRepairPatch"], scope, entity_ids, return_audit=True)
    assert audit["ok"], audit
    final, final_errors = visual._validate_kit(repaired, entity_ids, item_id)
    assert final is not None, final_errors
