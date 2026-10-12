from __future__ import annotations

import ast
import copy
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.core.vfx_manifest import _compile_manifest, validate_vfx_director_output
from infini_local.pipelines import visual_delivery_gate
from infini_local.pipelines.visual_delivery_gate import visual_delivery_report
from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets,
    write_no_image_fixture_png,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _vfx_output
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def _campaign_observers(fixture):
    """Execute only the campaign's real observer installation, without inference."""
    from types import SimpleNamespace
    from infini_local.pipelines import combine_pipeline
    from infini_local.qa import live_no_image_fixture

    harness = Path(__file__).resolve().parents[2] / "toolbox/live-generation/generate_20_items_without_images.py"
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
    harness = Path(__file__).resolve().parents[2] / "toolbox/live-generation/generate_20_items_without_images.py"
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
    data.update(id="qa-serving-root-control", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION)
    data["vfxManifest"] = _compile_manifest(data, {
        "effectMagnitude": 0.0, "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none",
                  "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0}, "slots": [],
    }, "no-image-serving-root")
    for entity in data["runtimeProgram"]["entities"]:
        entity.setdefault("visual", {})["assetMode"] = "baked_sprite"
    # Selected baked history consumes real PNG execution metadata, not just a
    # hydrated filename. Exercise the actual harness-installed final observer.
    authored = _vfx_output(data)
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


@pytest.mark.parametrize("selection", ["baked_history", "projectile_alias", "reuse_item_icon", "item_body"])
def test_campaign_execution_control_preserves_selected_owner_and_qa_evidence(tmp_path, monkeypatch, selection):
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    from infini_local.core.vfx_manifest import vfx_png_dependencies
    from infini_local.pipelines import combine_pipeline, visual_sprite_generation as sprites
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control
    import hashlib

    fixture = write_no_image_fixture_png(tmp_path / "qa-no-image-fixture.png")
    data = compile_runtime_program(build_runtime_fixture("returning_potion" if selection == "projectile_alias" else "workbench_blade"))
    data.update(id="qa-selected-owner", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION)
    entity = next(row for row in data["runtimeProgram"]["entities"] if (row["kind"] == "item_body") == (selection == "item_body"))
    for row in data["runtimeProgram"]["entities"]:
        row.setdefault("visual", {})["assetMode"] = "baked_sprite"
    entity["visual"]["assetMode"] = "reuse_item_icon" if selection == "reuse_item_icon" else "baked_sprite"
    authored = _vfx_output(data)
    authored["slots"][0].update(entityId=entity["id"], event="periodic",
                                textureRole="projectile" if selection == "projectile_alias" else "entity")
    admitted = validate_vfx_director_output(authored, data)
    assert admitted["ok"], admitted["errors"]
    data["vfxManifest"] = _compile_manifest(data, admitted["normalized"], "qa-selected-owner")
    hydrated = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(data, fixture))
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
def execution_control_case(tmp_path):
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION

    fixture = write_no_image_fixture_png(tmp_path / "qa-no-image-fixture.png")
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data.update(id="qa-fixture-byte-identity", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION)
    for entity in data["runtimeProgram"]["entities"]:
        entity.setdefault("visual", {})["assetMode"] = "baked_sprite"
    selected = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    authored = _vfx_output(data)
    authored["slots"][0].update(entityId=selected["id"], event="periodic")
    admitted = validate_vfx_director_output(authored, data)
    assert admitted["ok"], admitted["errors"]
    data["vfxManifest"] = _compile_manifest(data, admitted["normalized"], "qa-fixture-byte-identity")
    return fixture, sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(data, fixture))


