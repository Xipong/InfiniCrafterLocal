/* Node regression for the shipped browser controller; no DOM package required. */
'use strict';
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const nodes=new Map(), events={};
function node() {return {hidden:false,open:false,dataset:{},textContent:'',innerHTML:'',value:'',disabled:false,append(){},focus(){},replaceChildren(){},remove(){},classList:{toggle(){},add(){},remove(){},contains(){return false;}},setAttribute(){},addEventListener(){},close(){this.open=false;},showModal(){this.open=true;},querySelector(){return node();}};}
global.setTimeout=()=>0;
// Single- and multi-node queries must see the same mounted fixture nodes.
global.document={createElement:()=>node(),activeElement:null,addEventListener(name,fn){events[name]=fn;},querySelectorAll(selector){return nodes.has(selector) ? [nodes.get(selector)] : [];},querySelector(selector){if(selector === 'dialog[open]') return nodes.get('#utility-dialog')?.open ? nodes.get('#utility-dialog') : nodes.get('#search-dialog')?.open ? nodes.get('#search-dialog') : null;if(!nodes.has(selector)) nodes.set(selector,node());return nodes.get(selector);}};
global.window={INFINI_BOOTSTRAP:{token:'test-only'},addEventListener(){}};
const messages=[];
let source=fs.readFileSync(require('node:path').join(__dirname,'../infini_local/desktop/webui/studio.js'),'utf8');
assert(!source.includes('window.confirm('),'discard must use the in-page dialog');
source=source.replace('  navigate();poll();',`
  poll=()=>{};setMenu=()=>{};render=()=>{globalThis.renderCount++;};renderOperate=()=>{};syncInputs=()=>{};updateDiagnostics=()=>{};updateActionButtons=()=>{};
  const originalToast=toast;toast=(message,error)=>{originalToast(message,error);if(!state.suppressToast) globalThis.messages.push({message,error});};
  globalThis.studio={state,acceptSnapshot,recomputeDirty,heading,inactiveReason,fieldGroups,showDocument,showSaveConflict,focusField,navigate,fieldHTML,derivedField,defaultsSummary,showDefaultsUpdate,refreshDefaultsUpdate,action,makeFields,accountText,maybeLoadCatalog,restoreActionFocus};
`);
global.messages=messages;global.renderCount=0;
vm.runInThisContext(source);
const {state,acceptSnapshot,recomputeDirty,inactiveReason,fieldGroups,showDocument}=studio;
const key='INFINI_PROMPT_STYLE';
const snapshot=(values={},extra={})=>({values,defaults:{},savedValues:values,fields:[],presets:{},userPresets:{},lanEnabled:false,savedLanEnabled:false,...extra});
// Heading status follows typing, reversion, confirmed Save, and LAN-only drafts
// without rebuilding the page or disturbing the current input. Presentation
// details such as parameter-count markup are not part of this contract.
state.page='providers';
acceptSnapshot(snapshot({[key]:'saved'},{savedRevision:'heading-before'}));
const headingStatus=document.querySelector('[data-draft-status]');
headingStatus.textContent='Локальная конфигурация';
const input={dataset:{field:key},type:'text',tagName:'INPUT',value:'edited',
  matches:selector=>selector === '[data-field]',closest:()=>node()};
