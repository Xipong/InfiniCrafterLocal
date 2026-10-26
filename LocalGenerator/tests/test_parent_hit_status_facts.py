from __future__ import annotations

import copy
import json

import pytest

from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines.parent_context_pipeline import compact_projectile_profile
from prompt_packet_helpers import expand_native_source_references


@pytest.mark.parametrize("surface,key", [
    ("directProjectileRaw", "directProjectile"),
    ("effectiveProjectileRaw", "effectiveProjectile"),
])
def test_hit_status_certificate_and_limits_reach_author_without_mutating_parent(surface, key):
    observation = {
        "source": "verified_native_StatusNPC_reference",
        "fullName": "Terraria/ShadowFlameKnife",
        "sourceMethodSha256": "literal-source-certificate",
        "sourceModuleVersionId": "literal-module-identity",
        "effects": [{
        "buffId": 153,
        "buffFullName": "Terraria/ShadowFlame",
        "durationTicksMin": 60,
        "durationTicksMax": 179,
        "durationDistribution": "uniform_integer_steps_inclusive",
        "durationTicksStep": 1,
        "sourceIlOffset": 42,
        }, {"buffId": 20, "durationTicksMin": 60, "durationTicksMax": 60, "durationTicksStep": 1}],
        "scope": "NPC-hit request only; target immunity/global mods may change outcome.",
    }
    projectile = {"type": 497, "onHitStatusReference": observation}
    parent = {"name": "literal parent", "buffType": 0, surface: projectile}
    before = copy.deepcopy(parent)
    _, user, _ = author.build_initial_author_request(parent, {}, "source-status", model_name="offline-test-model")
    packet = json.loads(user)["parents"]["A"]["packet"]
    assert packet["raw"][key]["onHitStatusReference"] == observation
    compact = compact_projectile_profile(projectile)
    compact["onHitStatusReference"]["scope"] = "mutated copy"
    assert parent == before


@pytest.mark.parametrize("projectile", [
    {"type": 497},
    {"type": 497, "onHitStatusReference": None},
    {"fullName": "Terraria/GoldenShowerFriendly", "aiStyle": 12},
])
def test_unknown_hit_status_is_never_inferred_from_identity_or_ai(projectile):
    assert "onHitStatusReference" not in compact_projectile_profile(projectile)


def test_parent_ammo_observations_reach_author_with_scope_multiplicity_and_empty_inventory():
    observation = {"source": "verified native", "effects": [], "randomOutcomes": [
        {"sourceRandomCallIlOffset": 123, "randomMinimumInclusive": 0, "randomMaximumExclusive": 3,
         "alternatives": [
             {"randomValues": [0], "probabilityNumerator": 1, "probabilityDenominator": 3,
              "effects": [{"buffId": 24, "durationTicksMin": 600, "durationTicksMax": 600}]},
             {"randomValues": [1, 2], "probabilityNumerator": 2, "probabilityDenominator": 3,
              "effects": [{"buffId": 24, "durationTicksMin": 300, "durationTicksMax": 300}]}]}],
         "scope": "Mutually exclusive alternatives, not independent proc rolls."}
    candidate = {"source": "representative_ammo", "inventorySlot": -1, "type": 163,
                 "armorPenetration": 0, "onHitStatusReference": observation}
    parent = {"name": "synthetic ammo weapon", "shoot": 10, "lifeRegen": 2,
              "directProjectileRaw": {"type": 10, "armorPenetration": 5},
              "ammoRaw": {"mode": "weapon_uses_ammo", "ammoId": 931,
                  "playerInventoryAmmoRaw": [], "playerInventoryProjectileRaw": [],
                  "fallbackAmmoRaw": [{"type": 931, "source": "representative_ammo", "inventorySlot": -1, "damage": 0}],
                  "fallbackProjectileRaw": [candidate, candidate]}}
    before = copy.deepcopy(parent)
    _, user, _ = author.build_initial_author_request(parent, {}, "ammo-source", model_name="offline-test-model")
    packet = json.loads(user)
    assert "sourceSameAs" in user
    raw = expand_native_source_references(packet)["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["lifeRegen"] == 2
    assert raw["directProjectile"] == {"type": 10, "armorPenetration": 5}
    assert raw["ammo"] == parent["ammoRaw"]
    assert parent == before


def test_native_shoot_and_collision_certificates_keep_scopes_and_conditional_values():
    shoot = {"source": "verified_native_Player.ItemCheck_Shoot_reference", "fullName": "Terraria/Synthetic",
             "damageMultiplierAtSpawn": .5, "shotDamageLocalMayBeModifiedInBranch": True,
             "explicitSpawnCount": {"minimum": 1, "maximum": 1, "distribution": "fixed"},
             "sourceMethodSha256": "synthetic", "sourceModuleVersionId": "synthetic-module",
             "scope": "Branch-local current shot damage after conditional crit; not base damage or guaranteed hits."}
    collision = {"halfLengthTimesProjectileScale": 46.0, "lineWidthTimesProjectileScale": 8.0,
                 "scope": "Live scale, not necessarily default scale; native broadphase and hooks still gate collision."}
    parent = {"nativeShootReference": shoot, "directProjectileRaw": {"type": 974, "collisionReference": collision}}
    before = copy.deepcopy(parent)
    _, user, _ = author.build_initial_author_request(parent, {}, "attack-source", model_name="offline-test-model")
    raw = json.loads(user)["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["nativeShootReference"] == shoot
    assert raw["directProjectile"]["collisionReference"] == collision
    raw["item"]["nativeShootReference"]["damageMultiplierAtSpawn"] = 1
    assert parent == before


def test_contact_status_certificate_is_not_relabelled_as_projectile_status():
    contact = {"source": "verified_native_StatusToNPC_reference", "sourceKind": "contact", "fullName": "Terraria/BladeofGrass",
               "sourceMethodSha256": "contact-method", "sourceModuleVersionId": "module", "effects": [],
               "randomOutcomes": [{"alternatives": [{"probabilityNumerator": 1, "probabilityDenominator": 4,
                   "effects": [{"buffId": 20, "durationTicksMin": 420}]}]}], "scope": "Native item contact only."}
    parent = {"nativeContactHitStatusReference": contact, "shoot": 976}
    _, user, _ = author.build_initial_author_request(parent, {}, "contact-source", model_name="offline-test-model")
    raw = json.loads(user)["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["nativeContactHitStatusReference"] == contact
    assert "onHitStatusReference" not in raw["item"]
