"""Offline wearable facts through accepted Visual -> image jobs -> adapter HTTP.

Only image-provider responses are synthetic; prompt assembly, retry compaction,
postprocess, validation and publication use the production path.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from infini_local.pipelines import image_backend_pipeline as backend
from infini_local.pipelines import pipeline_visual_config as config
from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.pipelines.visual_prompt_contracts import image_final_frame_prompt_clause, normalize_asset_prompt
from test_image_attempt_contracts import Response, offline, png


def _accepted_equipment(slot: str = "accessory", *, mount: str | None = None, long_art: bool = False) -> dict:
    data = {
        "id": "wearable_facts_probe", "name": "Misleading leg armor helmet necklace", "category": "weapon",
        "armor": {"enabled": slot != "accessory", "slot": slot},
        "accessory": {"enabled": slot == "accessory"},
        "runtimeProgram": {"itemEntityId": "item", "entities": [
            {"id": "item", "kind": "item_body", "visualRole": "inventory_item", "visual": {}},
        ]},
    }
    overlay = {
        "prompt": "An isolated copper wearable with amber inlay.",
        "silhouette": "Two unequal curved prongs surrounding three separate square windows.",
        "visualIdentity": "Ivory dots on the left prong; violet enamel only on the right prong.",
        "preferredCanvasSize": 48,
    }
    if mount is not None:
        overlay["accessoryMount"] = mount
    if long_art:
        overlay["prompt"] = (overlay["prompt"] + " copper engraving" * 100)[:1400]
        for field, words, end in (("silhouette", " unequal curved prongs", "SILHOUETTE_END"),
                                  ("visualIdentity", " ivory and violet enamel", "IDENTITY_END")):
            overlay[field] = (overlay[field] + words * 40)[:700 - len(end)] + end
            assert len(overlay[field]) == 700
    kit, errors = visual._validate_kit({
        "schema": visual.VISUAL_KIT_SCHEMA,
        "item": {
            "prompt": "A distinct plain inventory pebble.", "negativePrompt": "authored exclusion: red ribbon",
            "silhouette": "one inventory-only oval", "visualIdentity": "inventory-only blue spot", "palette": ["blue"],
            "preferredCanvasSize": 32, "renderSizePx": 40, "forwardAngleDegrees": 45,
            "inventoryScale": 1.0, "worldScale": 1.0,
            "grip": {"normalizedX": 0.3, "normalizedY": 0.7},
        },
        "equipOverlay": overlay,
        "entities": [{"entityId": "item", "assetMode": "baked_sprite", "visualProjectRef": "item", "scale": 1.0}],
        "animationPlan": "Follow accepted movement only.",
    }, ["item"], "item", equipment_overlay_required=True)
    assert kit is not None, errors
    return visual._apply_kit(data, kit)


def _facts(prompt: str) -> dict:
    marker = "Read-only equipment overlay facts: "
    assert marker in prompt, "the actual image adapter request lost the overlay design"
    return json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])[0]


@pytest.mark.parametrize("slot,fit,body_part", [("head", 25, "head"), ("body", 31, "torso"), ("legs", 27, "legs"), ("accessory", 18, "body")])
def test_actual_adapter_receives_overlay_design_and_exact_slot_fit(offline, monkeypatch, slot, fit, body_part):
    _root, requests = offline
    monkeypatch.setattr(config, "ZIMAGE_POSITIVE_ONLY", False)
    data = _accepted_equipment(slot, mount="shoulder")
    frozen = copy.deepcopy(data)

    result = generation.maybe_generate_visual_assets(data)

    assert len(requests) == 2
    item_request, overlay_request = (row["payload"] for row in requests)
    authored = frozen["visualKit"]["equipOverlay"]
    expected = {
        "equipmentSlot": slot, "canvasSizePx": 48, "wholeTextureFitMaxPx": fit,
        "silhouette": authored["silhouette"], "visualIdentity": authored["visualIdentity"],
    }
    if slot == "accessory":
        expected["accessoryMount"] = "shoulder"
    assert _facts(overlay_request["prompt"]) == expected
    assert authored["prompt"] in overlay_request["prompt"]
    assert overlay_request["negative_prompt"] == frozen["visualKit"]["item"]["negativePrompt"]
    assert f"attached to the player's {body_part}" in overlay_request["prompt"]
    assert "fits the whole final PNG" in overlay_request["prompt"]
    assert "visible silhouette smaller" in overlay_request["prompt"]
    for foreign in ("inventory-only", '"renderSizePx"', '"grip"'):
        assert foreign not in overlay_request["prompt"]
    assert "Read-only equipment overlay facts:" not in item_request["prompt"]
    assert result["visualKit"] == frozen["visualKit"]
    assert result["armor"] == frozen["armor"] and result["accessory"] == frozen["accessory"]
    assert result["visual"]["equipOverlayStatus"] == "generated"
    assert Path(result["visual"]["equipOverlayPath"]).is_file()


@pytest.mark.parametrize("mount", [None, "chest", "back", "waist", "shoulder", "orbit"])
def test_all_explicit_mounts_reach_adapter_without_inventing_an_absent_mount(offline, mount):
    _root, requests = offline
    data = _accepted_equipment(mount=mount)
    generation.maybe_generate_visual_assets(data)
    facts = _facts(requests[1]["payload"]["prompt"])
    if mount is None:
        assert "accessoryMount" not in facts
        assert "accessoryMount" not in data["visualKit"]["equipOverlay"]
    else:
        assert facts["accessoryMount"] == mount


def test_exact_mount_repair_reaches_adapter_and_preserves_frozen_design(offline):
    _root, requests = offline
    data = _accepted_equipment(mount="back")
    raw = copy.deepcopy(data["visualKit"])
    original_overlay = copy.deepcopy(raw["equipOverlay"])
    raw["equipOverlay"]["accessoryMount"] = "wing"
    accepted, errors = visual._validate_kit(raw, ["item"], "item", equipment_overlay_required=True)
    assert accepted is None
    scope = visual._build_visual_repair_scope(raw, errors, ["item"], "item", equipment_overlay_required=True)
    assert scope["fieldPermissions"]["equipOverlayPaths"] == ["accessoryMount"]
    repaired, audit = visual._apply_visual_repair_patch(raw, {
        "schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None,
        "equipOverlayPatch": dict(original_overlay, accessoryMount="waist", silhouette="unrequested replacement"),
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "note": "Repair only the invalid mount.",
    }, scope, ["item"], return_audit=True)
    accepted, errors = visual._validate_kit(repaired, ["item"], "item", equipment_overlay_required=True)
    assert accepted is not None, errors
    assert audit["ignoredChanges"]
    projected = visual._apply_kit(data, accepted)
    assert projected["visual"]["accessoryMount"] == "waist"

    generation.maybe_generate_visual_assets(projected)

    facts = _facts(requests[1]["payload"]["prompt"])
    assert facts["accessoryMount"] == projected["visual"]["accessoryMount"]
    assert facts["silhouette"] == original_overlay["silhouette"]
    assert facts["visualIdentity"] == original_overlay["visualIdentity"]


@pytest.mark.parametrize("zimage", [False, True])
def test_retry_and_prompt_only_preserve_long_overlay_facts(offline, monkeypatch, zimage):
    _root, requests = offline
    data = _accepted_equipment(mount="back", long_art=True)
    frozen = copy.deepcopy(data)
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 1)
    monkeypatch.setattr(post, "image_backend_is_zimage", lambda: zimage)
    monkeypatch.setenv("INFINI_ZIMAGE_RETRY_PROMPT_LIMIT", "2200")

    def response(req, **kwargs):
        payload = json.loads(req.data)
        requests.append({"payload": payload})
        if len(requests) == 2:
            # Real first-overlay validation fails: nonempty but tiny isolated
            # alpha, not a mocked validation or hand-written retry receipt.
            image = Image.new("RGBA", (64, 64))
            image.paste((210, 100, 20, 255), (32, 32, 34, 34))
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            return Response(stream.getvalue())
        return Response(png((210, 100, 20)))

    monkeypatch.setattr(backend, "urlopen_no_redirect", response)
    result = generation.maybe_generate_visual_assets(data)
    assert len(requests) == 3
    first, retry = (row["payload"]["prompt"] for row in requests[1:])
    assert _facts(first) == _facts(retry)
    assert _facts(retry)["silhouette"] == frozen["visualKit"]["equipOverlay"]["silhouette"]
    assert _facts(retry)["visualIdentity"] == frozen["visualKit"]["equipOverlay"]["visualIdentity"]
    assert "SILHOUETTE_END" in retry and "IDENTITY_END" in retry
    assert "Technical correction:" in retry if zimage else "fix these technical issues:" in retry
    attempts = json.loads(result["debug"]["equip_overlaySpriteValidation"])
    assert not attempts[0]["validation"]["ok"] and attempts[1]["validation"]["ok"]
    # The sd.cpp adapter performs its existing whitespace normalization.
    assert " ".join(result["debug"]["equip_overlayFinalPrompt"].split()) == retry
    assert result["visualKit"] == frozen["visualKit"]

    monkeypatch.setattr(generation, "IMAGE_BACKEND", "off")
    prompt_only = generation.maybe_generate_visual_assets(copy.deepcopy(frozen))
    assert len(requests) == 3
    assert _facts(prompt_only["debug"]["equip_overlayFinalPrompt"]) == _facts(first)
    assert prompt_only["visual"]["equipOverlayStatus"] == "prompt_only"


def test_ordinary_item_adapter_request_unchanged_by_wearable_metadata(offline):
    _root, requests = offline
    ordinary = _accepted_equipment("head", mount="back")
    ordinary["armor"]["enabled"] = False
    ordinary["accessory"]["enabled"] = False
    without_overlay = copy.deepcopy(ordinary)
    without_overlay["visualKit"].pop("equipOverlay")
    without_overlay["visual"].pop("accessoryMount")

    generation.maybe_generate_visual_assets(ordinary)
    generation.maybe_generate_visual_assets(without_overlay)

    assert len(requests) == 2, "name/category or an inactive overlay must not create a wearable job"
    assert requests[0]["payload"] == requests[1]["payload"]
    assert "Read-only equipment overlay facts:" not in requests[0]["payload"]["prompt"]


@pytest.mark.parametrize("missing", ["equipOverlay", "prompt", "silhouette", "visualIdentity"])
def test_missing_overlay_design_is_not_reconstructed_from_inventory_or_name(missing):
    data = _accepted_equipment("head")
    if missing == "equipOverlay":
        data["visualKit"].pop(missing)
    else:
        data["visualKit"]["equipOverlay"].pop(missing)
    frozen = copy.deepcopy(data)
    assert image_final_frame_prompt_clause(data, "equip_overlay", 48) == ""
    prompt = normalize_asset_prompt(data, "equip_overlay", "existing authored prompt", 48)
    assert "Read-only equipment overlay facts:" not in prompt
    assert "inventory-only" not in prompt and "Misleading" not in prompt
    assert data == frozen


def test_unknown_explicit_slot_does_not_gain_guessed_body_placement():
    data = _accepted_equipment("head")
    data["armor"]["slot"] = "helmet"
    assert image_final_frame_prompt_clause(data, "equip_overlay", 48) == ""
