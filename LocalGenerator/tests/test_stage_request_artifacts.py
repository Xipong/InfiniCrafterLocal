from __future__ import annotations

import copy
import hashlib
import json
import socket
import pytest

from infini_local.storage import trace_runtime, trace_tools


def _cache(monkeypatch, tmp_path):
    monkeypatch.setattr(trace_runtime, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(trace_runtime, 'TRACE_FILE', tmp_path / 'pipeline_trace.ndjson')
    monkeypatch.setattr(trace_runtime, 'PROMPT_TRACE_FILE', tmp_path / 'prompt_trace.ndjson')
    monkeypatch.setattr(trace_runtime, 'TRACE_PROMPTS_ENABLED', True)


def test_exact_stage_artifact_keeps_clean_bytes_and_sanitizes_only_credentials(monkeypatch, tmp_path):
    _cache(monkeypatch, tmp_path)
    record = getattr(trace_runtime, 'trace_stage_request', None)
    assert callable(record), 'trace owner needs a full stage request artifact, not a clipped rolling preview'
    clean = '{"parents":"' + ('ж' * 94000) + '","tail":"PARENT_TAIL","escaped":"\\u0410"}\r\n'
    secret = 'sk-fixturecredential123456789'
    request = {'messages': [
        {'role': 'system', 'name': 'contract', 'content': 'Exact\r\n system  text'},
        {'role': 'user', 'name': 'context', 'content': clean},
        {'role': 'user', 'content': 'credential=' + secret},
    ], 'headers': {'Authorization': 'Bearer DO_NOT_PERSIST'}, 'config': {'api_key': 'DO_NOT_PERSIST'}}
    before = copy.deepcopy(request)
    replacements = []
    native_replace = trace_tools.os.replace
    def replace(source, target):
        if str(target).endswith('.json'):
            replacements.append((source, target))
            assert source != target
            assert json.loads(source.read_bytes())['messages'][1]['content'] == clean
        return native_replace(source, target)
    monkeypatch.setattr(trace_tools.os, 'replace', replace)
    receipt = record('gameplay_author', 'r_exact', request, recipe_id='g_exact')
    assert receipt['status'] == 'stored'
    path = tmp_path / receipt['path']
    raw = path.read_bytes()
    artifact = json.loads(raw)
    assert artifact['stage'] == 'gameplay_author' and artifact['recipeKey'] == 'r_exact' and artifact['recipeId'] == 'g_exact'
    assert artifact['messages'][0] == request['messages'][0]
    assert artifact['messages'][1]['content'].encode() == clean.encode()
    assert artifact['messages'][2]['content'] == 'credential=[REDACTED]'
    assert secret.encode() not in raw and b'DO_NOT_PERSIST' not in raw
    assert 'headers' not in artifact and 'config' not in artifact
    assert receipt['artifactSha256'] == hashlib.sha256(raw).hexdigest()
    encoded_messages = json.dumps(artifact['messages'], ensure_ascii=False, separators=(',', ':')).encode()
    assert artifact['messagesSha256'] == hashlib.sha256(encoded_messages).hexdigest()
    assert receipt['messagesSha256'] == artifact['messagesSha256']
    assert artifact['sanitized'] is True and receipt['bytes'] == len(raw)
    assert len(replacements) == 1 and request == before
    event = trace_tools.tail_ndjson(trace_runtime.TRACE_FILE, 1)[0]
    assert event['payload'] == receipt and event['stage'] == 'gameplay_author'


def test_artifact_refusals_never_publish_partial_or_follow_linked_storage(monkeypatch, tmp_path):
    _cache(monkeypatch, tmp_path)
    external = tmp_path / 'outside'
    external.mkdir()
    (tmp_path / 'stage_requests').symlink_to(external, target_is_directory=True)
    request = {'messages': [{'role': 'system', 'content': 'unchanged'}]}
    receipt = trace_runtime.trace_stage_request('visual_director', 'r_link', request)
    assert receipt['status'] == 'refused' and receipt['reason'] == 'linked_storage'
    assert list(external.iterdir()) == []

    (tmp_path / 'stage_requests').unlink()
    request['messages'][0]['content'] = 'ж' * (2 * 1024 * 1024)
    receipt = trace_runtime.trace_stage_request('visual_director', 'r_large', request)
    assert receipt['status'] == 'stored' and receipt['bytes'] > 2 * 1024 * 1024
    published = tmp_path / receipt['path']
    assert json.loads(published.read_bytes())['messages'] == request['messages']
    published.unlink()

    monkeypatch.setattr(trace_runtime, 'TRACE_PROMPTS_ENABLED', False)
    assert trace_runtime.trace_stage_request('visual_director', 'r_disabled', request) == {'status': 'disabled'}
    assert not list((tmp_path / 'stage_requests').glob('*.json'))
    monkeypatch.setattr(trace_runtime, 'TRACE_PROMPTS_ENABLED', True)
    request['messages'][0]['content'] = 'full payload'
    def fail_replace(*args):
        raise OSError('DO_NOT_PERSIST_PRIVATE_ERROR')
    monkeypatch.setattr(trace_tools.os, 'replace', fail_replace)
    receipt = trace_runtime.trace_stage_request('visual_repair', 'r_disk', request)
    assert receipt['status'] == 'refused' and receipt['reason'] == 'OSError'
    assert list((tmp_path / 'stage_requests').glob('*.json')) == []
    assert list((tmp_path / 'stage_requests').glob('.request-*')) == []
    assert 'DO_NOT_PERSIST' not in json.dumps(trace_tools.tail_ndjson(trace_runtime.TRACE_FILE))


def test_missing_recipe_join_is_an_explicit_refusal_not_an_unowned_artifact(monkeypatch, tmp_path):
    _cache(monkeypatch, tmp_path)
    request = {'messages': [{'role': 'system', 'content': 'complete'}]}
    receipt = trace_runtime.trace_stage_request('visual_director', None, request)
    assert receipt == {'stage': 'visual_director', 'recipeKey': None, 'status': 'refused', 'reason': 'missing_recipe_join'}
    assert not (tmp_path / 'stage_requests').exists()


@pytest.mark.parametrize('stage', ['gameplay_author', 'gameplay_format_repair', 'gameplay_repair', 'visual_director', 'visual_repair'])
def test_actual_stage_seam_records_complete_request_before_provider_without_live_calls(monkeypatch, tmp_path, stage):
    from infini_local.pipelines import llm_authoring_pipeline as author, visual_generation_pipeline as visual
    from infini_local.core.runtime_authoring import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    _cache(monkeypatch, tmp_path)
    captured = []
    class CaptureComplete(BaseException):
        pass
    def stop(request, **kwargs):
        captured.append(copy.deepcopy(request))
        raise CaptureComplete()
    def no_network(*args, **kwargs):
        raise AssertionError('network forbidden in stage artifact tests')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    for owner in (author, visual):
        monkeypatch.setattr(owner, 'llm_chat_json', stop)
        monkeypatch.setattr(owner, 'resolve_llm_model', lambda: 'offline-model')
    monkeypatch.setattr(author, 'USE_LLM', True)
    parent = {'name': 'literal source', 'width': 17, 'height': 29, 'useTime': 21, 'useAnimation': 25,
        'spriteReferenceRaw': {'source': 'TextureAssets.Item', 'textureWidthPx': 73, 'textureHeightPx': 68,
            'currentFrame': {'source': 'draw_animation', 'xPx': 0, 'yPx': 34, 'widthPx': 73, 'heightPx': 32}}}
    source = build_runtime_fixture('workbench_blade')
    source['recipeKey'] = 'r_capture'
    source['id'] = 'g_capture'
    before = copy.deepcopy((parent, source))
    with pytest.raises(CaptureComplete):
        if stage == 'gameplay_author':
            author.try_llm_plan(parent, parent, {}, {}, 'r_capture')
        elif stage == 'gameplay_format_repair':
            _, context, _ = author.build_initial_author_request(parent, parent, {}, {}, 'r_capture', model_name='offline-model')
            author._repair_malformed_author_json(malformed_raw_text=json.dumps(source)[:-1] + ',}',
                parse_error=ValueError('fixture syntax'), original_recipe_context=context, model_name='offline-model')
        elif stage == 'gameplay_repair':
            broken = copy.deepcopy(source)
            next(row for row in broken['runtimeProgram']['calls'] if row['fn'] == 'configure_item_stats')['params']['damage'] = -1
            author.repair_author_item_after_failure(broken, parent, parent, {}, {}, 'r_capture', failure_report=author.validate_runtime_program(broken))
        else:
            data = compile_runtime_program(source)
            data_before = copy.deepcopy(data)
            kwargs = {'repair_errors': [{'path': '$.item.silhouette', 'message': 'required'}],
                'previous': {'item': {'prompt': 'frozen'}}, 'repair_scope': {'itemMutable': True, 'fieldPermissions': {'itemPaths': ['silhouette']}}} if stage == 'visual_repair' else {}
            visual._request_visual_kit(data, parent, parent, {}, {}, **kwargs)
    paths = list((tmp_path / 'stage_requests').glob('*.json'))
    assert len(paths) == 1, 'production stage must persist the exact request at its provider seam'
    artifact = json.loads(paths[0].read_bytes())
    assert artifact['stage'] == stage and artifact['recipeKey'] == 'r_capture'
    assert artifact['messages'] == captured[0]['messages'] and artifact['sanitized'] is False
    assert (parent, source) == before
    if stage.startswith('visual'):
        assert data == data_before
        packet = json.loads(artifact['messages'][1]['content'])
        parents = packet['parentFactsReadOnly' if stage == 'visual_repair' else 'parents']
        assert parents['parentA']['packet']['raw']['spriteReference'] == parent['spriteReferenceRaw']
        assert artifact['recipeId'] == 'g_capture'
        rows = packet['runtimeEntitiesReadOnly' if stage == 'visual_repair' else 'runtimeEntities']
        for row, accepted in zip(rows, data['runtimeProgram']['entities']):
            for field in ('spawn', 'lifetimeTicks', 'collision'):
                assert (field in row) == (field in accepted), 'accepted downstream mechanics must not disappear or gain defaults'
                if field in accepted:
                    assert row[field] == accepted[field]
        mechanics = packet['acceptedPresentationMechanicsReadOnly']['gameplay']
        for field in ('useTime', 'useAnimation', 'reuseDelay'):
            assert (field in mechanics) == (field in data['gameplay'])
            if field in data['gameplay']:
                assert mechanics[field] == data['gameplay'][field]
        calibration = packet['spritePresentationReadOnly']['sourceCalibration']
        assert all(token in calibration for token in ('spriteReference', 'currentFrame', 'bake fill', 'unknown', 'hitbox', 'not a required copy'))


@pytest.mark.parametrize('context_join', [None, 'not_the_owner'], ids=['missing-dossier-join', 'stale-dossier-join'])
@pytest.mark.parametrize('changed_value', [False, True], ids=['syntax-only', 'semantic-change-refused'])
def test_format_repair_capture_joins_author_owner_without_changing_frozen_fields(monkeypatch, tmp_path, context_join, changed_value):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    _cache(monkeypatch, tmp_path)
    monkeypatch.setattr(author, 'USE_LLM', True)
    monkeypatch.setattr(author, 'resolve_llm_model', lambda: 'offline-model')
    monkeypatch.setattr(transport, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    native_builder = author.build_initial_author_request
    def build_without_owner_join(*args, **kwargs):
        request, user, system = native_builder(*args, **kwargs)
        dossier = json.loads(user)
        if context_join is None:
            del dossier['recipeKey']
        else:
            dossier['recipeKey'] = context_join
        user = json.dumps(dossier, ensure_ascii=False, separators=(',', ':'))
        request['messages'][1]['content'] = user
        return request, user, system
    monkeypatch.setattr(author, 'build_initial_author_request', build_without_owner_join)
    frozen = build_runtime_fixture('workbench_blade')
    repaired = copy.deepcopy(frozen)
    if changed_value:
        next(c for c in repaired['runtimeProgram']['calls'] if c['fn'] == 'configure_item_stats')['params']['damage'] += 1
    malformed = json.dumps(frozen)[:-1] + ',}'
    repaired_text = json.dumps(repaired)
    responses = iter([malformed, repaired_text])
    requests = []
    def respond(request, **kwargs):
        requests.append(copy.deepcopy(request))
        return {'choices': [{'message': {'content': next(responses)}}], '_debug': {'responseFormatType': 'json_object'}}
    monkeypatch.setattr(author, 'llm_chat_json', respond)
    if changed_value:
        with pytest.raises(PlannerUnavailable, match='changed recoverable authored fields'):
            author.try_llm_plan({}, {}, {}, {}, 'r_actual_owner')
    else:
        result = author.try_llm_plan({}, {}, {}, {}, 'r_actual_owner')
        assert {key: result[key] for key in frozen} == frozen
        assert result['debug']['gameplayFormatRepairRawOutput'] == repaired_text[:12000]
    artifacts = [json.loads(path.read_bytes()) for path in (tmp_path / 'stage_requests').glob('*.json')]
    assert {row['stage'] for row in artifacts} == {'gameplay_author', 'gameplay_format_repair'}
    assert all(row['recipeKey'] == 'r_actual_owner' for row in artifacts)
    captured = next(row for row in artifacts if row['stage'] == 'gameplay_format_repair')
    assert captured['messages'] == requests[1]['messages']
    dossier = json.loads(captured['messages'][1]['content'])
    assert dossier['malformedRawText'] == malformed
    assert dossier['originalRecipeContext'].get('recipeKey') == context_join
    assert [request['_infini_stage'] for request in requests] == ['planner', 'author_repair']


def test_author_request_owns_optional_alternate_cost_and_source_motion_advisories():
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
    parent = {'name': 'opaque parent', 'useTime': 21, 'useAnimation': 25, 'shootSpeed': 6.1}
    request, user, _ = author.build_initial_author_request(parent, parent, {}, {}, 'r_advisory', model_name='offline-model')
    packet = json.loads(request['messages'][1]['content'])
    assert user == request['messages'][1]['content']
    header = packet['priorityHeader']
    assert any('alternate_use is optional' in line and 'purposeful' in line and 'not required to preserve' in line for line in header)
    assert any('source tempo and motion' in line and 'when available' in line and 'not an algorithm' in line and 'intentional' in line for line in header)
    assert any('use your knowledge' in line and 'verified source facts' in line for line in header), 'the model can choose physics creatively; source evidence must not become a blanket inference ban'
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm
    catalog = sharp_engine_fn_catalog_for_llm()
    cost = json.dumps(catalog)
    assert 'intended lifetime' in cost and 'whole generated item' in cost and 'does not refund' in cost
    assert packet['parents']['A']['packet'] == raw_parent_card_for_llm(parent)
    assert packet['parents']['B']['packet'] == raw_parent_card_for_llm(parent)


def test_unknown_sprite_reference_never_comes_from_collider_dump_or_fallback(monkeypatch, tmp_path):
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.core.runtime_authoring import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    _cache(monkeypatch, tmp_path)
    parent = {'name': 'unknown loaded texture', 'width': 91, 'height': 7,
        'textureMetrics': {'width': 91, 'height': 7},
        'spriteReferenceRaw': {'source': 'fallback_texture', 'textureWidthPx': 91, 'textureHeightPx': 7}}
    data = compile_runtime_program(build_runtime_fixture('workbench_blade'))
    data['recipeKey'] = 'r_unknown_texture'
    class CaptureComplete(BaseException):
        pass
    def stop(*args, **kwargs):
        raise CaptureComplete()
    monkeypatch.setattr(visual, 'llm_chat_json', stop)
    monkeypatch.setattr(visual, 'resolve_llm_model', lambda: 'offline-model')
    for repair in (False, True):
        kwargs = {'repair_errors': [], 'previous': {'item': {}}, 'repair_scope': {}} if repair else {}
        with pytest.raises(CaptureComplete):
            visual._request_visual_kit(data, parent, parent, {}, {}, **kwargs)
    paths = list((tmp_path / 'stage_requests').glob('*.json'))
    assert len(paths) == 2
    for path in paths:
        artifact = json.loads(path.read_bytes())
        packet = json.loads(artifact['messages'][1]['content'])
        parents = packet['parentFactsReadOnly' if artifact['stage'] == 'visual_repair' else 'parents']
        for row in parents.values():
            assert 'spriteReference' not in row['packet']['raw']
            assert 'textureMetrics' not in row['packet']['raw']
