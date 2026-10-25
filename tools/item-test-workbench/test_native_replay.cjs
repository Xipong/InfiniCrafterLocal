// DOM-only control test; native PNG decode/hash correctness is checked separately.
const fs=require('fs'), assert=require('assert'), {JSDOM}=require('jsdom');
(async()=>{
 const dom=new JSDOM(fs.readFileSync(process.argv[2],'utf8'),{runScripts:'dangerously'});
 const d=dom.window.document,seek=d.getElementById('seek'),img=d.getElementById('native');
 assert(!d.querySelector('canvas'),'Native pixels must not be redrawn in JS');
 assert(img.getAttribute('src').endsWith('000000.png'));
 d.getElementById('next').click();assert.equal(+seek.value,1);assert(img.getAttribute('src').endsWith('000001.png'));assert(d.getElementById('state-summary').textContent.includes('tick 1'));assert(d.getElementById('state-summary').textContent.includes('lifecycle'));assert(d.getElementById('state-summary').textContent.includes('charge')||d.getElementById('state-summary').textContent.includes('none active'));assert.equal(JSON.parse(d.getElementById('state').textContent).nativeTick,1);
 d.getElementById('back').click();assert.equal(+seek.value,0);
 seek.value=Math.min(3,+seek.max);seek.dispatchEvent(new dom.window.Event('input'));assert.equal(+seek.value,Math.min(3,+seek.max));
 d.getElementById('restart').click();assert.equal(+seek.value,0);
 d.getElementById('play').click();assert.equal(d.getElementById('play').textContent,'Pause');
 await new Promise(r=>setTimeout(r,60));assert(+seek.value>0);
 d.getElementById('play').click();const paused=+seek.value;await new Promise(r=>setTimeout(r,40));assert.equal(+seek.value,paused);
 assert(d.getElementById('status').textContent.includes('Native run status'));
 const jumps=[...d.querySelectorAll('#event-jumps button')];assert(jumps.length>0);assert(jumps.every(b=>!b.textContent.includes('native_phase')));jumps.at(-1).click();assert(+seek.value>=0);assert.equal(JSON.parse(d.getElementById('state').textContent).nativeDrawReceipt.tick,JSON.parse(d.getElementById('state').textContent).nativeTick);
 dom.window.close();console.log('Native PNG viewer DOM PASS: exact image paths, next/back/seek/restart/play/pause; no canvas redraw (not a GPU/browser pixel test)');
})().catch(e=>{console.error(e);process.exit(1)});
