"""Offline canonical vfx packet contracts; no live services."""
from __future__ import annotations

import copy
import json
import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines import pipeline_visual_config as config
from infini_local.pipelines import llm_authoring_pipeline as stage
from tests.test_low_level_three_stage_pipeline import _accepted_visual_data, _vfx_output
from tests.test_repair_vfx_contract import _offline_transport
from tests.vfx_material_fixtures import _data, _legacy, _sent, _sprite

_GLOBAL_DESCRIPTIONS = {
    "effectMagnitude": ("no renderer consumer", "metadata"),
}

_MOTIF_DESCRIPTIONS = {
    "rhythm": ("no renderer consumer", "metadata"),
    "chaos": ("no renderer consumer", "metadata"),
}

_SLOT_DESCRIPTIONS = {
    "scale": ("renderer", "projectile.scale", "thickness", "light", "dust"),
    "density": ("projectile", "item", "count", "repeatevery"),
    "duration": ("sprite", "primitive", "world ticks", "fade", "history", "do not consume"),
    "alpha": ("draw", "sound", "dust", "clamp"),
    "spread": ("speed", "not angle", "projectile", "item"),
    "jitter": ("no renderer consumer",),
    "fadeIn": ("no renderer consumer",),
    "fadeOut": ("no renderer consumer",),
    "budgetWeight": ("no renderer consumer",),
    "signatureWeight": ("no renderer consumer",),
    "visualCost": ("no renderer consumer",),
    "startTick": ("projectile", "periodic", "only", "world tick"),
    "repeatEvery": ("periodic", "0", "automatic", "projectile", "item", "world tick"),
}

_EXPECTED_BOUNDS = {
    "scale": ("number", 0.15, 5.0), "density": ("number", 0.0, 1.0),
    "duration": ("integer", 3, 120), "alpha": ("number", 0.0, 1.0),
    "spread": ("number", 0.0, 2.0), "jitter": ("number", 0.0, 1.5),
    "fadeIn": ("number", 0.0, 0.8), "fadeOut": ("number", 0.0, 0.8),
    "budgetWeight": ("number", 0.1, 4.0), "signatureWeight": ("number", 0.0, 1.0),
    "visualCost": ("number", 0.0, 1.0), "startTick": ("integer", 0, 120),
    "repeatEvery": ("integer", 0, 120),
}


def test_numeric_descriptions_leave_keys_bounds_and_decoded_values_unchanged() -> None:
    data = {"runtimeProgram": {"entities": [{
        "id": "item_body", "kind": "item_body", "visualRole": "item",
        "events": [{"event": "periodic"}],
    }]}}
    packet = vfx._prompt_packet(data, None, None)
    normal = packet["outputSchema"]
    repair = vfx._vfx_repair_schema_from_packet(packet)
    standalone_repair = vfx.vfx_repair_schema(data)
    original_slot = normal["properties"]["slots"]["items"]
    repair_slot = repair["properties"]["slotsUpsert"]["items"]
    assert repair_slot == original_slot == standalone_repair["properties"]["slotsUpsert"]["items"]
    assert repair["properties"]["motif"]["anyOf"][0] == normal["properties"]["motif"]
    assert repair["properties"]["effectMagnitude"]["anyOf"][0] == normal["properties"]["effectMagnitude"]
    # Additive payloads/asset requests are conditionally required, never legacy defaults.
    assert set(original_slot["properties"]) - {"element", "path"} == set(original_slot["required"])
    assert set(normal["properties"]) - {"assets"} == set(normal["required"])
    assert packet["runtimeVocabulary"]["numericRanges"] == {
        "effectMagnitude": [0.0, 1.0], "scale": [0.15, 5.0],
        "density": [0.0, 1.0], "duration": [3, 120], "alpha": [0.0, 1.0],
        "spread": [0.0, 2.0], "jitter": [0.0, 1.5], "fadeIn": [0.0, 0.8],
        "fadeOut": [0.0, 0.8], "budgetWeight": [0.1, 4.0],
        "signatureWeight": [0.0, 1.0], "visualCost": [0.0, 1.0],
        "startTick": [0, 120], "repeatEvery": [0, 120],
    }
    pair = packet["runtimeSurface"]["runtimePairs"][0]
    slot = {key: (schema["enum"][0] if "enum" in schema else "") for key, schema in original_slot["properties"].items() if key in original_slot["required"]}
    slot.update({
        "id": "numeric_witness", **pair, "rendererKind": "impactRing",
        "scale": 2.75, "density": 0.36, "duration": 41, "alpha": 0.64,
        "spread": 1.25, "jitter": 0.9, "fadeIn": 0.2, "fadeOut": 0.3,
        "budgetWeight": 1.75, "signatureWeight": 0.44, "visualCost": 0.23,
        "startTick": 19, "repeatEvery": 0,
    })
    authored = {"schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.42,
                "visualBudgetClass": "normal", "motif": {
                    "element": "fire", "shapeLanguage": "ring", "motionLanguage": "outward",
                    "paletteRole": "primary", "rhythm": 1.9, "chaos": 0.73,
                }, "slots": [slot]}
    report = vfx.validate_vfx_director_output(copy.deepcopy(authored), data)
    assert report["ok"], report["errors"]
    assert report["normalized"]["effectMagnitude"] == authored["effectMagnitude"]
    assert report["normalized"]["motif"] == authored["motif"]
    for field in _EXPECTED_BOUNDS:
        assert report["normalized"]["slots"][0][field] == authored["slots"][0][field]

