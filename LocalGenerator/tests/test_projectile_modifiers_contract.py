"""A13/B15.1 explicit phase modifiers, ownership, provenance and frozen Repair."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.capability_registry import PROJECTILE_MODIFIER_COMPONENTS
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.capability_library_audit import capability_library_audit
from infini_local.qa.primitive_loss_audit import runtime_component_surface_audit
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from test_low_level_three_stage_pipeline import wire_transport

PARAMS = {
    "set_projectile_turn_modifier": dict(turnRadiansPerUpdate=.04, startDelayTicks=0, durationTicks=90),
    "set_projectile_speed_modifier": dict(speedMultiplierPerUpdate=1.01, maxSpeed=20, startDelayTicks=0, durationTicks=40),
    "set_projectile_homing_modifier": dict(rangeTiles=40, maxTurnRadiansPerUpdate=.1, requireLineOfSight=True, startDelayTicks=40, durationTicks=50),
    "attract_npcs_while_active": dict(rangeTiles=10, strengthPerUpdate=2, falloff="linear", maxTargets=8, startDelayTicks=5, durationTicks=60),
    "set_projectile_visual_scale_curve": dict(startScale=.5, endScale=4, startDelayTicks=5, durationTicks=60, curve="exponential"),
    "orient_whip_to_owner_gravity": {},
}

def call(doc, fn):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)

def source(fn):
    doc = build_capability_witness(fn)
    call(doc, fn)["params"] = deepcopy(PARAMS[fn])
    return doc

def entity(wire, fn):
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    return next(row for row in wire["runtimeProgram"]["entities"] if member in row)


@pytest.mark.parametrize("fn", PARAMS)
@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("repair", [False, True])
def test_actual_visual_and_repair_packets_preserve_exact_modifier_owner(wire_transport, monkeypatch, fn, format_mode, repair):
    from infini_local.pipelines import llm_transport, visual_generation_pipeline as visual

    data = compile_runtime_program(source(fn))
    frozen = deepcopy(data)
    responses, sent = wire_transport
    responses.append({})
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    kwargs = {"repair_errors": [{"path": "$.item.renderSizePx", "message": "required"}], "previous": {"item": {}}, "repair_scope": {}} if repair else {}
    visual._request_visual_kit(data, {}, {}, {}, {}, **kwargs)
    packet = json.loads(sent[-1]["messages"][1]["content"])
    rows = packet["runtimeEntitiesReadOnly" if repair else "runtimeEntities"]
    members = (*PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity")
    for row, accepted in zip(rows, data["runtimeProgram"]["entities"]):
        for member in members:
            assert (member in row) == (member in accepted)
            if member in accepted:
                assert row[member] == accepted[member]
                assert row["modifierMeaningReadOnly"][member] == CAPABILITY_REGISTRY[fn].summary
    formula = packet["spritePresentationReadOnly"]["formulas"]["body"]
    assert "visualScaleCurve is present" in formula
    assert "P=D*E*curveScale(active age) from that explicit visual owner" in formula
    assert "otherwise q_selected * clamp(P, .1, 8)" in formula
    assert packet["spritePresentationReadOnly"]["formulas"]["liveBodyCopy"].startswith("q_selected * clamp(P, .1, 8)")
    assert data == frozen

@pytest.mark.parametrize("fn", PARAMS)
def test_complete_vertical_witness_exact_identity_and_source_receipts(fn):
    doc = source(fn); before = deepcopy(doc)
    compiled = compile_runtime_program(doc)
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    assert entity(compiled, fn)[member] == (PARAMS[fn] if fn in PROJECTILE_MODIFIER_COMPONENTS else True)
    assert doc == before and validate_runtime_wire(compiled)["ok"]
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    owned = [row for row in rows if row.get("fn") == fn]
    assert len(owned) == (len(PARAMS[fn]) or 1)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=compiled)["ok"]
    assert audit_compiler_receipts(rows, final_document=compiled)["ok"]

@pytest.mark.parametrize("fn,leaf", [(fn, key) for fn, values in PARAMS.items() for key in values])
def test_all_new_choices_are_required_in_author_and_persisted_component(fn, leaf):
    doc = source(fn); compiled = compile_runtime_program(doc)
    del call(doc, fn)["params"][leaf]
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(doc)
    del entity(compiled, fn)[PROJECTILE_MODIFIER_COMPONENTS[fn]][leaf]
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn,leaf,value", [
    (fn, leaf, value)
    for fn, values in PARAMS.items() for leaf, original in values.items()
    for value in ([None, True, "1", -22000, float("inf"), float("nan")] if type(original) in (int, float)
                  else [None, 0, "unknown"] if isinstance(original, bool) else [None, 1, "unknown"])
])
def test_invalid_present_choice_is_red_at_author_and_wire_boundary(fn, leaf, value):
    doc = source(fn); compiled = compile_runtime_program(doc)
    call(doc, fn)["params"][leaf] = value
    assert not validate_runtime_program(doc)["ok"]
    entity(compiled, fn)[PROJECTILE_MODIFIER_COMPONENTS[fn]][leaf] = value
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn", PARAMS)
@pytest.mark.parametrize("mutation", ["null", "unknown", "duplicate", "receipt_deleted", "other_entity", "item_target"])
def test_modifier_cannot_be_injected_or_reassigned_without_authority(fn, mutation):
    doc = source(fn); compiled = compile_runtime_program(doc)
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    if mutation == "duplicate":
        second = deepcopy(call(doc, fn)); second["id"] = "duplicate_modifier"
        doc["runtimeProgram"]["calls"].append(second)
        assert not validate_runtime_program(doc)["ok"]
        return
    if mutation == "null": entity(compiled, fn)[member] = None
    elif mutation == "unknown":
        if fn in PROJECTILE_MODIFIER_COMPONENTS: entity(compiled, fn)[member]["familyInference"] = "spiral"
        else: entity(compiled, fn)[member] = False
    elif mutation == "receipt_deleted":
        compiled["runtimeContract"]["finalWireReceipts"] = [r for r in compiled["runtimeContract"]["finalWireReceipts"] if r.get("fn") != fn]
    elif mutation == "other_entity":
        for row in compiled["runtimeContract"]["finalWireReceipts"]:
            if row.get("fn") == fn: row["finalPath"] = row["finalPath"].replace("entities[1]", "entities[0]")
    else: compiled["runtimeProgram"]["entities"][0][member] = entity(compiled, fn).pop(member)
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn", PROJECTILE_MODIFIER_COMPONENTS)
def test_frozen_repair_changes_only_invalid_phase_leaf(fn):
    doc = source(fn); call(doc, fn)["params"]["durationTicks"] = 0
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    replacement = deepcopy(call(doc, fn)); replacement["params"]["durationTicks"] = 100
    replacement["params"]["startDelayTicks"] = 21000
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [replacement], "note": "fix invalid duration only"}, scope)
    assert audit["ok"]
    repaired = apply_repair_patch(doc, patch)
    call(before, fn)["params"]["durationTicks"] = 100
    assert repaired == before
    compile_runtime_program(repaired)

def test_simultaneous_and_delayed_modifiers_are_independent_of_the_movement_slot():
    doc = source("set_projectile_turn_modifier")
    target = call(doc, "set_projectile_turn_modifier")["target"]
    for index, fn in enumerate(list(PROJECTILE_MODIFIER_COMPONENTS)[1:]):
        doc["runtimeProgram"]["calls"].append(dict(id=f"modifier_{index}", fn=fn, target=target, params=deepcopy(PARAMS[fn])))
    doc["runtimeProgram"]["calls"].append(dict(id="gameplay_curve", fn="set_projectile_hitbox_curve", target=target,
        params=dict(startScale=1, endScale=2, startDelayTicks=0, durationTicks=80, curve="linear", mirrorToSprite=False)))
    compiled = compile_runtime_program(doc)
    final = entity(compiled, "set_projectile_turn_modifier")
    assert final["movement"]["code"] == 0
    for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items(): assert final[member] == PARAMS[fn]
    assert final["hitboxCurve"]["endScale"] == 2
    call(doc, "set_projectile_hitbox_curve")["params"]["mirrorToSprite"] = True
    errors = validate_runtime_program(doc)["errors"]
    assert any(row["code"] == "exclusive_component_conflict" and row["path"].endswith("mirrorToSprite") for row in errors)
    scope = build_runtime_repair_scope(doc, errors)
    fix = deepcopy(call(doc, "set_projectile_hitbox_curve")); fix["params"].update(mirrorToSprite=False, endScale=7)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [fix], "note": "retain the independent visual curve"}, scope)
    repaired = apply_repair_patch(doc, patch)
    assert call(repaired, "set_projectile_hitbox_curve")["params"]["endScale"] == 2
    compile_runtime_program(repaired)

def test_npc_attraction_alone_is_meaningful_on_a_field_without_drag():
    doc = source("attract_npcs_while_active")
    target = call(doc, "attract_npcs_while_active")["target"]
    next(row for row in doc["runtimeProgram"]["entities"] if row["id"] == target)["kind"] = "field"
    doc["runtimeProgram"]["calls"] = [row for row in doc["runtimeProgram"]["calls"] if row["fn"] not in {"move_straight", "set_projectile_damage"}]
    compiled = compile_runtime_program(doc)
    final = entity(compiled, "attract_npcs_while_active")
    assert "movement" not in final and "damage" not in final
    assert final["npcAttraction"] == PARAMS["attract_npcs_while_active"]

def test_whip_marker_requires_executed_whip_geometry():
    doc = source("orient_whip_to_owner_gravity")
    motion = call(doc, "move_whip_lash")
    motion.update(fn="move_straight", params={})
    assert not validate_runtime_program(doc)["ok"]
    compiled = compile_runtime_program(source("orient_whip_to_owner_gravity"))
    entity(compiled, "orient_whip_to_owner_gravity")["movement"].update(name="move_straight", code=0, params={})
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("driver", ["channel_beam", "move_whip_lash", "move_expanding_wave"])
def test_visual_curve_cannot_be_ignored_by_line_geometry_or_overwritten_by_another_scale_owner(driver):
    doc = build_capability_witness(driver)
    target = call(doc, driver)["target"]
    doc["runtimeProgram"]["calls"].append(dict(id="visual_curve", fn="set_projectile_visual_scale_curve", target=target,
        params=deepcopy(PARAMS["set_projectile_visual_scale_curve"])))
    assert any(row["code"] == "exclusive_component_conflict" for row in validate_runtime_program(doc)["errors"])
    compiled = compile_runtime_program(build_capability_witness(driver))
    next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == target)["visualScaleCurve"] = deepcopy(PARAMS["set_projectile_visual_scale_curve"])
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

def test_numeric_bounds_and_complete_dto_fields_are_machine_audited():
    assert runtime_component_surface_audit()["ok"]
    report = capability_library_audit()
    assert report["ok"], report.get("issues")
    dto_path = Path(__file__).parents[2] / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs"
    dto = dto_path.read_bytes().replace(b"[JsonRequired] public float StrengthPerUpdate", b"public float UnexposedPull { get; set; }\n    [JsonRequired] public float StrengthPerUpdate")
    assert not runtime_component_surface_audit(dto)["ok"]

@pytest.mark.parametrize("fn,leaf,collapsed,neutral,positive", [
    ("set_projectile_turn_modifier", "turnRadiansPerUpdate", 1e-46, 0, 0.04),
    ("set_projectile_speed_modifier", "speedMultiplierPerUpdate", 1.0000000000000002, 1, 1.01),
])
def test_non_neutral_modifier_cannot_collapse_in_the_real_consumer_and_repair_is_leaf_local(fn, leaf, collapsed, neutral, positive):
    doc = source(fn); call(doc, fn)["params"][leaf] = collapsed
    errors = validate_runtime_program(doc)["errors"]
    assert any(row["path"].endswith(".params." + leaf) for row in errors)
    scope = build_runtime_repair_scope(doc, errors)
    correction = deepcopy(call(doc, fn)); correction["params"].update({leaf: positive, "durationTicks": 20000})
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [correction], "note": "retain nonneutral consumer value"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(doc, patch)
    assert call(repaired, fn)["params"]["durationTicks"] == PARAMS[fn]["durationTicks"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    for accepted in (neutral, positive):
        control = source(fn); call(control, fn)["params"][leaf] = accepted
        assert validate_runtime_wire(compile_runtime_program(control))["ok"]
    del call(control, fn)["params"][leaf]
    assert not validate_runtime_program(control)["ok"]  # neutral metadata is not omission permission


@pytest.mark.parametrize("fn", [*PARAMS, "set_projectile_hitbox_curve"])
@pytest.mark.parametrize("mutation", ["missing-all", "status", "duplicate"])
def test_generic_provenance_owner_covers_present_modifier_slots(fn, mutation):
    doc = build_capability_witness(fn)
    wire = compile_runtime_program(doc)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    owned = [row for row in rows if row.get("fn") == fn]
    assert owned
    if mutation == "missing-all":
        rows[:] = [row for row in rows if row not in owned]
    elif mutation == "duplicate":
        rows.append(deepcopy(owned[0]))
    else:
        owned[0]["status"] = "delivered" if fn == "orient_whip_to_owner_gravity" else "technical_projection"
    # The canonical audit, not a parallel feature-specific wire checker, owns
    # provenance with and without the original Author document.
    for source_document in (None, doc):
        report = audit_compiler_receipts(rows, authored_document=source_document, final_document=wire)
        assert not report["ok"], report


def test_actual_author_request_exposes_every_explicit_choice():
    _, user, _ = build_initial_author_request({"name": "A"}, {"name": "B"}, {}, {}, "modifier-offline", model_name="test-model")
    import json
    payload = json.loads(user)
    cards = {row["fn"]: row for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    for fn, params in PARAMS.items(): assert set(cards[fn]["params"]) == set(params)

# Combined-owner acceptance: one composition, not a second provenance helper.
# Every explicit combat basis and every sampled-velocity variant is exercised
# beside the complete orthogonal modifier component inventory.
_COMBAT_CHOICES = [("authored_child", "authored_child"), ("authored_child", "live_parent"),
                   ("live_parent", "authored_child"), ("live_parent", "live_parent")]
_HAS_COMBAT = "damageBasis" in CAPABILITY_REGISTRY["spawn_entity_on_event"].params
_HAS_VELOCITY = "velocity" in CAPABILITY_REGISTRY["configure_spawn"].params
_VELOCITY_CHOICES = [None] if not _HAS_VELOCITY else [
    {"constantSpeedPxPerUpdate": 8.5},
    {"fanSpeed": {"minSpeedPxPerUpdate": 4.5, "maxSpeedPxPerUpdate": 8.5}},
    {"radial": {"minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7}},
    {"disk": {"maxSpeedPxPerUpdate": 6}},
    {"cone": {"minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7, "halfAngleRadians": .2}},
]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("bases", _COMBAT_CHOICES if _HAS_COMBAT else [None])
@pytest.mark.parametrize("velocity", _VELOCITY_CHOICES)
def test_combined_feature_modifier_complete_projection_and_actual_serialized_repair(
    monkeypatch, format_mode, bases, velocity,
):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract, llm_transport
    from test_codex_subscription_contract import _encode_nullable_fixture
    from test_repair_gameplay_contract import _offline_gameplay_repair

    feature = "spawn_entity_on_event" if bases else "select_targets_and_emit_on_event"
    doc = build_capability_witness(feature)
    producer = call(doc, feature)
    child = producer["params"]["entity"]
    spawn = next(row for row in doc["runtimeProgram"]["calls"]
                 if row["fn"] == "configure_spawn" and row["target"] == child)
    if bases:
        producer["params"].update(damageBasis=bases[0], knockbackBasis=bases[1])
    if velocity:
        spawn["params"]["velocity"] = deepcopy(velocity)
    for index, fn in enumerate(PROJECTILE_MODIFIER_COMPONENTS):
        doc["runtimeProgram"]["calls"].append(dict(
            id=f"combined_modifier_{index}", fn=fn, target=child, params=deepcopy(PARAMS[fn])))
    doc["runtimeProgram"]["calls"].append(dict(id="combined_hitbox_curve", fn="set_projectile_hitbox_curve", target=child,
        params=dict(startScale=1, endScale=2, startDelayTicks=0, durationTicks=80, curve="linear", mirrorToSprite=False)))
    original = json.dumps(doc, sort_keys=True)
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "combined-merge-offline", model_name="test-model")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    cards = {row["fn"]: row for row in catalog["capabilities"]}
    def expanded(value):
        if isinstance(value, dict):
            return {key: (catalog["fieldGuide"]["consumerConstraints"][child]
                          if key == "consumerConstraint" and isinstance(child, str) else expanded(child))
                    for key, child in value.items()}
        return [expanded(child) for child in value] if isinstance(value, list) else value
    for fn in (feature, "configure_spawn", *PROJECTILE_MODIFIER_COMPONENTS):
        assert expanded(cards[fn]) == CAPABILITY_REGISTRY[fn].author_prompt_card()
    encoded = _encode_nullable_fixture(doc, contract.author_item_response_schema()) if format_mode == "json_schema" else doc
    if format_mode == "json_schema":
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(encoded)
    restored = contract.project_provider_author_item_to_local(json.loads(json.dumps(encoded)), response_format=request["response_format"])
    assert json.dumps(restored, sort_keys=True) == original
    wire = compile_runtime_program(restored)
    assert validate_runtime_wire(wire)["ok"]
    accepted_child = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == child)
    for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items():
        assert accepted_child[member] == PARAMS[fn]
    assert accepted_child["hitboxCurve"]["mirrorToSprite"] is False
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for source_document in (None, doc):
        assert audit_compiler_receipts(rows, authored_document=source_document, final_document=wire)["ok"]
        # Independent receipt lanes remain mandatory inside the combined wire.
        mandatory = ["set_projectile_turn_modifier"]
        # Old scalar spawn/event wire is legitimately source-free; newly
        # explicit combat and typed velocity require retained presence receipts.
        if bases or source_document is not None:
            mandatory.append(feature)
        if velocity or source_document is not None:
            mandatory.append("configure_spawn")
        for fn in mandatory:
            removed = [row for row in rows if row.get("fn") != fn]
            assert not audit_compiler_receipts(removed, authored_document=source_document, final_document=wire)["ok"]
    without_provenance = deepcopy(wire); without_provenance.pop("runtimeContract")
    assert validate_runtime_wire(without_provenance)["ok"]

    broken = deepcopy(doc)
    modifier = call(broken, "set_projectile_turn_modifier")
    modifier["params"]["durationTicks"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": modifier["id"], "paths": ["params.durationTicks"]}]
    fix = deepcopy(modifier); fix["params"].update(durationTicks=90, turnRadiansPerUpdate=.2)
    hostile_feature = deepcopy(producer); hostile_feature["params"]["entity"] = "item"
    hostile_spawn = deepcopy(spawn); hostile_spawn["params"]["offsetPx"] = 10
    repaired, packet = _offline_gameplay_repair(monkeypatch, broken,
        {"note": "only exact phase duration", "realizationReplacement": doc["realization"],
         "callsUpsert": [fix, hostile_feature, hostile_spawn]}, format_mode, out_of_scope_response=True)
    assert packet["repairScope"]["fieldPermissions"]["calls"] == scope["fieldPermissions"]["calls"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == original
    repaired_wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(repaired_wire)["ok"]
    assert repaired_wire == wire
    assert json.dumps(doc, sort_keys=True) == original
