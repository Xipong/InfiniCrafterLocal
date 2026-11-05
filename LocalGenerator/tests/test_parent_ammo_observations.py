"""Weapon category and source conversion evidence, never concrete ammo examples."""
from __future__ import annotations

import copy
import json
import re
import pytest

from infini_local.pipelines.context.parents import compact_ammo_profile
from tests.test_units_packet_preservation import _source_packets, offline_packets, _CapturedRequest


def _all_stage_packets(parent, captured, other=None):
    from infini_local.pipelines.vfx import prompt, stage, request
    from tests.test_low_level_three_stage_pipeline import _accepted_visual_data
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    other = other or {}
    _source_packets(parent, captured, other)
    packet = prompt._prompt_packet(_accepted_visual_data('workbench_blade'), parent, other)
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            stage._request(request.call_llm_vfx_director, packet, **({'repair_errors': [], 'previous': {},
                'repair_scope': {'allowCreateSlots': True, 'fieldPermissions': {'globals': {}, 'slots': [], 'assets': []}}} if repair else {}))
    author, repair, visual, visual_repair, vfx, vfx_repair = [
        expand_native_source_references(request_dossier(payload)) for payload in captured]
    return [author['parents']['A']['packet']['raw'], repair['parents']['a']['packet']['raw'],
            visual['parents']['parentA']['packet']['raw'], visual_repair['parentFactsReadOnly']['parentA']['packet']['raw'],
            vfx['parents'][0]['packet']['raw'], vfx_repair['parentFactsReadOnly'][0]['packet']['raw']]


