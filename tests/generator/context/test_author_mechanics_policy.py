"""Actual projection tests; native producer owns AST mutation/escape semantics."""
import copy
import hashlib
import pytest
from tests.generator.context.test_native_csharp_source_view import _parent
from infini_local.pipelines.context.parents import compact_projectile_profile
from infini_local.pipelines.context.mechanics_context import mechanics_context
from infini_local.pipelines.context.attack_tables import unpack_attack_tables

CODE='void NativeAI() { if (channel && mana >= 10) { if (charge == 180) EmitBeam(1.5f); if (scale >= 1) { width = height = 144; Damage(); } } }'

def fixture():
    p=_parent()['directProjectileRaw'];p['aiStyle']=1
    ref=p['attackReference'];r=ref['nativeCSharpSource']['records'][0]
    r['metadataToken']=0x06000001
    graph=ref['motion']['programs'][0];graph['metadataToken']=r['metadataToken']
    for c in p['referencedProjectiles']['sourceCalls']:c['metadataToken']=r['metadataToken']
    mech={k:copy.deepcopy(r[k])for k in ('method','sourceModuleVersionId','sourceMethodSha256','metadataToken','assemblySha256','graphPaths')}
    mech.update(code=CODE,codeSha256=hashlib.sha256(CODE.encode()).hexdigest(),coverage='approximate_identity_ast_method',
        receiverBinding='captured_actor_source_binding',identityPruning={'allowed':True,'refusal':None},unresolved=[],
        approximation='captured type/aiStyle assumed stable across opaque calls',excludedCallOffsets=[])
    p['mechanicsSource']={'source':'native_mechanics_source','version':1,'identity':{'type':1,'aiStyle':1},'records':[mech],
        'unresolved':[],'strictSourceRefusals':[]}
    return p

def test_actual_projection_chooses_exact_bound_source_and_preserves_gameplay_guards():
    p=fixture();original=copy.deepcopy(p);out=compact_projectile_profile(p)
    assert out['mechanicsSource']['authorSelection']['aliases']=={'s0':0}
    assert 'verifiedSourceRecords'not in out['mechanicsSource']
    model=mechanics_context({'directProjectile':out})
    assert model is not None
    rows=model['mechanics']['source']
    assert [r['code']for r in rows]==[CODE]
    assert not any('unresolvedNativeCSharpSourceRef'in str(r)for r in rows)
    assert 'opaque calls'in str(model)
    assert out['referencedProjectiles']['sourceCalls'][0]['sourceLocation']['scope'].startswith('raw_capture_strict_source_lines')
    assert p==original

@pytest.mark.parametrize('kind',['missing-token','wrong-token','wrong-module','wrong-il','wrong-assembly','changed-code','mutation','escape','unbound','partial','missing-graph-token','wrong-graph-token','ambiguous','wrong-profile'])
def test_uncertain_identity_or_incomplete_certificate_keeps_strict(kind):
    p=fixture();r=p['mechanicsSource']['records'][0]
    if kind=='missing-token':r.pop('metadataToken')
    elif kind=='wrong-token':r['metadataToken']+=1
    elif kind=='wrong-module':r['sourceModuleVersionId']='other-module'
    elif kind=='wrong-il':r['sourceMethodSha256']='f'*64
    elif kind=='wrong-assembly':r['assemblySha256']='f'*64
    elif kind=='changed-code':r['code']+=' // changed'
    elif kind in ('mutation','escape'):r['identityPruning']={'allowed':False,'refusal':kind}
    elif kind=='unbound':r['receiverBinding']='unproved'
    elif kind=='partial':r['coverage']='approximate_identity_ast_regions'
    elif kind=='missing-graph-token':p['attackReference']['motion']['programs'][0].pop('metadataToken')
    elif kind=='wrong-graph-token':p['attackReference']['motion']['programs'][0]['metadataToken']+=1
    elif kind=='ambiguous':p['mechanicsSource']['records'].append(copy.deepcopy(r))
    elif kind=='wrong-profile':p['type']=2
    original=copy.deepcopy(p);out=compact_projectile_profile(p)
    assert 'authorSelection'not in out['mechanicsSource']
    assert p==original


