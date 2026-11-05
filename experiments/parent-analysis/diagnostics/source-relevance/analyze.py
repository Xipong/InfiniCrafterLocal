"""Offline source-evidence audit. No production changes, model calls or network.
All identity literals and branch targets come from the captured source.
"""
from pathlib import Path
import collections, json, re, sys, hashlib
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'ifc-parent-graph-prototype-20261105'))
import evaluate
from infini_local.pipelines.context.attack_tables import pack_attack_tables


def size(x):return len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
def closure(p):
    deps=p['dependencies']; predicates={x['id']:x for x in p['predicates']}; lookup={**deps,**predicates}
    keys=set(lookup)
    pattern=re.compile(r'(?<![a-zA-Z0-9_@])('+'|'.join(re.escape(x) for x in sorted(keys,key=len,reverse=True))+r')(?![a-zA-Z0-9_@])') if keys else None
    def refs(obj):
        if type(obj)==str:return set(pattern.findall(obj)) if pattern else set()
        if type(obj)==dict:return set().union(*(refs(v) for k,v in obj.items() if k!='id'))
        if type(obj)==list:return set().union(*(refs(v) for v in obj))
        return set()
    reached=refs(p['observations']); todo=list(reached)
    while todo:
        n=todo.pop()
        for k in refs(lookup[n])-reached: reached.add(k);todo.append(k)
    return {'dependencyCount':len(deps),'predicateCount':len(predicates),'observations':len(p['observations']),
            'orphanDependencies':sorted(set(deps)-reached),'orphanPredicates':sorted(set(predicates)-reached),
            'coverageCriterion':'Every observation is a root; traverse expression/arguments/receiver, every orderedSourceUses member, all requiredPredicates, predicate inputs, embedded alternatives/source_block guard references; IDs match exact token boundaries.'}

rows=[]
for file in sorted((ROOT/'ifc-magic-audit-20261105/context-cards-helper-final').glob('*.json')):
    source=json.loads(file.read_text())
    if 'cards' not in source:continue
    facing=evaluate.attack_walk(source['cards']['author'],mode='baseline')
    for path,p in evaluate.programs(facing):
        rows.append({'parent':file.stem,'path':path,**closure(p)})

packetfile=ROOT/'ifc-magic-audit-20261105/capture-helper-final/LastPrism.packet.json'
packet=json.loads(packetfile.read_text()); raw=packet['itemA']['directProjectileRaw']['attackReference']['motion']['programs'][0]['identitySelected']
cfg=json.loads((HERE/'LastPrism.full-cfg.json').read_text()); blocks={b['start']:b['next'] for b in cfg['blocks']}; values={v['id']:v for v in cfg['values']}; selected={int(k):v for k,v in cfg['selected'].items()}
def reach(start,selected):
    visited=set(); todo=[start]
    while todo:
        b=todo.pop()
        if b in visited:continue
        visited.add(b);todo.extend([selected[b]] if b in selected else blocks.get(b,[]))
    return visited
reached=reach(min(blocks),selected); assert reached==set(cfg['reachable'])
hazards=[h['value'] for h in cfg['hazards'] if h['reachable']]

# Deliberately INVALID counterfactual: assume captured identity never changes.
# Count what stronger side-effect proof would need to justify, not an optimized program.
identity={'type':cfg['identity']['type'],'aiStyle':cfg['identity']['style']}
def actor(id,seen=frozenset()):
    if id in seen:return False
    v=values[id]
    return (v['op']=='ldarg' and v['operand']=='0') or (v['op'] in ['ldloc','stloc'] and len(v['inputs'])==1 and actor(v['inputs'][0],seen|{id}))
def literal(id,seen=frozenset()):
    if id in seen:return None,False
    v=values[id]; op=v['op']; ins=v['inputs']; operand=v['operand']; seen=seen|{id}
    if op=='const':
        try:return int(operand),False
        except (ValueError,TypeError):return None,False
    if op=='ldfld' and v.get('operandOwner')=='Terraria.Projectile' and operand and operand.rsplit(' ',1)[-1] in identity and len(ins)==1 and actor(ins[0]): return identity[operand.rsplit(' ',1)[-1]],True
    if op in ['ldloc','stloc','conv.i4','conv.u4'] and len(ins)==1:return literal(ins[0],seen)
    if op in ['sub','ceq','clt','clt.un','cgt','cgt.un'] and len(ins)==2:
        a,ai=literal(ins[0],seen);b,bi=literal(ins[1],seen)
        if a is None or b is None:return None,False
        aa=(a&0xffffffff) if op.endswith('.un') else a;bb=(b&0xffffffff) if op.endswith('.un') else b
        return ({'sub':(a-b+2**31)%2**32-2**31,'ceq':int(a==b),'clt':int(aa<bb),'clt.un':int(aa<bb),'cgt':int(aa>bb),'cgt.un':int(aa>bb)}[op],ai or bi)
    return None,False
