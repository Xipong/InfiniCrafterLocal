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
)
from infini_local.core.runtime_authoring.capability_registry import (
    runtime_authoring_prompt_field_guide,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_MEANINGS, DAMAGE_CLASS_TOKENS, ITEM_USE_STYLE_MEANINGS, ITEM_USE_STYLE_TOKENS,
)
from infini_local.pipelines.author_item_contract import (
    RUNTIME_ROW_SHAPE_RULE,
    author_item_prompt_shape_card,
    primary_entity_llm_invariant,
)
from infini_local.pipelines.combine_balance import stat_profile_for
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.core.item_identity_tools import item_field
from infini_local.pipelines.pipeline_runtime_constants import LLM_ITEM_RAW_KEYS


# Engineering character guard, not a model token limit: exactly 220000 Unicode
# characters in the complete compact JSON dossier. Preserve both source tooltips
# and accepted generated graphs; never clip them to fit.
PLANNER_PROMPT_LIMIT_CHARS = 220_000
PLANNER_PROMPT_MIN_HEADROOM_CHARS = 1_000
COMBAT_EXECUTOR_RESULT_KIND_RULE = (
    "Do not choose a sword/bow/staff/sentry family. Choose explicit entities, input bindings, "
    "movement/controllers, damage, collision, lifecycle and event links from the catalog."
)
VISIBLE_ENGINE_FUNCTIONS = tuple(sorted(CAPABILITY_REGISTRY))


def concise_terraria_tick_guide_for_llm() -> dict[str, str]:
    """Shared Author units and source-grounded scale, not an extra design stage."""
    return {
        "time": (
            "Write world durations/intervals in decimal seconds. The engine has 60 world ticks = 1 second; "
            "lowering resolves seconds to the nearest world tick, half-tick ties upward. "
            "Explicit zero stays zero; a positive effect may not round to disabled zero. "
            "Raw immunity.localCooldown and explicitly named projectile-update counters are counts, not seconds."
        ),
        "distance": (
            "Write gameplay world distances in blocks. 1 Terraria block (tile) = 16 world pixels. "
            "rangeTiles/radiusTiles already mean blocks, including blink rangeTiles: do not divide again. "
            "Read whether each card means radius, diameter, origin offset or distance to a target center."
        ),
        "speed": (
            "Write gameplay speeds in blocks/s, physical accelerations in blocks/s^2 and declared angular rates in radians/s. "
            "The canonical lowering accounts for the affected target's updatesPerTick; do not manually rescale Author values. "
            "Initial speed, flat bonuses, sprint floors and event impulses are distinct, not guaranteed final movement or jump height. "
            "Ammo speed is a base native launch contribution; the eventual projectile can have its own update rate. "
            "Dimensionless retention/lerp/multiplier controls retain their declared per-update meaning."
        ),
        "scope": (
            "Use each Author card's declared units; the compiled wire and raw parent facts keep engine units. "
            "Pixel-labelled collision and local sprite geometry remain pixels; 16 world pixels = 1 block. "
            "Texture texels/canvas dimensions remain texture pixels; normalized UV/grip coordinates remain normalized: do not divide by 16. "
            "Texture resolution alone is not rendered world size, collision size or reach."
        ),
        "vanillaScaleReference": (
            "Vanilla scale reference, not a balance ceiling: an ordinary standing unmounted player's collision box is "
            "20x42 world pixels (1.25x2.625 blocks). Without gear/buffs or special terrain, nominal base run speed is "
            "11.25 blocks/s; a normal jump assigns about 18.79 blocks/s upward velocity. "
            "The 15-update held-jump counter is not a distance. Jump height/range depend on hold, gravity and horizontal motion; "
            "these are not a measured height/range or a limit on authored mechanics."
        ),
        "spread": "radians; total span",
    }


