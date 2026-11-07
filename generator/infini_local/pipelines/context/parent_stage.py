"""Stage-owned read-only parent presentation and exact native fact sharing."""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from typing import Any

from infini_local.pipelines.context.stats import parent_stat_context
from infini_local.pipelines.context.attack_tables import pack_attack_tables, unpack_attack_tables
from infini_local.pipelines.context.attack_behavior import (
    _PROGRAM_FIELDS, _ROW_FIELDS, known_identity_alternatives, ordered_attack_context,
)
from infini_local.pipelines.context.csharp_source_view import (
    known_native_csharp_context, known_native_csharp_program, prune_native_csharp_records,
)
from infini_local.pipelines.context.native_references import known_projectile_references


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
    if known_native_csharp_program(program):
        return True
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
        elif key == "identityAlternatives":
            if not known_identity_alternatives(value):
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
    fields = {"source", "version", "identityPredicates", "scope", "units", "motionDispatch", "motionDispatchEffects", "motion",
              "collision", "draw", "positionIntegration", "coverage", "admission", "expressionNotation",
              "behaviorView", "presentationScope", "nativeCSharpSource", "nativeCSharpSourceReading"}
    if (not isinstance(source, dict) or not set(source) <= fields
            or source.get("source") != "read_only_native_attack_source"
            or type(source.get("version")) is not int or source["version"] != 1):
        return False
    if ("nativeCSharpSource" in source or "nativeCSharpSourceReading" in source) and not known_native_csharp_context(source):
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
    if "motionDispatchEffects" in source:
        effects = source["motionDispatchEffects"]
        if not isinstance(effects, list) or not all(_known_context_program(program) for program in effects):
            return False
    if "motion" in source:
        motion = source["motion"]
        if not isinstance(motion, dict) or set(motion) != {"programs"} or not isinstance(motion["programs"], list):
            return False
        for program in motion["programs"]:
            if not _known_context_program(program) or not (known_native_csharp_program(program)
                    or isinstance(program.get("observations"), list)):
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


def _stage_projectile_profiles(raw: dict[str, Any], *, related: bool) -> Iterator[tuple[str, dict[str, Any]]]:
    """Visit only declared projectile locations and recognized producer child links."""
    def profile_rows(profile: Any, path: str) -> Iterator[tuple[str, dict[str, Any]]]:
        if not isinstance(profile, dict) or profile.get("unavailable") is True or "sameAs" in profile:
            return
        yield path, profile
        if not related:
            return
        references = profile.get("referencedProjectiles")
        if known_projectile_references(references):
            for index, row in enumerate(references["references"]):
                yield from profile_rows(row.get("profile"), f"{path}.referencedProjectiles.references[{index}].profile")

    for section in ("directProjectile", "effectiveProjectile"):
        yield from profile_rows(raw.get(section), section)
    if not related:
        return
    ammo = raw.get("ammo")
    if isinstance(ammo, dict):
        for section in ("projectileRaw", "weaponShootFieldProjectileRaw"):
            yield from profile_rows(ammo.get(section), "ammo." + section)
        for section in ("nativeReplacementProjectileRaw", "playerInventoryProjectileRaw", "fallbackProjectileRaw"):
            profiles = ammo.get(section)
            if isinstance(profiles, list):
                for index, profile in enumerate(profiles):
                    yield from profile_rows(profile, f"ammo.{section}[{index}]")


def parent_context_for_stage(parents: dict[str, Any] | list[dict[str, Any]], *, stage: str) -> dict[str, Any]:
    """Same brief layout for every ingredient, followed by technical source facts.

    No name/category routing or chosen inheritance roles. Native mechanics source
    uses an explicit approximate Author view; full graphs remain diagnostic.
    Item-only, modded and unavailable captures retain their literal source facts
    when approximate source is absent. Visual, VFX and accepted generated packets
    keep their own contracts unchanged.
    This is model-context presentation, never a mutation of captured parents.
    """
    if stage not in {"author", "visual", "vfx"}:
        raise ValueError(f"Unknown parent context stage: {stage}")
    is_list = isinstance(parents, list)
    result = copy.deepcopy(dict(enumerate(parents)) if is_list else parents)
    briefs: dict[str, Any] = {}
    for label, row in result.items():
        packet = row.get("packet", {})
        raw = parent_stat_context(packet.get("raw", {}))
        if "raw" in packet:
            packet["raw"] = raw
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
        for section, profile in _stage_projectile_profiles(raw, related=stage == "author"):
            attack = profile.get("attackReference")
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
            programs = list(programs) if isinstance(programs, list) else []
            effects = source.get("motionDispatchEffects")
            if isinstance(effects, list):
                programs.extend(effects)
            for program in programs:
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
                    source = prune_native_csharp_records(source)
                    profile["attackReference"] = pack_attack_tables(source)
            if stage == "author" and known_attack_context_schema(source):
                profile["attackReference"] = pack_attack_tables(ordered_attack_context(source))
        if "spriteReference" in raw:
            brief["appearance"]["spriteReference"] = copy.deepcopy(raw["spriteReference"])
        if stage == "author":
            from infini_local.pipelines.context.mechanics_context import mechanics_context
            mechanics = mechanics_context(raw)
            if mechanics is not None:
                packet["raw"] = mechanics
                brief["behavior"] = {"reading": "Selected mechanics and explicit uncertainty are in packet.raw.mechanics."}
        briefs[label] = brief
    # Author already has the shared-fact transport contract. Presentation stages
    # keep their existing literal wire rather than acquiring another decoding seam.
    technical = share_exact_native_parent_facts(result) if stage == "author" else {"parents": result}
    context = {"parentBriefRule": _BRIEF_RULE, "parentBriefs": briefs, **technical}
    if is_list:
        context["parents"] = list(context["parents"].values())
        context["parentBriefs"] = list(briefs.values())
    return context


__all__ = ["parent_context_for_stage", "known_attack_context_schema", "share_exact_native_parent_facts", "NATIVE_SOURCE_REFERENCE_RULE"]
