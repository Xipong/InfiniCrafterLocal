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
  const runs = await github.paginate(github.rest.actions.listWorkflowRuns, {...repo, workflow_id:'ci.yml', branch:'main', event:'push', head_sha:context.sha, per_page:100});
  const latest = runs.filter(r => r.head_sha === context.sha && r.head_branch === 'main' && r.event === 'push').sort((a,b)=>b.id-a.id)[0];
  if (!latest || latest.status !== 'completed' || latest.conclusion !== 'success') throw new Error('Latest exact main CI is not successful');
  const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts, {...repo, run_id:latest.id, per_page:100});
  const packageArtifacts = artifacts.filter(a => a.name === 'InfiniCrafterLocal-tmod' && !a.expired);
  if (packageArtifacts.length !== 1) throw new Error('Expected exactly one current official package artifact');
  core.setOutput('tag', tag); core.setOutput('version', tag.slice(1));
  core.setOutput('run', String(latest.id)); core.setOutput('artifact', String(packageArtifacts[0].id));
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
  await github.rest.repos.updateRelease({...repo, release_id:release.data.id, draft:false});
};
