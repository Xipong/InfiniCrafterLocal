"""Weapon category and native source rules are read-only evidence, not ammo examples."""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/generate"))


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_ammo_source_rules_survive_real_author_serialization(monkeypatch, mode):
    from infini_local.core import llm_config
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    reference = {
        "status": "source_inspected", "ammoProjectileRelation": "conditionally_replaced",
        "stages": [{"method": "Player.PickAmmo", "rules": [{
            "whenInputProjectileId": 1, "outputProjectileId": 932,
            "sourceStoreIlOffset": 396}]}],
        "unknowns": ["player equipment", "opaque GlobalItem.Shoot"],
        "scope": "Source parent evidence, not mandatory child behavior",
    }
    parent = {"type": 4953, "name": "Source", "ammoRaw": {
        "mode": "weapon_uses_ammo", "ammoId": 40, "ammoCategoryName": "Arrow",
        "projectileSemanticsReference": reference,
        "candidateProjectileBindings": [{"inputProjectileId": 1, "sourceRuleOutputProjectileId": 932, "includeInputProjectileProfile": False}],
        "nativeReplacementProjectileRaw": [{"type": 932, "source": "source_rule_not_final_shot", "tileCollide": True}],
        "playerInventoryAmmoRaw": [{"type": 40, "shoot": 1, "stack": 99,
                                     "pickAmmoHookReference": {"hooks": [{"shape": "literal_projectile_replacement", "outputProjectileId": 181}], "scope": "candidate only"}}],
    }}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {"type": 1, "name": "Other"}, "source-ammo", model_name="offline-test-model")
    assert request["response_format"]["type"] == mode
    ammo = expand_native_source_references(request_dossier(request))["parents"]["A"]["packet"]["raw"]["ammo"]
    assert ammo["projectileSemanticsReference"] == reference
    assert ammo["ammoCategoryName"] == "Arrow"
    assert set(ammo) == {"mode", "ammoId", "ammoCategoryName", "projectileSemanticsReference", "nativeReplacementProjectileRaw"}
    assert ammo["nativeReplacementProjectileRaw"] == parent["ammoRaw"]["nativeReplacementProjectileRaw"]
    assert parent == before


def assert_native_prepare_ammo_packet(packet):
    """CPU harness replay assertion, called with its actual Prepare JSON export."""
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    before = copy.deepcopy(packet)
    request, _, _ = build_initial_author_request(packet["itemA"], packet["itemB"], "native-ammo-source-replay", model_name="offline-test-model")
    dossier = expand_native_source_references(request_dossier(request))
    for side, expected in (("A", "replaced"), ("B", "retained_with_native_item_delivery")):
        raw = dossier["parents"][side]["packet"]["raw"]["ammo"]
        native = packet["item" + side]["ammoRaw"]["projectileSemanticsReference"]
        assert raw["projectileSemanticsReference"] == native
        assert native["ammoProjectileRelation"] == expected
        assert native["finalShotOutcome"] == "unknown_without_gameplay_execution"
        assert native["stages"][0]["hookDispatchTrace"]
        assert native["unknowns"]
        assert raw["ammoCategoryName"] == packet["item" + side]["ammoRaw"]["ammoCategoryName"]
        assert "playerInventoryAmmoRaw" not in raw
    a = dossier["parents"]["A"]["packet"]["raw"]["ammo"]["projectileSemanticsReference"]
    assert a["stages"][1]["rules"][0]["outputProjectileId"] == 357
    ammo_a = dossier["parents"]["A"]["packet"]["raw"]["ammo"]
    profiles = ammo_a["nativeReplacementProjectileRaw"]
    assert [profile["type"] for profile in profiles] == [357]
    assert profiles[0]["penetrate"] == 6
    assert profiles[0]["timeLeft"] == 600
    assert profiles[0]["extraUpdates"] == 2
    assert profiles[0]["attackReference"]
    assert "candidateProjectileBindings" not in ammo_a
    b = dossier["parents"]["B"]["packet"]["raw"]["ammo"]["projectileSemanticsReference"]
    assert b["stages"][1]["spawnOriginSetups"][0]["initialYRelativeToMountedCenterPx"] == -600
    assert packet == before
    return request["response_format"]["type"]