def _profile_source_ledger(profile):
    """Compare frozen source statements independently of tables and local names.

    Source step/block identify each scalar binding in these frozen captures.
    Everything except the representation's reading guide remains in the ledger.
    """
    from infini_local.pipelines.context.attack_tables import unpack_attack_tables
    from prompt_packet_helpers import expand_native_identifier_aliases

    def program(value):
        if isinstance(value, list):
            return [program(child) for child in value]
        if not isinstance(value, dict):
            return value
        if 'operations' not in value and not {'observations', 'dependencies', 'predicates'} <= set(value):
            return {key: program(child) for key, child in value.items() if key not in {'behaviorView', 'branchTests'}}
        result = copy.deepcopy(value)
        if 'operations' in result:
            operations = result.pop('operations')
            definitions = {row['bind']: {key: child for key, child in row.items() if key != 'bind'}
                           for row in operations if 'bind' in row}
            observations = [row for row in operations if 'bind' not in row and 'id' not in row]
            predicates = [row for row in operations if 'id' in row]
            assert len(operations) == len(definitions) + len(observations) + len(predicates)
        else:
            definitions = result.pop('dependencies')
            observations, predicates = result.pop('observations'), result.pop('predicates')
        positions = [(row['step'], row['block']) for row in definitions.values()]
        assert len(set(positions)) == len(positions)
        names = {name: f"valueAt{row['step']}Block{row['block']}" for name, row in definitions.items()}

        def rename(value):
            if isinstance(value, str):
                # Quoted literals stay literal, even if they contain a local name.
                return re.sub(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*',
                              lambda match: names.get(match[0], match[0]), value)
            if isinstance(value, list):
                return [rename(child) for child in value]
            if isinstance(value, dict):
                return {key: rename(child) for key, child in value.items()}
            return value

        result['definitions'] = {names[key]: rename(row) for key, row in definitions.items()}
        result['observations'] = rename(observations)
        result['predicates'] = rename(predicates)
        return {key: program(child) for key, child in result.items()}

    result = copy.deepcopy(profile)
    result['attackReference'] = program(expand_native_identifier_aliases(unpack_attack_tables(result['attackReference'])))
    return json.dumps(result, sort_keys=True)


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('ammo_mode', ['weapon_uses_ammo', 'unknown_future_mode', None])
@pytest.mark.parametrize('envelope,weapon_damage', [('root', 11), ('fingerprint', 14)])
def test_weapon_context_survives_all_stages_without_ammo_examples(offline_packets, legacy, envelope, weapon_damage, ammo_mode):
    from prompt_packet_helpers import request_dossier
    captured, _ = offline_packets
    replacement = {
        'source': 'source_inspected_replacement_projectile_identity_not_final_shot',
        'type': 485, 'timeLeft': 1200, 'extraUpdates': 0, 'penetrate': 1, 'tileCollide': True,
        'sourceReferences': [{'kind': 'native_projectile_replacement',
            'sourcePath': 'projectileSemanticsReference.stages[0].rules[0]',
            'sourceFact': {'whenInputProjectileId': 1, 'outputProjectileId': 485},
            'conditionStatus': 'source_conditions_not_evaluated'}],
        'profileScope': 'Source-referenced defaults; not an observed outgoing shot.',
        'attackReference': {'source': 'source-defined fixture', 'observations': [
            {'expression': 'source-write-2', 'condition': None},
            {'expression': 'source-write-1', 'alternatives': [0, False, 0.0, [], {}]},
            {'expression': 'source-write-2', 'condition': None}]},
        'motionReference': {'source': 'source-defined fixture', 'gravity': 0.1, 'unknowns': []},
        'collisionReference': {'source': 'source-defined fixture', 'enabled': False, 'radius': 0.0},
        'onHitStatusReference': {'source': 'source-defined fixture', 'effects': [], 'unknowns': ['opaque hook']},
        'referencedProjectiles': {'source': 'native_single_hop_projectile_references', 'version': 1,
            'sourceCalls': [{'condition': 'source branch', 'spawnCount': 2}],
            'references': [{'type': 2, 'sourceCallIndices': [0],
                'profile': {'type': 2, 'penetrate': 1, 'timeLeft': 600, 'extraUpdates': 0,
                    'collisionReference': {'source': 'child fixture', 'radius': 0},
                    'onHitStatusReference': {'source': 'child fixture', 'effects': []}}},
                {'type': 3, 'sourceCallIndices': [0], 'unresolved': 'unavailable source'}]},
    }
    expected = {
        'mode': 'weapon_uses_ammo', 'ammoId': 40, 'ammoCategoryName': 'Arrow',
        'weaponShootFieldProjectileRaw': {'type': 1, 'tileCollide': True},
        'nativeReplacementProjectileRaw': [replacement, {**copy.deepcopy(replacement), 'penetrate': -1}, copy.deepcopy(replacement)],
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
                                 'fallbackProjectileRaw', 'candidateProjectileBindings')})
        ammo.update(playerInventoryObservation={'status': 'observed'}, ammoItemRaw={'type': 872938}, projectileRaw={'type': 872938})
    source = {'damage': weapon_damage, 'ammoRaw': ammo}
    parent = {'name': 'Weapon source', **(source if envelope == 'root' else {'fingerprint': source})}
    other = {'name': 'Actual ammo ingredient', 'ammoRaw': {'mode': 'this_item_is_ammo', 'ammoId': 40,
             'ammoItemRaw': {'type': 40, 'damage': 6}, 'projectileRaw': {'type': 2}}}
    before = copy.deepcopy(parent)
    raws = _all_stage_packets(parent, captured, other)
    for raw in raws:
        assert json.dumps(raw['ammo'], sort_keys=True) == json.dumps(expected, sort_keys=True)
        for profile in raw['ammo']['nativeReplacementProjectileRaw']:
            for key in ('sourceReferences', 'attackReference', 'motionReference', 'collisionReference', 'onHitStatusReference'):
                assert json.dumps(profile[key]) == json.dumps(replacement[key])
        motion = raw['sourceMotionUnits']['values']
        assert motion == [{
            'sourcePath': f'raw.ammo.nativeReplacementProjectileRaw[{index}].timeLeft',
            'nativeMember': 'Terraria.Projectile.timeLeft', 'value': 1200, 'units': 'projectile updates',
            'clock': {'sourcePath': f'raw.ammo.nativeReplacementProjectileRaw[{index}].extraUpdates', 'updatesPerTick': 1},
            'equivalent': {'value': 20.0, 'units': 'seconds'},
        } for index in range(3)]
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
    serialized = json.dumps(captured)
    for sentinel in ('CANDIDATE_MUST_NOT_REACH_MODEL', '872938', '872939', '872940'):
        assert sentinel not in serialized
    detached = compact_ammo_profile(parent)
    detached['projectileSemanticsReference']['unknowns'].append('consumer mutation')
    detached['nativeReplacementProjectileRaw'][0]['sourceReferences'][0]['sourceFact']['outputProjectileId'] = 999
    detached['nativeReplacementProjectileRaw'][0]['referencedProjectiles']['references'].clear()
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


