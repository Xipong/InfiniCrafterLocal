"""Verify complete animation vocabulary reaches the production serialized Author request."""

import json

from infini_local.core.runtime_authoring.terraria_vocabulary import (
    ITEM_USE_STYLE_MEANINGS, ITEM_USE_STYLE_TMODLOADER_NAMES, ITEM_USE_STYLE_TOKENS,
)
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_LIMIT_CHARS, PLANNER_PROMPT_MIN_HEADROOM_CHARS,
)


def test_serialized_item_use_style_guide_covers_exact_enum_and_no_mechanics(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    parent_a = {"id": "blade", "name": "Blade", "damage": 7, "useTime": 20}
    parent_b = {"id": "bench", "name": "Workbench", "createTile": 18, "useTime": 15}
    request, user_content, _ = build_initial_author_request(
        parent_a, parent_b, parent_a, parent_b, "blade+bench", model_name="gemini-2.5-flash",
    )
    assert request["messages"][1]["content"] == user_content
    assert request["response_format"] == {"type": "json_object"}
    assert len(user_content) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    payload = json.loads(user_content)
    guide = payload["runtimeProgramInvariants"]["itemUseStyle"]
    card = next(row for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]
                if row["fn"] == "configure_item_use")
    assert guide["builtInTokens"] == list(ITEM_USE_STYLE_TOKENS)
    assert set(guide["meaningByToken"]) == set(card["params"]["useStyle"]["enum"])
    assert set(guide["meaningByToken"]) == set(ITEM_USE_STYLE_TOKENS) == set(ITEM_USE_STYLE_TMODLOADER_NAMES)
    assert guide["meaningByToken"] == dict(ITEM_USE_STYLE_MEANINGS)
    assert all(text.strip().endswith(".") for text in guide["meaningByToken"].values())
    meanings = guide["meaningByToken"]
    assert "horizontally" in meanings["thrust"] and "any angle" in meanings["rapier"]
    assert "early" in meanings["drink_long"] and "front arm" in meanings["drink_liquid"]
    assert "off hand" in meanings["raise_lamp"] and "animation" in meanings["hidden_animation"]
    assert "cursor" in meanings["shoot"] and "golf club" in meanings["golf_play"]
    assert all(term in guide["scope"] for term in (
        "configure_item_use.useStyle", "animation", "during active use only",
        "does not independently guarantee a functional tool/use mechanic",
        "input binding", "executable capabilities/effects separately", "not weapon presets",
    ))
    assert "meaningByToken" in payload["runtimeProgramInvariants"]["damageClass"]
