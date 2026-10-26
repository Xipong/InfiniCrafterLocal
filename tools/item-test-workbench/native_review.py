"""Read-only native PNG sequence review. Never simulates or redraws engine pixels."""
import hashlib,html,json,shutil,struct,zlib
from pathlib import Path


def png_dimensions(raw):
    if len(raw)<33 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR' or raw[8:12]!=b'\x00\x00\x00\r':raise ValueError('Native frame is not PNG')
    width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',raw[16:29])
    if not 1<=width<=1024 or not 1<=height<=1024 or (depth,color,compression,filtering,interlace)!=(8,6,0,0,0):raise ValueError('Expected bounded native RGBA8 noninterlaced PNG')
    offset=8;packed=[];ended=False
    while offset<len(raw):
        if len(raw)-offset<12:raise ValueError('Truncated PNG chunk')
        size=struct.unpack('>I',raw[offset:offset+4])[0];kind=raw[offset+4:offset+8];end=offset+12+size
        if end>len(raw):raise ValueError('Truncated PNG payload')
        payload=raw[offset+8:offset+8+size];crc=struct.unpack('>I',raw[offset+8+size:end])[0]
        if zlib.crc32(kind+payload)&0xffffffff!=crc:raise ValueError('PNG chunk checksum mismatch')
        if kind==b'IDAT':packed.append(payload)
        if kind==b'IEND':
            if size or end!=len(raw):raise ValueError('Invalid PNG end')
            ended=True
        offset=end
    if not ended or not packed:raise ValueError('Incomplete PNG image')
    expected=(width*4+1)*height;decoder=zlib.decompressobj()
    try:pixels=decoder.decompress(b''.join(packed),expected+1)
    except zlib.error as exc:raise ValueError('Invalid compressed PNG data') from exc
    if len(pixels)!=expected or not decoder.eof or decoder.unused_data or any(pixels[y*(width*4+1)]>4 for y in range(height)):raise ValueError('Invalid bounded PNG scanlines')
    return width,height


def native_frames(trace,trace_path):
    render=trace.get('nativeRender')
    if not isinstance(render,dict) or render.get('backend')!='original_mod_draw_layers':raise ValueError('No admitted original native draw-layer evidence')
    for key in ('itemArtworkRendered','projectileArtworkRendered','worldRendered'):
        if type(render.get(key)) is not bool:raise ValueError('Missing explicit native artwork/world coverage: '+key)
    if 'playerArtworkRendered' in render and type(render['playerArtworkRendered']) is not bool:raise ValueError('Invalid explicit player artwork coverage')
    frames=render.get('frames')
    if not isinstance(frames,list) or not 1<=len(frames)<=600:raise ValueError('Native review needs 1..600 recorded PNG frames')
    states=trace.get('snapshots')
    if not isinstance(states,list):raise ValueError('Native pixels require synchronized native state snapshots')
    completed={s.get('tick') for s in states if isinstance(s,dict) and s.get('phase')!='after_input_before_update'}
    parent=Path(trace_path).resolve().parent;result=[];previous=-1
    for f in frames:
        if not isinstance(f,dict) or type(f.get('tick')) is not int or f['tick']<=previous:raise ValueError('Native render ticks must be strictly increasing')
        if f['tick'] not in completed:raise ValueError('Native frame has no same-tick completed telemetry')
        if 'nativeDustStateTick' in f:
            if type(f['nativeDustStateTick']) is not int or f['nativeDustStateTick']!=f['tick']:raise ValueError('Native dust state tick disagrees with PNG')
            matches=[s for s in trace['nativeRender'].get('snapshots',[]) if s.get('tick')==f['tick']]
            if len(matches)!=1 or matches[0].get('nativeDustDrawExecuted') is not True:raise ValueError('Native dust state reference is missing or ambiguous')
            for state_key,count_key in [('nativeDustBeforeDraw','nativeDustBeforeDrawCount'),('nativeDustAfterDraw','nativeDustAfterDrawCount')]:
                if not isinstance(matches[0].get(state_key),list) or type(f.get(count_key)) is not int or f[count_key]!=len(matches[0][state_key]):raise ValueError('Native dust state count disagrees with PNG receipt')
        previous=f['tick'];relative=Path(f.get('path',''))
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:raise ValueError('Native PNG path must stay within trace directory')
        path=(parent/relative).resolve()
        if not path.is_relative_to(parent) or not path.is_file():raise ValueError('Native PNG absent or outside trace directory')
        if path.stat().st_size>16*1024*1024:raise ValueError('Oversized native PNG')
        raw=path.read_bytes()
        width,height=png_dimensions(raw)
        if type(f.get('width')) is not int or type(f.get('height')) is not int or f.get('width')!=width or f.get('height')!=height:raise ValueError('Native PNG dimensions disagree with receipt')
        if hashlib.sha256(raw).hexdigest()!=f.get('sha256'):raise ValueError('Native PNG hash disagrees with receipt')
        result.append((f,path))
    if trace.get('status')=='passed' and [f['tick'] for f,_ in result]!=list(range(trace['timeline']['completedTicks'])):
        raise ValueError('Passed native render is missing completed tick frames')
    return result


