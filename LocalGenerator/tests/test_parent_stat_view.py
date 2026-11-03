"""Source unit presentation keeps native guards and never activates a bonus."""
import copy
import json
from pathlib import Path
import re

import pytest

from infini_local.pipelines.context.stats import parent_stat_context
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from prompt_packet_helpers import request_dossier, expand_native_source_references

ROOT = Path(__file__).resolve().parents[2]


def equipment(item_id):
    text = (ROOT / 'ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeEquipmentFactsCatalog.g.cs').read_text()
    records = [row for raw in re.findall(r'"""(.*?)"""', text, re.S) for row in json.loads(raw)]
    row = next(row for row in records if row.get('itemId') == item_id)
    return {'source': 'verified_native_equipment_source_branches',
            'scope': 'source contributions; full sets conditional; other effects unknown',
            'equippedContributions': row}


def regeneration():
    text = (ROOT / 'ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeBuffEffectCatalog.g.cs').read_text()
    raw = re.search(r'\["player:2"\] = """(.*?)"""', text, re.S).group(1)
    return json.loads(raw) | {'source': 'certified_native_buff_operation_fragments'}


def test_exact_equipment_records_use_hp_per_second_and_do_not_invert_mining_time():
    for item_id, expected_stat, expected_value, expected_unit in [
        (2763, 'lifeRegen', 1, 'HP/s'),
        (410, 'miningUseTimeMultiplier', -0.1, 'additive_multiplier'),
    ]:
        source = {'item': {'nativeEquipmentReference': equipment(item_id)}}
        before = copy.deepcopy(source)
        result = parent_stat_context(source)
        original = source['item']['nativeEquipmentReference']['equippedContributions']
        projected = result['item']['nativeEquipmentReference']['equippedContributions']
        effect = next(row for row in projected['branches'][0]['effects'] if row['stat'] == expected_stat)
        assert effect['value'] == expected_value and effect['units'] == expected_unit
        assert effect['operation'] == 'add' and effect['receiver'] == 'player'
        assert 'nativeMember' not in effect
        assert projected['condition'] == original['condition']
        assert projected['branches'][0]['guardIlOffset'] == original['branches'][0]['guardIlOffset']
        assert source == before
        assert parent_stat_context(result) == result


def test_buff_hp_rate_retains_enclosing_unproved_guards_and_receiver():
    source = {'item': {'lifeRegen': 4, 'nativeBuffEffectReference': regeneration()}}
    before = copy.deepcopy(source)
    result = parent_stat_context(source)
    buff = result['item']['nativeBuffEffectReference']
    original = source['item']['nativeBuffEffectReference']
    operation = buff['fragments'][0]['operations'][0]
    assert {k: operation[k] for k in ['stat', 'value', 'units', 'receiver', 'operation']} == {
        'stat': 'lifeRegen', 'value': 2, 'units': 'HP/s', 'receiver': 'player', 'operation': 'add'}
    assert buff['fragments'][0]['condition'] == original['fragments'][0]['condition']
    assert buff['fragments'][0]['unsupported'] == original['fragments'][0]['unsupported']
    assert buff['unsupported'] == original['unsupported'] and buff['scope'] == original['scope']
    assert result['item']['lifeRegen'] == {'value': 2, 'units': 'HP/s'}
    assert source == before


@pytest.mark.parametrize('mutation', [
    {'value': True}, {'value': float('inf')}, {'nativeMember': 'Other.Player.lifeRegen'},
    {'units': 'unknown_units'}, {'futureCondition': 'must_not_discard'},
    {'operation': 'operator_call_and_assign', 'nativeOperator': 'Whatever.op_Addition'},
])
def test_unknown_effects_stay_literal_not_silently_interpreted(mutation):
    reference = regeneration()
    reference['fragments'][0]['operations'][0].update(mutation)
    source = {'item': {'nativeBuffEffectReference': reference}}
    assert parent_stat_context(source) == source


