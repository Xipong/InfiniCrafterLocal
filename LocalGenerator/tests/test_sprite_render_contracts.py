"""Offline canonical sprite render contracts; no live services."""
from __future__ import annotations
from prompt_packet_helpers import request_dossier

import pytest
from PIL import Image, ImageDraw
from infini_local.core.images import contracts
from infini_local.pipelines.images import postprocess as post
import infini_local.pipelines.images.pixels as post_pixels
import infini_local.pipelines.images.retry as post_retry
import infini_local.pipelines.images.validation as post_validation
from infini_local.pipelines.visual.assets import build_visual_asset_plan
import copy
from pathlib import Path
from infini_local.pipelines.images import stage as generation
from infini_local.core.runtime_authoring.capability_registry import VISUAL_ROLE_BY_ENTITY_KIND
from infini_local.pipelines.images.prompts import normalize_asset_prompt


CHROMA = {
    "magenta": (255, 0, 255), "green": (0, 255, 0), "lime": (0, 255, 0),
    "greenscreen": (0, 255, 0), "blue": (0, 0, 255), "cyan": (0, 255, 255),
    "white": (255, 255, 255), "black": (0, 0, 0),
}

@pytest.mark.parametrize("name,rgb", CHROMA.items())
def test_chroma_prompt_keyer_and_retry_agree(monkeypatch, name, rgb):
    from infini_local.core.images import config
    from infini_local.pipelines.images import prompts
    from infini_local.pipelines.images import keyer
    monkeypatch.setattr(config, "BG_COLOR", name)
    assert contracts.chroma_rgb() == prompts.chroma_rgb() == keyer.chroma_rgb() == rgb
    authored = "a magenta crystal, cyan rim and white tip"
    data = {"visual": {"palette": ["magenta", "cyan", "white"]}}
    prompt = prompts.normalize_asset_prompt(data, "item", authored, 128)
    assert authored in prompt
    assert data["visual"]["palette"] == ["magenta", "cyan", "white"]
    assert "rgb(%s,%s,%s)" % rgb in prompt
    raw = Image.new("RGBA", (64, 64), (*rgb, 255))
    raw.paste((180, 100, 30, 255), (16, 16, 48, 48))
    cleaned = keyer.apply_background_removal(raw)
    assert cleaned.getpixel((0, 0))[3] == 0
    assert cleaned.getpixel((32, 32)) == (180, 100, 30, 255)
    for zimage in (False, True):
        monkeypatch.setattr(post_retry, "image_backend_is_zimage", lambda: zimage)
        retry = post_retry.build_retry_prompt_from_validation(prompt, {}, "item", 1, 128)
        assert contracts.chroma_name() in retry
        assert authored in retry

# Distinct palette hazards, rather than every color × foreground combination.
@pytest.mark.parametrize("name,rgb,foreground", [
    ("cyan", (0, 255, 255), (255, 0, 255, 255)),
    ("green", (0, 255, 0), (110, 12, 105, 255)),
    ("black", (0, 0, 0), (255, 255, 255, 255)),
])
def test_nonmagenta_keys_preserve_authored_palette(monkeypatch, name, rgb, foreground):
    from infini_local.core.images import config
    from infini_local.pipelines.images import keyer
    monkeypatch.setattr(config, "BG_COLOR", name)
    raw = Image.new("RGBA", (64, 64), (*rgb, 255))
    raw.paste((180, 100, 30, 255), (12, 12, 52, 52))
    raw.paste(foreground, (20, 20, 44, 44))
    profile = keyer.estimate_sprite_key_profile(raw)
    cleaned = keyer.apply_background_removal(raw)
    cleaned = keyer.remove_key_colored_holes(cleaned, profile)
    cleaned = post_pixels.defringe_chroma_edges(cleaned)
    cleaned = post_pixels.neutralize_chroma_edge_colors(cleaned)
    assert cleaned.getpixel((32, 32)) == foreground
    assert cleaned.getpixel((0, 0))[3] == 0

