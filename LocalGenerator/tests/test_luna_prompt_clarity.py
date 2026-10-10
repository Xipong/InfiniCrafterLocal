"""Cold-reader gaps and concise prose without reducing the executable language."""
import copy
import json
import pytest
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport


def packet(monkeypatch, a=None, b=None):
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    request, user, _ = author.build_initial_author_request(a or {}, b or {}, {}, {}, 'cold-clarity', model_name='test-model')
    assert request['messages'][1]['content'] == user
    return json.loads(user)


def test_noncombat_parent_timing_is_literal_not_hidden_combat_default(monkeypatch):
    a = {'name': 'fruit', 'damage': -1, 'useTime': 17}
    b = {'name': 'flower', 'damage': -1, 'useTime': 10}
    before = copy.deepcopy((a, b))
    corridor = packet(monkeypatch, a, b)['balanceCorridor']
    assert corridor['parentUseTimeTicks'] == [17, 10]
    assert 'suggested' not in corridor['broadEnvelope']['useTimeTicks']
    assert (a, b) == before


def test_missing_parent_timing_stays_unknown(monkeypatch):
    corridor = packet(monkeypatch, {'name': 'unknown'}, {'name': 'known', 'useTime': 0})['balanceCorridor']
    assert corridor['parentUseTimeTicks'] == [None, 0]


def test_reusable_stack_rule_requires_explicit_placement(monkeypatch):
    cards = packet(monkeypatch)['runtimeCapabilityContract']['catalog']['capabilities']
    text = next(c['constructionMeaning'] for c in cards if c['fn'] == 'configure_item_stats')
    assert 'place_item binding' in text
    assert 'without placement' in text
    assert 'maxStack=1' in text


def test_repeated_consumer_guidance_is_short_and_keeps_all_boundaries(monkeypatch):
    catalog = packet(monkeypatch)['runtimeCapabilityContract']['catalog']
    profiles = catalog['fieldGuide']['consumerConstraints']
    constraints = [profiles[p['consumerConstraint']] for c in catalog['capabilities'] for p in c['params'].values()
                   if 'consumerConstraint' in p]
    meanings = [constraint['meaning'] for constraint in constraints if constraint.get('wireProjection')]
    assert meanings
    for text in meanings:
        assert len(text) <= 275
        for phrase in ('binary64', 'float32', 'both', 'exact neutral', 'No rounding or replacement', 'round-trip', 'gameplay arithmetic'):
            assert phrase in text
    # The predicate/metadata have not been replaced by prose.
    spec = CAPABILITY_REGISTRY['configure_accessory'].params['moveSpeedBonusPercent']
    assert spec.consumer_value_error(5e-324) is not None
    assert spec.consumer_value_error(15.125) is None
    assert spec.to_wire(15.125) == 0.15125


def test_contact_geometry_names_native_basis_not_a_fixed_png_box(monkeypatch):
    cards = packet(monkeypatch)['runtimeCapabilityContract']['catalog']['capabilities']
    text = next(c['does'] for c in cards if c['fn'] == 'configure_item_contact_hitbox')
    for phrase in ('current Terraria contact rectangle', 'not a fixed PNG', 'center', 'round', 'each side'):
        assert phrase in text


def test_boomerang_short_card_preserves_return_and_collision_facts(monkeypatch):
    cards = packet(monkeypatch)['runtimeCapabilityContract']['catalog']['capabilities']
    text = next(c['does'] for c in cards if c['fn'] == 'move_boomerang')
    assert len(text) <= 185
    for phrase in ('owner', 'wall collision', 'tileCollide', 'does not kill', 'tile bounces', 'NPC penetration'):
        assert phrase in text


def test_event_cards_do_not_borrow_other_operations_safety_or_payload(monkeypatch):
    cards = {c['fn']: c for c in packet(monkeypatch)['runtimeCapabilityContract']['catalog']['capabilities']}
    safety = cards['move_owner_on_event']['params']['safeTileOnly']['meaning']
    assert 'solid-tile overlap only' in safety
    assert 'No world-bounds or lava check' in safety
    aoe = cards['damage_area_on_event']['does']
    assert 'on_tile_collision/on_expire/on_kill carry no direct target' not in aoe
    assert 'only for on_hit/on_crit' in aoe
    placement = cards['configure_placeable']['does']
    assert 'both IDs enabled' in placement and 'runtime' in placement
