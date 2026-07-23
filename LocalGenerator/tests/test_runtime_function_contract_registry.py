"""Canonical runtime function registry: small invariants, not implementation snapshots.

The old suite froze hundreds of kilobytes of derived JSON and still missed lowerer /
provenance drift.  These tests instead protect ownership boundaries: provider and
prompt are projections, every typed lowerer has a closed output grammar, and the
original authored call survives normalization for provenance.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

import pytest

from infini_local.core.runtime_authoring.function_contract_types import (
    EngineFunctionContract,
    EngineLowererContract,
    EngineParamContract,
    LoweredParamBinding,
    NestedWirePathContract,
    NormalizedParamContract,
    ParamValueKind,
    RepairGroupContract,
    WireObligation,
    validate_engine_function_contracts,
)


def _param(
    name: str = "damage",
    *,
    prompt_description: str = "Base damage value.",
    value_kind: ParamValueKind | str = ParamValueKind.INTEGER,
    example_value: Any = 10,
    compiled_fields: tuple[str, ...] = ("damage",),
    wire_obligation: WireObligation | str = WireObligation.FINAL_WIRE,
    provenance_via_lowerer: bool = False,
    enum_values: tuple[str, ...] = (),
    string_pattern: str = "",
    object_model: type[Any] | None = None,
    list_item_model: type[Any] | None = None,
    function_card_visible: bool = True,
    prompt_group: str = "",
    nested_wire_paths: tuple[NestedWirePathContract, ...] = (),
) -> EngineParamContract:
    return EngineParamContract(
        name=name,
        prompt_description=prompt_description,
        value_kind=value_kind,
        example_value=example_value,
        compiled_fields=compiled_fields,
        wire_obligation=wire_obligation,
        provenance_via_lowerer=provenance_via_lowerer,
        enum_values=enum_values,
        string_pattern=string_pattern,
        object_model=object_model,
        list_item_model=list_item_model,
        function_card_visible=function_card_visible,
        prompt_group=prompt_group,
        nested_wire_paths=nested_wire_paths,
    )


def _fn(
    name: str = "set_item_stats",
    *,
    meaning: str = "Base item stats.",
    params: tuple[EngineParamContract, ...] | None = None,
    root_executor: bool = False,
    requires_root_executor: bool = False,
    repair_groups: tuple[RepairGroupContract, ...] = (),
    normalized_only_params: tuple[NormalizedParamContract, ...] = (),
    lowerers: tuple[EngineLowererContract, ...] = (),
) -> EngineFunctionContract:
    return EngineFunctionContract(
        name=name,
        meaning=meaning,
        params=params if params is not None else (_param(),),
        root_executor=root_executor,
        requires_root_executor=requires_root_executor,
        repair_groups=repair_groups,
        normalized_only_params=normalized_only_params,
        lowerers=lowerers,
    )


def test_production_registry_validates_without_shadow_side_tables() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
    )

    assert validate_engine_function_contracts(ENGINE_FUNCTION_CONTRACTS) == ()
    for spec in ENGINE_FUNCTION_CONTRACTS:
        assert not hasattr(spec, "allowed_result_kinds")
        assert not hasattr(spec, "compiled_source_overrides")
        assert not hasattr(spec, "lowered_function_names")


def test_provider_and_prompt_are_exact_registry_projections() -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
        accepted_engine_param_names,
        engine_function_catalog,
    )

    catalog = engine_function_catalog()
    for spec in ENGINE_FUNCTION_CONTRACTS:
        provider_names = set(engine_params_model(spec.name).model_json_schema()["properties"])
        assert provider_names == set(accepted_engine_param_names(spec.name))
        assert set(catalog[spec.name]["params"]) == {
            param.name for param in spec.params if param.function_card_visible
        }
        assert bool(catalog[spec.name].get("requiresRootExecutor")) is spec.requires_root_executor


def test_root_shared_params_have_one_canonical_type_owner() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
        ENGINE_FUNCTION_CONTRACT_BY_NAME,
        ROOT_EXECUTOR_SHARED_PARAM_NAMES,
    )

    target = {
        param.name: param
        for param in ENGINE_FUNCTION_CONTRACT_BY_NAME["shoot_projectile"].params
        if param.name in ROOT_EXECUTOR_SHARED_PARAM_NAMES
    }
    assert set(target) == set(ROOT_EXECUTOR_SHARED_PARAM_NAMES)
    for spec in ENGINE_FUNCTION_CONTRACTS:
        if not spec.root_executor:
            continue
        current = {param.name: param for param in spec.params}
        assert ROOT_EXECUTOR_SHARED_PARAM_NAMES <= current.keys(), spec.name
        for name, owner in target.items():
            derived = current[name]
            assert derived.value_kind == owner.value_kind, (spec.name, name)
            assert derived.example_value == owner.example_value, (spec.name, name)
            assert derived.enum_values == owner.enum_values, (spec.name, name)
            assert derived.string_pattern == owner.string_pattern, (spec.name, name)
            assert derived.object_model == owner.object_model, (spec.name, name)
            assert derived.list_item_model == owner.list_item_model, (spec.name, name)
            assert derived.wire_obligation == owner.wire_obligation, (spec.name, name)
            if spec.name == "shoot_projectile":
                assert derived.compiled_fields == owner.compiled_fields
                assert derived.provenance_via_lowerer is False
            else:
                assert derived.compiled_fields == ()
                assert derived.provenance_via_lowerer is True


def test_lowerer_graph_matches_semantics_and_declares_every_output_key() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
        compiled_fields_for_authored_path,
        compiled_fields_for_function_identity,
        validate_lowerer_output,
    )
    from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call

    for spec in ENGINE_FUNCTION_CONTRACTS:
        authored = {param.name: deepcopy(param.example_value) for param in spec.params}
        actual = _lower_typed_engine_call(spec.name, authored)
        actual_targets = tuple(target for target, _ in actual if target != spec.name)
        declared_targets = tuple(lowerer.target_function for lowerer in spec.lowerers)
        assert actual_targets == declared_targets, spec.name
        for target, params in actual:
            if target == spec.name:
                continue
            assert validate_lowerer_output(spec.name, target, params) == (), spec.name
        for lowerer in spec.lowerers:
            if any(binding.source_path == "$function" for binding in lowerer.bindings):
                assert compiled_fields_for_function_identity(spec.name), spec.name
            for binding in lowerer.bindings:
                if binding.source_path == "$function":
                    continue
                assert compiled_fields_for_authored_path(spec.name, binding.source_path), (
                    spec.name,
                    binding.source_path,
                )


def test_every_declared_family_branch_stays_inside_lowerer_output_grammar() -> None:
    """Exercise finite family branches, not one happy-path example per function.

    Enum families come directly from the canonical provider contract.  Magic keeps
    an open exact-family string for visual/form identity, so its prompt card's finite
    pipe tokens are the branch witnesses and one arbitrary value covers the default.
    """

    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
        validate_lowerer_output,
    )
    from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call

    for spec in ENGINE_FUNCTION_CONTRACTS:
        if not spec.lowerers:
            continue
        authored = {param.name: deepcopy(param.example_value) for param in spec.params}
        family = next((param for param in spec.params if param.name == "family"), None)
        branch_values: tuple[str, ...] = ()
        if family is not None and family.enum_values:
            branch_values = tuple(family.enum_values)
        elif family is not None:
            prompt_tokens = tuple(
                token.strip()
                for token in family.prompt_description.split("|")
                if token.strip().replace("_", "").isalnum()
                and " " not in token.strip()
            )
            branch_values = tuple(dict.fromkeys((*prompt_tokens, "custom_exact_family")))
        else:
            branch_values = ("",)

        assert branch_values, spec.name
        for branch in branch_values:
            params = deepcopy(authored)
            if family is not None:
                params["family"] = branch
            actual = _lower_typed_engine_call(spec.name, params)
            assert tuple(target for target, _ in actual if target != spec.name) == tuple(
                lowerer.target_function for lowerer in spec.lowerers
            ), (spec.name, branch)
            for target, lowered in actual:
                if target != spec.name:
                    assert validate_lowerer_output(spec.name, target, lowered) == (), (
                        spec.name,
                        branch,
                        lowered,
                    )


def test_lowerer_source_must_be_root_when_target_is_root() -> None:
    target = _fn(name="executor", root_executor=True)
    source = _fn(
        name="typed_source",
        params=(_param(compiled_fields=(), provenance_via_lowerer=True),),
        lowerers=(
            EngineLowererContract(
                target_function="executor",
                bindings=(LoweredParamBinding("damage", ("damage",)),),
            ),
        ),
    )
    errors = validate_engine_function_contracts((source, target))
    assert any("source must be root_executor" in error for error in errors)


def test_lowerer_target_must_be_terminal_until_normalization_supports_chains() -> None:
    terminal = _fn(name="terminal", root_executor=True)
    middle = _fn(
        name="middle",
        root_executor=True,
        params=(_param(compiled_fields=(), provenance_via_lowerer=True),),
        lowerers=(
            EngineLowererContract(
                target_function="terminal",
                bindings=(LoweredParamBinding("damage", ("damage",)),),
            ),
        ),
    )
    source = _fn(
        name="source",
        root_executor=True,
        params=(_param(compiled_fields=(), provenance_via_lowerer=True),),
        lowerers=(
            EngineLowererContract(
                target_function="middle",
                bindings=(LoweredParamBinding("damage", ("damage",)),),
            ),
        ),
    )

    errors = validate_engine_function_contracts((source, middle, terminal))
    assert any(
        "lowerer target 'middle' must be terminal" in error
        and "chained lowerers are unsupported" in error
        for error in errors
    )


def test_lowerer_unknown_target_and_output_fail_closed() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        validate_lowerer_output,
    )

    missing = _fn(
        name="typed_source",
        root_executor=True,
        params=(_param(compiled_fields=(), provenance_via_lowerer=True),),
        lowerers=(
            EngineLowererContract(
                target_function="missing_executor",
                bindings=(LoweredParamBinding("damage", ("damage",)),),
            ),
        ),
    )
    assert any("not in registry" in error for error in validate_engine_function_contracts((missing,)))
    errors = validate_lowerer_output(
        "deploy_sentry",
        "shoot_projectile",
        {"runtimeFamily": "sentry", "inventedAlias": 1},
    )
    assert errors and "inventedAlias" in errors[0]


def test_deploy_sentry_normalization_has_no_alias_shadow_and_preserves_root_params() -> None:
    from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace

    authored_params = {
        "placement": "grounded",
        "attackIntervalTicks": 30,
        "targetRangeTiles": 20,
        "helperLifetimeTicks": 600,
        "shotCount": 2,
        "speed": 8,
        "spreadRadians": 0.2,
        "pierce": 1,
        "secondaryDamageMultiplier": 0.5,
        "useTimeTicks": 20,
        "useAnimationTicks": 20,
    }
    data = {"runtimePlan": {"engineCalls": [{"callId": "sentry", "fn": "deploy_sentry", "params": authored_params}]}}
    normalize_runtime_plan_inplace(data)
    call = data["runtimePlan"]["engineCalls"][0]
    params = call["params"]
    assert call["fn"] == "shoot_projectile"
    assert call["_authoredFn"] == "deploy_sentry"
    assert call["_authoredParams"] == authored_params
    for stale_alias in ("placement", "attackIntervalTicks", "targetRangeTiles", "helperLifetimeTicks"):
        assert stale_alias not in params
    assert params["sentryPlacement"] == "grounded"
    assert params["sentryAttackIntervalTicks"] == 30
    assert params["sentryTargetRangeTiles"] == 20
    assert params["sentryLifetimeTicks"] == 600
    assert params["secondaryDamageMultiplier"] == 0.5
    assert params["useTimeTicks"] == 20
    assert params["useAnimationTicks"] == 20

    first = deepcopy(data)
    normalize_runtime_plan_inplace(data)
    assert data == first


def test_legacy_lowered_sentry_aliases_resolve_from_typed_graph_only() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        compiled_fields_for_lowered_compatibility_path,
    )

    legacy_target_params = {
        "runtimeFamily": "sentry",
        "placement": "grounded",
        "sentryPlacement": "grounded",
        "attackIntervalTicks": 45,
        "sentryAttackIntervalTicks": 45,
        "targetRangeTiles": 30,
        "sentryTargetRangeTiles": 30,
        "rangeTiles": 30,
        "helperLifetimeTicks": 3600,
        "sentryLifetimeTicks": 3600,
        "lifetimeTicks": 3600,
    }
    assert compiled_fields_for_lowered_compatibility_path(
        "shoot_projectile", "placement", legacy_target_params
    ) == {"sentryPlacement"}
    assert compiled_fields_for_lowered_compatibility_path(
        "shoot_projectile", "attackIntervalTicks", legacy_target_params
    ) == {"sentryAttackIntervalTicks"}
    assert compiled_fields_for_lowered_compatibility_path(
        "shoot_projectile", "targetRangeTiles", legacy_target_params
    ) == {"range", "rangeTiles", "sentryTargetRangeTiles"}
    assert compiled_fields_for_lowered_compatibility_path(
        "shoot_projectile", "helperLifetimeTicks", legacy_target_params
    ) == {"lifetime", "lifetimeTicks", "sentryLifetimeTicks"}
    # A target-owned public field must never be re-attributed through an incoming
    # lowerer alias.
    assert not compiled_fields_for_lowered_compatibility_path(
        "shoot_projectile", "rangeTiles", legacy_target_params
    )


def test_provenance_uses_original_authored_call_not_generated_lowerer_params() -> None:
    from infini_local.core.runtime_authoring.reports import runtime_plan_provenance_report

    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {
                    "callId": "ranged",
                    "fn": "fire_ranged_weapon",
                    "params": {
                        "family": "bow",
                        "ammoFor": "arrow",
                        "movement": "straight",
                        "speed": 10,
                        "rangeTiles": 40,
                        "lifetimeTicks": 120,
                        "shotCount": 1,
                        "spreadRadians": 0,
                        "pierce": 1,
                    },
                }
            ]
        },
    }
    report = runtime_plan_provenance_report(data)
    rows = report["authoredParameters"]
    assert {row["fn"] for row in rows} == {"fire_ranged_weapon"}
    assert {row["param"] for row in rows} == {
        "family", "ammoFor", "movement", "speed", "rangeTiles",
        "lifetimeTicks", "shotCount", "spreadRadians", "pierce",
    }
    assert not {"runtimeFamily", "delivery", "weaponFamily", "projectileFamily"}.intersection(
        row["param"] for row in rows
    )
    assert report["fieldSources"]["runtimeFamily"] == "fire_ranged_weapon"
    assert report["fieldSources"]["delivery"] == "fire_ranged_weapon"


def test_normalizer_rejects_semantics_output_outside_typed_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    import infini_local.core.runtime_authoring.normalize as normalize_mod

    original = normalize_mod._lower_typed_engine_call

    def broken(fn: str, params: dict[str, Any]):
        rows = original(fn, params)
        if fn == "fire_ranged_weapon":
            rows[0][1]["inventedAlias"] = 1
        return rows

    monkeypatch.setattr(normalize_mod, "_lower_typed_engine_call", broken)
    data = {
        "runtimePlan": {
            "engineCalls": [{
                "fn": "fire_ranged_weapon",
                "params": {"family": "bow", "shotCount": 1, "spreadRadians": 0},
            }]
        }
    }
    normalize_mod.normalize_runtime_plan_inplace(data)
    norm = data["runtimePlan"]["_normalization"]
    assert data["runtimePlan"]["engineCalls"] == []
    assert norm["rejectedEngineCalls"][0]["reason"] == "typed_lowerer_output_contract"


def test_compiled_provenance_map_is_derived_and_complete_for_public_final_wire_params() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
        compiled_field_source_map,
        compiled_fields_for_authored_path,
    )

    source_map = compiled_field_source_map()
    for spec in ENGINE_FUNCTION_CONTRACTS:
        for param in spec.params:
            if param.wire_obligation is not WireObligation.FINAL_WIRE:
                continue
            if param.nested_wire_paths:
                paths = tuple(f"{param.name}.{nested.path}" for nested in param.nested_wire_paths)
            else:
                paths = (param.name,)
            for path in paths:
                assert compiled_fields_for_authored_path(spec.name, path), (spec.name, path)
        for field, sources in source_map.get(spec.name, {}).items():
            assert field and sources


def test_contract_surface_contains_only_derived_public_and_lowerer_sections() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        engine_function_contract_surface,
    )

    surface = engine_function_contract_surface()
    assert surface
    for row in surface.values():
        assert set(row) == {
            "rootExecutor", "requiresRootExecutor", "paramOrder", "params",
            "repairGroups", "normalizedOnlyParams", "lowerers",
        }
        assert "allowedResultKinds" not in row
        assert "compiledSourceOverrides" not in row


def test_provider_shape_and_nested_path_invariants_are_local() -> None:
    class ObjectBoundary:
        pass

    nested = NestedWirePathContract("durationTicks", ("generatedBuff.durationTicks",))
    valid = _fn(
        params=(
            _param(
                value_kind=ParamValueKind.OBJECT,
                example_value=(),
                compiled_fields=(),
                provenance_via_lowerer=True,
                object_model=ObjectBoundary,
                nested_wire_paths=(nested,),
            ),
        )
    )
    assert validate_engine_function_contracts((valid,)) == ()

    invalid = (
        _fn(name="enum_without_values", params=(_param(value_kind=ParamValueKind.ENUM),)),
        _fn(name="object_without_model", params=(_param(value_kind=ParamValueKind.OBJECT),)),
        _fn(name="mutable_example", params=(_param(example_value={"x": 1}),)),
        _fn(name="scalar_nested", params=(_param(nested_wire_paths=(nested,)),)),
    )
    joined = "\n".join(validate_engine_function_contracts(invalid))
    for marker in ("enum_values", "object_model", "mutable_example", "nested_wire_paths"):
        assert marker in joined


def test_registry_validation_rejects_core_invariant_mutations() -> None:
    group = RepairGroupContract(("damage",), "runtime_secondary_policy")
    invalid_sets = (
        (_fn(name="dup"), _fn(name="dup")),
        (_fn(name=""),),
        (_fn(meaning=""),),
        (_fn(params=(_param(name="damage"), _param(name="damage"))),),
        (_fn(repair_groups=(RepairGroupContract(("missing",), "owner"),)),),
        (_fn(repair_groups=(RepairGroupContract(("damage",), ""),)),),
        (_fn(root_executor=True, requires_root_executor=True),),
        (_fn(params=(_param(compiled_fields=()),)),),
        (_fn(params=(_param(wire_obligation=WireObligation.NON_WIRE),)),),
    )
    for specs in invalid_sets:
        assert validate_engine_function_contracts(specs), specs
    assert validate_engine_function_contracts((_fn(repair_groups=(group,)),)) == ()


def test_contract_dataclasses_are_frozen_and_tuple_owned() -> None:
    param = _param()
    group = RepairGroupContract(("damage",), "owner")
    lowerer = EngineLowererContract("target", (LoweredParamBinding("damage", ("damage",)),))
    fn = _fn(repair_groups=(group,), lowerers=(lowerer,))
    for obj in (param, group, lowerer, fn):
        assert is_dataclass(obj)
        for field_name in getattr(type(obj), "__dataclass_fields__", {}):
            assert not isinstance(getattr(obj, field_name), dict)
    with pytest.raises(FrozenInstanceError):
        param.name = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        fn.root_executor = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("rendererKind", "hallucinatedRenderer"),
        ("channel", "hallucinatedChannel"),
        ("particleSystemId", "pl:not-real"),
    ),
)
def test_visual_effect_cue_closed_vocabularies_fail_at_provider_boundary(field: str, invalid: str) -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import validate_engine_call_params

    valid, errors = validate_engine_call_params(
        "visual_effect_cue",
        {
            "event": "travel",
            "rendererKind": "projectileAfterimage",
            "channel": "motionTrail",
            "particleSystemId": "pl:glow",
        },
    )
    assert errors == [] and valid is not None
    rejected, errors = validate_engine_call_params("visual_effect_cue", {field: invalid})
    assert rejected is None and any(field in error for error in errors)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("rendererKind", "hallucinatedRenderer"),
        ("channel", "hallucinatedChannel"),
        ("lane", "hallucinatedLane"),
        ("textureRole", "hallucinatedRole"),
        ("particleRole", "hallucinatedRole"),
        ("emissionMode", "hallucinatedEmission"),
        ("particleSystemId", "pl:not-real"),
        ("importance", "hallucinatedImportance"),
    ),
)
def test_visual_effect_cue_invalid_token_stays_inert_when_provider_is_bypassed(field: str, invalid: str) -> None:
    from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch

    data = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [{
                "callId": "bad_cue",
                "fn": "visual_effect_cue",
                "params": {
                    "event": "hit",
                    "rendererKind": "impactRing",
                    "channel": "impactShape",
                    "duration": 12,
                    field: invalid,
                },
            }],
        },
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert "vfxCues" not in patch and "vfxCueCount" not in patch


def test_types_module_owns_metadata_validation_not_runtime_execution() -> None:
    import inspect
    import infini_local.core.runtime_authoring.function_contract_types as mod

    source = inspect.getsource(mod).casefold()
    for forbidden in ("def compile", "def project_final", "route_by_name", "trigger_action"):
        assert forbidden not in source
