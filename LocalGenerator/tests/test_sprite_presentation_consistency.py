"""Real imports/Pillow regressions; no model, game, or AST-extracted stand-ins."""
import pytest
from PIL import Image, ImageDraw

from infini_local.pipelines import sprite_contracts as contracts
from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan

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


@pytest.mark.parametrize("canvas", CANVASES)
@pytest.mark.parametrize("role", ("item", "entity_bolt", "equip_overlay"))
def test_plan_to_real_postprocess_preserves_canvas(tmp_path, monkeypatch, canvas, role):
    data = {
        "id": "test", "armor": {"enabled": True, "slot": "head"},
        "visual": {"preferredCanvasSize": canvas},
        "visualKit": {"equipOverlay": {"preferredCanvasSize": canvas}},
        "runtimeProgram": {"itemEntityId": "item", "entities": [
            {"id": "item", "kind": "item_body", "visual": {"assetMode": "baked_sprite"}},
            {"id": "bolt", "kind": "projectile", "hitbox": {"widthPx": canvas, "heightPx": canvas},
             "visual": {"assetMode": "baked_sprite"}},
        ]},
    }
    plan = {row["role"].replace(":", "_"): row for row in build_visual_asset_plan(data)}
    target = plan[role]["canvas"]
    raw = Image.new("RGBA", (160, 160), (255, 0, 255, 255))
    ImageDraw.Draw(raw).rectangle((35, 45, 124, 114), fill=(180, 100, 30, 255))
    source = tmp_path / "raw.png"
    raw.save(source)
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    output = post.postprocess_sprite(str(source), "baked", target, role)
    assert output != str(source), "postprocess must not silently return raw on failure"
    with Image.open(output) as baked:
        assert baked.size == (canvas, canvas)
        assert baked.mode == "RGBA"
        assert baked.getchannel("A").getextrema() == (0, 255)
    assert contracts.sprite_contract_for(role, target)["size"] == canvas


@pytest.mark.parametrize("canvas", CANVASES)
@pytest.mark.parametrize("role", ("item", "entity_bolt", "equip_overlay"))
def test_generation_dispatch_bakes_requested_canvas(tmp_path, monkeypatch, canvas, role):
    from infini_local.pipelines import visual_sprite_generation as generation
    source = tmp_path / "raw_sdcpp.png"
    raw = Image.new("RGBA", (160, 160), (255, 0, 255, 255))
    raw.paste((180, 100, 30, 255), (35, 45, 125, 115))
    raw.save(source)
    # Only the external model boundary is substituted; selection, keying, bake,
    # validation and optional refit are the actual production implementation.
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(generation, "_backend_configuration_error", lambda: "")
    monkeypatch.setattr(generation, "_generate_backend_variants", lambda *args, **kwargs: [str(source)])
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    path, _, _, status = generation.generate_visual_asset({}, role, "copper slab with orange tip", "", "asset", canvas)
    assert path and path != str(source), status
    with Image.open(path) as image:
        assert image.size == (canvas, canvas)
        assert image.getchannel("A").getextrema() == (0, 255)


@pytest.mark.parametrize("canvas", CANVASES)
def test_procedural_canvas_matches_request(tmp_path, canvas):
    from infini_local.services.visual_asset_pipeline import generate_procedural_asset
    path = generate_procedural_asset({}, "item", canvas_size=canvas, sprite_dir=tmp_path,
                                     image_cls=Image, image_draw_cls=ImageDraw)
    with Image.open(path) as image:
        assert image.size == (canvas, canvas)


@pytest.mark.parametrize("canvas", (0, 129, 256))
def test_prompt_manifest_rejects_unsupported_canvas(canvas):
    from infini_local.pipelines import visual_prompt_contracts as prompts
    with pytest.raises(ValueError, match="canvas"):
        prompts.sprite_contract_for("item", canvas)


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


@pytest.mark.parametrize("canvas", (-1, 0, 129, 256))
@pytest.mark.parametrize("operation", ("fit_to_canvas", "bake_sprite_from_master", "prepare_sprite_master"))
def test_unsupported_final_canvas_is_diagnostic(canvas, operation):
    image = Image.new("RGBA", (32, 32))
    args = (image, "test", canvas) if operation == "prepare_sprite_master" else (image, canvas)
    with pytest.raises(ValueError, match="canvas"):
        getattr(post, operation)(*args)