def test_incoming_selection_cannot_authorize_source_removal():
    p=fixture();p['mechanicsSource']['records'][0].pop('metadataToken')
    p['mechanicsSource']['authorSelection']={'aliases':{'s0':0}}
    out=compact_projectile_profile(p)
    assert 'authorSelection'not in out['mechanicsSource']


def test_matched_graph_body_removed_but_coverage_and_unmatched_kill_kept():
    from infini_local.pipelines.context.author_mechanics_policy import selected_diagnostics
    rows=[{'path':['motion','programs',0],'selectedProgram':{'coverage':'partial','unresolved':['unknown hook'],'observations':[1]},'unresolved':'capture bound'},
          {'path':['lifecycle','Kill'],'selectedProgram':{'observations':['Damage()']}}]
    result=selected_diagnostics(rows,[['motion','programs',0]])
    assert result[0]['sourceCoverage']=={'coverage':'partial','unresolved':['unknown hook']}
    assert result[0]['unresolved']=='capture bound' and result[1]==rows[1]


def test_identity_pruning_refusal_cannot_hide_a_child_even_with_stale_exclusions():
    from tests.generator.context.test_mechanics_context import _raw, _profile
    raw = _raw(); profile = raw['directProjectile']
    profile['mechanicsSource']['records'][0]['identityPruning'] = {'allowed': False, 'refusal': 'identity mutation'}
    profile['referencedProjectiles'] = {'sourceCalls': [
        {'at': 40, 'method': 'Projectile.AI', 'sourceMethodSha256': 'sha', 'sourceModuleVersionId': 'module'}],
        'references': [{'type': 32, 'sourceCallIndices': [0], 'profile': _profile(32)}]}
    before = copy.deepcopy(raw)
    card = mechanics_context(raw)['mechanics']
    assert [p['defaults']['type'] for p in card['projectiles']] == [31, 32]
    assert not card['uncertainty'].get('excludedChildProfiles')
    assert raw == before


def test_selected_source_location_binds_method_but_keeps_strict_line_scope():
    out=compact_projectile_profile(fixture())
    card=mechanics_context({'directProjectile':out})
    def walk(v):
        if isinstance(v,dict):
            if 'scope' in v and 'raw_capture_strict_source_lines' in str(v['scope']):yield v
            for x in v.values():yield from walk(x)
        elif isinstance(v,list):
            for x in v:yield from walk(x)
    locations=list(walk(card))
    assert locations
    assert all('sourceRecord' not in x and 'mechanicsSourceIndex' in x for x in locations)


def region_fixture():
    p=fixture(); ref=p['attackReference']; strict=ref['nativeCSharpSource']['records'][0]
    readable=p['mechanicsSource']['records'][0]
    guards=[{'field':'Terraria.Projectile.type','operator':'==','literal':1,'ilOffset':3,
             'scope':'only_if_original_guard_is_reached; enclosing_dispatch_unknown'}]
    windows=[{'field':'type','literal':1,'guardOffset':3}]
    strict.update(coverage='conditional_ast_regions',entryGuards=guards,coveredWindows=windows)
    strict['code']='// '+('large-source-comment '*3000)+'\n'+strict['code']
    strict['codeSha256']=hashlib.sha256(strict['code'].encode()).hexdigest()
    ref['motion']['programs'][0]['identityWindows']=copy.deepcopy(windows)
    readable.update(coverage='approximate_identity_ast_regions',entryGuards=copy.deepcopy(guards))
    return p


def test_exact_guarded_regions_use_canonical_window_validation_and_keep_entry_scope():
    p=region_fixture(); before=copy.deepcopy(p)
    out=compact_projectile_profile(p)
    assert out['mechanicsSource']['authorSelection']['aliases']=={'s0':0}
    model=mechanics_context({'directProjectile':out})['mechanics']
    row=next(r for r in model['source']if r.get('code')==CODE)
    assert row['coverage']=='approximate_identity_ast_regions'
    assert row['entryGuards'][0]['scope']=='only_if_original_guard_is_reached; enclosing_dispatch_unknown'
    assert 'whole_method'not in row['coverage']
    assert not model.get('sourceSlices')
    assert p==before


