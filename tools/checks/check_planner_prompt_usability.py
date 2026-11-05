#!/usr/bin/env python3
"""Offline proof that the single Gameplay Author request exposes the complete v5 catalog."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.pipelines.author.prompt import planner_prompt_usability_report

PARENT_A = {"id":"workbench","name":"Workbench","damage":0,"useTime":20,"tags":["furniture"],"category":"placeable"}
PARENT_B = {"id":"blade","name":"Blade","damage":18,"useTime":24,"tags":["metal"],"category":"combat"}

def build_report(a: dict | None = None, b: dict | None = None, key: str = "workbench+blade") -> dict:
    report = planner_prompt_usability_report(PARENT_A if a is None else a, PARENT_B if b is None else b, key)
    expected = sum(cap.author_visible for cap in CAPABILITY_REGISTRY.values())
    report["expectedCapabilities"] = expected
    report["registeredCapabilities"] = len(CAPABILITY_REGISTRY)
    report["checks"] = {
        "singleSelfContainedCatalog": report.get("visibleCapabilities") == expected,
        "noMissing": not report.get("missingCapabilities"),
        "noExtra": not report.get("extraCapabilities"),
        "noWeaponMacro": not report.get("containsWeaponMacro"),
        "noFamilyRouter": not report.get("containsFamilyRouter"),
        "withinConfiguredLimit": int(report.get("chars", 0)) <= int(report.get("limit", 0)),
    }
    report["ok"] = all(report["checks"].values())
    return report


def captured_reports(directory: Path) -> list[dict]:
    """Measure complete Prepare captures with the production limit, offline."""
    paths = sorted(directory.glob("*.packet.json"))
    if not paths:
        raise ValueError(f"No *.packet.json captures in {directory}")
    reports = []
    for path in paths:
        source = path.read_bytes()
        row = {"capture": path.name, "sourceSha256": hashlib.sha256(source).hexdigest()}
        try:
            packet = json.loads(source)
            if not isinstance(packet, dict) or any(not isinstance(packet.get(key), dict) for key in ("itemA", "itemB")):
                raise ValueError("Expected a complete Prepare packet with itemA and itemB objects")
            row.update(build_report(packet["itemA"], packet["itemB"], path.stem))
        except (ValueError, TypeError) as error:
            row.update(ok=False, error=str(error))
        reports.append(row)
    return reports


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out", type=Path); ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--parent-captures", type=Path, help="Also check every canonical Prepare *.packet.json in this directory")
    args=ap.parse_args()
    r=build_report()
    if args.parent_captures:
        try:
            r["captures"] = captured_reports(args.parent_captures)
            r["ok"] = r["ok"] and all(row["ok"] for row in r["captures"])
        except (OSError, ValueError) as error:
            r.update(ok=False, captureError=str(error))
    text=json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.out: args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(text,encoding="utf-8")
    if not args.quiet: print(text,end="")
    return 0 if r["ok"] else 1
if __name__ == "__main__": raise SystemExit(main())
