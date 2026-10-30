"""Behavior facts survive model projection; dump-only proof data does not travel."""
import copy

import pytest

from infini_local.pipelines.native_attack_behavior_view import project_attack_behavior
from infini_local.pipelines.native_attack_tables import unpack_attack_tables
from infini_local.pipelines.parent_context_pipeline import compact_projectile_profile


def native_reference():
    certificate = {"method": "Terraria.Projectile.NativeAI()", "sourceModuleVersionId": "module", "sourceMethodSha256": "sha"}
    program = {**certificate,
        "observations": [
            {"kind": "state_write", "at": 42, "block": 20, "requiredPredicates": ["b8"],
             "expression": "stfld(Entity.velocity,this,mul(l1@12,-0.0))"},
            {"kind": "clock_or_ai_write", "at": 44, "block": 20, "requiredPredicates": ["b8"],
             "expression": 'opaque["l1@12",l1@12]'},
            {"kind": "collision_call", "at": 50, "block": 21, "requiredPredicates": ["b8"],
             "call": "Utils.Intersects", "receiver": "this", "arguments": {"target": "l1@12", "radius": "-1E-05"}},
        ],
        "dependencies": {
            "l1@12": {"at": 12, "block": 10, "requiredPredicates": ["b8"],
                       "expression": 'alternatives(0,source_block(20,requires=["b8"],value=mul(2,3)))'},
            "addressed_l2": {"scope": "address_alias_unknown", "orderedSourceUses": [
                {"at": 30, "block": 20, "requiredPredicates": ["b8"], "expression": "l1@12"},
                {"at": 31, "block": 20, "requiredPredicates": ["b8"], "expression": "l1@12"}]},
        },
        "predicates": [{"id": "b8", "at": 8, "op": "bge.un.s", "inputs": ["l1@12", "0"], "successors": [20, 21]}],
        "symbols": {"Entity.velocity": "Terraria.Entity.velocity", "Utils.Intersects": "Terraria.Utils.Intersects(System.Single)"},
        "coverage": "connected_source_slice; opaque_fields_calls_and_address_aliases_are_symbolic",
        "unresolved": ["native_hook"],
    }
    return {"source": "read_only_native_attack_source", "version": 1,
            "identityPredicates": {"Projectile.type": 42, "Projectile.aiStyle": 1},
            "sourceMethods": [certificate], "motion": {"programs": [program]},
            "coverage": {"unresolved": ["damage_can_stop_before_visual_lifetime"]},
            "admission": {"ownerHitCheck": False, "ownerHitCheckDistance": 0},
            "future": {"at": 7, "expression": "l1@12", "sourceMethodSha256": "unknown-field"}}


def test_behavior_projection_preserves_connected_branch_and_target_semantics():
    source = native_reference()
    before = copy.deepcopy(source)
    result = unpack_attack_tables(compact_projectile_profile({"attackReference": source})["attackReference"])
    program = result["motion"]["programs"][0]
    assert program == {
        "method": "T.Projectile.NativeAI()",
        "observations": [
            {"kind": "state_write", "step": 4, "block": 20, "requiredPredicates": ["b8"], "expression": "set((this).Entity.velocity,(d0*-0.0))"},
            {"kind": "clock_or_ai_write", "step": 5, "block": 20, "requiredPredicates": ["b8"], "expression": 'opaque["l1@12",d0]'},
            {"kind": "collision_call", "step": 6, "block": 21, "requiredPredicates": ["b8"], "call": "Utils.Intersects", "receiver": "this",
             "arguments": {"target": "d0", "radius": "-1E-05"}},
        ],
        "dependencies": {
            "d0": {"step": 1, "block": 10, "requiredPredicates": ["b8"], "expression": 'alternatives(0,source_block(20,requires=["b8"],value=(2*3)))'},
            "d1": {"scope": "address_alias_unknown", "orderedSourceUses": [
                {"step": 2, "block": 20, "requiredPredicates": ["b8"], "expression": "d0"},
                {"step": 3, "block": 20, "requiredPredicates": ["b8"], "expression": "d0"}]},
        },
        "predicates": [{"id": "b8", "step": 0, "op": "bge.un.s", "inputs": ["d0", "0"], "successors": [20, 21]}],
        "symbols": {"Utils.Intersects": "T.Utils.Intersects(float)"},
        "unresolved": ["native_hook"],
    }
    assert "sourceMethods" not in result
    for key in ("identityPredicates", "coverage", "admission", "future"):
        assert result[key] == source[key]
    assert source == before
    assert project_attack_behavior(result) == result
    result["admission"]["ownerHitCheck"] = True
    assert source == before


