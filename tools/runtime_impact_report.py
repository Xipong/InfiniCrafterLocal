#!/usr/bin/env python3
"""Report that QA/control-plane code stays outside the executable v5 runtime."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import semantic_runtime_diff

def build_report()->dict:
    leaks=[]
    for path in (ROOT/"LocalGenerator/infini_local").rglob("*.py"):
        text=path.read_text(encoding="utf-8-sig",errors="ignore")
        if re.search(r"(?:from|import)\s+(?:tools|contract_parity|mutation_contract_gate)\b",text): leaks.append(path.relative_to(ROOT).as_posix())
    csroot=ROOT/"ModSources/InfiniCrafterLocal"; selftest=csroot/"Common/Systems/InfiniAgentContractSelfTestSystem.cs"; source=selftest.read_text(encoding="utf-8-sig",errors="ignore") if selftest.exists() else ""
    checks={"noQaImports":not leaks,"v5SelfTest":"infini.runtime-program.v5" in source,"selfTestOptIn":"INFINI_AGENT_SELFTEST" in source,"noSelfTestProjectileSpawn":"Projectile.NewProjectile" not in source,"semanticFixtures":semantic_runtime_diff.build_report()["ok"]}
    return {"schema":"infini.low-level-runtime-impact.v2","ok":all(checks.values()),"checks":checks,"controlPlaneLeaks":leaks,"runtimePolicy":{"validatorsAuthorGameplay":False,"familyRouter":False,"capabilityPath":"registry -> strict Author schema -> compiler -> strict wire DTO -> finite C# dispatcher"}}
def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out",type=Path); a=ap.parse_args(); r=build_report(); t=json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+"\n"; a.out and (a.out.parent.mkdir(parents=True,exist_ok=True),a.out.write_text(t,encoding="utf-8")); print(t,end=""); return 0 if r["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
