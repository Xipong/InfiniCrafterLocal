/* Node regression for the shipped browser controller; no DOM package required. */
'use strict';
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const nodes=new Map(), events={};
function node() {return {hidden:false,open:false,dataset:{},textContent:'',innerHTML:'',value:'',disabled:false,append(){},replaceChildren(){},remove(){},classList:{toggle(){},add(){},remove(){},contains(){return false;}},setAttribute(){},addEventListener(){},close(){this.open=false;},showModal(){this.open=true;},querySelector(){return node();}};}
global.setTimeout=()=>0;
global.document={createElement:()=>node(),activeElement:null,addEventListener(name,fn){events[name]=fn;},querySelectorAll(){return [];},querySelector(selector){if(!nodes.has(selector)) nodes.set(selector,node());return nodes.get(selector);}};
global.window={INFINI_BOOTSTRAP:{token:'test-only'},addEventListener(){}};
const messages=[];
let source=fs.readFileSync(require('node:path').join(__dirname,'../infini_local/desktop/webui/studio.js'),'utf8');
assert(!source.includes('window.confirm('),'discard must use the in-page dialog');
source=source.replace('  navigate();poll();',`
  poll=()=>{};setMenu=()=>{};render=()=>{};renderOperate=()=>{};syncInputs=()=>{};updateDiagnostics=()=>{};updateActionButtons=()=>{};
  const originalToast=toast;toast=(message,error)=>{originalToast(message,error);if(!state.suppressToast) globalThis.messages.push({message,error});};
  globalThis.studio={state,acceptSnapshot,recomputeDirty,inactiveReason,fieldGroups,showDocument,showSaveConflict,focusField,navigate,fieldHTML,derivedField,defaultsSummary,showDefaultsUpdate,action};
`);
global.messages=messages;
vm.runInThisContext(source);
const {state,acceptSnapshot,recomputeDirty,inactiveReason,fieldGroups,showDocument}=studio;
const key='INFINI_PROMPT_STYLE';
const snapshot=(values={},extra={})=>({values,defaults:{},savedValues:values,fields:[],presets:{},userPresets:{},lanEnabled:false,savedLanEnabled:false,...extra});
acceptSnapshot(snapshot({[key]:'saved'}));
state.pending={id:'own-command',action:'save',sent:{[key]:'mine'},clock:1};
state.editClock=2;state.edits[key]=2;state.draft[key]='newer edit';recomputeDirty();
acceptSnapshot(snapshot({[key]:'mine'},{actionResults:[{id:'own-command',status:'running',ok:true}],lastAction:{id:'other-tab',status:'succeeded',ok:true}}));
assert(state.pending,'running is not success');
acceptSnapshot(snapshot({[key]:'other tab saved'},{actionResults:[{id:'own-command',status:'succeeded',ok:true,savedValues:{[key]:'mine'}}],lastAction:{id:'other-tab',status:'succeeded',ok:true}}));
assert.equal(state.pending,null,'retained per-ID result unlocks despite a newer lastAction');
assert.equal(state.draft[key],'newer edit','post-submit edit remains protected');
assert(state.dirty.has(key));
state.pending={id:'transform',action:'resetSprite',sent:{},clock:3};
acceptSnapshot(snapshot({[key]:'later remote'},{actionResults:[{id:'transform',status:'succeeded',ok:true,values:{[key]:'own transformed'}}]}));
assert.equal(state.draft[key],'own transformed','transformation uses its receipt, not newer remote values');
state.pending={id:'failed',action:'save',sent:{},clock:3};
acceptSnapshot(snapshot({}, {actionResults:[{id:'failed',status:'failed',ok:false,message:'explicit failure'}]}));
assert.equal(state.pending,null);assert(messages.some(row=>row.message==='explicit failure' && row.error));
const notice={id:'notice-1',title:'Validation',message:'Missing model',level:'warning'};
acceptSnapshot(snapshot({}, {notifications:[notice]}));acceptSnapshot(snapshot({}, {notifications:[notice]}));
assert.equal(messages.filter(row=>row.message==='Validation · Missing model').length,1,'notifications deduplicate by ID');
state.draft={INFINI_LLM_PROVIDER:'openai_codex',INFINI_BG_COLOR:'transparent',INFINI_LLM_POOL_2_ENABLED:'0'};
assert(inactiveReason({key:'INFINI_LLM_TEMPERATURE'}));
assert(inactiveReason({key:'INFINI_CHROMA_TOLERANCE'}));
assert(inactiveReason({key:'INFINI_LLM_POOL_2_MODEL'}));
state.page='providers';
const grouped=fieldGroups([{key:'INFINI_INTERNAL_TUNING',advanced:false},{key:'INFINI_LLM_PROVIDER',options:['local','openai_codex']}]);
assert(grouped.indexOf('INFINI_INTERNAL_TUNING')>grouped.indexOf('providers-advanced'),'uncurated controls remain available under advanced');
showDocument({title:'Config',content:'<script>unsafe()</script>'});
assert(document.querySelector('#utility-body').innerHTML.includes('&lt;script&gt;'));
assert(!document.querySelector('#utility-body').innerHTML.includes('<script>'));

