"""Native motion unit views describe source fields, never an inferred shot."""
import copy

import pytest

from infini_local.pipelines.context.stats import parent_stat_context
from prompt_packet_helpers import expand_native_source_references, request_dossier


def rows(result):
    scope = result['sourceMotionUnits']['scope']
    for calculation in ('=', '*', 'convert', 'calculate', 'divide', 'multiply'):
        assert calculation not in scope.lower(), 'native context supplies values, not calculation instructions'
    values = result['sourceMotionUnits']['values']
    indexed = {row['sourcePath']: row for row in values}
    assert len(indexed) == len(values), 'each exact source path is described once'
    return indexed


def test_native_motion_units_keep_source_values_and_use_only_the_profile_clock():
    # Source shape/values from the captured ThoriumStaff / ThoriumBolt request.
    source = {
        'item': {'shootSpeed': 6, 'useAmmo': 0, 'ammo': 0},
        'directProjectile': {'source': 'item.shoot', 'type': 4765,
                             'itemShootSpeed': 6, 'extraUpdates': 1, 'timeLeft': 240},
    }
    before = copy.deepcopy(source)
    result = parent_stat_context(source)
    observed = rows(result)
    assert observed['raw.item.shootSpeed'] == {
        'sourcePath': 'raw.item.shootSpeed', 'nativeMember': 'Terraria.Item.shootSpeed',
        'value': 6, 'units': 'pixels/projectile update',
    }
    speed = observed['raw.directProjectile.itemShootSpeed']
    assert speed['value'] == 6 and speed['nativeMember'] == 'Terraria.Item.shootSpeed'
    assert speed['clock'] == {'sourcePath': 'raw.directProjectile.extraUpdates', 'updatesPerTick': 2}
    assert speed['equivalent'] == {'value': 45, 'units': 'blocks/s'}
    assert observed['raw.directProjectile.timeLeft']['equivalent'] == {'value': 2, 'units': 'seconds'}
    assert source == before
    assert {k: v for k, v in result.items() if k != 'sourceMotionUnits'} == before
    assert parent_stat_context(result) == result


@pytest.mark.parametrize('extra_updates', [None, -1, True, 1.5, '2', 2**31 - 1])
def test_missing_or_invalid_profile_clock_never_defaults_to_one_update(extra_updates):
    profile = {'itemShootSpeed': 6, 'timeLeft': 240}
    if extra_updates is not None:
        profile['extraUpdates'] = extra_updates
    result = parent_stat_context({'directProjectile': profile})
    for row in rows(result).values():
        assert 'clock' not in row and 'equivalent' not in row
    assert result['directProjectile'] == profile


@pytest.mark.parametrize('extra_updates, speed, seconds', [(0, 22.5, 4), (2, 67.5, 4 / 3)])
def test_profile_update_counts_and_zero_are_exact(extra_updates, speed, seconds):
    source = {'directProjectile': {'itemShootSpeed': 6, 'extraUpdates': extra_updates, 'timeLeft': 240},
              'effectiveProjectile': {'itemShootSpeed': 0, 'extraUpdates': 0, 'timeLeft': 0}}
    observed = rows(parent_stat_context(source))
    assert observed['raw.directProjectile.itemShootSpeed']['equivalent']['value'] == speed
    assert observed['raw.directProjectile.timeLeft']['equivalent']['value'] == seconds
    assert observed['raw.effectiveProjectile.itemShootSpeed']['equivalent']['value'] == 0
    assert observed['raw.effectiveProjectile.timeLeft']['equivalent']['value'] == 0


def test_legacy_ammo_candidates_are_excluded_but_native_replacements_keep_motion_context():
    profile = {'source': 'inventory.shoot', 'inventorySlot': 3, 'itemShootSpeed': 2,
               'extraUpdates': 0, 'timeLeft': 600}
    source = {'item': {'shootSpeed': 6, 'useAmmo': 97}, 'ammo': {
        'mode': 'weapon_uses_ammo', 'playerInventoryObservation': {'status': 'unavailable'},
        'projectileRaw': {'sameAs': 'directProjectile'},
        'playerInventoryAmmoRaw': [{'source': 'inventory', 'inventorySlot': 3, 'shootSpeed': 2, 'ammo': 97}],
        'fallbackAmmoRaw': [{'source': 'representative', 'shootSpeed': 4, 'notAmmo': False}],
        'playerInventoryProjectileRaw': [profile, copy.deepcopy(profile)],
        'fallbackProjectileRaw': [{'source': 'representative.shoot', 'itemShootSpeed': 4, 'extraUpdates': 2}],
        'nativeReplacementProjectileRaw': [{'source': 'native_source_replacement', 'timeLeft': 300, 'extraUpdates': 0}],
    }}
    before = copy.deepcopy(source)
    result = parent_stat_context(source)
    observed = rows(result)
    assert [row for path, row in observed.items() if path.startswith('raw.ammo.')] == [{
        'sourcePath': 'raw.ammo.nativeReplacementProjectileRaw[0].timeLeft',
        'nativeMember': 'Terraria.Projectile.timeLeft', 'value': 300, 'units': 'projectile updates',
        'clock': {'sourcePath': 'raw.ammo.nativeReplacementProjectileRaw[0].extraUpdates', 'updatesPerTick': 1},
        'equivalent': {'value': 5.0, 'units': 'seconds'},
    }]
    assert result['ammo'] == before['ammo'] and source == before


