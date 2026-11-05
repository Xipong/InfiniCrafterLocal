"""Weapon category and source conversion evidence, never concrete ammo examples."""
from __future__ import annotations

import copy
import pytest

from infini_local.pipelines.context.parents import compact_ammo_profile
from tests.test_units_packet_preservation import _source_packets, offline_packets, _CapturedRequest


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('ammo_mode', ['weapon_uses_ammo', 'unknown_future_mode', None])
@pytest.mark.parametrize('envelope,weapon_damage', [('root', 11), ('fingerprint', 14)])
def test_weapon_context_survives_all_stages_without_ammo_examples(offline_packets, legacy, envelope, weapon_damage, ammo_mode):
    from infini_local.pipelines.vfx import prompt, stage, request
    from tests.test_low_level_three_stage_pipeline import _accepted_visual_data
    from prompt_packet_helpers import request_dossier
    captured, _ = offline_packets
    expected = {
        'mode': 'weapon_uses_ammo', 'ammoId': 40, 'ammoCategoryName': 'Arrow',
        'weaponShootFieldProjectileRaw': {'type': 1, 'tileCollide': True},
        'projectileSemanticsReference': {
            'ammoProjectileRelation': 'conditionally_replaced',
            'stages': [{'rules': [{'whenInputProjectileId': 1, 'outputProjectileId': 485}]}],
            'unknowns': ['selected ammo/PickAmmo not resolved', 'current specific-match table entries not resolved'],
            'scope': 'Source parent evidence, not mandatory child behavior',
        },
    }
    if ammo_mode is None:
        expected.pop('mode')
    else:
        expected['mode'] = ammo_mode
    ammo = copy.deepcopy(expected)
    if legacy:
        ammo.update({key: [{'type': 872938, 'damage': 872939, 'internalName': 'CANDIDATE_MUST_NOT_REACH_MODEL', 'shootSpeed': 872940}]
                     for key in ('playerInventoryAmmoRaw', 'fallbackAmmoRaw', 'playerInventoryProjectileRaw',
                                 'fallbackProjectileRaw', 'nativeReplacementProjectileRaw', 'candidateProjectileBindings')})
        ammo.update(playerInventoryObservation={'status': 'observed'}, ammoItemRaw={'type': 872938}, projectileRaw={'type': 872938})
    source = {'damage': weapon_damage, 'ammoRaw': ammo}
    parent = {'name': 'Weapon source', **(source if envelope == 'root' else {'fingerprint': source})}
    other = {'name': 'Actual ammo ingredient', 'ammoRaw': {'mode': 'this_item_is_ammo', 'ammoId': 40,
             'ammoItemRaw': {'type': 40, 'damage': 6}, 'projectileRaw': {'type': 2}}}
    before = copy.deepcopy(parent)
    raws = _source_packets(parent, captured, other)
    packet = prompt._prompt_packet(_accepted_visual_data('workbench_blade'), parent, other)
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            stage._request(request.call_llm_vfx_director, packet, **({'repair_errors': [], 'previous': {}, 'repair_scope': {'allowCreateSlots': True, 'fieldPermissions': {'globals': {}, 'slots': [], 'assets': []}}} if repair else {}))
        dossier = request_dossier(captured[-1])
        raws.append(dossier['parentFactsReadOnly' if repair else 'parents'][0]['packet']['raw'])
    for raw in raws:
        assert raw['ammo'] == expected
        assert raw['item']['damage'] == weapon_damage
    for index, payload in enumerate(captured):
        dossier = request_dossier(payload)
        if index < 2:
            other_raw = dossier['parents']['B' if index == 0 else 'b']['packet']['raw']
        elif index < 4:
            other_raw = dossier['parents' if index == 2 else 'parentFactsReadOnly']['parentB']['packet']['raw']
        else:
            other_raw = dossier['parents' if index == 4 else 'parentFactsReadOnly'][1]['packet']['raw']
        assert other_raw['ammo']['ammoItemRaw']['damage'] == 6
    import json
    serialized = json.dumps(captured)
    for sentinel in ('CANDIDATE_MUST_NOT_REACH_MODEL', '872938', '872939', '872940'):
        assert sentinel not in serialized
    detached = compact_ammo_profile(parent)
    detached['projectileSemanticsReference']['unknowns'].append('consumer mutation')
    assert parent == before


def test_actual_ammo_parent_keeps_own_profile(offline_packets):
    captured, _ = offline_packets
    parent = {'ammoRaw': {'mode': 'this_item_is_ammo', 'ammoId': 40,
                         'ammoItemRaw': {'type': 40, 'damage': 5, 'stack': 99},
                         'projectileRaw': {'type': 1, 'tileCollide': True}}}
    expected = {'mode': 'this_item_is_ammo', 'ammoId': 40,
        'ammoItemRaw': {'type': 40, 'damage': 5}, 'projectileRaw': {'type': 1, 'tileCollide': True}}
    assert compact_ammo_profile(parent) == expected
    for raw in _source_packets(parent, captured):
        assert raw['ammo'] == expected


def test_explicit_empty_ammo_observation_does_not_borrow_fingerprint():
    parent = {'ammoRaw': {}, 'fingerprint': {'ammoRaw': {
        'mode': 'weapon_uses_ammo', 'ammoId': 1, 'ammoCategoryName': 'Arrow',
        'playerInventoryAmmoRaw': [{'type': 40, 'stack': 999}]}}}
    assert compact_ammo_profile(parent) == {}
    del parent['ammoRaw']
    assert compact_ammo_profile(parent) == {'mode': 'weapon_uses_ammo', 'ammoId': 1, 'ammoCategoryName': 'Arrow'}
