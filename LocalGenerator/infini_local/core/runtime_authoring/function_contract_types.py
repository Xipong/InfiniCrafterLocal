"""Immutable Author engine function/parameter wire-contract primitives.

Typed registry descriptors only. No compiler behavior, item/name/prose routing,
generic trigger/action runtime, provider logic, or cross-version adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable, Sequence


_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class WireObligation(str, Enum):
    """How an authored parameter relates to executable final wire."""

    FINAL_WIRE = "final_wire"
    DEFERRED_VFX = "deferred_vfx"
    CONTROL_DERIVED = "control_derived"
    NON_WIRE = "non_wire"


class ParamValueKind(str, Enum):
    """Closed provider grammar kinds; gameplay bounds remain compiler policy."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    ENUM = "enum"
    OBJECT = "object"
    LIST = "list"


@dataclass(frozen=True, slots=True)
class NestedWirePathContract:
    """One nested authored leaf and its exact compiled destinations."""

    path: str
    compiled_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompiledFieldSourceOverride:
    """Exact compiler/lowerer-owned source paths for one compiled field."""

    compiled_field: str
    source_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EngineParamContract:
    """One authored parameter on an engine function."""

    name: str
    prompt_description: str
    value_kind: ParamValueKind | str
    example_value: Any
    compiled_fields: tuple[str, ...]
    wire_obligation: WireObligation
    provenance_via_lowerer: bool = False
    enum_values: tuple[str, ...] = ()
    string_pattern: str = ""
    object_model: type[Any] | None = None
    list_item_model: type[Any] | None = None
    function_card_visible: bool = True
    prompt_group: str = ""
    nested_wire_paths: tuple[NestedWirePathContract, ...] = ()


@dataclass(frozen=True, slots=True)
class RepairGroupContract:
    """Atomic repair dependency group referencing a canonical policy owner."""

    members: tuple[str, ...]
    policy_owner: str


@dataclass(frozen=True, slots=True)
class EngineFunctionContract:
    """Immutable wire-contract descriptor for one Author engine function."""

    name: str
    meaning: str
    params: tuple[EngineParamContract, ...]
    root_executor: bool
    requires_root_executor: bool
    allowed_result_kinds: tuple[str, ...]
    repair_groups: tuple[RepairGroupContract, ...]
    compiled_source_overrides: tuple[CompiledFieldSourceOverride, ...] = ()


def _blank(value: Any) -> bool:
    return not str(value or "").strip()


def _as_wire_obligation(raw: WireObligation | str) -> WireObligation | None:
    if isinstance(raw, WireObligation):
        return raw
    try:
        return WireObligation(str(raw))
    except ValueError:
        return None


def _as_value_kind(raw: ParamValueKind | str) -> ParamValueKind | None:
    if isinstance(raw, ParamValueKind):
        return raw
    try:
        return ParamValueKind(str(raw))
    except ValueError:
        return None


def _example_is_immutable(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if isinstance(value, tuple):
        return all(_example_is_immutable(item) for item in value)
    return False


def _normalize_compiled_fields(raw: Any) -> tuple[str, ...] | None:
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)):
        return None
    if not isinstance(raw, (tuple, list)):
        return None
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        out.append(item)
    return tuple(out)


