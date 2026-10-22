"""Offline reconciliation of existing campaign lanes, including interrupted runs."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from toolbox.live.support import case_transport_retry_report, transport_retry_summary


def _rows(path: Path) -> list[dict[str, Any]]:
    result = []
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f'{path.name}:{number}: invalid JSON (raw data withheld)') from exc
        if not isinstance(row, dict):
            raise ValueError(f'{path.name}:{number}: expected object')
        result.append(row)
    return result


def _terminals(rows: list[dict[str, Any]]) -> tuple[int, list[Any], bool]:
    requests = Counter(row.get('sequence') for row in rows if row.get('phase') == 'request')
    ends = Counter(row.get('sequence') for row in rows if row.get('phase') in ('response', 'error'))
    pending = sorted((requests - ends).elements(), key=str)
    return sum(requests.values()), pending, bool(requests) and requests == ends and all(n == 1 for n in requests.values())


def summarize(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / 'campaign_manifest.json').read_text(encoding='utf-8'))
    planned = manifest.get('cases')
    if not isinstance(planned, list) or not planned or any(not isinstance(c, str) for c in planned) or len(planned) != len(set(planned)):
        raise ValueError('campaign manifest requires distinct nonempty case IDs')
    names = ('results', 'logical_llm', 'http_llm', 'harness_events', 'image_boundary')
    missing = [name + '.ndjson' for name in names if not (directory / (name + '.ndjson')).is_file()]
    lanes = {name: _rows(directory / (name + '.ndjson')) if name + '.ndjson' not in missing else [] for name in names}
    results = lanes['results']
    counts = Counter(row.get('case') for row in results)
    completed = set(counts) & set(planned)
    observed = {row.get("case") for rows in lanes.values() for row in rows}
    unknown_activity = observed - set(planned)
    successful = [row['case'] for row in results if row.get('ok') is True]
    image_counts = Counter(row.get('case') for row in lanes['image_boundary'])
    logical_count, logical_pending, logical_ok = _terminals(lanes['logical_llm'])
    http_count, http_pending, http_ok = _terminals(lanes['http_llm'])
    report: dict[str, Any] = {
        'schema': 'infini.toolbox-offline-summary.v1',
        'planned': len(planned), 'completed': len(completed),
        'succeeded': sum(counts[c] == 1 and c in successful for c in planned),
        'failedCases': [row.get('case') for row in results if row.get('ok') is not True],
        'missingCases': [c for c in planned if c not in completed],
        'duplicateCases': sorted((c for c, n in counts.items() if n > 1), key=str),
        'unexpectedCases': sorted(set(counts) - set(planned), key=str),
        'unexpectedTraceCases': sorted(unknown_activity, key=str),
        'unstartedCases': [c for c in planned if c not in observed] if not missing else None,
        'unfinishedCases': [c for c in planned if c not in completed and c in observed],
        'missingFiles': missing,
        'logicalRequests': None if 'logical_llm.ndjson' in missing else logical_count,
        'httpRequests': None if 'http_llm.ndjson' in missing else http_count,
        'logicalPending': logical_pending, 'httpPending': http_pending,
        'terminalCoverage': logical_ok and http_ok,
        'imageBoundaryMissing': [c for c in successful if image_counts[c] == 0],
        'imageBoundaryDuplicates': sorted((c for c, n in image_counts.items() if n > 1), key=str),
        'imageBoundaryUnexpected': sorted(set(image_counts) - set(successful), key=str),
        'firstAuthorSuccesses': sum(row.get('ok') is True and row.get('firstAuthorSuccess') is True and int(row.get('caseTransportRetries') or 0) == 0 for row in results),
        'authorBudgetViolations': [row.get('case') for row in results if row.get('authorCallBudgetValid') is not True],
        'realImageGeneration': manifest.get('realImageGeneration'),
        'claim': 'Saved receipt accounting only; no fresh inference, wire revalidation, art or game acceptance.',
    }
    report.update(transport_retry_summary(lanes['logical_llm'], logical_requests=logical_count, http_requests=http_count))
    report.update(case_transport_retry_report(lanes['logical_llm'], lanes['harness_events']))
    report['caseTransportRetryAccountingConsistent'] = report['caseTransportRetryCount'] == sum(int(row.get('caseTransportRetries') or 0) for row in results)
    logical_domain_errors = any(row.get('phase') == 'error' and not row.get('transportError') for row in lanes['logical_llm'])
    report['ok'] = (
        not any(report[key] for key in ('failedCases', 'missingCases', 'duplicateCases', 'unexpectedCases',
                                        'missingFiles', 'unexpectedTraceCases', 'imageBoundaryMissing', 'imageBoundaryDuplicates',
                                        'imageBoundaryUnexpected', 'authorBudgetViolations', 'unaccountedTransportErrors'))
        and report['terminalCoverage'] and report['caseAttemptCoverage'] and report['retryWaitCoverage']
        and report['caseTransportRetryAccountingConsistent'] and report['transportRetryAccountingConsistent']
        and report['transportRetryCount'] == 0 and not logical_domain_errors
        and report['firstAuthorSuccesses'] >= int(manifest.get('minFirstAuthor') or 0)
    )
    return report