@pytest.mark.parametrize('envelope', ['root', 'fingerprint'])
def test_captured_molten_fury_replacement_retains_fire_arrow_facts_in_every_stage(offline_packets, envelope):
    import gzip
    import hashlib
    from pathlib import Path
    from infini_local.pipelines.context.attack_tables import unpack_attack_tables

    # Complete unmodified itemB from the 2026-11-05 baseline Prepare capture,
    # profiling/baseline/ammo/cold-first-request.json. This is source input, not
    # a golden generated from the fixed consumer or a gameplay simulation.
    data = gzip.decompress((Path(__file__).parent / 'fixtures/native_molten_fury_parent_capture.json.gz').read_bytes())
    assert hashlib.sha256(data).hexdigest() == '5f593a6a5b74c2d11f679b01869ab207bdb0b3dac6c9b400ef2f988e12677964'
    source = json.loads(data)
    assert source['internalName'] == 'MoltenFury'
    native = source['ammoRaw']['nativeReplacementProjectileRaw'][0]
    assert native['fullName'] == 'Terraria/FireArrow'
    assert native['motionReference'] is None and native['collisionReference'] is None
    assert 'sourceReferences' not in native  # Legacy applicability stays unknown.
    original_operation = native['onHitStatusReference']['randomOutcomes'][0]['alternatives'][0]['effects'][0][
        'buffEffectReference']['fragments'][0]['operations'][0]
    assert original_operation['value'] == -8 and original_operation['units'] == 'native_lifeRegen_units'
    # Independent replay against pristine main, captured before restoring this
    # consumer. Do not derive expected output by calling the owner under test.
    expected = json.loads(gzip.decompress((Path(__file__).parent /
        'fixtures/native_molten_fury_stage_profiles.json.gz').read_bytes()))
    assert hashlib.sha256(data).hexdigest() == expected['sourceItemSha256']
    parent = source if envelope == 'root' else {'name': 'Molten Fury', 'fingerprint': source['fingerprint']}
    before = copy.deepcopy(parent)
    captured, _ = offline_packets
    for index, raw in enumerate(_all_stage_packets(parent, captured)):
        ammo = raw['ammo']
        assert len(ammo['nativeReplacementProjectileRaw']) == 1
        replacement = ammo['nativeReplacementProjectileRaw'][0]
        assert _profile_source_ledger(replacement) == _profile_source_ledger(expected['author' if index < 2 else 'presentation'])
        assert {key: replacement[key] for key in ('type', 'penetrate', 'maxPenetrate', 'timeLeft', 'extraUpdates', 'tileCollide')} == {
            'type': 2, 'penetrate': 1, 'maxPenetrate': 1, 'timeLeft': 1200, 'extraUpdates': 0, 'tileCollide': True}
        assert 'sourceReferences' not in replacement and 'profileScope' not in replacement
        assert ammo['projectileSemanticsReference'] == source['ammoRaw']['projectileSemanticsReference']
        assert ammo['projectileSemanticsReference']['finalShotOutcome'] == 'unknown_without_gameplay_execution'
        outcomes = replacement['onHitStatusReference']['randomOutcomes'][0]['alternatives']
        assert [(row['randomValues'], row['probabilityNumerator'], row['probabilityDenominator']) for row in outcomes] == [
            ([0], 1, 3), ([1, 2], 2, 3)]
        assert outcomes[1]['effects'] == []
        effect = outcomes[0]['effects'][0]
        assert (effect['buffFullName'], effect['durationTicksMin'], effect['durationTicksMax']) == ('Terraria/OnFire', 180, 180)
        fragment = effect['buffEffectReference']['fragments'][0]
        assert fragment['condition'] == native['onHitStatusReference']['randomOutcomes'][0]['alternatives'][0]['effects'][0][
            'buffEffectReference']['fragments'][0]['condition']
        operation = fragment['operations'][0]
        assert (operation['value'], operation['units']) == (-4.0, 'HP/s at 60 accumulator updates/s')
        assert operation['unitEvidence'] == original_operation['unitEvidence']
        assert operation['nominalRateScope'] == original_operation['nominalRateScope']
        attack = unpack_attack_tables(replacement['attackReference'])
        if index < 2:
            motion = attack['motion']['programs'][0]
            observations = [row for row in motion.get('operations', motion.get('observations')) if 'kind' in row]
            assert [row['kind'] for row in observations] == [
                'clock_or_ai_write', 'clock_or_ai_write', 'state_write', 'state_write', 'rotation', 'state_write', 'state_write']
            assert observations[2]['requiredPredicates'] == ['b47116', 'b47132']
            assert observations[3]['requiredPredicates'] == ['b47116', 'b47132']
        assert attack['coverage']['unresolved'] == native['attackReference']['coverage']['unresolved']
        rows = [row for row in raw['sourceMotionUnits']['values'] if 'nativeReplacementProjectileRaw' in row['sourcePath']]
        assert rows == [{'sourcePath': 'raw.ammo.nativeReplacementProjectileRaw[0].timeLeft',
            'nativeMember': 'Terraria.Projectile.timeLeft', 'value': 1200, 'units': 'projectile updates',
            'clock': {'sourcePath': 'raw.ammo.nativeReplacementProjectileRaw[0].extraUpdates', 'updatesPerTick': 1},
            'equivalent': {'value': 20.0, 'units': 'seconds'}}]
        assert not set(ammo).intersection(('candidateProjectileBindings', 'playerInventoryAmmoRaw',
            'playerInventoryProjectileRaw', 'fallbackAmmoRaw', 'fallbackProjectileRaw'))
    assert parent == before


