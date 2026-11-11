"""Keep symbolic outgoing arguments when unchanged whole C# owns the body."""
import copy

import pytest

from infini_local.pipelines.context.whole_method_author import (
    _residual_edge_context, prepare_whole_method_author, apply_whole_method_author,
)
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from infini_local.pipelines.context.mechanics_context import mechanics_context
from tests.generator.context.test_author_mechanics_policy import whole_method_parent


def argument_parent():
    item = whole_method_parent()
    graph = item['parentSourceGraph']
    node = graph['nodes'][0]
    # Live branch, opaque result and two possible local definitions. All are
    # source observations. In particular no evaluator may choose one write.
    node['values'].update({
        '1': ['ldarg', 0, [], 0],
        '2': ['call', {'member': 0}, ['1'], 0],
        '3': ['ldc.r4', 1.5, [], 0],
        '4': ['ldc.r4', 2.0, [], 0],
        '5': ['ldloc', 0, ['3', '4'], 0],
        '6': ['brfalse', 20, ['2'], 0],
        '9': ['mul', None, ['2', '5'], 20],
        '10': ['call', {'member': 0}, ['1', '9'], 20],
        '30': ['call', {'member': 0}, ['1'], 30],
    })
    node['blocks'] = [[0, [20, 30], 6, []], [20, [30], None, ['6']], [30, [], None, []]]
    node['possibleLocalWrites'] = {'5': ['3', '4', '3']}
    node['statements'] = ['2', '10', '30']
    graph['edges'][0]['context'] = ['1', '9']
    return item


def test_retained_argument_control_and_local_alternatives_are_unchanged():
    item = argument_parent(); before = copy.deepcopy(item)
    graph = item['parentSourceGraph']; original = graph['nodes'][0]
    residual = _residual_edge_context(graph, original)
    assert residual is not None
    assert set(residual['values']) == {'1', '2', '3', '4', '5', '6', '9', '10'}
    assert residual['values'] == {k: v for k, v in original['values'].items() if k != '30' and k in residual['values']}
    assert residual['blocks'] == original['blocks']
    assert residual['possibleLocalWrites'] == original['possibleLocalWrites']
    prepared, choices = prepare_whole_method_author(item)
    assert len(choices) == 1 and choices[0]['residual'] == residual
    raw = mechanics_context(raw_parent_card_for_llm(prepared)['raw'])
    assert apply_whole_method_author(raw, choices)
    projected = raw['item']['parentSourceGraph']['nodes'][0]
    for field, value in residual.items():
        assert projected[field] == value
    source = raw['mechanics']['source'][projected['bodySource']['mechanicsSourceIndex']]
    assert source['code'] == item['directProjectileRaw']['attackReference']['nativeCSharpSource']['records'][0]['code']
    assert 'Hook(ref type)' in source['code'] and 'type == 757' in source['code'] and 'scale *= 2' in source['code']
    assert 'not a second complete body or evaluated helper results' in raw['item']['parentSourceGraphReading']
    assert projected['unresolved'] == original['unresolved']
    assert raw['item']['parentSourceGraph']['edges'] == graph['edges']
    assert 'statements' not in projected
    assert item == before


@pytest.mark.parametrize('change', [
    'missing-input', 'missing-branch', 'missing-local-write', 'missing-callsite',
    'unknown-context', 'integer-context', 'bool-callsite', 'unknown-value-shape',
    'integer-input', 'bool-block', 'unknown-block-shape', 'unknown-predicate',
    'unknown-writes', 'fragments',
])
def test_incomplete_dependency_namespace_refuses_without_mutation(change):
    item = argument_parent(); graph = item['parentSourceGraph']; node = graph['nodes'][0]
    if change == 'missing-input': node['values'].pop('2')
    elif change == 'missing-branch': node['values'].pop('6')
    elif change == 'missing-local-write': node['values'].pop('4')
    elif change == 'missing-callsite': node['values'].pop('10')
    elif change == 'unknown-context': graph['edges'][0]['context'] = {'receiver': '9'}
    elif change == 'integer-context': graph['edges'][0]['context'] = [9]
    elif change == 'bool-callsite': graph['edges'][0]['at'] = True
    elif change == 'unknown-value-shape': node['values']['9'].append('future qualifier')
    elif change == 'integer-input': node['values']['9'][2] = [2, 5]
    elif change == 'bool-block': node['blocks'][0][0] = True
    elif change == 'unknown-block-shape': node['blocks'][0].append('future predicate')
    elif change == 'unknown-predicate': node['blocks'][1][3] = ['absent']
    elif change == 'unknown-writes': node['possibleLocalWrites']['5'] = {'if': ['3']}
    elif change == 'fragments': node['fragments'] = []
    before = copy.deepcopy(item)
    assert _residual_edge_context(graph, node) is None
    prepared, choices = prepare_whole_method_author(item)
    assert choices == [] and prepared == before and item == before


def test_cyclic_dependencies_and_duplicate_alternative_order_are_not_evaluated():
    item = argument_parent(); graph = item['parentSourceGraph']; node = graph['nodes'][0]
    node['values']['4'] = ['ldloc', 1, ['5'], 20]
    before = copy.deepcopy(node)
    result = _residual_edge_context(graph, node)
    assert result is not None and result['values']['4'] == before['values']['4']
    assert result['values']['5'] == before['values']['5']
    assert result['possibleLocalWrites'] == {'5': ['3', '4', '3']}
    assert node == before


def test_modified_edge_dependencies_after_prepare_refuse_atomically():
    prepared, choices = prepare_whole_method_author(argument_parent())
    raw = mechanics_context(raw_parent_card_for_llm(prepared)['raw'])
    raw['item']['parentSourceGraph']['nodes'][0]['values']['9'][2] = ['1']
    before = copy.deepcopy(raw)
    assert not apply_whole_method_author(raw, choices)
    assert raw == before