@pytest.mark.parametrize('kind',['guard-offset','guard-scope','missing-guard','missing-window','extra-window','unknown-graph-field','partial-coverage'])
def test_regional_selection_does_not_bypass_guards_or_canonical_graph_validation(kind):
    p=region_fixture(); ref=p['attackReference']; strict=ref['nativeCSharpSource']['records'][0]
    readable=p['mechanicsSource']['records'][0];graph=ref['motion']['programs'][0]
    if kind=='guard-offset':readable['entryGuards'][0]['ilOffset']+=1
    elif kind=='guard-scope':readable['entryGuards'][0]['scope']='different scope'
    elif kind=='missing-guard':readable['entryGuards']=[]
    elif kind=='missing-window':strict['coveredWindows']=[]
    elif kind=='extra-window':graph['identityWindows'].append({'field':'type','literal':1,'guardOffset':5})
    elif kind=='unknown-graph-field':graph['futureRuntimeEffect']={'mustKeep':True}
    elif kind=='partial-coverage':readable['coverage']='some_partial_excerpt'
    out=compact_projectile_profile(p)
    assert 'authorSelection'not in out['mechanicsSource']


@pytest.mark.parametrize('factory',[fixture,region_fixture])
@pytest.mark.parametrize('kind',['stale-reference','bool-reference','bool-profile','bool-mechanics','missing-reference','unknown-identity-axis'])
def test_exact_typed_identity_must_bind_profile_mechanics_and_reference(factory,kind):
    p=factory();ref=p['attackReference']
    if kind=='stale-reference':ref['identityPredicates']={'Projectile.type':999,'Projectile.aiStyle':999}
    elif kind=='bool-reference':ref['identityPredicates']['Projectile.type']=True
    elif kind=='bool-profile':p['type']=True
    elif kind=='bool-mechanics':p['mechanicsSource']['identity']['type']=True
    elif kind=='missing-reference':ref.pop('identityPredicates')
    elif kind=='unknown-identity-axis':ref['identityPredicates']['Projectile.owner']=0
    before=copy.deepcopy(p);out=compact_projectile_profile(p)
    assert 'authorSelection'not in out['mechanicsSource']
    assert p==before


"""Synthetic contracts: exact source admission and real Author handoff behavior."""
import copy
import hashlib
import pytest
from infini_local.pipelines.context.whole_method_author import prepare_whole_method_author, apply_whole_method_author
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from infini_local.pipelines.context.mechanics_context import mechanics_context


def whole_method_parent():
    profile = fixture()
    source = profile['attackReference']['nativeCSharpSource']['records'][0]
    code = 'void NativeAI() { Hook(ref type); if (type == 247 && active) Spawn(248); if (type == 757) Spawn(928); scale *= 2; }'
    source.update(code=code, codeSha256=hashlib.sha256(code.encode()).hexdigest(), locations=[])
    profile['mechanicsSource']['records'][0]['excludedCallOffsets'] = [10]
    return {'name': 'Source fixture', 'directProjectileRaw': profile, 'parentSourceGraph': {
        'source': 'parent_reachable_compiled_source_graph', 'version': 1, 'roots': [],
        'members': [{'name': 'Fixture.NativeAI()', 'module': 0}],
        'modules': [{'assembly': 'Fixture', 'mvid': 'fixture-module'}],
        'nodes': [{'id': 0, 'method': 0, 'static': False, 'arguments': [], 'sha256': 'a' * 64,
                   'values': {str(i): ['ldarg', 0, [], i] for i in range(100)},
                   'statements': ['10'], 'blocks': [], 'possibleLocalWrites': {'1': ['3']},
                   'unresolved': ['opaque hook'], 'coverage': 'source_slice'}],
        'edges': [{'from': 0, 'to': 0, 'at': 10, 'context': ['9'], 'kind': 'helper_source'}],
        'unresolved': ['execution unknown'], 'completeness': 'partial_source_graph'}}