def test_unavailable_native_replacement_retains_reason_and_unknowns_in_every_stage(offline_packets):
    parent = {'ammoRaw': {'mode': 'weapon_uses_ammo', 'nativeReplacementProjectileRaw': [{
        'type': 42, 'unavailable': True, 'unresolved': 'projectile_defaults_snapshot_unavailable',
        'sourceReferences': [{'kind': 'inspected_hook_projectile_replacement', 'sourceFact': {
            'outputProjectileId': 42, 'unknown': None}, 'conditionStatus': 'source_conditions_not_evaluated',
            'dispatchStatus': 'unverified', 'blockingHookIndices': []}],
        'profileScope': 'Source reference only; defaults unavailable.',
    }]}}
    before = copy.deepcopy(parent)
    captured, _ = offline_packets
    for raw in _all_stage_packets(parent, captured):
        assert raw['ammo'] == parent['ammoRaw']
        assert 'sourceMotionUnits' not in raw
    assert parent == before


@pytest.mark.parametrize('item_id,projectile_id,penetration,lifetime,updates,relation,condition,kind', [
    ('120', 2, 1, 1200, 0, 'conditionally_replaced', 1, 'native_projectile_replacement'),
    ('2223', 357, 6, 600, 2, 'replaced', None, 'native_projectile_replacement'),
    ('3019', 485, -1, 1200, 0, 'conditionally_replaced', 1, 'native_projectile_replacement'),
    ('4381', 819, 1, 3600, 1, 'replaced', None, 'native_projectile_replacement'),
    ('3930', 714, -1, 3600, 0, 'native_ammo_table_or_offset_selection', None, 'native_fixed_projectile_spawn'),
    ('3029', None, None, None, None, 'retained_with_native_item_delivery', None, None),
])
def test_native_producer_replacement_profiles_reach_every_stage(offline_packets, item_id, projectile_id,
        penetration, lifetime, updates, relation, condition, kind):
    import gzip
    from pathlib import Path
    from infini_local.pipelines.context.attack_tables import unpack_attack_tables
    capture = json.loads(gzip.decompress((Path(__file__).parent /
        'fixtures/native_weapon_replacement_parents.json.gz').read_bytes()))
    parent = capture['parents'][item_id]
    before = copy.deepcopy(parent)
    native_ammo = parent['ammoRaw']
    native_profiles = native_ammo['nativeReplacementProjectileRaw']
    captured, _ = offline_packets
    for index, raw in enumerate(_all_stage_packets(parent, captured)):
        ammo = raw['ammo']
        assert ammo['projectileSemanticsReference'] == native_ammo['projectileSemanticsReference']
        assert ammo['projectileSemanticsReference']['ammoProjectileRelation'] == relation
        assert ammo['projectileSemanticsReference']['finalShotOutcome'] == 'unknown_without_gameplay_execution'
        assert ammo['ammoCategoryName'] == native_ammo['ammoCategoryName']
        assert not set(ammo).intersection(('candidateProjectileBindings', 'playerInventoryAmmoRaw',
            'playerInventoryProjectileRaw', 'fallbackAmmoRaw', 'fallbackProjectileRaw'))
        profiles = ammo['nativeReplacementProjectileRaw']
        assert [profile['type'] for profile in profiles] == ([] if projectile_id is None else [projectile_id])
        if projectile_id is None:
            assert ammo['projectileSemanticsReference']['stages'][1]['spawnOriginSetups'][0]['initialYRelativeToMountedCenterPx'] == -600
            continue
        profile, native = profiles[0], native_profiles[0]
        assert (profile['penetrate'], profile['timeLeft'], profile['extraUpdates']) == (penetration, lifetime, updates)
        assert json.dumps(profile['sourceReferences']) == json.dumps(native['sourceReferences'])
        assert profile['profileScope'] == native['profileScope']
        reference = profile['sourceReferences'][0]
        assert reference['kind'] == kind
        assert reference['conditionStatus'] == 'source_conditions_not_evaluated'
        assert reference['dispatchStatus'] == 'source_site_only_not_guaranteed_execution'
        assert reference['sourceFact'].get('whenInputProjectileId') == condition
        assert 'itemShootSpeed' not in profile  # No guessed fired speed from weapon/ammo coefficients.
        attack = unpack_attack_tables(profile['attackReference'])
        assert attack['identityPredicates']['Projectile.type'] == projectile_id
        assert attack['coverage'] == native['attackReference']['coverage']
        if index < 2:
            assert 'positionIntegration' in attack
        else:
            assert not set(attack).intersection(('motion', 'motionDispatch', 'collision', 'positionIntegration'))
        rows = [row for row in raw['sourceMotionUnits']['values'] if 'nativeReplacementProjectileRaw' in row['sourcePath']]
        assert rows == [{'sourcePath': 'raw.ammo.nativeReplacementProjectileRaw[0].timeLeft',
            'nativeMember': 'Terraria.Projectile.timeLeft', 'value': lifetime, 'units': 'projectile updates',
            'clock': {'sourcePath': 'raw.ammo.nativeReplacementProjectileRaw[0].extraUpdates', 'updatesPerTick': updates + 1},
            'equivalent': {'value': lifetime / (60 * (updates + 1)), 'units': 'seconds'}}]
    assert parent == before


