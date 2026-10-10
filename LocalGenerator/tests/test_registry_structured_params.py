"""Structured Author parameters keep strict shape and exact wire provenance."""
from copy import deepcopy
from dataclasses import replace
import sys
from types import MappingProxyType

import pytest

from infini_local.core.runtime_authoring import capability_registry as registry
from infini_local.core.runtime_authoring import compiler, technical_lowering
from infini_local.core.runtime_authoring.capability_registry import ParamSpec
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness


def _typed_collision(monkeypatch):
    """Use an existing executable component to prove the generic seam."""
    document = build_capability_witness("set_projectile_collision")
    cap = registry.CAPABILITY_REGISTRY["set_projectile_collision"]
    params = dict(cap.params)
    params.pop("npcImmunityMode")
    cooldown = params.pop("localNpcHitCooldownEngineUnits")
    params["immunity"] = ParamSpec(
        "union", "Exact immunity variant", alternatives=(
            ParamSpec("string", "Owner immunity", enum=("owner_shared",),
                      wire_literals=MappingProxyType({"npcImmunityMode": "owner", "localNpcHitCooldownTicks": -1})),
            ParamSpec("object", "Local cooldown", properties=MappingProxyType({
                "localCooldown": replace(cooldown, minimum=0),
            }), wire_literals=MappingProxyType({"npcImmunityMode": "local"})),
        ),
    )
    modified = dict(registry.CAPABILITY_REGISTRY)
    changed = replace(cap, params=MappingProxyType(params), retained_receipt_params=MappingProxyType({
        name: cap.params[name] for name in ("npcImmunityMode", "localNpcHitCooldownEngineUnits")
    }))
    modified[cap.name] = replace(changed, final_wire_paths=registry._exact_wire_paths(changed))
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", modified)
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"].pop("npcImmunityMode")
    call["params"].pop("localNpcHitCooldownEngineUnits")
    return document, call


@pytest.mark.parametrize("value, mode, cooldown", [
    ("owner_shared", "owner", -1), ({"localCooldown": 0}, "local", 0),
    ({"localCooldown": 37}, "local", 37), ({"localCooldown": 600}, "local", 600),
])
def test_structured_param_compiles_existing_wire_and_exact_receipts(monkeypatch, value, mode, cooldown):
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = value
    compiled = compiler.compile_runtime_program(document)
    entity = next(e for e in compiled["runtimeProgram"]["entities"] if e["id"] == call["target"])
    assert entity["collision"]["npcImmunityMode"] == mode
    assert entity["collision"]["localNpcHitCooldownTicks"] == cooldown
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=compiled)["ok"]
    relevant = [r for r in receipts if ".params.immunity" in r.get("authoredPath", "")]
    assert len(relevant) == 2
    for removed in relevant:
        assert not technical_lowering.audit_compiler_receipts(
            [r for r in receipts if r is not removed], authored_document=document, final_document=compiled,
        )["ok"]
    forged = deepcopy(receipts)
    next(r for r in forged if r.get("authoredPath") == relevant[0]["authoredPath"])["value"] = "forged"
    assert not technical_lowering.audit_compiler_receipts(forged, authored_document=document, final_document=compiled)["ok"]


@pytest.mark.parametrize("invalid", [None, "local", {}, {"localCooldown": -1},
                                      {"localCooldown": 601}, {"localCooldown": True},
                                      {"localCooldown": 10, "owner": True}])
def test_structured_param_rejects_missing_or_invalid_choice(monkeypatch, invalid):
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = invalid
    with pytest.raises(ValueError):
        compiler.compile_runtime_program(document)


def test_object_keeps_exact_leaf_units_and_rejects_empty_group():
    spec = ParamSpec("object", "Explicit grouped stats", min_properties=1, properties={
        "radiusTiles": ParamSpec("number", "Radius on the exact pixel lattice", minimum=0.5,
                                 maximum=48, multiple_of=1 / 16, wire_multiplier=16, wire_name="radiusPx"),
        "updatesPerTick": ParamSpec("integer", "Updates", minimum=1, maximum=6, wire_offset=-1,
                                    wire_name="extraUpdates", required=False),
    })
    assert not strict_schema_errors({"radiusTiles": 8.0625, "updatesPerTick": 6}, spec.schema())
    rows = spec.projected_fields({"radiusTiles": 8.0625, "updatesPerTick": 6}, "group")
    assert [(r.authored_path, r.wire_path, r.value) for r in rows] == [
        ("group.radiusTiles", "radiusPx", 129), ("group.updatesPerTick", "extraUpdates", 5),
    ]
    assert strict_schema_errors({}, spec.schema())
    assert strict_schema_errors({"radiusTiles": 0.6}, spec.schema())


