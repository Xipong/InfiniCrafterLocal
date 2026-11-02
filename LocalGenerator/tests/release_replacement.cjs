// Executes the actual Actions owner with an isolated in-memory GitHub API.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const owner=require('../../tools/build/release_github.js');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const sha='a'.repeat(40),old='b'.repeat(40),tag='v0.5.5';
const names=['InfiniCrafterLocal.tmod','InfiniCrafterLocal_0.5.5_Source_and_LocalGenerator.zip','build-provenance.json','package-verification.json','release-provenance.json','SHA256SUMS.txt'].sort();
async function scenario(mode){
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'release-replace-'));process.env.RUNNER_TEMP=temp;process.env.CI_RUN='12';process.env.BACKUP_ARTIFACT_ID='90';process.env.BACKUP_ARTIFACT_DIGEST='d'.repeat(64);
 const writes=[],bytes=new Map();let tagSha=old,tick=0,nextId=100;
 let release={id:3,tag_name:tag,target_commitish:old,name:tag,body:'original',draft:false,prerelease:false,immutable:false,updated_at:'original'};
 let assets=[...names,...names.map(n=>'previous-'+n)].map((name,i)=>{const data=Buffer.from('old:'+name);bytes.set(i+1,data);return{id:i+1,name,label:null,size:data.length,digest:'sha256:'+hash(data),state:'uploaded',updated_at:'original'};});
 const state=()=>({id:release.id,tag:release.tag_name,target:release.target_commitish,name:release.name,body:release.body,draft:release.draft,prerelease:release.prerelease,immutable:release.immutable,updated:release.updated_at,assets:assets.map(a=>({id:a.id,name:a.name,label:a.label,size:a.size,digest:a.digest,state:a.state,updated:a.updated_at})).sort((a,b)=>a.id-b.id)});
 if(mode==='existingSection')release.body='Useful original notes\n<!-- infini-verified-rebuild:begin -->old rebuild<!-- infini-verified-rebuild:end -->\nMore notes';
 if(mode==='malformedSection')release.body='Useful original notes\n<!-- infini-verified-rebuild:begin -->unfinished';
 if(mode==='duplicateSection')release.body='Notes<!-- infini-verified-rebuild:begin --><!-- infini-verified-rebuild:begin --><!-- infini-verified-rebuild:end -->';
 const input={apply:mode==='dry'?'false':'true',tag,target_sha:sha,expected_old_tag:old,release_id:'3',expected_snapshot:hash(JSON.stringify(state()))};
 const context={repo:{owner:'Xipong',repo:'InfiniCrafterLocal'},eventName:'workflow_dispatch',ref:'refs/heads/main',sha,payload:{inputs:input}};
 const run={id:12,head_sha:sha,head_branch:'main',event:'push',status:'completed',conclusion:'success'};
 const outputs={},core={setOutput:(k,v)=>outputs[k]=v,info:()=>{}};
 const clone=x=>JSON.parse(JSON.stringify(x));
 const github={rest:{git:{getRef:async a=>({data:{object:{sha:a.ref==='heads/main'?(mode==='wrongMain'?'c'.repeat(40):sha):tagSha,type:'commit'}}}),updateRef:async a=>{writes.push('tag');assert.equal(a.ref,'tags/v0.5.5');if(mode==='tagFailure')throw Error('tag rejected');tagSha=a.sha;if(mode==='afterTag')throw Error('uncertain response');}},repos:{
 getRelease:async()=>({data:clone(release)}),listReleaseAssets:'assets',getReleaseAsset:async a=>({data:mode==='badBackup'?Buffer.from('bad'):bytes.get(a.asset_id)}),
 updateRelease:async a=>{writes.push(a.draft===true?'draft':a.draft===false?'publish':'body');if(mode==='bodyFailure'&&a.body)throw Error('body failed');for(const k of ['draft','body','target_commitish'])if(k in a)release[k]=a[k];release.updated_at=String(++tick);return{data:clone(release)};},
 updateReleaseAsset:async a=>{writes.push('archive');const row=assets.find(x=>x.id===a.asset_id);row.name=a.name;row.updated_at=String(++tick);release.updated_at=String(tick);if(mode==='externalRename'){release.body='external edit';}return{data:clone(row)};},
 uploadReleaseAsset:async a=>{writes.push('upload');if(mode==='uploadFailure')throw Error('upload failed');const row={id:nextId++,name:a.name,label:null,size:a.data.length,digest:'sha256:'+hash(a.data),state:'uploaded',updated_at:String(++tick)};assets.push(row);bytes.set(row.id,a.data);release.updated_at=String(tick);if(mode==='badUpload')row.digest='sha256:'+'0'.repeat(64);return{data:clone(row)};}
 },actions:{listWorkflowRuns:'runs',listWorkflowRunArtifacts:'artifacts',getWorkflowRun:async()=>({data:clone(run)})}},paginate:async method=>method==='assets'?clone(assets):method==='runs'?[clone(run)]:[{id:4,name:'InfiniCrafterLocal-tmod',expired:mode==='expired'}]};
 if(mode==='wrongTag')tagSha='c'.repeat(40);
 if(mode==='immutable')release.immutable=true;
 if(mode==='staleSnapshot')release.body='external changed';
 if(mode==='failedCI')run.conclusion='failure';
 let error;
 try{
  await owner.inspectReplacement({github,context,core});
  assert.equal(fs.readdirSync(path.join(temp,'release-backup')).length,13);
  fs.mkdirSync(path.join(temp,'release-assets'));
  for(const name of names)fs.writeFileSync(path.join(temp,'release-assets',name),name==='release-provenance.json'?JSON.stringify({sourceCommit:sha,version:'0.5.5',ciRunId:'12'}):'new:'+name);
  if(mode==='ciChanged')run.conclusion='failure';
  if(mode==='releaseChanged')release.body='external after backup';
  if(mode==='noBackupReceipt')delete process.env.BACKUP_ARTIFACT_ID;
  if(mode==='collision'){
   // Pin a real collision as the expected initial state: it must fail before draft.
   const a=assets.find(a=>a.name===names[0]);assets.push({...a,id:99,name:`archive-${a.id}-${a.name}`});
   input.expected_snapshot=hash(JSON.stringify(state()));
   fs.writeFileSync(path.join(temp,'release-backup','snapshot.json'),JSON.stringify({tag:old,state:state()}));
  }
  await owner.replace({github,context,core});
 }catch(e){error=e;}
 if(['good','existingSection'].includes(mode)){
  assert.equal(error,undefined);assert(release.body.includes(mode==='good'?'original':'Useful original notes'));if(mode==='existingSection'){assert(release.body.endsWith('More notes'));assert(!release.body.includes('old rebuild'));}assert.equal(release.body.split('<!-- infini-verified-rebuild:begin -->').length,2);assert.equal(tagSha,sha);assert.equal(release.draft,false);assert.equal(assets.length,18);
  assert.equal(writes[0],'draft');assert.equal(writes.at(-1),'publish');assert.equal(writes.filter(x=>x==='archive').length,6);assert.equal(writes.filter(x=>x==='upload').length,6);
  for(const name of names){assert.equal(assets.filter(a=>a.name===name).length,1);assert.equal(assets.filter(a=>a.name==='previous-'+name).length,1);}
  assert.equal(JSON.parse(fs.readFileSync(path.join(temp,'replacement-recovery.json'))).status,'published');
 }else if(mode==='dry'){assert.equal(error,undefined);assert.deepEqual(writes,[]);assert.equal(tagSha,old);}
 else{assert(error,mode);assert(!writes.includes('publish'),mode);if(writes.includes('draft')){assert.equal(release.draft,true);const receipt=JSON.parse(fs.readFileSync(path.join(temp,'replacement-recovery.json')));assert.equal(receipt.status,'stopped-needs-reconciliation');assert(receipt.backupArtifactId);if(mode==='afterTag')assert.equal(receipt.observedAfterFailure.tag,sha);assert.equal(assets.filter(a=>a.id<=12).length,12);}else assert.deepEqual(writes,[]);if(!['afterTag','bodyFailure','wrongTag'].includes(mode))assert.equal(tagSha,old);}
 fs.rmSync(temp,{recursive:true});
}
(async()=>{for(const name of ['good','existingSection','malformedSection','duplicateSection','dry','ciChanged','releaseChanged','wrongMain','wrongTag','immutable','staleSnapshot','failedCI','expired','badBackup','noBackupReceipt','collision','externalRename','uploadFailure','badUpload','tagFailure','afterTag','bodyFailure'])await scenario(name);console.log('22 replacement state-machine cases PASS');})().catch(e=>{console.error(e);process.exitCode=1;});
