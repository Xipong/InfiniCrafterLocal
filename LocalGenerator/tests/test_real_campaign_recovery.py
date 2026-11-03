from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from toolbox.live.budget import budget_status, initialize_budget
from toolbox.live.options import build_parser
from toolbox.live.preflight import prepare
from toolbox.live.real_run import PhysicalAccounting, _ACTIVE_CASE, case_payload, execute_case


@pytest.fixture
def budget(tmp_path):
    path = tmp_path / 'budget.sqlite'
    initialize_budget(path, ceiling=140, opening_debit=51, opening_note='reconstructed historical opening')
    return path


def test_case_identity_independent_of_subset_order():
    parents = ({'internalName': 'A'}, {'internalName': 'B'})
    ordered = {name: case_payload(name, *parents) for name in ('one', 'two')}
    reversed_cases = {name: case_payload(name, *parents) for name in ('two', 'one')}
    assert ordered == reversed_cases
    assert ordered['one'] == case_payload('one', *parents)
    assert ordered['one']['worldId'] != ordered['two']['worldId']


def emit(observer, call, endpoint, outcome='success'):
    for event in ('request', 'post_start', 'attempt_end', 'call_end'):
        observer({'event': event, 'transportCallId': call, 'endpoint': endpoint,
                  'outcome': outcome, 'authorization': 'NEVER_LOG', 'raw': 'NEVER_LOG'})


def test_real_attempt_reserves_before_pipeline_and_keeps_delivery_roster(tmp_path, budget):
    observer_holder = {}
    @contextmanager
    def observations(join, observer):
        observer_holder['observe'] = observer
        yield
    delivered = {'recipeMeta': {'assetFiles': ['real.png']}, 'visual': {'spritePath': 'real.png'}}
    def pipeline(payload):
        assert budget_status(budget)['charged'] == 52
        state = _ACTIVE_CASE.get()
        for index, stage in enumerate(('initial_author', 'visual_director', 'vfx_director')):
            state['logical'].append({'event': 'request', 'stage': stage})
            emit(observer_holder['observe'], str(index), 'https://chatgpt.com/backend-api/codex/responses')
        emit(observer_holder['observe'], 'img', 'https://chatgpt.com/backend-api/codex/images/generations')
        return delivered
    receipt = execute_case('test_case', {}, {}, output=tmp_path, budget_path=budget,
                           combine_call=pipeline, observation_scope=observations)
    assert receipt['ok'] and receipt['physicalImagePosts'] == 1 and receipt['physicalTextPosts'] == 3
    assert json.loads((tmp_path / 'cases/test_case/final_item.json').read_text()) == delivered
    assert 'NEVER_LOG' not in (tmp_path / 'cases/test_case/physical.ndjson').read_text()
    assert budget_status(budget)['active'] == 0
    assert budget_status(budget)['charged'] == 52
    with pytest.raises(FileExistsError):
        execute_case('test_case', {}, {}, output=tmp_path, budget_path=budget,
                     combine_call=pipeline, observation_scope=observations)
    assert budget_status(budget)['charged'] == 52


def test_failure_still_charged_and_unfinished_calls_honest(tmp_path, budget):
    @contextmanager
    def observations(join, observer):
        observer({'event': 'request', 'transportCallId': 'lost'})
        observer({'event': 'post_start', 'transportCallId': 'lost', 'endpoint': 'https://chatgpt.com/backend-api/codex/responses'})
        yield
    def broken(_):
        raise RuntimeError('potential sensitive provider message')
    receipt = execute_case('broken', {}, {}, output=tmp_path, budget_path=budget,
                           combine_call=broken, observation_scope=observations)
    assert not receipt['ok'] and receipt['unfinishedCalls'] == ['lost']
    assert receipt['physicalTextPosts'] == 1 and receipt['errorType'] == 'RuntimeError'
    assert budget_status(budget)['charged'] == 52
    assert 'sensitive' not in (tmp_path / 'cases/broken/receipt.json').read_text()


def test_missing_boundary_observations_never_pass(tmp_path, budget):
    @contextmanager
    def observations(*_):
        yield
    receipt = execute_case('silent', {}, {}, output=tmp_path, budget_path=budget,
                           combine_call=lambda _: {'id': 'cache'}, observation_scope=observations)
    assert not receipt['ok']
    assert not receipt['requiredStagesObserved']