def test_captured_actual_ammo_parent_keeps_own_item_and_projectile_in_every_stage(offline_packets):
    from pathlib import Path
    from infini_local.pipelines.context.attack_tables import unpack_attack_tables
    parent = json.loads((Path(__file__).parent / 'fixtures/native_wooden_arrow_parent_capture.json').read_text())
    before = copy.deepcopy(parent)
    captured, _ = offline_packets
    for index, raw in enumerate(_all_stage_packets(parent, captured)):
        ammo = raw['ammo']
        assert ammo['mode'] == 'this_item_is_ammo' and ammo['ammoId'] == 40
        assert ammo['ammoItemRaw'] == {
            'source': 'parent_item', 'inventorySlot': -1, 'type': 40, 'internalName': 'WoodenArrow',
            'sourceMod': 'Terraria', 'fullName': 'Terraria/WoodenArrow', 'damage': 5, 'damageClass': 'ranged',
            'ammo': 40, 'ammoCategoryName': 'arrow', 'notAmmo': False, 'useAmmo': 0,
            'shoot': 1, 'shootSpeed': 3, 'knockback': 2, 'rare': 0, 'value': 5, 'maxStack': 9999,
            'consumable': True, 'material': False}
        profile = ammo['projectileRaw']
        if 'sameAs' in profile:
            assert profile == {'sameAs': 'raw.directProjectile', 'source': 'this_ammo_item.shoot'}
            profile = raw['directProjectile']
        assert (profile['type'], profile['penetrate'], profile['timeLeft'], profile['extraUpdates']) == (1, 1, 1200, 0)
        assert profile['tileCollide'] is True and profile['friendly'] is True and profile['hostile'] is False
        attack = unpack_attack_tables(profile['attackReference'])
        assert attack['coverage'] == parent['ammoRaw']['projectileRaw']['attackReference']['coverage']
        if index < 2:
            assert attack['identityPredicates'] == {'Projectile.type': 1, 'Projectile.aiStyle': 1}
            motion = attack['motion']['programs'][0]
            operations = motion.get('observations', motion.get('operations'))
            assert len([row for row in operations if 'kind' in row]) == 7
        assert not set(ammo).intersection(('playerInventoryAmmoRaw', 'fallbackAmmoRaw', 'candidateProjectileBindings'))
    assert parent == before


