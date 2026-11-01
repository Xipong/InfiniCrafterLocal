#!/usr/bin/env python3
"""Agent CLI: native execution and read-only telemetry replay. No gameplay simulation."""
from __future__ import annotations
import argparse
import hashlib
import io
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIMIT = 64 * 1024 * 1024


def read_json(path: Path):
    if path.stat().st_size > LIMIT:
        raise ValueError(f"Input exceeds {LIMIT} bytes: {path}")
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()



def drawable(actor):
    return all(isinstance(actor.get(k),(int,float)) and math.isfinite(actor[k]) for k in ("x","y","width","height"))


def validate_trace(trace):
    if not isinstance(trace,dict):raise ValueError("Telemetry must be an object")
    if type(trace.get("schemaVersion")) is not int or trace["schemaVersion"] != 1:
        raise ValueError("Expected telemetry schemaVersion 1")
    if not isinstance(trace.get("execution"), dict):
        raise ValueError("Missing execution provenance")
    for field in ("scene", "input", "coverage", "nativeRender", "resources", "failure"):
        if field in trace and not isinstance(trace[field], dict):
            raise ValueError("Malformed native object: " + field)
    status=trace.get("status")
    if status not in ("passed","failed","error"):
        raise ValueError("Trace is not a terminal native result")
    assertions=trace.get("assertions")
    if not isinstance(assertions,list) or any(not isinstance(a,dict) or a.get("status") not in ("passed","failed") for a in assertions):
        raise ValueError("Malformed assertion results")
    if status=="passed" and (not assertions or any(a["status"]!="passed" for a in assertions)):
        raise ValueError("Passed trace requires nonempty passing assertions")
    if status=="passed" and (trace.get("error") or trace.get("failure")):
        raise ValueError("Passed trace cannot contain native error/failure evidence")
    if status=="failed" and not (trace.get("failure") or any(a["status"]=="failed" for a in assertions)):
        raise ValueError("Failed trace needs a failed assertion or native invariant evidence")
    snapshots = trace.get("snapshots")
    if not isinstance(snapshots, list) or len(snapshots) > 20000:
        raise ValueError("Missing or oversized snapshots")
    for tile in trace.get("scene",{}).get("tiles",[]):
        if any(not isinstance(tile.get(k),(int,float)) or not math.isfinite(tile[k]) for k in ("x","y","width","height")):
            raise ValueError("Invalid native tile rectangle")
    previous = (-2, -2, -1)
    for snap in snapshots:
        if not isinstance(snap,dict) or type(snap.get("tick")) is not int or type(snap.get("substep",0)) is not int:
            raise ValueError("Invalid snapshot/tick")
        if not isinstance(snap.get("player"),dict) or not isinstance(snap.get("dummy"),dict):
            raise ValueError("Snapshot needs recorded player and dummy bounds")
        current = (snap["tick"], snap.get("substep", 0),
                   0 if snap.get("phase")=="after_input_before_update" else 1)
        if current <= previous:
            raise ValueError("Snapshots must be ordered by tick/substep/phase without duplicates")
        previous = current
        if not isinstance(snap.get("events",[]),list) or any(not isinstance(e,dict) or not isinstance(e.get("kind"),str) for e in snap.get("events",[])):
            raise ValueError("Malformed recorded native events")
        if not isinstance(snap.get("projectiles",[]),list) or any(not isinstance(p,dict) for p in snap.get("projectiles",[])):
            raise ValueError("Malformed recorded projectiles")
        for actor in [snap.get("player"), snap.get("dummy"), *snap.get("projectiles", [])]:
            if actor is None:
                continue
            if "nonFinite" in actor and type(actor["nonFinite"]) is not bool:
                raise ValueError("Invalid native nonFinite flag")
            if actor.get("nonFinite") is True and status == "passed":
                raise ValueError("Passed trace contains invalid native state")
            if actor.get("nonFinite") is True and trace.get("status") in ("failed","error"):
                # Native invalid state stays in JSON and is visibly not drawable.
                continue
            for key in ("x", "y", "width", "height"):
                value = actor.get(key)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    raise ValueError(f"Invalid actor coordinate {key}: {value!r}")
            if actor["width"] < 0 or actor["height"] < 0:
                raise ValueError("Negative actor dimensions")
            for key in ("vx", "vy", "rotation"):
                if key in actor and (type(actor[key]) not in (int,float) or not math.isfinite(actor[key])):
                    raise ValueError("Invalid native motion field: " + key)
        exhaustion=snap["player"].get("generatedItemExhaustion",[])
        if not isinstance(exhaustion,list) or any(not isinstance(e,dict) or type(e.get("remainingTicks")) is not int or e["remainingTicks"]<0 for e in exhaustion):
            raise ValueError("Malformed native generated-item exhaustion clocks")
        pose=snap["player"].get("itemPose")
        if pose is not None and not (snap["player"].get("nonFinite") is True and status in ("failed","error")):
            if not isinstance(pose,dict) or any(type(pose.get(k)) not in (int,float) or not math.isfinite(pose[k]) for k in ("x","y","rotation")):
                raise ValueError("Invalid recorded native item pose")
        for event in snap.get("events",[]):
            rectangles=[event] if event.get("kind")=="item_contact_query" else [event.get("native"),event.get("final")] if event.get("kind")=="item_contact_geometry" else []
            for rectangle in rectangles:
                if not isinstance(rectangle,dict) or any(type(rectangle.get(k)) not in (int,float) or not math.isfinite(rectangle[k]) for k in ("x","y","width","height")) or rectangle["width"]<0 or rectangle["height"]<0:
                    raise ValueError("Invalid observed native contact rectangle")
    timeline=trace.get("timeline")
    if snapshots or status!="error":
        if not isinstance(timeline,dict):raise ValueError("Missing native timeline completion evidence")
        requested,completed=timeline.get("requestedTicks"),timeline.get("completedTicks")
        if type(requested) is not int or type(completed) is not int or requested<1 or not 0<=completed<=requested:
            raise ValueError("Invalid native tick accounting")
        completed_frames=[s["tick"] for s in snapshots if s["tick"]>=0 and s.get("phase")!="after_input_before_update"]
        if status=="passed" and (timeline.get("complete") is not True or completed!=requested or completed_frames!=list(range(requested))):
            raise ValueError("Passed trace is incomplete or truncated")
    return trace


def summarize_trace(trace):
    """Read-only aggregate of recorded evidence, never a new pass/fail verdict."""
    trace=validate_trace(trace)
    frames=trace["snapshots"]
    events=[e for frame in frames for e in frame.get("events",[])]
    counts={kind:sum(e.get("kind")==kind for e in events) for kind in sorted({e.get("kind") for e in events if isinstance(e.get("kind"),str)})}
    def endpoints(actor,key):
        values=[frames[i].get(actor,{}).get(key) for i in (0,-1)] if frames else [None,None]
        return {"initial":values[0],"final":values[1],"delta":values[1]-values[0] if all(type(v) in (int,float) for v in values) else None}
    damage={}
    for kind in ("item_hit","hit"):
        hits=[e for e in events if e.get("kind")==kind]
        amounts=[e.get("damageDone") for e in hits]
        valid=all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in amounts)
        if not valid:raise ValueError("Invalid recorded native hit damage")
        damage[kind]={"count":len(hits),"damageDone":sum(amounts),"criticalCount":sum(e.get("crit") is True for e in hits),"unknownCriticalCount":sum(type(e.get("crit")) is not bool for e in hits)}
    return {"status":trace["status"],"error":trace.get("error"),"fullGameParity":trace["execution"].get("fullGameParity"),
            "backend":trace["execution"].get("backend"),"scope":trace["execution"].get("scope"),
            "input":trace.get("input"),"coverage":trace.get("coverage"),"sceneIdentity":{k:trace.get("scene",{}).get(k) for k in ("worldId","sourceWorldId","sourceWorldScoped","currentWorldSource")},"timeline":trace.get("timeline"),"snapshotCount":len(frames),
            "resources":{"mana":endpoints("player","mana"),"playerLife":endpoints("player","life"),"dummyLife":endpoints("dummy","life")},
            "nativeResourceObservers":trace.get("resources"),"finalGeneratedEffects":{k:frames[-1]["player"].get(k) for k in ("generatedBuffTicks","generatedItemExhaustion","moveSpeed","lifeRegen")} if frames else None,"nativeHits":damage,"eventCounts":counts,
            "activeProjectilesAtEnd":sum(p.get("active") is True for p in frames[-1].get("projectiles",[])) if frames else None,
            "failedAssertions":[a for a in trace["assertions"] if a["status"]=="failed"],
            "unsupported":trace["execution"].get("unsupported",[]),
            "note":"Recorded aggregates only. Resource deltas are net changes, not inferred costs or healing; inspect native events for causality."}


