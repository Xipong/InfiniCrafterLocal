from __future__ import annotations

import copy
import json

import pytest

from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines.parent_context_pipeline import compact_projectile_profile


@pytest.mark.parametrize("surface,key", [
    ("directProjectileRaw", "directProjectile"),
    ("effectiveProjectileRaw", "effectiveProjectile"),
])
def test_hit_status_certificate_and_limits_reach_author_without_mutating_parent(surface, key):
    observation = {
        "source": "verified_native_StatusNPC_reference",
        "fullName": "Terraria/ShadowFlameKnife",
        "sourceMethodSha256": "literal-source-certificate",
        "buffId": 153,
        "buffFullName": "Terraria/ShadowFlame",
        "durationTicksMin": 60,
        "durationTicksMax": 179,
        "durationDistribution": "uniform_integer_inclusive",
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