def test_campaign_refuses_fixture_byte_swap_during_projection(execution_control_case, monkeypatch):
    from infini_local.qa import live_no_image_fixture as qa

    fixture, data = execution_control_case
    observer = _campaign_observers(fixture)
    assert observer._cached_payload_report(data)["ok"]
    before = copy.deepcopy(data)
    original = qa.FunctionType
    projected = []

    def swap_during_projection(code, globals_, *args):
        projector = original(code, globals_, *args)

        def swapped(control):
            write_no_image_fixture_png(fixture, size=16)
            projected.append(True)
            return projector(control)

        return swapped

    monkeypatch.setattr(qa, "FunctionType", swap_during_projection)
    report = observer._cached_payload_report(data)
    assert projected == [True]
    assert not report["ok"], "different complete fixture bytes survived metadata projection"
    assert "qa_fixture_identity_changed" in {row["code"] for row in report["visual"]["problems"]}
    assert report["noImageExecutionControl"]["owners"] == []
    assert data == before
    write_no_image_fixture_png(fixture)
    with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked, match="qa_fixture_identity_changed"):
        observer.assert_visual_delivery_ready(data)
    assert data == before


@pytest.mark.parametrize("consumer", ["early", "final"])
@pytest.mark.parametrize("swap_at", ["after_projection", "before_gate", "after_gate"])
def test_campaign_refuses_fixture_byte_swap_at_readiness_consumption(
    execution_control_case, monkeypatch, consumer, swap_at,
):
    from infini_local.pipelines import combine_pipeline

    fixture, data = execution_control_case
    before = copy.deepcopy(data)
    attr = "assert_visual_delivery_ready" if consumer == "early" else "_cached_payload_report"
    original = getattr(combine_pipeline, attr)
    visited = []

    def swapping_gate(control):
        # This callback is the actual consumer held by the campaign wrapper, not
        # another QA report. Swap after projection immediately before its read,
        # or after a successful read but before returning the cached result.
        if swap_at == "before_gate":
            write_no_image_fixture_png(fixture, size=16)
        result = original(control)
        visited.append(True)
        if consumer == "final":
            assert result["ok"]
        if swap_at == "after_gate":
            write_no_image_fixture_png(fixture, size=16)
        return result

    if swap_at == "after_projection":
        from infini_local.qa import live_no_image_fixture as qa
        project = qa.synthetic_no_image_execution_control

        def swap_after_projection(*args):
            control = project(*args)
            write_no_image_fixture_png(fixture, size=16)
            return control

        monkeypatch.setattr(qa, "synthetic_no_image_execution_control", swap_after_projection)
    monkeypatch.setattr(combine_pipeline, attr, swapping_gate)
    observer = _campaign_observers(fixture)
    if consumer == "early":
        with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked, match="qa_fixture_identity_changed"):
            observer.assert_visual_delivery_ready(data)
    else:
        report = observer._cached_payload_report(data)
        assert not report["ok"], "different complete fixture bytes survived final readiness consumption"
        assert "qa_fixture_identity_changed" in {row["code"] for row in report["visual"]["problems"]}
        assert report["noImageExecutionControl"]["owners"] == []
    assert visited == ([] if swap_at == "after_projection" else [True])
    assert data == before


@pytest.mark.parametrize("swap_at", ["projection", "before_gate", "after_gate"])
def test_campaign_accepts_same_fixture_bytes_replacement(execution_control_case, monkeypatch, swap_at):
    from infini_local.pipelines import combine_pipeline
    from infini_local.qa import live_no_image_fixture as qa
    import hashlib

    fixture, data = execution_control_case
    before = copy.deepcopy(data)
    expected_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    visited = []

    def replace_same_bytes():
        replacement = fixture.with_name("replacement.png")
        replacement.write_bytes(fixture.read_bytes())
        replacement.replace(fixture)
        visited.append(True)

    if swap_at == "projection":
        original = qa.FunctionType

        def same_byte_projector(code, globals_, *args):
            projector = original(code, globals_, *args)

            def replaced(control):
                replace_same_bytes()
                return projector(control)

            return replaced

        monkeypatch.setattr(qa, "FunctionType", same_byte_projector)
    else:
        for attr in ("_cached_payload_report", "assert_visual_delivery_ready"):
            original = getattr(combine_pipeline, attr)

            def same_byte_gate(control, original=original):
                if swap_at == "before_gate":
                    replace_same_bytes()
                result = original(control)
                if swap_at == "after_gate":
                    replace_same_bytes()
                return result

            monkeypatch.setattr(combine_pipeline, attr, same_byte_gate)

    observer = _campaign_observers(fixture)
    report = observer._cached_payload_report(data)
    assert report["ok"], report
    assert {row["sha256"] for row in report["noImageExecutionControl"]["owners"]} == {expected_sha}
    assert observer.assert_visual_delivery_ready(data) is data
    assert visited == [True, True]
    assert data == before