@pytest.mark.parametrize("expression", ["unsupported source syntax", "opaque[d0,l1@12]"])
def test_unsupported_syntax_or_local_alias_collision_never_partially_renames(expression):
    source = native_reference()
    source["motion"]["programs"][0]["observations"][0]["expression"] = expression
    program = project_attack_behavior(source)["motion"]["programs"][0]
    assert list(program["dependencies"]) == ["l1@12", "addressed_l2"]
    assert program["observations"][0]["expression"] == expression
    assert program["observations"][2]["arguments"]["target"] == "l1@12"
    assert program["predicates"][0]["inputs"] == ["l1@12", "0"]


@pytest.mark.parametrize("extra", [{"source": "future_source"}, {"version": True}, {"version": 2}, {"behaviorView": {"future": True}}])
def test_unknown_contract_is_literal_detached(extra):
    source = native_reference() | extra
    result = project_attack_behavior(source)
    assert result == source
    assert result is not source


def test_real_native_capture_keeps_attack_geometry_timing_targets_and_draw():
    import json
    from pathlib import Path
    from infini_local.pipelines.native_attack_expression_view import compact_attack_expressions
    from infini_local.pipelines.native_attack_tables import pack_attack_tables
    parent = json.loads((Path(__file__).parent / "fixtures" / "native_excalibur_parent_capture.json").read_text())
    snapshot = copy.deepcopy(parent)
    raw = parent["directProjectileRaw"]
    compact = compact_projectile_profile(raw)
    view = unpack_attack_tables(compact["attackReference"])
    motion = view["motion"]["programs"][0]
    raw_motion = raw["attackReference"]["motion"]["programs"][0]
    assert len(raw_motion["observations"]) == 9
    assert len(motion["observations"]) == 6
    assert len(motion["dependencies"]) == 7
    assert motion["identitySelection"]["forCapturedIdentity"] is True
    assert view["identityPredicates"] == {"Projectile.type": 982, "Projectile.aiStyle": 190}
    assert motion["observations"][3]["expression"] == "set((this).Projectile.scale,(d5+(d2*d6)))"
    assert motion["dependencies"]["d5"]["expression"] == "1"
    assert motion["dependencies"]["d6"]["expression"] == "0.6"
    assert [predicate["id"] for predicate in motion["predicates"]] == ["b2504"]
    assert motion["dependencies"]["d2"]["expression"] == "(f32_at((this).Projectile.localAI,0)/f32_at((this).Projectile.ai,1))"
    assert motion["observations"][-2]["expression"] == "set((this).Projectile.scale,((this).Projectile.scale*f32_at((this).Projectile.ai,2)))"
    assert motion["observations"][-1]["call"] == "Projectile.Kill"
    assert motion["observations"][-1]["requiredPredicates"] == ["b2504"]
    assert motion["predicates"][-1]["inputs"] == ["f32_at((this).Projectile.localAI,0)", "f32_at((this).Projectile.ai,1)"]
    collision = view["collision"]
    assert collision["dependencies"]["d0"]["expression"] == "(94*(this).Projectile.scale)"
    assert collision["dependencies"]["d3"]["expression"] == "0.7853982"
    cone_calls = [row for row in collision["observations"] if row.get("call") == "Utils.IntersectsConeSlowMoreAccurate"]
    assert [row["arguments"]["targetRect"] for row in cone_calls] == ["targetRect", "targetRect"]
    assert [row["arguments"]["coneRotation"] for row in cone_calls] == ["d1", "d5"]
    assert [row["requiredPredicates"] for row in cone_calls] == [["b407"], ["b407", "b478", "b543"]]
    assert len(collision["predicateSources"]) == 2
    assert len([row for row in view["draw"]["programs"][0]["layers"] if row["kind"] == "sprite"]) == 7
    for field in ("penetrate", "maxPenetrate", "usesLocalNPCImmunity", "localNPCHitCooldown", "usesIDStaticNPCImmunity", "idStaticNPCHitCooldown", "stopsDealingDamageAfterPenetrateHits"):
        assert compact[field] == raw[field]
    # This is a real captured regression, not an asserted universal size budget.
    dump = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    previous = pack_attack_tables(compact_attack_expressions(raw["attackReference"]))
    assert len(dump(compact["attackReference"])) < len(dump(previous))
    assert "sourceMethodSha256" not in dump(view)
    assert "sourceModuleVersionId" not in dump(view)
    assert "PublicKeyToken=" not in dump(view)
    assert parent == snapshot


