"""Receipt provenance cannot be forged even when equal-valued outputs are swapped."""

from copy import deepcopy
import re
from typing import Any
import pytest
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    compile_runtime_program,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import (
    PRIMARY_BINDING_ROLE_LOWERER_ID,
    PRIMARY_OWNER_LOWERER_ID,
    audit_compiler_receipts,
)
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture


def _call(doc, fn):
    return next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)


def _receipt(rows, path):
    return next(r for r in rows if r.get("finalPath") == path)


@pytest.mark.parametrize(
    "fn,params,mutation,paths,reason",
    [
        pytest.param(
            "configure_accessory",
            None,
            "source",
            ("accessory.defense", "maxManaPoints"),
            "absent from originating call",
            id="source-absent-in-exact-call",
        ),
        pytest.param(
            "configure_accessory",
            None,
            "value",
            ("accessory.defense", "not_the_authored_value"),
            "not the declared projection",
            id="not-authored-value",
        ),
        pytest.param(
            "configure_accessory",
            {"defensePoints": 1, "moveSpeedBonusPercent": 5},
            "drop",
            ("accessory.defense",),
            "equipment parameter has no receipt",
            id="equipment-missing-param",
        ),
        pytest.param(
            "configure_item_stats",
            None,
            "drop",
            ("gameplay.value",),
            "authored parameter has no compiler receipt",
            id="ordinary-missing-param",
        ),
        pytest.param(
            "configure_accessory",
            {"defensePoints": 1},
            "wire",
            ("accessory.defense", 99),
            "final wire value differs",
            id="wire-disagrees-with-provenance",
        ),
        pytest.param(
            "configure_item_stats",
            None,
            "swap",
            ("gameplay.damage", "gameplay.useTime"),
            "wrong item stat output",
            id="equal-item-stat-outputs",
        ),
        pytest.param(
            "configure_tool",
            {"pickPower": 20, "axePowerTooltipPercent": 100},
            "swap",
            ("gameplay.pickPower", "gameplay.axePower"),
            "wrong capability output",
            id="equal-tool-outputs",
        ),
        pytest.param(
            "configure_tool",
            {"pickPower": 20, "axePowerTooltipPercent": 125},
            "technical-swap",
            ("gameplay.pickPower", "gameplay.axePower"),
            "wrong capability output",
            id="unequal-tool-status-bypass",
        ),
        pytest.param(
            "apply_vanilla_buff_on_use",
            {"buffId": 20, "durationTicks": 20},
            "swap",
            ("gameplay.extraBuffs[0].buffCode", "gameplay.extraBuffs[0].buffTime"),
            "wrong capability output",
            id="equal-buff-outputs",
        ),
        pytest.param(
            "configure_accessory",
            {"defensePoints": 1},
            "class-swap",
            ("accessory.meleeDamage", "accessory.rangedDamage"),
            "wrong equipment output",
            id="equal-equipment-class-outputs",
        ),
    ],
)
def test_receipt_identity_and_complete_projection(fn, params, mutation, paths, reason):
    source = build_capability_witness(fn)
    if params:
        _call(source, fn)["params"].update(params)
    if mutation == "class-swap":
        _call(source, fn)["params"] = {"defensePoints": 1}
        source["runtimeProgram"]["calls"].extend(
            [
                {
                    "id": dc + "_bonus",
                    "fn": "add_equipment_damage_bonus",
                    "params": {"phase": "equipped", "damageClass": dc, "bonusPercent": 15},
                }
                for dc in ("melee", "ranged")
            ]
        )
    wire = compile_runtime_program(source)
    rows = deepcopy(wire["runtimeContract"]["finalWireReceipts"])
    selected = _receipt(rows, paths[0])
    if mutation == "source":
        selected["authoredPath"] = selected["authoredPath"].rsplit(".", 1)[0] + "." + paths[1]
    elif mutation == "value":
        selected["value"] = paths[1]
    elif mutation == "drop":
        rows.remove(selected)
    elif mutation == "wire":
        ns, field = paths[0].split(".")
        wire[ns][field] = paths[1]
    else:
        other = _receipt(rows, paths[1])
        if mutation != "technical-swap":
            assert selected["value"] == other["value"]
        if mutation == "swap" and fn == "configure_item_stats":
            assert selected["value"] == 20
        selected["finalPath"], other["finalPath"] = other["finalPath"], selected["finalPath"]
        if mutation == "technical-swap":
            selected["value"], other["value"] = other["value"], selected["value"]
            selected["status"] = other["status"] = "technical_projection"
    report = audit_compiler_receipts(rows, authored_document=source, final_document=wire)
    assert not report["ok"] and any(reason in v["reason"] for v in report["violations"]), report
    if mutation in {"swap", "technical-swap", "wire"}:
        wire["runtimeContract"]["finalWireReceipts"] = rows
        report = validate_runtime_wire(wire)
        assert not report["ok"]
        if mutation == "wire":
            assert any(e["code"] == "undeclared_technical_lowering" for e in report["errors"])


