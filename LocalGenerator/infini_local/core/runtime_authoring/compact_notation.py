from __future__ import annotations

"""An explicit Author syntax version with an auditable path to the canonical graph.

This is a syntax projection, not a save importer or a gameplay design pass.
Every choice is present in the source, implied by its chosen strict variant, or
is the unique item-body reference proved by the authored entity declarations.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY, CAPABILITY_REGISTRY, INPUT_KIND_REGISTRY, RUNTIME_PROGRAM_SCHEMA,
)
from infini_local.core.runtime_authoring.program_schema import (
    assert_bounded_author_input, author_item_response_schema, binding_schema, strict_schema_errors,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts


COMPACT_AUTHOR_SCHEMA = "infini.runtime-program.authoring.compact.v1"
COMPACT_SOURCE_SCHEMA = "infini.compact-author-source.v1"


class CompactAuthorError(ValueError):
    def __init__(self, errors: Sequence[Mapping[str, Any]]):
        self.errors = [dict(row) for row in errors]
        super().__init__("compact Author rejected: " + "; ".join(
            f"{row.get('path')}: {row.get('code', row.get('kind'))}" for row in self.errors[:12]))


def _refuse(path: str, code: str) -> None:
    raise CompactAuthorError([{"path": path, "code": code}])


def _item_only(fn: str) -> bool:
    return CAPABILITY_REGISTRY[fn].target_kinds == ("item_body",)


def compact_binding_schema() -> dict[str, Any]:
    variants = []
    for original in binding_schema()["oneOf"]:
        branch = deepcopy(original)
        properties = branch["properties"]
        input_name = properties["input"]["const"]
        policy = properties.pop("usePolicy")
        for name, child in policy["properties"].items():
            if "const" in child:
                continue
            child = deepcopy(child)
            if name == "action":
                action_name = child["properties"]["kind"]["const"]
                if len(INPUT_KIND_REGISTRY[input_name].allowed_actions) == 1:
                    child["properties"].pop("kind")
                if BINDING_ACTION_REGISTRY[action_name].target_kinds == ("item_body",):
                    child["properties"].pop("targetId")
                child["required"] = [key for key in child["required"] if key in child["properties"]]
                if not child["properties"]:
                    continue
            properties[name] = child
        branch["required"] = ["id", "input", *(
            key for key in policy["required"] if key in properties)]
        variants.append(branch)
    return {"oneOf": variants}


def compact_call_schema(*, item_only: bool | None, with_target: bool = False) -> dict[str, Any]:
    variants = []
    for name, cap in CAPABILITY_REGISTRY.items():
        if not cap.prompt_visible or cap.decision != "expose" or (item_only is not None and _item_only(name) != item_only):
            continue
        row = deepcopy(cap.provider_variant_schema())
        if not with_target or _item_only(name):
            row["properties"].pop("target")
            row["required"].remove("target")
        if not cap.params:
            row["properties"].pop("params")
            row["required"].remove("params")
        variants.append(row)
    return {"oneOf": variants}


def compact_author_item_schema() -> dict[str, Any]:
    schema = author_item_response_schema()
    program = schema["properties"]["runtimeProgram"]
    properties = program["properties"]
    properties["schema"] = {"const": COMPACT_AUTHOR_SCHEMA}
    properties["bindings"]["items"] = compact_binding_schema()
    calls = properties.pop("calls")
    call_limit = calls["maxItems"]
    group_variants = []
    for body in (True, False):
        group_properties: dict[str, Any] = {}
        if not body:
            group_properties["target"] = {
                "type": "string", "pattern": r"^[a-z][a-z0-9_]{0,47}$",
                "description": "Exact declared target for every call in this consecutive group",
            }
        group_properties["calls"] = {
            "type": "array", "minItems": 1, "maxItems": call_limit,
            "items": compact_call_schema(item_only=body),
        }
        group_variants.append({"type": "object", "additionalProperties": False,
                               "properties": group_properties, "required": list(group_properties)})
    properties["callGroups"] = {
        "type": "array", "minItems": calls.get("minItems", 0), "maxItems": call_limit,
        "items": {"oneOf": group_variants},
        "description": f"Expand in exact group/call order; at most {call_limit} total calls. Never merge nonconsecutive groups.",
    }
    program["required"] = ["callGroups" if key == "calls" else key for key in program["required"]]
    _replace_planned_intent_schema(schema["properties"]["realization"], schema)
    return schema


def _replace_planned_intent_schema(realization: dict[str, Any], author_schema: Mapping[str, Any]) -> None:
    row = realization["properties"]["selfEvaluation"]["properties"]["planVsProgram"]["properties"]["actionChecks"]["items"]
    row["properties"].pop("plannedIntent")
    limit = author_schema["properties"]["concept"]["properties"]["plannedPlayerActions"]["maxItems"]
    row["properties"]["plannedActionIndex"] = {
        "anyOf": [{"type": "integer", "minimum": 0, "maximum": limit - 1}, {"type": "null"}],
        "description": "Exact zero-based frozen concept row; null iff result is added. Never match intent text.",
    }
    row["required"] = ["plannedActionIndex" if key == "plannedIntent" else key for key in row["required"]]


def _checks(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    return document["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"]


@dataclass(frozen=True)
class CompactProjection:
    canonical: dict[str, Any]
    sources: dict[str, dict[str, Any]]

    def origins(self, canonical_path: str) -> dict[str, Any]:
        candidates = [key for key in self.sources if canonical_path == key or canonical_path.startswith(key + ".") or canonical_path.startswith(key + "[")]
        if not candidates:
            return {"sourcePaths": [canonical_path], "rule": "identity"}
        key = max(candidates, key=len)
        row = deepcopy(self.sources[key])
        suffix = canonical_path[len(key):]
        row["sourcePaths"] = [path + suffix for path in row["sourcePaths"]]
        return row

    def source_error(self, error: Mapping[str, Any]) -> dict[str, Any]:
        out = deepcopy(dict(error))
        path = str(out.get("path") or "$")
        if path == "$":
            return out
        origin = self.origins(path.removeprefix("$."))
        out["path"] = "$." + origin["sourcePaths"][0]
        if len(origin["sourcePaths"]) > 1:
            out["sourcePaths"] = ["$." + p for p in origin["sourcePaths"]]
        return out

    def source_receipts(self, canonical_receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for receipt in canonical_receipts:
            paths = receipt.get("authoredPaths") or [receipt.get("authoredPath", "")]
            origins = [self.origins(path) for path in paths]
            result.append({
                "callId": receipt.get("callId", ""), "fn": receipt.get("fn", ""),
                "canonicalAuthoredPaths": list(paths),
                "authoredPaths": [p for origin in origins for p in origin["sourcePaths"]],
                "rules": [origin["rule"] for origin in origins],
                "finalPath": receipt["finalPath"], "value": deepcopy(receipt.get("value")),
                "status": receipt["status"],
            })
        return result


def project_compact_author(document: Mapping[str, Any], *, check_shape: bool = True, allow_unresolved_reports: bool = False) -> CompactProjection:
    try:
        return _project_compact_author(document, check_shape=check_shape, allow_unresolved_reports=allow_unresolved_reports)
    except CompactAuthorError:
        raise
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise CompactAuthorError([{"path": "$", "code": "unprojectable_compact_structure", "message": str(exc)}]) from exc


def _project_compact_author(document: Mapping[str, Any], *, check_shape: bool, allow_unresolved_reports: bool) -> CompactProjection:
    schema = compact_author_item_schema()
    candidate, limit = assert_bounded_author_input(document, schema=schema, authored_only=False)
    if isinstance(candidate, Mapping) and set(candidate) - set(schema["properties"]):
        _refuse("$", "unknown_compact_author_root_field")
    if check_shape:
        errors = strict_schema_errors(candidate, schema, limit=limit)
        if errors:
            raise CompactAuthorError(errors)
    if not isinstance(candidate, Mapping) or candidate.get("runtimeProgram", {}).get("schema") != COMPACT_AUTHOR_SCHEMA:
        _refuse("$.runtimeProgram.schema", "explicit_compact_version_required")
    canonical = deepcopy(dict(document))
    program = canonical["runtimeProgram"]
    authored = document["runtimeProgram"]
    if not isinstance(authored.get("entities"), list) or any(not isinstance(row, Mapping) for row in authored["entities"]):
        _refuse("$.runtimeProgram.entities", "explicit_entity_declarations_required")
    for owner, rows in (("entities", authored["entities"]), ("bindings", authored["bindings"])):
        ids = [row.get("id") for row in rows]
        if any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
            _refuse(f"$.runtimeProgram.{owner}", "unique_explicit_ids_required")
    body_rows = [(i, row) for i, row in enumerate(authored["entities"]) if row.get("kind") == "item_body"]
    if len(body_rows) != 1:
        _refuse("$.runtimeProgram.entities", "exactly_one_authored_item_body_required")
    body_index, body = body_rows[0]
    if strict_schema_errors(body["id"], {"type": "string", "pattern": r"^[a-z][a-z0-9_]{0,47}$"}):
        _refuse(f"$.runtimeProgram.entities[{body_index}].id", "invalid_item_body_id")
    body_id = body["id"]
    sources: dict[str, dict[str, Any]] = {}

    def origin(target: str, source: str | list[str], rule: str = "identity") -> None:
        sources[target] = {"sourcePaths": [source] if isinstance(source, str) else source, "rule": rule}

    origin("runtimeProgram.schema", "runtimeProgram.schema", "explicit_syntax_version")
    program["schema"] = RUNTIME_PROGRAM_SCHEMA
    calls = []
    for group_index, group in enumerate(authored["callGroups"]):
        group_path = f"runtimeProgram.callGroups[{group_index}]"
        if not isinstance(group, Mapping) or set(group) - {"target", "calls"}:
            _refuse("$." + group_path, "unknown_call_group_field")
        for local_index, source_call in enumerate(group["calls"]):
            call = deepcopy(source_call)
            fn = call["fn"]
            if fn not in CAPABILITY_REGISTRY or not CAPABILITY_REGISTRY[fn].prompt_visible or CAPABILITY_REGISTRY[fn].decision != "expose":
                _refuse(f"$.{group_path}.calls[{local_index}].fn", "unknown_public_capability")
            target_path = f"runtimeProgram.calls[{len(calls)}]"
            call_path = f"{group_path}.calls[{local_index}]"
            if "target" in call:
                _refuse("$." + call_path + ".target", "call_target_belongs_to_group")
            origin(target_path, call_path)
            if _item_only(fn):
                if "target" in group:
                    _refuse(f"$.{group_path}.target", "item_only_group_has_no_target_field")
                call["target"] = body_id
                origin(target_path + ".target", f"runtimeProgram.entities[{body_index}].id", "unique_item_body")
            else:
                if "target" not in group:
                    _refuse(f"$.{group_path}.target", "explicit_group_target_required")
                call["target"] = group["target"]
                origin(target_path + ".target", group_path + ".target", "consecutive_group_target")
            if not CAPABILITY_REGISTRY[fn].params:
                if "params" in call:
                    _refuse(f"$.{call_path}.params", "no_argument_variant_has_no_params")
                call["params"] = {}
                origin(target_path + ".params", call_path + ".fn", "zero_argument_variant")
            calls.append(call)
    max_calls = author_item_response_schema()["properties"]["runtimeProgram"]["properties"]["calls"]["maxItems"]
    if len(calls) > max_calls:
        _refuse("$.runtimeProgram.callGroups", "total_call_limit")
    call_ids = [row.get("id") for row in calls]
    if any(not isinstance(value, str) for value in call_ids) or len(set(call_ids)) != len(call_ids):
        _refuse("$.runtimeProgram.callGroups", "unique_explicit_call_ids_required")
    program.pop("callGroups")
    program["calls"] = calls
    variants = {(row["properties"]["input"]["const"], row["properties"]["usePolicy"]["properties"]["action"]["properties"]["kind"]["const"]): row for row in binding_schema()["oneOf"]}
    for index, binding in enumerate(authored["bindings"]):
        path = f"runtimeProgram.bindings[{index}]"
        input_name = binding["input"]
        if input_name not in INPUT_KIND_REGISTRY:
            _refuse("$." + path + ".input", "unknown_binding_input")
        allowed = INPUT_KIND_REGISTRY[input_name].allowed_actions
        action = deepcopy(binding.get("action", {}))
        action_name = allowed[0] if len(allowed) == 1 else action.get("kind")
        if (input_name, action_name) not in variants:
            _refuse("$." + path + ".action.kind", "invalid_binding_action")
        source_policy = variants[input_name, action_name]["properties"]["usePolicy"]
        allowed_binding_fields = {"id", "input"} | {
            name for name, prop in source_policy["properties"].items()
            if "const" not in prop and (name != "action" or action)
        }
        if set(binding) - allowed_binding_fields:
            _refuse("$." + path, "forbidden_compact_binding_field")
        if len(allowed) == 1 and "kind" in action:
            _refuse("$." + path + ".action.kind", "binding_kind_is_variant_constant")
        if BINDING_ACTION_REGISTRY[action_name].target_kinds == ("item_body",) and "targetId" in action:
            _refuse("$." + path + ".action.targetId", "binding_target_is_unique_item_body")
        policy: dict[str, Any] = {}
        for name, prop in source_policy["properties"].items():
            canonical_path = path + ".usePolicy." + name
            if "const" in prop:
                policy[name] = deepcopy(prop["const"])
                origin(canonical_path, path + (".action.kind" if action_name == "place_item" else ".input"), "binding_variant_constant")
            elif name != "action":
                if name in binding:
                    policy[name] = deepcopy(binding[name])
                origin(canonical_path, path + "." + name, "binding_wrapper")
            else:
                action["kind"] = action_name
                origin(canonical_path, path + ".action", "binding_wrapper")
                if len(allowed) == 1:
                    origin(canonical_path + ".kind", path + ".input", "binding_variant_constant")
                if BINDING_ACTION_REGISTRY[action_name].target_kinds == ("item_body",):
                    action["targetId"] = body_id
                    origin(canonical_path + ".targetId", f"runtimeProgram.entities[{body_index}].id", "unique_item_body")
                policy[name] = action
        program["bindings"][index] = {"id": binding["id"], "input": input_name, "usePolicy": policy}
    planned = document["concept"].get("plannedPlayerActions", [])
    for index, row in enumerate(_checks(canonical)):
        path = f"realization.selfEvaluation.planVsProgram.actionChecks[{index}]"
        chosen = row.get("plannedActionIndex")
        invalid = ("plannedActionIndex" not in row
                   or (chosen is None and row.get("result") != "added")
                   or (chosen is not None and (type(chosen) is not int or chosen < 0 or chosen >= len(planned) or row.get("result") == "added")))
        if invalid and allow_unresolved_reports:
            # Keep the exact invalid source field in this repair-only graph.
            # No intent string or alternate reference is invented to make it valid.
            origin(path + ".plannedIntent", path + ".plannedActionIndex", "unresolved_report_reference")
            continue
        if "plannedActionIndex" not in row:
            _refuse("$." + path + ".plannedActionIndex", "explicit_planned_action_index_required")
        row.pop("plannedActionIndex", None)
        if chosen is None:
            if row["result"] != "added":
                _refuse("$." + path + ".plannedActionIndex", "null_index_requires_added_result")
            row["plannedIntent"] = "no corresponding initial action"
            origin(path + ".plannedIntent", path + ".plannedActionIndex", "explicit_added_action")
        else:
            if type(chosen) is not int or chosen < 0 or chosen >= len(planned) or row["result"] == "added":
                _refuse("$." + path + ".plannedActionIndex", "invalid_planned_action_index")
            row["plannedIntent"] = planned[chosen]["intent"]
            origin(path + ".plannedIntent", [path + ".plannedActionIndex", f"concept.plannedPlayerActions[{chosen}].intent"], "exact_planned_action_reference")
    return CompactProjection(canonical, sources)


def encode_compact_author(canonical: Mapping[str, Any], *, planned_action_indices: Sequence[int | None], preserve_groups_from: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Encode without text matching: report indices must be supplied explicitly."""
    out = deepcopy(dict(canonical))
    program = out["runtimeProgram"]
    program["schema"] = COMPACT_AUTHOR_SCHEMA
    groups: list[dict[str, Any]] = []
    old_group_by_id = ({call["id"]: index for index, group in enumerate(preserve_groups_from["runtimeProgram"]["callGroups"]) for call in group["calls"]}
                       if preserve_groups_from is not None else {})
    previous_group = None
    for index, original in enumerate(program.pop("calls")):
        call = deepcopy(original)
        target = call.pop("target")
        body = _item_only(call["fn"])
        key = {} if body else {"target": target}
        if not CAPABILITY_REGISTRY[call["fn"]].params:
            if call.pop("params", {}) != {}:
                _refuse("$.runtimeProgram.calls", "nonempty_no_argument_params")
        old_group = old_group_by_id.get(call["id"], ("new", index))
        if (not groups or {k: v for k, v in groups[-1].items() if k != "calls"} != key
                or (preserve_groups_from is not None and old_group != previous_group)):
            groups.append({**key, "calls": []})
        groups[-1]["calls"].append(call)
        previous_group = old_group
    program["callGroups"] = groups
    for index, old in enumerate(program["bindings"]):
        row = {"id": old["id"], "input": old["input"]}
        policy = deepcopy(old["usePolicy"])
        action = policy.pop("action")
        name = action["kind"]
        if BINDING_ACTION_REGISTRY[name].target_kinds == ("item_body",):
            action.pop("targetId")
        if len(INPUT_KIND_REGISTRY[old["input"]].allowed_actions) == 1:
            action.pop("kind")
        if action:
            row["action"] = action
        for key, value in policy.items():
            if key in {"stackCost", "contactDamage"} and (old["input"] in {"hold", "equipped"} or name == "place_item"):
                continue
            row[key] = value
        program["bindings"][index] = row
    rows = _checks(out)
    if len(rows) != len(planned_action_indices):
        _refuse("$.realization.selfEvaluation.planVsProgram.actionChecks", "explicit_index_for_each_report_row_required")
    for row, index in zip(rows, planned_action_indices):
        row.pop("plannedIntent")
        row["plannedActionIndex"] = index
    projected = project_compact_author(out)
    if projected.canonical != canonical:
        _refuse("$", "compact_encoding_would_change_authored_values")
    return out


