"""DOCX #21/#22: completed PNGs do not turn unfinished producers into ready art.

Pixels and backend responses are explicitly offline fixtures, not generated art.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from infini_local.pipelines import visual_delivery_gate as delivery
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from tests.vfx_image_fixtures import _data, _request, _existing_texture_data, offline_backend


def _retained_delivery():
    from infini_local.core.vfx_manifest import _compile_manifest, VFX_DIRECTOR_SCHEMA
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    import json
    from infini_local.pipelines import visual_generation_pipeline as visual
    from tests.test_low_level_three_stage_pipeline import _visual_kit

    # Replay unchanged saved wire through existing presentation adapters. Fresh
    # Author now emits independent motion fields, which legitimately alter its
    # read-only image facts; this control protects the historical delivery ABI.
    fixture = Path(__file__).resolve().parents[2] / "tools/fixtures/docx-image-ready-delivered.json"
    saved = json.loads(fixture.read_text(encoding="utf-8"))
    assert validate_runtime_wire(saved)["ok"]
    mechanics = copy.deepcopy(saved["runtimeProgram"])
    data = visual._apply_kit(saved, _visual_kit(saved))
    data.update(id="docx_image_ready_offline", sourceMode="generated", schemaVersion=5,
                runtimeApiVersion="infini.runtime-program.v5", recipeKey="docx_readiness_offline")
    data["vfxManifest"] = _compile_manifest(data, {"schema": VFX_DIRECTOR_SCHEMA, "slots": []}, "offline_recipe")
    data = generation.maybe_generate_visual_assets(data)
    path = Path(data["visual"]["spritePath"])
    raw = path.read_bytes()
    alias_file = path.with_name("docx-image-ready.png")
    alias_file.write_bytes(raw)
    alias = "https://offline.invalid/sprites/" + alias_file.name + "?revision=2#cached"
    data["visual"]["spritePath"] = alias
    for entity in data["runtimeProgram"]["entities"]:
        if entity["kind"] == "item_body" or entity["visual"]["assetMode"] == "reuse_item_icon":
            entity["visual"]["spritePath"] = alias
    assert delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    data.pop("debug", None)  # Non-authoritative private paths are not retained fixtures.
    data["visual"].update(spriteRawPath="", assetManifestPath="")
    outgoing = sanitize_recipe_for_delivery(data)
    assert validate_runtime_wire(outgoing)["ok"]
    delivered_mechanics = copy.deepcopy(outgoing["runtimeProgram"])
    for runtime in (delivered_mechanics, mechanics):
        for entity in runtime["entities"]:
            entity.pop("visual", None)
    assert delivered_mechanics == mechanics
    return outgoing, raw


def test_qa_execution_control_authenticates_fixture_without_admitting_pending(offline_backend):
    from infini_local.qa.live_no_image_fixture import (
        hydrate_no_image_fixture_assets, synthetic_no_image_execution_control,
        write_no_image_fixture_png,
    )
    fixture = write_no_image_fixture_png(delivery.SPRITE_DIR / "qa-ready-control.png")
    data = _data([])
    hydrate_no_image_fixture_assets(data, fixture)
    assert not delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    original = copy.deepcopy(data)
    control = synthetic_no_image_execution_control(data, fixture)
    assert delivery.visual_delivery_report(control, check_backend_config=False)["ok"]
    assert data == original
    assert control["debug"]["noImageExecutionControl"]["synthetic"] is True
    assert control["debug"]["noImageExecutionControl"]["realImageGeneration"] is False
    pending = copy.deepcopy(data)
    pending["visual"]["spriteStatus"] = "pending"
    refused = synthetic_no_image_execution_control(pending, fixture)
    assert refused["visual"]["spriteStatus"] == "pending"
    assert not delivery.visual_delivery_report(refused, check_backend_config=False)["ok"]


def test_retained_native_fixture_is_real_final_offline_projection(offline_backend):
    import json
    outgoing, raw = _retained_delivery()
    root = Path(__file__).resolve().parents[2] / "tools/fixtures"
    retained = json.loads((root / "docx-image-ready-delivered.json").read_text(encoding="utf-8"))
    from collections import Counter
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    # This native witness fixes image delivery, not every later gameplay field.
    # Preserve its historical bytes and prove both payloads remain consumable.
    for payload in (retained, outgoing):
        assert validate_runtime_wire(payload)["ok"]
        assert validate_vfx_manifest_wire(payload)["ok"]
        assert delivery.visual_delivery_report(payload, check_backend_config=False)["ok"]
    assert retained["visual"] == outgoing["visual"]
    assert retained["vfxManifest"] == outgoing["vfxManifest"]
    def entity_images(payload):
        return Counter((entity["id"], entity["kind"], json.dumps(entity["visual"], sort_keys=True))
                       for entity in payload["runtimeProgram"]["entities"])
    # Include owner identity and multiplicity: dropping/duplicating a delivery or
    # assigning the right image to the wrong entity must not pass.
    assert entity_images(retained) == entity_images(outgoing)
    assert (root / "docx-image-ready.png").read_bytes() == raw



def test_pending_item_cannot_borrow_previous_png_readiness(offline_backend):
    data = generation.maybe_generate_visual_assets(_data([]))
    assert delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    before = copy.deepcopy(data)
    data["visual"]["spriteStatus"] = "pending"
    report = delivery.visual_delivery_report(data, check_backend_config=False)
    assert not report["ok"], "a previous PNG is not completion of a pending producer"
    assert "required_item_sprite_missing" in {row["code"] for row in report["problems"]}
    assert Path(before["visual"]["spritePath"]).read_bytes() == Path(data["visual"]["spritePath"]).read_bytes()


def test_prompt_only_attempt_clears_previous_item_publication(offline_backend, monkeypatch):
    data = generation.maybe_generate_visual_assets(_data([]))
    previous_path = Path(data["visual"]["spritePath"])
    assert previous_path.is_file()
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "off")
    out = generation.maybe_generate_visual_assets(data)
    assert out["visual"]["spriteStatus"] == "prompt_only"
    assert out["visual"]["spritePath"] == "", "disabled attempt must not publish a previous attempt's PNG"
    assert out["visual"]["spriteUrl"] == out["visual"]["spriteRawPath"] == ""
    assert not delivery.visual_delivery_report(out, check_backend_config=False)["ok"]
    assert previous_path.is_file(), "revoking a DTO publication never deletes historical PNGs"


@pytest.mark.parametrize("producer", ["item", "entity", "impact", "overlay"])
@pytest.mark.parametrize("status", ["pending", "generating", "not_required", "future_unknown", "failed"])
def test_unfinished_selected_producer_never_borrows_healthy_sibling_png(offline_backend, producer, status):
    data = generation.maybe_generate_visual_assets(_existing_texture_data(producer) if producer in {"entity", "impact"} else _data([]))
    if producer == "overlay":
        data["accessory"] = {"enabled": True}
        data["visual"].update(equipOverlayPath=data["visual"]["spritePath"], equipOverlayStatus="generated")
    assert delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    if producer in {"item", "overlay"}:
        owner = data["visual"]
        field = "equipOverlayStatus" if producer == "overlay" else "spriteStatus"
    else:
        owner = next(row["visual"] for row in data["runtimeProgram"]["entities"] if row["id"] == "orb")
        field = "impactSpriteStatus" if producer == "impact" else "spriteStatus"
    owner[field] = status
    assert not delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    outgoing = sanitize_recipe_for_delivery(data)
    assert not delivery.visual_delivery_report(outgoing, check_backend_config=False)["ok"]


@pytest.mark.parametrize("status", ["generated", "generated_warn_invalid", "fallback", "fallback_after_failed_generation"])
def test_existing_completed_statuses_remain_usable_without_touching_declared_no_asset(offline_backend, status):
    data = generation.maybe_generate_visual_assets(_data([]))
    data["visual"]["spriteStatus"] = status
    assert delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    orb = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "orb")
    assert orb["visual"]["assetMode"] == "runtime_geometry"
    assert orb["visual"]["spriteStatus"] == "not_required" and orb["visual"]["spritePath"] == ""


def test_independent_vfx_images_use_existing_two_slot_bound(offline_backend, monkeypatch):
    import threading
    from infini_local.services.sdcpp_service import ImageRequestGate
    from infini_local.services import codex_auth

    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    backend = generation.generate_sdcpp
    barrier = threading.Barrier(2)
    observed = []
    lock = threading.Lock()
    active = peak = 0

    def transport(prompt, negative, asset_id, canvas, *, output_dir=None):
        nonlocal active, peak
        if not asset_id.startswith("infini_vfx_job_"):
            return backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            # This is a synchronization witness, not a provider speed benchmark.
            barrier.wait(timeout=3)
            join, observer = codex_auth._GENERATION_OBSERVATIONS.get()
            observed.append(dict(join))
            return backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    data = _data([_request("first"), _request("second")])
    data["debug"] = {"vfx:firstFinalPrompt": "previous first", "vfx:secondFinalPrompt": "previous second"}
    with codex_auth.generation_observations({"requestId": "offline_parallel_join"}, None):
        out = generation.maybe_generate_visual_assets(data)
    assert delivery.visual_delivery_report(out, check_backend_config=False)["ok"], "independent image jobs must both complete under the existing two-slot bound"
    assert peak == 2
    assert len(observed) == 2 and all(row["requestId"] == "offline_parallel_join" for row in observed)
    assert {row["role"] for row in observed} == {"vfx:first", "vfx:second"}
    for asset in out["vfxManifest"]["assets"]:
        assert asset["spriteStatus"] == "generated"
        assert out["debug"]["vfx:" + asset["id"] + "FinalPrompt"] != "previous " + asset["id"]
    assert len(offline_backend[0]) == 3, "one item and exactly two planned images, no extra attempts"


@pytest.mark.parametrize("capacity", [1, 2])
def test_ingredient_scheduling_keeps_bound_and_failed_identity(offline_backend, monkeypatch, capacity):
    import threading
    from infini_local.services.sdcpp_service import ImageRequestGate
    from infini_local.services import codex_auth

    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(capacity))
    backend = generation.generate_sdcpp
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    calls = []
    active = peak = admitted = 0

    def transport(prompt, negative, asset_id, canvas, *, output_dir=None):
        nonlocal active, peak, admitted
        join, _ = codex_auth._GENERATION_OBSERVATIONS.get()
        role = join["role"]
        ordinal = 0
        with lock:
            calls.append(role)
            if role != "item":
                active += 1
                admitted += 1
                ordinal = admitted
                peak = max(peak, active)
        try:
            if role != "item" and capacity > 1 and ordinal <= 2:
                barrier.wait(timeout=3)
            if role == "vfx:bad":
                return []  # Explicit transport fixture failure, not fabricated art.
            return backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
        finally:
            if role != "item":
                with lock:
                    active -= 1

    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    data = _data([_request("first"), _request("bad"), _request("third")])
    frozen_runtime = copy.deepcopy(data["runtimeProgram"])
    out = generation.maybe_generate_visual_assets(data)
    assets = {row["id"]: row for row in out["vfxManifest"]["assets"]}
    assert peak == capacity and len(calls) == 4
    assert set(calls) == {"item", "vfx:first", "vfx:bad", "vfx:third"}
    if capacity == 1:
        assert calls[0] == "item", "single-slot mode preserves original order"
    assert assets["bad"]["spriteStatus"] == "failed" and assets["bad"]["spritePath"] == ""
    assert all(assets[name]["spriteStatus"] == "generated" for name in ("first", "third"))
    report = delivery.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"]
    assert {row.get("assetId") for row in report["problems"] if row["code"] == "required_vfx_sprite_missing_or_invalid"} == {"bad"}
    assert "vfx:badSpriteValidation" in out["debug"] and "vfx:firstSpriteValidation" in out["debug"]
    assert out["runtimeProgram"]["bindings"] == frozen_runtime["bindings"]


def test_query_alias_ready_delivery_preserves_exact_selected_basename(offline_backend):
    data = generation.maybe_generate_visual_assets(_data([]))
    path = Path(data["visual"]["spritePath"])
    alias = "https://offline.invalid/sprites/" + path.name + "?revision=2#cached"
    data["visual"]["spritePath"] = alias
    for entity in data["runtimeProgram"]["entities"]:
        if entity["kind"] == "item_body":
            entity["visual"]["spritePath"] = alias
    assert delivery.visual_delivery_report(data, check_backend_config=False)["ok"]
    outgoing = sanitize_recipe_for_delivery(data)
    assert outgoing["visual"]["spritePath"] == alias
    assert path.is_file()
