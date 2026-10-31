from __future__ import annotations

import ast
import copy
import json
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.vfx_manifest import _compile_manifest, validate_vfx_director_output
from infini_local.pipelines import visual_delivery_gate
from infini_local.pipelines.visual_delivery_gate import visual_delivery_report
from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets,
    write_no_image_fixture_png,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from tests.vfx_material_fixtures import _shape, _sprite, _history, _legacy
from pipeline_test_support import isolated_serving_roots, install_campaign_fault
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def test_campaign_placed_body_uses_authenticated_qa_root_png(tmp_path):
    authored = build_runtime_fixture("fishing_platform_tool")
    authored["runtimeProgram"]["calls"].append({
        "id": "placed_body", "fn": "placed_sprite", "target": "item",
        "params": {"placementCallId": "platform_result", "renderSizePx": 32,
                   "footprintAnchorX": 0.5, "footprintAnchorY": 1,
                   "pivotSpace": "alpha_bounds", "imagePivotX": 0.5, "imagePivotY": 1,
                   "offsetXPx": 0, "offsetYPx": 0, "rotationDegrees": 0,
                   "flipX": False, "flipY": False},
    })
    data = compile_runtime_program(authored)
    data.update(id="qa-placed-body", visual={"preferredCanvasSize": 32,
                "renderSizePx": 32, "forwardAngleDegrees": 0})
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "qa-placed-body")
    fixture = write_no_image_fixture_png(tmp_path / "qa-no-image-fixture.png")
    data = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(data, fixture))
    before = copy.deepcopy(data)
    assert "required_placed_body_sprite_missing" in {
        row["code"] for row in visual_delivery_report(data, check_backend_config=False)["problems"]
    }
    observer = _campaign_observers(fixture)
    assert observer.assert_visual_delivery_ready(data) is data
    assert data == before
    for status in ("pending", "failed", "unknown"):
        refused = copy.deepcopy(data)
        refused["visual"]["spriteStatus"] = status
        with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked):
            observer.assert_visual_delivery_ready(refused)


@pytest.mark.parametrize("mode", ["runtime_geometry", "no_asset", "baked_sprite"])
def test_campaign_normalizes_prompts_only_for_image_jobs(tmp_path, mode):
    from typing import Any, cast
    from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
    from infini_local.pipelines.visual_prompt_contracts import asset_negative_prompt, normalize_asset_prompt

    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data.update(id="qa-prompt-boundary", visual={
        "preferredCanvasSize": 32, "renderSizePx": 32, "forwardAngleDegrees": 0,
        "imagePrompt": "One explicit pixel-art fixture item on a magenta key background.",
    })
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "qa-prompt-boundary")
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["visual"] = {"assetMode": mode, "prompt": "", "preferredCanvasSize": 32}
    harness = Path(__file__).resolve().parents[2] / "toolbox/live/runner.py"
    node = next(node for node in ast.parse(harness.read_text(encoding="utf-8")).body
                if isinstance(node, ast.FunctionDef) and node.name == "capture_image_boundary")
    captured = []
    namespace = {"Any": Any, "cast": cast, "copy": copy, "json": json,
                 "normalize_asset_prompt": normalize_asset_prompt, "asset_negative_prompt": asset_negative_prompt,
                 "build_visual_asset_plan": build_visual_asset_plan,
                 "hydrate_no_image_fixture_assets": hydrate_no_image_fixture_assets,
                 "NO_IMAGE_FIXTURE": write_no_image_fixture_png(tmp_path / "qa-no-image-fixture.png"),
                 "IMAGES": None, "case_trace_fields": lambda: {}, "append": lambda _path, row: captured.append(row)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(harness), "exec"), namespace)
    if mode == "baked_sprite":
        with pytest.raises(ValueError, match="explicit non-empty authored image prompt required"):
            namespace["capture_image_boundary"](data)
    else:
        namespace["capture_image_boundary"](data)
        slot = next(row for row in captured[0]["backendCallsThatWouldOccur"]
                    if row["role"] == "entity:" + entity["id"])
        assert not slot["shouldCallBackend"]
        assert slot["finalPrompt"] == ""
        assert entity["visual"]["assetMode"] == mode


