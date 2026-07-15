from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.item_power_knowledge import apply_item_knowledge
from infini_local.pipelines.item_power_knowledge import canonicalize
from infini_local.pipelines.item_power_knowledge import infer_item_card
from infini_local.pipelines import llm_transport as transport
from infini_local.pipelines.llm_transport import _llm_replay_stage_from_payload, llm_chat_json
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt
from infini_local.storage.world_recipe_runtime import sanitize_recipe_for_delivery

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _wooden_sword(name: str = "Wooden Sword", damage: int = 7) -> dict:
    return {
        "name": name,
        "internalName": "WoodenSword",
        "sourceMod": "Terraria",
        "damage": damage,
        "damageClass": "melee",
        "useStyle": 1,
        "useTime": 20,
        "useAnimation": 20,
        "rare": 0,
        "value": 100,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "shoot": 0,
        "shootSpeed": 0,
    }


def _spear_parent() -> dict:
    return {
        "name": "Копье",
        "internalName": "Spear",
        "sourceMod": "Terraria",
        "damage": 8,
        "damageClass": "melee",
        "useStyle": 5,
        "useTime": 31,
        "useAnimation": 31,
        "rare": 1,
        "value": 1210,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "noMelee": True,
        "noUseGraphic": True,
        "shoot": 49,
        "shootSpeed": 3.7,
        "directProjectileRaw": {
            "source": "item.shoot",
            "type": 49,
            "internalName": "Spear",
            "sourceMod": "Terraria",
            "itemShootSpeed": 3.7,
            "width": 21,
            "height": 21,
            "scale": 1.2,
            "penetrate": -1,
            "timeLeft": 3600,
            "tileCollide": False,
            "ownerHitCheck": True,
            "damageClass": "melee",
        },
    }


def _rope_parent() -> dict:
    return {
        "name": "Веревка",
        "internalName": "Rope",
        "sourceMod": "Terraria",
        "damage": -1,
        "damageClass": "none",
        "useStyle": 1,
        "useTime": 8,
        "useAnimation": 14,
        "rare": 0,
        "value": 10,
        "maxStack": 9999,
        "consumable": True,
        "material": True,
        "createTile": 213,
        "shoot": 0,
        "shootSpeed": 0,
    }


def _validate_and_attach(plan: dict, a: dict, b: dict, key: str) -> dict:
    ca = canonicalize(a)
    cb = canonicalize(b)
    data = validate_and_repair(plan, a, b, ca, cb, key)
    data = apply_item_knowledge(data, a, b, ca, cb)
    data = attach_gameplay_and_attack(data, a, b, ca, cb)
    return data




def _llm_replay_content(req: dict) -> str:
    return llm_chat_json(req)["choices"][0]["message"]["content"]


def _check_llm_chat_json_raw_replay_intercepts_planner_without_network(monkeypatch, tmp_path) -> None:
    raw_text = (FIXTURES / "llm_raw" / "twin_grain_saber_wrapped.txt").read_text(encoding="utf-8")
    replay = tmp_path / "planner.txt"
    replay.write_text(raw_text, encoding="utf-8")
    monkeypatch.setenv("INFINI_LLM_REPLAY_RAW", str(replay))
    monkeypatch.setattr(transport, "LLM_POOL_PROFILES", ())
    monkeypatch.setattr(transport, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_BASE_URL", "https://must-not-run.example/v1")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_API_KEY", "")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_MODEL", "replay-model")
    monkeypatch.setattr(transport, "LLM_API_MODE", "responses")
    transport._reset_llm_pool_runtime_for_tests()

    def fail_network(*_args, **_kwargs):
        raise AssertionError("raw replay must resolve before auth or Responses HTTP")

    monkeypatch.setattr(transport, "http_json", fail_network)

    req = {
        "model": "fake",
        "messages": [
            {"role": "system", "content": "You are the AUTHOR of a Terraria-like generated item."},
            {"role": "user", "content": "Combine itemA and itemB into one playable Terraria-like item."},
        ],
        "response_format": {"type": "json_object"},
    }
    content = _llm_replay_content(req)
    plan = parse_first_valid_llm_json(content)
    assert plan["name"] == "Twin Grain Saber"


def _check_llm_replay_stage_prefers_planner_over_loose_name_repair_match() -> None:
    # Planner payloads often mention both "repair" and "name" (repairPolicy, display names).
    # That must not route the author hop to name_repair fixtures.
    req = {
        "messages": [
            {"role": "system", "content": "You are the AUTHOR of a Terraria-like generated item."},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "author one item",
                        "priorityHeader": "repair policy notes and names are context only",
                        "requiredJsonShape": {"runtimePlan": {"engineCalls": []}},
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "infini_runtime_plan"}},
    }
    assert _llm_replay_stage_from_payload(req) == "planner"


