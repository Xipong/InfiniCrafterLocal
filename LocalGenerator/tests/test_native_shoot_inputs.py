"""Nonexecuting, typed native spawn expression controls."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/generate"))
import native_attack_fact_analysis as analysis
from test_native_attack_fact_analysis import program, spawn, wrap

VECTOR_CTOR = ("Microsoft.Xna.Framework.Vector2..ctor", "2002010c0c")


def anchored_spawn():
    field = lambda name: [("ldarg", 0), ("ldfld", "Terraria.Player." + name)]
    return [("ldarg", 0), ("ldarg", 2),
            ("call", ("Terraria.Player.GetAdjustedItemScale", 1, True, True)), ("stloc", 322),
            ("ldloc", 7), ("ldarg", 0), ("call", ("Terraria.Player.get_MountedCenter", 0, True, True))] + field("direction") + [
            ("conv", "conv.r4"), ("const", 0.0), ("newobj", VECTOR_CTOR),
            ("ldloc", 0), ("ldloc", 4), ("ldloc", 5), ("ldarg", 1)] + field("direction") + [
            ("conv", "conv.r4")] + field("gravDir") + [("mul",)] + field("itemAnimationMax") + [
            ("conv", "conv.r4"), ("ldloc", 322),
            ("call", ("Terraria.Projectile.NewProjectile", 10, False, True)), ("pop",), ("ret",)]


def test_spawn_inputs_keep_native_anchor_ai_and_single_assignment_helper_output():
    row = analysis.shoot_facts(program(wrap(anchored_spawn())))[0]
    inputs = row["spawnInputs"]
    assert set(inputs) == {"source", "position", "velocity", "type", "damage", "knockback", "owner", "ai0", "ai1", "ai2"}
    assert inputs["position"]["member"] == "Terraria.Player.get_MountedCenter"
    assert inputs["position"]["arguments"] == [{"kind": "argument", "index": 0}]
    assert inputs["velocity"]["kind"] == "data_constructor"
    assert inputs["velocity"]["signature"] == VECTOR_CTOR[1]
    assert inputs["velocity"]["arguments"][0]["value"]["member"] == "Terraria.Player.direction"
    assert inputs["type"]["role"] == "current_native_shot_type"
    assert inputs["damage"]["role"] == "current_native_shot_damage"
    assert inputs["knockback"]["role"] == "current_native_knockback"
    assert inputs["owner"] == {"kind": "argument", "index": 1}
    assert inputs["ai0"]["operator"] == "mul"
    assert inputs["ai0"]["right"]["member"] == "Terraria.Player.gravDir"
    assert inputs["ai1"]["value"]["member"] == "Terraria.Player.itemAnimationMax"
    scale = inputs["ai2"]
    assert scale["kind"] == "local_definition"
    assert scale["local"] == 322
    assert scale["value"]["member"] == "Terraria.Player.GetAdjustedItemScale"
    assert scale["value"]["evaluation"] == "unresolved_helper_or_hook_output"
    assert scale["value"]["provenance"]["status"] == "unknown"
    assert row["spawnInputCoverage"]["scope"] == "native_call_arguments_only_not_final_attack"
    assert row["sourcePredicates"] == [{"field": "Terraria.Item.type", "argument": 2, "operator": "equals", "literal": 123, "sourceIlOffset": 5}]



@pytest.mark.parametrize("setup, reason", [
    ([("ldsfld", "unknown"), ("brfalse", "use"), ("const", 2.0), ("stloc", 322), ("label", "use")], "definition_does_not_dominate_use"),
    ([("const", 2.0), ("stloc", 322), ("const", 3.0), ("stloc", 322)], "multiple_branch_local_definitions"),
    ([("const", 2.0), ("stloc", 322), ("ldloca", 322), ("call", ("unknown.Mutate", 1, False, False))], "address_exposed_local"),
    ([("unknown_stack",), ("stloc", 322)], "unsupported_definition_expression"),
])
def test_unsafe_local_definitions_remain_explicit_unknowns_without_losing_count_proof(setup, reason):
    body = anchored_spawn()[4:]
    row = analysis.shoot_facts(program(wrap(setup + body)))[0]
    scale = row["spawnInputs"]["ai2"]
    assert scale["kind"] == "unknown"
    assert scale["local"] == 322
    assert scale["reason"] == reason
    assert row["explicitSpawnCount"]["minimum"] == 1


def test_scalar_overload_preserves_all_twelve_inputs_in_native_order():
    args = [("ldloc", 7)] + [("const", float(i)) for i in range(4)] + [("ldloc", 0), ("ldloc", 4), ("ldloc", 5), ("ldarg", 1)] + [("const", i) for i in (8, 9, 10)]
    code = program(wrap(args + [("call", ("Terraria.Projectile.NewProjectile", 12, False, True)), ("pop",), ("ret",)]))
    inputs = analysis.shoot_facts(code)[0]["spawnInputs"]
    assert [inputs[k]["value"] for k in ("positionX", "positionY", "velocityX", "velocityY", "ai0", "ai1", "ai2")] == [0., 1., 2., 3., 8, 9, 10]


@pytest.mark.parametrize("prefix, suffix", [
    ([("ldsfld", "unknown.admission"), ("brfalse", "outside")], []),
    ([], anchored_spawn()[:-1]),
])
def test_typed_constructor_does_not_turn_conditional_or_multispawn_into_fixed_one(prefix, suffix):
    assert analysis.shoot_facts(program(wrap(prefix + anchored_spawn()[:-1] + suffix + [("ret",)]))) == []


def test_local_definition_is_a_snapshot_not_a_new_field_read_at_spawn():
    body = anchored_spawn()
    body[:4] = [("ldarg", 0), ("ldfld", "Terraria.Player.gravDir"), ("stloc", 322),
                ("ldarg", 0), ("const", -1.0), ("stfld", "Terraria.Player.gravDir")]
    scale = analysis.shoot_facts(program(wrap(body)))[0]["spawnInputs"]["ai2"]
    assert scale["scope"] == "value_at_store"
    assert scale["value"]["member"] == "Terraria.Player.gravDir"
    assert scale["sourceStoreIlOffset"] == 8


def test_typed_vector_constructor_closes_real_stack_shape_without_execution():
    body = spawn()
    body[2:3] = [("ldarg", 0), ("ldfld", "Terraria.Player.direction"),
                 ("conv", "conv.r4"), ("const", 0.0), ("newobj", VECTOR_CTOR)]
    records = analysis.shoot_facts(program(wrap(body + [("ret",)])))
    assert len(records) == 1
    assert records[0]["explicitSpawnCount"] == {"minimum": 1, "maximum": 1, "distribution": "fixed"}
    assert records[0]["damageMultiplierAtSpawn"] == 1


@pytest.mark.parametrize("ctor", [
    ("Unknown.Vector2..ctor", "2002010c0c"),
    (VECTOR_CTOR[0], "2001010c"),
    (VECTOR_CTOR[0], "0002010c0c"),
    (VECTOR_CTOR[0], "2002010808"),
])
def test_constructor_name_or_arity_alone_is_not_a_typed_data_constructor(ctor):
    code = program([("const", 1.0), ("const", 0.0), ("newobj", ctor)])
    with pytest.raises(analysis.Unrecognized):
        analysis.expression(code, 2)
