"""Offline release admission and non-retrying publication controls."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
_OLD_PATH = sys.path[:]
sys.path.insert(0, str(ROOT / 'tools/build'))
SPEC = importlib.util.spec_from_file_location('prepare_release', ROOT / 'tools/build/prepare_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
sys.path[:] = _OLD_PATH
SHA = 'a' * 40


def encoded(value):
    raw=value.encode(); assert len(raw)<128
    return bytes([len(raw)])+raw


@pytest.fixture
def package(tmp_path):
    root=tmp_path/'source'; artifact=tmp_path/'artifact'; artifact.mkdir()
    for name,text in [('LocalGenerator/infini_local/__init__.py','APP_VERSION = "0.5.5"'),
        ('ModSources/InfiniCrafterLocal/InfiniCrafterLocal.cs','ModVersion = "0.5.5"'),
        ('ModSources/InfiniCrafterLocal/build.txt','version = 0.5.5\nmodReferences = Luminance\n')]:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    info=encoded('version')+encoded('0.5.5')+encoded('modReferences')+encoded('Luminance')+encoded('')+encoded('')
    from tools.testing.test_tmod_package import studio_fixture, fixture
    from tools.build.build_studio_bundle import SOURCE_FILES, SOURCE_DIRS, source_files, verify_resources, RESOURCE_MANIFEST
    for name in SOURCE_FILES:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():p.write_bytes(b'synthetic tracked source')
    for name in SOURCE_DIRS:
        (root/name).mkdir(parents=True,exist_ok=True)
        (root/name/'fixture.txt').write_text('tracked source directory witness')
    (root/'LocalGenerator/server.py').write_bytes(b'line one\nline two\n')
    files={'Info':info,'InfiniCrafterLocal.dll':b'MZsynthetic-not-executable'}
    files.update(studio_fixture(extra={name:path.read_bytes() for name,path in source_files(root).items()}))
    data=fixture(files,name='InfiniCrafterLocal',version='0.5.5')
    (artifact/'InfiniCrafterLocal.tmod').write_bytes(data)
    provenance={'sourceCommit':SHA,'packageSha256':release.digest(data),'assemblySha256':release.digest(files['InfiniCrafterLocal.dll']),'tmlVersion':'2026.8.3.0'}
    verified={'status':'passed','sha256':release.digest(data),'bytes':len(data),'name':'InfiniCrafterLocal','version':'0.5.5','tmlVersion':'2026.8.3.0'}
    provenance.update(studioManifest=json.loads(files[RESOURCE_MANIFEST]),studioRuntimeSmoke='passed: embedded interpreter imports, HTTP frontend and managed shutdown')
    verified['studio']=verify_resources(files.__getitem__,source_root=root)
    (artifact/'build-provenance.json').write_text(json.dumps(provenance));(artifact/'package-verification.json').write_text(json.dumps(verified))
    return root,artifact


def test_actual_tmod_container_and_source_versions(package):
    root,artifact=package
    assert release.validate_package(root,artifact,'0.5.5',SHA)['sourceCommit']==SHA


@pytest.mark.parametrize('file,key,value',[
 ('build-provenance.json','sourceCommit','b'*40),('build-provenance.json','packageSha256','wrong'),
 ('build-provenance.json','assemblySha256','wrong'),('build-provenance.json','tmlVersion','wrong'),
 ('package-verification.json','status','failed'),('package-verification.json','version','0.5.4'),
 ('package-verification.json','bytes',1),('package-verification.json','studio',{}),
 ('build-provenance.json','studioManifest',{}),('build-provenance.json','studioRuntimeSmoke','notRun')])
def test_refuse_mismatched_ci_package(package,file,key,value):
    root,artifact=package;p=artifact/file;row=json.loads(p.read_text());row[key]=value;p.write_text(json.dumps(row))
    with pytest.raises(ValueError):release.validate_package(root,artifact,'0.5.5',SHA)


def test_refuse_source_version_or_package_corruption(package):
    root,artifact=package
    with pytest.raises(ValueError):release.validate_package(root,artifact,'0.5.4',SHA)
    p=artifact/'InfiniCrafterLocal.tmod';p.write_bytes(p.read_bytes()+b'corruption')
    with pytest.raises(ValueError):release.validate_package(root,artifact,'0.5.5',SHA)


@pytest.mark.parametrize('scenario,stage,expected_writes',[
 ('good','guard',[]),('wrongMain','guard',[]),('badBranch','guard',[]),('tagCreate','guard',[]),('good','admit',[]),('wrongMain','admit',[]),('failedCI','admit',[]),('existingTag','admit',[]),
 ('existingRelease','admit',[]),('expired','admit',[]),('good','publish',['tag','draft','upload','publish']),
 ('wrongMain','publish',[]),('failedCI','publish',[]),('existingTag','publish',[]),
 ('existingRelease','publish',[]),('uploadFailure','publish',['tag','draft','upload']),
 ('uploadMismatch','publish',['tag','draft','upload']),
 ('uploadName','publish',['tag','draft','upload']),('uploadState','publish',['tag','draft','upload']),
 ('uploadSize','publish',['tag','draft','upload'])])
def test_workflow_executes_admission_and_publication_without_retry(tmp_path,scenario,stage,expected_writes):
    node=shutil.which('node')
    if not node:pytest.skip('Node required to execute GitHub Actions JavaScript controls')
    assets=tmp_path/'release-assets';assets.mkdir();(assets/'fixture.txt').write_text('safe')
    harness=r'''
const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));const writes=[],outputs={};
const scenario=input.scenario,sha='a'.repeat(40),run={id:12,head_sha:sha,head_branch:'main',event:'push',status:'completed',conclusion:scenario==='failedCI'?'failure':'success'};
const missing=()=>{let e=new Error('missing');e.status=404;throw e;};
const github={rest:{git:{getRef:async a=>a.ref==='heads/main'?{data:{object:{sha:scenario==='wrongMain'?'b'.repeat(40):sha}}}:scenario==='existingTag'?{data:{}}:missing(),createRef:async()=>{if(scenario==='existingTag')throw new Error('409');writes.push('tag');}},
repos:{listReleases:'releases',createRelease:async()=>{writes.push('draft');return{data:{id:3}};},uploadReleaseAsset:async a=>{writes.push('upload');if(scenario==='uploadFailure')throw new Error('upload failed');if(a.headers['content-type']!=='application/octet-stream'||a.headers['content-length']!==a.data.length)throw new Error('invalid upload headers');return {data:{name:scenario==='uploadName'?'other':a.name,state:scenario==='uploadState'?'new':'uploaded',size:scenario==='uploadSize'?0:a.data.length,digest:scenario==='uploadMismatch'?'wrong':'sha256:'+require('crypto').createHash('sha256').update(a.data).digest('hex')}};},updateRelease:async a=>{if(a.tag_name!=='v0.5.5')throw new Error('publication must preserve explicit tag');writes.push('publish');}},
actions:{listWorkflowRuns:'runs',listWorkflowRunArtifacts:'artifacts',getWorkflowRun:async()=>({data:run})}},
paginate:async method=>method==='releases'?(scenario==='existingRelease'?[{tag_name:'v0.5.5'}]:[]):method==='runs'?[run]:[{id:4,name:'InfiniCrafterLocal-tmod',expired:scenario==='expired'}]};
process.env.RELEASE_TAG='v0.5.5';process.env.CI_RUN='12';process.env.RUNNER_TEMP=input.temp;
const context={repo:{owner:'Xipong',repo:'InfiniCrafterLocal'},sha,payload:{ref_type:scenario==='tagCreate'?'tag':'branch',ref:scenario==='badBranch'?'other':'release/v0.5.5'}};
(async()=>{let error=null;try{const core={setOutput:(k,v)=>outputs[k]=v};if(input.stage==='guard'){await new (Object.getPrototypeOf(async function(){}).constructor)('github','context','core',input.guard)(github,context,core);}else{await require(input.module)[input.stage]({github,context,core});}}catch(e){error=e.message;}console.log(JSON.stringify({writes,outputs,error}));})();
'''
    # Execute the first inline script exactly as the workflow does, before checkout.
    lines=(ROOT/'.github/workflows/release.yml').read_text().splitlines()
    begin=next(i for i,line in enumerate(lines) if line.strip()=='script: |')+1
    block=[]
    for line in lines[begin:]:
        if not line.startswith('            '):break
        block.append(line[12:])
    result=subprocess.run([node,'-e',harness],input=json.dumps({'scenario':scenario,'temp':str(tmp_path),'module':str(ROOT/'tools/build/release_github.js'),'stage':stage,'guard':'\n'.join(block)}),text=True,capture_output=True,check=True,timeout=30)
    row=json.loads(result.stdout);assert row['writes']==expected_writes
    assert (row['error'] is None)==(scenario=='good')
    if stage=='admit' and scenario=='good':assert row['outputs']['run']=='12' and row['outputs']['version']=='0.5.5'


def test_prepare_archives_only_tracked_source_and_refuses_overwrite(package,tmp_path):
    root,artifact=package
    hygiene=root/'tools/checks/check_project_hygiene.py';hygiene.parent.mkdir(parents=True)
    hygiene.write_text("import sys; assert sys.argv[1:] == ['--strict-archive']\n")
    subprocess.run(['git','init',str(root)],check=True,capture_output=True,timeout=30)
    subprocess.run(['git','add','.'],cwd=root,check=True,timeout=30)
    subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture'],cwd=root,check=True,capture_output=True,timeout=30)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=30).strip()
    p=artifact/'build-provenance.json';row=json.loads(p.read_text());row['sourceCommit']=sha;p.write_text(json.dumps(row))
    (root/'private-untracked.txt').write_text('dummy exclusion witness')
    out=tmp_path/'assets'
    release.prepare(root,artifact,out,'0.5.5',sha,'12')
    with zipfile.ZipFile(out/'InfiniCrafterLocal_0.5.5_Source_and_LocalGenerator.zip') as zipped:
        assert 'private-untracked.txt' not in zipped.namelist()
        assert 'ModSources/InfiniCrafterLocal/build.txt' in zipped.namelist()
    for line in (out/'SHA256SUMS.txt').read_text().splitlines():
        sha256,name=line.split('  ');assert release.digest((out/name).read_bytes())==sha256
    with pytest.raises(ValueError,match='Output must be new'):
        release.prepare(root,artifact,out,'0.5.5',sha,'12')
    (root/'LocalGenerator/infini_local/untracked.txt').write_text('untracked selected source')
    original=(root/'LocalGenerator/server.py').read_bytes()
    (root/'LocalGenerator/server.py').write_text('changed tracked source')
    clean_out=tmp_path/'tracked-assets'
    release.prepare(root,artifact,clean_out,'0.5.5',sha,'12')
    with zipfile.ZipFile(clean_out/'InfiniCrafterLocal_0.5.5_Source_and_LocalGenerator.zip') as zipped:
        assert 'LocalGenerator/infini_local/untracked.txt' not in zipped.namelist()
        assert zipped.read('LocalGenerator/server.py')==original


def test_invalid_package_never_prepares_assets(package,tmp_path):
    root,artifact=package;out=tmp_path/'assets'
    hygiene=root/'tools/checks/check_project_hygiene.py';hygiene.parent.mkdir(parents=True)
    hygiene.write_text("import sys; assert sys.argv[1:] == ['--strict-archive']\n")
    subprocess.run(['git','init',str(root)],check=True,capture_output=True,timeout=30)
    subprocess.run(['git','add','.'],cwd=root,check=True,timeout=30)
    subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture'],cwd=root,check=True,capture_output=True,timeout=30)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=30).strip()
    corrupt=b'not a package'
    (artifact/'InfiniCrafterLocal.tmod').write_bytes(corrupt)
    provenance=artifact/'build-provenance.json';row=json.loads(provenance.read_text())
    row.update(sourceCommit=sha,packageSha256=release.digest(corrupt));provenance.write_text(json.dumps(row))
    verified=artifact/'package-verification.json';row=json.loads(verified.read_text())
    row.update(sha256=release.digest(corrupt),bytes=len(corrupt));verified.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='Not a TMOD package'):
        release.prepare(root,artifact,out,'0.5.5',sha,'12')
    assert not out.exists()


def test_embedded_studio_must_match_current_source_not_only_outer_mod_version(package):
    root,artifact=package
    (root/'LocalGenerator/server.py').write_text('changed source after bundle')
    with pytest.raises(ValueError,match='Studio source missing or changed'):
        release.validate_package(root,artifact,'0.5.5',SHA)


def test_old_unbundled_package_is_not_a_current_release(package):
    from tools.testing.test_tmod_package import fixture
    root,artifact=package
    p=artifact/'InfiniCrafterLocal.tmod'
    files=release.read_package(p.read_bytes())[3]
    files={name:data for name,data in files.items() if not name.startswith('Studio/')}
    data=fixture(files,name='InfiniCrafterLocal',version='0.5.5');p.write_bytes(data)
    for name,key in [('build-provenance.json','packageSha256'),('package-verification.json','sha256')]:
        report=artifact/name;row=json.loads(report.read_text());row[key]=release.digest(data)
        if name=='package-verification.json':row['bytes']=len(data)
        report.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='Studio manifest missing'):
        release.validate_package(root,artifact,'0.5.5',SHA)


@pytest.mark.parametrize('autocrlf', ['true','false'])
def test_cross_platform_checkout_must_preserve_blob_bytes_for_studio(package,tmp_path,autocrlf):
    root,artifact=package
    subprocess.run(['git','init',str(root)],check=True,capture_output=True,timeout=30)
    subprocess.run(['git','add','.'],cwd=root,check=True,timeout=30)
    subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture'],cwd=root,check=True,capture_output=True,timeout=30)
    checkout=tmp_path/'checkout'
    subprocess.run(['git','-c',f'core.autocrlf={autocrlf}','clone',str(root),str(checkout)],check=True,capture_output=True,timeout=30)
    original=(root/'LocalGenerator/server.py').read_bytes()
    copied=(checkout/'LocalGenerator/server.py').read_bytes()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,timeout=30)==subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,timeout=30)
    if autocrlf=='true':
        assert copied==original.replace(b'\n',b'\r\n')
        with pytest.raises(ValueError,match='Studio source missing or changed'):
            release.validate_package(checkout,artifact,'0.5.5',SHA)
    else:
        assert copied==original
        assert release.validate_package(checkout,artifact,'0.5.5',SHA)['sourceCommit']==SHA


def test_guarded_replacement_preserves_backups_and_stops_partial_publication():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required to execute GitHub Actions replacement controls')
    subprocess.run([node, str(Path(__file__).with_name('release_replacement.cjs'))],
                   check=True, capture_output=True, text=True, timeout=30)
