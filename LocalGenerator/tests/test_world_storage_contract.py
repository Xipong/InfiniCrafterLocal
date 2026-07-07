from __future__ import annotations

import json
from pathlib import Path

from infini_local.storage import world_storage


def _check_safe_file_part_is_stable_and_boring() -> None:
    assert world_storage.safe_file_part(" My World: #1! ") == "My_World_1"
    assert world_storage.safe_file_part("***", "fallback") == "fallback"
    assert len(world_storage.safe_file_part("x" * 200, max_len=12)) == 12


def _check_world_cache_delivery_sanitizes_debug_and_runtime_only_fields(tmp_path: Path) -> None:
    data = {
        "id": "generated_test",
        "name": "Generated Test",
        "debug": {"nested": {"ok": True}, "num": 7},
        "_llmContinuation": {"messages": ["must not leak"]},
        "_runtimePlanCompileCache": {"must": "not leak"},
    }

    world_storage.write_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "parentA+parentB",
        "world:alpha",
        data,
        parent_a_name="A",
        parent_b_name="B",
        world_name="Alpha",
    )

    stored_path = world_storage.world_recipe_file(tmp_path, "world:alpha", "parentA+parentB")
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    assert "_llmContinuation" not in stored
    assert "_runtimePlanCompileCache" not in stored
    assert stored["debug"]["nested"] == '{"ok":true}'
    assert stored["debug"]["num"] == "7"
    assert stored["debug"]["recipeHealthStatus"] == "healthy"
    assert stored["recipeMeta"]["parentA"] == "A"
    assert stored["recipeMeta"]["worldScoped"] is True

    loaded = world_storage.read_world_recipe_cache(tmp_path, "9.9.9", "recipe_v_test", "parentA+parentB", "world:alpha")
    assert loaded is not None
    assert loaded["debug"]["cacheHit"] == "world_file"
    assert loaded["debug"]["recipeIdentityVersion"] == "recipe_v_test"


def _check_deliverable_recipe_payload_rejects_placeholders_and_fallbacks() -> None:
    assert world_storage.is_deliverable_recipe_payload({"id": "x", "name": "Real", "sourceMode": "llm"}) is True
    assert world_storage.is_deliverable_recipe_payload({"id": "placeholder", "name": "Real"}) is False
    assert world_storage.is_deliverable_recipe_payload({"id": "x", "name": "Real", "sourceMode": "fallback_dev"}) is False


def _check_world_recipe_health_index_tracks_runtime_assets_and_contracts(tmp_path: Path) -> None:
    data = {
        "id": "g_health",
        "name": "Health Blade",
        "sourceMode": "generated",
        "recipeKey": "r_health",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "runtimeOutputKind": "weapon"},
        "attack": {"enabled": True, "delivery": "thrust", "runtimeFamily": "thrust", "damagePath": "generated_executor"},
        "visual": {"spriteStatus": "generated"},
        "debug": {"runtimePlanValidation": '{"ok":true}', "runtimePlanProvenance": '{"gameplayChildren":{"enabled":false},"pureVfx":{"enabled":true}}'},
        "recipeMeta": {"assetFiles": ["g_health.png"]},
    }
    contract_versions = {"schema": "infini.contract-stamp.v1", "appVersion": "9.9.9", "runtimeApiVersion": "v_test"}
    visual_report = {
        "ok": True,
        "slots": [
            {"role": "item", "required": True, "status": "generated", "exists": True, "usable": True},
            {"role": "projectile", "required": False, "status": "", "exists": False, "usable": False},
        ],
    }
    world_storage.attach_recipe_health(data, app_version="9.9.9", contract_versions=contract_versions, visual_report=visual_report)
    assert data["recipeHealth"]["ok"] is True
    assert data["recipeHealth"]["runtime"]["pureVfx"] is True
    assert data["contractVersions"]["runtimeApiVersion"] == "v_test"

    world_storage.write_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "r_health",
        "world-health",
        data,
        parent_a_name="A",
        parent_b_name="B",
        world_name="Health World",
    )
    root = world_storage.world_recipe_dir(tmp_path, "world-health")
    stored = json.loads(world_storage.world_recipe_file(tmp_path, "world-health", "r_health").read_text(encoding="utf-8"))
    health_index = json.loads((root / "health.json").read_text(encoding="utf-8"))
    world_index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert stored["recipeHealth"]["status"] == "healthy"
    assert health_index["counts"]["healthy"] == 1
    assert health_index["recipes"]["r_health"]["runtime"]["delivery"] == "thrust"
    assert world_index["recipes"]["r_health"]["health"]["ok"] is True

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_safe_file_part_is_stable_and_boring',
    '_check_world_cache_delivery_sanitizes_debug_and_runtime_only_fields',
    '_check_deliverable_recipe_payload_rejects_placeholders_and_fallbacks',
    '_check_world_recipe_health_index_tracks_runtime_assets_and_contracts'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_world_storage_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