// Forced and computed settings are readable outputs, never false edit promises.
state.draft.INFINI_VISUAL_STRICT_AI_AUTHORSHIP='1';
state.draft.INFINI_SDCPP_LORA_FILE='C:\\models\\adapter.safetensors';
assert.equal(studio.derivedField('INFINI_SDCPP_LORA_DIR').value,'C:\\models');
const forced=studio.fieldHTML({key:'INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK',options:['0','1']});
assert(forced.includes('<output '));assert(!forced.includes('data-field='));
// A terminal result with its own notification produces one visible result.
state.pending={id:'validation',action:'validate',sent:{},clock:3};
const before=messages.length;
acceptSnapshot(snapshot({}, {actionResults:[{id:'validation',status:'failed',ok:false,message:'Missing model'}],notifications:[{id:'validation-notice',actionId:'validation',title:'Paths',message:'Missing model',level:'error'}]}));
assert.equal(messages.length,before+1);assert.equal(messages.at(-1).message,'Paths · Missing model');

// Native disabled metadata from another controller draft cannot hide this tab.
state.draft={INFINI_LLM_PROVIDER:'local',INFINI_LMSTUDIO_URL:'http://localhost:1234'};state.dirty.clear();
state.remote={values:{INFINI_LLM_PROVIDER:'openrouter',INFINI_LMSTUDIO_URL:'http://localhost:1234'}};
assert.equal(inactiveReason({key:'INFINI_LMSTUDIO_URL',disabled:'Other provider'}),'');

// Saving a named profile selects only this tab's resulting profile draft.
state.pending={id:'profile',action:'savePreset',sent:{},clock:state.editClock};
acceptSnapshot(snapshot({}, {actionResults:[{id:'profile',status:'succeeded',ok:true,lanEnabled:false,values:{INFINI_GUI_PIPELINE_PRESET:'Мой: New'}}]}));
assert.equal(state.draft.INFINI_GUI_PIPELINE_PRESET,'Мой: New');
assert.equal(messages.at(-1).message,'Профиль сохранён отдельно. config.env не изменён.');

// A stale draft's revision stays pinned until explicit, field-wise reconciliation.
state.pending=null;state.shutdown=false;state.draft={};state.dirty.clear();state.remote=null;state.edits={};
const x='INFINI_X',y='INFINI_Y';
acceptSnapshot(snapshot({[x]:'old-x',[y]:'old-y'},{savedRevision:'disk-A'}));
state.draft[x]='my-x';state.edits[x]=++state.editClock;recomputeDirty();
acceptSnapshot(snapshot({[x]:'old-x',[y]:'other-y'},{savedRevision:'disk-B'}));
assert.equal(state.savedRevision,'disk-A');assert.equal(state.draft[x],'my-x');assert.equal(state.draft[y],'other-y');
assert.deepEqual([...state.dirty],[x]);
studio.showSaveConflict();document.querySelector('#reconcile-draft').onclick();
assert.equal(state.savedRevision,'disk-B');assert.equal(state.draft[x],'my-x');assert.equal(state.draft[y],'other-y');
assert.deepEqual([...state.dirty],[x]);