def _campaign_observers(fixture):
    """Execute only the campaign's real observer installation, without inference."""
    from types import SimpleNamespace
    from infini_local.pipelines import combine_pipeline
    from infini_local.qa import live_no_image_fixture

    harness = Path(__file__).resolve().parents[2] / "toolbox/live/runner.py"
    nodes = []
    for node in ast.parse(harness.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom) and node.module == "infini_local.qa.live_no_image_fixture":
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {
            "identity_data", "no_image_cached_payload_report", "no_image_assert_visual_delivery_ready",
        }:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            (isinstance(target, ast.Name) and target.id in {
                "original_cached_payload_report", "original_assert_visual_delivery_ready",
            }) or (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                   and target.value.id == "combine" and target.attr in {
                       "_cached_payload_report", "assert_visual_delivery_ready",
                   }) for target in node.targets
        ):
            nodes.append(node)
    observer = SimpleNamespace(
        _cached_payload_report=combine_pipeline._cached_payload_report,
        assert_visual_delivery_ready=combine_pipeline.assert_visual_delivery_ready,
    )
    namespace = {"combine": observer, "NO_IMAGE_FIXTURE": fixture, "Any": object, "copy": copy}
    namespace.update(vars(live_no_image_fixture))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(harness), "exec"), namespace)
    return observer


@pytest.mark.parametrize("output_depth", ["short", "long"])
def test_campaign_fixture_uses_canonical_serving_root(tmp_path, monkeypatch, output_depth):
    from infini_local.core import config_bootstrap
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    from infini_local.pipelines.combine_pipeline import _cached_payload_report
    from infini_local.services.asset_sync_service import find_asset_file

    output = tmp_path / ("run" if output_depth == "short" else "deep-campaign-" * 12)
    sprites = output / "cache" / "sprites"
    world_recipes = output / "cache" / "world_recipes"
    monkeypatch.setattr(config_bootstrap, "SPRITE_DIR", sprites)
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", sprites)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", world_recipes)

    # Execute the actual campaign fixture owner without argparse, config loading
    # or inference. A helper-only check would miss an OUT-local fixture again.
    harness = Path(__file__).resolve().parents[2] / "toolbox/live/runner.py"
    nodes: list[ast.stmt] = [
        node for node in ast.parse(harness.read_text(encoding="utf-8")).body
        if (isinstance(node, ast.ImportFrom) and node.module == "infini_local.core.config_bootstrap")
        or (isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "NO_IMAGE_FIXTURE"
            for target in node.targets
        ))
    ]
    assert sum(isinstance(node, ast.Assign) for node in nodes) == 1
    namespace = {"OUT": output, "write_no_image_fixture_png": write_no_image_fixture_png}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(harness), "exec"), namespace)
    fixture = namespace["NO_IMAGE_FIXTURE"]
    if output_depth == "long":
        assert len(str(fixture.resolve())) > 139

    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data.update(id="qa-serving-root-control", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,
                visual={"preferredCanvasSize": 32})
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "no-image-serving-root")
    for entity in data["runtimeProgram"]["entities"]:
        entity.setdefault("visual", {})["assetMode"] = "baked_sprite"
        if entity["kind"] != "item_body":
            entity["visual"]["preferredCanvasSize"] = 32
    # Selected baked history consumes real PNG execution metadata, not just a
    # hydrated filename. Exercise the actual harness-installed final observer.
    authored = _history(data, "entity")
    selected = next(entity for entity in data["runtimeProgram"]["entities"] if entity["kind"] != "item_body")
    authored["slots"][0].update(entityId=selected["id"], event="periodic")
    admitted = validate_vfx_director_output(authored, data)
    assert admitted["ok"], admitted["errors"]
    data["vfxManifest"] = _compile_manifest(data, admitted["normalized"], "qa-history-control")
    before = copy.deepcopy(data)
    delivered = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(data, fixture))
    qa_before = copy.deepcopy(delivered)
    observer = _campaign_observers(fixture)
    report = observer._cached_payload_report(delivered)
    assert report.get("runtime", {}).get("ok"), report
    assert report.get("vfx", {}).get("ok"), report
    assert report["ok"], report["errors"]
    assert delivered == qa_before
    assert not _cached_payload_report(delivered)["ok"]  # Production stays strict.
    assert report["noImageExecutionControl"]["synthetic"] is True
    assert report["noImageExecutionControl"]["realImageGeneration"] is False
    assert observer.assert_visual_delivery_ready(delivered) is delivered
    assert delivered == qa_before
    assert fixture == sprites / "qa-no-image-fixture.png"
    assert find_asset_file(fixture.name, sprite_dir=sprites, world_recipes_dir=world_recipes) == fixture
    assert delivered["visual"]["spritePath"] == str(fixture.resolve())
    for original, entity in zip(before["runtimeProgram"]["entities"], delivered["runtimeProgram"]["entities"]):
        assert {key: value for key, value in entity.items() if key != "visual"} == {
            key: value for key, value in original.items() if key != "visual"
        }
        assert entity["visual"]["assetMode"] == original["visual"]["assetMode"]
        assert entity["visual"]["spritePath"] == str(fixture.resolve())

    short_reference = copy.deepcopy(delivered)
    short_reference["visual"]["spritePath"] = fixture.name
    for entity in short_reference["runtimeProgram"]["entities"]:
        entity["visual"]["spritePath"] = fixture.name
    assert observer._cached_payload_report(short_reference)["ok"]

    # An existing absolute outside-root PNG is not an authority. Keep this
    # refusal even though it has the same basename and bytes as the QA fixture.
    outside = write_no_image_fixture_png(output / fixture.name)
    assert outside.read_bytes() == fixture.read_bytes()
    fixture.unlink()
    refused = observer._cached_payload_report(sanitize_recipe_for_delivery(
        hydrate_no_image_fixture_assets(copy.deepcopy(before), outside)
    ))
    assert not refused["ok"]
    codes = {problem["code"] for problem in refused["visual"]["problems"]}
    assert {"required_entity_sprite_missing", "asset_roster_file_missing"} <= codes

    # A present serving-root file still has to pass the production PNG gate.
    write_no_image_fixture_png(fixture)
    fixture.write_bytes(fixture.read_bytes()[:-1])
    corrupt = observer._cached_payload_report(delivered)
    assert not corrupt["ok"]
    assert "asset_roster_invalid_png" in {
        problem["code"] for problem in corrupt["visual"]["problems"]
    }