def test_native_source_defined_hook_roster_keeps_motion_collision_and_child_profiles(offline_packets):
    import gzip
    from pathlib import Path
    capture = json.loads(gzip.decompress((Path(__file__).parent /
        'fixtures/native_hook_replacement_sources.json.gz').read_bytes()))
    assert capture['rosterSource']['fixtureKind'] == 'source_defined_global_hooks_not_loaded_mod_capture'
    parent = capture['rosterParent']
    before = copy.deepcopy(parent)
    native = parent['ammoRaw']['nativeReplacementProjectileRaw']
    captured, _ = offline_packets
    for raw in _all_stage_packets(parent, captured):
        profiles = raw['ammo']['nativeReplacementProjectileRaw']
        assert [profile['type'] for profile in profiles] == [1, 2, 617, 974, 181]
        for profile, source in zip(profiles, native, strict=True):
            assert json.dumps(profile['sourceReferences']) == json.dumps(source['sourceReferences'])
            assert profile['profileScope'] == source['profileScope']
        assert json.dumps(profiles[0]['motionReference']) == json.dumps(native[0]['motionReference'])
        assert (profiles[0]['motionReference']['firstGravityUpdate'],
                profiles[0]['motionReference']['verticalVelocityIncrementPerUpdate'],
                profiles[0]['motionReference']['maxDownwardVelocityPxPerUpdate']) == (15, 0.1, 16)
        assert json.dumps(profiles[3]['collisionReference']) == json.dumps(native[3]['collisionReference'])
        assert (profiles[3]['collisionReference']['halfLengthTimesProjectileScale'],
                profiles[3]['collisionReference']['lineWidthTimesProjectileScale']) == (46.0, 8.0)
        children, source_children = profiles[2]['referencedProjectiles'], native[2]['referencedProjectiles']
        assert {key: value for key, value in children.items() if key != 'references'} == {
            key: value for key, value in source_children.items() if key != 'references'}
        assert [(row['type'], row['sourceCallIndices']) for row in children['references']] == [(618, [0])]
        child = children['references'][0]['profile']
        assert (child['type'], child['penetrate'], child['timeLeft'], child['extraUpdates']) == (618, -1, 420, 0)
        assert child['attackReference'] and 'referencedProjectiles' not in child
    assert parent == before


@pytest.mark.parametrize('fixture,expected_ids', [
    ('ConditionalAmmoHook', [181]), ('UnknownAfterLiteralAmmoHook', [181]),
    ('OwnProjectileAmmoHook', [181]), ('OpaqueAmmoHook', []),
    ('InvalidOutputAmmoHook', []), ('SuppressedAmmoHook', []), ('UnavailableProjectileDefaults', [181]),
    ('GlobalAndOwnSpawn', [181, 2]), ('GlobalSuppressedOwnSpawn', [181, 2]),
])
def test_native_hook_conditions_unknowns_and_unavailable_profiles_remain_literal(offline_packets, fixture, expected_ids):
    import gzip
    from pathlib import Path
    capture = json.loads(gzip.decompress((Path(__file__).parent /
        'fixtures/native_hook_replacement_sources.json.gz').read_bytes()))['cases'][fixture]
    assert capture['source']['fixtureKind'] == 'source_defined_hooks_not_loaded_mod_capture'
    parent = {'ammoRaw': capture['ammoRaw']}
    before = copy.deepcopy(parent)
    captured, _ = offline_packets
    for raw in _all_stage_packets(parent, captured):
        ammo = raw['ammo']
        assert json.dumps(ammo['projectileSemanticsReference']) == json.dumps(capture['ammoRaw']['projectileSemanticsReference'])
        profiles = ammo['nativeReplacementProjectileRaw']
        assert [profile['type'] for profile in profiles] == expected_ids
        for profile, source in zip(profiles, capture['ammoRaw']['nativeReplacementProjectileRaw'], strict=True):
            assert json.dumps(profile['sourceReferences']) == json.dumps(source['sourceReferences'])
            assert profile['profileScope'] == source['profileScope']
            assert all(reference['conditionStatus'] == 'source_conditions_not_evaluated'
                       for reference in profile['sourceReferences'])
        if fixture in ('GlobalAndOwnSpawn', 'GlobalSuppressedOwnSpawn'):
            own_spawn = profiles[0]['sourceReferences'][0]
            assert own_spawn['kind'] == 'inspected_hook_fixed_projectile_spawn'
            if fixture == 'GlobalSuppressedOwnSpawn':
                assert own_spawn['dispatchStatus'] == 'blocked_by_inspected_global_shoot_suppression'
                assert own_spawn['blockingHookIndices'] == [2]
            else:
                assert own_spawn['dispatchStatus'] == 'certified_dispatch_order_gameplay_admission_unknown'
                assert 'blockingHookIndices' not in own_spawn
        if fixture == 'UnavailableProjectileDefaults':
            assert profiles[0]['unavailable'] is True
            assert profiles[0]['unresolved'] == 'projectile_defaults_snapshot_unavailable'
            assert 'timeLeft' not in profiles[0] and 'extraUpdates' not in profiles[0]
            assert not any('nativeReplacementProjectileRaw' in row['sourcePath']
                           for row in raw.get('sourceMotionUnits', {}).get('values', []))
    assert parent == before


