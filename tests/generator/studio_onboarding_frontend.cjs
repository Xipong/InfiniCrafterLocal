/* Execute the shipped onboarding controller with a small DOM boundary fixture. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../generator/infini_local/desktop/webui/studio-onboarding.js'),'utf8');
function fixture({seen=false,step=0,completed=false,otherDialog=false}={}) {
  const events={},requests=[],focused=[],routes=[],fields=[],drafts=[],copied=[];
  const body={},title={isConnected:true,focus(){focused.push('title');document.activeElement=this;}},content={scrollTop:0},feedback={textContent:''},progressFeedback={textContent:''};
  let other=otherDialog;
  const launcher={disabled:true,isConnected:true,focus(){focused.push('launcher');document.activeElement=this;}};
  const dialog={open:false,innerHTML:'',shows:0,
    querySelector(selector){return selector==='#onboarding-title'?title:selector==='.onboarding-content'?content:selector==='#onboarding-progress-feedback'?progressFeedback:feedback;},
    showModal(){this.open=true;this.shows++;},close(){if(!this.open)return;this.open=false;document.activeElement=body;events.close();},
    contains(node){return node===title;},addEventListener(name,fn){events[name]=fn;}};
  const document={body,activeElement:body,documentElement:{lang:'ru'},querySelector(selector){return selector==='#onboarding-dialog'?dialog:selector==='#onboarding-launcher'?launcher:other?{}:dialog.open?dialog:null;}};
  const state={shutdown:false,dirty:new Set(),lan:false,baselineLan:false};
  const values={INFINI_OPENAI_COMPAT_API_KEY:'must-never-travel'};
  let fail=false;
  const sandbox={window:{},document,URL,navigator:{clipboard:{writeText:async text=>copied.push(text)}}};
  vm.runInNewContext(source,sandbox);
  const api=async(url,payload)=>{requests.push(JSON.parse(JSON.stringify(payload)));if(fail) throw fail===true?Error('offline'):fail;return {ok:true,id:String(requests.length)};};
  const owner=sandbox.window.InfiniOnboarding.create({api,state,value:key=>values[key] || '',focusField:key=>fields.push(key),navigateTo:route=>routes.push(route),applyDraft:updates=>{drafts.push({...updates});Object.assign(values,updates);}});
  const remote={onboarding:{version:1,seen,step,completed},actionResults:[]};
  const click=async(dataset={},attributes=[])=>events.click({target:{closest(){return {dataset,hasAttribute:name=>attributes.includes(name)};}}});
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  const ack=async(ok=true,status='succeeded')=>{remote.actionResults.push({id:String(requests.length),status,ok});owner.sync(remote);await tick();};
  return {owner,remote,dialog,launcher,document,requests,focused,routes,fields,state,values,drafts,copied,feedback,progressFeedback,click,tick,ack,setOther(value){other=value;},setFail(value){fail=value;}};
}
(async()=>{
  const f=fixture();f.owner.sync(f.remote);await f.tick();
  assert.equal(f.dialog.shows,1);assert.equal(f.launcher.disabled,false);assert.equal(f.focused.at(-1),'title');
  assert.deepEqual(f.requests,[{action:'onboardingProgress',values:{},extra:{step:0,completed:false}}]);
  f.owner.sync(f.remote);f.owner.open();assert.equal(f.dialog.shows,1,'repeated snapshot/open must not stack dialogs');
  await f.click({},['data-onboarding-next']);await f.click({},['data-onboarding-next']);
  assert.equal(f.requests.length,1,'progress coalesces until the previous receipt arrives');
  await f.ack();assert.equal(f.requests.length,2);assert.equal(f.requests[1].extra.step,2);
  f.owner.dismiss();f.owner.sync(f.remote);assert.equal(f.dialog.open,false,'stale seen=false must not reopen dismissed guide');
  f.owner.open();assert(f.dialog.innerHTML.includes('Теперь добавим характер'));
  assert(!f.dialog.innerHTML.includes('must-never-travel'));
  await f.ack();
  await f.click({onboardingField:'INFINI_LLM_PROVIDER'});assert.equal(f.dialog.open,false);assert.deepEqual(f.fields,['INFINI_LLM_PROVIDER']);
  assert.deepEqual(f.values,{INFINI_OPENAI_COMPAT_API_KEY:'must-never-travel'});
  f.owner.open();await f.click({onboardingStep:'4'});await f.click({},['data-onboarding-next']);
  assert.equal(f.dialog.open,false);await f.ack();await f.ack();assert.equal(f.requests.at(-1).extra.completed,true);
  assert(f.requests.every(r=>Object.keys(r.values).length===0));
  const returning=fixture({seen:true,step:3});returning.owner.sync(returning.remote);assert.equal(returning.dialog.shows,0);returning.owner.open();
  assert(returning.dialog.innerHTML.includes('Соедини всё в Studio'));returning.owner.dismiss();assert.equal(returning.focused.at(-1),'launcher');
  returning.document.documentElement.lang='en';returning.owner.open();assert(returning.dialog.innerHTML.includes('Connect it in Studio'));
  assert(!/[А-Яа-яЁё]/.test(returning.dialog.innerHTML),'English guide must translate all owned content');
  await returning.click({onboardingRoute:'operate'});assert.deepEqual(returning.routes,['operate']);assert.equal(returning.dialog.open,false);
  const deferred=fixture({otherDialog:true});deferred.owner.sync(deferred.remote);assert.equal(deferred.dialog.open,false);deferred.setOther(false);deferred.owner.sync(deferred.remote);assert.equal(deferred.dialog.shows,1);
  deferred.owner.dismiss();deferred.owner.sync(deferred.remote);assert.equal(deferred.dialog.open,false);
  const failed=fixture();failed.setFail(true);failed.owner.sync(failed.remote);await failed.tick();assert.equal(failed.requests.length,1);failed.owner.sync(failed.remote);assert.equal(failed.requests.length,1,'failed transmission is not retried automatically');
  failed.setFail(false);await failed.click({},['data-onboarding-next']);await failed.tick();assert.equal(failed.requests.length,2);
  const warning=failed.progressFeedback.textContent;
  assert(warning,'A successful POST only acknowledges queueing, not disk persistence');
  failed.owner.sync({...failed.remote,actionResults:[{id:'unrelated',status:'succeeded',ok:true}]});
  assert.equal(failed.progressFeedback.textContent,warning,'Other actions cannot clear a progress warning');
  await failed.ack(true,'running');assert.equal(failed.progressFeedback.textContent,warning);
  await failed.click({onboardingCopy:'model-name'});assert.equal(failed.feedback.textContent,'Скопировано.');
  await failed.ack();assert.equal(failed.progressFeedback.textContent,'');
  assert.equal(failed.feedback.textContent,'Скопировано.','Progress recovery must not clear unrelated feedback');
  await failed.click({},['data-onboarding-next']);await failed.tick();await failed.ack(false);
  assert.match(failed.progressFeedback.textContent,/папке конфигурации/);
  await failed.click({},['data-onboarding-next']);await failed.tick();
  assert.match(failed.progressFeedback.textContent,/папке конфигурации/,'Keep disk errors until a successful receipt');
  await failed.ack();assert.equal(failed.progressFeedback.textContent,'');
  for(const [cause,ru,en] of [
    [{httpStatus:400},'актуальной версии','current version folder'],
    [{httpStatus:403},'Сессия недоступна','session is unavailable'],
    [{httpStatus:409},'Studio закрыта','Studio is closed'],
    [{httpStatus:429},'Studio занята','Studio is busy'],
    [{httpStatus:408},'не ответила вовремя','did not respond in time'],
    [{name:'AbortError'},'не ответила вовремя','did not respond in time'],
    [{name:'TypeError'},'Проверь соединение','Check the connection'],
    [{httpStatus:500},'Проверь соединение','Check the connection']
  ]) {
    for(const [language,expected] of [['ru',ru],['en',en]]) {
      const rejected=fixture();rejected.document.documentElement.lang=language;
      rejected.setFail({...cause,message:'private-token https://localhost/?token=do-not-display'});
      rejected.owner.sync(rejected.remote);await rejected.tick();
      assert(rejected.progressFeedback.textContent.includes(expected));
      assert(!/private-token|do-not-display|https:/.test(rejected.progressFeedback.textContent));
      assert(!rejected.feedback.textContent,'Progress diagnostics have their own feedback state');
    }
  }
  const inactive=fixture();inactive.owner.sync({});assert.equal(inactive.launcher.disabled,true);assert.equal(inactive.dialog.shows,0);
  for(const language of ['ru','en']) {
    returning.document.documentElement.lang=language;returning.owner.open();
    for(let step=0;step<5;step++) {
      await returning.click({onboardingStep:String(step)});
      const html=returning.dialog.innerHTML;
      for(const tag of html.matchAll(/<a\s[^>]+>/g)) {assert(tag[0].includes('href="https://'));assert(tag[0].includes('rel="noopener noreferrer"'));}
      if(language==='en') assert(!/[А-Яа-яЁё]/.test(html));
      if(step===0) {
        assert(html.includes('VPN') && html.includes('https://openrouter.ai/terms'));
        assert(html.includes(language==='ru'?'запрещает обход':'prohibits bypassing'));
      }
      if(step===1) {
        assert(html.includes('NVIDIA Nemotron 3.5 Super VL'));
        assert(html.includes('https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free'));
        assert(!html.includes('Gemma') && !html.includes('XingChen'));
      }
      if(step===2) {
        assert(html.includes('<h3>Microsoft Mage-Flow Turbo</h3>'));
        assert(html.includes('Qwen3-VL') && html.includes('VAE'));
        assert(html.includes('gpt-image-2') && html.includes('medium') && !html.includes('high'));
        assert(!html.includes('нет готового встроенного подключения') && !html.includes('no built-in Studio integration'));
        assert(!html.includes('2.5') && !html.includes('2.6'));
      }
      if(step===3) {
        assert(html.includes('Mage-Flow Turbo') && html.includes('Qwen3-VL') && html.includes('Mage-VAE'));
        assert(html.includes('https://github.com/leejet/stable-diffusion.cpp/blob/master-1068-fc350be/docs/mage_flow.md'));
        assert(html.includes('CFG 1.0') && html.includes('512–2048'));
        assert(html.includes('data-onboarding-copy="nvidia/nemotron-3.5-super-vl:free"'));
      }
    }
    returning.owner.dismiss();
  }
  const setup=fixture({seen:true,step:3});setup.owner.sync(setup.remote);setup.owner.open();
  setup.values.INFINI_OPENAI_COMPAT_BASE_URL='https://another.example/v1';
  setup.values.INFINI_PROMPT_STYLE='my unsaved style';
  await setup.click({onboardingPreset:'gemini'});
  assert.equal(setup.values.INFINI_OPENAI_COMPAT_API_KEY,'','never move another API credential to Gemini');
  assert.equal(setup.values.INFINI_PROMPT_STYLE,'my unsaved style');
  assert.equal(setup.values.INFINI_LLM_API_MODE,'chat_completions');
  assert.equal(setup.fields.at(-1),'INFINI_OPENAI_COMPAT_API_KEY');
  setup.values.INFINI_OPENAI_COMPAT_API_KEY='existing-gemini-key';setup.owner.open();
  await setup.click({onboardingPreset:'gemini'});assert.equal(setup.values.INFINI_OPENAI_COMPAT_API_KEY,'existing-gemini-key');
  const openrouter=fixture({seen:true,step:3});openrouter.owner.sync(openrouter.remote);openrouter.owner.open();await openrouter.tick();
  const starterModel='nvidia/nemotron-3.5-super-vl:free';
  assert(openrouter.dialog.innerHTML.includes(`data-onboarding-copy="${starterModel}"`));
  await openrouter.click({onboardingCopy:starterModel});assert.deepEqual(openrouter.copied,[starterModel]);
  Object.assign(openrouter.values,{INFINI_OPENROUTER_PROVIDER:'anthropic',INFINI_OPENROUTER_MODEL:'anthropic/claude-sonnet',INFINI_OPENROUTER_API_KEY:'existing-openrouter-key',INFINI_PROMPT_STYLE:'my unsaved style',INFINI_LLM_TEMPERATURE:'0.73'});
  openrouter.state.dirty.add('INFINI_PROMPT_STYLE');openrouter.state.dirty.add('INFINI_LLM_TEMPERATURE');
  const requestsBeforePreset=JSON.stringify(openrouter.requests);
  await openrouter.click({onboardingPreset:'openrouter'});await openrouter.tick();
  assert.deepEqual(openrouter.drafts,[{INFINI_USE_LLM:'1',INFINI_LLM_PROVIDER:'openrouter',INFINI_OPENROUTER_MODEL:'nvidia/nemotron-3.5-super-vl:free',INFINI_OPENROUTER_PROVIDER:''}]);
  assert.equal(openrouter.values.INFINI_OPENROUTER_PROVIDER,'','clear an incompatible provider-only restriction for automatic model routing');
  assert.equal(openrouter.values.INFINI_OPENROUTER_API_KEY,'existing-openrouter-key');
  assert.equal(openrouter.values.INFINI_OPENAI_COMPAT_API_KEY,'must-never-travel');
  assert.equal(openrouter.values.INFINI_PROMPT_STYLE,'my unsaved style');
  assert.equal(openrouter.values.INFINI_LLM_TEMPERATURE,'0.73');
  assert.deepEqual([...openrouter.state.dirty],['INFINI_PROMPT_STYLE','INFINI_LLM_TEMPERATURE']);
  assert.equal(JSON.stringify(openrouter.requests),requestsBeforePreset,'preset is draft-only: no save, runtime action or provider request');
  const install=fixture({seen:true,step:2});install.owner.sync(install.remote);install.owner.open();await install.tick();
  install.remote.sdcppInstall={status:'installed',busy:false,installedPath:'/tmp/official/sd-server'};install.owner.sync(install.remote);
  assert.equal(install.drafts.length,0);await install.click({},['data-onboarding-use']);
  assert.equal(install.values.INFINI_SDCPP_SERVER_EXE,'/tmp/official/sd-server');
  assert.equal(install.values.INFINI_SDCPP_SERVER_COMMAND_MODE,'safe_args');
  assert.equal(install.values.INFINI_OPENAI_COMPAT_API_KEY,'must-never-travel');
  await install.click({onboardingInstallAction:'sdCatalog'});await install.tick();
  assert.deepEqual(install.requests.at(-1),{action:'sdCatalog',values:{},extra:{}});
  assert(install.requests.every(r=>!JSON.stringify(r).includes('must-never-travel')));
  for(const [reason, status, expected] of [
    ['Неверный запрос действия.',400,'Полностью закрой Studio'],
    ['Сессия недоступна. Открой студию заново через запускатор.',403,'Сессия недоступна'],
    ['Студия уже закрыта. Открой её заново через запускатор.',409,'Студия уже закрыта'],
  ]) {
    const rejected=fixture({seen:true,step:2});rejected.owner.sync(rejected.remote);rejected.owner.open();await rejected.tick();
    rejected.setFail(Object.assign(Error(reason),{httpStatus:status}));
    await rejected.click({onboardingInstallAction:'sdCatalog'});
    assert(rejected.feedback.textContent.includes(expected),`Installer hid the actual rejection: ${reason}`);
    rejected.setFail(false);
    await rejected.click({onboardingInstallAction:'sdCatalog'});
    assert.equal(rejected.feedback.textContent,'','Retry clears the previous installer error');
    assert.equal(rejected.requests.filter(r=>r.action==='sdCatalog').length,2);
    await rejected.ack();
    await rejected.click({onboardingInstallAction:'sdCatalog'});
    assert.equal(rejected.requests.filter(r=>r.action==='sdCatalog').length,3,'Receipt releases the installer retry guard');
    assert.equal(rejected.drafts.length,0,'Catalog retry must never adopt or save a draft');
  }
  console.log('Onboarding frontend behavior passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