def planner_priority_header_for_llm() -> list[str]:
    return [
        "category is UI/equipment metadata only; never select a weapon archetype for execution. Deterministic code never infers gameplay from names, parent tooltip, tags, category or parent prose; author every mechanic explicitly in runtimeProgram.",
        "Use only capabilities present in runtimeCapabilityContract.catalog.capabilities.",
        "Source provenance constrains factual claims about the parents, not the mechanics you may invent. Create new purposeful mechanics from catalog primitives inspired by both parent identities; neither parent needs to have performed them. Do not present invented effects as observed parent abilities. No forced twist or unrelated gimmick is required.",
        "Use source tempo when available and useful to the composition; make deviations intentional.",
        "All ids are stable lowercase snake_case and globally unique across entities, bindings, and calls.",
    ]


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
    scopes: dict[tuple[str, str], dict[str, list[str]]] = {}

    def leaves(spec: Any, path: str):
        if spec.alternatives:
            for variant in spec.alternatives:
                yield from leaves(variant, path)
        elif spec.kind == "object":
            for name, child in spec.properties.items():
                yield from leaves(child, f"{path}.{name}")
        elif spec.kind in {"integer", "number"}:
            yield path, spec

    def has_field(container: Mapping[str, Any], field_path: str) -> bool:
        parent, _, leaf = field_path.rpartition(".")
        owners = _source_path_objects(container, parent) if parent else [container]
        return any(leaf in owner for owner in owners)

    for capability in CAPABILITY_REGISTRY.values():
        for name, parameter in capability.params.items():
            for author_path, spec in leaves(parameter, name):
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
                        fields = scopes.setdefault((source, capability.name), {})
                        entry = [author_path, reading, spec.units]
                        previous = fields.get(field_path)
                        if previous is not None:
                            if previous[1:] != entry[1:]:
                                raise ValueError("one wire field has incompatible unit readings in declared variants")
                            entry[0] = " | ".join(sorted(set(previous[0].split(" | ")) | {author_path}))
                        fields[field_path] = entry
    scope_rows = []
    for (source, fn), fields in scopes.items():
        if parent_packets is not None:
            containers = [row for packet in parent_packets for row in _source_path_objects(packet, source)]
            fields = {name: reading for name, reading in fields.items()
                      if any(has_field(row, name) for row in containers)}
        if fields:
            scope_rows.append({"source": source, "fn": fn, "fields": fields})
    return {
        "readingRule": (
            "Paths are relative to each parent packet; [] means each entry in that exact container. "
            "Read a source number in the listed Author param's units using sourceToAuthor; source means unchanged magnitude. "
            "Dotted field keys are relative paths inside that exact source container. Only declared numeric projections are listed; "
            "no rule is implied for unlisted fields, boolean projections or a changed selector. "
            "For update-scaled readings, updatesPerTick is collision.extraUpdates + 1 of the same entity, never its emitter; "
            "if that context is absent, do not assume an update count. A list of alternative Author paths is a unit aid, "
            "not a branch reconstruction or permission to change the source. Use the exact scope and fn, never the bare field name. "
            "This is a unit explanation, not a bit-exact inverse for arbitrary floating-point values; "
            "do not rewrite source, round it or replace it with tooltip prose. Values still must satisfy the selected "
            "card's bounds/dependencies. This reading aid does not require an inherited ability for each new mechanic "
            "or authorize code-selected rebalancing, defaults or additional Repair permissions."
        ),
        "fieldColumns": ["authorParam", "sourceToAuthor", "authorUnits"],
        "scopes": scope_rows,
    }


def descendant_spawn_budget_for_llm() -> str:
    """Shared execution meaning, not a required concurrency design."""
    return (
        "Projectile periodic/event/controller producers share the activation's default "
        "32-successful-child-spawn lifetime allowance across descendants, unless the root explicitly "
        "selects set_descendant_concurrency. Child death does not refund that allowance: later spawn "
        "requests are refused after exhaustion even if the producer remains alive. Failed or cancelled "
        "reservations are refunded. An optional set_descendant_concurrency on the root instead uses "
        "pending/live descendant slots released at retirement; a nested pool retains every ancestor "
        "pool and ancestor lifetime ledger. Intentionally finite producers remain valid without this "
        "call. Describe the chosen finite or replenishable output honestly; an interval and long "
        "lifetime alone are not guaranteed successful shots. Owner/entity/depth limits still apply. "
        "This projectile lifetime ledger is not the item_body periodic clock's per-dispatch budget. "
        "Read-only Repair context does not authorize adding a pool."
    )


def runtime_units_for_llm() -> dict[str, Any]:
    """The same registry-owned unit and binding reading guide for Author/Repair."""
    guide = runtime_authoring_prompt_field_guide()
    return {
        "paramNotation": guide["paramNotation"],
        "playerFacingUnits": concise_terraria_tick_guide_for_llm(),
        "sourceWireUnits": source_wire_units_for_llm(),
        "bindingTarget": guide["bindingTarget"],
        "descendantSpawnBudget": descendant_spawn_budget_for_llm(),
    }


