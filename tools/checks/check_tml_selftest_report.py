#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

REQUIRED = {
    "multi-entity-program-normalizes",
    "category-cannot-select-equipment-role",
    "duplicate-exclusive-input-rejected",
    "event-cycle-rejected",
    "old-runtime-api-rejected",
    "retired-shape-rejected",
    "strict-vfx-json",
}
EXPECTED_SCHEMA = "infini.tml-runtime-selftest.v3"
EXPECTED_RUNTIME_API = "infini.runtime-program.v5"


def assembly_mvid(path: Path) -> str:
    """Read the ECMA-335 Module row without loading or executing the target DLL."""
    data = path.read_bytes()

    def read(offset: int, count: int) -> bytes:
        if offset < 0 or count < 0 or offset + count > len(data):
            raise ValueError("truncated managed PE image")
        return data[offset:offset + count]

    def number(offset: int, size: int) -> int:
        return int.from_bytes(read(offset, size), "little")

    pe = number(0x3c, 4)
    if read(0, 2) != b"MZ" or read(pe, 4) != b"PE\0\0":
        raise ValueError("not a PE image")
    optional = pe + 24
    magic = number(optional, 2)
    if magic not in {0x10b, 0x20b}:
        raise ValueError("unsupported PE optional header")
    directories = optional + (96 if magic == 0x10b else 112)
    section_table = optional + number(pe + 20, 2)

    def from_rva(rva: int) -> int:
        for index in range(number(pe + 6, 2)):
            section = section_table + index * 40
            start, length = number(section + 12, 4), number(section + 16, 4)
            if start <= rva < start + length:
                return number(section + 20, 4) + rva - start
        raise ValueError("managed metadata RVA is outside file-backed sections")

    cli = from_rva(number(directories + 14 * 8, 4))
    metadata = from_rva(number(cli + 8, 4))
    if read(metadata, 4) != b"BSJB":
        raise ValueError("missing CLI metadata signature")
    cursor = metadata + 16 + ((number(metadata + 12, 4) + 3) & ~3)
    stream_count = number(cursor + 2, 2)
    cursor += 4
    streams: dict[str, tuple[int, int]] = {}
    for _ in range(stream_count):
        offset, size = number(cursor, 4), number(cursor + 4, 4)
        name_start = cursor + 8
        name_end = data.find(b"\0", name_start, name_start + 32)
        if name_end < 0:
            raise ValueError("invalid CLI stream name")
        name = read(name_start, name_end - name_start).decode("ascii")
        read(metadata + offset, size)
        streams[name] = (metadata + offset, size)
        cursor = (name_end + 4) & ~3
    tables, tables_size = streams.get("#~", streams.get("#-", (0, 0)))
    guids, guid_size = streams.get("#GUID", (0, 0))
    if tables_size < 28 or guid_size < 16:
        raise ValueError("missing CLI Module/GUID metadata")
    heaps, valid = number(tables + 6, 1), number(tables + 8, 8)
    if not valid & 1 or number(tables + 24, 4) != 1:
        raise ValueError("expected one CLI Module row")
    module = tables + 24 + valid.bit_count() * 4
    string_width, guid_width = (4 if heaps & 1 else 2), (4 if heaps & 2 else 2)
    if module + 2 + string_width + guid_width > tables + tables_size:
        raise ValueError("truncated CLI Module row")
    index = number(module + 2 + string_width, guid_width)
    if index < 1 or index * 16 > guid_size:
        raise ValueError("invalid Module MVID index")
    value = uuid.UUID(bytes_le=read(guids + (index - 1) * 16, 16))
    if value.int == 0:
        raise ValueError("empty Module MVID")
    return str(value)


def validate(path: Path, *, mod_dll: Path | None = None, tml_dll: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": "infini.tml-runtime-selftest-check.v1", "ok": False, "path": str(path), "errors": [repr(exc)]}
    if not isinstance(payload, dict):
        return {"schema": "infini.tml-runtime-selftest-check.v1", "ok": False, "path": str(path), "errors": ["report must be an object"]}
    if payload.get("schema") != EXPECTED_SCHEMA:
        errors.append(f"unexpected schema {payload.get('schema')!r}")
    if payload.get("runtimeApi") != EXPECTED_RUNTIME_API:
        errors.append(f"unexpected runtimeApi {payload.get('runtimeApi')!r}")
    identities = payload.get("assemblies")
    for key, target in (("mod", mod_dll), ("tml", tml_dll)):
        if target is None:
            errors.append(f"{key} target DLL required to verify report identity")
            continue
        try:
            expected = assembly_mvid(target)
        except (OSError, ValueError) as exc:
            errors.append(f"{key} target DLL unreadable: {exc}")
            continue
        reported = identities.get(key) if isinstance(identities, dict) else None
        if not isinstance(reported, dict) or reported.get("moduleVersionId") != expected:
            errors.append(f"{key} assembly identity does not match target DLL")
    raw_rows = payload.get("checks")
    rows = raw_rows if isinstance(raw_rows, list) else []
    ids = [str(row.get("id") or "") for row in rows if isinstance(row, dict)]
    duplicates = sorted({check_id for check_id in ids if check_id and ids.count(check_id) > 1})
    if duplicates:
        errors.append("duplicate checks: " + ", ".join(duplicates))
    by_id = {str(row.get("id") or ""): row for row in rows if isinstance(row, dict)}
    missing = sorted(REQUIRED - set(by_id))
    if missing:
        errors.append("missing checks: " + ", ".join(missing))
    failed = sorted(check_id for check_id, row in by_id.items() if check_id and row.get("ok") is not True)
    if failed:
        errors.append("failed checks: " + ", ".join(failed))
    if payload.get("ok") is not True:
        errors.append("runtime report ok is not true")
    failures = payload.get("failures")
    if not isinstance(failures, list) or failures:
        errors.append("runtime report failures must be an empty array")
    return {
        "schema": "infini.tml-runtime-selftest-check.v1",
        "ok": not errors,
        "path": str(path),
        "checkCount": len(rows),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--mod-dll", type=Path, required=True)
    parser.add_argument("--tml-dll", type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.report, mod_dll=args.mod_dll, tml_dll=args.tml_dll)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