def test_nonmagenta_key_does_not_resample_magenta_art_as_background(monkeypatch):
    from infini_local.core.images import config
    from infini_local.pipelines.images import keyer
    monkeypatch.setattr(config, "BG_COLOR", "cyan")
    raw = Image.new("RGBA", (64, 64), (202, 4, 140, 255))
    assert keyer.estimate_sprite_key_profile(raw)["key"] == (0, 255, 255)

@pytest.mark.parametrize("name", ("chartreuse", ""))
def test_invalid_chroma_is_diagnostic(monkeypatch, name):
    from infini_local.core.images import config
    from infini_local.pipelines.images import prompts
    monkeypatch.setattr(config, "BG_COLOR", name)
    with pytest.raises(ValueError, match="INFINI_BG_COLOR"):
        prompts.normalize_asset_prompt({}, "item", "red crystal", 32)
    with pytest.raises(ValueError, match="INFINI_BG_COLOR"):
        contracts.chroma_rgb()

@pytest.mark.parametrize("color,remove_bg,mode,keyed,repair", [
    ("cyan", True, "sprite_keyer", True, False),
    ("cyan", True, "chroma", True, True),
    ("cyan", False, "sprite_keyer", False, True),
    ("cyan", True, "off", False, False),
    ("transparent", True, "sprite_keyer", False, True),
])
def test_delivered_visual_rules_match_raw_background_transport(monkeypatch, color, remove_bg, mode, keyed, repair):
    import json
    from infini_local.core.images import config
    from infini_local.pipelines.visual import stage as stage
    import infini_local.pipelines.visual.request as stage_request
    from infini_local.pipelines.images import prompts
    monkeypatch.setattr(config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(config, "BG_REMOVE_MODE", mode)
    monkeypatch.setattr(config, "BG_COLOR", color)
    captured = {}
    def transport(request, **kwargs):
        captured.update(request)
        return {"choices": [{"message": {"content": "{}"}}]}
    monkeypatch.setattr(stage_request, "llm_chat_json", transport)
    monkeypatch.setattr(stage_request, "resolve_llm_model", lambda: "test-model")
    stage_request._request_visual_kit({}, {}, {}, repair_errors=[] if repair else None)
    rules = request_dossier(captured)["rules"]
    rule = next((rule for rule in rules if "final PNG" in rule), "")
    assert "transparent background" in rule
    authored = "transparent glass vessel with magenta crystal and white tip"
    prompt = prompts.normalize_asset_prompt({}, "item", authored, 32)
    assert authored in prompt  # no regex rewriting of art text
    if keyed:
        assert "raw image" in rule and "solid rgb(0,255,255)" in rule
        assert "solid rgb(0,255,255)" in prompt
        assert "never request a solid" not in rule
    else:
        assert "solid rgb" not in prompt
        assert "transparent background" in prompt

def test_retry_diagnostic_uses_configured_key(monkeypatch):
    from infini_local.core.images import config
    monkeypatch.setattr(config, "BG_COLOR", "cyan")
    notes = post_retry.validation_retry_notes({"reasons": ["magenta_key_background_left", "almost_no_transparency_after_bg_removal", "very_dense_opaque_area"]}, "item")
    assert "magenta" not in notes
    assert contracts.chroma_name() in notes


@pytest.mark.parametrize("remove_bg", (False, True))
def test_transparent_selects_native_alpha_without_a_chroma_fallback(monkeypatch, remove_bg):
    from infini_local.core.images import config
    from infini_local.pipelines.images import prompts
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(config, "BG_REMOVE_MODE", "sprite_keyer")
    assert not contracts.uses_key_background()
    # Transparency is a policy, never an RGB alias.
    with pytest.raises(ValueError, match="INFINI_BG_COLOR"):
        contracts.chroma_rgb()
    authored = "transparent glass with magenta crystal and white tip"
    for role in ("item", "runtime:projectile", "equip_overlay", "impact", "vfx_cutout", "vfx_strip"):
        assert prompts.sprite_contract_for(role, 32)["background"] == "transparent"
        text = prompts.normalize_asset_prompt({}, role, authored, 32)
        assert authored in text and "transparent background" in text and "solid rgb" not in text
    rule = prompts.visual_background_transport_rule()
    assert "transparent background in the raw image" in rule and "solid rgb" not in rule


def source_image():
    image = Image.new("RGBA", (96, 96), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    for radius in range(34, 0, -1):
        draw.ellipse((48-radius, 48-radius, 48+radius, 48+radius),
                     fill=(35, 130, 225, 20 + (34-radius)*5))
    return image

@pytest.mark.parametrize("role,soft", [("impact", True), ("field", True), ("runtime:field", True),
                                      ("item", False), ("equip_overlay", False), ("runtime:projectile", False)])
def test_full_pipeline_alpha_and_source_preservation(tmp_path, monkeypatch, role, soft):
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", True)
    raw = tmp_path / "pristine.png"
    source_image().save(raw)
    original = raw.read_bytes()
    output = Path(post.postprocess_sprite(str(raw), "result", 32, role))
    assert output != raw
    assert raw.read_bytes() == original
    image = Image.open(output).convert("RGBA")
    assert image.size == (32, 32)
    values = set(image.getchannel("A").tobytes())
    assert bool(values - {0, 255}) == soft
    if soft:
        for stage in ("10_sprite_keyer_fullres", "20_master_norm", "30_baked_final"):
            stage_image = Image.open(tmp_path / f"result_stage_{stage}.png")
            assert set(stage_image.getchannel("A").tobytes()) - {0, 255}
        validation = post_validation.validate_processed_sprite(str(output), role)
        assert validation["ok"], validation
        assert "many_partial_alpha_pixels" not in validation["warnings"]

@pytest.mark.parametrize("remove_bg,role,opaque_first", [(False, "item", False), (True, "impact", False), (True, "vfx_strip", False), (False, "item", True)])
def test_native_alpha_background_bypasses_keying_through_retry_and_saved_png(tmp_path, monkeypatch, remove_bg, role, opaque_first):
    from infini_local.core.images import config
    from infini_local.pipelines.images import keyer
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(config, "BG_REMOVE_MODE", "sprite_keyer")
    image = Image.new("RGBA", (64, 64))
    image.paste((255, 0, 255, 180 if role != "item" else 255), (8, 16, 48, 48))
    image.paste((255, 255, 255, 255), (18, 24, 30, 36))
    assert keyer.apply_background_removal(image).tobytes() == image.tobytes()
    authored = "transparent glass with magenta crystal and white tip"
    validation = {"reasons": ["almost_no_transparency_after_bg_removal", "very_dense_opaque_area"]}
    for zimage in (False, True):
        monkeypatch.setattr(post_retry, "image_backend_is_zimage", lambda: zimage)
        retry = post_retry.build_retry_prompt_from_validation(authored, validation, role, 1, 32)
        assert authored in retry and "transparent background" in retry
        assert "configured key" not in retry and "pure flat" not in retry
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    # Exercise the real producer lifecycle, including a rejected empty first
    # attempt and native-alpha retry. Only the provider response seam is synthetic.
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 1)
    monkeypatch.setattr(generation, "_backend_configuration_error", lambda: "")
    captured = []
    def producer(_data, **kwargs):
        captured.append(kwargs)
        source = kwargs["output_dir"] / "fixture_raw_openai_codex.png"
        supplied = Image.new("RGBA", (64, 64), "white" if opaque_first else (0, 0, 0, 0)) if len(captured) == 1 else image
        supplied.save(source)
        return [str(source)]
    monkeypatch.setattr(generation, "_generate_backend_variants", producer)
    data = {"id": "native-fixture", "vfxManifest": {"recipeId": "native-fixture"}}
    published, _, _, status = generation.generate_visual_asset(data, role, authored, "", "native-producer", 32)
    assert published and status == "generated", data
    assert len(captured) == 2
    assert all(authored in call["prompt"] and "transparent background" in call["prompt"] for call in captured)
    assert post_validation.validate_processed_sprite(published, role)["ok"]
    with Image.open(published) as final:
        assert final.mode == "RGBA" and final.size == (32, 32)
        assert final.getchannel("A").getextrema()[0] == 0
        assert bool(set(final.getchannel("A").tobytes()) - {0, 255}) == (role != "item")
        # Native magenta is authored content, not a key to remove.
        assert any(r == 255 and g == 0 and b == 255 and a > 0 for _, (r, g, b, a) in final.getcolors(maxcolors=32 * 32))
    if role == "vfx_strip":
        with Image.open(published) as final:
            assert final.getchannel("A").getbbox() == (4, 8, 24, 24)


def run_plan(tmp_path, monkeypatch, entity_id, kind, declared=None):
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "image_api")
    monkeypatch.setattr(generation, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(generation, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(generation, "maybe_generate_sprite", lambda data: data)
    monkeypatch.setattr(generation, "write_visual_manifest", lambda *args: None)
    raw = tmp_path / "source.png"
    source_image().save(raw)
    calls = []
    def backend(data, **kwargs):
        calls.append(kwargs)
        return [str(raw)]
    monkeypatch.setattr(generation, "_generate_backend_variants", backend)
    entity = {"id": entity_id, "kind": kind, "visualRole": declared if declared is not None else VISUAL_ROLE_BY_ENTITY_KIND[kind],
              "hitbox": {"widthPx": 32, "heightPx": 32},
              "visual": {"assetMode": "baked_sprite", "prompt": "blue authored shape", "preferredCanvasSize": 32, "renderSizePx": 32, "forwardAngleDegrees": 0}}
    data = {"id": "fixture", "visual": {}, "runtimeProgram": {"entities": [entity]},
            "vfxManifest": {"slots": [{"entityId": entity_id, "rendererKind": "impactSprite"}]}}
    entity["visual"].update(impactPrompt="blue authored impact", impactCanvasSize=32)
    plan = build_visual_asset_plan(copy.deepcopy(data))
    result = generation.maybe_generate_visual_assets(data)
    # Independent body/impact providers may finish in either order.
    calls.sort(key=lambda call: (call["role"] == "impact", call["role"]))
    return plan, result, calls

@pytest.mark.parametrize("kind", [k for k in VISUAL_ROLE_BY_ENTITY_KIND if k != "item_body"])
def test_plan_backend_postprocess_is_independent_of_entity_id(tmp_path, monkeypatch, kind):
    snapshots = []
    for entity_id in ("fire_blade", "frost_cloud_unrelated"):
        plan, result, calls = run_plan(tmp_path, monkeypatch, entity_id, kind)
        assert plan[0]["visualRole"] == VISUAL_ROLE_BY_ENTITY_KIND[kind]
        assert [c["role"] for c in calls] == ["runtime:" + VISUAL_ROLE_BY_ENTITY_KIND[kind], "impact"]
        # Identity is now an explicit final-frame owner fact, never design prose.
        import json
        normalized_prompts = []
        for call in calls:
            prompt = call["prompt"]
            marker = "Read-only final-frame facts: "
            if marker in prompt:
                prefix, framed = prompt.split(marker, 1)
                facts, end = json.JSONDecoder().raw_decode(framed)
                assert facts["entityId"] == entity_id
                facts["entityId"] = "same_explicit_owner"
                prompt = prefix + marker + json.dumps(facts, sort_keys=True) + framed[end:]
            normalized_prompts.append(prompt)
        visual = result["runtimeProgram"]["entities"][0]["visual"]
        assert visual["spritePath"] and visual["impactSpritePath"]
        body = Image.open(visual["spritePath"]).convert("RGBA")
        impact = Image.open(visual["impactSpritePath"]).convert("RGBA")
        assert bool(set(body.getchannel("A").tobytes()) - {0, 255}) == (kind == "field")
        assert set(impact.getchannel("A").tobytes()) - {0, 255}
        snapshots.append((body.tobytes(), impact.tobytes(), normalized_prompts))
    assert snapshots[0] == snapshots[1]

@pytest.mark.parametrize("role", ["impact", "runtime:field"])
def test_soft_policy_preserves_low_alpha_but_rejects_empty(tmp_path, role):
    image = Image.new("RGBA", (32, 32), (35, 130, 225, 1))
    assert post_pixels.cleanup_alpha(image, role).getpixel((0, 0))[3] == 1
    empty = tmp_path / "empty.png"
    Image.new("RGBA", (32, 32)).save(empty)
    validation = post_validation.validate_processed_sprite(str(empty), role)
    assert "empty_alpha_bbox" in validation["reasons"]
    assert post_validation.sprite_validation_fatal(validation)

def test_runtime_projectile_does_not_canonicalize_to_legacy_x():
    image = Image.new("RGBA", (64, 64))
    ImageDraw.Draw(image).rectangle((28, 8, 36, 56), fill=(200, 100, 30, 255))
    output, evidence = post_pixels.canonicalize_projectile_forward_axis(image, "runtime:projectile")
    assert output.tobytes() == image.tobytes()
    assert not evidence["rotated"] and not evidence["flipped"]

def test_mismatched_role_is_not_reinterpreted(tmp_path, monkeypatch):
    _, result, calls = run_plan(tmp_path, monkeypatch, "field_named_body", "free_projectile", "field")
    assert result["runtimeProgram"]["entities"][0]["visual"]["spriteStatus"] == "invalid_runtime_visual_role"
    assert [call["role"] for call in calls] == ["impact"]


# Cover each entry point, plan owner, and supported canvas once; generation
# already executes postprocessing, so their full Cartesian product adds no path.
@pytest.mark.parametrize("canvas,entry,role", [
    (24, "generation", "item"),
    (32, "generation", "entity_bolt"),
    (48, "generation", "equip_overlay"),
    (64, "postprocess", "item"),
    (96, "procedural", "item"),
    (128, "generation", "item"),
])
def test_canvas_consumer_pixels(tmp_path, monkeypatch, canvas, entry, role):
    data = {
        "id": "test", "armor": {"enabled": True, "slot": "head"},
        "visual": {"preferredCanvasSize": canvas}, "visualKit": {"equipOverlay": {"preferredCanvasSize": canvas}},
        "runtimeProgram": {"itemEntityId": "item", "entities": [
            {"id": "item", "kind": "item_body", "visual": {"assetMode": "baked_sprite"}},
            {"id": "bolt", "kind": "projectile", "hitbox": {"widthPx": canvas, "heightPx": canvas}, "visual": {"assetMode": "baked_sprite", "preferredCanvasSize": canvas}},
        ]},
    }
    target = {row["role"].replace(":", "_"): row for row in build_visual_asset_plan(data)}[role]["canvas"]
    source = tmp_path / "raw_sdcpp.png"
    raw = Image.new("RGBA", (160, 160), (255, 0, 255, 255))
    raw.paste((180, 100, 30, 255), (35, 45, 125, 115)); raw.save(source)
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    if entry == "postprocess":
        path = post.postprocess_sprite(str(source), "baked", target, role)
    elif entry == "generation":
        monkeypatch.setattr(generation, "IMAGE_BACKEND", "sdcpp")
        monkeypatch.setattr(generation, "SPRITE_RETRIES", 0)
        monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path)
        monkeypatch.setattr(generation, "_backend_configuration_error", lambda: "")
        monkeypatch.setattr(generation, "_generate_backend_variants", lambda *args, **kwargs: [str(source)])
        path, _, _, status = generation.generate_visual_asset({}, role, "copper slab with orange tip", "", "asset", canvas)
        assert path, status
    else:
        from infini_local.services.visual_asset_pipeline import generate_procedural_asset
        path = generate_procedural_asset({}, "item", canvas_size=canvas, sprite_dir=tmp_path, image_cls=Image, image_draw_cls=ImageDraw)
    assert path != str(source), "consumer returned raw rather than baked pixels"
    with Image.open(path) as image:
        assert image.size == (canvas, canvas)
        if entry != "procedural":
            assert image.mode == "RGBA" and image.getchannel("A").getextrema() == (0, 255)
    assert contracts.sprite_contract_for(role, target)["size"] == canvas

# Owner selection and value validation are independent: retain every invalid
# value, plus each ownership route with its positive and missing-canvas checks.
@pytest.mark.parametrize("owner,value", [
    pytest.param("item", value, id=label + "-item")
    for label, value in (("missing", None), ("bool", True), ("string", "32"), ("float", 32.0), ("unsupported", 33))
] + [pytest.param(owner, None, id="missing-" + owner) for owner in ("reuse", "distinct")])
def test_asset_plan_requires_explicit_image_project_canvas_without_hitbox_fallback(owner, value):
    data = {"visual": {"preferredCanvasSize": 96}, "runtimeProgram": {"itemEntityId": "item", "entities": []}}
    entity = {"id": "item" if owner == "item" else "body", "kind": "item_body" if owner == "item" else "free_projectile",
              "hitbox": {"widthPx": 32, "heightPx": 32},
              "visual": {"assetMode": "reuse_item_icon" if owner == "reuse" else "baked_sprite", "preferredCanvasSize": 64}}
    data["runtimeProgram"]["entities"].append(entity)
    assert build_visual_asset_plan(data)[0]["canvas"] == (64 if owner == "distinct" else 96)
    canvas_owner = entity["visual"] if owner == "distinct" else data["visual"]
    if value is None:
        canvas_owner.pop("preferredCanvasSize")
    else:
        canvas_owner["preferredCanvasSize"] = value
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="explicit supported canvas size required"):
        build_visual_asset_plan(data)
    assert data == before


