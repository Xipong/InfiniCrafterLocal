"""Exact native-source notation projection, not evaluation or gameplay inference."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.pipelines.native_attack_expression_view import compact_attack_expressions, expand_attack_expressions
from infini_local.pipelines.parent_context_pipeline import compact_projectile_profile


def attack_fixture():
    return {"source": "read_only_native_attack_source", "version": 1,
        "identityPredicates": {"Projectile.type": 982, "Projectile.aiStyle": 190},
        "motion": {"programs": [{"method": "Fixture.NativeAI", "observations": [
            {"kind": "live_scale", "at": 12, "block": 0, "requiredPredicates": [],
             "expression": "stfld(Projectile.scale,this,mul(add(1,mul(l1@130,0.6)),ldelem.r4(ldfld(Projectile.ai,this),2)))"}],
            "dependencies": {}, "predicates": [], "symbols": {"Projectile.scale": "Terraria.Projectile.scale"}}]},
        "coverage": {"unresolved": ["native hooks"], "false": False, "zero": 0, "floatZero": 0.0, "empty": None}}


def test_actual_parent_projection_marks_behavior_view_and_keeps_raw_detached():
    source = attack_fixture()
    result = compact_projectile_profile({"type": 982, "attackReference": source})["attackReference"]
    from infini_local.pipelines.native_attack_tables import unpack_attack_tables
    result = unpack_attack_tables(result)
    assert result["behaviorView"]["version"] == 1
    assert result["coverage"] == source["coverage"]
    assert "behaviorView" not in source


def test_readable_math_view_preserves_source_and_grouping():
    source = attack_fixture()
    before = copy.deepcopy(source)
    result = compact_attack_expressions(source)
    text = json.dumps(result, ensure_ascii=False)
    assert "(1+(l1@130*0.6))" in text
    assert "(this).Projectile.ai" in text
    assert source == before


@pytest.mark.parametrize("expression", [
    "add(-1E-05,div(mul(3.1415927,l1@3),-0.0))",
    "div.un(conv.r4(ldelem.i4(ldfld(Projectile.ai,this),0)),2)",
    'alternatives(l0@12,source_block(23,requires=["b3","b6"],value=mul(l1@2,0.6)))',
    'stind.r4(ldelema(ldfld(Projectile.localAI,this),0;"System.Single"),add(ldind.r4(ldelema(ldfld(Projectile.localAI,this),0;"System.Single")),1))',
    "Vector2.op_Addition[ldfld(Entity.position,this),Vector2.op_Multiply[ldfld(Entity.velocity,this),mul(45,l9@434)]]",
    "ldelem.ref(ldsfld(Main.player),ldfld(Projectile.owner,this))",
    'Member.Unknown["commas,and+operators;[]()",0,-0.0]',
    'switch(sub(ldfld(Projectile.type,this),982);[246,264,280,235])',
    "unsupported syntax: retain + unbalanced(",
])
def test_notation_roundtrip_preserves_exact_source_string(expression):
    source = attack_fixture()
    program = source["motion"]["programs"][0]
    program["dependencies"] = {"addressed_l1": {"orderedSourceUses": [
        {"expression": expression, "requiredPredicates": ["b3"], "at": 42, "block": 23}]}}
    program["predicates"] = [{"id": "b3", "at": 3, "op": "bge.un.s", "inputs": [expression, "-0.0"], "successors": [23, 45]}]
    program["observations"].append({"call": "Member.Opaque", "receiver": expression, "arguments": {"value": expression},
                                     "requiredPredicates": ["b3"], "at": 50, "block": 23})
    before = json.dumps(source, ensure_ascii=False)
    result = compact_attack_expressions(source)
    assert json.dumps(expand_attack_expressions(result), ensure_ascii=False) == before
    assert json.dumps(source, ensure_ascii=False) == before
    assert compact_attack_expressions(result) == result
    # Symbols, certificates, branch meaning/successors and unknown/zero kinds
    # are not shortened, reclassified or moved by the notation transformer.
    assert result["motion"]["programs"][0]["predicates"][0]["op"] == "bge.un.s"
    assert result["coverage"] == source["coverage"]


@pytest.mark.parametrize("extra", [{"source": "unrecognized"}, {"version": True}, {"version": 2},
    {"expressionNotation": {"future": "literal producer field"}}])
def test_unknown_schema_or_reserved_notation_is_detached_literal_passthrough(extra):
    source = attack_fixture()
    source.update(extra)
    result = compact_attack_expressions(source)
    assert json.dumps(result) == json.dumps(source)
    assert result is not source


def test_reserved_alias_collision_does_not_reinterpret_source():
    source = attack_fixture()
    source["motion"]["programs"][0]["dependencies"]["l0@7"] = {"expression": "Vector2.mul[this,2]"}
    assert compact_attack_expressions(source) == source


def test_full_qualified_symbol_metadata_has_reversible_readable_type_aliases():
    source = attack_fixture()
    source["motion"]["programs"][0]["symbols"]["Vector2.op_Multiply"] = (
        "Microsoft.Xna.Framework.Vector2.op_Multiply(Microsoft.Xna.Framework.Vector2,System.Single)")
    result = compact_attack_expressions(source)
    symbol = result["motion"]["programs"][0]["symbols"]["Vector2.op_Multiply"]
    assert symbol == "Xna.Vector2.op_Multiply(Xna.Vector2,float)"
    assert json.dumps(expand_attack_expressions(result)) == json.dumps(source)


def test_unknown_nested_fields_and_literal_tooltips_are_not_interpreted():
    source = attack_fixture()
    source["future"] = {"expression": "mul(1,2)", "tooltipLines": ["add(1,2)"]}
    source["motion"]["programs"][0]["future"] = {"expression": "div(1,0)"}
    result = compact_attack_expressions(source)
    assert result["future"] == source["future"]
    assert result["motion"]["programs"][0]["future"] == source["motion"]["programs"][0]["future"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("stage", ["Author", "GameplayRepair", "Visual", "VisualRepair", "VFX", "VFXRepair"])
@pytest.mark.parametrize("fixture", ["synthetic", "native_excalibur"])
def test_native_v1_behavior_view_at_each_real_serialized_stage(monkeypatch, mode, stage, fixture):
    from infini_local.core import llm_config, vfx_manifest as vfx
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.pipelines import vfx_generation_pipeline as transport
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit
    from test_parent_attack_reference import _capture_stage, _CapturedRequest
    # Table packing is a separate, explicit decoding layer. Do not modify the
    # ordinary packet reader to conceal what the model literally receives.
    from infini_local.pipelines.native_attack_tables import unpack_attack_tables
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    source = attack_fixture()
    # A representative repeated-row program amortizes the self-contained guide.
    # Small native sources also carry the explicit behavior-view contract.
    template = source["motion"]["programs"][0]["observations"][0]
    source["motion"]["programs"][0]["observations"] = [copy.deepcopy(template) | {"at": 12 + index} for index in range(24)]
    parent = {"directProjectileRaw": {"type": 982, "attackReference": source}}
    if fixture == "native_excalibur":
        parent = json.loads((Path(__file__).parent / "fixtures" / "native_excalibur_parent_capture.json").read_text())
        source = parent["directProjectileRaw"]["attackReference"]
    before = json.dumps(parent)
    captured = []
    scope = None
    if stage == "Author":
        request, _, _ = author.build_initial_author_request(parent, parent, "compact-source", model_name="offline")
    elif stage == "GameplayRepair":
        from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
        from repair_test_helpers import repair_with_response
        child = build_runtime_fixture("workbench_blade")
        lifetime = next(row for row in child["runtimeProgram"]["calls"] if row["fn"] == "set_projectile_lifetime")
        correct = copy.deepcopy(lifetime)
        lifetime["params"]["lifetimeSeconds"] = 0
        _, request = repair_with_response(monkeypatch, child, {"note": "lifetime only", "callsUpsert": [correct]},
                                          mode, parents=(parent, parent))
    else:
        child = _accepted_visual_data("workbench_blade")
        if stage.startswith("Visual"):
            _capture_stage(monkeypatch, visual, captured)
            kwargs = {}
            if stage == "VisualRepair":
                scope = {"fieldPermissions": {"itemPaths": ["prompt"], "entities": [], "equipOverlayPaths": []}}
                kwargs = {"repair_errors": [{"path": "$.item.prompt"}], "previous": _visual_kit(child), "repair_scope": scope}
            with pytest.raises(_CapturedRequest):
                visual._request_visual_kit(child, parent, parent, **kwargs)
        else:
            _capture_stage(monkeypatch, transport, captured)
            monkeypatch.setattr(transport, "USE_LLM", True)
            kwargs = {}
            if stage == "VFXRepair":
                scope = {"allowCreateSlots": True, "fieldPermissions": {"globals": {}, "slots": [], "assets": []}}
                kwargs = {"repair_errors": [], "previous": {}, "repair_scope": scope}
            with pytest.raises(_CapturedRequest):
                vfx._request(transport.call_llm_vfx_director, vfx._prompt_packet(child, parent, parent), **kwargs)
        request = captured[0]
    assert request["response_format"]["type"] == mode
    packet = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    found = []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "attackReference":
                    found.append(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(packet["parentFactsReadOnly" if stage in ("VisualRepair", "VFXRepair") else "parents"])
    assert len(found) == 2
    for view in found:
        if fixture == "synthetic":
            # This future-shaped coverage fixture deliberately adds unknown
            # fields. Stage pruning must retain its complete connected graph.
            assert "(1+(l1@130*0.6))" in json.dumps(view)
        from infini_local.pipelines.native_attack_behavior_view import project_attack_behavior
        projected = unpack_attack_tables(view)
        expected = project_attack_behavior(source)
        author_presentation = fixture == "native_excalibur" and stage in {"Author", "GameplayRepair"}
        if author_presentation:
            expected.pop("draw")
            assert "Native draw layer instructions omitted" in projected.pop("presentationScope")
        if fixture == "native_excalibur" and stage not in {"Author", "GameplayRepair"}:
            for field in ("motion", "motionDispatch", "collision", "positionIntegration"):
                expected.pop(field, None)
            assert projected.pop("presentationScope")
        assert projected == expected
        assert projected["behaviorView"]["version"] == 1
        if fixture == "native_excalibur":
            if author_presentation:
                brief = next(iter(packet["parentBriefs"].values()))
                appearance = brief["appearance"]["directProjectile"]
                assert appearance["sourceRenderKinds"] == ["sprite", "nativeStarSparkle"]
                assert appearance["sourceColorWrites"][0]["expression"] == "writeRGB(tint1,180,160,60)"
            else:
                literal_draw = view.get("data", view)["draw"]["programs"][0]
                assert literal_draw["layers"][6]["tint"] == "((rgba.white*0.4)*fade)"
                assert "$table" not in json.dumps(literal_draw)
            if stage in {"Author", "GameplayRepair"}:
                assert "geometryRule" in projected["collision"]["predicateSources"][0]
    if scope is not None:
        assert packet["repairScope"] == scope
    assert json.dumps(parent) == before
