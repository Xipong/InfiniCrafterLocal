"""Prepare explicit native probes without per-item Python or handwritten suites."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
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


def artwork_files(item_path, definition, extra_dirs):
    """Resolve selected publication names, never change item bytes or substitute art."""
    visual = definition.get("visual") or {}
    entities = (definition.get("runtimeProgram") or {}).get("entities") or []
    manifest = definition.get("vfxManifest") or {}
    slots = manifest.get("slots") or []
    paths = [visual.get("spritePath")]
    for entity in entities:
        v = entity.get("visual") or {}
        if v.get("assetMode") == "baked_sprite" and entity.get("kind") != "item_body":
            paths.append(v.get("spritePath"))
        for slot in slots:
            if slot.get("entityId") != entity.get("id"):
                continue
            textures = [(slot.get(part) or {}).get("texture") or {} for part in ("element", "path")]
            if slot.get("rendererKind") == "impactSprite" or any(t.get("source") == "impact" for t in textures):
                paths.append(v.get("impactSpritePath"))
    asset_ids = {t.get("assetId") for slot in slots for part in ("element", "path")
                 for t in [(slot.get(part) or {}).get("texture") or {}] if t.get("source") == "asset"}
    paths += [a.get("spritePath") for a in manifest.get("assets") or [] if a.get("id") in asset_ids]
    if (definition.get("accessory") or {}).get("enabled") or (definition.get("armor") or {}).get("enabled"):
        paths.append(visual.get("equipOverlayPath"))
    if any(not isinstance(path, str) or not path.strip() for path in paths):
        raise ValueError("Item has a selected artwork with no sprite path; cannot render it")
    explicit_dirs = [Path(p).expanduser().resolve() for p in extra_dirs]
    dirs = []
    for ancestor in [item_path.parent, *item_path.parents]:
        dirs.extend((ancestor, ancestor / "art/game_ready", ancestor / "sprites", ancestor / "cache/sprites"))
    result = []
    for raw in dict.fromkeys(paths):
        name = raw.replace("\\", "/").rsplit("/", 1)[-1]
        explicit = [directory / name for directory in explicit_dirs]
        candidates = [Path(raw).expanduser()] + [directory / name for directory in dirs]
        # An explicit directory resolves ambiguity deliberately. If it has no match,
        # retain the normal nearby lookup and report all conflicting bytes.
        selected = [p for p in explicit if p.is_file()] or [p for p in candidates if p.is_file()]
        matches = list(dict.fromkeys(p.resolve() for p in selected))
        if len({w.digest(p) for p in matches}) > 1:
            raise ValueError(f"Conflicting artwork files for {name}: " + ", ".join(map(str, matches)) + "; remove ambiguity or point to the exact asset")
        match = matches[0] if matches else None
        if match is None:
            raise ValueError(f"Missing selected artwork {name}; use --asset-dir DIR containing its published PNG")
        if str(match) not in result:
            result.append(str(match))
    return result


def plan_probe(args):
    scene = w.read_json(w.HERE / "scenarios/probe.json")
    scene["playerUpdate"] = args.mode
    if args.ticks is not None:
        scene["ticks"] = args.ticks
    if args.seed is not None:
        scene["seed"] = args.seed
    if args.gif:
        if args.mode != "full" or args.review != "none":
            raise ValueError("--gif selects client_vfx and native review; do not also set --mode or --review")
        scene["playerUpdate"] = "client_vfx"
        scene["dummy"] = {"mode": "native_training_dummy", "tileX": 53, "tileY": 44}
        # A fixed, reproducible side view. --set may override the prepared fields below.
        scene["nativeRender"] = {"width": 960, "height": 540, "cameraX": 480, "cameraY": 430,
                                 "zoom": 1.25, "capture": True, "lightingMode": "viewport_fill", "drawArtwork": True,
                                 "drawPlayer": True, "drawNativeDust": True}
    for assignment in args.set:
        set_field(scene, assignment)
    if args.ammo:
        if len(args.ammo) > 4:
            raise ValueError("--ammo supports at most four native ammo slots")
        inventory = scene.setdefault("inventory", [])
        if not isinstance(inventory, list) or any(not isinstance(row, dict) for row in inventory):
            raise ValueError("scene inventory must be an array of objects")
        occupied = {row.get("slot") for row in inventory}
        for index, spec in enumerate(args.ammo):
            parts = spec.split(":")
            if len(parts) not in (1, 2) or any(not p.isdecimal() for p in parts):
                raise ValueError("--ammo requires ITEM_ID or ITEM_ID:STACK, e.g. 40:200")
            item_id = bounded_integer(int(parts[0]), 1, 2147483647, "--ammo item ID")
            stack = bounded_integer(int(parts[1]) if len(parts) == 2 else 100, 1, 9999, "--ammo stack")
            slot = 54 + index
            if slot in occupied:
                raise ValueError(f"--ammo would overwrite occupied inventory slot {slot}")
            inventory.append({"slot": slot, "itemId": item_id, "stack": stack})
    if args.aim is not None and any(not math.isfinite(v) or abs(v) > 1_000_000 for v in args.aim):
        raise ValueError("--aim coordinates must be finite and within +/-1000000 pixels")
    ticks = bounded_integer(scene.get("ticks"), 1, 14400, "ticks")
    bounded_integer(args.start, 0, ticks - 1, "--start")
    hold = bounded_integer(args.hold if args.hold is not None else (min(120, ticks - args.start - 1) if args.gif and args.repeat is None else 1), 1, 14399, "--hold")
    if args.repeat is not None:
        bounded_integer(args.repeat, 2, 14400, "--repeat")
    if args.gif and (scene.get("playerUpdate") != "client_vfx" or
                     any(scene.get("nativeRender", {}).get(k) is not True for k in ("capture", "drawArtwork", "drawPlayer"))):
        raise ValueError("--gif requires client_vfx, capture, drawArtwork and drawPlayer; do not disable them with --set")
    if scene.get("playerUpdate") not in ("item_check", "full", "client", "client_hybrid", "client_vfx"):
        raise ValueError("Unknown playerUpdate mode")
    if scene["playerUpdate"] == "client_vfx" and (ticks > 600 or not isinstance(scene.get("nativeRender"), dict)):
        raise ValueError("client_vfx requires <=600 ticks and explicit --set nativeRender=JSON settings")
    bounded_integer(args.timeout, 1, 3600, "--timeout")
    if args.gif_stride is not None:
        bounded_integer(args.gif_stride, 1, 600, "--gif-stride")
    gif_stride = args.gif_stride or 1
    if args.gif:
        render = scene["nativeRender"]
        width = bounded_integer(render.get("width", 512), 64, 1024, "nativeRender.width")
        height = bounded_integer(render.get("height", 512), 64, 1024, "nativeRender.height")
        def gif_pixels(stride):
            frame_count = len(range(0, ticks, stride)) + int((ticks - 1) % stride != 0)
            return frame_count * width * height
        if args.gif_stride is None:
            while gif_pixels(gif_stride) > 100_000_000 and gif_stride < 600:
                gif_stride += 1
        elif gif_pixels(gif_stride) > 100_000_000:
            raise ValueError("Requested GIF exceeds the 100 million pixel budget; increase --gif-stride")
    if args.test_world_id is not None and not args.gif:
        raise ValueError("--test-world-id currently requires --gif")
    if args.test_world_id is not None and args.vanilla_item:
        raise ValueError("--test-world-id applies only to generated items")
    if args.test_world_id is not None:
        bounded_integer(args.test_world_id, 0, 2147483647, "--test-world-id")
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
        definition = w.read_json(path)
        if not isinstance(definition, dict):
            raise ValueError("Item JSON must be an object: " + str(path))
        display = definition.get("name")
        source = {"item": str(path), "itemSha256": w.digest(path), "label": path.stem,
                  "displayName": display if isinstance(display, str) and display.strip() else path.name}
        bindings = (definition.get("runtimeProgram") or {}).get("bindings")
        if not args.input and isinstance(bindings, list) and bindings and all(
            isinstance(b, dict) and b.get("input") == "equipped"
            and isinstance(b.get("usePolicy"), dict) and isinstance(b["usePolicy"].get("action"), dict)
            and b["usePolicy"]["action"].get("kind") == "equip_passive" for b in bindings
        ):
            source["defaultInput"] = "equip"
            source["inputSelection"] = "authored equipped-only bindings"
        if args.gif:
            source["artworkFiles"] = artwork_files(path, definition, args.asset_dir)
            world = (definition.get("recipeMeta") or {}).get("worldId")
            if args.test_world_id is not None:
                if not (definition.get("recipeMeta") or {}).get("worldScoped") or world is None:
                    raise ValueError("--test-world-id requires an existing world-scoped recipeMeta.worldId")
                source["worldId"] = args.test_world_id
                source["testWorldOverride"] = {"original": world, "test": str(args.test_world_id), "field": "recipeMeta.worldId"}
            elif world is not None:
                try:
                    source["worldId"] = int(world)
                    if str(source["worldId"]) != str(world).strip() or not 0 <= source["worldId"] <= 2147483647:
                        raise ValueError("not a canonical Terraria world ID")
                except (ValueError, TypeError):
                    raise ValueError("Item recipeMeta.worldId is not a canonical numeric Terraria world ID; use --test-world-id N to explicitly run a copy in a test world. Original remains unchanged.")
        sources.append(source)
    for name in args.vanilla_item:
        if not name.strip() or (name.lstrip("-").isdigit() and int(name) <= 0):
            raise ValueError("Vanilla item must be a native ItemID name or positive ID")
        if args.item_boundary != "fresh":
            raise ValueError("Vanilla items cannot use the local_cache boundary")
        sources.append({"vanillaItem": name, "label": name, "displayName": name})
    case_inputs = [(index, source, kind) for index, source in enumerate(sources, 1)
                   for kind in (args.input or [source.get("defaultInput", "primary")])]
    if not sources or len(case_inputs) > 128:
        raise ValueError("Probe requires items/vanilla items and at most 128 item × input cases")
    inputs = list(dict.fromkeys(kind for _, _, kind in case_inputs))
    if any(k in ("idle", "equip") for k in inputs) and (args.hold is not None or args.repeat is not None):
        raise ValueError("--hold/--repeat apply only to primary/alt; probe idle/equip separately")
    scenes = {}
    for kind in inputs:
        value = copy.deepcopy(scene)
        aim = args.aim if args.aim is not None else ((864, 732) if args.gif else None)
        default_aim = [{"tick": 0, "kind": "aim", "x": aim[0], "y": aim[1]}] if aim else []
        value["actions"] = sorted(default_aim + input_actions(kind, ticks, args.start, hold, args.repeat) + extra_actions,
                                  key=lambda a: a["tick"])
        if len(value["actions"]) > 256:
            raise ValueError("Probe exceeds the native limit of 256 scripted actions")
        scenes[kind] = value
    cases = []
    for index, source, kind in case_inputs:
        # Numeric prefix preserves duplicate basenames and prevents path traversal.
        label = re.sub(r"[^a-zA-Z0-9_-]+", "-", source["label"]).strip("-_")[:36] or "item"
        scene_key = kind
        if args.gif:
            scene_key = f"{index:03d}-{kind}"
            scenes[scene_key] = copy.deepcopy(scenes[kind])
            if "vanillaItem" in source:
                scenes[scene_key]["vanillaAssetRoot"] = str(args.vanilla_assets.expanduser().resolve())
                scenes[scene_key]["nativeRender"]["artworkFiles"] = []
                scenes[scene_key]["nativeRender"]["drawVanillaProjectiles"] = True
            else:
                scenes[scene_key]["nativeRender"]["artworkFiles"] = source["artworkFiles"]
            if "worldId" in source:
                scenes[scene_key]["worldId"] = source["worldId"]
        cases.append({"name": f"{index:03d}-{label}-{kind}", "sourceIndex": index, "input": kind, "sceneKey": scene_key,
                      **{k: v for k, v in source.items() if k != "label"},
                      "expect": expectation, "itemBoundary": args.item_boundary,
                      "review": "native" if args.gif else args.review, "timeout": args.timeout,
                      **({"gif": True, "gifStride": gif_stride} if args.gif else {})})
    if args.gif:
        scenes = {case["sceneKey"]: scenes[case["sceneKey"]] for case in cases}
    return {"schemaVersion": 1, "kind": "native-probe-plan", "scenes": scenes, "cases": cases,
            "wholeItemCertified": False,
            "note": "Explicit native observations only. Default assertion is no_nonfinite, not proof of damage or correct mechanics. " +
                    ("A test copy changes only recipeMeta.worldId; original bytes are retained. " if args.test_world_id is not None else "No item rewriting. ") +
                    "No ammo inference, API calls or execution-mode retry. Native admission remains authoritative."}


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
        case = next(c for c in plan["cases"] if c["sourceIndex"] == index)
        if "testWorldOverride" in case:
            (output / "inputs" / f"original-item-{index:03d}.json").write_bytes(data)
            definition = json.loads(data)
            definition["recipeMeta"]["worldId"] = case["testWorldOverride"]["test"]
            data = (json.dumps(definition, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        (output / "inputs" / f"item-{index:03d}.json").write_bytes(data)
    for kind, scene in plan["scenes"].items():
        write_json(output / "inputs" / f"{kind}.json", scene)
    cases = []
    for case in plan["cases"]:
        cases.append({**{k: case[k] for k in ("name", "expect", "itemBoundary", "review", "timeout", "gif", "gifStride") if k in case},
                      "scenario": f"inputs/{case['sceneKey']}.json",
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
    by_name = {case["name"]: case for case in plan["cases"]}
    cases = []
    for row in data["cases"]:
        case = by_name[row["name"]]
        gif_path = output / "runs" / case["name"] / "review/native.gif"
        close_path = output / "runs" / case["name"] / "review/native-close.gif"
        cases.append({**row, **({"gif": str(gif_path)} if args.gif and gif_path.is_file() else {}),
                      **({"closeGif": str(close_path)} if args.gif and close_path.is_file() else {}),
                      "displayName": case["displayName"],
                      **{key: case[key] for key in ("item", "vanillaItem", "testWorldOverride") if key in case}})
    result = {**result, "status": "completed", "passed": data["passed"],
              "summary": str(output / "runs/summary.json"), "cases": cases}
    write_json(output / "probe-result.json", result)
    return result


def add_parser(subparsers):
    parser = subparsers.add_parser("probe", help="Test items without writing Python, scenario JSON or a suite manifest")
    parser.add_argument("--item", type=Path, nargs="+", action="extend", default=[], help="One or more generated item JSONs; shell globs work")
    parser.add_argument("--vanilla-item", nargs="+", action="extend", default=[], help="Explicit native ItemID names/IDs for controls")
    parser.add_argument("--vanilla-assets", type=Path, default=w.ROOT / "artifacts/dependencies/vanilla-assets", help="Pinned native item/projectile PNG root for vanilla GIF captures")
    parser.add_argument("--input", nargs="+", action="extend", choices=("primary", "alt", "idle", "equip"), help="Item × input matrix; default primary")
    parser.add_argument("--mode", choices=("item_check", "full", "client", "client_hybrid", "client_vfx"), default="full")
    parser.add_argument("--ticks", type=int, help="Observed native ticks; default 180")
    parser.add_argument("--seed", type=int, help="Native scene seed; default 1")
    parser.add_argument("--start", type=int, default=0, help="First input tick; default 0")
    parser.add_argument("--hold", type=int, help="Ticks between press and release; default 1")
    parser.add_argument("--repeat", type=int, help="Ticks between explicit presses; must exceed hold")
    parser.add_argument("--ammo", action="append", default=[], metavar="ITEM_ID[:STACK]", help="Place explicit vanilla ammunition in slots 54..57 (repeatable, default stack 100)")
    parser.add_argument("--aim", type=float, nargs=2, metavar=("X", "Y"), help="Aim at world pixel coordinates from tick 0")
    parser.add_argument("--set", action="append", default=[], metavar="PATH=JSON", help="Set a scene field, e.g. dummy.x=840 or tiles.0.tileY=44")
    parser.add_argument("--action", action="append", default=[], metavar="JSON", help="Append native actions; same-tick order follows generated input")
    parser.add_argument("--assert", dest="assertions", action="append", default=[], metavar="KIND_OR_JSON", help="Append a native assertion; default only no_nonfinite")
    parser.add_argument("--expect", default='{"status":"passed"}', metavar="JSON", help="Suite expectation; negative controls require exact failures/error substring")
    parser.add_argument("--item-boundary", choices=("fresh", "local_cache"), default="fresh")
    parser.add_argument("--review", choices=("none", "schematic", "native"), default="none")
    parser.add_argument("--gif", action="store_true", help="Capture actual native player/item/VFX frames and export a GIF (requires graphics assets)")
    parser.add_argument("--test-world-id", type=int, help="Explicitly copy an item to this numeric test world (only recipeMeta.worldId changes; original and receipt retained)")
    parser.add_argument("--asset-dir", type=Path, action="append", default=[], help="Directory with published item PNGs; repeatable")
    parser.add_argument("--gif-stride", type=int, help="Sample every N recorded frames in GIF; default auto-fits pixel budget")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--out", type=Path, help="Fresh output directory; default unique artifacts/workbench/probe-* directory")
    parser.add_argument("--no-build", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan", action="store_true", help="Read-only resolved cases and scenarios, no SDK or outputs needed")
    group.add_argument("--prepare", action="store_true", help="Write a portable suite and exact item copies without building or running")