@pytest.mark.parametrize("selection", ["baked_history", "projectile_body", "reuse_item_icon", "item_body"])
def test_campaign_execution_control_preserves_selected_owner_and_qa_evidence(campaign_case, tmp_path, monkeypatch, selection):
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    from infini_local.core.vfx_manifest import vfx_png_dependencies
    from infini_local.pipelines import combine_pipeline, visual_sprite_generation as sprites
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control
    import hashlib

    fixture, hydrated, entity = campaign_case(selection=selection)
    before = copy.deepcopy(hydrated)
    owner_id = entity["id"]
    expected_role = "item" if selection in {"reuse_item_icon", "item_body"} else "entity:" + owner_id
    observer = _campaign_observers(fixture)
    projector_globals_before = {key: getattr(sprites, key) for key in (
        "maybe_generate_sprite", "generate_visual_asset", "_generate_backend_variants", "write_visual_manifest",
    )}
    control = synthetic_no_image_execution_control(hydrated, fixture)
    assert {key: getattr(sprites, key) for key in projector_globals_before} == projector_globals_before
    assert hydrated == before
    assert control["vfxManifest"] == hydrated["vfxManifest"]
    execution_keys = {"spritePath", "spriteStatus", "spriteUrl", "spriteTechnicalScore"}
    assert {key: value for key, value in control.items() if key not in {"visual", "debug", "runtimeProgram"}} == {
        key: value for key, value in hydrated.items() if key not in {"visual", "debug", "runtimeProgram"}
    }
    assert {key: value for key, value in control["visual"].items() if key not in execution_keys} == {
        key: value for key, value in hydrated["visual"].items() if key not in execution_keys
    }
    for projected, original in zip(control["runtimeProgram"]["entities"], hydrated["runtimeProgram"]["entities"]):
        assert {key: value for key, value in projected.items() if key != "visual"} == {
            key: value for key, value in original.items() if key != "visual"
        }
        assert {key: value for key, value in projected["visual"].items() if key not in execution_keys} == {
            key: value for key, value in original["visual"].items() if key not in execution_keys
        }
    dependency = vfx_png_dependencies(control)["dependencies"][0]
    assert dependency["role"] == expected_role
    assert dependency["spriteStatus"] == "generated"
    assert control["debug"]["noImageExecutionControl"]["synthetic"] is True
    assert control["debug"]["noImageExecutionControl"]["realImageGeneration"] is False
    witness = next(row for row in control["debug"]["noImageExecutionControl"]["owners"] if row["role"] == expected_role)
    assert witness["selectedServingPath"] == str(fixture.resolve())
    assert witness["sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert witness["completePng"] is True
    assert not combine_pipeline._cached_payload_report(hydrated)["ok"]
    assert observer._cached_payload_report(hydrated)["ok"]
    assert observer.assert_visual_delivery_ready(hydrated) is hydrated
    assert hydrated == before

    def selected_owner(payload):
        if selection == "reuse_item_icon":
            return payload["visual"]
        return next(row["visual"] for row in payload["runtimeProgram"]["entities"] if row["id"] == owner_id)

    for mutation in ("pending", "missing_path", "wrong_owner"):
        negative = copy.deepcopy(hydrated)
        selected = selected_owner(negative)
        if mutation == "pending":
            selected["spriteStatus"] = "pending"
        elif mutation == "missing_path":
            selected["spritePath"] = ""
        else:
            # A generated sibling/root cannot lend readiness to the selected owner.
            selected["spritePath"] = str(tmp_path / "missing-selected-owner.png")
            if selection != "reuse_item_icon":
                negative["visual"]["spriteStatus"] = "generated"
        immutable = copy.deepcopy(negative)
        refused = observer._cached_payload_report(negative)
        assert not refused["ok"], mutation
        assert "required_vfx_texture_not_ready" in {row["code"] for row in refused["visual"]["problems"]}, mutation
        with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked):
            observer.assert_visual_delivery_ready(negative)
        assert negative == immutable

    # A healthy same-name shadow must not authenticate the fixture's exact bytes.
    shadow = tmp_path / "other-serving-root"
    write_no_image_fixture_png(shadow / fixture.name, size=16)
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", shadow)
    assert not observer._cached_payload_report(hydrated)["ok"]
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    fixture.write_bytes(fixture.read_bytes()[:-1])
    corrupt = observer._cached_payload_report(hydrated)
    assert not corrupt["ok"]
    assert "asset_roster_invalid_png" in {row["code"] for row in corrupt["visual"]["problems"]}
    fixture.unlink()
    missing = observer._cached_payload_report(hydrated)
    assert not missing["ok"]
    assert "asset_roster_file_missing" in {row["code"] for row in missing["visual"]["problems"]}
    assert hydrated == before


