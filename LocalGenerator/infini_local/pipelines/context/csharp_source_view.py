"""Read-only projection of producer-certified native C# source.

The native capture keeps its original graphs. This owner only replaces explicitly
named, certificate-matched graph locations in a detached model-facing copy.
"""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from infini_local.pipelines.context.attack_behavior import _PROGRAM_FIELDS, _ROW_FIELDS

SOURCE_READING = (
    "Read-only decompiled C# source, never executable Author code or an imported behavior. "
    "A matching method uses C# only when its complete source record and references are smaller than "
    "the compact captured graph; other methods retain their graph. Unused source records stay diagnostic. "
    "nativeCSharpSourceRef resolves to nativeCSharpSource.records.id in this same parent reference. "
    "A whole_method record retains all its source branches; conditional_ast_regions retains only the "
    "producer-certified closed regions and their explicit entry/coverage limits. Source calls/hooks and "
    "enclosing flow are not evaluated. graphCapture preserves extraction gaps; the full captured graphs "
    "remain diagnostic evidence. sourceLocation binds requiredPredicates IDs to certified IL/source "
    "locations; unavailable mappings remain unknown, never true conditions or guaranteed spawns."
)
_CERT = ("method", "sourceModuleVersionId", "sourceMethodSha256")
_REFERENCE_FIELDS = {"source", "version", "identityPredicates", "scope", "units", "motionDispatch",
    "motionDispatchEffects", "motion", "collision", "draw", "positionIntegration", "sourceMethods", "coverage",
    "admission", "nativeCSharpSource"}
_RECORD_FIELDS = {"id", *_CERT, "metadataToken", "assemblySha256", "decompiler", "coverage", "graphPaths",
    "code", "codeSha256", "locations", "unresolved", "entryGuards", "coveredWindows"}
_CAPTURE_FIELDS = _PROGRAM_FIELDS | {"identitySelected", "identitySelection"}
_MODEL_SOURCE = "read_only_native_csharp_view"
_MODEL_SCOPE = ("Gameplay source view: code, entry conditions, coverage and unresolveds are unchanged. "
    "PE/IL/decompiler certificates, hashes and graph-proof paths remain in the raw diagnostic capture.")


def _model_records(reference: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    envelope = reference.get("nativeCSharpSource")
    if (not isinstance(envelope, dict) or set(envelope) != {"source", "version", "records", "unresolved", "scope"}
            or envelope["source"] != _MODEL_SOURCE or type(envelope["version"]) is not int or envelope["version"] != 1
            or envelope["scope"] != _MODEL_SCOPE or not isinstance(envelope["records"], list)
            or not isinstance(envelope["unresolved"], list)):
        return None
    if any(not isinstance(row, dict) or set(row) != {"method", "unresolved"}
           or not all(isinstance(value, str) for value in row.values()) for row in envelope["unresolved"]):
        return None
    result = {}
    for record in envelope["records"]:
        if (not isinstance(record, dict) or set(record) != {"id", "method", "code", "coverage", "entryGuards", "unresolved"}
                or any(not isinstance(record[key], str) or not record[key] for key in ("id", "method", "code"))
                or record["id"] in result or not isinstance(record["coverage"], str)
                or record["coverage"] not in {"whole_method", "conditional_ast_regions"}
                or not isinstance(record["unresolved"], list) or any(not isinstance(value, str) for value in record["unresolved"])
                or not isinstance(record["entryGuards"], list)):
            return None
        for guard in record["entryGuards"]:
            if (not isinstance(guard, dict) or set(guard) != {"field", "operator", "literal", "scope"}
                    or not isinstance(guard["field"], str) or guard["field"] not in {
                        "Terraria.Projectile.type", "Terraria.Projectile.aiStyle"}
                    or guard["operator"] != "==" or type(guard["literal"]) is not int
                    or guard["scope"] != "only_if_original_guard_is_reached; enclosing_dispatch_unknown"):
                return None
        result[record["id"]] = record
    return result


def _compact_model_view(reference: dict[str, Any], calls: list[dict[str, Any]] | None
                        ) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    out, linked = copy.deepcopy(reference), copy.deepcopy(calls)
    records = _records(out)
    if not records or out.get("nativeCSharpSourceReading") != SOURCE_READING:
        return out, linked
    ids = {identity: f"s{index}" for index, identity in enumerate(records)}

    def visit(value: Any) -> Any:
        if known_native_csharp_program(value):
            return {"nativeCSharpSourceRef": ids[value["nativeCSharpSourceRef"]]}
        if isinstance(value, dict):
            return {key: visit(child) for key, child in value.items() if key != "nativeCSharpSource"}
        return [visit(child) for child in value] if isinstance(value, list) else value

    out = visit(out)
    out["nativeCSharpSource"] = {"source": _MODEL_SOURCE, "version": 1, "scope": _MODEL_SCOPE,
        "unresolved": copy.deepcopy(reference["nativeCSharpSource"]["unresolved"]),
        "records": [{"id": ids[identity], **{key: copy.deepcopy(record[key]) for key in (
            "method", "code", "coverage", "unresolved")}, "entryGuards": [{key: copy.deepcopy(value)
                for key, value in guard.items() if key != "ilOffset"} for guard in record["entryGuards"]]}
            for identity, record in records.items()]}
    if linked is not None:
        for call in linked:
            location = call.get("sourceLocation")
            if isinstance(location, dict) and location.get("sourceRecord") in ids:
                location["sourceRecord"] = ids[location["sourceRecord"]]
    return out, linked


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def _certificate(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key] for key in _CERT):
        return None
    return tuple(value[key] for key in _CERT)


