from __future__ import annotations

from argparse import Namespace
from collections.abc import Iterable
import copy
import hashlib
import json
from typing import Any

from toolbox.live.catalog import DEFAULT_PRESETS, FIXTURES, load_panel


def select_case_routes(routes: Iterable[tuple[str, str, str]], selected_ids: set[str]) -> list[tuple[str, str, str]]:
    rows = list(routes)
    unknown = selected_ids - {row[0] for row in rows}
    if unknown:
        raise ValueError(f"unknown case IDs: {', '.join(sorted(unknown))}")
    return [row for row in rows if not selected_ids or row[0] in selected_ids]


def load_selection(args: Namespace):
    preset_name = getattr(args, 'preset', None)
    if preset_name and args.cases_file:
        raise ValueError('--preset and --cases-file are mutually exclusive')
    package = None
    if args.cases_file:
        source_path = args.cases_file.expanduser().resolve()
        default_dump = FIXTURES / 'items.jsonl'
    else:
        package = load_panel(preset_name or DEFAULT_PRESETS[args.panel])
        if package['command'] != args.panel:
            raise ValueError('--preset belongs to a different live command')
        source_path = package['sourcePath']
        default_dump = package['runtimeDumpPath']
    runtime_dump = (args.runtime_dump or default_dump).expanduser().resolve()
    if not runtime_dump.is_file():
        raise ValueError(f"parent runtime dump is missing: {runtime_dump}")
    items: dict[str, dict[str, Any]] = {}
    with runtime_dump.open(encoding="utf-8-sig") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            internal = str(row.get("internalName") or "")
            if internal:
                if internal in items:
                    raise ValueError(f"duplicate parent identity: {internal}")
                items[internal] = row

    raw_payload = json.loads(source_path.read_text(encoding="utf-8"))
    raw_cases = raw_payload.get("cases") if isinstance(raw_payload, dict) else raw_payload
    if not isinstance(raw_cases, list):
        raise ValueError("--cases-file must contain a list or an object with a cases list")
    active_routes: list[tuple[str, str, str]] = []
    seen_case_ids: set[str] = set()
    for index, row in enumerate(raw_cases):
        if not isinstance(row, dict):
            raise ValueError(f"--cases-file row {index} must be an object")
        case_id = str(row.get("case") or "").strip()
        parent_a = str(row.get("itemA") or "").strip()
        parent_b = str(row.get("itemB") or "").strip()
        if (
            not case_id or len(case_id) > 64 or not case_id.replace("_", "").isalnum()
            or case_id.lower() != case_id
        ):
            raise ValueError(f"--cases-file row {index} has invalid case ID {case_id!r}")
        if not parent_a or not parent_b:
            raise ValueError(f"--cases-file row {index} requires itemA and itemB")
        if case_id in seen_case_ids:
            raise ValueError(f"--cases-file repeats case ID {case_id!r}")
        seen_case_ids.add(case_id)
        active_routes.append((case_id, parent_a, parent_b))
    if not active_routes:
        raise ValueError("--cases-file has no cases")
    cases_file_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    requested_ids = [value.strip() for value in args.cases.split(',')] if args.cases is not None else []
    if args.cases is not None and (not all(requested_ids) or len(requested_ids) != len(set(requested_ids))):
        raise ValueError('--cases must contain distinct nonempty IDs')
    selected_routes = select_case_routes(active_routes, set(requested_ids))
    missing_items = sorted({
        name for _, a_name, b_name in selected_routes
        for name in (a_name, b_name) if name not in items
    })
    if missing_items:
        raise ValueError(f"runtime dump is missing: {', '.join(missing_items)}")
    selected_cases = [
        (case_id, copy.deepcopy(items[parent_a]), copy.deepcopy(items[parent_b]))
        for case_id, parent_a, parent_b in selected_routes
    ]
    if not selected_cases:
        raise ValueError("no live cases selected")
    if args.expected_case_count is not None and len(selected_cases) != args.expected_case_count:
        raise ValueError(f"selected {len(selected_cases)} cases, expected {args.expected_case_count}")
    if args.min_first_author < 0 or args.min_first_author > len(selected_cases):
        raise ValueError(f"--min-first-author must be within 0..{len(selected_cases)}")
    metadata = {
        'preset': package['id'] if package else None,
        'panelTitle': package['title'] if package else 'Custom case selection',
        'panelProvenance': package['provenance'] if package else 'Explicit custom --cases-file; not a built-in historical cohort.',
        'historicalPreset': package['historical'] if package else False,
        'fullPreset': len(selected_routes) == len(active_routes),
        'casesFile': str(source_path), 'casesFileSha256': cases_file_sha256,
    }
    return runtime_dump, selected_routes, selected_cases, str(source_path), cases_file_sha256, metadata
