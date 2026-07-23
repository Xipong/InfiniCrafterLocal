from __future__ import annotations

import math
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, StringConstraints, ValidationError, create_model

from infini_local.core.runtime_authoring.engine_param_boundaries import (
    ArmorSetBonusParamBoundary,
    BuffParamBoundary,
    EquipmentStatsParamBoundary,
    GeneratedBuffParamBoundary,
    StrictEngineParamModel,
)
from infini_local.core.runtime_authoring.function_contract_registry import (
    ENGINE_FUNCTION_CONTRACT_BY_NAME,
    accepted_engine_param_names,
)
from infini_local.core.runtime_authoring.function_contract_types import (
    EngineParamContract,
    ParamValueKind,
)


def _param_contract(fn: str, name: str) -> EngineParamContract:
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(str(fn or ""))
    if spec is None:
        raise KeyError(fn)
    for param in spec.params:
        if param.name == name:
            return param
    raise KeyError(f"{fn}.{name}")


def engine_param_enum_values(fn: str, name: str) -> tuple[str, ...]:
    """Return the canonical closed enum values from the immutable registry."""

    return tuple(_param_contract(fn, name).enum_values)


def _literal_type(values: tuple[str, ...]) -> Any:
    literal_factory: Any = Literal
    # ``typing.Literal`` caches equal value sets without preserving which caller's
    # order won first. Canonical sorting keeps provider schema bytes independent
    # of the first function validated in this process.
    return literal_factory.__getitem__(tuple(sorted(values)))


def _param_annotation(fn: str, name: str) -> Any:
    param = _param_contract(fn, name)
    try:
        kind = ParamValueKind(param.value_kind)
    except ValueError as exc:  # protected by registry validation; fail closed if corrupted
        raise TypeError(f"unsupported provider kind for {fn}.{name}: {param.value_kind!r}") from exc

    if kind is ParamValueKind.BOOLEAN:
        return bool
    if kind is ParamValueKind.INTEGER:
        return int
    if kind is ParamValueKind.NUMBER:
        return int | float
    if kind is ParamValueKind.ENUM:
        return _literal_type(tuple(param.enum_values))
    if kind is ParamValueKind.OBJECT:
        if param.object_model is None:
            raise TypeError(f"missing object model for {fn}.{name}")
        return param.object_model
    if kind is ParamValueKind.LIST:
        if param.list_item_model is None:
            raise TypeError(f"missing list item model for {fn}.{name}")
        return list[param.list_item_model]
    if kind is ParamValueKind.STRING and param.string_pattern:
        return Annotated[str, StringConstraints(pattern=param.string_pattern)]
    if kind is ParamValueKind.STRING:
        return str
    raise TypeError(f"unsupported provider kind for {fn}.{name}: {kind.value}")


@lru_cache(maxsize=None)
def engine_params_model(fn: str) -> type[BaseModel]:
    if fn not in ENGINE_FUNCTION_CONTRACT_BY_NAME:
        raise KeyError(fn)
    fields: dict[str, tuple[Any, Any]] = {}
    for name in sorted(accepted_engine_param_names(fn)):
        annotation = _param_annotation(fn, name)
        fields[name] = (annotation | None, None)
    model_factory: Any = create_model
    return model_factory(
        "EngineParams_" + "".join(part.capitalize() for part in fn.split("_")),
        __base__=StrictEngineParamModel,
        **fields,
    )


def validate_engine_call_params(fn: str, params: Any) -> tuple[dict[str, Any] | None, list[str]]:
    if fn not in ENGINE_FUNCTION_CONTRACT_BY_NAME:
        return None, [f"unknown function {fn}"]
    if not isinstance(params, dict):
        return None, ["params must be an object"]
    try:
        parsed = engine_params_model(fn).model_validate(params)
    except ValidationError as exc:
        errors: list[str] = []
        for row in exc.errors(include_url=False):
            loc = ".".join(str(x) for x in row.get("loc") or ())
            msg = str(row.get("msg") or "invalid")
            errors.append(f"{loc}: {msg}" if loc else msg)
        return None, errors
    out = parsed.model_dump(exclude_none=True)
    for key, value in out.items():
        if isinstance(value, float) and not math.isfinite(value):
            return None, [f"{key}: finite number required"]
    return out, []


def engine_contract_inventory() -> dict[str, dict[str, str]]:
    return {
        fn: {
            name: str(_param_annotation(fn, name))
            for name in sorted(accepted_engine_param_names(fn))
        }
        for fn in sorted(ENGINE_FUNCTION_CONTRACT_BY_NAME)
    }


__all__ = [
    "StrictEngineParamModel",
    "BuffParamBoundary",
    "GeneratedBuffParamBoundary",
    "EquipmentStatsParamBoundary",
    "ArmorSetBonusParamBoundary",
    "engine_param_enum_values",
    "engine_params_model",
    "validate_engine_call_params",
    "engine_contract_inventory",
]
