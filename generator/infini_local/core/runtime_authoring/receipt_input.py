"""Structural receipt admission without historical spelling or path adapters."""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.parameter_contract import ParamSpec


def receipt_param_spec(cap: Any, path: str) -> ParamSpec | None:
    parts = path.split(".")
    spec = cap.params.get(parts[0])
    for part in parts[1:]:
        spec = spec.properties.get(part) if spec is not None else None
    return spec


def receipt_path_segments(path: str) -> list[str | int] | None:
    """Parse receipt grammar; unrepresentable numeric indices are malformed."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*|\[\d+\])*", path):
        return None
    try:
        return [int(segment[1:-1]) if segment.startswith("[") else segment
                for segment in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path)]
    except ValueError:
        # Python bounds decimal conversion. Report bad input, never truncate it
        # or change the process-wide integer conversion limit.
        return None


def prepare_receipt_rows(receipts: Iterable[Any]) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    """Inspect exact current receipt rows without rewriting input."""
    violations: list[dict[str, Any]] = []
    receipt_rows: list[Mapping[str, Any]] = []
    for receipt_index, receipt in enumerate(receipts):
        row_path = f"$.runtimeContract.finalWireReceipts[{receipt_index}]"
        malformed: list[str] = []
        if not isinstance(receipt, Mapping):
            malformed.append("")
        else:
            required = {"finalPath", "status"}
            required.update({"authoredPaths"} if receipt.get("lowererId") else {"fn", "callId", "authoredPath"})
            for key in ("fn", "lowererId", "callId", "finalPath", "authoredPath", "status"):
                if key in receipt or key in required:
                    if not isinstance(receipt.get(key), str) or not receipt[key]:
                        malformed.append(key)
            if "authoredPaths" in receipt or "authoredPaths" in required:
                paths = receipt.get("authoredPaths")
                if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
                    malformed.append("authoredPaths")
            if "value" not in receipt:
                malformed.append("value")
            for key in ("finalPath", "authoredPath", "authoredPaths"):
                paths = receipt.get(key)
                paths = paths if key == "authoredPaths" else [paths]
                if isinstance(paths, list):
                    for index, path in enumerate(paths):
                        if isinstance(path, str) and receipt_path_segments(path) is None:
                            malformed.append(f"{key}[{index}]" if key == "authoredPaths" else key)
        if malformed:
            violations.extend({"receiptIndex": receipt_index,
                               "path": row_path + (f".{key}" if key else ""),
                               "reason": "malformed compiler receipt row or field"}
                              for key in malformed)
            continue
        # Only structurally valid rows can participate in source coverage.
        receipt_rows.append(receipt)
    return receipt_rows, violations
