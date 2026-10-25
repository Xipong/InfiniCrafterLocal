"""Portable agent evidence: audit saved runs and select real pixels.

No inference, game execution, physics, or interpretation of item names/prose.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import io
import json
from pathlib import Path

import workbench as w

NATIVE_EXIT = {"passed": 0, "failed": 1, "error": 2}


def trace_path(value):
    path = Path(value).resolve()
    return path / "native.json" if path.is_dir() else path


def audit_run(path, trace):
    """Check archived evidence only; never require the original checkout/host paths.

    Hashes establish internal consistency, not authenticity or loaded-byte proof.
    A direct/legacy native trace stays inspectable but cannot become verified.
    """
    receipt_path = path.parent / "run.json"
    if not receipt_path.is_file():
        return {"status": "unverified", "issues": ["No wrapper run.json receipt"]}
    receipt = w.read_json(receipt_path)
    if not isinstance(receipt, dict):
        raise ValueError("run.json must be an object")
    issues, missing = [], []
    for name, expected in ((path.name, receipt.get("traceSha256")),
                           ("scenario.json", receipt.get("scenarioSha256"))):
        archived = path.parent / name
        if not isinstance(expected, str):
            missing.append("Missing receipt hash: " + name)
        elif not archived.is_file() or w.digest(archived) != expected:
            issues.append("Archived hash mismatch or missing file: " + name)
    source = receipt.get("source", {})
    native_input = trace.get("input", {})
    if not isinstance(source, dict) or not isinstance(native_input, dict):
        raise ValueError("Source/input provenance must be objects")
    if source.get("kind") == "generated-json":
        archived = path.parent / "item.json"
        expected = receipt.get("itemSha256")
        if not isinstance(expected, str):
            missing.append("Missing receipt hash: item.json")
        elif not archived.is_file() or w.digest(archived) != expected:
            issues.append("Archived hash mismatch or missing file: item.json")
        if native_input and native_input.get("sha256") != expected:
            issues.append("Native item hash disagrees with run receipt")
    elif source.get("kind") != "vanilla":
        missing.append("Missing source identity")
    if trace["status"] != "error" and not native_input:
        issues.append("Native behavioral result has no input provenance")
    if native_input and native_input.get("scenarioSha256") != receipt.get("scenarioSha256"):
        issues.append("Native scenario hash disagrees with run receipt")
    native_exit = receipt.get("nativeExitCode", receipt.get("exitCode"))
    if type(native_exit) is not int or native_exit != NATIVE_EXIT[trace["status"]]:
        issues.append("Native process exit code disagrees with trace status")
    if receipt.get("error"):
        issues.append("Runner error: " + str(receipt["error"]))
    if receipt.get("reviewErrors"):
        issues.append("Requested review export failed: " + str(receipt["reviewErrors"]))
    return {"status": "invalid" if issues else "unverified" if missing else "verified",
            "issues": issues + missing, "runnerExitCode": receipt.get("exitCode"),
            "sourceSha256": receipt.get("sourceSha256"),
            "nativeDllSha256": receipt.get("nativeDllSha256"),
            "scope": "Saved archive consistency only; no authentication or current-build verification"}


def failure_context(trace):
    """Point at observed state; never invent a failure tick for a final assertion."""
    frames = trace["snapshots"]
    tick = (trace.get("failure") or {}).get("tick")
    if tick is None:
        invalid = next((s for s in frames if any(e["kind"] == "invalid_native_state"
                                               for e in s.get("events", []))), None)
        tick = invalid["tick"] if invalid else None
    failed = [a for a in trace["assertions"] if a["status"] == "failed"]
    ticks = sorted({a.get("request", {}).get("tick") for a in failed
                    if type(a.get("request", {}).get("tick")) is int})
    if tick is not None:
        ticks = sorted(set(ticks + [tick]))
    if not ticks and trace["status"] != "passed" and frames:
        ticks = [frames[-1]["tick"]]
    selected = [s for s in frames if any(abs(s["tick"] - t) <= 1 for t in ticks)]
    return {"observedFailureTick": tick, "assertionTicks": sorted({a.get("request", {}).get("tick")
            for a in failed if type(a.get("request", {}).get("tick")) is int}),
            "contextTicks": sorted({s["tick"] for s in selected}),
            "eventContext": [{"tick": s["tick"], "phase": s.get("phase", "after_update"),
                              "events": s.get("events", [])} for s in selected],
            "note": "Final assertions have no inferred failure tick; context defaults to last recorded tick"}


def recorded_frames(trace, path):
    render = trace.get("nativeRender", {})
    if render.get("frames") or (render.get("capture") is True and trace["status"] == "passed"):
        from native_review import native_frames
        return native_frames(trace, path)
    return []


def report(value):
    path = trace_path(value)
    trace = w.validate_trace(w.read_json(path))
    counts = Counter(e["kind"] for s in trace["snapshots"] for e in s.get("events", []))
    first = {}
    for index, state in enumerate(trace["snapshots"]):
        for event in state.get("events", []):
            first.setdefault(event["kind"], {"tick": state["tick"], "snapshotIndex": index,
                                            "phase": state.get("phase", "after_update")})
    render = trace.get("nativeRender", {})
    frames = recorded_frames(trace, path)
    integrity = audit_run(path, trace)
    summary = w.summarize_trace(trace)
    return {"schemaVersion": 1, "kind": "saved-native-agent-report", "trace": str(path),
            "traceSha256": w.digest(path), "nativeStatus": trace["status"],
            "integrity": integrity, "summary": summary, "failureContext": failure_context(trace),
            "events": {kind: {"count": counts[kind], "first": first[kind]} for kind in sorted(counts)},
            "vision": {"nativeFrames": len(frames), "captureEnabled": render.get("capture"),
                       "pixelSource": "recorded-native-png" if frames else "none",
                       "renderScope": render.get("scope"),
                       "artworkCoverage": {key: render.get(key) for key in (
                           "playerArtworkRendered", "itemArtworkRendered", "projectileArtworkRendered",
                           "worldRendered", "nativeDustDrawExecuted")},
                       "visualApproval": "not performed"},
            "nextInspection": {"trace": str(path), "failedRequests": summary["failedAssertions"],
                               "ticks": failure_context(trace)["contextTicks"],
                               "logs": [str(path.parent / name) for name in ("stdout.log", "stderr.log")
                                        if (path.parent / name).is_file()]},
            "wholeItemCertified": False}


def markdown(data):
    summary = data["summary"]
    rows = ["# Native item evidence", "",
            f"Native result: **{data['nativeStatus']}**. Archive: **{data['integrity']['status']}**.",
            "", "Scope: explicit scenario assertions only. Whole item and visual quality are not certified.",
            "", f"Backend: `{summary['backend']}`.", "",
            "## Assertions", "", "```json", json.dumps(summary["failedAssertions"], indent=2), "```",
            "", "## Failure context", "", "```json", json.dumps(data["failureContext"], indent=2), "```",
            "", "## Coverage and unsupported paths", "", "```json",
            json.dumps({"coverage": summary["coverage"], "unsupported": summary["unsupported"]}, indent=2), "```",
            "", "## Native observations", "", "```json",
            json.dumps({key: summary[key] for key in ("timeline", "nativeHits", "nativeResourceObservers",
                                                      "resources", "activeProjectilesAtEnd")}, indent=2), "```",
            "", "Net resources include regeneration; use native debit/heal observations for costs.",
            "", "## Archive integrity", "", "```json", json.dumps(data["integrity"], indent=2), "```", ""]
    return "\n".join(rows)


def fresh_directory(output, source):
    output = Path(output).resolve()
    parent = trace_path(source).parent
    if output == parent or parent.is_relative_to(output) or output.is_relative_to(parent / "native-frames"):
        raise ValueError("Output must not overwrite source evidence")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh output directory")
    output.mkdir(parents=True, exist_ok=True)
    return output


def export_report(value, output, contact_sheet=False):
    data = report(value)
    # Validate real frame evidence (and optional Pillow) before creating output.
    if contact_sheet:
        from PIL import Image  # noqa: F401
        if not data["vision"]["nativeFrames"]:
            raise ValueError("Contact sheet requires recorded native PNGs; schematic replay is not pixels")
    output = fresh_directory(output, value)
    if contact_sheet:
        data["vision"]["contactSheet"] = export_contact_sheet(value, output)
    (output / "report.json").write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    (output / "report.md").write_text(markdown(data), encoding="utf-8")
    return data


def export_contact_sheet(value, output):
    from PIL import Image, ImageDraw
    from native_review import native_frames, observed_bookmarks
    path = trace_path(value)
    trace = w.validate_trace(w.read_json(path))
    frames = native_frames(trace, path)
    by_tick = {f["tick"]: i for i, (f, _) in enumerate(frames)}
    # Start/end, earliest instance of each native event, actual state transitions.
    # Include immediate neighbors so agents can inspect poses around a hit/release.
    anchors = [0, len(frames) - 1]
    failure_tick = (trace.get("failure") or {}).get("tick")
    if failure_tick in by_tick:
        anchors.insert(1, by_tick[failure_tick])
    seen = set()
    for s in trace["snapshots"]:
        kinds = {e["kind"] for e in s.get("events", [])} - {"native_phase", "item_contact_query", "item_contact_geometry"}
        if kinds - seen and s["tick"] in by_tick:
            anchors.append(by_tick[s["tick"]])
        seen.update(kinds)
    anchors.extend(by_tick[b["tick"]] for b in observed_bookmarks(trace) if b["tick"] in by_tick)
    selected = list(dict.fromkeys(anchors))[:12]
    for i in anchors:
        for neighbor in (i - 1, i + 1):
            if len(selected) < 12 and 0 <= neighbor < len(frames) and neighbor not in selected:
                selected.append(neighbor)
    selected.sort()
    cell_w, cell_h = 400, 300
    sheet = Image.new("RGB", (cell_w * min(3, len(selected)), 60 + cell_h * ((len(selected) + 2) // 3)), "#111827")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), "NATIVE PNG THUMBNAILS | no visual approval", fill="#fbbf24")
    coverage = trace["nativeRender"]
    draw.text((12, 31), " | ".join(f"{label}={coverage.get(key, '?')}" for label,key in (
        ("player","playerArtworkRendered"), ("item","itemArtworkRendered"),
        ("projectile","projectileArtworkRendered"), ("world","worldRendered"))), fill="#cbd5e1")
    entries = []
    for slot, index in enumerate(selected):
        descriptor, source = frames[index]
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise ValueError("Native PNG changed during contact sheet export")
        with Image.open(io.BytesIO(raw)) as im:
            image = im.convert("RGB")
        image.thumbnail((cell_w - 12, cell_h - 45), Image.Resampling.NEAREST)
        x, y = (slot % 3) * cell_w, 60 + (slot // 3) * cell_h
        sheet.paste(image, (x + 6, y + 6))
        tick = descriptor["tick"]
        kinds = sorted({e["kind"] for s in trace["snapshots"] if s["tick"] == tick
                        for e in s.get("events", [])} - {"native_phase"})
        draw.text((x + 6, y + cell_h - 34), f"tick {tick} | source frame {index}", fill="white")
        draw.text((x + 6, y + cell_h - 19), ", ".join(kinds)[:60] or "recorded state", fill="#cbd5e1")
        entries.append({"sourceFrameIndex": index, "tick": tick, "path": descriptor["path"],
                        "sha256": descriptor["sha256"], "events": kinds})
    sheet.save(output / "vision.png")
    metadata = {"path": "vision.png", "sha256": w.digest(output / "vision.png"),
                "selection": "Bounded start/end, first native events, observed transitions and available neighbors",
                "frames": entries, "totalNativeFrames": len(frames), "interpolated": False,
                "note": "Thumbnail contact sheet with labels; original PNGs remain authoritative"}
    (output / "vision.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