@pytest.fixture
def campaign_case(tmp_path):
    def build(*, selection="baked_history", ingredient=None, fixture_name="qa-no-image-fixture.png", identity="qa-selected-owner"):
        from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
        from tests.vfx_image_fixtures import _data

        fixture = write_no_image_fixture_png(tmp_path / fixture_name)
        if ingredient is not None:
            data = _data([ingredient])
            entity = None
        else:
            data = compile_runtime_program(build_runtime_fixture("returning_potion" if selection == "projectile_body" else "workbench_blade"))
            data.update(id=identity, schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,
                        visual={"preferredCanvasSize": 32})
            entity = next(row for row in data["runtimeProgram"]["entities"] if (row["kind"] == "item_body") == (selection == "item_body"))
            for row in data["runtimeProgram"]["entities"]:
                row.setdefault("visual", {})["assetMode"] = "baked_sprite"
                if row["kind"] != "item_body":
                    row["visual"]["preferredCanvasSize"] = 32
            entity["visual"]["assetMode"] = "reuse_item_icon" if selection == "reuse_item_icon" else "baked_sprite"
            if selection == "reuse_item_icon":
                entity["visual"].pop("preferredCanvasSize")
            authored = _history(data, "entity") if selection == "baked_history" else _sprite(data)
            authored["slots"][0].update(entityId=entity["id"], event="periodic")
            if selection != "baked_history":
                authored["slots"][0]["repeatEvery"] = 4
                authored["slots"][0]["element"]["texture"] = {"source": "entity", "assetId": "", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}
            admitted = validate_vfx_director_output(authored, data)
            assert admitted["ok"], admitted["errors"]
            data["vfxManifest"] = _compile_manifest(data, admitted["normalized"], identity)
        return fixture, sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(data, fixture)), entity
    return build