def _records(reference: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    envelope = reference.get("nativeCSharpSource")
    if (not isinstance(envelope, dict) or set(envelope) != {"source", "version", "records", "unresolved", "scope"}
            or envelope["source"] != "verified_decompiled_native_csharp" or type(envelope["version"]) is not int
            or envelope["version"] != 1 or not isinstance(envelope["records"], list)
            or not isinstance(envelope["unresolved"], list) or not isinstance(envelope["scope"], str)):
        return None
    if any(not isinstance(row, dict) or set(row) != {"method", "unresolved"}
           or not all(isinstance(value, str) for value in row.values()) for row in envelope["unresolved"]):
        return None
    result, certificates = {}, set()
    for record in envelope["records"]:
        if (not isinstance(record, dict) or set(record) != _RECORD_FIELDS
                or not isinstance(record.get("id"), str) or not record["id"] or record["id"] in result
                or _certificate(record) is None or _certificate(record) in certificates
                or not _sha(record["sourceMethodSha256"]) or not _sha(record["assemblySha256"]) or not _sha(record["codeSha256"])
                or not _integer(record["metadataToken"]) or not isinstance(record["code"], str)
                or not record["code"].strip() or not isinstance(record["coverage"], str)
                or record["coverage"] not in {"whole_method", "conditional_ast_regions"}
                or not isinstance(record["unresolved"], list) or any(not isinstance(value, str) for value in record["unresolved"])
                or not isinstance(record["graphPaths"], list)
                or not record["graphPaths"] or not isinstance(record["locations"], list)):
            return None
        if hashlib.sha256(record["code"].encode("utf-8")).hexdigest() != record["codeSha256"]:
            return None
        engine = record["decompiler"]
        if (not isinstance(engine, dict) or set(engine) != {"name", "version", "assemblySha256", "settings"}
                or engine["name"] != "ICSharpCode.Decompiler" or not isinstance(engine["version"], str)
                or engine["version"] != "8.2.0.7535" or not _sha(engine["assemblySha256"])
                or engine["settings"] != "csharp_default_no_indentation_v1"):
            return None
        if any(not isinstance(path, list) or not path or any(
                not (isinstance(part, str) and part or _integer(part)) for part in path) for path in record["graphPaths"]):
            return None
        lines = len(record["code"].split("\n"))
        for location in record["locations"]:
            if not isinstance(location, dict) or not _integer(location.get("ilOffset")):
                return None
            if set(location) == {"ilOffset", "unresolved"}:
                if location["unresolved"] != "decompiler_source_location_unavailable":
                    return None
            elif (set(location) != {"ilOffset", "startLine", "endLine"}
                    or not _integer(location["startLine"]) or not _integer(location["endLine"])
                    or not 1 <= location["startLine"] <= location["endLine"] <= lines):
                return None
        guards = record.get("entryGuards", [])
        if not isinstance(guards, list) or record["coverage"] == "conditional_ast_regions" and not guards:
            return None
        for guard in guards:
            if (not isinstance(guard, dict) or set(guard) != {"field", "operator", "literal", "ilOffset", "scope"}
                    or not isinstance(guard["field"], str) or guard["field"] not in {"Terraria.Projectile.aiStyle", "Terraria.Projectile.type"}
                    or guard["operator"] != "==" or type(guard["literal"]) is not int or not _integer(guard["ilOffset"])
                    or guard["scope"] != "only_if_original_guard_is_reached; enclosing_dispatch_unknown"):
                return None
        if not isinstance(record["coveredWindows"], list) or any(not isinstance(window, dict)
                or set(window) != {"field", "literal", "guardOffset"} or not isinstance(window["field"], str)
                or window["field"] not in {"aiStyle", "type"}
                or type(window["literal"]) is not int or not _integer(window["guardOffset"])
                for window in record["coveredWindows"]):
            return None
        result[record["id"]] = record
        certificates.add(_certificate(record))
    return result


def _known_row(row: Any) -> bool:
    if not isinstance(row, dict) or not set(row) <= _ROW_FIELDS:
        return False
    if any(key in row and not isinstance(row[key], str)
           for key in ("kind", "expression", "call", "receiver", "scope", "id", "op")):
        return False
    if any(key in row and not _integer(row[key]) for key in ("at", "block")):
        return False
    if any(key in row and (not isinstance(row[key], list) or any(not isinstance(value, str) for value in row[key]))
           for key in ("requiredPredicates", "inputs")):
        return False
    if "successors" in row and (not isinstance(row["successors"], list) or any(not _integer(value) for value in row["successors"])):
        return False
    if "arguments" in row and (not isinstance(row["arguments"], dict)
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in row["arguments"].items())):
        return False
    return "orderedSourceUses" not in row or isinstance(row["orderedSourceUses"], list) and all(
        _known_row(use) for use in row["orderedSourceUses"])