// Recommendations never interrupt loading, polling, or a deliberate custom edit.
document.querySelector('#utility-dialog').open=false;
const offer={version:'0.5.02',changes:[{key:x,current:'0.55',recommended:'0.5',reason:'Optional recommendation'}],dismissed:false,revision:'offer-1'};
acceptSnapshot(snapshot({[x]:'0.55'}, {defaultsUpdate:offer}));
assert.equal(document.querySelector('#utility-dialog').open,false);
assert(studio.defaultsSummary().includes('1 параметр'));
acceptSnapshot(snapshot({[x]:'0.55'}, {defaultsUpdate:offer}));
assert.equal(document.querySelector('#utility-dialog').open,false);
studio.showDefaultsUpdate();assert.equal(document.querySelector('#utility-dialog').open,true);
document.querySelector('#utility-dialog').close();

// Polling must not reset a selected (not yet applied) profile when focus moves.
state.page='configure';
events.input({target:{id:'preset-select',value:'Chosen profile',matches(){return false;}}});
acceptSnapshot(snapshot({INFINI_GUI_PIPELINE_PRESET:'Saved profile'}));
assert.equal(document.querySelector('#preset-select').value,'Chosen profile');
state.pending={id:'apply-choice',action:'applyPreset',sent:{},clock:state.editClock};
acceptSnapshot(snapshot({INFINI_GUI_PIPELINE_PRESET:'Saved profile'}, {actionResults:[{id:'apply-choice',status:'succeeded',ok:true,values:{INFINI_GUI_PIPELINE_PRESET:'Chosen profile'}}]}));
assert.equal(state.presetChoice,null);assert.equal(document.querySelector('#preset-select').value,'Chosen profile');

// Typing a new path invalidates the previously selected file and in-flight list.
state.picker={request:1,selection:'/old/file.gguf'};
events.input({target:{id:'file-path',value:'/new/file.gguf',matches(){return false;}}});
assert.equal(state.picker.request,2);assert.equal(state.picker.selection,null);assert(document.querySelector('#file-select').disabled);
state.picker=null;

// Search waits for exactly one hashchange render before opening and focusing.
global.location={hash:'#operate'};
global.requestAnimationFrame=callback=>callback();
global.matchMedia=()=>({matches:true});
window.scrollY=0;global.window.scrollY=0;
let scroll=null,focused=false;window.scrollTo=options=>{scroll=options;};
state.fields=[{key:'INFINI_LLM_TEMPERATURE',route:'providers'}];
const row=document.querySelector('[data-field-row="INFINI_LLM_TEMPERATURE"]');
row.parentElement={tagName:'DETAILS',dataset:{details:'providers-advanced'},open:false,parentElement:null};
row.getBoundingClientRect=()=>({top:600});
row.querySelector=()=>({focus(){focused=true;}});
studio.focusField('INFINI_LLM_TEMPERATURE');
assert.equal(location.hash,'providers');assert.equal(scroll,null);
location.hash='#providers';studio.navigate();
assert(row.parentElement.open);assert(focused);assert.equal(scroll.top,506);assert.equal(state.focusKey,null);
// Exit must remain unconfirmed while running, even if HTTP accepted the queue.
state.pending={id:'exit',action:'exitStudio',sent:{},clock:3};
acceptSnapshot(snapshot({}, {actionResults:[{id:'exit',status:'running',ok:true}]}));
assert.equal(state.shutdown,false);
acceptSnapshot(snapshot({}, {actionResults:[{id:'exit',status:'succeeded',ok:true}]}));
assert.equal(state.shutdown,true);

async function testRepeatedSubmission() {
  state.shutdown=false;state.connected=true;state.pending=null;state.submission=null;state.posting=false;
  let calls=0,release;
  global.fetch=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
  const first=studio.action('save');
  const repeated=studio.action('save');
  assert.equal(calls,1,'a repeated shortcut cannot duplicate an in-flight request');
  assert.equal(state.submission.action,'save');
  release({ok:true,json:async()=>({ok:true,id:'single-save'})});
  await Promise.all([first,repeated]);
  assert.equal(state.pending.id,'single-save');assert.equal(calls,1);
}
testRepeatedSubmission().then(()=>console.log('Studio frontend regressions passed')).catch(error=>{console.error(error);process.exitCode=1;});
