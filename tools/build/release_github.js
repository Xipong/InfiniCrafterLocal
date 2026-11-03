// Release orchestration only; called by the narrowly permissioned workflow.
exports.admit = async ({github, context, core}) => {
  if (context.payload.ref_type !== 'branch' || !/^release\/v\d+\.\d+\.\d+$/.test(context.payload.ref)) throw new Error('Invalid release branch creation');
  const tag = context.payload.ref.slice('release/'.length);
  if (!/^v\d+\.\d+\.\d+$/.test(tag)) throw new Error('Invalid release branch');
  const repo = context.repo;
  const main = await github.rest.git.getRef({...repo, ref:'heads/main'});
  if (main.data.object.sha !== context.sha) throw new Error('Release branch must equal current main');
  const releases = await github.paginate(github.rest.repos.listReleases, {...repo, per_page:100});
  if (releases.some(r => r.tag_name === tag)) throw new Error('Release already exists; no retry/clobber');
  try { await github.rest.git.getRef({...repo, ref:`tags/${tag}`}); throw new Error('Tag already exists'); }
  catch (e) { if (e.status !== 404) throw e; }
  await admitPackage({github, context, core}, tag);
};
exports.publish = async ({github, context, core}) => {
  const fs = require('fs'), path = require('path');
  const repo = context.repo, tag = process.env.RELEASE_TAG;
  const main = await github.rest.git.getRef({...repo, ref:'heads/main'});
  if (main.data.object.sha !== context.sha) throw new Error('Main advanced; stop before publication');
  const releases = await github.paginate(github.rest.repos.listReleases, {...repo, per_page:100});
  if (releases.some(r=>r.tag_name===tag)) throw new Error('Release appeared; no overwrite');
  const run = await github.rest.actions.getWorkflowRun({...repo, run_id:Number(process.env.CI_RUN)});
  if (run.data.head_sha !== context.sha || run.data.event !== 'push' || run.data.head_branch !== 'main' || run.data.status !== 'completed' || run.data.conclusion !== 'success') throw new Error('CI changed before publication');
  // createRef is atomic and refuses any existing tag. No retries or cleanup
  // that could move/delete a release identity after a partial failure.
  await github.rest.git.createRef({...repo, ref:`refs/tags/${tag}`, sha:context.sha});
  const release = await github.rest.repos.createRelease({...repo, tag_name:tag, target_commitish:context.sha, name:tag, draft:true,
    body:`Verified official CI package and matching tracked sources at ${context.sha}. See README for changes and update instructions. Checksums and build provenance are attached. Packaging checks do not certify a full in-game/multiplayer session.`});
  const directory = path.join(process.env.RUNNER_TEMP, 'release-assets');
  for (const name of fs.readdirSync(directory).sort()) {
    const data = fs.readFileSync(path.join(directory,name));
    const uploaded = await github.rest.repos.uploadReleaseAsset({...repo, release_id:release.data.id, name, data, headers:{'content-type':'application/octet-stream','content-length':data.length}});
    const expectedDigest = 'sha256:' + require('crypto').createHash('sha256').update(data).digest('hex');
    if (uploaded.data.name !== name || uploaded.data.state !== 'uploaded' || uploaded.data.size !== data.length || uploaded.data.digest !== expectedDigest)
      throw new Error('Uploaded asset metadata/digest mismatch; draft remains unpublished');
  }
  await github.rest.repos.updateRelease({...repo, release_id:release.data.id, tag_name:tag, draft:false});
};

async function admitPackage({github, context, core}, tag) {
  const repo = context.repo;
  const runs = await github.paginate(github.rest.actions.listWorkflowRuns, {...repo, workflow_id:'ci.yml', branch:'main', event:'push', head_sha:context.sha, per_page:100});
  const latest = runs.filter(r => r.head_sha === context.sha && r.head_branch === 'main' && r.event === 'push').sort((a,b)=>b.id-a.id)[0];
  if (!latest || latest.status !== 'completed' || latest.conclusion !== 'success') throw new Error('Latest exact main CI is not successful');
  const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts, {...repo, run_id:latest.id, per_page:100});
  const packageArtifacts = artifacts.filter(a => a.name === 'InfiniCrafterLocal-tmod' && !a.expired);
  if (packageArtifacts.length !== 1) throw new Error('Expected exactly one current official package artifact');
  core.setOutput('tag', tag); core.setOutput('version', tag.slice(1));
  core.setOutput('run', String(latest.id)); core.setOutput('artifact', String(packageArtifacts[0].id));
}

