"""Canonical Gameplay Repair: diagnostics -> exact scope -> filter -> apply -> compiler."""
import copy
import json

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope, runtime_repair_fragments
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.program_schema import strict_repair_structure_report, strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


from repair_test_helpers import gameplay_repair as _offline_gameplay_repair, assert_delivery, assert_repaired_source


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("fn,leaf,old,new,hostile,frozen_leaf,frozen_value", [
    pytest.param("configure_item_stats", "damage", True, 1, {"manaCost": 10}, "useStyle", "swing", id="true-to-integer-one"),
    pytest.param("configure_item_stats", "damage", False, 0, {"manaCost": 10}, "useStyle", "swing", id="false-to-integer-zero"),
    pytest.param("configure_item_stats", "damage", 1.0, 1, {"manaCost": 10}, "useStyle", "swing", id="float-to-integer"),
    pytest.param("configure_item_use", "autoReuse", 1, True, {"useTurn": False}, "knockback", 3, id="integer-to-boolean"),
])
def test_gameplay_type_only_repair_survives_real_caller(monkeypatch, format_mode, fn, leaf, old, new, hostile, frozen_leaf, frozen_value):
    doc = build_capability_witness("configure_item_use")
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"][leaf] = old
    before = json.dumps(doc, sort_keys=True)
    expected = copy.deepcopy(doc)
    expected_call = next(row for row in expected["runtimeProgram"]["calls"] if row["fn"] == fn)
    expected_call["params"][leaf] = new
    candidate = copy.deepcopy(expected_call)
    candidate["params"].update(hostile)
    frozen = copy.deepcopy(next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] != fn))
    frozen["params"][frozen_leaf] = frozen_value
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "explicit exact JSON-type correction", "realizationReplacement": doc["realization"],
        "callsUpsert": [candidate, frozen]}, format_mode, out_of_scope_response=True)
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and "$.callsUpsert[0].params." + leaf in audit["acceptedPaths"]
    assert any(row["reason"] == "independent_valid_node_frozen" for row in audit["ignoredChanges"])
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + leaf]}]
    assert json.dumps(repaired["debug"]["gameplayRepairPatch"]["callsUpsert"], sort_keys=True) == json.dumps([expected_call], sort_keys=True)
    assert_repaired_source(repaired, expected)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("fn,selector,value", [
    pytest.param("pull_on_event", "when", {"everySeconds": 0.2}, id="periodic"),
    pytest.param("require_use_condition", "condition", {"lifeAtLeast": 100}, id="life-threshold"),
    pytest.param("require_use_condition", "condition", {"manaAtLeast": 100}, id="mana-threshold"),
])
def test_gameplay_conditional_choice_accepts_only_exact_missing_dependency(monkeypatch, fn, selector, value):
    doc = build_capability_witness(fn)
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    if selector == "when":
        call["params"][selector] = "on_use"
    else:
        call["params"] = {selector: "invalid"}
    before = json.dumps(doc, sort_keys=True)
    candidate = copy.deepcopy(call)
    candidate["params"][selector] = value
    expected = copy.deepcopy(doc)
    next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"][selector] = copy.deepcopy(value)
    assert_delivery(expected)
    if selector == "when":
        candidate["params"].update(impulseBlocksPerSecond=15, radiusTiles=60)
    stats = copy.deepcopy(next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats"))
    stats["params"]["damage"] = 1999
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "model-selected complete conditional alternative", "realizationReplacement": doc["realization"],
        "callsUpsert": [candidate, stats]}, "json_object", out_of_scope_response=True)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + selector]}]
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and "$.callsUpsert[0].params." + selector in audit["acceptedPaths"]
    assert audit["ignoredChanges"]
    assert_repaired_source(repaired, expected)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("fn,initial,chosen,hostile,fix_stats,paths,refuse", [
    pytest.param("pull_on_event", {"when": {}}, {"when": {"everySeconds": 0.2}}, {"impulseBlocksPerSecond": 15}, False,
                 ['params.when.everySeconds'], False, id="periodic-already-selected"),
    pytest.param("pull_on_event", {"when": "on_use"}, {"when": "on_expire"}, {"impulseBlocksPerSecond": 15, "delaySeconds": 0.2},
                 False, ["params.when"], False, id="nonconditional-event"),
    pytest.param("require_use_condition", {"condition": "invalid"}, {"condition": "grounded"}, {}, False,
                 ["params.condition"], False, id="nonconditional-mode"),
    pytest.param("require_use_condition", {"condition": {"lifeAtLeast": 50}}, {"condition": {"manaAtLeast": 100}}, {},
                 True, ["params.damage"], False, id="existing-threshold-frozen"),
    pytest.param("require_use_condition", {"condition": "grounded"}, {"condition": {"manaAtLeast": 100}}, {},
                 True, ["params.damage"], False, id="unrelated-selector-frozen"),
    pytest.param("require_use_condition", {"condition": "invalid"}, {"condition": {}}, {}, False,
                 ["params.condition"], True, id="missing-explicit-dependency"),
])
def test_gameplay_conditional_dependency_keeps_frozen_controls(
    monkeypatch, fn, initial, chosen, hostile, fix_stats, paths, refuse,
):
    from infini_local.core.errors import PlannerUnavailable

    doc = build_capability_witness(fn)
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    if fn == "pull_on_event":
        call["params"].update(initial)
    else:
        call["params"] = copy.deepcopy(initial)
    stats = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    if fix_stats:
        stats["params"]["damage"] = True
    before = json.dumps(doc, sort_keys=True)
    expected = copy.deepcopy(doc)
    expected_call = next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == (stats if fix_stats else call)["id"])
    expected_call["params"].update({"damage": 1} if fix_stats else chosen)
    candidate = copy.deepcopy(call)
    candidate["params"].update(chosen, **hostile)
    upserts = [candidate, {**copy.deepcopy(stats), "params": {**stats["params"], "damage": 1}}] if fix_stats else [candidate]
    patch = {"note": "explicit choice; no synthesized missing values", "realizationReplacement": doc["realization"],
             "callsUpsert": [] if refuse else upserts}
    if refuse:
        with pytest.raises(PlannerUnavailable, match="deterministically filtered"):
            _offline_gameplay_repair(monkeypatch, doc, patch, "json_object")
    else:
        repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, patch, "json_object", out_of_scope_response=fix_stats)
        assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": (stats if fix_stats else call)["id"], "paths": paths}]
        assert_repaired_source(repaired, expected)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("owner", ["item-condition", "projectile-trigger"])