def test_full_source_is_only_method_body_and_retains_hook_conditions_and_child():
    original = whole_method_parent(); saved = copy.deepcopy(original)
    prepared, choices = prepare_whole_method_author(original)
    assert choices and original == saved
    assert prepared['directProjectileRaw']['mechanicsSource']['records'] == []
    raw = mechanics_context(raw_parent_card_for_llm(prepared)['raw'])
    assert apply_whole_method_author(raw, choices)
    node = raw['item']['parentSourceGraph']['nodes'][0]
    assert not {'values', 'statements', 'blocks', 'possibleLocalWrites'} & set(node)
    code = raw['mechanics']['source'][node['bodySource']['mechanicsSourceIndex']]['code']
    assert code == saved['directProjectileRaw']['attackReference']['nativeCSharpSource']['records'][0]['code']
    assert 'Hook(ref type)' in code and 'type == 247 && active' in code and 'type == 757' in code
    assert not raw['mechanics']['uncertainty']['excludedChildProfiles']
    assert 2 in [r['defaults'].get('type') for r in raw['mechanics']['projectiles']]
    edge = raw['item']['parentSourceGraph']['edges'][0]
    assert edge['context']['argumentBindings'] == [{'sourceILValue': '9', 'input': 'this', 'identityAfterHooks': 'unknown'}]
    assert node['unresolved'] == ['opaque hook']


@pytest.mark.parametrize('change', ['mvid','sha','signature','token','code','ambiguous','region','unknown-mechanics',
    'unknown-graph','missing-members','bad-member','bool-member','missing-call-input','missing-argument','static','parameters','duplicate-id','generated'])
def test_uncertainty_keeps_original_graph_and_approximation(change):
    item=whole_method_parent();profile=item['directProjectileRaw'];g=item['parentSourceGraph'];r=profile['attackReference']['nativeCSharpSource']['records'][0]
    if change=='mvid':g['modules'][0]['mvid']='other'
    elif change=='sha':g['nodes'][0]['sha256']='d'*64
    elif change=='signature':g['members'][0]['name']='Fixture.NativeAI(System.Int32)'
    elif change=='token':r['metadataToken']+=1
    elif change=='code':r['code']+='tampered'
    elif change=='ambiguous':profile['mechanicsSource']['records'].append(copy.deepcopy(profile['mechanicsSource']['records'][0]))
    elif change=='region':r['coverage']='conditional_ast_regions'
    elif change=='unknown-mechanics':profile['mechanicsSource']['records'][0]['futureGameplayFact']=1
    elif change=='unknown-graph':g['nodes'][0]['futureGuard']=1
    elif change=='missing-members':g.pop('members')
    elif change=='bad-member':g['nodes'][0]['method']=999
    elif change=='bool-member':g['nodes'][0]['method']=False
    elif change=='missing-call-input':g['nodes'][0]['values']['9']=['call',{'member':0},['absent'],0]
    elif change=='missing-argument':g['nodes'][0]['values'].pop('9')
    elif change=='static':g['nodes'][0]['static']=True
    elif change=='parameters':g['nodes'][0]['arguments']=['int x']
    elif change=='duplicate-id':g['nodes'].append(copy.deepcopy(g['nodes'][0]))
    elif change=='generated':item['generatedData']={'id':'generated'}
    saved=copy.deepcopy(item);prepared,choices=prepare_whole_method_author(item)
    assert choices==[] and prepared==saved and item==saved


def test_existing_missing_call_argument_remains_unknown_and_never_becomes_this():
    item=whole_method_parent();edge=item['parentSourceGraph']['edges'][0]
    edge.update(context=['1000'],sourceCoverage='callsite_omitted_from_source_slice',unresolved='identity unknown')
    prepared, choices = prepare_whole_method_author(item)
    raw=mechanics_context(raw_parent_card_for_llm(prepared)['raw'])
    assert apply_whole_method_author(raw,choices)
    assert raw['item']['parentSourceGraph']['edges'][0]['context']['argumentBindings']==[{'sourceILValue':'1000','unresolved':'identity unknown'}]


