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
        kind = "Item" if source.get("sourceKind") == "contact" else "Projectile"
        assert source["covered" + kind + "Effects"] == sum(len(r["effects"]) for r in records)
        assert source["covered" + kind + "Types"] == len(records)
        assert source["covered" + kind + "Types"] < source["analyzed" + kind + "Types"]
        assert source["uncoveredMethodAddBuffOffsets"]  # honest partial coverage
        if kind == "Projectile":
            pygmy = next(r for r in records if r["projectileName"] == "PygmySpear")
            assert pygmy["effects"][0]["durationTicksStep"] == 60
        else:
            grass = next(r for r in records if r["itemId"] == 190)
            assert grass["randomOutcomes"][0]["alternatives"][0]["probabilityDenominator"] == 4


def random_choice(high):
    return [("call", ("Terraria.Main.get_rand", 0, False, True)), ("const", high),
            ("call", ("Terraria.Utilities.UnifiedRandom.Next", 1, True, True))]


def test_bounded_random_proc_preserves_empty_alternative_and_exact_probability():
    result = analysis.analyze(program(random_choice(4) + [("brtrue", 11)] + effect([("const", 420)]) + [("ret",)]), 1)
    assert result["effects"] == []
    choice = result["randomOutcomes"][0]
    assert choice["sourceRandomCallIlOffset"] == 2
    assert [(a["randomValues"], a["probabilityNumerator"], a["probabilityDenominator"], len(a["effects"]))
            for a in choice["alternatives"]] == [([0], 1, 4, 1), ([1, 2, 3], 3, 4, 0)]
    assert choice["alternatives"][0]["effects"][0]["durationTicksMin"] == 420


def test_discrete_random_durations_are_mutually_exclusive_not_two_simultaneous_buffs():
    # One random call chooses either 600 or 300 ticks, never both requests.
    ops = random_choice(3) + [("brtrue", 12)] + effect() + [("br", 19)] + effect([("const", 300)]) + [("ret",)]
    result = analysis.analyze(program(ops), 1)
    assert result["effects"] == []
    alternatives = result["randomOutcomes"][0]["alternatives"]
    assert [(a["probabilityNumerator"], a["probabilityDenominator"], a["effects"][0]["durationTicksMin"])
            for a in alternatives] == [(1, 3, 600), (2, 3, 300)]


def test_random_choice_does_not_erase_unknown_world_condition_or_expand_large_ranges():
    ops = random_choice(4) + [("brtrue", 13), ("ldsfld", "Terraria.Main.hardMode"), ("brfalse", 13)] + effect() + [("ret",)]
    assert analysis.analyze(program(ops), 1)["randomOutcomes"] == []
    assert analysis.analyze(program(random_choice(100) + [("brtrue", 11)] + effect() + [("ret",)]), 1)["randomOutcomes"] == []


def labeled(ops):
    labels, clean = {}, []
    for op in ops:
        if op[0] == "label":
            labels[op[1]] = len(clean)
        else:
            clean.append(op)
    return program([(op[0], labels.get(op[1], op[1])) if len(op) == 2 and isinstance(op[1], str) and op[1] in labels else op for op in clean])


def test_request_depending_on_two_random_draws_is_not_claimed_as_single_draw():
    ops = random_choice(4) + [("brtrue", "done")] + random_choice(3) + [("brtrue", "done")] + effect() + [("label", "done"), ("ret",)]
    result = analysis.analyze(labeled(ops), 1)
    assert result["effects"] == [] and result["randomOutcomes"] == []


def test_irrelevant_second_random_draw_does_not_hide_proved_first_draw():
    ops = random_choice(4) + [("brtrue", "other")] + effect() + [("label", "other")] + random_choice(3) + [("brtrue", "done"), ("ret",), ("label", "done"), ("ret",)]
    result = analysis.analyze(labeled(ops), 1)
    assert len(result["randomOutcomes"]) == 1
    assert [a["probabilityNumerator"] for a in result["randomOutcomes"][0]["alternatives"]] == [1, 3]


