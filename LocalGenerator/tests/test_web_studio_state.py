"""Run the shipped draft reconciliation in Node without Tk or browser downloads."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_persisted_baseline_reload_discard_and_delayed_ack(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Frontend state regression needs Node.js')
    source = Path(__file__).parents[1] / 'infini_local/desktop/webui/studio.js'
    harness = tmp_path / 'studio-state.cjs'
    harness.write_text(r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const nodes = new Map();
global.document = {
  activeElement:null, addEventListener(){}, querySelectorAll(){return [];},
  querySelector(selector){
    if (!nodes.has(selector)) nodes.set(selector,{hidden:false,textContent:'',innerHTML:'',classList:{toggle(){}}});
    return nodes.get(selector);
  }
};
global.window = {INFINI_BOOTSTRAP:{token:'test-only'},addEventListener(){}};
let source = fs.readFileSync(process.argv[2],'utf8');
// Only replace the startup call. Reconciliation and dirty-state code are the
// production functions; rendering is outside this state-only regression.
source = source.replace('  navigate();poll();', `
  render=()=>{}; renderOperate=()=>{}; syncInputs=()=>{};
  updateDiagnostics=()=>{}; updateActionButtons=()=>{}; toast=()=>{};
  globalThis.testStudio={state,acceptSnapshot,recomputeDirty};
`);
vm.runInThisContext(source);
const {state,acceptSnapshot,recomputeDirty}=testStudio;
const key='INFINI_PROMPT_STYLE', secret='INFINI_OPENAI_COMPAT_API_KEY';
const disk = {[key]:'Default',[secret]:'dummy-old'};
const snapshot = (values=disk,savedValues=disk,extra={}) => ({
  values:{...values},savedValues:{...savedValues},defaults:{},fields:[],
  presets:{},userPresets:{},lanEnabled:false,savedLanEnabled:false,...extra
});
// Fresh tab after a non-saving action/profile/reset sees the real disk baseline.
const prepared = snapshot({[key]:'Terraria Like',[secret]:'dummy-new'});
acceptSnapshot(prepared);
assert.equal(state.baseline[key],'Default');
assert.equal(state.draft[key],'Terraria Like');
assert(state.dirty.has(key)); assert(state.dirty.has(secret));
assert.equal(document.querySelector('#save-tray').hidden,false);
// Discard to disk must survive subsequent identical controller snapshots.
state.draft={...state.baseline};state.lan=state.baselineLan;recomputeDirty();
acceptSnapshot(prepared);acceptSnapshot(prepared);
assert.equal(state.draft[key],'Default');assert.equal(state.dirty.size,0);
// A newly prepared remote transformation is still dirty, never a disk baseline.
acceptSnapshot(snapshot({[key]:'Another style',[secret]:'dummy-new'}));
assert.equal(state.draft[key],'Another style');assert(state.dirty.has(key));
// Save has already reached disk, but acknowledgement is delayed. Preserve a
// newer local edit both before and after the matching acknowledgement arrives.
state.editClock=2;state.edits[key]=2;state.draft[key]='Newer local edit';
const submitted={[key]:'Another style',[secret]:'dummy-new'};
state.submission={action:'save',sent:submitted,clock:1,lan:false};
recomputeDirty();
acceptSnapshot(snapshot(submitted,submitted));
assert.equal(state.baseline[key],'Another style');
assert.equal(state.draft[key],'Newer local edit');assert(state.dirty.has(key));
state.submission=null;
state.pending={id:'save-1',action:'save',sent:submitted,clock:1,lan:false};
acceptSnapshot(snapshot(submitted,submitted,{status:'Saved: isolated config',lastAction:{id:'save-1',ok:true}}));
assert.equal(state.draft[key],'Newer local edit');assert(state.dirty.has(key));
assert.equal(state.baseline[secret],'dummy-new');
// A failed/non-saving action never advances the baseline from in-memory values.
acceptSnapshot(snapshot({[key]:'unsaved backend', [secret]:'dummy-new'},submitted));
assert.equal(state.baseline[key],'Another style');
assert.equal(state.draft[key],'Newer local edit');
// Reverting the local field to disk is clean; polling cannot resurrect the
// controller's stale draft after that explicit reversion.
state.draft[key]=state.baseline[key];recomputeDirty();
acceptSnapshot(snapshot({[key]:'unsaved backend', [secret]:'dummy-new'},submitted));
assert.equal(state.draft[key],'Another style');assert.equal(state.dirty.size,0);
''', encoding='utf-8')
    result = subprocess.run([node, str(harness), str(source)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
