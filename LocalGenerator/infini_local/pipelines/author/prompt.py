from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    compact_capability_catalog,
    author_parameter_shape,
)
from infini_local.core.runtime_authoring.capability_registry import (
    runtime_authoring_prompt_field_guide,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_MEANINGS, DAMAGE_CLASS_TOKENS, ITEM_USE_STYLE_MEANINGS, ITEM_USE_STYLE_TOKENS,
)
from infini_local.pipelines.author.item_contract import AUTHOR_DESIGN_QUALITY_RULE, AUTHOR_STATUS_COMPOSITION_RULE, RUNTIME_ROW_SHAPE_RULE, author_item_prompt_shape_card, primary_entity_llm_invariant
from infini_local.pipelines.combine_balance import stat_profile_for
from infini_local.pipelines.context.stats import parent_stat_context

from infini_local.pipelines.context.cards import (
    NATIVE_SOURCE_REFERENCE_RULE, raw_parent_card_for_llm, parent_context_for_stage,
)
from infini_local.core.item_identity_tools import item_field
from infini_local.pipelines.pipeline_runtime_constants import LLM_ITEM_RAW_KEYS


# Engineering character guard, not a model token limit: complete compact JSON
# dossiers include parent-local source effects and source-derived ammo variants.
# Preserve literal tooltips, accepted graphs and capabilities; never clip to fit.
PLANNER_PROMPT_LIMIT_CHARS = 300_000
PLANNER_PROMPT_MIN_HEADROOM_CHARS = 1_000
COMBAT_EXECUTOR_RESULT_KIND_RULE = (
    "Choose a concrete item identity and play experience freely. Express its implementation through explicit entities, input bindings, "
    "movement/controllers, damage, collision, lifecycle and event links from the catalog, not a weapon-family runtime selector."
)
VISIBLE_ENGINE_FUNCTIONS = tuple(sorted(name for name, capability in CAPABILITY_REGISTRY.items() if capability.author_visible))


def concise_terraria_tick_guide_for_llm() -> dict[str, str]:
    """Author units, raw-source distinction and engine-specific quantization."""
    return {
        "nativeSourceReferences": NATIVE_SOURCE_REFERENCE_RULE,
        "time": "Seconds resolve to the nearest world tick (60/s), half-tick ties upward. Positive effects that round to zero are rejected. immunity.localCooldown and projectile-update counters remain counts.",
        "distance": "World distances use blocks; Tiles also means blocks. 1 block = 16 world pixels.",
        "speed": "Physical speed/acceleration use blocks/s and blocks/s^2; angular rates use radians/s. The engine applies the target's updatesPerTick conversion. Retention/lerp/multiplier controls keep their declared per-update meaning.",
        "scope": "Author cards use player-facing units; raw parent facts and compiled wire retain engine units. Pixel geometry and normalized UV/grip coordinates retain their own units. Texture resolution is independent of rendered size and collision geometry.",
        "vanillaScaleReference": "Ordinary unmounted player: 20x42-pixel collision box; base run speed 11.25 blocks/s; normal jump initial upward velocity about 18.79 blocks/s.",
        "spread": "radians; total span",
    }


def source_interpretation_for_llm() -> dict[str, str]:
    """Interpret observations without turning source metadata into mechanics."""
    return {
        "progression": "Inventory entries are current observations; fallback examples are illustrative. Acquisition/progression facts establish tier, not rarity or value alone.",
        "ammunition": (
            "weapon_item.shoot_field is a native field, not an observed fired shot, even under effectiveProjectile. "
            "Ammo damage contributes to a compatible launcher, including when its projectile is replaced; "
            "ammo useTime does not set the launcher's cadence. Weapon-ammo configurations describe separate cases."
        ),
        "inventoryPassives": "dropSeedsIfInInventory is the native inventory passive implemented by collect_seeds.",
    }


def planner_priority_header_for_llm() -> list[str]:
    return [AUTHOR_DESIGN_QUALITY_RULE]


def _source_path_objects(packet: Mapping[str, Any], path: str) -> list[Mapping[str, Any]]:
    """Read the exact declared namespace; [] visits only that named array."""
    values: list[Any] = [packet]
    for part in path.split("."):
        is_array = part.endswith("[]")
        key = part[:-2] if is_array else part
        next_values: list[Any] = []
        for value in values:
            if not isinstance(value, Mapping) or key not in value:
                continue
            child = value[key]
            if is_array:
                if isinstance(child, list):
                    next_values.extend(child)
            else:
                next_values.append(child)
        values = next_values
    return [value for value in values if isinstance(value, Mapping)]


