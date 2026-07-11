from __future__ import annotations

from infini_local.pipelines import pipeline_visual_config as VISUAL
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt


def _enable_zimage(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")


def test_weapon_item_prompt_has_one_primary_grip_topology(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Emberleaf Saber",
        "runtimePlan": {"resultKind": "weapon"},
        "attack": {"enabled": True, "runtimeFamily": "swing", "delivery": "swing", "weaponFamily": "broadsword"},
        "concept": {"fantasy": "A leaf-shaped ember saber with an ornate brass hilt."},
        "visual": {"palette": ["dark steel", "ember orange", "brass"]},
    }

    prompt = normalize_asset_prompt(data, "item", "leaf-shaped dark steel saber with an ornate brass hilt", 48).lower()

    assert "one continuous weapon object topology" in prompt
    assert "exactly one primary grip, handle, or hilt assembly" in prompt
    assert "do not mirror or duplicate handles" in prompt
    assert "two-handed weapon uses one longer shared grip, not two separate handles" in prompt


def test_weapon_topology_guard_allows_explicit_paired_contract_without_erasing_it(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Twin Tonfa Relay",
        "runtimePlan": {"resultKind": "weapon"},
        "attack": {"enabled": True, "runtimeFamily": "swing", "delivery": "swing", "weaponFamily": "melee"},
        "visual": {
            "itemSilhouetteContract": "A deliberately paired set of two compact tonfa joined as one inventory icon, each with one short side grip.",
            "palette": ["black steel", "cyan"],
        },
    }

    prompt = normalize_asset_prompt(data, "item", "paired black-steel tonfa with cyan cores", 48).lower()

    assert "deliberately paired set of two compact tonfa" in prompt
    assert "unless the authored silhouette contract explicitly requires a paired or double-ended construction" in prompt


def test_non_weapon_item_does_not_receive_weapon_topology_guard(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Braided Brass Charm",
        "runtimePlan": {"resultKind": "accessory"},
        "attack": {"enabled": False, "runtimeFamily": "none"},
        "visual": {"palette": ["brass", "brown"]},
    }

    prompt = normalize_asset_prompt(data, "item", "one braided brass charm with a brown cord", 32).lower()

    assert "one continuous weapon object topology" not in prompt
    assert "exactly one primary grip" not in prompt
