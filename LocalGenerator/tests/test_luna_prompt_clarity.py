
from prompt_packet_helpers import dossier_text
"""Cold-reader gaps and concise prose without reducing the executable language."""
import copy
import json
from infini_local.core import llm_config
from infini_local.pipelines import llm_authoring_pipeline as author


def packet(monkeypatch, a=None, b=None):
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', 'json_object')
    request, user, _ = author.build_initial_author_request(a or {}, b or {}, 'cold-clarity', model_name='test-model')
    assert dossier_text(request) == user
    return json.loads(user)


def test_noncombat_parent_timing_is_literal_not_hidden_combat_default(monkeypatch):
    a = {'name': 'fruit', 'damage': -1, 'useTime': 17}
    b = {'name': 'flower', 'damage': -1, 'useTime': 10}
    before = copy.deepcopy((a, b))
    corridor = packet(monkeypatch, a, b)['balanceCorridor']
    assert corridor['parentUseTimeTicks'] == [17, 10]
    assert 'suggested' not in corridor['broadEnvelope']['useTimeSeconds']
    assert (a, b) == before


def test_missing_parent_timing_stays_unknown(monkeypatch):
    corridor = packet(monkeypatch, {'name': 'unknown'}, {'name': 'known', 'useTime': 0})['balanceCorridor']
    assert corridor['parentUseTimeTicks'] == [None, 0]
