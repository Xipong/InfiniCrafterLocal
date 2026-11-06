"""Explicitly approximate, producer-backed mechanics presentation for Author.

Normalization is lossy and declared: diagnostic graphs stay in captured packets.
This consumer does not parse C#, infer item families, evaluate calls or choose ammo.
Older captures without this producer contract retain the legacy presentation.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from infini_local.pipelines.context.mechanics_expression import MechanicsRenderer
from infini_local.pipelines.context.attack_tables import unpack_attack_tables

_ROOTS = ("nativeShootReference", "nativeContactHitStatusReference", "nativeEquipmentReference",
          "nativeEnvironmentReference", "nativeBuffEffectReference", "nativeItemDispatchReference")
_PROFILE_FIELDS = ("directProjectile", "effectiveProjectile")
_AMMO_PROFILES = ("projectileRaw", "weaponShootFieldProjectileRaw", "nativeReplacementProjectileRaw",
                  "playerInventoryProjectileRaw", "fallbackProjectileRaw")
_DIAGNOSTICS = {"attackReference", "referencedProjectiles", "mechanicsSource", "sourceReferences",
                "runtimeDumpProvenance", "spriteReference", "engineMetrics", "textureMetrics"}
_READING = (
    "Selected native mechanics, not executed gameplay or a complete specification. "
    "Identity pruning assumes captured type/aiStyle remain stable across opaque calls. "
    "Code retains source conditions and numbers; calls, hooks and unavailable source remain unknown. "
    "Projectile fields are captured defaults, not final fired damage or lifetime. "
    "Ammo rows are ordered candidate inputs, not selected shots. Source paths name original capture "
    "locations, mapped by projectiles.captures. Each capture retains its itemShootSpeed observation; "
    "it is not a shared projectile default or final shot velocity. Exact profile aliases copy a resolvable speed observation; "
    "dangling or cyclic aliases do not supply a speed. Draw is omitted; position integration "
    "source retains movement gates and exceptions. Expression opcodes retain native arithmetic types; snapshots are values at stores, "
    "and path_value alternatives follow source paths, not independent random rolls. "
    "sourceSlices retain connected symbolic caller facts when readable methods are unavailable, not full execution proofs. "
    "mechanicsSourceIndex is a zero-based index into source; unresolvedNativeCSharpSourceRef preserves an unbound capture-local reference. "
    "Full source graphs and provenance remain in diagnostic captures; no consumer size truncation."
)


def _source_gaps(gaps: set[str]) -> dict[str, Any]:
    """Group repeated native site receipts without hiding distinct refusals."""
    literal = []
    sites: dict[str, list[int]] = {}
    for gap in sorted(gaps):
        match = re.fullmatch(
            r"(.+):effect_source_site@(0|[1-9][0-9]{0,9}):effect_source_site_count_bound", gap)
        if match is None:
            literal.append(gap)
        else:
            sites.setdefault(match[1], []).append(int(match[2]))
    return {"sourceGaps": literal, **({"sourceGapSites": [
        {"source": source, "reason": "effect_source_site_count_bound", "ilOffsets": sorted(offsets)}
        for source, offsets in sites.items()
    ]} if sites else {})}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _source(profile: dict[str, Any]) -> dict[str, Any] | None:
    value = profile.get("mechanicsSource")
    if (isinstance(value, dict) and value.get("source") == "native_mechanics_source"
            and type(value.get("version")) is int and value["version"] == 1
            and isinstance(value.get("identity"), dict)
            and type(value["identity"].get("type")) is int
            and type(profile.get("type")) is int
            and value["identity"]["type"] == profile["type"]
            and ("aiStyle" not in profile or value["identity"].get("aiStyle") == profile["aiStyle"])
            and isinstance(value.get("unresolved"), list)
            and isinstance(value.get("records"), list)
            and all(isinstance(row, dict) and isinstance(row.get("code"), str)
                    and isinstance(row.get("method"), str)
                    and isinstance(row.get("excludedCallOffsets", []), list)
                    and all(type(offset) is int and offset >= 0 for offset in row.get("excludedCallOffsets", []))
                    for row in value["records"])):
        return value
    return None


def _roots(raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result = [(key, raw[key]) for key in _PROFILE_FIELDS if isinstance(raw.get(key), dict)]
    ammo = raw.get("ammo")
    if isinstance(ammo, dict):
        for key in _AMMO_PROFILES:
            value = ammo.get(key)
            if isinstance(value, dict):
                result.append(("ammo." + key, value))
            elif isinstance(value, list):
                result.extend((f"ammo.{key}[{i}]", row) for i, row in enumerate(value) if isinstance(row, dict))
    return result


def mechanics_context(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Build one self-contained view, leaving the original packet untouched."""
    if "generatedParent" in raw:
        return None
    roots = _roots(raw)
    if not any(_source(profile) is not None for _, profile in roots):
        return None
    # A child can be the canonical capture behind a later exact profile alias.
    # Keep its subtree even when that child's own spawn candidates are excluded;
    # otherwise the surviving alias would silently lose its native facts.
    alias_targets: set[str] = set()
    def collect_aliases(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("sameAs"), str):
                alias_targets.add(value["sameAs"].removeprefix("raw."))
            for child in value.values():
                collect_aliases(child)
        elif isinstance(value, list):
            for child in value:
                collect_aliases(child)
    collect_aliases(raw)
    renderer = MechanicsRenderer()
    item = raw.get("item", {})
    item = item if isinstance(item, dict) else {}
    gaps: set[str] = set()
    code: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    seen_code: dict[str, dict[str, Any]] = {}
    seen_slices: dict[str, dict[str, Any]] = {}

    def add_code(record: dict[str, Any], identity: Any) -> None:
        row = {key: record[key] for key in
               ("method", "code", "coverage", "entryGuards", "entryCondition", "entryScope", "unresolved") if key in record}
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key not in seen_code:
            stored = {"projectiles": [], **copy.deepcopy(row)}
            seen_code[key] = stored
            code.append(stored)
        if identity not in seen_code[key]["projectiles"]:
            seen_code[key]["projectiles"].append(identity)

    def excluded(call: dict[str, Any], source: dict[str, Any], child_type: Any = None) -> bool:
        # Producer IL anchors, never line-based lexical ranges or numeric ID inference.
        for record in _rows(source.get("records")):
            if not (all(call.get(key) is not None and call.get(key) == record.get(key)
                        for key in ("method", "sourceMethodSha256", "sourceModuleVersionId"))
                    and type(call.get("at")) is int):
                continue
            if call["at"] in record.get("excludedCallOffsets", []):
                return True
            candidates = [row for row in _rows(record.get("spawnTypeCandidates")) if row.get("at") == call["at"]]
            if len(candidates) != 1 or type(child_type) is not int:
                continue
            row = candidates[0]
            values = row.get("projectileTypes")
            if (type(row.get("at")) is int and row.get("scope") ==
                    "all_surviving_local_writes_are_integer_literals; conservative_union_not_execution"
                    and isinstance(values, list) and values and all(type(value) is int for value in values)
                    and child_type not in values):
                return True
        return False

    def visit(path: str, profile: dict[str, Any]) -> None:
        defaults = {key: value for key, value in profile.items() if key not in _DIAGNOSTICS}
        if "sameAs" in defaults:
            # Capture aliases are renamed and point to the sourcePath rows below,
            # not to deleted raw sections in the mechanics view.
            defaults["sameDefaultsAsSourcePath"] = str(defaults.pop("sameAs")).removeprefix("raw.")
        profiles.append({"sourcePath": path, "defaults": {key: renderer.render(value) for key, value in defaults.items()}})
        source = _source(profile)
        if source is not None:
            if not source["records"]:
                gaps.add("approximate_method_records_unavailable:" + path)
            for record in _rows(source["records"]):
                paths = record.get("graphPaths", [])
                if paths and all(isinstance(p, list) and p and p[0] == "draw" for p in paths):
                    continue
                add_code(record, profile.get("type"))
            for field in ("unresolved", "strictSourceRefusals"):
                entries = source.get(field, [])
                for gap in entries if isinstance(entries, list) else [field + "_unavailable"]:
                    if isinstance(gap, dict) and isinstance(gap.get("unresolved"), str):
                        gaps.add(str(gap.get("method", "unknown_method")) + ":" + gap["unresolved"])
                    else:
                        gaps.add(str(gap))
        elif "sameAs" not in profile:
            gaps.add("mechanics_source_unavailable:" + path)
        # Approximate full-method extraction can refuse a large dispatcher while
        # its verified closed region is available. Never lose that source merely
        # because another method in this profile has a mechanics record.
        reference = profile.get("attackReference")
        try:
            reference = unpack_attack_tables(reference) if isinstance(reference, dict) else {}
        except (TypeError, ValueError):
            reference = {}
        coverage = reference.get("coverage")
        if isinstance(coverage, dict) and isinstance(coverage.get("unresolved"), list):
            gaps.update(str(gap) for gap in coverage["unresolved"])
        csharp = reference.get("nativeCSharpSource")
        fallback = (_rows(csharp.get("records")) if isinstance(csharp, dict)
                    and csharp.get("source") == "read_only_native_csharp_view"
                    and type(csharp.get("version")) is int and csharp["version"] == 1 else [])
        if source is not None:
            selected_methods = {record.get("method") for record in fallback}
            fallback += [record for record in _rows(source.get("verifiedSourceRecords"))
                         if record.get("method") not in selected_methods]
        represented = {record.get("method") for record in _rows(source.get("records"))} if source else set()
        roles: dict[str, set[str]] = {}

        def collect_roles(value: Any, root: str) -> None:
            if isinstance(value, dict):
                identifier = value.get("nativeCSharpSourceRef")
                if isinstance(identifier, str):
                    roles.setdefault(identifier, set()).add(root)
                for key, child in value.items():
                    if key not in ("nativeCSharpSource", "lifecycle"):
                        collect_roles(child, root)
            elif isinstance(value, list):
                for child in value:
                    collect_roles(child, root)

        for root, value in reference.items():
            if root not in ("nativeCSharpSource", "lifecycle"):
                collect_roles(value, root)
        for record in fallback:
            if record.get("method") in represented:
                continue
            paths = record.get("graphPaths", [])
            identifier = record.get("id")
            record_roles = roles.get(identifier, set()) if isinstance(identifier, str) else set()
            if ((paths and all(isinstance(p, list) and p and p[0] == "draw" for p in paths))
                    or record_roles and record_roles <= {"draw"}):
                continue
            if isinstance(record.get("code"), str):
                add_code(record, profile.get("type"))
        lifecycle = reference.get("lifecycle")
        if (isinstance(lifecycle, dict) and lifecycle.get("source") == "read_only_conditional_native_lifecycle_csharp"
                and type(lifecycle.get("version")) is int and lifecycle["version"] == 1):
            for record in _rows(lifecycle.get("records")):
                if isinstance(record.get("code"), str) and record.get("method") not in represented:
                    add_code({**record, "entryScope": lifecycle.get("scope", "source_entry_unknown")}, profile.get("type"))
            for gap in lifecycle.get("unresolved", []) if isinstance(lifecycle.get("unresolved"), list) else []:
                gaps.add("lifecycle:" + str(gap))
        # A readable helper is not a replacement for its missing caller. Keep
        # connected symbolic programs when that method has no readable record;
        # do not infer the caller's arguments, branch choice or final outcome.
        def method_name(value: Any) -> Any:
            return "Terraria." + value[2:] if isinstance(value, str) and value.startswith("T.") else value

        available_methods = {method_name(row.get("method")) for row in code
                             if profile.get("type") in row["projectiles"]}
        def bind_source_refs(value: Any) -> Any:
            if isinstance(value, list):
                return [bind_source_refs(child) for child in value]
            if not isinstance(value, dict):
                return copy.deepcopy(value)
            result = {key: bind_source_refs(child) for key, child in value.items()
                      if key != "nativeCSharpSourceRef"}
            if "nativeCSharpSourceRef" not in value:
                return result
            identifier = value["nativeCSharpSourceRef"]
            # IDs are local to this profile's verified source table. Match the
            # actual emitted body, not just a same-named partial method.
            records = [record for record in fallback
                       if isinstance(identifier, str) and record.get("id") == identifier]
            matches = {index for record in records for index, emitted in enumerate(code)
                       if profile.get("type") in emitted["projectiles"]
                       and method_name(record.get("method")) == method_name(emitted.get("method"))
                       and isinstance(record.get("code"), str)
                       and record["code"] == emitted.get("code")}
            if len(matches) == 1:
                result["mechanicsSourceIndex"] = next(iter(matches))
            else:
                result["unresolvedNativeCSharpSourceRef"] = copy.deepcopy(identifier)
                result["sourceReferenceStatus"] = "no_unique_emitted_source_record"
            return result

        programs = [(role, reference.get(role)) for role in ("motionDispatch", "collision", "positionIntegration")]
        programs += [("motionDispatchEffects", row) for row in _rows(reference.get("motionDispatchEffects"))]
        motion = reference.get("motion")
        if isinstance(motion, dict):
            programs += [("motion", row) for row in _rows(motion.get("programs"))]
        for role, program in programs:
            if (not isinstance(program, dict) or not isinstance(program.get("method"), str)
                    or method_name(program["method"]) in available_methods
                    or not any(key in program for key in ("observations", "dependencies", "predicates"))):
                continue
            row = {"role": role, "program": bind_source_refs(program),
                   **{key: copy.deepcopy(reference[key]) for key in
                      ("scope", "units", "expressionNotation", "behaviorView", "identityPredicates", "admission")
                      if key in reference}}
            key = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if key not in seen_slices:
                seen_slices[key] = {"projectiles": [], **row}
                slices.append(seen_slices[key])
            if profile.get("type") not in seen_slices[key]["projectiles"]:
                seen_slices[key]["projectiles"].append(profile.get("type"))
        links = profile.get("referencedProjectiles")
        if not isinstance(links, dict):
            return
        calls = links.get("sourceCalls", [])
        references = links.get("references")
        for index, child in enumerate(references if isinstance(references, list) else []):
            if not isinstance(child, dict):
                gaps.add("malformed_child_reference:" + path + ":" + str(index))
                continue
            indices = child.get("sourceCallIndices")
            child_path = f"{path}.referencedProjectiles.references[{index}].profile"
            alias_target = any(target == child_path or target.startswith(child_path + ".") for target in alias_targets)
            if (not alias_target and source is not None and isinstance(calls, list) and isinstance(indices, list) and indices
                    and all(type(i) is int and 0 <= i < len(calls) and isinstance(calls[i], dict)
                            and excluded(calls[i], source, child.get("type")) for i in indices)):
                omitted.append({"parentPath": path, "child": child.get("type"),
                                "reason": ("all_indexed_calls_in_identity_excluded_arms"
                                           if all(excluded(calls[i], source) for i in indices) else
                                           "all_indexed_calls_exclude_child_type_under_identity_assumption")})
                continue
            if isinstance(child.get("profile"), dict):
                visit(child_path, child["profile"])

    for path, profile in roots:
        visit(path, profile)
    # Exact full-profile aliases included the source capture's speed before it
    # moved out of defaults. Copy only a present observation at a resolved path;
    # explicit values win and cyclic/dangling aliases stay unfilled.
    by_path = {row["sourcePath"]: row["defaults"] for row in profiles}
    for row in profiles:
        target = row["defaults"]
        visited: set[str] = set()
        while "itemShootSpeed" not in target:
            alias = target.get("sameDefaultsAsSourcePath")
            if not isinstance(alias, str) or alias in visited or alias not in by_path:
                break
            visited.add(alias)
            target = by_path[alias]
        if "itemShootSpeed" in target:
            row["defaults"]["itemShootSpeed"] = copy.deepcopy(target["itemShootSpeed"])
    # Group literally equal defaults, retaining every observation role/slot.
    # This shares values, never selects an ammo candidate or projectile design.
    grouped: list[dict[str, Any]] = []
    defaults_index: dict[str, dict[str, Any]] = {}
    for row in profiles:
        defaults = row["defaults"]
        capture = {key: defaults.pop(key) for key in ("source", "inventorySlot", "profileScope", "itemShootSpeed") if key in defaults}
        key = json.dumps(defaults, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        observation = {"sourcePath": row["sourcePath"], **capture}
        if key not in defaults_index:
            grouped_row = {"defaults": defaults, "captures": []}
            grouped.append(grouped_row)
            defaults_index[key] = grouped_row
        defaults_index[key]["captures"].append(observation)
    profiles = grouped
    ammo = raw.get("ammo")
    ammo = {k: v for k, v in ammo.items() if k not in _AMMO_PROFILES} if isinstance(ammo, dict) else {}
    mechanical_roots = {key: renderer.render(item[key]) for key in _ROOTS if key in item}
    result = {
        "item": copy.deepcopy({key: value for key, value in item.items() if key not in {*_ROOTS, "parentSourceGraph"}}),
        "mechanics": {"reading": _READING, "projectiles": profiles, "source": code,
                      "itemRules": mechanical_roots, "ammoInputs": renderer.render(ammo),
                      "uncertainty": {**_source_gaps(gaps),
                                      "excludedChildProfiles": omitted}},
    }
    if slices:
        result["mechanics"]["sourceSlices"] = slices
    metadata = renderer.finish()
    if metadata:
        result["mechanics"]["expressions"] = metadata
    for key in ("crossModIdentity", "vanillaFlags", "runtimeProbe", "sourceStatReading", "sourceMotionUnits", "runtimeDumpProvenance"):
        if key in raw:
            result[key] = copy.deepcopy(raw[key])
    return result
