#!/usr/bin/env python3
"""Registry/schema/prompt/compiler/C#-owner parity for the v5 low-level runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from check_delivery_contract import build_report as delivery_report
from check_planner_prompt_usability import build_report as prompt_report
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    capability_provider_union,
    compact_capability_catalog,
    runtime_program_author_schema,
)
from infini_local.qa.capability_library_audit import capability_library_audit
from infini_local.qa.capability_witnesses import capability_vertical_slice_report


def build_report() -> dict[str, Any]:
    names = set(CAPABILITY_REGISTRY)
    schema_names = {
        row["properties"]["fn"]["const"]
        for row in runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"]
    }
    library_audit = capability_library_audit()
    witness = capability_vertical_slice_report()
    delivery = delivery_report()
    prompt = prompt_report()
    scanner = subprocess.run(
        [sys.executable, str(ROOT / "tools/check_csharp_contracts.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    checks = {
        "registryProvider": {
            row["properties"]["fn"]["const"] for row in capability_provider_union()
        } == names,
        "registryCatalog": {row["fn"] for row in compact_capability_catalog()} == names,
        "registrySchema": schema_names == names,
        "compilerWitnesses": bool(witness.get("ok"))
        and witness.get("capabilityCount") == len(names),
        "csharpOwners": bool(library_audit["criteria"]["runtimeOwnership"]),
        "machineReadableLibrary": bool(library_audit["ok"]),
        "delivery": bool(delivery.get("ok")),
        "prompt": bool(prompt.get("ok")),
        "csharpScanner": scanner.returncode == 0,
    }
    return {
        "schema": "infini.low-level-contract-parity.v1",
        "ok": all(checks.values()),
        "capabilityCount": len(names),
        "checks": checks,
        "capabilityLibraryAudit": library_audit,
        "witnessFailures": [row for row in witness.get("rows", []) if not row.get("ok")],
        "csharpScannerOutput": scanner.stdout.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if not args.quiet:
        print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
