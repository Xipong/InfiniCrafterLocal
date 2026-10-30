from __future__ import annotations

import copy
import json
import re
from typing import Any

from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables
from infini_local.pipelines.native_attack_behavior_view import _PROGRAM_FIELDS, _ROW_FIELDS, ordered_attack_context

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    generated_data_of,
    item_field,
    name_of,
)
from infini_local.pipelines.parent_context_pipeline import (
    _compact_keep,
    _compact_raw_value,
    _dedupe_projectile_profile,
    _raw_section_dict,
    compact_ammo_profile,
    compact_item_raw_for_llm,
    compact_projectile_profile,
    compact_vanilla_flags_for_llm,
    effective_projectile_profile_of,
    projectile_profile_of,
)

# LLM parent packet owner. Extraction lives in parent_context_pipeline; identity
# primitives come directly from their defining module. No derived-card alternative.

NATIVE_SOURCE_REFERENCE_RULE = (
    "Read-only native source values may be shared as {sourceSameAs:N}: read the complete value "
    "at nativeSourceFacts[N] in this same dossier, expanding recursively. These are exact repetitions, "
    "not inferred mechanics or Author values. Literal tooltips and accepted generatedParent packets stay inline."
)


def share_exact_native_parent_facts(parents: dict[str, Any]) -> dict[str, Any]:
    """Intern exact repeated native JSON; keep every value in this same dossier.

    Scalar kinds/presence, source/scope and list order/multiplicity are unchanged.
    Literal tooltips and complete accepted generated packets are never interned.
    """
    counts: dict[str, int] = {}
    indices: dict[str, int] = {}
    shared: list[Any] = []
    literal_keys = {"tooltipLines", "tooltipSource", "generatedParent"}

    def contains_literal(value: Any) -> bool:
        if isinstance(value, dict):
            return bool(literal_keys.intersection(value)) or any(contains_literal(child) for child in value.values())
        return isinstance(value, list) and any(contains_literal(child) for child in value)

    def candidate(value: Any) -> str | None:
        if not isinstance(value, (dict, list, str)) or contains_literal(value):
            return None
        if isinstance(value, dict) and ("sameAs" in value or "sourceSameAs" in value):
            return None
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return encoded if len(encoded) >= 128 else None

    def count(value: Any) -> None:
        key = candidate(value)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
        if isinstance(value, dict):
            for name, child in value.items():
                if name not in literal_keys:
                    count(child)
        elif isinstance(value, list):
            for child in value:
                count(child)

    def children(value: Any) -> Any:
        if isinstance(value, dict):
            return {name: copy.deepcopy(child) if name in literal_keys else visit(child)
                    for name, child in value.items()}
        if isinstance(value, list):
            return [visit(child) for child in value]
        return copy.deepcopy(value)

    def visit(value: Any) -> Any:
        key = candidate(value)
        if key is not None and counts[key] > 1:
            if key not in indices:
                index = indices[key] = len(shared)
                shared.append(None)
                shared[index] = children(value)
            return {"sourceSameAs": indices[key]}
        return children(value)

    for row in parents.values():
        raw = row.get("packet", {}).get("raw", {})
        if "generatedParent" not in raw:
            count(raw)
    result = copy.deepcopy(parents)
    for row in result.values():
        raw = row.get("packet", {}).get("raw", {})
        if "generatedParent" not in raw:
            # Keep the native raw section map itself; intern only its values.
            row["packet"]["raw"] = {name: visit(value) for name, value in raw.items()}
    return {"parents": result, **({"nativeSourceFacts": shared} if shared else {})}

_FORBIDDEN_DERIVED_PACKET_KEYS = frozenset({
    "behaviorDigest", "mechanicalHint", "semantics",
    "canonical", "tags", "headNoun", "primaryCategory", "classifier", "class",
    "hardTags", "softTags", "shapeAnchors", "visualAnchors", "modifiers",
})


def _strip_derived_packet_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            # This optional native observation has its own producer-owned
            # vocabulary. A nested source member named e.g. class/semantics is
            # not a derived parent hint and must not be rewritten or removed.
            key: copy.deepcopy(item) if key == "attackReference" else _strip_derived_packet_fields(item)
            for key, item in value.items()
            if key not in _FORBIDDEN_DERIVED_PACKET_KEYS
        }
    if isinstance(value, list):
        return [_strip_derived_packet_fields(item) for item in value]
    return value

