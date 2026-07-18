from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


MODULE_NAME = "infini_local.pipelines.debug_delivery_overrides"


def _overlay(monkeypatch: pytest.MonkeyPatch, item: dict, *, enabled: str = "1", minimum: str = "10") -> dict:
    monkeypatch.setenv("INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED", enabled)
    monkeypatch.setenv("INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD", minimum)
    spec = importlib.util.find_spec(MODULE_NAME)
    assert spec is not None, "debug delivery override module is missing"
    module = importlib.import_module(MODULE_NAME)
    return module.apply_debug_attack_consumable_minimum_for_delivery(item)


def test_debug_minimum_normalizes_only_attacking_consumables_without_mutating_canonical_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        (
            "consumable weapon",
            {"category": "weapon", "gameplay": {"kind": "weapon", "consumable": True, "maxStack": 1, "craftYield": 1}, "attack": {"enabled": True}},
            (10, 10),
        ),
        (
            "actual ammo",
            {"category": "ammo", "gameplay": {"kind": "ammo", "consumable": True, "ammoFor": "arrow", "maxStack": 2, "craftYield": 1}, "attack": {"enabled": False}},
            (10, 10),
        ),
        (
            "generic attacking consumable",
            {"category": "generic", "gameplay": {"kind": "generic", "consumable": True, "maxStack": 4, "craftYield": 2}, "attack": {"enabled": True}},
            (10, 10),
        ),
        (
            "authored batch above minimum",
            {"category": "weapon", "gameplay": {"kind": "weapon", "consumable": True, "maxStack": 50, "craftYield": 25}, "attack": {"enabled": True}},
            (50, 25),
        ),
        (
            "potion stays authored even with an attack executor",
            {"category": "potion", "gameplay": {"kind": "potion", "consumable": True, "maxStack": 1, "craftYield": 1}, "attack": {"enabled": True}},
            (1, 1),
        ),
        (
            "material stays authored even with an attack executor",
            {"category": "material", "gameplay": {"kind": "material", "consumable": True, "maxStack": 1, "craftYield": 1}, "attack": {"enabled": True}},
            (1, 1),
        ),
    ]

    for label, canonical, expected in cases:
        original_gameplay = dict(canonical["gameplay"])
        delivered = _overlay(monkeypatch, canonical)
        assert (delivered["gameplay"]["maxStack"], delivered["gameplay"]["craftYield"]) == expected, label
        assert canonical["gameplay"] == original_gameplay, f"{label}: canonical recipe was mutated"

    disabled = {"category": "ammo", "gameplay": {"kind": "ammo", "consumable": True, "ammoFor": "bullet", "maxStack": 1, "craftYield": 1}, "attack": {"enabled": False}}
    disabled_result = _overlay(monkeypatch, disabled, enabled="0")
    assert disabled_result is disabled

    non_target = {"category": "potion", "gameplay": {"kind": "potion", "consumable": True, "maxStack": 1, "craftYield": 1}, "attack": {"enabled": True}}
    non_target_result = _overlay(monkeypatch, non_target, enabled="1")
    assert non_target_result is non_target


def test_debug_overlay_is_delivery_only_for_fresh_and_cached_recipes() -> None:
    pipeline_source = (
        Path(__file__).resolve().parents[1]
        / "infini_local"
        / "pipelines"
        / "combine_pipeline.py"
    ).read_text(encoding="utf-8")
    prompt_source = (
        Path(__file__).resolve().parents[1]
        / "infini_local"
        / "pipelines"
        / "llm_authoring_prompt.py"
    ).read_text(encoding="utf-8")

    call = "apply_debug_attack_consumable_minimum_for_delivery"
    assert pipeline_source.count(call) == 3, "expected one import plus cache/fresh delivery calls"
    assert f"return {call}(sanitize_recipe_for_delivery(cached))" in pipeline_source
    cache_put_index = pipeline_source.index("cache_put(key, a, b, data, world_id, world_name)")
    fresh_overlay_index = pipeline_source.index(f"return {call}(data)", cache_put_index)
    assert cache_put_index < fresh_overlay_index, "canonical authored recipe must be cached before applying debug delivery overlay"
    assert "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD" not in prompt_source