def test_observer_write_loss_fails_closed(tmp_path):
    observer = PhysicalAccounting(tmp_path / 'missing' / 'events.ndjson')
    observer.observe({'event': 'post_start', 'transportCallId': 'a'})
    assert observer.summary()['observationWriteFailed']


def test_options_keep_legacy_default_and_explicit_unavailable_modes():
    args = build_parser(internal=True).parse_args([])
    assert not args.real_images and args.attempt_budget is None
    assert args.reuse_images_from is None and args.vfx_only_from is None
    args.reuse_images_from = Path('old')
    with pytest.raises(ValueError, match='does not yet support'):
        prepare(args)


def test_canonical_transport_observer_counts_actual_send_boundary(tmp_path, monkeypatch):
    from urllib.request import Request
    from infini_local.services import codex_auth
    import time
    observed = PhysicalAccounting(tmp_path / 'physical.ndjson')
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def open_fake(req, *, deadline, on_open):
        on_open()
        return Response()
    monkeypatch.setattr(codex_auth, 'urlopen_no_redirect', open_fake)
    req = Request('https://chatgpt.com/backend-api/codex/images/generations', data=b'{}', method='POST')
    with codex_auth.generation_observations({}, observed.observe):
        result = codex_auth._generation_request(req, deadline=time.monotonic() + 5, attempts=1,
            payload={}, headers={'Authorization': 'Bearer SECRET'}, read_response=lambda _: b'{}')
    assert result == b'{}'
    report = observed.summary()
    assert report['physicalImagePosts'] == 1 and report['unfinishedCalls'] == []
    assert report['failedAttempts'] == 0 and 'SECRET' not in observed.path.read_text()


def real_args(tmp_path, budget):
    project = tmp_path / 'project'
    (project / 'LocalGenerator/infini_local').mkdir(parents=True)
    (project / '.git').mkdir()
    cases = tmp_path / 'cases.json'
    cases.write_text(json.dumps([{'case': 'control', 'itemA': 'A', 'itemB': 'B'}]))
    parents = tmp_path / 'parents.jsonl'
    parents.write_text('{"internalName":"A"}\n{"internalName":"B"}\n')
    return build_parser(internal=True).parse_args([
        '--run', '--real-images', '--parallel-crafts', '1', '--project', str(project),
        '--output', str(tmp_path / 'new-output'), '--cases-file', str(cases), '--runtime-dump', str(parents),
        '--attempt-budget', str(budget), '--expected-head', 'test-head',
        '--expected-provider', 'openai_codex', '--expected-model', 'terra-test',
        '--expected-base-url', 'https://chatgpt.com/backend-api/codex/', '--expected-api-mode', 'responses',
        '--expected-response-format', 'json_object', '--expected-temperature', '0.7',
        '--expected-vfx-temperature', '0.7', '--expected-repair-temperature', '0.2',
        '--expected-max-tokens', '100', '--expected-visual-max-tokens', '100', '--expected-vfx-max-tokens', '100',
        '--expected-reasoning-effort', 'high', '--expected-image-model', 'gpt-image-2',
        '--expected-image-quality', 'medium', '--expected-image-size', '1024x1024',
    ])


@pytest.mark.parametrize('git_state', ['clean', 'missing', 'wrong_head', 'dirty'])
def test_real_preflight_settings_and_existing_budget_are_read_only(tmp_path, budget, monkeypatch, git_state):
    from toolbox.live import preflight
    env = {'INFINI_LLM_PROVIDER': 'openai_codex', 'INFINI_CODEX_LLM_MODEL': 'terra-test',
           'INFINI_LLM_API_MODE': 'responses', 'INFINI_LLM_RESPONSE_FORMAT': 'json_object',
           'INFINI_USE_LLM': '1', 'INFINI_IMAGE_BACKEND': 'openai_codex',
           'INFINI_LLM_FALLBACK_NETWORK_FAILS': '1', 'INFINI_SPRITE_RETRIES': '0'}
    monkeypatch.setattr(preflight, 'read_environment', lambda *_: env)
    commands = []
    def git_output(command, **_):
        commands.append(command)
        if 'rev-parse' in command:
            return 'other-head\n' if git_state == 'wrong_head' else 'test-head\n'
        return ' M source.py\n' if git_state == 'dirty' else ''
    monkeypatch.setattr(preflight.subprocess, 'check_output', git_output)
    args = real_args(tmp_path, budget)
    if git_state == 'missing':
        (Path(args.project) / '.git').rmdir()
    if git_state != 'clean':
        match = 'clean project worktree' if git_state == 'dirty' else 'HEAD does not match'
        with pytest.raises(ValueError, match=match):
            prepare(args)
        assert not args.output.exists() and budget_status(budget)['charged'] == 51
        assert len(commands) == (0 if git_state == 'missing' else 2)
        return
    report, _ = prepare(args)
    assert len(commands) == 2
    assert report['realImageGeneration'] and report['attemptBudget']['charged'] == 51
    assert report['configured']['model'] == 'terra-test'
    assert not args.output.exists() and budget_status(budget)['charged'] == 51
    for key, value, match in (
        ('INFINI_IMAGE_BACKEND', 'procedural', 'canonical Codex'),
        ('INFINI_CODEX_IMAGE_MODEL', 'other', 'image model'),
        ('INFINI_LLM_FALLBACK_NETWORK_FAILS', '2', 'hidden text retry'),
        ('INFINI_SPRITE_RETRIES', '2', 'image retries'),
    ):
        old = env.get(key)
        env[key] = value
        with pytest.raises(ValueError, match=match):
            prepare(args)
        if old is None: env.pop(key)
        else: env[key] = old


