"""Native source ordering preserves alias roles, branch edges and uncertainty."""
from collections import Counter
import copy
import json
import re

import pytest

from infini_local.pipelines.context.attack_behavior import ordered_attack_context


def _row(step, expression, guards=None):
    return {"step": step, "block": 10, "expression": expression,
            "requiredPredicates": ["b9"] if guards is None else guards}


def _source():
    shared = _row(3, "Native.Mutate[a0,a1]")
    return {"method": "Native.Source", "symbols": {"Native.Mutate": "Native.Mutate(ref A,ref A)"},
            "dependencies": {
                "d0": _row(0, "@Native.clock"),
                "a0": {"scope": "first alias; writes and reaching value unresolved",
                       "orderedSourceUses": [_row(2, "d0"), shared, copy.deepcopy(shared)]},
                "a1": {"scope": "second alias; writes and reaching value unresolved",
                       "orderedSourceUses": [copy.deepcopy(shared)]}},
            "observations": [dict(_row(4, "Native.Read[a0]"), kind="call")],
            "predicates": [{"step": 1, "id": "b9", "op": "switch", "inputs": ["d0"],
                            "successors": [10, 10, 30, 40]}],
            "unresolved": ["alias memory and branch execution remain unresolved"]}


def _rename(text, names):
    # Independent literal token observer: quoted content is never a reference.
    result, at = [], 0
    while at < len(text):
        if text[at] == '"':
            _, end = json.JSONDecoder().raw_decode(text, at)
            result.append(text[at:end])
            at = end
            continue
        token = re.match(r"[A-Za-z_][A-Za-z0-9_@.#`]*", text[at:])
        if token:
            result.append(names.get(token[0], token[0]))
            at += len(token[0])
        else:
            result.append(text[at])
            at += 1
    return "".join(result)


def _canonical_row(row, names):
    row = copy.deepcopy(row)
    for key in ("expression", "receiver"):
        if isinstance(row.get(key), str):
            row[key] = _rename(row[key], names)
    if "inputs" in row:
        row["inputs"] = [_rename(value, names) for value in row["inputs"]]
    return json.dumps(row, sort_keys=True)


def test_addressed_source_uses_join_ordered_stream_without_losing_duplicate_membership():
    source = _source()
    before = copy.deepcopy(source)
    projected = ordered_attack_context({"program": source})
    program = projected["program"]
    assert source == before
    assert all(key not in program for key in ("observations", "dependencies", "predicates"))
    assert [row["step"] for row in program["operations"]] == [0, 1, 2, 3, 4]
    # Metadata identifies aliases; no fictitious initialized value is attached.
    alias_names = {row["scope"].split()[0]: name for name, row in program["addressedLocals"].items()}
    assert all(set(row) == {"scope"} for row in program["addressedLocals"].values())
    scalar = next(row for row in program["operations"] if "bind" in row)
    names = {scalar["bind"]: "value", alias_names["first"]: "aliasA", alias_names["second"]: "aliasB"}
    old_names = {"d0": "value", "a0": "aliasA", "a1": "aliasB"}
    expected, delivered = Counter(), Counter()
    for name, dependency in source["dependencies"].items():
        for row in dependency.get("orderedSourceUses", []):
            expected[(old_names[name], _canonical_row(row, old_names))] += 1
    for operation in program["operations"]:
        use = copy.deepcopy(operation)
        local_names = use.pop("localUses", [])
        if str(use.get("block")) in program.get("blockGuards", {}):
            use["requiredPredicates"] = program["blockGuards"][str(use["block"])]
        for name in local_names:
            delivered[(names[name], _canonical_row(use, names))] += 1
    assert delivered == expected
    assert sum(delivered.values()) == 4
    assert len(next(row for row in program["operations"] if row["step"] == 3)["localUses"]) == 3
    switch = next(row for row in program["operations"] if row.get("op") == "switch")
    assert switch["successors"] == [10, 10, 30, 40]
    assert switch["inputs"] == [scalar["bind"]]
    assert "fallthrough" in projected["branchTests"]["switch"]
    assert program["unresolved"] == source["unresolved"]
    assert ordered_attack_context(projected) == projected


def test_conflicting_same_block_guards_remain_attached_to_each_source_record():
    source = _source()
    source["observations"][0]["requiredPredicates"] = ["otherBranch", "otherBranch"]
    program = ordered_attack_context({"program": source})["program"]
    assert "10" not in program.get("blockGuards", {})
    assert next(row for row in program["operations"] if row.get("kind") == "call")["requiredPredicates"] == [
        "otherBranch", "otherBranch"]
    assert next(row for row in program["operations"] if "localUses" in row)["requiredPredicates"] == ["b9"]


@pytest.mark.parametrize("mutation", ["future_use", "missing_step", "future_local", "unknown_branch", "empty_switch",
                                     "future_input", "future_argument"])
def test_unknown_source_shapes_keep_their_complete_reference_namespace(mutation):
    source = _source()
    if mutation == "future_use":
        source["dependencies"]["a0"]["orderedSourceUses"][0]["futureRelation"] = "d0"
    elif mutation == "missing_step":
        del source["dependencies"]["a0"]["orderedSourceUses"][0]["step"]
    elif mutation == "future_local":
        source["dependencies"]["a0"]["futureRelation"] = "d0"
    elif mutation == "unknown_branch":
        source["predicates"][0]["op"] = "future.branch"
    elif mutation == "future_input":
        source["predicates"][0]["inputs"] = [{"futureReference": "d0"}]
    elif mutation == "future_argument":
        source["observations"][0]["arguments"] = {"argument": {"futureReference": "d0"}}
    else:
        source["predicates"][0]["successors"] = []
    assert ordered_attack_context({"program": source}) == {"program": source}


@pytest.mark.parametrize("opaque", ["opaque(;7)", "opaque(d0;;7)"])
def test_opaque_expression_is_literal_and_cannot_acquire_a_dangling_renamed_reference(opaque):
    source = _source()
    source["observations"].append(dict(_row(5, opaque), kind="unknown_call"))
    program = ordered_attack_context({"program": source})["program"]
    assert next(row for row in program["operations"] if row.get("kind") == "unknown_call")["expression"] == opaque
    bound = next(row["bind"] for row in program["operations"] if "bind" in row)
    if "d0" in opaque:
        assert bound == "d0"
        assert set(program["addressedLocals"]) == {"a0", "a1"}
    else:
        assert bound != "d0"


def test_distinct_native_names_cannot_become_the_same_scalar_binding():
    program = {"method": "Native.Source", "symbols": {}, "observations": [], "predicates": [],
               "dependencies": {"l1@12": _row(0, "1"), "d0": _row(1, "2")}}
    operations = ordered_attack_context({"program": program})["program"]["operations"]
    assert len({row["bind"] for row in operations}) == 2
    assert [row["expression"] for row in operations] == ["1", "2"]