@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("fixture", [
    "workbench_blade", "umbrella_grenade", "door_on_chain", "returning_potion",
    "fishing_platform_tool", "shield_and_disc", "held_and_deployed", "equipment_tool_combat",
])
def test_actual_vfx_packet_contains_exact_read_only_runtime_mechanics(repair, fixture):
    data = _accepted_visual_data(fixture)
    # Compare the actual compiler projection, not a guessed second mechanics DTO.
    entity = data["runtimeProgram"]["entities"][0]
    entity["visual"] = {"spritePath": "private-local-path.png", "prompt": "not mechanical"}
    original = copy.deepcopy(data)
    expected = copy.deepcopy(data["runtimeProgram"])
    for row in expected["entities"]:
        row.pop("visual", None)
    packet = vfx._prompt_packet(data, None, None)
    sent = [_sent(data, repair, packet)]
    vocabulary_key = "runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"
    surface_key = "runtimeSurfaceReadOnly" if repair else "runtimeSurface"
    vocabulary, surface = sent[0][vocabulary_key], sent[0][surface_key]
    assert not (vocabulary.keys() & surface.keys())
    assert json.dumps({**vocabulary, **surface}, sort_keys=True) == json.dumps(vfx.vfx_director_surface(data), sort_keys=True)
    assert vocabulary == _sent({}, repair)[vocabulary_key]
    assert sent[0].get("acceptedRuntimeProgramReadOnly") == expected
    assert "private-local-path.png" not in json.dumps(sent[0])
    assert data == original
    packet["acceptedRuntimeProgramReadOnly"]["entities"][0]["lifetimeTicks"] = 999
    packet["runtimeVocabulary"]["rendererRequirements"]["impactSprite"]["textureRole"] = "none"
    packet["runtimeSurface"]["entityTextureSources"][0]["sources"].append("unrequested")
    assert data == original
    assert vfx.vfx_director_surface(data)["rendererRequirements"]["impactSprite"]["textureRole"] == "impact"

def test_empty_mechanical_context_does_not_invent_entities_or_parameters():
    packet = vfx._prompt_packet({}, None, None)
    assert packet.get("acceptedRuntimeProgramReadOnly") == {}


