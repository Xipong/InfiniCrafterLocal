"""Advisory design/debug output cannot own executable admission or Repair."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines.gameplay_stage import compile_and_validate_authored_runtime
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from repair_test_helpers import offline_builder


def _run_stage(_name, function, *args, **kwargs):
    return function(*args, **kwargs)


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('case,value', [
    ('missing', None), ('legacy', None), ('text', 'An experimental design; not runtime evidence.'),
    ('null', None), ('boolean', True), ('number', 17), ('list', ['debug', 2]),
    ('malformed-object', {'description': [1], 'unexpected': False}),
])
def test_advisory_shapes_survive_real_author_and_gameplay_without_repair(monkeypatch, mode, case, value):
    source = build_runtime_fixture('workbench_blade')
    expected = compile_runtime_program(source)
    if case == 'missing':
        source.pop('concept', None)
        source.pop('realization', None)
    elif case != 'legacy':
        source.update(concept=deepcopy(value), realization=deepcopy(value))
    before = deepcopy(source)
    requests = []

    def respond(request, **_kwargs):
        requests.append(deepcopy(request))
        assert len(requests) == 1, 'Advisory data must not trigger Format or Gameplay Repair'
        return {'choices': [{'message': {'content': json.dumps(source)}}],
                '_debug': {'responseFormatType': mode}}

    offline_builder(monkeypatch, mode, respond)
    accepted = author.try_llm_plan({}, {}, 'advisory-only')
    assert accepted is not None
    delivered = compile_and_validate_authored_runtime(accepted, {}, {}, 'advisory-only', run_stage=_run_stage)
    assert len(requests) == 1
    for field in ('runtimeProgram', 'gameplay', 'accessory', 'armor'):
        assert delivered[field] == expected[field]
    for field in ('concept', 'realization'):
        if case == 'missing':
            assert field not in delivered
        elif case == 'null' and mode == 'json_schema' and field not in delivered:
            pass  # Declared nullable optional transport wrapper means omission.
        else:
            assert delivered[field] == before[field]
    assert source == before


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_runtime_defect_still_repairs_with_malformed_advisory_patch(monkeypatch, mode):
    source = build_runtime_fixture('workbench_blade')
    source.update(concept=['raw debug'], realization='unstructured post-program report')
    expected = compile_runtime_program(source)
    stats = next(row for row in source['runtimeProgram']['calls'] if row['fn'] == 'configure_item_stats')
    correction = deepcopy(stats)
    stats['params']['damage'] = True  # bool is not an authored integer.
    responses = [source, {'note': 'Correct only damage type', 'callsUpsert': [correction],
                          'metadataPatch': {'concept': ['malformed but advisory']},
                          'realizationReplacement': ['raw optional debug']}]
    requests = []

    def respond(request, **_kwargs):
        requests.append(deepcopy(request))
        assert responses, 'Only one conditional Gameplay Repair is allowed'
        return {'choices': [{'message': {'content': json.dumps(responses.pop(0))}}],
                '_debug': {'responseFormatType': mode}}

    offline_builder(monkeypatch, mode, respond)
    accepted = author.try_llm_plan({}, {}, 'executable-defect')
    delivered = compile_and_validate_authored_runtime(accepted, {}, {}, 'executable-defect', run_stage=_run_stage)
    assert len(requests) == 2 and not responses
    assert delivered['runtimeProgram'] == expected['runtimeProgram']
    assert delivered['gameplay'] == expected['gameplay']
    audit = delivered['debug']['gameplayRepairFilterAudit']
    assert audit['ok']
    assert '$.callsUpsert[0].params.damage' in audit['acceptedPaths']
    assert delivered['concept'] == ['raw debug'], 'Unrequested concept remains frozen'
    assert delivered['realization'] == ['raw optional debug']


@pytest.mark.parametrize('value', ['debug text', [1], True, 17, None])
def test_development_visual_accepts_nonobject_realization(monkeypatch, value):
    source = build_runtime_fixture('workbench_blade')
    source['realization'] = deepcopy(value)
    compiled = compile_runtime_program(source)
    before = deepcopy(compiled)
    monkeypatch.setattr(visual, 'USE_LLM', False)
    projected = visual.apply_visual_director(compiled, {}, {})
    gameplay = deepcopy(projected['runtimeProgram'])
    for entity in gameplay['entities']:
        entity.pop('visual', None)
    original_gameplay = deepcopy(before['runtimeProgram'])
    for entity in original_gameplay['entities']:
        entity.pop('visual', None)
    assert gameplay == original_gameplay
    assert compiled['runtimeProgram'] == before['runtimeProgram']
    assert projected['realization'] == value
    assert projected['visualKit']['item']['visualIdentity']


def test_format_repair_preserves_string_reports_through_actual_strict_schema(monkeypatch):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture

    source = build_runtime_fixture('workbench_blade')
    source['concept'] = '  Идея 🌟\nA design hypothesis, not an execution claim.  '
    source['realization'] = '  Реализация\r\nOnly the authored events execute.  '
    before = deepcopy(source)
    malformed = json.dumps(source, ensure_ascii=False)[:-1] + ',}'
    requests = []

    def respond(request, **_kwargs):
        requests.append(deepcopy(request))
        assert len(requests) <= 2
        if len(requests) == 1:
            content = malformed
        else:
            # Encode ordinary runtime optionals independently, leaving the exact
            # new string reports intact; validate against the actual sent schema.
            encoded = _encode_nullable_fixture(source, author_item_response_schema())
            schema = request['response_format']['json_schema']['schema']
            Draft202012Validator(schema).validate(encoded)
            content = json.dumps(encoded, ensure_ascii=False)
        return {'choices': [{'message': {'content': content}}],
                '_debug': {'responseFormatType': 'json_schema'}}

    offline_builder(monkeypatch, 'json_schema', respond)
    accepted = author.try_llm_plan({}, {}, 'syntax-only-reports')
    assert accepted is not None
    delivered = compile_and_validate_authored_runtime(accepted, {}, {}, 'syntax-only-reports', run_stage=_run_stage)
    assert len(requests) == 2
    assert delivered['concept'] == before['concept']
    assert delivered['realization'] == before['realization']
    assert delivered['runtimeProgram'] == compile_runtime_program(before)['runtimeProgram']
    assert source == before


def test_whole_input_work_guard_still_refuses_excessively_deep_advisory_json():
    source = build_runtime_fixture('workbench_blade')
    nested = 'debug'
    for _ in range(50):
        nested = [nested]
    source['realization'] = nested
    with pytest.raises(RuntimeError, match=r'Author input exceeds schema-derived work bounds at \$\.realization'):
        author._prepare_parsed_author_item(source)


def test_string_report_reaches_generated_parent_summary_and_vfx_description():
    from infini_local.core.vfx_manifest import _prompt_packet
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data

    source = build_runtime_fixture('workbench_blade')
    source['id'] = 'advisory_handoff_fixture'
    source['concept'] = '  Initial design idea 🌟  '
    source['realization'] = '  Accepted mechanism description\r\nwith literal spacing.  '
    compiled = compile_runtime_program(source)
    before = deepcopy(compiled)
    summary = generated_parent_summary_from_data(compiled)
    packet = _prompt_packet(compiled, {}, {})
    assert summary['description'] == source['realization'].strip()
    assert packet['item']['description'] == source['realization']
    assert compiled == before
    assert compiled['concept'] == source['concept']


@pytest.mark.parametrize('field', ['concept', 'realization'])
@pytest.mark.parametrize('transport', ['exact', 'json_object', 'not-required', 'reversed-wrapper', 'altered-string'])
def test_initial_report_null_inversion_requires_exact_sent_transport(monkeypatch, field, transport):
    from infini_local.core import llm_config
    from infini_local.pipelines.author_item_contract import project_provider_author_item_to_local

    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', 'json_schema')
    request, _, _ = author.build_initial_author_request({}, {}, 'report-null', model_name='offline')
    response_format = deepcopy(request['response_format'])
    schema = response_format['json_schema']['schema']
    assert schema['properties'][field]['anyOf'][1] == {'type': 'null'}
    assert field in schema['required']
    if transport == 'json_object':
        response_format = {'type': 'json_object'}
    elif transport == 'not-required':
        schema['required'].remove(field)
    elif transport == 'reversed-wrapper':
        schema['properties'][field]['anyOf'].reverse()
    elif transport == 'altered-string':
        child = schema['properties'][field]['anyOf'][0]
        if field == 'concept':
            child['maxLength'] = 100
        else:
            child['properties']['description']['anyOf'][0]['maxLength'] = 100
    source = build_runtime_fixture('workbench_blade')
    source[field] = None
    before = deepcopy(source)
    result = project_provider_author_item_to_local(source, response_format=response_format)
    expected = deepcopy(source)
    if transport == 'exact':
        expected.pop(field)
    assert result == expected
    assert source == before


def test_plain_design_notes_reach_actual_visual_packet_without_mechanical_changes(monkeypatch):
    from prompt_packet_helpers import request_dossier

    source = build_runtime_fixture('workbench_blade')
    source['concept'] = '  Free-form initial concept 🌟  '
    source['realization'] = '  What the emitted program implements.\n  '
    compiled = compile_runtime_program(source)
    control = deepcopy(compiled)
    control.pop('concept')
    control.pop('realization')
    before = deepcopy(compiled)
    requests = []

    def respond(request, **_kwargs):
        requests.append(deepcopy(request))
        return {'choices': [{'message': {'content': '{}'}}]}

    offline_builder(monkeypatch, 'json_object', respond)
    monkeypatch.setattr(visual, 'llm_chat_json', respond)
    monkeypatch.setattr(visual, 'resolve_llm_model', lambda: 'offline')
    monkeypatch.setattr(visual, 'trace_event', lambda *args, **kwargs: None)
    monkeypatch.setattr(visual, 'trace_stage_request', lambda *args, **kwargs: None)
    visual._request_visual_kit(compiled, {}, {})
    visual._request_visual_kit(control, {}, {})
    packet, baseline = map(request_dossier, requests)
    assert packet['item']['concept'] == source['concept']
    assert packet['item']['realization'] == source['realization']
    assert 'literalSynthesis' not in packet['item']
    assert {key: value for key, value in packet.items() if key != 'item'} == {
        key: value for key, value in baseline.items() if key != 'item'}
    assert compiled == before


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_separate_player_description_and_full_debug_through_real_handoffs(monkeypatch, mode):
    from infini_local.core.vfx_manifest import _prompt_packet
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    source = build_runtime_fixture('workbench_blade')
    source['id'] = 'separate_advisory_fixture'
    source['concept'] = 'Throw a blade, with an intended dash.'
    source['realization'] = {
        'description': 'Use: throw the blade; it returns after hitting.',
        'selfEvaluation': ('DEBUG: intended dash is absent. 🌟\r\n' * 3000),
    }
    before = deepcopy(source)
    requests = []

    def respond(request, **_kwargs):
        requests.append(request)
        assert len(requests) == 1, 'Long debug is not a gameplay defect'
        return {'choices': [{'message': {'content': json.dumps(source)}}],
                '_debug': {'responseFormatType': mode}}

    offline_builder(monkeypatch, mode, respond)
    accepted = author.try_llm_plan({}, {}, 'separate-advisory')
    delivered = compile_and_validate_authored_runtime(accepted, {}, {}, 'separate-advisory', run_stage=_run_stage)
    delivered['generatedParentSummary'] = generated_parent_summary_from_data(delivered)
    summary = delivered['generatedParentSummary']
    vfx = _prompt_packet(delivered, {}, {})
    parent = raw_parent_card_for_llm({'generatedData': delivered})
    assert summary['description'] == before['realization']['description']
    assert summary['playerExperience'] == ''  # Notes falls back to description.
    assert vfx['item']['description'] == summary['description']
    assert parent['raw']['generatedParent']['summary']['description'] == summary['description']
    assert 'DEBUG:' not in json.dumps(summary)
    assert 'DEBUG:' not in json.dumps(vfx)
    assert 'DEBUG:' not in json.dumps(parent)
    assert delivered['realization'] == before['realization']
    assert delivered['concept'] == before['concept']
    assert source == before


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
@pytest.mark.parametrize('length', [0, 4001, 5500, 100000])
def test_format_repair_preserves_separated_notes_without_promoting_debug(monkeypatch, mode, length):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture

    source = build_runtime_fixture('workbench_blade')
    source['concept'] = '  A brief idea 🌟  '
    source['realization'] = {'description': '  Use the blade.\r\n', 'selfEvaluation': '  Dash is not implemented.  ' + 'д' * length}
    before = deepcopy(source)
    responses = []

    def respond(request, **_kwargs):
        responses.append(request)
        assert len(responses) <= 2
        if len(responses) == 1:
            content = json.dumps(source)[:-1] + ',}'
        else:
            encoded = _encode_nullable_fixture(source, author_item_response_schema()) if mode == 'json_schema' else source
            if mode == 'json_schema':
                Draft202012Validator(request['response_format']['json_schema']['schema']).validate(encoded)
            content = json.dumps(encoded)
        return {'choices': [{'message': {'content': content}}], '_debug': {'responseFormatType': mode}}

    offline_builder(monkeypatch, mode, respond)
    accepted = author.try_llm_plan({}, {}, 'separate-syntax-repair')
    delivered = compile_and_validate_authored_runtime(accepted, {}, {}, 'separate-syntax-repair', run_stage=_run_stage)
    assert len(responses) == 2
    assert delivered['realization'] == before['realization']
    assert delivered['concept'] == before['concept']
    assert delivered['runtimeProgram'] == compile_runtime_program(before)['runtimeProgram']


@pytest.mark.parametrize('field,maximum', [('description', 4000), ('playerExperience', 3000)])
@pytest.mark.parametrize('extra', [0, 1, 1500, 96000])
def test_summary_matches_native_unicode_bound_without_touching_raw(field, maximum, extra):
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    text = 'ж' * (maximum - 1) + '🌟' + 'TAIL' * extra
    source = compile_runtime_program(build_runtime_fixture('workbench_blade'))
    source['id'] = 'unicode_summary'
    source['realization'] = {field: '\u0085\u00a0  ' + text + ' \r\n', 'selfEvaluation': 'Full debug is separate.'}
    before = deepcopy(source)
    summary = generated_parent_summary_from_data(source)
    assert summary[field] == text[:maximum]
    assert len(summary[field]) == maximum
    source['generatedParentSummary'] = summary
    parent = raw_parent_card_for_llm({'generatedData': source})
    assert parent['raw']['generatedParent']['summary'][field] == text[:maximum]
    assert source['realization'] == before['realization']


def test_summary_unicode_scalars_and_dotnet_trim_edge_cases():
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data

    source = {'id': 'unicode_edges', 'realization': {'description': '\x1c\ud83c\udf1f\ud800\x1c'}}
    before = deepcopy(source)
    assert generated_parent_summary_from_data(source)['description'] == '\x1c🌟\ufffd\x1c'
    assert source == before


def test_fresh_strict_transport_decodes_only_declared_optional_report_fields(monkeypatch):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture

    source = build_runtime_fixture('workbench_blade')
    source['concept'] = 'A short idea.'
    source['realization'] = {'selfEvaluation': 'No player description was supplied.'}

    def respond(request, **_kwargs):
        encoded = _encode_nullable_fixture(source, author_item_response_schema())
        encoded['realization'].pop('playerExperience')
        assert encoded['realization']['description'] is None
        Draft202012Validator(request['response_format']['json_schema']['schema']).validate(encoded)
        return {'choices': [{'message': {'content': json.dumps(encoded)}}],
                '_debug': {'responseFormatType': 'json_schema'}}

    offline_builder(monkeypatch, 'json_schema', respond)
    accepted = author.try_llm_plan({}, {}, 'fresh-report-nullable')
    assert accepted['realization'] == source['realization']
    assert accepted['concept'] == source['concept']
