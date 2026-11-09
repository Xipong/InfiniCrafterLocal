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