def _known_graph(program: Any) -> bool:
    if not isinstance(program, dict) or not set(program) <= _CAPTURE_FIELDS or _certificate(program) is None:
        return False
    if "identityWindows" in program:
        windows = program["identityWindows"]
        if not isinstance(windows, list) or any(not isinstance(window, dict)
                or set(window) != {"field", "literal", "guardOffset"} or not isinstance(window["field"], str)
                or window["field"] not in {"aiStyle", "type"} or type(window["literal"]) is not int
                or not _integer(window["guardOffset"]) for window in windows):
            return False
    graph_keys = {"observations", "dependencies", "predicates", "symbols"}
    if graph_keys.intersection(program):
        if (not graph_keys <= set(program) or not isinstance(program["observations"], list)
                or not isinstance(program["dependencies"], dict) or not isinstance(program["predicates"], list)
                or not isinstance(program["symbols"], dict)
                or any(not isinstance(key, str) or not isinstance(value, str) for key, value in program["symbols"].items())):
            return False
        rows = [*program["observations"], *program["dependencies"].values(), *program["predicates"]]
        if any(not _known_row(row) for row in rows):
            return False
    if program.get("predicateSources"):
        return False  # A separate callee graph requires its own explicit replacement.
    selected = program.get("identitySelected")
    return selected is None or _known_graph(selected) and _certificate(selected) == _certificate(program)


def _at_path(reference: dict[str, Any], path: list[str | int]) -> tuple[Any, str | int, Any] | None:
    owner: Any = reference
    for part in path[:-1]:
        if isinstance(owner, dict) and isinstance(part, str) and part in owner:
            owner = owner[part]
        elif isinstance(owner, list) and _integer(part) and part < len(owner):
            owner = owner[part]
        else:
            return None
    leaf = path[-1]
    if isinstance(owner, dict) and isinstance(leaf, str) and leaf in owner:
        return owner, leaf, owner[leaf]
    if isinstance(owner, list) and _integer(leaf) and leaf < len(owner):
        return owner, leaf, owner[leaf]
    return None


def _windows(program: dict[str, Any]) -> list[dict[str, Any]]:
    selected = program.get("identitySelected")
    return [*program.get("identityWindows", []), *(_windows(selected) if isinstance(selected, dict) else [])]


def _capture_metadata(program: dict[str, Any]) -> dict[str, Any]:
    result = {key: copy.deepcopy(value) for key, value in program.items()
              if key not in {*_CERT, "observations", "dependencies", "predicates", "symbols", "identitySelected"}}
    if isinstance(program.get("identitySelected"), dict):
        result["selectedCapture"] = _capture_metadata(program["identitySelected"])
    return result


def known_native_csharp_program(program: Any) -> bool:
    if not isinstance(program, dict) or not isinstance(program.get("nativeCSharpSourceRef"), str):
        return False
    return set(program) == {"nativeCSharpSourceRef"} or (
        set(program) == {*_CERT, "nativeCSharpSourceRef", "graphCapture"} and _certificate(program) is not None
        and isinstance(program["graphCapture"], dict))