def test_native_unknown_outer_guard_keeps_profile_without_claiming_applicability(offline_packets):
    import gzip
    from pathlib import Path
    fixtures = Path(__file__).parent / 'fixtures'
    capture = json.loads(gzip.decompress((fixtures / 'native_unknown_outer_guard_ammo.json.gz').read_bytes()))
    assert capture['source']['fixtureKind'] == 'synthetic_source_only_native_catalog_metadata'
    parent = {'ammoRaw': capture['ammoRaw']}
    before = copy.deepcopy(parent)
    baseline = json.loads(gzip.decompress((fixtures / 'native_molten_fury_stage_profiles.json.gz').read_bytes()))
    source_profile = parent['ammoRaw']['nativeReplacementProjectileRaw'][0]
    captured, _ = offline_packets
    for index, raw in enumerate(_all_stage_packets(parent, captured)):
        ammo = raw['ammo']
        semantics = ammo['projectileSemanticsReference']
        assert json.dumps(semantics) == json.dumps(parent['ammoRaw']['projectileSemanticsReference'])
        assert semantics['ammoProjectileRelation'] == 'unknown_native_projectile_semantics'
        assert semantics['finalShotOutcome'] == 'unknown_without_gameplay_execution'
        stage = semantics['stages'][1]
        assert stage['rules'] == []
        assert stage['unresolvedLiteralWrites'] == [{
            'outputProjectileId': 2, 'sourceStoreIlOffset': 536, 'sourceGuardIlOffset': 533,
            'applicability': 'unknown', 'reason': 'unknown_enclosing_guard', 'ownershipStatus': 'proved_item_guard'}]
        assert [profile['type'] for profile in ammo['nativeReplacementProjectileRaw']] == [2]
        profile = ammo['nativeReplacementProjectileRaw'][0]
        reference = profile['sourceReferences'][0]
        assert reference['kind'] == 'native_literal_write_unresolved_applicability'
        assert reference['conditionStatus'] == 'source_applicability_unresolved'
        assert reference['sourcePath'] == 'projectileSemanticsReference.stages[1].unresolvedLiteralWrites[0]'
        assert reference['sourceFact'] == stage['unresolvedLiteralWrites'][0]
        assert 'whenInputProjectileId' not in reference['sourceFact']
        assert json.dumps(profile['sourceReferences']) == json.dumps(source_profile['sourceReferences'])
        expected = {**baseline['author' if index < 2 else 'presentation'],
            'sourceReferences': source_profile['sourceReferences'], 'profileScope': source_profile['profileScope']}
        assert _profile_source_ledger(profile) == _profile_source_ledger(expected)
        assert (profile['penetrate'], profile['timeLeft'], profile['extraUpdates']) == (1, 1200, 0)
        assert not set(ammo).intersection(('candidateProjectileBindings', 'playerInventoryAmmoRaw',
            'playerInventoryProjectileRaw', 'fallbackAmmoRaw', 'fallbackProjectileRaw'))
    assert parent == before
