#!/usr/bin/env python3
"""Offline proof that the single Gameplay Author request exposes the complete v5 catalog."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
from infini_local.pipelines.llm_authoring_prompt import planner_prompt_usability_report

PARENT_A = {"id":"workbench","name":"Workbench","damage":0,"useTime":20,"tags":["furniture"],"category":"placeable"}
PARENT_B = {"id":"blade","name":"Blade","damage":18,"useTime":24,"tags":["metal"],"category":"combat"}

def build_report() -> dict:
    report = planner_prompt_usability_report(PARENT_A, PARENT_B, PARENT_A, PARENT_B, "workbench+blade")
    report["expectedCapabilities"] = len(CAPABILITY_REGISTRY)
    report["checks"] = {
        "singleSelfContainedCatalog": report.get("visibleCapabilities") == len(CAPABILITY_REGISTRY),
        "noMissing": not report.get("missingCapabilities"),
        "noExtra": not report.get("extraCapabilities"),
        "noWeaponMacro": not report.get("containsWeaponMacro"),
        "noFamilyRouter": not report.get("containsFamilyRouter"),
        "withinConfiguredLimit": int(report.get("chars", 0)) <= int(report.get("limit", 0)),
    }
    report["ok"] = all(report["checks"].values())
    return report

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out", type=Path); ap.add_argument("--quiet", action="store_true"); args=ap.parse_args()
    r=build_report(); text=json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.out: args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(text,encoding="utf-8")
    if not args.quiet: print(text,end="")
    return 0 if r["ok"] else 1
if __name__ == "__main__": raise SystemExit(main())