@pytest.mark.parametrize(
    "receipt,reason",
    [
        pytest.param(
            {
                "callId": "stats",
                "fn": "configure_item_stats",
                "status": "delivered",
                "authoredPath": "runtimeProgram.calls[0].params.useTime",
                "finalPath": "gameplay.useTime",
                "value": 24,
            },
            "compiler receipt used an undeclared authored parameter",
            id="undeclared-param",
        ),
        pytest.param(
            {
                "callId": "item_stats",
                "fn": "configure_item_stats",
                "status": "technical_projection",
                "authoredPath": "$.runtimeProgram.calls[0].params.damage",
                "finalPath": "runtimeProgram.entities[0].movement.code",
                "value": 7,
            },
            None,
            id="undeclared-technical-path",
        ),
    ],
)
def test_only_declared_authored_to_wire_paths_are_auditable(receipt, reason):
    wire = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"] is True
    report = audit_compiler_receipts([receipt] if reason else wire["runtimeContract"]["finalWireReceipts"] + [receipt])
    assert not report["ok"] and report["violations"]
    if reason:
        assert report["violations"][0]["reason"] == reason


@pytest.mark.parametrize(
    "fn,params,bonus,expected",
    [
        pytest.param(
            "configure_item_stats",
            None,
            None,
            {"gameplay.useTime": 24, "runtimeProgram.itemUse.channel": False},
            id="item-stat-renaming-and-channel",
        ),
        pytest.param(
            "configure_accessory",
            {
                "defensePoints": 4,
                "genericCritChancePercentagePoints": 3,
                "maxRunSpeedBonusPxPerTick": 1.5,
                "fallDamageImmune": True,
                "ammoSaveChancePercent": 25,
            },
            None,
            {
                "accessory.defense": 4,
                "accessory.genericCrit": 3,
                "accessory.maxRunSpeed": 1.5,
                "accessory.fallDamageImmune": True,
                "accessory.ammoSaveChance": 0.25,
            },
            id="accessory-exact-tml-fields",
        ),
        pytest.param(
            "configure_armor",
            {
                "slot": "head",
                "setKey": "tested_set",
                "defensePoints": 5,
                "setBonuses": {"manaCostReductionPercentagePoints": 10, "minionSlotsBonus": 2},
            },
            None,
            {"armor.defense": 5, "armor.setBonusManaCostReduction": 0.10, "armor.setBonusMinionSlots": 2},
            id="armor-exact-tml-fields",
        ),
        pytest.param(
            "configure_accessory",
            {"defensePoints": 4},
            ("equipped", "melee"),
            {"accessory.meleeDamage": 0.15},
            id="equipped-accessory-class-bonus",
        ),
        pytest.param(
            "configure_armor",
            {"slot": "head", "setKey": "coral_set", "defensePoints": 4},
            ("equipped", "summon"),
            {"armor.summonDamage": 0.15},
            id="equipped-armor-class-bonus",
        ),
        pytest.param(
            "configure_armor",
            {"slot": "head", "setKey": "coral_set", "defensePoints": 4},
            ("matching_armor_set", "magic"),
            {"armor.setBonusMagicDamage": 0.15},
            id="matching-set-class-bonus",
        ),
        pytest.param("configure_accessory", {}, ("equipped", "melee"), {"accessory.meleeDamage": 0.15}, id="class-bonus-only-accessory"),
    ],
)
def test_item_and_equipment_projection_has_exact_fields_and_param_receipts(fn, params, bonus, expected):
    source = build_runtime_fixture("workbench_blade") if fn == "configure_item_stats" else build_capability_witness(fn)
    call = _call(source, fn)
    if params is not None:
        call["params"] = params
    if bonus:
        source["runtimeProgram"]["calls"].append(
            {
                "id": "class_bonus",
                "fn": "add_equipment_damage_bonus",
                "params": {"phase": bonus[0], "damageClass": bonus[1], "bonusPercent": 15},
            }
        )
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for path, value in expected.items():
        actual = wire
        for part in path.split("."):
            actual = actual[part]
        assert actual == pytest.approx(value) if isinstance(value, float) else actual == value
        if bonus:
            assert any(r.get("callId") == "class_bonus" and r.get("finalPath") == path and r["value"] == pytest.approx(value) for r in rows)
    for param in params or {}:
        if param not in {"slot", "setKey"}:
            leaves = [f"{param}.{key}" for key in params[param]] if isinstance(params[param], dict) else [param]
            for leaf in leaves:
                assert any(r.get("callId") == call["id"] and r.get("authoredPath", "").endswith(".params." + leaf) for r in rows)
    if fn == "configure_item_stats":
        index = source["runtimeProgram"]["calls"].index(call)
        row = _receipt(rows, "gameplay.useTime")
        assert row["authoredPath"] == f"runtimeProgram.calls[{index}].params.useTimeTicks"
        assert row["value"] == call["params"]["useTimeTicks"]
        assert wire["runtimeProgram"]["itemUse"]["channel"] is False and "channelUse" not in wire["gameplay"]


