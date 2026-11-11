/* Real HTTP plus shipped API/onboarding owners; only the DOM is a small fixture. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const handshake=process.env.IFC_HANDSHAKE;
const events={},body={},feedback={textContent:''},progressFeedback={textContent:''};
const target={focus(){},scrollTop:0},launcher={isConnected:true,focus(){}};
let html='',lastPostStatus;
const dialog={open:false,
  querySelector(s){return s==='#onboarding-feedback'?feedback:s==='#onboarding-progress-feedback'?progressFeedback:target;},
  showModal(){this.open=true;},close(){this.open=false;events.close();},contains(){return false;},
  addEventListener(n,fn){events[n]=fn;},get innerHTML(){return html;},set innerHTML(value){
    html=value;
    for(const [id,node] of [['onboarding-feedback',feedback],['onboarding-progress-feedback',progressFeedback]]) {
      node.textContent=value.match(new RegExp('id="'+id+'"[^>]*>([^<]*)</p>'))?.[1] || '';
    }
  }
};
const document={body,activeElement:body,documentElement:{lang:'ru'},addEventListener(){},querySelectorAll(){return [];},
  querySelector(s){return s==='#onboarding-dialog'?dialog:s==='#onboarding-launcher'?launcher:s==='dialog[open]'?(dialog.open?dialog:null):target;}};
const sandbox={window:{INFINI_BOOTSTRAP:{token:process.env.IFC_TOKEN},InfiniI18n:{t:message=>message},addEventListener(){}},
  document,URL,AbortController,setTimeout,clearTimeout,navigator:{clipboard:{writeText:async()=>{}}},
  fetch:async(url,options)=>{
    const response=await fetch(new URL(url,process.env.IFC_BASE),options);
    if(options.method==='POST')lastPostStatus=response.status;
    return response;
  }};
const assets=path.join(process.env.IFC_GENERATOR,'infini_local/desktop/webui');
const studio=fs.readFileSync(path.join(assets,'studio.js'),'utf8');
assert(studio.includes('  navigate();poll();'));
// Same startup substitution as studio_frontend.cjs; the API owner is unmodified.
vm.runInNewContext(studio.replace('  navigate();poll();','  globalThis.studioApi=api;'),sandbox);
vm.runInNewContext(fs.readFileSync(path.join(assets,'studio-onboarding.js'),'utf8'),sandbox);
const api=sandbox.studioApi;
let releasePost;
const beginPost=()=>new Promise(resolve=>{releasePost=resolve;});
const trackedApi=async(...args)=>{try{return await api(...args);}finally{if(args[1])releasePost();}};
const owner=sandbox.window.InfiniOnboarding.create({api:trackedApi,state:{shutdown:false,dirty:new Set(),lan:false,baselineLan:false},
  value:()=>'',focusField(){},navigateTo(){}});
const click=async(dataset={},attributes=['data-onboarding-next'])=>events.click({target:{closest(){return {dataset,hasAttribute:n=>attributes.includes(n)};}}});
const progress=()=>html.includes('id="onboarding-progress-feedback"')?progressFeedback:feedback;
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function nextStep() {lastPostStatus=null;const settled=beginPost();await click();await settled;await tick();assert(lastPostStatus);}
async function exchange(event) {
  fs.writeFileSync(path.join(handshake,event),'');
  const deadline=Date.now()+15000;
  while(!fs.existsSync(path.join(handshake,event+'.continue'))) {
    assert(!fs.existsSync(path.join(handshake,'stop')),'Python fixture stopped');
    assert(Date.now()<deadline,'Python fixture did not acknowledge '+event);
    await new Promise(resolve=>setTimeout(resolve,10));
  }
}
(async()=>{
  const initial=beginPost();owner.sync(await api('/api/state'));await initial;await tick();
  assert.equal(lastPostStatus,429);assert(progress().textContent);
  const diagnostic=progress().textContent;
  await exchange('rejected');
  await nextStep();
  assert.equal(lastPostStatus,202);assert(progress().textContent,'Queue ACK must not clear the warning');
  await exchange('accepted');
  let remote=await api('/api/state');owner.sync(remote);
  assert.equal(remote.onboarding.step,1);assert(remote.actionResults.some(r=>r.action==='onboardingProgress'&&r.ok));
  assert.equal(progress().textContent,'','Confirmed disk recovery must clear the old error');
  assert(diagnostic.includes('Studio занята'),'Actual HTTP status must reach the safe diagnostic');
  await nextStep();assert.equal(lastPostStatus,202);
  await exchange('disk-request');
  remote=await api('/api/state');owner.sync(remote);
  assert.match(progress().textContent,/папке конфигурации/);
  await click({onboardingCopy:'example-model'},[]);assert.equal(feedback.textContent,'Скопировано.');
  const unrelated=feedback.textContent;
  await nextStep();assert.equal(lastPostStatus,202);
  assert.match(progress().textContent,/папке конфигурации/);
  await exchange('recovery-request');
  remote=await api('/api/state');owner.sync(remote);assert.equal(remote.onboarding.step,3);
  assert.equal(progress().textContent,'');assert.equal(feedback.textContent,unrelated);
  console.log(JSON.stringify({event:'passed'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
