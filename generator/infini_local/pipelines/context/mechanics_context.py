"""Explicitly approximate, producer-backed mechanics presentation for Author.

Normalization is lossy and declared: diagnostic graphs stay in captured packets.
This consumer does not parse C#, infer item families, evaluate calls or choose ammo.
Current modded/unavailable projectiles and item-only captures can lack this
optional source contract; their literal source presentation remains authoritative.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from infini_local.pipelines.context.mechanics_expression import MechanicsRenderer
from infini_local.pipelines.context.attack_tables import pack_attack_tables, unpack_attack_tables
from infini_local.pipelines.context.csharp_source_view import _REFERENCE_FIELDS
from infini_local.pipelines.context.attack_namespaces import _identifier
from infini_local.pipelines.context.mechanics_selection import _gameplay_identity_program, _identity_unresolved

_ROOTS = ("nativeShootReference", "nativeContactHitStatusReference", "nativeEquipmentReference",
          "nativeEnvironmentReference", "nativeBuffEffectReference", "nativeItemDispatchReference")
_PROFILE_FIELDS = ("directProjectile", "effectiveProjectile")
_AMMO_PROFILES = ("projectileRaw", "weaponShootFieldProjectileRaw", "nativeReplacementProjectileRaw",
                  "playerInventoryProjectileRaw", "fallbackProjectileRaw")
_DIAGNOSTICS = {"attackReference", "referencedProjectiles", "mechanicsSource", "sourceReferences",
                "runtimeDumpProvenance", "spriteReference", "engineMetrics", "textureMetrics", "strictIdentitySelections"}

_GRAPH_FIELDS = {"source", "version", "roots", "nodes", "members", "modules", "edges", "unresolved", "scope", "limits",
                 "omittedNodeCount", "omittedRootCount", "omittedBodyCount", "omittedEdgeCount", "completeness",
                 "nativeCatalogCoverage", "selection", "selectedEdgeCount"}
_GRAPH_ROW_FIELDS = {
    "roots": {"event", "node", "owner", "receiver", "receiverType", "originReceiverType"},
    "nodes": {"static", "arguments", "values", "statements", "blocks", "coverage", "unresolved", "method", "sha256",
              "id", "omittedStatementCount", "unresolvedEnclosingBranchCount", "unresolvedLocalDependencyCount", "reason",
              "nativeIdentity", "blockedIdentityReadCount", "blockedIdentityReads", "blockedIdentityReadsOmitted",
              "selectionUnavailable", "fragments", "receiverType", "originReceiverType", "sourceSelection", "possibleLocalWrites"},
    "members": {"module", "name", "returns", "type"},
    "modules": {"assembly", "mvid"},
    "edges": {"at", "context", "from", "kind", "sourceCoverage", "to", "unresolved"},
}
_GRAPH_NESTED_FIELDS = {"member", "projectileId", "projectileType", "aiStyle", "buffId", "event", "entryAndOmittedFlow",
                        "receiver", "receiverType", "originReceiverType", "coverage", "unresolved", "source", "version",
                        "reason", "at", "kind", "scope", "id", "offset", "field", "value", "node", "method",
                        "admission", "grantImmunityWith", "shoot", "contactStatus", "equipment", "environment", "nodes",
                        "edges", "helperDepth", "characters", "allocatedCharacters", "reservedCatalogCoverageCharacters", "discoveryNodes", "discoveryEdges", "sourceModuleVersionId",
                        "selection", "selectedEdgeCount", "selectionUnavailable", "blockedIdentityReadCount", "blockedIdentityReads",
                        "blockedIdentityReadsOmitted", "fragments"}

_LOCAL_WRITES_READING = (
    "possibleLocalWrites are candidate source writes to an address-exposed local, not reaching definitions or executed values. "
    "They may be conditional, overwritten or from other iterations; missing candidates do not prove no writes."
)


def _graph_local_writes_reading(graph: dict[str, Any]) -> str | None:
    nodes = graph.get("nodes")
    return _LOCAL_WRITES_READING if isinstance(nodes, list) and any(
        isinstance(node, dict) and "possibleLocalWrites" in node for node in nodes) else None


def _author_source_graph(graph: Any) -> dict[str, Any] | None:
    """Keep the bounded producer graph's known gameplay schema, not diagnostics."""
    if (not isinstance(graph, dict) or graph.get("source") != "parent_reachable_compiled_source_graph"
            or type(graph.get("version")) is not int or graph["version"] != 1):
        return None
    omitted = 0
    def clean(value: Any) -> Any:
        nonlocal omitted
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                if isinstance(key, str) and (key in _GRAPH_NESTED_FIELDS or key.isdecimal()
                                             or re.fullmatch(r"in[0-9]+:[0-9]+", key)):
                    out[key] = clean(child)
                else:
                    omitted += 1
            return out
        if isinstance(value, list):
            return [clean(child) for child in value]
        return copy.deepcopy(value)
    result = {}
    for key, value in graph.items():
        if key not in _GRAPH_FIELDS:
            omitted += 1
        elif key in _GRAPH_ROW_FIELDS and isinstance(value, list):
            rows = []
            for row in value:
                if not isinstance(row, dict):
                    omitted += 1
                    continue
                filtered = {}
                for field, child in row.items():
                    if field in _GRAPH_ROW_FIELDS[key]:
                        filtered[field] = clean(child)
                    else:
                        omitted += 1
                rows.append(filtered)
            result[key] = rows
        else:
            result[key] = clean(value)
    if omitted:
        result["transportOmissions"] = {"unknownFieldCount": omitted,
            "scope": "Unrecognized graph fields omitted by Author projection; absence is not evidence of absent behavior."}
    return result
