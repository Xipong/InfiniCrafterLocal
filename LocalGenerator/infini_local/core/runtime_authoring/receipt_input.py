"""Structural receipt admission and finite saved-provenance reading.

This owner never compiles Author input or authenticates a wire value. Semantic
projection/coverage checks remain in technical_lowering; current source-backed
calls explicitly disable historical spelling resolution.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import ParamSpec, capability_for_saved_receipt


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


def prepare_receipt_rows(receipts: Iterable[Any], *, allow_saved_names: bool) -> tuple[
    list[Mapping[str, Any]], set[int], list[dict[str, Any]]
]:
    """Return detached normalization where needed, preserving the input bytes."""
    violations: list[dict[str, Any]] = []
    receipt_rows: list[Mapping[str, Any]] = []
    predecessor_receipt_indices: set[int] = set()
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
        # Saved receipts retain their literal bytes. A local audit view may
        # resolve ONLY finite registry-declared predecessor source paths; a
        # source-backed current Author never enters this admission lane.
        if allow_saved_names and (cap := capability_for_saved_receipt(str(receipt.get("fn") or ""))) is not None:
            receipt = {**receipt, "fn": cap.name}
            match = re.fullmatch(r"(runtimeProgram\.calls\[\d+\]\.params\.)([A-Za-z][A-Za-z0-9_.]*)", receipt.get("authoredPath", ""))
            if match and (canonical := cap.canonical_receipt_param_path(match.group(2))) is not None:
                canonical_path = match.group(1) + canonical
                if canonical_path != receipt.get("authoredPath"):
                    leaf = receipt_param_spec(cap, canonical)
                    if leaf is None or match.group(2).rsplit(".", 1)[-1] not in leaf.previous_author_names:
                        predecessor_receipt_indices.add(len(receipt_rows))
                receipt = {**receipt, "authoredPath": canonical_path}
        # Only structurally valid rows can participate in source coverage.
        receipt_rows.append(receipt)
    return receipt_rows, predecessor_receipt_indices, violations