@pytest.mark.parametrize('source', [
    {'generatedParent': {'runtimeProgram': {}}, 'item': {'shootSpeed': 6}},
    {'directProjectile': {'unavailable': True, 'itemShootSpeed': 6, 'extraUpdates': 0}},
    {'directProjectile': {'sameAs': 'effectiveProjectile', 'itemShootSpeed': 6, 'extraUpdates': 0}},
    {'item': {'shootSpeed': True}, 'directProjectile': {'speed': 6, 'extraUpdates': 0}},
    {'directProjectile': {'itemShootSpeed': float('inf'), 'timeLeft': -1}},
    {'futureContainer': {'itemShootSpeed': 6, 'extraUpdates': 0, 'timeLeft': 600}},
])
def test_unknown_or_unavailable_sources_do_not_gain_motion_facts(source):
    assert parent_stat_context(source) == source


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('stage', ['author', 'repair'])
def test_serialized_requests_carry_ready_native_motion_values_unchanged(monkeypatch, mode, stage):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from test_source_unit_guidance import _broken_item, _repair_request, _serialized_chat_request
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    a = {'name': 'Native field sample', 'shootSpeed': 6, 'useAmmo': 0,
         'directProjectileRaw': {'source': 'item.shoot', 'type': 4765, 'itemShootSpeed': 6,
                                 'extraUpdates': 1, 'timeLeft': 240, 'tileCollide': True}}
    before = copy.deepcopy(a)
    if stage == 'author':
        request, _, _ = build_initial_author_request(
            a, {'name': 'Other input'}, 'source-motion-units', model_name='offline')
    else:
        request, _ = _repair_request(monkeypatch, mode, a, _broken_item())
    sent = _serialized_chat_request(monkeypatch, request)
    dossier = expand_native_source_references(request_dossier(sent, declaration=request))
    raw = dossier['parents']['A' if stage == 'author' else 'a']['packet']['raw']
    observed = rows(raw)
    assert observed['raw.directProjectile.itemShootSpeed']['equivalent'] == {'value': 45, 'units': 'blocks/s'}
    assert observed['raw.directProjectile.timeLeft']['equivalent'] == {'value': 2, 'units': 'seconds'}
    assert 'equivalent' not in observed['raw.item.shootSpeed']
    assert raw['item']['shootSpeed'] == 6 and raw['directProjectile']['extraUpdates'] == 1
    assert raw['directProjectile']['tileCollide'] is True
    assert a == before


def test_native_replacements_use_each_own_clock_and_preserve_order_and_unknown_clock():
    source = {'ammo': {'nativeReplacementProjectileRaw': [
        {'type': 2, 'timeLeft': 1200, 'extraUpdates': 0},
        {'type': 357, 'timeLeft': 600, 'extraUpdates': 2},
        {'type': 999, 'timeLeft': 1200},
        {'type': 2, 'timeLeft': 1200, 'extraUpdates': 0},
    ]}}
    before = copy.deepcopy(source)
    result = parent_stat_context(source)
    observed = list(rows(result).values())
    assert [(row['sourcePath'], row['value'], row.get('equivalent')) for row in observed] == [
        ('raw.ammo.nativeReplacementProjectileRaw[0].timeLeft', 1200, {'value': 20.0, 'units': 'seconds'}),
        ('raw.ammo.nativeReplacementProjectileRaw[1].timeLeft', 600, {'value': 10 / 3, 'units': 'seconds'}),
        ('raw.ammo.nativeReplacementProjectileRaw[2].timeLeft', 1200, None),
        ('raw.ammo.nativeReplacementProjectileRaw[3].timeLeft', 1200, {'value': 20.0, 'units': 'seconds'}),
    ]
    assert 'clock' not in observed[2]
    assert result['ammo'] == before['ammo'] and source == before
