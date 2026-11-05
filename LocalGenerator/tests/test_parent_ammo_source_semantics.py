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


def _state_conditioned_ammo_rewrite(*, mutate=(), outer=(), guard_op="bne", entry=None, tail=()):
    from native_hit_status_analysis import Instruction as I
    pairs = [("ldarg", 2), ("ldfld", "Terraria.Item.shoot"), ("stloc", 0)]
    if entry:
        pairs.append(("br", entry))
    pairs += list(outer)
    pairs += [("ldarg", 2), ("ldfld", "Terraria.Item.type"), ("const", 90123), ("bne", "end")]
    labels = {"body": len(pairs)}
    pairs += [("ldarg", 0), ("ldfld", "Fixture.Player.maximum"), ("ldarg", 0),
              ("ldfld", "Fixture.Player.remaining"), ("sub", None), ("const", 3), ("div", None), ("stloc", 7)]
    labels["defined"] = len(pairs)
    pairs += list(mutate)
    labels["test"] = len(pairs)
    pairs += [("ldloc", 7), ("const", 4), (guard_op, "skip")]
    labels["literal"] = len(pairs)
    pairs += [("const", 876), ("stloc", 0)]
    labels["skip"] = len(pairs)
    pairs += list(tail)
    labels["end"] = len(pairs)
    pairs += [("ret", None)]
    return [I(n, op, [labels[arg]] if op == "switch" else labels.get(arg, arg) if isinstance(arg, str) else arg) for n, (op, arg) in enumerate(pairs)]


def test_native_ammo_cfg_extracts_only_controlling_snapshot_expression():
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(), "ItemCheck_Shoot")
    rule, = row["rules"]
    assert rule["outputProjectileId"] == 876
    condition = rule["whenSourceCondition"]
    assert condition["kind"] == "branch"
    assert condition["opcode"] == "bne" and condition["taken"] is False
    assert condition["right"]["value"] == 4
    snapshot = condition["left"]
    assert snapshot["kind"] == "local_definition" and snapshot["local"] == 7
    assert snapshot["scope"] == "value_at_store"
    value = snapshot["value"]
    assert value["operator"] == "div" and value["right"]["value"] == 3
    assert value["left"]["operator"] == "sub"
    assert value["left"]["left"]["member"] == "Fixture.Player.maximum"
    assert value["left"]["right"]["member"] == "Fixture.Player.remaining"
    assert value["left"]["left"]["sourceIlOffset"] != value["left"]["right"]["sourceIlOffset"]
    assert row["unrecognizedProjectileWriteOffsets"] == []


@pytest.mark.parametrize("mutation", [
    {"mutate": [("const", 9), ("stloc", 7)]},
    {"mutate": [("ldloca", 7), ("call", ("Opaque.Mutate", 1, False, False))]},
    {"mutate": [("ldloca", 0), ("call", ("Opaque.Mutate", 1, False, False))]},
    {"mutate": [("call", ("Opaque.Check", 0, False, True)), ("brfalse", "skip")]},
    {"mutate": [("br", "defined")]},
    {"outer": [("call", ("Opaque.Check", 0, False, True)), ("brfalse", "end")]},
    {"entry": "literal"},
    {"entry": "test"},
    {"guard_op": "switch"},
])
def test_native_ammo_cfg_refuses_ambiguous_control_and_values(mutation):
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(**mutation), "ItemCheck_Shoot")
    assert row["rules"] == []
    assert row["unrecognizedProjectileWriteOffsets"]


def test_native_ammo_cfg_known_store_keeps_later_opaque_write_unknown():
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(tail=[("call", ("Opaque.Compute", 0, False, True)), ("stloc", 0)]), "ItemCheck_Shoot")
    assert len(row["rules"]) == 1
    assert len(row["unrecognizedProjectileWriteOffsets"]) == 1
    assert row["unrecognizedProjectileWriteOffsets"][0] > row["rules"][0]["sourceStoreIlOffset"]