// Replacement is explicit, default-read-only, and never retries a partial write.
const crypto = require('crypto'), fs = require('fs'), path = require('path');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function releaseState(release, assets) {
  return {id:release.id, tag:release.tag_name, target:release.target_commitish,
    name:release.name, body:release.body, draft:release.draft, prerelease:release.prerelease,
    immutable:release.immutable, updated:release.updated_at,
    assets:assets.map(a=>({id:a.id,name:a.name,label:a.label,size:a.size,digest:a.digest,state:a.state,updated:a.updated_at})).sort((a,b)=>a.id-b.id)};
}
const stateHash = state => hash(JSON.stringify(state));
function replacementInput(context) {
  const i = context.payload.inputs || {};
  if (context.eventName !== 'workflow_dispatch' || context.ref !== 'refs/heads/main' ||
      !/^v\d+\.\d+\.\d+$/.test(i.tag || '') || !/^[0-9a-f]{40}$/.test(i.expected_old_tag || '') ||
      !/^[0-9a-f]{40}$/.test(i.target_sha || '') || i.target_sha !== context.sha ||
      !/^[1-9]\d*$/.test(i.release_id || '') || !/^[0-9a-f]{64}$/.test(i.expected_snapshot || '') ||
      !['true','false'].includes(String(i.apply)) || !['true','false'].includes(String(i.confirm_asset_replacement))) throw new Error('Invalid explicit replacement identity');
  return i;
}
async function readReplacement(github, repo, i, requireIdentity = true) {
  const main = (await github.rest.git.getRef({...repo,ref:'heads/main'})).data.object;
  const tag = (await github.rest.git.getRef({...repo,ref:`tags/${i.tag}`})).data.object;
  const release = (await github.rest.repos.getRelease({...repo,release_id:Number(i.release_id)})).data;
  const assets = await github.paginate(github.rest.repos.listReleaseAssets,{...repo,release_id:release.id,per_page:100});
  if (requireIdentity && (main.sha !== i.target_sha || tag.type !== 'commit' || release.tag_name !== i.tag || release.immutable))
    throw new Error('Replacement main/tag/release identity changed or immutable');
  return {main:main.sha,tag:tag.sha,tagType:tag.type,state:releaseState(release,assets)};
}
function canonicalNames(tag) {
  return ['InfiniCrafterLocal.tmod',`InfiniCrafterLocal_${tag.slice(1)}_Source_and_LocalGenerator.zip`,
    'build-provenance.json','package-verification.json','release-provenance.json','SHA256SUMS.txt'].sort();
}
function rebuildBody(body, repo, tag, sha, run) {
  const begin='<!-- infini-verified-rebuild:begin -->', end='<!-- infini-verified-rebuild:end -->';
  const original=body || '', first=original.indexOf(begin), last=original.indexOf(end);
  if ((first<0)!==(last<0) || (first>=0 && (last<first || original.indexOf(begin,first+begin.length)>=0 || original.indexOf(end,last+end.length)>=0)))
    throw new Error('Malformed rebuild section markers; preserve notes and stop');
  const assets=`https://github.com/${repo.owner}/${repo.repo}/releases/download/${tag}`;
  const section=`${begin}\n## Verified rebuild\nUpdated ${new Date().toISOString()} at commit ${sha}, exact main CI ${run}. This rebuild supersedes earlier build/tag notices below or above. The tag, official package, tracked sources and bundled Studio now refer to this commit.\n\n[Checksums](${assets}/SHA256SUMS.txt) · [Build provenance](${assets}/build-provenance.json) · [Release provenance](${assets}/release-provenance.json). The download list contains only the six current build assets. Existing clones may retain the old tag. Packaging checks do not certify a full in-game/multiplayer session.\n${end}`;
  const updated=first<0 ? original+(original?'\n\n':'')+section : original.slice(0,first)+section+original.slice(last+end.length);
  if(updated.length>60000) throw new Error('Preserved notes plus rebuild section exceed safe release body bound');
  return updated;
}
exports.inspectReplacement = async ({github,context,core}) => {
  const i = replacementInput(context), repo = context.repo;
  const current = await readReplacement(github,repo,i);
  core.info(`Observed release snapshot SHA256: ${stateHash(current.state)}`);
  if (current.tag !== i.expected_old_tag || current.state.draft || stateHash(current.state) !== i.expected_snapshot)
    throw new Error('Expected published release snapshot/tag differs');
  const names = canonicalNames(i.tag);
  if (current.state.assets.length!==names.length || names.some(n=>current.state.assets.filter(a=>a.name===n).length!==1))
    throw new Error('Expected only the six canonical old assets; reconcile foreign/missing/duplicate assets');
  const backup = path.join(process.env.RUNNER_TEMP,'release-backup');
  fs.mkdirSync(backup,{recursive:false});
  for (const asset of current.state.assets) {
    if (asset.state !== 'uploaded' || !/^sha256:[0-9a-f]{64}$/.test(asset.digest || '')) throw new Error('Old asset lacks verified digest');
    const response = await github.rest.repos.getReleaseAsset({...repo,asset_id:asset.id,headers:{accept:'application/octet-stream'}});
    const bytes = Buffer.from(response.data);
    if (bytes.length !== asset.size || `sha256:${hash(bytes)}` !== asset.digest) throw new Error('Backup byte verification failed');
    fs.writeFileSync(path.join(backup,String(asset.id)),bytes,{flag:'wx'});
  }
  fs.writeFileSync(path.join(backup,'snapshot.json'),JSON.stringify(current,null,2));
  await admitPackage({github,context,core},i.tag);
  core.setOutput('backup',backup);
  core.setOutput('snapshot',stateHash(current.state));
};
exports.replace = async ({github,context,core}) => {
  const i = replacementInput(context);
  if (String(i.apply) !== 'true') { core.info('Read-only replacement validation; no release/tag writes'); return; }
  if (String(i.confirm_asset_replacement) !== 'true') throw new Error('Explicit old-asset replacement confirmation required');
  if (!/^[1-9]\d*$/.test(process.env.BACKUP_ARTIFACT_ID || '') || !/^[0-9a-f]{64}$/.test(process.env.BACKUP_ARTIFACT_DIGEST || ''))
    throw new Error('Durable backup upload receipt required before mutation');
  const repo=context.repo, directory=path.join(process.env.RUNNER_TEMP,'release-assets');
  const backupArtifact=(await github.rest.actions.getArtifact({...repo,artifact_id:Number(process.env.BACKUP_ARTIFACT_ID)})).data;
  if (String(backupArtifact.id)!==process.env.BACKUP_ARTIFACT_ID || backupArtifact.expired
      || backupArtifact.name!==`release-backup-${context.runId}-${process.env.GITHUB_RUN_ATTEMPT}`
      || backupArtifact.workflow_run?.id!==context.runId
      || backupArtifact.digest!==`sha256:${process.env.BACKUP_ARTIFACT_DIGEST}`
      || !(Date.parse(backupArtifact.expires_at)>Date.now()))
    throw new Error('Backup artifact identity, digest or retention not verified');
  core.info(`Verified recovery artifact ${backupArtifact.id}, expires ${backupArtifact.expires_at}; repository access rules apply.`);
  const backup=JSON.parse(fs.readFileSync(path.join(process.env.RUNNER_TEMP,'release-backup','snapshot.json'),'utf8'));
  const names=canonicalNames(i.tag);
  if (JSON.stringify(fs.readdirSync(directory).sort())!==JSON.stringify(names)) throw new Error('Unexpected new asset set');
  const prepared=names.map(name=>{const bytes=fs.readFileSync(path.join(directory,name));return {name,bytes,size:bytes.length,digest:`sha256:${hash(bytes)}`};});
  const provenance=JSON.parse(prepared.find(a=>a.name==='release-provenance.json').bytes);
  if (provenance.sourceCommit!==context.sha || provenance.version!==i.tag.slice(1) || String(provenance.ciRunId)!==process.env.CI_RUN)
    throw new Error('Prepared replacement provenance differs');
  const body=rebuildBody(backup.state.body,repo,i.tag,context.sha,process.env.CI_RUN);
  let expected=backup.state, expectedTag=i.expected_old_tag;
  const receipt={old:backup,target:context.sha,backupArtifactId:process.env.BACKUP_ARTIFACT_ID,
    backupArtifactDigest:process.env.BACKUP_ARTIFACT_DIGEST,backupArtifactExpiresAt:backupArtifact.expires_at,operations:[],status:'prepared'};
  const save=()=>fs.writeFileSync(path.join(process.env.RUNNER_TEMP,'replacement-recovery.json'),JSON.stringify(receipt,null,2));
  const guard=async()=>{
    const now=await readReplacement(github,repo,i);
    if(now.tag!==expectedTag || stateHash(now.state)!==stateHash(expected)) throw new Error('Concurrent release/tag change; reconcile without retry');
    const run=(await github.rest.actions.getWorkflowRun({...repo,run_id:Number(process.env.CI_RUN)})).data;
    if(run.head_sha!==context.sha || run.event!=='push' || run.head_branch!=='main' || run.status!=='completed' || run.conclusion!=='success')
      throw new Error('Exact CI no longer successful');
  };
  const updateRelease=async fields=>{
    await guard();
    const result=(await github.rest.repos.updateRelease({...repo,release_id:expected.id,tag_name:i.tag,...fields})).data;
    const anticipated={...expected,updated:result.updated_at};
    for(const [key,value] of Object.entries(fields)) anticipated[key==='target_commitish'?'target':key]=value;
    const observed=releaseState(result,expected.assets.map(a=>({...a,updated_at:a.updated})));
    if(stateHash(observed)!==stateHash(anticipated)) throw new Error('Release mutation response differs; reconcile');
    expected=anticipated;
  };
  try {
    if(stateHash(expected)!==i.expected_snapshot || backup.tag!==expectedTag) throw new Error('Backup snapshot mismatch');
    // Temporary names exist only in the maintenance draft, never in a published release.
    if(expected.assets.length!==names.length || names.some(name=>expected.assets.filter(a=>a.name===name).length!==1))
      throw new Error('Expected only canonical old assets before maintenance');
    const oldAssets=expected.assets.map(a=>({...a}));
    save();
    await updateRelease({draft:true});receipt.operations.push('maintenance-draft');save();
    for(const name of names){
      await guard();const old=expected.assets.find(a=>a.name===name);
      const renamed=(await github.rest.repos.updateReleaseAsset({...repo,asset_id:old.id,name:`replacement-old-${old.id}-${name}`})).data;
      if(renamed.id!==old.id || renamed.name!==`replacement-old-${old.id}-${name}` || renamed.digest!==old.digest || renamed.size!==old.size)throw new Error('Temporary old-asset rename mismatch');
      expected.assets=expected.assets.map(a=>a.id===old.id?releaseState({},[renamed]).assets[0]:a);
      // Asset mutations can update the parent timestamp; compare all other fields.
      const now=await readReplacement(github,repo,i);expected.updated=now.state.updated;
      if(now.tag!==expectedTag || stateHash(now.state)!==stateHash(expected))throw new Error('Unexpected mutation during temporary rename');
      receipt.operations.push({stagedOld:old.id,name:renamed.name});save();
    }
    for(const asset of prepared){
      await guard();const uploaded=(await github.rest.repos.uploadReleaseAsset({...repo,release_id:expected.id,name:asset.name,data:asset.bytes,
        headers:{'content-type':'application/octet-stream','content-length':asset.size}})).data;
      if(uploaded.name!==asset.name || uploaded.state!=='uploaded' || uploaded.size!==asset.size || uploaded.digest!==asset.digest)throw new Error('Replacement upload verification failed');
      expected.assets.push(releaseState({},[uploaded]).assets[0]);expected.assets.sort((a,b)=>a.id-b.id);
      const now=await readReplacement(github,repo,i);expected.updated=now.state.updated;
      if(now.tag!==expectedTag || stateHash(now.state)!==stateHash(expected))throw new Error('Unexpected mutation during upload');
      receipt.operations.push({upload:uploaded.id,name:asset.name,digest:asset.digest});save();
    }
    // New bytes are all verified before deleting exactly the snapshotted old IDs.
    // An uncertain result is observed in the catch receipt; never repeat the deletion.
    for(const old of oldAssets){
      await guard();
      receipt.operations.push({deleteRequested:old.id,digest:old.digest});save();
      await github.rest.repos.deleteReleaseAsset({...repo,asset_id:old.id});
      expected.assets=expected.assets.filter(a=>a.id!==old.id);
      const now=await readReplacement(github,repo,i);expected.updated=now.state.updated;
      if(now.tag!==expectedTag || stateHash(now.state)!==stateHash(expected))throw new Error('Unexpected mutation during old-asset deletion');
      receipt.operations.push({deleted:old.id});save();
    }
    if(expected.assets.length!==prepared.length || prepared.some(a=>expected.assets.filter(b=>b.name===a.name && b.digest===a.digest && b.size===a.size).length!==1))
      throw new Error('Final canonical asset set differs');
    await guard();
    receipt.status='tag-move-requested';save();
    await github.rest.git.updateRef({...repo,ref:`tags/${i.tag}`,sha:context.sha,force:true});
    expectedTag=context.sha;receipt.operations.push('tag-moved');save();
    await updateRelease({target_commitish:context.sha,body});
    await guard();
    await updateRelease({draft:false});
    await guard();receipt.status='published';save();
  } catch(error) {
    receipt.status='stopped-needs-reconciliation';receipt.error=error.message;
    try { receipt.observedAfterFailure=await readReplacement(github,repo,i,false); }
    catch(observationError) { receipt.observationError=observationError.message; }
    save();throw error;
  }
};