def assert_native_hellwing_ammo_packet(packet):
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    before = copy.deepcopy(packet)
    request, _, _ = build_initial_author_request(packet["itemA"], packet["itemB"], "native-hellwing-replay", model_name="offline-test-model")
    ammo = expand_native_source_references(request_dossier(request))["parents"]["A"]["packet"]["raw"]["ammo"]
    assert ammo["projectileSemanticsReference"] == packet["itemA"]["ammoRaw"]["projectileSemanticsReference"]
    assert ammo["ammoCategoryName"] == packet["itemA"]["ammoRaw"]["ammoCategoryName"]
    assert "candidateProjectileBindings" not in ammo
    assert "playerInventoryAmmoRaw" not in ammo
    profiles = ammo["nativeReplacementProjectileRaw"]
    assert [profile["type"] for profile in profiles] == [485]
    assert (profiles[0]["penetrate"], profiles[0]["timeLeft"], profiles[0]["extraUpdates"]) == (-1, 1200, 0)
    assert profiles[0]["attackReference"]
    assert packet == before
    return request["response_format"]["type"]


def test_exact_native_ammo_rewrite_and_spawn_extraction():
    from generate_native_ammo_facts import extract
    installed = Path(os.environ.get("INFINI_NATIVE_AMMO_ASSEMBLY", "/mnt/c/Program Files (x86)/Steam/steamapps/common/tModLoader/tModLoader.dll"))
    if not installed.exists():
        pytest.skip("exact native source assembly unavailable")
    sources = extract(installed)
    pick = next(s for s in sources if s["method"] == "Player.PickAmmo")
    rules = {r["itemId"]: r["rules"] for r in pick["records"]}
    assert rules[4381][0]["outputProjectileId"] == 819
    assert "whenInputProjectileId" not in rules[4381][0]
    assert rules[4953][0]["whenInputProjectileId"] == 1
    assert rules[4953][0]["outputProjectileId"] == 932
    shoot = next(s for s in sources if s["method"] == "Player.ItemCheck_Shoot")
    rows = {r["itemId"]: r for r in shoot["records"]}
    assert rows[120]["rules"][0]["whenInputProjectileId"] == 1
    assert rows[120]["rules"][0]["outputProjectileId"] == 2
    assert rows[3029]["spawnSites"][0]["projectileBasis"] == "current_shot_projectile"
    assert rows[4381]["spawnSites"][0]["projectileBasis"] == "current_shot_projectile"
    assert rows[3029]["spawnSites"][0]["nativeItemSpecificDelivery"] is True
    # IDs above are regression assertions against actual source, never analyzer routers.
    assert pick["sourceModuleVersionId"] == shoot["sourceModuleVersionId"]
    assert pick["defaultProjectileSelection"]["ammoShootStoreIlOffset"] > 0
    assert {r["nativeCategoryField"] for r in pick["defaultProjectileSelection"]["categoryOffsetSelectors"]} == {"Terraria.ID.AmmoID.Rocket", "Terraria.ID.AmmoID.Solution"}
    assert rows[3029]["spawnOriginSetups"][0]["initialYRelativeToMountedCenterPx"] == -600
    assert rows[3029]["spawnSites"][0]["spawnCountBounds"]["minimum"] == 2
    assert rows[3029]["spawnSites"][0]["spawnCountBounds"]["maximum"] == 4
    assert rows[2223]["rules"][0]["outputProjectileId"] == 357
    assert rules[3019][0]["whenInputProjectileId"] == 1
    assert rules[3019][0]["outputProjectileId"] == 485
    assert 39 not in shoot["itemTypeMentions"]  # Plain native stock bow follows default path.
    assert 4381 in shoot["itemTypeMentions"]
    selection = pick["defaultProjectileSelection"]
    assert selection["specificMatchLookupFirst"] is True
    assert selection["nonPositiveAmmoShoot"] == "retain_weapon_shoot"
    assert selection["specificMatchLookupCertificate"].endswith(":" + pick["sourceModuleVersionId"])
    from generate_native_hit_status import decode
    from generate_native_ammo_facts import native_ammo_category_literals
    from native_ammo_fact_analysis import default_ammo_selection
    from native_hit_status_analysis import Instruction as I
    code = decode(installed, "Player", "PickAmmo", allow_opaque=True, overload_index=1)[0]
    categories = native_ammo_category_literals(installed)
    lookup = next(n for n, ins in enumerate(code) if ins.op == "call" and ins.arg[0] == "Terraria.Player.PickAmmo_TryFindingSpecificMatches")
    # Isolated familiar stores are insufficient: altered table precedence,
    # extra guards and external entry into an arm must all refuse certification.
    broken_fallthrough = list(code)
    guard = code[lookup + 1]
    broken_fallthrough[lookup + 1] = I(guard.offset, guard.op, guard.arg + 1)
    for changed in (broken_fallthrough,
                    code[:lookup + 1] + [I(guard.offset - 1, "opaque", "extra_condition")] + code[lookup + 1:],
                    [I(-1, "br", code[lookup + 2].offset)] + code):
        with pytest.raises(ValueError):
            default_ammo_selection(changed, categories)
    dispatch = {row["method"]: row for row in pick["hookDispatchTrace"]}
    assert dispatch["Terraria.ModLoader.ItemLoader.PickAmmo"]["directHookCalls"] == ["Terraria.ModLoader.ModItem.PickAmmo", "Terraria.ModLoader.GlobalItem.PickAmmo"]
    assert dispatch["Terraria.ModLoader.ItemLoader.ModifyShootStats"]["directHookCalls"] == ["Terraria.ModLoader.ModItem.ModifyShootStats", "Terraria.ModLoader.GlobalItem.ModifyShootStats"]
    assert dispatch["Terraria.ModLoader.ItemLoader.Shoot"]["directHookCalls"] == ["Terraria.ModLoader.GlobalItem.Shoot", "Terraria.ModLoader.ModItem.Shoot"]


