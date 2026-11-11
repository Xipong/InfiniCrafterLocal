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

from infini_local.pipelines.context.author_mechanics_policy import POLICY
from infini_local.pipelines.context.author_source_notation import _source_sites
from infini_local.pipelines.context.mechanics_expression import MechanicsRenderer
from infini_local.pipelines.context.native_references import known_projectile_references
from infini_local.pipelines.context.attack_tables import pack_attack_tables, unpack_attack_tables
from infini_local.pipelines.context.csharp_source_view import _REFERENCE_FIELDS
from infini_local.pipelines.context.mechanics_selection import _gameplay_identity_program, _identity_unresolved

_ROOTS = ("nativeShootReference", "nativeContactHitStatusReference", "nativeEquipmentReference",
          "nativeEnvironmentReference", "nativeBuffEffectReference", "nativeItemDispatchReference")
_PROFILE_FIELDS = ("directProjectile", "effectiveProjectile")
_AMMO_PROFILES = ("projectileRaw", "weaponShootFieldProjectileRaw", "nativeReplacementProjectileRaw",
                  "playerInventoryProjectileRaw", "fallbackProjectileRaw")
_DIAGNOSTICS = {"attackReference", "referencedProjectiles", "mechanicsSource", "spriteReference",
                "engineMetrics", "textureMetrics", "strictIdentitySelections"}

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


def _graph_local_entry(key: str, value: Any) -> bool:
    # ParentSourceMethod emits a typed, unresolved entry definition for a local
    # read whose value can enter the captured slice from omitted control flow.
    # Keep that dependency without converting it into an executed/known value.
    return (re.fullmatch(r"local_entry:(0|[1-9][0-9]*)", key) is not None
            and isinstance(value, list) and len(value) == 4 and value[0] == "unresolved_local_entry"
            and isinstance(value[1], dict) and set(value[1]) == {"member"}
            and type(value[1]["member"]) is int and value[1]["member"] >= 0
            and isinstance(value[2], list) and not value[2]
            and type(value[3]) is int and value[3] == 0)


def _author_source_graph(graph: Any) -> dict[str, Any] | None:
    """Keep the bounded producer graph's known gameplay schema, not diagnostics."""
    if (not isinstance(graph, dict) or graph.get("source") != "parent_reachable_compiled_source_graph"
            or type(graph.get("version")) is not int or graph["version"] != 1):
        return None
    omitted = 0
    def clean(value: Any, *, local_values: bool = False) -> Any:
        nonlocal omitted
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                if isinstance(key, str) and (key in _GRAPH_NESTED_FIELDS or key.isdecimal()
                                             or re.fullmatch(r"in[0-9]+:[0-9]+", key)
                                             or local_values and _graph_local_entry(key, child)):
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
                        filtered[field] = clean(child, local_values=key == "nodes" and field == "values")
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
    "removedSwitchSectionCount", "removedUnreachableStatementCount", "identityPruning",
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
    "sourceSlices retain connected symbolic facts alongside readable source; partial C# regions do not cover whole methods. "
    "Projectile reference envelopes retain call indices, guards, candidate types and unresolved alternatives; "
    "profileSourcePath names the original capture; referenceExclusion applies to that candidate edge, "
    "while another admitted edge may retain the shared profile body. "
    "sourceReferences and runtimeDumpProvenance qualify individual captures, not shared defaults or executed spawns. "
    "mechanicsSourceIndex is a zero-based index into source; unresolvedNativeCSharpSourceRef preserves an unbound capture-local reference. "
    "uncertainty.sourceFacts retains literal refusals or unprojected source subtrees at their original sourcePath. "
    "sourceFields retains unfamiliar literal fields belonging to its source record. "
    "Full diagnostic graphs and source certificates remain in captures; no consumer size truncation."
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