def test_wrong_receiver_modded_source_and_generated_parent_are_not_native_projection():
    for mutation in [{'receiver': 'npc'}, {'source': 'modded_source'}, {'source': {'future': True}}]:
        reference = regeneration() | mutation
        source = {'item': {'nativeBuffEffectReference': reference}}
        assert parent_stat_context(source) == source
    source = {'generatedParent': {'runtimeProgram': {}}, 'item': {'lifeRegen': 4}}
    assert parent_stat_context(source) == source


def test_multiplier_operation_is_factor_not_a_bonus_percentage():
    source = {'item': {'nativeBuffEffectReference': regeneration()}}
    row = source['item']['nativeBuffEffectReference']['fragments'][0]['operations'][0]
    row.update(nativeMember='Terraria.Player.moveSpeed', operation='multiply', value=0.5,
               units='dimensionless_factor', storageType='float32')
    projected = parent_stat_context(source)['item']['nativeBuffEffectReference']['fragments'][0]['operations'][0]
    assert projected['operation'] == 'multiply' and projected['value'] == 0.5
    assert projected['stat'] == 'movementSpeed' and projected['units'] == 'dimensionless_factor'


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_actual_author_request_uses_one_source_vocabulary_without_mutating_parent(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    a = {'name': 'Source sample', 'lifeRegen': 4, 'nativeEquipmentReference': equipment(410)}
    b = {'nativeBuffEffectReference': regeneration()}
    before = copy.deepcopy((a, b))
    request, _, _ = build_initial_author_request(a, b, 'source-stat-view', model_name='offline')
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    assert dossier['parentBriefs']['A']['properties']['lifeRegen'] == {'value': 2, 'units': 'HP/s'}
    raw_a = dossier['parents']['A']['packet']['raw']
    effect = raw_a['item']['nativeEquipmentReference']['equippedContributions']['branches'][0]['effects'][0]
    assert effect['stat'] == 'miningUseTimeMultiplier' and effect['value'] == -0.1
    buff = dossier['parents']['B']['packet']['raw']['item']['nativeBuffEffectReference']
    assert buff['fragments'][0]['operations'][0]['value'] == 2
    assert buff['fragments'][0]['condition']['nativeControlFlowMustReachTest'] == 469
    assert (a, b) == before
    assert raw_parent_card_for_llm(a)['raw']['item']['lifeRegen'] == 4


def test_npc_counter_rate_requires_producer_unit_evidence_and_keeps_cadence_condition():
    text = (ROOT / 'ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeBuffEffectCatalog.g.cs').read_text()
    buff = json.loads(re.search(r'\["npc:20"\] = """(.*?)"""', text, re.S).group(1))
    buff['source'] = 'certified_native_buff_operation_fragments'
    source = {'item': {'nativeBuffEffectReference': buff}}
    original = buff['fragments'][0]['operations'][0]
    projected = parent_stat_context(source)['item']['nativeBuffEffectReference']['fragments'][0]['operations'][0]
    assert projected['stat'] == 'lifeRegen' and projected['value'] == -6
    assert projected['units'] == 'HP/s at 60 accumulator updates/s'
    assert projected['clampPositiveToZeroFirst'] is True
    assert projected['nominalRateScope'] == original['nominalRateScope']
    assert projected['unitEvidence'] == original['unitEvidence']
    for key in ['unitEvidence', 'nominalHpLossPerSecondAt60Updates']:
        without = copy.deepcopy(source)
        del without['item']['nativeBuffEffectReference']['fragments'][0]['operations'][0][key]
        assert parent_stat_context(without) == without


@pytest.mark.parametrize('mutation', [{'operation': {'future': True}}, {'storageType': ['int32']}])
def test_future_nonscalar_operation_metadata_is_literal(mutation):
    reference = regeneration()
    reference['fragments'][0]['operations'][0].update(mutation)
    source = {'item': {'nativeBuffEffectReference': reference}}
    assert parent_stat_context(source) == source


def test_environment_regen_keeps_local_scene_guard_and_scope():
    row = {'field': 'Player.lifeRegen', 'add': 1, 'condition': 'local_player_and_scene_flag',
           'units': 'native_life_regen_counter_units', 'scope': 'source addition before other effects'}
    source = {'item': {'nativeEnvironmentReference': {'source': 'certified_native_environment_reference',
                                                    'auras': [{'sceneFlag': 'HasCampfire', 'effect': row}]}}}
    result = parent_stat_context(source)['item']['nativeEnvironmentReference']['auras'][0]
    assert result['sceneFlag'] == 'HasCampfire'
    assert result['effect']['value'] == 0.5 and result['effect']['units'] == 'HP/s'
    assert result['effect']['condition'] == row['condition'] and result['effect']['scope'] == row['scope']


def test_conditional_equipment_effect_is_not_promoted_to_unconditional():
    reference = equipment(238)
    source = {'item': {'nativeEquipmentReference': reference}}
    result = parent_stat_context(source)['item']['nativeEquipmentReference']
    original = reference['equippedContributions']['branches'][0]
    projected = result['equippedContributions']['branches'][0]
    assert 'conditionalEffects' in original
    assert projected['conditionalEffects'][0]['condition'] == original['conditionalEffects'][0]['condition']
    assert projected['conditionalEffects'][0]['condition']['observed'] is False
    assert len(projected['effects']) == len(original['effects'])


def captured_stat_parents():
    capture = json.loads((Path(__file__).parent / 'fixtures/native_stat_source_capture.json').read_text())
    return capture['parents']['itemA'], capture['parents']['itemB']


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_actual_native_prepare_stat_sections_drop_only_audit_metadata_in_author(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    a, b = captured_stat_parents()
    before = copy.deepcopy((a, b))
    request, _, _ = build_initial_author_request(a, b, 'captured-stat-metadata', model_name='offline')
    packet = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    equipment = packet['parents']['A']['packet']['raw']['item']['nativeEquipmentReference']
    buff = packet['parents']['B']['packet']['raw']['item']['nativeBuffEffectReference']
    assert 'equipmentSourceCertificate' not in equipment and 'setSourceCertificate' not in equipment
    assert 'sourceCertificate' not in buff
    effects = equipment['equippedContributions']['branches'][0]['effects']
    assert effects[0]['stat'] == 'miningUseTimeMultiplier' and effects[0]['value'] == -0.1
    assert 'ilOffset' not in effects[0]
    assert equipment['equippedContributions']['branches'][0]['guardIlOffset'] == 7313
    for new, old in zip(equipment['conditionalArmorSets'], a['nativeEquipmentReference']['conditionalArmorSets']):
        assert new['condition'] == old['condition'] and new['guardIlOffset'] == old['guardIlOffset']
        assert 'ilOffset' not in new['effects'][0]
    fragment = buff['fragments'][0]
    assert fragment['condition'] == b['nativeBuffEffectReference']['fragments'][0]['condition']
    assert fragment['operations'][0]['value'] == 2 and fragment['operations'][0]['units'] == 'HP/s'
    assert 'sourceIlOffset' not in fragment['operations'][0]
    assert fragment['sourceMethod'] == 'Player.UpdateBuffs'
    assert buff['requestedDurationTicks'] == 28800
    assert (a, b) == before
    assert 'sourceCertificate' in b['nativeBuffEffectReference']
    assert b['nativeBuffEffectReference']['fragments'][0]['operations'][0]['sourceIlOffset'] == 489


@pytest.mark.parametrize('mutation', ['envelope', 'row', 'certificate', 'units'])
def test_unfamiliar_stat_source_shapes_keep_audit_metadata(mutation):
    _, parent = captured_stat_parents()
    reference = parent['nativeBuffEffectReference']
    row = reference['fragments'][0]['operations'][0]
    if mutation == 'envelope':
        reference['futureReference'] = {'sourceIlOffset': 489}
    elif mutation == 'row':
        row['futureCondition'] = {'sourceCertificateRef': 'sourceCertificate'}
    elif mutation == 'units':
        row['units'] = 'future_units'
    else:
        reference['sourceCertificate']['futureProof'] = 'retain'
    projected = parent_stat_context({'item': parent})['item']['nativeBuffEffectReference']
    assert projected['sourceCertificate'] == reference['sourceCertificate']
    assert projected['fragments'][0]['operations'][0]['sourceIlOffset'] == 489
