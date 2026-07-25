from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.runtime_authoring import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    RUNTIME_CONTRACT_SCHEMA,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    compact_capability_catalog,
)
from infini_local.pipelines.author_item_contract import author_item_prompt_shape_card
from infini_local.pipelines.combine_balance import stat_profile_for
from infini_local.pipelines.item_power_knowledge import tags_of
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


PLANNER_PROMPT_LIMIT_CHARS = 96_000
PLANNER_PROMPT_MIN_HEADROOM_CHARS = 1_000
COMBAT_EXECUTOR_RESULT_KIND_RULE = (
    "Do not choose a sword/bow/staff/sentry family. Choose explicit entities, input bindings, "
    "movement/controllers, damage, collision, lifecycle and event links from the catalog."
)
VISIBLE_ENGINE_FUNCTIONS = tuple(sorted(CAPABILITY_REGISTRY))


def normalize_llm_attack_shape(obj: dict[str, Any]) -> dict[str, Any]:
    return obj


def normalize_behavior_toy_fields(obj: dict[str, Any]) -> dict[str, Any]:
    return obj


def normalize_runtime_authoring_fields(data: dict[str, Any]) -> dict[str, Any]:
    return data


def runtime_value(data: dict[str, Any], fn: str, field: str, fallback: Any = None) -> Any:
    program = data.get("runtimeProgram")
    if not isinstance(program, dict):
        return fallback
    calls = program.get("calls")
    if not isinstance(calls, list):
        return fallback
    for call in calls:
        if isinstance(call, dict) and call.get("fn") == fn and isinstance(call.get("params"), dict) and field in call["params"]:
            return call["params"][field]
    return fallback


def terraria_tick_guide_for_llm() -> dict[str, Any]:
    return {
        "ticksPerSecond": 60,
        "commonDurations": {"0.1s": 6, "0.25s": 15, "0.5s": 30, "1s": 60, "2s": 120, "5s": 300},
        "tilesToPixels": "1 tile = 16 pixels",
        "angles": "spreadRadians is the full angular span, not degrees",
    }


def concise_terraria_tick_guide_for_llm() -> dict[str, str]:
    return {
        "time": "60 ticks = 1 second",
        "distance": "1 tile = 16 pixels",
        "spread": "radians; total span",
    }


def planner_priority_header_for_llm() -> list[str]:
    return [
        "Return one complete bounded runtimeProgram in this single response; no tool loop and no second design pass.",
        "Directly compose low-level entities, bindings, capabilities and event links. Never classify the item into sword/bow/staff/sentry for execution.",
        "category is UI/equipment metadata only. Names, tooltip, tags and parent prose never select gameplay behaviour.",
        "Every movement, attachment/entity kind, damage path, input binding, lifecycle, targeting and child action must be explicit.",
        "Use only capabilities present in capabilityCatalog. Do not promise gameplay that has no call/binding backing.",
        "Parent useAmmo/ammo-candidate facts are read-only Terraria context. No ammo-consuming weapon capability exists yet: author explicit projectile entities and never claim vanilla PickAmmo/stack consumption unless a future catalog capability provides the full pipeline.",
        "Preserve literal parent physics where useful: a workbench may remain a literal workbench attached to a blade. Do not replace it with a vague wooden theme.",
        "Do not add a mandatory weird twist. Novelty comes from the authored composition itself, not an unrelated gimmick.",
        "Multiple independent actions are legal: primary held action plus alternate deployed action, equipment/tool/placeable plus combat, fields plus child projectiles.",
        "All ids are stable lowercase snake_case and globally unique across entities, bindings, calls and claims.",
        "Exactly one item_body is required. All other entities need explicit spawn, lifetime, hitbox, collision and, where moving, movement/controller calls.",
        "Primary/alternate inputs are exclusive. Sequence extra behaviour through supported events rather than competing bindings.",
        "Before answering, verify references, target kinds, exclusive components, event cycles, child depth/count and claim backing.",
    ]


def sharp_engine_fn_catalog_for_llm() -> dict[str, Any]:
    return {
        "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        "authoringSchema": RUNTIME_PROGRAM_SCHEMA,
        "entityKinds": [row.prompt_card() for row in ENTITY_KIND_REGISTRY.values()],
        "inputs": [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()],
        "bindingActions": [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()],
        "events": [row.prompt_card() for row in EVENT_KIND_REGISTRY.values()],
        "limits": {"entities": 12, "bindings": 8, "calls": 48, "childDepth": 3, "eventSpawnsPerActivation": 32},
        "capabilities": compact_capability_catalog(),
    }


def engine_runtime_capability_contract_for_llm(
    a: dict[str, Any],
    b: dict[str, Any],
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del a, b
    return {
        "principle": "The author composes the item. Deterministic code only type-checks, bounds, compiles and executes explicit choices.",
        "catalog": sharp_engine_fn_catalog_for_llm(),
        "balanceCorridor": copy.deepcopy(envelope or {}),
        "technicalNotes": concise_terraria_tick_guide_for_llm(),
        "claimRule": "Every gameplay claim in runtimeContract.claims.backedBy cites one or more existing call/binding ids.",
        "literalSynthesisRule": "Keep concrete parent objects/parts literal when the concept uses them; do not code-normalize furniture into a material theme.",
    }


def authored_num(src: dict[str, Any], key: str, fallback: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(src.get(key, fallback))))
    except (TypeError, ValueError):
        return fallback