@pytest.mark.parametrize("root", [None, [], "32", 32, True])
def test_asset_plan_refuses_nonobject_root_visual_for_item_canvas(root):
    data = {"visual": root, "runtimeProgram": {"itemEntityId": "item", "entities": [
        {"id": "item", "kind": "item_body", "hitbox": {"widthPx": 32, "heightPx": 32},
         "visual": {"assetMode": "baked_sprite", "preferredCanvasSize": 64}}]}}
    with pytest.raises(ValueError, match=r"\$\.visual\.preferredCanvasSize"):
        build_visual_asset_plan(data)


@pytest.mark.parametrize("entry,canvas", [
    ("bake_sprite_from_master", -1), ("bake_sprite_from_master", 129),
    ("prepare_sprite_master", 0), ("prepare_sprite_master", 256),
    ("prompt", 0), ("prompt", 129),
])
def test_canvas_boundary_refusal(entry, canvas):
    from infini_local.pipelines.images import prompts
    image = Image.new("RGBA", (32, 32))
    consumer = prompts.sprite_contract_for if entry == "prompt" else getattr(post, entry)
    args = ("item", canvas) if entry == "prompt" else (image, "test", canvas) if entry == "prepare_sprite_master" else (image, canvas)
    with pytest.raises(ValueError, match="canvas"):
        consumer(*args)