def _compact_raw_source_coordinates(location: Any, call: dict[str, Any], source_count: int) -> Any:
    """Drop only coordinates of absent strict text; keep calls and branch IDs.

    The complete original mapping remains in the capture. Unknown extensions or
    unbound records stay literal rather than being treated as diagnostic noise.
    """
    if (not isinstance(location, dict)
            or set(location) != {"statement", "predicates", "scope", "mechanicsSourceIndex"}
            or location["scope"] != "raw_capture_strict_source_lines; not_lines_of_readable_author_source"
            or type(location["mechanicsSourceIndex"]) is not int
            or not 0 <= location["mechanicsSourceIndex"] < source_count):
        return location
    statement, predicates = location["statement"], location["predicates"]
    if (not isinstance(statement, dict) or set(statement) != {"mapping", "ilOffset", "locations"}
            or statement["mapping"] != "source_lines" or type(statement["ilOffset"]) is not int
            or statement["ilOffset"] != call.get("at") or not isinstance(statement["locations"], list)):
        return location
    for row in statement["locations"]:
        if (not isinstance(row, dict) or set(row) != {"ilOffset", "startLine", "endLine"}
                or any(type(row[k]) is not int for k in row)
                or row["ilOffset"] < 0 or not 0 < row["startLine"] <= row["endLine"]):
            return location
    if not isinstance(predicates, list) or not isinstance(call.get("requiredPredicates"), list):
        return location
    ids = []
    for predicate in predicates:
        if isinstance(predicate, dict) and "sourceSites" in predicate:
            predicate = _source_sites(predicate)
        if (not isinstance(predicate, dict) or set(predicate) != {"id", "ilSites"}
                or not isinstance(predicate["id"], str) or not isinstance(predicate["ilSites"], list)):
            return location
        ids.append(predicate["id"])
        for site in predicate["ilSites"]:
            if (not isinstance(site, dict) or set(site) != {"ilOffset", "sourceLines"}
                    or type(site["ilOffset"]) is not int or site["ilOffset"] < 0):
                return location
            lines = site["sourceLines"]
            if lines is not None and (not isinstance(lines, list) or any(
                    not isinstance(pair, list) or len(pair) != 2
                    or any(type(n) is not int for n in pair) or not 0 < pair[0] <= pair[1]
                    for pair in lines)):
                return location
    if ids != call["requiredPredicates"]:
        return location
    return {"mechanicsSourceIndex": location["mechanicsSourceIndex"],
            "scope": location["scope"],
            "coordinatesOmitted": "strict_source_coordinates_retained_in_raw_capture"}


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
                elif key not in {"draw", "nativeCSharpSource", "lifecycle", "interactionSources"}:
                    retain_refusals(path + "." + key, child)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                retain_refusals(f"{path}[{index}]", child)

    def add_code(record: dict[str, Any], identity: Any) -> int:
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
        return code.index(seen_code[key])

    def excluded(call: dict[str, Any], source: dict[str, Any], child_type: Any = None) -> bool:
        # Producer IL anchors, never line-based lexical ranges or numeric ID inference.
        for record in _rows(source.get("records")):
            receipt = record.get("identityPruning")
            if receipt is not None and receipt != {"allowed": True, "refusal": None}:
                continue
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
            if (type(row.get("at")) is int and row.get("scope") in (
                    "all_surviving_local_writes_are_integer_literals; conservative_union_not_execution",
                    "reaching_literal_local_stores; conservative_control_flow_union_not_execution")
                    and isinstance(values, list) and values and all(type(value) is int for value in values)
                    and child_type not in values):
                return True
        return False

    visited_profile_paths: set[str] = set()

    def visit(path: str, profile: dict[str, Any],
              graph_profiles: dict[int, tuple[str, dict[str, Any]]] | None = None) -> None:
        if path in visited_profile_paths:
            return
        visited_profile_paths.add(path)
        if graph_profiles is None:
            graph_profiles = {}

            def index_profiles(origin: str, value: dict[str, Any]) -> None:
                links = value.get("referencedProjectiles")
                if not known_projectile_references(links) or links.get("source") != "native_bounded_projectile_references":
                    return
                for index, row in enumerate(links["references"]):
                    child = row.get("profile")
                    if isinstance(child, dict) and type(row.get("type")) is int:
                        child_path = f"{origin}.referencedProjectiles.references[{index}].profile"
                        graph_profiles.setdefault(row["type"], (child_path, child))
                        index_profiles(child_path, child)

            index_profiles(path, profile)
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
                "source", "version", "identity", "records", "unresolved", "strictSourceRefusals", "verifiedSourceRecords", "authorSelection"}}
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
            if "interactionSources" in reference:
                # Keep this independent source namespace whole: helper IDs are
                # local to each root, and source-only entry locals are unknown.
                # Neither recognized nor future/malformed variants may vanish
                # merely because another method has approximate mechanics.
                retain_source(path + ".attackReference.interactionSources", reference["interactionSources"])
        coverage = reference.get("coverage")
        if isinstance(coverage, dict) and isinstance(coverage.get("unresolved"), list):
            gaps.update(str(gap) for gap in coverage["unresolved"])
        csharp = reference.get("nativeCSharpSource")
        fallback = (_rows(csharp.get("records")) if isinstance(csharp, dict)
                    and csharp.get("source") == "read_only_native_csharp_view"
                    and type(csharp.get("version")) is int and csharp["version"] == 1 else [])
        source_aliases: list[tuple[str, dict[str, Any]]] = []
        source_targets: dict[str, set[int]] = {}
        if source is not None and isinstance(source.get("authorSelection"), dict):
            aliases = source["authorSelection"].get("aliases", {})
            records = source["records"]
            if isinstance(aliases, dict) and all(isinstance(k, str) and type(v) is int
                    and 0 <= v < len(records) for k, v in aliases.items()):
                retained = []
                for record in fallback:
                    identifier = record.get("id")
                    if identifier in aliases:
                        target = records[aliases[identifier]]
                        source_aliases.append((identifier, target))
                        retained.append(target)
                    else:
                        retained.append(record)
                fallback = retained
                retain_source(path + ".authorSourcePolicy", POLICY)
        if source is not None:
            supplements = _rows(source.get("verifiedSourceRecords"))
            # Compare the exact declared model projection, not a method name.
            # Prefer the supplement's original entry offsets when both views
            # carry the same body, coverage, guards and uncertainty.
            def model_record(record: dict[str, Any]) -> dict[str, Any]:
                return {**{key: record[key] for key in (
                    "method", "code", "coverage", "unresolved", "identitySpecialization") if key in record},
                    "entryGuards": ([{key: value for key, value in guard.items() if key != "ilOffset"}
                                     if isinstance(guard, dict) else guard
                                     for guard in record.get("entryGuards", [])]
                                    if isinstance(record.get("entryGuards", []), list)
                                    else record["entryGuards"])}
            projections = [model_record(record) for record in supplements]
            unmatched = []
            for record in fallback:
                projected = {key: value for key, value in record.items() if key != "id"}
                matches = [supplement for supplement, projection in zip(supplements, projections)
                           if projected == projection]
                if matches and isinstance(record.get("id"), str):
                    source_aliases.extend((record["id"], target) for target in matches)
                else:
                    unmatched.append(record)
            fallback = unmatched + supplements
        roles: dict[str, set[str]] = {}

        def collect_roles(value: Any, root: str) -> None:
            if isinstance(value, dict):
                identifier = value.get("nativeCSharpSourceRef")
                if isinstance(identifier, str):
                    roles.setdefault(identifier, set()).add(root)
                for key, child in value.items():
                    if key not in ("nativeCSharpSource", "lifecycle", "interactionSources"):
                        collect_roles(child, root)
            elif isinstance(value, list):
                for child in value:
                    collect_roles(child, root)

        for root, value in reference.items():
            if root not in ("nativeCSharpSource", "lifecycle", "interactionSources"):
                collect_roles(value, root)
        for record in fallback:
            paths = record.get("graphPaths", [])
            identifiers = [identifier for identifier in [record.get("id"),
                           *(alias for alias, target in source_aliases if target is record)]
                           if isinstance(identifier, str)]
            record_roles = set().union(*(roles.get(identifier, set()) for identifier in identifiers))
            if ((paths and all(isinstance(p, list) and p and p[0] == "draw" for p in paths))
                    or record_roles and record_roles <= {"draw"}):
                continue
            if isinstance(record.get("code"), str):
                index = add_code(record, profile.get("type"))
                for identifier in identifiers:
                    source_targets.setdefault(identifier, set()).add(index)
        lifecycle = reference.get("lifecycle")
        if (isinstance(lifecycle, dict) and lifecycle.get("source") == "read_only_conditional_native_lifecycle_csharp"
                and type(lifecycle.get("version")) is int and lifecycle["version"] == 1):
            for record in _rows(lifecycle.get("records")):
                if isinstance(record.get("code"), str):
                    add_code({**record, "entryScope": lifecycle.get("scope", "source_entry_unknown")}, profile.get("type"))
            for gap in lifecycle.get("unresolved", []) if isinstance(lifecycle.get("unresolved"), list) else []:
                gaps.add("lifecycle:" + str(gap))
        # A same-named readable record can be only a conditional region. Keep
        # connected symbolic programs unless the upstream verified projection
        # has already replaced that exact slice with a source reference.
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
            # Bind the exact record emitted in this capture, including aliases
            # proved equal above. Names/bodies alone cannot identify coverage.
            matches = source_targets.get(identifier, set()) if isinstance(identifier, str) else set()
            if len(matches) == 1:
                result["mechanicsSourceIndex"] = next(iter(matches))
            else:
                result["unresolvedNativeCSharpSourceRef"] = copy.deepcopy(identifier)
                result["sourceReferenceStatus"] = "no_unique_emitted_source_record"
            return result

        if "strictIdentitySelections" in profile:
            # Resolve only the exact whole-method receipt issued upstream.
            selections = copy.deepcopy(profile["strictIdentitySelections"])
            if isinstance(selections, list):
                selections = [bind_source_refs(row) if isinstance(row, dict)
                              and row.get("selectedSource") == "unchanged_verified_whole_method"
                              else row for row in selections]
            strict_selections.append({"sourcePath": path, "selections": selections})

        programs = [(role, reference.get(role)) for role in ("motionDispatch", "collision", "positionIntegration")]
        programs += [("motionDispatchEffects", row) for row in _rows(reference.get("motionDispatchEffects"))]
        motion = reference.get("motion")
        if isinstance(motion, dict):
            programs += [("motion", row) for row in _rows(motion.get("programs"))]
        for role, program in programs:
            if (not isinstance(program, dict) or not isinstance(program.get("method"), str)
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
            if "referencedProjectiles" in profile:
                retain_source(path + ".referencedProjectiles", links)
            return
        # Preserve the call-to-candidate graph literally, including unknown-only
        # calls. Move only profile bodies to their existing capture locations;
        # this avoids recursively duplicating all descendant profiles.
        link_view = copy.deepcopy({key: value for key, value in links.items() if key != "references"})
        calls = links.get("sourceCalls", [])
        if known_projectile_references(links):
            for call in _rows(link_view.get("sourceCalls")):
                location = call.get("sourceLocation")
                if (isinstance(location, dict) and isinstance(location.get("sourceRecord"), str)
                        and set(location) <= {"sourceRecord", "statement", "predicates", "scope"}):
                    # Upstream line mappings name the profile-local verified
                    # source table. An approximate same-named body is not it.
                    call["sourceLocation"] = bind_source_refs({
                        **{key: value for key, value in location.items() if key != "sourceRecord"},
                        "nativeCSharpSourceRef": location["sourceRecord"]})
                    call["sourceLocation"] = _compact_raw_source_coordinates(
                        call["sourceLocation"], call, len(code))
        references = links.get("references")
        if "references" in links:
            link_view["references"] = [] if isinstance(references, list) else copy.deepcopy(references)
        for index, child in enumerate(references if isinstance(references, list) else []):
            if not isinstance(child, dict):
                link_view["references"].append(copy.deepcopy(child))
                gaps.add("malformed_child_reference:" + path + ":" + str(index))
                continue
            indices = child.get("sourceCallIndices")
            child_path = f"{path}.referencedProjectiles.references[{index}].profile"
            child_view = copy.deepcopy({key: value for key, value in child.items()
                                        if key != "profile" or not isinstance(value, dict)})
            link_view["references"].append(child_view)
            if isinstance(child.get("profile"), dict):
                child_view["profileSourcePath"] = child_path
            alias_target = any(target == child_path or target.startswith(child_path + ".") for target in alias_targets)
            if (not alias_target and source is not None and isinstance(calls, list) and isinstance(indices, list) and indices
                    and all(type(i) is int and 0 <= i < len(calls) and isinstance(calls[i], dict)
                            and excluded(calls[i], source, child.get("type")) for i in indices)):
                reason = ("all_indexed_calls_in_identity_excluded_arms"
                          if all(excluded(calls[i], source) for i in indices) else
                          "all_indexed_calls_exclude_child_type_under_identity_assumption")
                omitted.append({"parentPath": path, "child": child.get("type"), "reason": reason})
                child_view["referenceExclusion"] = reason
                continue
            if isinstance(child.get("profile"), dict):
                visit(child_path, child["profile"], graph_profiles)
            elif (known_projectile_references(links) and links.get("source") == "native_bounded_projectile_references"
                    and type(child.get("profileRefType")) is int
                    and child.get("type") == child["profileRefType"]
                    and child["profileRefType"] in graph_profiles):
                # Reuse the exact captured profile/path, not a catalog guess.
                # A valid edge can keep a shared profile whose first edge was
                # excluded; visited paths terminate self/cross-reference cycles.
                target_path, target = graph_profiles[child["profileRefType"]]
                child_view["profileSourcePath"] = target_path
                visit(target_path, target, graph_profiles)
        retain_source(path + ".referencedProjectiles", link_view if known_projectile_references(links) else links)

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
        capture = {key: defaults.pop(key) for key in ("source", "inventorySlot", "profileScope", "itemShootSpeed",
                                                   "sourceReferences", "runtimeDumpProvenance") if key in defaults}
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
