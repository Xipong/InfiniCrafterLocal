"""Offline canonical sprite render contracts; no live services."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw
from infini_local.pipelines import sprite_contracts as contracts
from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
import copy
from pathlib import Path
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.core.runtime_authoring.capability_registry import VISUAL_ROLE_BY_ENTITY_KIND
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt


CANVASES = (24, 32, 48, 64, 96, 128)

CHROMA = {
    "magenta": (255, 0, 255), "green": (0, 255, 0), "lime": (0, 255, 0),
    "greenscreen": (0, 255, 0), "blue": (0, 0, 255), "cyan": (0, 255, 255),
    "white": (255, 255, 255), "black": (0, 0, 0),
}

@pytest.mark.parametrize("name,rgb", CHROMA.items())
def test_chroma_prompt_keyer_and_retry_agree(monkeypatch, name, rgb):
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines import visual_prompt_contracts as prompts
    from infini_local.pipelines import sprite_keyer as keyer
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
        monkeypatch.setattr(post, "image_backend_is_zimage", lambda: zimage)
        retry = post.build_retry_prompt_from_validation(prompt, {}, "item", 1, 128)
        assert contracts.chroma_name() in retry
        assert authored in retry

@pytest.mark.parametrize("name,rgb", [(name, rgb) for name, rgb in CHROMA.items() if name != "magenta"])
@pytest.mark.parametrize("foreground", ((255, 0, 255, 255), (110, 12, 105, 255), (255, 255, 255, 255)))
def test_nonmagenta_keys_preserve_authored_palette(monkeypatch, name, rgb, foreground):
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines import sprite_keyer as keyer
    monkeypatch.setattr(config, "BG_COLOR", name)
    raw = Image.new("RGBA", (64, 64), (*rgb, 255))
    raw.paste((180, 100, 30, 255), (12, 12, 52, 52))
    raw.paste(foreground, (20, 20, 44, 44))
    profile = keyer.estimate_sprite_key_profile(raw)
    cleaned = keyer.apply_background_removal(raw)
    cleaned = keyer.remove_key_colored_holes(cleaned, profile)
    cleaned = post.defringe_chroma_edges(cleaned)
    cleaned = post.neutralize_chroma_edge_colors(cleaned)
    assert cleaned.getpixel((32, 32)) == foreground
    assert cleaned.getpixel((0, 0))[3] == 0

def test_nonmagenta_key_does_not_resample_magenta_art_as_background(monkeypatch):
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines import sprite_keyer as keyer
    monkeypatch.setattr(config, "BG_COLOR", "cyan")
    raw = Image.new("RGBA", (64, 64), (202, 4, 140, 255))
    assert keyer.estimate_sprite_key_profile(raw)["key"] == (0, 255, 255)

@pytest.mark.parametrize("name", ("chartreuse", "transparent", "", "#ff00ff"))
def test_invalid_chroma_is_diagnostic(monkeypatch, name):
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines import visual_prompt_contracts as prompts
    monkeypatch.setattr(config, "BG_COLOR", name)
    with pytest.raises(ValueError, match="INFINI_BG_COLOR"):
        prompts.normalize_asset_prompt({}, "item", "red crystal", 32)
    with pytest.raises(ValueError, match="INFINI_BG_COLOR"):
        contracts.chroma_rgb()

@pytest.mark.parametrize("remove_bg,mode,keyed", ((True, "sprite_keyer", True), (True, "chroma", True), (False, "sprite_keyer", False), (True, "off", False)))
@pytest.mark.parametrize("repair", (False, True))
def test_delivered_visual_rules_match_raw_background_transport(monkeypatch, remove_bg, mode, keyed, repair):
    import json
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines import visual_generation_pipeline as stage
    from infini_local.pipelines import visual_prompt_contracts as prompts
    monkeypatch.setattr(config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(config, "BG_REMOVE_MODE", mode)
    monkeypatch.setattr(config, "BG_COLOR", "cyan")
    captured = {}
    def transport(request, **kwargs):
        captured.update(request)
        return {"choices": [{"message": {"content": "{}"}}]}
    monkeypatch.setattr(stage, "llm_chat_json", transport)
    monkeypatch.setattr(stage, "resolve_llm_model", lambda: "test-model")
    stage._request_visual_kit({}, {}, {}, {}, {}, repair_errors=[] if repair else None)
    rules = json.loads(captured["messages"][1]["content"])["rules"]
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
    from infini_local.pipelines import pipeline_visual_config as config
    monkeypatch.setattr(config, "BG_COLOR", "cyan")
    notes = post.validation_retry_notes({"reasons": ["magenta_key_background_left", "almost_no_transparency_after_bg_removal", "very_dense_opaque_area"]}, "item")
    assert "magenta" not in notes
    assert contracts.chroma_name() in notes

@pytest.mark.parametrize("size", ((64, 32), (32, 64), (64, 64)))
@pytest.mark.parametrize("position", ("center", "offcenter", "empty"))
def test_rectangular_normalized_centers(size, position):
    from infini_local.pipelines.sprite_geometry import sprite_bbox_stats
    w, h = size
    image = Image.new("RGBA", size)
    if position == "center":
        box, expected = (w // 4, h // 4, w * 3 // 4, h * 3 // 4), (0.5, 0.5)
    elif position == "offcenter":
        box, expected = (0, 0, w // 2, h // 2), (0.25, 0.25)
    else:
        box, expected = None, (0.0, 0.0)
    if box:
        image.paste((180, 100, 30, 255), box)
    stats = sprite_bbox_stats(image)
    assert stats["core_center_norm"] == expected
    assert stats["effect_center_norm"] == expected


def test_native_alpha_manifest_does_not_claim_chroma(monkeypatch):
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines import visual_prompt_contracts as prompts
    monkeypatch.setattr(config, "REMOVE_BG", False)
    assert prompts.sprite_contract_for("item", 128)["background"] == "transparent"

@pytest.mark.parametrize("canvas", CANVASES)
@pytest.mark.parametrize("empty", (False, True))
def test_fit_and_master_bake_canvas(canvas, empty):
    raw = Image.new("RGBA", (64, 32))
    if not empty:
        ImageDraw.Draw(raw).rectangle((16, 8, 47, 23), fill=(180, 100, 30, 255))
    assert post.fit_to_canvas(raw, canvas, "impact").size == (canvas, canvas)
    master = post.prepare_sprite_master(raw, "test", canvas, "impact")
    assert post.bake_sprite_from_master(master, canvas, "impact").size == (canvas, canvas)


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
        validation = post.validate_processed_sprite(str(output), role)
        assert validation["ok"], validation
        assert "many_partial_alpha_pixels" not in validation["warnings"]

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
              "visual": {"assetMode": "baked_sprite", "prompt": "blue authored shape"}}
    data = {"id": "fixture", "runtimeProgram": {"entities": [entity]},
            "vfxManifest": {"slots": [{"entityId": entity_id, "rendererKind": "impactSprite"}]}}
    entity["visual"]["impactPrompt"] = "blue authored impact"
    plan = build_visual_asset_plan(copy.deepcopy(data))
    result = generation.maybe_generate_visual_assets(data)
    return plan, result, calls

@pytest.mark.parametrize("kind", [k for k in VISUAL_ROLE_BY_ENTITY_KIND if k != "item_body"])
def test_plan_backend_postprocess_is_independent_of_entity_id(tmp_path, monkeypatch, kind):
    snapshots = []
    for entity_id in ("fire_blade", "frost_cloud_unrelated"):
        plan, result, calls = run_plan(tmp_path, monkeypatch, entity_id, kind)
        assert plan[0]["visualRole"] == VISUAL_ROLE_BY_ENTITY_KIND[kind]
        assert [c["role"] for c in calls] == ["runtime:" + VISUAL_ROLE_BY_ENTITY_KIND[kind], "impact"]
        assert all(entity_id not in c["prompt"] for c in calls)
        visual = result["runtimeProgram"]["entities"][0]["visual"]
        assert visual["spritePath"] and visual["impactSpritePath"]
        body = Image.open(visual["spritePath"]).convert("RGBA")
        impact = Image.open(visual["impactSpritePath"]).convert("RGBA")
        assert bool(set(body.getchannel("A").tobytes()) - {0, 255}) == (kind == "field")
        assert set(impact.getchannel("A").tobytes()) - {0, 255}
        snapshots.append((body.tobytes(), impact.tobytes(), [c["prompt"] for c in calls]))
    assert snapshots[0] == snapshots[1]

@pytest.mark.parametrize("role", ["impact", "runtime:field"])
def test_soft_policy_preserves_low_alpha_but_rejects_empty(tmp_path, role):
    image = Image.new("RGBA", (32, 32), (35, 130, 225, 1))
    assert post.cleanup_alpha(image, role).getpixel((0, 0))[3] == 1
    empty = tmp_path / "empty.png"
    Image.new("RGBA", (32, 32)).save(empty)
    validation = post.validate_processed_sprite(str(empty), role)
    assert "empty_alpha_bbox" in validation["reasons"]
    assert post.sprite_validation_fatal(validation)

def test_runtime_projectile_does_not_canonicalize_to_legacy_x():
    image = Image.new("RGBA", (64, 64))
    ImageDraw.Draw(image).rectangle((28, 8, 36, 56), fill=(200, 100, 30, 255))
    output, evidence = post.canonicalize_projectile_forward_axis(image, "runtime:projectile")
    assert output.tobytes() == image.tobytes()
    assert not evidence["rotated"] and not evidence["flipped"]

def test_mismatched_role_is_not_reinterpreted(tmp_path, monkeypatch):
    _, result, calls = run_plan(tmp_path, monkeypatch, "field_named_body", "free_projectile", "field")
    assert result["runtimeProgram"]["entities"][0]["visual"]["spriteStatus"] == "invalid_runtime_visual_role"
    assert [call["role"] for call in calls] == ["impact"]


CANVAS_CONSUMERS = [(entry, role) for entry in ("postprocess", "generation")
                    for role in ("item", "entity_bolt", "equip_overlay")] + [("procedural", "item")]

@pytest.mark.parametrize("canvas", CANVASES)
@pytest.mark.parametrize("entry,role", CANVAS_CONSUMERS)
def test_canvas_consumer_pixels(tmp_path, monkeypatch, canvas, entry, role):
    data = {
        "id": "test", "armor": {"enabled": True, "slot": "head"},
        "visual": {"preferredCanvasSize": canvas}, "visualKit": {"equipOverlay": {"preferredCanvasSize": canvas}},
        "runtimeProgram": {"itemEntityId": "item", "entities": [
            {"id": "item", "kind": "item_body", "visual": {"assetMode": "baked_sprite"}},
            {"id": "bolt", "kind": "projectile", "hitbox": {"widthPx": canvas, "heightPx": canvas}, "visual": {"assetMode": "baked_sprite"}},
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

INVALID_CANVASES = [(entry, canvas) for entry in ("fit_to_canvas", "bake_sprite_from_master", "prepare_sprite_master") for canvas in (-1, 0, 129, 256)] + [("prompt", canvas) for canvas in (0, 129, 256)]

@pytest.mark.parametrize("entry,canvas", INVALID_CANVASES)
def test_canvas_boundary_refusal(entry, canvas):
    from infini_local.pipelines import visual_prompt_contracts as prompts
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
