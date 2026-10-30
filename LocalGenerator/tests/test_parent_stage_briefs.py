"""Actual packet presentation is role-neutral and does not choose parent mechanics."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.pipelines.parent_context_cards import parent_context_for_stage, raw_parent_card_for_llm
from infini_local.pipelines.native_attack_tables import unpack_attack_tables
from prompt_packet_helpers import request_dossier, expand_native_source_references


def _native():
    return json.loads((Path(__file__).parent / "fixtures/native_excalibur_parent_capture.json").read_text())


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_author_briefs_precede_details_and_preserve_all_gameplay(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    a = _native()
    b = {"name": "Material", "damage": 0, "consumable": False, "maxStack": 9999, "tooltipLines": ["literal"]}
    before = copy.deepcopy((a, b))
    request, _, _ = build_initial_author_request(a, b, "briefs", model_name="offline")
    packet = expand_native_source_references(request_dossier(request))
    assert list(packet).index("parentBriefs") < list(packet).index("parents")
    assert set(packet["parentBriefs"]["A"]) == set(packet["parentBriefs"]["B"]) == {
        "identity", "properties", "behavior", "appearance"}
    assert packet["parentBriefs"]["B"]["properties"]["damage"] == 0
    assert packet["parentBriefs"]["B"]["properties"]["consumable"] is False
    assert packet["parentBriefs"]["B"]["identity"]["tooltipLines"] == ["literal"]
    old = unpack_attack_tables(raw_parent_card_for_llm(a)["raw"]["directProjectile"]["attackReference"])
    current = unpack_attack_tables(packet["parents"]["A"]["packet"]["raw"]["directProjectile"]["attackReference"])
    assert "draw" not in current
    assert "omitted" in current.pop("presentationScope")
    old.pop("draw")
    # Includes complete conditions, collision/target admission, clocks and gaps;
    # no reduced graph based on a guessed weapon family or inferred DPS.
    assert current == old
    assert (a, b) == before


@pytest.mark.parametrize("stage", ["author", "visual", "vfx"])
@pytest.mark.parametrize("as_list", [False, True])
@pytest.mark.parametrize("mutation", ["future_layer", "null_view", "bool_version", "null_ordered_uses",
                                     "future_outer", "future_defaults", "future_ordered_row", "null_programs", "null_observations",
                                     "future_defaults_value", "future_layer_value"])
def test_unknown_draw_kept_and_parent_names_do_not_select_projection(stage, as_list, mutation):
    source = raw_parent_card_for_llm(_native())
    attack = unpack_attack_tables(source["raw"]["directProjectile"]["attackReference"])
    program = attack["draw"]["programs"][0]
    if mutation == "future_layer":
        program["layers"][0]["futureField"] = {"dynamic": True}
    elif mutation == "null_view":
        program["renderLayerView"] = None
    elif mutation == "bool_version":
        program["renderLayerView"]["version"] = True
    elif mutation == "null_ordered_uses":
        program["definitions"]["tint1"]["orderedSourceUses"] = None
    elif mutation == "future_outer":
        attack["futureBinding"] = {"sourceRef": "draw.programs[0].definitions.tint1"}
    elif mutation == "future_defaults":
        program["spriteLayerDefaults"]["futureField"] = {"dynamicMechanic": True}
    elif mutation == "future_ordered_row":
        program["definitions"]["tint1"]["orderedSourceUses"][0]["futureField"] = {"dynamicMechanic": True}
    elif mutation == "null_programs":
        attack["motion"]["programs"] = None
    elif mutation == "null_observations":
        attack["motion"]["programs"][0]["observations"] = None
    elif mutation == "future_defaults_value":
        program["spriteLayerDefaults"]["texture"] = {"futureBinding": "motion.programs"}
    else:
        program["layers"][0]["tint"] = {"futureBinding": "motion.programs"}
    if stage in {"visual", "vfx"}:
        from infini_local.pipelines.parent_presentation_context import presentation_attack_reference
        assert presentation_attack_reference(attack, stage=stage) == attack
    source["raw"]["directProjectile"]["attackReference"] = attack
    parents = [{"packet": source}] if as_list else {"A": {"packet": source}}
    before = copy.deepcopy(parents)
    result = expand_native_source_references(parent_context_for_stage(parents, stage=stage))
    output = result["parents"][0 if as_list else "A"]["packet"]
    assert output["raw"] == source["raw"]
    renamed = copy.deepcopy(parents)
    renamed[0 if as_list else "A"]["packet"]["name"] = "Unrelated unrelated"
    other = expand_native_source_references(parent_context_for_stage(renamed, stage=stage))
    assert other["parents"][0 if as_list else "A"]["packet"]["raw"] == output["raw"]
    assert parents == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("mutation", ["future_outer", "null_programs", "null_observations",
                                     "future_program", "future_row", "future_coverage", "future_admission"])
def test_unknown_native_source_remains_literal_through_actual_author(monkeypatch, mode, mutation):
    from infini_local.core import llm_config
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    item = _native()
    # Already-produced behavior view isolates the stage boundary from capture
    # projection; unknown sibling references may require the complete draw graph.
    source = unpack_attack_tables(raw_parent_card_for_llm(item)["raw"]["directProjectile"]["attackReference"])
    if mutation == "future_outer":
        source["futureBinding"] = {"sourceRef": "draw.programs[0].definitions.tint1"}
    elif mutation == "null_programs":
        source["motion"]["programs"] = None
    elif mutation == "null_observations":
        source["motion"]["programs"][0]["observations"] = None
    else:
        container = {"future_program": source["motion"]["programs"][0],
                     "future_row": source["motion"]["programs"][0]["observations"][0],
                     "future_coverage": source["coverage"], "future_admission": source["admission"]}[mutation]
        container["futureBinding"] = {"sourceRef": "draw.programs[0].definitions.tint1"}
    item["directProjectileRaw"]["attackReference"] = source
    before = copy.deepcopy(item)
    request, _, _ = build_initial_author_request(item, {}, "unknown-context", model_name="offline")
    dossier = expand_native_source_references(request_dossier(request))
    attack = dossier["parents"]["A"]["packet"]["raw"]["directProjectile"]["attackReference"]
    assert unpack_attack_tables(attack) == source
    assert item == before


def test_visual_vfx_keep_complete_drawing_but_briefs_never_claim_final_palette():
    source = raw_parent_card_for_llm(_native())
    for stage in ("visual", "vfx"):
        context = expand_native_source_references(parent_context_for_stage({"A": {"packet": source}}, stage=stage))
        assert context["parents"]["A"]["packet"] == source
        appearance = context["parentBriefs"]["A"]["appearance"]["directProjectile"]
        assert appearance["sourceRenderKinds"] == ["sprite", "nativeStarSparkle"]
        assert "not final colors" in appearance["scope"]
        assert appearance["sourceColorWrites"][0]["expression"] == "writeRGB(tint1,180,160,60)"


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_real_arrow_selected_motion_and_raw_refusal_reach_actual_author(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    arrow = json.loads((Path(__file__).parent / "fixtures/native_wooden_arrow_parent_capture.json").read_text())
    before = copy.deepcopy(arrow)
    raw = arrow["directProjectileRaw"]["attackReference"]
    native_program = raw["motion"]["programs"][0]
    refusal = "connected_source_dependency_count_bound:193>192"
    assert native_program["coverage"] == "unknown"
    assert native_program["unresolved"] == refusal
    assert native_program["identitySelected"]["identitySelection"]["identityPredicates"] == {
        "Projectile.type": 1, "Projectile.aiStyle": 1}
    request, _, _ = build_initial_author_request({}, arrow, "real-arrow-source", model_name="offline")
    assert request["response_format"]["type"] == mode
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    reference = unpack_attack_tables(dossier["parents"]["B"]["packet"]["raw"]["directProjectile"]["attackReference"])
    program = reference["motion"]["programs"][0]
    assert program["method"] == "T.Projectile.AI_001"
    assert program["identitySelection"]["fullMethodCapture"] == {"coverage": "unknown", "unresolved": refusal}
    assert "motion_source:Terraria.Projectile.AI_001:" + refusal in reference["coverage"]["unresolved"]
    assert "Colliding_identity_dispatch_outside_supported_source_shape" in reference["coverage"]["unresolved"]
    assert "draw_type_dispatch_outside_supported_source_shape" in reference["coverage"]["unresolved"]
    # Exact source equations, not prose keyword checks. Native CPU oracle covers
    # the positive-gravity execution branch; the packet retains both branches.
    assert [row["expression"] for row in program["observations"]] == [
        'stind.r4(ldelema((this).Projectile.ai,0;"System.Single"),(ldind.r4(ldelema((this).Projectile.ai,0;"System.Single"))+1))',
        "stelem.r4((this).Projectile.ai,0,15)",
        "stind.r4(ldflda(Vector2.Y,ldflda(Entity.velocity,this)),(ldind.r4(ldflda(Vector2.Y,ldflda(Entity.velocity,this)))-0.1))",
        "stind.r4(ldflda(Vector2.Y,ldflda(Entity.velocity,this)),(ldind.r4(ldflda(Vector2.Y,ldflda(Entity.velocity,this)))+0.1))",
        "set((this).Projectile.rotation,(conv.r4(Math.Atan2[conv.r8((ldflda(Entity.velocity,this)).Vector2.Y),conv.r8((ldflda(Entity.velocity,this)).Vector2.X)])+1.57))",
        "set((ldflda(Entity.velocity,this)).Vector2.Y,-16)",
        "set((ldflda(Entity.velocity,this)).Vector2.Y,16)",
    ]
    predicates = {row["id"]: row for row in program["predicates"]}
    assert len(predicates) == 7
    assert predicates["b47116"]["inputs"] == ["f32_at((this).Projectile.ai,0)", "15"]
    assert predicates["b47116"]["op"] == "blt.un.s"
    assert predicates["b47132"]["inputs"] == ["d1"]
    assert predicates["b47132"]["successors"] == [47156, 47134]
    assert program["dependencies"]["d1"]["expression"] == "0"
    assert program["observations"][3]["requiredPredicates"] == ["b47116", "b47132"]
    assert predicates["b49427"]["inputs"] == ["(ldflda(Entity.velocity,this)).Vector2.Y", "-16"]
    assert predicates["b49461"]["inputs"] == ["(ldflda(Entity.velocity,this)).Vector2.Y", "16"]
    assert len(program["dependencies"]) == 3
    assert reference == unpack_attack_tables(raw_parent_card_for_llm(arrow)["raw"]["directProjectile"]["attackReference"])
    assert arrow == before