@pytest.mark.parametrize("corruption", ["pending-root", "wrong-alias-path"])
def test_no_image_execution_control_does_not_repair_invalid_reuse(campaign_case, corruption):
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control

    fixture, data, entity = campaign_case(selection="reuse_item_icon")
    alias = next(row["visual"] for row in data["runtimeProgram"]["entities"] if row["id"] == entity["id"])
    if corruption == "pending-root":
        data["visual"]["spriteStatus"] = "pending"
    else:
        alias["spritePath"] = str(write_no_image_fixture_png(fixture.with_name("other-owner.png")))
    before = copy.deepcopy(data)
    control = synthetic_no_image_execution_control(data, fixture)
    assert not visual_delivery_report(control, check_backend_config=False)["ok"]
    assert control["visual"]["spriteStatus"] == data["visual"]["spriteStatus"]
    assert data == before


CAMPAIGN_CONSUMPTION_CASES = [
    pytest.param("fixture", "projection", "final", "changed", id="fixture-during-projection"),
    *(pytest.param("fixture", boundary, consumer, "changed", id=f"fixture-{consumer}-{boundary}")
      for consumer in ("early", "final") for boundary in ("after_projection", "before_gate", "after_gate")),
    *(pytest.param("fixture", boundary, consumer, "same", id=f"same-bytes-{consumer}-{boundary}")
      for boundary in ("projection", "before_gate", "after_gate") for consumer in ("final", "early")),
    *(pytest.param("fixture", "serving_selection", consumer, "changed", id=f"same-bytes-other-root-{consumer}")
      for consumer in ("early", "final")),
    *(pytest.param("ingredient", boundary, "final", "changed", id=f"ingredient-{boundary}")
      for boundary in ("projection", "before_gate", "after_gate", "serving_selection")),
]


@pytest.mark.parametrize("owner,boundary,consumer,policy", CAMPAIGN_CONSUMPTION_CASES)
def test_campaign_consumption_authenticates_bytes_and_serving_selection(
    campaign_case, monkeypatch, owner, boundary, consumer, policy,
):
    import hashlib
    from tests.vfx_image_fixtures import _request

    fixture, data, _ = campaign_case(ingredient=_request() if owner == "ingredient" else None, identity="qa-fixture-byte-identity")
    path = Path(data["vfxManifest"]["assets"][0]["spritePath"]) if owner == "ingredient" else fixture
    before = copy.deepcopy(data)
    expected_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert _campaign_observers(fixture)._cached_payload_report(data)["ok"]

    def change():
        if policy == "same":
            replacement = path.with_name("replacement.png")
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
        elif boundary == "serving_selection":
            shadow = fixture.parent / "new-serving-root"
            shadow.mkdir(exist_ok=True)
            for file in {fixture, path}:
                copy_path = shadow / file.name
                copy_path.write_bytes(file.read_bytes())
                assert copy_path.read_bytes() == file.read_bytes()
            monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", shadow)
        elif owner == "ingredient":
            with Image.open(path) as image:
                image.putpixel((9, 9), (1, 2, 3, 255))
                image.save(path)
        else:
            write_no_image_fixture_png(path, size=16)
        if policy == "changed" and boundary != "serving_selection":
            with Image.open(path) as image:
                image.load()  # Both sides are complete real PNGs, not a corrupt-byte shortcut.
            assert hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha

    visited = install_campaign_fault(monkeypatch, boundary=boundary, consumer=consumer, change=change)
    observer = _campaign_observers(fixture)
    if consumer == "early":
        if policy == "same":
            assert observer.assert_visual_delivery_ready(data) is data
        else:
            with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked, match="qa_fixture_identity_changed"):
                observer.assert_visual_delivery_ready(data)
    else:
        report = observer._cached_payload_report(data)
        assert report["ok"] is (policy == "same"), report
        if policy == "same":
            assert {row["sha256"] for row in report["noImageExecutionControl"]["owners"]} == {expected_sha}
        else:
            assert "qa_fixture_identity_changed" in {row["code"] for row in report["visual"]["problems"]}
            if boundary != "serving_selection":
                assert report["noImageExecutionControl"]["owners"] == []
    assert visited == (["projection"] if boundary == "projection" and policy == "changed" else
                       ["projection", "gate"] if boundary == "projection" else
                       ["after_projection"] if boundary == "after_projection" else ["gate"])
    assert data == before


