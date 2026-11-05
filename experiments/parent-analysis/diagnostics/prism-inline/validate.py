import json, pathlib, hashlib
p=pathlib.Path(__file__).resolve().parent
rows=[];checks=0
for t in [632,455,461,537,642]:
 d=p/f'{t}-sparse'; logs=[json.loads(x) for x in (p/f'{t}-sparse.log').read_text().splitlines() if x.startswith('{')]
 assert not [x for x in logs if x.get('error')], (t,'harness_error'); checks+=1
 w=json.loads((d/'windows.json').read_text());w=next(x for x in w if x['field']=='aiStyle');assert (w['raw'],w['meaningful'])==(3013,2357);checks+=1
 a=json.loads((d/'selected_dispatch.json').read_text());b=json.loads((d/'selected_effects.json').read_text())
 for key,pk in [('observations','at'),('predicates','id')]:
  expanded={x[pk]:x for x in b[key]}
  assert len(expanded)==len(b[key]);checks+=1
  for x in a[key]:assert expanded[x[pk]]==x,(t,key,x);checks+=1
 for key in ['symbols','dependencies']:
  for k,v in a[key].items():assert b[key][k]==v,(t,key,k);checks+=1
 # Explicit roots bypass existing unknown-call reporting; preserve its warnings,
 # and explicitly retain call/memory unresolvedness rather than claim completeness.
 b['unresolved']=list(dict.fromkeys(a.get('unresolved',[])+b.get('unresolved',[])+['generic_effect_root_diagnostic_only; callee_effects_and_array_memory_reaching_writes_remain_unproved']))
 for v in a.get('unresolved',[]):assert v in b['unresolved'];checks+=1
 (d/'selected_effects.preserved.json').write_text(json.dumps(b,ensure_ascii=False,separators=(',',':'))+'\n')
 local=[x for x in logs if 'storedCells' in x]
 assert len(local)==4 and all(x['allLocals']==1774 and x['usedLocals']==97 for x in local);checks+=1
 by={(x['label'],x['variant']):x for x in local}
 for label in ['raw','selected']:
  dense,sparse=[by[label,k] for k in ['dense','sparse']]
  assert dense['passes']==sparse['passes'] and dense['assertions']==sparse['assertions'];checks+=1
 rows.append({'type':t,'baselineObservations':len(a['observations']),'genericEffectObservations':len(b['observations']),'baselineChars':len((d/'selected_dispatch.json').read_text()),'effectCharsBeforeWarningPreservation':len((d/'selected_effects.json').read_text()),'localSolver':local,'measurements':[x for x in logs if 'alloc' in x]})
# Exact 632 coverage additions. These are fixture assertions, not production routing.
a=json.loads((p/'632-sparse/selected_dispatch.json').read_text());b=json.loads((p/'632-sparse/selected_effects.json').read_text());old={x['at'] for x in a['observations']}; extra=[x for x in b['observations'] if x['at'] not in old]
assert len(extra)==6;checks+=1
assert sum(x.get('call')=='Projectile.set_Opacity' for x in extra)==3;checks+=1
assert any('Projectile.friendly' in x.get('expression','') and ',30)' in x.get('expression','') for x in extra);checks+=1
assert any(x.get('call')=='Collision.LaserScan' and x['arguments']['maxDistance']=='2400' and x['arguments']['samples']=='l1061@126997' for x in extra);checks+=1
assert any(x.get('call')=='Projectile.GetLastPrismHue' for x in extra);checks+=1
for f in ['selected_dispatch.json','selected_motion.json','identity.json']:
 assert json.loads((p/'632'/f).read_text())==json.loads((p/'632-sparse'/f).read_text());checks+=1
# Both ldloc/stloc and address-only locals are included in sparse source-set.
il=json.loads((p/'632-sparse/VanillaAI.il.json').read_text());il=[x for x in il if 123508<=x['at']<131901]
used={x['arg'] for x in il if x['op'] in ['ldloc','stloc','ldloca']};assert len(used)==97;checks+=1
manifest={}
for f in [p/'MeasureSlice.cs',p/'validate.py',p.parent/'ifc-magic-audit-20261105/helper-final-native/EngineRuntimeChecks.dll',p.parent/'ifc-magic-audit-20261105/helper-final-native/tModLoader.dll',p.parent/'last-prism-source-20261105/Projectile.cs']:
 manifest[str(f.relative_to(p.parent))]=hashlib.sha256(f.read_bytes()).hexdigest()
result={'checks':checks,'sourceOnly':True,'productionChanged':False,'gitOperations':False,'LLMCalls':False,'budgetBypassOnlyInHarness':True,'sourceManifest':manifest,'rows':rows}
(p/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'checks':checks,'types':len(rows),'sourceOnly':True,'errors':0,'summary':str(p/'summary.json')}))