_SOURCE_RECEIPTS = {
    "id", "sourceMethodSha256", "sourceModuleVersionId", "metadataToken", "assemblySha256",
    "decompiler", "codeSha256", "graphPaths", "locations", "coveredWindows", "excludedCallOffsets",
    "spawnTypeCandidates", "removedConditionalCount", "removedEmptyStatementCount",
    "removedSwitchSectionCount", "removedUnreachableStatementCount",
}
_SOURCE_FIELDS = {"method", "code", "coverage", "entryGuards", "entryCondition", "entryScope", "unresolved",
                  "approximation", "receiverBinding", "identitySpecialization", "identityWitnesses", "spawnSites"}
_READING = (
    "Selected native mechanics, not executed gameplay or a complete specification. "
    "Identity pruning assumes captured type/aiStyle remain stable across opaque calls. "
    "Code retains source conditions and numbers; calls, hooks and unavailable source remain unknown. "
    "Projectile fields are captured defaults, not final fired damage or lifetime. "
    "Ammo rows are ordered candidate inputs, not selected shots. Source paths name original capture "
    "locations, mapped by projectiles.captures. Each capture retains its itemShootSpeed observation; "
    "it is not a shared projectile default or final shot velocity. Exact profile aliases copy a resolvable speed observation; "
    "dangling or cyclic aliases do not supply a speed. Draw is omitted; position integration "
    "source retains movement gates and exceptions. Expression opcodes retain native arithmetic types; snapshots identify values at stores "
    "within a captured method, not execution counts or independent evaluations, "
    "and path_value alternatives follow source paths, not independent random rolls. "
    "sourceSlices retain connected symbolic caller facts when readable methods are unavailable, not full execution proofs. "
    "mechanicsSourceIndex is a zero-based index into source; unresolvedNativeCSharpSourceRef preserves an unbound capture-local reference. "
    "uncertainty.sourceFacts retains literal refusals or unprojected source subtrees at their original sourcePath. "
    "sourceFields retains unfamiliar literal fields belonging to its source record. "
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
    source_facts: list[dict[str, Any]] = []
    code: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    strict_selections: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    seen_code: dict[str, dict[str, Any]] = {}
    seen_slices: dict[str, dict[str, Any]] = {}

    def retain_source(path: str, value: Any) -> None:
        source_facts.append({"sourcePath": path, "value": copy.deepcopy(value)})

    def retain_refusals(path: str, value: Any) -> None:
        # A readable method does not discharge a graph extraction refusal.
        # Keep the original path, including nested selected captures/programs.
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"graphCapture", "identitySelectionUnavailable"} and child:
                    retain_source(path + "." + key, child)
                elif key not in {"draw", "nativeCSharpSource", "lifecycle"}:
                    retain_refusals(path + "." + key, child)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                retain_refusals(f"{path}[{index}]", child)

    def add_code(record: dict[str, Any], identity: Any) -> None:
        # Only declared receipts are lossy. New entry constraints and current
        # receiver/identity assumptions must travel with the body they qualify.
        row = {key: value for key, value in record.items() if key in _SOURCE_FIELDS}
        extra = {key: value for key, value in record.items() if key not in _SOURCE_FIELDS | _SOURCE_RECEIPTS}
        if extra:
            # Keep unfamiliar fields literal without letting a new producer key
            # collide with the emitted projectiles/record presentation namespace.
            row["sourceFields"] = extra
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
        if "strictIdentitySelections" in profile:
            # These retain producer graphs that a readable C# view replaced,
            # using the established Author projection when it is recognized.
            strict_selections.append({"sourcePath": path, "selections": copy.deepcopy(profile["strictIdentitySelections"])})
        defaults = {key: value for key, value in profile.items() if key not in _DIAGNOSTICS}
        if "sameAs" in defaults:
            # Capture aliases are renamed and point to the sourcePath rows below,
            # not to deleted raw sections in the mechanics view.
            defaults["sameDefaultsAsSourcePath"] = str(defaults.pop("sameAs")).removeprefix("raw.")
        profiles.append({"sourcePath": path, "defaults": {
            key: renderer.render(value, source_path=path + "." + key) for key, value in defaults.items()}})
        source = _source(profile)
        if source is not None:
            extra = {key: value for key, value in source.items() if key not in {
                "source", "version", "identity", "records", "unresolved", "strictSourceRefusals", "verifiedSourceRecords"}}
            if extra:
                retain_source(path + ".mechanicsSource", extra)
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
            if "mechanicsSource" in profile:
                retain_source(path + ".mechanicsSource", profile["mechanicsSource"])
        # Approximate full-method extraction can refuse a large dispatcher while
        # its verified closed region is available. Never lose that source merely
        # because another method in this profile has a mechanics record.
        reference = profile.get("attackReference")
        try:
            reference = unpack_attack_tables(reference) if isinstance(reference, dict) else {}
        except (TypeError, ValueError):
            retain_source(path + ".attackReference", profile["attackReference"])
            reference = {}
        if set(reference) - (_REFERENCE_FIELDS | {
                "expressionNotation", "behaviorView", "presentationScope", "nativeCSharpSourceReading",
                "branchTests", "operationReading"}):
            # An unknown sibling can refer to any graph namespace. Retain the
            # whole subtree, not just its leaf after rewriting/removing targets.
            retain_source(path + ".attackReference", reference)
        else:
            retain_refusals(path + ".attackReference", reference)
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
        def method_name(value: Any, native_names: bool = False) -> Any:
            if native_names and isinstance(value, str):
                value = _identifier(value, restore=True)
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
                    or (method_name(program["method"], program.get("nativeNames") == 1) in available_methods
                        and "identitySelected" not in program and "identitySelection" not in program)
                    or not any(key in program for key in ("observations", "dependencies", "predicates", "operations",
                                                          "identitySelected", "identitySelection"))):
                continue
            if "identitySelected" in program:
                # An unrecognized selected producer shape is not safe to send
                # as arbitrary diagnostic JSON or to represent as certified.
                nested_unresolved = _identity_unresolved(program["identitySelected"])
                outer_unresolved = _identity_unresolved(program)
                if any(key in program and key not in outer_unresolved for key in ("coverage", "unresolved")):
                    outer_unresolved["unknownRefusalEntriesOmitted"] = True
                program = {"method": program["method"], **outer_unresolved}
                if nested_unresolved:
                    program["identitySelectionRefusal"] = nested_unresolved
                program["unresolvedIdentitySelection"] = "unrecognized_identity_selection_omitted"
            elif "identitySelection" in program:
                program, omitted_fields = _gameplay_identity_program(program)
                if omitted_fields:
                    program["omittedProgramFields"] = omitted_fields
            row = {"role": role, "program": bind_source_refs(program),
                   **{key: copy.deepcopy(reference[key]) for key in
                      ("scope", "units", "expressionNotation", "behaviorView", "identityPredicates", "admission",
                       "branchTests", "operationReading")
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
            if not isinstance(child.get("profile"), dict):
                retain_source(child_path.removesuffix(".profile"), child)
            elif set(child) - {"type", "sourceCallIndices", "profile"}:
                retain_source(child_path.removesuffix(".profile"), {k: v for k, v in child.items() if k != "profile"})
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
    mechanical_roots = {key: renderer.render(item[key], source_path="item." + key) for key in _ROOTS if key in item}
    graph = _author_source_graph(item.get("parentSourceGraph"))
    result = {
        "item": copy.deepcopy({key: value for key, value in item.items() if key not in {*_ROOTS, "parentSourceGraph"}}),
        "mechanics": {"reading": _READING, "projectiles": profiles, "source": code,
                      "itemRules": mechanical_roots, "ammoInputs": renderer.render(ammo, source_path="ammo"),
                      "uncertainty": {**_source_gaps(gaps),
                                      "excludedChildProfiles": omitted}},
    }
    if graph is not None:
        result["item"]["parentSourceGraph"] = graph
        if reading := _graph_local_writes_reading(graph):
            result["item"]["parentSourceGraphReading"] = reading
    elif "parentSourceGraph" in item:
        result["mechanics"]["uncertainty"]["parentSourceGraphOmission"] = {
            "reason": "unrecognized_parent_source_graph_omitted", **_identity_unresolved(item["parentSourceGraph"])}
    if slices:
        result["mechanics"]["sourceSlices"] = slices
    if strict_selections:
        result["mechanics"]["strictIdentitySelections"] = pack_attack_tables({
            "source": "read_only_native_attack_source", "version": 1, "selections": strict_selections})
        result["mechanics"]["reading"] += (
            " Strict identity selections are partial source facts, not execution. Source order is in step; "
            "requiredPredicates refer to reached branch IDs, not necessarily their true arms. dN are local definitions; "
            "alternatives are reaching definitions. T=Terraria; Xna=Microsoft.Xna.Framework. "
            "f32_at/ref_at and readFloat are source array reads; writeFloat checks the address before evaluating its value. "
            "Fields and calls are live, and unknowns and omitted effects remain unresolved."
        )
    if source_facts:
        result["mechanics"]["uncertainty"]["sourceFacts"] = source_facts
    metadata = renderer.finish()
    if metadata:
        result["mechanics"]["expressions"] = metadata
    for key in ("crossModIdentity", "vanillaFlags", "sourceStatReading", "sourceMotionUnits", "runtimeDumpProvenance"):
        if key in raw:
            result[key] = copy.deepcopy(raw[key])
    return result