document.activeElement=input;
const beforeHeadingEdit=global.renderCount;
events.input({target:input});
assert.equal(headingStatus.textContent,'Черновик / Не сохранён','typing marks the existing heading dirty');
assert.equal(document.querySelector('#save-tray').hidden,false);
input.value='saved';events.input({target:input});
assert.equal(headingStatus.textContent,'Локальная конфигурация','reverting the field clears the existing heading');
input.value='edited';events.input({target:input});
state.pending={id:'heading-save',action:'save',sent:{[key]:'edited'},clock:state.editClock,lan:false};
acceptSnapshot(snapshot({[key]:'edited'},{savedRevision:'heading-after',actionResults:[{
  id:'heading-save',status:'succeeded',ok:true,savedValues:{[key]:'edited'},savedRevision:'heading-after',savedLanEnabled:false
}]}));
assert.equal(headingStatus.textContent,'Локальная конфигурация','confirmed Save clears the existing heading');
assert.equal(document.querySelector('#save-tray').hidden,true);
assert.equal(global.renderCount,beforeHeadingEdit,'status updates do not rebuild the current page');
assert.equal(document.activeElement,input,'typing and Save preserve input focus');
state.lan=true;recomputeDirty();
assert.equal(state.dirty.size,0);
assert.equal(headingStatus.textContent,'Черновик / Не сохранён','LAN alone makes the existing heading dirty');
assert(studio.heading('multiplayer').includes('Черновик / Не сохранён'),'rendered headings also include LAN-only drafts');
state.lan=false;recomputeDirty();
assert.equal(headingStatus.textContent,'Локальная конфигурация');
assert(studio.heading('configure').includes('Локальная конфигурация'));
assert(studio.heading('operate').includes('data-draft-status'),'workbench status stays readable too');
document.activeElement=null;state.remote=null;state.draft={};state.dirty.clear();state.edits={};
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
state.page='models';
const loraHelp=fieldGroups([{key:'INFINI_SDCPP_LORA_FILE'}]);
assert(loraHelp.includes('Отключение сбросит настройки адаптера. Файл на диске останется.'),
  'LoRA help distinguishes clearing adapter settings from deleting the file');
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

// Changing an unrelated draft field must not enable API-only reasoning controls.
state.draft={INFINI_LLM_PROVIDER:'openrouter',INFINI_LLM_REASONING_MODE:'prompt_light',INFINI_PORT:'5055'};
state.remote={values:{...state.draft}};state.baseline={...state.draft};state.lan=state.baselineLan=false;state.dirty.clear();
const excludeField={key:'INFINI_LLM_REASONING_EXCLUDE',disabled:'API reasoning only'};
assert(inactiveReason(excludeField),'prompt-only reasoning keeps exclude inactive while clean');
state.draft.INFINI_PORT='6060';recomputeDirty();
assert(inactiveReason(excludeField),'an unrelated port edit cannot enable API reasoning exclude');
state.draft.INFINI_LLM_REASONING_MODE='high';recomputeDirty();
assert.equal(inactiveReason(excludeField),'','an explicit API effort makes exclude active');
state.draft.INFINI_LLM_PROVIDER='local';recomputeDirty();
assert(inactiveReason(excludeField),'local reasoning cannot use API exclude');

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

// Conflict review includes externally removed fields, without exposing credentials.
state.revisionValues={INFINI_REMOVED:'old',INFINI_API_KEY:'old-secret'};
state.remote=snapshot({}, {savedRevision:'disk-C'});
state.draft={INFINI_REMOVED:'my-restored-value',INFINI_API_KEY:'new-secret'};
state.baseline={};recomputeDirty();
studio.showSaveConflict();
const removedReview=document.querySelector('#utility-body').innerHTML;
assert(removedReview.includes('INFINI_REMOVED'),'externally removed fields appear in conflict review');
assert(removedReview.includes('my-restored-value'));
assert(removedReview.includes('Не задано'));
assert(!removedReview.includes('old-secret') && !removedReview.includes('new-secret'));
document.querySelector('#reconcile-draft').onclick();
assert.equal(state.draft.INFINI_REMOVED,'my-restored-value');
assert.equal(state.savedRevision,'disk-C');
assert(state.dirty.has('INFINI_REMOVED'));

