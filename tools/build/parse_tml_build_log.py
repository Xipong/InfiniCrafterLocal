#!/usr/bin/env python3
"""Parse dotnet/tModLoader build logs into a compact error summary.

Portable helper for the real tModLoader build loop.  It understands both plain
MSBuild/Roslyn diagnostics and the tML client.log wrapper format, e.g.:
`[12:52:39] [.NET TP Worker/ERROR] [tML]: C:/.../File.cs(10,5): error CS1061: ...`.
It also collapses repeated UI `Error:` echoes so a single compiler issue is not
reported three times.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

TML_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s+\[[^\]]+/[^\]]+\]\s+\[[^\]]+\]:\s*(?P<body>.*)$")
UI_ERROR_PREFIX_RE = re.compile(r"^(?:Error|Ошибка)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
DIAG_RE = re.compile(
    r"^(?P<file>.*?)(?:\((?P<line>\d+)(?:,(?P<col>\d+))?\))?\s*:\s*"
    r"(?P<level>error|warning)\s+(?P<code>[A-Z]+\d+|CS\d+|MSB\d+|NETSDK\d+)\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
ERROR_LINE_RE = re.compile(r"\b(error\s+(?:CS|MSB|NETSDK)\d+|\[ERROR\]|Build FAILED|Сборка.*ошиб|Компиляция.*провал)", re.IGNORECASE)
WARNING_LINE_RE = re.compile(r"\b(warning\s+(?:CS|MSB|NETSDK)\d+|\[WARN\])", re.IGNORECASE)


def _unwrap_log_line(line: str) -> str:
    """Strip tML/client UI prefixes while preserving the original diagnostic body."""
    line = line.strip().lstrip("\ufeff")
    for _ in range(3):
        m = TML_PREFIX_RE.match(line)
        if m:
            line = m.group("body").strip()
            continue
        m = UI_ERROR_PREFIX_RE.match(line)
        if m:
            line = m.group("body").strip()
            continue
        break
    return line


def _dedupe_key(entry: dict[str, object]) -> tuple[str, int, int, str, str]:
    return (
        str(entry.get("file") or "").lower(),
        int(entry.get("line") or 0),
        int(entry.get("col") or 0),
        str(entry.get("code") or "").upper(),
        str(entry.get("message") or "")[:220],
    )


def _mod_match(entry: dict[str, object], mod: str | None) -> bool:
    if not mod:
        return True
    hay = f"{entry.get('file','')} {entry.get('message','')}".lower()
    return mod.lower() in hay


def parse_build_log(text: str, *, mod: str | None = None, dedupe: bool = True) -> dict[str, object]:
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    raw_error_lines: list[str] = []
    seen_errors: set[tuple[str, int, int, str, str]] = set()
    seen_warnings: set[tuple[str, int, int, str, str]] = set()
    seen_raw: set[str] = set()

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _unwrap_log_line(raw)
        if not line:
            continue
        match = DIAG_RE.match(line)
        if match:
            entry: dict[str, object] = {k: (v or "") for k, v in match.groupdict().items()}
            entry["logLine"] = lineno
            try:
                entry["line"] = int(entry["line"] or 0)
                entry["col"] = int(entry["col"] or 0)
            except Exception:
                pass
            if not _mod_match(entry, mod):
                continue
            if str(entry.get("level", "")).lower() == "error":
                key = _dedupe_key(entry)
                if not dedupe or key not in seen_errors:
                    errors.append(entry)
                    seen_errors.add(key)
            else:
                key = _dedupe_key(entry)
                if not dedupe or key not in seen_warnings:
                    warnings.append(entry)
                    seen_warnings.add(key)
            continue
        if ERROR_LINE_RE.search(line):
            if mod and mod.lower() not in line.lower():
                continue
            clipped = line[:600]
            if not dedupe or clipped not in seen_raw:
                raw_error_lines.append(clipped)
                seen_raw.add(clipped)
        elif WARNING_LINE_RE.search(line):
            if mod and mod.lower() not in line.lower():
                continue
            entry = {"file": "", "line": 0, "col": 0, "level": "warning", "code": "", "message": line[:600], "logLine": lineno}
            key = _dedupe_key(entry)
            if not dedupe or key not in seen_warnings:
                warnings.append(entry)
                seen_warnings.add(key)

    by_code: dict[str, int] = {}
    for e in errors:
        code = str(e.get("code") or "raw")
        by_code[code] = by_code.get(code, 0) + 1
    # tModLoader often repeats a concise BuildException/UI summary after Roslyn
    # diagnostics.  Keep raw error lines only when they are the only signal, so
    # the user sees actionable file/line errors instead of inflated counts.
    effective_raw_error_lines = [] if errors else raw_error_lines
    return {
        "ok": not errors and not effective_raw_error_lines,
        "errorCount": len(errors) + len(effective_raw_error_lines),
        "warningCount": len(warnings),
        "errors": errors[:80],
        "warnings": warnings[:80],
        "rawErrorLines": effective_raw_error_lines[:80],
        "errorCodes": dict(sorted(by_code.items())),
        "deduped": bool(dedupe),
        "modFilter": mod or "",
    }


def format_summary(summary: dict[str, object], *, max_items: int = 20) -> str:
    status = "OK" if summary["ok"] else "FAIL"
    lines = [f"[{status}] errors={summary['errorCount']} warnings={summary['warningCount']}"]
    if summary.get("modFilter"):
        lines.append(f"[filter] mod={summary['modFilter']}")
    codes = summary.get("errorCodes") or {}
    if codes:
        lines.append("[codes] " + ", ".join(f"{k}x{v}" for k, v in dict(codes).items()))
    for e in list(summary.get("errors") or [])[:max_items]:
        loc = f"{e.get('file')}({e.get('line')},{e.get('col')})" if e.get("file") else f"log:{e.get('logLine')}"
        lines.append(f" - {loc}: {e.get('level')} {e.get('code')}: {e.get('message')}")
    for line in list(summary.get("rawErrorLines") or [])[:max_items]:
        lines.append(f" - {line}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", help="Build/client log file. Reads stdin when omitted.")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary.")
    ap.add_argument("--mod", default="", help="Only keep diagnostics mentioning this mod/name/path fragment, e.g. InfiniCrafterLocal.")
    ap.add_argument("--no-dedupe", action="store_true", help="Keep duplicate tML/UI echo diagnostics.")
    args = ap.parse_args(argv)

    if args.log:
        text = Path(args.log).read_text(encoding="utf-8", errors="ignore")
    else:
        text = sys.stdin.read()
    summary = parse_build_log(text, mod=args.mod or None, dedupe=not args.no_dedupe)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_summary(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
