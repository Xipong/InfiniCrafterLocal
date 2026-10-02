"""Canonical Gameplay Repair: diagnostics -> exact scope -> filter -> apply -> compiler."""
import copy
import json

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope, runtime_repair_fragments,
    validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.program_schema import strict_repair_structure_report, strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


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
    ("configure_placeable", "tileId"),
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
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert doc == before


@pytest.mark.parametrize("companion_fn", [None, "apply_vanilla_buff_on_use", "apply_generated_buff_on_use", "move_player_on_use"])
@pytest.mark.parametrize("chosen_heal", ["healLife", "healMana"])
def test_empty_healing_lane_exposes_only_causal_effect_leaves(companion_fn, chosen_heal):
    doc = build_capability_witness("restore_resources_on_use")
    calls = doc["runtimeProgram"]["calls"]
    healing = next(row for row in calls if row["fn"] == "restore_resources_on_use")
    healing["params"].update(healLife=0, healMana=0, usesPotionRules=False)
    if companion_fn:
        companion = copy.deepcopy(next(row for row in build_capability_witness(companion_fn)["runtimeProgram"]["calls"] if row["fn"] == companion_fn))
        companion.update(id="active_companion", target=healing["target"])
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
    "placement-input", "placement-cross-field", "damage-frozen-range",
    "buff-dense", "buff-sparse", "accessory-dark", "accessory-lit",
    "action-missing", "action-unknown", "input-missing",
])
def test_gameplay_exact_leaf_repair(case):
    fn = ("configure_placeable" if case.startswith("placement") else
          "apply_generated_buff_on_use" if case.startswith("buff") else
          "configure_accessory" if case.startswith("accessory") else "configure_item_stats")
    doc = build_runtime_fixture("workbench_blade") if case.startswith(("action", "input")) else build_capability_witness(fn)
    section = "bindings" if case.startswith(("placement", "action", "input")) else "calls"
    rows = doc["runtimeProgram"][section]
    node = (next(row for row in rows if row["usePolicy"]["action"]["kind"] == "place_item")
            if case.startswith("placement") else rows[0] if section == "bindings" else
            next(row for row in rows if row["fn"] == fn))
    good = copy.deepcopy(node)
    candidate = copy.deepcopy(node)
    if case.startswith("placement"):
        node["usePolicy"]["action"]["placementCallId"] = "missing_placement"
        if case == "placement-input":
            candidate["input"] = "alternate_use" if node["input"] == "primary_use" else "primary_use"
        else:
            candidate["usePolicy"].update(stackCost=0, contactDamage=True)
        paths = ["usePolicy.action.placementCallId"]
    elif case.startswith(("action", "input")):
        if case == "input-missing":
            del node["input"]
            paths = ["input"]
        else:
            if case == "action-missing":
                del node["usePolicy"]["action"]["kind"]
            else:
                node["usePolicy"]["action"]["kind"] = "unknown_kind"
            paths = ["usePolicy.action.kind"]
            candidate["input"] = "alternate_use"
            candidate["usePolicy"]["action"]["targetId"] = "nail"
        candidate["usePolicy"].update(contactDamage=not node["usePolicy"]["contactDamage"], stackCost=1)
    elif case == "damage-frozen-range":
        node["params"]["damage"] = -1
        candidate["params"].update(damage=20, manaCost=-1)
        good["params"]["damage"] = 20
        paths = ["params.damage"]
    elif case.startswith("buff"):
        for name, spec in CAPABILITY_REGISTRY[fn].params.items():
            if name not in {"durationTicks", "lightColor"}:
                if case == "buff-sparse" and not spec.required:
                    node["params"].pop(name, None)
                else:
                    node["params"][name] = spec.neutral
        node["params"].update(durationTicks=60, lightColor="blue")
        good = copy.deepcopy(node)
        good["params"]["oreSenseEnabled"] = True
        candidate = copy.deepcopy(node)
        candidate["params"].update(oreSenseEnabled=True, durationTicks=21600, lightColor="red")
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
        assert any(e["code"] == "shape_one_of" and e["path"].endswith(".action.kind") for e in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    permissions = next(row["paths"] for row in scope["fieldPermissions"][section] if row["id"] == node["id"])
    if paths is not None:
        assert scope["fieldPermissions"][section] == [{"id": node["id"], "paths": paths}]
    if case.startswith("buff"):
        assert not {"params.durationTicks", "params.lightColor"}.intersection(permissions)
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
        assert len(audit["ignoredChanges"]) == 2
    if case == "accessory-dark":
        assert any(row["path"].endswith(".lightColor") for row in audit["ignoredChanges"])
    if case.startswith(("action", "input")):
        assert {"contactDamage", "stackCost"} <= {row["path"].rsplit(".", 1)[-1] for row in audit["ignoredChanges"]}


@pytest.mark.parametrize("case", ["type", "null", "unknown_key", "union", "null_row", "boolean_as_integer", "in-scope-range", "valid-control"])
def test_gameplay_patch_admission(case):
    doc = build_capability_witness("configure_item_stats")
    node = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    node["params"]["damage"] = -1
    candidate = copy.deepcopy(node)
    candidate["params"]["damage"] = -2 if case == "in-scope-range" else 20
    if case in {"type", "null", "boolean_as_integer"}:
        candidate["params"]["manaCost"] = {"type": "bad", "null": None, "boolean_as_integer": False}[case]
    elif case == "unknown_key":
        candidate["params"]["unknown"] = None
    elif case == "union":
        candidate["fn"] = "not_registered"
    elif case == "null_row":
        candidate = None
    patch = {"note": "repair", "realizationReplacement": doc["realization"], "callsUpsert": [candidate]}
    structure_ok = case in {"in-scope-range", "valid-control"}
    assert strict_repair_structure_report(patch)["ok"] is structure_ok
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"] is (case == "valid-control"), audit
    if not structure_ok:
        assert not audit["acceptedPaths"]
    if case == "valid-control":
        assert validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]


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
    assert scope["fieldPermissions"]["calls"] == [{"id": node["id"], "paths": sorted("params." + key for key in missing)}]
    assert node["id"] not in scope["identityChanges"]["callFnIds"]
    assert not any(row["callId"] == node["id"] and row["key"] in node["params"] for row in scope["deletable"]["callParamKeys"])
    candidate = copy.deepcopy(original)
    candidate["params"].update(node["params"], pierce=4)
    upserts = [candidate]
    if foreign_fn:
        foreign = next(row for row in build_runtime_fixture("equipment_tool_combat")["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
        foreign.update(id=node["id"], target=node["target"])
        upserts.append(foreign)
    patch = {"note": "complete collision", "callsUpsert": upserts,
             "callParamKeysDelete": [{"callId": node["id"], "key": key} for key in ("tileCollide", "pierce")]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    expected = copy.deepcopy(original)
    expected["params"].update(node["params"])
    assert filtered["callsUpsert"] == [expected] and not filtered["callParamKeysDelete"]
    assert set(filtered["callsUpsert"][0]["params"]) == required
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
    assert validate_runtime_program(doc)["ok"]
    node.update(action=original["usePolicy"]["action"]["kind"], target=original["usePolicy"]["action"]["targetId"])
    del node["usePolicy"]
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"] if e["code"].startswith("shape_")} == {"$.runtimeProgram.bindings[0]" + tail for tail in ("", ".usePolicy", ".action", ".target")}
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["bindings"] == [{"id": node["id"], "paths": ["action", "target", "usePolicy", "usePolicy.action.kind", "usePolicy.action.targetId"]}]
    transaction = {"input": original["input"], "usePolicy": copy.deepcopy(original["usePolicy"])}
    transaction["usePolicy"]["contactDamage"] = False
    assert transaction in next(row["allowed"] for row in scope["bindingAlternatives"] if row["bindingId"] == node["id"])
    candidate = {"id": node["id"], **transaction}
    if attempt == "wrong-input":
        candidate["input"] = "alternate_use"
    elif attempt == "legacy-sibling":
        candidate["action"] = node["action"]
    elif attempt == "wrong-id":
        candidate["id"] = other["id"]
    filtered, audit = filter_repair_patch_scope(doc, {"note": "complete transaction", "bindingsUpsert": [candidate]}, scope)
    assert audit["ok"] is (attempt == "exact"), audit
    if attempt == "exact":
        assert filtered["bindingsUpsert"] == [candidate]
        assert validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]
    else:
        assert filtered["bindingsUpsert"] != [candidate]
        if attempt == "legacy-sibling":
            assert any(row["path"] == "$.bindingsUpsert[0].action" and row["kind"] == "additional_property" for row in audit["errors"])
        else:
            suffix, reason = (".input", "frozen_valid_value") if attempt == "wrong-input" else ("", "independent_valid_node_frozen")
            assert any(row["path"] == "$.bindingsUpsert[0]" + suffix and row["reason"] == reason for row in audit["ignoredChanges"])
            if attempt == "wrong-id":
                assert filtered["bindingsUpsert"] == []


@pytest.mark.parametrize("fn", [fn for fn, cap in CAPABILITY_REGISTRY.items() if cap.provider_variant_schema()["properties"]["params"]["required"]])
def test_registry_discriminator_reports_own_missing_fields(fn):
    variants = {name: cap.provider_variant_schema() for name, cap in CAPABILITY_REGISTRY.items()}
    required = variants[fn]["properties"]["params"]["required"]
    errors = strict_schema_errors({"id": "probe", "fn": fn, "target": "item", "params": {}}, {"oneOf": list(variants.values())})
    assert {e["path"] for e in errors if e["kind"] == "required"} == {"$.params." + key for key in required}
    assert all(not (e["path"] == "$.fn" and e["kind"] == "const") for e in errors)


@pytest.mark.parametrize("case", ["ordered", "reversed", "unknown-fn", "missing-fn", "empty", "nested-exact", "nested-unknown", "nested-missing", "input-missing", "input-unknown", "valid", "multi-match"])
def test_oneof_exact_diagnostic_selection(case):
    failure = {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0}
    if case.startswith("nested") or case.startswith("input"):
        branches = [{"type": "object", "properties": {"input": {"const": name}, "policy": {"type": "object", "properties": {"action": {"type": "object", "properties": {"kind": {"const": action}}, "required": ["kind"]}}}, "value": {"type": "integer"}}, "required": ["input", "policy", "value"]} for name, action in [("use", "launch"), ("use", "place"), ("hold", "launch")]]
        value = {"input": "use", "policy": {"action": {"kind": "place"}}}
        expected = [failure, {"path": "$.value", "kind": "required"}]
        if case == "nested-unknown":
            value["policy"]["action"]["kind"] = "unknown"
            expected = [failure, {"path": "$.policy.action.kind", "kind": "one_of"}]
        elif case == "nested-missing":
            value["policy"]["action"] = {}
            expected.append({"path": "$.policy.action.kind", "kind": "required"})
        elif case.startswith("input"):
            value["policy"]["action"]["kind"] = "launch"
            if case == "input-missing":
                del value["input"]
                expected = [failure, {"path": "$.input", "kind": "required"}, {"path": "$.value", "kind": "required"}]
            else:
                value["input"] = "unknown"
                expected = [failure, {"path": "$.input", "kind": "one_of"}]
    elif case in {"valid", "multi-match"}:
        branch = {"type": "object", "properties": {"fn": {"const": "same"}}, "required": ["fn"]}
        branches = [branch, copy.deepcopy(branch) if case == "multi-match" else {"properties": {"fn": {"const": "other"}}}]
        value = {"fn": "same"}
        expected = [{**failure, "actual": 2}] if case == "multi-match" else []
    else:
        branches = [{"type": "object", "properties": {"fn": {"const": fn}, "value": {"type": "integer"}, **({"other": {"type": "string"}} if fn == "beta" else {})}, "required": ["fn", "value", *(["other"] if fn == "beta" else [])]} for fn in ("alpha", "beta")]
        value = {"fn": "beta"}
        expected = [failure, {"path": "$.value", "kind": "required"}, {"path": "$.other", "kind": "required"}]
        if case == "reversed":
            branches.reverse()
        elif case in {"unknown-fn", "missing-fn", "empty"}:
            value = {"unknown-fn": {"fn": "unknown"}, "missing-fn": {"value": 1}, "empty": {}}[case]
            expected = [failure]
    assert strict_schema_errors(value, {"oneOf": branches}) == expected


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