def _check_llm_chat_json_raw_replay_directory_routes_multiple_llm_hops(monkeypatch, tmp_path) -> None:
    # One replay seam lives in llm_chat_json, so it can cover planner, VFX-director,
    # and repair calls instead of only try_llm_plan. This stays out of production
    # unless INFINI_LLM_REPLAY_RAW is explicitly set.
    (tmp_path / "planner.txt").write_text('{"name":"Planner Replay","runtimePlan":{"engineCalls":[]}}', encoding="utf-8")
    (tmp_path / "visual_director.txt").write_text('{"visualKit":{"projectileSpritePrompt":"compact harpoon head","negativePrompt":""}}', encoding="utf-8")
    monkeypatch.setenv("INFINI_LLM_REPLAY_RAW", str(tmp_path))

    planner_req = {
        "messages": [
            {"role": "system", "content": "You are the AUTHOR of a Terraria-like generated item."},
            {"role": "user", "content": "Combine itemA and itemB into one playable Terraria-like item."},
        ]
    }
    vfx_req = {
        "messages": [
            {"role": "system", "content": "You are a pixel-art asset director for Z-Image in a Terraria-like generated item mod."},
            {"role": "user", "content": "make visualKit"},
        ]
    }

    assert parse_first_valid_llm_json(_llm_replay_content(planner_req))["name"] == "Planner Replay"
    assert parse_first_valid_llm_json(_llm_replay_content(vfx_req))["visualKit"]["projectileSpritePrompt"] == "compact harpoon head"


def _check_replay_stage_prefers_canonical_message_names_over_prose() -> None:
    expected = {
        "item_author_contract": "planner",
        "runtime_repair_contract": "author_repair",
        "genome_repair_contract": "genome_repair",
        "name_repair_contract": "name_repair",
        "visual_director_contract": "visual_director",
        "vfx_director_contract": "vfx_director",
    }
    for name, stage in expected.items():
        payload = {"messages": [{"role": "system", "name": name, "content": "opaque contract"}]}
        assert _llm_replay_stage_from_payload(payload) == stage


def _check_raw_llm_text_replay_goes_through_real_parser_and_runtime_adapter() -> None:
    # This fixture is intentionally raw wrapped model output, not a pre-parsed dict.
    # It catches the JSON extraction/repair seam that deterministic_plan cannot test.
    raw_text = (FIXTURES / "llm_raw" / "twin_grain_saber_wrapped.txt").read_text(encoding="utf-8")
    plan = parse_first_valid_llm_json(raw_text)
    assert plan["name"] == "Twin Grain Saber"
    assert plan["runtimePlan"]["engineCalls"]

    data = _validate_and_attach(plan, _wooden_sword(damage=7), _wooden_sword(damage=8), "test_replay_twin_grain_saber")
    assert data["category"] == "weapon"
    assert data["attack"]["enabled"] is True
    assert data["attack"]["runtimePlanAuthored"] is True
    assert data["attack"]["delivery"] == "swing"
    assert data["attack"]["movement"] == "straight"
    assert data["gameplay"]["damage"] == 10
    assert data["sourceMode"] == "generated"


