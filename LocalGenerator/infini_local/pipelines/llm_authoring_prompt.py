from __future__ import annotations

import json
from typing import Any

from infini_local.core.runtime_authoring import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    compact_capability_catalog,
)
from infini_local.core.runtime_authoring.capability_registry import (
    runtime_authoring_prompt_field_guide,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_MEANINGS, DAMAGE_CLASS_TOKENS, ITEM_USE_STYLE_MEANINGS, ITEM_USE_STYLE_TOKENS,
)
from infini_local.pipelines.author_item_contract import (
    author_item_prompt_shape_card,
    primary_entity_llm_invariant,
)
from infini_local.pipelines.combine_balance import stat_profile_for
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


PLANNER_PROMPT_LIMIT_CHARS = 96_000
PLANNER_PROMPT_MIN_HEADROOM_CHARS = 1_000
COMBAT_EXECUTOR_RESULT_KIND_RULE = (
    "Do not choose a sword/bow/staff/sentry family. Choose explicit entities, input bindings, "
    "movement/controllers, damage, collision, lifecycle and event links from the catalog."
)
VISIBLE_ENGINE_FUNCTIONS = tuple(sorted(CAPABILITY_REGISTRY))


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
        "Return one immutable response containing concept, executable runtimeProgram, and final realization with diagnostic selfEvaluation. There is no subsequent model or tool pass.",
        "Directly compose low-level entities, bindings, capabilities and event links. Never classify the item into sword/bow/staff/sentry for execution.",
        "category is UI/equipment metadata only. Deterministic code never infers gameplay from names, parent tooltip, tags, category or parent prose; use source-backed parent facts only to author explicit runtimeProgram mechanics.",
        "Every movement, attachment/entity kind, damage path, input binding, lifecycle, targeting and child action must be explicit.",
        "Use only capabilities present in capabilityCatalog. Catalog membership is not a recommendation; select only mechanics belonging to your authored design. Do not describe gameplay that has no exact runtimeProgram backing.",
        "Parent useAmmo/ammo-candidate facts are read-only Terraria context. No ammo-consuming weapon capability exists yet: author explicit projectile entities and never claim vanilla PickAmmo/stack consumption unless a future catalog capability provides the full pipeline.",
        "Preserve literal parent physics where useful: a workbench may remain a literal workbench attached to a blade. Do not replace it with a vague wooden theme.",
        "Do not add a mandatory weird twist. Novelty comes from the authored composition itself, not an unrelated gimmick.",
        "Multiple independent actions are legal when they belong to the authored composition; do not add an unrelated action merely because the catalog exposes it.",
        "All ids are stable lowercase snake_case and globally unique across entities, bindings, and calls.",
    ]