@pytest.mark.parametrize("role,present,long", [("item", True, False), ("item", False, False), ("runtime:projectile", True, False), ("item", True, True)])
def test_grip_image_boundary(monkeypatch, role, present, long):
    data = {"visual": {"grip": {"normalizedX": 0.123456789 if role == "item" else 0.2, "normalizedY": 0.8 if role == "item" else 0.7}}} if present else {}
    before = copy.deepcopy(data)
    authored = "brass " * 230 + "red_tip" if long else "brass handle" if not present else "blue mote" if role != "item" else "asymmetric brass handle, red crystal and translucent blue fin"
    assert len(authored) <= 1400
    text = normalize_asset_prompt(data, role, authored, 64)
    assert authored in text and data == before
    if role == "item" and present:
        assert '"normalizedX":0.123456789' in text and '"normalizedY":0.8' in text
        assert "final canvas" in text and "upper-left" in text
    else:
        assert "normalizedX" not in text
    if long:
        captured = []
        monkeypatch.setattr(generation, "IMAGE_BACKEND", "sdcpp")
        monkeypatch.setattr(generation, "SPRITE_RETRIES", 0)
        monkeypatch.setattr(generation, "_backend_configuration_error", lambda: "")
        def capture(_data, **kwargs):
            captured.append(kwargs); return []
        monkeypatch.setattr(generation, "_generate_backend_variants", capture)
        generation.generate_visual_asset(data, "item", authored, "", "grip_probe", 64)
        assert len(captured) == 1
        assert authored in captured[0]["prompt"] and '"normalizedX":0.123456789' in captured[0]["prompt"] and '"normalizedY":0.8' in captured[0]["prompt"]