// A conflict dialog can outlive the disk revision it showed. Re-review the
// latest snapshot instead of acknowledging an already stale comparison.
state.remote=snapshot({[x]:'other-x',[y]:'disk-b'},{savedRevision:'review-b'});
state.savedRevision='review-a';state.revisionValues={[x]:'old-x',[y]:'old-y'};
state.draft={[x]:'my-x',[y]:'disk-b'};state.baseline={...state.remote.savedValues};recomputeDirty();
studio.showSaveConflict();
acceptSnapshot(snapshot({[x]:'newer-x',[y]:'disk-c'},{savedRevision:'review-c'}));
document.querySelector('#reconcile-draft').onclick();
assert(document.querySelector('#utility-dialog').open,'new disk changes require another review');
assert(document.querySelector('#utility-body').innerHTML.includes('newer-x'));
assert.equal(state.savedRevision,'review-a');assert.equal(state.draft[x],'my-x');assert.equal(state.draft[y],'disk-c');
// Unreadable disk state cannot certify the shown revision either.
state.remote.savedRevision=null;document.querySelector('#reconcile-draft').onclick();
assert(document.querySelector('#utility-dialog').open);assert.equal(state.savedRevision,'review-a');
state.remote.savedRevision='review-c';document.querySelector('#reconcile-draft').onclick();
assert.equal(state.savedRevision,'review-c');assert.equal(state.draft[x],'my-x');assert.equal(state.draft[y],'disk-c');
assert(!document.querySelector('#utility-dialog').open);

// Terminal action feedback restores only abandoned button focus, not a newer
// input, modal, or navigation choice. A disappearing Save tray stays hidden.
document.body=node();document.activeElement=document.body;state.page='providers';
let actionFocus=0;
const refreshButton={isConnected:true,disabled:false,dataset:{action:'codexCatalog'},getClientRects:()=>[{}],focus(){actionFocus++;}};
const completed={focus:{element:refreshButton,action:'codexCatalog',page:'providers'}};
studio.restoreActionFocus(completed);assert.equal(actionFocus,1);
document.activeElement={dataset:{field:x}};studio.restoreActionFocus(completed);assert.equal(actionFocus,1);
document.activeElement=document.body;document.querySelector('#utility-dialog').open=true;
studio.restoreActionFocus(completed);assert.equal(actionFocus,1);
document.querySelector('#utility-dialog').open=false;state.page='multiplayer';
studio.restoreActionFocus(completed);assert.equal(actionFocus,1);
state.page='providers';refreshButton.getClientRects=()=>[];studio.restoreActionFocus(completed);assert.equal(actionFocus,1);
document.activeElement=null;

// Recommendations never interrupt loading, polling, or a deliberate custom edit.
document.querySelector('#utility-dialog').open=false;
const offer={version:'0.5.02',changes:[{key:x,current:'0.55',recommended:'0.5',reason:'Optional recommendation'}],dismissed:false,revision:'offer-1'};
acceptSnapshot(snapshot({[x]:'0.55'}, {defaultsUpdate:offer}));
assert.equal(document.querySelector('#utility-dialog').open,false);
assert(studio.defaultsSummary().includes('Доступно 1 рекомендаций'));
assert(studio.defaultsSummary().includes(offer.version));
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

