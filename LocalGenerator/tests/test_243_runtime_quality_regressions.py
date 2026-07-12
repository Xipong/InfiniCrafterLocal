from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from infini_local.pipelines import combine_pipeline as COMBINE
from infini_local.pipelines import image_backend_pipeline as IMAGE_BACKEND
from infini_local.pipelines import pipeline_visual_config as VISUAL_CONFIG
from infini_local.pipelines import visual_sprite_generation as SPRITES
from infini_local.pipelines import visual_delivery_gate as DELIVERY
from infini_local.services import sdcpp_service
from infini_local.services import visual_asset_pipeline
from infini_local.desktop.settings_schema import PRESETS
from infini_local.storage import world_storage


def _parents() -> tuple[dict, dict]:
    return (
        {
            "name": "Деревянный меч",
            "internalName": "WoodenSword",
            "sourceMod": "Terraria",
            "damage": 7,
            "damageClass": "melee",
            "useTime": 20,
            "useAnimation": 20,
            "rare": 0,
            "value": 100,
            "maxStack": 1,
        },
        {
            "name": "Верстак",
            "internalName": "WorkBench",
            "sourceMod": "Terraria",
            "damage": -1,
            "damageClass": "none",
            "useTime": 10,
            "useAnimation": 14,
            "rare": 0,
            "value": 150,
            "maxStack": 9999,
            "consumable": True,
            "createTile": 18,
        },
    )


def _plan() -> dict:
    return {
        "name": "Workbench-on-a-Stick",
        "tooltip": "It is exactly what it looks like.",
        "concept": {
            "fantasy": "A whole workbench bolted sideways to a wooden sword.",
            "mergeLogic": "The sword remains the handle; the complete workbench is the striking body.",
            "weirdTwist": "Hits throw three bounded wooden splinter projectiles.",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "sourceRolePreservation": {
                "itemA": "the wooden sword remains the handle",
                "itemB": "the complete workbench remains visibly bolted to it",
            },
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "melee",
                        "damage": 12,
                        "useTimeTicks": 24,
                        "useAnimationTicks": 24,
                        "knockback": 6,
                        "maxStack": 1,
                    },
                },
                {
                    "fn": "perform_melee_attack",
                    "params": {
                        "family": "broadsword",
                        "speed": 8,
                        "rangeTiles": 3,
                        "lifetimeTicks": 24,
                        "projectileShape": "workbench bolted to a wooden sword",
                    },
                },
                {
                    "fn": "spawn_secondary_projectiles",
                    "params": {
                        "trigger": "on_hit",
                        "count": 3,
                        "damageMultiplier": 0.35,
                        "projectileShape": "wooden splinter",
                        "material": "wood",
                    },
                },
            ],
            "visualIntent": {
                "item": "A whole rectangular workbench bolted sideways to a wooden sword.",
                "impact": "Wood chips and sawdust.",
                "vfxIntent": "Wood chips and sawdust on impact.",
                "vfxAvoid": "No magical glow.",
            },
        },
        "visual": {
            "itemPrompt": "A whole rectangular workbench bolted sideways to a wooden sword.",
            "palette": ["brown", "tan", "dark brown"],
        },
    }