def attach_compact_source(compiled: dict[str, Any], source: Mapping[str, Any], projection: CompactProjection) -> None:
    contract = compiled["runtimeContract"]
    contract["compactAuthorSource"] = {"schema": COMPACT_SOURCE_SCHEMA, "document": deepcopy(dict(source)), "sourceMap": deepcopy(projection.sources)}
    contract["compactSourceReceipts"] = projection.source_receipts(contract["finalWireReceipts"])


def audit_compact_source(compiled: Mapping[str, Any], *, authored_document: Mapping[str, Any] | None = None) -> dict[str, Any]:
    contract = compiled.get("runtimeContract", {})
    record = contract.get("compactAuthorSource")
    try:
        if not isinstance(record, Mapping) or record.get("schema") != COMPACT_SOURCE_SCHEMA or set(record) != {"schema", "document", "sourceMap"}:
            _refuse("$.runtimeContract.compactAuthorSource", "invalid_compact_source_record")
        source = record["document"]
        if authored_document is not None and source != authored_document:
            _refuse("$.runtimeContract.compactAuthorSource.document", "different_author_source")
        projection = project_compact_author(source)
        for key in ("name", "category", "concept", "realization"):
            if compiled.get(key) != projection.canonical.get(key):
                _refuse("$." + key, "compiled_report_does_not_match_compact_source")
        if record["sourceMap"] != projection.sources:
            _refuse("$.runtimeContract.compactAuthorSource.sourceMap", "source_map_is_not_exact_projection")
        rows = contract.get("finalWireReceipts", [])
        if contract.get("compactSourceReceipts") != projection.source_receipts(rows):
            _refuse("$.runtimeContract.compactSourceReceipts", "source_receipts_are_not_exact_projection")
        audit = audit_compiler_receipts(rows, authored_document=projection.canonical, final_document=compiled)
        if not audit["ok"]:
            return {"ok": False, "errors": audit["violations"]}
        return {"ok": True, "errors": []}
    except (CompactAuthorError, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "errors": getattr(exc, "errors", [{"code": "invalid_compact_source", "message": str(exc)}])}