@pytest.mark.parametrize("canvas", [24, 64, 128])
def test_main_canvas_and_presentation_do_not_leak_to_dedicated_impact(canvas):
    data = {"id": "plan", "visual": {"preferredCanvasSize": 96, "renderSizePx": 40, "forwardAngleDegrees": 45},
        "runtimeProgram": {"itemEntityId": "opaque_root", "entities": [
            {"id": "opaque_root", "kind": "item_body", "visual": {"assetMode": "baked_sprite"}},
            {"id": "opaque_body", "kind": "free_projectile", "visualRole": "projectile", "hitbox": {"widthPx": 21, "heightPx": 21},
             "visual": {"assetMode": "baked_sprite", "preferredCanvasSize": canvas, "renderSizePx": 48, "forwardAngleDegrees": -30, "impactPrompt": "authored impact", "impactCanvasSize": 24}},
            {"id": "alias", "kind": "free_projectile", "visual": {"assetMode": "reuse_item_icon"}},
        ]}, "vfxManifest": {"slots": [{"entityId": "opaque_body", "rendererKind": "impactSprite"}]}}
    before = copy.deepcopy(data)
    plan = {row["role"]: row for row in build_visual_asset_plan(data)}
    assert plan["entity:opaque_body"]["canvas"] == canvas
    assert plan["entity:opaque_body"]["renderSizePx"] == 48
    assert plan["entity:opaque_body"]["forwardAngleDegrees"] == -30
    assert plan["item"]["renderSizePx"] == plan["entity:alias"]["renderSizePx"] == 40
    assert plan["entity:alias"]["canvas"] == 96
    assert plan["entity:alias"]["forwardAngleDegrees"] == 45
    assert plan["entity:alias"]["presentationOwnerEntityId"] == "opaque_root"
    assert plan["impact:opaque_body"]["canvas"] == 24
    assert all(field not in plan["impact:opaque_body"] for field in ("renderSizePx", "forwardAngleDegrees", "presentationOwnerEntityId"))
    assert data == before


