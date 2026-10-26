"""Read-only ammo observations at the actual serialized stage boundaries."""
from __future__ import annotations

import copy

import pytest

from infini_local.pipelines.parent_context_pipeline import compact_ammo_profile
from tests.test_units_packet_preservation import _source_packets, offline_packets  # noqa: F401


def test_inventory_observation_preserves_facts_but_not_current_quantities(offline_packets):
    captured, _ = offline_packets
    ammo = {
        "mode": "weapon_uses_ammo", "ammoId": 1,
        "playerInventoryObservation": {
            "source": "Player.inventory", "status": "observed", "candidateLimit": 3,
            "selection": "inventory_order_category_match_not_native_PickAmmo",
        },
        "playerInventoryAmmoRaw": [
            {"type": 40, "source": "player_inventory_ammo_candidate_base_no_prefix", "inventorySlot": 54,
             "stack": 17, "potion": False},
            {"type": 40, "source": "player_inventory_ammo_candidate_base_no_prefix", "inventorySlot": 55,
             "stack": 9, "potion": False},
        ],
        "playerInventoryProjectileRaw": [{"type": 1, "inventorySlot": 54}, {"type": 1, "inventorySlot": 55}],
        "fallbackAmmoRaw": [], "fallbackProjectileRaw": [],
    }
    parent = {"name": "literal ammo observation", "ammoRaw": ammo}
    before = copy.deepcopy(parent)
    expected = copy.deepcopy(ammo)
    for row in expected["playerInventoryAmmoRaw"]:
        row.pop("stack")
        row.pop("potion")
    for raw in _source_packets(parent, captured):
        assert raw["ammo"] == expected
    detached = compact_ammo_profile(parent)
    detached["playerInventoryObservation"]["status"] = "hostile mutation"
    assert parent == before


@pytest.mark.parametrize("status,reason", [("unavailable", "no_player"), ("unavailable", "inventory_scan_failed")])
def test_unavailable_inventory_never_becomes_observed_empty(offline_packets, status, reason):
    captured, _ = offline_packets
    observation = {"source": "Player.inventory", "status": status, "reason": reason, "candidateLimit": 3}
    parent = {"name": "unknown inventory", "ammoRaw": {
        "mode": "weapon_uses_ammo", "ammoId": 1, "playerInventoryObservation": observation,
        "playerInventoryAmmoRaw": None, "playerInventoryProjectileRaw": None,
        "fallbackAmmoRaw": [], "fallbackProjectileRaw": [],
    }}
    for raw in _source_packets(parent, captured):
        assert raw["ammo"]["playerInventoryObservation"] == observation
        assert "playerInventoryAmmoRaw" not in raw["ammo"]
        assert "playerInventoryProjectileRaw" not in raw["ammo"]


def test_explicit_empty_ammo_observation_does_not_borrow_fingerprint():
    parent = {"ammoRaw": {}, "fingerprint": {"ammoRaw": {
        "mode": "weapon_uses_ammo", "ammoId": 1, "playerInventoryAmmoRaw": [{"type": 40, "stack": 999}],
    }}}
    assert compact_ammo_profile(parent) == {}
    del parent["ammoRaw"]
    assert compact_ammo_profile(parent)["playerInventoryAmmoRaw"] == [{"type": 40}]