// Clean custom keys removed on disk must disappear, not become write-back edits.
state.remote=null;state.draft={};state.dirty.clear();state.edits={};
acceptSnapshot(snapshot({INFINI_KEEP:'a',INFINI_REMOVED:'old'},{savedRevision:'disk-1'}));
acceptSnapshot(snapshot({INFINI_KEEP:'a'},{savedRevision:'disk-2'}));
assert(!Object.hasOwn(state.draft,'INFINI_REMOVED'));assert(!state.dirty.has('INFINI_REMOVED'));
assert(!state.fields.some(field=>field.key==='INFINI_REMOVED'));
// A genuinely edited removed key is retained as the user's explicit draft.
acceptSnapshot(snapshot({INFINI_KEEP:'a',INFINI_REMOVED:'old'}));
state.draft.INFINI_REMOVED='my edit';recomputeDirty();
acceptSnapshot(snapshot({INFINI_KEEP:'a'}));
assert.equal(state.draft.INFINI_REMOVED,'my edit');assert(state.dirty.has('INFINI_REMOVED'));
// External provider changes update presentation without destroying local text/focus.
state.remote=null;state.draft={};state.dirty.clear();state.edits={};state.page='providers';
const local={INFINI_LLM_PROVIDER:'local',INFINI_LMSTUDIO_URL:'http://local',INFINI_OPENROUTER_MODEL:'model'};
acceptSnapshot(snapshot(local));
state.draft.INFINI_LMSTUDIO_URL='http://edited';recomputeDirty();
let restoredFocus=0,restoredSelection=null;
const activeField={dataset:{field:'INFINI_LMSTUDIO_URL'},selectionStart:3,selectionEnd:8};
document.activeElement=activeField;
const restored=document.querySelector('[data-field="INFINI_LMSTUDIO_URL"]');
restored.parentElement={tagName:'DETAILS',dataset:{details:'providers-inactive'},open:false,parentElement:null};
restored.focus=()=>restoredFocus++;restored.setSelectionRange=(...range)=>{restoredSelection=range;};
global.renderCount=0;
acceptSnapshot(snapshot({...local,INFINI_LLM_PROVIDER:'openrouter'}));
assert.equal(global.renderCount,1);assert.equal(state.draft.INFINI_LMSTUDIO_URL,'http://edited');
assert.equal(restoredFocus,1);assert.deepEqual(restoredSelection,[3,8]);assert(restored.parentElement.open);
document.activeElement=null;
// Global Save must not run underneath confirmation, file, or search dialogs.
state.connected=false;state.pending=null;state.submission=null;state.shutdown=false;
const keyEvent={ctrlKey:true,code:'KeyS',key:'s',preventDefault(){},target:{id:'confirm-submit',matches(){return false;}}};
const beforeShortcut=state.notifications.length;
document.querySelector('#utility-dialog').open=true;events.keydown(keyEvent);
assert.equal(state.notifications.length,beforeShortcut);
document.querySelector('#utility-dialog').open=false;document.querySelector('#search-dialog').open=true;events.keydown(keyEvent);
assert.equal(state.notifications.length,beforeShortcut);
document.querySelector('#search-dialog').open=false;events.keydown(keyEvent);
assert.equal(state.notifications.length,beforeShortcut+1,'outside a modal, Save still reaches the connectivity guard');

// A failed process launch still acknowledges its confirmed normalized disk write.
state.remote=null;state.draft={};state.dirty.clear();state.edits={};state.pending=null;
acceptSnapshot(snapshot({INFINI_A:'old-a',INFINI_B:'old-b'},{savedRevision:'before-launch'}));
state.draft={INFINI_A:' submitted-a ',INFINI_B:'newer-b'};state.edits={INFINI_A:1,INFINI_B:2};recomputeDirty();
state.pending={id:'failed-after-save',action:'start',clock:1,sent:{INFINI_A:' submitted-a ',INFINI_B:'submitted-b'}};
acceptSnapshot(snapshot({INFINI_A:'submitted-a',INFINI_B:'submitted-b'},{savedRevision:'after-launch-save',actionResults:[{id:'failed-after-save',ok:false,status:'failed',saved:true,savedRevision:'after-launch-save',savedValues:{INFINI_A:'submitted-a',INFINI_B:'submitted-b'},message:'config.env saved; server.py failed'}]}));
assert.equal(state.savedRevision,'after-launch-save');assert.equal(state.draft.INFINI_A,'submitted-a');assert.equal(state.draft.INFINI_B,'newer-b');
assert(!state.dirty.has('INFINI_A'));assert(state.dirty.has('INFINI_B'));assert.equal(state.pending,null);
assert.equal(messages.at(-1).message,'config.env saved; server.py failed');assert(messages.at(-1).error);