def test_unknown_control_flow_does_not_become_unconditional_replacement():
    from native_ammo_fact_analysis import literal_rewrite
    from native_hit_status_analysis import Instruction as I
    code = [I(1, "ldarg", 2), I(2, "const", 12), I(3, "stind.i4", None)]
    assert literal_rewrite(code, ("argument", 2)) == [{"outputProjectileId": 12, "sourceStoreIlOffset": 3}]
    assert literal_rewrite([I(0, "call", ("Opaque.Check", 0, False, True)), I(1, "brfalse", 5), *code], ("argument", 2)) is None


def _nested_ammo_rewrite(*, pick=False, outer=(), inner=(), gap=(), entry=None):
    """Synthetic source, with every label bound after the requested mutation."""
    from native_hit_status_analysis import Instruction as I
    item_arg, read = (1, [("ldarg", 2), ("ldind.i4", None)]) if pick else (2, [("ldloc", 0)])
    pairs = [] if pick else [("ldarg", 2), ("ldfld", "Terraria.Item.shoot"), ("stloc", 0)]
    labels = {}
    if entry is not None:
        pairs.append(("br", entry))
    for condition in outer:
        labels.setdefault("outer", len(pairs))
        pairs += read + [("const", condition), ("bne", "end")]
    pairs += list(gap)
    labels["item"] = len(pairs)
    pairs += [("ldarg", item_arg), ("ldfld", "Terraria.Item.type"), ("const", 90210), ("bne", "end")]
    labels["body"] = len(pairs)
    for condition in inner:
        pairs += read + [("const", condition), ("bne", "end")]
    pairs += [("ldarg", 2)] if pick else []
    labels["literal"] = len(pairs)
    pairs += [("const", 73), ("stind.i4", None) if pick else ("stloc", 0)]
    labels["end"] = len(pairs)
    pairs += [("ret", None)]
    return [I(n, op, labels.get(arg, arg) if isinstance(arg, str) else arg)
            for n, (op, arg) in enumerate(pairs)]


@pytest.mark.parametrize("pick", [False, True])
@pytest.mark.parametrize("outer,inner", [([17], []), ([17, 17], []), ([17], [17]), ([], [17, 17])])
def test_native_ammo_nested_equalities_preserve_exact_input(pick, outer, inner):
    from native_ammo_fact_analysis import ammo_method_facts
    rows = ammo_method_facts(_nested_ammo_rewrite(pick=pick, outer=outer, inner=inner), "PickAmmo" if pick else "ItemCheck_Shoot")
    assert len(rows) == 1
    assert len(rows[0]["rules"]) == 1
    assert rows[0]["rules"][0]["whenInputProjectileId"] == 17
    assert rows[0]["rules"][0]["outputProjectileId"] == 73
    assert rows[0]["unrecognizedProjectileWriteOffsets"] == []


