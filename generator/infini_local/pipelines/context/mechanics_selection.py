"""Bounded gameplay roots from an already validated strict source presentation.

This is a lossy Author view, never an execution or a proof of absent effects.
Conditions and dependencies of retained roots remain literal and connected.
"""

from __future__ import annotations
import copy
import json
import re
from collections import Counter
from typing import Any

_KEEP_KINDS = {"lifetime_end", "clock_or_ai_write", "center_assignment", "live_scale", "rotation", "return", "dispatch_call"}
_PHYSICAL = {
    "Entity.position",
    "Entity.velocity",
    "Entity.width",
    "Entity.height",
    "Entity.direction",
    "Projectile.damage",
    "Projectile.knockBack",
    "Projectile.armorPenetration",
    "Projectile.timeLeft",
    "Projectile.penetrate",
    "Projectile.maxPenetrate",
    "Projectile.netUpdate",
    "Projectile.tileCollide",
    "Projectile.ignoreWater",
    "Projectile.friendly",
    "Projectile.hostile",
    "Projectile.owner",
    "Projectile.ai",
    "Projectile.localAI",
    "Projectile.extraUpdates",
    "Projectile.scale",
    "Projectile.rotation",
}
_VISUAL = {"Projectile.alpha", "Projectile.frame", "Projectile.frameCounter", "Projectile.spriteDirection", "Projectile.light"}
_OMIT_CALLS = {"Utils.SelectRandom", "SoundEngine.PlaySound"}
_DREF, _BREF = re.compile(r"\bd\d+\b"), re.compile(r"\bb\d+\b")


def _references(value: Any) -> tuple[set[str], set[str]]:
    text = json.dumps(value, ensure_ascii=False)
    return set(_DREF.findall(text)), set(_BREF.findall(text))


def _include(row: dict[str, Any]) -> bool | None:
    kind = row.get("kind")
    if kind in _KEEP_KINDS:
        return True
    if kind == "state_write":
        expr = row.get("expression")
        if not isinstance(expr, str):
            return None
        match = re.match(r"^set\(\(this\)\.(Entity\.[A-Za-z_]+|Projectile\.[A-Za-z_]+),", expr)
        if match and match[1] in _PHYSICAL:
            return True
        if match and match[1] in _VISUAL:
            return False
        if re.match(r"^set\(\(ldflda\(Entity\.(?:position|velocity),this\)\)\.Vector2\.[XY],", expr):
            return True
    if kind == "motion_call" and row.get("call") in _OMIT_CALLS:
        return False
    return None