@pytest.mark.parametrize(
    "fn,param,value,accepted,path,expected",
    [
        pytest.param("add_equipment_damage_bonus", "damageClass", dc, True, "accessory." + dc + "Damage", 0.15, id="damage-class-" + dc)
        for dc in CAPABILITY_REGISTRY["add_equipment_damage_bonus"].params["damageClass"].enum
    ]
    + [
        pytest.param("add_equipment_damage_bonus", "damageClass", dc, False, None, None, id="unimplemented-class-" + dc)
        for dc in ("melee_no_speed", "ExampleMod/CustomDamage", "Terraria/ThornWhip")
    ]
    + [
        pytest.param(fn, "damageClass", dc, accepted, None, None, id=fn + "-" + dc)
        for fn in ("configure_item_stats", "set_projectile_damage")
        for dc, accepted in (("Terraria/ThornWhip", False), ("ExampleMod/CustomDamage", True))
    ]
    + [
        pytest.param(
            "configure_accessory", "fallDamageImmune", True, True, "accessory.fallDamageImmune", True, id="boolean-only-accessory"
        ),
        pytest.param(
            "apply_generated_buff_on_use", "oreSenseEnabled", True, True, "gameplay.generatedBuff.oreSenseRadiusTiles", 1, id="spelunker-on"
        ),
        pytest.param(
            "apply_generated_buff_on_use",
            "oreSenseEnabled",
            False,
            True,
            "gameplay.generatedBuff.oreSenseRadiusTiles",
            0,
            id="spelunker-off",
        ),
    ],
)
def test_author_selector_and_boolean_projection(fn, param, value, accepted, path, expected):
    source = (
        build_runtime_fixture("workbench_blade")
        if fn in {"configure_item_stats", "set_projectile_damage"}
        else build_capability_witness(fn)
    )
    call = _call(source, fn)
    if fn == "configure_accessory":
        call["params"] = {}
    call["params"][param] = value
    assert validate_runtime_program(source)["ok"] is accepted
    if accepted:
        wire = compile_runtime_program(source)
        assert validate_runtime_wire(wire)["ok"]
        if path:
            actual = wire
            for part in path.split("."):
                actual = actual[part]
            assert actual == pytest.approx(expected) if isinstance(expected, float) else actual == expected
        if param == "oreSenseEnabled":
            call["params"]["oreSenseRadiusTiles"] = 30
            assert not validate_runtime_program(source)["ok"]


