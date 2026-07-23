"""Immutable Author and normalized-runtime function contract primitives.

The registry owns public provider/prompt parameters plus the narrow normalized IR
used between typed lowerers and the finite compiler.  Gameplay value transforms stay
in ``semantics.py``; this module only describes and validates their boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable, Sequence


_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FUNCTION_SOURCE_PATH = "$function"


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
class NormalizedParamContract:
    """Compiler-visible IR parameter that is never accepted from the Author.

    These names are emitted only by a declared typed lowerer.  Keeping them separate
    from ``EngineParamContract`` prevents internal aliases from silently expanding the
    provider schema.
    """

    name: str
    compiled_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoweredParamBinding:
    """Authored source path(s) that may produce normalized target parameter(s)."""

    source_path: str
    target_param_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EngineLowererContract:
    """One typed Author function lowering edge into the normalized compiler IR."""

    target_function: str
    bindings: tuple[LoweredParamBinding, ...]


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
    """Immutable contract descriptor for one Author engine function."""

    name: str
    meaning: str
    params: tuple[EngineParamContract, ...]
    root_executor: bool
    requires_root_executor: bool
    repair_groups: tuple[RepairGroupContract, ...]
    normalized_only_params: tuple[NormalizedParamContract, ...] = ()
    lowerers: tuple[EngineLowererContract, ...] = ()


def _blank(value: Any) -> bool:
    return not str(value or "").strip()


def _valid_path(value: object, *, allow_function: bool = False) -> bool:
    path = str(value or "").strip()
    if allow_function and path == FUNCTION_SOURCE_PATH:
        return True
    return bool(path) and all(_PATH_SEGMENT_RE.fullmatch(segment) for segment in path.split("."))


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
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (tuple, list)):
        return None
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        out.append(item)
    return tuple(out)


def _declared_authored_paths(spec: EngineFunctionContract) -> set[str]:
    paths: set[str] = set()
    for param in spec.params if isinstance(spec.params, tuple) else ():
        if not isinstance(param, EngineParamContract):
            continue
        name = str(param.name or "").strip()
        if not name:
            continue
        paths.add(name)
        for nested in param.nested_wire_paths if isinstance(param.nested_wire_paths, tuple) else ():
            if isinstance(nested, NestedWirePathContract) and str(nested.path or "").strip():
                paths.add(f"{name}.{str(nested.path).strip()}")
    return paths


def _declared_normalized_paths(spec: EngineFunctionContract) -> set[str]:
    paths = _declared_authored_paths(spec)
    for param in spec.normalized_only_params if isinstance(spec.normalized_only_params, tuple) else ():
        if isinstance(param, NormalizedParamContract) and str(param.name or "").strip():
            paths.add(str(param.name).strip())
    return paths


def validate_engine_function_contracts(
    specs: Sequence[EngineFunctionContract] | Iterable[EngineFunctionContract],
) -> tuple[str, ...]:
    """Validate the registry and every cross-function lowering edge."""

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
            if not _TOKEN_RE.fullmatch(key):
                errors.append(f"{fn_label}: invalid function name {key!r}")
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
            errors.append(f"{fn_label}: root_executor and requires_root_executor cannot both be true")

        if not isinstance(spec.params, tuple):
            errors.append(f"{fn_label}: params must be a tuple")
            param_iter: Sequence[Any] = ()
        else:
            param_iter = spec.params
        if not isinstance(spec.repair_groups, tuple):
            errors.append(f"{fn_label}: repair_groups must be a tuple")
            group_iter: Sequence[Any] = ()
        else:
            group_iter = spec.repair_groups
        if not isinstance(spec.normalized_only_params, tuple):
            errors.append(f"{fn_label}: normalized_only_params must be a tuple")
            normalized_iter: Sequence[Any] = ()
        else:
            normalized_iter = spec.normalized_only_params
        if not isinstance(spec.lowerers, tuple):
            errors.append(f"{fn_label}: lowerers must be a tuple")
            lowerer_iter: Sequence[Any] = ()
        else:
            lowerer_iter = spec.lowerers

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
                if not _PATH_SEGMENT_RE.fullmatch(pkey):
                    errors.append(f"{p_label}: invalid param name {pkey!r}")
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
                if not _valid_path(path):
                    errors.append(f"{p_label}: invalid nested wire path {nested.path!r}")
                if path in seen_nested_paths:
                    errors.append(f"{p_label}: duplicate nested wire path {path!r}")
                seen_nested_paths.add(path)
                nested_fields = _normalize_compiled_fields(nested.compiled_fields)
                if not nested_fields or any(_blank(field) for field in nested_fields):
                    errors.append(f"{p_label}.{path}: nested compiled_fields must be non-empty")

            obligation = _as_wire_obligation(param.wire_obligation)
            if obligation is None:
                errors.append(f"{p_label}: unknown wire_obligation {param.wire_obligation!r}")
                continue
            compiled = _normalize_compiled_fields(param.compiled_fields)
            if compiled is None:
                errors.append(f"{p_label}: compiled_fields must be a tuple of strings")
                continue
            if obligation is WireObligation.FINAL_WIRE:
                if not compiled and not param.provenance_via_lowerer:
                    errors.append(
                        f"{p_label}: final_wire param requires non-empty compiled_fields "
                        "or provenance_via_lowerer"
                    )
                if compiled and param.provenance_via_lowerer:
                    errors.append(
                        f"{p_label}: static compiled_fields and provenance_via_lowerer are mutually exclusive owners"
                    )
            elif obligation is WireObligation.CONTROL_DERIVED:
                if param.provenance_via_lowerer:
                    errors.append(
                        f"{p_label}: control_derived param is a compiler control, not a lowerer-owned final field"
                    )
            else:
                if compiled and obligation is WireObligation.NON_WIRE:
                    errors.append(f"{p_label}: non_wire param must not declare compiled_fields {compiled!r}")
                if param.provenance_via_lowerer:
                    errors.append(f"{p_label}: {obligation.value} param must not use provenance_via_lowerer")

        seen_normalized: set[str] = set()
        for n_index, normalized in enumerate(normalized_iter):
            n_label = f"{fn_label}.normalized_only_params[{n_index}]"
            if not isinstance(normalized, NormalizedParamContract):
                errors.append(f"{n_label}: expected NormalizedParamContract, got {type(normalized).__name__}")
                continue
            nname = str(normalized.name or "").strip()
            if not nname or not _PATH_SEGMENT_RE.fullmatch(nname):
                errors.append(f"{n_label}: invalid normalized param name {normalized.name!r}")
            if nname in param_names:
                errors.append(f"{n_label}: normalized-only param {nname!r} duplicates public param")
            if nname in seen_normalized:
                errors.append(f"{n_label}: duplicate normalized-only param {nname!r}")
            seen_normalized.add(nname)
            compiled = _normalize_compiled_fields(normalized.compiled_fields)
            if not compiled or any(_blank(field) for field in compiled):
                errors.append(f"{n_label}: compiled_fields must be a non-empty tuple")

        seen_lowerer_targets: set[str] = set()
        for l_index, lowerer in enumerate(lowerer_iter):
            l_label = f"{fn_label}.lowerers[{l_index}]"
            if not isinstance(lowerer, EngineLowererContract):
                errors.append(f"{l_label}: expected EngineLowererContract, got {type(lowerer).__name__}")
                continue
            target = str(lowerer.target_function or "").strip()
            if not target or not _TOKEN_RE.fullmatch(target):
                errors.append(f"{l_label}: invalid target function {lowerer.target_function!r}")
            if target == name.strip():
                errors.append(f"{l_label}: lowerer target cannot reference itself")
            if target in seen_lowerer_targets:
                errors.append(f"{l_label}: duplicate lowerer target {target!r}")
            seen_lowerer_targets.add(target)
            if not isinstance(lowerer.bindings, tuple) or not lowerer.bindings:
                errors.append(f"{l_label}: bindings must be a non-empty tuple")
                bindings: Sequence[Any] = ()
            else:
                bindings = lowerer.bindings
            seen_bindings: set[tuple[str, tuple[str, ...]]] = set()
            for b_index, binding in enumerate(bindings):
                b_label = f"{l_label}.bindings[{b_index}]"
                if not isinstance(binding, LoweredParamBinding):
                    errors.append(f"{b_label}: expected LoweredParamBinding, got {type(binding).__name__}")
                    continue
                source = str(binding.source_path or "").strip()
                if not _valid_path(source, allow_function=True):
                    errors.append(f"{b_label}: invalid source path {binding.source_path!r}")
                targets = binding.target_param_paths
                if not isinstance(targets, tuple) or not targets:
                    errors.append(f"{b_label}: target_param_paths must be a non-empty tuple")
                    targets = ()
                for target_path in targets:
                    if not _valid_path(target_path):
                        errors.append(f"{b_label}: invalid target param path {target_path!r}")
                identity = (source, tuple(str(path) for path in targets))
                if identity in seen_bindings:
                    errors.append(f"{b_label}: duplicate lowerer binding {identity!r}")
                seen_bindings.add(identity)

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
            if _blank(group.policy_owner):
                errors.append(f"{g_label}: blank policy_owner")
            for member in members:
                mkey = str(member or "").strip()
                if not mkey:
                    errors.append(f"{g_label}: blank repair group member")
                elif mkey not in param_names:
                    errors.append(f"{g_label}: repair member {mkey!r} is not in params")

    by_name = {
        str(spec.name).strip(): spec
        for spec in ordered
        if isinstance(spec, EngineFunctionContract) and str(spec.name or "").strip()
    }
    for index, spec in enumerate(ordered):
        if not isinstance(spec, EngineFunctionContract):
            continue
        fn_name = str(spec.name or "").strip()
        fn_label = f"function[{index}]({fn_name})" if fn_name else f"function[{index}]"
        authored_paths = _declared_authored_paths(spec)
        lowerers = spec.lowerers if isinstance(spec.lowerers, tuple) else ()
        bound_source_paths: set[str] = set()
        for l_index, lowerer in enumerate(lowerers):
            if not isinstance(lowerer, EngineLowererContract):
                continue
            target_name = str(lowerer.target_function or "").strip()
            target_spec = by_name.get(target_name)
            l_label = f"{fn_label}.lowerers[{l_index}]"
            if target_spec is None:
                errors.append(f"{l_label}: lowerer target {target_name!r} is not in registry")
                continue
            if target_spec.root_executor and not spec.root_executor:
                errors.append(
                    f"{l_label}: source must be root_executor because target {target_name!r} is root_executor"
                )
            target_paths = _declared_normalized_paths(target_spec)
            for binding in lowerer.bindings if isinstance(lowerer.bindings, tuple) else ():
                if not isinstance(binding, LoweredParamBinding):
                    continue
                source = str(binding.source_path or "").strip()
                if source != FUNCTION_SOURCE_PATH:
                    bound_source_paths.add(source)
                    if source not in authored_paths:
                        errors.append(f"{l_label}: source path {source!r} is not declared by {fn_name!r}")
                for target_path in binding.target_param_paths:
                    path = str(target_path or "").strip()
                    if path not in target_paths:
                        errors.append(
                            f"{l_label}: target path {path!r} is not in normalized grammar for {target_name!r}"
                        )
        if lowerers:
            for param in spec.params if isinstance(spec.params, tuple) else ():
                if not isinstance(param, EngineParamContract) or not param.provenance_via_lowerer:
                    continue
                name = str(param.name or "").strip()
                nested = {
                    f"{name}.{str(row.path).strip()}"
                    for row in param.nested_wire_paths
                    if isinstance(row, NestedWirePathContract)
                }
                if name not in bound_source_paths and not nested.intersection(bound_source_paths):
                    errors.append(
                        f"{fn_label}: lowerer-owned param {name!r} has no typed lowerer binding"
                    )

    # Reject cycles independently of declaration order.
    edges = {
        name: tuple(
            str(lowerer.target_function or "").strip()
            for lowerer in spec.lowerers
            if isinstance(lowerer, EngineLowererContract)
        )
        for name, spec in by_name.items()
    }
    for origin in sorted(edges):
        active: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in active:
                errors.append(f"function({origin}): lowerer cycle reaches {node!r}")
                return
            if node in visited:
                return
            active.add(node)
            for target in edges.get(node, ()):
                if target in edges:
                    visit(target)
            active.remove(node)
            visited.add(node)

        visit(origin)

    return tuple(dict.fromkeys(errors))


__all__ = [
    "FUNCTION_SOURCE_PATH",
    "ParamValueKind",
    "NestedWirePathContract",
    "NormalizedParamContract",
    "LoweredParamBinding",
    "EngineLowererContract",
    "WireObligation",
    "EngineParamContract",
    "RepairGroupContract",
    "EngineFunctionContract",
    "validate_engine_function_contracts",
]
