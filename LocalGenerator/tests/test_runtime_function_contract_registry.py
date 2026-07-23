"""Immutable Author engine-function registry and its projected boundaries."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

import pytest

from infini_local.core.runtime_authoring.function_contract_types import (
    CompiledFieldSourceOverride,
    EngineFunctionContract,
    EngineParamContract,
    NestedWirePathContract,
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


def _group(
    members: tuple[str, ...] = ("damage",),
    *,
    policy_owner: str = "runtime_secondary_policy",
) -> RepairGroupContract:
    return RepairGroupContract(members=members, policy_owner=policy_owner)


def _fn(
    name: str = "set_item_stats",
    *,
    meaning: str = "Base item stats.",
    params: tuple[EngineParamContract, ...] | None = None,
    root_executor: bool = False,
    requires_root_executor: bool = False,
    allowed_result_kinds: tuple[str, ...] = ("weapon",),
    repair_groups: tuple[RepairGroupContract, ...] = (),
    compiled_source_overrides: tuple[CompiledFieldSourceOverride, ...] = (),
    lowered_function_names: tuple[str, ...] = (),
) -> EngineFunctionContract:
    if params is None:
        params = (_param(),)
    return EngineFunctionContract(
        name=name,
        meaning=meaning,
        params=params,
        root_executor=root_executor,
        requires_root_executor=requires_root_executor,
        allowed_result_kinds=allowed_result_kinds,
        repair_groups=repair_groups,
        compiled_source_overrides=compiled_source_overrides,
        lowered_function_names=lowered_function_names,
    )


def test_wire_obligation_values_are_exact_string_tokens() -> None:
    assert WireObligation.FINAL_WIRE.value == "final_wire"
    assert WireObligation.DEFERRED_VFX.value == "deferred_vfx"
    assert WireObligation.CONTROL_DERIVED.value == "control_derived"
    assert WireObligation.NON_WIRE.value == "non_wire"
    assert {m.value for m in WireObligation} == {
        "final_wire",
        "deferred_vfx",
        "control_derived",
        "non_wire",
    }


def test_provenance_requirement_is_projected_from_canonical_param_contracts() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACT_BY_NAME,
        engine_param_wire_obligation,
    )
    from infini_local.core.runtime_contracts import authored_param_requires_final_wire_provenance

    assert engine_param_wire_obligation("set_item_stats", "damage") is WireObligation.FINAL_WIRE
    assert engine_param_wire_obligation("emit_light", "durationTicks") is WireObligation.CONTROL_DERIVED
    assert engine_param_wire_obligation("apply_player_effect_on_use", "note") is WireObligation.NON_WIRE
    assert engine_param_wire_obligation("visual_effect_cue", "duration") is WireObligation.DEFERRED_VFX
    assert authored_param_requires_final_wire_provenance("set_item_stats", "damage") is True
    assert authored_param_requires_final_wire_provenance("emit_light", "durationTicks") is False
    assert authored_param_requires_final_wire_provenance("apply_player_effect_on_use", "note") is False
    assert authored_param_requires_final_wire_provenance("visual_effect_cue", "duration") is False
    assert authored_param_requires_final_wire_provenance("future_unknown_fn", "futureParam") is True
    alt_mode = next(
        param
        for param in ENGINE_FUNCTION_CONTRACT_BY_NAME["set_alt_use_mode"].params
        if param.name == "mode"
    )
    assert alt_mode.enum_values == ("mobility", "generated_buff", "light")


def test_armor_set_bonus_prompt_card_matches_typed_boundary_keys() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import engine_function_catalog

    description = engine_function_catalog()["armor_effect"]["params"]["setBonus"]
    for key in (
        "text", "genericDamage", "meleeDamage", "rangedDamage", "magicDamage",
        "summonDamage", "genericCrit", "movementSpeed", "lifeRegen", "manaRegen",
        "minionSlots", "sentrySlots", "manaCostReduction", "ammoSaveChance", "aggro",
        "endurance", "armorPenetration",
    ):
        assert key in description
    tokens = {token.strip() for token in description.split(":", 1)[-1].split(",")}
    for stale_key in ("classDmg", "crit", "move", "regen", "minions"):
        assert stale_key not in tokens


def test_param_value_kinds_are_closed_provider_tokens() -> None:
    assert {member.value for member in ParamValueKind} == {
        "boolean", "integer", "number", "string", "enum", "object", "list",
    }


def test_provider_shape_invariants_reject_side_table_drift() -> None:
    class ObjectBoundary:
        pass

    valid = (
        _fn(
            params=(
                _param(
                    name="movement",
                    value_kind=ParamValueKind.ENUM,
                    example_value="straight",
                    enum_values=("straight", "gravity_arc"),
                ),
                _param(
                    name="damageClass",
                    value_kind=ParamValueKind.STRING,
                    example_value="mod:class",
                    string_pattern=r"^[A-Za-z0-9_.:-]+$",
                    compiled_fields=("damageClass",),
                ),
                _param(
                    name="stats",
                    value_kind=ParamValueKind.OBJECT,
                    example_value=(),
                    object_model=ObjectBoundary,
                    compiled_fields=(),
                    provenance_via_lowerer=True,
                ),
                _param(
                    name="buffs",
                    value_kind=ParamValueKind.LIST,
                    example_value=(),
                    list_item_model=ObjectBoundary,
                    compiled_fields=(),
                    provenance_via_lowerer=True,
                ),
            ),
        ),
    )
    assert validate_engine_function_contracts(valid) == ()

    bad = (
        _fn(name="unknown_kind", params=(_param(value_kind="mystery"),)),
        _fn(name="enum_without_values", params=(_param(value_kind=ParamValueKind.ENUM),)),
        _fn(
            name="scalar_with_enum_values",
            params=(_param(value_kind=ParamValueKind.STRING, enum_values=("x",)),),
        ),
        _fn(name="object_without_model", params=(_param(value_kind=ParamValueKind.OBJECT),)),
        _fn(name="list_without_model", params=(_param(value_kind=ParamValueKind.LIST),)),
        _fn(
            name="number_with_pattern",
            params=(_param(value_kind=ParamValueKind.NUMBER, string_pattern="x"),),
        ),
        _fn(name="mutable_example", params=(_param(example_value={"x": 1}),)),
    )
    joined = "\n".join(validate_engine_function_contracts(bad))
    for marker in (
        "mystery", "enum_values", "object_model", "list_item_model",
        "string_pattern", "mutable_example",
    ):
        assert marker in joined


def test_nested_wire_paths_are_immutable_and_object_scoped() -> None:
    class ObjectBoundary:
        pass

    nested = NestedWirePathContract(
        path="durationTicks",
        compiled_fields=("generatedBuff.durationTicks",),
    )
    valid = (
        _fn(params=(
            _param(
                value_kind=ParamValueKind.OBJECT,
                example_value=(),
                compiled_fields=(),
                provenance_via_lowerer=True,
                object_model=ObjectBoundary,
                nested_wire_paths=(nested,),
            ),
        )),
    )
    assert validate_engine_function_contracts(valid) == ()
    invalid = (
        _fn(name="scalar_nested", params=(_param(nested_wire_paths=(nested,)),)),
        _fn(name="bad_nested_path", params=(
            _param(
                value_kind=ParamValueKind.OBJECT,
                example_value=(),
                compiled_fields=(),
                provenance_via_lowerer=True,
                object_model=ObjectBoundary,
                nested_wire_paths=(NestedWirePathContract(path="bad path", compiled_fields=("x",)),),
            ),
        )),
    )
    joined = "\n".join(validate_engine_function_contracts(invalid))
    assert "nested_wire_paths require object/list" in joined
    assert "invalid nested wire path" in joined


def test_compiler_source_overrides_are_explicit_and_unique() -> None:
    override = CompiledFieldSourceOverride(
        compiled_field="useStyleCode",
        source_paths=("useStyleCode",),
    )
    assert validate_engine_function_contracts(
        (_fn(compiled_source_overrides=(override,)),)
    ) == ()
    invalid = _fn(
        name="bad_overrides",
        compiled_source_overrides=(
            override,
            override,
            CompiledFieldSourceOverride(
                compiled_field="",
                source_paths=("bad path",),
            ),
        ),
    )
    joined = "\n".join(validate_engine_function_contracts((invalid,)))
    assert "duplicate compiled source override" in joined
    assert "blank field" in joined
    assert "invalid compiler source path" in joined


def test_nested_parameter_boundaries_have_one_leaf_owner() -> None:
    import inspect

    from infini_local.core.runtime_authoring import engine_call_contracts as generated_models
    from infini_local.core.runtime_authoring import engine_param_boundaries as boundaries

    for name in (
        "StrictEngineParamModel",
        "BuffParamBoundary",
        "GeneratedBuffParamBoundary",
        "EquipmentStatsParamBoundary",
        "ArmorSetBonusParamBoundary",
    ):
        assert getattr(generated_models, name) is getattr(boundaries, name)
    generated_source = inspect.getsource(generated_models)
    assert "class BuffParamBoundary" not in generated_source
    assert "class EquipmentStatsParamBoundary" not in generated_source


def test_hidden_shared_params_require_one_explicit_prompt_group() -> None:
    valid = (
        _fn(params=(_param(function_card_visible=False, prompt_group="root_executor"),)),
        _fn(name="visible_group_member", params=(_param(prompt_group="root_executor"),)),
    )
    assert validate_engine_function_contracts(valid) == ()
    invalid = (
        _fn(name="hidden_without_group", params=(_param(function_card_visible=False),)),
    )
    joined = "\n".join(validate_engine_function_contracts(invalid))
    assert "hidden params require prompt_group" in joined


def test_current_engine_function_surface_matches_frozen_baseline() -> None:
    import json
    from collections.abc import Mapping
    from pathlib import Path

    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ACCEPTED_PARAM_EXTRAS_BY_FUNCTION,
        ENGINE_FUNCTION_CATALOG,
        REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION,
        accepted_engine_param_names,
        engine_function_contract_surface,
    )

    def clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): clean(child) for key, child in sorted(value.items())}
        if isinstance(value, (list, tuple, frozenset, set)):
            return [
                clean(child)
                for child in sorted(
                    value,
                    key=lambda item: json.dumps(clean(item), sort_keys=True),
                )
            ]
        return value

    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "engine_function_contract_surface_v1.json"
    )
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    actual = {
        "schema": "infini.engine-function-surface-baseline.v1",
        "catalog": clean(ENGINE_FUNCTION_CATALOG),
        "acceptedParams": {
            fn: sorted(accepted_engine_param_names(fn))
            for fn in sorted(ENGINE_FUNCTION_CATALOG)
        },
        "acceptedExtras": clean(ACCEPTED_PARAM_EXTRAS_BY_FUNCTION),
        "repairGroups": clean(REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION),
        "typedContracts": engine_function_contract_surface(),
        "providerSchemas": {
            fn: engine_params_model(fn).model_json_schema()
            for fn in sorted(ENGINE_FUNCTION_CATALOG)
        },
    }
    assert actual == expected


def test_provider_enum_order_is_deterministic_across_shared_literal_sets() -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model

    shoot = engine_params_model("shoot_projectile").model_json_schema()
    sentry = engine_params_model("deploy_sentry").model_json_schema()
    for schema in (shoot, sentry):
        movement = next(
            branch["enum"]
            for branch in schema["properties"]["movement"]["anyOf"]
            if "enum" in branch
        )
        assert movement == sorted(movement)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("rendererKind", "hallucinatedRenderer"),
        ("channel", "hallucinatedChannel"),
        ("particleSystemId", "pl:not-real"),
    ),
)
def test_visual_effect_cue_closed_vocabularies_fail_at_provider_boundary(
    field: str,
    invalid: str,
) -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import (
        validate_engine_call_params,
    )

    valid, valid_errors = validate_engine_call_params(
        "visual_effect_cue",
        {
            "event": "travel",
            "rendererKind": "projectileAfterimage",
            "channel": "motionTrail",
            "particleSystemId": "pl:glow",
        },
    )
    assert valid_errors == []
    assert valid is not None

    rejected, errors = validate_engine_call_params(
        "visual_effect_cue",
        {field: invalid},
    )
    assert rejected is None
    assert errors and any(field in error for error in errors)


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
def test_visual_effect_cue_invalid_finite_token_stays_inert_when_provider_is_bypassed(
    field: str,
    invalid: str,
) -> None:
    from infini_local.core.runtime_authoring.compiler import (
        compile_runtime_plan_to_genome_patch,
    )

    data = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "callId": "bad_cue",
                    "fn": "visual_effect_cue",
                    "params": {
                        "event": "hit",
                        "rendererKind": "impactRing",
                        "channel": "impactShape",
                        "duration": 12,
                        field: invalid,
                    },
                }
            ],
        },
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert "vfxCues" not in patch
    assert "vfxCueCount" not in patch


def test_lowerer_impact_metadata_is_typed_and_fail_closed() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        engine_function_impact_names,
    )

    assert engine_function_impact_names("fire_ranged_weapon") == frozenset(
        {"fire_ranged_weapon", "shoot_projectile"}
    )
    assert engine_function_impact_names("shoot_projectile") == frozenset(
        {"shoot_projectile"}
    )
    assert engine_function_impact_names("not_a_function") == frozenset()

    missing_target = _fn(
        name="typed_lowerer",
        lowered_function_names=("missing_executor",),
    )
    errors = validate_engine_function_contracts((missing_target,))
    assert any("not in registry" in error for error in errors)


def test_typed_lowerer_metadata_matches_production_semantic_lowerer() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACTS,
    )
    from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call

    representative_params = {
        "perform_melee_attack": {"family": "broadsword"},
        "fire_ranged_weapon": {"family": "bow"},
        "cast_magic_weapon": {"family": "staff"},
        "deploy_sentry": {"placement": "grounded"},
        "spawn_temporary_helper_projectile": {"family": "drone"},
    }
    for contract in ENGINE_FUNCTION_CONTRACTS:
        actual_targets = tuple(
            target
            for target, _params in _lower_typed_engine_call(
                contract.name,
                representative_params.get(contract.name, {}),
            )
            if target != contract.name
        )
        assert actual_targets == contract.lowered_function_names, contract.name


@pytest.mark.parametrize(
    ("fn", "field", "invalid"),
    (
        ("shoot_projectile", "effect", "made_up_effect"),
        ("deploy_sentry", "onHit", "split"),
        ("set_item_stats", "armorSlot", "hat"),
    ),
)
def test_executor_closed_vocabularies_reject_non_executable_values(
    fn: str,
    field: str,
    invalid: str,
) -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import (
        validate_engine_call_params,
    )

    parsed, errors = validate_engine_call_params(fn, {field: invalid})
    assert parsed is None
    assert errors and any(field in error for error in errors)

    if fn == "deploy_sentry":
        parsed, errors = validate_engine_call_params(fn, {field: "slow"})
        assert errors == []
        assert parsed == {"onHit": "slow"}


def test_compiled_field_provenance_matches_pre_migration_baseline() -> None:
    import json
    from pathlib import Path

    from infini_local.core.runtime_authoring.function_contract_registry import (
        compiled_field_source_map,
    )

    expected = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "compiled_field_source_map_v1.json"
        ).read_text(encoding="utf-8")
    )["functions"]
    actual = json.loads(json.dumps(compiled_field_source_map()))
    assert actual == expected


def test_contract_dataclasses_are_frozen_and_reject_mutation() -> None:
    param = _param()
    group = _group()
    fn = _fn(repair_groups=(group,))
    assert is_dataclass(param) and is_dataclass(group) and is_dataclass(fn)
    with pytest.raises(FrozenInstanceError):
        param.name = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        group.policy_owner = "x"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        fn.root_executor = True  # type: ignore[misc]


def test_nested_collections_are_tuples_not_mutable_dicts() -> None:
    param = _param(compiled_fields=("a", "b"))
    group = _group(members=("damage", "knockback"))
    fn = _fn(
        params=(param, _param(name="knockback", compiled_fields=("knockback",))),
        allowed_result_kinds=("weapon", "tool"),
        repair_groups=(group,),
    )
    assert isinstance(param.compiled_fields, tuple)
    assert isinstance(group.members, tuple)
    assert isinstance(fn.params, tuple)
    assert isinstance(fn.allowed_result_kinds, tuple)
    assert isinstance(fn.repair_groups, tuple)
    assert not isinstance(fn.params, list)
    # No mutable dict storage on the contract surface (slots-safe field walk).
    for obj in (param, group, fn):
        for field_name in getattr(type(obj), "__dataclass_fields__", {}):
            value = getattr(obj, field_name)
            assert not isinstance(value, dict), f"mutable dict on {type(obj).__name__}.{field_name}"


def test_new_nonblank_policy_owner_requires_no_central_allowlist() -> None:
    spec = _fn(
        repair_groups=(
            _group(
                members=("damage",),
                policy_owner="runtime_authoring.specialized_new_policy",
            ),
        ),
    )
    assert validate_engine_function_contracts((spec,)) == ()


def test_valid_minimal_registry_has_no_errors() -> None:
    specs = (
        _fn(
            params=(
                _param(name="damage"),
                _param(
                    name="debugTrace",
                    prompt_description="QA-only marker.",
                    value_kind=ParamValueKind.BOOLEAN,
                    example_value=False,
                    compiled_fields=(),
                    wire_obligation=WireObligation.NON_WIRE,
                ),
            ),
            repair_groups=(_group(members=("damage",), policy_owner="runtime_secondary_policy"),),
        ),
        _fn(
            name="shoot_projectile",
            meaning="Root combat executor.",
            params=(
                _param(name="runtimeFamily", compiled_fields=("runtimeFamily",)),
                _param(
                    name="shotCount",
                    prompt_description="Projectiles per use.",
                    compiled_fields=("shotCount",),
                ),
            ),
            root_executor=True,
            allowed_result_kinds=("weapon", "consumable_weapon"),
        ),
        _fn(
            name="spawn_contact_particles",
            meaning="Impact particles requiring a root executor.",
            params=(_param(name="material", compiled_fields=("material",)),),
            requires_root_executor=True,
            allowed_result_kinds=("weapon",),
        ),
    )
    errors = validate_engine_function_contracts(specs)
    assert errors == ()


def test_validate_returns_deterministic_tuple() -> None:
    bad = (
        _fn(name="dup"),
        _fn(name="dup"),
    )
    first = validate_engine_function_contracts(bad)
    second = validate_engine_function_contracts(bad)
    assert isinstance(first, tuple)
    assert first == second
    assert first  # non-empty
    assert all(isinstance(e, str) and e.strip() for e in first)


def test_reject_duplicate_function_names() -> None:
    errors = validate_engine_function_contracts((_fn(name="same"), _fn(name="same")))
    assert any("duplicate" in e.lower() and "same" in e for e in errors)


def test_reject_duplicate_param_names_within_function() -> None:
    errors = validate_engine_function_contracts(
        (
            _fn(
                params=(
                    _param(name="damage"),
                    _param(name="damage", compiled_fields=("damage",)),
                ),
            ),
        )
    )
    assert any("duplicate" in e.lower() and "damage" in e for e in errors)


def test_reject_blank_function_name_and_meaning() -> None:
    errors = validate_engine_function_contracts(
        (
            _fn(name="  ", meaning="ok"),
            _fn(name="ok_fn", meaning=""),
            _fn(name="ok_fn2", meaning="   "),
        )
    )
    joined = "\n".join(errors)
    assert "blank" in joined.lower() or "empty" in joined.lower()
    assert any("name" in e.lower() for e in errors)
    assert any("meaning" in e.lower() for e in errors)


def test_reject_blank_param_name_and_prompt_description() -> None:
    errors = validate_engine_function_contracts(
        (
            _fn(params=(_param(name="", prompt_description="desc"),)),
            _fn(name="other", params=(_param(name="x", prompt_description="  "),)),
        )
    )
    joined = "\n".join(errors).lower()
    assert "blank" in joined or "empty" in joined
    assert "prompt" in joined or "description" in joined


def test_reject_repair_member_not_in_params() -> None:
    errors = validate_engine_function_contracts(
        (
            _fn(
                params=(_param(name="damage"),),
                repair_groups=(_group(members=("damage", "missingLeaf")),),
            ),
        )
    )
    assert any("missingLeaf" in e and ("repair" in e.lower() or "member" in e.lower()) for e in errors)


def test_reject_blank_but_not_new_policy_owner() -> None:
    blank = validate_engine_function_contracts(
        (
            _fn(
                params=(_param(name="damage"),),
                repair_groups=(_group(members=("damage",), policy_owner="  "),),
            ),
        )
    )
    new_owner = validate_engine_function_contracts(
        (
            _fn(
                params=(_param(name="damage"),),
                repair_groups=(_group(members=("damage",), policy_owner="not_a_real_policy"),),
            ),
        )
    )
    assert any("policy" in e.lower() for e in blank)
    assert new_owner == ()


def test_reject_final_wire_and_control_derived_without_compiled_fields() -> None:
    final_errors = validate_engine_function_contracts(
        (
            _fn(
                params=(
                    _param(
                        name="damage",
                        compiled_fields=(),
                        wire_obligation=WireObligation.FINAL_WIRE,
                    ),
                ),
            ),
        )
    )
    control_errors = validate_engine_function_contracts(
        (
            _fn(
                params=(
                    _param(
                        name="controlFlag",
                        compiled_fields=(),
                        wire_obligation=WireObligation.CONTROL_DERIVED,
                    ),
                ),
            ),
        )
    )
    assert any("compiled_fields" in e.lower() or "compiled field" in e.lower() for e in final_errors)
    assert any("final_wire" in e.lower() or "damage" in e for e in final_errors)
    assert any("compiled_fields" in e.lower() or "compiled field" in e.lower() for e in control_errors)
    assert any("control_derived" in e.lower() or "controlFlag" in e for e in control_errors)

    lowered_alias = validate_engine_function_contracts(
        (
            _fn(
                name="lowered_alias",
                params=(
                    _param(
                        name="speed",
                        compiled_fields=(),
                        wire_obligation=WireObligation.FINAL_WIRE,
                        provenance_via_lowerer=True,
                    ),
                ),
            ),
        )
    )
    assert lowered_alias == ()


def test_reject_non_wire_param_with_compiled_fields() -> None:
    errors = validate_engine_function_contracts(
        (
            _fn(
                params=(
                    _param(
                        name="debugOnly",
                        prompt_description="Must not wire.",
                        compiled_fields=("debugOnly",),
                        wire_obligation=WireObligation.NON_WIRE,
                    ),
                ),
            ),
        )
    )
    assert any("non_wire" in e.lower() for e in errors)
    assert any("compiled" in e.lower() for e in errors)

    lowerer_errors = validate_engine_function_contracts(
        (
            _fn(
                name="bad_non_wire_lowerer",
                params=(
                    _param(
                        name="debugOnly",
                        compiled_fields=(),
                        wire_obligation=WireObligation.NON_WIRE,
                        provenance_via_lowerer=True,
                    ),
                ),
            ),
        )
    )
    assert any("non_wire" in e.lower() and "lower" in e.lower() for e in lowerer_errors)


def test_reject_root_executor_and_requires_root_executor_simultaneously() -> None:
    errors = validate_engine_function_contracts(
        (
            _fn(
                name="bad_root",
                root_executor=True,
                requires_root_executor=True,
            ),
        )
    )
    assert any(
        "root_executor" in e.lower() and "requires_root_executor" in e.lower()
        for e in errors
    )


def test_deferred_vfx_may_have_compiled_fields_or_empty() -> None:
    """deferred_vfx is not final wire; empty or non-empty compiled_fields are both structural OK."""
    with_fields = validate_engine_function_contracts(
        (
            _fn(
                name="vfx_a",
                params=(
                    _param(
                        name="trailStyle",
                        prompt_description="Deferred VFX trail.",
                        compiled_fields=("trailStyle",),
                        wire_obligation=WireObligation.DEFERRED_VFX,
                    ),
                ),
            ),
        )
    )
    empty_fields = validate_engine_function_contracts(
        (
            _fn(
                name="vfx_b",
                params=(
                    _param(
                        name="sparkHint",
                        prompt_description="Deferred VFX hint.",
                        compiled_fields=(),
                        wire_obligation=WireObligation.DEFERRED_VFX,
                    ),
                ),
            ),
        )
    )
    assert with_fields == ()
    assert empty_fields == ()


def test_mutation_self_tests_cover_each_registry_invariant() -> None:
    """Each invariant fails when a single field is mutated away from a valid base."""
    base_params = (
        _param(name="damage"),
        _param(
            name="knockback",
            prompt_description="Knockback strength.",
            value_kind=ParamValueKind.NUMBER,
            example_value=4.0,
            compiled_fields=("knockback",),
        ),
    )
    base = _fn(
        name="base_fn",
        meaning="Valid baseline function.",
        params=base_params,
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=("weapon",),
        repair_groups=(_group(members=("damage", "knockback"), policy_owner="runtime_secondary_policy"),),
    )
    assert validate_engine_function_contracts((base,)) == ()

    cases: list[tuple[str, tuple[EngineFunctionContract, ...]]] = [
        (
            "duplicate_function_names",
            (base, _fn(name="base_fn", params=(_param(name="other", compiled_fields=("other",)))),),
        ),
        (
            "duplicate_params",
            (
                _fn(
                    name="dup_params",
                    meaning="dup params",
                    params=(_param(name="damage"), _param(name="damage")),
                ),
            ),
        ),
        (
            "blank_function_name",
            (_fn(name="", meaning="m", params=(_param(),)),),
        ),
        (
            "blank_function_meaning",
            (_fn(name="blank_meaning", meaning=" ", params=(_param(),)),),
        ),
        (
            "blank_param_name",
            (
                _fn(
                    name="blank_param",
                    meaning="m",
                    params=(_param(name=" "),),
                ),
            ),
        ),
        (
            "blank_param_description",
            (
                _fn(
                    name="blank_desc",
                    meaning="m",
                    params=(_param(name="p", prompt_description="")),
                ),
            ),
        ),
        (
            "repair_member_not_in_params",
            (
                _fn(
                    name="bad_member",
                    meaning="m",
                    params=(_param(name="damage"),),
                    repair_groups=(_group(members=("nope",)),),
                ),
            ),
        ),
        (
            "blank_policy_owner",
            (
                _fn(
                    name="blank_policy",
                    meaning="m",
                    params=(_param(name="damage"),),
                    repair_groups=(_group(members=("damage",), policy_owner=""),),
                ),
            ),
        ),

        (
            "final_wire_without_compiled_fields",
            (
                _fn(
                    name="fw_empty",
                    meaning="m",
                    params=(
                        _param(
                            name="damage",
                            compiled_fields=(),
                            wire_obligation=WireObligation.FINAL_WIRE,
                        ),
                    ),
                ),
            ),
        ),
        (
            "control_derived_without_compiled_fields",
            (
                _fn(
                    name="cd_empty",
                    meaning="m",
                    params=(
                        _param(
                            name="flag",
                            compiled_fields=(),
                            wire_obligation=WireObligation.CONTROL_DERIVED,
                        ),
                    ),
                ),
            ),
        ),
        (
            "non_wire_with_compiled_fields",
            (
                _fn(
                    name="nw_fields",
                    meaning="m",
                    params=(
                        _param(
                            name="dbg",
                            prompt_description="debug",
                            compiled_fields=("dbg",),
                            wire_obligation=WireObligation.NON_WIRE,
                        ),
                    ),
                ),
            ),
        ),
        (
            "root_and_requires_root",
            (
                _fn(
                    name="both_root",
                    meaning="m",
                    params=(_param(),),
                    root_executor=True,
                    requires_root_executor=True,
                ),
            ),
        ),
    ]

    seen_keys: list[str] = []
    for key, specs in cases:
        errors = validate_engine_function_contracts(specs)
        assert errors, f"expected failure for invariant {key!r}"
        assert isinstance(errors, tuple)
        seen_keys.append(key)

    required = {
        "duplicate_function_names",
        "duplicate_params",
        "blank_function_name",
        "blank_function_meaning",
        "blank_param_name",
        "blank_param_description",
        "repair_member_not_in_params",
        "blank_policy_owner",

        "final_wire_without_compiled_fields",
        "control_derived_without_compiled_fields",
        "non_wire_with_compiled_fields",
        "root_and_requires_root",
    }
    assert set(seen_keys) == required


def test_types_module_exposes_no_compiler_or_routing_behavior() -> None:
    """Guard: metadata types may name wire concepts but own no execution behavior."""
    import inspect

    import infini_local.core.runtime_authoring.function_contract_types as mod

    public_functions = {
        name
        for name, value in vars(mod).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }
    assert public_functions == {"dataclass", "validate_engine_function_contracts"}
    source = inspect.getsource(mod).casefold()
    for forbidden_behavior in (
        "def compile",
        "def lower",
        "def project_final",
        "route_by_name",
        "trigger_action",
        "def compatibility",
    ):
        assert forbidden_behavior not in source
