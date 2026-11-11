"""Choose a verified, read-only native source representation for the Author."""
from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.pipelines.context.attack_behavior import project_attack_behavior
from infini_local.pipelines.context.attack_tables import pack_attack_tables
from infini_local.pipelines.context.csharp_source_view import (
    SOURCE_READING, _CERT, _REFERENCE_FIELDS, _at_path, _capture_metadata, _certificate,
    _compact_model_view, _token_matches, _integer, _known_graph, _linked_calls, _records, _windows, _specialized_record, project_lifecycle_source,
)
from infini_local.pipelines.context.parent_stage import parent_context_for_stage
from infini_local.pipelines.context.native_interaction_source import project_interaction_source


def native_csharp_source_for_llm(reference: dict[str, Any], source_calls: list[dict[str, Any]] | None = None, *,
                                preferred_source_records: list[str] | None = None
                                ) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    """Prefer only explicit matching source records; all refusals preserve input facts."""
    reference = project_interaction_source(project_lifecycle_source(reference))
    original, calls = copy.deepcopy(reference), copy.deepcopy(source_calls)
    records = _records(reference)
    if (records is None or not records or not set(reference) <= _REFERENCE_FIELDS
            or reference.get("source") != "read_only_native_attack_source"
            or type(reference.get("version")) is not int or reference["version"] != 1):
        return original, calls
    call_fields = {*_CERT, "at", "requiredPredicates", "projectileTypes"}
    if source_calls is not None and any(not isinstance(call, dict) or not call_fields <= set(call) <= call_fields | {"unresolved", "metadataToken"}
            or _certificate(call) is None or not _integer(call["at"])
            or not isinstance(call["requiredPredicates"], list)
            or any(not isinstance(guard, str) for guard in call["requiredPredicates"])
            or not isinstance(call["projectileTypes"], list)
            or any(not _integer(value) for value in call["projectileTypes"])
            or "unresolved" in call and not isinstance(call["unresolved"], str) for call in source_calls):
        return original, calls
    if source_calls is not None:
        by_certificate = {_certificate(record): record for record in records.values()}
        for call in source_calls:
            record = by_certificate.get(_certificate(call))
            if record is not None and not _token_matches(call, record):
                return original, calls
    paths, predicates = [], {}
    for record in records.values():
        windows = set()
        for path in record["graphPaths"]:
            key = tuple(path)
            if any(key[:len(previous)] == previous or previous[:len(key)] == key for previous in paths):
                return original, calls
            found = _at_path(original, path)
            if (found is None or not _known_graph(found[2]) or _certificate(found[2]) != _certificate(record) or not _token_matches(found[2], record)):
                return original, calls
            if record["coverage"] == "conditional_ast_regions":
                for window in _windows(found[2]):
                    if (not isinstance(window, dict) or set(window) != {"field", "literal", "guardOffset"}
                            or not isinstance(window["field"], str) or window["field"] not in {"aiStyle", "type"}
                            or type(window["literal"]) is not int
                            or not _integer(window["guardOffset"])):
                        return original, calls
                    windows.add((window["field"], window["literal"], window["guardOffset"]))
            paths.append(key)
            for graph in (found[2], found[2].get("identitySelected", {})):
                for predicate in graph.get("predicates", []):
                    if isinstance(predicate.get("id"), str) and _integer(predicate.get("at")):
                        predicates.setdefault((_certificate(record), predicate["id"]), []).append(predicate["at"])
        if record["coverage"] == "conditional_ast_regions" and (not windows or windows != {
                (window["field"], window["literal"], window["guardOffset"]) for window in record["coveredWindows"]}):
            return original, calls
    def candidate(selected: dict[str, dict[str, Any]]) -> dict[str, Any]:
        out = copy.deepcopy(reference)
        for record in selected.values():
            for path in record["graphPaths"]:
                owner, leaf, graph = _at_path(out, path)
                owner[leaf] = {**{key: graph[key] for key in _CERT}, "nativeCSharpSourceRef": record["id"],
                               "graphCapture": _capture_metadata(graph)}
        if selected:
            out["nativeCSharpSource"]["records"] = list(copy.deepcopy(selected).values())
            out["nativeCSharpSourceReading"] = SOURCE_READING
        else:
            out.pop("nativeCSharpSource")
        return out

    def measured_view(value: dict[str, Any], selection: dict[str, dict[str, Any]]) -> tuple[int, dict[str, Any], list[dict[str, Any]] | None]:
        # Use the real stage/exact-sharing owner, rather than summing duplicate
        # graph costs. This already-captured packet cannot re-enter compaction.
        compact, linked = _compact_model_view(value, _linked_calls(calls, selection, predicates), selection)
        profile = {"attackReference": pack_attack_tables(project_attack_behavior(compact))}
        if calls is not None:
            profile["referencedProjectiles"] = {"source": "native_single_hop_projectile_references", "version": 1,
                "sourceCalls": linked, "references": []}
        context = parent_context_for_stage({"A": {"packet": {"raw": {"directProjectile": profile}}}}, stage="author")
        return len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))), compact, linked

    chosen = {}
    original = candidate(chosen)
    # Full-method evidence wins regardless of size. Defer the expensive Author
    # projection until a genuine size comparison is needed; every comparison
    # still uses the exact-sharing stage, never a guessed sum of records.
    best_size: int | None = None
    best_view: tuple[dict[str, Any], list[dict[str, Any]] | None] | None = None
    for record in records.values():
        for alternative in (record, _specialized_record(reference, record)):
            if alternative is None:
                continue
            selection = {**chosen, record["id"]: alternative}
            proposed = candidate(selection)
            # The graph contract captures connected slices, not the complete
            # method. A certified whole body (or its proved identity variant)
            # therefore takes priority even when a partial graph is smaller.
            fuller_source = record["coverage"] == "whole_method" and record["id"] not in chosen
            if fuller_source or record["id"] in (preferred_source_records or []):
                chosen, original, best_size, best_view = selection, proposed, None, None
                continue
            if best_size is None:
                best_size, compact, linked = measured_view(original, chosen)
                best_view = compact, linked
            size, compact, linked = measured_view(proposed, selection)
            if size < best_size:
                chosen, original, best_size = selection, proposed, size
                best_view = compact, linked
    if best_view is None:
        return _compact_model_view(original, _linked_calls(calls, chosen, predicates), chosen)
    return best_view