def select_gameplay_roots(program: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep a literal, dependency-closed source slice; report every omitted class."""
    source = copy.deepcopy(program)
    try:
        obs, deps, predicates = source["observations"], source["dependencies"], source["predicates"]
        if not isinstance(obs, list) or not isinstance(deps, dict) or not isinstance(predicates, list):
            raise ValueError("unknown_program_shape")
        if any(not isinstance(row, dict) for row in obs + predicates):
            raise ValueError("unknown_source_row")
        predmap = {row["id"]: row for row in predicates}
        if len(predmap) != len(predicates):
            raise ValueError("ambiguous_predicate_ids")
        decisions = [_include(row) for row in obs]
        # Unknown rows may be gameplay. Keep them as roots without preventing
        # independent, recognized presentation-only omissions elsewhere.
        selected = [row for row, decision in zip(obs, decisions) if decision is not False]
        needed_d, needed_b = _references(selected)
        done_d: set[str] = set()
        done_b: set[str] = set()
        while needed_d - done_d or needed_b - done_b:
            for key in sorted(needed_d - done_d):
                if key not in deps:
                    raise ValueError("missing_dependency")
                d, b = _references(deps[key])
                needed_d |= d
                needed_b |= b
                done_d.add(key)
            for key in sorted(needed_b - done_b):
                if key not in predmap:
                    raise ValueError("missing_predicate")
                d, b = _references(predmap[key])
                needed_d |= d
                needed_b |= b
                done_b.add(key)
        out = copy.deepcopy(source)
        out["observations"] = selected
        out["dependencies"] = {k: v for k, v in deps.items() if k in needed_d}
        out["predicates"] = [row for row in predicates if row["id"] in needed_b]
        omitted = [row for row, decision in zip(obs, decisions) if decision is False]
        return out, {
            "mode": "gameplay_roots_with_source_closure",
            "omittedObservations": len(omitted),
            **({"retainedUnclassifiedObservations": decisions.count(None)} if None in decisions else {}),
            "omittedByKind": dict(sorted(Counter(str(row.get("kind")) for row in omitted).items())),
            "omittedDependencies": len(deps) - len(out["dependencies"]),
            "omittedPredicates": len(predicates) - len(out["predicates"]),
            "scope": "Other source effects, including visual writes and RNG calls, are omitted and may affect later behavior. Not complete AI or runtime execution.",
        }
    except (ValueError, KeyError, TypeError):
        # Unsupported shapes keep their already allowlisted, bounded program,
        # never a raw producer dump. Unknowns are not silently discarded.
        return source, {"mode": "all_allowlisted_roots", "unresolved": "gameplay_selection_unavailable"}


def _identity_unresolved(value: Any) -> dict[str, Any]:
    """Retain producer refusal text without passing unknown-shaped payloads."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ("coverage", "unresolved"):
        child = value.get(key)
        if isinstance(child, str) and not child.lower().startswith("diagnostic"):
            result[key] = child
        elif isinstance(child, list):
            safe = [v for v in child if isinstance(v, str) and not v.lower().startswith("diagnostic")]
            if safe or not child:
                result[key] = safe
            if len(safe) != len(child):
                result["unknownRefusalEntriesOmitted"] = True
    return result


def _gameplay_identity_program(value: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Known gameplay fields only; unknown schema is an omission, not a fact."""
    fields = ("method", "observations", "dependencies", "predicates", "symbols", "coverage", "unresolved", "identitySelection")
    record_fields = {"kind", "block", "call", "expression", "arguments", "receiver", "requiredPredicates", "step",
                     "orderedSourceUses", "scope", "id", "op", "inputs", "successors", "target", "value", "type",
                     "count", "projectile", "damage", "knockback", "position", "velocity", "condition", "unresolved"}
    identity_fields = {"forCapturedIdentity", "scope", "fullMethodCapture", "coverage", "unresolved"}
    omitted = ["identityAlternatives" if key == "identityAlternatives" else "unknown_program_field"
               for key in value if key not in fields]
    def scrub(child: Any) -> Any:
        if isinstance(child, dict):
            result = {}
            for key, v in child.items():
                if isinstance(key, str) and not key.lower().startswith("diagnostic"):
                    result[key] = scrub(v)
                else:
                    omitted.append("diagnostic_or_invalid_field")
            return result
        if isinstance(child, list):
            return [scrub(v) for v in child]
        return copy.deepcopy(child)
    def record(v: Any) -> Any:
        if not isinstance(v, dict):
            return scrub(v)
        out = {}
        for key, child in v.items():
            if key not in record_fields:
                omitted.append("source_record_field")
            elif key == "orderedSourceUses" and isinstance(child, list):
                out[key] = [record(x) for x in child]
            else:
                out[key] = scrub(child)
        return out
    result = {}
    for key in fields:
        if key not in value:
            continue
        child = value[key]
        if key in ("observations", "predicates") and isinstance(child, list):
            result[key] = [record(v) for v in child]
        elif key == "dependencies" and isinstance(child, dict):
            result[key] = {name: record(v) for name, v in child.items() if isinstance(name, str) and name.startswith("d") and name[1:].isdigit()}
            if len(result[key]) != len(child):
                omitted.append("dependency_identifier")
        elif key == "identitySelection" and isinstance(child, dict):
            result[key] = {k: scrub(v) for k, v in child.items() if k in identity_fields}
            if len(result[key]) != len(child):
                omitted.append("identity_receipt_field")
        else:
            result[key] = scrub(child)
    return result, sorted(set(omitted))