def _share_consumer_constraints(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Intern only literally equal metadata; no gameplay value is transformed.

    Labels are packet-local references, not a parallel table of numeric rules.
    A new registry rule receives a new definition rather than a guessed profile.
    """
    profiles: dict[str, dict[str, Any]] = {}
    labels: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("consumerConstraint", "x-infini-consumerConstraint"):
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
    field_guide["descendantSpawnBudget"] = descendant_spawn_budget_for_llm()
    if include_source_units:
        field_guide.update(runtime_units_for_llm())

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
        "Choose meaningful params from design/source facts or omit unnecessary calls. "
        "Never guess tile/wall/buff IDs or copy source sentinel -1 into a param whose card minimum is 0."
    )
    field_guide["projectileMotion"] = (
        "Decide the trajectory of every moving entity deliberately. move_straight has no falling arc; "
        "move_gravity_arc adds its explicit vertical velocity increment from the first projectile update. "
        "Source projectile identity, arrow flags and aiStyle do not execute native AI in a generated entity. "
        "Use observed source motion when provided; otherwise your domain knowledge may guide the authored "
        "choice, but is not a verified source measurement. A straight or altered shot remains legal when "
        "intentional and coherent with the concept. Do not accidentally promise ballistic motion while "
        "authoring constant velocity. No host-selected movement or weapon preset is supplied."
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
            entity["constructionMeaning"] = "Exactly one item_body."
        elif kind == "free_projectile":
            entity["constructionMeaning"] = "An admitted spawn creates independent projectiles, not a singleton minion/companion; no minion-slot behavior or per-owner cap is implied. configure_spawn.count is a batch count, not a live-copy cap. A hold binding does not spawn again while a matching entity remains alive."
    inputs = [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()]
    for row in inputs:
        if row["input"] == "hold":
            row["constructionMeaning"] = "While-selected HoldItem lane, not an extra primary_use or equipped/worn effect."
        elif row["input"] == "equipped":
            row["constructionMeaning"] = "Passive while worn, not active use or item_body periodic. At most one equipped binding: runtime uses the first. Matching armor-set effects run from the head only with matching head/body/legs equipped."
    actions = [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()]
    for action in actions:
        if action["action"] == "place_item":
            action["constructionMeaning"] = (
                "Pure placeable uses primary_use; hybrid uses non-placement primary_use and place_item on alternate_use. "
                "placementCallId references one configure_tile_placement or configure_wall_placement on the same item_body. "
                "Only accepted placement spends the stack and escrows this same generated item, unavailable while placed and returned when its tile breaks. "
                "No item_body.on_use or simultaneous attack on this placement binding. Parent tileId alone does not establish placeStyle or exact tile behavior."
            )
    events = [row.prompt_card() for row in EVENT_KIND_REGISTRY.values()]
    event_detail = {
        "on_hit": "Requires actual NPC collision/contact; item_body also needs enabled body hitbox, not merely contactDamage=true. Proximity alone is insufficient.",
        "on_crit": "Requires actual critical NPC contact; item_body needs enabled body hitbox.",
        "on_kill": "Projectile termination event, including collision death, penetration exhaustion, proximity detonation, natural expiry and ordinary return-to-owner completion or controller cancellation. Only explicitly attached actions execute; termination does not imply an explosion.",
        "on_tile_collision": "Emitted at each tile collision, including a bounce.",
        "periodic": "Periodic event calls require when={everyTicks:n}; n is an explicit integer from 6 to 3600. item_body periodic runs while held (HoldItem), not merely equipped.",
    }
    for event in events:
        if event["event"] in event_detail:
            event["constructionMeaning"] = event_detail[event["event"]]
    capabilities = compact_capability_catalog()
    field_guide["rowShapes"] = RUNTIME_ROW_SHAPE_RULE
    field_guide["consumerConstraints"] = _share_consumer_constraints(capabilities)
    field_guide["consumerConstraintReadingRule"] = (
        "Param consumerConstraint and nested shape x-infini-consumerConstraint name one complete rule "
        "in fieldGuide.consumerConstraints. The referenced precision, neutral and wireProjection constraints all apply."
    )
    for card in capabilities:
        if card["fn"] in {"target_and_fire", "spawn_entity_on_event"}:
            card["constructionMeaning"] = (
                "For projectile descendant production, see fieldGuide.descendantSpawnBudget: "
                "interval and entity lifetime do not guarantee sustained output."
            )
        elif card["fn"] == "present_placed_item_sprite":
            card["constructionMeaning"] = "Certified native scope: 16x16/256 cells max; unproved post-place actors or visual callbacks are refused before mutation."
        elif card["fn"] == "add_placed_light":
            card["constructionMeaning"] = "Independent explicit light; one center cell per committed native footprint, not player/held PNG or sprite heads. Certified 16x16/256 cells max; unproved post-place actors refused before mutation. Strength/color remain required; no default."
        elif card["fn"] == "charge_then_release":
            card["constructionMeaning"] = "Needs channel=true and an explicitly spawned charged entity; non-damaging until release, then bounded chargeSeconds scales authored release velocity/movement. customHeldSprite is presentation, not release trigger."
        elif card["fn"] == "configure_item_use":
            card["constructionMeaning"] = "Timing is owned by configure_item_stats.useTimeSeconds (cadence) and configure_item_stats.useAnimationSeconds (animation duration), not params of this call. Here autoReuse repeats active use while held, and channel keeps that use active."
        elif card["fn"] == "configure_item_stats":
            card["constructionMeaning"] = "Only an item with both a place_item binding and reusable spawn_entity/use_item_body use (stackCost=0) requires maxStack=1: one durable unit switches inventory/placed form. This rule does not limit stacks without placement or with only one-shot non-placement use (stackCost=1)."
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
        "rule": "These are broad numeric bounds and literal parent observations, not proof of acquisition tier or expected power, a semantic classifier, weapon archetype, or permission for code to rewrite the design.",
    }


def runtime_program_invariants_for_llm() -> dict[str, Any]:
    return {
        "primaryEntityOwnership": primary_entity_llm_invariant(),
        "graphAndSpawnBudget": "Event references form an acyclic graph. From binding spawn roots, child depth <= catalog.limits.childDepth (3); each event spawn count <= 12, and the static sum of spawn_entity_on_event counts <= catalog.limits.eventSpawnsPerActivation (32). Periodic/controller repetitions use a runtime activation budget: the default lifetime allowance does not replenish. Explicit set_descendant_concurrency replaces a root's descendant ledger with a replenishable live-slot pool; nested pools retain ancestor limits. Owner/entity/depth caps still apply; no successful shot count is guaranteed.",
    }

def realization_execution_truth_for_llm() -> dict[str, str]:
    return {
        "authority": "Optional realization.description, realization.playerExperience and realization.selfEvaluation are advisory context, never executable facts or required reports. Account for the chosen inputs, entities, subscribed events and terminal paths; report only behaviors supported by that exact topology, including their conditions and limits. A newly invented mechanic needs executable support, not parent precedent.",
        "placementUse": "The placement binding action performs the authored placement transaction and does not emit item_body.on_use; contactDamage must be false. If the result must both attack/use its body and place, author those as separate supported inputs. Never describe them as simultaneous on one placement binding.",
        "terminationEvents": "on_expire fires on natural lifetime expiry and move_proximity_missile proximity detonation; a kill before the final lifetime update does not emit it. on_kill fires on projectile termination, including collision death, penetration exhaustion, proximity detonation, natural expiry, ordinary return-to-owner completion and controller cancellation. Only explicitly attached actions execute. on_hit needs actual collision, not proximity alone; on_tile_collision means each collision. An on_expire effect is not guaranteed at an earlier final bounce/collision. Area damage excludes the direct NPC only for on_hit/on_crit; on_kill has no remembered direct target.",
        "entityTopology": "Stationary kind alone does not fire. Explicit periodic spawn_entity_on_event can shoot a referenced entity; target_and_fire separately provides NPC acquisition and timed shooting. An admitted free_projectile spawn creates independent projectiles; configure_spawn.count is a batch count, not a live-copy cap. A hold binding does not spawn again while a matching entity remains alive. Do not claim a singleton minion/companion, minion-slot behavior or a per-owner cap unless explicitly authored.",
        "activeEquipment": "equipped is passive only. Any raised/used/placed/heal action requires a primary_use or alternate_use binding and must be described as requiring the item to be actively used rather than merely worn.",
        "stackCost": "For a non-placement active use, stackCost=1 consumes one whole generated item. There is no hidden charge counter; do not call whole-item consumption a charge unless an explicit supported state mechanic exists.",
        "durablePlacedForm": "When a hybrid has a reusable spawn_entity/use_item_body active use (stackCost=0), configure_item_stats.maxStack must be 1: one durable unit switches between inventory and escrowed placed form. A one-shot non-placement use (stackCost=1) is not subject to this particular maxStack rule; choose its stack size deliberately.",
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
        "runtimeCapabilityContract": engine_runtime_capability_contract_for_llm(a, b),
        "requiredJsonShape": author_item_prompt_shape_card(),
        "diagnosticReport": {"selfEvaluation": realization_execution_truth_for_llm()["selfEvaluation"]},
        # Recipe-specific values stay last. JSON object order is not semantic,
        # but this preserves a large exact request prefix without hiding or
        # removing any Author capability.
        "recipeKey": key,
        "parents": parents,
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
    expected_names = set(CAPABILITY_REGISTRY)
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