@pytest.mark.parametrize(
    "fn,old",
    [
        pytest.param(fn, old, id=fn + "-" + old)
        for fn, old in (
            ("configure_accessory", "genericDamage"),
            ("configure_accessory", "meleeDamage"),
            ("configure_armor", "setBonusGenericDamage"),
            ("configure_accessory", "meleeDamageBonusPercent"),
            ("configure_armor", "meleeDamageBonusPercent"),
        )
    ],
)
def test_equipment_alias_is_not_a_second_author_surface(fn, old):
    for dc in ("generic", "melee", "ranged", "magic", "summon"):
        assert dc + "DamageBonusPercent" not in CAPABILITY_REGISTRY[fn].params
        assert "setBonus" + dc.title() + "DamageBonusPercent" not in CAPABILITY_REGISTRY[fn].params
    source = build_capability_witness(fn)
    call = _call(source, fn)
    call["params"] = {"slot": "head", "setKey": "checked"} if fn == "configure_armor" else {}
    call["params"][old] = 0.15 if old in {"genericDamage", "meleeDamage", "setBonusGenericDamage"} else 15
    assert not validate_runtime_program(source)["ok"]


@pytest.mark.parametrize(
    "fn",
    [
        fn
        for fn, cap in CAPABILITY_REGISTRY.items()
        if any(r.kind == "binding_action_present" and "apply_item_effects" in r.any_of for r in cap.requirements)
    ],
)
def test_item_effects_require_their_executable_binding(fn):
    source = build_capability_witness(fn)
    binding = source["runtimeProgram"]["bindings"][0]
    assert binding["action"]["kind"] == "apply_item_effects"
    assert validate_runtime_program(source)["ok"]
    binding["action"]["kind"] = "use_item_body"
    report = validate_runtime_program(source)
    assert not report["ok"] and any(e["code"] == "missing_binding_dependency" for e in report["errors"])


@pytest.mark.parametrize(
    "fn",
    [
        fn
        for fn, cap in CAPABILITY_REGISTRY.items()
        if cap.category == "event" and cap.prompt_visible and cap.decision == "expose"
        and "delayTicks" in cap.params and fn != "spawn_entity_on_event"
    ],
)
def test_each_declared_event_delay_reaches_real_wire(fn):
    source = build_capability_witness(fn)
    call = _call(source, fn)
    call["params"]["delayTicks"] = 30
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    actions = [a for e in wire["runtimeProgram"]["entities"] for a in e.get("events", [])]
    action = next(a for a in actions if a["id"] == call["id"])
    assert action["delayTicks"] == 30
    if fn == "move_owner_on_event":
        assert "mode" not in CAPABILITY_REGISTRY[fn].params
        assert action["mode"] == "blink_to_event_position"
        call["params"]["mode"] = "blink_to_entity"
        assert not validate_runtime_program(source)["ok"]