def _native_sprite_reference_for_llm(value: Any) -> dict[str, Any]:
    """Copy loaded texture/UI-frame facts, never a collider or inferred display size."""
    if not isinstance(value, dict) or value.get("source") != "TextureAssets.Item":
        return {}
    width, height = value.get("textureWidthPx"), value.get("textureHeightPx")
    if any(type(dimension) is not int or not 1 <= dimension <= 2_147_483_647 for dimension in (width, height)):
        return {}
    observation = {"source": value["source"], "textureWidthPx": width, "textureHeightPx": height}
    frame = value.get("currentFrame")
    if isinstance(frame, dict) and frame.get("source") in ("texture_bounds", "draw_animation"):
        numbers: list[Any] = [frame.get(key) for key in ("xPx", "yPx", "widthPx", "heightPx")]
        x, y, w, h = numbers
        if (all(type(number) is int for number in (x, y, w, h))
                and x >= 0 and y >= 0 and w > 0 and h > 0
                and x + w <= width and y + h <= height
                and (frame["source"] != "texture_bounds" or (x, y, w, h) == (0, 0, width, height))):
            observation["currentFrame"] = {key: frame[key] for key in ("source", "xPx", "yPx", "widthPx", "heightPx")}
    return copy.deepcopy(observation)


# Accepted appearance only: omit PNG paths, URLs, image-job/status/score data and
# derived classifications. These values are copied, never interpreted as design.
_PARENT_VISUAL_FIELDS = (
    "role", "assetMode", "visualProjectRef", "prompt", "imagePrompt", "negativePrompt",
    "silhouette", "visualIdentity", "palette", "preferredCanvasSize", "renderSizePx",
    "forwardAngleDegrees", "inventoryScale", "worldScale", "scale", "grip",
    "drawOffsetX", "drawOffsetY", "accessoryMount", "equipOverlayPrompt",
)