def test_fit_refit_samples_retained_master_not_degraded_final(tmp_path):
    # Synthetic narrow physical mark with different adjacent colors. A tiny bake
    # averages those colors; scaling that bake cannot recover the authored detail.
    master = Image.new('RGBA', (96, 96))
    draw = ImageDraw.Draw(master)
    for y in range(36, 64):
        draw.line((40, y, 55, y), fill=((220, 25, 15, 255) if y % 4 < 2 else (230, 190, 30, 255)))
    master_path = tmp_path / 'master.png'
    master.save(master_path)
    final = post_pixels.bake_sprite_from_master(master, 24, 'field')
    path = tmp_path / 'final.png'
    final.save(path)
    validation = generation.validate_processed_sprite(str(path), 'field')
    assert not validation['ok']
    assert any('silhouette_too_small' in reason for reason in validation['reasons'])
    old_path = generation.refit_processed_sprite_to_contract(str(path), 'low', 24, 'field', validation, output_dir=tmp_path)
    new_path = generation.refit_processed_sprite_to_contract(str(path), 'master', 24, 'field', validation,
        output_dir=tmp_path, master_path=master_path)
    old, new = Image.open(old_path), Image.open(new_path)
    assert new.size == old.size == (24, 24)
    assert new.getbbox() == old.getbbox()  # same existing fit; no new layout policy
    assert generation.validate_processed_sprite(new_path, 'field')['ok']
    assert len(new.getcolors(24 * 24)) > len(old.getcolors(24 * 24))
    assert new.tobytes() != old.tobytes()
    # Full-frame VFX UV assets must never take this crop/refit path.
    assert not generation.refit_processed_sprite_to_contract(str(path), 'strip', 24, 'vfx_strip', validation,
        output_dir=tmp_path, master_path=master_path)


