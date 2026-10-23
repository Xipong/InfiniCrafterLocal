"""Read-only ammunition observations must not select a child's design."""
from __future__ import annotations

import copy
import json

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


def test_real_author_packet_explains_ammo_identity_without_forcing_projectile_design():
    from infini_local.pipelines.author_item_contract import author_item_response_schema

    request, _, _ = build_initial_author_request({}, {}, "ammo-reading", model_name="offline-test-model")
    payload = request_dossier(request)
    card = next(row for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]
                if row["fn"] == "configure_weapon_ammo")
    text = json.dumps(card, ensure_ascii=False)
    assert "Seeds share the dart category" in text
    assert "does not select projectile appearance" in text
    assert "inventory-only" in text
    # This is comprehension guidance, not a new seed ammo category or forced design.
    assert author_item_response_schema()["required"] == ["name", "category", "runtimeProgram"]


def test_author_advisory_exposes_inheritance_tradeoffs_and_explicit_cost_scope():
    from infini_local.pipelines.author_item_contract import author_item_response_schema

    request, _, _ = build_initial_author_request({}, {}, "source-tradeoffs", model_name="offline-test-model")
    payload = request_dossier(request)
    guidance = payload["requiredJsonShape"]["concept"]["coreMechanic"]
    assert "Compare the resulting primary action" in guidance
    assert "manaCostInput" in guidance
    stats = next(card for card in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]
                 if card["fn"] == "configure_item_stats")
    scope = stats["params"]["manaCostInput"]
    # The actual model-facing contract offers each cost scope and explicitly
    # preserves old shared-cost semantics on omission; prose order is irrelevant.
    assert set(scope["enum"]) == {"primary_use", "alternate_use", "both"}
    assert scope["optional"] is True
    assert scope["default"] == scope["neutral"] == "both"
    assert "no mandatory upgrade or inheritance" in guidance
    assert "dropSeedsIfInInventory" in guidance
    assert "only by explicit collect_seeds_from_grass selection" in guidance
    assert "never mandatory inheritance" in guidance
    assert "concept" not in author_item_response_schema()["required"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_actual_author_cards_explain_spawn_axes_event_origin_and_independent_rotation(monkeypatch, format_mode):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', format_mode)
    request, _, _ = build_initial_author_request({}, {}, "emission-reading", model_name="offline-test-model")
    cards = {row["fn"]: row for row in request_dossier(request)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    spawn = json.dumps(cards["configure_spawn"], ensure_ascii=False)
    rotation = cards["set_projectile_rotation"]
    aim = cards["set_projectile_aim"]
    assert "move_yoyo_hover" not in cards
    assert "on_hit/on_crit: struck NPC center" in spawn
    assert "periodic/on_spawn/on_kill: source projectile center" in spawn
    assert "facing uses current owner.direction" in spawn
    assert "velocity uses the producer-supplied gameplay axis" in spawn
    assert "cursor uses MouseWorld minus the shifted spawn position" in spawn
    assert "not the visible sprite's rotation" in spawn
    assert "without changing velocity" in rotation["does"]
    assert set(rotation["params"]["mode"]["enum"]) == {"axis", "velocity", "spin"}
    assert rotation["params"]["radiansPerSecond"]["units"] == "radians/second"
    assert "required for spin, exact zero for other modes" in rotation["params"]["radiansPerSecond"]["meaning"]
    assert set(aim["params"]["source"]["enum"]) == {"initial", "cursor", "facing", "velocity"}
    assert aim["params"]["turnOwner"]["default"] is False
    assert "omission adds no turning side effect" in aim["params"]["turnOwner"]["meaning"]


def test_author_distinguishes_weapon_shoot_field_from_an_observed_ammunition_shot():
    request, _, _ = build_initial_author_request({}, {}, "source-observation-reading", model_name="offline-test-model")
    guidance = request_dossier(request)["requiredJsonShape"]["concept"]["coreMechanic"]
    assert "useAmmoCategoryName describes required ammo" in guidance
    assert "ammoCategoryName describes an ammo item's own category" in guidance
    assert "weapon_item.shoot_field is not a fired-shot observation" in guidance
    assert "effectiveProjectile" in guidance