@pytest.mark.parametrize("consumer", ["early", "final"])
def test_campaign_refuses_changed_canonical_selection_with_same_fixture_bytes(
    execution_control_case, monkeypatch, consumer,
):
    from infini_local.pipelines import combine_pipeline

    fixture, data = execution_control_case
    before = copy.deepcopy(data)
    shadow_root = fixture.parent / "new-serving-root"
    shadow = write_no_image_fixture_png(shadow_root / fixture.name)
    assert shadow.read_bytes() == fixture.read_bytes()
    attr = "assert_visual_delivery_ready" if consumer == "early" else "_cached_payload_report"
    original = getattr(combine_pipeline, attr)
    visited = []

    def root_changed_gate(control):
        monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", shadow_root)
        result = original(control)
        visited.append(True)
        if consumer == "final":
            assert result["ok"]
        return result

    monkeypatch.setattr(combine_pipeline, attr, root_changed_gate)
    observer = _campaign_observers(fixture)
    if consumer == "early":
        with pytest.raises(visual_delivery_gate.VisualDeliveryBlocked, match="qa_fixture_identity_changed"):
            observer.assert_visual_delivery_ready(data)
    else:
        report = observer._cached_payload_report(data)
        assert not report["ok"]
        assert "qa_fixture_identity_changed" in {row["code"] for row in report["visual"]["problems"]}
    assert visited == [True]
    assert data == before


@pytest.fixture(autouse=True)
def isolated_serving_roots(monkeypatch, tmp_path):
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")


@pytest.mark.parametrize("layout,canvas", [("strip", 16), ("strip", 32), ("cutout", 64), ("cutout", 128)])
def test_campaign_declared_vfx_canvas_alpha_and_private_projection(tmp_path, layout, canvas):
    import hashlib
    import json
    from tests.vfx_image_fixtures import _data, _request
    from infini_local.qa.live_no_image_fixture import synthetic_no_image_execution_control

    fixture = write_no_image_fixture_png(tmp_path / "qa.png")
    data = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(
        _data([_request("ingredient", layout=layout, canvas=canvas)]), fixture,
    ))
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
def test_campaign_vfx_ingredient_controls_refuse(tmp_path, mutation):
    from tests.vfx_image_fixtures import _data, _request

    fixture = write_no_image_fixture_png(tmp_path / "qa.png")
    data = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(_data([_request()]), fixture))
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


@pytest.mark.parametrize("swap_at", ["projection", "before_gate", "after_gate", "serving_selection"])
def test_campaign_vfx_ingredient_hash_binds_actual_consumption(tmp_path, monkeypatch, swap_at):
    from tests.vfx_image_fixtures import _data, _request
    from infini_local.qa import live_no_image_fixture as qa
    from infini_local.pipelines import combine_pipeline

    fixture = write_no_image_fixture_png(tmp_path / "qa.png")
    data = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(_data([_request()]), fixture))
    path = Path(data["vfxManifest"]["assets"][0]["spritePath"])
    before = copy.deepcopy(data)
    if swap_at == "projection":
        original = qa.FunctionType
        def projector_wrapper(code, globals_, *args):
            projector = original(code, globals_, *args)
            def replaced(control):
                with Image.open(path) as image:
                    image.putpixel((9, 9), (1, 2, 3, 255))
                    image.save(path)
                return projector(control)
            return replaced
        monkeypatch.setattr(qa, "FunctionType", projector_wrapper)
    else:
        original = combine_pipeline._cached_payload_report
        def gate_wrapper(control):
            if swap_at in {"before_gate", "serving_selection"}:
                if swap_at == "serving_selection":
                    shadow = tmp_path / "shadow"
                    shadow.mkdir()
                    for file in (fixture, path):
                        (shadow / file.name).write_bytes(file.read_bytes())
                    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", shadow)
                else:
                    with Image.open(path) as image:
                        image.putpixel((9, 9), (1, 2, 3, 255))
                        image.save(path)
            result = original(control)
            if swap_at == "after_gate":
                with Image.open(path) as image:
                    image.putpixel((9, 9), (1, 2, 3, 255))
                    image.save(path)
            return result
        monkeypatch.setattr(combine_pipeline, "_cached_payload_report", gate_wrapper)
    report = _campaign_observers(fixture)._cached_payload_report(data)
    assert not report["ok"]
    assert "qa_fixture_identity_changed" in {row["code"] for row in report["visual"]["problems"]}
    assert data == before