def timeline_svg(trace):
    """Plot recorded completed-tick resource/effect clocks, without simulation."""
    trace=validate_trace(trace)
    frames=[s for s in trace["snapshots"] if s["tick"]>=0 and s.get("phase")!="after_input_before_update"]
    if not frames:raise ValueError("Timeline needs recorded completed snapshots")
    ticks=[s["tick"] for s in frames];start,end=min(ticks),max(ticks)
    series=[("Native mana",[s["player"].get("mana") for s in frames],"#38bdf8"),
            ("Generated utility buff ticks",[s["player"].get("generatedBuffTicks") for s in frames],"#86efac"),
            ("Generated-item exhaustion: maximum recorded ticks",[max([e["remainingTicks"] for e in s["player"].get("generatedItemExhaustion",[])]+[0]) if "generatedItemExhaustion" in s["player"] else None for s in frames],"#fbbf24")]
    if any(type(v) not in (int,float) or not math.isfinite(v) for _,values,_ in series for v in values):
        raise ValueError("Timeline requires native mana/buff/exhaustion fields on every completed snapshot")
    esc=lambda value:html.escape(str(value),quote=True)
    x=lambda t:90+(t-start)/max(1,end-start)*850
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="680" viewBox="0 0 1000 680"><rect width="1000" height="680" fill="#111827"/>',
         '<g font-family="sans-serif" fill="#e5e7eb"><text x="24" y="30" font-size="19" fill="#fbbf24">RECORDED NATIVE CLOCKS · NOT TERRARIA RENDERING</text>',
         f'<text x="24" y="55" font-size="13">Status: {esc(trace["status"])} · completed snapshots only · connected samples, not simulated values</text>']
    uses=[(s["tick"],e.get("input")) for s in trace["snapshots"] for e in s.get("events",[]) if e.get("kind")=="input" and e.get("input") in ("primary","alt")]
    for row,(label,values,color) in enumerate(series):
        top=95+row*180;bottom=top+125;maximum=max(1,max(values));y=lambda value:bottom-value/maximum*115
        out.append(f'<text x="24" y="{top-12}" font-size="15">{esc(label)}</text><path d="M90,{top} V{bottom} H940" stroke="#64748b" fill="none"/>')
        out.append(f'<text x="40" y="{top+12}" font-size="12">{maximum:g}</text><text x="62" y="{bottom}" font-size="12">0</text>')
        points=" ".join(f'{x(t):.2f},{y(v):.2f}' for t,v in zip(ticks,values))
        out.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        for tick,kind in uses:
            out.append(f'<path d="M{x(tick):.2f},{top} V{bottom}" stroke="#a78bfa" opacity=".4" stroke-dasharray="3 4"/>')
        for tick in sorted({start,end,*[round(start+(end-start)*n/4) for n in range(1,4)]}):
            out.append(f'<text x="{x(tick):.2f}" y="{bottom+19}" text-anchor="middle" font-size="12">{tick}</text>')
    use_text=", ".join(f'{kind}@{tick}' for tick,kind in uses[:10])+(" …" if len(uses)>10 else "")
    out.append(f'<text x="24" y="640" font-size="13">Input attempts (not proof effect accepted): {esc(use_text or "none")}</text><text x="24" y="663" font-size="12" fill="#94a3b8">X axis: native ticks. Inspect JSON for exact phase timing, source world identity, admission and all observations.</text></g></svg>')
    return "".join(out)


def world_bounds(trace, camera="action"):
    actors = [a for s in trace["snapshots"] for a in
              [s.get("player"), s.get("dummy") if camera=="scene" else None, *s.get("projectiles", [])] if a]
    actors += [e for s in trace["snapshots"] for e in s.get("events",[]) if e.get("kind")=="item_contact_query"]
    actors = [a for a in actors if drawable(a)]
    if camera=="scene":actors += trace.get("scene",{}).get("tiles",[])
    if not actors:
        return (0, 0, 800, 400)
    left = min(a["x"] for a in actors) - 80
    top = min(a["y"] for a in actors) - 100
    right = max(a["x"] + a["width"] for a in actors) + 80
    bottom = max(a["y"] + a["height"] for a in actors) + 80
    return left, top, max(right - left, 320), max(bottom - top, 200)


