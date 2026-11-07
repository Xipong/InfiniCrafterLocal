// Executes the actual Actions owner; only GitHub I/O is simulated.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const owner=require('../../tools/build/release_github.js');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const sha='a'.repeat(40),old='b'.repeat(40),tag='v0.5.5';
const names=['InfiniCrafterLocal.tmod','InfiniCrafterLocal_0.5.5_Source_and_LocalGenerator.zip','build-provenance.json','package-verification.json','release-provenance.json','SHA256SUMS.txt'].sort();
async function scenario(mode){
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'release-replace-'));
 Object.assign(process.env,{RUNNER_TEMP:temp,CI_RUN:'12',BACKUP_ARTIFACT_ID:'90',BACKUP_ARTIFACT_DIGEST:'d'.repeat(64),GITHUB_RUN_ATTEMPT:'1'});
 const writes=[],deleted=[],bytes=new Map();let tagSha=old,tick=0,nextId=100;
 let release={id:3,tag_name:tag,target_commitish:old,name:tag,body:'original',draft:false,prerelease:false,immutable:false,updated_at:'original'};
 let assets=names.map((name,i)=>{const data=Buffer.from('old:'+name);bytes.set(i+1,data);return{id:i+1,name,label:null,size:data.length,digest:'sha256:'+hash(data),state:'uploaded',updated_at:'original'};});
 const state=()=>({id:release.id,tag:release.tag_name,target:release.target_commitish,name:release.name,body:release.body,draft:release.draft,prerelease:release.prerelease,immutable:release.immutable,updated:release.updated_at,assets:assets.map(a=>({id:a.id,name:a.name,label:a.label,size:a.size,digest:a.digest,state:a.state,updated:a.updated_at})).sort((a,b)=>a.id-b.id)});
 if(mode==='existingSection')release.body='Useful original notes\n<!-- infini-verified-rebuild:begin -->old rebuild<!-- infini-verified-rebuild:end -->\nMore notes';
 if(mode==='malformedSection')release.body='Useful original notes\n<!-- infini-verified-rebuild:begin -->unfinished';
 if(mode==='duplicateSection')release.body='Notes<!-- infini-verified-rebuild:begin --><!-- infini-verified-rebuild:begin --><!-- infini-verified-rebuild:end -->';
 if(mode==='foreignAsset')assets.push({...assets[0],id:99,name:'foreign-note.txt'});
 const input={apply:mode==='dry'?'false':'true',confirm_asset_replacement:['dry','unconfirmed'].includes(mode)?'false':'true',tag,target_sha:sha,expected_old_tag:old,release_id:'3',expected_snapshot:hash(JSON.stringify(state()))};
 const context={repo:{owner:'Xipong',repo:'InfiniCrafterLocal'},eventName:'workflow_dispatch',ref:'refs/heads/main',sha,runId:50,payload:{inputs:input}};
 const run={id:12,head_sha:sha,head_branch:'main',event:'push',status:'completed',conclusion:'success'};
 const backupArtifact={id:90,name:'release-backup-50-1',digest:'sha256:'+'d'.repeat(64),expired:false,expires_at:new Date(Date.now()+90*86400000).toISOString(),workflow_run:{id:50}};
 if(mode==='backupExpired')backupArtifact.expired=true;
 if(mode==='backupExpiryPast')backupArtifact.expires_at=new Date(Date.now()-1000).toISOString();
 if(mode==='backupExpiryInvalid')backupArtifact.expires_at='unknown';
 if(mode==='backupWrongRun')backupArtifact.workflow_run.id=51;
 if(mode==='backupWrongName')backupArtifact.name='unrelated';
 if(mode==='backupWrongDigest')backupArtifact.digest='sha256:'+'0'.repeat(64);
 const outputs={},core={setOutput:(k,v)=>outputs[k]=v,info:()=>{}};
 const clone=x=>JSON.parse(JSON.stringify(x));
 const github={rest:{git:{
  getRef:async a=>({data:{object:{sha:a.ref==='heads/main'?(mode==='wrongMain'?'c'.repeat(40):sha):tagSha,type:'commit'}}}),
  updateRef:async a=>{writes.push('tag');assert.equal(a.ref,'tags/v0.5.5');if(mode==='tagFailure')throw Error('tag rejected');tagSha=a.sha;if(mode==='afterTag')throw Error('uncertain response');}
 },repos:{
  getRelease:async()=>({data:clone(release)}),listReleaseAssets:'assets',getReleaseAsset:async a=>({data:mode==='badBackup'?Buffer.from('bad'):bytes.get(a.asset_id)}),
  updateRelease:async a=>{
   writes.push(a.draft===true?'draft':a.draft===false?'publish':'body');
   if(mode==='bodyFailure'&&a.body)throw Error('body failed');
   if(release.draft&&a.target_commitish&&!a.tag_name&&mode==='serverNormalizesTag')release.tag_name='untagged-regression';
   for(const k of ['draft','body','target_commitish','tag_name'])if(k in a)release[k]=a[k];
   if(mode==='serverTagChange'&&a.target_commitish)release.tag_name='untagged-regression';
   release.updated_at=String(++tick);return{data:clone(release)};
  },
  updateReleaseAsset:async a=>{writes.push('stage');assert.equal(release.draft,true);const row=assets.find(x=>x.id===a.asset_id);row.name=a.name;row.updated_at=String(++tick);release.updated_at=String(tick);if(mode==='externalRename')release.body='external edit';return{data:clone(row)};},
  uploadReleaseAsset:async a=>{writes.push('upload');if(mode==='uploadFailure')throw Error('upload failed');const row={id:nextId++,name:a.name,label:null,size:a.data.length,digest:'sha256:'+hash(a.data),state:'uploaded',updated_at:String(++tick)};assets.push(row);bytes.set(row.id,a.data);release.updated_at=String(tick);if(mode==='badUpload')row.digest='sha256:'+'0'.repeat(64);return{data:clone(row)};},
  deleteReleaseAsset:async a=>{
   writes.push('delete');assert.equal(release.draft,true);assert.equal(tagSha,old);
   // Destructive writes are never allowed until every new delivery is present and verified.
   for(const name of names){const rows=assets.filter(x=>x.name===name);assert.equal(rows.length,1);assert(rows[0].id>=100);assert.equal(rows[0].digest,'sha256:'+hash(bytes.get(rows[0].id)));}
   assert(a.asset_id>=1&&a.asset_id<=6);assert(!deleted.includes(a.asset_id));
   if(mode==='deleteFailure')throw Error('delete rejected');
   assets=assets.filter(x=>x.id!==a.asset_id);deleted.push(a.asset_id);release.updated_at=String(++tick);
   if(mode==='deleteUncertain')throw Error('delete response lost');
   if(mode==='externalDelete')release.body='external edit after delete';
   return{status:204};
  }
 },actions:{listWorkflowRuns:'runs',listWorkflowRunArtifacts:'artifacts',getWorkflowRun:async()=>({data:clone(run)}),getArtifact:async()=>({data:clone(backupArtifact)})}},
 paginate:async method=>method==='assets'?clone(assets):method==='runs'?[clone(run)]:[{id:4,name:'InfiniCrafterLocal-tmod',expired:mode==='expired'}]};
 if(mode==='wrongTag')tagSha='c'.repeat(40);
 if(mode==='immutable')release.immutable=true;
 if(mode==='staleSnapshot')release.body='external changed';
 if(mode==='failedCI')run.conclusion='failure';
 let error;
 try{
  await owner.inspectReplacement({github,context,core});
  assert.equal(fs.readdirSync(path.join(temp,'release-backup')).length,7);
  fs.mkdirSync(path.join(temp,'release-assets'));
  for(const name of names)fs.writeFileSync(path.join(temp,'release-assets',name),name==='release-provenance.json'?JSON.stringify({sourceCommit:sha,version:'0.5.5',ciRunId:'12'}):'new:'+name);
  if(mode==='ciChanged')run.conclusion='failure';
  if(mode==='releaseChanged')release.body='external after backup';
  if(mode==='noBackupReceipt')delete process.env.BACKUP_ARTIFACT_ID;
  await owner.replace({github,context,core});
 }catch(e){error=e;}
 const success=['good','existingSection','serverNormalizesTag'].includes(mode);
 if(success){
  assert.equal(error,undefined);assert(release.body.includes(mode==='existingSection'?'Useful original notes':'original'));
  if(mode==='existingSection'){assert(release.body.endsWith('More notes'));assert(!release.body.includes('old rebuild'));}
  assert.equal(release.body.split('<!-- infini-verified-rebuild:begin -->').length,2);
  assert.equal(tagSha,sha);assert.equal(release.draft,false);assert.equal(release.tag_name,tag);assert.equal(assets.length,6);
  assert.deepEqual(assets.map(a=>a.name).sort(),names);assert.deepEqual(deleted.sort((a,b)=>a-b),[1,2,3,4,5,6]);
  assert.equal(writes[0],'draft');assert.equal(writes.at(-1),'publish');assert.equal(writes.filter(x=>x==='upload').length,6);
  assert(writes.lastIndexOf('upload')<writes.indexOf('delete'));assert(writes.lastIndexOf('delete')<writes.indexOf('tag'));
  const receipt=JSON.parse(fs.readFileSync(path.join(temp,'replacement-recovery.json')));
  assert.equal(receipt.status,'published');assert.equal(receipt.backupArtifactExpiresAt,backupArtifact.expires_at);
 }else if(mode==='dry'){assert.equal(error,undefined);assert.deepEqual(writes,[]);assert.equal(tagSha,old);}
 else{
  assert(error,mode);assert(!writes.includes('publish'),mode);
  if(writes.includes('draft')){
   assert.equal(release.draft,true);const receipt=JSON.parse(fs.readFileSync(path.join(temp,'replacement-recovery.json')));
   assert.equal(receipt.status,'stopped-needs-reconciliation');assert(receipt.backupArtifactId);
   if(mode==='afterTag')assert.equal(receipt.observedAfterFailure.tag,sha);
   if(mode==='serverTagChange'){assert.equal(receipt.observedAfterFailure.state.tag,'untagged-regression');assert.equal(receipt.observedAfterFailure.state.draft,true);}
   if(mode==='deleteUncertain'){assert.equal(deleted.length,1);assert.equal(writes.filter(x=>x==='delete').length,1);assert.equal(receipt.observedAfterFailure.state.assets.length,11);}
  }else assert.deepEqual(writes,[]);
  if(['unconfirmed','backupExpired','backupExpiryPast','backupExpiryInvalid','backupWrongRun','backupWrongName','backupWrongDigest','foreignAsset'].includes(mode))assert.deepEqual(writes,[]);
 }
 fs.rmSync(temp,{recursive:true});
}
const cases=['good','existingSection','serverNormalizesTag','serverTagChange','malformedSection','duplicateSection','dry','unconfirmed','ciChanged','releaseChanged','wrongMain','wrongTag','immutable','staleSnapshot','failedCI','expired','badBackup','noBackupReceipt','backupExpired','backupExpiryPast','backupExpiryInvalid','backupWrongRun','backupWrongName','backupWrongDigest','foreignAsset','externalRename','uploadFailure','badUpload','deleteFailure','deleteUncertain','externalDelete','tagFailure','afterTag','bodyFailure'];
(async()=>{for(const name of process.argv[2]?[process.argv[2]]:cases)await scenario(name);console.log(`${process.argv[2]?1:cases.length} replacement behavior cases PASS`);})().catch(e=>{console.error(e);process.exitCode=1;});