def observed_bookmarks(trace):
    """Labels for transitions between recorded states, not synthesized engine events."""
    result=[];previous=None;particles=None
    vfx={s['tick']:s for s in trace.get('nativeRender',{}).get('snapshots',[])}
    for state in trace.get('snapshots',[]):
        if state['tick']<0 or state.get('phase')=='after_input_before_update':continue
        tick=state['tick'];player=state.get('player',{})
        def add(label,field):result.append({'tick':tick,'label':label,'sourceField':field,'kind':'observed-state-transition'})
        if previous is not None:
            old=previous.get('player',{})
            for field,label in [('generatedBuffTicks','generated buff clock reached zero'),('mobilityCooldownTicks','mobility cooldown reached zero')]:
                if old.get(field,0)>0 and player.get(field)==0:add(label,'player.'+field)
            old_projectiles={p['id']:p for p in previous.get('projectiles',[])}
            for projectile in state.get('projectiles',[]):
                old_p=old_projectiles.get(projectile['id'])
                if old_p is not None:
                    for field,label in [('released','entered released state'),('returning','entered returning state')]:
                        if old_p.get(field) is False and projectile.get(field) is True:add('projectile '+str(projectile['id'])+' '+label,'projectiles.'+field)
                    if old_p.get('active') is True and projectile.get('active') is False:add('projectile '+str(projectile['id'])+' became inactive (see native event for cause)','projectiles.active')
                    if (old_p.get('chargeStatus') or {}).get('ready') is False and (projectile.get('chargeStatus') or {}).get('ready') is True:add('projectile '+str(projectile['id'])+' charge ready (native status)','projectiles.chargeStatus.ready')
        count=vfx.get(tick,{}).get('particleCount')
        if particles is not None and particles>0 and count==0:add('native particle count reached zero','nativeRender.snapshots.particleCount')
        if count is not None:particles=count
        previous=state
    return result