def _check_parsed_author_plan_replay_keeps_tether_as_runtime_visual_not_png_line() -> None:
    # Real Rope Spear author plan from trace: old projectilePrompt contained
    # "thin taught rope line back to the player". The image prompt must scrub
    # only the full-canvas/off-canvas tether instruction, while preserving a
    # short local rope/chain detail if it helps the projectile silhouette.
    import os
    os.environ.pop("INFINI_LLM_REPLAY_RAW", None)
    plan = json.loads((FIXTURES / "author_plan" / "rope_spear_author_plan.json").read_text(encoding="utf-8"))
    data = _validate_and_attach(plan, _spear_parent(), _rope_parent(), "test_replay_rope_spear")
    assert data["attack"]["genome"]["runtimeFamily"] == "returning"
    assert data["attack"]["genome"]["pullStrength"] == 0.35
    assert data["attack"]["genome"]["pullMode"] == "owner_to_target"

    projectile_prompt = data["visual"].get("projectileImagePrompt") or data["visual"].get("projectilePrompt", "")
    prompt = normalize_asset_prompt(data, "projectile", projectile_prompt, 48).lower()
    assert "thin taught rope line" not in prompt
    assert "thin taut rope line" not in prompt
    assert "extending left" not in prompt
    assert "back to the player" not in prompt
    assert "long rope/chain/tether is not part of the png" not in prompt
    assert "short local" in prompt or "local attachment" in prompt or "short rope" in prompt

    item_source_prompt = data["visual"].get("imagePrompt") or data["visual"].get("itemPrompt", "")
    item_prompt = normalize_asset_prompt(data, "item", item_source_prompt, 32).lower()
    assert "not a long spear pole" not in item_prompt
    assert "rope coil" in item_prompt or "coiled rope" in item_prompt or "rope grip" in item_prompt


def _check_delivery_payload_replay_normalizes_object_debug_without_changing_gameplay() -> None:
    payload = json.loads((FIXTURES / "combine_payload" / "object_debug_payload.json").read_text(encoding="utf-8"))
    delivered = sanitize_recipe_for_delivery(payload)

    assert delivered["runtimeApiVersion"] == "v0.4.23"
    assert delivered["gameplay"]["damage"] == payload["gameplay"]["damage"]
    assert delivered["attack"]["projectileWidth"] == payload["attack"]["projectileWidth"]
    assert "damage" not in delivered["attack"]
    assert "useProjectile" not in delivered["attack"]
    assert isinstance(delivered["debug"], dict)
    assert all(isinstance(v, str) for v in delivered["debug"].values())
    assert "authorPreservingValidation" in delivered["debug"]
    assert delivered["debug"]["authorPreservingValidation"].startswith("{")


def _silver_coin_parent() -> dict:
    return {
        "name": "Серебряная монета",
        "internalName": "SilverCoin",
        "fullName": "Terraria/SilverCoin",
        "sourceMod": "Terraria",
        "damage": 50,
        "damageClass": "ranged",
        "useStyle": 0,
        "useTime": 10,
        "useAnimation": 15,
        "rare": 0,
        "value": 500,
        "maxStack": 100,
        "consumable": True,
        "material": False,
        "ammo": 71,
        "useAmmo": 0,
        "shoot": 159,
        "shootSpeed": 2,
        "directProjectileRaw": {
            "type": 159,
            "internalName": "SilverCoin",
            "sourceMod": "Terraria",
            "width": 4,
            "height": 4,
            "aiStyle": 1,
            "penetrate": 1,
            "timeLeft": 600,
            "extraUpdates": 1,
            "tileCollide": True,
            "ownerHitCheck": False,
            "friendly": True,
            "damageClass": "ranged",
        },
    }


def _check_parent_stage_hints_do_not_turn_starter_melee_or_coins_into_boss_tiers() -> None:
    wooden = infer_item_card(_wooden_sword())
    assert wooden["tier"] in {"early", "pre_boss", "wood"}
    assert float(wooden["powerScore"]) < 55

    coin = infer_item_card(_silver_coin_parent())
    assert coin["tier"] not in {"lunar", "endgame", "post_moonlord"}
    assert float(coin["powerScore"]) <= 72.0
    assert "+currency_ammo_cap" in coin["signals"]["mechanicPower"]["basis"]

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_llm_chat_json_raw_replay_intercepts_planner_without_network',
    '_check_llm_replay_stage_prefers_planner_over_loose_name_repair_match',
    '_check_llm_chat_json_raw_replay_directory_routes_multiple_llm_hops',
    '_check_replay_stage_prefers_canonical_message_names_over_prose',
    '_check_raw_llm_text_replay_goes_through_real_parser_and_runtime_adapter',
    '_check_parsed_author_plan_replay_keeps_tether_as_runtime_visual_not_png_line',
    '_check_delivery_payload_replay_normalizes_object_debug_without_changing_gameplay',
    '_check_parent_stage_hints_do_not_turn_starter_melee_or_coins_into_boss_tiers'
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


def test_replay_fixtures_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
