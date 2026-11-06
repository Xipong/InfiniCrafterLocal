import copy

import pytest

from infini_local.pipelines.context.mechanics_expression import MechanicsRenderer


def const(value):
    return {"kind": "constant", "value": value}


def test_shared_card_namespace_preserves_distinct_store_values_and_multiplicity():
    renderer = MechanicsRenderer()
    first = {"kind": "local_definition", "local": 3, "scope": "value_at_store",
             "sourceStoreIlOffset": 10, "value": const(5)}
    second = {**first, "sourceStoreIlOffset": 20, "value": const(7)}
    source = {"shot": [first, first], "root": second}
    before = copy.deepcopy(source)
    result = renderer.render(source)
    assert result == {"shot": ["snapshot1", "snapshot1"], "root": "snapshot2"}
    metadata = renderer.finish()
    assert metadata["snapshots"] == {
        "snapshot1": {"local": 3, "scope": "value_at_store", "value": "5"},
        "snapshot2": {"local": 3, "scope": "value_at_store", "value": "7"},
    }
    metadata["snapshots"].clear()
    assert len(renderer.finish()["snapshots"]) == 2
    assert source == before


def test_equal_values_in_distinct_stores_are_not_merged():
    renderer = MechanicsRenderer()
    store = {"kind": "local_definition", "local": 0, "scope": "value_at_store", "value": const(5)}
    assert renderer.render({**store, "sourceStoreIlOffset": 1}) != renderer.render({**store, "sourceStoreIlOffset": 2})


@pytest.mark.parametrize("opcode", ["ble.un", "bne.un", "bgt", "beq"])
def test_branch_opcode_and_taken_direction_preserved_without_guessed_comparison(opcode):
    renderer = MechanicsRenderer()
    branch = {"kind": "branch", "opcode": opcode, "left": const(1), "right": const(2), "taken": False}
    assert renderer.render(branch) == f"not({opcode}(1, 2))"
    assert renderer.render({**branch, "taken": True}) == f"{opcode}(1, 2)"


def test_boolean_branch_operands_are_expressions_not_uninterpreted_ast():
    renderer = MechanicsRenderer()
    assert renderer.render({"kind": "branch", "opcode": "brfalse", "taken": True,
                            "operands": [{"kind": "argument", "index": 2}]}) == "brfalse(arg2)"


@pytest.mark.parametrize("opcode", ["div", "div.un", "shr.un", "mul.ovf.un"])
def test_arithmetic_retains_native_opcode(opcode):
    assert MechanicsRenderer().render({"kind": "binary", "operator": opcode,
                                       "left": const(-3), "right": const(2)}) == f"{opcode}(-3, 2)"


@pytest.mark.parametrize("value", [
    {"kind": "constant", "value": 3, "futureUnits": "ticks"},
    {"kind": "binary", "operator": "future", "left": const(1), "right": const(2)},
    {"kind": "binary", "operator": [], "left": const(1), "right": const(2)},
    {"kind": "branch", "opcode": "ble.un", "left": const(1), "right": const(2), "taken": 0},
    {"kind": "argument", "index": True},
    {"kind": "unknown", "reason": "missing_helper", "local": 4, "future": {"effect": 8}},
    {"kind": "new_expression", "value": const(9), "sourceIlOffset": 123},
    {"kind": "call", "member": "Thing", "arguments": [], "evaluation": "executed"},
])
def test_unknown_or_malformed_expression_is_literal_and_not_silently_projected(value):
    renderer = MechanicsRenderer()
    assert renderer.render(value) == value
    if value.get("kind") == "unknown":
        assert renderer.finish()["unknowns"] == ["missing_helper"]


def test_source_alternatives_keep_conditions_order_duplicates_and_store_definitions():
    renderer = MechanicsRenderer()
    row = {"whenSourceCondition": {"kind": "argument", "argument": 1}, "value": const(7)}
    source = {"kind": "source_alternatives", "local": 2,
              "scope": "last_local_definition_on_source_path_to_read; predicates_not_evaluated",
              "alternatives": [row, row]}
    assert renderer.render(source) == "local2 path_value{when arg1: 7; when arg1: 7}"
    source["alternatives"][0] = {**row, "futureGuard": False}
    assert renderer.render(source) == source


