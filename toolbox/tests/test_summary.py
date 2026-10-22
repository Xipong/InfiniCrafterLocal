from __future__ import annotations

import json
from pathlib import Path

from test_cli import cli  # shared offline CLI harness


def saved_run(tmp_path: Path):
    (tmp_path / 'campaign_manifest.json').write_text(json.dumps({'cases': ['a', 'b'], 'minFirstAuthor': 1, 'realImageGeneration': False}))
    rows = [{'case': c, 'ok': True, 'firstAuthorSuccess': True, 'authorCallBudgetValid': True, 'caseTransportRetries': 0} for c in ('a', 'b')]
    lanes = {'results': rows, 'logical_llm': [], 'http_llm': [], 'image_boundary': [{'case': c} for c in ('a', 'b')], 'harness_events': []}
    for i, case in enumerate(('a', 'b'), 1):
        for phase in ('request', 'response'):
            lanes['logical_llm'].append(dict(case=case, sequence=i, phase=phase))
            lanes['http_llm'].append(dict(case=case, sequence=i, phase=phase))
        for event in ('CASE_ATTEMPT_START', 'CASE_ATTEMPT_END'):
            lanes['harness_events'].append(dict(case=case, caseIndex=i, attempt=1, event=event))
    for name, data in lanes.items():
        write_rows(tmp_path / (name + '.ndjson'), data)
    return lanes


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_summary_reconciles_saved_ledgers_without_trusting_old_summary(monkeypatch, capsys, tmp_path):
    saved_run(tmp_path)
    (tmp_path / 'summary.json').write_text('{"ok":false,"cases":999}')
    code, output = cli(monkeypatch, capsys, 'summary', tmp_path)
    assert code == 0, output
    report = json.loads(output.out)
    assert report['ok'] is True
    assert (report['planned'], report['completed'], report['succeeded']) == (2, 2, 2)
    assert report['httpRequests'] == report['logicalRequests'] == 2
    assert report['realImageGeneration'] is False


def test_summary_preserves_interrupted_unknowns_and_duplicate_results(monkeypatch, capsys, tmp_path):
    lanes = saved_run(tmp_path)
    write_rows(tmp_path / 'results.ndjson', [lanes['results'][0]] * 2)
    write_rows(tmp_path / 'http_llm.ndjson', lanes['http_llm'][:-1])
    code, output = cli(monkeypatch, capsys, 'summary', tmp_path)
    assert code == 1
    report = json.loads(output.out)
    assert report['missingCases'] == ['b']
    assert report['duplicateCases'] == ['a']
    assert report['httpPending'] == [2]
    assert report['completed'] == 1


def test_summary_exposes_hidden_retry_and_missing_image_boundary(monkeypatch, capsys, tmp_path):
    lanes = saved_run(tmp_path)
    write_rows(tmp_path / 'http_llm.ndjson', lanes['http_llm'] + [dict(sequence=3, phase=p, case='a') for p in ('request', 'error')])
    write_rows(tmp_path / 'image_boundary.ndjson', [{'case': 'a'}])
    code, output = cli(monkeypatch, capsys, 'summary', tmp_path)
    report = json.loads(output.out)
    assert code == 1
    assert report['transportRetryCount'] == 1
    assert not report['transportRetryAccountingConsistent']
    assert report['imageBoundaryMissing'] == ['b']


def test_summary_unplanned_network_activity_is_not_silently_accepted(monkeypatch, capsys, tmp_path):
    lanes = saved_run(tmp_path)
    for lane in ('logical_llm', 'http_llm'):
        write_rows(tmp_path / (lane + '.ndjson'), lanes[lane] + [dict(case='unplanned', sequence=3, phase=p) for p in ('request', 'response')])
    code, output = cli(monkeypatch, capsys, 'summary', tmp_path)
    assert code == 1
    assert json.loads(output.out)['unexpectedTraceCases'] == ['unplanned']


def test_summary_missing_lane_is_unknown_not_zero_success(monkeypatch, capsys, tmp_path):
    saved_run(tmp_path)
    (tmp_path / 'logical_llm.ndjson').unlink()
    code, output = cli(monkeypatch, capsys, 'summary', tmp_path)
    assert code == 1
    report = json.loads(output.out)
    assert report['missingFiles'] == ['logical_llm.ndjson']
    assert report['logicalRequests'] is None
