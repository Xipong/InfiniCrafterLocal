"""Explicit bounded target links emit authored physical children; no radial alias."""
from copy import deepcopy
import hashlib
import json

import pytest
from repair_test_helpers import gameplay_repair, frozen_gameplay_repair
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.capability_registry import EVENT_ACTION_OPCODE
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import llm_authoring_pipeline as author
from test_codex_subscription_contract import _encode_nullable_fixture
from test_low_level_three_stage_pipeline import wire_transport


FN = "select_targets_and_emit_on_event"
CAP = CAPABILITY_REGISTRY[FN]


def _doc(**choices):
    doc = build_capability_witness(FN)
    _call(doc)["params"].update(choices)
    return doc


def _call(doc):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == FN)


def _event(wire):
    return next(event for entity in wire["runtimeProgram"]["entities"] for event in entity["events"]
                if event["action"] == FN)


def _child_spawn(doc):
    return next(row for row in doc["runtimeProgram"]["calls"]
                if row.get("target") == _call(doc)["params"]["entity"] and row["fn"] == "configure_spawn")


def test_child_reference_requirements_do_not_expand_source_entity_dependency_scope():
    doc = _doc(stepRangeTiles=61)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["capabilitySubset"] == [FN]
    assert not scope["create"]["entities"]["allowed"]
    assert not scope["create"]["calls"]["allowed"]


# Pairwise selection witnesses plus both event routes and scheduler boundaries.
@pytest.mark.parametrize("anchor,repeats,los,event_name,delay", [
    ("previous_target", "allow_revisits", False, "on_hit", 0),
    ("previous_target", "exclude_visited", True, "on_crit", 600),
    ("event_target", "allow_revisits", True, "on_hit", 600),
    ("event_target", "exclude_visited", False, "on_crit", 0),
])
def test_representative_selection_choices_reach_exact_opcode_and_receipts(anchor, repeats, los, event_name, delay):
    doc = _doc(selectionAnchor=anchor, repeatPolicy=repeats, requireLineOfSight=los, when=event_name, delaySeconds=delay / 60)
    original = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    event = _event(wire)
    assert event == {"id": "witness_call", "action": FN, "actionCode": 8,
                     **{CAP.params[k].wire_name or k: CAP.params[k].to_wire(v) for k, v in _call(doc)["params"].items()}}
    receipts = [row for row in wire["runtimeContract"]["finalWireReceipts"]
                if row.get("fn") == FN and ".params." in row["authoredPath"]]
    assert len(receipts) == len(CAP.params) == 9
    for name, spec in CAP.params.items():
        receipt = next(row for row in receipts if row["authoredPath"].endswith(".params." + name))
        assert receipt["value"] == spec.to_wire(_call(doc)["params"][name])
        assert receipt["finalPath"].endswith("." + (spec.wire_name or name))
        assert receipt["status"] == "delivered"
    assert validate_runtime_wire(wire)["ok"]
    assert doc == original


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_real_author_packet_and_nullable_inverse_preserve_full_emission_choice(wire_transport, monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    responses, requests = wire_transport
    doc = _doc(selectionAnchor="event_target", repeatPolicy="exclude_visited", requireLineOfSight=True,
               stepCount=12, stepRangeTiles=59.99999999999999, initialIgnoreCountdownUpdates=0, delaySeconds=1 / 60)
    payload = _encode_nullable_fixture(doc, contract.author_item_response_schema()) if mode == "json_schema" else doc
    responses.append(payload)
    result = author.try_llm_plan({"name": "A"}, {"name": "B"}, "explicit links")
    assert result is not None
    assert len(requests) == 1
    request = requests[0]
    assert request["response_format"]["type"] == mode
    if mode == "json_schema":
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
    assert _call(result) == _call(doc)
    assert compile_runtime_program(result)["runtimeProgram"] == compile_runtime_program(doc)["runtimeProgram"]


@pytest.mark.parametrize("name", list(CAP.params))
def test_required_choices_cannot_be_filled_by_provider_or_author_defaults(name):
    doc = _doc()
    _call(doc)["params"].pop(name)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"] and any(row["path"].endswith(".params." + name) for row in report["errors"])
    assert doc == before


@pytest.mark.parametrize("name,value", [
    ("when", "on_kill"), ("when", None), ("entity", None), ("entity", "UNKNOWN"),
    ("stepCount", None), ("stepCount", True), ("stepCount", 2.0), ("stepCount", 0), ("stepCount", 13),
    ("stepRangeTiles", False), ("stepRangeTiles", "22.5"), ("stepRangeTiles", 0.9999999999999999),
    ("stepRangeTiles", 60.00000000000001), ("stepRangeTiles", float("nan")), ("stepRangeTiles", float("inf")),
    ("selectionAnchor", None), ("selectionAnchor", "closest"), ("repeatPolicy", "never"),
    ("requireLineOfSight", 0), ("requireLineOfSight", None),
    ("initialIgnoreCountdownUpdates", None), ("initialIgnoreCountdownUpdates", -1),
    ("initialIgnoreCountdownUpdates", 601), ("initialIgnoreCountdownUpdates", 10.0),
    ("delaySeconds", True), ("delaySeconds", -0.5), ("delaySeconds", 601 / 60),
])
def test_invalid_present_author_and_saved_wire_choices_remain_red(name, value):
    doc = _doc(**{name: value})
    assert not validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(_doc())
    wire.pop("runtimeContract")
    _event(wire)[CAP.params[name].wire_name or name] = (value * 60 if name == "delaySeconds" and type(value) in (int, float) else value)
    report = validate_runtime_wire(wire)
    assert not report["ok"], report
    assert any(row["path"].endswith("." + (CAP.params[name].wire_name or name)) for row in report["errors"])


@pytest.mark.parametrize("name", list(CAP.params))
def test_saved_wire_cannot_invent_any_missing_emission_parameter(name):
    wire = compile_runtime_program(_doc())
    wire.pop("runtimeContract")
    _event(wire).pop(CAP.params[name].wire_name or name)
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name,value", [
    ("aim", "cursor"), ("aim", "facing"), ("position", {"at": "owner_center"}),
    ("position", {"at": "cursor"}), ("offsetBlocks", 1 / 16),
])
def test_reference_diagnoses_exact_exclusive_child_dependency_without_rewriting_it(name, value):
    doc = _doc(); spawn = _child_spawn(doc); spawn["params"][name] = value
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert [row["code"] for row in report["errors"]] == ["reference_requirements_unsatisfied"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": spawn["id"], "paths": ["params." + name]}]
    assert not scope["create"]["entities"]["allowed"]
    assert not scope["create"]["calls"]["allowed"]
    assert doc == before
    wire = compile_runtime_program(_doc()); wire.pop("runtimeContract")
    child = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == "witness_child")
    child["spawn"][CAPABILITY_REGISTRY["configure_spawn"].params[name].wire_name or name] = value
    assert not validate_runtime_wire(wire)["ok"]


