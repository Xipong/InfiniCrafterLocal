from prompt_packet_helpers import request_dossier, dossier_text
"""Real builder admission, no provider calls or synthetic responses."""
import copy
import json

import pytest

from infini_local.pipelines import llm_transport
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.llm_authoring_prompt import PLANNER_PROMPT_LIMIT_CHARS


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_literal_source_tooltip_context_fits_without_clipping(monkeypatch, mode):
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    literal = "literal source context " + "Ж" * 1000
    source = {
        "id": 2322, "name": "Mining Potion", "sourceMod": "Terraria", "internalName": "MiningPotion",
        "fullName": "Terraria/MiningPotion", "damage": 0, "buffType": 104, "buffTime": 21600,
        "tooltipLines": [literal] * 12,
        "tooltipSource": {"source": "Lang.GetTooltip", "fullName": "Terraria/MiningPotion", "language": "ru-RU", "status": "observed_literal"},
    }
    before = copy.deepcopy(source)
    request, user, _ = build_initial_author_request(source, source, {}, {}, "headroom", model_name="offline")
    payload = json.loads(user)
    for label in ("A", "B"):
        assert payload["parents"][label]["packet"]["raw"]["item"]["tooltipLines"] == source["tooltipLines"]
    assert request_dossier(request) == payload
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) < PLANNER_PROMPT_LIMIT_CHARS
    assert source == before


def test_decimal_character_guard_accepts_exact_boundary_and_rejects_next_unicode_character(monkeypatch):
    from infini_local.pipelines import llm_authoring_prompt as prompt

    assert prompt.PLANNER_PROMPT_LIMIT_CHARS == 220_000
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    _, initial, _ = build_initial_author_request({}, {}, {}, {}, "", model_name="offline")
    key = "Ж" * (220_000 - len(initial))
    before = copy.deepcopy(key)
    request, text, _ = build_initial_author_request({}, {}, {}, {}, key, model_name="offline")
    assert len(text) == 220_000
    assert len(text.encode("utf-8")) > 220_000
    assert request_dossier(request)["recipeKey"] == key == before
    with pytest.raises(ValueError, match="220001 chars, above configured 220000"):
        build_initial_author_request({}, {}, {}, {}, key + "Ж", model_name="offline")


def test_oversize_author_payload_refuses_instead_of_clipping(monkeypatch):
    from infini_local.pipelines import llm_authoring_prompt as prompt
    monkeypatch.setattr(prompt, "PLANNER_PROMPT_LIMIT_CHARS", 10)
    with pytest.raises(ValueError, match="above configured 10"):
        build_initial_author_request({}, {}, {}, {}, "oversize", model_name="offline")