def test_members_and_string_literals_remain_unambiguous():
    renderer = MechanicsRenderer()
    assert renderer.render(const("snapshot1")) == '"snapshot1"'
    assert renderer.render({"kind": "field", "member": "Namespace.One.damage", "receiver": {"kind": "argument", "index": 0}}) == "arg0.[Namespace.One.damage]"
    call = {"kind": "call", "member": "Terraria.Hooks.CheckMana", "arguments": [const(10)],
            "evaluation": "unresolved_helper_or_hook_output", "sourceIlOffset": 5}
    assert renderer.render(call) == "unexecuted Terraria.Hooks.CheckMana(10)"


def test_only_explicit_receipts_removed_and_unknown_tree_keeps_all_information():
    renderer = MechanicsRenderer()
    value = {"sourceIlOffset": 5, "scope": "per_hit", "signature": "meaningful",
             "condition": {"kind": "unknown", "reason": "unresolved", "sourceIlOffset": 9}}
    assert renderer.render(value) == {"scope": "per_hit", "signature": "meaningful", "condition": value["condition"]}
    assert renderer.finish()["unknowns"] == ["unresolved"]


def coverage():
    row = {"status": "partial_source_expression", "unresolved": [
        {"path": "inputs.velocity", "reason": "helper_output_not_evaluated", "member": "Helper", "sourceIlOffset": 8},
        {"path": "inputs.velocity.value", "reason": "helper_output_not_evaluated", "member": "OtherHelper", "sourceIlOffset": 9},
    ]}
    return {"scope": "source_call_arguments_only; not_final_values_or_guaranteed_execution",
            "localValues": "guarded_reaching_definitions; branch_entry_values_unknown_not_item_defaults",
            "controlFlow": "normal_flow_from_item_branch_entry; external_gates_hooks_and_player_state_not_evaluated",
            "calls": "symbolic_source_only; helpers_hooks_getters_and_constructors_not_executed",
            "limits": {key: 10 for key in ("instructions", "expressionNodes", "predicateNodes", "definitionAlternatives", "expressionDepth", "localDefinitionDepth")},
            "condition": copy.deepcopy(row), "fields": {"velocity": row}}


def test_known_coverage_compacts_diagnostics_but_not_actions_guards_values():
    observation = {"spawnInputCoverage": coverage(), "spawnInputs": {"damage": const(77)},
                   "whenSourceCondition": {"kind": "argument", "index": 5}}
    before = copy.deepcopy(observation)
    result = MechanicsRenderer().render(observation)
    summary = result["spawnInputCoverage"]
    assert summary["fields"]["velocity"] == {"status": "partial_source_expression", "reasons": ["helper_output_not_evaluated"]}
    assert summary["condition"]["status"] == "partial_source_expression"
    assert "audit" in summary["scope"]
    assert result["spawnInputs"] == {"damage": "77"}
    assert result["whenSourceCondition"] == "arg5"
    assert observation == before


@pytest.mark.parametrize("part", ["top", "diagnostic", "scope", "status", "limit"])
def test_unfamiliar_coverage_envelope_stays_literal(part):
    value = coverage()
    if part == "top":
        value["newMechanic"] = 3
    elif part == "diagnostic":
        value["fields"]["velocity"]["unresolved"][0]["futureEffect"] = 8
    elif part == "scope":
        value["scope"] = "future_scope"
    elif part == "status":
        value["condition"]["status"] = "future_status"
    else:
        value["limits"]["futureLimit"] = 8
    assert MechanicsRenderer().render(value) == value


def test_unit_evidence_keeps_immortality_routing_cadence_and_numeric_relation():
    value = {"unitEvidence": {"accumulatorUnitsPerHealthPoint": 120, "healthPointsPerLoopBody": 1,
                             "targetRouting": "realLife_if_nonnegative_else_whoAmI", "damageCondition": "resolved_target.immortal == false",
                             "scope": "cadence not guaranteed", "healthStoreIlOffset": 2173},
             "durationTicksMin": 180, "probabilityNumerator": 1, "probabilityDenominator": 3,
             "sourceCertificate": {"assemblySha256": "diagnostic", "methods": []}}
    result = MechanicsRenderer().render(value)
    assert "sourceCertificate" not in result
    assert result["unitEvidence"] == {k: v for k, v in value["unitEvidence"].items() if k != "healthStoreIlOffset"}
    assert {k: result[k] for k in ("durationTicksMin", "probabilityNumerator", "probabilityDenominator")} == {
        "durationTicksMin": 180, "probabilityNumerator": 1, "probabilityDenominator": 3}