@pytest.mark.parametrize("entry", [{}, {"assetId": "grain", "path": None}, {"assetId": "grain", "path": "qa.png", "sha256": []}])
def test_campaign_malformed_ingredient_provenance_refuses(tmp_path, entry):
    import json
    from tests.vfx_image_fixtures import _data, _request

    fixture = write_no_image_fixture_png(tmp_path / "qa.png")
    data = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(_data([_request()]), fixture))
    entry = {**entry, "assetId": "grain"}
    data["debug"]["noImageQaIngredientFixtures"] = json.dumps([entry])
    report = _campaign_observers(fixture)._cached_payload_report(data)
    assert not report["ok"]


def test_no_image_fixture_hydrates_real_delivery_paths_without_backend(tmp_path: Path) -> None:
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

    data = build_runtime_fixture("workbench_blade")
    data["visual"] = {}
    non_item = [
        entity
        for entity in data["runtimeProgram"]["entities"]
        if entity["kind"] != "item_body"
    ]
    non_item[0]["visualRole"] = "projectile"
    non_item[0]["visual"] = {"assetMode": "baked_sprite"}
    non_item[1]["visualRole"] = "child"
    non_item[1]["visual"] = {"assetMode": "reuse_item_icon"}

    hydrated = hydrate_no_image_fixture_assets(data, fixture_path)
    report = visual_delivery_report(hydrated, check_backend_config=False)

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
    required.setdefault("visual", {})["impactSpriteStatus"] = "pending"
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
    assert "required_equipment_overlay_missing" not in problem_codes
    assert "required_impact_sprite_missing" not in problem_codes


def test_primitive_impact_ring_does_not_require_a_texture_but_impact_sprite_does(tmp_path: Path) -> None:
    fixture = write_no_image_fixture_png(tmp_path / "no-image.png")
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    for row in data["runtimeProgram"]["entities"]:
        if row["kind"] != "item_body":
            row.setdefault("visual", {})["assetMode"] = "baked_sprite"
    authored = _vfx_output(data)
    authored["slots"][0].update(entityId=entity["id"], event="periodic",
                                rendererKind="impactRing", textureRole="impact")
    report = validate_vfx_director_output(authored, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = _compile_manifest(data, report["normalized"], "no_image_impact_probe")

    hydrate_no_image_fixture_assets(data, fixture)
    assert "impactSpritePath" not in entity["visual"]
    ring_report = visual_delivery_report(data, check_backend_config=False)
    assert ring_report["ok"], ring_report["problems"]
    assert not any(slot["role"] == "impact:" + entity["id"] for slot in ring_report["slots"])

    data["vfxManifest"]["slots"][0]["rendererKind"] = "impactSprite"
    sprite_report = visual_delivery_report(data, check_backend_config=False)
    assert "required_impact_sprite_missing" in {problem["code"] for problem in sprite_report["problems"]}
    hydrate_no_image_fixture_assets(data, fixture)
    assert "required_vfx_texture_not_ready" in {
        problem["code"] for problem in visual_delivery_report(data, check_backend_config=False)["problems"]
    }
    # The no-image hydrator deliberately labels QA bytes, not a completed image
    # execution. Supply that result explicitly for this offline delivery fixture.
    entity["visual"]["impactSpriteStatus"] = "generated"
    final_report = visual_delivery_report(data, check_backend_config=False)
    assert final_report["ok"], final_report["problems"]
