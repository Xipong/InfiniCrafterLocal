#!/usr/bin/env python3
"""Export/check compact fingerprints derived from the canonical function registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.qa.runtime_contract_replay import (  # noqa: E402
    runtime_contract_fingerprint_manifest,
)

DEFAULT_OUT = ROOT / ".agent" / "runtime_contract_fingerprints.json"


def _text() -> str:
    return json.dumps(
        runtime_contract_fingerprint_manifest(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = _text()
    if args.check:
        if not args.out.is_file():
            print(json.dumps({"ok": False, "error": f"missing fingerprint file: {args.out}"}))
            return 1
        actual = args.out.read_text(encoding="utf-8")
        ok = actual == expected
        print(json.dumps({"ok": ok, "out": str(args.out)}, sort_keys=True))
        return 0 if ok else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(expected, encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