def _copy_child(doc, name):
    entity = deepcopy(next(row for row in doc["runtimeProgram"]["entities"] if row["id"] == "witness_child"))
    entity["id"] = name
    calls = [deepcopy(row) for row in doc["runtimeProgram"]["calls"] if row.get("target") == "witness_child"]
    for row in calls:
        row["id"] = name + "_" + row["id"]
        row["target"] = name
        if row["fn"] == "configure_spawn":
            row["params"].update(aim="velocity", position={"at": "activation_origin"}, offsetBlocks=(0) / 16)
    return entity, calls


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("create", [False, True])
def test_production_repair_can_retarget_or_create_exact_child_and_freezes_existing_nodes(monkeypatch, mode, create):
    doc = _doc(); _child_spawn(doc)["params"]["aim"] = "cursor"
    # The independently valid child remains reachable through its existing
    # producer. Repair cannot delete it or invent a new producer to hide an
    # orphan caused by retargeting the only reference (negative case below).
    doc["runtimeProgram"]["calls"].append({"id": "keep_original", "target": "witness_entity", "fn": "spawn_entity_on_event",
        "params": {"entity": "witness_child", "when": "on_hit", "count": 1, "spreadRadians": 0.0,
                   "damageMultiplier": 1.0, 'delaySeconds': (0) / 60,
                   "damageBasis": "authored_child", "knockbackBasis": "authored_child"}})
    child, calls = _copy_child(doc, "selected")
    if not create:
        doc["runtimeProgram"]["entities"].append(child); doc["runtimeProgram"]["calls"].extend(calls)
        doc["runtimeProgram"]["calls"].append({"id": "keep_selected", "target": "witness_entity", "fn": "spawn_entity_on_event",
            "params": {"entity": "selected", "when": "on_hit", "count": 1, "spreadRadians": 0.0,
                       "damageMultiplier": 1.0, 'delaySeconds': (0) / 60,
                       "damageBasis": "authored_child", "knockbackBasis": "authored_child"}})
    before = deepcopy(doc)
    candidate = deepcopy(_call(doc)); candidate["params"].update(entity="selected", stepCount=12)
    hostile = deepcopy(_child_spawn(doc)); hostile["params"]["aim"] = "velocity"
    incoming = {"note": "explicit compatible child reference", "callsUpsert": [candidate, hostile],
                "realizationReplacement": doc["realization"]}
    if create:
        incoming["entitiesUpsert"] = [child]
        incoming["callsUpsert"].extend(calls)
    repaired, dossier = gameplay_repair(monkeypatch, doc, incoming, mode)
    expected = deepcopy(doc); _call(expected)["params"]["entity"] = "selected"
    if create:
        expected["runtimeProgram"]["entities"].append(child); expected["runtimeProgram"]["calls"].extend(calls)
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": "witness_call", "paths": ["params.entity"]}]
    assert doc == before


