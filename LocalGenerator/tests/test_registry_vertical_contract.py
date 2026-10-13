"""Canonical registry inventories and real schema/validator/Repair/compiler consumers."""

from __future__ import annotations
import ast
import inspect
from dataclasses import replace
from types import MappingProxyType, ModuleType
from infini_local.core.runtime_authoring.capability_registry import visible_capabilities
from copy import deepcopy
import pytest
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    BINDING_ACTION_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    runtime_authoring_registry_manifest,
    capability_provider_union,
    compact_capability_catalog,
    compile_runtime_program,
    validate_runtime_program,
    validate_runtime_wire,
    audit_compiler_receipts,
    compiler,
    validator,
    repair_scope,
)
from infini_local.core.runtime_authoring import capability_registry
import infini_local.core.runtime_authoring.capability_registry as registry_module
import infini_local.core.runtime_authoring.validator as validator_module
from infini_local.core.runtime_authoring.capability_registry import (
    runtime_authoring_prompt_field_guide,
    EventDependencyAlternative,
    event_dependency_alternatives,
    event_alternative_is_present,
)
from infini_local.core.runtime_authoring.program_schema import (
    runtime_program_author_schema,
    PRIMARY_ENTITY_FIELD,
    PRIMARY_ENTITY_SELECTION_FIELD,
    authored_primary_entity_id,
    primary_entity_repair_transaction,
)
from infini_local.core.runtime_authoring.technical_lowering import (
    EXACT_REPETITION_COMPRESSION_POLICY,
    GLOBAL_TECHNICAL_LOWERINGS,
    MIN_EXACT_REPETITION_COMPRESSION,
    PRIMARY_BINDING_ROLE_LOWERER_ID,
    PRIMARY_OWNER_LOWERER_ID,
    primary_binding_role,
    primary_owner_for_kind,
)
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa.capability_library_audit import capability_library_audit
from infini_local.pipelines.author_item_contract import author_item_provider_response_schema
from infini_local.pipelines import llm_authoring_pipeline as pipeline


@pytest.mark.parametrize(
    "key,identity,registry",
    [
        pytest.param("entityKinds", "kind", ENTITY_KIND_REGISTRY, id="entity-kinds"),
        pytest.param("inputs", "input", INPUT_KIND_REGISTRY, id="inputs"),
        pytest.param("bindingActions", "action", BINDING_ACTION_REGISTRY, id="binding-actions"),
        pytest.param("events", "event", EVENT_KIND_REGISTRY, id="events"),
        pytest.param("capabilities", "fn", {cap.name: cap for cap in visible_capabilities()}, id="capabilities"),
    ],
)
def test_machine_manifest_has_exact_registry_identity(key, identity, registry):
    rows = runtime_authoring_registry_manifest()[key]
    expected = ({name for name, cap in registry.items() if cap.prompt_visible and cap.decision == "expose"}
                if key == "capabilities" else set(registry))
    assert {r[identity] for r in rows} == expected
    assert len(rows) == len(expected)
    if key == "capabilities":
        assert all(r["slot"] and r["authority"] for r in rows)
        assert all(
            {"requires", "positionOwnership", "activationSpawnCountParam", "meaningfulForStationary", "multiplicity"} <= r.keys()
            for r in rows
        )