def _grouped_armor(monkeypatch):
    # Exact #12 alias witness: setBonuses.aggroPoints -> armor.setBonusAggro,
    # integer -1000..1000. This is test metadata, not a production Author alias.
    document = build_capability_witness("configure_armor")
    cap = registry.CAPABILITY_REGISTRY["configure_armor"]
    params = dict(cap.params)
    old = params["setBonuses"].properties["aggroPoints"]
    params["setBonuses"] = ParamSpec("object", "Explicit set bonuses", required=False,
                                    min_properties=1, properties={"aggroPoints": old})
    modified = dict(registry.CAPABILITY_REGISTRY)
    changed = replace(cap, params=params, retained_receipt_params={"setBonusAggroPoints": old})
    modified[cap.name] = replace(changed, final_wire_paths=registry._exact_wire_paths(changed))
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", modified)
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"]["setBonuses"] = {"aggroPoints": 1}
    return document, call


@pytest.mark.parametrize("bad", [True, 1001, 1.0, None])
def test_grouped_source_domain_is_not_authenticated_by_coherent_receipts(monkeypatch, bad):
    from infini_local.core.runtime_authoring import validate_runtime_program
    document, call = _grouped_armor(monkeypatch)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    call["params"]["setBonuses"]["aggroPoints"] = bad
    wire["armor"]["setBonusAggro"] = bad
    next(r for r in receipts if r["finalPath"] == "armor.setBonusAggro")["value"] = bad
    assert not validate_runtime_program(document)["ok"]
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=document, final_document=wire,
    )["ok"]


def test_ambiguous_union_fails_closed():
    spec = ParamSpec("union", "Invalid duplicate branches", alternatives=(
        ParamSpec("string", "One", enum=("x",), wire_literals={"field": 1}),
        ParamSpec("string", "Two", enum=("x",), wire_literals={"field": 2}),
    ))
    with pytest.raises(ValueError, match="exactly one"):
        spec.projected_fields("x", "choice")


def test_nested_union_diagnostic_does_not_unfreeze_the_valid_sibling(monkeypatch):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, validate_runtime_program
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = {"localCooldown": 601}
    report = validate_runtime_program(document)
    assert not report["ok"]
    leaf = next(e for e in report["errors"] if e["path"].endswith(".immunity.localCooldown"))
    assert leaf["code"] == "shape_maximum"
    scope = build_runtime_repair_scope(document, report["errors"])
    permissions = next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == "witness_call")
    assert "params.immunity.localCooldown" in permissions
    assert "params.immunity" not in permissions
    assert "params" not in permissions


