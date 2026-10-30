from copy import deepcopy
import pytest
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def combat_document(activation='apply_generated_buff_on_use'):
    doc = build_capability_witness(activation)
    buff = next(c for c in doc['runtimeProgram']['calls'] if c['fn'] == 'apply_generated_buff_on_use')
    buff['params'].update(lightStrength=0, miningSpeedMultiplier=1, treasureSense=False,
        moveSpeedBonusPercent=0, jumpSpeedBonusBlocksPerSecond=0, manaRegenBonusPoints=0, lifeRegen=0)
    buff['params']['combat'] = dict(defensePoints=10, attackSpeedPercent=15, critChancePoints=4, damagePercent=25, damageClass='melee')
    return doc


@pytest.mark.parametrize('activation', ['apply_generated_buff_on_use', 'refresh_generated_effect_group_while_held', 'apply_generated_buff_on_event'])
def test_combat_only_buff_reaches_default_named_and_reactive_groups(activation):
    doc = combat_document(activation)
    assert validate_runtime_program(doc)['ok'], validate_runtime_program(doc)
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert doc == before
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    wire.pop('runtimeContract')
    assert validate_runtime_wire(wire)['ok'], validate_runtime_wire(wire)
    buff = wire['gameplay'].get('generatedBuff') or wire['runtimeProgram']['effectGroups'][0]['generatedBuff']
    assert buff['combat']['defensePoints'] == 10
    assert buff['combat']['damageClass'] == 'melee'
    buff['combat']['damagePercent'] = 201
    assert not validate_runtime_wire(wire)['ok']


def test_empty_combat_is_not_an_effect_and_invalid_fields_are_not_defaulted():
    doc = combat_document(); params = next(c['params'] for c in doc['runtimeProgram']['calls'] if c['fn'] == 'apply_generated_buff_on_use')
    for name in ['defensePoints', 'attackSpeedPercent', 'critChancePoints', 'damagePercent']:
        params['combat'][name] = 0
    assert not validate_runtime_program(doc)['ok']
    params['combat']['defensePoints'] = 10
    assert validate_runtime_program(doc)['ok']
    del params['combat']['damageClass']
    assert not validate_runtime_program(doc)['ok']


def test_oversized_combat_integer_is_rejected_without_crashing_validation():
    doc = combat_document()
    params = next(c['params'] for c in doc['runtimeProgram']['calls'] if c['fn'] == 'apply_generated_buff_on_use')
    params['combat']['defensePoints'] = 10 ** 1000
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report['ok']
    assert report['errors']
    assert doc == before