@pytest.mark.parametrize("fn", [pytest.param(fn, id=fn) for fn in (cap.name for cap in visible_capabilities())])
def test_registered_capability_survives_schema_card_projection_compiler_and_wire(fn):
    cap = CAPABILITY_REGISTRY[fn]
    assert all("*" not in p for p in cap.final_wire_paths)
    full, compact = cap.prompt_card(), cap.author_prompt_card()
    assert {k: v for k, v in compact.items() if k != "params"} == {k: v for k, v in full.items() if k != "params"}
    assert set(compact["params"]) == set(full["params"]) == set(cap.params)
    assert compact.get("requires", []) == [r.card() for r in cap.requirements]
    guide = runtime_authoring_prompt_field_guide()
    for name, spec in cap.params.items():
        row, original = compact["params"][name], full["params"][name]
        if fn != "add_equipment_damage_bonus":
            assert all(any(p.endswith("." + wire_name) for p in cap.final_wire_paths) for wire_name in spec.wire_field_names(name)), (fn, name)
        meaning = row.get("meaning", "")
        if fn == "configure_armor" and name.startswith("setBonus") and name != "setBonuses":
            meaning = guide["setBonusParamPrefix"] + meaning
        elif fn == "configure_armor" and not meaning:
            meaning = CAPABILITY_REGISTRY["configure_accessory"].params[name].description
        assert meaning == original["meaning"] == spec.description
        assert row["type"] == original["type"] == spec.kind
        assert row.get("optional", False) is not spec.required
        for key in ("min", "max", "enum", "pattern", "reference"):
            assert row.get(key) == original.get(key)
        assert row.get("min") == spec.minimum and row.get("max") == spec.maximum
        assert row.get("multipleOf") == spec.multiple_of
        if "units" not in row and spec.units:
            assert any(
                name.endswith(suffix) and spec.units == unit
                for suffix, unit in (("Ticks", "ticks"), ("Tiles", "tiles"), ("Px", "pixels"), ("Radians", "radians"))
            )
        else:
            assert row.get("units") == original.get("units")
        if "neutral" not in row and "neutral" in original:
            assert not spec.required and spec.neutral == 0
        else:
            assert row.get("neutral") == original.get("neutral")
    import json
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_canonical_author_notation import _explicit_calls
    item = build_capability_witness(fn)
    before = deepcopy(item)
    explicit = _explicit_calls(item)
    explicit_before = deepcopy(explicit)
    assert all(set(call) == {"id", "fn", "target", "params"} for call in explicit["runtimeProgram"]["calls"])
    assert Draft202012Validator(author_item_response_schema()).is_valid(explicit)
    response_format = {"type": "json_schema", "json_schema": {"schema": author_item_provider_response_schema()}}
    assert pipeline._prepare_parsed_author_item(item, response_format=response_format) == item
    projected = pipeline._prepare_parsed_author_item(explicit, response_format=response_format)
    assert projected == explicit
    wire = compile_runtime_program(projected)
    sparse_wire = compile_runtime_program(item)
    assert json.dumps(wire, ensure_ascii=False) == json.dumps(sparse_wire, ensure_ascii=False), "Exact serialized executable wire AND receipts remain unchanged"
    assert wire["runtimeContract"]["finalWireReceipts"]
    assert validate_runtime_wire(wire)["ok"]
    # Compiler authenticates explicit source; sparse identity is a distinct oracle.
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=item, final_document=wire)["ok"]
    assert item == before and explicit == explicit_before
    if cap.params:
        rows = deepcopy(wire["runtimeContract"]["finalWireReceipts"])
        direct = next(
            (r for r in rows if r.get("fn") == fn and r.get("status") in {"delivered", "alias_lowering"} and ".params." in str(r.get("authoredPath") or "")),
            None,
        )
        if direct is None:
            assert fn == "apply_vanilla_buff_on_use"
        else:
            direct["status"] = "technical_projection"
            assert not audit_compiler_receipts(rows, authored_document=item, final_document=wire)["ok"]
            wire["runtimeContract"]["finalWireReceipts"] = rows
            assert not validate_runtime_wire(wire)["ok"]


def test_library_audit_and_shared_notation_have_no_missing_boundary():
    expected = {cap.name for cap in visible_capabilities()}
    for rows, identity in ((runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"], lambda row: row["properties"]["fn"]["const"]),
                           (capability_provider_union(), lambda row: row["properties"]["fn"]["const"]),
                           (compact_capability_catalog(), lambda row: row["fn"])):
        assert {identity(row) for row in rows} == expected and len(rows) == len(expected)
    report = capability_library_audit()
    assert report["ok"] and report["score"] == report["scoreMax"], report["issues"]
    lifetime = next(row for row in report["rangeParity"]
                    if row["capability"] == "set_projectile_lifetime")
    assert lifetime["authorBounds"] == lifetime["csharpBounds"] == [1, 36000]
    assert lifetime["preserved"]
    metrics = report["metrics"]
    assert metrics["capabilities"] == len(CAPABILITY_REGISTRY)
    assert metrics["publicCapabilities"] == metrics["verticalSliceCount"] == sum(cap.prompt_visible and cap.decision == "expose" for cap in CAPABILITY_REGISTRY.values())
    assert metrics["boundedNumericParameters"] == metrics["numericParameters"]
    expected_references = sum(spec.reference is not None and spec.reference.namespace == "entity"
                              for cap in CAPABILITY_REGISTRY.values() for spec in cap.params.values())
    assert metrics["typedEntityReferences"] == expected_references and metrics["requirements"] >= 10
    guide = runtime_authoring_prompt_field_guide()
    assert "unless marked optional" in guide["paramNotation"]
    for suffix, unit in (("Ticks", "ticks"), ("Tiles", "tiles"), ("Px", "pixels"), ("Radians", "radians")):
        assert f"{suffix}={unit}" in guide["paramNotation"]
    assert guide["exclusiveGroup"]["scope"] == "per exact target entity" and "authority" not in guide
    assert set(guide["positionOwnership"]) == {c.position_ownership for c in CAPABILITY_REGISTRY.values()}
    assert "configure_accessory" in guide["armorParamInheritance"]
    assert "Matching armor set" in guide["setBonusParamPrefix"]


def test_registry_mutation_updates_schema_but_missing_executor_stays_red(monkeypatch: pytest.MonkeyPatch) -> None:
    source = CAPABILITY_REGISTRY["emit_light_while_active"]
    synthetic = replace(
        source,
        name="emit_test_light",
        summary="Synthetic mutation witness over an existing parameter surface.",
        compiler_owner="synthetic.missing.vertical.slice",
        csharp_owner="SyntheticMissingExecutor.cs",
        provenance="mutation test",
    )
    mutated = dict(CAPABILITY_REGISTRY)
    mutated[synthetic.name] = synthetic
    frozen = MappingProxyType(mutated)
    monkeypatch.setattr(registry_module, "CAPABILITY_REGISTRY", frozen)
    monkeypatch.setattr(validator_module, "CAPABILITY_REGISTRY", frozen)
    schema = runtime_program_author_schema()
    variants = schema["properties"]["calls"]["items"]["oneOf"]
    assert any(row["properties"]["fn"].get("const") == synthetic.name for row in variants)

    authored = build_runtime_fixture("door_on_chain")
    authored["runtimeProgram"]["calls"].append(
        {
            "id": "synthetic_light",
            "fn": synthetic.name,
            "target": "chained_door",
            "params": {"strength": 0.5, "color": "white"},
        }
    )
    with pytest.raises(AssertionError, match="unhandled runtime entity capability"):
        compile_runtime_program(authored)


def _imports_symbol(module: ModuleType, imported_module: str, symbol: str) -> bool:
    tree = ast.parse(inspect.getsource(module))
    return any(
        isinstance(node, ast.ImportFrom) and node.module == imported_module and any(alias.name == symbol for alias in node.names)
        for node in ast.walk(tree)
    )


def _imports_module(module: ModuleType, imported_module: str) -> bool:
    tree = ast.parse(inspect.getsource(module))
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == imported_module
        or isinstance(node, ast.Import)
        and any(alias.name == imported_module for alias in node.names)
        for node in ast.walk(tree)
    )