def test_actual_canonical_asset_projection_survives_attempt(tmp_path, budget):
    from infini_local.services.asset_sync_service import attach_asset_sync_meta
    @contextmanager
    def observations(*_): yield
    data = {'visual': {'spritePath': '/private/art/kept.png'}, 'recipeMeta': {}}
    def pipeline(_):
        return attach_asset_sync_meta(data, asset_public_base_url='http://localhost:1234/assets')
    execute_case('roster', {}, {}, output=tmp_path, budget_path=budget,
                 combine_call=pipeline, observation_scope=observations)
    saved = json.loads((tmp_path / 'cases/roster/final_item.json').read_text())
    assert 'kept.png' in saved['recipeMeta']['assetFiles']


def test_exact_native_input_preserves_context_and_rejects_changed_parents(tmp_path, budget):
    from toolbox.live.panels import load_case_input_payloads
    a, b = {'internalName': 'A'}, {'internalName': 'B'}
    native = {'itemA': a, 'itemB': b, 'worldId': 12, 'player': 'native',
              'craftInputPolicy': 'base_item_stats_ignore_prefixes', 'multiplayer': False}
    source = tmp_path / 'native.json'
    source.write_text(json.dumps(native))
    cases = tmp_path / 'cases.json'
    cases.write_text(json.dumps([{'case': 'exact', 'inputJson': 'native.json'}]))
    refs = load_case_input_payloads(cases, [('exact', a, b)])
    @contextmanager
    def observations(*_): yield
    outgoing = []
    execute_case('exact', a, b, output=tmp_path, budget_path=budget,
        combine_call=lambda payload: outgoing.append(payload) or {'id': 'control'},
        observation_scope=observations, exact_input=refs['exact'])
    assert outgoing == [native]
    assert (tmp_path / 'cases/exact/source_input.json').read_bytes() == source.read_bytes()
    assert json.loads((tmp_path / 'cases/exact/input.json').read_text()) == native
    with pytest.raises(ValueError, match='parents differ'):
        load_case_input_payloads(cases, [('exact', {'internalName': 'Other'}, b)])
    source.unlink()
    with pytest.raises(FileNotFoundError):
        load_case_input_payloads(cases, [('exact', a, b)])


def test_exact_input_change_after_admission_cannot_spend(tmp_path, budget):
    from toolbox.live.panels import load_case_input_payloads
    source = tmp_path / 'native.json'
    source.write_text('{"itemA":{},"itemB":{},"worldId":12}')
    cases = tmp_path / 'cases.json'
    cases.write_text('[{"case":"exact","inputJson":"native.json"}]')
    ref = load_case_input_payloads(cases, [('exact', {}, {})])['exact']
    source.write_text('{"itemA":{},"itemB":{},"worldId":13}')
    with pytest.raises(ValueError, match='changed after admission'):
        execute_case('exact', {}, {}, output=tmp_path, budget_path=budget,
                     combine_call=lambda _: pytest.fail('must not call'), observation_scope=None, exact_input=ref)
    assert budget_status(budget)['charged'] == 51


