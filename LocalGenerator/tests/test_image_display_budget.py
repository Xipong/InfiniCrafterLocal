"""Offline image framing at real compile -> Visual -> image/retry boundaries.

Only the external image response is synthetic; builders, selection, Pillow
processing, validation, retry compaction and publication remain production code.
These tests establish prospective prompt transport, not semantic art acceptance.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from infini_local.core import llm_config
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.pipelines import pipeline_visual_config as config
from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.pipelines.visual_prompt_contracts import image_final_frame_prompt_clause, image_generation_prompt_suffix
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _accepted_visual_data(*, long_art: bool = False) -> dict:
    author = build_runtime_fixture("workbench_blade")
    for call in author["runtimeProgram"]["calls"]:
        if call["fn"] == "configure_item_stats":
            call["params"]["scale"] = 1.25
        if call["fn"] == "set_projectile_hitbox":
            call["params"]["drawScale"] = 1.75 if call["target"] == "nail" else 1.5
    data = compile_runtime_program(author)
    item_id = data["runtimeProgram"]["itemEntityId"]
    item_art = "Four short blades around a red glass vial, copper handle and oak brace."
    nail_art = "One wooden arrow, continuous shaft, one steel tip and two feather vanes."
    if long_art:
        item_art = (item_art + " copper engraving" * 130)[:1400]
        nail_art = (nail_art + " oak grain" * 180)[:1400]
    item = dict(prompt=item_art, negativePrompt="", silhouette="four-point body with four short blades",
                visualIdentity="red glass vial, copper handle, oak brace", palette=["red", "copper", "brown"],
                preferredCanvasSize=48, renderSizePx=32, forwardAngleDegrees=45,
                inventoryScale=0.9, worldScale=1.1,
                grip={"normalizedX": 0.3, "normalizedY": 0.72})
    rows = []
    for entity in data["runtimeProgram"]["entities"]:
        if entity["id"] == item_id:
            rows.append(dict(entityId=item_id, assetMode="baked_sprite", visualProjectRef="item",
                             prompt=item_art, silhouette=item["silhouette"], visualIdentity=item["visualIdentity"], scale=1.0))
        elif entity["id"] == "nail":
            rows.append(dict(entityId="nail", assetMode="baked_sprite", visualProjectRef="entity", prompt=nail_art,
                             silhouette="one continuous shaft, one tip, two vanes", visualIdentity="wood, steel, feathers",
                             preferredCanvasSize=32, renderSizePx=22, forwardAngleDegrees=0, scale=0.8))
        else:
            rows.append(dict(entityId=entity["id"], assetMode="reuse_item_icon", visualProjectRef="item", scale=0.75))
    kit, errors = visual._validate_kit(dict(schema=visual.VISUAL_KIT_SCHEMA, item=item, entities=rows,
                                         animationPlan="Follow accepted movement without changing gameplay."),
                                     [row["id"] for row in data["runtimeProgram"]["entities"]], item_id)
    assert kit is not None, errors
    return visual._apply_kit(data, kit)


def _framing(text: str) -> dict:
    marker = "Read-only final-frame facts: "
    assert marker in text, "selected pixel budget must reach the actual backend prompt"
    return json.JSONDecoder().raw_decode(text.split(marker, 1)[1])[0]


def _capture_backend(monkeypatch, tmp_path: Path, *, retries: bool = False) -> list[dict]:
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(generation, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 1 if retries else 0)
    monkeypatch.setattr(generation, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path / "sprites")
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    calls = []

    def offline_response(prompt, negative, asset_id, canvas, *, output_dir=None):
        assert output_dir is not None
        raw = output_dir / (asset_id + "_raw_openai_codex.png")
        image = Image.new("RGBA", (64, 64))
        if retries and output_dir.name == "attempt-0":
            # A tiny nonempty subject produces independent size/opacity failures
            # (an empty PNG short-circuits validation to only empty_alpha_bbox).
            image.paste((170, 90, 40, 255), (32, 32, 34, 34))
        else:
            image.paste((170, 90, 40, 255), (18, 8, 46, 56))
        image.save(raw)
        calls.append(dict(prompt=prompt, negative=negative, canvas=canvas, raw=str(raw), bytes=raw.read_bytes()))
        return [str(raw)]

    monkeypatch.setattr(generation, "generate_openai_codex", offline_response)
    return calls


def test_absent_presentation_stays_absent_and_special_assets_do_not_borrow_root_budget():
    from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt

    data = _accepted_visual_data()
    legacy = copy.deepcopy(data)
    for owner in [legacy["visual"], *[row["visual"] for row in legacy["runtimeProgram"]["entities"]]]:
        owner.pop("renderSizePx", None)
        owner.pop("forwardAngleDegrees", None)
    frozen = copy.deepcopy(legacy)
    for role, entity_id in (("item", ""), ("runtime:child_projectile", "nail")):
        assert "Read-only final-frame facts:" not in normalize_asset_prompt(legacy, role, "literal subject", 32, entity_id=entity_id)
    assert legacy == frozen
    for role in ("impact", "equip_overlay", "vfx_strip", "vfx_cutout"):
        prompt = normalize_asset_prompt(data, role, "literal subject", 32, entity_id="nail")
        assert "Read-only final-frame facts:" not in prompt
        assert '"renderSizePx"' not in prompt and '"grip"' not in prompt
    for mode in ("no_asset", "runtime_geometry"):
        inactive = copy.deepcopy(data)
        inactive["runtimeProgram"]["entities"][2]["visual"]["assetMode"] = mode
        assert not image_final_frame_prompt_clause(inactive, "runtime:child_projectile", 32, entity_id="nail")
    assert not image_final_frame_prompt_clause(data, "runtime:child_projectile", 32, entity_id="unknown")


@pytest.mark.parametrize("style", ["Default", "Terraria Like"])
@pytest.mark.parametrize("zimage", [False, True])
def test_real_retry_compactor_retains_selected_frame_with_long_art_and_png_diagnostics(monkeypatch, tmp_path, style, zimage):
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", style)
    monkeypatch.setattr(post, "image_backend_is_zimage", lambda: zimage)
    monkeypatch.setenv("INFINI_ZIMAGE_RETRY_PROMPT_LIMIT", "2200")
    data = _accepted_visual_data(long_art=True)
    frozen = copy.deepcopy(data)
    calls = _capture_backend(monkeypatch, tmp_path, retries=True)
    result = generation.maybe_generate_visual_assets(data)
    assert len(calls) == 4
    for first, retry, role in ((calls[0], calls[1], "item"), (calls[2], calls[3], "runtime:child_projectile")):
        assert _framing(retry["prompt"]) == _framing(first["prompt"])
        assert "Retain the literal authored silhouette, component count" in retry["prompt"]
        # The tiny PNG went through real postprocess/validation. No hand-written
        # reasons dictionary and no stubbed retry builder can satisfy this case.
        audit = "itemSpriteValidation" if role == "item" else role + "SpriteValidation"
        attempts = json.loads(result["debug"][audit])
        validation = attempts[0]["validation"]
        assert not validation["ok"] and any(reason.startswith("too_few_opaque_pixels") for reason in validation["reasons"])
        assert len(validation["reasons"]) >= 2
        assert post.validation_retry_notes(validation, role)
        assert "Technical correction:" in retry["prompt"] if zimage else "fix these technical issues:" in retry["prompt"]
        framing = image_final_frame_prompt_clause(frozen, role, first["canvas"], entity_id="nail" if role != "item" else "")
        guidance = image_generation_prompt_suffix()
        core = first["prompt"][:-len(guidance)]
        assert core.endswith(framing)
        historical = post.build_retry_prompt_from_validation(core[:-len(framing)] + guidance, validation, role, 1, first["canvas"])
        assert retry["prompt"] == historical[:-len(guidance)] + framing + guidance, "new metadata must not displace or rewrite the historical compacted core"
        from infini_local.services.sdcpp_backend import server_payload
        for call in (first, retry):
            payload = server_payload(config._sdcpp_config(), call["prompt"], "not sent", 512, 512, 42, "a1111", is_zimage=zimage, positive_only=True)
            wire = json.loads(json.dumps(payload, ensure_ascii=False))
            assert _framing(wire["prompt"]) == _framing(call["prompt"])
            assert wire["negative_prompt"] == ""
            assert "Terraria (tModLoader) game asset" in wire["prompt"]
            assert ("Terraria Like art direction" in wire["prompt"]) == (style == "Terraria Like")
        assert Path(first["raw"]).read_bytes() == first["bytes"]
        assert Path(retry["raw"]).read_bytes() == retry["bytes"]
    assert frozen["visual"]["imagePrompt"] in calls[0]["prompt"]
    assert result["visualKit"] == frozen["visualKit"]
    assert result["visual"]["spriteStatus"] == "generated"


@pytest.mark.parametrize("style", ["Default", "Terraria Like"])
def test_prompt_only_mode_preserves_the_same_exact_backend_framing(monkeypatch, tmp_path, style):
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", style)
    data = _accepted_visual_data(long_art=True)
    calls = _capture_backend(monkeypatch, tmp_path)
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "off")
    result = generation.maybe_generate_visual_assets(data)
    assert calls == []
    assert _framing(result["visual"]["finalItemPrompt"])["renderSizePx"] == 32
    assert _framing(result["debug"]["runtime:child_projectileFinalPrompt"])["renderSizePx"] == 22
    assert result["visual"]["spriteStatus"] == "prompt_only"


@pytest.mark.parametrize("style", ["Default", "Terraria Like"])
def test_image_composition_preserves_prospective_grip_and_literal_topology(monkeypatch, tmp_path, style):
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", style)
    data = _accepted_visual_data()
    calls = _capture_backend(monkeypatch, tmp_path)
    result = generation.maybe_generate_visual_assets(data)
    root_prompt, arrow_prompt = (call["prompt"] for call in calls)
    for prompt in (root_prompt, arrow_prompt):
        assert "Retain the literal authored silhouette, component count, spatial arrangement and distinctive elements" in prompt
        assert "Do not omit or merge authored parts to simplify the sprite" in prompt
    assert "visible handle/hand-contact region must contain the declared final-space grip" in root_prompt
    assert "not the guard, blade or empty space" in root_prompt
    assert "not a RAW-image coordinate" in root_prompt
    assert "not a RAW-image coordinate" not in arrow_prompt
    assert result["visual"]["semanticReviewStatus"] == "not_performed"


@pytest.mark.parametrize("style", ["Default", "Terraria Like"])
def test_real_image_jobs_forward_exact_selected_frame_owner_and_multipliers(monkeypatch, tmp_path, style):
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", style)
    data = _accepted_visual_data()
    frozen = copy.deepcopy(data)
    calls = _capture_backend(monkeypatch, tmp_path)
    result = generation.maybe_generate_visual_assets(data)
    assert len(calls) == 2, "reuse_item_icon must not invent a third image job"
    root, arrow = (_framing(call["prompt"]) for call in calls)
    assert root["canvasSizePx"] == 48 and root["renderSizePx"] == 32
    assert root["forwardAngleDegrees"] == 45
    assert root["grip"] == {"normalizedX": 0.3, "normalizedY": 0.72}
    assert root["multipliers"] == {"gameplay.itemScale": 1.25, "visual.inventoryScale": 0.9, "visual.worldScale": 1.1}
    assert root["sharedEntityMultipliers"] == [{"entityId": "workbench_blade", "hitbox.drawScale": 1.5, "visual.scale": 0.75}]
    assert arrow["canvasSizePx"] == 32 and arrow["renderSizePx"] == 22
    assert arrow["entityId"] == "nail" and arrow["forwardAngleDegrees"] == 0
    assert arrow["multipliers"] == {"hitbox.drawScale": 1.75, "visual.scale": 0.8}
    assert "grip" not in arrow and "sharedEntityMultipliers" not in arrow
    assert root["silhouette"] == frozen["visual"]["silhouette"]
    assert arrow["silhouette"] == frozen["runtimeProgram"]["entities"][2]["visual"]["silhouette"]
    for call in calls:
        assert Path(call["raw"]).read_bytes() == call["bytes"]
        assert "R/C" in call["prompt"] and "not hitbox" in call["prompt"]
    assert frozen["visual"]["imagePrompt"] in calls[0]["prompt"]
    assert frozen["runtimeProgram"]["entities"][2]["visual"]["prompt"] in calls[1]["prompt"]
    assert result["gameplay"] == frozen["gameplay"]
    assert result["visualKit"] == frozen["visualKit"]
    assert result["visual"]["semanticReviewStatus"] == "not_performed"
    for entity, before in zip(result["runtimeProgram"]["entities"], frozen["runtimeProgram"]["entities"]):
        assert {key: value for key, value in entity.items() if key != "visual"} == {key: value for key, value in before.items() if key != "visual"}
        for key in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees", "scale", "prompt", "silhouette", "visualIdentity"):
            assert entity["visual"].get(key) == before["visual"].get(key)
    assert result["runtimeProgram"]["entities"][1]["visual"]["spritePath"] == result["visual"]["spritePath"]
    for owner, role in ((result["visual"], "item"), (result["runtimeProgram"]["entities"][2]["visual"], "runtime:child_projectile")):
        assert owner["spriteStatus"] == "generated"
        assert post.validate_processed_sprite(owner["spritePath"], role)["ok"]