def _accepted_visual_facts(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    facts = {key: copy.deepcopy(value[key]) for key in _PARENT_VISUAL_FIELDS if key in value}
    size = facts.get("renderSizePx")
    if "renderSizePx" in facts and not (type(size) is int and 1 <= size <= 512):
        facts.pop("renderSizePx")
    return facts


def raw_parent_card_for_llm(item: dict[str, Any], *, include_visual_reference: bool = False) -> dict[str, Any]:
    """Compact parent card for the LLM.

    The packet contains raw source fields or exact accepted generated runtime facts.
    It never adds code-derived semantics, behavior digests, categories or tags.
    Visual consumers may opt into read-only accepted appearance and calibration:
    loaded native texture/UI-frame pixels or generated root/entity identity,
    silhouette, palette, grip, canvas/axis and scales. Missing facts stay unknown;
    no appearance becomes a gameplay choice or required child dimension.
    """
    item_raw = compact_item_raw_for_llm(item)
    cross_mod_identity = {
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "fullName": str(item_field(item, "fullName", "")),
        "shootProjectileFullName": str(item_field(item, "shootProjectileFullName", "")),
    }
    cross_mod_identity = {k: v for k, v in cross_mod_identity.items() if _compact_keep(v)}
    card: dict[str, Any] = {
        "name": name_of(item),
        "internalName": str(item_field(item, "internalName", "")),
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "raw": {"item": item_raw},
    }
    if cross_mod_identity:
        card["raw"]["crossModIdentity"] = cross_mod_identity
    vanilla_flags = compact_vanilla_flags_for_llm(item)
    if vanilla_flags:
        card["raw"]["vanillaFlags"] = vanilla_flags
    gd = generated_data_of(item)
    if include_visual_reference and not isinstance(item.get("generatedData"), dict):
        sprite_reference = _native_sprite_reference_for_llm(item.get("spriteReferenceRaw"))
        if sprite_reference:
            card["raw"]["spriteReference"] = sprite_reference
    direct: dict[str, Any] = {}
    effective: dict[str, Any] = {}
    ammo: dict[str, Any] = {}
    if not gd:
        direct = compact_projectile_profile(projectile_profile_of(item))
        effective = compact_projectile_profile(effective_projectile_profile_of(item))
        ammo = compact_ammo_profile(item)
    if direct:
        card["raw"]["directProjectile"] = direct
    if effective:
        card["raw"]["effectiveProjectile"] = effective

    if ammo:
        if direct:
            _dedupe_projectile_profile(card["raw"], "effectiveProjectile", "directProjectile", direct)
            _dedupe_projectile_profile(ammo, "projectileRaw", "directProjectile", direct)
            _dedupe_projectile_profile(ammo, "weaponShootFieldProjectileRaw", "directProjectile", direct)
        elif effective:
            _dedupe_projectile_profile(ammo, "projectileRaw", "effectiveProjectile", effective)
            _dedupe_projectile_profile(ammo, "weaponShootFieldProjectileRaw", "effectiveProjectile", effective)
        if ammo:
            card["raw"]["ammo"] = ammo
    elif direct:
        _dedupe_projectile_profile(card["raw"], "effectiveProjectile", "directProjectile", direct)
    runtime_probe = _raw_section_dict(item, "runtimeProbeRaw")
    if runtime_probe:
        card["raw"]["runtimeProbe"] = _compact_raw_value(runtime_probe)
    if isinstance(gd, dict) and gd:
        runtime_raw = dict_get_ci(gd, "runtimeProgram", {})
        runtime_raw = runtime_raw if isinstance(runtime_raw, dict) else {}
        summary_raw = dict_get_ci(gd, "generatedParentSummary", {})
        runtime = copy.deepcopy(runtime_raw)
        summary = summary_raw if isinstance(summary_raw, dict) else {}
        # Read-only identity projection, not authoring/lowering: preserve every
        # accepted mechanical value, binding/event ID, zero, false and empty list.
        # Appearance has a separate Visual-only handoff below; never let it
        # become Author context or replace exact mechanics with a prose summary.
        for entity in runtime.get("entities") or []:
            if isinstance(entity, dict):
                entity.pop("visual", None)
        generated_parent = {"runtimeProgram": runtime}
        for key in ("id", "recipeKey", "gameplay", "accessory", "armor"):
            value = dict_get_ci(gd, key)
            if value is not None:
                generated_parent[key] = copy.deepcopy(value)
        if summary:
            generated_parent["summary"] = {key: copy.deepcopy(summary.get(key)) for key in (
                "schema", "name", "identity", "description", "playerExperience",
            ) if _compact_keep(summary.get(key))}
        if include_visual_reference:
            visual = _accepted_visual_facts(dict_get_ci(gd, "visual", {}))
            if visual:
                generated_parent["visual"] = visual
            # Exact entity IDs and kinds remain alongside their own accepted
            # appearance; do not select one parent entity or fill inherited data.
            for source, entity in zip(runtime_raw.get("entities") or [], runtime.get("entities") or []):
                if isinstance(source, dict) and isinstance(entity, dict):
                    appearance = _accepted_visual_facts(source.get("visual"))
                    if appearance:
                        entity["visual"] = appearance
        card["raw"]["generatedParent"] = generated_parent
    # Do not send section bookkeeping or token-byte metadata to the LLM; the raw object keys are enough.
    return _strip_derived_packet_fields({k: v for k, v in card.items() if _compact_keep(v)})

_BRIEF_PROPERTIES = (
    "damage", "damageClass", "crit", "knockback", "useTime", "useAnimation", "channel",
    "autoReuse", "consumable", "material", "maxStack", "value", "rare", "ammo", "useAmmo", "manaCost", "defense",
    "accessory", "healLife", "healMana", "lifeRegen", "pickPower", "axePower", "hammerPower",
    "createTile", "createWall", "bait", "fishingPole",
)
_BRIEF_PROJECTILE = (
    "friendly", "hostile", "tileCollide", "penetrate", "ownerHitCheck",
    "usesLocalNPCImmunity", "localNPCHitCooldown", "extraUpdates",
)
_BRIEF_RULE = (
    "Briefs are selected literal source facts, not a parent role, inherited design or complete behavior. "
    "Values retain the source units of their packet.raw fields, not Author parameter units. "
    "Missing facts remain unknown; source observations and color writes do not prove execution, final "
    "appearance, target count or DPS. parents contains the stage-relevant technical reference."
)


def _context_literals(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float)) or (
        isinstance(value, list) and all(_context_literals(child) for child in value))


