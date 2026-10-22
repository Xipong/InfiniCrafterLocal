"""Exercise the entire campaign executable with a labeled, failing offline sender."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('outcome,panel,preset', [
    ('failure', 'live10', 'live10-midgame'), ('success', 'live10', 'live10-midgame'),
    ('success', 'live20', 'live20-classic'), ('success', 'live20', 'live20-classic-sprites'),
])
def test_real_campaign_entry_records_synthetic_sender_without_network_or_live_inference(tmp_path, outcome, panel, preset):
    output = tmp_path / 'campaign'
    env = {key: value for key, value in os.environ.items() if not key.startswith('INFINI_')}
    env.update(INFINI_SKIP_CONFIG_FILE='1', INFINI_USE_LLM='1', INFINI_CACHE_DIR=str(tmp_path / 'preimport/cache'),
               INFINI_WORLD_RECIPES_DIR=str(tmp_path / 'preimport/worlds'), INFINI_SDCPP_SERVER_AUTOSTART='0',
               INFINI_LLM_PROVIDER='openai_compat', INFINI_OPENAI_COMPAT_MODEL='qa-model',
               INFINI_OPENAI_COMPAT_BASE_URL='https://example.invalid/v1/', INFINI_LLM_API_MODE='chat_completions',
               INFINI_LLM_RESPONSE_FORMAT='json_object', INFINI_LLM_MAX_TOKENS='512', INFINI_LLM_TEMPERATURE='0.5',
               INFINI_LLM_FALLBACK_NETWORK_FAILS='1', INFINI_VISUAL_DIRECTOR_TEMPERATURE='0.5')
    script = textwrap.dedent('''
        import json, runpy, subprocess, sys
        from pathlib import Path
        root, output, outcome, panel, preset = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
        case_id = 'night_missile' if panel == 'live10' else 'woodwork_blade'
        sys.path[:0] = [str(root), str(root / 'LocalGenerator')]
        def offline(event, args):
            if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
                raise AssertionError('unexpected external network')
        sys.addaudithook(offline)
        # A tiny explicit Git fixture owns source-admission state even in source archives.
        # Runtime still comes from the source under test; no operator checkout is changed.
        project = output.parent / 'source-admission-fixture'
        (project / 'LocalGenerator/infini_local').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=QA', '-c', 'user.email=qa@example.invalid',
                        'commit', '--allow-empty', '-qm', 'synthetic admission fixture'], check=True)
        head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        from infini_local.pipelines import llm_transport
        physical = []
        responses = None
        def synthetic_sender(url, payload, **kwargs):
            global responses
            physical.append(payload)
            if outcome == 'failure':
                raise RuntimeError('SYNTHETIC_OFFLINE_SENDER_NOT_INFERENCE')
            if responses is None:
                # Import stage helpers only AFTER campaign instrumentation is installed.
                from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
                from infini_local.core.runtime_authoring.compiler import compile_runtime_program
                sys.path.insert(0, str(root / 'LocalGenerator/tests'))
                from test_low_level_three_stage_pipeline import _visual_kit, _vfx_output
                authored = build_runtime_fixture('workbench_blade')
                compiled = compile_runtime_program(authored)
                responses = [authored, _visual_kit(compiled), _vfx_output(compiled)]
            assert responses, 'unexpected extra stage/Repair'
            return {'choices': [{'message': {'content': json.dumps(responses.pop(0))}}]}
        llm_transport.http_json = synthetic_sender
        sys.argv = ['campaign', '--run', '--panel', panel, '--output', str(output),
            '--project', str(project), '--expected-head', head, '--cases', case_id, '--preset', preset,
            '--expected-case-count', '1', '--parallel-crafts', '1',
            '--expected-provider', 'openai_compat', '--expected-model', 'qa-model',
            '--expected-base-url', 'https://example.invalid/v1/', '--expected-api-mode', 'chat_completions',
            '--expected-response-format', 'json_object', '--expected-temperature', '0.5',
            '--expected-vfx-temperature', '0.34', '--expected-repair-temperature', '0.12',
            '--expected-max-tokens', '512', '--expected-visual-max-tokens', '512', '--expected-vfx-max-tokens', '512']
        try:
            runpy.run_module('toolbox.live.runner', run_name='__main__')
        except SystemExit as exc:
            assert outcome == "failure" and exc.code == 1, (output / "results.ndjson").read_text()
        else:
            assert outcome == 'success', 'synthetic failed campaign must exit nonzero'
        assert len(physical) == (1 if outcome == 'failure' else 3), (output / 'results.ndjson').read_text()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(output), outcome, panel, preset], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr + result.stdout[-1500:]
    manifest = json.loads((output / 'campaign_manifest.json').read_text())
    summary = json.loads((output / 'summary.json').read_text())
    assert manifest['panel'] == panel
    case_id = 'night_missile' if panel == 'live10' else 'woodwork_blade'
    assert manifest['cases'] == [case_id]
    assert manifest['preset'] == preset
    assert manifest['fullPreset'] is False
    assert manifest['realImageGeneration'] is False
    assert summary['failedCases'] == ([case_id] if outcome == 'failure' else [])
    assert summary['logicalRequests'] == summary['httpRequests'] == (1 if outcome == 'failure' else 3)
    rows = [json.loads(line) for line in (output / 'results.ndjson').read_text().splitlines()]
    if outcome == 'failure':
        assert 'SYNTHETIC_OFFLINE_SENDER_NOT_INFERENCE' in rows[0]['error']
    assert rows[0]['ok'] is (outcome == 'success')
    assert summary['ok'] is (outcome == 'success')
    if outcome == 'success':
        saved = tmp_path / 'saved-wire'
        saved.mkdir()
        boundary = json.loads((output / 'image_boundary.ndjson').read_text().splitlines()[0])
        (saved / 'final_item.json').write_text(json.dumps(boundary['finalContract']))
        replay = subprocess.run([sys.executable, '-m', 'toolbox', 'replay', str(saved)], cwd=ROOT, text=True, capture_output=True)
        assert replay.returncode == 0, replay.stderr + replay.stdout
        assert json.loads(replay.stdout)['ok'] is True