def export_native_review(trace,trace_path,output,gif=False,gif_stride=1):
    if type(gif_stride) is not int or not 1<=gif_stride<=600:raise ValueError("GIF stride must be an integer1..600")
    trace_bytes=Path(trace_path).read_bytes()
    if json.loads(trace_bytes)!=trace:raise ValueError('Native trace changed before review export')
    trace_hash=hashlib.sha256(trace_bytes).hexdigest()
    frames=native_frames(trace,trace_path);output=Path(output).resolve();parent=Path(trace_path).resolve().parent
    if output==parent or output.is_relative_to(parent/'native-frames'):raise ValueError('Review must not overwrite native source files')
    if output.exists() and any(output.iterdir()):raise ValueError('Use a fresh native review directory')
    output.mkdir(parents=True,exist_ok=True);(output/'frames').mkdir()
    descriptors=[]
    for index,(f,path) in enumerate(frames):
        rel=f'frames/{index:06}.png';shutil.copyfile(path,output/rel)
        if hashlib.sha256((output/rel).read_bytes()).hexdigest()!=f['sha256']:raise ValueError('Native PNG changed during export')
        descriptors.append({**f,'path':rel,'snapshotIndices':[i for i,s in enumerate(trace['snapshots']) if s['tick']==f['tick']]})
    bookmarks=observed_bookmarks(trace)
    metadata={'observedStateBookmarks':bookmarks,'kind':'original-native-png-sequence-review','sourceTraceSha256':trace_hash,'nativeRendering':trace['nativeRender'],'frames':descriptors,'pixelsRedrawn':False,'interpolated':False}
    if gif:
        gif_frames=frames[::gif_stride]
        if gif_frames[-1]!=frames[-1]:gif_frames.append(frames[-1])
        if sum(f['width']*f['height'] for f,_ in gif_frames)>100_000_000:raise ValueError('GIF exceeds safe pixel budget; use --gif-stride or HTML/raw PNGs')
        try:from PIL import Image
        except ImportError as exc:raise RuntimeError('Native GIF export requires optional Pillow') from exc
        dimensions={(f['width'],f['height']) for f,_ in frames}
        if len(dimensions)!=1:raise ValueError('Native GIF requires constant frame dimensions')
        images=[]
        for _,path in gif_frames:
            with Image.open(path) as im:images.append(im.convert('RGB'))
        # Quantize cumulative native tick times, so 60/30fps rounding cannot drift.
        times=[round((f['tick']-gif_frames[0][0]['tick'])*100/60) for f,_ in gif_frames]
        durations=[max(10,(b-a)*10) for a,b in zip(times,times[1:])]+[800]
        images[0].save(output/'native.gif',save_all=True,append_images=images[1:],duration=durations,loop=0)
        metadata['gif']={'path':'native.gif','frameDurationsMs':durations,'sourceTicks':[f['tick'] for f,_ in gif_frames],'stride':gif_stride,'omittedFrames':len(frames)-len(gif_frames),'note':'Original PNG samples only; optional stride omits GIF frames, never HTML/native data. Palette/timing quantized; last frame pause800ms.'}
    (output/'native-review.json').write_text(json.dumps(metadata,separators=(',',':')))
    data=json.dumps({'bookmarks':bookmarks,'frames':descriptors,'status':trace['status'],'render':{k:v for k,v in trace['nativeRender'].items() if k!='frames'},'coverage':trace.get('coverage'),'execution':trace.get('execution'),'states':trace['snapshots'],'resources':trace.get('resources'),'scene':trace.get('scene'),'assertions':trace.get('assertions'),'input':trace.get('input')},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    page='''<!doctype html><meta charset="utf-8"><title>Original native VFX pixels</title><style>body{background:#111827;color:#e5e7eb;font:16px system-ui;max-width:1100px;margin:28px auto;padding:12px}h1{font-size:23px;color:#fbbf24}button,input{margin:8px}img{display:block;max-width:100%;image-rendering:pixelated;border:1px solid #64748b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1f2937;padding:14px}a{color:#7dd3fc}</style><h1 id="title">ORIGINAL NATIVE MOD PIXELS</h1><p>Native drawing on a neutral background. Not a complete Terraria world render. Raw PNG pixels, no JS physics or redraw.</p><p id="draw-scope" style="color:#fbbf24"></p><p id="status"></p><p id="input-boundary" style="color:#fbbf24"></p><button id="back">Previous</button><button id="play">Play</button><button id="next">Next</button><button id="restart">Restart</button><label>Playback <select id="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label><input id="seek" type="range" min="0" value="0"><p id="frame"></p><div id="event-jumps"></div><details><summary>Recorded state transitions (not synthetic engine events)</summary><div id="state-jumps"></div></details><a id="raw" target="_blank">Open exact native PNG</a><img id="native" alt="Original native render target pixels"><p>Display may scale to fit; PNG dimensions and camera zoom are recorded below. Missing artwork is not silently replaced.</p><h2>Exact same-tick telemetry</h2><p id="state-summary"></p><details open><summary>Recorded state, phase/input commands, events and native particles (no interpolation)</summary><pre id="state"></pre></details><details><summary>Native scope / missing artwork / resource readiness / end-of-run totals</summary><pre id="scope"></pre></details><p><a href="native-review.json">Frame hashes and original native rendering metadata</a></p><script>
const data=TRACE_DATA,frames=data.frames,seek=document.getElementById('seek');let timer=null;
seek.max=frames.length-1;document.getElementById('title').textContent=data.render.playerArtworkRendered?'ORIGINAL NATIVE PLAYER / ITEM / PROJECTILE / VFX PIXELS':(data.render.itemArtworkRendered||data.render.projectileArtworkRendered)?'ORIGINAL NATIVE ITEM / PROJECTILE / VFX PIXELS':'ORIGINAL NATIVE MOD VFX PIXELS';document.getElementById('draw-scope').textContent=data.render.scope+(data.render.partialProjectileHook?' · Partial projectile hook: full PreDraw is not claimed.':'')+(data.render.trainingDummy?.animationCompatibilityVerified===false?` · WARNING: dummy animation compatibility remains unverified (native frame stride ${data.render.trainingDummy.nativeCalculatedFrameStride} / tile divisor ${data.render.trainingDummy.nativeTileMapperDivisor}).`:'');document.getElementById('status').textContent='Native run status: '+data.status+' — scenario assertions only; this is not visual approval or a whole-item certificate.';document.getElementById('input-boundary').textContent='Native input boundary: '+(data.input?.boundary??data.input?.readBoundary??'see raw input provenance');
document.getElementById('scope').textContent=JSON.stringify({render:{...data.render,frames:undefined,snapshots:undefined},coverage:data.coverage,execution:data.execution,scene:data.scene,endOfRunResources:data.resources,assertions:data.assertions,input:data.input},null,2);
function stop(){if(timer)clearTimeout(timer);timer=null;document.getElementById('play').textContent='Play';}
function show(i){i=Math.max(0,Math.min(frames.length-1,i));seek.value=i;const f=frames[i];document.getElementById('native').src=f.path;document.getElementById('raw').href=f.path;document.getElementById('frame').textContent=`Native tick ${f.tick} · frame ${i+1}/${frames.length} · ${f.width}×${f.height} · particles ${f.particles??'?'} · records ${f.records??'?'}`;const states=f.snapshotIndices.map(n=>data.states[n]),completed=states.filter(s=>s.phase!=='after_input_before_update').at(-1),p=completed?.player||{},npc=completed?.dummy||{};document.getElementById('state-summary').textContent=`Same native tick ${f.tick}: life ${p.life??'?'} · mana ${p.mana??'?'} · target #${npc.slot??'?'} life ${npc.life??'?'}${npc.immortal?' (native immortal)':''} · hit reaction ${f.trainingDummy?.hitReactionTicks??npc.localAI?.[0]??'?'} · active projectiles ${(completed?.projectiles||[]).filter(p=>p.active).length} · generated buff ${p.generatedBuffTicks??'?'} ticks · mobility cooldown ${p.mobilityCooldownTicks??'?'} ticks · lifecycle ${(completed?.projectiles||[]).filter(q=>q.active).map(q=>`#${q.id} ${q.returning?'returning':q.released?'released':'unreleased'}; charge ${q.chargeStatus?`${Math.floor(q.chargeStatus.progress*100)}% ${q.chargeStatus.ready?'READY':''} (${q.chargeStatus.chargeUpdates}/${q.chargeStatus.durationUpdates} updates)`:`${q.chargeTicks??'?'} updates`}; damage ${q.damage??'?'}`).join(' | ')||'none active'} · native dust ${completed?.nativeActiveDust??'?'} ${data.render.nativeDustDrawExecuted?'(original native dust draw)':'(sprites not rendered)'}`;document.getElementById('state').textContent=JSON.stringify({nativeTick:f.tick,frameSha256:f.sha256,nativeDrawReceipt:f,snapshots:states,vfxState:(data.render.snapshots||[]).find(s=>s.tick===f.tick)},null,2);}
const jumps=document.getElementById('event-jumps');for(const f of frames){const events=f.snapshotIndices.flatMap(n=>data.states[n].events||[]).filter(e=>e.kind!=='native_phase');if(!events.length)continue;const b=document.createElement('button');b.textContent=`Tick ${f.tick}: ${[...new Set(events.map(e=>e.kind))].join(', ')}`;b.onclick=()=>{stop();show(frames.indexOf(f))};jumps.appendChild(b);}
for(const mark of data.bookmarks){const index=frames.findIndex(f=>f.tick===mark.tick);if(index<0)continue;const b=document.createElement('button');b.textContent=`Tick ${mark.tick}: ${mark.label}`;b.onclick=()=>{stop();show(index)};document.getElementById('state-jumps').appendChild(b);}
function advance(){const i=+seek.value;if(i>=frames.length-1){stop();return}const dt=(frames[i+1].tick-frames[i].tick)*1000/60/Number(document.getElementById('speed').value);timer=setTimeout(()=>{show(i+1);advance()},Math.max(1,dt));}
seek.oninput=()=>{stop();show(+seek.value)};document.getElementById('next').onclick=()=>{stop();show(+seek.value+1)};document.getElementById('back').onclick=()=>{stop();show(+seek.value-1)};document.getElementById('restart').onclick=()=>{stop();show(0)};document.getElementById('play').onclick=()=>{if(timer){stop();return}if(+seek.value===frames.length-1)show(0);document.getElementById('play').textContent='Pause';advance()};show(0);
</script>'''.replace('TRACE_DATA',data)
    if hashlib.sha256(Path(trace_path).read_bytes()).hexdigest()!=trace_hash:raise ValueError('Native trace changed during export')
    (output/'native.html').write_text(page,encoding='utf-8')
    return {'nativeReplay':str(output/'native.html'),'nativeFrames':len(frames),'nativeGif':str(output/'native.gif') if gif else None,'sourceTraceSha256':metadata['sourceTraceSha256']}