@pytest.mark.parametrize("mutation", [
    {"outer": [17, 18]},
    {"outer": [17], "inner": [18]},
    {"inner": [17, 18]},
    {"outer": [17], "gap": [("const", 18), ("stloc", 0)]},
    {"outer": [17], "gap": [("ldloca", 0), ("call", ("Opaque.Mutate", 1, False, False))]},
    {"gap": [("call", ("Opaque.Check", 0, False, True)), ("brfalse", "end")]},
    {"gap": [("ldloc", 0), ("const", 17), ("beq", "end")]},
    {"outer": [17], "entry": "item"},
    {"outer": [17], "entry": "body"},
    {"outer": [17], "entry": "literal"},
])
def test_native_ammo_unproved_enclosing_shapes_remain_unknown(mutation):
    from native_ammo_fact_analysis import ammo_method_facts, item_type_mentions
    code = _nested_ammo_rewrite(**mutation)
    rows = ammo_method_facts(code, "ItemCheck_Shoot")
    assert item_type_mentions(code, 2) == [90210]
    assert all(not row["rules"] for row in rows)
    # A rejected type block remains an unmodeled item mention; a recognized
    # item block must retain its unproved write, never imply input retention.
    assert all(row["unrecognizedProjectileWriteOffsets"] or row["unresolvedLiteralWrites"] for row in rows)


@pytest.mark.parametrize("entry,ownership", [(None, "proved_item_guard"), ("body", "unproved_item_guard")])
def test_native_ammo_unknown_gate_preserves_only_source_literal(entry, ownership):
    from native_ammo_fact_analysis import ammo_method_facts
    code = _nested_ammo_rewrite(entry=entry, gap=[("call", ("Opaque.Check", 0, False, True)), ("brfalse", "end")])
    row, = ammo_method_facts(code, "ItemCheck_Shoot")
    assert row["rules"] == []
    site, = row["unresolvedLiteralWrites"]
    assert site["outputProjectileId"] == 73
    assert site["applicability"] == "unknown"
    assert site["ownershipStatus"] == ownership
    assert site["reason"]
    assert "whenInputProjectileId" not in site


@pytest.mark.parametrize("pick", [False, True])
def test_native_ammo_contradictory_inner_guards_keep_unknown_literal(pick):
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_nested_ammo_rewrite(pick=pick, inner=[17, 18]), "PickAmmo" if pick else "ItemCheck_Shoot")
    assert row["rules"] == []
    site, = row["unresolvedLiteralWrites"]
    assert site["outputProjectileId"] == 73
    assert site["sourceInputProjectileIds"] == [17, 18]
    assert site["reason"] == "contradictory_projectile_guards"
    assert site["applicability"] == "unknown"
    assert "whenInputProjectileId" not in site


def test_native_ammo_byref_overwrite_prevents_inherited_input_predicate():
    from native_ammo_fact_analysis import ammo_method_facts
    code = _nested_ammo_rewrite(pick=True, outer=[17], gap=[("ldarg", 2), ("const", 18), ("stind.i4", None)])
    row, = ammo_method_facts(code, "PickAmmo")
    assert row["rules"] == []
    site, = row["unresolvedLiteralWrites"]
    assert site["outputProjectileId"] == 73
    assert site["reason"] == "intervening_instructions_after_enclosing_guard"
    assert site["applicability"] == "unknown"
    assert "whenInputProjectileId" not in site


@pytest.mark.parametrize("foreign_entry", [False, True])
def test_native_ammo_known_rule_does_not_hide_later_opaque_write(foreign_entry):
    from native_ammo_fact_analysis import ammo_method_facts
    from native_hit_status_analysis import Instruction as I
    pairs = [("ldarg", 2), ("ldfld", "Terraria.Item.shoot"), ("stloc", 0),
             ("ldarg", 2), ("ldfld", "Terraria.Item.type"), ("const", 90210), ("bne", 9),
             ("const", 73), ("stloc", 0),
             ("ldarg", 2), ("ldfld", "Terraria.Item.type"), ("const", 90210), ("bne", 15),
             ("call", ("Opaque.Compute", 0, False, True)), ("stloc", 0)]
    if foreign_entry:
        pairs += [("call", ("Opaque.Check", 0, False, True)), ("brtrue", 13)]
    pairs += [("ret", None)]
    row, = ammo_method_facts([I(n, op, arg) for n, (op, arg) in enumerate(pairs)], "ItemCheck_Shoot")
    assert row["rules"] == [{"outputProjectileId": 73, "sourceStoreIlOffset": 8, "sourceGuardIlOffset": 6}]
    assert row["unrecognizedProjectileWriteOffsets"] == [14]
    assert row["unresolvedLiteralWrites"] == []
