from __future__ import annotations

"""Tiny HTML renderer for trace/debug snapshots.

This intentionally receives a ready snapshot dict from server.py. The renderer should
not know about runtime globals, LLM config, or combine state; it only formats data.
"""

import html
from typing import Any, Callable


def render_trace_snapshot_html(snap: dict[str, Any], *, app_version: str, trace_clip: Callable[[Any, int | None], str]) -> str:
    def esc(x: Any) -> str:
        return html.escape(str(x), quote=True)

    def table_for(d: dict[str, Any], keys: list[str] | None = None) -> str:
        items = [(k, d.get(k)) for k in (keys or list(d.keys()))]
        return "<table>" + "".join(f"<tr><th>{esc(k)}</th><td><pre>{esc(trace_clip(v, 4000))}</pre></td></tr>" for k, v in items) + "</table>"

    def event_list(items: list[dict[str, Any]], with_prompts: bool = False) -> str:
        parts = []
        for ev in reversed(items[-80:]):
            title = ev.get("title") or ev.get("message") or ev.get("stage") or "event"
            stage = ev.get("stage") or ev.get("level") or ev.get("kind") or ""
            body = {k: v for k, v in ev.items() if k not in {"prompt", "negative", "response"}}
            details = f"<pre>{esc(trace_clip(body, 5000))}</pre>"
            if with_prompts:
                if ev.get("prompt"):
                    details += f"<h4>Prompt</h4><pre>{esc(ev.get('prompt'))}</pre>"
                if ev.get("negative"):
                    details += f"<h4>Negative</h4><pre>{esc(ev.get('negative'))}</pre>"
                if ev.get("response"):
                    details += f"<h4>Response</h4><pre>{esc(ev.get('response'))}</pre>"
            parts.append(f"<details open><summary><b>{esc(stage)}</b> — {esc(title)} <small>{esc(ev.get('ts', ''))}</small></summary>{details}</details>")
        return "\n".join(parts) or "<p>Пока пусто.</p>"

    style = "".join([
        "body{font-family:Segoe UI,Arial,sans-serif;background:#111827;color:#e5e7eb;margin:0;padding:24px}",
        "h1{margin:0 0 12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}",
        ".card{background:#1f2937;border:1px solid #374151;border-radius:12px;padding:16px;margin:0 0 16px;box-shadow:0 8px 18px #0005}",
        "table{border-collapse:collapse;width:100%}th{text-align:left;color:#93c5fd;width:220px;vertical-align:top}td,th{border-bottom:1px solid #374151;padding:6px}",
        "pre{white-space:pre-wrap;word-break:break-word;background:#0b1020;border:1px solid #263247;border-radius:8px;padding:10px;color:#d1d5db;max-height:360px;overflow:auto}",
        "details{background:#111827;border:1px solid #374151;border-radius:10px;padding:8px;margin:8px 0}summary{cursor:pointer}small{color:#9ca3af}a{color:#93c5fd}",
    ])
    pipeline = snap.get("pipeline") if isinstance(snap.get("pipeline"), dict) else {}
    sdcpp = snap.get("sdcpp") if isinstance(snap.get("sdcpp"), dict) else {}
    sdcpp_keys = ["serverUrl", "serverAlive", "serverConfigured", "serverAutostart", "showConsole", "logFile", "lastCommand", "lastStartError", "lastExit", "logTail"]
    cards = []
    cards.append('<section class="card"><h2>Pipeline</h2>' + table_for(pipeline) + '</section>')
    cards.append('<section class="card"><h2>sd.cpp / Z-Image</h2>' + table_for(sdcpp, sdcpp_keys) + '</section>')
    return "".join([
        '<!doctype html><meta charset="utf-8"><title>InfiniCrafter trace</title><style>', style, '</style>',
        f'<h1>InfiniCrafterLocal trace v{esc(app_version)}</h1>',
        '<p><a href="/trace.json">trace.json</a> · <a href="/sdcpp_debug">sdcpp_debug</a> · <a href="/health">health</a></p>',
        '<div class="grid">', *cards, '</div>',
        '<section class="card"><h2>Prompt trace</h2>', event_list(snap.get("promptTrace") or [], True), '</section>',
        '<section class="card"><h2>Pipeline trace</h2>', event_list(snap.get("pipelineTrace") or [], False), '</section>',
        '<section class="card"><h2>Events</h2>', event_list(snap.get("events") or [], False), '</section>',
        '<section class="card"><h2>Last combine failure</h2><pre>', esc(trace_clip(snap.get("lastCombineFailure"), 12000)), '</pre></section>',
    ])


def render_mp_connect_html(info: dict[str, Any]) -> str:
    def esc(x: Any) -> str:
        return html.escape(str(x), quote=True)

    style = "".join([
        "body{font-family:Segoe UI,Arial,sans-serif;background:#111827;color:#e5e7eb;padding:24px}",
        "pre{background:#0b1020;border:1px solid #374151;border-radius:8px;padding:12px;white-space:pre-wrap}",
        "code{color:#93c5fd}",
    ])
    friend = esc(info.get("friendText", ""))
    debug = esc(__import__("json").dumps(info, ensure_ascii=False, indent=2))
    return "".join([
        '<!doctype html><html><head><meta charset="utf-8"><title>InfiniCrafterLocal MP connect</title><style>', style, '</style></head><body>',
        '<h1>InfiniCrafterLocal / Radmin connect</h1>',
        '<p>Эта страница открылась с host-ПК. Если друг видит её по Radmin IP, asset host доступен.</p>',
        '<h2>Дай другу это</h2><pre>', friend, '</pre>',
        '<h2>Debug</h2><pre>', debug, '</pre>',
        '</body></html>',
    ])