def authored_int(src: dict[str, Any], key: str, fallback: int, lo: int, hi: int) -> int:
    return int(round(authored_num(src, key, fallback, lo, hi)))


def authored_str(src: dict[str, Any], key: str, fallback: str = "") -> str:
    value = src.get(key, fallback)
    return str(value) if value is not None else fallback


def authored_weapon_damage(*args: Any, **kwargs: Any) -> int:
    # Kept as a neutral numeric helper for callers outside the authoring contract;
    # it never selects a runtime class or component.
    for value in args:
        if isinstance(value, dict) and "damage" in value:
            try:
                return max(0, int(value["damage"]))
            except (TypeError, ValueError):
                pass
    return max(0, int(kwargs.get("fallback", 0) or 0))


def llm_category_without_router(
    data: dict[str, Any], requested_kind: Any, tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None
) -> tuple[str, dict[str, Any]]:
    del data, tags, a, b, key
    allowed = {"combat", "tool", "equipment", "placeable", "consumable", "material", "hybrid", "generic"}
    requested = str(requested_kind or "generic").strip().lower()
    selected = requested if requested in allowed else "generic"
    return selected, {"source": "authored_ui_category", "gameplayRouter": False}


def _balance_corridor(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    stage = stat_profile_for(a, b, tags_of(a) | tags_of(b))
    envelope = stage.get("balanceEnvelope") if isinstance(stage.get("balanceEnvelope"), dict) else {}
    return {
        "stage": stage.get("name"),
        "powerBudget": stage.get("powerBudget"),
        "parentDamage": stage.get("sourceDamage"),
        "suggestedDamage": stage.get("derivedDamage"),
        "rarity": stage.get("rarity"),
        "valueCopper": stage.get("value"),
        "suggestedUseTimeTicks": stage.get("useTime"),
        "broadEnvelope": envelope,
        "rule": "These are broad balance bounds, not a weapon archetype and not permission for code to rewrite the design.",
    }


def build_llm_author_payload(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    corridor = _balance_corridor(a, b)
    payload = {
        "priorityHeader": planner_priority_header_for_llm(),
        "recipeKey": key,
        "parents": {
            "A": {"packet": raw_parent_card_for_llm(a), "canonical": copy.deepcopy(ca)},
            "B": {"packet": raw_parent_card_for_llm(b), "canonical": copy.deepcopy(cb)},
        },
        "balanceCorridor": corridor,
        "runtimeCapabilityContract": engine_runtime_capability_contract_for_llm(a, b, corridor),
        "requiredJsonShape": author_item_prompt_shape_card(),
        "runtimeContractSchema": RUNTIME_CONTRACT_SCHEMA,
        "selfCheck": [
            "all refs exist and target kinds match",
            "one item_body and no duplicate exclusive input",
            "every spawned entity has explicit spawn/lifetime/hitbox/collision",
            "moving entities have exactly one movement/controller",
            "event graph is acyclic and within depth/count limits",
            "every gameplay claim is backed by calls/bindings",
            "no family/archetype/semantic default is requested",
            "no unsupported vanilla useAmmo/PickAmmo behaviour is claimed",
        ],
    }
    chars = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    if chars > PLANNER_PROMPT_LIMIT_CHARS:
        raise ValueError(
            f"honest low-level Author payload is {chars} chars, above configured {PLANNER_PROMPT_LIMIT_CHARS}; "
            "raise the configured limit rather than hiding capabilities"
        )
    return payload


def planner_prompt_usability_report(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    payload = build_llm_author_payload(a, b, ca, cb, key)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    catalog_names = [row["fn"] for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]]
    return {
        "schema": "infini.low-level-author-prompt-usability.v1",
        "ok": len(encoded) <= PLANNER_PROMPT_LIMIT_CHARS and set(catalog_names) == set(CAPABILITY_REGISTRY),
        "chars": len(encoded),
        "limit": PLANNER_PROMPT_LIMIT_CHARS,
        "headroom": PLANNER_PROMPT_LIMIT_CHARS - len(encoded),
        "visibleCapabilities": len(catalog_names),
        "missingCapabilities": sorted(set(CAPABILITY_REGISTRY) - set(catalog_names)),
        "extraCapabilities": sorted(set(catalog_names) - set(CAPABILITY_REGISTRY)),
        "containsWeaponMacro": any(
            name in encoded
            for name in (
                "perform_" + "melee_attack",
                "fire_" + "ranged_weapon",
                "cast_" + "magic_weapon",
                "deploy_" + "sentry",
                "shoot_" + "projectile",
            )
        ),
        "containsFamilyRouter": "runtimeFamily" in encoded or "weaponFamily" in encoded,
    }


__all__ = [
    "COMBAT_EXECUTOR_RESULT_KIND_RULE",
    "PLANNER_PROMPT_LIMIT_CHARS",
    "PLANNER_PROMPT_MIN_HEADROOM_CHARS",
    "VISIBLE_ENGINE_FUNCTIONS",
    "authored_int",
    "authored_num",
    "authored_str",
    "authored_weapon_damage",
    "build_llm_author_payload",
    "concise_terraria_tick_guide_for_llm",
    "engine_runtime_capability_contract_for_llm",
    "llm_category_without_router",
    "normalize_behavior_toy_fields",
    "normalize_llm_attack_shape",
    "normalize_runtime_authoring_fields",
    "planner_priority_header_for_llm",
    "planner_prompt_usability_report",
    "runtime_value",
    "sharp_engine_fn_catalog_for_llm",
    "terraria_tick_guide_for_llm",
]