// A running start ignores status prose; only its final receipt adopts saved values.
for(const finalStatus of ['succeeded','cancelled']) {
  state.remote=null;state.draft={};state.dirty.clear();state.edits={};state.pending=null;
  acceptSnapshot(snapshot({INFINI_A:'before',INFINI_B:'before-b'},{savedRevision:'before-start'}));
  state.draft={INFINI_A:' submitted ',INFINI_B:'newer-b'};state.edits={INFINI_A:1,INFINI_B:2};recomputeDirty();
  state.pending={id:'guarded-start',action:'start',clock:1,sent:{INFINI_A:' submitted ',INFINI_B:'submitted-b'}};
  acceptSnapshot(snapshot({INFINI_A:'other-tab',INFINI_B:'other-b'},{savedRevision:'other-revision',status:'Saved: config.env; server.py запущен',actionResults:[{id:'guarded-start',status:'running',ok:true}]}));
  assert(state.pending);assert.equal(state.draft.INFINI_A,' submitted ');assert.equal(state.savedRevision,'before-start');
  const receipt={id:'guarded-start',status:finalStatus,ok:finalStatus === 'succeeded',message:finalStatus};
  if(finalStatus === 'succeeded') Object.assign(receipt,{saved:true,savedValues:{INFINI_A:'submitted',INFINI_B:'submitted-b'},savedRevision:'own-revision'});
  acceptSnapshot(snapshot({INFINI_A:'other-tab',INFINI_B:'other-b'},{savedRevision:'other-revision',actionResults:[receipt]}));
  assert.equal(state.pending,null);assert.equal(state.draft.INFINI_B,'newer-b');
  assert.equal(state.draft.INFINI_A,finalStatus === 'succeeded' ? 'submitted':' submitted ');
  assert.equal(state.savedRevision,finalStatus === 'succeeded' ? 'own-revision':'before-start');
}

// Effort choices follow this tab's selected draft model, without rewriting values.
state.draft={INFINI_LLM_PROVIDER:'openai_codex',INFINI_CODEX_LLM_MODEL:'model-b',INFINI_LLM_REASONING_MODE:'high',INFINI_CODEX_VISUAL_REASONING:'inherit'};
state.remote={values:{INFINI_CODEX_LLM_MODEL:'model-a'},defaults:{},fields:[{key:'INFINI_LLM_REASONING_MODE',options:['off','high']},{key:'INFINI_CODEX_VISUAL_REASONING',options:['inherit','high']}],account:{authenticated:true,catalog:'Текстовая модель аккаунта: effort high',textModels:{'model-a':{efforts:['high'],defaultEffort:'high'},'model-b':{efforts:['low'],defaultEffort:'low'}}}};
let catalogFields=studio.makeFields(state.remote);
assert.deepEqual(catalogFields.find(field=>field.key==='INFINI_LLM_REASONING_MODE').options,['off','low']);
assert.equal(state.draft.INFINI_LLM_REASONING_MODE,'high');assert(studio.accountText('providers').includes('не поддерживается'));
assert(!studio.accountText('providers').includes('Текстовая модель аккаунта: effort high'));
state.draft.INFINI_CODEX_LLM_MODEL='manual-unknown';catalogFields=studio.makeFields(state.remote);
assert.deepEqual(catalogFields.find(field=>field.key==='INFINI_LLM_REASONING_MODE').options,[]);
assert.equal(state.draft.INFINI_CODEX_LLM_MODEL,'manual-unknown');

// Search waits for exactly one hashchange render before opening and focusing.
global.location={hash:'#operate'};
global.requestAnimationFrame=callback=>callback();
global.matchMedia=()=>({matches:true});
window.scrollY=0;global.window.scrollY=0;
let scroll=null,focused=false;window.scrollTo=options=>{scroll=options;};
state.fields=[{key:'INFINI_LLM_TEMPERATURE',route:'providers'}];
const row=document.querySelector('[data-field-row="INFINI_LLM_TEMPERATURE"]');
row.parentElement={tagName:'DETAILS',dataset:{details:'providers-advanced'},open:false,parentElement:null};
const searchRowTop=600;window.innerHeight=400;
row.getBoundingClientRect=()=>({top:searchRowTop});
row.querySelector=()=>({focus(){focused=true;}});
studio.focusField('INFINI_LLM_TEMPERATURE');
assert.equal(location.hash,'providers');assert.equal(scroll,null);
location.hash='#providers';studio.navigate();
assert(row.parentElement.open);assert(focused);
// The destination must bring the row into view, not encode today's header offset.
assert(scroll && Number.isFinite(scroll.top),'search must request a finite scroll destination');
assert(scroll.top>0 && scroll.top<=searchRowTop && searchRowTop-scroll.top<window.innerHeight,
  'search must scroll toward the requested row and leave it inside the viewport');