def test_reference_repair_does_not_hide_new_orphans_by_deleting_frozen_child():
    doc = _doc(); _child_spawn(doc)["params"]["aim"] = "cursor"
    child, calls = _copy_child(doc, "selected")
    candidate = deepcopy(_call(doc)); candidate["params"]["entity"] = "selected"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    filtered, report = filter_repair_patch_scope(doc, {"note": "explicit new child", "entitiesUpsert": [child], "callsUpsert": [candidate, *calls]}, scope)
    assert not report["ok"]
    assert not scope["create"]["entities"]["allowed"]
    # The impossible replacement is refused before it can orphan the old child.
    assert all(row["id"] != "selected" for row in filtered["entitiesUpsert"])
    assert _child_spawn(doc)["params"]["aim"] == "cursor"


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_leaf_repair_changes_only_invalid_range_and_keeps_all_selection_decisions(monkeypatch, mode):
    doc = _doc(stepRangeTiles=61, selectionAnchor="event_target", requireLineOfSight=True)
    candidate = deepcopy(_call(doc)); candidate["params"].update(stepRangeTiles=60, selectionAnchor="previous_target", requireLineOfSight=False)
    expected = deepcopy(doc); _call(expected)["params"]["stepRangeTiles"] = 60
    repaired, packet, final = frozen_gameplay_repair(monkeypatch, doc,
        {"note": "exact range correction", "callsUpsert": [candidate], "realizationReplacement": doc["realization"]}, mode,
        {"calls": [{"id": "witness_call", "paths": ["params.stepRangeTiles"]}]}, expected)
    assert packet["existingBrokenCapabilityCards"] == [CAP.prompt_card()]
    assert _event(final)["stepRangeTiles"] == 60
    assert _event(final)["selectionAnchor"] == "event_target" and _event(final)["requireLineOfSight"] is True


@pytest.mark.parametrize("mutation", ["wrong-opcode", "wrong-name", "foreign-fields", "non-neutral-unused"])
def test_wire_opcode_ownership_is_exact(mutation):
    wire = compile_runtime_program(_doc()); wire.pop("runtimeContract")
    event = _event(wire)
    if mutation == "wrong-opcode": event["actionCode"] = 4
    elif mutation == "wrong-name": event["action"] = "chain_damage_on_event"
    elif mutation == "foreign-fields":
        event.update(action="chain_damage_on_event", actionCode=4)
    else: event["damageMultiplier"] = 0.75
    assert not validate_runtime_wire(wire)["ok"]


def test_explicit_step_count_contributes_to_author_and_retained_wire_graph_budgets():
    doc = _doc(stepCount=12)
    for i in range(2):
        call = deepcopy(_call(doc)); call["id"] = "more_" + str(i)
        doc["runtimeProgram"]["calls"].append(call)
    assert not validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(_doc(stepCount=12)); wire.pop("runtimeContract")
    source = next(row for row in wire["runtimeProgram"]["entities"] if row["events"])
    source["events"] = [dict(_event(wire), id="event_" + str(i)) for i in range(3)]
    assert any(e["code"] == "event_spawn_budget_exceeded" for e in validate_runtime_wire(wire)["errors"])