def test_future_program_fields_cannot_acquire_dangling_renamed_local_references():
    source = native_reference()
    source["motion"]["programs"][0]["futureConsumer"] = {"expression": "l1@12"}
    program = project_attack_behavior(source)["motion"]["programs"][0]
    assert program["futureConsumer"] == {"expression": "l1@12"}
    assert "l1@12" in program["dependencies"]
    assert program["observations"][2]["arguments"]["target"] == "l1@12"


def test_step_ordinals_preserve_cross_list_order_same_offset_and_future_collision():
    source = native_reference()
    program = source["motion"]["programs"][0]
    program["dependencies"]["l1@12"]["at"] = 42
    view = project_attack_behavior(source)["motion"]["programs"][0]
    assert view["dependencies"]["d0"]["step"] == view["observations"][0]["step"]
    assert view["predicates"][0]["step"] < view["dependencies"]["d1"]["orderedSourceUses"][0]["step"] < view["observations"][0]["step"]
    program["observations"][0]["step"] = "future-owned"
    view = project_attack_behavior(source)["motion"]["programs"][0]
    assert view["observations"][0]["step"] == "future-owned"
    assert view["observations"][0]["at"] == 42
    assert view["predicates"][0]["at"] == 8


@pytest.mark.parametrize("uses", [None, 7, "future-format", [None], [{"nextOffset": 42}]])
def test_malformed_or_future_addressed_use_schema_is_literal_not_a_projection_crash(uses):
    source = native_reference()
    original = source["motion"]["programs"][0]
    original["dependencies"]["addressed_l2"]["orderedSourceUses"] = uses
    before = copy.deepcopy(source)
    result = unpack_attack_tables(compact_projectile_profile({"attackReference": source})["attackReference"])
    program = result["motion"]["programs"][0]
    assert program["dependencies"]["addressed_l2"]["orderedSourceUses"] == uses
    assert program["observations"][0]["at"] == 42
    assert program["predicates"][0]["at"] == 8
    assert list(program["dependencies"]) == ["l1@12", "addressed_l2"]
    assert "step" not in program["observations"][0]
    assert source == before


def test_future_offset_reference_preserves_all_original_offset_targets():
    source = native_reference()
    source["motion"]["programs"][0]["futureConsumer"] = {"nextOffset": 42}
    program = project_attack_behavior(source)["motion"]["programs"][0]
    assert program["futureConsumer"] == {"nextOffset": 42}
    assert program["observations"][0]["at"] == 42
    assert program["predicates"][0]["at"] == 8
    assert "step" not in program["observations"][0]


def identity_selection_reference():
    source = native_reference()
    program = source["motion"]["programs"][0]
    selected = copy.deepcopy(program)
    selected["observations"] = selected["observations"][1:]
    selected["identitySelection"] = {
        "source": "certified_receiver_identity_cfg", "version": 1,
        "identityPredicates": copy.deepcopy(source["identityPredicates"]),
        "scope": "Only certified receiver identity branches selected; live state remains symbolic.",
        "selectedEdges": [{"at": 8, "block": 0, "op": "beq.s", "successor": 20}],
    }
    program["identitySelected"] = selected
    return source