@pytest.mark.parametrize(
    "fn,mutation,code",
    [
        pytest.param(
            "add_equipment_damage_bonus", "duplicate", "duplicate_equipment_damage_selector", id="duplicate-selector-not-addition"
        ),
        pytest.param("add_equipment_damage_bonus", "mixed-equipment", "equipment_scope_conflict", id="one-equipment-kind"),
        pytest.param("configure_armor", "missing-set-key", "missing_set_key", id="matching-set-key"),
        pytest.param("configure_armor", "body-set-bonus", "set_bonus_head_only", id="matching-set-head-only"),
        pytest.param("configure_accessory", "missing-light-color", "missing_light_color", id="accessory-light-color"),
        pytest.param("configure_armor", "missing-light-color", "missing_light_color", id="armor-light-color"),
    ],
)
def test_equipment_dependencies_refuse_invalid_composition_before_projection(fn, mutation, code):
    doc = build_capability_witness(fn)
    call = _call(doc, fn)
    if mutation == "duplicate":
        extra = deepcopy(call)
        extra["id"] = "same_class_again"
        doc["runtimeProgram"]["calls"].append(extra)
    elif mutation == "mixed-equipment":
        doc["runtimeProgram"]["calls"].append(
            {"id": "also_armor", "fn": "configure_armor", "params": {"slot": "head", "setKey": "", "defensePoints": 2}}
        )
    elif mutation in {"missing-set-key", "body-set-bonus"}:
        call["params"] = {
            "slot": "body" if mutation == "body-set-bonus" else "head",
            "setKey": "matching_set" if mutation == "body-set-bonus" else "",
            "defensePoints": 2,
        }
        doc["runtimeProgram"]["calls"].append(
            {
                "id": "set_damage",
                "fn": "add_equipment_damage_bonus",
                "params": {
                    "phase": "matching_armor_set",
                    "damageClass": "generic" if mutation == "body-set-bonus" else "melee",
                    "bonusPercent": 10 if mutation == "body-set-bonus" else 15,
                },
            }
        )
    else:
        call["params"] = {"lightStrength": 0.35}
        if fn == "configure_armor":
            call["params"].update(slot="head", setKey="")
    report = validate_runtime_program(doc)
    assert not report["ok"] and any(e["code"] == code for e in report["errors"])
    if mutation == "missing-set-key":
        call["params"]["setKey"] = "matching_set"
    elif mutation == "body-set-bonus":
        call["params"]["slot"] = "head"
    elif mutation == "missing-light-color":
        call["params"]["lightColor"] = "yellow"
    else:
        return
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    if mutation == "missing-light-color":
        assert wire["accessory" if fn == "configure_accessory" else "armor"]["lightColorName"] == "yellow"


# Event blink mode is checked in the move_owner_on_event delay case.


@pytest.mark.parametrize(
    "fn,param,source_value,forged",
    [
        ("configure_item_stats", "valueCopper", 1, True),
        ("configure_item_stats", "valueCopper", 1, 1.0),
        ("configure_accessory", "defensePoints", 1, True),
        ("configure_tool", "axePowerTooltipPercent", 5, True),
        ("configure_accessory", "moveSpeedBonusPercent", 100, True),
        ("configure_spawn", "velocity.constantSpeedPxPerUpdate", -0.0, 0.0),
    ],
)
def test_source_receipt_projection_rejects_equal_numeric_representation_forgery(fn, param, source_value, forged):
    source = build_capability_witness(fn)
    call = _call(source, fn)
    slot = call["params"]
    for part in param.split(".")[:-1]:
        slot = slot[part]
    slot[param.rsplit(".", 1)[-1]] = source_value
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    selected = next(r for r in rows if r.get("callId") == call["id"] and r.get("authoredPath", "").endswith(".params." + param))
    assert selected["value"] == forged  # Python equality is exactly the broken criterion.
    selected["value"] = forged
    segments = [int(v[1:-1]) if v.startswith("[") else v for v in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", selected["finalPath"])]
    slot: Any = wire
    for key in segments[:-1]:
        slot = slot[key]
    slot[segments[-1]] = forged
    frozen = deepcopy((source, wire))
    report = audit_compiler_receipts(rows, authored_document=source, final_document=wire)
    assert not report["ok"], report
    expected_reason = "exact authored variant projection" if "." in param else "not the declared projection"
    assert any(expected_reason in v["reason"] for v in report["violations"]), report
    assert (source, wire) == frozen
    # Coherently forged wire/receipt values do not authenticate their source.
    standalone = audit_compiler_receipts(rows, final_document=wire)
    assert standalone["authoredSourceChecked"] is False


def test_source_receipt_projection_rejects_bool_for_identity_integer():
    source = build_capability_witness("configure_spawn")
    call = _call(source, "configure_spawn")
    call["params"]["count"] = 1
    wire = compile_runtime_program(source)
    call["params"]["count"] = True
    assert not validate_runtime_program(source)["ok"]  # Separate audit-only bug, not compiler admission.
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)
    assert not report["ok"], report
    assert any("compiler receipt value is not the declared projection of its authored parameter" == v["reason"]
               for v in report["violations"]), report