def test_gameplay_conditional_missing_permissions_follow_registry_owner(monkeypatch, owner):
    from dataclasses import replace
    import infini_local.core.runtime_authoring.capability_registry as capability_registry
    import infini_local.core.runtime_authoring.repair_scope as repair_scope
    import infini_local.core.runtime_authoring.validator as validator
    import infini_local.core.runtime_authoring.compiler as compiler
    import infini_local.core.runtime_authoring.technical_lowering as technical_lowering
    from infini_local.core.runtime_authoring.capability_registry import ParamSpec

    fn = "require_use_condition" if owner == "item-condition" else "pull_on_event"
    root, old_leaf, new_leaf, literal = (("condition", "lifeAtLeast", "customLife", {"useConditionMode": "life_above"})
                                       if owner == "item-condition" else
                                       ("when", "everySeconds", "customInterval", {"event": "periodic"}))
    doc = build_capability_witness(fn)
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    cap = CAPABILITY_REGISTRY[fn]
    leaf = next(v.properties[old_leaf] for v in cap.params[root].alternatives if old_leaf in v.properties)
    changed = ParamSpec("object", "Mutated exact typed leaf", properties={new_leaf: leaf}, wire_literals=literal)
    registry = {**CAPABILITY_REGISTRY, fn: replace(cap, params={**cap.params, root: changed})}
    for consumer in (capability_registry, repair_scope, validator, compiler, technical_lowering):
        monkeypatch.setattr(consumer, "CAPABILITY_REGISTRY", registry)
    call["params"][root] = {new_leaf: True if owner == "item-condition" else 5 / 60}
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + root + "." + new_leaf]}]
    candidate = copy.deepcopy(call)
    candidate["params"][root] = {new_leaf: 100 if owner == "item-condition" else 100 / 60}
    expected = apply_repair_patch(doc, {"note": "registry-chosen conditional control", "callsUpsert": [candidate]})
    if owner == "projectile-trigger":
        candidate["params"]["impulseBlocksPerSecond"] = 750
    filtered, audit = filter_repair_patch_scope(doc, {
        "note": "consume mutated canonical facts", "realizationReplacement": doc["realization"], "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert_delivery(repaired)


@pytest.mark.parametrize("namespace,position", [(n, p) for n in ("entities", "bindings", "calls") for p in ("head", "tail")])
def test_malformed_row_owns_only_its_original_index(namespace, position):
    doc = build_capability_witness("restore_resources_on_use")
    original = copy.deepcopy(doc)
    rows = doc["runtimeProgram"][namespace]
    index = 0 if position == "head" else len(rows)
    rows.insert(index, None)
    before = copy.deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    index_key = {"entities": "entityIndices", "bindings": "bindingIndices", "calls": "callIndices"}[namespace]
    assert scope["deletable"][index_key] == [index], "diagnostics must keep original array coordinates"
    assert all(not paths for paths in scope["fieldPermissions"].values()), "a malformed row cannot unfreeze its valid sibling"
    assert runtime_repair_fragments(doc, scope)["brokenByIndex"][namespace] == [{"index": index, "value": None}]

    patch = {"note": "no node operations", "realizationReplacement": doc["realization"]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert not audit["ok"], "a no-op must leave the original malformed row RED"
    assert apply_repair_patch(doc, filtered) == doc, "omission cannot silently sanitize malformed rows"
    assert not validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]

    candidate = copy.deepcopy(original["runtimeProgram"][namespace][0])
    if namespace == "entities":
        candidate["kind"] = "field"
    elif namespace == "bindings":
        candidate["input"] = "alternate_use"
    else:
        candidate["params"]["damage"] = 100
    patch.update({namespace + "Upsert": [candidate], index_key + "Delete": [index]})
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    assert filtered[namespace + "Upsert"] == []
    assert filtered[index_key + "Delete"] == [index]
    repaired = apply_repair_patch(doc, filtered)
    assert repaired == original
    assert validate_runtime_program(repaired)["ok"]
    compiled = compile_runtime_program(repaired)
    assert validate_runtime_wire(compiled)["ok"]
    assert doc == before


@pytest.mark.parametrize("malformed", [None, False, "broken", {}, {"params": {"damage": 999}}])
def test_sparse_patch_preserves_every_original_occurrence(malformed):
    doc = build_capability_witness("configure_item_stats")
    rows = doc["runtimeProgram"]["calls"]
    rows.insert(0, copy.deepcopy(malformed))
    rows.append(copy.deepcopy(malformed))
    before = copy.deepcopy(doc)
    assert apply_repair_patch(doc, {"note": "no node edits"}) == before
    assert doc == before


@pytest.mark.parametrize("namespace", ["entities", "bindings", "calls"])
def test_duplicate_occurrences_require_exact_index_deletion(namespace):
    doc = build_capability_witness("restore_resources_on_use")
    original = copy.deepcopy(doc)
    rows = doc["runtimeProgram"][namespace]
    duplicate = copy.deepcopy(rows[0])
    if namespace == "entities":
        duplicate["kind"] = "field"
    elif namespace == "bindings":
        duplicate["input"] = "alternate_use"
    else:
        duplicate["params"]["damage"] = 100
    duplicate_index = len(rows)
    rows.append(duplicate)
    before = copy.deepcopy(doc)
    assert apply_repair_patch(doc, {"note": "no edits"}) == doc, "duplicates must retain their distinct original values"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    shared_id = duplicate["id"]
    scope_key = {"entities": "entityIds", "bindings": "bindingIds", "calls": "callIds"}[namespace]
    index_key = {"entities": "entityIndices", "bindings": "bindingIndices", "calls": "callIndices"}[namespace]
    assert not any(row["id"] == shared_id for row in scope["fieldPermissions"][namespace]), "ID-only permissions cannot identify one duplicate occurrence"
    assert shared_id not in scope["deletable"][scope_key]
    assert duplicate_index in scope["deletable"][index_key]
    patch = {"note": "drop only the duplicate", "realizationReplacement": doc["realization"],
             index_key + "Delete": [duplicate_index], scope_key + "Delete": [shared_id], namespace + "Upsert": [duplicate]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    assert filtered[namespace + "Upsert"] == [] and filtered[scope_key + "Delete"] == []
    assert apply_repair_patch(doc, filtered) == original
    assert validate_runtime_wire(compile_runtime_program(original))["ok"]
    assert doc == before


@pytest.mark.parametrize("fn,param", [
    ("apply_generated_buff_on_use", "miningSpeedMultiplier"),
    ("apply_generated_buff_on_use", "manaRegenBonusPoints"),
    ("configure_tile_placement", "tileId"),
    ("configure_accessory", "lightStrength"),
])
@pytest.mark.parametrize("value", [10**400, 65536], ids=["huge-json-integer", "bounded-range-error"])
def test_large_json_numbers_keep_exact_shape_repair(fn, param, value):
    good = build_capability_witness(fn)
    if fn == "configure_accessory":
        next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == fn)["params"].update(lightStrength=0, lightColor="white")
    doc = copy.deepcopy(good)
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    node["params"][param] = value
    # Exercise valid JSON numeric transport, not NaN/Infinity or changed limits.
    doc = json.loads(json.dumps(doc, allow_nan=False))
    before = copy.deepcopy(doc)
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    index = doc["runtimeProgram"]["calls"].index(node)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(row["code"].startswith("shape_") and row["path"] == f"$.runtimeProgram.calls[{index}].params.{param}" for row in report["errors"]), report
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": node["id"], "paths": ["params." + param]}]
    candidate = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == fn))
    filtered, audit = filter_repair_patch_scope(doc, {"note": "restore the exact invalid number", "realizationReplacement": doc["realization"], "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert repaired == good
    assert_delivery(repaired)
    assert doc == before


@pytest.mark.parametrize("companion_fn,chosen_heal", [
    pytest.param(None, "healLife", id="empty-life-correction"),
    pytest.param(None, "healMana", id="empty-mana-correction"),
    pytest.param("apply_vanilla_buff_on_use", "healLife", id="neutral-with-vanilla-buff"),
    pytest.param("apply_generated_buff_on_use", "healLife", id="neutral-with-generated-buff"),
    pytest.param("move_player_on_use", "healLife", id="neutral-with-mobility"),
])
def test_empty_healing_lane_exposes_only_causal_effect_leaves(companion_fn, chosen_heal):
    doc = build_capability_witness("restore_resources_on_use")
    calls = doc["runtimeProgram"]["calls"]
    healing = next(row for row in calls if row["fn"] == "restore_resources_on_use")
    healing["params"].update(healLife=0, healMana=0, usesPotionRules=False)
    if companion_fn:
        companion = copy.deepcopy(next(row for row in build_capability_witness(companion_fn)["runtimeProgram"]["calls"] if row["fn"] == companion_fn))
        companion.update(id="active_companion")
        calls.append(companion)
    before = copy.deepcopy(doc)
    report = validate_runtime_program(doc)
    if companion_fn:
        assert report["ok"], "intentional neutral healing remains valid with another active use effect"
        assert validate_runtime_wire(compile_runtime_program(doc))["ok"]
        return
    assert not report["ok"], "empty effective-use composition must fail while authored paths still exist"
    assert report["errors"] == [{
        "path": f"$.runtimeProgram.calls[{calls.index(healing)}].params", "code": "empty_component",
        "message": CAPABILITY_REGISTRY[healing["fn"]].requirements[-1].message,
        "allowed": ["healLife > 0", "healMana > 0"], "relatedIds": [],
    }]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert not scope["nonRepairableErrors"]
    assert scope["fieldPermissions"]["calls"] == [{"id": healing["id"], "paths": ["params.healLife", "params.healMana"]}]
    assert not scope["fieldPermissions"]["bindings"]
    candidate = copy.deepcopy(healing)
    candidate["params"].update({chosen_heal: 20, "usesPotionRules": True})
    stats = copy.deepcopy(next(row for row in calls if row["fn"] == "configure_item_stats"))
    stats["params"]["damage"] = 100
    filtered, audit = filter_repair_patch_scope(doc, {"note": "choose one explicit healing effect", "realizationReplacement": doc["realization"], "callsUpsert": [candidate, stats]}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    expected = copy.deepcopy(doc)
    expected["runtimeProgram"]["calls"][calls.index(healing)]["params"][chosen_heal] = 20
    repaired = apply_repair_patch(doc, filtered)
    assert repaired == expected
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert doc == before


@pytest.mark.parametrize("case", [
    "placement-cross-field", "damage-frozen-range",
    "buff-dense", "buff-sparse", "accessory-dark", "accessory-lit",
    "action-missing", "action-unknown", "input-missing",
])
def test_gameplay_exact_leaf_repair(case):
    fn = ("configure_tile_placement" if case.startswith("placement") else
          "apply_generated_buff_on_use" if case.startswith("buff") else
          "configure_accessory" if case.startswith("accessory") else "configure_item_stats")
    doc = build_runtime_fixture("workbench_blade") if case.startswith(("action", "input")) else build_capability_witness(fn)
    section = "bindings" if case.startswith(("placement", "action", "input")) else "calls"
    rows = doc["runtimeProgram"][section]
    node = (next(row for row in rows if row["action"]["kind"] == "place_item")
            if case.startswith("placement") else rows[0] if section == "bindings" else
            next(row for row in rows if row["fn"] == fn))
    good = copy.deepcopy(node)
    candidate = copy.deepcopy(node)
    if case.startswith("placement"):
        node["action"]["placementCallId"] = "missing_placement"
        candidate["input"] = "alternate_use" if node["input"] == "primary_use" else "primary_use"
        paths = ["action.placementCallId"]
    elif case.startswith(("action", "input")):
        if case == "input-missing":
            del node["input"]
            paths = ["input"]
        else:
            if case == "action-missing":
                del node["action"]["kind"]
            else:
                node["action"]["kind"] = "unknown_kind"
            paths = ["action.kind"]
            candidate["input"] = "alternate_use"
            candidate["action"]["targetId"] = "nail"
        candidate .update(contactDamage=not node["contactDamage"], stackCost=1)
    elif case == "damage-frozen-range":
        node["params"]["damage"] = -1
        candidate["params"].update(damage=20, manaCost=-1)
        good["params"]["damage"] = 20
        paths = ["params.damage"]
    elif case.startswith("buff"):
        for name, spec in CAPABILITY_REGISTRY[fn].params.items():
            if name not in {"durationTicks", "lightColor"} and spec.neutral is not None:
                if case == "buff-sparse" and not spec.required:
                    node["params"].pop(name, None)
                else:
                    node["params"][name] = spec.neutral
        node["params"].update(durationSeconds=(60) / 60, lightColor="blue")
        good = copy.deepcopy(node)
        good["params"]["oreSenseEnabled"] = True
        candidate = copy.deepcopy(node)
        candidate["params"].update(oreSenseEnabled=True, durationSeconds=(21600) / 60, lightColor="red")
        paths = None
    else:
        node["params"] = {}
        strength = int(case == "accessory-lit")
        candidate["params"] = {"defensePoints": 2, "lightStrength": strength, "lightColor": "red"}
        good["params"] = {"defensePoints": 2, "lightStrength": strength, **({"lightColor": "red"} if strength else {})}
        paths = None
    before = json.dumps(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"], report
    if case == "action-unknown":
        assert any(e["code"] in {"shape_one_of", "shape_const"} and e["path"].endswith(".action.kind") for e in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    permissions = next(row["paths"] for row in scope["fieldPermissions"][section] if row["id"] == node["id"])
    if paths is not None:
        assert scope["fieldPermissions"][section] == [{"id": node["id"], "paths": paths}]
    if case.startswith("buff"):
        assert not {'params.durationSeconds', "params.lightColor"}.intersection(permissions)
    patch = {"note": "repair diagnosed leaves", "realizationReplacement": copy.deepcopy(doc["realization"]), section + "Upsert": [candidate]}
    patch_before = json.dumps(patch)
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    assert json.dumps(filtered[section + "Upsert"], sort_keys=True) == json.dumps([good], sort_keys=True), "filtered_exact_leaf_and_frozen_siblings"
    merged = apply_repair_patch(doc, filtered)
    expected = copy.deepcopy(doc)
    expected["runtimeProgram"][section][rows.index(node)] = good
    assert json.dumps(merged, sort_keys=True) == json.dumps(expected, sort_keys=True), "exact_leaf_and_frozen_siblings"
    assert validate_runtime_program(merged)["ok"], validate_runtime_program(merged)
    assert compile_runtime_program(merged)["runtimeProgram"]["bindings" if section == "bindings" else "entities"]
    assert (json.dumps(doc), json.dumps(patch)) == (before, patch_before)
    if case != "accessory-lit":
        assert audit["ignoredChanges"]
    if case == "placement-cross-field":
        assert audit["ignoredChanges"]
    if case == "accessory-dark":
        assert any(row["path"].endswith(".lightColor") for row in audit["ignoredChanges"])
    if case.startswith(("action", "input")):
        assert {"contactDamage", "stackCost"} <= {row["path"].rsplit(".", 1)[-1] for row in audit["ignoredChanges"]}


@pytest.mark.parametrize("edits,damage,structure_ok,accepted", [
    pytest.param({"params.manaCost": "bad"}, 20, False, False, id="type"),
    pytest.param({"params.manaCost": None}, 20, False, False, id="null"),
    pytest.param({"params.unknown": None}, 20, False, False, id="unknown-key"),
    pytest.param({"fn": "not_registered"}, 20, False, False, id="union"),
    pytest.param(None, 20, False, False, id="null-row"),
    pytest.param({"params.manaCost": False}, 20, False, False, id="boolean-as-integer"),
    pytest.param({}, -2, True, False, id="in-scope-range"),
    pytest.param({}, 20, True, True, id="valid-control"),
])
def test_gameplay_patch_admission(edits, damage, structure_ok, accepted):
    from repair_test_helpers import edit_fields

    doc = build_capability_witness("configure_item_stats")
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    node["params"]["damage"] = -1
    candidate = copy.deepcopy(node) if edits is not None else None
    if candidate is not None:
        edit_fields(candidate, {"params.damage": damage, **edits})
    patch = {"note": "repair", "realizationReplacement": doc["realization"], "callsUpsert": [candidate]}
    assert strict_repair_structure_report(patch)["ok"] is structure_ok
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"] is accepted, audit
    if not structure_ok:
        assert not audit["acceptedPaths"]
    if accepted:
        assert_delivery(apply_repair_patch(doc, filtered))


def test_gameplay_inert_call_deletion():
    doc = build_capability_witness("configure_accessory")
    armor = copy.deepcopy(next(row for row in build_capability_witness("configure_armor")["runtimeProgram"]["calls"] if row["fn"] == "configure_armor"))
    armor["id"] = "remaining_armor"
    doc["runtimeProgram"]["calls"].append(armor)
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
    node["params"] = {}
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert node["id"] in scope["deletable"]["callIds"]
    filtered, audit = filter_repair_patch_scope(doc, {"note": "remove inert call", "realizationReplacement": doc["realization"], "callIdsDelete": [node["id"]]}, scope)
    assert audit["ok"] and filtered["callIdsDelete"] == [node["id"]]
    repaired = apply_repair_patch(doc, filtered)
    assert repaired["runtimeProgram"]["calls"] == [row for row in doc["runtimeProgram"]["calls"] if row is not node]
    assert validate_runtime_program(repaired)["ok"]
    assert compile_runtime_program(repaired)


@pytest.mark.parametrize("foreign_fn", [False, True], ids=["missing-fields", "foreign-fn-frozen"])
def test_collision_missing_parameters_keep_authored_branch(foreign_fn):
    doc = build_runtime_fixture("workbench_blade")
    calls = doc["runtimeProgram"]["calls"]
    index = next(i for i, row in enumerate(calls) if row["id"] == "nail_collision")
    node = calls[index]
    original = copy.deepcopy(node)
    node["params"] = {"tileCollide": True, "pierce": -1, "ignoreWater": True}
    required = set(CAPABILITY_REGISTRY[node["fn"]].provider_variant_schema()["properties"]["params"]["required"])
    missing = required - node["params"].keys()
    assert missing
    base = f"$.runtimeProgram.calls[{index}]"
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"] if e["code"].startswith("shape_") and e["path"].startswith(base)} == {base, *(f"{base}.params.{key}" for key in missing)}
    assert all(e["path"] != base + ".fn" for e in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": node["id"], "paths": sorted("params." + key for key in missing | {"bounceCount"})}]
    assert node["id"] not in scope["identityChanges"]["callFnIds"]
    assert not any(row["callId"] == node["id"] and row["key"] in node["params"] for row in scope["deletable"]["callParamKeys"])
    candidate = copy.deepcopy(original)
    candidate["params"].update(node["params"], pierce=4)
    upserts = [candidate]
    if foreign_fn:
        foreign = next(row for row in build_runtime_fixture("equipment_tool_combat")["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
        foreign.update(id=node["id"])
        upserts.append(foreign)
    patch = {"note": "complete collision", "callsUpsert": upserts,
             "callParamKeysDelete": [{"callId": node["id"], "key": key} for key in ("tileCollide", "pierce")]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    expected = copy.deepcopy(original)
    expected["params"].update(node["params"])
    assert filtered["callsUpsert"] == [expected] and not filtered["callParamKeysDelete"]
    assert set(filtered["callsUpsert"][0]["params"]) == required | {"bounceCount"}
    if foreign_fn:
        assert any(row["path"].endswith(".fn") for row in audit["ignoredChanges"])
    repaired = apply_repair_patch(doc, filtered)
    assert repaired["runtimeProgram"]["calls"][index] == expected
    assert validate_runtime_program(repaired)["ok"]
    assert compile_runtime_program(repaired)["runtimeProgram"]["entities"]


@pytest.mark.parametrize("attempt", ["exact", "wrong-input", "legacy-sibling", "wrong-id"])
def test_binding_atomic_transaction_requires_exact_identity(attempt):
    doc = build_runtime_fixture("workbench_blade")
    node = doc["runtimeProgram"]["bindings"][0]
    original = copy.deepcopy(node)
    other = {**copy.deepcopy(node), "id": "other_binding", "input": "alternate_use"}
    doc["runtimeProgram"]["bindings"].append(other)
    node["action"] = "malformed"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    candidate = copy.deepcopy(original)
    if attempt == "wrong-input":
        candidate["input"] = "alternate_use"
    elif attempt == "legacy-sibling":
        candidate["usePolicy"] = {"action": copy.deepcopy(original["action"])}
    elif attempt == "wrong-id":
        candidate["id"] = other["id"]
    filtered, audit = filter_repair_patch_scope(doc, {"note": "exact action", "bindingsUpsert": [candidate]}, scope)
    if attempt == "exact":
        assert audit["ok"] and filtered["bindingsUpsert"] == [original]
        assert validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]
    elif attempt == "wrong-input":
        assert audit["ok"] and filtered["bindingsUpsert"] == [original]
        assert any(row["reason"] == "frozen_valid_value" for row in audit["ignoredChanges"])
    else:
        assert not audit["ok"]
        assert filtered["bindingsUpsert"] != [candidate]


@pytest.mark.parametrize("fn", [fn for fn, cap in CAPABILITY_REGISTRY.items() if cap.provider_variant_schema()["properties"].get("params", {}).get("required", [])])
def test_registry_discriminator_reports_own_missing_fields(fn):
    variants = {name: cap.provider_variant_schema() for name, cap in CAPABILITY_REGISTRY.items()}
    required = variants[fn]["properties"]["params"]["required"]
    errors = strict_schema_errors({"id": "probe", "fn": fn, "target": "item", "params": {}}, {"oneOf": list(variants.values())})
    assert {e["path"] for e in errors if e["kind"] == "required"} == {"$.params." + key for key in required}
    assert all(not (e["path"] == "$.fn" and e["kind"] == "const") for e in errors)


UNION_FAILURE = {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0}
FUNCTION_BRANCHES = [
    {"type": "object", "properties": {"fn": {"const": "alpha"}, "value": {"type": "integer"}}, "required": ["fn", "value"]},
    {"type": "object", "properties": {"fn": {"const": "beta"}, "value": {"type": "integer"}, "other": {"type": "string"}},
     "required": ["fn", "value", "other"]},
]
NESTED_BRANCHES = [
    {"type": "object", "properties": {
        "input": {"const": name}, "policy": {"type": "object", "properties": {"action": {
            "type": "object", "properties": {"kind": {"const": action}}, "required": ["kind"]}}},
        "value": {"type": "integer"}}, "required": ["input", "policy", "value"]}
    for name, action in [("use", "launch"), ("use", "place"), ("hold", "launch")]
]
SAME_BRANCH = {"type": "object", "properties": {"fn": {"const": "same"}}, "required": ["fn"]}


@pytest.mark.parametrize("branches,value,diagnostics", [
    pytest.param(FUNCTION_BRANCHES, {"fn": "beta"}, [("$.value", "required"), ("$.other", "required")], id="ordered"),
    pytest.param(FUNCTION_BRANCHES[::-1], {"fn": "beta"}, [("$.value", "required"), ("$.other", "required")], id="reversed"),
    pytest.param(FUNCTION_BRANCHES, {"fn": "unknown"}, [("$.value", "required")], id="unknown-fn"),
    pytest.param(FUNCTION_BRANCHES, {"value": 1}, [("$.fn", "required")], id="missing-fn"),
    pytest.param(FUNCTION_BRANCHES, {}, [("$.fn", "required"), ("$.value", "required")], id="empty"),
    pytest.param(NESTED_BRANCHES, {"input": "use", "policy": {"action": {"kind": "place"}}},
                 [("$.value", "required")], id="nested-exact"),
    pytest.param(NESTED_BRANCHES, {"input": "use", "policy": {"action": {"kind": "unknown"}}},
                 [("$.policy.action.kind", "one_of"), ("$.value", "required")], id="nested-unknown"),
    pytest.param(NESTED_BRANCHES, {"input": "use", "policy": {"action": {}}},
                 [("$.value", "required"), ("$.policy.action.kind", "required")], id="nested-missing"),
    pytest.param(NESTED_BRANCHES, {"policy": {"action": {"kind": "launch"}}},
                 [("$.input", "required"), ("$.value", "required")], id="input-missing"),
    pytest.param(NESTED_BRANCHES, {"input": "unknown", "policy": {"action": {"kind": "launch"}}},
                 [("$.input", "one_of"), ("$.value", "required")], id="input-unknown"),
    pytest.param([SAME_BRANCH, {"properties": {"fn": {"const": "other"}}}], {"fn": "same"}, None, id="valid"),
    pytest.param([SAME_BRANCH, SAME_BRANCH], {"fn": "same"}, 2, id="multi-match"),
])
def test_oneof_exact_diagnostic_selection(branches, value, diagnostics):
    expected = ([] if diagnostics is None else [{**UNION_FAILURE, "actual": diagnostics}]
                if isinstance(diagnostics, int) else [UNION_FAILURE, *({"path": path, "kind": kind} for path, kind in diagnostics)])
    assert strict_schema_errors(value, {"oneOf": branches}) == expected


@pytest.mark.parametrize("fn", ["configure_item_stats", "configure_item_use"])
def test_explicit_item_target_is_accepted_and_preserved_by_real_repair(monkeypatch, fn):
    doc = build_capability_witness(fn)
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)
    node["target"] = next(row["id"] for row in doc["runtimeProgram"]["entities"] if row["kind"] == "item_body")
    assert validate_runtime_program(doc)["ok"], "A correct redundant target must not require Format Repair"
    expected = copy.deepcopy(doc)
    candidate = copy.deepcopy(node)
    leaf = "damage" if fn == "configure_item_stats" else "useStyle"
    node["params"][leaf] = -1 if leaf == "damage" else "not_a_style"
    before = copy.deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": node["id"], "paths": ["params." + leaf]}]
    incoming = {"note": "repair the actual invalid parameter", "realizationReplacement": doc["realization"],
                "callsUpsert": [candidate]}
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, incoming, "json_object")
    assert dossier["repairScope"] == scope
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ok"]
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert doc == before


@pytest.mark.parametrize("nested", [False, True], ids=["call-literal-key", "param-literal-key"])
def test_gameplay_literal_member_deletion_is_exact(nested):
    doc = build_capability_witness("configure_item_stats")
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    candidate = copy.deepcopy(node)
    candidate["params"]["damage"] += 1
    key = "damage.fake" if nested else "params.damage"
    (node["params"] if nested else node)[key] = "foreign"
    before = copy.deepcopy(doc)
    relative = ("params" if nested else "") + "[" + json.dumps(key) + "]"
    report = validate_runtime_program(doc)
    assert not report["ok"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": node["id"], "paths": [relative]}]
    assert scope["deletable"]["callParamKeys" if nested else "callPropertyKeys"] == [{"callId": node["id"], "key": key}]
    filtered, audit = filter_repair_patch_scope(doc, {"note": "remove literal member", "callsUpsert": [candidate], "callParamKeysDelete" if nested else "callPropertyKeysDelete": [{"callId": node["id"], "key": key}]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    expected = copy.deepcopy(doc)
    target = next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == node["id"])
    (target["params"] if nested else target).pop(key)
    assert repaired == expected, "literal_member_must_not_alias_nested_permission"
    assert validate_runtime_program(repaired)["ok"] and compile_runtime_program(repaired)
    assert doc == before


# Both input branches and both sparse/hostile responses cross each transport;
# the full product adds no independent permission or parser behavior.
@pytest.mark.parametrize("format_mode,input_name,explicit_frozen_literals", [
    pytest.param("json_object", "equipped", False, id="object-equipped-sparse"),
    pytest.param("json_schema", "equipped", True, id="schema-equipped-frozen"),
    pytest.param("json_schema", "hold", False, id="schema-hold-sparse"),
    pytest.param("json_object", "hold", True, id="object-hold-frozen"),
])
def test_sparse_binding_missing_input_survives_real_repair(
    monkeypatch, format_mode, input_name, explicit_frozen_literals,
):
    from repair_test_helpers import binding_case, explicit_binding

    doc, binding = binding_case(input_name)
    assert validate_runtime_program(doc)["ok"]
    expected = copy.deepcopy(doc)
    candidate = copy.deepcopy(binding)
    if explicit_frozen_literals:
        candidate = explicit_binding(doc, candidate)
    binding.pop("input")
    before = copy.deepcopy(doc)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "restore only the model-selected missing input",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [candidate],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["fieldPermissions"]["bindings"] == [{"id": binding["id"], "paths": ["input"]}]
    assert scope["identityChanges"]["bindingInputIds"] == [binding["id"]]
    assert scope["identityChanges"]["bindingActionIds"] == []
    assert scope["identityChanges"]["bindingTargetIds"] == []
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and "$.bindingsUpsert[0].input" in audit["acceptedPaths"]
    assert {path for path in audit["acceptedPaths"] if path.startswith("$.bindingsUpsert")} == {
        "$.bindingsUpsert[0].input",
    }
    if explicit_frozen_literals:
        assert audit["ignoredChanges"]
    repaired.pop("debug")
    assert repaired == expected
    assert doc == before
    assert_delivery(repaired)


def test_missing_binding_input_noop_never_infers_equipment_input(monkeypatch):
    from infini_local.core.errors import PlannerUnavailable

    doc = build_capability_witness("configure_accessory")
    doc["runtimeProgram"]["bindings"][0].pop("input")
    before = copy.deepcopy(doc)
    with pytest.raises(PlannerUnavailable):
        _offline_gameplay_repair(monkeypatch, doc, {
            "note": "no model-selected input", "realizationReplacement": doc["realization"],
        }, "json_object")
    assert doc == before
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


def test_missing_binding_input_and_unknown_action_have_independent_exact_scope(monkeypatch):
    doc = build_capability_witness("configure_accessory")
    binding = doc["runtimeProgram"]["bindings"][0]
    binding["action"] = {"kind": "equip_passive", "targetId": "item"}
    expected = copy.deepcopy(doc)
    candidate = copy.deepcopy(binding)
    binding.pop("input")
    binding["action"]["kind"] = "unknown"
    before = copy.deepcopy(doc)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "model explicitly supplies both missing input and invalid action",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [candidate],
    }, "json_object")
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [
        {"id": binding["id"], "paths": ["action.kind", "input"]},
    ]
    assert dossier["repairScope"]["identityChanges"]["bindingTargetIds"] == []
    repaired.pop("debug")
    assert repaired == expected
    assert doc == before
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