def _known_context_row(row: Any) -> bool:
    if not isinstance(row, dict) or not set(row) <= _ROW_FIELDS | {"step"}:
        return False
    for key, value in row.items():
        if key in {"expression", "receiver", "call", "scope", "kind", "id", "op"} and not isinstance(value, str):
            return False
        if key == "orderedSourceUses":
            if not isinstance(value, list) or not all(_known_context_row(child) for child in value):
                return False
        elif key == "arguments":
            if not isinstance(value, dict) or not all(isinstance(child, str) for child in value.values()):
                return False
        elif not _context_literals(value):
            return False
    return True


def _known_context_program(program: Any) -> bool:
    if not isinstance(program, dict) or not set(program) <= _PROGRAM_FIELDS | {"identitySelection", "geometryRule"}:
        return False
    for key, value in program.items():
        if key in {"observations", "predicates"}:
            if not isinstance(value, list) or not all(_known_context_row(row) for row in value):
                return False
        elif key == "dependencies":
            if not isinstance(value, dict) or not all(_known_context_row(row) for row in value.values()):
                return False
        elif key == "symbols":
            if not isinstance(value, dict) or not all(isinstance(symbol, str) for symbol in value.values()):
                return False
        elif key == "predicateSources":
            if not isinstance(value, list) or not all(_known_context_program(row) for row in value):
                return False
        elif key == "identityWindows":
            if not isinstance(value, list) or any(not isinstance(row, dict) or not set(row) <= {
                    "field", "literal", "guardOffset"} or not all(_context_literals(v) for v in row.values()) for row in value):
                return False
        elif key == "identitySelection":
            if not isinstance(value, dict) or not set(value) <= {"forCapturedIdentity", "scope", "fullMethodCapture"}:
                return False
            for name, child in value.items():
                if name == "fullMethodCapture":
                    if not isinstance(child, dict) or not set(child) <= {"coverage", "unresolved"} or not all(
                            _context_literals(v) for v in child.values()):
                        return False
                elif not _context_literals(child):
                    return False
        elif key == "geometryRule":
            if not isinstance(value, dict) or not set(value) <= {
                    "kind", "inputs", "forwardTip", "orderedPoints", "accept", "rectangleEdges", "scope",
                    "offset", "angle", "boundaries", "numeric"} or not all(_context_literals(v) for v in value.values()):
                return False
        elif not _context_literals(value):
            return False
    return True


def known_attack_context_schema(source: Any) -> bool:
    """Admit stage-specific omission only for the current behavior envelope.

    A future sibling could reference a graph that this stage would remove. Keep
    such references literal instead of guessing their dependencies or meaning.
    """
    fields = {"source", "version", "identityPredicates", "scope", "units", "motionDispatch", "motion",
              "collision", "draw", "positionIntegration", "coverage", "admission", "expressionNotation",
              "behaviorView", "presentationScope"}
    if (not isinstance(source, dict) or not set(source) <= fields
            or source.get("source") != "read_only_native_attack_source"
            or type(source.get("version")) is not int or source["version"] != 1):
        return False
    view = source.get("behaviorView")
    if (not isinstance(view, dict) or set(view) != {"version", "scope"}
            or type(view.get("version")) is not int or view["version"] != 1 or not isinstance(view["scope"], str)):
        return False
    for field in ("scope", "units", "expressionNotation", "presentationScope"):
        if field in source and not isinstance(source[field], str):
            return False
    for field, keys in (("identityPredicates", {"Projectile.type", "Projectile.aiStyle"}),
                        ("coverage", {"proved", "unresolved", "boundaries"}),
                        ("admission", {"ownerHitCheck", "ownerHitCheckDistance", "usesOwnerMeleeHitCD", "scope"})):
        if field in source:
            value = source[field]
            if not isinstance(value, dict) or not set(value) <= keys or not all(_context_literals(v) for v in value.values()):
                return False
    for field in ("motionDispatch", "collision", "positionIntegration"):
        if field in source and not _known_context_program(source[field]):
            return False
    if "motion" in source:
        motion = source["motion"]
        if not isinstance(motion, dict) or set(motion) != {"programs"} or not isinstance(motion["programs"], list):
            return False
        for program in motion["programs"]:
            if not _known_context_program(program) or not isinstance(program.get("observations"), list):
                return False
    if "draw" in source:
        draw = source["draw"]
        if not isinstance(draw, dict) or set(draw) != {"dispatch", "programs"} or not _known_context_program(draw["dispatch"]):
            return False
        programs = draw["programs"]
        if not isinstance(programs, list):
            return False
        if any(isinstance(program, dict) and "renderLayerView" in program for program in programs):
            if _draw_character(draw) is None:
                return False
        elif not all(_known_context_program(program) for program in programs):
            return False
    return True


