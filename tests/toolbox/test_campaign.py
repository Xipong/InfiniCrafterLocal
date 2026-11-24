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


@pytest.mark.parametrize('outcome,api_mode', [
    ('failure', 'chat_completions'), ('success', 'chat_completions'), ('success', 'responses'),
    ('wire-drift', 'responses'), ('reasoning-conflict', 'chat_completions'), ('reasoning-missing', 'chat_completions'),
])
def test_real_campaign_entry_records_synthetic_sender_without_network_or_live_inference(tmp_path, outcome, api_mode):
    panel, preset = 'live20', 'live20-classic'
    output = tmp_path / 'campaign'
    env = {key: value for key, value in os.environ.items() if not key.startswith('INFINI_')}
    env.update(INFINI_SKIP_CONFIG_FILE='1', INFINI_USE_LLM='1', INFINI_CACHE_DIR=str(tmp_path / 'preimport/cache'),
               INFINI_WORLD_RECIPES_DIR=str(tmp_path / 'preimport/worlds'), INFINI_SDCPP_SERVER_AUTOSTART='0',
               INFINI_LLM_PROVIDER='openai_compat', INFINI_OPENAI_COMPAT_MODEL='qa-model',
               INFINI_OPENAI_COMPAT_BASE_URL='https://example.invalid/v1/', INFINI_LLM_API_MODE=api_mode,
               INFINI_LLM_RESPONSE_FORMAT='json_object', INFINI_LLM_MAX_TOKENS='512', INFINI_LLM_TEMPERATURE='0.5',
               INFINI_LLM_NETWORK_ATTEMPTS='1', INFINI_VISUAL_DIRECTOR_TEMPERATURE='0.5')
    script = textwrap.dedent('''
        import json, runpy, subprocess, sys
        from pathlib import Path
        root, output, outcome, panel, preset, api_mode = Path(sys.argv[1]), Path(sys.argv[2]), *sys.argv[3:]
        case_id = 'night_missile' if panel == 'live10' else 'woodwork_blade'
        sys.path[:0] = [str(root), str(root / 'generator')]
        def offline(event, args):
            if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
                raise AssertionError('unexpected external network')
        sys.addaudithook(offline)
        # Stub only the separate source-admission boundary. This test checks the
        # actual runner + provider interception, not Git's clean-tree behavior.
        project = output.parent / 'source-admission-fixture'
        (project / 'generator/infini_local').mkdir(parents=True)
        (project / '.git').mkdir()
        head = 'f' * 40
        original_check_output = subprocess.check_output
        def fake_check_output(command, *args, **kwargs):
            if command == ['git', '-C', str(project), 'rev-parse', 'HEAD']:
                return head + '\\n'
            if command == ['git', '-C', str(project), 'status', '--porcelain']:
                return ''
            return original_check_output(command, *args, **kwargs)
        subprocess.check_output = fake_check_output
        parents = [
            {'internalName': 'WoodenSword', 'name': 'Wooden Sword', 'sourceMod': 'Terraria', 'damage': 7},
            {'internalName': 'WorkBench', 'name': 'Work Bench', 'sourceMod': 'Terraria'},
        ]
        dump = output.parent / 'current-parents.jsonl'
        dump.write_text(''.join(json.dumps(row) + '\\n' for row in parents))
        from infini_local.pipelines.transport import client, http as transport_http, provider_wire
        if outcome in ('reasoning-conflict', 'reasoning-missing'):
            apply_common = provider_wire.apply_llm_common_options
            def injected_logical_request(*args, **kwargs):
                payload = apply_common(*args, **kwargs)
                payload.pop('reasoning_effort', None)
                payload.pop('reasoning', None)
                if outcome == 'reasoning-conflict':
                    payload.update(reasoning_effort='high', reasoning={'effort': 'medium'})
                return payload
            provider_wire.apply_llm_common_options = injected_logical_request
        if outcome == 'wire-drift':
            project_request = client._payload_for_context
            def injected_wire_request(*args, **kwargs):
                body = project_request(*args, **kwargs)
                body['temperature'] = 1.9
                return body
            client._payload_for_context = injected_wire_request
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
                sys.path.insert(0, str(root / 'tests/generator'))
                from authoring.test_low_level_three_stage_pipeline import _visual_kit, _vfx_output
                authored = build_runtime_fixture('workbench_blade')
                compiled = compile_runtime_program(authored)
                from infini_local.core.vfx.materials import vfx_model_payload
                responses = [authored, _visual_kit(compiled), vfx_model_payload(_vfx_output(compiled))]
            assert responses, 'unexpected extra stage/Repair'
            content = json.dumps(responses.pop(0))
            if api_mode == 'responses':
                return {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': content}]}]}
            return {'choices': [{'message': {'content': content}}]}
        transport_http.http_json = synthetic_sender
        sys.argv = ['campaign', '--run', '--panel', panel, '--output', str(output),
            '--project', str(project), '--expected-head', head, '--cases', case_id, '--preset', preset,
            '--expected-case-count', '1', '--parallel-crafts', '1', '--runtime-dump', str(dump),
            '--expected-provider', 'openai_compat', '--expected-model', 'qa-model',
            '--expected-base-url', 'https://example.invalid/v1/', '--expected-api-mode', api_mode,
            '--expected-response-format', 'json_object', '--expected-temperature', '0.5',
            '--expected-vfx-temperature', '0.34', '--expected-repair-temperature', '0.12',
            '--expected-max-tokens', '512', '--expected-visual-max-tokens', '512', '--expected-vfx-max-tokens', '512']
        if outcome.startswith('reasoning-'):
            sys.argv += ['--expected-reasoning-effort', 'high']
        try:
            runpy.run_module('toolbox.live.runner', run_name='__main__')
        except SystemExit as exc:
            assert outcome != "success" and exc.code == 1, (output / "results.ndjson").read_text()
        else:
            assert outcome == 'success', 'synthetic failed campaign must exit nonzero'
        assert len(physical) == {'failure': 1, 'success': 3}.get(outcome, 0), (output / 'results.ndjson').read_text()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(output), outcome, panel, preset, api_mode], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr + result.stdout[-1500:]
    manifest = json.loads((output / 'campaign_manifest.json').read_text())
    summary = json.loads((output / 'summary.json').read_text())
    assert manifest['panel'] == panel
    case_id = 'night_missile' if panel == 'live10' else 'woodwork_blade'
    assert manifest['cases'] == [case_id]
    assert manifest['preset'] == preset
    assert manifest['fullPreset'] is False
    assert manifest['realImageGeneration'] is False
    assert summary['failedCases'] == ([] if outcome == 'success' else [case_id])
    assert summary['logicalRequests'] == (3 if outcome == 'success' else 1)
    assert summary['httpRequests'] == {'failure': 1, 'success': 3}.get(outcome, 0)
    rows = [json.loads(line) for line in (output / 'results.ndjson').read_text().splitlines()]
    if outcome == 'failure':
        assert 'SYNTHETIC_OFFLINE_SENDER_NOT_INFERENCE' in rows[0]['error']
    elif outcome in {'wire-drift', 'reasoning-conflict', 'reasoning-missing'}:
        attempts = [json.loads(line) for line in (output / 'logical_llm.ndjson').read_text().splitlines()]
        errors = [row for row in attempts if row['phase'] == 'error']
        assert len(errors) == 1
        assert ('temperature' if outcome == 'wire-drift' else 'reasoning effort') in errors[0]['error']
        assert errors[0]['activeLogical'] == errors[0]['activeHttp'] == 0
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
