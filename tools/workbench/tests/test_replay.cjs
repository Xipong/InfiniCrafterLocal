// Optional DOM behavior test: npm install jsdom. This is not a browser rendering test.
const fs=require('fs'),assert=require('node:assert/strict'),{JSDOM,VirtualConsole}=require('jsdom');
const errors=[], vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(fs.readFileSync(process.argv[2],'utf8'),{runScripts:'dangerously',virtualConsole:vc});
const d=dom.window.document;
assert.deepEqual(errors,[]);
const trace=JSON.parse(d.getElementById('trace').textContent), last=trace.snapshots.length-1;
assert.match(d.getElementById('status').textContent,new RegExp('Run: '+(trace.status||'unknown')));
assert.match(d.getElementById('clock').textContent,/frame 1\//);
d.getElementById('next').click();assert.match(d.getElementById('clock').textContent,/frame 2\//);
d.getElementById('previous').click();assert.match(d.getElementById('clock').textContent,/frame 1\//);
d.getElementById('seek').value=last;d.getElementById('seek').dispatchEvent(new dom.window.Event('input'));
assert.match(d.getElementById('clock').textContent,new RegExp('frame '+(last+1)+'/'));
d.getElementById('play').click();assert.match(d.getElementById('clock').textContent,/frame 1\//);
d.getElementById('play').click();assert.equal(d.getElementById('play').textContent,'Play');
const clock=d.getElementById('clock').textContent;d.getElementById('camera').value='scene';d.getElementById('camera').dispatchEvent(new dom.window.Event('change'));assert.equal(d.getElementById('clock').textContent,clock);d.getElementById('camera').value='action';d.getElementById('camera').dispatchEvent(new dom.window.Event('change'));assert.equal(d.querySelectorAll('#scene > svg').length,1);assert.deepEqual(errors,[]);
if(trace.error)assert.ok(d.getElementById('status').textContent.includes(trace.error));
dom.window.close();console.log('DOM controls PASS: next/back/seek/restart/pause/status (not GPU/browser rendering)');
