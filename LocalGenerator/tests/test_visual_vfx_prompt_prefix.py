"""Outgoing provider roles, stable instructions and changing accepted recipe facts."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import llm_config, provider_schema
import infini_local.pipelines.vfx.prompt as vfx_prompt
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.pipelines.vfx import request as stage
from infini_local.pipelines.author.request import build_initial_author_request
import infini_local.pipelines.visual.contract as visual_contract
import infini_local.pipelines.visual.request as visual_request
import infini_local.pipelines.visual.stage as visual_stage
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit, _vfx_output, wire_transport


@pytest.mark.parametrize("director,repair,mode", [
    pytest.param("visual", False, "json_schema", id="visual-director-schema"),
    pytest.param("visual", True, "json_object", id="visual-scoped-repair-object"),
    pytest.param("vfx", False, "json_object", id="vfx-director-object"),
    pytest.param("vfx", True, "json_schema", id="vfx-scoped-repair-schema"),
])
def test_provider_instructions_stay_static_while_recipe_and_parent_facts_change(wire_transport, monkeypatch, director, repair, mode):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    responses, sent = wire_transport
    packets = []
    for fixture, width in (("workbench_blade", 40), ("door_on_chain", 73)):
        data = _accepted_visual_data(fixture)
        data["name"] = fixture
        parent = {"id": 1, "name": fixture, "damage": 17, "spriteReferenceRaw": {
            "source": "TextureAssets.Item", "textureWidthPx": width, "textureHeightPx": 68,
            "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": width, "heightPx": 32}}}
        frozen = copy.deepcopy((data, parent))
        responses.append({})
        if director == "visual":
            kwargs = {} if not repair else {
                "repair_errors": [{"path": "$.item.inventoryScale", "message": "invalid"}],
                "previous": {"schema": visual_contract.VISUAL_KIT_SCHEMA, "item": {"inventoryScale": 99}, "entities": []},
                "repair_scope": {"fieldPermissions": {"itemPaths": ["inventoryScale"]}},
            }
            visual_request._request_visual_kit(data, parent, {}, **kwargs)
        else:
            kwargs = {} if not repair else {
                "repair_errors": [{"path": "$.slots[0].alpha", "message": "invalid"}],
                "previous": _vfx_output(data),
                "repair_scope": {"fieldPermissions": {"slots": [{"slotId": "slot_0", "paths": ["alpha"]}]}},
            }
            vfx_stage._request(stage.call_llm_vfx_director, vfx_prompt._prompt_packet(data, parent, {}), **kwargs)
        request = sent[-1]
        assert [row["role"] for row in request["messages"]] == ["system", "developer", "user"]
        assert request["_infini_prompt_cache"] == {"instructionMessageIndex": 1}
        assert request["response_format"]["type"] == mode
        packet = request_dossier(request)
        schema = packet["responseSchema" if director == "visual" else "outputSchema"]
        if mode == "json_schema":
            assert request["response_format"]["json_schema"]["strict"] is True
            expected_wire = schema if director == "visual" else provider_schema._provider_strict_projection(
                provider_schema.defer_provider_cross_field_constraints(schema), omit_annotations=True,
            )
            assert request["response_format"]["json_schema"]["schema"] == expected_wire
        if director == "visual":
            assert packet["itemReadOnly" if repair else "item"]["literalSynthesis"] == data["concept"]["literalSynthesis"]
            parent_reference = (packet["parentSizeReferencesReadOnly"]["parentA"]["spriteReference"] if repair
                                else packet["parents"]["parentA"]["packet"]["raw"]["spriteReference"])
            assert parent_reference == {
                "source": "TextureAssets.Item", "textureWidthPx": width, "textureHeightPx": 68,
                "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": width, "heightPx": 32}}
            context = packet["acceptedPresentationMechanicsReadOnly"]
            assert context["gameplay"]["useTime"] == 24
            assert context["itemUse"] == data["runtimeProgram"]["itemUse"]
            assert packet["spritePresentationReadOnly"]["formulas"]["q"] == "R / max(actual final PNG frame width, height)"
        else:
            assert packet["acceptedGameplayReadOnly"] == data["gameplay"]
            mechanics = copy.deepcopy(data["runtimeProgram"])
            for row in mechanics["entities"]:
                row.pop("visual", None)
            assert packet["acceptedRuntimeProgramReadOnly"] == mechanics
            assert packet["acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"] == data["visualKit"]
            surface = packet["runtimeSurfaceReadOnly" if repair else "runtimeSurface"]
            assert {("item", "on_use"), ("item", "periodic")}.issubset({(row["entityId"], row["event"]) for row in surface["runtimePairs"]})
        if repair:
            assert packet["repairScope"] == kwargs["repair_scope"]
            assert packet["exactErrors"] == kwargs["repair_errors"]
        assert (data, parent) == frozen
        packets.append(packet)
    assert sent[0]["messages"][1]["content"] == sent[1]["messages"][1]["content"]
    assert sent[0]["messages"][2]["content"] != sent[1]["messages"][2]["content"]
    schema_key = "responseSchema" if director == "visual" else "outputSchema"
    if director == "visual" and repair:
        assert packets[0][schema_key] == packets[1][schema_key], "same scalar edit domain does not depend on frozen entity roster"
    else:
        assert packets[0][schema_key] != packets[1][schema_key]
    assert not responses


def test_catalog_revision_reaches_outgoing_instruction_not_recipe_tail(wire_transport, monkeypatch):
    responses, sent = wire_transport
    data = _accepted_visual_data("door_on_chain")
    responses.extend([{}, {}])
    visual_request._request_visual_kit(data, {}, {})
    catalog = copy.deepcopy(visual_request.visual_asset_mode_catalog())
    catalog[0]["runtimeEffect"] += " Explicit catalog revision."
    monkeypatch.setattr(visual_request, "visual_asset_mode_catalog", lambda: catalog)
    visual_request._request_visual_kit(data, {}, {})
    assert sent[0]["messages"][1]["content"] != sent[1]["messages"][1]["content"]
    assert sent[0]["messages"][2]["content"] == sent[1]["messages"][2]["content"]
    assert request_dossier(sent[1])["assetModeCatalog"] == catalog


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_visual_preserves_literal_synthesis_without_promoting_gameplay_intent(wire_transport, monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    responses, sent = wire_transport
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    data.pop("realization", None)
    packets = []
    for synthesis in (" A glass door hangs from a copper chain.\n", "The copper chain forms a handle around the glass door."):
        data["concept"] = {
            "literalSynthesis": synthesis,
            "coreMechanic": "UNREALIZED_GAMEPLAY_INTENT",
            "plannedPlayerActions": [{"input": "alternate_use", "intent": "UNREALIZED_GAMEPLAY_INTENT"}],
        }
        before = copy.deepcopy(data)
        responses.append({})
        visual_request._request_visual_kit(data, {}, {})
        packet = request_dossier(sent[-1])
        assert packet["item"] == {"name": data["name"], "realization": {}, "literalSynthesis": synthesis}
        assert "UNREALIZED_GAMEPLAY_INTENT" not in str(sent[-1]["messages"])
        assert data == before
        packets.append(packet)
    assert sent[0]["messages"][:2] == sent[1]["messages"][:2]
    assert sent[0]["messages"][2]["content"] != sent[1]["messages"][2]["content"]
    assert sent[0]["response_format"] == sent[1]["response_format"]
    assert packets[0]["runtimeEntities"] == packets[1]["runtimeEntities"]
    assert packets[0]["acceptedPresentationMechanicsReadOnly"] == packets[1]["acceptedPresentationMechanicsReadOnly"]
    assert len(sent) == 2 and not responses


@pytest.mark.parametrize("concept", [None, {}, "informal concept", {"literalSynthesis": None},
                                    {"literalSynthesis": 42}, {"literalSynthesis": " \n"}])
def test_visual_does_not_invent_literal_synthesis_from_missing_or_malformed_advisory(wire_transport, concept):
    responses, sent = wire_transport
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    data["concept"] = concept
    before = copy.deepcopy(data)
    responses.append({})
    visual_request._request_visual_kit(data, {}, {})
    assert "literalSynthesis" not in request_dossier(sent[0])["item"]
    assert data == before and not responses


@pytest.mark.parametrize("mirror", [pytest.param(False, id="independent-hitbox"), pytest.param(True, id="explicit-mirroring")])
def test_visual_receives_authored_hitbox_curve_without_selecting_sprite_scale(wire_transport, mirror):
    source = build_capability_witness("hitbox_curve")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "hitbox_curve")
    call["params"].update(startScale=0.25, endScale=8, mirrorToSprite=mirror)
    data = compile_runtime_program(source)
    before = copy.deepcopy(data)
    responses, sent = wire_transport
    responses.append({})
    visual_request._request_visual_kit(data, {}, {})
    packet = request_dossier(sent[0])
    entity = next(row for row in packet["runtimeEntities"] if "hitboxCurve" in row)
    assert entity["hitboxCurve"]["startScale"] == 0.25
    assert entity["hitboxCurve"]["endScale"] == 8
    assert entity["hitboxCurve"]["mirrorToSprite"] is mirror
    assert "q_selected * P" in packet["spritePresentationReadOnly"]["formulas"]["body"]
    assert data == before


@pytest.mark.parametrize("base_flight", [False, True], ids=["attached-line", "moving-line"])
def test_physical_geometry_is_read_only_guidance_and_can_have_no_vfx_slots(wire_transport, base_flight):
    source = build_capability_witness("beam_geometry")
    if not base_flight:
        calls = source["runtimeProgram"]["calls"]
        calls[:] = [call for call in calls if call["fn"] != "move_straight"]
        calls.append({"id": "explicit_anchor", "fn": "attach", "target": "witness_entity",
                      "params": {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0}})
        next(call for call in calls if call["fn"] == "projectile_collision")["params"]["tileCollide"] = False
    next(call for call in source["runtimeProgram"]["calls"]
         if call["fn"] == "beam_geometry")["params"]["length"] = 1.0
    beam = compile_runtime_program(source)
    before = copy.deepcopy(beam)
    raw = _visual_kit(beam)
    body = next(row for row in raw["entities"] if row["entityId"] == "witness_entity")
    body.update(assetMode="runtime_geometry", visualProjectRef="none")
    from tests.visual_geometry_fixtures import segment_geometry
    body["geometry"] = segment_geometry()
    authored = _vfx_output(beam)
    authored["slots"] = []
    responses, sent = wire_transport
    responses.extend([raw, authored])
    projected = visual_stage.apply_visual_director(beam, {}, {})
    packet = request_dossier(sent[0])
    entity = next(row for row in packet["runtimeEntities"] if "beamGeometry" in row)
    assert entity["beamGeometry"]["lengthPx"] == 16.0
    assert entity["beamGeometry"] == before["runtimeProgram"]["entities"][1]["beamGeometry"]
    assert "collision" in entity["modifierMeaningReadOnly"]["beamGeometry"]
    assert bool(entity["movement"]) is base_flight
    assert entity["controller"] == {}
    if not base_flight:
        assert entity["attachment"] == before["runtimeProgram"]["entities"][1]["attachment"]
    final = vfx_stage.attach_vfx_manifest(projected, "beam-geometry", llm_director=stage.call_llm_vfx_director)
    surface = request_dossier(sent[1])["runtimeSurface"]
    assert "beam" in next(row["sources"] for row in surface["texturedPathSources"] if row["entityId"] == "witness_entity")
    assert final["vfxManifest"]["slots"] == []
    assert final["runtimeProgram"]["entities"][1]["visual"]["assetMode"] == "runtime_geometry"
    def mechanics(runtime):
        result = copy.deepcopy(runtime)
        for row in result["entities"]:
            row.pop("visual", None)
        return result
    assert mechanics(final["runtimeProgram"]) == mechanics(before["runtimeProgram"])
    assert final["gameplay"] == before["gameplay"]
    assert not responses


def test_visual_style_changes_advisory_system_only(wire_transport, monkeypatch):
    data = _accepted_visual_data("door_on_chain")
    responses, sent = wire_transport
    responses.extend([{}, {}])
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Default", raising=False)
    visual_request._request_visual_kit(data, {}, {})
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Terraria Like", raising=False)
    visual_request._request_visual_kit(data, {}, {})
    assert "Terraria Like art direction" in sent[1]["messages"][0]["content"]
    assert sent[0]["messages"][1:] == sent[1]["messages"][1:]
    assert sent[0]["response_format"] == sent[1]["response_format"]


def test_invalid_visual_style_is_rejected_by_its_visual_consumer(wire_transport, monkeypatch):
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Unknown", raising=False)
    with pytest.raises(ValueError, match="INFINI_PROMPT_STYLE"):
        visual_request._request_visual_kit(_accepted_visual_data("door_on_chain"), {}, {})
    assert wire_transport[1] == [], "invalid style must fail before provider transport"


def test_generated_parent_visual_calibration_stays_in_visual_tail_not_gameplay(wire_transport):
    parent = {"id": 1, "name": "same proxy", "width": 999, "height": 888,
              "generatedData": {"id": "exact-definition", "gameplay": {"damage": 19},
                                "visual": {"renderSizePx": 47, "preferredCanvasSize": 32, "spritePath": "private.png"},
                                "runtimeProgram": {"entities": [], "bindings": []}}}
    before = copy.deepcopy(parent)
    data = _accepted_visual_data("door_on_chain")
    responses, sent = wire_transport
    responses.extend([{}, {}])
    visual_request._request_visual_kit(data, parent, {})
    parent["generatedData"]["visual"]["renderSizePx"] = 48
    visual_request._request_visual_kit(data, parent, {})
    packets = [request_dossier(request)["parents"]["parentA"]["packet"] for request in sent]
    assert packets[0]["raw"]["generatedParent"]["visual"] == {"renderSizePx": 47, "preferredCanvasSize": 32}
    assert packets[1]["raw"]["generatedParent"]["visual"]["renderSizePx"] == 48
    assert sent[0]["messages"][1]["content"] == sent[1]["messages"][1]["content"]
    assert sent[0]["messages"][2]["content"] != sent[1]["messages"][2]["content"]
    request, _, _ = build_initial_author_request(before, {}, "parent-control", model_name="test-model")
    gameplay = request_dossier(request)["parents"]["A"]["packet"]
    assert gameplay["raw"]["generatedParent"]["gameplay"] == {"damage": 19}
    assert "visual" not in gameplay["raw"]["generatedParent"]
    older = copy.deepcopy(before)
    older["generatedData"]["visual"].pop("renderSizePx")
    assert "renderSizePx" not in raw_parent_card_for_llm(older, include_visual_reference=True)["raw"]["generatedParent"]["visual"]


@pytest.mark.parametrize("defect", ["texture-type", "frame-outside", "unobserved-location"])
def test_parent_reference_never_invents_pixels_from_gameplay_bounds(defect):
    observation = {"source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68,
                   "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": 40, "heightPx": 32}}
    parent = {"id": 1, "name": "literal", "width": 999, "height": 888}
    if defect == "texture-type":
        observation["textureWidthPx"] = True
    elif defect == "frame-outside":
        observation["currentFrame"]["heightPx"] = 69
    if defect == "unobserved-location":
        parent["fingerprint"] = {"spriteReferenceRaw": observation}
    else:
        parent["spriteReferenceRaw"] = observation
    before = copy.deepcopy(parent)
    raw = raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]
    if defect == "frame-outside":
        assert raw["spriteReference"] == {"source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68}
    else:
        assert "spriteReference" not in raw
    assert parent == before


def test_public_visual_schemas_share_owner_catalogs_without_per_token_cases():
    director = visual_contract.visual_response_schema(["item", "body"], True, item_body_id="item")["properties"]
    repair = visual_contract.visual_repair_schema(["item", "body"], True, item_body_id="item")["properties"]
    assert "effectColor" not in director["item"]["properties"]
    assert "effectColor" not in repair["itemPatch"]["anyOf"][0]["properties"]
    assert director["equipOverlay"]["properties"]["accessoryMount"]["enum"] == repair["equipOverlayPatch"]["anyOf"][0]["properties"]["accessoryMount"]["enum"]
    modes = {branch["properties"]["assetMode"]["const"] for branch in director["entities"]["items"]["oneOf"]}
    assert modes == {row["mode"] for row in visual_request.visual_asset_mode_catalog()}


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("fixture_name", ["door_on_chain", "workbench_blade"])
def test_minimal_author_result_preserves_visual_mechanics_and_parent_facts(wire_transport, monkeypatch, mode, fixture_name):
    """Advisory omission changes only optional appearance hints, not Visual's facts."""
    from infini_local.core.runtime_authoring.validator import validate_runtime_program

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    source = build_runtime_fixture(fixture_name)
    minimal = {key: copy.deepcopy(source[key]) for key in ("name", "category", "runtimeProgram")}
    assert validate_runtime_program(minimal)["ok"]
    if mode == "json_schema":
        from jsonschema import Draft202012Validator
        from infini_local.pipelines.author import item_contract as contract
        from test_codex_subscription_contract import _encode_nullable_fixture

        request, _, _ = build_initial_author_request({}, {}, "minimal-visual", model_name="offline")
        local = contract.author_item_response_schema()
        encoded = _encode_nullable_fixture(minimal, local)
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(encoded)
        restored = contract.project_provider_author_item_to_local(encoded, response_format=request["response_format"])
        assert restored == minimal
        minimal = restored
    data = compile_runtime_program(minimal)
    assert "concept" not in data and "realization" not in data
    parents = (
        {"id": 1, "name": "Glass Door", "internalName": "GlassDoor", "sourceMod": "Terraria",
         "fullName": "Terraria/GlassDoor", "width": 16, "height": 32,
         "spriteReferenceRaw": {"source": "TextureAssets.Item", "textureWidthPx": 16, "textureHeightPx": 32}},
        {"id": 2, "name": "Chain", "internalName": "Chain", "sourceMod": "Terraria",
         "fullName": "Terraria/Chain", "width": 12, "height": 18,
         "spriteReferenceRaw": {"source": "TextureAssets.Item", "textureWidthPx": 12, "textureHeightPx": 18}},
    )
    frozen = copy.deepcopy((data, parents))
    responses, sent = wire_transport
    responses.extend([{}, {}])
    visual_request._request_visual_kit(data, *parents)
    visual_request._request_visual_kit(compile_runtime_program(source), *parents)
    packet, advisory_packet = (request_dossier(request) for request in sent)
    assert packet["item"] == {"name": source["name"], "realization": {}}
    assert packet["requiredEntityIds"] == [entity["id"] for entity in data["runtimeProgram"]["entities"]]
    for label, parent in zip(("parentA", "parentB"), parents):
        delivered = packet["parents"][label]["packet"]
        assert delivered["name"] == parent["name"]
        assert delivered["internalName"] == parent["internalName"]
        assert delivered["sourceMod"] == parent["sourceMod"]
        assert delivered["raw"]["crossModIdentity"]["fullName"] == parent["fullName"]
        assert delivered["raw"]["spriteReference"] == parent["spriteReferenceRaw"]
    context = packet["acceptedPresentationMechanicsReadOnly"]
    for field in ("itemEntityId", "primaryEntityId", "primaryOwner", "itemUse", "itemContact", "bindings"):
        if field in data["runtimeProgram"]:
            assert context[field] == data["runtimeProgram"][field]
    assert context["gameplay"]["useTime"] == data["gameplay"]["useTime"]
    for delivered, accepted in zip(packet["runtimeEntities"], data["runtimeProgram"]["entities"]):
        assert delivered["id"] == accepted["id"] and delivered["kind"] == accepted["kind"]
        for field in ("spawn", "lifetimeTicks", "hitbox", "collision", "movement", "controller",
                      "aim", "attachment", "reach", "rotation", "seek", "returnTrigger", "arrival", "ownerControl"):
            if field in accepted:
                assert delivered[field] == accepted[field]
    # Compare the entire delivered dossiers, not just a few selected facts.
    # Only the optional item hints may differ from the advisory-bearing control.
    assert {k: v for k, v in packet.items() if k != "item"} == {
        k: v for k, v in advisory_packet.items() if k != "item"}
    assert sent[0]["messages"][:2] == sent[1]["messages"][:2]
    assert sent[0]["response_format"] == sent[1]["response_format"]
    assert len(sent) == 2 and not responses
    assert (data, parents) == frozen
