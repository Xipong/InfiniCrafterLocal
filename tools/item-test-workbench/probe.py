"""Prepare explicit native probes without per-item Python or handwritten suites."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re

import workbench as w
from campaign import expected_result, run_suite


def finite_json(value):
    def reject(number):
        raise ValueError("Non-finite JSON number: " + number)
    parsed = json.loads(value, parse_constant=reject)
    # json.loads also accepts an overflowing exponent such as 1e999.
    json.dumps(parsed, allow_nan=False)
    return parsed


def assertion(value):
    if re.fullmatch(r"[a-z][a-z0-9_]*", value):
        return {"kind": value}
    parsed = finite_json(value)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("kind"), str) or not parsed["kind"]:
        raise ValueError('--assert needs a native assertion name or JSON object with "kind"')
    return parsed


def set_field(scene, assignment):
    path, separator, raw = assignment.partition("=")
    parts = path.split(".")
    if not separator or any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*|[0-9]+", p) for p in parts):
        raise ValueError("--set needs dotted.path=JSON, for example tiles.0.tileY=44")
    if parts[0] in ("actions", "assertions"):
        raise ValueError("Use --action or --assert instead of replacing " + parts[0])
    value = finite_json(raw)
    parent = scene
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if isinstance(parent, dict):
            if last:
                parent[part] = value
            else:
                if part not in parent:
                    raise ValueError("Missing --set parent; set its object first: " + ".".join(parts[:i + 1]))
                parent = parent[part]
        elif isinstance(parent, list) and part.isdigit() and int(part) < len(parent):
            if last:
                parent[int(part)] = value
            else:
                parent = parent[int(part)]
        else:
            raise ValueError("Invalid --set path: " + path)


def input_actions(kind, ticks, start, hold, repeat):
    if kind == "idle":
        return []
    if kind == "equip":
        return [{"tick": start, "kind": "equip"}]
    if repeat is not None and repeat <= hold:
        raise ValueError("--repeat must exceed --hold so every press has a release interval")
    if start + hold >= ticks:
        raise ValueError("Input release must be inside --ticks; increase --ticks or shorten --hold")
    starts = range(start, ticks, repeat) if repeat is not None else [start]
    actions = []
    for tick in starts:
        # Refuse an incomplete last press instead of silently shortening it.
        if tick + hold >= ticks:
            raise ValueError("Last repeated release is outside --ticks; adjust --ticks, --start or --repeat")
        actions.extend([{"tick": tick, "kind": kind}, {"tick": tick + hold, "kind": "release"}])
        if len(actions) > 256:
            raise ValueError("Probe exceeds the native limit of 256 scripted actions")
    return actions


def bounded_integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}..{maximum}")
    return value


def plan_probe(args):
    scene = w.read_json(w.HERE / "scenarios/probe.json")
    scene["playerUpdate"] = args.mode
    if args.ticks is not None:
        scene["ticks"] = args.ticks
    if args.seed is not None:
        scene["seed"] = args.seed
    for assignment in args.set:
        set_field(scene, assignment)
    ticks = bounded_integer(scene.get("ticks"), 1, 14400, "ticks")
    bounded_integer(args.start, 0, ticks - 1, "--start")
    hold = bounded_integer(args.hold if args.hold is not None else 1, 1, 14399, "--hold")
    if args.repeat is not None:
        bounded_integer(args.repeat, 2, 14400, "--repeat")
    if scene.get("playerUpdate") not in ("item_check", "full", "client", "client_hybrid", "client_vfx"):
        raise ValueError("Unknown playerUpdate mode")
    if scene["playerUpdate"] == "client_vfx" and (ticks > 600 or not isinstance(scene.get("nativeRender"), dict)):
        raise ValueError("client_vfx requires <=600 ticks and explicit --set nativeRender=JSON settings")
    bounded_integer(args.timeout, 1, 3600, "--timeout")
    inputs = args.input or ["primary"]
    if len(inputs) != len(set(inputs)):
        raise ValueError("Duplicate --input")
    if any(k in ("idle", "equip") for k in inputs) and (args.hold is not None or args.repeat is not None):
        raise ValueError("--hold/--repeat apply only to primary/alt; probe idle/equip separately")
    scene["assertions"].extend(assertion(value) for value in args.assertions)
    extra_actions = [finite_json(value) for value in args.action]
    for action in extra_actions:
        if not isinstance(action, dict) or not isinstance(action.get("kind"), str) or not action["kind"]:
            raise ValueError('--action needs a JSON object with "kind" and "tick"')
        bounded_integer(action.get("tick"), 0, ticks - 1, "--action tick")
    expectation = expected_result(finite_json(args.expect))
    sources = []
    for item in args.item:
        path = item.expanduser().resolve()
        if not isinstance(w.read_json(path), dict):
            raise ValueError("Item JSON must be an object: " + str(path))
        sources.append({"item": str(path), "itemSha256": w.digest(path), "label": path.stem})
    for name in args.vanilla_item:
        if not name.strip() or (name.lstrip("-").isdigit() and int(name) <= 0):
            raise ValueError("Vanilla item must be a native ItemID name or positive ID")
        if args.item_boundary != "fresh":
            raise ValueError("Vanilla items cannot use the local_cache boundary")
        sources.append({"vanillaItem": name, "label": name})
    if not sources or len(sources) * len(inputs) > 128:
        raise ValueError("Probe requires items/vanilla items and at most 128 item × input cases")
    scenes = {}
    for kind in inputs:
        value = copy.deepcopy(scene)
        value["actions"] = sorted(input_actions(kind, ticks, args.start, hold, args.repeat) + extra_actions,
                                  key=lambda a: a["tick"])
        if len(value["actions"]) > 256:
            raise ValueError("Probe exceeds the native limit of 256 scripted actions")
        scenes[kind] = value
    cases = []
    for (index, source), kind in itertools.product(enumerate(sources, 1), inputs):
        # Numeric prefix preserves duplicate basenames and prevents path traversal.
        label = re.sub(r"[^a-zA-Z0-9_-]+", "-", source["label"]).strip("-_")[:36] or "item"
        cases.append({"name": f"{index:03d}-{label}-{kind}", "sourceIndex": index, "input": kind,
                      **{k: v for k, v in source.items() if k != "label"},
                      "expect": expectation, "itemBoundary": args.item_boundary,
                      "review": args.review, "timeout": args.timeout})
    return {"schemaVersion": 1, "kind": "native-probe-plan", "scenes": scenes, "cases": cases,
            "wholeItemCertified": False,
            "note": "Explicit native observations only. Default assertion is no_nonfinite, not proof of damage or correct mechanics. "
                    "No item rewriting, ammo inference, API calls or execution-mode retry. Native admission remains authoritative."}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def prepare_probe(plan, output):
    output = Path(output).expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh probe output directory")
    # Read and verify everything before creating any outputs.
    items = {}
    for case in plan["cases"]:
        if "item" in case and case["sourceIndex"] not in items:
            data = Path(case["item"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != case["itemSha256"]:
                raise ValueError("Probe item changed after planning: " + case["item"])
            items[case["sourceIndex"]] = data
    (output / "inputs").mkdir(parents=True)
    for index, data in items.items():
        (output / "inputs" / f"item-{index:03d}.json").write_bytes(data)
    for kind, scene in plan["scenes"].items():
        write_json(output / "inputs" / f"{kind}.json", scene)
    cases = []
    for case in plan["cases"]:
        cases.append({**{k: case[k] for k in ("name", "expect", "itemBoundary", "review", "timeout")},
                      "scenario": f"inputs/{case['input']}.json",
                      **({"item": f"inputs/item-{case['sourceIndex']:03d}.json"} if "item" in case
                         else {"vanillaItem": case["vanillaItem"]})})
    write_json(output / "suite.json", {"schemaVersion": 1, "cases": cases})
    write_json(output / "probe-plan.json", plan)
    return output


def execute_probe(args):
    plan = plan_probe(args)
    if args.plan:
        return plan
    output = args.out or w.ROOT / "artifacts/workbench" / datetime.now(timezone.utc).strftime("probe-%Y%m%d-%H%M%S-%f")
    # Refuse missing/stale native dependencies before writing a prepared suite.
    # run_suite builds once and each child verifies provenance as usual.
    if not args.prepare:
        if args.no_build:
            w.native_executable(True)
        elif not w.doctor()["ready"]:
            raise RuntimeError("Native prerequisites unavailable: " + json.dumps(w.doctor()))
    output = prepare_probe(plan, output)
    result = {"kind": "native-probe", "output": str(output), "manifest": str(output / "suite.json"),
              "plannedCases": len(plan["cases"]), "wholeItemCertified": False, "note": plan["note"]}
    if args.prepare:
        return {**result, "status": "prepared", "nativeStatus": "notRun"}
    data = run_suite(output / "suite.json", output / "runs", args.no_build)
    return {**result, "status": "completed", "passed": data["passed"],
            "summary": str(output / "runs/summary.json"), "cases": data["cases"]}


def add_parser(subparsers):
    parser = subparsers.add_parser("probe", help="Test items without writing Python, scenario JSON or a suite manifest")
    parser.add_argument("--item", type=Path, nargs="+", action="extend", default=[], help="One or more generated item JSONs; shell globs work")
    parser.add_argument("--vanilla-item", nargs="+", action="extend", default=[], help="Explicit native ItemID names/IDs for controls")
    parser.add_argument("--input", nargs="+", action="extend", choices=("primary", "alt", "idle", "equip"), help="Item × input matrix; default primary")
    parser.add_argument("--mode", choices=("item_check", "full", "client", "client_hybrid", "client_vfx"), default="full")
    parser.add_argument("--ticks", type=int, help="Observed native ticks; default 180")
    parser.add_argument("--seed", type=int, help="Native scene seed; default 1")
    parser.add_argument("--start", type=int, default=0, help="First input tick; default 0")
    parser.add_argument("--hold", type=int, help="Ticks between press and release; default 1")
    parser.add_argument("--repeat", type=int, help="Ticks between explicit presses; must exceed hold")
    parser.add_argument("--set", action="append", default=[], metavar="PATH=JSON", help="Set a scene field, e.g. dummy.x=840 or tiles.0.tileY=44")
    parser.add_argument("--action", action="append", default=[], metavar="JSON", help="Append native actions; same-tick order follows generated input")
    parser.add_argument("--assert", dest="assertions", action="append", default=[], metavar="KIND_OR_JSON", help="Append a native assertion; default only no_nonfinite")
    parser.add_argument("--expect", default='{"status":"passed"}', metavar="JSON", help="Suite expectation; negative controls require exact failures/error substring")
    parser.add_argument("--item-boundary", choices=("fresh", "local_cache"), default="fresh")
    parser.add_argument("--review", choices=("none", "schematic", "native"), default="none")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--out", type=Path, help="Fresh output directory; default unique artifacts/workbench/probe-* directory")
    parser.add_argument("--no-build", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan", action="store_true", help="Read-only resolved cases and scenarios, no SDK or outputs needed")
    group.add_argument("--prepare", action="store_true", help="Write a portable suite and exact item copies without building or running")