def _draw_character(draw: Any) -> dict[str, Any] | None:
    """Read certified presentation motifs, never interpret a renderer as mechanics.

    The deliberately lossy Author view is admitted only for the known semantic
    render-layer schema. Unknown/future drawing stays in the technical packet.
    Color writes are source observations, not evaluated/final palette values.
    """
    if not isinstance(draw, dict) or set(draw) != {"dispatch", "programs"}:
        return None
    dispatch = draw["dispatch"]
    if (not isinstance(dispatch, dict) or not set(dispatch) <= {
            "method", "observations", "dependencies", "predicates", "symbols", "unresolved",
            "identityWindows", "identitySelection", "coverage"}):
        return None
    programs = draw["programs"]
    if not isinstance(programs, list) or not programs:
        return None
    known = {"method", "renderLayerView", "spriteLayerDefaults", "layers", "definitions",
             "conditions", "setup", "unresolved"}
    kinds: list[str] = []
    writes: list[dict[str, Any]] = []
    for program in programs:
        if not isinstance(program, dict):
            return None
        view = program.get("renderLayerView")
        if (not set(program) <= known or not isinstance(view, dict)
                or set(view) != {"version", "scope"} or type(view.get("version")) is not int or view["version"] != 1
                or not isinstance(view["scope"], str)
                or not isinstance(program.get("layers"), list)
                or not isinstance(program.get("conditions"), list)
                or not isinstance(program.get("setup"), list)
                or not isinstance(program.get("definitions"), dict)):
            return None
        defaults = program.get("spriteLayerDefaults")
        if (not isinstance(defaults, dict) or not set(defaults) <= {
                "texture", "position", "origin", "effects", "layerDepth", "renderer"}
                or not all(isinstance(value, str) for value in defaults.values())):
            return None
        if any(not isinstance(row, dict) or not set(row) <= {"id", "op", "inputs", "successors", "step"}
               or not _known_context_row(row)
               for row in program.get("conditions", [])):
            return None
        if any(not isinstance(row, dict) or not set(row) <= {"step", "block", "requiredPredicates", "expression"}
               or not _known_context_row(row)
               for row in program.get("setup", [])):
            return None
        for layer in program["layers"]:
            if not isinstance(layer, dict) or layer.get("kind") not in {"sprite", "nativeStarSparkle"}:
                return None
            if not set(layer) <= {"kind", "step", "block", "requiredPredicates", "rotation", "scale", "frame", "tint",
                                  "opacity", "dir", "drawpos", "drawColor", "shineColor", "flareCounter",
                                  "fadeInStart", "fadeInEnd", "fadeOutStart", "fadeOutEnd", "fatness"}:
                return None
            if not all(_context_literals(value) for value in layer.values()):
                return None
            if layer["kind"] not in kinds:
                kinds.append(layer["kind"])
        for definition in program["definitions"].values():
            if (not isinstance(definition, dict) or not set(definition) <= {
                    "expression", "scope", "orderedSourceUses", "block", "requiredPredicates", "step"}
                    or not _known_context_row(definition)):
                return None
            for row in definition.get("orderedSourceUses", []):
                if not isinstance(row, dict) or not set(row) <= {"expression", "block", "requiredPredicates", "step"}:
                    return None
                if re.fullmatch(
                        r"writeRGB\([A-Za-z][A-Za-z0-9_]*,\d+,\d+,\d+\)", str(row.get("expression", ""))):
                    writes.append({"method": program.get("method"), **copy.deepcopy(row)})
    return {
        "sourceRenderKinds": kinds,
        "sourceColorWrites": writes,
        "scope": "Presentation motifs only; conditional source writes, not final colors. Layer order, "
                 "multipliers, fades, transforms, loops and GPU extent are not evaluated here. "
                 "Full native drawing remains in the capture and Visual/VFX context.",
    }