def test_logical_settings_guard_catches_conflicting_effort_and_wrong_stage():
    from toolbox.live.real_run import validate_logical_request
    args = SimpleNamespace(expected_model='model', expected_temperature=0.7,
        expected_repair_temperature=0.2, expected_vfx_temperature=0.8,
        expected_max_tokens=100, expected_visual_max_tokens=200, expected_vfx_max_tokens=300,
        expected_reasoning_effort='high', expected_response_format='json_object')
    payload = {'_infini_stage': 'planner', 'model': 'model', 'temperature': 0.7, 'max_tokens': 100,
               'reasoning_effort': 'high', 'response_format': {'type': 'json_object'}}
    assert validate_logical_request(payload, args) == 'initial_author'
    with pytest.raises(ValueError, match='reasoning effort'):
        validate_logical_request({**payload, 'reasoning': {'effort': 'low'}}, args)
    with pytest.raises(ValueError, match='unclassified'):
        validate_logical_request({**payload, '_infini_stage': 'unknown'}, args)


def test_projected_codex_settings_guard_detects_later_override():
    from toolbox.live.real_run import validate_projected_text_request
    args = SimpleNamespace(expected_model='model', expected_reasoning_effort='high',
                           expected_response_format='json_object')
    request = {'model': 'model', 'reasoning': {'effort': 'high'}, 'text': {'format': {'type': 'json_object'}}}
    url = 'https://chatgpt.com/backend-api/codex/responses'
    validate_projected_text_request(url, request, args)
    for changed in ({**request, 'reasoning': {}}, {**request, 'model': 'other'},
                    {**request, 'text': {'format': {'type': 'json_schema'}}}):
        with pytest.raises(ValueError, match='drift'):
            validate_projected_text_request(url, changed, args)
    with pytest.raises(ValueError, match='endpoint'):
        validate_projected_text_request('https://other.invalid/responses', request, args)


@pytest.mark.parametrize('retry_count', [0, 2])
def test_image_retry_setting_reaches_canonical_transport_policy(monkeypatch, retry_count):
    from infini_local.services import codex_auth
    monkeypatch.setenv('INFINI_SPRITE_RETRIES', str(retry_count))
    observed = []
    def fake_generation(req, **kwargs):
        observed.append(kwargs['attempts'])
        return b'{}'
    monkeypatch.setattr(codex_auth, '_generation_request', fake_generation)
    assert codex_auth.post_json('https://chatgpt.com/backend-api/codex/images/generations', {}) == {}
    assert observed == [retry_count + 1]


@pytest.mark.parametrize('require_zero', [False, True])
def test_required_zero_retries_is_enforced_not_silently_ignored(tmp_path, budget, require_zero):
    holder = {}
    @contextmanager
    def observations(join, observer):
        holder['observe'] = observer
        yield
    def pipeline(_):
        for index, stage in enumerate(('initial_author', 'visual_director', 'vfx_director')):
            _ACTIVE_CASE.get()['logical'].append({'event': 'request', 'stage': stage})
            emit(holder['observe'], str(index), 'https://chatgpt.com/backend-api/codex/responses')
        base = {'transportCallId': 'image', 'endpoint': 'https://chatgpt.com/backend-api/codex/images/generations'}
        holder['observe']({**base, 'event': 'request'})
        for index in (1, 2):
            holder['observe']({**base, 'event': 'post_start', 'physicalAttemptIndex': index,
                               'reason': 'initial' if index == 1 else 'transport_retry'})
            holder['observe']({**base, 'event': 'attempt_end', 'physicalAttemptIndex': index,
                               'outcome': 'failure' if index == 1 else 'success'})
        holder['observe']({**base, 'event': 'call_end', 'outcome': 'success'})
        return {'id': 'valid'}
    receipt = execute_case('retries', {}, {}, output=tmp_path, budget_path=budget,
        combine_call=pipeline, observation_scope=observations, require_zero_transport_retries=require_zero)
    assert receipt['transportRetryPosts'] == 1 and receipt['physicalImagePosts'] == 2
    assert receipt['ok'] is (not require_zero)
    assert budget_status(budget)['charged'] == 52


def test_call_completion_does_not_hide_unfinished_physical_attempt(tmp_path):
    observer = PhysicalAccounting(tmp_path / 'events.ndjson')
    for event in ('request', 'post_start', 'call_end'):
        observer.observe({'event': event, 'transportCallId': 'partial', 'physicalAttemptIndex': 1})
    assert observer.summary()['unfinishedCalls'] == []
    assert observer.summary()['unfinishedPhysicalAttempts'] == [['partial', 1]]