def test_emitted_source_mismatch_refuses_all_body_changes():
    prepared, choices=prepare_whole_method_author(whole_method_parent())
    raw=mechanics_context(raw_parent_card_for_llm(prepared)['raw'])
    raw['mechanics']['source'][0]['code']+='changed'
    before=copy.deepcopy(raw)
    assert not apply_whole_method_author(raw,choices) and raw==before


def test_unknown_sibling_profile_refuses_entire_shared_definition():
    item=whole_method_parent()
    item['effectiveProjectileRaw']=copy.deepcopy(item['directProjectileRaw'])
    item['effectiveProjectileRaw']['mechanicsSource']['records'][0]['futureGameplayFact']={'mustKeep':True}
    before=copy.deepcopy(item)
    prepared, choices=prepare_whole_method_author(item)
    assert not choices and prepared==before and item==before


def test_conditional_fact_value_borrowing_keeps_original_body():
    item=whole_method_parent()
    item['parentSourceGraph']['nodes'][0]['conditionalFacts']=[{'sourceSlice':{'valuesInNode':['9']}}]
    before=copy.deepcopy(item)
    prepared, choices=prepare_whole_method_author(item)
    assert not choices and prepared==before and item==before


def test_unknown_edge_context_cannot_hide_a_value_reference():
    item=whole_method_parent()
    item['parentSourceGraph']['edges'][0]['context']={'receiver':'9'}
    before=copy.deepcopy(item)
    prepared, choices=prepare_whole_method_author(item)
    assert not choices and prepared==before and item==before


def test_unrelated_metadata_is_not_a_source_owner():
    item=whole_method_parent()
    item['unrelatedMetadata']={'profile':copy.deepcopy(item['directProjectileRaw'])}
    item['unrelatedMetadata']['profile']['mechanicsSource']['records'][0]['futureGameplayFact']=1
    saved=copy.deepcopy(item['unrelatedMetadata'])
    prepared,choices=prepare_whole_method_author(item)
    assert choices and prepared['unrelatedMetadata']==saved


def graph_with_unused_tables():
    return {
        'source': 'parent_reachable_compiled_source_graph', 'version': 1, 'roots': [],
        'modules': [{'assembly': 'Unused', 'mvid': 'unused'}, {'assembly': 'A', 'mvid': 'a'},
                    {'assembly': 'B', 'mvid': 'b'}],
        'members': [{'name': 'Old()', 'module': 0}, {'name': 'Same()', 'module': 1},
                    {'name': 'RemovedField', 'module': 1}, {'name': 'Same()', 'module': 2},
                    {'name': 'Receiver', 'module': 2}],
        'nodes': [
            {'id': 10, 'method': 1, 'receiverType': 4, 'originReceiverType': 4,
             'bodySource': {'mechanicsSourceIndex': 0, 'representation': 'unchanged_verified_whole_method',
                            'metadataToken': 42}, 'unresolved': ['hook may mutate identity']},
            {'id': 20, 'method': 3, 'values': {'1': ['call', {'member': 1}, [], 0],
                                             '2': ['call', {'member': 1}, [], 1]},
             'statements': ['1', '2'], 'blocks': [['entry', ['1', '2']]],
             'possibleLocalWrites': {'0': ['1', '2']}}],
        'edges': [{'from': 10, 'to': 20, 'at': 5, 'context': {'argumentBindings': []}, 'kind': 'helper_source'}],
        'unresolved': ['not execution'], 'completeness': 'partial_source_graph'}


def resolved_graph_tables(graph):
    """Independent semantic oracle: replace every lookup by its literal row."""
    g = copy.deepcopy(graph)
    members, modules = g.pop('members'), g.pop('modules')
    for member in members:
        member['module'] = modules[member['module']]
    for node in g['nodes']:
        for key in ('method', 'receiverType', 'originReceiverType'):
            if key in node:
                node[key] = copy.deepcopy(members[node[key]])
        for value in node.get('values', {}).values():
            if isinstance(value[1], dict):
                value[1] = {'member': copy.deepcopy(members[value[1]['member']])}
    return g


