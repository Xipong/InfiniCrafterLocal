from __future__ import annotations

import ast
import inspect
from pathlib import Path

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring import compiler as compiler_mod
from infini_local.core.runtime_authoring import equipment as equipment_mod
from infini_local.core.runtime_authoring import secondary as secondary_mod
from infini_local.core.runtime_authoring import semantics as semantics_mod
from infini_local.core.runtime_authoring.equipment import (
    _EQUIPMENT_STAT_FIELDS,
    apply_accessory_calls,
    apply_armor_calls,
)
from infini_local.core.runtime_authoring.secondary import (
    apply_primary_onhit_child_gates,
    apply_secondary_projectile_calls,
)


_RA = Path(__file__).resolve().parents[1] / "infini_local" / "core" / "runtime_authoring"


def _source(mod) -> str:
    return Path(inspect.getfile(mod)).read_text(encoding="utf-8")


def test_equipment_module_owns_shared_stat_clamp_table_once() -> None:
    assert isinstance(_EQUIPMENT_STAT_FIELDS, list)
    assert len(_EQUIPMENT_STAT_FIELDS) >= 20
    names = [row[0] for row in _EQUIPMENT_STAT_FIELDS]
    assert names == list(dict.fromkeys(names))
    assert "movementSpeed" in names
    assert "lightStrength" in names
    # One shared table — no duplicate equipment field lists in compiler.
    compiler_src = _source(compiler_mod)
    assert "equipment_fields" not in compiler_src
    assert "armor_equipment_fields" not in compiler_src
    assert "apply_accessory_calls" in compiler_src
    assert "apply_armor_calls" in compiler_src
    equip_src = _source(equipment_mod)
    assert equip_src.count("_EQUIPMENT_STAT_FIELDS") >= 2  # def + use
    # Dependency direction: equipment → common only (no compiler/secondary import).
    tree = ast.parse(equip_src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    assert all("compiler" not in m and "secondary" not in m for m in imported)
    assert any(m.endswith(".common") for m in imported)


def test_accessory_and_armor_lowerers_preserve_clamps_and_kind() -> None:
    acc_patch: dict = {}
    apply_accessory_calls(
        acc_patch,
        [{
            "archetype": "Utility Belt",
            "defense": 99,
            "stats": {
                "movementSpeed": 9.0,
                "maxLife": 250,
                "fallDamageImmune": True,
                "lightColorName": "aurora_shift_very_long_name_truncated",
            },
        }],
    )
    assert acc_patch["kind"] == "accessory"
    assert acc_patch["maxStack"] == 1
    assert acc_patch["accessory"]["enabled"] is True
    assert acc_patch["accessory"]["defense"] == 20
    assert acc_patch["accessory"]["movementSpeed"] == 1.0
    assert acc_patch["accessory"]["maxLife"] == 100
    assert acc_patch["accessory"]["fallDamageImmune"] is True
    assert acc_patch["accessory"]["lightColorName"] == "aurora_shift_very_long_name_truncated"[:32]

    arm_patch: dict = {}
    apply_armor_calls(
        arm_patch,
        [{
            "armorSlot": "head",
            "setKey": "probe_set",
            "archetype": "magic",
            "defense": 100,
            "stats": {"magicDamage": 0.9, "maxMana": 999},
            "setBonus": {"text": "Finite set.", "magicDamage": 0.9, "minionSlots": 5},
        }],
        {"resultKind": "armor"},
    )
    assert arm_patch["kind"] == "armor"
    assert arm_patch["damage"] == 0
    assert arm_patch["armor"]["slot"] == "head"
    assert arm_patch["armor"]["defense"] == 80
    assert arm_patch["armor"]["magicDamage"] == 0.4
    assert arm_patch["armor"]["maxMana"] == 100
    assert arm_patch["armor"]["setBonusText"] == "Finite set."
    assert arm_patch["armor"]["setBonusMagicDamage"] == 0.4
    assert arm_patch["armor"]["setBonusMinionSlots"] == 2


def test_compiler_routes_equipment_and_preserves_end_to_end_patch() -> None:
    accessory = compile_runtime_plan_to_genome_patch({
        "category": "accessory",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "accessory"}},
                {
                    "fn": "accessory_effect",
                    "params": {
                        "archetype": "utility",
                        "defense": 10,
                        "stats": {
                            "movementSpeed": 0.12,
                            "ammoSaveChance": 0.13,
                            "fallDamageImmune": True,
                        },
                    },
                },
            ]
        },
    })
    assert accessory["kind"] == "accessory"
    assert accessory["accessory"]["defense"] == 10
    assert accessory["accessory"]["movementSpeed"] == 0.12
    assert accessory["accessory"]["ammoSaveChance"] == 0.13
    assert accessory["accessory"]["fallDamageImmune"] is True
    assert accessory["useTimeTicks"] == 10
    assert accessory["useAnimationTicks"] == 10

    armor = compile_runtime_plan_to_genome_patch({
        "category": "armor",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "armor", "armorSlot": "body"}},
                {
                    "fn": "armor_effect",
                    "params": {
                        "armorSlot": "body",
                        "setKey": "owner_cleanup_set",
                        "archetype": "melee",
                        "defense": 12,
                        "stats": {"meleeDamage": 0.1},
                        "setBonus": {"text": "Owner cleanup.", "meleeDamage": 0.1},
                    },
                },
            ]
        },
    })
    assert armor["kind"] == "armor"
    assert armor["armor"]["slot"] == "body"
    assert armor["armor"]["defense"] == 12
    assert armor["armor"]["meleeDamage"] == 0.1
    assert armor["armor"]["setBonusMeleeDamage"] == 0.1
    assert armor["damage"] == 0


