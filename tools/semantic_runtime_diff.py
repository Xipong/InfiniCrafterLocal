#!/usr/bin/env python3
"""Deterministic v5 fixture snapshot without preserving the retired weapon IR."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"LocalGenerator"))
from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture

def build_current()->dict:
    out={}
    for name in NON_ARCHETYPAL_FIXTURES:
        x=compile_runtime_program(build_runtime_fixture(name)); report=validate_runtime_wire(x); runtime=x["runtimeProgram"]
        encoded=json.dumps(runtime,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        out[name]={"ok":report["ok"],"sha256":hashlib.sha256(encoded.encode()).hexdigest(),"entityKinds":sorted({e["kind"] for e in runtime["entities"]}),"entityCount":len(runtime["entities"]),"bindingCount":len(runtime["bindings"]),"hasFamilyAuthority":any(k in encoded for k in ("runtimeFamily","weaponFamily"))}
    return out

def build_report()->dict:
    cases=build_current(); return {"schema":"infini.low-level-semantic-proof.v1","ok":all(x["ok"] and not x["hasFamilyAuthority"] for x in cases.values()),"baselinePolicy":"v5 fixtures prove explicit entities/inputs/events; old weapon-IR zero-diff is intentionally retired","cases":cases}
def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out",type=Path); ap.add_argument("--write-current",type=Path); a=ap.parse_args(); r=build_report(); target=a.out or a.write_current
    t=json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+"\n"; target and (target.parent.mkdir(parents=True,exist_ok=True),target.write_text(t,encoding="utf-8")); print(t,end=""); return 0 if r["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