def test_source_substitution_compacts_only_unused_lookup_rows_without_new_notation():
    from infini_local.pipelines.context.whole_method_author import _compact_graph_tables
    graph = graph_with_unused_tables(); before = copy.deepcopy(graph)
    assert _compact_graph_tables(graph)
    assert len(graph['members']) == 3 and len(graph['modules']) == 2
    assert resolved_graph_tables(graph) == resolved_graph_tables(before)
    # Same member name in different assemblies is not a duplicate; both calls
    # and their multiplicity/position remain, along with guards and uncertainty.
    assert graph['nodes'][0]['method'] != graph['nodes'][1]['method']
    assert len(graph['nodes'][1]['values']) == 2
    compacted = copy.deepcopy(graph)
    assert not _compact_graph_tables(graph) and graph == compacted


@pytest.mark.parametrize('change', ['roots', 'version', 'source', 'no-substitution', 'unknown-graph',
    'unknown-node', 'unknown-member', 'unknown-module', 'unknown-edge', 'omissions',
    'block-member', 'edge-member', 'rootless-method-metadata', 'invalid-member', 'bool-member',
    'invalid-module', 'operand-shape', 'value-shape', 'fragments', 'member-metadata', 'module-metadata'])
def test_uncertain_table_namespace_remains_byte_for_byte(change):
    from infini_local.pipelines.context.whole_method_author import _compact_graph_tables
    graph = graph_with_unused_tables()
    if change == 'roots': graph['roots'] = [{'node': 10, 'receiverType': 'A.Receiver'}]
    elif change == 'version': graph['version'] = 2
    elif change == 'source': graph['source'] = 'future_graph'
    elif change == 'no-substitution': graph['nodes'][0].pop('bodySource')
    elif change == 'unknown-graph': graph['futureTable'] = [0]
    elif change == 'unknown-node': graph['nodes'][0]['futureTable'] = [0]
    elif change == 'unknown-member': graph['members'][0]['future'] = 0
    elif change == 'unknown-module': graph['modules'][0]['future'] = 0
    elif change == 'unknown-edge': graph['edges'][0]['future'] = 0
    elif change == 'omissions': graph['transportOmissions'] = {'unknownFieldCount': 1}
    elif change == 'block-member': graph['nodes'][1]['blocks'] = [{'member': 0}]
    elif change == 'edge-member': graph['edges'][0]['context']['member'] = 0
    elif change == 'rootless-method-metadata': graph['limits'] = {'method': 0}
    elif change == 'invalid-member': graph['nodes'][1]['values']['1'][1]['member'] = 99
    elif change == 'bool-member': graph['nodes'][0]['receiverType'] = False
    elif change == 'invalid-module': graph['members'][0]['module'] = 99
    elif change == 'operand-shape': graph['nodes'][1]['values']['1'][1]['future'] = 0
    elif change == 'value-shape': graph['nodes'][1]['values']['1'].append(0)
    elif change == 'fragments': graph['nodes'][1]['fragments'] = [[0, 1, 2]]
    elif change == 'member-metadata': graph['members'][0]['returns'] = {'futureIndex': 0}
    elif change == 'module-metadata': graph['modules'][0]['assembly'] = ['future', 0]
    before = copy.deepcopy(graph)
    assert not _compact_graph_tables(graph) and graph == before


def test_actual_whole_source_handoff_drops_lookups_used_only_by_superseded_body():
    item = whole_method_parent()
    graph = item['parentSourceGraph']
    graph['modules'].append({'assembly': 'Other', 'mvid': 'other'})
    graph['members'].append({'name': 'FieldInFullSource', 'module': 1})
    graph['nodes'][0]['values']['8'] = ['ldfld', {'member': 1}, ['7'], 8]
    before = copy.deepcopy(item)
    prepared, choices = prepare_whole_method_author(item)
    raw = mechanics_context(raw_parent_card_for_llm(prepared)['raw'])
    assert apply_whole_method_author(raw, choices)
    assert len(raw['item']['parentSourceGraph']['members']) == 1
    assert len(raw['item']['parentSourceGraph']['modules']) == 1
    assert item == before
    assert raw['mechanics']['source'][0]['code'] == before['directProjectileRaw']['attackReference']['nativeCSharpSource']['records'][0]['code']