unsafe=dict(selected)
for v in values.values():
    ns=blocks[v['block']]
    if len(ns)!=2:continue
    lits=[literal(i) for i in v['inputs']]
    if len(lits)!=2 or not any(x[1] for x in lits) or any(x[0] is None for x in lits):continue
    a,b=(x[0] for x in lits);op=v['op'];take=None
    if op in ['bne.un','bne.un.s']:take=a!=b
    if op in ['beq','beq.s']:take=a==b
    if take is not None:unsafe[v['block']]=ns[0 if take else 1]
unsafe_reached=reach(min(blocks),unsafe)
unsafe_obs=[r for r in raw['observations'] if r['block'] in unsafe_reached]

# Verify every current observation, scalar and alias-use source record is reachable
# under the ACTUAL certified selector. A predicate's source block comes from actual IL.
current_unreachable=[]
for kind,records in [('observation',raw['observations']),('predicate',raw['predicates'])]:
    for r in records:
        block=r.get('block',values[str(r['at'])]['block'])
        if block not in reached:current_unreachable.append([kind,r.get('at'),block])
for name,row in raw['dependencies'].items():
    for r in row.get('orderedSourceUses',[row]):
        if r['block'] not in reached:current_unreachable.append(['dependency/'+name,r.get('at'),r['block']])

# Earliest hazards reaching first remaining direct identity read.
late_identity=[v for v in values.values() if v['op']=='ldfld' and v['operand']=='Int32 type' and v['block'] in reached and v['at']>min(h['at'] for h in hazards)]
first=sorted(late_identity,key=lambda v:v['at'])[0]
reaching_hazards=[h for h in hazards if (h['block']==first['block'] and h['at']<first['at']) or (h['block']!=first['block'] and first['block'] in reach(h['block'],selected))]

summary={'corpusPrograms':len(rows),'corpusParents':len(set(r['parent'] for r in rows)),'corpusOrphanDependencies':sum(len(r['orphanDependencies']) for r in rows),'corpusOrphanPredicates':sum(len(r['orphanPredicates']) for r in rows),'corpus':rows,
'lastPrism':{'rawProgramChars':size(raw),'facingUnpackedChars':size(json.loads((HERE/'LastPrism.baseline-program.json').read_text())),'closure':closure(raw),'totalBlocks':len(blocks),'certifiedSelectedEdges':len(selected),'reachableBlocks':len(reached),'reachableHazards':hazards,'currentUnreachableEvidenceRows':current_unreachable,'firstLateIdentityRead':first,'hazardsReachingFirstLateRead':reaching_hazards,
'INVALID_fixedIdentityCounterfactual':{'warning':'NOT an accepted optimization. Ignores all identity hazards and mutable callback effects. Cannot preserve strict baseline facts or unknowns. These are only conditional counts, not savings.','reachableBlocks':len(unsafe_reached),'observationCount':len(unsafe_obs),'removedObservationCount':len(raw['observations'])-len(unsafe_obs),'chosenEdges':len(unsafe),'remainingObservationKinds':dict(collections.Counter(x['kind'] for x in unsafe_obs))}},
'limits':['All baseline observations treated as relevant; no weapon-name/ID routing or model choices.', 'This proves reference closure and source-CFG reachability, not native gameplay equivalence, hook purity, or original extraction completeness.', 'Counterfactual is intentionally unaccepted and is not used to rewrite any production or model-facing packet.'],
'sourceHashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [packetfile,HERE/'LastPrism.full-cfg.json',ROOT/'ifc-magic-audit-20261105/helper-final-native/tModLoader.dll',ROOT/'ifc-magic-audit-20261105/helper-final-native/EngineRuntimeChecks.dll']},'network':'NotRun','model':'NotRun','git':'NotRun','productionChanges':'None'}
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['corpus','sourceHashes']},indent=2))
