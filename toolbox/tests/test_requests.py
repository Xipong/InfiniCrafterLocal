"""Cold-process real request builder -> campaign guards -> transport -> JSON parser."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('api_mode', ['chat_completions', 'responses'])
@pytest.mark.parametrize('mutation,expected', [('none', 'accepted'), ('temperature', 'blocked'), ('wire-temperature', 'blocked'), ('image', 'blocked')])
def test_actual_request_and_parser_through_campaign_hooks(tmp_path, mutation, expected, api_mode):
    # Import-time provider configuration is intentionally exercised in a fresh process.
    script = textwrap.dedent('''
        import ast, copy, json, os, sys, threading, time
        from pathlib import Path
        from typing import Any, cast
        from datetime import datetime, timezone
        root, output, mutation, api_mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
        sys.path[:0] = [str(root), str(root / 'LocalGenerator')]
        for key in list(os.environ):
            if key.startswith('INFINI_'):
                del os.environ[key]
        os.environ.update(INFINI_SKIP_CONFIG_FILE='1', INFINI_CACHE_DIR=str(output / 'cache'),
            INFINI_WORLD_RECIPES_DIR=str(output / 'worlds'), INFINI_SDCPP_SERVER_AUTOSTART='0',
            INFINI_LLM_PROVIDER='openai_compat', INFINI_OPENAI_COMPAT_MODEL='qa-model',
            INFINI_OPENAI_COMPAT_BASE_URL='https://example.invalid/v1/', INFINI_LLM_API_MODE=api_mode, INFINI_LLM_MAX_TOKENS='512',
            INFINI_LLM_RESPONSE_FORMAT='json_object', INFINI_LLM_FALLBACK_NETWORK_FAILS='1',
            INFINI_LLM_TEMPERATURE='0.5')
        def offline(event, args):
            if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
                raise AssertionError('unexpected external network')
        sys.addaudithook(offline)
        from toolbox.live.options import build_parser
        from toolbox.live import support
        from infini_local.pipelines.transport import client as llm_transport
        from infini_local.pipelines.author.request import build_initial_author_request
        from infini_local.core.llm_json_tools import parse_first_valid_llm_json
        from infini_local.pipelines.transport.provider_wire import with_llm_stage
        args = build_parser().parse_args(['--expected-model', 'qa-model', '--expected-temperature', '0.5', '--expected-max-tokens', '512', '--expected-response-format', 'json_object'])
        from contextvars import ContextVar
        active_stage = ContextVar('test_stage', default='non_author')
        if mutation == 'wire-temperature':
            original_projection = llm_transport._payload_for_context
            def changed_projection(payload, context):
                result = original_projection(payload, context)
                result['temperature'] = 1.9
                return result
            llm_transport._payload_for_context = changed_projection
        captured = []
        sent = []
        def sender(url, payload, **kwargs):
            sent.append(payload)
            if api_mode == 'responses':
                return {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}]}
            return {'choices': [{'message': {'content': '{"ok":true}'}}]}
        ns = dict(globals(), args=args, expected_model='qa-model', expected_base_url='https://example.invalid/v1/',
            global_accounting=support.GlobalStageAccounting(), original_http_json=sender, ACTIVE_STAGE=active_stage,
            original_llm_chat_json=llm_transport.llm_chat_json,
            append=lambda lane, row: captured.append((lane,row)), HTTP='http', LOGICAL='logical')
        ns.update(vars(support))
        harness = root / 'toolbox/live/runner.py'
        selected = {'assert_frozen_logical_settings', 'captured_http_json', 'captured_llm_chat_json',
                    'lease_snapshot', 'case_trace_fields', 'wall_time_fields', 'forbidden_backend'}
        nodes = [node for node in ast.parse(harness.read_text()).body if isinstance(node, ast.FunctionDef) and node.name in selected]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(harness), 'exec'), ns)
        llm_transport.http_json = ns['captured_http_json']
        items = [json.loads(line) for line in (root / 'toolbox/fixtures/items.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        parents = {row['internalName']: row for row in items}
        request, _, _ = build_initial_author_request(parents['WoodenSword'], parents['WorkBench'], 'qa-request')
        request = with_llm_stage(request, 'planner')
        if mutation == 'temperature':
            request['temperature'] = 1.9
        try:
            if mutation == 'image':
                ns['forbidden_backend']()
            else:
                response = ns['captured_llm_chat_json'](request, timeout=10)
                assert parse_first_valid_llm_json(response['choices'][0]['message']['content']) == {'ok':True}
            outcome = 'accepted'
        except (RuntimeError, AssertionError) as exc:
            outcome = 'blocked'
        print(json.dumps({'outcome':outcome, 'sent':len(sent), 'counts':ns['global_accounting'].snapshot()}))
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(tmp_path), mutation, api_mode], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report['outcome'] == expected
    assert report['sent'] == (1 if expected == 'accepted' else 0)
    assert report['counts']['activeLogical'] == report['counts']['activeHttp'] == 0