@pytest.mark.parametrize("layout,canvas", [("strip", 16), ("strip", 32), ("cutout", 64), ("cutout", 128)])
def test_campaign_declared_vfx_canvas_alpha_and_private_projection(campaign_case, layout, canvas):
    import hashlib
    import json
    from tests.vfx_image_fixtures import _request
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control

    fixture, data, _ = campaign_case(ingredient=_request("ingredient", layout=layout, canvas=canvas), fixture_name="qa.png")
    before = copy.deepcopy(data)
    asset = data["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "qa_no_image_fixture"
    assert asset["spritePath"] != data["visual"]["spritePath"]
    with Image.open(asset["spritePath"]) as image:
        assert image.size == (canvas, canvas)
        assert image.getchannel("A").getextrema() == (0, 255)
    observer = _campaign_observers(fixture)
    report = observer._cached_payload_report(data)
    assert report["ok"], report
    assert observer.assert_visual_delivery_ready(data) is data
    control = synthetic_no_image_execution_control(data, fixture)
    assert control["vfxManifest"]["assets"][0]["spriteStatus"] == "generated"
    execution_keys = {"spritePath", "spriteUrl", "spriteStatus", "spriteTechnicalScore"}
    assert {k: v for k, v in control["vfxManifest"]["assets"][0].items() if k not in execution_keys} == {
        k: v for k, v in asset.items() if k not in execution_keys
    }
    witness = next(row for row in report["noImageExecutionControl"]["owners"] if row["role"] == "vfx:ingredient")
    binding = json.loads(data["debug"]["noImageQaIngredientFixtures"])[0]
    assert witness["sha256"] == binding["sha256"] == hashlib.sha256(Path(asset["spritePath"]).read_bytes()).hexdigest()
    assert not visual_delivery_report(data, check_backend_config=False)["ok"]
    assert data == before


@pytest.mark.parametrize("mutation", ["wrong_canvas", "opaque", "rgb", "empty", "pending", "wrong_owner", "missing", "corrupt", "no_provenance"])
def test_campaign_vfx_ingredient_controls_refuse(campaign_case, mutation):
    from tests.vfx_image_fixtures import _request

    fixture, data, _ = campaign_case(ingredient=_request(), fixture_name="qa.png")
    observer = _campaign_observers(fixture)
    assert observer._cached_payload_report(data)["ok"]
    asset = data["vfxManifest"]["assets"][0]
    path = Path(asset["spritePath"])
    if mutation == "wrong_canvas":
        write_no_image_fixture_png(path, size=64, ingredient=True)
    elif mutation == "opaque":
        Image.new("RGBA", (32, 32), (24, 24, 24, 255)).save(path)
    elif mutation == "rgb":
        Image.new("RGB", (32, 32), (24, 24, 24)).save(path)
    elif mutation == "empty":
        Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(path)
    elif mutation == "pending":
        asset["spriteStatus"] = "pending"
    elif mutation == "wrong_owner":
        asset["spritePath"] = str(fixture)
    elif mutation == "missing":
        path.unlink()
    elif mutation == "corrupt":
        path.write_bytes(path.read_bytes()[:-1])
    elif mutation == "no_provenance":
        data["debug"].pop("noImageQaIngredientFixtures")
    if mutation in {"wrong_canvas", "opaque", "rgb", "empty", "corrupt"}:
        # Authenticate the malformed bytes too, so this negative proves the
        # canonical PNG contract, not merely a mismatch against the old hash.
        import hashlib
        import json
        binding = json.loads(data["debug"]["noImageQaIngredientFixtures"])
        binding[0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        data["debug"]["noImageQaIngredientFixtures"] = json.dumps(binding)
    before = copy.deepcopy(data)
    report = observer._cached_payload_report(data)
    assert not report["ok"]
    reasons = {reason for row in report["visual"]["problems"] for reason in row.get("validation", {}).get("reasons", [])}
    if mutation == "wrong_canvas":
        assert "final_canvas_mismatch" in reasons
    elif mutation == "rgb":
        assert "png_alpha_channel_missing" in reasons
    elif mutation == "opaque":
        assert "almost_no_transparency_after_bg_removal" in reasons
    elif mutation == "empty":
        assert "empty_alpha_bbox" in reasons
    with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked):
        observer.assert_visual_delivery_ready(data)
    assert data == before


@pytest.mark.parametrize("entry", [{}, {"assetId": "grain", "path": None}, {"assetId": "grain", "path": "qa.png", "sha256": []}])
def test_campaign_malformed_ingredient_provenance_refuses(campaign_case, entry):
    import json
    from tests.vfx_image_fixtures import _request

    fixture, data, _ = campaign_case(ingredient=_request(), fixture_name="qa.png")
    entry = {**entry, "assetId": "grain"}
    data["debug"]["noImageQaIngredientFixtures"] = json.dumps([entry])
    report = _campaign_observers(fixture)._cached_payload_report(data)
    assert not report["ok"]


def test_no_image_fixture_hydrates_real_delivery_paths_without_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from infini_local.core.runtime_authoring.capability_registry import VISUAL_ROLE_BY_ENTITY_KIND
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    fixture_path = write_no_image_fixture_png(tmp_path / "qa-fixture.png")
    # Exercise the decoder used by delivery consumers, not a parallel partial PNG parser.
    with Image.open(fixture_path) as image:
        assert image.format == "PNG"
        assert image.size == (32, 32)
        assert image.mode == "RGBA"
        image.load()
        assert image.getpixel((0, 0)) == (24, 24, 24, 255)
        assert image.getpixel((4, 0)) == (255, 0, 255, 255)
    # Negative control: a matching PNG header/dimensions with a broken IHDR CRC
    # cannot pass merely because its signature looks right.
    damaged = bytearray(fixture_path.read_bytes())
    damaged[24] ^= 1
    with pytest.raises(OSError):
        Image.open(BytesIO(damaged)).load()

    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data["visual"] = {"preferredCanvasSize": 32}
    non_item = [
        entity
        for entity in data["runtimeProgram"]["entities"]
        if entity["kind"] != "item_body"
    ]
    non_item[0]["visualRole"] = VISUAL_ROLE_BY_ENTITY_KIND[non_item[0]["kind"]]
    non_item[0]["visual"] = {"assetMode": "baked_sprite", "preferredCanvasSize": 32}
    non_item[1]["visualRole"] = VISUAL_ROLE_BY_ENTITY_KIND[non_item[1]["kind"]]
    non_item[1]["visual"] = {"assetMode": "reuse_item_icon"}
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "qa-path-hydration")

    hydrated = hydrate_no_image_fixture_assets(data, fixture_path)
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control
    assert not visual_delivery_report(hydrated, check_backend_config=False)["ok"]
    control = synthetic_no_image_execution_control(hydrated, fixture_path)
    report = visual_delivery_report(control, check_backend_config=False)

    assert report["ok"], report
    assert hydrated["visual"]["spriteStatus"] == "qa_no_image_fixture"
    item_body = next(entity for entity in data["runtimeProgram"]["entities"] if entity["kind"] == "item_body")
    assert item_body["visual"]["assetMode"] == "baked_sprite"
    assert item_body["visual"]["spriteStatus"] == "qa_no_image_fixture"
    assert item_body["visual"]["spritePath"] == str(fixture_path.resolve())
    assert non_item[0]["visual"]["spriteStatus"] == "qa_no_image_fixture"
    assert non_item[1]["visual"]["spriteStatus"] == "reused_item_icon"
    assert hydrated["debug"]["noImageQaFixturePath"] == str(fixture_path.resolve())


