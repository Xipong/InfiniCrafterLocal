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
    assert json.loads(request["messages"][1]["content"]) == payload
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) < PLANNER_PROMPT_LIMIT_CHARS
    assert source == before


def test_oversize_author_payload_refuses_instead_of_clipping(monkeypatch):
    from infini_local.pipelines import llm_authoring_prompt as prompt
    monkeypatch.setattr(prompt, "PLANNER_PROMPT_LIMIT_CHARS", 10)
    with pytest.raises(ValueError, match="above configured 10"):
        build_initial_author_request({}, {}, {}, {}, "oversize", model_name="offline")