def test_certified_same_identity_selection_supplies_behavior_not_the_full_other_identity_graph():
    source = identity_selection_reference()
    before = copy.deepcopy(source)
    result = project_attack_behavior(source)
    program = result["motion"]["programs"][0]
    assert len(program["observations"]) == 2
    assert [row["kind"] for row in program["observations"]] == ["clock_or_ai_write", "collision_call"]
    assert program["observations"][1]["arguments"]["target"] == "d0"
    assert program["predicates"][0]["successors"] == [20, 21]
    assert set(program["identitySelection"]) == {"forCapturedIdentity", "scope"}
    assert program["identitySelection"]["forCapturedIdentity"] is True
    assert result["identityPredicates"] == source["identityPredicates"]
    assert "identitySelected" not in program
    assert source == before
    assert len(source["motion"]["programs"][0]["observations"]) == 3


@pytest.mark.parametrize("mutation", ["method", "certificate", "identity", "bool_identity", "version", "future_receipt", "future_program", "future_row", "original_future_row", "bad_uses"])
def test_unrecognized_or_mismatched_identity_selection_preserves_the_complete_raw_source(mutation):
    source = identity_selection_reference()
    selected = source["motion"]["programs"][0]["identitySelected"]
    receipt = selected["identitySelection"]
    if mutation == "method":
        selected["method"] = "Terraria.OtherMethod"
    elif mutation == "certificate":
        selected["sourceMethodSha256"] = "other-binary"
    elif mutation == "identity":
        receipt["identityPredicates"]["Projectile.type"] = 43
    elif mutation == "bool_identity":
        receipt["identityPredicates"]["Projectile.aiStyle"] = True
    elif mutation == "version":
        receipt["version"] = True
    elif mutation == "future_receipt":
        receipt["future"] = "unknown"
    elif mutation == "future_program":
        selected["future"] = "unknown"
    elif mutation == "future_row":
        selected["observations"][0]["nextOffset"] = 42
    elif mutation == "original_future_row":
        source["motion"]["programs"][0]["observations"][0]["futureMechanic"] = "literal"
    else:
        selected["dependencies"]["addressed_l2"]["orderedSourceUses"] = None
    before = copy.deepcopy(source)
    assert project_attack_behavior(source) == before
    assert source == before


@pytest.mark.parametrize("certified", [True, False])
def test_native_color_display_preserves_typed_rgba_operation_and_grouping(certified):
    source = native_reference()
    program = source["motion"]["programs"][0]
    program["observations"][0]["expression"] = "Color.op_Multiply[Color.op_Multiply[Color.get_White[],0.4],l1@12]"
    owner = "Microsoft.Xna.Framework.Color" if certified else "Other.Color"
    program["symbols"].update({"Color.op_Multiply": f"{owner}.op_Multiply({owner},System.Single)",
                               "Color.get_White": f"{owner}.get_White()"})
    result = project_attack_behavior(source)["motion"]["programs"][0]
    expected = "((rgba.white*0.4)*d0)" if certified else "Color.mul[Color.mul[Color.get_White[],0.4],d0]"
    assert result["observations"][0]["expression"] == expected
    assert result["dependencies"]["d0"]["expression"] == 'alternatives(0,source_block(20,requires=["b8"],value=(2*3)))'
    assert result["observations"][0]["block"] == 20
    assert result["observations"][0]["requiredPredicates"] == ["b8"]
    assert program["observations"][0]["expression"] == "Color.op_Multiply[Color.op_Multiply[Color.get_White[],0.4],l1@12]"


def test_color_display_does_not_rewrite_quoted_literals_or_unknown_metadata():
    source = native_reference()
    program = source["motion"]["programs"][0]
    program["symbols"]["Color.get_White"] = "Microsoft.Xna.Framework.Color.get_White()"
    program["observations"][0]["expression"] = 'opaque["Color.get_White[]",Color.get_White[]]'
    result = project_attack_behavior(source)["motion"]["programs"][0]
    assert result["observations"][0]["expression"] == 'opaque["Color.get_White[]",rgba.white]'
    program["futureColor"] = {"expression": "Color.get_White[]"}
    result = project_attack_behavior(source)["motion"]["programs"][0]
    assert result["futureColor"] == {"expression": "Color.get_White[]"}
    assert result["observations"][0]["expression"] == 'opaque["Color.get_White[]",Color.get_White[]]'
