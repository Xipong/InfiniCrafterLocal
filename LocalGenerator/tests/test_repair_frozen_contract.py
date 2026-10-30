"""Canonical frozen JSON values, Visual exact locations and captured offline replays."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.llm_authoring_pipeline import build_gameplay_repair_dossier
from infini_local.pipelines import visual_generation_pipeline as visual
from tests.test_visual_presentation_metadata import kit
from tests.captured_projectile_author import project_captured_projectile_call
from tests.captured_parent_combat_author import captured_parent_combat_author
from tests.captured_spawn_velocity_author import captured_spawn_velocity_author


def test_saved_initial_projectile_lifetime_compiles_without_repair(monkeypatch):
    # Exact initial saved answer, not the campaign's later repaired/final output.
    import hashlib
    from test_gameplay_repair_readonly_context import _offline_builder
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import gameplay_stage as combine
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts

    path = Path(__file__).with_name("fixtures") / "projectile_lifetime_initial_author.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "d9a149814d5fa0894e1757fe384882bffbfa20813c700f540c2a0b4404c6b89c"
    saved = json.loads(raw)
    before = copy.deepcopy(saved)
    from captured_projectile_author import project_captured_world_units
    assert not validate_runtime_program(saved)["ok"]
    current = project_captured_world_units(saved)
    requests = []

    def respond(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(current)}}]}

    def no_repair(*_args, **_kwargs):
        raise AssertionError("saved initial Author must not invoke Repair")

    _offline_builder(monkeypatch, "json_object", respond)
    monkeypatch.setattr(combine, "repair_author_item_after_failure", no_repair)
    initial = author.try_llm_plan({}, {}, "saved-initial-projectile-lifetime")
    assert initial is not None
    assert initial["runtimeProgram"] == current["runtimeProgram"]
    wire = combine.compile_and_validate_authored_runtime(
        initial, {}, {}, "saved-initial-projectile-lifetime",
        run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
    assert len(requests) == 1
    assert wire["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 0
    assert saved == before
    assert initial["runtimeProgram"] == current["runtimeProgram"]
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                   authored_document=current, final_document=wire)["ok"]
    sentry = next(row for row in wire["runtimeProgram"]["entities"]
                  if row["id"] == "queen_ichor_sentry")
    assert sentry["lifetimeTicks"] == 36000
    assert wire["runtimeProgram"]["limits"]["maxEventSpawnsPerActivation"] == 32


@pytest.mark.parametrize("original,candidate,paths,expected", [
    pytest.param({"leaf": True, "sibling": "old"}, {"leaf": 1, "sibling": "hostile"}, ["leaf"], {"leaf": 1, "sibling": "old"}, id="authorized-type-change-frozen-sibling"),
    pytest.param({"leaf": 1}, {"leaf": 1.0}, [], {"leaf": 1}, id="frozen-integer-not-float"),
    pytest.param({"nested": [{"leaf": False}]}, {"nested": [{"leaf": 0}]}, [], {"nested": [{"leaf": False}]}, id="nested-boolean-not-integer"),
    pytest.param({"profile": [1, True, 0]}, {"profile": [1, 1, 0]}, ["profile[1]"], {"profile": [1, True, 0]}, id="array-not-thawed-by-descendant"),
    pytest.param({"a": [None, False, 1, 1.0], "b": {"c": 0}}, {"b": {"c": 0}, "a": [None, False, 1, 1.0]}, [], {"a": [None, False, 1, 1.0], "b": {"c": 0}}, id="object-order-is-not-a-change"),
])
def test_frozen_json_permissions_preserve_types_and_unchanged_source(original, candidate, paths, expected):
    before = json.dumps(original), json.dumps(candidate)
    merged, _ignored, _accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=paths, audit_path="$", allow_additions=False)
    assert json.dumps(merged, sort_keys=True) == json.dumps(expected, sort_keys=True)
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
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
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


def _current_grammar_scenario(document):
    # Explicit test-only current-grammar counterpart, NOT raw historical replay
    # or production migration. Preserve the original artifact for refusal checks.
    from infini_local.core.runtime_authoring.capability_registry import capability_for_saved_receipt
    projected = captured_parent_combat_author(copy.deepcopy(document))
    renames = {"item_use": ("releaseTiming", "customHeldSprite"),
               "spawn": ("speedPxPerTick", "speedPxPerUpdate"),
               "projectile_collision": ("localNpcHitCooldownTicks", "localNpcHitCooldownEngineUnits")}
    for row in projected.get("runtimeProgram", {}).get("calls", []) + projected.get("callsUpsert", []):
        cap = capability_for_saved_receipt(row.get("fn"))
        if cap is not None:
            row["fn"] = cap.name
        pair = renames.get(row.get("fn"))
        if pair and pair[0] in row.get("params", {}):
            assert pair[1] not in row["params"]
            row["params"][pair[1]] = row["params"].pop(pair[0])
        params = row.get("params", {})
        if row.get("fn") == "item_use" and "customHeldSprite" in params:
            value = params["customHeldSprite"]
            mapping = {"": "inherit", "immediate": "hidden", "on_release": "visible", "after_charge": "visible"}
            if isinstance(value, str) and value in mapping:
                params["customHeldSprite"] = mapping[value]
        if row.get("fn") == "configure_placeable" and params.get("wallId") == -1:
            row["fn"] = "place_tile"
            del params["wallId"]
        elif row.get("fn") == "configure_placeable" and params.get("tileId") == -1:
            row["fn"] = "place_wall"
            del params["tileId"]
        project_captured_projectile_call(row)
    from tests.captured_projectile_author import project_captured_author_notation
    return project_captured_author_notation(captured_spawn_velocity_author(projected))


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


@pytest.mark.parametrize("section,case,fresh_motion", [
    pytest.param(section, case, False, id=case)
    for section in ("gameplayApplyCases", "gameplayDiagnosticCases") for case in _REPLAY[section]
] + [pytest.param("gameplayApplyCases", "ropebound_spear", True, id="ropebound_spear-independent-composition")])
def test_current_grammar_gameplay_repair_scenario_from_capture(section, case, fresh_motion):
    archive_before = copy.deepcopy(_REPLAY[section][case])
    # Archived answers are evidence, not fresh v7 Author/Repair input. The
    # following executable scenario is independently named and projected.
    assert not validate_runtime_program(archive_before["initialAuthor"])["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(archive_before["initialAuthor"])
    if section == "gameplayApplyCases":
        from infini_local.core.runtime_authoring.program_schema import strict_repair_shape_report
        # The archived mandatory report tree also exceeds today's finite
        # patch envelope; that explicit refusal is not replay acceptance.
        with pytest.raises(RuntimeError, match="Author input exceeds schema-derived work bounds"):
            strict_repair_shape_report(archive_before["repairPatch"])
    replay = copy.deepcopy(archive_before)
    initial = _current_grammar_scenario(replay["initialAuthor"])
    if fresh_motion:
        # A separate future Author control, NOT a migration or recompile of the
        # retired code19 capture. All choices are explicit and the RAW is frozen.
        old = next(row for row in initial["runtimeProgram"]["calls"] if row["fn"] == "move_forward_then_retract")
        initial["runtimeProgram"]["calls"].remove(old)
        initial["runtimeProgram"]["calls"].extend([
            {"id": "explicit_axis", "fn": "set_aim", "target": old["target"],
             "params": {"source": "cursor", "turnOwner": False}},
            {"id": "explicit_anchor", "fn": "attach", "target": old["target"],
             "params": {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0,
                        "reachCurve": {"duration": 31 / 60, "startOffsetBlocks": 1.125,
                        "peakOffsetBlocks": 6.125, "endOffsetBlocks": 1.125, "peakProgress": 0.5}}},
        ])
    historical_patch = _current_grammar_scenario(replay["repairPatch"]) if section == "gameplayApplyCases" else None
    if historical_patch is not None:
        # The old sparse-notation projector dropped valid fixed placement lanes.
        # They are legal again: retain the captured model's explicit correction,
        # never synthesize it from current alternatives or change archive bytes.
        captured_by_id = {row["id"]: row for row in replay["repairPatch"].get("bindingsUpsert", [])}
        for row in historical_patch.get("bindingsUpsert", []):
            captured_policy = captured_by_id[row["id"]].get("usePolicy", {})
            if captured_policy.get("action", {}).get("kind") == "place_item":
                for key in ("stackCost", "contactDamage"):
                    if key in captured_policy:
                        row[key] = copy.deepcopy(captured_policy[key])
    old_axe = None
    if case == "obsidian_pickaxe":
        tool = next(row for row in initial["runtimeProgram"]["calls"] if row["fn"] == "tool_stats")
        old_axe = tool["params"].pop("axePower")
        assert type(old_axe) is int and 0 <= old_axe <= 100
        tool["params"]["axePower"] = old_axe * 5
        for row in historical_patch["callsUpsert"]:
            if row["fn"] == "tool_stats":
                assert row["params"].pop("axePower") == old_axe
                row["params"]["axePower"] = old_axe * 5
    initial_before = copy.deepcopy(initial)
    report = validate_runtime_program(initial)
    expected_codes = set(replay["expectedInitialCodes"])
    retired_motion = case == "ropebound_spear" and not fresh_motion
    if retired_motion:
        expected_codes.add("unknown_capability")
        old = next(row for row in initial["runtimeProgram"]["calls"] if row["fn"] == "move_forward_then_retract")
        index = initial["runtimeProgram"]["calls"].index(old)
        assert [(row["path"], row["code"]) for row in report["errors"] if row["code"] == "unknown_capability"] == [
            (f"$.runtimeProgram.calls[{index}].fn", "unknown_capability")]
    if fresh_motion:
        # The old shape_one_of was exclusively the captured conflicting binding;
        # the explicit independent trajectory introduces no new diagnostic.
        assert case == "ropebound_spear"
    if case == "obsidian_pickaxe":
        # Native tool admission no longer requires an independent combat lane.
        # Preserve captured bytes and every remaining historical refusal.
        expected_codes.remove("missing_binding_dependency")
    if case in {"ropebound_spear", "silt_extractinator"}:
        # Fixed placement cost is legal again only as exact integer one.
        # Captured wrong cost still receives the original const + semantic refusal.
        assert "shape_const" in expected_codes
        assert any(row["code"] == "shape_const" and row["path"].endswith(".stackCost") for row in report["errors"])
        assert any(row["code"] == "place_item_without_stack_cost" and row["path"].endswith(".stackCost") for row in report["errors"])
    assert {str(row.get("code") or "") for row in report.get("errors") or []} == expected_codes
    scope = build_runtime_repair_scope(initial, report["errors"])
    if historical_patch is not None:
        # Captured report ceremony is retired. Apply the projected executable
        # correction without making the historical advisory tree a current
        # provider requirement; fixture/archive bytes remain untouched.
        assert historical_patch.pop("realizationReplacement") is not None
        filtered, audit = filter_repair_patch_scope(initial, historical_patch, scope)
        if retired_motion:
            assert not audit["ok"]
            assert [(row["code"], row["actual"]["code"], row["actual"]["affectedIds"])
                    for row in audit["errors"]] == [
                ("repair_scope_violation", "shape_one_of", ["call_movement"]),
                ("repair_scope_violation", "unknown_capability", ["call_movement"]),
            ]
        else:
            assert audit["ok"], audit
        repaired = apply_repair_patch(initial, filtered)
        assert repaired["realization"] == initial["realization"]
        final_report = validate_runtime_program(repaired)
        if retired_motion:
            # Binding repair still executes, but cannot turn a retired Author
            # card back into a fresh capability. Preserve its exact RAW call.
            assert {row["code"] for row in final_report["errors"]} == {"shape_one_of", "unknown_capability"}
            retained_call = next(row for row in initial_before["runtimeProgram"]["calls"] if row["fn"] == "move_forward_then_retract")
            retained_index = initial_before["runtimeProgram"]["calls"].index(retained_call)
            assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == retained_call["id"]) == retained_call
            assert all(row["path"].startswith(f"$.runtimeProgram.calls[{retained_index}]") for row in final_report["errors"])
            with pytest.raises(ValueError):
                compile_runtime_program(repaired)
        else:
            assert final_report["ok"], final_report
        if case == "ropebound_spear":
            lane = next(row for row in repaired["runtimeProgram"]["bindings"] if row["id"] == "bind_place_rope")
            assert lane["input"] == "alternate_use" and lane["stackCost"] == 1
            assert repaired["runtimeProgram"]["calls"] == initial_before["runtimeProgram"]["calls"]
            if fresh_motion:
                from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
                from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
                wire = compile_runtime_program(repaired)
                assert validate_runtime_wire(wire)["ok"]
                for source in (repaired, None):
                    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                        authored_document=source, final_document=wire)["ok"]
        if case == "obsidian_pickaxe":
            assert old_axe is not None
            assert compile_runtime_program(repaired)["gameplay"]["axePower"] == old_axe
    else:
        dossier = build_gameplay_repair_dossier(initial, {}, {}, failure_report=report)
        assert dossier["repairScope"] == scope
        expected_paths = replay.get("expectedMutableBindingPaths")
        if expected_paths is not None:
            actual = {row["id"]: row["paths"] for row in scope["fieldPermissions"]["bindings"]}
            assert case == "jester_bow"
            assert expected_paths == {"b_primary_use": ["action", "input", "target", "usePolicy", "usePolicy.action.targetId"], "b_spawn_arrow": ["input"]}
            projected = {"b_primary_use": ["action", "action.kind", "action.targetId", "input", "target"], "b_spawn_arrow": ["input"]}
            assert actual == projected
            assert all(not any(path.startswith("usePolicy") for path in paths) for paths in actual.values())
            assert scope["retarget"]["bindingTargetIds"] == replay["expectedRetargetBindingTargetIds"]
        source_code = replay.get("createAllowedFnsFromErrorCode")
        if source_code is not None:
            error = next(row for row in report["errors"] if row["code"] == source_code)
            create = scope["create"]["calls"]
            assert create["allowed"] is True
            assert create["allowedTargetIds"] == replay["expectedCreateCallTargetIds"]
            assert set(create["allowedFns"]) == set(error["allowed"])
            assert {row["fn"] for row in dossier["blockerCapabilities"]} == set(error["allowed"]).union(replay.get("expectedAdditionalBlockerCapabilities", []))
    assert initial == initial_before
    assert _REPLAY[section][case] == archive_before


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
    current_entity_schema = visual._visual_entity_schema
    def historical_entity_schema(entity_ids, item_body_id=None):
        schema = current_entity_schema(entity_ids, item_body_id)
        root = (schema.get("oneOf") or [schema])[0]
        for field, limit in (("prompt", 1400), ("silhouette", 700), ("visualIdentity", 700)):
            root["properties"][field] = {"type": "string", "minLength": 1, "maxLength": limit}
            root["required"].append(field)
        return schema
    # Preserve the captured v1 grammar; this is not a production legacy reader.
    monkeypatch.setattr(visual, "_visual_entity_schema", historical_entity_schema)
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
