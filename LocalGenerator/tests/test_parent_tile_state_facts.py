"""Literal native tile state survives the real parent packet without becoming design."""
from __future__ import annotations

import copy
import pytest
from prompt_packet_helpers import request_dossier
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


NATIVE_STATE = {"tileId": 215, "placeStyle": 0, "selector": "top_left_frame_y",
                "onMin": 0, "onMax": 35, "offMin": 36, "offMax": 71,
                "provenance": "Terraria.Wiring.ToggleCampFire"}


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("envelope", ["root", "fingerprint"])
def test_native_frame_state_reaches_actual_author_request(monkeypatch, mode, envelope):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    fact = {"nativeTileState": copy.deepcopy(NATIVE_STATE)}
    parent = {"name": "opaque source", **(fact if envelope == "root" else {envelope: fact})}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "native-tile-state", model_name="offline-test-model")
    item = request_dossier(request)["parents"]["A"]["packet"]["raw"]["item"]
    assert item["nativeTileState"] == NATIVE_STATE
    assert item["nativeTileState"]["onMin"] == 0
    assert parent == before
    item["nativeTileState"]["onMax"] = 999
    assert parent == before


def test_missing_native_state_stays_unknown_even_with_a_familiar_name_or_tile():
    for parent in ({"name": "Campfire"}, {"name": "opaque", "createTile": 215, "placeStyle": 0}):
        assert "nativeTileState" not in raw_parent_card_for_llm(parent)["raw"]["item"]
