#!/usr/bin/env python3
"""Registry/schema/prompt/compiler/C#-owner parity for the v5 low-level runtime."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"LocalGenerator"))
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, capability_provider_union, compact_capability_catalog, runtime_program_author_schema
from infini_local.qa.capability_witnesses import capability_vertical_slice_report
from infini_local.qa.capability_library_audit import capability_library_audit
from check_delivery_contract import build_report as delivery_report
from check_planner_prompt_usability import build_report as prompt_report

def build_report() -> dict:
    names=set(CAPABILITY_REGISTRY)
    schema_names={x["properties"]["fn"]["const"] for x in runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"]}
    library_audit=capability_library_audit()
    witness=capability_vertical_slice_report(); delivery=delivery_report(); prompt=prompt_report()
    scanner=subprocess.run([sys.executable,str(ROOT/"tools/check_csharp_contracts.py")],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    checks={
      "registryProvider":{x["properties"]["fn"]["const"] for x in capability_provider_union()}==names,
      "registryCatalog":{x["fn"] for x in compact_capability_catalog()}==names,
      "registrySchema":schema_names==names,
      "compilerWitnesses":bool(witness.get("ok")) and witness.get("capabilityCount")==len(names),
      "csharpOwners":bool(library_audit["criteria"]["runtimeOwnership"]),
      "machineReadableLibrary":bool(library_audit["ok"]),
      "delivery":bool(delivery.get("ok")),"prompt":bool(prompt.get("ok")),"csharpScanner":scanner.returncode==0,
    }
    return {"schema":"infini.low-level-contract-parity.v1","ok":all(checks.values()),"capabilityCount":len(names),"checks":checks,"capabilityLibraryAudit":library_audit,"witnessFailures":[x for x in witness.get("rows",[]) if not x.get("ok")],"csharpScannerOutput":scanner.stdout.strip()}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out",type=Path); ap.add_argument("--quiet",action="store_true"); a=ap.parse_args(); r=build_report(); t=json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if a.out: a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(t,encoding="utf-8")
    if not a.quiet: print(t,end="")
    return 0 if r["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
