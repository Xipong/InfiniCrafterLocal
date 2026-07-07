from __future__ import annotations

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result


def test_authored_runtime_fields_have_precise_provenance() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 21, "useTimeTicks": 17}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "cast", "delivery": "cast", "movement": "straight", "shotCount": 3, "speed": 11, "pierce": 2, "rangeTiles": 44, "lifetimeTicks": 120}},
                {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 2, "maxChildProjectiles": 4}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "burst", "aoeRadiusTiles": 3}},
                {"fn": "spawn_contact_particles", "params": {"effect": "star", "burstDustCap": 20}},
                {"fn": "leave_trail_or_field", "params": {"trailLength": 12, "fieldRadiusTiles": 5}},
            ]
        },
    }

    result = compile_runtime_plan_to_genome_result(data)
    provenance = result["provenance"]
    sources = provenance["fieldSources"]

    assert sources["damage"] == "set_item_stats"
    assert sources["useTimeTicks"] == "set_item_stats"
    assert sources["damageClass"] == "set_item_stats"
    assert sources["shotCount"] == "shoot_projectile"
    assert sources["speed"] == "shoot_projectile"
    assert sources["pierce"] == "shoot_projectile"
    assert sources["rangeTiles"] == "shoot_projectile"
    assert sources["range"] == "shoot_projectile"
    assert sources["lifetimeTicks"] == "shoot_projectile"
    assert sources["lifetime"] == "shoot_projectile"
    assert sources["runtimeFamily"] == "shoot_projectile"
    assert sources["splitCount"] == "spawn_secondary_projectiles"
    assert sources["maxChildProjectiles"] == "spawn_secondary_projectiles"
    assert sources["onHit"] == "apply_on_hit_effect"
    assert sources["aoeRadiusTiles"] == "apply_on_hit_effect"
    assert sources["burstDustCap"] == "spawn_contact_particles"
    assert sources["effect"] == "spawn_contact_particles"
    assert sources["trailLength"] == "leave_trail_or_field"
    assert sources["vfxFieldRadiusTiles"] == "leave_trail_or_field"
    assert sources["fieldRadius"] == "leave_trail_or_field"

    assert provenance["gameplayChildren"]["enabled"] is True
    assert provenance["gameplayChildren"]["source"] == "spawn_secondary_projectiles"
    assert provenance["pureVfx"]["enabled"] is True
    assert provenance["pureVfx"]["authoredCallCount"] >= 2
    assert provenance["authoredFields"]["damage"] is True


def test_defaults_are_distinguishable_from_authored_fields() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 8, "useTimeTicks": 24}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9}},
            ]
        },
    }
    provenance = compile_runtime_plan_to_genome_result(data)["provenance"]
    sources = provenance["fieldSources"]

    assert sources["damage"] == "set_item_stats"
    assert sources["useTimeTicks"] == "set_item_stats"
    assert sources["shotCount"] == "runtime_compiler_default"
    assert provenance["authoredFields"]["shotCount"] is False
    assert sources["speed"] == "shoot_projectile"
