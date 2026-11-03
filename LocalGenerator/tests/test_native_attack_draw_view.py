"""Readable native render layers retain appearance, ordering and bindings."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.pipelines.context.attack_behavior import _program, project_attack_behavior
from infini_local.pipelines.context.attack_draw import project_draw_layers
from infini_local.pipelines.context.attack_expressions import compact_attack_expressions
from infini_local.pipelines.context.parents import compact_projectile_profile


def captured():
    parent = json.loads((Path(__file__).parent / "fixtures" / "native_excalibur_parent_capture.json").read_text())
    source = parent["directProjectileRaw"]["attackReference"]
    compact = compact_attack_expressions(source)
    original = compact["draw"]["programs"][0]
    return parent, source, original, _program(original), compact["sourceMethods"]


def test_real_draw_has_named_layers_palette_fade_and_exact_ordered_mutations():
    parent, source, original, model, certs = captured()
    before = copy.deepcopy((parent, original, model, certs))
    result = project_draw_layers(original, model, certs)
    assert result is not None
    assert [layer["kind"] for layer in result["layers"]] == ["sprite"] * 7 + ["nativeStarSparkle"] * 2
    assert [layer["step"] for layer in result["layers"]] == [18, 29, 30, 31, 33, 35, 37, 43, 48]
    assert result["spriteLayerDefaults"] == {"texture": "textureAsset", "position": "position", "origin": "origin",
                                           "effects": "effects", "layerDepth": "0", "renderer": "@Main.spriteBatch"}
    definitions = result["definitions"]
    assert definitions["position"]["expression"] == "Vector2.sub[Entity.get_Center[proj],@Main.screenPosition]"
    assert definitions["spriteScale"]["expression"] == "((proj).Projectile.scale*1.1)"
    assert definitions["frameRect"]["expression"] == "frame(textureAsset,columns=1,rows=4,x=0,y=0,offsetX=0,offsetY=0)"
    assert definitions["tint1"]["orderedSourceUses"] == [
        {"block": 93, "expression": "writeRGB(tint1,180,160,60)", "requiredPredicates": [], "step": 17}]
    assert definitions["fade"]["expression"] == "(Utils.Remap[fadeInput,0,0.6,0,1,1]*Utils.Remap[fadeInput,0.6,1,1,0,1])"
    assert definitions["fade"]["step"] == 9
    assert definitions["fadeInput"]["expression"] == "(f32_at((proj).Projectile.localAI,0)/f32_at((proj).Projectile.ai,1))"
    assert definitions["fadeInput"]["step"] == 8
    assert result["layers"][6]["tint"] == "((rgba.white*0.4)*fade)"
    assert result["layers"][6]["scale"] == "(spriteScale*0.6)"
    assert result["layers"][6]["frame"] == "frame(textureAsset,columns=1,rows=4,x=0,y=3,offsetX=0,offsetY=0)"
    assert result["layers"][7]["requiredPredicates"] == ["b1286"]
    assert result["layers"][7]["fadeInStart"] == "0"
    assert result["layers"][7]["fadeOutEnd"] == "1"
    # Addressed per-channel changes are not replaced by an invented scalar tint.
    assert [use["step"] for use in definitions["d17"]["orderedSourceUses"]] == [24, 25, 26, 27, 28]
    assert definitions["d17"]["orderedSourceUses"][-1]["expression"] == "Color.set_B[d17,conv.u1((conv.r4(Color.get_R[d17])*(0.25+(d4*0.75))))]"
    # Non-duplicate factory evaluations retain their separate source points.
    assert [setup["step"] for setup in result["setup"]] == [2, 32, 34, 36, 42, 47]
    assert result["conditions"][1]["successors"] == [1011, 1291]
    assert "symbols" not in result
    assert (parent, original, model, certs) == before


@pytest.mark.parametrize("mutation", ["module", "hash", "signature", "unknown_call", "unknown_field", "unknown_expression"])
def test_unrecognized_renderer_source_or_certificate_keeps_current_source_view(mutation):
    _, _, original, model, certs = captured()
    if mutation == "module":
        original["sourceModuleVersionId"] = "unverified-module"
    elif mutation == "hash":
        original["sourceMethodSha256"] = "other-source"
    elif mutation == "signature":
        model["symbols"]["SpriteBatch.Draw"] = model["symbols"]["SpriteBatch.Draw"].replace("XnaGfx.SpriteBatch", "Other.SpriteBatch")
    elif mutation == "unknown_call":
        model["observations"][2]["call"] = "Custom.Draw"
    elif mutation == "unknown_field":
        model["observations"][2]["newMechanic"] = True
    else:
        model["observations"][2]["arguments"]["position"] = "future unsupported syntax"
    before = copy.deepcopy((original, model, certs))
    assert project_draw_layers(original, model, certs) is None
    assert (original, model, certs) == before


def test_renderer_name_is_not_a_preset_and_changed_tint_is_preserved():
    _, _, original, model, certs = captured()
    old = original["method"]
    original["method"] = model["method"] = "T.Main.UnrelatedNativeRenderer"
    for cert in certs:
        if cert["method"] == old:
            cert["method"] = original["method"]
    model["observations"][13]["arguments"]["color"] = "((rgba.white*0.37)*d10)"
    result = project_draw_layers(original, model, certs)
    assert result["method"] == "T.Main.UnrelatedNativeRenderer"
    assert result["layers"][6]["tint"] == "((rgba.white*0.37)*fade)"


def test_nonmatching_constructor_write_keeps_setup_and_non_envelope_keeps_local_name():
    _, _, original, model, certs = captured()
    model["dependencies"]["d1"]["orderedSourceUses"][0]["step"] = 16
    model["dependencies"]["d10"]["expression"] = "(d11*0.4)"
    result = project_draw_layers(original, model, certs)
    assert any(row["step"] == 17 and row["expression"] == "writeRGB(tint1,180,160,60)" for row in result["setup"])
    assert "fade" not in result["definitions"]
    assert result["layers"][6]["tint"] == "((rgba.white*0.4)*d10)"


def test_semantic_layers_remain_named_in_actual_parent_transport_and_raw_is_unchanged():
    parent, source, _, _, _ = captured()
    before = copy.deepcopy(parent)
    attack = compact_projectile_profile(parent["directProjectileRaw"])["attackReference"]
    draw = attack.get("data", attack)["draw"]["programs"][0]
    assert draw["renderLayerView"]["version"] == 1
    assert isinstance(draw["layers"], list)
    assert draw["layers"][6]["tint"] == "((rgba.white*0.4)*fade)"
    assert "$table" not in json.dumps(draw)
    assert project_attack_behavior(source)["draw"]["programs"][0]["layers"] == draw["layers"]
    assert parent == before


@pytest.mark.parametrize("with_symbol", [False, True])
def test_unknown_nested_expression_api_retains_its_full_symbolic_source(with_symbol):
    _, _, original, model, certs = captured()
    model["observations"][2]["arguments"]["color"] = "Unknown.Paint[d0]"
    if with_symbol:
        model["symbols"]["Unknown.Paint"] = "Other.Paint(Texture)"
    assert project_draw_layers(original, model, certs) is None


def test_constructor_dedupe_preserves_duplicate_observation_multiplicity():
    _, _, original, model, certs = captured()
    model["observations"].insert(2, copy.deepcopy(model["observations"][1]))
    result = project_draw_layers(original, model, certs)
    remaining = [row for row in result["setup"] if row["step"] == 17]
    assert len(remaining) == 1
    assert remaining[0]["expression"] == "writeRGB(tint1,180,160,60)"


@pytest.mark.parametrize("certificates", [None, {}, "unknown-roster"])
def test_unknown_certificate_roster_is_not_a_parent_projection_crash(certificates):
    _, _, original, model, _ = captured()
    assert project_draw_layers(original, model, certificates) is None