def test_no_image_fixture_hydrates_canonical_required_asset_plan_roles(tmp_path: Path) -> None:
    fixture_path = write_no_image_fixture_png(tmp_path / "qa-impact-fixture.png")
    data = build_runtime_fixture("workbench_blade")
    data["accessory"] = {"enabled": True}
    entities = data["runtimeProgram"]["entities"]
    required = entities[1]
    unrelated = entities[2]
    required.setdefault("visual", {}).update(impactSpriteStatus="pending", impactCanvasSize=32)
    unrelated.setdefault("visual", {})["impactSpriteStatus"] = "pending"
    data["vfxManifest"] = {
        "slots": [{
            "entityId": required["id"],
            "rendererKind": "impactSprite",
            "textureRole": "impact",
        }],
    }

    hydrated = hydrate_no_image_fixture_assets(data, fixture_path)
    required_visual = required["visual"]
    assert required_visual["impactSpriteStatus"] == "qa_no_image_fixture"
    assert required_visual["impactSpritePath"] == str(fixture_path.resolve())
    assert required_visual["impactSpriteUrl"] == ""
    assert required_visual["impactSpriteTechnicalScore"] == 1.0
    assert unrelated["visual"]["impactSpriteStatus"] == "pending"
    assert "impactSpritePath" not in unrelated["visual"]
    visual = hydrated["visual"]
    assert visual["equipOverlayStatus"] == "qa_no_image_fixture"
    assert visual["equipOverlayPath"] == str(fixture_path.resolve())
    assert visual["equipOverlayUrl"] == ""
    assert visual["equipOverlayTechnicalScore"] == 1.0
    assert visual["equipOverlayScore"] == 1.0
    problem_codes = {
        str(problem.get("code") or "")
        for problem in visual_delivery_report(hydrated, check_backend_config=False)["problems"]
    }
    # Hydration supplies real files with QA provenance, not a completed
    # production image result. This partial plan is not full VFX wire either;
    # the complete impact consumer is exercised by the next test below.
    assert "required_equipment_overlay_missing" in problem_codes
    assert "vfx_manifest_invalid" in problem_codes