def known_native_csharp_context(reference: dict[str, Any]) -> bool:
    if "nativeCSharpSource" not in reference:
        return reference.get("nativeCSharpSourceReading") == SOURCE_READING and not has_native_csharp_reference(reference)
    if isinstance(reference.get("nativeCSharpSource"), dict) and reference["nativeCSharpSource"].get("source") == _MODEL_SOURCE:
        records = _model_records(reference)
        if records is None or reference.get("nativeCSharpSourceReading") != SOURCE_READING:
            return False
        used = set()

        def bound(value: Any) -> bool:
            if isinstance(value, dict):
                if "nativeCSharpSourceRef" in value:
                    identity = value["nativeCSharpSourceRef"]
                    if set(value) != {"nativeCSharpSourceRef"} or not isinstance(identity, str) or identity not in records:
                        return False
                    used.add(identity)
                return all(bound(child) for key, child in value.items() if key != "nativeCSharpSource")
            return not isinstance(value, list) or all(bound(child) for child in value)

        return bound(reference) and used == set(records)
    records = _records(reference)
    if records is None:
        return False
    if not records:
        return "nativeCSharpSourceReading" not in reference
    if reference.get("nativeCSharpSourceReading") != SOURCE_READING:
        return False
    declared = set()
    for record in records.values():
        for path in record["graphPaths"]:
            target = _at_path(reference, path)
            if (target is None or not known_native_csharp_program(target[2])
                    or target[2]["nativeCSharpSourceRef"] != record["id"]
                    or _certificate(target[2]) != _certificate(record)):
                return False
            declared.add(tuple(path))

    def linked(value: Any, path: tuple[str | int, ...] = ()) -> bool:
        if isinstance(value, dict):
            if "nativeCSharpSourceRef" in value and path not in declared:
                return False
            return all(linked(child, (*path, key)) for key, child in value.items() if key != "nativeCSharpSource")
        return not isinstance(value, list) or all(linked(child, (*path, index)) for index, child in enumerate(value))

    return linked(reference)


def has_native_csharp_reference(value: Any) -> bool:
    if known_native_csharp_program(value):
        return True
    if isinstance(value, dict):
        return any(has_native_csharp_reference(child) for child in value.values())
    return isinstance(value, list) and any(has_native_csharp_reference(child) for child in value)


def prune_native_csharp_records(reference: dict[str, Any]) -> dict[str, Any]:
    """Remove source records made unused by an already-admitted stage omission."""
    out = copy.deepcopy(reference)
    model = _model_records(out)
    if model is not None and out.get("nativeCSharpSourceReading") == SOURCE_READING:
        used = set()

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                if set(value) == {"nativeCSharpSourceRef"} and isinstance(value["nativeCSharpSourceRef"], str):
                    used.add(value["nativeCSharpSourceRef"])
                for key, child in value.items():
                    if key != "nativeCSharpSource": collect(child)
            elif isinstance(value, list):
                for child in value: collect(child)

        collect(out)
        if not used <= set(model):
            return out
        out["nativeCSharpSource"]["records"] = [record for identity, record in model.items() if identity in used]
        if not used:
            out.pop("nativeCSharpSource")
            out.pop("nativeCSharpSourceReading")
        return out
    records = _records(out)
    if records is None or out.get("nativeCSharpSourceReading") != SOURCE_READING:
        return out
    retained = []
    for record in records.values():
        paths = []
        for path in record["graphPaths"]:
            found = _at_path(out, path)
            if found is None:
                continue
            if (not known_native_csharp_program(found[2]) or found[2]["nativeCSharpSourceRef"] != record["id"]
                    or _certificate(found[2]) != _certificate(record)):
                return copy.deepcopy(reference)
            paths.append(path)
        if paths:
            retained.append({**record, "graphPaths": paths})
    if retained:
        out["nativeCSharpSource"]["records"] = retained
    else:
        out.pop("nativeCSharpSource")
        out.pop("nativeCSharpSourceReading")
    return out


def _linked_calls(calls: list[dict[str, Any]] | None, records: dict[str, dict[str, Any]], predicates: dict
                  ) -> list[dict[str, Any]] | None:
    out = copy.deepcopy(calls)
    if out is None:
        return None
    by_cert = {_certificate(record): record for record in records.values()}
    for call in out:
        record = by_cert.get(_certificate(call))
        if record is None:
            continue

        def location(offset: int | None) -> dict[str, Any]:
            matches = [copy.deepcopy(row) for row in record["locations"]
                       if row["ilOffset"] == offset and "startLine" in row]
            return {"mapping": "source_lines" if matches else "unavailable", "ilOffset": offset,
                    **({"locations": matches} if matches else {})}

        call["sourceLocation"] = {"sourceRecord": record["id"], "statement": location(call["at"]),
            "predicates": [{"id": guard, "sourceSites": [location(offset) for offset in
                dict.fromkeys(predicates.get((_certificate(call), guard), []))],
                "mapping": "raw_predicate_sites" if predicates.get((_certificate(call), guard)) else "unavailable"}
                for guard in call["requiredPredicates"]]}
    return out


