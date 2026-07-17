from __future__ import annotations

from infini_local.pipelines import pipeline_visual_config as VISUAL
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt, role_visual_prompt_guard


def _enable_zimage(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")


def _contract_check_weapon_item_prompt_preserves_authored_topology_without_choosing_grip_count(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Emberleaf Saber",
        "runtimePlan": {"resultKind": "weapon"},
        "attack": {"enabled": True, "runtimeFamily": "swing", "delivery": "swing", "weaponFamily": "broadsword"},
        "concept": {"fantasy": "A leaf-shaped ember saber with an ornate brass hilt."},
        "visual": {"palette": ["dark steel", "ember orange", "brass"]},
    }

    prompt = normalize_asset_prompt(data, "item", "leaf-shaped dark steel saber with an ornate brass hilt", 48).lower()

    assert "leaf-shaped dark steel saber with an ornate brass hilt" in prompt
    assert "single centered object" not in prompt
    assert "geometry priority" not in prompt
    assert "do not add mirrored or duplicated structural parts" not in prompt
    assert "absent from the authored item prompt or silhouette contract" not in prompt
    assert "exactly one primary grip" not in prompt
    assert "two-handed weapon uses one longer shared grip" not in prompt


def _contract_check_weapon_topology_guard_allows_explicit_paired_contract_without_erasing_it(monkeypatch) -> None:
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
    assert prompt.index("deliberately paired set of two compact tonfa") < prompt.index("paired black-steel tonfa with cyan cores")
    assert "single centered object" not in prompt
    assert "geometry priority" not in prompt
    assert "do not add mirrored or duplicated structural parts" not in prompt
    assert "exactly one primary grip" not in prompt


def _contract_check_non_weapon_item_does_not_receive_weapon_topology_guard(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Braided Brass Charm",
        "runtimePlan": {"resultKind": "accessory"},
        "attack": {"enabled": False, "runtimeFamily": "none"},
        "visual": {"palette": ["brass", "brown"]},
    }

    prompt = normalize_asset_prompt(data, "item", "one braided brass charm with a brown cord", 32).lower()

    assert "one braided brass charm with a brown cord" in prompt
    assert "single centered object" not in prompt
    assert "geometry priority" not in prompt
    assert "preserve the planner-authored topology and part count" not in prompt
    assert "exactly one primary grip" not in prompt


def _contract_check_semantic_item_prompt_places_model_authored_topology_before_decoration_without_meta_prose(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Solar Phantasm Bow",
        "runtimePlan": {"resultKind": "weapon"},
        "canonical": {
            "headNoun": "bow",
            "shapeAnchors": ["bow", "bow limbs", "string"],
        },
        "visual": {
            "itemPrompt": "A golden bow with solar fragment accents and a glowing core.",
            "imagePrompt": "A single upright recurved archery bow with a compact amber sunstone inset into the grip.",
            "itemSilhouetteContract": "One continuous wooden stave forms one arc, and one taut string joins only its two tips.",
            "palette": ["gold", "brass", "white"],
        },
    }

    prompt = normalize_asset_prompt(data, "item", data["visual"]["imagePrompt"], 64).lower()

    silhouette = "one continuous wooden stave forms one arc, and one taut string joins only its two tips"
    appearance = "a single upright recurved archery bow with a compact amber sunstone inset into the grip"
    assert silhouette in prompt
    assert appearance in prompt
    assert prompt.index(silhouette) < prompt.index(appearance)
    assert "a golden bow with solar fragment accents and a glowing core" not in prompt
    assert "geometry priority" not in prompt
    assert "canonical silhouette" not in prompt
    assert "styling priority" not in prompt
    assert "authored composition" not in prompt
    assert "standard complete connected" not in prompt
    assert "do not mirror" not in prompt
    assert "cross, pair" not in prompt
    assert "disassembled" not in prompt


def _contract_check_semantic_item_prompt_keeps_visual_director_prompt_and_silhouette_over_planner_fallback(monkeypatch) -> None:
    _enable_zimage(monkeypatch)
    data = {
        "name": "Copper Crescent Relic",
        "canonical": {"headNoun": "relic", "shapeAnchors": ["relic"]},
        "visualKit": {
            "itemIconPrompt": "one asymmetric copper crescent connected to a wooden grip",
            "itemSilhouetteContract": "One copper crescent joins one wooden grip at its lower tip.",
        },
        "visual": {
            "itemPrompt": "a generic copper relic",
            "imagePrompt": "one asymmetric copper crescent connected to a wooden grip",
            "itemSilhouetteContract": "A generic round relic silhouette.",
            "palette": ["copper", "brown"],
        },
    }

    # Even if a caller accidentally forwards the planner fallback, an accepted
    # Visual Director prompt remains the authoritative appearance source.
    prompt = normalize_asset_prompt(data, "item", data["visual"]["itemPrompt"], 64).lower()

    assert "one asymmetric copper crescent connected to a wooden grip" in prompt
    assert "one copper crescent joins one wooden grip at its lower tip" in prompt
    assert "a generic copper relic" not in prompt
    assert "a generic round relic silhouette" not in prompt

    data["visual"]["imagePrompt"] = prompt
    data["visual"]["finalItemPrompt"] = prompt
    repeated = normalize_asset_prompt(data, "item", data["visual"]["imagePrompt"], 64).lower()
    assert "one asymmetric copper crescent connected to a wooden grip" in repeated
    assert "one copper crescent joins one wooden grip at its lower tip" in repeated
    assert "a generic copper relic" not in repeated


def _contract_check_legacy_item_role_guard_does_not_inject_negative_topology_language() -> None:
    data = {
        "runtimePlan": {"resultKind": "weapon"},
        "visual": {
            "itemSilhouetteContract": "Two separate compact tonfa form the intentional inventory pair.",
        },
    }

    guarded = role_visual_prompt_guard("item", "two compact tonfa side by side", data).lower()

    assert "two compact tonfa side by side" in guarded
    assert "do not add mirrored" not in guarded
    assert "duplicated structural parts" not in guarded
    assert "absent from the authored item prompt" not in guarded


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_weapon_topology_prompt_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_weapon_item_prompt_preserves_authored_topology_without_choosing_grip_count',
            '_contract_check_weapon_topology_guard_allows_explicit_paired_contract_without_erasing_it',
            '_contract_check_non_weapon_item_does_not_receive_weapon_topology_guard',
            '_contract_check_semantic_item_prompt_places_model_authored_topology_before_decoration_without_meta_prose',
            '_contract_check_semantic_item_prompt_keeps_visual_director_prompt_and_silhouette_over_planner_fallback',
            '_contract_check_legacy_item_role_guard_does_not_inject_negative_topology_language',
        ),
    )
