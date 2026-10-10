from __future__ import annotations

"""Strict JSON-shape validation shared by Author schema and typed parameters.

This lower-level owner has no registry dependency. Registry-selected parameter
variants and complete Author documents therefore use the same exact validator
without a capability-registry/program-schema import cycle.
"""

import math
import re
from typing import Any, Mapping

from infini_local.core.repair_merge import json_path_child


def _is_finite_number(value: int | float) -> bool:
    """Refuse JSON integers outside the runtime float domain without raising."""
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and _is_finite_number(value)
    if expected == "null":
        return value is None
    return False


def _resolve_ref(root: Mapping[str, Any], ref: str) -> Mapping[str, Any] | None:
    if not ref.startswith("#/$defs/"):
        return None
    defs = root.get("$defs")
    if not isinstance(defs, Mapping):
        return None
    value = defs.get(ref.removeprefix("#/$defs/"))
    return value if isinstance(value, Mapping) else None


def _schema_const_paths(branch: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    """Collect literal const paths from schema properties, not authored prose."""
    result = {prefix: branch["const"]} if "const" in branch else {}
    properties = branch.get("properties")
    if isinstance(properties, Mapping):
        for key, child in properties.items():
            if isinstance(key, str) and isinstance(child, Mapping):
                result.update(_schema_const_paths(child, (*prefix, key)))
    return result


def _authored_const_value(value: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return False, None
        value = value[key]
    return True, value


def _authored_const_matches(value: Any, path: tuple[str, ...], expected: Any) -> bool:
    present, actual = _authored_const_value(value, path)
    return present and type(actual) is type(expected) and actual == expected


def strict_schema_errors(value: Any, schema: Mapping[str, Any], *, path: str = "$", root: Mapping[str, Any] | None = None, limit: int = 128) -> list[dict[str, Any]]:
    root_schema = root or schema
    errors: list[dict[str, Any]] = []

    def add(kind: str, error_path: str, expected: Any = None, actual: Any = None) -> None:
        if len(errors) >= limit:
            return
        row: dict[str, Any] = {"path": error_path, "kind": kind}
        if expected is not None:
            row["expected"] = expected
        if actual is not None:
            row["actual"] = actual if isinstance(actual, (str, int, float, bool)) else type(actual).__name__
        errors.append(row)

    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _resolve_ref(root_schema, ref)
        if resolved is None:
            add("unresolved_ref", path, ref)
            return errors
        return strict_schema_errors(value, resolved, path=path, root=root_schema, limit=limit)

    if "const" in schema and value != schema.get("const"):
        add("const", path, schema.get("const"), value)
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        add("enum", path, enum, value)

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for branch in all_of:
            if isinstance(branch, Mapping) and len(errors) < limit:
                errors.extend(strict_schema_errors(value, branch, path=path, root=root_schema, limit=limit - len(errors)))

    one_of = schema.get("oneOf")
    union = one_of if isinstance(one_of, list) else schema.get("anyOf")
    if isinstance(union, list):
        exclusive = isinstance(one_of, list)
        branches = [branch for branch in union if isinstance(branch, Mapping)]
        branch_results = [strict_schema_errors(value, branch, path=path, root=root_schema, limit=limit) for branch in branches]
        matches = [branch for branch in branch_results if not branch]
        if not matches or (exclusive and len(matches) != 1):
            if exclusive:
                add("one_of", path, "exactly_one", len(matches))
            else:
                add("any_of", path)
            if not matches and branch_results:
                const_paths = [_schema_const_paths(branch) for branch in branches]
                shared = set.intersection(*(set(paths) for paths in const_paths)) if const_paths else set()
                discriminators = {
                    key for key in shared
                    if any(type(paths[key]) is not type(const_paths[0][key]) or paths[key] != const_paths[0][key]
                           for paths in const_paths[1:])
                }
                # Non-discriminating consts (e.g. place_item stackCost=1) are
                # ordinary validation constraints, not evidence of branch identity.
                selected = [index for index, paths in enumerate(const_paths)
                            if discriminators and all(_authored_const_matches(value, key, paths[key])
                                                      for key in discriminators)]
                all_identity_paths = {key for key in set().union(*(set(paths) for paths in const_paths))
                                      if all(isinstance(paths[key], str) for paths in const_paths if key in paths)
                                      and _authored_const_value(value, key)[0]}
                identity_selected = [index for index, paths in enumerate(const_paths)
                                     if all_identity_paths and all(key in paths and _authored_const_matches(value, key, paths[key])
                                                                   for key in all_identity_paths)]
                for selector in (set.intersection(*(set(paths) for paths in const_paths))
                                 if const_paths and any(set(paths) != set(const_paths[0]) for paths in const_paths) else set()):
                    present, actual = _authored_const_value(value, selector)
                    if (present and all(isinstance(paths[selector], str) for paths in const_paths)
                            and not any(_authored_const_matches(value, selector, paths[selector]) for paths in const_paths)):
                        selector_path = path
                        for part in selector:
                            selector_path = json_path_child(selector_path, part)
                        if not any(row["path"] == selector_path for row in errors):
                            add("one_of" if exclusive else "any_of", selector_path)
                if len(identity_selected) == 1:
                    # Exact string identity outranks foreign numeric constraints.
                    # A forbidden fixed cost is not evidence for another action.
                    selected = identity_selected
                if len(selected) != 1:
                    # A closed branch may omit an inner discriminator entirely.
                    # Use present exact consts hierarchically: input first, then
                    # action.kind only among compatible branches. Never choose
                    # by error count or absent foreign branch literals.
                    all_paths = set().union(*(set(paths) for paths in const_paths))
                    variant_paths = {key for key in all_paths if len({repr((type(paths[key]), paths[key]))
                                     for paths in const_paths if key in paths}) > 1}
                    present_paths = {key for key in variant_paths if _authored_const_value(value, key)[0]}
                    # A present selector that is unknown everywhere is diagnosed
                    # at that leaf; compatible other selectors still expose only
                    # errors shared by their remaining declared branches.
                    unknown = {key for key in present_paths if not any(key in paths and _authored_const_matches(value, key, paths[key]) for paths in const_paths)}
                    compatible = [i for i, paths in enumerate(const_paths) if present_paths - unknown and
                                  all(key in paths and _authored_const_matches(value, key, paths[key]) for key in present_paths - unknown)]
                    if unknown and compatible and present_paths != discriminators:
                        for key in unknown:
                            error_path = path
                            for part in key:
                                error_path = json_path_child(error_path, part)
                            add("one_of" if exclusive else "any_of", error_path)
                    exact = [i for i, paths in enumerate(const_paths)
                             if present_paths and all(key in paths and _authored_const_matches(value, key, paths[key])
                                                      for key in present_paths)]
                    if unknown and compatible and present_paths != discriminators:
                        selected = compatible
                    elif exact:
                        selected = exact
                    elif present_paths != discriminators:
                        # A known outer selector plus an unknown inner selector
                        # owns only that causal leaf, never the complete row.
                        for key in present_paths:
                            others = present_paths - {key}
                            candidates = [paths for paths in const_paths if others and
                                          all(other in paths and _authored_const_matches(value, other, paths[other]) for other in others)]
                            if candidates and all(key in paths for paths in candidates) and not any(
                                _authored_const_matches(value, key, paths[key]) for paths in candidates
                            ):
                                error_path = path
                                for part in key:
                                    error_path = json_path_child(error_path, part)
                                if not any(row["path"] == error_path for row in errors):
                                    add("one_of" if exclusive else "any_of", error_path)
                                break
                if not selected and not discriminators:
                    # Typed parameter unions use JSON type or an explicitly
                    # supplied property name as their discriminator. Preserve
                    # a known branch's exact invalid leaf, without choosing a
                    # missing branch on behalf of Author or Repair.
                    typed = [i for i, branch in enumerate(branches)
                             if not isinstance(branch.get("type"), str)
                             or _type_matches(value, branch["type"])]
                    if len(typed) == 1:
                        selected = typed
                    elif isinstance(value, dict) and typed:
                        keys = [set(branches[i].get("properties", {})) for i in typed]
                        distinct = set.union(*keys) - set.intersection(*keys)
                        present = set(value) & distinct
                        selected = [i for i, names in zip(typed, keys) if present and present <= names]
                        if not present:
                            selected = typed
                if len(selected) == 1:
                    errors.extend(branch_results[selected[0]][: max(0, limit - len(errors))])
                elif selected:
                    # Relaxed value variants may share one registered identity.
                    # Only errors common to every candidate have exact authority.
                    errors.extend(row for row in branch_results[selected[0]]
                                  if all(row in branch_results[index] for index in selected[1:]))
                elif not selected:
                    # A numeric constraint in a closed action variant must not
                    # hide its exact leaf when string discriminators uniquely
                    # identify the branch. This selects diagnostics, not values.
                    identity = {key for key in discriminators
                                if all(isinstance(paths[key], str) for paths in const_paths)}
                    identity_selected = [index for index, paths in enumerate(const_paths)
                                         if identity and all(_authored_const_matches(value, key, paths[key]) for key in identity)]
                    if len(identity_selected) == 1:
                        errors.extend(branch_results[identity_selected[0]][: max(0, limit - len(errors))])
                        return errors[:limit]
                    present = {key for key in discriminators if _authored_const_value(value, key)[0]}
                    partial = [index for index, paths in enumerate(const_paths)
                               if present and all(_authored_const_matches(value, key, paths[key]) for key in present)]
                    if partial and len(present) < len(discriminators):
                        # A known outer discriminator can still expose errors
                        # identical in every remaining branch, without guessing
                        # which nested variant the Author meant.
                        for row in branch_results[partial[0]]:
                            if row["kind"] in {"required", "additional_property"} and all(row in branch_results[index] for index in partial[1:]):
                                errors.append(row)
                                if len(errors) >= limit:
                                    break
                    elif not partial and present and len(present) == len(discriminators):
                        # All outer discriminators except one are exact, but its
                        # authored value is unknown. Point at that invalid leaf
                        # without advertising any variant's const as expected.
                        for key in discriminators:
                            other_keys = present - {key}
                            if not other_keys or key not in present:
                                continue
                            candidates = [paths for paths in const_paths
                                          if all(_authored_const_matches(value, other, paths[other])
                                                 for other in other_keys)]
                            if candidates and not any(_authored_const_matches(value, key, paths[key])
                                                      for paths in candidates):
                                error_path = path
                                for part in key:
                                    error_path = json_path_child(error_path, part)
                                add("one_of" if exclusive else "any_of", error_path)
                                break
        return errors[:limit]

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _type_matches(value, expected_type):
        add("type", path, expected_type, value)
        return errors[:limit]

    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            add("min_length", path, schema["minLength"], len(value))
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            add("max_length", path, schema["maxLength"], len(value))
        if isinstance(schema.get("pattern"), str) and re.fullmatch(str(schema["pattern"]), value) is None:
            add("pattern", path, schema["pattern"], value)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        finite = _is_finite_number(value)
        if not finite:
            add("finite", path, "finite number", value)
        if schema.get("minimum") is not None and value < schema["minimum"]:
            add("minimum", path, schema["minimum"], value)
        if schema.get("maximum") is not None and value > schema["maximum"]:
            add("maximum", path, schema["maximum"], value)
        step = schema.get("multipleOf")
        if isinstance(step, (int, float)) and step > 0 and finite:
            # The only authored fractional step is an exact binary half; check
            # the quotient without rounding or approximating engine quantities.
            if value % step != 0:
                add("multiple_of", path, step, value)

    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            add("min_items", path, schema["minItems"], len(value))
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            add("max_items", path, schema["maxItems"], len(value))
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, child in enumerate(value):
                errors.extend(strict_schema_errors(child, item_schema, path=json_path_child(path, index), root=root_schema, limit=max(0, limit - len(errors))))
                if len(errors) >= limit:
                    break

    if isinstance(value, dict):
        if isinstance(schema.get("minProperties"), int) and len(value) < schema["minProperties"]:
            add("min_properties", path, schema["minProperties"], len(value))
        condition = schema.get("if")
        if isinstance(condition, Mapping) and not strict_schema_errors(value, condition, path=path, root=root_schema, limit=limit):
            consequent = schema.get("then")
            if isinstance(consequent, Mapping):
                errors.extend(strict_schema_errors(value, consequent, path=path, root=root_schema, limit=max(0, limit - len(errors))))
        raw_properties = schema.get("properties")
        properties: Mapping[str, Any] = raw_properties if isinstance(raw_properties, Mapping) else {}
        raw_required = schema.get("required")
        required: list[Any] = raw_required if isinstance(raw_required, list) else []
        for key in required:
            if key not in value:
                add("required", json_path_child(path, key))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    add("additional_property", json_path_child(path, str(key)))
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, Mapping):
                errors.extend(strict_schema_errors(child, child_schema, path=json_path_child(path, str(key)), root=root_schema, limit=max(0, limit - len(errors))))
                if len(errors) >= limit:
                    break
    return errors[:limit]


__all__ = ["strict_schema_errors"]
