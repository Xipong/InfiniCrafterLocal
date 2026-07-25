#!/usr/bin/env python3
"""Compile non-archetypal Author programs through strict v5 wire and storage delivery."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"LocalGenerator"))
from infini_local.core.runtime_authoring import RUNTIME_PROGRAM_API_VERSION, RUNTIME_WIRE_SCHEMA, compile_runtime_program, validate_runtime_program, validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture
from infini_local.storage.world_storage import sanitize_recipe_for_delivery

def build_report() -> dict:
    rows=[]
    for name in NON_ARCHETYPAL_FIXTURES:
        authored=build_runtime_fixture(name); author=validate_runtime_program(authored)
        try:
            compiled=compile_runtime_program(authored); wire=validate_runtime_wire(compiled); delivered=sanitize_recipe_for_delivery(compiled)
            delivered_wire=validate_runtime_wire(delivered) if isinstance(delivered,dict) else {"ok":False,"errors":[{"message":"delivery returned non-object"}]}
        except Exception as exc:
            compiled={}; wire={"ok":False,"errors":[{"message":repr(exc)}]}; delivered_wire=wire
        runtime=compiled.get("runtimeProgram",{}) if isinstance(compiled,dict) else {}
        ok=bool(author.get("ok") and wire.get("ok") and delivered_wire.get("ok") and runtime.get("apiVersion")==RUNTIME_PROGRAM_API_VERSION and runtime.get("schema")==RUNTIME_WIRE_SCHEMA and "calls" not in runtime)
        rows.append({"fixture":name,"ok":ok,"authorErrors":author.get("errors",[])[:8],"wireErrors":wire.get("errors",[])[:8],"deliveryErrors":delivered_wire.get("errors",[])[:8],"entities":len(runtime.get("entities",[])),"bindings":len(runtime.get("bindings",[]))})
    return {"schema":"infini.low-level-delivery-proof.v1","ok":all(r["ok"] for r in rows),"apiVersion":RUNTIME_PROGRAM_API_VERSION,"wireSchema":RUNTIME_WIRE_SCHEMA,"rows":rows}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out",type=Path); ap.add_argument("--quiet",action="store_true"); a=ap.parse_args(); r=build_report(); t=json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if a.out: a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(t,encoding="utf-8")
    if not a.quiet: print(t,end="")
    return 0 if r["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