def sharp_engine_fn_catalog_for_llm() -> dict[str, Any]:
    # Registry cards retain their canonical fields; only missing execution facts
    # are attached to the relevant presentation card.
    field_guide = runtime_authoring_prompt_field_guide()
    field_guide["stackCost"] = (
        "For non-placement active use, stackCost=1 consumes one whole generated item (not ammo, projectile or a charge); "
        "stackCost=0 retains it, including reusable throws. Projectile return does not refund a consumed item."
    )
    field_guide["bindingTarget"] += (
        " Every binding owns one usePolicy with action, stackCost and contactDamage; no call/global shadows it. "
        "Actual item-body contact requires configure_item_use.disableMeleeHitbox=false and no ammo category: "
        "either may set Item.noMelee and suppress item_body on_hit/on_crit despite contactDamage=true. "
        "Item-body damage uses configure_item_stats.damage; projectile damage uses set_projectile_damage."
    )
    field_guide["referenceRules"] = (
        "Reference fields use their own targetKinds/allowSelf/graphEdge cards: an existing compatible entity, "
        "not a created-by-reference binding; graph edges cannot cycle. target_and_fire needs a source in its targets "
        "and an explicitly referenced shot entity."
    )
    field_guide["eventSource"] = (
        "Event call target is its emitting source, not necessarily the binding action target; "
        "use event sources/producers and call acceptedEvents. Names or proximity alone do not produce events."
    )
    field_guide["sourceValues"] = (
        "Neutral values are not defaults: choose meaningful params from design/source facts or omit unnecessary calls. "
        "Never guess tile/wall/buff IDs or copy source sentinel -1 into a param whose card minimum is 0."
    )
    field_guide["damageClass"] = {
        "builtInTokens": list(DAMAGE_CLASS_TOKENS), "meaningByToken": dict(DAMAGE_CLASS_MEANINGS),
        "scope": "Damage/stat inheritance and class effects only; no movement, minions, ammo consumption or mana cost. Parent damageClass=none is source-only, not a runtime token. Modded token is exact parent-backed ModName/ClassName; no other tokens.",
    }
    field_guide["itemUseStyle"] = {
        "builtInTokens": list(ITEM_USE_STYLE_TOKENS), "meaningByToken": dict(ITEM_USE_STYLE_MEANINGS),
        "scope": "configure_item_use.useStyle selects held-item/player-arm animation during active use only, not a functional tool/use mechanic, projectile, damage, food, drink, golf, mowing or lamp effect. Author the input binding and executable effects separately; style names are not weapon presets.",
    }
    entities = [row.prompt_card() for row in ENTITY_KIND_REGISTRY.values()]
    for entity in entities:
        kind = entity["kind"]
        if kind == "item_body":
            entity["constructionMeaning"] = "Exactly one item_body; configure_item_stats is required by requiredComponents. Not a projectile spawn."
        elif kind == "stationary_projectile":
            entity["constructionMeaning"] = "Use requiredComponents for spawn/lifetime/hitbox/collision and positionRequirement for a controller. Without target_and_fire and an explicitly referenced shot entity, this is stationary contact, not a firing turret/sentry."
        elif kind == "free_projectile":
            entity["constructionMeaning"] = "Use requiredComponents for spawn/lifetime/hitbox/collision and positionRequirement for movement. Each use spawns an independent projectile; no singleton minion/companion, minion-slot behavior or per-owner cap is implied."
        else:
            entity["constructionMeaning"] = "Use requiredComponents and positionRequirement for explicit spawn, lifetime, hitbox, collision and movement/controller ownership."
    inputs = [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()]
    for row in inputs:
        if row["input"] in ("primary_use", "alternate_use"):
            row["constructionMeaning"] = "One action root for this exclusive input; additional effects use supported events, not a second binding. configure_item_use configures that root, and item_body does not require use_item_body."
        elif row["input"] == "hold":
            row["constructionMeaning"] = "While-selected HoldItem lane, not an extra primary_use or equipped/worn effect."
        elif row["input"] == "equipped":
            row["constructionMeaning"] = "Passive while worn, not active use or item_body periodic. At most one equipped binding: runtime uses the first. Matching armor-set effects run from the head only with matching head/body/legs equipped."
    actions = [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()]
    for action in actions:
        if action["action"] == "place_item":
            action["constructionMeaning"] = (
                "Pure placeable uses primary_use; hybrid uses non-placement primary_use and place_item on alternate_use. "
                "placementCallId references one configure_placeable on the same item_body; stackCost=1 and contactDamage=false. "
                "Only accepted placement spends the stack and escrows this same generated item, unavailable while placed and returned when its tile breaks. "
                "No item_body.on_use or simultaneous attack on this placement binding. Parent tileId alone does not establish placeStyle or exact tile behavior."
            )
    events = [row.prompt_card() for row in EVENT_KIND_REGISTRY.values()]
    event_detail = {
        "on_use": "Emitted for non-placement primary_use/alternate_use regardless of action target (body or spawned entity); placement emits none.",
        "on_hit": "Requires actual NPC collision/contact; item_body also needs enabled body hitbox, not merely contactDamage=true. Proximity alone is insufficient.",
        "on_crit": "Requires actual critical NPC contact; item_body needs enabled body hitbox.",
        "on_expire": "Natural lifetime expiry and move_proximity_missile proximity detonation only; other early kills do not emit on_expire. A bouncing entity with only on_expire effects does not produce that effect at its final collision.",
        "on_kill": "Terminal event for collision death, penetration exhaustion, proximity detonation and natural expiry.",
        "on_tile_collision": "Emitted at each tile collision, including a bounce.",
        "periodic": "periodTicks is required on periodic event calls. item_body periodic runs while held (HoldItem), not merely equipped.",
    }
    for event in events:
        if event["event"] in event_detail:
            event["constructionMeaning"] = event_detail[event["event"]]
    capabilities = compact_capability_catalog()
    for card in capabilities:
        if card["fn"] == "charge_then_release":
            card["constructionMeaning"] = "Needs channel=true and an explicitly spawned charged entity; non-damaging until release, then bounded chargeTicks scales authored release velocity/movement. heldSpriteVisibilityHint is presentation, not release trigger."
        elif card["fn"] == "configure_item_use":
            card["constructionMeaning"] = "useTimeTicks is cadence, useAnimationTicks animation duration; autoReuse repeats active use while held, channel keeps that use active."
        elif card["fn"] == "configure_item_stats":
            card["constructionMeaning"] = "A hybrid with reusable spawn_entity/use_item_body use (stackCost=0) has maxStack=1: one durable unit moves between inventory and escrowed placed form. One-shot non-placement use (stackCost=1) is not subject to this maxStack rule."
    return {
        "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        "authoringSchema": RUNTIME_PROGRAM_SCHEMA,
        "entityKinds": entities,
        "inputs": inputs,
        "bindingActions": actions,
        "events": events,
        "fieldGuide": field_guide,
        "limits": {"entities": 12, "bindings": 8, "calls": 48, "childDepth": 3, "eventSpawnsPerActivation": 32},
        "capabilities": capabilities,
    }