def test_primary_shape_and_repair_transaction_have_one_schema_owner() -> None:
    program = {PRIMARY_ENTITY_FIELD: "boomerang"}
    assert authored_primary_entity_id(program) == "boomerang"
    assert primary_entity_repair_transaction(["item", "boomerang", "item"]) == {
        "allowed": True,
        "candidateEntityIds": ["boomerang", "item"],
        "mustSelectExactlyOne": True,
    }
    assert _imports_symbol(
        validator,
        "infini_local.core.runtime_authoring.program_schema",
        "authored_primary_entity_id",
    )
    assert _imports_symbol(
        repair_scope,
        "infini_local.core.runtime_authoring.program_schema",
        "primary_entity_repair_transaction",
    )
    assert PRIMARY_ENTITY_SELECTION_FIELD == "primaryEntitySelection"


def test_primary_wire_projection_has_one_lowering_owner_and_receipts() -> None:
    assert primary_binding_role("boomerang", "boomerang") == "primary"
    assert primary_binding_role("boomerang", "item") == "secondary"
    assert primary_owner_for_kind("item_body") == "item_body"
    assert primary_owner_for_kind("free_projectile") == "projectile"
    assert primary_owner_for_kind("unknown_future_kind") == ""
    assert _imports_symbol(
        compiler,
        "infini_local.core.runtime_authoring.technical_lowering",
        "primary_binding_role",
    )

    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    owner_receipts = [row for row in receipts if row.get("lowererId") == PRIMARY_OWNER_LOWERER_ID]
    assert len(owner_receipts) == 1
    assert owner_receipts[0]["value"] == compiled["runtimeProgram"]["primaryOwner"]
    assert audit_compiler_receipts(receipts)["ok"] is True

    role_lowerer = next(row for row in GLOBAL_TECHNICAL_LOWERINGS if row["id"] == PRIMARY_BINDING_ROLE_LOWERER_ID)
    assert role_lowerer["addsDesignChoice"] is False
    assert "authoringCompression" not in role_lowerer


def test_exact_repetition_policy_is_global_and_not_a_primary_semantic_rule() -> None:
    assert MIN_EXACT_REPETITION_COMPRESSION == 5
    assert EXACT_REPETITION_COMPRESSION_POLICY == {
        "kind": "exact_repetition",
        "minimumRepeatedPlacements": 5,
        "requiresLiteralEquality": True,
        "mayAddDesignChoice": False,
    }
    for lowerer in GLOBAL_TECHNICAL_LOWERINGS:
        compression = lowerer.get("authoringCompression")
        if compression is not None:
            assert compression["minimumRepeatedPlacements"] >= 5
            assert compression["kind"] == "exact_repetition"