def test_exact_native_state_guard_rewrite_extraction():
    from generate_native_ammo_facts import extract
    installed = Path(os.environ.get("INFINI_NATIVE_AMMO_ASSEMBLY", "/missing-native-assembly"))
    if not installed.exists():
        pytest.skip("exact native source assembly unavailable")
    sources = extract(installed)
    rows = {r["itemId"]: r for s in sources if s["method"] == "Player.ItemCheck_Shoot" for r in s["records"]}
    rule, = rows[4953]["rules"]
    assert rule["outputProjectileId"] == 932 and rule["sourceStoreIlOffset"] == 10873
    predicate = rule["whenSourceCondition"]
    assert predicate["sourceBranchIlOffset"] == 10866
    assert predicate["opcode"] == "bne" and predicate["taken"] is False
    value = predicate["left"]["value"]
    assert predicate["left"]["sourceStoreIlOffset"] == 10599
    assert value["operator"] == "div" and value["right"]["value"] == 2
    assert value["left"]["operator"] == "sub"
    assert value["left"]["left"]["member"] == "Terraria.Player.itemAnimationMax"
    assert value["left"]["right"]["member"] == "Terraria.Player.itemAnimation"
    assert rows[4953]["unrecognizedProjectileWriteOffsets"] == []
    assert rows[3859]["rules"][0]["outputProjectileId"] == 710
    assert "whenSourceCondition" not in rows[3859]["rules"][0]
    assert rows[3542]["unrecognizedProjectileWriteOffsets"] == [319]
    assert rows[1157]["unrecognizedProjectileWriteOffsets"] == [16434]


def test_native_ammo_cfg_drops_irrelevant_opaque_diamond_but_not_controlling_call():
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(mutate=[("call", ("Opaque.Check", 0, False, True)), ("brfalse", "test"), ("const", 123), ("stloc", 12)]), "ItemCheck_Shoot")
    assert len(row["rules"]) == 1
    assert row["rules"][0]["whenSourceCondition"]["left"]["local"] == 7
    assert row["unrecognizedProjectileWriteOffsets"] == []


@pytest.mark.parametrize("mutate", [
    [("ldloc", 7), ("const", 5), ("bne", "skip")],
    [("call", ("Opaque.Check", 0, False, True)), ("brfalse", "test"), ("const", 9), ("stloc", 7)],
    [("call", ("Opaque.Check", 0, False, True)), ("brtrue", "defined")],
    [("br", 99999)],
])
def test_native_ammo_cfg_rejects_contradiction_competing_definition_loop_and_bad_target(mutate):
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(mutate=mutate), "ItemCheck_Shoot")
    assert row["rules"] == []
    assert row["unrecognizedProjectileWriteOffsets"]


def test_native_ammo_cfg_exception_handler_metadata_is_not_discarded():
    from native_ammo_fact_analysis import ammo_method_facts
    from generate_native_hit_status import DecodedInstructions
    code = DecodedInstructions(_state_conditioned_ammo_rewrite())
    code.has_exception_handlers = True
    with pytest.raises(ValueError, match="exception handlers"):
        ammo_method_facts(code, "ItemCheck_Shoot")


def test_native_ammo_cfg_ignores_only_disconnected_sibling_spans():
    from native_ammo_fact_analysis import ammo_method_facts
    from native_hit_status_analysis import Instruction as I
    original = _state_conditioned_ammo_rewrite()
    # A sibling arm can jump past our item or return, but cannot reach it.
    prefix = [I(-7, "ldarg", 2), I(-6, "ldfld", "Terraria.Item.type"), I(-5, "const", 77777), I(-4, "bne", 0),
              I(-3, "call", ("Opaque.Check", 0, False, True)), I(-2, "brtrue", original[-1].offset), I(-1, "ret", None)]
    rows = ammo_method_facts(prefix + original, "ItemCheck_Shoot")
    row = next(row for row in rows if row["itemId"] == 90123)
    assert len(row["rules"]) == 1 and row["unrecognizedProjectileWriteOffsets"] == []
    # If that arm can fall through into our item, its spanning guard is real.
    entering = prefix[:-1] + [I(-1, "nop", None)] + original
    row = next(row for row in ammo_method_facts(entering, "ItemCheck_Shoot") if row["itemId"] == 90123)
    assert row["rules"] == [] and row["unrecognizedProjectileWriteOffsets"]


