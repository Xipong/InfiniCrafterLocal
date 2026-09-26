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
    primary_entity_self_check,
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
        "Return one complete bounded runtimeProgram in this single response; no tool loop and no second design pass.",
        "Directly compose low-level entities, bindings, capabilities and event links. Never classify the item into sword/bow/staff/sentry for execution.",
        "category is UI/equipment metadata only. Deterministic code never infers gameplay from names, parent tooltip, tags, category or parent prose; use source-backed parent facts only to author explicit runtimeProgram mechanics.",
        "Every movement, attachment/entity kind, damage path, input binding, lifecycle, targeting and child action must be explicit.",
        "Use only capabilities present in capabilityCatalog. Catalog membership is not a recommendation; select only mechanics belonging to your authored design. Do not describe gameplay that has no exact runtimeProgram backing.",
        "Parent useAmmo/ammo-candidate facts are read-only Terraria context. No ammo-consuming weapon capability exists yet: author explicit projectile entities and never claim vanilla PickAmmo/stack consumption unless a future catalog capability provides the full pipeline.",
        "Preserve literal parent physics where useful: a workbench may remain a literal workbench attached to a blade. Do not replace it with a vague wooden theme.",
        "Do not add a mandatory weird twist. Novelty comes from the authored composition itself, not an unrelated gimmick.",
        "Multiple independent actions are legal when they belong to the authored composition; do not add an unrelated action merely because the catalog exposes it.",
        "All ids are stable lowercase snake_case and globally unique across entities, bindings, and calls.",
        "Exactly one item_body is required. All other entities need explicit spawn, lifetime, hitbox, collision and, where moving, movement/controller calls.",
        "Primary/alternate inputs are exclusive. Sequence extra behaviour through supported events rather than competing bindings.",

        "Before answering, follow runtimeProgramInvariants.structureCheck for references, producers, budgets and required params; then check complete selfEvaluation coverage.",
    ]


def sharp_engine_fn_catalog_for_llm() -> dict[str, Any]:
    return {
        "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        "authoringSchema": RUNTIME_PROGRAM_SCHEMA,
        "entityKinds": [row.prompt_card() for row in ENTITY_KIND_REGISTRY.values()],
        "inputs": [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()],
        "bindingActions": [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()],
        "placementInputRoles": "If placement is selected: pure placeable uses place_item on primary_use; hybrid uses non-placement primary_use and place_item on alternate_use. The placement action references one configure_placeable on the same item_body via placementCallId, with stackCost=1 and contactDamage=false. Only accepted placement escrows the generated item until its tile is broken. Parent tileId alone does not establish a source placeStyle or exact tile behavior.",
        "events": [row.prompt_card() for row in EVENT_KIND_REGISTRY.values()],
        "fieldGuide": runtime_authoring_prompt_field_guide(),
        "limits": {"entities": 12, "bindings": 8, "calls": 48, "childDepth": 3, "eventSpawnsPerActivation": 32},
        "capabilities": compact_capability_catalog(),
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
            "name": "initial_design_draft",
            "field": "concept",
            "meaning": "A non-binding first sketch of intended player actions. It anchors design and enables diagnosis, but semantic drift from it never rejects the craft.",
        },
        {
            "name": "executable_gameplay_program",
            "field": "runtimeProgram",
            "meaning": "The only executable gameplay authority: exact entities, input bindings, calls, parameters, events, and references consumed by the compiler/runtime.",
        },
        {
            "name": "final_gameplay_report",
            "field": "realization.description + realization.playerExperience",
            "meaning": "The same Author's plain-language report of what the executable program actually lets the player do, not a repetition of the initial draft.",
        },
        {
            "name": "same_pass_self_evaluation",
            "field": "realization.selfEvaluation",
            "meaning": "The last block of the same model response: independently compare draft versus program, then program versus final report, using exact runtime references.",
        },
    ]


