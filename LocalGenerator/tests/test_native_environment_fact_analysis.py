"""Negative controls for literal conditional native-environment extraction."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/generate"))
from native_hit_status_analysis import Instruction as I
from native_environment_fact_analysis import aura_branches, scene_regen_additions
import generate_native_environment_facts as generator


def code(ops):
    return [I(n, op, arg) for n, (op, arg) in enumerate(ops)]


def aura():
    return code([("ldloca", 7), ("call", ("Terraria.Tile.get_type", 0, True, True)), ("ldind.u2", None),
        ("const", 215), ("bne", 13), ("ldloca", 7), ("call", ("Terraria.Tile.get_frameY", 0, True, True)),
        ("ldind.i2", None), ("const", 36), ("bge", 13), ("ldarg", 0), ("const", 1),
        ("call", ("Terraria.SceneMetrics.set_HasCampfire", 1, True, False)), ("ret", None)])


def regen():
    return code([("ldarg", 0), ("ldfld", "Terraria.Entity.whoAmI"), ("ldsfld", "Terraria.Main.myPlayer"),
        ("bne", 13), ("ldsfld", "Terraria.Main.SceneMetrics"), ("call", ("Terraria.SceneMetrics.get_HasCampfire", 0, True, True)),
        ("brfalse", 13), ("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.Player.lifeRegen"), ("const", 1),
        ("add", None), ("stfld", "Terraria.Player.lifeRegen"), ("nop", None), ("ret", None), ("ret", None)])


def test_tile_frame_condition_is_not_unconditional_item_bonus():
    rows = aura_branches(aura())
    assert rows[0]["tileId"] == 215
    assert rows[0]["tileFrameConditions"] == [{"field": "frameY", "comparison": "less_than", "value": 36}]
    for at, replacement in [(9, I(9, "bge", 12)), (11, I(11, "const", 0)), (5, I(5, "ldloca", 8))]:
        changed = aura(); changed[at] = replacement
        assert aura_branches(changed) == []
    assert aura_branches([I(-1, "br", 10), *aura()]) == []


def test_regen_component_requires_local_player_and_scene_gates():
    assert scene_regen_additions(regen())["HasCampfire"]["add"] == 1
    for at, replacement in [(3, I(3, "bne", 12)), (6, I(6, "brfalse", 15)),
                            (12, I(12, "stfld", "Terraria.Player.statLife"))]:
        changed = regen(); changed[at] = replacement
        assert scene_regen_additions(changed) == {}
    assert scene_regen_additions([I(-1, "br", 7), *regen()]) == {}


def test_generated_environment_catalog_exact_projection():
    data = json.loads(generator.REPORT.read_text())
    assert generator.OUTPUT.read_text() == generator.render(data)
    by_tile = {r["tileId"]: r for r in data["auras"]}
    assert by_tile[215]["regenerationComponent"]["add"] == 1
    assert len(data["auras"]) == 5
    assert all(len(s["assemblySha256"]) == 64 and len(s["sourceMethodSha256"]) == 64 for s in data["sources"])
