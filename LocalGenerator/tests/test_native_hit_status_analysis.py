"""Behavior of the offline source analyzer; no Terraria execution or SDK needed."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/generate/native_hit_status_analysis.py"
spec = importlib.util.spec_from_file_location("native_hit_status_analysis", MODULE)
analysis = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = analysis
spec.loader.exec_module(analysis)
I = analysis.Instruction


def program(ops):
    return [I(offset, *op) for offset, op in enumerate(ops)]


def target():
    return [("ldsfld", "Terraria.Main.npc"), ("ldarg", 1), ("ldelem",)]


def effect(duration=None):
    return target() + [("const", 20)] + (duration or [("const", 600)]) + [
        ("const", 0), ("call", ("Terraria.NPC.AddBuff", 3, True, False)),
    ]


def test_unconditional_request_and_multiple_effects_preserve_identity():
    result = analysis.analyze(program(effect() + effect([("const", 120)]) + [("ret",)]), 1)
    assert [(e["buffId"], e["durationTicksMin"]) for e in result["effects"]] == [(20, 600), (20, 120)]


def test_random_duration_preserves_step_and_exclusive_upper_bound():
    random = [("call", ("Terraria.Main.get_rand", 0, False, True)),
              ("const", 5), ("const", 11),
              ("call", ("Terraria.Utilities.UnifiedRandom.Next", 2, True, True)),
              ("const", 60), ("mul",)]
    result = analysis.analyze(program(effect(random) + [("ret",)]), 1)
    value = result["effects"][0]
    assert (value["durationTicksMin"], value["durationTicksMax"], value["durationTicksStep"]) == (300, 600, 60)


@pytest.mark.parametrize("field", ["Terraria.Projectile.ai", "Terraria.Player.magmaStone", "Terraria.Main.hardMode"])
def test_conditional_state_is_not_promoted_to_unconditional(field):
    # Unknown player/world/AI condition may bypass the otherwise valid request.
    ops = [("ldsfld", field), ("brfalse", 9)] + effect() + [("ret",)]
    result = analysis.analyze(program(ops), 1)
    assert result["effects"] == []
    assert result["excludedSites"][0]["reason"] == "conditional_player_world_ai_or_random_path"


def test_type_condition_is_resolved_for_each_type_not_inferred_from_name():
    ops = [("ldarg", 0), ("ldfld", "Terraria.Projectile.type"), ("const", 7), ("bne", 11)] + effect() + [("ret",)]
    assert len(analysis.analyze(program(ops), 7)["effects"]) == 1
    assert analysis.analyze(program(ops), 8)["effects"] == []


def test_dynamic_duration_and_random_proc_are_excluded():
    assert analysis.analyze(program(effect([("ldsfld", "unknownDuration")]) + [("ret",)]), 1)["effects"] == []
    random = [("call", ("Terraria.Main.get_rand", 0, False, True)), ("const", 2),
              ("call", ("Terraria.Utilities.UnifiedRandom.Next", 1, True, True)), ("brfalse", 11)]
    assert analysis.analyze(program(random + effect() + [("ret",)]), 1)["effects"] == []


def test_differing_branch_durations_merge_as_unknown_not_last_path_wins():
    # Both branches reach one AddBuff site with different duration values.
    ops = target() + [("const", 20), ("ldsfld", "unknown"), ("brtrue", 8),
          ("const", 60), ("br", 9), ("const", 120), ("const", 0),
          ("call", ("Terraria.NPC.AddBuff", 3, True, False)), ("ret",)]
    assert analysis.analyze(program(ops), 1)["effects"] == []


@pytest.mark.parametrize("ops", [[("br", 0)], [("call", ("Mod.Hook", 0, False, False)), ("ret",)], [("stfld", "anything"), ("ret",)]])
def test_unsupported_code_fails_closed_instead_of_sampling(ops):
    with pytest.raises(ValueError):
        analysis.analyze(program(ops), 1)


def test_generated_catalog_preserves_all_reported_effects_and_both_certificates():
    # Generated file must be an exact projection of analysis evidence, not a
    # separately maintained hand-written per-item table.
    generator_path = ROOT / "tools/generate/generate_native_hit_status.py"
    spec = importlib.util.spec_from_file_location("generate_native_hit_status", generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    report = json.loads(generator.REPORT.read_text())
    assert generator.OUTPUT.read_text() == generator.render(report["sources"])
    for source in report["sources"]:
        records = source["records"]
        assert source["coveredProjectileEffects"] == sum(len(r["effects"]) for r in records)
        assert source["coveredProjectileTypes"] == len(records)
        assert source["coveredProjectileTypes"] < source["analyzedProjectileTypes"]
        assert source["uncoveredMethodAddBuffOffsets"]  # honest partial coverage
        pygmy = next(r for r in records if r["projectileName"] == "PygmySpear")
        assert pygmy["effects"][0]["durationTicksStep"] == 60