def validate_engine_function_contracts(
    specs: Sequence[EngineFunctionContract] | Iterable[EngineFunctionContract],
) -> tuple[str, ...]:
    """Validate a collection of function contracts.

    Returns a deterministic tuple of human-readable error strings (empty when
    the registry is structurally sound). Does not compile or execute gameplay.
    """
    errors: list[str] = []
    seen_function_names: dict[str, int] = {}
    ordered = list(specs)

    for index, spec in enumerate(ordered):
        if not isinstance(spec, EngineFunctionContract):
            errors.append(f"specs[{index}]: expected EngineFunctionContract, got {type(spec).__name__}")
            continue

        fn_label = f"function[{index}]"
        name = str(spec.name) if spec.name is not None else ""
        if _blank(name):
            errors.append(f"{fn_label}: blank function name")
        else:
            fn_label = f"function[{index}]({name.strip()})"
            key = name.strip()
            if key in seen_function_names:
                errors.append(
                    f"{fn_label}: duplicate function name {key!r} "
                    f"(also at index {seen_function_names[key]})"
                )
            else:
                seen_function_names[key] = index

        if _blank(spec.meaning):
            errors.append(f"{fn_label}: blank function meaning")

        if spec.root_executor and spec.requires_root_executor:
            errors.append(
                f"{fn_label}: root_executor and requires_root_executor cannot both be true"
            )

        if not isinstance(spec.params, tuple):
            errors.append(f"{fn_label}: params must be a tuple")
            param_iter: Sequence[Any] = ()
        else:
            param_iter = spec.params

        if not isinstance(spec.allowed_result_kinds, tuple):
            errors.append(f"{fn_label}: allowed_result_kinds must be a tuple")

        if not isinstance(spec.repair_groups, tuple):
            errors.append(f"{fn_label}: repair_groups must be a tuple")
            group_iter: Sequence[Any] = ()
        else:
            group_iter = spec.repair_groups

        if not isinstance(spec.compiled_source_overrides, tuple):
            errors.append(f"{fn_label}: compiled_source_overrides must be a tuple")
            source_overrides: Sequence[Any] = ()
        else:
            source_overrides = spec.compiled_source_overrides

        seen_override_fields: set[str] = set()
        for override in source_overrides:
            if not isinstance(override, CompiledFieldSourceOverride):
                errors.append(f"{fn_label}: compiled_source_overrides contains a non-contract value")
                continue
            field = str(override.compiled_field or "").strip()
            if not field:
                errors.append(f"{fn_label}: compiled source override has a blank field")
            if field in seen_override_fields:
                errors.append(f"{fn_label}: duplicate compiled source override for {field!r}")
            seen_override_fields.add(field)
            if not isinstance(override.source_paths, tuple) or not override.source_paths:
                errors.append(f"{fn_label}.{field}: source_paths must be a non-empty tuple")
                continue
            for source_path in override.source_paths:
                path = str(source_path or "").strip()
                if not path or any(
                    not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", segment)
                    for segment in path.split(".")
                ):
                    errors.append(f"{fn_label}.{field}: invalid compiler source path {source_path!r}")

        param_names: set[str] = set()
        seen_params: dict[str, int] = {}
        for p_index, param in enumerate(param_iter):
            p_label = f"{fn_label}.params[{p_index}]"
            if not isinstance(param, EngineParamContract):
                errors.append(f"{p_label}: expected EngineParamContract, got {type(param).__name__}")
                continue

            pname = str(param.name) if param.name is not None else ""
            if _blank(pname):
                errors.append(f"{p_label}: blank param name")
            else:
                pkey = pname.strip()
                p_label = f"{fn_label}.params[{p_index}]({pkey})"
                if pkey in seen_params:
                    errors.append(
                        f"{p_label}: duplicate param name {pkey!r} "
                        f"(also at params index {seen_params[pkey]})"
                    )
                else:
                    seen_params[pkey] = p_index
                    param_names.add(pkey)

            if _blank(param.prompt_description):
                errors.append(f"{p_label}: blank param prompt_description")

            value_kind = _as_value_kind(param.value_kind)
            if value_kind is None:
                errors.append(f"{p_label}: unknown value_kind {param.value_kind!r}")
            else:
                if not isinstance(param.enum_values, tuple):
                    errors.append(f"{p_label}: enum_values must be a tuple")
                    enum_values: tuple[Any, ...] = ()
                else:
                    enum_values = param.enum_values
                enum_tokens = tuple(str(value).strip() for value in enum_values)
                enum_tokens_valid = bool(enum_tokens) and all(enum_tokens)
                if value_kind is ParamValueKind.ENUM:
                    if not enum_tokens_valid:
                        errors.append(f"{p_label}: enum value_kind requires non-empty enum_values")
                    elif len(set(enum_tokens)) != len(enum_tokens):
                        errors.append(f"{p_label}: enum_values contains duplicates")
                elif enum_values:
                    errors.append(f"{p_label}: enum_values is valid only for enum value_kind")

                pattern = str(param.string_pattern or "")
                if pattern and value_kind is not ParamValueKind.STRING:
                    errors.append(f"{p_label}: string_pattern is valid only for string value_kind")

                if value_kind is ParamValueKind.OBJECT:
                    if not isinstance(param.object_model, type):
                        errors.append(f"{p_label}: object value_kind requires object_model")
                elif param.object_model is not None:
                    errors.append(f"{p_label}: object_model is valid only for object value_kind")

                if value_kind is ParamValueKind.LIST:
                    if not isinstance(param.list_item_model, type):
                        errors.append(f"{p_label}: list value_kind requires list_item_model")
                elif param.list_item_model is not None:
                    errors.append(f"{p_label}: list_item_model is valid only for list value_kind")

            if not _example_is_immutable(param.example_value):
                errors.append(f"{p_label}: example_value must be an immutable JSON scalar/tuple")
            prompt_group = str(param.prompt_group or "").strip()
            if not param.function_card_visible and not prompt_group:
                errors.append(f"{p_label}: hidden params require prompt_group")
            if prompt_group and not _TOKEN_RE.fullmatch(prompt_group):
                errors.append(f"{p_label}: invalid prompt_group {prompt_group!r}")

            if not isinstance(param.nested_wire_paths, tuple):
                errors.append(f"{p_label}: nested_wire_paths must be a tuple")
                nested_paths: Sequence[Any] = ()
            else:
                nested_paths = param.nested_wire_paths
            if nested_paths and value_kind not in {ParamValueKind.OBJECT, ParamValueKind.LIST}:
                errors.append(f"{p_label}: nested_wire_paths require object/list value_kind")
            seen_nested_paths: set[str] = set()
            for nested in nested_paths:
                if not isinstance(nested, NestedWirePathContract):
                    errors.append(f"{p_label}: nested_wire_paths contains a non-contract value")
                    continue
                path = str(nested.path or "").strip()
                if not path or any(
                    not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", segment)
                    for segment in path.split(".")
                ):
                    errors.append(f"{p_label}: invalid nested wire path {nested.path!r}")
                if path in seen_nested_paths:
                    errors.append(f"{p_label}: duplicate nested wire path {path!r}")
                seen_nested_paths.add(path)
                nested_fields = _normalize_compiled_fields(nested.compiled_fields)
                if not nested_fields or any(_blank(field) for field in nested_fields):
                    errors.append(f"{p_label}.{path}: nested compiled_fields must be non-empty")

            obligation = _as_wire_obligation(param.wire_obligation)
            if obligation is None:
                errors.append(
                    f"{p_label}: unknown wire_obligation {param.wire_obligation!r}"
                )
                continue

            compiled = _normalize_compiled_fields(param.compiled_fields)
            if compiled is None:
                errors.append(f"{p_label}: compiled_fields must be a tuple of strings")
                continue

            if obligation in (WireObligation.FINAL_WIRE, WireObligation.CONTROL_DERIVED):
                if not compiled and not param.provenance_via_lowerer:
                    errors.append(
                        f"{p_label}: {obligation.value} param requires non-empty compiled_fields "
                        "or provenance_via_lowerer"
                    )
                if compiled and param.provenance_via_lowerer:
                    errors.append(
                        f"{p_label}: static compiled_fields and provenance_via_lowerer "
                        "are mutually exclusive owners"
                    )
            else:
                if compiled:
                    if obligation is WireObligation.NON_WIRE:
                        errors.append(
                            f"{p_label}: non_wire param must not declare compiled_fields {compiled!r}"
                        )
                if param.provenance_via_lowerer:
                    errors.append(
                        f"{p_label}: {obligation.value} param must not use provenance_via_lowerer"
                    )

        for g_index, group in enumerate(group_iter):
            g_label = f"{fn_label}.repair_groups[{g_index}]"
            if not isinstance(group, RepairGroupContract):
                errors.append(f"{g_label}: expected RepairGroupContract, got {type(group).__name__}")
                continue

            if not isinstance(group.members, tuple):
                errors.append(f"{g_label}: members must be a tuple")
                members: Sequence[Any] = ()
            else:
                members = group.members

            owner = str(group.policy_owner) if group.policy_owner is not None else ""
            if _blank(owner):
                errors.append(f"{g_label}: blank policy_owner")

            for member in members:
                member_s = str(member) if member is not None else ""
                if _blank(member_s):
                    errors.append(f"{g_label}: blank repair group member")
                    continue
                mkey = member_s.strip()
                if mkey not in param_names:
                    errors.append(
                        f"{g_label}: repair member {mkey!r} is not in params"
                    )

    return tuple(errors)


__all__ = [
    "ParamValueKind",
    "NestedWirePathContract",
    "CompiledFieldSourceOverride",
    "WireObligation",
    "EngineParamContract",
    "RepairGroupContract",
    "EngineFunctionContract",
    "validate_engine_function_contracts",
]
