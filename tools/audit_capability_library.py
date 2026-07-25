from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "LocalGenerator"
if str(LOCAL) not in sys.path:
    sys.path.insert(0, str(LOCAL))

from infini_local.qa.capability_library_audit import capability_library_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the machine-readable low-level runtime capability library.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = capability_library_audit()
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, "utf-8")
    print(encoded, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