def test_explicit_shape_needs_no_texture_but_saved_impact_sprite_still_does(tmp_path: Path) -> None:
    fixture = write_no_image_fixture_png(tmp_path / "no-image.png")
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data["visual"] = {"preferredCanvasSize": 32}
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    for row in data["runtimeProgram"]["entities"]:
        if row["kind"] != "item_body":
            row.setdefault("visual", {}).update(assetMode="baked_sprite", preferredCanvasSize=32)
    authored = _shape(data)
    authored["slots"][0].update(entityId=entity["id"], event="periodic", repeatEvery=4)
    report = validate_vfx_director_output(authored, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = _compile_manifest(data, report["normalized"], "no_image_impact_probe")

    hydrate_no_image_fixture_assets(data, fixture)
    assert "impactSpritePath" not in entity["visual"]
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control
    ring_control = synthetic_no_image_execution_control(data, fixture)
    ring_report = visual_delivery_report(ring_control, check_backend_config=False)
    assert ring_report["ok"], ring_report["problems"]
    assert not any(slot["role"] == "impact:" + entity["id"] for slot in ring_report["slots"])

    # Historical impact consumers remain valid persisted wire. This does not
    # feed a retired renderer to the fresh Director.
    saved = _legacy(data)
    slot = saved["slots"][0]
    slot.update(entityId=entity["id"], event="periodic", repeatEvery=4,
                rendererKind="impactSprite", textureRole="impact")
    for field in ("spread", "particleSystemId", "density"):
        slot.pop(field)
    data["vfxManifest"] = _compile_manifest(data, saved, "saved-impact-consumer")
    entity["visual"]["impactCanvasSize"] = 32
    sprite_report = visual_delivery_report(data, check_backend_config=False)
    assert "required_impact_sprite_missing" in {problem["code"] for problem in sprite_report["problems"]}
    hydrate_no_image_fixture_assets(data, fixture)
    assert "required_vfx_texture_not_ready" in {
        problem["code"] for problem in visual_delivery_report(data, check_backend_config=False)["problems"]
    }
    # Only the authenticated private control may bridge the QA labels; keep
    # the original fixture and every production readiness guard unchanged.
    final_control = synthetic_no_image_execution_control(data, fixture)
    final_report = visual_delivery_report(final_control, check_backend_config=False)
    assert final_report["ok"], final_report["problems"]
