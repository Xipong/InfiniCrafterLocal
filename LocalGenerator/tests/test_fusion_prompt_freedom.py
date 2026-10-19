
from prompt_packet_helpers import request_dossier, dossier_text
"""Creative freedom is prose-only; inspect actual Author/Repair messages offline."""
from copy import deepcopy
import json

import pytest

from infini_local.core import llm_config
from infini_local.pipelines import llm_authoring_pipeline as author


@pytest.mark.parametrize('mode', ['json_object', 'json_schema', 'off'])
def test_actual_author_scopes_provenance_to_parent_claims_not_invented_mechanics(monkeypatch, mode):
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    request, user, _ = author.build_initial_author_request({}, {}, 'fusion', model_name='offline')
    assert dossier_text(request) == user
    header = ' '.join(json.loads(user)['priorityHeader'])
    assert 'Source provenance constrains factual claims about the parents, not the mechanics you may invent' in header
    assert 'new purposeful mechanics from catalog primitives inspired by both parent identities' in header
    assert 'neither parent needs to have performed them' in header
    assert 'Do not present invented effects as observed parent abilities' in header
    assert 'use source-backed parent facts only to author' not in user
    assert 'No forced twist or unrelated gimmick is required' in header
    assert 'Do not add a mandatory weird twist' not in user


@pytest.mark.parametrize('mode', ['json_object', 'json_schema', 'off'])
def test_actual_author_does_not_turn_coherence_or_source_units_into_inheritance_rules(monkeypatch, mode):
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    request, user, _ = author.build_initial_author_request({'name': 'A', 'damage': 0}, {'name': 'B'}, 'coherence', model_name='offline')
    packet = request_dossier(request)
    assert user == dossier_text(request)
    assert [row["role"] for row in request["messages"]] == ["system", "developer", "user"]
    concept = packet['requiredJsonShape']['concept']
    assert 'not a single-loop rule' in concept['coreMechanic']
    assert 'multiple complementary actions' in concept['coreMechanic']
    assert 'do not invent an acquisition tier' in concept['coreMechanic']
    assert 'one clear core gameplay loop' not in user
    for field in ('parentAContribution', 'parentBContribution'):
        assert 'newly invented rather than inherited' in concept[field]
        assert 'appearance/identity' in concept[field]
        assert 'copying every parent capability is not required' in concept[field]
    assert 'does not require an inherited ability for each new mechanic' in packet['sourceWireUnits']['readingRule']
    assert 'rebalance choices' not in packet['sourceWireUnits']['readingRule']
    assert 'not proof of acquisition tier or expected power' in packet['balanceCorridor']['rule']


@pytest.mark.parametrize('mode', ['json_object', 'json_schema', 'off'])
def test_actual_shared_repair_report_is_an_account_not_a_design_rejection(monkeypatch, mode):
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness

    source = build_capability_witness('configure_item_stats')
    call = next(row for row in source['runtimeProgram']['calls'] if row['fn'] == 'configure_item_stats')
    call['params']['damage'] = True
    before = deepcopy(source)
    requests = []

    class Captured(BaseException):
        pass

    def capture(request, **kwargs):
        requests.append(deepcopy(request))
        raise Captured()

    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    for name, value in dict(USE_LLM=True, resolve_llm_model=lambda: 'offline', llm_chat_json=capture,
                           trace_event=lambda *a, **k: None, trace_stage_request=lambda *a, **k: None,
                           llm_reasoning_system_suffix=lambda *a, **k: '',
                           apply_llm_common_options=lambda request, **kwargs: request).items():
        monkeypatch.setattr(author, name, value)
    with pytest.raises(Captured):
        author.repair_author_item_after_failure(source, {}, {}, 'report', failure_report=validate_runtime_program(source))
    assert source == before and len(requests) == 1
    packet = request_dossier(requests[0])
    truth = packet['runtimeExecutionTruth']
    assert 'Account for the chosen inputs' in truth['authority']
    assert 'Walk every' not in truth['authority']
    assert 'A newly invented mechanic needs executable support, not parent precedent' in truth['authority']
    assert 'Optional advisory' in truth['selfEvaluation']
    assert 'No checklist' in truth['selfEvaluation']
    assert packet['repairScope']['fieldPermissions']['calls'] == [{'id': call['id'], 'paths': ['params.damage']}]
    assert packet['acceptedItemContext']['runtimeProgram'] == before['runtimeProgram']
    assert packet['acceptedItemContext']['concept'] == before['concept']
    assert 'keep every frozen value and absence unchanged' in ' '.join(packet['rules'])
    _, user, _ = author.build_initial_author_request({}, {}, 'report', model_name='offline')
    assert json.loads(user)['diagnosticReport']['selfEvaluation'] == truth['selfEvaluation']


@pytest.mark.parametrize('mode', ['json_object', 'json_schema', 'off'])
def test_actual_periodic_producer_guidance_discloses_exhaustion_without_forcing_pool(monkeypatch, mode):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.qa.capability_witnesses import build_capability_witness
    from test_author_prompt_consistency import _stationary_periodic_shooter

    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    _, user, _ = author.build_initial_author_request({}, {}, 'producer', model_name='offline')
    packet = json.loads(user)
    catalog = packet['runtimeCapabilityContract']['catalog']
    budget = catalog['fieldGuide']['descendantSpawnBudget']
    for phrase in ('32-successful-child-spawn lifetime allowance', 'Child death does not refund',
                   'producer remains alive', 'Failed or cancelled reservations are refunded',
                   'optional', 'nested pool', 'ancestor lifetime ledger',
                   'Intentionally finite producers remain valid', 'not guaranteed successful shots'):
        assert phrase in budget
    for fn in ('target_and_fire', 'spawn_entity_on_event'):
        card = next(row for row in catalog['capabilities'] if row['fn'] == fn)
        assert 'fieldGuide.descendantSpawnBudget' in card['constructionMeaning']
        assert 'do not guarantee sustained output' in card['constructionMeaning']
    # No design requirement or semantic router: both finite and replenishable designs execute unchanged.
    for pool in (None, 3):
        doc, root, child = _stationary_periodic_shooter(pool)
        assert validate_runtime_program(doc)['ok']
        assert validate_runtime_wire(compile_runtime_program(doc))['ok']
    doc = build_capability_witness('target_and_fire')
    assert not any(row['fn'] == 'set_descendant_concurrency' for row in doc['runtimeProgram']['calls'])
    next(row for row in doc['runtimeProgram']['calls'] if row['fn'] == 'set_projectile_damage')['params']['damage'] = True
    requests = []
    class Captured(BaseException):
        pass
    def capture(request, **kwargs):
        requests.append(deepcopy(request))
        raise Captured()
    for name, value in dict(USE_LLM=True, resolve_llm_model=lambda: 'offline', llm_chat_json=capture,
                           trace_event=lambda *a, **k: None, trace_stage_request=lambda *a, **k: None,
                           llm_reasoning_system_suffix=lambda *a, **k: '',
                           apply_llm_common_options=lambda request, **kwargs: request).items():
        monkeypatch.setattr(author, name, value)
    with pytest.raises(Captured):
        author.repair_author_item_after_failure(doc, {}, {}, 'producer', failure_report=validate_runtime_program(doc))
    repair = request_dossier(requests[0])
    assert repair['runtimeExecutionTruth']['units']['descendantSpawnBudget'] == budget
    assert repair['acceptedItemContext']['runtimeProgram'] == doc['runtimeProgram']
    assert 'set_descendant_concurrency' not in json.dumps(repair['repairScope'])