@pytest.mark.parametrize(
    "fixture,primary,lowerer",
    [
        ("workbench_blade", "nail", PRIMARY_OWNER_LOWERER_ID),
        ("held_and_deployed", "deployed_lantern", PRIMARY_BINDING_ROLE_LOWERER_ID),
    ],
)
def test_global_receipts_reject_valid_changed_primary_source(fixture, primary, lowerer):
    source = build_runtime_fixture(fixture)
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    frozen_wire = deepcopy(wire)
    source["runtimeProgram"]["primaryEntityId"] = primary
    assert validate_runtime_program(source)["ok"]
    frozen_source = deepcopy(source)
    report = audit_compiler_receipts(
        wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire,
    )
    assert not report["ok"], report
    assert any(v.get("lowererId") == lowerer for v in report["violations"]), report
    assert source == frozen_source and wire == frozen_wire


@pytest.mark.parametrize("lowerer", [PRIMARY_OWNER_LOWERER_ID, PRIMARY_BINDING_ROLE_LOWERER_ID])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "duplicate-input", "status", "split-index", "missing-source"])
@pytest.mark.parametrize("with_source", [False, True])
def test_primary_global_receipts_require_exact_inputs_and_unique_coverage(lowerer, mutation, with_source):
    source = build_runtime_fixture("held_and_deployed")
    wire = compile_runtime_program(source)
    rows = deepcopy(wire["runtimeContract"]["finalWireReceipts"])
    selected = next(r for r in rows if r.get("lowererId") == lowerer)
    if mutation == "drop":
        rows.remove(selected)
    elif mutation == "duplicate":
        rows.append(deepcopy(selected))
    elif mutation == "duplicate-input":
        selected["authoredPaths"].append(selected["authoredPaths"][-1])
    elif mutation == "status":
        selected["status"] = "delivered"
    elif mutation == "split-index":
        selected["authoredPaths"][-1] = selected["authoredPaths"][-1].replace("[1]", "[2]")
        if lowerer == PRIMARY_BINDING_ROLE_LOWERER_ID:
            # Binding 0 was authored before binding 1 but is sorted after it.
            selected["finalPath"] = "runtimeProgram.bindings[1].role"
            selected["value"] = wire["runtimeProgram"]["bindings"][1]["role"]
    else:
        selected["authoredPaths"] = [p.replace("[1]", "[999]") for p in selected["authoredPaths"]]
    if not with_source and mutation == "missing-source":
        # A wire-only audit cannot resolve Author indices: do not invent proof.
        report = audit_compiler_receipts(rows, final_document=wire)
        assert report["ok"] and report.get("authoredSourceChecked") is False
    else:
        report = audit_compiler_receipts(rows, authored_document=source if with_source else None, final_document=wire)
        assert not report["ok"], report
        assert any(v.get("lowererId") == lowerer for v in report["violations"]), report


@pytest.mark.parametrize("mutation", ["source", "same-valued-source", "value-and-wire", "drop", "duplicate", "duplicate-input", "status"])
@pytest.mark.parametrize("with_source", [False, True])
def test_visual_global_receipts_bind_kind_identity_and_complete_outputs(mutation, with_source):
    source = build_runtime_fixture("held_and_deployed")
    if mutation == "same-valued-source":
        # Another valid owner-attached entity shares the role, but not identity.
        program = source["runtimeProgram"]
        program["entities"].append({"id": "other_held", "kind": "owner_attached_projectile"})
        for call in list(program["calls"]):
            if call.get("target") == "held_lantern_pike":
                extra = deepcopy(call)
                extra.update(id="other_" + call["id"], target="other_held")
                program["calls"].append(extra)
        program["calls"].append({
            "id": "spawn_other", "fn": "spawn_entity_on_event", "target": "held_lantern_pike",
            "params": {"when": "on_hit", "entity": "other_held", "count": 1,
                       "spreadRadians": 0, "damageMultiplier": 1, "delayTicks": 0, "damageBasis": "authored_child", "knockbackBasis": "authored_child"},
        })
        assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    rows = deepcopy(wire["runtimeContract"]["finalWireReceipts"])
    selected = _receipt(rows, "runtimeProgram.entities[1].visualRole")
    if mutation == "source":
        selected["authoredPaths"] = ["runtimeProgram.entities[2].kind"]
    elif mutation == "same-valued-source":
        other = _receipt(rows, "runtimeProgram.entities[4].visualRole")
        assert selected["value"] == other["value"]
        selected["authoredPaths"], other["authoredPaths"] = other["authoredPaths"], selected["authoredPaths"]
    elif mutation == "value-and-wire":
        selected["value"] = wire["runtimeProgram"]["entities"][1]["visualRole"] = "projectile"
    elif mutation == "drop":
        rows.remove(selected)
    elif mutation == "duplicate":
        rows.append(deepcopy(selected))
    elif mutation == "duplicate-input":
        selected["authoredPaths"] *= 2
    else:
        selected["status"] = "delivered"
    report = audit_compiler_receipts(rows, authored_document=source if with_source else None, final_document=wire)
    if not with_source and mutation in {"source", "same-valued-source"}:
        assert report["ok"] and report["authoredSourceChecked"] is False
    else:
        assert not report["ok"], report
        assert any(v.get("lowererId") == "entity_kind_to_visual_role" for v in report["violations"]), report