def test_event_dependency_is_a_typed_registry_projection() -> None:
    on_hit = event_dependency_alternatives("on_hit", "free_projectile")
    assert on_hit == (EventDependencyAlternative.required_call("set_projectile_damage"),)
    assert event_alternative_is_present(
        on_hit[0],
        target_id="projectile",
        target_calls=[{"fn": "set_projectile_damage", "params": {"damage": 7}}],
        bindings=[],
    )
    assert not event_alternative_is_present(
        on_hit[0],
        target_id="projectile",
        target_calls=[],
        bindings=[],
    )

    on_use = event_dependency_alternatives("on_use", "item_body")
    assert on_use == (
        EventDependencyAlternative.any_binding_input(
            ("primary_use", "alternate_use"),
            ("spawn_entity", "use_item_body", "apply_item_effects"),
        ),
    )
    assert event_alternative_is_present(
        on_use[0],
        target_id="item",
        target_calls=[],
        bindings=[
            {
                "input": "primary_use",
                "action": {"kind": "use_item_body", "targetId": "item"},
                "stackCost": 0,
                "contactDamage": True,
            }
        ],
    )
    assert not event_alternative_is_present(
        on_use[0],
        target_id="item",
        target_calls=[],
        bindings=[
            {
                "input": "primary_use",
                "usePolicy": {
                    "action": {"kind": "place_item", "targetId": "item", "placementCallId": "place"},
                    "stackCost": 1,
                    "contactDamage": False,
                },
            }
        ],
    )
    assert EVENT_KIND_REGISTRY["on_use"].prompt_card()["producerFreeKinds"] == []
    assert "free_projectile" in EVENT_KIND_REGISTRY["on_spawn"].prompt_card()["producerFreeKinds"]
    tile = event_dependency_alternatives("on_tile_collision", "free_projectile")
    assert tile == (
        EventDependencyAlternative.required_call(
            "set_projectile_collision",
            {"tileCollide": True},
        ),
    )


def test_event_registry_mutation_reaches_validator_and_repair_projection(monkeypatch) -> None:
    # Without damage, this on_hit has no producer under the original registry;
    # its existing collision call becomes the producer after the registry edit.
    without_damage = build_runtime_fixture("workbench_blade")
    without_damage["runtimeProgram"]["calls"] = [
        row for row in without_damage["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_damage"
    ]
    original_errors = validator.validate_runtime_program(without_damage)["errors"]
    assert [(row["code"], row["allowed"]) for row in original_errors] == [
        ("event_not_emitted", ["set_projectile_damage"]),
    ]

    # Conversely, removing collision leaves an unrelated required-component
    # error, but on_hit itself is still emitted by the original damage call.
    without_collision = build_runtime_fixture("workbench_blade")
    without_collision["runtimeProgram"]["calls"] = [
        row for row in without_collision["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_collision"
    ]
    assert [row["code"] for row in validator.validate_runtime_program(without_collision)["errors"]] == [
        "missing_required_component",
    ]

    registry = dict(EVENT_KIND_REGISTRY)
    registry["on_hit"] = replace(
        registry["on_hit"],
        producer_capabilities=("set_projectile_collision",),
    )
    monkeypatch.setattr(capability_registry, "EVENT_KIND_REGISTRY", registry)
    assert validator.validate_runtime_program(without_damage)["ok"] is True

    changed_errors = validator.validate_runtime_program(without_collision)["errors"]
    event_errors = [row for row in changed_errors if row["code"] == "event_not_emitted"]
    assert len(event_errors) == 1
    assert event_errors[0]["allowed"] == ["set_projectile_collision"]
    assert event_errors[0]["relatedIds"] == ["workbench_blade"]
    scope = repair_scope.build_runtime_repair_scope(without_collision, event_errors)
    assert scope["create"]["calls"]["allowedFns"] == ["set_projectile_collision"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["workbench_blade"]
    assert scope["repairRequirements"][0]["requiredOneOfCapabilities"] == ["set_projectile_collision"]
    assert scope["eventAlternatives"] == [
        {
            "callId": "shed_nails",
            "targetId": "workbench_blade",
            "allowed": [
                {
                    "event": "on_hit",
                    "requiredCalls": [
                        {
                            "fn": "set_projectile_collision",
                            "targetId": "workbench_blade",
                            "exactParams": [],
                        }
                    ],
                    "requiredBindings": [],
                }
            ],
            "mustChooseOneCompleteAlternative": True,
        }
    ]


def test_removed_facade_modules_have_no_consumers() -> None:
    consumers = (compiler, validator, repair_scope)
    forbidden = (
        "infini_local.core.runtime_authoring.primary_entity_contract",
        "infini_local.core.runtime_authoring.event_dependency_contract",
    )
    assert not any(_imports_module(module, imported_module) for module in consumers for imported_module in forbidden)
