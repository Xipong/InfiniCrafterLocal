from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.qa.capability_selection_experiment import (
    build_author_variant, build_selector_packet, catalogue_index, catalog_revision,
    _positive_dependencies,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.fixture(scope="module")
def payload():
    return build_llm_author_payload({"name": "A"}, {"name": "B"}, "selection-test")


def choice(payload, selected=(), full=False):
    return {"catalogRevision": catalog_revision(payload), "selected": list(selected),
            "fullCatalog": full, "intent": "Keep independent secondary mechanics."}


@pytest.mark.parametrize("mode", ["groups", "capabilities"])
def test_full_catalogue_discoverable_and_secondary_contracts_literal(payload, mode):
    before = deepcopy(payload)
    packet, audit = build_author_variant(payload, mode, choice(payload))
    assert {c["fn"] for c in catalogue_index(payload)} == set(CAPABILITY_REGISTRY)
    originals = {c["fn"]: c for c in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    cards = {c["fn"]: c for c in packet["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    index_names = {c["fn"] for c in packet["runtimeCapabilityContract"]["indexOnlyCapabilities"]}
    assert set(cards) | index_names == set(CAPABILITY_REGISTRY)
    assert not set(cards) & index_names
    for name in audit["secondaryReserveIds"]:
        assert cards[name] == originals[name]
    for name in ("configure_tool", "configure_accessory", "configure_armor",
                 "refresh_generated_effect_group_while_held", "apply_generated_buff_on_use",
                 "configure_tile_placement", "enable_placed_vfx", "spawn_entity_on_event",
                 "heal_owner_on_event", "configure_weapon_ammo", "configure_vanilla_ammo_item"):
        assert name in cards
    assert payload == before
    assert packet["requiredJsonShape"] == payload["requiredJsonShape"]
    assert not audit["runtimeAdmissionChanged"]


def test_groups_include_all_movement_alternatives_without_instantiating_them(payload):
    packet, audit = build_author_variant(payload, "groups", choice(payload, ["movement"]))
    assert {n for n,c in CAPABILITY_REGISTRY.items() if c.category == "movement"} <= set(audit["detailedIds"])
    assert "calls" not in packet


def test_different_entity_movements_survive_and_conflicts_are_not_dependencies(payload):
    _, audit = build_author_variant(payload, "capabilities", choice(payload, ["move_gravity_arc", "move_slow_homing"]))
    assert {"move_gravity_arc", "move_slow_homing"} <= set(audit["detailedIds"])
    expanded, _ = _positive_dependencies({"set_projectile_turn_modifier"})
    assert "channel_beam" not in expanded
    assert "charge_then_release" not in expanded


def test_declared_alternative_dependency_exposes_all_legal_choices():
    expanded, _ = _positive_dependencies({"charge_then_release"})
    assert {n for n,c in CAPABILITY_REGISTRY.items() if c.category == "movement"} <= expanded
    assert "configure_item_use" in expanded


@pytest.mark.parametrize("mode", ["groups", "capabilities"])
def test_explicit_full_catalogue_is_literal_not_a_hidden_retry(payload, mode):
    packet, audit = build_author_variant(payload, mode, choice(payload, full=True))
    assert packet["runtimeCapabilityContract"] == payload["runtimeCapabilityContract"]
    assert packet["priorityHeader"] == payload["priorityHeader"]
    assert audit["indexOnlyIds"] == []


@pytest.mark.parametrize("edit", [
    {"catalogRevision": "stale"}, {"selected": ["not_a_capability"]},
    {"fullCatalog": "false"}, {"selected": ["configure_tool", "configure_tool"]},
    {"undeclared": True},
])
def test_invalid_selection_never_silently_changes_design(payload, edit):
    selection = choice(payload)
    selection.update(edit)
    with pytest.raises(ValueError):
        build_author_variant(payload, "capabilities", selection)


def test_selector_includes_secondary_parameter_names_and_exact_revision(payload):
    packet = build_selector_packet(payload, "capabilities")
    cards = {c["fn"]: c for c in packet["static"]["completeCatalogue"]}
    assert "oreSenseEnabled" in cards["apply_generated_buff_on_use"]["parameters"]
    assert "defensePoints" in cards["configure_accessory"]["parameters"]
    assert packet["static"]["outputSchema"]["properties"]["catalogRevision"]["const"] == catalog_revision(payload)


def test_existing_full_registry_validator_remains_unchanged(payload):
    original = build_runtime_fixture("equipment_tool_combat")
    assert validate_runtime_program(original)["ok"]
    build_author_variant(payload, "capabilities", choice(payload))
    assert validate_runtime_program(original)["ok"]