def _check_live_combine_spine_reaches_cache_without_visual_fields_in_attack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item_a, item_b = _parents()
    generated_sprite = tmp_path / "workbench_sword.png"
    generated_sprite.write_bytes(b"not-a-real-png-but-a-real-delivery-file")
    cached: dict[str, object] = {}

    monkeypatch.setattr(COMBINE, "USE_LLM", True)
    monkeypatch.setattr(COMBINE, "cache_get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(COMBINE, "try_llm_plan", lambda *_args, **_kwargs: _plan())
    monkeypatch.setattr(COMBINE, "apply_visual_director", lambda data, *_args, **_kwargs: data)

    def fake_assets(data: dict) -> dict:
        visual = data.setdefault("visual", {})
        visual["spriteStatus"] = "generated"
        visual["spritePath"] = str(generated_sprite)
        visual["spriteUrl"] = "/sprite/workbench_sword.png"
        return data

    monkeypatch.setattr(COMBINE, "maybe_generate_visual_assets", fake_assets)
    monkeypatch.setattr(COMBINE, "attach_hybrid_vfx_manifest", lambda data, *_args, **_kwargs: data)
    monkeypatch.setattr(COMBINE, "attach_generated_parent_summary", lambda data: data)
    monkeypatch.setattr(COMBINE.asset_sync_service, "attach_asset_sync_meta", lambda data, **_kwargs: data)
    monkeypatch.setattr(COMBINE.world_storage, "attach_recipe_health", lambda data, **_kwargs: data)
    monkeypatch.setattr(COMBINE, "cache_put", lambda key, _a, _b, data, *_args: cached.update({"key": key, "data": data}))
    monkeypatch.setattr(COMBINE.generation_debug, "clear_combine_failure", lambda _reason: None)
    monkeypatch.setattr(COMBINE.generation_debug, "record_combine_failure", lambda *_args, **_kwargs: None)

    result = COMBINE.combine({"itemA": item_a, "itemB": item_b, "worldId": "quality-test"})

    assert cached["data"] is result
    assert result["name"] == "Workbench-on-a-Stick"
    assert "whole rectangular workbench" in result["visual"]["itemPrompt"].lower()
    assert result["visual"]["vfxIntent"] == "Wood chips and sawdust on impact."
    assert "vfxIntent" not in result["attack"]
    assert "vfxAvoid" not in result["attack"]
    pipeline = json.loads(result["debug"]["pipelineLog"])
    labels = [row["stage"] for row in pipeline]
    assert labels.index("08c_strict_executable_preflight") < labels.index("09_visual_asset_generation")
    assert all(row["ok"] for row in pipeline)


def _check_image_backend_never_silently_becomes_procedural(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SPRITES, "IMAGE_BACKEND", "unknown-backend")
    monkeypatch.setattr(SPRITES, "IMAGE_BACKEND_CONFIG_ERROR", "unsupported image backend: unknown-backend")
    data = {"id": "backend-test", "visual": {"itemPrompt": "one authored object"}, "attack": {}}
    result = SPRITES.maybe_generate_sprite(data)
    assert result["visual"]["spriteStatus"] == "backend_config_error"
    assert "unsupported image backend" in result["debug"]["imageBackendConfigError"]

    monkeypatch.setattr(IMAGE_BACKEND, "resolve_comfyui_workflow_path", lambda: None)
    assert IMAGE_BACKEND.generate_comfyui("authored subject", "", "missing-workflow") == []

    monkeypatch.setattr(SPRITES, "IMAGE_BACKEND", "comfyui")
    monkeypatch.setattr(SPRITES, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(SPRITES, "generate_comfyui", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        visual_asset_pipeline,
        "generate_procedural_sprite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("procedural fallback must not run")),
    )
    assert SPRITES._generate_backend_variants(
        {}, prompt="authored subject", negative="", asset_id="no-fallback", canvas=48, role="item"
    ) == []

    # Environment misconfiguration blocks a fresh generation, but it must not make an
    # already-produced valid cache payload look corrupt and eligible for quarantine.
    with pytest.MonkeyPatch.context() as delivery_patch:
        delivery_patch.setattr(DELIVERY, "IMAGE_BACKEND", "unknown-backend")
        delivery_patch.setattr(DELIVERY, "IMAGE_BACKEND_RAW", "unknown-backend")
        delivery_patch.setattr(DELIVERY, "IMAGE_BACKEND_CONFIG_ERROR", "unsupported image backend")
        delivery_patch.setattr(DELIVERY, "VISUAL_REQUIRE_ZIMAGE_BACKEND", False)
        delivery_patch.setattr(DELIVERY, "VISUAL_REQUIRE_ITEM_SPRITE", True)
        sprite = Path(__file__)
        cached_payload = {"visual": {"spriteStatus": "generated", "spritePath": str(sprite)}, "attack": {}}
        assert DELIVERY.visual_delivery_report(cached_payload)["ok"] is False
        cache_report = DELIVERY.visual_delivery_report(cached_payload, check_backend_config=False)
        assert cache_report["ok"] is True
        assert cache_report["backendConfigChecked"] is False


def _check_invalid_world_cache_is_quarantined_and_deindexed(tmp_path: Path) -> None:
    payload = {
        "id": "g_bad_cache",
        "name": "Broken cached item",
        "sourceMode": "generated",
        "recipeHealth": {"status": "invalid", "ok": False},
    }
    world_storage.write_world_recipe_cache(
        tmp_path,
        "0.4.test",
        "r_bad",
        "world-bad",
        payload,
        parent_a_name="A",
        parent_b_name="B",
    )
    active = world_storage.world_recipe_file(tmp_path, "world-bad", "r_bad")
    assert active.exists()

    quarantined = Path(
        world_storage.quarantine_world_recipe_cache(
            tmp_path,
            world_id="world-bad",
            recipe_key_value="r_bad",
            reason="strict_boundary_invalid",
            details={"field": "attack.futureField"},
        )
    )
    assert not active.exists()
    assert quarantined.exists()
    reason = json.loads(quarantined.with_suffix(".reason.json").read_text(encoding="utf-8"))
    assert reason["reason"] == "strict_boundary_invalid"
    assert reason["details"]["field"] == "attack.futureField"

    root = world_storage.world_recipe_dir(tmp_path, "world-bad")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    health = json.loads((root / "health.json").read_text(encoding="utf-8"))
    assert "r_bad" not in index.get("recipes", {})
    assert "r_bad" not in health.get("recipes", {})

    malformed = world_storage.world_recipe_file(tmp_path, "world-bad", "r_malformed")
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("{this is not json", encoding="utf-8")
    assert world_storage.read_world_recipe_cache(
        tmp_path, "0.4.test", "recipe-v-test", "r_malformed", "world-bad"
    ) is None
    assert not malformed.exists()
    invalid_names = {path.name for path in (root / "invalid").glob("*.json")}
    assert any("r_malformed" in name and "json_unreadable_or_empty" in name for name in invalid_names)


def _check_sdcpp_cleanup_escalates_and_closes_log(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []

    class LogHandle:
        closed = False

        def close(self) -> None:
            self.closed = True

    class Process:
        pid = 424242

        def __init__(self) -> None:
            self._infini_log_handle = LogHandle()
            self.wait_calls = 0

        def poll(self):
            return None

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired("sd-server", timeout)
            return 0

    process = Process()
    state = sdcpp_service.SdcppServerState(process=process)
    monkeypatch.setattr(sdcpp_service, "_terminate_process_tree", lambda _proc, *, hard: calls.append(hard))
    sdcpp_service.cleanup_server_process(state, lambda *_args, **_kwargs: None, "test")

    assert calls == [False, True]
    assert state.process is None
    assert process._infini_log_handle.closed is True


def _check_prompt_compaction_keeps_authored_subject_and_final_guard() -> None:
    authored = "A whole rectangular workbench bolted sideways to a wooden sword, used as an absurd club-blade"
    filler = " ".join(f"descriptive-detail-{index}" for index in range(160))
    guard = (
        "Flat #ff00ff magenta chroma-key background. Show only the described sprite subject, fully inside the frame. "
        "Use crisp hard pixel edges and do not add unrequested duplicate parts"
    )
    prompt = visual_asset_pipeline.compact_zimage_asset_prompt([authored, filler, guard], "item", limit=520)

    assert len(prompt) <= 520
    assert "whole rectangular workbench bolted sideways" in prompt.lower()
    assert "#ff00ff" in prompt.lower()
    assert "unrequested duplicate parts" in prompt.lower()
    assert prompt.endswith(".")

    cleaned = visual_asset_pipeline.zimage_pe_clean_text("no magic glow, no coin silhouette")
    assert "without magical glow" in cleaned.lower()
    assert "without a coin silhouette" in cleaned.lower()
    assert "matte physical surface" not in cleaned.lower()
    assert "jagged fragments" not in cleaned.lower()


def _check_default_backend_matches_shipped_base_profile() -> None:
    assert VISUAL_CONFIG.IMAGE_BACKEND == "sdcpp"
    assert VISUAL_CONFIG.IMAGE_BACKEND_CONFIG_ERROR == ""
    no_image = PRESETS["API LLM only: без картинок"]
    assert no_image["INFINI_IMAGE_BACKEND"] == "off"
    assert no_image["INFINI_VISUAL_REQUIRE_ITEM_SPRITE"] == "0"
    for name, preset in PRESETS.items():
        if preset.get("INFINI_IMAGE_BACKEND") in {"sdcpp", "image_api"}:
            assert preset.get("INFINI_VISUAL_REQUIRE_ITEM_SPRITE") == "1", name


def test_runtime_quality_regressions_coarse_contract(tmp_path: Path) -> None:
    checks = [
        _check_live_combine_spine_reaches_cache_without_visual_fields_in_attack,
        _check_image_backend_never_silently_becomes_procedural,
        _check_invalid_world_cache_is_quarantined_and_deindexed,
        _check_sdcpp_cleanup_escalates_and_closes_log,
        _check_prompt_compaction_keeps_authored_subject_and_final_guard,
        _check_default_backend_matches_shipped_base_profile,
    ]
    for check in checks:
        case_dir = tmp_path / check.__name__
        case_dir.mkdir(parents=True, exist_ok=True)
        with pytest.MonkeyPatch.context() as monkeypatch:
            kwargs = {}
            if "tmp_path" in check.__annotations__:
                kwargs["tmp_path"] = case_dir
            if "monkeypatch" in check.__annotations__:
                kwargs["monkeypatch"] = monkeypatch
            check(**kwargs)