def test_retained_provenance_preserves_old_wire_without_accepting_old_author(monkeypatch):
    old_author = build_capability_witness("set_projectile_collision")
    old_wire = compiler.compile_runtime_program(old_author)
    old_receipts = deepcopy(old_wire["runtimeContract"]["finalWireReceipts"])
    _typed_collision(monkeypatch)
    assert technical_lowering.audit_compiler_receipts(old_receipts, final_document=old_wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts(
        old_receipts, authored_document=old_author, final_document=old_wire,
    )["ok"]
    with pytest.raises(ValueError):
        compiler.compile_runtime_program(old_author)
    changed = deepcopy(old_receipts)
    row = next(r for r in changed if r.get("authoredPath", "").endswith(".localNpcHitCooldownEngineUnits"))
    row["value"] = 10.5
    assert not technical_lowering.audit_compiler_receipts(changed)["ok"]
    row["value"] = 10
    row["authoredPath"] = row["authoredPath"].replace("localNpcHitCooldownEngineUnits", "unregisteredOldName")
    assert not technical_lowering.audit_compiler_receipts(changed)["ok"]


def _two_collision_calls(monkeypatch, typed):
    document = build_capability_witness("spawn_entity_on_event")
    if typed:
        _typed_collision(monkeypatch)
    calls = [c for c in document["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision"]
    assert len(calls) == 2
    for i, call in enumerate(calls):
        if typed:
            call["params"].pop("npcImmunityMode")
            call["params"].pop("localNpcHitCooldownEngineUnits")
            call["params"]["immunity"] = {"localCooldown": 10 + i}
        else:
            call["params"]["localNpcHitCooldownEngineUnits"] = 10 + i
    return document, calls


@pytest.mark.parametrize("typed", [False, True], ids=["legacy-scalar", "typed-immunity"])
@pytest.mark.parametrize("attack", ["source-targets", "final-owners"])
def test_call_projection_authenticates_exact_entity_owner(monkeypatch, typed, attack):
    from infini_local.core.runtime_authoring import validate_runtime_program
    document, calls = _two_collision_calls(monkeypatch, typed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    if attack == "source-targets":
        calls[0]["target"], calls[1]["target"] = calls[1]["target"], calls[0]["target"]
        assert validate_runtime_program(document)["ok"]  # valid new Author, stale proof
    else:
        entities = wire["runtimeProgram"]["entities"]
        indices = [next(i for i, e in enumerate(entities) if e["id"] == c["target"]) for c in calls]
        entities[indices[0]]["collision"], entities[indices[1]]["collision"] = (
            entities[indices[1]]["collision"], entities[indices[0]]["collision"])
        for row in receipts:
            if row.get("fn") == "set_projectile_collision":
                old = next(i for i in indices if row["finalPath"].startswith(f"runtimeProgram.entities[{i}]."))
                new = indices[1] if old == indices[0] else indices[0]
                row["finalPath"] = row["finalPath"].replace(f"entities[{old}]", f"entities[{new}]")
    standalone = technical_lowering.audit_compiler_receipts(receipts, final_document=wire)
    assert standalone["ok"] and standalone["authoredSourceChecked"] is False
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=document, final_document=wire,
    )["ok"]


@pytest.mark.parametrize("alias", [False, True], ids=["legacy-chain", "pr26-nearest"])
@pytest.mark.parametrize("attack", ["id-only", "coordinated-events"])
def test_event_projection_authenticates_exact_call_identity(monkeypatch, alias, attack):
    document = build_capability_witness("chain_damage_on_event")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    another = deepcopy(call)
    another.update(id="another_nearest")
    another["params"]["count"] = 7
    document["runtimeProgram"]["calls"].append(another)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    if alias:
        # Replay the exact #26 alias over compiler-produced action-4 wire.
        # #10 intentionally does not admit/compile this future Author vocabulary.
        cap = registry.CAPABILITY_REGISTRY["chain_damage_on_event"]
        params = dict(cap.params)
        params["maxTargets"] = replace(params.pop("count"), wire_name="count")
        params["when"] = replace(params.pop("event"), wire_name="event")
        modified = dict(registry.CAPABILITY_REGISTRY)
        modified["damage_nearest_on_event"] = replace(cap, name="damage_nearest_on_event", params=params,
                                                     fixed_wire_literals={"action": "chain_damage_on_event", "actionCode": 4})
        monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", modified)
        for source in (call, another):
            source["fn"] = "damage_nearest_on_event"
            source["params"]["maxTargets"] = source["params"].pop("count")
            source["params"]["when"] = source["params"].pop("event")
        for row in receipts:
            if row.get("fn") == "chain_damage_on_event":
                row["fn"] = "damage_nearest_on_event"
                row["authoredPath"] = row["authoredPath"].replace(".params.count", ".params.maxTargets").replace(".params.event", ".params.when")
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    events = entity["events"]
    assert len(events) == 2
    if attack == "id-only":
        events[0]["id"], events[1]["id"] = events[1]["id"], events[0]["id"]
    else:
        ids = [e["id"] for e in events]
        events.reverse()
        for event, identity in zip(events, ids):
            event["id"] = identity
        for row in receipts:
            if row.get("callId") in {call["id"], another["id"]}:
                row["finalPath"] = row["finalPath"].replace("events[0]", "events[x]").replace("events[1]", "events[0]").replace("events[x]", "events[1]")
    for source in (None, document):
        assert not technical_lowering.audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("attack", ["range", "hybrid", "missing", "duplicate", "foreign-source"])
def test_wire_only_immunity_requires_one_complete_admitted_variant(monkeypatch, attack):
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = {"localCooldown": 19}
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    group = [r for r in receipts if ".params.immunity" in r.get("authoredPath", "")]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    assert technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]
    if attack == "range":
        entity["collision"]["localNpcHitCooldownTicks"] = 601
        next(r for r in group if r["finalPath"].endswith(".localNpcHitCooldownTicks"))["value"] = 601
    elif attack == "hybrid":
        entity["collision"]["npcImmunityMode"] = "owner"
        next(r for r in group if r["finalPath"].endswith(".npcImmunityMode"))["value"] = "owner"
    elif attack == "missing":
        receipts.remove(group[0])
    elif attack == "duplicate":
        receipts.append(deepcopy(group[0]))
    else:
        group[0]["authoredPath"] += ".foreign"
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_wire_only_grouped_armor_rejects_bool_alias(monkeypatch):
    document, _ = _grouped_armor(monkeypatch)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    wire["armor"]["setBonusAggro"] = True
    next(r for r in receipts if r["finalPath"] == "armor.setBonusAggro")["value"] = True
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_wire_only_spawn_position_rejects_impossible_above_height(monkeypatch):
    # #14 exact above-height witness, without importing another tree's owners.
    document = build_capability_witness("configure_spawn")
    cap = registry.CAPABILITY_REGISTRY["configure_spawn"]
    params = dict(cap.params)
    placement = params.pop("placement")
    params["position"] = ParamSpec("object", "Above anchor", properties={
        "above": replace(placement, enum=("cursor",), wire_name="placement"),
        "heightTiles": ParamSpec("number", "Height", minimum=1, maximum=80, wire_name="overTarget.heightTiles"),
        "activationDelayTicks": ParamSpec("integer", "Delay", minimum=0, maximum=600, wire_name="overTarget.delayTicks"),
    })
    changed = replace(cap, params=params)
    modified = dict(registry.CAPABILITY_REGISTRY)
    modified[cap.name] = replace(changed, final_wire_paths=registry._exact_wire_paths(changed))
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", modified)
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"].pop("placement")
    call["params"]["position"] = {"above": "cursor", "heightTiles": 1, "activationDelayTicks": 0}
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity["spawn"]["overTarget"]["heightTiles"] = 0.5
    next(r for r in receipts if r.get("authoredPath", "").endswith(".position.heightTiles"))["value"] = 0.5
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


@pytest.mark.parametrize("typed", [False, True], ids=["legacy-scalar", "typed-immunity"])
@pytest.mark.parametrize("attack", ["duplicate", "missing-all", "source-index"])
def test_projection_coverage_is_unique_and_complete(monkeypatch, typed, attack):
    document, calls = _two_collision_calls(monkeypatch, typed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    source_tail = ".params.immunity" if typed else ".params.localNpcHitCooldownEngineUnits"
    relevant = [r for r in receipts if r.get("callId") == calls[0]["id"]
                and source_tail in r.get("authoredPath", "")]
    if attack == "duplicate":
        receipts.append(deepcopy(relevant[-1]))
    elif attack == "missing-all":
        receipts[:] = [r for r in receipts if r not in relevant]
    else:
        # Different source coordinates cannot claim one wire owner's output.
        for r in relevant:
            r["authoredPath"] = r["authoredPath"].replace("calls[", "calls[9")
    for source in (None, document):
        assert not technical_lowering.audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("bad", [True, 601, 1.0, None])
@pytest.mark.parametrize("source_available", [False, True])
def test_legacy_scalar_domain_is_not_authenticated_by_coherent_receipts(bad, source_available):
    document = build_capability_witness("set_projectile_collision")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    call["params"]["localNpcHitCooldownEngineUnits"] = bad
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity["collision"]["localNpcHitCooldownTicks"] = bad
    next(r for r in receipts if r.get("callId") == call["id"] and r["finalPath"].endswith(".localNpcHitCooldownTicks"))["value"] = bad
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=document if source_available else None, final_document=wire,
    )["ok"]


@pytest.mark.parametrize("typed", [False, True], ids=["legacy-scalar", "typed-immunity"])
def test_wire_claim_cannot_split_one_call_across_entity_owners(monkeypatch, typed):
    document, calls = _two_collision_calls(monkeypatch, typed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    entities = wire["runtimeProgram"]["entities"]
    indices = [next(i for i, e in enumerate(entities) if e["id"] == c["target"]) for c in calls]
    # Equal-valued scalar fields still belong to one exact call/component.
    row = next(r for r in receipts if r.get("callId") == calls[0]["id"] and r["finalPath"].endswith(".tileCollide"))
    row["finalPath"] = row["finalPath"].replace(f"entities[{indices[0]}]", f"entities[{indices[1]}]")
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_unrelated_retained_parameter_cannot_excuse_missing_typed_outputs(monkeypatch):
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = {"localCooldown": 19}
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    cap = technical_lowering.CAPABILITY_REGISTRY["set_projectile_collision"]
    retained = dict(cap.retained_receipt_params)
    retained["extraUpdates"] = registry.CAPABILITY_REGISTRY[cap.name].params["extraUpdates"]
    modified = dict(technical_lowering.CAPABILITY_REGISTRY)
    modified[cap.name] = replace(cap, retained_receipt_params=retained)
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", modified)
    receipts[:] = [r for r in receipts if ".params.immunity" not in r.get("authoredPath", "")]
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


@pytest.mark.parametrize("missing", ["npcImmunityMode", "localNpcHitCooldownEngineUnits"])
def test_retained_scalar_variant_outputs_still_require_complete_coverage(monkeypatch, missing):
    document = build_capability_witness("set_projectile_collision")
    wire = compiler.compile_runtime_program(document)
    _typed_collision(monkeypatch)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipts[:] = [r for r in receipts if not (r.get("callId") == "witness_call"
                                             and r["authoredPath"].endswith(".params." + missing))]
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_wire_output_cannot_be_claimed_by_two_distinct_calls():
    document = build_capability_witness("set_projectile_collision")
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    duplicates = [deepcopy(r) for r in receipts if r.get("callId") == "witness_call"]
    for row in duplicates:
        row["callId"] = "another_collision"
        row["authoredPath"] = row["authoredPath"].replace("calls[", "calls[9")
    receipts.extend(duplicates)
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_retained_same_name_domain_is_wire_only_not_author_permission(monkeypatch):
    document = build_capability_witness("move_player_on_use")
    wire = compiler.compile_runtime_program(document)
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"]["mode"] = wire["gameplay"]["mobilityMode"] = "recall_home"
    for row in wire["runtimeContract"]["finalWireReceipts"]:
        if row.get("callId") == call["id"] and row.get("authoredPath", "").endswith(".params.mode"):
            row["value"] = "recall_home"
    receipts = deepcopy(wire["runtimeContract"]["finalWireReceipts"])
    cap = registry.CAPABILITY_REGISTRY["move_player_on_use"]
    params = dict(cap.params)
    params["mode"] = replace(params["mode"], enum=("blink_to_cursor",))
    changed = dict(registry.CAPABILITY_REGISTRY)
    changed[cap.name] = replace(cap, params=params, retained_receipt_params={"mode": cap.retained_receipt_params["mode"]})
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", changed)
    before = deepcopy(wire)
    assert technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    assert wire == before and receipts == wire["runtimeContract"]["finalWireReceipts"]


def test_fn_literal_provenance_requires_value_source_and_complete_coverage(monkeypatch):
    document = build_capability_witness("configure_spawn")
    changed = dict(registry.CAPABILITY_REGISTRY)
    changed["configure_spawn"] = replace(changed["configure_spawn"], fixed_wire_literals={"enabled": True})
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", changed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    literal = next(r for r in receipts if r.get("fn") == "configure_spawn" and r["finalPath"].endswith(".enabled"))
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    for key, value in (("value", False), ("status", "delivered"), ("authoredPath", "runtimeProgram.calls[0].fn")):
        forged = deepcopy(receipts)
        forged[receipts.index(literal)][key] = value
        assert not technical_lowering.audit_compiler_receipts(forged, authored_document=document, final_document=wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts([r for r in receipts if r is not literal], final_document=wire)["ok"]