def test_primary_onhit_child_gates_owned_by_secondary_before_secondary_calls() -> None:
    compiler_src = _source(compiler_mod)
    secondary_src = _source(secondary_mod)
    assert "def apply_primary_onhit_child_gates" in secondary_src
    assert "apply_primary_onhit_child_gates(patch, hit)" in compiler_src
    # Call order: primary gate then secondary projectile owner.
    gate_pos = compiler_src.index("apply_primary_onhit_child_gates(patch, hit)")
    secondary_pos = compiler_src.index("apply_secondary_projectile_calls(patch, secondary_calls)")
    assert gate_pos < secondary_pos
    # Compiler must not still own the chain/maxChild demotion body.
    assert 'onhit in {"chain", "lightning_arc"}' not in compiler_src
    assert "chain_count + 1" not in compiler_src
    assert "requires_count_gt_0" not in compiler_src


def test_primary_onhit_child_gates_budget_and_demotion_behavior() -> None:
    chain = apply_primary_onhit_child_gates(
        {"onHit": "chain", "chainCount": 3, "splitCount": 0},
        {},
    )
    assert chain["maxChildProjectiles"] == 4
    assert chain["maxChildDepth"] == 1
    assert chain["onHit"] == "chain"

    # splitCount promotes into chainCount when chainCount missing.
    promoted = apply_primary_onhit_child_gates(
        {"onHit": "lightning_arc", "splitCount": 2},
        {},
    )
    assert promoted["chainCount"] == 2
    assert promoted["splitCount"] == 0
    assert promoted["maxChildProjectiles"] == 3

    demoted = apply_primary_onhit_child_gates({"onHit": "starburst", "splitCount": 0}, {})
    assert demoted["onHit"] == "none"
    assert demoted["onHitDemotedReason"] == "starburst_requires_count_gt_0"

    kept = apply_primary_onhit_child_gates({"onHit": "starburst", "splitCount": 5}, {})
    assert kept["onHit"] == "starburst"
    assert kept["maxChildProjectiles"] == 5
    assert kept["maxChildDepth"] == 1


def test_compiler_end_to_end_primary_child_budget_before_secondary() -> None:
    starburst = compile_runtime_plan_to_genome_patch({
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "shoot",
                        "delivery": "shoot",
                        "movement": "straight",
                        "speed": 12,
                        "rangeTiles": 20,
                        "lifetimeTicks": 40,
                    },
                },
                {"fn": "apply_on_hit_effect", "params": {"onHit": "starburst", "count": 4}},
            ]
        },
    })
    assert starburst["onHit"] == "starburst"
    assert starburst["splitCount"] == 4
    assert starburst["maxChildProjectiles"] == 4
    assert starburst["maxChildDepth"] == 1

    demoted = compile_runtime_plan_to_genome_patch({
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "shoot",
                        "delivery": "shoot",
                        "movement": "straight",
                        "speed": 12,
                        "rangeTiles": 20,
                        "lifetimeTicks": 40,
                    },
                },
                {"fn": "apply_on_hit_effect", "params": {"onHit": "mini_missiles"}},
            ]
        },
    })
    assert demoted["onHit"] == "none"
    assert demoted["onHitDemotedReason"] == "mini_missiles_requires_count_gt_0"


def test_proven_dead_cleanup_removed() -> None:
    secondary_src = _source(secondary_mod)
    semantics_src = _source(semantics_mod)
    assert "_DEBUFF_ONHITS" not in secondary_src
    assert 'elif current_onhit == "split"' not in secondary_src
    assert "def _runtime_family_from_fields" not in semantics_src
    assert "_runtime_family_from_fields" not in semantics_mod.__all__
    # No remaining callers in runtime_authoring package.
    package_hits = []
    for path in _RA.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "_runtime_family_from_fields" in text:
            package_hits.append(path.name)
        if "_DEBUFF_ONHITS" in text:
            package_hits.append(path.name)
    assert package_hits == []


def test_secondary_export_surface_and_split_without_secondary_still_works() -> None:
    assert "apply_primary_onhit_child_gates" in secondary_mod.__all__
    assert "apply_secondary_projectile_calls" in secondary_mod.__all__
    # split is in _CHILD_ONHITS; dead duplicate elif branch must not be required.
    patch = apply_secondary_projectile_calls(
        {"onHit": "split", "splitCount": 3},
        [],
    )
    assert patch["maxChildProjectiles"] == 3
    assert patch["maxChildDepth"] == 1
    empty = apply_secondary_projectile_calls({"onHit": "split", "splitCount": 0}, [])
    assert empty["onHit"] == "none"
    assert empty["onHitDemotedReason"] == "split_requires_secondary_count_gt_0"
