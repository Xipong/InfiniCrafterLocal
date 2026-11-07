"""Authored traversal uses the same mechanics in equipment and generated buffs."""
from copy import deepcopy
import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from tests.generator.equipment.test_player_effect_primitives import source

CASES = [
    ('autoJump', True, 'autoJump', True),
    ('gravityControl', True, 'gravityControl', True),
    ('gravityMultiplier', .4, 'gravityMultiplier', .4),
    ('maxFallSpeedBlocksPerSecond', 15, 'maxFallSpeedPxPerTick', 4),
    ('safeFallDistanceBlocks', 9, 'safeFallDistanceBlocks', 9),
    ('waterBreathing', True, 'waterBreathing', True),
    ('swimJump', True, 'swimJump', True),
    ('waterBuoyancy', True, 'waterBuoyancy', True),
    ('wallSlideAndJump', True, 'wallSlideAndJump', True),
    ('wallCling', True, 'wallCling', True),
    ('breathCapacityBonus', 60, 'breathCapacityBonus', 60),
]

@pytest.mark.parametrize('fn', ['accessory', 'armor', 'generated_buff_on_use'])
@pytest.mark.parametrize('name,value,wire_name,wire_value', CASES)
def test_traversal_mechanic_delivers_exact_typed_wire(fn, name, value, wire_name, wire_value):
    doc, _ = source(fn, {name:value})
    assert validate_runtime_program(doc)['ok']
    wire = compile_runtime_program(doc)
    report = validate_runtime_wire(wire)
    assert report['ok'], report
    target = wire['gameplay']['generatedBuff'] if fn=='generated_buff_on_use' else wire['armor' if fn=='armor' else 'accessory']
    assert target['playerEffect'] == {'condition':'always', wire_name:wire_value}
    assert audit_compiler_receipts(wire['runtimeContract']['finalWireReceipts'], authored_document=doc, final_document=wire)['ok']
    target['playerEffect'][wire_name]=None
    assert not validate_runtime_wire(wire)['ok']

@pytest.mark.parametrize('fn', ['accessory', 'armor', 'generated_buff_on_use'])
def test_air_jump_keeps_authored_movement_and_exact_neutral_receipts(fn):
    effect={'airJump':{'count':3,'launchSpeedBlocksPerSecond':30,'holdDurationSeconds':.25}}
    doc, call = source(fn,effect)
    before=deepcopy(doc)
    wire=compile_runtime_program(doc)
    target=wire['gameplay']['generatedBuff'] if fn=='generated_buff_on_use' else wire['armor' if fn=='armor' else 'accessory']
    assert target['playerEffect']['airJump']=={'count':3,'launchSpeedPxPerTick':8,'holdDurationTicks':15,'horizontalAccelerationMultiplier':1,'horizontalSpeedMultiplier':1}
    assert validate_runtime_wire(wire)['ok']
    receipts=wire['runtimeContract']['finalWireReceipts']
    for field in ('horizontalAccelerationMultiplier','horizontalSpeedMultiplier'):
        assert any(r.get('callId')==call['id'] and r.get('status')=='declared_neutral_omission' and r['finalPath'].endswith('.airJump.'+field) and r['value']==1 for r in receipts)
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)['ok']
    assert doc==before
    del target['playerEffect']['airJump']['count']
    assert not validate_runtime_wire(wire)['ok']

@pytest.mark.parametrize('field', ['autoPaint','rulerGrid','buildRangeTiles','tileSpeedBonusPercent','wallSpeedBonusPercent','jumpCloud','jumpBlizzard','jumpSandstorm','jumpFart','jumpTsunami','frogJump','divingHelm'])
def test_building_and_named_jump_presets_are_absent(field):
    doc,call=source('accessory',{'autoJump':True})
    call['params'][field]=True
    assert not validate_runtime_program(doc)['ok']
    del call['params'][field]
    wire=compile_runtime_program(doc)
    wire['accessory'][field]=True
    assert not validate_runtime_wire(wire)['ok']

@pytest.mark.parametrize('effect', [{'gravityMultiplier':1}, {'condition':'stationary','gravityMultiplier':1,'autoJump':False}])
def test_neutral_traversal_component_does_not_create_an_effect(effect):
    doc, _ = source('accessory', effect)
    report=validate_runtime_program(doc)
    assert not report['ok']
    assert any(row['code']=='inert_component' for row in report['errors'])


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_air_jump_exact_leaf_repair_keeps_motion_and_optional_absence_frozen(monkeypatch, mode):
    from prompt_packet_helpers import request_dossier
    from repair_test_helpers import repair_with_response

    effect = {"airJump": {"count": 3, "launchSpeedBlocksPerSecond": 30, "holdDurationSeconds": .25}}
    doc, call = source("accessory", effect)
    expected = deepcopy(doc)
    call["params"]["playerEffect"]["airJump"]["count"] = None
    candidate = deepcopy(call)
    candidate["params"]["playerEffect"]["airJump"].update(
        count=3, launchSpeedBlocksPerSecond=60, horizontalSpeedMultiplier=2,
    )
    repaired, request = repair_with_response(monkeypatch, doc, {
        "note": "repair count only", "callsUpsert": [candidate],
    }, mode)
    assert request_dossier(request)["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": call["id"], "paths": ["params.playerEffect.airJump.count"]},
    ]
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    final = compile_runtime_program(repaired)
    assert validate_runtime_wire(final)["ok"]
    assert final["accessory"]["playerEffect"]["airJump"] == {
        "count": 3, "launchSpeedPxPerTick": 8, "holdDurationTicks": 15,
        "horizontalAccelerationMultiplier": 1, "horizontalSpeedMultiplier": 1,
    }
    assert audit_compiler_receipts(final["runtimeContract"]["finalWireReceipts"],
                                   authored_document=repaired, final_document=final)["ok"]


@pytest.mark.parametrize("speed,hold,wire_speed,wire_ticks", [
    (.375, 1 / 60, .1, 1), (120, 2, 32, 120), (30, .025, 8, 2),
])
def test_air_jump_world_units_keep_native_bounds_and_tick_rounding(speed, hold, wire_speed, wire_ticks):
    doc, _ = source("accessory", {"airJump": {
        "count": 1, "launchSpeedBlocksPerSecond": speed, "holdDurationSeconds": hold,
    }})
    final = compile_runtime_program(doc)
    jump = final["accessory"]["playerEffect"]["airJump"]
    assert jump["launchSpeedPxPerTick"] == wire_speed and jump["holdDurationTicks"] == wire_ticks
    assert validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("field,value", [
    ("launchSpeedBlocksPerSecond", .374), ("launchSpeedBlocksPerSecond", 121),
    ("holdDurationSeconds", 0), ("holdDurationSeconds", 2.1),
    ("horizontalAccelerationMultiplier", None), ("horizontalSpeedMultiplier", True),
])
def test_air_jump_invalid_present_fields_are_not_neutral_omissions(field, value):
    jump = {"count": 1, "launchSpeedBlocksPerSecond": 30, "holdDurationSeconds": .25, field: value}
    doc, _ = source("accessory", {"airJump": jump})
    assert not validate_runtime_program(doc)["ok"]