def engine_runtime_capability_contract_for_llm(
    a: dict[str, Any],
    b: dict[str, Any],
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del a, b, envelope
    return {
        "principle": "The author composes the item. Deterministic code only type-checks, bounds, compiles and executes explicit choices.",
        "catalog": sharp_engine_fn_catalog_for_llm(),
        "technicalNotes": concise_terraria_tick_guide_for_llm(),
        "reportEvidenceRule": "Every selfEvaluation actionCheck/behaviorCheck cites exact existing runtimeProgram entity, binding, or call ids.",
        "literalSynthesisRule": "Keep concrete parent objects/parts literal when the concept uses them; do not code-normalize furniture into a material theme.",
    }


def _balance_corridor(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    stage = stat_profile_for(a, b)
    envelope = stage.get("balanceEnvelope") if isinstance(stage.get("balanceEnvelope"), dict) else {}
    return {
        "authority": stage.get("authority"),
        "powerBudget": stage.get("powerBudget"),
        "parentDamage": stage.get("sourceDamage"),
        "parentUseTimeTicks": stage.get("sourceFastestUseTime"),
        "parentProgressionFacts": stage.get("sourceNumericProgressionFacts"),
        "suggestedDamage": stage.get("derivedDamage"),
        "broadEnvelope": envelope,
        "rule": "These are broad source-numeric balance bounds, not a semantic classifier, weapon archetype, or permission for code to rewrite the design.",
    }


def gameplay_authoring_stages_for_llm() -> list[dict[str, str]]:
    """Plain names for the four causal sections of one Author response."""
    return [
        {
            "name": "initial_concept",
            "field": "concept",
            "meaning": "First, state the intended player actions to establish the design trajectory. This is non-binding; divergence from executable gameplay is diagnostic, not a rejection.",
        },
        {
            "name": "executable_gameplay_program",
            "field": "runtimeProgram",
            "meaning": "The only executable gameplay authority: exact entities, input bindings, calls, parameters, events, and references consumed by the compiler/runtime.",
        },
        {
            "name": "final_gameplay_report",
            "field": "realization.description + realization.playerExperience",
            "meaning": "The same Author's plain-language account of what the executable program lets the player do, not a repetition of the initial concept.",
        },
        {
            "name": "same_pass_self_evaluation",
            "field": "realization.selfEvaluation",
            "meaning": "Final diagnostic within the same immutable response: compare concept with the emitted program, and final report with the emitted program. This is interpretation, not execution evidence.",
        },
    ]


def runtime_program_invariants_for_llm() -> dict[str, Any]:
    return {
        "primaryEntityOwnership": primary_entity_llm_invariant(),
        "graphAndSpawnBudget": "Event references form an acyclic graph. From binding spawn roots, child depth <= catalog.limits.childDepth (3); each event spawn count <= 12, and the static sum of spawn_entity_on_event counts <= catalog.limits.eventSpawnsPerActivation (32). Periodic/controller repetitions also spend the runtime activation budget: no unbounded or guaranteed shot count.",
    }

def realization_execution_truth_for_llm() -> dict[str, str]:
    return {
        "authority": "realization.description, realization.playerExperience and realization.selfEvaluation are the final post-authoring report of the emitted runtimeProgram, not a repetition of the non-binding concept. Walk every input, entity, event and terminal path before writing them; report a behavior only when that exact topology executes it.",
        "placementUse": "The placement binding action performs the authored placement transaction and does not emit item_body.on_use; contactDamage must be false. If the result must both attack/use its body and place, author those as separate supported inputs. Never describe them as simultaneous on one placement binding.",
        "terminationEvents": "on_expire fires on natural lifetime expiry and also on move_proximity_missile proximity detonation; other early kills do not emit it. on_kill is the terminal event for collision death, penetration exhaustion, proximity detonation and natural expiry. on_hit needs actual collision, not proximity alone. on_tile_collision means each collision. A bounce-capable projectile with an effect only on on_expire does not guarantee that effect after its final collision; describe the exact event or wire the desired terminal path.",
        "entityTopology": "A stationary_projectile without target_and_fire plus an explicitly referenced shot entity is a stationary contact entity, not a firing turret/sentry. Each use of free_projectile creates another independent projectile; do not claim a singleton minion/companion, minion-slot behavior or a per-owner cap unless the emitted topology explicitly provides that bound.",
        "activeEquipment": "equipped is passive only. Any raised/used/placed/heal action requires a primary_use or alternate_use binding and must be described as requiring the item to be actively used rather than merely worn.",
        "stackCost": "For a non-placement active use, stackCost=1 consumes one whole generated item. There is no hidden charge counter; do not call whole-item consumption a charge unless an explicit supported state mechanic exists.",
        "durablePlacedForm": "When a hybrid has a reusable spawn_entity/use_item_body active use (stackCost=0), configure_item_stats.maxStack must be 1: one durable unit switches between inventory and escrowed placed form. A one-shot non-placement use (stackCost=1) is not subject to this particular maxStack rule; choose its stack size deliberately.",
        "placementEscrow": "For a successful placement binding, the committed generated item is held by the world-persistent placement ledger and returned as that same generated item when the placed tile is destroyed. Describe it as placed/recoverable, not permanently consumed; it remains unavailable while placed.",
        "selfEvaluation": "Write realization.selfEvaluation last. planVsProgram.actionChecks must cover every concept.plannedPlayerActions row and every executable input/event lane, cite exact runtimeProgram ids even when aligned, and mark a runtime lane with no draft counterpart as added; concept drift is diagnostic and never rejects the craft. programVsReport.behaviorChecks must separately cover every executable input/entity/event lane and compare it with description/playerExperience, again including aligned lanes. Do not produce a blanket aligned verdict: each row states its own result and reason. State intentionality for plan drift, and use uncertain when the program semantics are not understood.",
    }


def build_llm_author_payload(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    # Legacy deterministic/debug callers still provide ca/cb, but inferred
    # canonical/category/tag/head-noun data is never model-facing.
    _ = (ca, cb)
    corridor = _balance_corridor(a, b)
    payload = {
        "priorityHeader": planner_priority_header_for_llm(),
        "gameplayAuthoringStages": gameplay_authoring_stages_for_llm(),
        "runtimeProgramInvariants": runtime_program_invariants_for_llm(),
        "runtimeCapabilityContract": engine_runtime_capability_contract_for_llm(a, b),
        "requiredJsonShape": author_item_prompt_shape_card(),
        "diagnosticReport": {"selfEvaluation": realization_execution_truth_for_llm()["selfEvaluation"]},
        # Recipe-specific values stay last. JSON object order is not semantic,
        # but this preserves a large exact request prefix without hiding or
        # removing any Author capability.
        "recipeKey": key,
        "parents": {
            "A": {"packet": raw_parent_card_for_llm(a)},
            "B": {"packet": raw_parent_card_for_llm(b)},
        },
        "balanceCorridor": corridor,
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
    "build_llm_author_payload",
    "concise_terraria_tick_guide_for_llm",
    "engine_runtime_capability_contract_for_llm",
    "planner_priority_header_for_llm",
    "planner_prompt_usability_report",
    "sharp_engine_fn_catalog_for_llm",
    "terraria_tick_guide_for_llm",
]