@pytest.mark.parametrize("failure", ["cycle", "self", "depth", "limits"])
def test_saved_wire_refuses_unbounded_graph_without_author_provenance(failure):
    wire = compile_runtime_program(_doc()); wire.pop("runtimeContract")
    entities = wire["runtimeProgram"]["entities"]
    root = next(row for row in entities if row["id"] == "witness_entity")
    child = next(row for row in entities if row["id"] == "witness_child")
    if failure == "self":
        root["spawn"].update(aim="velocity", offsetPx=0)
        root["events"][0]["entityId"] = root["id"]
    elif failure == "cycle":
        root["spawn"].update(aim="velocity", offsetPx=0)
        child["events"] = [dict(root["events"][0], id="back", entityId=root["id"])]
    elif failure == "limits": wire["runtimeProgram"]["limits"]["maxChildDepth"] = True
    else:
        previous = child
        for i in range(3):
            following = deepcopy(child); following.update(id="next_" + str(i), events=[])
            previous["events"] = [dict(root["events"][0], id="edge_" + str(i), entityId=following["id"])]
            entities.append(following); previous = following
    assert not validate_runtime_wire(wire)["ok"]


def test_receipt_forgery_cannot_change_selection_under_a_valid_author_claim():
    wire = compile_runtime_program(_doc())
    _event(wire)["repeatPolicy"] = "exclude_visited"
    assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