@pytest.mark.parametrize("capability", ["channel_beam", "move_whip_lash"])
def test_actual_vfx_prefix_keeps_color_opacity_and_dedicated_impact_repair_frozen(monkeypatch, capability):
    prefixes = []
    for color, opacity in (("cyan", 0.25), ("orange", 0.75)):
        data = _data(capability)
        data["visual"] = {"effectColor": color}
        data["visualKit"] = {"item": {"effectColor": color}}
        accepted = _sprite(data)
        accepted["slots"][0]["element"]["opacityProfile"]["middle"] = opacity
        accepted["slots"][0]["element"]["colorProfile"]["middle"] = color
        impact = _legacy(data)["slots"][0]
        impact.update(id="dedicated_impact", rendererKind="impactSprite", textureRole="impact",
                      spritePrompt=f"one dedicated {color} impact sprite", spriteNegativePrompt="no atlas")
        accepted["slots"].append(impact)
        assert vfx.validate_vfx_director_output(accepted, data)["ok"]
        raw = copy.deepcopy(accepted)
        raw["slots"][0]["alpha"] = 2.0
        report = vfx.validate_vfx_director_output(raw, data)
        scope = vfx._build_vfx_repair_scope(raw, report["errors"])
        assert scope["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "ingredient_element", "paths": ["alpha"]}], "assets": []}
        candidate = copy.deepcopy(accepted["slots"][0])
        candidate["element"]["opacityProfile"]["middle"] = 0.0
        candidate["element"]["colorProfile"]["middle"] = "pink"
        hostile_impact = {**impact, "spritePrompt": "unrequested substitute", "textureRole": "item"}
        patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate, hostile_impact], "note": "alpha only"}
        before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
        sent = _offline_transport(monkeypatch, capability + "_" + color, [raw, patch])
        final = vfx.attach_hybrid_vfx_manifest(data, "prefix-" + capability, llm_director=stage.call_llm_vfx_director)
        assert final["debug"]["vfxDirectorRaw"] == accepted
        assert raw == raw_before
        assert final["runtimeProgram"]["entities"][0]["visual"]["impactPrompt"] == impact["spritePrompt"]
        assert final["gameplay"] == before["gameplay"]
        director, repair = [json.loads(request["messages"][1]["content"]) for request in sent]
        assert repair["exactErrors"] == report["errors"][:24]
        assert repair["repairScope"] == scope
        assert repair["brokenFragments"]["slots"] == [raw["slots"][0]]
        assert repair["validGeneratedContext"]["slots"] == [impact]
        assert director["acceptedVisualKit"] == repair["acceptedVisualKitReadOnly"] == before["visualKit"]
        assert director["acceptedRuntimeProgramReadOnly"] == repair["acceptedRuntimeProgramReadOnly"]
        sources = director["runtimeSurface"]["texturedPathSources"]
        assert any(("beam" if capability == "channel_beam" else "whip") in row["sources"] for row in sources)
        for packet, request, keys in ((director, sent[0], vfx.VFX_PROMPT_STATIC_KEYS), (repair, sent[1], vfx.VFX_REPAIR_PROMPT_STATIC_KEYS)):
            length = request["_infini_prompt_cache"]["prefixChars"]
            prefix = json.dumps({key: packet[key] for key in keys}, ensure_ascii=False, separators=(",", ":"))[:-1] + ","
            assert request["messages"][1]["content"][:length] == prefix
        prefixes.append(tuple(request["messages"][1]["content"][:request["_infini_prompt_cache"]["prefixChars"]] for request in sent))
    assert prefixes[0] == prefixes[1]


