"""Coordinate-only reduction preserves gameplay calls, guards and unknown shapes."""
import copy
import pytest
from infini_local.pipelines.context.mechanics_context import _compact_raw_source_coordinates


def sample():
    return {'at': 42, 'requiredPredicates': ['charge_ready'], 'projectileTypes': [9],
            'arguments': {'damage': 'damage * 1.5', 'velocity': 'velocity * 2'},
            'unresolved': ['dynamic_owner'], 'sourceLocation': {
                'mechanicsSourceIndex': 0,
                'scope': 'raw_capture_strict_source_lines; not_lines_of_readable_author_source',
                'statement': {'mapping': 'source_lines', 'ilOffset': 42,
                              'locations': [{'ilOffset': 42, 'startLine': 3, 'endLine': 4}]},
                'predicates': [{'id': 'charge_ready', 'ilSites': [{'ilOffset': 21, 'sourceLines': [[1, 2]]}]}]}}


def test_coordinate_compaction_keeps_call_facts_and_input():
    call = sample(); original = copy.deepcopy(call)
    out = {**call, 'sourceLocation': _compact_raw_source_coordinates(call['sourceLocation'], call, 1)}
    assert call == original
    assert {k: v for k, v in out.items() if k != 'sourceLocation'} == {k: v for k, v in original.items() if k != 'sourceLocation'}
    assert out['sourceLocation']['mechanicsSourceIndex'] == 0
    assert 'coordinatesOmitted' in out['sourceLocation']
    assert _compact_raw_source_coordinates(out['sourceLocation'], out, 1) == out['sourceLocation']


@pytest.mark.parametrize('kind', ['scope', 'unknown', 'unbound', 'boolean-index', 'offset', 'guards',
                                  'statement-extension', 'site-extension', 'predicate-extension', 'malformed-lines'])
def test_unknown_or_unbound_coordinates_are_retained(kind):
    call = sample(); loc = call['sourceLocation']
    if kind == 'scope': loc['scope'] = 'actual_readable_source_lines'
    if kind == 'unknown': loc['behavior'] = 'important'
    if kind == 'unbound': loc['mechanicsSourceIndex'] = 1
    if kind == 'boolean-index': loc['mechanicsSourceIndex'] = False
    if kind == 'offset': call['at'] += 1
    if kind == 'guards': call['requiredPredicates'] = []
    if kind == 'statement-extension': loc['statement']['damage'] = 4
    if kind == 'site-extension': loc['predicates'][0]['ilSites'][0]['condition'] = 'hp < 10'
    if kind == 'predicate-extension': loc['predicates'][0]['condition'] = 'hp < 10'
    if kind == 'malformed-lines': loc['predicates'][0]['ilSites'][0]['sourceLines'] = [[3, 1]]
    before = copy.deepcopy(call)
    assert _compact_raw_source_coordinates(loc, call, 1) == loc
    assert call == before


def test_native_source_sites_shape_is_recognized_without_losing_guard():
    call = sample()
    call['sourceLocation']['predicates'] = [{'id': 'charge_ready', 'mapping': 'raw_predicate_sites',
        'sourceSites': [{'mapping': 'source_lines', 'ilOffset': 21,
                         'locations': [{'ilOffset': 21, 'startLine': 1, 'endLine': 2}]}]}]
    assert 'coordinatesOmitted' in _compact_raw_source_coordinates(call['sourceLocation'], call, 1)
    call['sourceLocation']['predicates'][0]['sourceSites'][0]['damage'] = 4
    assert _compact_raw_source_coordinates(call['sourceLocation'], call, 1) == call['sourceLocation']