@pytest.mark.parametrize("lowerer", [PRIMARY_OWNER_LOWERER_ID, PRIMARY_BINDING_ROLE_LOWERER_ID])
@pytest.mark.parametrize("with_source", [False, True])
def test_primary_global_receipts_reject_coherently_forged_wire_values(lowerer, with_source):
    source = build_runtime_fixture("held_and_deployed")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    selected = next(r for r in rows if r.get("lowererId") == lowerer)
    if lowerer == PRIMARY_OWNER_LOWERER_ID:
        selected["value"] = wire["runtimeProgram"]["primaryOwner"] = "item_body"
    else:
        selected["value"] = wire["runtimeProgram"]["bindings"][0]["role"] = "primary"
    report = audit_compiler_receipts(rows, authored_document=source if with_source else None, final_document=wire)
    assert not report["ok"], report
    assert any(v.get("lowererId") == lowerer for v in report["violations"]), report


@pytest.mark.parametrize("mutation", ["swap-source-paths", "swap-wire-ids"])
def test_primary_global_receipts_reject_equal_role_cross_binding_identity(mutation):
    source = build_runtime_fixture("equipment_tool_combat")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    roles = [r for r in rows if r.get("lowererId") == PRIMARY_BINDING_ROLE_LOWERER_ID]
    assert all(r["value"] == "primary" for r in roles)
    if mutation == "swap-source-paths":
        roles[0]["authoredPaths"], roles[1]["authoredPaths"] = roles[1]["authoredPaths"], roles[0]["authoredPaths"]
    else:
        bindings = wire["runtimeProgram"]["bindings"]
        bindings[0]["id"], bindings[1]["id"] = bindings[1]["id"], bindings[0]["id"]
    report = audit_compiler_receipts(rows, authored_document=source, final_document=wire)
    assert not report["ok"]
    assert any("authored identity" in v["reason"] for v in report["violations"]), report
    # The unchanged role values alone cannot expose this forged ownership.
    standalone = audit_compiler_receipts(rows, final_document=wire)
    # Direct identity receipts now expose changed final IDs even wire-only;
    # swapping only source paths still cannot authenticate source indices.
    assert standalone["ok"] is (mutation == "swap-source-paths")
    assert standalone["authoredSourceChecked"] is False


@pytest.mark.parametrize("fixture", NON_ARCHETYPAL_FIXTURES)
def test_global_receipts_accept_real_compiler_fixtures_without_mutation(fixture):
    source = build_runtime_fixture(fixture)
    source["runtimeProgram"]["entities"].reverse()
    source["runtimeProgram"]["bindings"].reverse()
    frozen_source = deepcopy(source)
    wire = compile_runtime_program(source)
    frozen_wire = deepcopy(wire)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    assert audit_compiler_receipts(rows, authored_document=source)["ok"]
    report = audit_compiler_receipts(rows, final_document=wire)
    assert report["ok"] and report.get("authoredSourceChecked") is False
    assert validate_runtime_wire(wire)["ok"]
    assert source == frozen_source and wire == frozen_wire
