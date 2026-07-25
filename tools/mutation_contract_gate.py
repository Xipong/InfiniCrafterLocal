#!/usr/bin/env python3
"""Mutation witnesses for registry locality, duplicate writers, lowerers and final wire."""
from __future__ import annotations
import json, sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"LocalGenerator"))
import infini_local.core.runtime_authoring.capability_registry as registry_module
import infini_local.core.runtime_authoring.validator as validator_module
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, audit_compiler_receipts, compile_runtime_program, runtime_program_author_schema, validate_runtime_program, validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

def build_report()->dict:
    rows=[]
    source=CAPABILITY_REGISTRY["emit_light_while_active"]
    synthetic=replace(source,name="emit_mutation_light",compiler_owner="missing.vertical.slice",csharp_owner="MissingExecutor.cs")
    mutated=MappingProxyType({**dict(CAPABILITY_REGISTRY),synthetic.name:synthetic})
    old_r,old_v=registry_module.CAPABILITY_REGISTRY,validator_module.CAPABILITY_REGISTRY
    try:
        registry_module.CAPABILITY_REGISTRY=mutated; validator_module.CAPABILITY_REGISTRY=mutated
        visible=any(x["properties"]["fn"].get("const")==synthetic.name for x in runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"])
        doc=build_runtime_fixture("door_on_chain"); doc["runtimeProgram"]["calls"].append({"id":"mutation_light","fn":synthetic.name,"target":"chained_door","params":{"strength":0.5,"color":"white"}})
        try: compile_runtime_program(doc); stayed_red=False
        except AssertionError: stayed_red=True
    finally:
        registry_module.CAPABILITY_REGISTRY=old_r; validator_module.CAPABILITY_REGISTRY=old_v
    rows.append({"mutation":"new_capability_missing_executor","caught":visible and stayed_red})
    dup=build_runtime_fixture("workbench_blade"); call=deepcopy(dup["runtimeProgram"]["calls"][0]); call["id"]="duplicate_writer"; dup["runtimeProgram"]["calls"].append(call)
    rows.append({"mutation":"second_writer_existing_component","caught":any(x.get("code")=="duplicate_single_component" for x in validate_runtime_program(dup)["errors"])})
    bad=audit_compiler_receipts([{"callId":"alias","fn":"emit_light_while_active","authoredPath":"x","finalPath":"runtimeProgram.entities[].movement.code","value":1,"status":"delivered"}])
    rows.append({"mutation":"technical_alias_undeclared_output","caught":not bad["ok"]})
    wire=compile_runtime_program(build_runtime_fixture("workbench_blade")); wire["runtimeProgram"]["entities"][0]["newFinalWireField"]={}
    rows.append({"mutation":"new_final_wire_field_without_dto","caught":any(x.get("code")=="unknown_final_wire_field" for x in validate_runtime_wire(wire)["errors"])})
    return {"schema":"infini.low-level-mutation-gate.v1","ok":all(x["caught"] for x in rows),"rows":rows}
if __name__=="__main__":
    r=build_report(); print(json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)); raise SystemExit(0 if r["ok"] else 1)