def source_wire_units_for_llm(
    parent_packets: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Registry reading aid, optionally limited to exact present parent paths.

    Final paths supply the scope; a bare legacy leaf name cannot establish its
    units. Boolean projections are excluded; alternative paths explain units, not original Author choices.
    """
    scopes: dict[tuple[str, str, tuple[tuple[str, Any], ...]], dict[str, list[str]]] = {}
    if parent_packets is not None:
        # Match the stage-visible source representation. Native numeric facts
        # already expressed as explicit value/unit objects need no wire math;
        # accepted generated-parent wire remains unchanged by this projection.
        parent_packets = [{**packet, "raw": parent_stat_context(dict(packet.get("raw") or {}))}
                          for packet in parent_packets]

    def leaves(spec: Any, path: str, conditions: tuple[tuple[str, Any], ...] = ()):
        conditions = (*conditions, *spec.wire_literals.items())
        if spec.alternatives:
            for variant in spec.alternatives:
                yield from leaves(variant, path, conditions)
        elif spec.kind == "object":
            for name, child in spec.properties.items():
                yield from leaves(child, f"{path}.{name}", conditions)
        elif spec.kind in {"integer", "number"}:
            yield path, spec, conditions

    def has_field(container: Mapping[str, Any], field_path: str, *, numeric: bool = False) -> bool:
        parent, _, leaf = field_path.rpartition(".")
        owners = _source_path_objects(container, parent) if parent else [container]
        return any(leaf in owner and (not numeric or type(owner[leaf]) in {int, float}) for owner in owners)

    for capability in CAPABILITY_REGISTRY.values():
        numeric = [leaf for name, parameter in capability.params.items() for leaf in leaves(parameter, name)]
        readings: dict[str, set[tuple[Any, ...]]] = {}
        for _, spec, _ in numeric:
            readings.setdefault(spec.wire_name, set()).add((spec.wire_offset, spec.wire_multiplier,
                spec.wire_divisor, spec.wire_updates_power, spec.units))
        for author_path, spec, conditions in numeric:
            # Different laws can store different physical quantities in the
            # same native leaf. Keep their declared discriminator, never
            # infer a law or collapse incompatible unit conversions.
            condition = tuple(sorted(conditions)) if len(readings[spec.wire_name]) > 1 else ()
            projection = spec.wire_projection_card()
            field_path = projection["wireName"]
            if not field_path or spec.wire_enum or spec.wire_boolean_true_value is not None:
                continue
            # The existing canonical projection owns both ratio terms and
            # the target-update exponent; no capability-name unit table.
            offset = spec.wire_offset
            reading = (f"source - {offset}" if offset > 0 else f"source + {abs(offset)}") if offset else "source"
            if projection["divisor"] != 1:
                reading += f" * {projection['divisor']}"
            power = projection["updatesPerTickPower"]
            if power:
                reading += " * updatesPerTick" + (f"^{power}" if power != 1 else "")
            if projection["multiplier"] != 1:
                reading += f" / {projection['multiplier']}"
            suffix = "." + field_path
            for path in capability.final_wire_paths:
                if not path.endswith(suffix):
                    continue
                root = path[:-len(suffix)]
                roots = [f"raw.generatedParent.{root}"]
                if root == "gameplay" and field_path in LLM_ITEM_RAW_KEYS:
                    roots.append("raw.item")
                for source in roots:
                    fields = scopes.setdefault((source, capability.name, condition), {})
                    entry = [author_path, reading, spec.units]
                    previous = fields.get(field_path)
                    if previous is not None:
                        if previous[1:] != entry[1:]:
                            raise ValueError("one wire field has incompatible unit readings in declared variants")
                        entry[0] = " | ".join(sorted(set(previous[0].split(" | ")) | {author_path}))
                    fields[field_path] = entry
    scope_rows = []
    for (source, fn, condition), fields in scopes.items():
        if parent_packets is not None:
            containers = [row for packet in parent_packets for row in _source_path_objects(packet, source)]
            containers = [row for row in containers if all(
                any(owner.get(path.rsplit(".", 1)[-1]) == expected for owner in (
                    _source_path_objects(row, path.rsplit(".", 1)[0]) if "." in path else [row]))
                for path, expected in condition)]
            fields = {name: reading for name, reading in fields.items()
                      if any(has_field(row, name, numeric=source == "raw.item") for row in containers)}
        if fields:
            scope_rows.append({"source": source, "fn": fn, **({"when": dict(condition)} if condition else {}), "fields": fields})
    return {
        "readingRule": (
            "Paths start at each parent packet; [] visits that array. Field keys are relative to the named source container. "
            "Apply sourceToAuthor only to the stated source, fn and matching when discriminators; source alone means unchanged magnitude. "
            "For update-scaled values, updatesPerTick = collision.extraUpdates + 1 on the same entity. "
            "Unlisted fields or absent update context have no supplied conversion. Alternative authorParam paths share a unit reading."
        ),
        "fieldColumns": ["authorParam", "sourceToAuthor", "authorUnits"],
        "scopes": scope_rows,
    }


def descendant_spawn_budget_for_llm() -> str:
    """Shared execution meaning, not a required concurrency design."""
    return (
        "Projectile descendants share 32 successful child spawns over an activation's lifetime; child death does not refund them. "
        "Failed/cancelled reservations are refunded. descendant_limit instead uses pending/live slots released at retirement; "
        "nested pools retain ancestor pools and lifetime ledgers. Item-body periodic uses a per-dispatch budget."
    )


def runtime_units_for_llm(*, include_source_units: bool = True) -> dict[str, Any]:
    """The same registry-owned unit and binding reading guide for Author/Repair."""
    guide = runtime_authoring_prompt_field_guide()
    return {
        "paramNotation": guide["paramNotation"],
        "playerFacingUnits": concise_terraria_tick_guide_for_llm(),
        **({"sourceWireUnits": source_wire_units_for_llm()} if include_source_units else {}),
        "bindingTarget": guide["bindingTarget"],
        "descendantSpawnBudget": descendant_spawn_budget_for_llm(),
    }


def _share_consumer_constraints(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Share literal storage/projection rules, including nested numeric shapes.

    Labels are packet-local references, not a parallel table of numeric rules.
    A new registry rule receives a new definition rather than a guessed profile.
    """
    profiles: dict[str, dict[str, Any]] = {}
    labels: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("consumerConstraint", "x-infini-consumerConstraint",
                        "projectionConstraints", "x-infini-authorProjection"):
                constraint = value.get(key)
                if not isinstance(constraint, dict):
                    continue
                identity = json.dumps(constraint, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                if identity not in labels:
                    label = f"numeric{len(labels) + 1}"
                    labels[identity] = label
                    profiles[label] = constraint
                value[key] = labels[identity]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(cards)
    return profiles


def sharp_engine_fn_catalog_for_llm(*, include_source_units: bool = True) -> dict[str, Any]:
    # Registry cards retain their canonical fields; only missing execution facts
    # are attached to the relevant presentation card.
    field_guide = runtime_authoring_prompt_field_guide()
    field_guide["types"] = {name: author_parameter_shape(schema) for name, schema in field_guide["types"].items()}
    field_guide["descendantSpawnBudget"] = descendant_spawn_budget_for_llm()
    field_guide["sourceInterpretation"] = source_interpretation_for_llm()
    field_guide["statusEffects"] = AUTHOR_STATUS_COMPOSITION_RULE
    if include_source_units:
        field_guide.update(runtime_units_for_llm())

    field_guide["sourceValues"] = "Native Item.damage=-1 is a sentinel, not the damage or cadence of a wired tile attack."
    field_guide["projectileMotion"] = (
        "since_release/since_return clocks start at their latch. "
        "Source projectile identity, arrow flags and aiStyle do not execute native AI here."
    )
    field_guide["damageClass"] = {
        "builtInTokens": list(DAMAGE_CLASS_TOKENS), "meaningByToken": dict(DAMAGE_CLASS_MEANINGS),
        "nativeManaPayment": "Native integer truncation can make cheap spells cost zero even with a positive mana-cost coefficient. The coefficient floor 0.1 is not a minimum of 1 mana.",
        "scope": "Parent damageClass=none is source-only. Modded tokens use the exact parent-backed ModName/ClassName.",
    }
    field_guide["itemUseStyle"] = {
        "builtInTokens": list(ITEM_USE_STYLE_TOKENS), "meaningByToken": dict(ITEM_USE_STYLE_MEANINGS),
        "scope": "item_use.useStyle selects held-item/player-arm animation during active use. Select input bindings and executable effects separately.",
    }
    entities = [row.prompt_card() for row in ENTITY_KIND_REGISTRY.values()]
    for entity in entities:
        if entity["kind"] == "item_body":
            entity["constructionMeaning"] = "Exactly one item_body."
    inputs = [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()]
    actions = [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()]
    events = [row.author_prompt_card() for row in EVENT_KIND_REGISTRY.values()]
    capabilities = compact_capability_catalog()
    target_groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for card in capabilities:
        target_groups.setdefault(tuple(card["targets"]), []).append(card)
    target_sets: dict[str, list[str]] = {}
    for targets, cards in target_groups.items():
        if len(cards) < 2 or len(json.dumps(targets, separators=(",", ":"))) < 48:
            continue
        reference = "k" + str(len(target_sets))
        target_sets[reference] = list(targets)
        for card in cards:
            card["targetsRef"] = reference
            del card["targets"]
    if target_sets:
        field_guide["targetKindSets"] = target_sets
        field_guide["targetKindReadingRule"] = (
            "targetsRef refers to fieldGuide.targetKindSets."
        )
    field_guide["rowShapes"] = RUNTIME_ROW_SHAPE_RULE
    field_guide["consumerConstraints"] = _share_consumer_constraints(capabilities)
    field_guide["consumerConstraintReadingRule"] = (
        "At every parameter depth, consumerConstraint/projectionConstraints string values refer to "
        "fieldGuide.consumerConstraints; object values are literal rules."
    )
    for card in capabilities:
        if card["fn"] == "item_stats":
            card["constructionMeaning"] = "Combining placement with reusable spawn_entity/use_item_body (stackCost=0) requires maxStack=1."
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

def engine_runtime_capability_contract_for_llm() -> dict[str, Any]:
    return {
        "catalog": sharp_engine_fn_catalog_for_llm(include_source_units=False),
        "technicalNotes": concise_terraria_tick_guide_for_llm(),
    }


def _balance_corridor(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    stage = stat_profile_for(a, b)
    envelope = {key: dict(value) if isinstance(value, dict) else value
                for key, value in (stage.get("balanceEnvelope") or {}).items()}
    return {
        "authority": stage.get("authority"),
        "parentDamage": stage.get("sourceDamage"),
        "parentUseTimeTicks": [item_field(parent, "useTime", None) for parent in (a, b)],
        "parentProgressionFacts": stage.get("sourceNumericProgressionFacts"),
        "broadEnvelope": envelope,
        "rule": "Broad numeric bounds and observed parent values. Acquisition tier requires source progression facts, not rarity or value alone.",
    }


def runtime_program_invariants_for_llm() -> dict[str, Any]:
    return {
        "ids": "Entity, binding and call ids are globally unique and match catalog.fieldGuide.stableIdPattern.",
        "primaryEntityOwnership": primary_entity_llm_invariant(),
        "graphAndSpawnBudget": "Event references form an acyclic graph. From binding spawn roots, child depth <= 3; each event spawn count <= 12, and the static sum of spawn_on_event counts <= 32. For item-body on_use, count shared/both/other events plus the larger of primary-only and alternate-only subtotals. Runtime lifetime/concurrency accounting is explained in catalog.fieldGuide.descendantSpawnBudget.",
    }

def realization_execution_truth_for_llm() -> dict[str, str]:
    return {
        "nativeSourceReferences": NATIVE_SOURCE_REFERENCE_RULE,
        "statusEffects": AUTHOR_STATUS_COMPOSITION_RULE,
        "authority": "Optional realization.description, realization.playerExperience and realization.selfEvaluation are advisory context, never executable facts or required reports. Account for the chosen inputs, entities, subscribed events and terminal paths; report only behaviors supported by that exact topology, including their conditions and limits. A newly invented mechanic needs executable support, not parent precedent.",
        "placementUse": "The placement binding action performs the authored placement transaction and does not emit item_body.on_use; contactDamage must be false. If the result must both attack/use its body and place, author those as separate supported inputs. Never describe them as simultaneous on one placement binding.",
        "terminationEvents": "on_expire fires on natural lifetime expiry or explicit proximity_action action=expire_then_kill; an earlier kill does not emit it. on_kill fires on projectile termination, including collision death, penetration exhaustion, natural expiry and explicit kill actions such as arrival. A return trigger alone does not kill or seek. Only attached actions execute; termination does not imply an explosion. on_hit needs actual collision, not proximity alone; on_tile_collision means each collision. Area damage excludes the direct NPC only for on_hit/on_crit; on_kill has no remembered direct target.",
        "entityTopology": "Stationary kind alone does not fire. Explicit periodic spawn_on_event can shoot a referenced entity; target_and_fire separately provides NPC acquisition and timed shooting. An admitted free_projectile spawn creates independent projectiles; spawn.count is a batch count, not a live-copy cap. A hold binding does not spawn again while a matching entity remains alive. Do not claim a singleton minion/companion, minion-slot behavior or a per-owner cap unless explicitly authored.",
        "activeEquipment": "equipped is passive only. Any raised/used/placed/heal action requires a primary_use or alternate_use binding and must be described as requiring the item to be actively used rather than merely worn.",
        "stackCost": "For a non-placement active use, stackCost=1 consumes one whole generated item. There is no hidden charge counter; do not call whole-item consumption a charge unless an explicit supported state mechanic exists.",
        "durablePlacedForm": "When a hybrid has a reusable spawn_entity/use_item_body active use (stackCost=0), item_stats.maxStack must be 1: one durable unit switches between inventory and escrowed placed form. A one-shot non-placement use (stackCost=1) is not subject to this particular maxStack rule; choose its stack size deliberately.",
        "placementEscrow": "For a successful placement binding, the committed generated item is held by the world-persistent placement ledger and returned as that same generated item when the placed tile is destroyed. Describe it as placed/recoverable, not permanently consumed; it remains unavailable while placed.",
        "selfEvaluation": "Optional advisory self-check for the model's own use. No checklist, verdict, cited-id coverage or report replacement is required. Prose and self-evaluation never establish execution, reject gameplay or trigger Repair.",
    }


def build_llm_author_payload(a: dict[str, Any], b: dict[str, Any], key: str) -> dict[str, Any]:
    corridor = _balance_corridor(a, b)
    parents = {
        "A": {"packet": raw_parent_card_for_llm(a)},
        "B": {"packet": raw_parent_card_for_llm(b)},
    }
    payload = {
        "priorityHeader": planner_priority_header_for_llm(),
        "runtimeProgramInvariants": runtime_program_invariants_for_llm(),
        "runtimeCapabilityContract": engine_runtime_capability_contract_for_llm(),
        "requiredJsonShape": author_item_prompt_shape_card(),
        # Recipe-specific values stay last. JSON object order is not semantic,
        # but this preserves a large exact request prefix without hiding or
        # removing any Author capability.
        "recipeKey": key,
        **parent_context_for_stage(parents, stage="author"),
        "balanceCorridor": corridor,
        "sourceWireUnits": source_wire_units_for_llm([row["packet"] for row in parents.values()]),
    }
    chars = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    if chars > PLANNER_PROMPT_LIMIT_CHARS:
        raise ValueError(
            f"honest low-level Author payload is {chars} chars, above configured {PLANNER_PROMPT_LIMIT_CHARS}; "
            "raise the configured limit rather than hiding capabilities"
        )
    return payload


def planner_prompt_usability_report(a: dict[str, Any], b: dict[str, Any], key: str) -> dict[str, Any]:
    payload = build_llm_author_payload(a, b, key)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    catalog_names = [row["fn"] for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]]
    expected_names = set(VISIBLE_ENGINE_FUNCTIONS)
    return {
        "schema": "infini.low-level-author-prompt-usability.v1",
        "ok": len(encoded) <= PLANNER_PROMPT_LIMIT_CHARS and set(catalog_names) == expected_names,
        "chars": len(encoded),
        "limit": PLANNER_PROMPT_LIMIT_CHARS,
        "headroom": PLANNER_PROMPT_LIMIT_CHARS - len(encoded),
        "visibleCapabilities": len(catalog_names),
        "missingCapabilities": sorted(expected_names - set(catalog_names)),
        "extraCapabilities": sorted(set(catalog_names) - expected_names),
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
]
