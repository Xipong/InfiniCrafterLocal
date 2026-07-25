#!/usr/bin/env python3
"""Export deterministic v5 Author/Repair/Visual/VFX schemas and registry manifests."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"LocalGenerator"))
from infini_local.core.runtime_authoring import author_item_repair_schema, author_item_response_schema, capability_inventory_rows, runtime_program_author_schema, runtime_repair_scope_schema, technical_lowering_manifest
from infini_local.core.vfx_manifest import vfx_director_schema, vfx_repair_schema
from infini_local.pipelines.visual_generation_pipeline import visual_repair_schema, visual_response_schema
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
OUT=ROOT/"contracts/schemas"

def _doc(name:str, schema:dict[str,Any])->dict[str,Any]:
    out=dict(schema); out.setdefault("$schema","https://json-schema.org/draft/2020-12/schema"); out["$id"]=f"https://infinicrafter.local/contracts/{name}"; out["x-infini-generated"]=True; return out

def render()->dict[Path,str]:
    sample=compile_runtime_program(build_runtime_fixture("workbench_blade")); ids=[x["id"] for x in sample["runtimeProgram"]["entities"]]
    payloads={
      "runtime_program_author.schema.json":_doc("runtime_program_author.schema.json",runtime_program_author_schema()),
      "author_item_response.schema.json":_doc("author_item_response.schema.json",author_item_response_schema()),
      "author_item_repair.schema.json":_doc("author_item_repair.schema.json",author_item_repair_schema()),
      "runtime_repair_scope.schema.json":_doc("runtime_repair_scope.schema.json",runtime_repair_scope_schema()),
      "visual_runtime_entities.schema.json":_doc("visual_runtime_entities.schema.json",visual_response_schema(ids)),
      "visual_repair_patch.schema.json":_doc("visual_repair_patch.schema.json",visual_repair_schema(ids)),
      "vfx_runtime_events.schema.json":_doc("vfx_runtime_events.schema.json",vfx_director_schema(sample)),
      "vfx_repair_patch.schema.json":_doc("vfx_repair_patch.schema.json",vfx_repair_schema(sample)),
      "capability_inventory.generated.json":{"schema":"infini.low-level-capability-inventory.v1","capabilities":capability_inventory_rows()},
      "technical_lowering.generated.json":technical_lowering_manifest(),
    }
    return {OUT/k:json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+"\n" for k,v in payloads.items()}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--check",action="store_true"); a=ap.parse_args(); rows=render(); bad=[]
    if a.check:
      for p,t in rows.items():
        if not p.exists() or p.read_text(encoding="utf-8")!=t: bad.append(p.relative_to(ROOT).as_posix())
      if bad:
        print("[FAIL] stale/missing generated contracts:",", ".join(bad)); return 1
      print(f"[OK] {len(rows)} v5 contract artifacts are current"); return 0
    OUT.mkdir(parents=True,exist_ok=True)
    for old in OUT.glob("*.json"): old.unlink()
    for p,t in rows.items(): p.write_text(t,encoding="utf-8"); print("[write]",p.relative_to(ROOT))
    return 0
if __name__=="__main__": raise SystemExit(main())