def test_old_wire_and_instant_radial_action_remain_distinct_and_unchanged():
    doc = build_runtime_fixture("returning_potion")
    wire = compile_runtime_program(doc)
    for entity in wire["runtimeProgram"]["entities"]:
        if "overTarget" in entity.get("spawn", {}):
            assert entity["spawn"].pop("overTarget") == {"heightTiles": 0, "delayTicks": 0}
    from captured_projectile_author import historical_returning_potion_program
    historical = historical_returning_potion_program(wire["runtimeProgram"])
    fingerprint = hashlib.sha256(json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert fingerprint == "beccfa0cf7d8d67c54a27b7f28017d83b1c394277409bcbc662a878766877d04"
    assert not any(key in json.dumps(wire["runtimeProgram"]) for key in ("stepCount", "selectionAnchor", "repeatPolicy"))
    # The current exact fresh alias keeps the old radial runtime discriminator.
    old = compile_runtime_program(build_capability_witness("damage_nearest_on_event"))
    events = [e for row in old["runtimeProgram"]["entities"] for e in row["events"]]
    assert events[0]["actionCode"] == EVENT_ACTION_OPCODE["chain_damage_on_event"] == 4
    assert "stepCount" not in events[0]
    assert events[0]["action"] == "chain_damage_on_event"


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_combined_hitbox_ammo_named_utility_provider_and_frozen_leaf_repair(wire_transport, monkeypatch, format_mode):
    """Current-main additions coexist with this feature through real offline callers."""
    from infini_local.pipelines import llm_transport as transport

    doc = _doc()
    binding = doc["runtimeProgram"]["bindings"][0]
    binding.update(stackCost=1, stackConsumeChancePercent=37)
    calls = doc["runtimeProgram"]["calls"]
    emission = _call(doc)
    child_spawn = _child_spawn(doc)
    child_spawn["params"]["velocity"] = {"cone": {'minSpeedBlocksPerSecond': (4) * 60 / 16, 'maxSpeedBlocksPerSecond': (7) * 60 / 16, "halfAngleRadians": 0.2}}
    calls.append({"id": "combined_hit_target_geometry", "fn": "spawn_entity_from_hit_target",
                  "target": emission["target"],
                  "params": {**deepcopy(next(row["params"] for row in
                      build_capability_witness("spawn_entity_from_hit_target")["runtimeProgram"]["calls"]
                      if row["fn"] == "spawn_entity_from_hit_target")), "entity": emission["params"]["entity"]}})
    calls.append({"id": "combined_parent_combat", "fn": "spawn_entity_on_event", "target": emission["target"],
                  "params": {"when": "on_hit", "entity": emission["params"]["entity"], "count": 1,
                             "spreadRadians": 0.0, "damageMultiplier": 0.5, 'delaySeconds': (0) / 60,
                             "damageBasis": "live_parent", "knockbackBasis": "authored_child"}})
    owner = next(row["target"] for row in calls if row["fn"] == "set_projectile_hitbox")
    for fn in ("set_projectile_hitbox_curve", "configure_weapon_ammo", "refresh_generated_effect_group_while_held"):
        for row in build_capability_witness(fn)["runtimeProgram"]["calls"]:
            if row["fn"] not in {fn, "apply_generated_buff_on_use"}:
                continue
            row["id"] = "combined_" + str(len(calls))
            if fn == "set_projectile_hitbox_curve":
                row["target"] = owner
            else:
                row.pop("target", None)
            calls.append(row)
    before = json.dumps(doc, sort_keys=True)
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    responses, requests = wire_transport
    payload = _encode_nullable_fixture(doc, contract.author_item_response_schema()) if format_mode == "json_schema" else doc
    responses.append(payload)
    accepted = author.try_llm_plan({"name": "A"}, {"name": "B"}, "combined-offline")
    assert accepted is not None and len(requests) == 1 and not responses
    request = requests[0]
    assert request["response_format"]["type"] == format_mode
    if format_mode == "json_schema":
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
    assert json.dumps(accepted["runtimeProgram"], sort_keys=True) == json.dumps(doc["runtimeProgram"], sort_keys=True)
    wire = compile_runtime_program(accepted)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=accepted, final_document=wire)["ok"]
    event = next(event for entity in wire["runtimeProgram"]["entities"] for event in entity["events"]
                 if event["id"] == "combined_parent_combat")
    assert event["damageBasis"] == "live_parent" and event["knockbackBasis"] == "authored_child"
    assert _event(wire)["action"] == FN
    sampled_child = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == emission["params"]["entity"])
    assert sampled_child["spawn"]["velocityDistribution"] == {"kind": "cone", "minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7, "halfAngleRadians": 0.2}
    geometry = next(event for entity in wire["runtimeProgram"]["entities"] for event in entity["events"]
                    if event["id"] == "combined_hit_target_geometry")
    assert geometry["action"] == "spawn_entity_on_event" and geometry["actionCode"] == 1
    assert geometry["hitTargetSpawn"]["beforeProbability"] == 0.85
    for source in (None, accepted):
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source,
                                       final_document=wire)["ok"]
    assert wire["runtimeProgram"]["weaponAmmo"] == {"ammoCategory": "arrow", "speedBasis": "authored_spawn"}
    assert wire["runtimeProgram"]["bindings"][0]["usePolicy"]["stackConsumeChancePercent"] == 37
    assert wire["runtimeProgram"]["bindings"][0]["usePolicy"]["stackCost"] == 1
    assert wire["runtimeProgram"]["heldEffectGroupId"] == "witness"
    assert [group["id"] for group in wire["runtimeProgram"]["effectGroups"]] == ["witness"]
    assert next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == owner)["hitboxCurve"]["endScale"] == 0.25

    broken = deepcopy(accepted)
    curve = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "set_projectile_hitbox_curve")
    curve["params"]["endScale"] = 9
    candidate = deepcopy(curve)
    candidate["params"].update(endScale=0.25, startScale=7)
    frozen = deepcopy(next(row for row in calls if row["fn"] == "configure_weapon_ammo"))
    frozen["params"]["ammoCategory"] = "bullet"
    hostile_spawn = deepcopy(child_spawn)
    hostile_spawn["params"]["velocity"]["cone"]['maxSpeedBlocksPerSecond'] = (12) * 60 / 16
    hostile_emission = deepcopy(emission)
    hostile_emission["params"]["selectionAnchor"] = "event_target"
    hostile_geometry = deepcopy(next(row for row in calls if row["id"] == "combined_hit_target_geometry"))
    hostile_geometry["params"]["geometry"]["beforeProbability"] = 0.5
    hostile_combat = deepcopy(next(row for row in calls if row["id"] == "combined_parent_combat"))
    hostile_combat["params"]["damageBasis"] = "authored_child"
    hostile_binding = deepcopy(binding)
    hostile_binding["stackConsumeChancePercent"] = 90
    repaired, dossier, repaired_wire = frozen_gameplay_repair(monkeypatch, broken,
        {"note": "exact curve correction with hostile frozen companions", "realizationReplacement": broken["realization"],
         "callsUpsert": [candidate, frozen, hostile_spawn, hostile_emission, hostile_combat, hostile_geometry],
         "bindingsUpsert": [hostile_binding]}, format_mode,
        {"calls": [{"id": curve["id"], "paths": ["params.endScale"]}]},
        {key: value for key, value in accepted.items() if key != "debug"}, out_of_scope_response=True)
    assert repaired_wire["runtimeProgram"] == wire["runtimeProgram"]
    assert json.dumps(doc, sort_keys=True) == before