@pytest.mark.parametrize("repair", [False, True])
def test_serialized_director_and_repair_explain_legacy_png_dependencies(monkeypatch, repair):
    data = _accepted_visual_data("workbench_blade")
    accepted = _vfx_output(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["entityId"] = "missing_entity"
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": accepted["slots"], "note": "retarget only the pair"}
    sent = _offline_transport(monkeypatch, "legacy_png_packet", [raw, patch])
    vfx.attach_hybrid_vfx_manifest(data, "legacy_png_guide", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2
    packet = json.loads(sent[int(repair)]["messages"][1]["content"])
    surface = packet["runtimeSurfaceReadOnly" if repair else "runtimeSurface"]
    slot_schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
    description = slot_schema["properties"]["textureRole"]["description"]
    for renderer in vfx.SPRITE_TEXTURE_RENDERERS:
        assert renderer in description
    for clause in (
        "item=accepted item PNG", "entity=bound entity baked_sprite/reuse_item_icon PNG",
        "no_asset/runtime_geometry cannot supply one", "projectile/field alias entity only when equal to bound visualRole",
        "same mode requirement", "impact=same-entity impactSprite producer", "none invalid for sprites",
        "Primitive/Dust/cue renderer hints require no PNG",
    ):
        assert clause in description, clause
    vocabulary = packet["runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"]
    assert "projectile/field aliases require exact bound visualRole" in vocabulary["textureDependencyTuples"]["entity"]
    assert vocabulary["textureRole"] == slot_schema["properties"]["textureRole"]["enum"]
    sources = {row["entityId"]: row for row in surface["entityTextureSources"]}
    for entity in data["runtimeProgram"]["entities"]:
        assert sources[entity["id"]]["assetMode"] == entity["visual"]["assetMode"]
    assert packet["acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"] == data["visualKit"]

FIELD_CONTRACTS = [("global", field, terms, ("number", 0.0, 1.0), True) for field, terms in _GLOBAL_DESCRIPTIONS.items()]
FIELD_CONTRACTS += [("motif", field, terms, ("number", 0.2, 3.0) if field == "rhythm" else ("number", 0.0, 1.0), True) for field, terms in _MOTIF_DESCRIPTIONS.items()]
FIELD_CONTRACTS += [("slot", field, terms + (("spriteElement", "texturedPath") if field in {"duration", "startTick", "repeatEvery", "alpha"} else ()), _EXPECTED_BOUNDS[field], field not in {"duration", "startTick", "repeatEvery"}) for field, terms in _SLOT_DESCRIPTIONS.items()]
FIELD_CONTRACTS += [("slot", field, ("spriteElement", "texturedPath"), None, False) for field in ("backend", "textureRole")]
_PAYLOAD_FIELDS = _sent(_data(), False)["outputSchema"]["properties"]["slots"]["items"]["properties"]
FIELD_CONTRACTS += [(payload, field, ("profile coordinate",) if field.endswith("Profile") else (), None, False)
                    for payload in ("element", "path") for field, schema in _PAYLOAD_FIELDS[payload]["properties"].items()
                    if schema.get("type") in ("integer", "number") or field.endswith("Profile")]
FIELD_CONTRACTS += [(payload, field + "." + knot, (), None, False)
                    for payload in ("element", "path") for field in _PAYLOAD_FIELDS[payload]["properties"] if field.endswith("Profile") for knot in ("start", "middle", "end")]
FIELD_CONTRACTS += [("element", "inheritVelocity", ("world tick", "extraUpdates", "Player.velocity", "not measured anchor displacement"), None, False)]

@pytest.mark.parametrize("container,field,terms,bounds,engine_units", FIELD_CONTRACTS, ids=[container + "." + field for container, field, *_ in FIELD_CONTRACTS])
@pytest.mark.parametrize("repair", [False, True])
def test_transported_vfx_field_contract(container, field, terms, bounds, engine_units, repair):
    assert set(_SLOT_DESCRIPTIONS) == set(_EXPECTED_BOUNDS)
    output = _sent(_data(), repair)["outputSchema"]["properties"]
    slot = output["slotsUpsert" if repair else "slots"]["items"]["properties"]
    schema = output[field]["anyOf"][0] if container == "global" and repair else output[field] if container == "global" else ((output["motif"]["anyOf"][0] if repair else output["motif"])["properties"][field] if container == "motif" else slot[field] if container == "slot" else slot[container])
    if container in {"element", "path"}:
        for token in field.split("."):
            schema = schema["properties"][token]
    description = schema.get("description", "")
    assert description
    assert all(term.lower() in description.lower() for term in terms), description
    if engine_units: assert "engine units" in description.lower()
    if bounds: assert {key: schema[key] for key in ("type", "minimum", "maximum")} == dict(zip(("type", "minimum", "maximum"), bounds))

@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("color,remove_bg,keyed", [("cyan", False, False), ("cyan", True, True), ("transparent", True, False)])
def test_transported_vfx_presentation_policy(monkeypatch, repair, color, remove_bg, keyed):
    from infini_local.pipelines import pipeline_visual_config as config
    monkeypatch.setattr(config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(config, "BG_REMOVE_MODE", "sprite_keyer")
    monkeypatch.setattr(config, "BG_COLOR", color)
    packet = _sent({}, repair)
    slot = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]["properties"]
    surface = packet["runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"]
    rules = slot["spritePrompt"].get("description", "")
    assert "final impact PNG" in rules and "raw image" in rules
    assert "must request one dedicated transparent impact sprite" not in rules
    if keyed:
        assert "rgb(0,255,255)" in rules
    else:
        assert "transparent background" in rules and "solid rgb" not in rules
    assert "Dust/FNA" in slot["backend"].get("description", "")
    particles = slot["particleSystemId"].get("description", "")
    assert "Terraria dust" in particles and "not" in particles and "ParticleLibrary" in particles
    assert "effectColor" in surface["colorPolicy"] and "legacy" in surface["colorPolicy"]
    semantics = surface["rendererSemantics"]
    assert set(semantics) == set(surface["rendererKind"])
    assert "wave" in semantics["wavyStrip"] and "motes" in semantics["orbitingMotes"]
    assert "120" in semantics["ghostArc"] and "tip" in semantics["tipTrail"]
    assert semantics == vfx._prompt_packet({}, None, None)["runtimeVocabulary"]["rendererSemantics"]
    if repair:
        assert any("deletePaths" in rule and "omissions" in rule for rule in packet["rules"])
    else:
        assert all(rule.startswith("Legacy ") for rule in packet["rules"] if "Procedural phase" in rule or "Sprite renderers require" in rule)
        assert any("spriteElement and texturedPath" in rule and "nested texture" in rule for rule in packet["rules"])
