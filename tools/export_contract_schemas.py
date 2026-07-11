#!/usr/bin/env python3
"""Export deterministic JSON Schemas from the strict Python wire boundaries.

The schemas are diagnostic contracts, not code generators.  Python/C# runtime
owners remain explicit and are compared separately by tools/contract_parity.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.core.boundary_models import (  # noqa: E402
    AttackSpecBoundary,
    GameplaySpecBoundary,
    RuntimePlanBoundary,
    VfxManifestBoundary,
    VisualKitBoundary,
)

SCHEMA_DIR = ROOT / "contracts" / "schemas"
SCHEMAS: dict[str, type] = {
    "runtime_plan.schema.json": RuntimePlanBoundary,
    "attack_spec.schema.json": AttackSpecBoundary,
    "gameplay_spec.schema.json": GameplaySpecBoundary,
    "visual_kit.schema.json": VisualKitBoundary,
    "vfx_manifest.schema.json": VfxManifestBoundary,
}


def _schema_document(filename: str, model: type) -> dict[str, Any]:
    document = model.model_json_schema(by_alias=True, mode="validation")
    document["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    document["$id"] = f"https://infinicrafter.local/contracts/{filename}"
    document["x-infini-owner"] = f"{model.__module__}.{model.__name__}"
    document["x-infini-generated"] = True
    return document


def render_schemas() -> dict[Path, str]:
    return {
        SCHEMA_DIR / filename: json.dumps(_schema_document(filename, model), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        for filename, model in SCHEMAS.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail when committed schemas differ from strict models")
    args = parser.parse_args()
    rendered = render_schemas()
    mismatches: list[str] = []
    if args.check:
        for path, text in rendered.items():
            if not path.exists():
                mismatches.append(f"missing: {path.relative_to(ROOT)}")
            elif path.read_text(encoding="utf-8") != text:
                mismatches.append(f"stale: {path.relative_to(ROOT)}")
        if mismatches:
            for row in mismatches:
                print(f"[FAIL] {row}")
            return 1
        print(f"[OK] {len(rendered)} contract schemas are current")
        return 0

    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in rendered.items():
        path.write_text(text, encoding="utf-8")
        print(f"[write] {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