def frame_svg(trace, index, camera="action"):
    s = trace["snapshots"][index]
    x, y, width, height = world_bounds(trace,camera)
    esc = lambda value: html.escape(str(value), quote=True)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600" viewBox="0 0 1000 600" role="img" aria-label="Telemetry replay, not Terraria rendering">',
           '<rect width="1000" height="600" fill="#101827"/>',
           f'<text x="20" y="30" fill="#fbbf24" font-size="18">NATIVE TELEMETRY REPLAY · NOT TERRARIA RENDER · tick {esc(s["tick"])}</text>']
    invalid=[p for p in [s.get("player"),s.get("dummy"),*s.get("projectiles",[])] if p and p.get("nonFinite")]
    if invalid:
        out.append(f'<text x="20" y="54" fill="#fb7185" font-size="14">NATIVE INVALID STATE: {len(invalid)} actor(s); invalid fields omitted; inspect JSON</text>')
    crowded=len(s.get("projectiles",[]))>3
    out.append(f'<svg x="20" y="70" width="{740 if crowded else 960}" height="430" viewBox="{x} {y} {width} {height}">')
    for tile in trace.get("scene",{}).get("tiles",[]):
        out.append(f'<rect x="{tile["x"]}" y="{tile["y"]}" width="{tile["width"]}" height="{tile["height"]}" fill="#6b4f35" stroke="#c49a6c" stroke-width="1"/>')
    # Historical trails are recorded points only, never extrapolated.
    ids = {str(p["id"]) for prior in trace["snapshots"][:index+1] for p in prior.get("projectiles", [])}
    for pid in sorted(ids):
        points = [f'{p["x"]+p["width"]/2},{p["y"]+p["height"]/2}' for prior in trace["snapshots"][:index+1]
                  for p in prior.get("projectiles", []) if str(p["id"]) == pid and p.get("active",True) and drawable(p)]
        if points:
            out.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#38bdf8" stroke-opacity=".35" stroke-width="1"/>')
    for actor, color, label in [(s.get("player"), "#34d399", "player"), (s.get("dummy"), "#fb7185", "dummy")]+[
            (p, "#38bdf8" if p.get("active",True) else "#64748b", (f'#{p["id"]}' if crowded else f'#{p["id"]} {p.get("entityId", "")}')) for p in s.get("projectiles", [])]:
        if not actor or not drawable(actor):
            continue
        ax, ay, aw, ah = [actor[k] for k in ("x","y","width","height")]
        out.append(f'<rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" fill="{color}" fill-opacity=".18" stroke="{color}" stroke-width="1.5"/>')
        label=label if len(label)<=24 else label[:23]+"…"
        lx = ax-4 if label == "player" else ax+aw+4 if label == "dummy" else ax
        ly = ay-6 if label in ("player", "dummy") else ay-20-(int(actor.get("id",0))%5)*10 if crowded else ay-20
        anchor = "end" if label == "player" else "start"
        if not (crowded and actor.get("active") is False):
            out.append(f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" fill="{color}" font-size="10">{esc(label)}</text>')
        if all(isinstance(actor.get(k),(int,float)) and math.isfinite(actor[k]) for k in ("vx","vy")):
            cx, cy = ax+aw/2, ay+ah/2
            out.append(f'<line x1="{cx}" y1="{cy}" x2="{cx+actor["vx"]*3}" y2="{cy+actor["vy"]*3}" stroke="#fff" stroke-width="1"/>')
    # Contact queries are observed engine rectangles, never inferred from art or actor bounds.
    for event in s.get("events",[]):
        if event.get("kind") == "item_contact_query" and drawable(event):
            out.append(f'<rect x="{event["x"]}" y="{event["y"]}" width="{event["width"]}" height="{event["height"]}" fill="#fb923c" fill-opacity=".12" stroke="#fb923c" stroke-width="1.5"/>')
            out.append(f'<text x="{event["x"]}" y="{event["y"]-20}" fill="#fb923c" font-size="9">native contact query (not hit)</text>')
    pose=s.get("player",{}).get("itemPose",{})
    if trace.get("execution",{}).get("clientGraphics",{}).get("nativeClientBranch") and pose and all(isinstance(pose.get(k),(int,float)) and math.isfinite(pose[k]) for k in ("x","y","rotation")):
        px,py=pose["x"],pose["y"];angle=pose["rotation"]
        out.append(f'<circle cx="{px}" cy="{py}" r="2" fill="#fef08a"/><line x1="{px}" y1="{py}" x2="{px+12*math.cos(angle)}" y2="{py+12*math.sin(angle)}" stroke="#fef08a" stroke-width="1.5"/>')
    player=s.get("player",{}); dummy=s.get("dummy",{})
    if player and drawable(player) and all(isinstance(player.get(k),(int,float)) and math.isfinite(player[k]) for k in ("aimX","aimY")):
        out.append(f'<line x1="{player["x"]+player["width"]/2}" y1="{player["y"]+player["height"]/2}" x2="{player["aimX"]}" y2="{player["aimY"]}" stroke="#34d399" stroke-opacity=".4" stroke-dasharray="3 4"/>')
    out.append('</svg>')
    if crowded:
        out.append('<text x="780" y="90" fill="#e2e8f0" font-size="13">Recorded projectiles</text>')
        for row,p in enumerate(s.get("projectiles",[])[:18]):
            entity=str(p.get("entityId") or "?");entity=entity if len(entity)<=18 else entity[:17]+"…"
            detail=f'#{p["id"]} {entity} · {"active" if p.get("active",True) else "inactive"} · dmg {p.get("damage","?")}'
            out.append(f'<text x="780" y="{110+row*18}" fill="{"#38bdf8" if p.get("active",True) else "#94a3b8"}" font-size="11">{esc(detail)}</text>')
        if len(s["projectiles"])>18:out.append('<text x="780" y="455" fill="#94a3b8" font-size="11">More actors in exact JSON</text>')
    if trace.get("execution",{}).get("clientGraphics",{}).get("phaseFlags",{}).get("Projectile.Update.dedServ") is False:
        hit_events=[e for e in s.get("events",[]) if e.get("kind") in ("item_hit","hit")]
        body_damage=sum(e.get("damageDone",0) for e in hit_events if e["kind"]=="item_hit")
        shot_damage=sum(e.get("damageDone",0) for e in hit_events if e["kind"]=="hit")
        critical=sum(e.get("crit") is True for e in hit_events)
        out.append(f'<text x="20" y="488" fill="#86efac" font-size="13">This snapshot: native item damage {body_damage} · projectile damage {shot_damage} · critical hits {critical} · healed +{sum(e.get("gained",0) for e in s.get("events",[]) if e.get("kind")=="native_heal")}</text>')
    supplies=[a for a in player.get("inventory",[]) if a.get("slot",0)>0]
    if supplies:
        stock=" · ".join(f'slot {a["slot"]}: native {a["nativeType"]} × {a["stack"]}' for a in supplies[:5])
        out.append(f'<text x="20" y="{68 if invalid else 54}" fill="#fde68a" font-size="13">Inventory · {esc(stock)}</text>')
    if trace.get("execution",{}).get("clientGraphics",{}).get("nativeClientBranch"):
        out.append(f'<text x="20" y="{68 if invalid or supplies else 54}" fill="#fdba74" font-size="13">Native client contact · orange = queried box, not hit · yellow = pose marker, not artwork</text>')
    if "manaCost" in player:
        slots=", ".join(f'{a["placement"]}:{a["slot"]}' for a in player.get("armor",[])) or "none"
        equipment=f'Native equipment · max mana {player.get("maxMana","?")} · mana cost {player["manaCost"]:.3f} · defense {player.get("defense","?")} · slots {slots}'
        out.append(f'<text x="20" y="507" fill="#a5b4fc" font-size="13">{esc(equipment)}</text>')
    if "generatedBuffTicks" in player:
        stats=f'Generated buff ticks {player["generatedBuffTicks"]} · jump boost {player.get("jumpSpeedBoost","?")} · move {player.get("moveSpeed","?")} · pick {player.get("pickSpeed","?")}'
        if player.get("generatedItemExhaustion"):
            remaining=max(e["remainingTicks"] for e in player["generatedItemExhaustion"])
            stats=f'Generated buff ticks {player["generatedBuffTicks"]} · item exhaustion max {remaining} · move {player.get("moveSpeed","?")} · life regen {player.get("lifeRegen","?")}'

        out.append(f'<text x="20" y="525" fill="#c4b5fd" font-size="14">{esc(stats)}</text>')
    state=f'Player life {player.get("life","?")} · mana {player.get("mana","?")} · channel {player.get("channel","?")} | Dummy life {dummy.get("life","?")}'
    if trace.get("execution",{}).get("clientGraphics",{}).get("nativeClientBranch"):
        state += f' · native animation {pose.get("itemAnimation","?")}'
    out.append(f'<text x="20" y="550" fill="#e2e8f0" font-size="16">{esc(state)}</text>')
    out.append(f'<text x="20" y="580" fill="#94a3b8" font-size="12">Camera: {camera} (offscreen actors may be omitted) · entity boxes, not custom collision shapes · dashed = aim</text>')
    out.append('</svg>')
    return "".join(out)


def render(trace_path: Path, output: Path, png=False, gif=False, camera="action"):
    if png or gif:
        try:
            import cairosvg
        except ImportError as exc:
            raise RuntimeError("PNG export requires optional cairosvg; SVG/HTML need only Python stdlib") from exc
    trace = validate_trace(read_json(trace_path))
    if not trace["snapshots"]:
        raise ValueError("No snapshots: native run did not establish replayable execution")
    output.mkdir(parents=True, exist_ok=True)
    # The JSON uses a non-executing script block and escapes HTML delimiters.
    data = json.dumps(trace, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    frame_count = len(trace["snapshots"])
    page = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Item test workbench · native telemetry</title>
<style>body{margin:24px auto;max-width:1200px;padding:0 18px;background:#101827;color:#e2e8f0;font:15px system-ui}h1{font-size:25px}strong{color:#fbbf24}.panel{padding:16px;border:1px solid #334155;border-radius:10px;margin:12px 0}button,input{accent-color:#38bdf8}button{padding:8px 14px;background:#1e293b;color:white;border:1px solid #64748b;border-radius:5px}#scene svg{width:100%;height:440px}#seek{width:55%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}summary{cursor:pointer}#status{font-weight:600;white-space:pre-wrap}#provenance{white-space:pre-wrap;font-size:12px}</style>
<h1>Item test workbench</h1><strong>Recorded native telemetry · abstract replay, NOT Terraria rendering</strong>
<div class="panel" id="provenance"></div><div class="panel"><button id="play">Play</button> <button id="previous">− step</button> <button id="next">+ step</button> <input id="seek" type="range" min="0" value="0" aria-label="Recorded frame"> <span id="clock"></span> <select id="camera" aria-label="Replay camera"><option value="action">Player + projectiles</option><option value="scene">Whole scene</option></select><small> · 10 recorded frames/s review speed</small><div id="scene"></div></div>
<div class="panel"><div id="status"></div><pre id="checks"></pre></div><details class="panel"><summary>Exact frame state (code-readable)</summary><pre id="state"></pre></details>
<script type="application/json" id="trace">TRACE_DATA</script>
<script>
(()=>{
const trace=JSON.parse(document.getElementById('trace').textContent), frames=trace.snapshots;
const ns='http://www.w3.org/2000/svg';
const valid=a=>a&&[a.x,a.y,a.width,a.height].every(Number.isFinite);
const actionActors=frames.flatMap(s=>[s.player,...(s.projectiles||[]),...(s.events||[]).filter(e=>e.kind==='item_contact_query')]).filter(valid);
const sceneActors=[...actionActors,...frames.map(s=>s.dummy).filter(valid),...(trace.scene?.tiles||[])];
function bounds(actors){if(!actors.length)return [0,0,800,400];const l=actors.reduce((v,a)=>Math.min(v,a.x),Infinity)-80,t=actors.reduce((v,a)=>Math.min(v,a.y),Infinity)-100;return [l,t,Math.max(l+320,actors.reduce((v,a)=>Math.max(v,a.x+a.width),-Infinity)+80),Math.max(t+200,actors.reduce((v,a)=>Math.max(v,a.y+a.height),-Infinity)+80)];}
const cameras={action:bounds(actionActors),scene:bounds(sceneActors)};
document.getElementById('camera').value='CAMERA_MODE';
function el(name,attrs,text){const e=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function draw(i){const [left,top,right,bottom]=cameras[document.getElementById('camera').value];const s=frames[i], outer=el('svg',{viewBox:'0 0 1000 600'}), svg=el('svg',{x:20,y:70,width:(s.projectiles||[]).length>3?740:960,height:430,viewBox:`${left} ${top} ${Math.max(320,right-left)} ${Math.max(200,bottom-top)}`,role:'img','aria-label':'Abstract telemetry replay'});
outer.append(el('rect',{width:1000,height:600,fill:'#101827'}));
outer.append(el('text',{x:20,y:30,fill:'#fbbf24','font-size':18},`NATIVE TELEMETRY REPLAY · NOT TERRARIA RENDER · tick ${s.tick}`));
for(const t of trace.scene?.tiles||[])svg.append(el('rect',{x:t.x,y:t.y,width:t.width,height:t.height,fill:'#6b4f35',stroke:'#c49a6c','stroke-width':1}));
const crowded=(s.projectiles||[]).length>3;
const trails=new Map();for(let j=Math.max(0,i-120);j<=i;j++)for(const p of frames[j].projectiles||[]){if(p.active===false||![p.x,p.y,p.width,p.height].every(Number.isFinite))continue;const key=String(p.id);if(!trails.has(key))trails.set(key,[]);trails.get(key).push(`${p.x+p.width/2},${p.y+p.height/2}`);}
for(const points of trails.values())svg.append(el('polyline',{points:points.join(' '),fill:'none',stroke:'#38bdf8','stroke-opacity':.35,'stroke-width':1}));
for(const [a,color,label] of [[s.player,'#34d399','player'],[s.dummy,'#fb7185','dummy'],...(s.projectiles||[]).map(p=>[p,p.active===false?'#64748b':'#38bdf8',crowded?`#${p.id}`:`#${p.id} ${p.entityId||''}`])]){if(!a||![a.x,a.y,a.width,a.height].every(Number.isFinite))continue;svg.append(el('rect',{x:a.x,y:a.y,width:a.width,height:a.height,fill:color,'fill-opacity':.18,stroke:color,'stroke-width':1.5}));if(!(crowded&&a.active===false))svg.append(el('text',{x:label==='player'?a.x-4:label==='dummy'?a.x+a.width+4:a.x,y:a.y-(label==='player'||label==='dummy'?6:20+(crowded?(Number(a.id)||0)%5*10:0)),'text-anchor':label==='player'?'end':'start',fill:color,'font-size':10},label.length>24?label.slice(0,23)+'…':label));if(Number.isFinite(a.vx)&&Number.isFinite(a.vy))svg.append(el('line',{x1:a.x+a.width/2,y1:a.y+a.height/2,x2:a.x+a.width/2+a.vx*3,y2:a.y+a.height/2+a.vy*3,stroke:'#fff','stroke-width':1}));}
for(const e of s.events||[])if(e.kind==='item_contact_query'&&valid(e)){svg.append(el('rect',{x:e.x,y:e.y,width:e.width,height:e.height,fill:'#fb923c','fill-opacity':.12,stroke:'#fb923c','stroke-width':1.5}));svg.append(el('text',{x:e.x,y:e.y-20,fill:'#fb923c','font-size':9},'native contact query (not hit)'));}
const pose=s.player?.itemPose;if(trace.execution?.clientGraphics?.nativeClientBranch&&pose&&[pose.x,pose.y,pose.rotation].every(Number.isFinite)){svg.append(el('circle',{cx:pose.x,cy:pose.y,r:2,fill:'#fef08a'}));svg.append(el('line',{x1:pose.x,y1:pose.y,x2:pose.x+12*Math.cos(pose.rotation),y2:pose.y+12*Math.sin(pose.rotation),stroke:'#fef08a','stroke-width':1.5}));}
const invalid=[s.player,s.dummy,...(s.projectiles||[])].filter(p=>p&&p.nonFinite);if(invalid.length)outer.append(el('text',{x:20,y:54,fill:'#fb7185','font-size':14},`NATIVE INVALID STATE: ${invalid.length} actor(s); invalid fields omitted; see exact JSON`));
const player=s.player||{}, dummy=s.dummy||{};
const supplies=(player.inventory||[]).filter(a=>a.slot>0);if(supplies.length)outer.append(el('text',{x:20,y:invalid.length?68:54,fill:'#fde68a','font-size':13},'Inventory · '+supplies.slice(0,5).map(a=>`slot ${a.slot}: native ${a.nativeType} × ${a.stack}`).join(' · ')));
if(trace.execution?.clientGraphics?.nativeClientBranch)outer.append(el('text',{x:20,y:invalid.length||supplies.length?68:54,fill:'#fdba74','font-size':13},'Native client contact · orange = queried box, not hit · yellow = pose marker, not artwork'));
if('manaCost' in player){const slots=(player.armor||[]).map(a=>`${a.placement}:${a.slot}`).join(', ')||'none';outer.append(el('text',{x:20,y:507,fill:'#a5b4fc','font-size':13},`Native equipment · max mana ${player.maxMana} · mana cost ${Number(player.manaCost).toFixed(3)} · defense ${player.defense} · slots ${slots}`));}
if([player.x,player.y,player.width,player.height,player.aimX,player.aimY].every(Number.isFinite))svg.append(el('line',{x1:player.x+player.width/2,y1:player.y+player.height/2,x2:player.aimX,y2:player.aimY,stroke:'#34d399','stroke-opacity':.4,'stroke-dasharray':'3 4'}));
if('generatedBuffTicks' in player){const stats=player.generatedItemExhaustion?.length?`Generated buff ticks ${player.generatedBuffTicks} · item exhaustion max ${Math.max(...player.generatedItemExhaustion.map(e=>e.remainingTicks))} · move ${player.moveSpeed} · life regen ${player.lifeRegen}`:`Generated buff ticks ${player.generatedBuffTicks} · jump boost ${player.jumpSpeedBoost} · move ${player.moveSpeed} · pick ${player.pickSpeed}`;outer.append(el('text',{x:20,y:525,fill:'#c4b5fd','font-size':14},stats));}
outer.append(el('text',{x:20,y:550,fill:'#e2e8f0','font-size':16},`Player life ${player.life} · mana ${player.mana} · channel ${player.channel} | Dummy life ${dummy.life}${trace.execution?.clientGraphics?.nativeClientBranch?` · native animation ${pose?.itemAnimation}`:''}`));
outer.append(el('text',{x:20,y:580,fill:'#94a3b8','font-size':12},`Camera: ${document.getElementById('camera').value} (offscreen actors may be omitted) · entity boxes · trails = last 120 frames`));
outer.append(svg);
if(crowded){outer.append(el('text',{x:780,y:90,fill:'#e2e8f0','font-size':13},'Recorded projectiles'));(s.projectiles||[]).slice(0,18).forEach((p,row)=>outer.append(el('text',{x:780,y:110+row*18,fill:p.active===false?'#94a3b8':'#38bdf8','font-size':11},`#${p.id} ${String(p.entityId||'?').slice(0,18)} · ${p.active===false?'inactive':'active'} · dmg ${p.damage??'?'}`)));if(s.projectiles.length>18)outer.append(el('text',{x:780,y:455,fill:'#94a3b8','font-size':11},'More actors in exact JSON'));}
if(trace.execution?.clientGraphics?.phaseFlags?.['Projectile.Update.dedServ']===false){const hits=(s.events||[]).filter(e=>e.kind==='item_hit'||e.kind==='hit');outer.append(el('text',{x:20,y:488,fill:'#86efac','font-size':13},`This snapshot: native item damage ${hits.filter(e=>e.kind==='item_hit').reduce((a,e)=>a+(e.damageDone||0),0)} · projectile damage ${hits.filter(e=>e.kind==='hit').reduce((a,e)=>a+(e.damageDone||0),0)} · critical hits ${hits.filter(e=>e.crit===true).length} · healed +${(s.events||[]).filter(e=>e.kind==='native_heal').reduce((a,e)=>a+(e.gained||0),0)}`));}
document.getElementById('scene').replaceChildren(outer);}
const seek=document.getElementById('seek'); seek.max=frames.length-1;
document.getElementById('provenance').textContent=JSON.stringify({execution:trace.execution,coverage:trace.coverage,timeline:trace.timeline,input:trace.input},null,2);
const checks=trace.assertions||[];document.getElementById('checks').textContent=JSON.stringify(checks,null,2);
document.getElementById('status').textContent='Run: '+(trace.status||'unknown')+' · Whole item not certified · Assertions: '+checks.filter(c=>c.status==='passed').length+' passed; '+checks.filter(c=>c.status==='failed').length+' failed. Unsupported / notRun are not passes.'+(trace.error?'\\nERROR: '+trace.error:'')+(trace.failure?'\\nFAILURE: '+JSON.stringify(trace.failure):'');
function show(i){i=Math.max(0,Math.min(frames.length-1,i));seek.value=i;draw(i);document.getElementById('state').textContent=JSON.stringify(trace.snapshots[i],null,2);document.getElementById('clock').textContent=`frame ${i+1}/${frames.length} · tick ${trace.snapshots[i].tick}`;}
let timer=null;function stop(){clearInterval(timer);timer=null;document.getElementById('play').textContent='Play';}
document.getElementById('camera').onchange=()=>{stop();show(+seek.value)};seek.oninput=()=>{stop();show(+seek.value)};document.getElementById('previous').onclick=()=>{stop();show(+seek.value-1)};document.getElementById('next').onclick=()=>{stop();show(+seek.value+1)};
document.getElementById('play').onclick=()=>{if(timer){stop();return}if(+seek.value===frames.length-1)show(0);document.getElementById('play').textContent='Pause';timer=setInterval(()=>{if(+seek.value>=frames.length-1){stop();return}show(+seek.value+1)},100)};show(0);
})();
</script>'''.replace('TRACE_DATA',data).replace('CAMERA_MODE',camera)
    (output / "replay.html").write_text(page,encoding="utf-8")
    # Keep representative SVG frames and all exact data; avoid thousands of duplicate assets.
    keyframes={0,frame_count//4,frame_count//2,3*frame_count//4,frame_count-1}
    event_frames=[i for i,s in enumerate(trace["snapshots"]) if s.get("events")]
    keyframes.update(event_frames[:8]);keyframes.update(event_frames[-2:])
    for index in sorted(keyframes):
        svg=frame_svg(trace,index,camera)
        (output/f"frame-{index:05}.svg").write_text(svg,encoding="utf-8")
        if png:
            cairosvg.svg2png(bytestring=svg.encode(),write_to=str(output/f"frame-{index:05}.png"))
    if gif:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("GIF export requires optional Pillow") from exc
        stride=max(1,math.ceil(frame_count/180))
        indices=sorted(set(range(0,frame_count,stride))|{frame_count-1})
        images=[]
        for index in indices:
            pixels=cairosvg.svg2png(bytestring=frame_svg(trace,index,camera).encode(),output_width=800,output_height=480)
            images.append(Image.open(io.BytesIO(pixels)).convert("RGB"))
        durations=[max(20,round((trace["snapshots"][b]["tick"]-trace["snapshots"][a]["tick"])*100/60)*10) for a,b in zip(indices,indices[1:])]+[800]
        images[0].save(output/"replay.gif",save_all=True,append_images=images[1:],duration=durations,loop=0)
        (output/"gif-export.json").write_text(json.dumps({"kind":"abstract-native-telemetry-replay-not-game-render","frameIndices":indices,"nativeTicksPerSecond":60,"frameDurationsMs":durations,"timing":"quantized GIF review playback; use native tick labels for timing assertions","finalPauseMs":800,"interpolated":False}))
    (output/"telemetry.json").write_text(json.dumps(trace,indent=2,allow_nan=False),encoding="utf-8")
    return {"replay":str(output/"replay.html"),"frames":frame_count,"sourceSha256":digest(trace_path)}


def native_environment():
    from native_environment import discover
    return discover(ROOT)


def doctor():
    env, sources = native_environment()
    dotnet = env.get("DOTNET", "dotnet")
    tml = Path(env.get("INFINI_TML_REFERENCE_DIR", "/nonexistent")).expanduser()
    deps = Path(env.get("INFINI_TML_DEPS_SRC", "/nonexistent")).expanduser()
    checks = {"dotnet":shutil.which(dotnet),"tModLoader":(tml/"tModLoader.dll").is_file(),
              "ParticleLibrary":(deps/"ParticleLibrary/ParticleLibrary.dll").is_file(),
              "Luminance":(deps/"Luminance/bin/Debug/net8.0/Luminance.dll").is_file()}
    graphics = {
        "nativeLibraries": all((Path(env.get("INFINI_TML_NATIVE_DIR", "/nonexistent")) / name).is_file()
                               for name in ("libSDL2-2.0.so.0", "libFNA3D.so.0", "libFAudio.so.0", "libtheorafile.so")),
        "tModLoaderContent": (Path(env.get("INFINI_TML_CONTENT_DIR", "/nonexistent")) / "PixelShader.xnb").is_file(),
        "playerAssets": (Path(env.get("INFINI_PLAYER_ASSET_DIR", "/nonexistent")) / "Images/MagicPixel.png").is_file(),
        "particleAssets": all((Path(env.get("INFINI_PARTICLE_ASSET_DIR", "/nonexistent")) / name).is_file()
                              for name in ("Assets/Textures/Star.png", "Assets/Effects/InstancedParticle.xnb")),
    }
    return {"ready":all(checks.values()), "checks":checks,
            "graphicsFilesPresent": graphics, "paths": {name:env[name] for name in sources if name in env},
            "discovery": sources,
            "note":"Basic file checks only: neither graphics initialization, matching versions, complete assets nor native execution are verified."}


def source_fingerprint():
    files = sorted([*ROOT.glob("ModSources/InfiniCrafterLocal/**/*.cs"),
                    *ROOT.glob("tools/native/EngineRuntimeChecks*.cs"),
                    *HERE.glob("*.cs"), *HERE.glob("*.csproj"), *HERE.glob("production-mod/*.csproj"),
                    HERE/"vanilla-item-assets.json",
                    *ROOT.glob("ModSources/InfiniCrafterLocal/Assets/**/*.*"),
                    *ROOT.glob("ModSources/InfiniCrafterLocal/Localization/**/*.*"),
                    ROOT/"ModSources/InfiniCrafterLocal/build.txt"])
    hasher = hashlib.sha256()
    for path in files:
        if "obj" in path.parts or "bin" in path.parts:
            continue
        hasher.update(str(path.relative_to(ROOT)).encode()); hasher.update(path.read_bytes())
    return hasher.hexdigest()


def configured_reference_paths():
    paths = {}
    env, _ = native_environment()
    tml = env.get("INFINI_TML_REFERENCE_DIR")
    deps = env.get("INFINI_TML_DEPS_SRC")
    if tml:
        paths["tModLoader"] = Path(tml).expanduser().resolve() / "tModLoader.dll"
    if deps:
        base = Path(deps).expanduser().resolve()
        paths["ParticleLibrary"] = base / "ParticleLibrary/ParticleLibrary.dll"
        paths["Luminance"] = base / "Luminance/bin/Debug/net8.0/Luminance.dll"
    return paths


def build_state(dll):
    assets={str(p.relative_to(dll.parent)):digest(p) for p in sorted([
        *(dll.parent/"native-assets").glob("*.png"),
        *(p for p in (dll.parent/"native-mod").rglob("*") if p.is_file())])}
    runtime = sorted({*dll.parent.glob("*.dll"), *dll.parent.glob("*.deps.json"), *dll.parent.glob("*.runtimeconfig.json")})
    references = {name:{"path":str(path),"sha256":digest(path) if path.is_file() else None}
                  for name,path in configured_reference_paths().items()}
    return {"sourceSha256":source_fingerprint(),"dllSha256":digest(dll),"nativeAssetSha256":assets,
            "runtimeFilesSha256":{p.name:digest(p) for p in runtime},"configuredReferences":references}


def native_binaries_state(dll):
    """Bind direct native evidence to both the host and its IFC assembly."""
    dll = Path(dll)
    mod = dll.parent / "InfiniCrafterLocal.dll"
    if not dll.is_file() or not mod.is_file():
        raise FileNotFoundError("Both ItemTestWorkbench.dll and its sibling InfiniCrafterLocal.dll are required")
    return {"nativeDllSha256": digest(dll), "productionDllSha256": digest(mod)}


def build():
    state=doctor()
    if not state["ready"]:
        raise RuntimeError("Native prerequisites unavailable: "+json.dumps(state))
    env, _ = native_environment()
    command=[env.get("DOTNET","dotnet"),"build",str(HERE/"ItemTestWorkbench.csproj"),"-c","Release",
             "-p:InfiniTmlReferenceDir="+str(Path(env["INFINI_TML_REFERENCE_DIR"]).expanduser().resolve()),
             "-p:InfiniExternalDepsRoot="+str(Path(env["INFINI_TML_DEPS_SRC"]).expanduser().resolve())]
    subprocess.run(command,cwd=ROOT,env=env,check=True,stdout=sys.stderr)
    dll=HERE/"bin/Release/net8.0/ItemTestWorkbench.dll"
    (dll.parent/"build-provenance.json").write_text(json.dumps(build_state(dll)))


def native_executable(no_build=False):
    state = doctor()
    if not state["ready"]:
        raise RuntimeError("Native prerequisites unavailable: " + json.dumps(state))
    if not no_build:
        build()
    dll = HERE / "bin/Release/net8.0/ItemTestWorkbench.dll"
    if not dll.is_file():
        raise RuntimeError("Native executable absent; run build first")
    provenance_path = dll.parent / "build-provenance.json"
    if not provenance_path.is_file():
        raise RuntimeError("Build provenance missing; run workbench build (not raw dotnet build)")
    provenance = read_json(provenance_path)
    if provenance != build_state(dll):
        raise RuntimeError("Native build is stale or modified; rebuild before executing")
    return dll, provenance


def fixtures(output, no_build=False):
    """Expose the native fixture owner without requiring agents to find its DLL."""
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh fixture directory")
    dll, provenance = native_executable(no_build)
    subprocess.run([os.environ.get("DOTNET", "dotnet"), str(dll), "--write-fixtures", str(output)],
                   cwd=ROOT, check=True, stdout=sys.stderr, timeout=180)
    if build_state(dll) != provenance:
        raise RuntimeError("Native build changed while writing fixtures")
    paths = sorted(output.glob("*.json"))
    if not paths:
        raise RuntimeError("Native fixture writer produced no JSON files")
    return {"kind": "synthetic-native-fixtures", "directory": str(output),
            "files": {p.name: digest(p) for p in paths}}


def execute_loader_run(args):
    """Run the real DLL autoload path without packaging or launching Terraria."""
    if not 1 <= args.timeout <= 3600:
        raise ValueError("Timeout must be 1..3600 seconds")
    if bool(args.probe_dll) != bool(args.probe_mod_root):
        raise ValueError("--probe-dll and --probe-mod-root must be supplied together")
    item = args.item.resolve() if args.item is not None else None
    native_item = getattr(args,"native_item",None)
    if (item is None) == (native_item is None):
        raise ValueError("Supply exactly one --item or --native-item")
    if item is None and args.item_boundary != "fresh":
        raise ValueError("item-boundary applies only to generated JSON")
    scenario, output = args.scenario.resolve(), args.out.resolve()
    if item is not None:read_json(item)
    scene = read_json(scenario)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh output directory")
    dll, provenance = native_executable(args.no_build)
    output.mkdir(parents=True, exist_ok=True)
    if item is not None:shutil.copyfile(item, output / "item.json")
    shutil.copyfile(scenario, output / "scenario.json")
    item_sha, scenario_sha = digest(output / "item.json") if item is not None else None, digest(output / "scenario.json")
    command = [os.environ.get("DOTNET", "dotnet"), str(dll), "--native-loader-scene"]
    command += ["--item",str(output/"item.json")] if item is not None else ["--native-item",native_item]
    command += ["--scenario", str(output / "scenario.json"),
               "--output", str(output / "native.json"), "--item-boundary", args.item_boundary]
    external = {}
    external_content = {}
    def mod_content_state(root, external=False):
        paths={root/"build.txt"}
        if external:
            # External source mods may load Items/, Projectiles/, Effects/,
            # Sounds/, or any other content path. Do not treat Assets/ as the
            # complete resource tree. Git bookkeeping is not runtime content.
            paths.update(p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts)
        else:
            for name in ("Localization","Assets","asset-content"):
                paths.update(p for p in (root/name).rglob("*") if p.is_file())
        return {str(p.relative_to(root)):digest(p) if p.is_file() else None for p in sorted(paths)}
    # The native host permits a source-root override. Bind evidence to the
    # effective metadata/assets, not just the default copied build content.
    env, _ = native_environment()
    configured_root = env.get("INFINI_MOD_SOURCE_ROOT", "")
    production_root = (Path(configured_root) if configured_root.strip() else dll.parent / "native-mod").resolve()
    env["INFINI_MOD_SOURCE_ROOT"] = str(production_root)
    production_content = {"root": str(production_root), "files": mod_content_state(production_root)}
    pairs = []
    if args.probe_dll:
        pairs.append((args.probe_dll, args.probe_mod_root, True))
    pairs.extend((Path(dll), Path(root), False) for dll, root in getattr(args, "mods", []))
    for mod_dll, mod_root, legacy in pairs:
        probe = mod_dll.expanduser().resolve(strict=True)
        probe_root = mod_root.expanduser().resolve(strict=True)
        if not probe.is_file() or not probe_root.is_dir():
            raise ValueError("Each extra mod requires an existing DLL and source directory")
        command.extend((["--probe-dll", str(probe), "--probe-mod-root", str(probe_root)] if legacy else
                        ["--mod-dll", str(probe), "--mod-root", str(probe_root)]))
        external[str(probe)] = digest(probe)
        external_content[str(probe_root)] = mod_content_state(probe_root, external=True)
    try:
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        decode = lambda v: v.decode(errors="replace") if isinstance(v, bytes) else v or ""
        proc = subprocess.CompletedProcess(command, 124, decode(exc.stdout), decode(exc.stderr) + "\nNative loader scene timed out")
    (output / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (output / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    unchanged = build_state(dll) == provenance and all(Path(p).is_file() and digest(Path(p)) == h for p,h in external.items())
    unchanged = unchanged and all(mod_content_state(Path(p), external=True) == h for p,h in external_content.items())
    unchanged = unchanged and mod_content_state(production_root) == production_content["files"]
    unchanged = unchanged and (item is None or digest(output / "item.json") == item_sha) and digest(output / "scenario.json") == scenario_sha
    receipt = {"command": command, "exitCode": proc.returncode, "build": provenance,
               "itemSha256": item_sha, "nativeItem": native_item, "scenarioSha256": scenario_sha,
               "extraAssemblies": external, "extraContent": external_content, "productionContent": production_content, "binariesUnchanged": unchanged}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if not unchanged:
        raise RuntimeError("Native loader inputs or binaries changed during execution")
    trace = read_json(output / "native.json")
    status = trace.get("status")
    expected = {"passed": 0, "failed": 1, "error": 2}.get(status)
    if expected is None or proc.returncode != expected:
        raise RuntimeError("Native loader report and process exit disagree; inspect logs")
    if status == "passed":
        frames, checks = trace.get("snapshots", []), trace.get("assertions", [])
        if not checks or any(c.get("status") != "passed" for c in checks) or not frames or frames[-1].get("tick") != scene.get("ticks",120)-1:
            raise RuntimeError("Incomplete native loader report cannot pass")
    print(json.dumps({"status": status, "trace": str(output / "native.json"), "combat": trace.get("combat")}, ensure_ascii=False))
    return expected


def execute_run(args):
    from agent_evidence import NATIVE_EXIT, report, markdown
    if not 1 <= args.timeout <= 3600:
        raise ValueError("Timeout must be 1..3600 seconds")
    if args.review == "none" and (args.png or args.gif):
        raise ValueError("PNG/GIF export requires --review schematic or native")
    if args.vanilla_item is not None and args.vanilla_item.lstrip("-").isdigit() and int(args.vanilla_item) <= 0:
        raise ValueError("Vanilla ItemID must be positive")
    if args.item_boundary != "fresh" and args.item is None:
        raise ValueError("Saved-cache boundary requires --item")
    item = args.item.resolve() if args.item is not None else None
    scenario, output = args.scenario.resolve(), args.out.resolve()
    if item is not None:
        read_json(item)
    read_json(scenario)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output directory is not empty; use a new run directory to preserve evidence")
    dll, provenance = native_executable(args.no_build)
    output.mkdir(parents=True, exist_ok=True)
    if item is not None:
        shutil.copyfile(item, output / "item.json")
    shutil.copyfile(scenario, output / "scenario.json")
    item_sha = digest(output / "item.json") if item is not None else None
    scenario_sha = digest(output / "scenario.json")
    trace_path = output / "native.json"
    cmd = [os.environ.get("DOTNET", "dotnet"), str(dll)]
    cmd += ["--item", str(output / "item.json")] if item is not None else ["--vanilla-item", str(args.vanilla_item)]
    cmd += ["--scenario", str(output / "scenario.json"), "--output", str(trace_path)]
    if args.item_boundary != "fresh":
        cmd.extend(["--item-boundary", args.item_boundary])
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=native_environment()[0], capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        decode = lambda v: v.decode(errors="replace") if isinstance(v, bytes) else v or ""
        proc = subprocess.CompletedProcess(cmd, 124, decode(exc.stdout),
            decode(exc.stderr) + f"\nNative execution timed out after {args.timeout} seconds")
    except OSError as exc:
        proc = subprocess.CompletedProcess(cmd, 2, "", str(exc))
    (output / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (output / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    receipt = {"schemaVersion": 2, "command": cmd, "exitCode": proc.returncode,
        "nativeExitCode": proc.returncode, "scenarioSha256": scenario_sha,
        "sourceScenarioPath": str(scenario), "nativeDllSha256": provenance["dllSha256"],
        "inputBoundary": args.item_boundary, "timeoutSeconds": args.timeout,
        **{k: provenance[k] for k in ("sourceSha256", "nativeAssetSha256", "runtimeFilesSha256", "configuredReferences")},
        "dependencyReceiptScope": "Copied runtime DLL/load manifest hashes; build references are not loaded-byte proof",
        "review": {"requested": args.review, "status": "notRun"}}
    if item is None:
        receipt["source"] = {"kind": "vanilla", "requestedItem": args.vanilla_item}
    else:
        receipt.update(itemSha256=item_sha, sourceItemPath=str(item), source={"kind": "generated-json"})
    errors = []
    try:
        if (item is not None and digest(output / "item.json") != item_sha) or digest(output / "scenario.json") != scenario_sha:
            errors.append("Archived input changed during execution; result is not trustworthy")
        if build_state(dll) != provenance:
            errors.append("Native source/build/assets changed during execution; result is not trustworthy")
    except (OSError,ValueError) as exc:
        errors.append("Native inputs/build evidence unavailable after execution: " + str(exc))
    native = None
    try:
        native = validate_trace(read_json(trace_path))
        receipt["traceSha256"] = digest(trace_path)
        receipt["nativeStatus"] = native["status"]
        if proc.returncode != NATIVE_EXIT[native["status"]]:
            errors.append("Native exit code disagrees with terminal trace status")
        observed = native.get("input")
        if observed is not None and (observed.get("scenarioSha256") != scenario_sha or
                                    item is not None and observed.get("sha256") != item_sha):
            errors.append("Native input hashes disagree with archived input")
        if native["status"] != "error" and not isinstance(observed, dict):
            errors.append("Native behavioral result is missing input provenance")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append("Missing or invalid terminal native trace: " + str(exc))
    if errors:
        receipt["error"] = "; ".join(errors)
        receipt["exitCode"] = 2
    # Save a receipt even if PNG/GIF export or native trace validation fails.
    receipt_path = output / "run.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if native is not None and not errors and args.review != "none" and native["snapshots"]:
        try:
            if args.review == "native":
                from native_review import export_native_review
                if args.png:
                    raise ValueError("Native PNGs are recorded by scenario.nativeRender; --png selects schematic export")
                receipt.update(export_native_review(native, trace_path, output / "review", args.gif, args.gif_stride))
            else:
                receipt.update(render(trace_path, output / "review", args.png, args.gif, args.camera))
            receipt["review"]["status"] = "exported"
        except (ValueError, OSError, RuntimeError, ImportError, KeyError, TypeError) as exc:
            receipt["review"]["status"] = "error"
            receipt["reviewErrors"] = [str(exc)]
            receipt["exitCode"] = 2
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if native is not None:
        try:
            data = report(trace_path)
            (output / "agent-report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            (output / "agent-report.md").write_text(markdown(data), encoding="utf-8")
            receipt["agentReport"] = str(output / "agent-report.json")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            receipt["error"] = "; ".join(filter(None, [receipt.get("error"), "Agent evidence validation failed: " + str(exc)]))
            receipt["exitCode"] = 2
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    from probe import add_parser,execute_probe
    add_parser(sub)
    sub.add_parser("doctor");sub.add_parser("build");sub.add_parser("test",help="Run offline utility tests; not native gameplay verification")
    r=sub.add_parser("setup-particle",help="Install the pinned ParticleLibrary DLL and resources");r.add_argument("--deps-root",type=Path,help="Dependency root (default: INFINI_TML_DEPS_SRC or artifacts/dependencies)")
    for name,help_text in (("setup-luminance","Install the pinned Luminance DLL and textures"),("setup-vfx","Install both ParticleLibrary and Luminance")):
        r=sub.add_parser(name,help=help_text);r.add_argument("--deps-root",type=Path,help="Dependency root (default: INFINI_TML_DEPS_SRC or artifacts/dependencies)")
    sub.add_parser("catalog",help="Read-only inventory of supplied scenarios, actions and assertions")
    r=sub.add_parser("fixtures",help="Write synthetic fixtures through the native owner");r.add_argument("--out",type=Path,required=True);r.add_argument("--no-build",action="store_true")
    r=sub.add_parser("loader-run",help="Standalone native tML DLL autoload and controlled combat scene; no .tmod or game launch")
    sources=r.add_mutually_exclusive_group(required=True);sources.add_argument("--item",type=Path);sources.add_argument("--native-item",help="Native ItemID/name or registered Mod/Item")
    r.add_argument("--scenario",type=Path,required=True);r.add_argument("--out",type=Path,required=True)
    r.add_argument("--no-build",action="store_true");r.add_argument("--item-boundary",choices=("fresh","local_cache"),default="fresh")
    r.add_argument("--timeout",type=int,default=180);r.add_argument("--probe-dll",type=Path);r.add_argument("--probe-mod-root",type=Path)
    r.add_argument("--mod", dest="mods", type=Path, nargs=2, action="append", default=[], metavar=("DLL", "SOURCE_ROOT"), help="Additional original mod and source root; repeat for each dependency")
    r=sub.add_parser("report",help="Audit a saved run and emit compact agent evidence; no execution");r.add_argument("run",type=Path);r.add_argument("--out",type=Path);r.add_argument("--contact-sheet",action="store_true")
    r=sub.add_parser("suite",help="Execute an explicit scenario matrix, preserving expected native failures");r.add_argument("manifest",type=Path);r.add_argument("--out",type=Path,required=True);r.add_argument("--no-build",action="store_true");r.add_argument("--plan",action="store_true",help="Read-only input validation and case listing; not a run")
    r=sub.add_parser("inspect");r.add_argument("trace",type=Path);r.add_argument("--tick",type=int);r.add_argument("--events",action="store_true");r.add_argument("--kind");r.add_argument("--summary",action="store_true",help="Compact read-only resource/hit/event aggregates")
    r=sub.add_parser("native-review");r.add_argument("trace",type=Path);r.add_argument("--out",type=Path,required=True);r.add_argument("--gif",action="store_true");r.add_argument("--gif-stride",type=int,default=1,help="Sample every N original PNGs only in optional GIF; HTML retains every native tick")
    r=sub.add_parser("timeline");r.add_argument("trace",type=Path);r.add_argument("--out",type=Path,required=True)
    r=sub.add_parser("frame");r.add_argument("trace",type=Path);r.add_argument("--tick",type=int,required=True);r.add_argument("--out",type=Path,required=True);r.add_argument("--camera",choices=("action","scene"),default="action")
    r=sub.add_parser("render");r.add_argument("trace",type=Path);r.add_argument("--out",type=Path,required=True);r.add_argument("--png",action="store_true");r.add_argument("--gif",action="store_true");r.add_argument("--camera",choices=("action","scene"),default="action")
    r=sub.add_parser("run");sources=r.add_mutually_exclusive_group(required=True);sources.add_argument("--item",type=Path);sources.add_argument("--vanilla-item",help="Exact native ItemID name or positive integer; backend admits verified controls only");r.add_argument("--scenario",type=Path,required=True);r.add_argument("--out",type=Path,required=True);r.add_argument("--no-build",action="store_true");r.add_argument("--item-boundary",choices=("fresh","local_cache"),default="fresh",help="Use the actual fresh-input or saved-cache production reader; never rewrite source JSON");r.add_argument("--png",action="store_true");r.add_argument("--gif",action="store_true");r.add_argument("--camera",choices=("action","scene"),default="action")
    r.add_argument("--review",choices=("schematic","native","none"),default="schematic",help="Review export only; none still records native frames if requested by scenario")
    r.add_argument("--gif-stride",type=int,default=1);r.add_argument("--timeout",type=int,default=180)
    args=parser.parse_args()
    try:
        if args.command in ("setup-particle","setup-luminance","setup-vfx"):
            from fetch_vfx_assets import MANIFEST,setup_particle
            root=(args.deps_root or Path(os.environ.get("INFINI_TML_DEPS_SRC",ROOT/"artifacts/dependencies"))).expanduser()
            if args.command=="setup-particle":result=setup_particle(root,read_json(MANIFEST))
            else:
                from fetch_luminance import setup_luminance
                result=setup_luminance(root) if args.command=="setup-luminance" else {
                    "particle":setup_particle(root,read_json(MANIFEST)),"luminance":setup_luminance(root)}
            print(json.dumps(result,indent=2));return 0
        if args.command=="test":
            import unittest
            suite=unittest.defaultTestLoader.discover(str(HERE),pattern="test_*.py")
            return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1
        if args.command=="doctor":
            state=doctor();print(json.dumps(state,indent=2));return 0 if state["ready"] else 2
        if args.command=="build":build();return 0
        if args.command=="probe":
            data=execute_probe(args)
            print(json.dumps(data,indent=2,allow_nan=False))
            return 0 if args.plan or args.prepare or data["passed"] else 1
        if args.command=="fixtures":print(json.dumps(fixtures(args.out,args.no_build),indent=2));return 0
        if args.command=="loader-run":return execute_loader_run(args)
        if args.command=="catalog":
            rows=[]
            for path in sorted((HERE/"scenarios").glob("*.json")):
                scene=read_json(path)
                rows.append({"path":str(path),"playerUpdate":scene.get("playerUpdate","item_check"),"ticks":scene["ticks"],
                    "actions":sorted({a["kind"] for a in scene.get("actions",[])}),
                    "assertions":scene["assertions"],"nativeRender":scene.get("nativeRender"),
                    "note":"Choose expectations for your item explicitly; this template is not universally applicable"})
            print(json.dumps({"scenarios":rows,"supportMatrix":str(HERE/"SUPPORT_MATRIX.md")},indent=2));return 0
        if args.command=="report":
            from agent_evidence import report,export_report
            if args.contact_sheet and args.out is None:raise ValueError("--contact-sheet requires --out")
            data=export_report(args.run,args.out,args.contact_sheet) if args.out else report(args.run)
            print(json.dumps(data,indent=2,allow_nan=False));return 2 if data["integrity"]["status"]=="invalid" else 0
        if args.command=="suite":
            from campaign import plan_suite,run_suite
            data=plan_suite(args.manifest) if args.plan else run_suite(args.manifest,args.out,args.no_build)
            print(json.dumps(data,indent=2,allow_nan=False));return 0 if args.plan or data["passed"] else 1
        if args.command=="inspect":
            native=validate_trace(read_json(args.trace))
            selected=[s for s in native["snapshots"] if args.tick is None or s["tick"]==args.tick]
            if args.tick is not None and not selected:raise ValueError("Requested tick has no recorded snapshot")
            if args.summary:
                if args.tick is not None or args.events or args.kind:raise ValueError("--summary cannot be combined with tick/event filters")
                result=summarize_trace(native)
            elif args.events or args.kind:
                result=[{"tick":s["tick"],"substep":s.get("substep"),**e} for s in selected for e in s.get("events",[]) if args.kind is None or e.get("kind")==args.kind]
            elif args.tick is not None:result=selected
            else:result={**{k:v for k,v in native.items() if k!="snapshots"},"snapshotCount":len(selected),"firstTick":selected[0]["tick"] if selected else None,"lastTick":selected[-1]["tick"] if selected else None}
            print(json.dumps(result,indent=2,allow_nan=False));return 0
        if args.command=="native-review":
            from native_review import export_native_review
            native=validate_trace(read_json(args.trace))
            print(json.dumps(export_native_review(native,args.trace,args.out,args.gif,args.gif_stride),indent=2));return 0
        if args.command=="timeline":
            svg=timeline_svg(read_json(args.trace))
            if args.out.resolve()==args.trace.resolve():raise ValueError("Cannot overwrite native trace")
            if args.out.suffix.lower() not in (".svg",".png"):raise ValueError("Timeline output must be .svg or .png")
            args.out.parent.mkdir(parents=True,exist_ok=True)
            if args.out.suffix.lower()==".png":
                try:import cairosvg
                except ImportError as exc:raise RuntimeError("PNG export requires optional cairosvg") from exc
                cairosvg.svg2png(bytestring=svg.encode(),write_to=str(args.out))
            else:args.out.write_text(svg,encoding="utf-8")
            print(json.dumps({"output":str(args.out),"sourceSha256":digest(args.trace),"kind":"recorded-native-clock-plot"}));return 0
        if args.command=="frame":
            native=validate_trace(read_json(args.trace))
            indices=[i for i,s in enumerate(native["snapshots"]) if s["tick"]==args.tick and s.get("phase")!="after_input_before_update"]
            if not indices:raise ValueError("No completed/update-failure snapshot at requested tick")
            index=indices[-1];svg=frame_svg(native,index,args.camera)
            if args.out.resolve()==args.trace.resolve():raise ValueError("Cannot overwrite native trace")
            if args.out.suffix.lower() not in (".svg",".png"):raise ValueError("Frame output must be .svg or .png")
            args.out.parent.mkdir(parents=True,exist_ok=True)
            if args.out.suffix.lower()==".png":
                try:import cairosvg
                except ImportError as exc:raise RuntimeError("PNG export requires optional cairosvg") from exc
                cairosvg.svg2png(bytestring=svg.encode(),write_to=str(args.out))
            else:args.out.write_text(svg,encoding="utf-8")
            print(json.dumps({"tick":args.tick,"frameIndex":index,"camera":args.camera,"output":str(args.out),"sourceSha256":digest(args.trace)}));return 0
        if args.command=="render":print(json.dumps(render(args.trace,args.out,args.png,args.gif,args.camera),indent=2));return 0
        receipt=execute_run(args)
        print(json.dumps(receipt,indent=2,allow_nan=False))
        return receipt["exitCode"]
    except (ValueError,OSError,RuntimeError,ImportError,subprocess.SubprocessError,KeyError,TypeError) as error:
        print(json.dumps({"status":"error","error":str(error)}),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
