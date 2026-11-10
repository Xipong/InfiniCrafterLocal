"""Only exact emitted unchanged whole methods discharge duplicate derived graphs."""
import copy
import pytest
from tests.generator.context.test_author_mechanics_policy import fixture
from infini_local.pipelines.context.parents import compact_projectile_profile
from infini_local.pipelines.context.attack_tables import unpack_attack_tables
from infini_local.pipelines.context.author_mechanics_policy import strict_source_diagnostics, _definition


def inputs():
    p = fixture()
    p['mechanicsSource']['records'][0]['coverage'] = 'unpruned_method'
    attack = compact_projectile_profile(p)['attackReference']
    rows = [{'path': ['motion', 'programs', 0], 'selectionScope': {'scope': 'entry not executed'},
             'selectedProgram': {'observations': [{'expression': 'charge damage velocity ' * 100,
                                                   'unresolved': 'unknown live owner'}],
                                 'coverage': 'partial', 'unresolved': ['unknown hook']}}]
    return p['attackReference'], unpack_attack_tables(attack), rows


def test_whole_source_replaces_graph_but_preserves_qualifiers_and_inputs():
    ref, attack, rows = inputs(); before = copy.deepcopy((ref, attack, rows))
    out = strict_source_diagnostics(rows, ref, attack, [])
    assert 'selectedProgram' not in out[0]
    assert out[0]['selectedSource'] == 'unchanged_verified_whole_method'
    assert out[0]['nativeCSharpSourceRef'] == 's0'
    assert out[0]['selectionScope'] == rows[0]['selectionScope']
    assert {'path': ['observations', 0, 'unresolved'], 'value': 'unknown live owner'} in out[0]['selectedProgramQualifiers']
    assert (ref, attack, rows) == before


@pytest.mark.parametrize('kind', ['missing-token', 'wrong-token', 'wrong-module', 'wrong-il',
                                  'unknown-program', 'no-source', 'changed-code', 'ambiguous',
                                  'wrong-path', 'approximate-replacement', 'regional', 'tiny'])
def test_unproved_or_unhelpful_replacement_keeps_graph(kind):
    ref, attack, rows = inputs(); removed = []
    graph = ref['motion']['programs'][0]
    if kind == 'missing-token': graph.pop('metadataToken')
    if kind == 'wrong-token': graph['metadataToken'] += 1
    if kind == 'wrong-module': graph['sourceModuleVersionId'] = 'other'
    if kind == 'wrong-il': graph['sourceMethodSha256'] = '0' * 64
    if kind == 'unknown-program': rows[0]['selectedProgram']['futureEffects'] = [1]
    if kind == 'no-source': attack.pop('nativeCSharpSource')
    if kind == 'changed-code': attack['nativeCSharpSource']['records'][0]['code'] += '\nDamage();'
    if kind == 'ambiguous': attack['nativeCSharpSource']['records'].append(copy.deepcopy(attack['nativeCSharpSource']['records'][0]))
    if kind == 'wrong-path': rows[0]['path'] = ['collision']
    if kind == 'approximate-replacement': removed = [_definition(graph)]
    if kind == 'regional': ref['nativeCSharpSource']['records'][0]['coverage'] = 'conditional_ast_regions'
    if kind == 'tiny': rows[0]['selectedProgram'] = {'coverage': 'partial'}
    assert strict_source_diagnostics(rows, ref, attack, removed) == rows