assert.equal(state.focusKey,null);
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
async function testCatalogAutoload() {
  state.shutdown=false;state.connected=true;state.pending=null;state.submission=null;state.posting=false;state.catalogAutoRequested=false;state.page='providers';
  state.remote={account:{authenticated:true,textModels:{}}};state.draft={INFINI_LLM_PROVIDER:'openai_codex',INFINI_CODEX_LLM_MODEL:'keep-manual'};
  let calls=0;global.fetch=async()=>{calls++;return {ok:true,json:async()=>({ok:true,id:`catalog-${calls}`})};};
  await studio.maybeLoadCatalog();await studio.maybeLoadCatalog();assert.equal(calls,1);
  state.pending=null;await studio.maybeLoadCatalog();assert.equal(calls,1,'polls do not repeat an unsuccessful/empty auto attempt');
  await studio.action('codexCatalog');assert.equal(calls,2,'manual retry stays available');
  state.pending=null;state.remote.account.authenticated=false;studio.maybeLoadCatalog();assert.equal(state.catalogAutoRequested,false);
  state.remote.account.authenticated=true;await studio.maybeLoadCatalog();assert.equal(calls,3,'a new authenticated session can retry once');
  assert.equal(state.draft.INFINI_CODEX_LLM_MODEL,'keep-manual');
}
async function testInterruptedDefaultsRefresh() {
  for(const interruption of ['close','replace','reopen','submit','repeat','none','error']) {
    state.remote=null;state.draft={};state.dirty.clear();state.pending=null;state.posting=false;state.submission=null;
    const original=snapshot({}, {savedRevision:'original',defaultsUpdate:{revision:'offer-a',changes:[]}});
    acceptSnapshot(original);studio.showDefaultsUpdate();
    const pending=[];
    global.fetch=()=>new Promise(resolve=>pending.push(resolve));
    const first=studio.refreshDefaultsUpdate();
    const dialog=document.querySelector('#utility-dialog');
    if(['close','replace','reopen','error'].includes(interruption)) dialog.close();
    if(interruption === 'replace') showDocument({title:'Newer document',content:'Keep this'});
    if(interruption === 'reopen') studio.showDefaultsUpdate();
    if(interruption === 'submit') state.posting=true;
    let second;
    if(interruption === 'repeat') second=studio.refreshDefaultsUpdate();
    const preview=state.defaultsPreview, title=document.querySelector('#utility-title').textContent;
    pending[0]({ok:interruption !== 'error',json:async()=>snapshot({}, {savedRevision:'stale',defaultsUpdate:{revision:'offer-stale',changes:[]}})});
    await first;
    if(interruption === 'none') {
      assert.equal(state.remote.savedRevision,'stale','active refresh is still applied');
      assert.notEqual(state.defaultsPreview,preview);
    } else {
      assert.equal(state.remote.savedRevision,'original',`${interruption}: obsolete refresh cannot roll back the current snapshot`);
      assert.equal(state.defaultsPreview,preview,`${interruption}: obsolete refresh cannot replace the current preview`);
      assert.equal(document.querySelector('#utility-title').textContent,title);
      if(['close','error'].includes(interruption)) assert.equal(dialog.open,false,'dismissed dialog stays closed');
    }
    if(second) {
      pending[1]({ok:true,json:async()=>snapshot({}, {savedRevision:'latest',defaultsUpdate:{revision:'offer-latest',changes:[]}})});
      await second;
      assert.equal(state.remote.savedRevision,'latest','latest repeated refresh wins');
    }
    state.posting=false;
  }
}
testRepeatedSubmission().then(testCatalogAutoload).then(testInterruptedDefaultsRefresh).then(()=>console.log('Studio frontend regressions passed')).catch(error=>{console.error(error);process.exitCode=1;});