@pytest.mark.parametrize("branch", ["blt", "blt.un", "bge", "bge.un"])
def test_native_ammo_cfg_preserves_signedness_and_source_snapshot(branch):
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(guard_op=branch, mutate=[("ldarg", 0), ("const", 0), ("stfld", "Fixture.Player.remaining")]), "ItemCheck_Shoot")
    rule, = row["rules"]
    predicate = rule["whenSourceCondition"]
    assert predicate["opcode"] == branch and predicate["taken"] is False
    snapshot = predicate["left"]
    assert snapshot["scope"] == "value_at_store"
    assert snapshot["sourceStoreIlOffset"] < snapshot["sourceIlOffset"]
    assert snapshot["value"]["left"]["right"]["sourceIlOffset"] < snapshot["sourceStoreIlOffset"]


def test_native_ammo_cfg_header_reentry_cannot_forge_item_ownership():
    from native_ammo_fact_analysis import ammo_method_facts
    from native_hit_status_analysis import Instruction as I
    code = _state_conditioned_ammo_rewrite()
    # The later path enters after Item.type was supposed to have been loaded.
    end = code[-1].offset
    code = code[:-1] + [I(end, "const", 90123), I(end + 1, "br", 5)]
    row, = ammo_method_facts(code, "ItemCheck_Shoot")
    assert row["rules"] == []
    assert row["unrecognizedProjectileWriteOffsets"]


def test_native_ammo_cfg_retains_alternative_paths_and_bounds_formula_output():
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(mutate=[("ldloc", 7), ("const", 5), ("beq", "literal")]), "ItemCheck_Shoot")
    condition = row["rules"][0]["whenSourceCondition"]
    assert condition["kind"] == "if" and condition["then"] is True
    assert condition["condition"]["opcode"] == "beq" and condition["condition"]["right"]["value"] == 5
    assert condition["else"]["opcode"] == "bne" and condition["else"]["right"]["value"] == 4
    # Bound the real output tree, not only instruction count.
    row, = ammo_method_facts(_state_conditioned_ammo_rewrite(mutate=[("ldloc", 7), ("const", 4), ("bne", "skip")] * 20), "ItemCheck_Shoot")
    assert row["rules"] == [] and row["unrecognizedProjectileWriteOffsets"]


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_native_state_condition_survives_actual_prepare_author_request(monkeypatch, mode):
    import json
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    path = Path(os.environ.get("INFINI_PARENT_STATE_PACKET", "/missing-native-prepare-packet"))
    if not path.exists():
        pytest.skip("actual native state-conditioned Prepare packet unavailable")
    packet = json.loads(path.read_text())
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request(packet["itemA"], packet["itemB"], "state-source-roundtrip", model_name="offline-test-model")
    raw = expand_native_source_references(request_dossier(request))["parents"]["A"]["packet"]["raw"]["ammo"]
    expected = packet["itemA"]["ammoRaw"]
    assert raw["projectileSemanticsReference"] == expected["projectileSemanticsReference"]
    # Existing Author projection compacts attack tables and omits unrelated
    # snapshot fields. This change's exact contract is the two source sites and
    # their condition, both beside the profile and in the stage reference.
    profile, = raw["nativeReplacementProjectileRaw"]
    native, = expected["nativeReplacementProjectileRaw"]
    assert profile["type"] == native["type"]
    assert profile["sourceReferences"] == native["sourceReferences"]
    assert profile["profileScope"] == native["profileScope"]
    assert (profile["penetrate"], profile["timeLeft"], profile["extraUpdates"]) == (5, 120, 0)
    source = raw["projectileSemanticsReference"]
    assert source["ammoProjectileRelation"] == "conditionally_replaced"
    assert source["stages"][1]["rules"][0]["whenSourceCondition"]["left"]["scope"] == "value_at_store"
    assert len(raw["nativeReplacementProjectileRaw"][0]["sourceReferences"]) == 2
