"""Behavioral controls for narrow static source-shape recognizers."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/generate"))
from native_hit_status_analysis import Instruction as I
import native_attack_fact_analysis as analysis
import generate_native_attack_facts as generator


def program(ops):
    labels, clean = {}, []
    for op in ops:
        if op[0] == "label": labels[op[1]] = len(clean)
        else: clean.append(op)
    return [I(n, op[0], labels.get(op[1], op[1]) if len(op) == 2 and isinstance(op[1], str) else op[1] if len(op) == 2 else None) for n, op in enumerate(clean)]


def spawn(damage=None):
    # Vector NewProjectile overload: source, position, velocity, type, damage,
    # knockback, owner, ai0, ai1, ai2.
    return [("ldloc", 7), ("ldloc", 8), ("ldloc", 9), ("ldloc", 0)] + (damage or [("ldloc", 4)]) + [
        ("ldloc", 5), ("ldarg", 1), ("const", 0), ("const", 0), ("const", 0),
        ("call", ("Terraria.Projectile.NewProjectile", 10, False, True)), ("pop",)]


def wrap(body):
    return [("ldarg", 3), ("stloc", 4), ("ldarg", 2), ("ldfld", "Terraria.Item.type"),
            ("const", 123), ("bne", "outside")] + body + [("label", "outside"), ("ret",)]


def loop(prefix=None, suffix=None, step=1):
    return (prefix or []) + [("call", ("Terraria.Main.get_rand", 0, False, True)), ("const", 3), ("const", 5),
        ("call", ("Terraria.Utilities.UnifiedRandom.Next", 2, True, True)), ("stloc", 10),
        ("const", 0), ("stloc", 11), ("br", "condition"), ("label", "body")] + spawn() + [
        ("ldloc", 11), ("const", step), ("add",), ("stloc", 11), ("label", "condition"),
        ("ldloc", 11), ("ldloc", 10), ("blt", "body"), ("ret",)] + (suffix or [])


def test_branch_multiplier_is_current_shot_local_not_item_base_damage():
    damage = [("ldloc", 4), ("conv", "conv.r8"), ("const", .25), ("mul",), ("conv", "conv.i4")]
    result = analysis.shoot_facts(program(wrap(spawn(damage) + [("ret",)])))
    assert len(result) == 1
    assert result[0]["damageMultiplierAtSpawn"] == .25
    assert result[0]["explicitSpawnCount"] == {"minimum": 1, "maximum": 1, "distribution": "fixed"}
    conditional = [("ldsfld", "unknown"), ("brfalse", "spawn"), ("ldloc", 4), ("const", 2), ("mul",), ("stloc", 4), ("label", "spawn")]
    assert analysis.shoot_facts(program(wrap(conditional + spawn(damage) + [("ret",)])))[0]["shotDamageLocalMayBeModifiedInBranch"] is True


def test_canonical_counted_loop_preserves_uniform_exclusive_upper_bound():
    result = analysis.shoot_facts(program(wrap(loop())))
    assert result[0]["explicitSpawnCount"] == {"minimum": 3, "maximum": 4, "distribution": "uniform_integer_inclusive"}
    assert result[0]["damageMultiplierAtSpawn"] == 1


@pytest.mark.parametrize("body", [
    loop(prefix=[("ret",)]),
    loop(prefix=[("ldsfld", "unknown"), ("brtrue", "outside")]),
    loop(prefix=[("ldloca", 10), ("call", ("unknown.mutate", 1, False, False))]),
    loop(prefix=[("const", 7), ("stloc", 10)]),
    loop(step=2),
    spawn() + [("br", "outside")],  # this path still executes one spawn; handled separately below
])
def test_noncanonical_counting_fails_closed(body):
    if body == spawn() + [("br", "outside")]:
        # A branch that exits after one call remains a valid single-spawn proof.
        assert analysis.shoot_facts(program(wrap(body)))[0]["explicitSpawnCount"]["minimum"] == 1
    else:
        assert analysis.shoot_facts(program(wrap(body))) == []


def test_duplicate_type_guards_and_conditional_skip_are_not_overwritten_or_certified():
    first = wrap(spawn() + [("ret",)])
    duplicate = program(first + first)
    assert analysis.shoot_facts(duplicate) == []
    unsupported = wrap(spawn([("ldsfld", "unknown.damage")]) + [("ret",)])
    assert analysis.shoot_facts(program(first + unsupported)) == []
    body = [("ldsfld", "unknown"), ("brtrue", "outside")] + spawn() + [("ret",)]
    assert analysis.shoot_facts(program(wrap(body))) == []


def test_generated_attack_catalog_is_exact_report_projection_with_real_source_certificates():
    sources = json.loads(generator.REPORT.read_text())["sources"]
    assert generator.OUTPUT.read_text() == generator.render(sources)
    shoot = next(s for s in sources if s["method"] == "Player.ItemCheck_Shoot")
    by_id = {r["itemId"]: r for r in shoot["records"]}
    assert by_id[190]["damageMultiplierAtSpawn"] == .25
    assert by_id[46]["damageMultiplierAtSpawn"] == .5
    assert by_id[46]["shotDamageLocalMayBeModifiedInBranch"] is True
    assert by_id[964]["explicitSpawnCount"] == {"minimum": 3, "maximum": 4, "distribution": "uniform_integer_inclusive"}
    collision = next(s for s in sources if s["method"] == "Projectile.Colliding")["records"]
    assert next(r for r in collision if r["projectileId"] == 974)["halfLengthTimesProjectileScale"] == 46
    assert all(len(s["sourceMethodSha256"]) == 64 and s["sourceModuleVersionId"] for s in sources)


def line_body():
    call = lambda name, count, instance=False: ("call", (name, count, instance, True))
    center = [("ldarg", 0), call("Terraria.Entity.get_Center", 0, True)]
    delta = [("ldloc", 34), ("ldloc", 32), call("Microsoft.Xna.Framework.Vector2.op_Multiply", 2)]
    return [("ldarg", 0), ("ldfld", "Terraria.Projectile.rotation"), ("const", 0.0), ("stloc", 31),
            ("const", 46.0), ("ldarg", 0), ("ldfld", "Terraria.Projectile.scale"), ("mul",), ("stloc", 32),
            ("const", 8.0), ("stloc", 33), call("Terraria.Utils.ToRotationVector2", 1), ("stloc", 34),
            ("ldarg", 2), call("Terraria.Utils.TopLeft", 1), ("ldarg", 2), call("Terraria.Utils.Size", 1)] + center + delta + [
            call("Microsoft.Xna.Framework.Vector2.op_Subtraction", 2)] + center + delta + [call("Microsoft.Xna.Framework.Vector2.op_Addition", 2),
            ("ldloc", 33), ("ldarg", 0), ("ldfld", "Terraria.Projectile.scale"), ("mul",), ("ldloca", 31),
            call("Terraria.Collision.CheckAABBvLineCollision", 6), ("ret",)]


def collision_program(body):
    return program([("ldarg", 0), ("ldfld", "Terraria.Projectile.type"), ("const", 123), ("bne", "outside")] + body + [("label", "outside"), ("ret",)])


def test_line_arguments_keep_live_scale_and_refuse_unknown_mutations():
    result = analysis.line_collision_facts(collision_program(line_body()))
    assert result[0]["halfLengthTimesProjectileScale"] == 46
    assert result[0]["lineWidthTimesProjectileScale"] == 8
    for change in [[("ldloca", 32), ("call", ("unknown.mutate", 1, False, False))],
                   [("const", 99), ("stloc", 32)], [("ret",)],
                   [("call", ("unknown.mutate_scale", 0, False, False))]]:
        assert analysis.line_collision_facts(collision_program(change + line_body())) == []


def test_collision_setup_cannot_be_bypassed_by_control_flow():
    body = line_body()
    body.insert(13, ("label", "arguments"))
    assert analysis.line_collision_facts(collision_program([("br", "arguments")] + body)) == []


def test_external_control_flow_cannot_bypass_type_guard():
    body = [("label", "inside")] + spawn() + [("ret",)]
    assert analysis.shoot_facts(program([("br", "inside")] + wrap(body))) == []