def test_reused_random_local_keeps_correlated_requests_in_one_alternative():
    ops = random_choice(3) + [("stloc", 0), ("ldloc", 0), ("brtrue", "second")] + effect() + [
        ("label", "second"), ("ldloc", 0), ("brtrue", "done")] + effect([("const", 120)]) + [("label", "done"), ("ret",)]
    result = analysis.analyze(labeled(ops), 1)
    assert len(result["randomOutcomes"]) == 1
    alternatives = result["randomOutcomes"][0]["alternatives"]
    assert [(a["randomValues"], len(a["effects"])) for a in alternatives] == [([0], 2), ([1, 2], 0)]


def test_shared_random_duration_and_proc_are_one_correlated_choice():
    draw = [("call", ("Terraria.Main.get_rand", 0, False, True)), ("const", 1), ("const", 4),
            ("call", ("Terraria.Utilities.UnifiedRandom.Next", 2, True, True)), ("stloc", 0)]
    duration = [("ldloc", 0), ("const", 60), ("mul",)]
    ops = draw + effect(duration) + [("ldloc", 0), ("const", 1), ("bne", "done")] + effect() + [("label", "done"), ("ret",)]
    result = analysis.analyze(labeled(ops), 1)
    assert result["effects"] == []  # no independent duration range alongside the proc
    assert len(result["randomOutcomes"]) == 1
    alternatives = result["randomOutcomes"][0]["alternatives"]
    assert [(a["randomValues"], [e["durationTicksMin"] for e in a["effects"]]) for a in alternatives] == [([1], [60, 600]), ([2], [120]), ([3], [180])]


@pytest.mark.parametrize("high", [4, 100])
def test_reused_duration_roll_is_joint_or_declined_when_over_bound(high):
    draw = [("call", ("Terraria.Main.get_rand", 0, False, True)), ("const", 1), ("const", high),
            ("call", ("Terraria.Utilities.UnifiedRandom.Next", 2, True, True)), ("stloc", 0)]
    ops = draw + effect([("ldloc", 0), ("const", 60), ("mul",)]) + effect([("ldloc", 0), ("const", 120), ("mul",)]) + [("ret",)]
    result = analysis.analyze(program(ops), 1)
    assert result["effects"] == []
    if high == 4:
        assert [[e["durationTicksMin"] for e in a["effects"]] for a in result["randomOutcomes"][0]["alternatives"]] == [[60, 120], [120, 240], [180, 360]]
    else:
        assert result["randomOutcomes"] == []
        assert len(result["excludedSites"]) == 2


def test_random_switch_retains_every_exclusive_arm_and_empty_default():
    ops = random_choice(4) + [("switch", (5, 13)), ("br", 20)] + effect() + [("br", 20)] + effect([("const", 120)]) + [("ret",)]
    result = analysis.analyze(program(ops), 1)
    assert result["effects"] == []
    assert len(result["randomOutcomes"]) == 1
    alternatives = result["randomOutcomes"][0]["alternatives"]
    assert [(a["randomValues"], [e["durationTicksMin"] for e in a["effects"]]) for a in alternatives] == [([0], [600]), ([1], [120]), ([2, 3], [])]


def test_contact_signature_binds_item_type_and_npc_index_without_player_equipment_inference():
    # Unlike projectile StatusNPC, contact signature passes native item type as
    # arg1 and target NPC index as arg2. Player fields remain unknown.
    contact_effect = [("ldsfld", "Terraria.Main.npc"), ("ldarg", 2), ("ldelem",),
                      ("const", 20), ("const", 420), ("const", 0),
                      ("call", ("Terraria.NPC.AddBuff", 3, True, False))]
    ops = [("ldarg", 1), ("const", 190), ("bne", "done")] + random_choice(4) + [("brtrue", "done")] + contact_effect + [("label", "done"), ("ret",)]
    assert len(analysis.analyze(labeled(ops), 190, "contact")["randomOutcomes"]) == 1
    assert analysis.analyze(labeled(ops), 191, "contact")["randomOutcomes"] == []
    conditional = [("ldarg", 0), ("ldfld", "Terraria.Player.magmaStone"), ("brfalse", "done")] + ops
    assert analysis.analyze(labeled(conditional), 190, "contact")["randomOutcomes"] == []
    with pytest.raises(ValueError):
        analysis.analyze(labeled(ops), 190, "unknown_signature")