def test_postprocess_retains_exact_prebake_master_privately(tmp_path, monkeypatch):
    raw = Image.new('RGBA', (96, 96))
    ImageDraw.Draw(raw).rectangle((30, 20, 65, 75), fill=(160, 50, 20, 255))
    source, master_path = tmp_path / 'raw.png', tmp_path / 'master.png'
    raw.save(source)
    monkeypatch.setattr(post, 'SAVE_SPRITE_STAGES', False)
    final_path = post.postprocess_sprite(str(source), 'synthetic', 24, 'field',
        output_dir=tmp_path, master_output=master_path)
    master = Image.open(master_path)
    assert master.width > 24
    assert Image.open(final_path).tobytes() == post_pixels.bake_sprite_from_master(master, 24, 'field').tobytes()

@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
@pytest.mark.parametrize("role", ["item", "runtime:child_projectile", "vfx_cutout"])
def test_native_alpha_raw_opaque_card_cannot_become_valid_by_padding(tmp_path, monkeypatch, mode, role):
    from infini_local.core.images import config
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    raw = Image.new(mode, (64, 64), "white")
    draw = ImageDraw.Draw(raw)
    for y in range(0, 64, 8):
        for x in range(0, 64, 8):
            if (x // 8 + y // 8) % 2:
                draw.rectangle((x, y, x + 7, y + 7), fill="#bfbfbf")
    draw.line((32, 8, 32, 56), fill="#a08010", width=5)
    source = tmp_path / "raw.png"
    raw.save(source)
    original = source.read_bytes()
    with pytest.raises(post.RawSpriteBackgroundError):
        post.postprocess_sprite(str(source), "opaque-result", 32, role, output_dir=tmp_path)
    assert source.read_bytes() == original
    assert not (tmp_path / "opaque-result.png").exists()


def test_native_alpha_checker_pattern_is_not_a_semantic_rejection(tmp_path, monkeypatch):
    from infini_local.core.images import config
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    raw = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(raw)
    for y in range(8, 56, 8):
        for x in range(8, 56, 8):
            draw.rectangle((x, y, x + 7, y + 7), fill=(200, 200, 200, 255) if (x // 8 + y // 8) % 2 else (255, 255, 255, 255))
    source = tmp_path / "authored-pattern.png"
    raw.save(source)
    result = post.postprocess_sprite(str(source), "pattern-result", 32, "runtime:child_projectile", output_dir=tmp_path)
    assert post_validation.validate_processed_sprite(result, "runtime:child_projectile", expected_canvas=32)["ok"]