def runtime_program_invariants_for_llm() -> dict[str, Any]:
    return {
        "primaryEntityOwnership": primary_entity_llm_invariant(),
        "exclusiveInputs": {
            "maxBindingsPerInput": 1,
            "inputs": sorted(
                name for name, spec in INPUT_KIND_REGISTRY.items() if spec.exclusive
            ),
            "authoringProcedure": "Choose one action root per exclusive input. Never author separate use_item_body and spawn_entity binding rows with the same input; sequence additional behavior through a supported event or another input.",
            "configureItemUseRule": "configure_item_use supplies item-use parameters for whichever single action root you choose. It does not require a use_item_body binding. Presence of item_body also does not require use_item_body.",
        },
        "bindingUseTransactions": {
            "singleOwner": "Every binding owns one complete usePolicy containing action, stackCost and contactDamage. No call or global field may shadow those decisions.",
            "bodyDamageLane": "contactDamage=true requests item-body contact on an active use, even with spawn_entity (no second binding); it does not select primaryEntityId or held ownership. Actual melee contact needs configure_item_use.disableMeleeHitbox=false and no ammo category: either can set Item.noMelee and prevent item-body hits/on_hit/on_crit despite contactDamage=true. Projectile damage comes from set_projectile_damage on its entity; item-body contact uses configure_item_stats.damage. Placement and non-use inputs require contactDamage=false.",
            "catalogNeutrality": "An available action is not a design suggestion. Omit actions that do not belong to the authored composition.",
        },
        "structureCheck": {
            "order": "Choose exact input/action/target from catalog bindingActions.targets; add the item_body and any explicitly spawned or referenced entities with their required calls; then attach event calls to their source entity. Check each selected capability's targets, acceptedEvents, requires, exclusiveGroup and params before writing the report.",
            "eventSources": "For item_body, non-placement primary_use/alternate_use emits on_use regardless of whether the binding action targets the body or a spawned entity; placement emits no on_use. item_body on_hit/on_crit need an actual enabled body hitbox and NPC contact, not just contactDamage=true. item_body periodic gameplay events run while held (HoldItem), not just while equipped. Projectile events belong to the projectile that emits them; on_expire is not every death. An event call's target is its event source, not necessarily the binding action's target. Event availability is checked by the validator; do not invent events from names or proximity alone.",
            "referencesAndBudgets": "For spawn_entity_on_event.entity and target_and_fire.shotEntity, use each param card's reference.targetKinds (projectile kinds, not item_body); the referenced entity must exist, cannot be the source itself and must not form a cycle. target_and_fire needs a source allowed by its targets card and a referenced shot; references do not create a direct binding. Check graph depth <= catalog.limits.childDepth from binding spawn roots, each event spawn count <= 12, and the static sum of all spawn_entity_on_event counts <= catalog.limits.eventSpawnsPerActivation (32). Repeating periodic/controller spawns also consume the runtime activation budget; do not promise an unbounded or guaranteed shot count.",
            "completeCalls": "For EVERY selected call, supply all keys in that capability's params except optional:true, including required fields with zero/false/empty values when those are deliberately chosen and allowed. Check each card's type, enum, bounds, references and requires; conditional required fields (for example periodTicks on periodic) still apply. A neutral value is not an automatic default: choose meaningful fields explicitly from the design/source facts, or omit the unnecessary call; never guess a missing tile/wall/buff ID.",
            "useAndEquipment": "useTimeTicks is the use cadence; useAnimationTicks is the use animation duration. autoReuse repeats active use while input is held; channel keeps that use active for channelled entities. hold is a separate while-selected HoldItem lane, not an extra primary_use binding or worn equipment effect. charge_then_release requires channel=true and an explicit spawned charged entity: it stays non-damaging until release, scales with bounded chargeTicks, then uses authored release velocity/movement; releaseTiming is a held-item presentation hint, not a gameplay release trigger. equipped executes passive effects while worn, not active use or item_body periodic; matching armor-set bonuses execute from the head only when a matching head/body/legs set is worn. Author at most one equipped binding: runtime looks up the first, so do not rely on multiple equipped bindings to compose bonuses.",
        },
        "damageClass": {
            "builtInTokens": list(DAMAGE_CLASS_TOKENS),
            "meaningByToken": dict(DAMAGE_CLASS_MEANINGS),
            "scope": "Selects damage/stat inheritance and class effects; it does not create movement, minions, ammo consumption or mana costs. Author those separately.",
            "moddedTokenShape": "ModName/ClassName copied from parent facts",
            "otherTokensAllowed": False,
            "sourceSentinelRule": "Parent fact damageClass=none is read-only source data and is never a valid runtime token; choose one exact built-in token or an exact parent-backed ModName/ClassName.",
        },
        "itemUseStyle": {
            "builtInTokens": list(ITEM_USE_STYLE_TOKENS),
            "meaningByToken": dict(ITEM_USE_STYLE_MEANINGS),
            "scope": "configure_item_use.useStyle selects the held-item/player-arm animation during active use only. It does not independently guarantee a functional tool/use mechanic, projectile, damage, food, drink, golf, mowing or lamp effect. Author the input binding and executable capabilities/effects separately; style names are not weapon presets.",
        },
        "capabilityParams": {
            "exactCardMatch": True,
            "sourceSentinelRule": "Do not copy Terraria sentinel -1 into a runtime param whose capability card minimum is 0; use an allowed value or omit the unnecessary capability.",
        },
        "realizationExecutionTruth": realization_execution_truth_for_llm(),
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
        "selfCheck": [
            primary_entity_self_check(),
            "all refs exist and binding/call target kinds match their registry cards",
            "one item_body and exactly one binding row at most owns each runtimeProgramInvariants.exclusiveInputs input; never pair use_item_body plus spawn_entity on one input",
            "every damageClass is a listed built-in token or exact parent-backed ModName/ClassName; parent sentinel none is forbidden and the Author must choose the exact canonical token",
            "every call params object exactly matches its capability card; no below-minimum source sentinel such as -1 is copied",
            "for every selected call, every required param and every exact requires row is satisfied on the required target",
            "every binding has one structurally complete usePolicy transaction; contactDamage is an independent item-body lane and may coexist with spawn_entity on the same active-use binding without changing primaryEntityId/held ownership",
            "every spawned entity has explicit spawn/lifetime/hitbox/collision",
            "moving entities have exactly one movement/controller",
            "apply runtimeProgramInvariants.structureCheck to event sources, reference kinds and static/runtime spawn budgets",
            "write realization as the literal final gameplay report, then write realization.selfEvaluation LAST using runtimeProgramInvariants.realizationExecutionTruth",
            "selfEvaluation.planVsProgram.actionChecks must cover every concept.plannedPlayerActions row and every executable input/event lane with exact-id evidence, marking lanes absent from the draft as added; concept is non-binding and changed/uncertain drift never rejects the craft",
            "selfEvaluation.programVsReport.behaviorChecks must independently cover every executable input/entity/event lane against description/playerExperience; never copy planVsProgram's verdict and never declare aligned from prose similarity alone",
            "every actionCheck and behaviorCheck cites exact existing entity/binding/call ids, gives its own result and reason, and uses uncertain instead of pretending to understand an engine parameter",
            "no family/archetype/semantic default is requested",
            "no unsupported vanilla useAmmo/PickAmmo behaviour is claimed",
        ],
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
