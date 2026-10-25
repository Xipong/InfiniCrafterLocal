"""Read-only ammunition observations must not select a child's design."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("envelope", ["root", "fingerprint"])
def test_native_required_ammo_category_reaches_actual_author_request(monkeypatch, format_mode, envelope):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', format_mode)
    facts = {"useAmmo": 283, "useAmmoCategoryName": "dart", "ammo": 0, "ammoCategoryName": ""}
    # Neutral identity ensures there is no name-based category interpretation.
    parent = {"name": "opaque source", **(facts if envelope == "root" else {envelope: facts})}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "ammo-information", model_name="offline-test-model")
    item = request_dossier(request)["parents"]["A"]["packet"]["raw"]["item"]
    assert item["useAmmoCategoryName"] == "dart"
    assert item["useAmmo"] == 283
    assert item["ammo"] == 0
    assert parent == before


def test_absent_category_remains_unknown_instead_of_being_decoded_from_id_or_name():
    parent = {"name": "Musket", "useAmmo": 97}
    assert "useAmmoCategoryName" not in raw_parent_card_for_llm(parent)["raw"]["item"]


@pytest.mark.parametrize("enabled", [False, True])
def test_literal_inventory_seed_drop_flag_is_source_context_not_implicit_child_behavior(enabled):
    parent = {"name": "opaque source", "dropSeedsIfInInventory": enabled}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "inventory-fact", model_name="offline-test-model")
    assert request_dossier(request)["parents"]["A"]["packet"]["raw"]["item"]["dropSeedsIfInInventory"] is enabled
    assert parent == before
    assert "dropSeedsIfInInventory" not in raw_parent_card_for_llm({"name": "Blowpipe"})["raw"]["item"]