def parent_context_for_stage(parents: dict[str, Any] | list[dict[str, Any]], *, stage: str) -> dict[str, Any]:
    """Same brief layout for every ingredient, followed by technical source facts.

    No name/category routing or chosen inheritance roles. Author omits only the
    recognized presentation-only render-layer graph, retaining native gameplay
    graphs, conditions, admission and extraction gaps. Other stages retain it.
    This is model-context presentation, never a mutation of captured parents.
    """
    if stage not in {"author", "visual", "vfx"}:
        raise ValueError(f"Unknown parent context stage: {stage}")
    is_list = isinstance(parents, list)
    result = copy.deepcopy(dict(enumerate(parents)) if is_list else parents)
    briefs: dict[str, Any] = {}
    for label, row in result.items():
        packet = row.get("packet", {})
        raw = packet.get("raw", {})
        item = raw.get("item", {})
        brief = {
            "identity": {key: copy.deepcopy(packet[key]) for key in ("name", "internalName", "sourceMod") if key in packet},
            "properties": {key: copy.deepcopy(item[key]) for key in _BRIEF_PROPERTIES if key in item},
            "behavior": {},
            "appearance": {},
        }
        if "tooltipLines" in item:
            brief["identity"]["tooltipLines"] = copy.deepcopy(item["tooltipLines"])
        generated = raw.get("generatedParent")
        if isinstance(generated, dict):
            brief["behavior"] = copy.deepcopy(generated.get("summary", {}))
            brief["appearance"] = copy.deepcopy(generated.get("visual", {}))
        projectile = raw.get("directProjectile", {})
        if isinstance(projectile, dict) and "sameAs" not in projectile:
            brief["behavior"]["projectileFields"] = {
                key: copy.deepcopy(projectile[key]) for key in _BRIEF_PROJECTILE if key in projectile}
            if "light" in projectile:
                brief["appearance"]["light"] = copy.deepcopy(projectile["light"])
        for section in ("directProjectile", "effectiveProjectile"):
            profile = raw.get(section, {})
            attack = profile.get("attackReference") if isinstance(profile, dict) else None
            if not isinstance(attack, dict):
                continue
            try:
                source = unpack_attack_tables(attack)
            except (TypeError, ValueError):
                # An unfamiliar reference is evidence, not permission to drop it.
                continue
            if (source.get("source") != "read_only_native_attack_source"
                    or type(source.get("version")) is not int or source["version"] != 1):
                continue
            brief["behavior"][section] = {"coverage": copy.deepcopy(source.get("coverage", {}))}
            observation_kinds = []
            motion = source.get("motion", {})
            programs = motion.get("programs") if isinstance(motion, dict) else None
            for program in programs if isinstance(programs, list) else []:
                observations = program.get("observations") if isinstance(program, dict) else None
                for observation in observations if isinstance(observations, list) else []:
                    kind = observation.get("kind") if isinstance(observation, dict) else None
                    if isinstance(kind, str) and kind not in observation_kinds:
                        observation_kinds.append(kind)
            if observation_kinds:
                brief["behavior"][section]["sourceMotionObservationKinds"] = observation_kinds
            appearance = _draw_character(source.get("draw")) if known_attack_context_schema(source) else None
            if appearance is not None:
                brief["appearance"][section] = appearance
                if stage == "author":
                    del source["draw"]
                    source["presentationScope"] = "Native draw layer instructions omitted for Gameplay Author; " \
                        "source presentation motifs are in parentBriefs. Gameplay source is unchanged."
                    profile["attackReference"] = pack_attack_tables(source)
            if stage == "author" and known_attack_context_schema(source):
                profile["attackReference"] = ordered_attack_context(source)
        if "spriteReference" in raw:
            brief["appearance"]["spriteReference"] = copy.deepcopy(raw["spriteReference"])
        briefs[label] = brief
    # Author already has the shared-fact transport contract. Presentation stages
    # keep their existing literal wire rather than acquiring another decoding seam.
    technical = share_exact_native_parent_facts(result) if stage == "author" else {"parents": result}
    context = {"parentBriefRule": _BRIEF_RULE, "parentBriefs": briefs, **technical}
    if is_list:
        context["parents"] = list(context["parents"].values())
        context["parentBriefs"] = list(briefs.values())
    return context


__all__ = ["raw_parent_card_for_llm", "share_exact_native_parent_facts", "parent_context_for_stage",
           "known_attack_context_schema", "NATIVE_SOURCE_REFERENCE_RULE"]
