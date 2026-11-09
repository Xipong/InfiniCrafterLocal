"""Ammo identity is an input; native source rules are separate read-only evidence."""
from __future__ import annotations
from suite_paths import REPO_ROOT

import copy
import json
import re
import os
import sys
from pathlib import Path

import pytest

ROOT = REPO_ROOT
sys.path.insert(0, str(ROOT / "tools/generate"))


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_ammo_source_rules_survive_real_author_serialization(monkeypatch, mode):
    from infini_local.core import llm_config
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    reference = {
        "status": "source_inspected", "ammoProjectileRelation": "conditionally_replaced",
        "stages": [{"method": "Player.PickAmmo", "rules": [{
            "whenInputProjectileId": 1, "outputProjectileId": 932,
            "sourceStoreIlOffset": 396}]}],
        "unknowns": ["player equipment", "opaque GlobalItem.Shoot"],
        "scope": "Source parent evidence, not mandatory child behavior",
    }
    parent = {"type": 4953, "name": "Source", "ammoRaw": {
        "mode": "weapon_uses_ammo", "ammoId": 40,
        "projectileSemanticsReference": reference,
        "candidateProjectileBindings": [{"inputProjectileId": 1, "sourceRuleOutputProjectileId": 932, "includeInputProjectileProfile": False}],
        "nativeReplacementProjectileRaw": [{"type": 932, "source": "source_rule_not_final_shot", "tileCollide": True}],
        "playerInventoryAmmoRaw": [{"type": 40, "shoot": 1, "stack": 99,
                                     "pickAmmoHookReference": {"hooks": [{"shape": "literal_projectile_replacement", "outputProjectileId": 181}], "scope": "candidate only"}}],
    }}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {"type": 1, "name": "Other"}, "source-ammo", model_name="offline-test-model")
    assert request["response_format"]["type"] == mode
    ammo = request_dossier(request)["parents"]["A"]["packet"]["raw"]["ammo"]
    assert ammo["projectileSemanticsReference"] == reference
    assert ammo["candidateProjectileBindings"] == parent["ammoRaw"]["candidateProjectileBindings"]
    assert ammo["nativeReplacementProjectileRaw"] == parent["ammoRaw"]["nativeReplacementProjectileRaw"]
    assert ammo["playerInventoryAmmoRaw"][0]["pickAmmoHookReference"] == parent["ammoRaw"]["playerInventoryAmmoRaw"][0]["pickAmmoHookReference"]
    assert "stack" not in ammo["playerInventoryAmmoRaw"][0]
    assert parent == before


def assert_native_prepare_ammo_packet(packet):
    """CPU harness replay assertion, called with its actual Prepare JSON export."""
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    before = copy.deepcopy(packet)
    request, _, _ = build_initial_author_request(packet["itemA"], packet["itemB"], "native-ammo-source-replay", model_name="offline-test-model")
    dossier = request_dossier(request)
    for side, expected in (("A", "replaced"), ("B", "retained_with_native_item_delivery")):
        raw = dossier["parents"][side]["packet"]["raw"]["ammo"]
        native = packet["item" + side]["ammoRaw"]["projectileSemanticsReference"]
        assert raw["projectileSemanticsReference"] == native
        assert native["ammoProjectileRelation"] == expected
        assert native["finalShotOutcome"] == "unknown_without_gameplay_execution"
        assert native["stages"][0]["hookDispatchTrace"]
        assert native["unknowns"]
        assert raw["playerInventoryAmmoRaw"][0]["shoot"] == 1
        assert "stack" not in raw["playerInventoryAmmoRaw"][0]
    a = dossier["parents"]["A"]["packet"]["raw"]["ammo"]["projectileSemanticsReference"]
    assert a["stages"][1]["rules"][0]["outputProjectileId"] == 357
    ammo_a = dossier["parents"]["A"]["packet"]["raw"]["ammo"]
    assert ammo_a["playerInventoryProjectileRaw"] == []
    assert ammo_a["fallbackProjectileRaw"] == []
    assert ammo_a["nativeReplacementProjectileRaw"][0]["type"] == 357
    assert ammo_a["playerInventoryAmmoRaw"][0]["damage"] == packet["itemA"]["ammoRaw"]["playerInventoryAmmoRaw"][0]["damage"]
    b = dossier["parents"]["B"]["packet"]["raw"]["ammo"]["projectileSemanticsReference"]
    assert b["stages"][1]["spawnOriginSetups"][0]["initialYRelativeToMountedCenterPx"] == -600
    assert packet == before
    return request["response_format"]["type"]


def assert_native_hellwing_ammo_packet(packet):
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    before = copy.deepcopy(packet)
    request, _, _ = build_initial_author_request(packet["itemA"], packet["itemB"], "native-hellwing-replay", model_name="offline-test-model")
    ammo = request_dossier(request)["parents"]["A"]["packet"]["raw"]["ammo"]
    bindings = [row for row in ammo["candidateProjectileBindings"] if row["inventorySlot"] in (54, 55)]
    assert [(row["inputProjectileId"], row["sourceRuleOutputProjectileId"]) for row in bindings] == [(1, 485), (2, 2)]
    assert [row["type"] for row in ammo["playerInventoryProjectileRaw"]] == [2]
    assert [row["type"] for row in ammo["nativeReplacementProjectileRaw"]] == [485]
    assert [row["shoot"] for row in ammo["playerInventoryAmmoRaw"]] == [1, 2]
    assert all("stack" not in row for row in ammo["playerInventoryAmmoRaw"])
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
@pytest.mark.parametrize("outer,inner", [([], []), ([17], []), ([17, 17], []), ([17], [17]), ([], [17]), ([], [17, 17])])
def test_native_ammo_nested_equalities_preserve_exact_input(pick, outer, inner):
    from native_ammo_fact_analysis import ammo_method_facts
    code = _nested_ammo_rewrite(pick=pick, outer=outer, inner=inner)
    rows = ammo_method_facts(code, "PickAmmo" if pick else "ItemCheck_Shoot")
    row, = rows
    rule = {"outputProjectileId": 73, "sourceStoreIlOffset": code[-2].offset,
            "sourceGuardIlOffset": next(ins.offset for ins in code if ins.op == "const" and ins.arg == 90210) + 1}
    if outer or inner:
        rule["whenInputProjectileId"] = 17
    assert row["rules"] == [rule]
    assert row["unrecognizedProjectileWriteOffsets"] == []


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
    assert all(row["unrecognizedProjectileWriteOffsets"] for row in rows)


@pytest.mark.parametrize("gap", [
    [("ldarg", 2), ("const", 18), ("stind.i4", None)],
    [("ldarg", 2), ("call", ("Opaque.Mutate", 1, False, False))],
])
def test_native_ammo_byref_mutation_does_not_inherit_outer_input(gap):
    from native_ammo_fact_analysis import ammo_method_facts
    row, = ammo_method_facts(_nested_ammo_rewrite(pick=True, outer=[17], gap=gap), "PickAmmo")
    assert row["rules"] == []
    assert row["unrecognizedProjectileWriteOffsets"]


from native_ammo_fact_analysis import ammo_method_facts
from native_hit_status_analysis import Instruction as VariantInstruction


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


def _assert_literal_prepare_ammo(raw, native):
    """Keep the original exact source boundary separately from Author presentation."""
    assert raw["projectileSemanticsReference"] == native["projectileSemanticsReference"]
    assert raw.get("candidateProjectileBindings") == native.get("candidateProjectileBindings")
    for field in ("nativeReplacementProjectileRaw", "nativeFixedProjectileRaw"):
        profiles, originals = raw.get(field, []), native.get(field, [])
        assert len(profiles) == len(originals)
        for profile, original in zip(profiles, originals, strict=True):
            for key in ("type", "sourceReferences", "profileScope", "penetrate", "timeLeft", "extraUpdates"):
                assert profile[key] == original[key]


def _prepare_ammo_mechanics(packet, mode):
    from infini_local.pipelines.author.request import build_initial_author_request
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    before = copy.deepcopy(packet)
    native = packet["itemA"]["ammoRaw"]
    literal = raw_parent_card_for_llm(packet["itemA"])["raw"]["ammo"]
    _assert_literal_prepare_ammo(literal, native)
    request, _, _ = build_initial_author_request(
        packet["itemA"], packet["itemB"], "native-ammo-source-roundtrip", model_name="offline-test-model")
    assert request["response_format"]["type"] == mode
    # This independent observer expands only the documented source sharing.
    # Ammo expressions are not attack tables; do not decode/re-render unrelated graphs.
    raw = expand_native_source_references(request_dossier(request))["parents"]["A"]["packet"]["raw"]
    assert "mechanics" in raw and "ammo" not in raw
    assert packet == before
    return raw["mechanics"], literal


def _assert_ammo_source_metadata(source, original):
    # Keep every non-expression fact, its ordering and multiplicity. The small
    # exclusions below are explicit Author receipt omissions, not a renderer.
    assert {k: v for k, v in source.items() if k != "stages"} == {
        k: v for k, v in original.items() if k != "stages"}
    assert len(source["stages"]) == len(original["stages"])
    receipts = {"sourceMethodSha256", "sourceModuleVersionId", "sourceVerification"}
    transformed = {"rules", "spawnSites", "defaultProjectileSelection", "hookDispatchTrace"}
    for stage, native_stage in zip(source["stages"], original["stages"], strict=True):
        assert stage.keys() == native_stage.keys() - receipts
        assert {k: v for k, v in stage.items() if k not in transformed} == {
            k: v for k, v in native_stage.items() if k not in transformed | receipts}
        if native_stage.get("defaultProjectileSelection") is not None:
            selection, native_selection = stage["defaultProjectileSelection"], native_stage["defaultProjectileSelection"]
            assert {k: v for k, v in selection.items() if k != "categoryOffsetSelectors"} == {
                k: v for k, v in native_selection.items() if k != "categoryOffsetSelectors"}
            assert selection["categoryOffsetSelectors"] == [
                {k: v for k, v in row.items() if k != "sourceStoreIlOffset"}
                for row in native_selection["categoryOffsetSelectors"]]
        else:
            assert stage.get("defaultProjectileSelection") == native_stage.get("defaultProjectileSelection")
        if "hookDispatchTrace" in native_stage:
            assert stage["hookDispatchTrace"] == [
                {k: v for k, v in row.items() if k != "sourceMethodSha256"}
                for row in native_stage["hookDispatchTrace"]]


def _assert_ammo_observations(mechanics, packet, name):
    ammo, native = mechanics["ammoInputs"], packet["itemA"]["ammoRaw"]
    source, original = ammo["projectileSemanticsReference"], native["projectileSemanticsReference"]
    _assert_ammo_source_metadata(source, original)
    assert source["finalShotOutcome"] == "unknown_without_gameplay_execution"
    assert source["unknowns"]
    assert [stage["method"] for stage in source["stages"]] == [stage["method"] for stage in original["stages"]]
    assert source["stages"][0]["spawnSites"] == original["stages"][0]["spawnSites"] == []
    bindings, originals = ammo.get("candidateProjectileBindings", []), native.get("candidateProjectileBindings", [])
    assert len(bindings) == len(originals)
    for binding, original_binding in zip(bindings, originals, strict=True):
        assert {k: v for k, v in binding.items() if k != "matchedSourceRules"} == {
            k: v for k, v in original_binding.items() if k != "matchedSourceRules"}
        matches = binding["matchedSourceRules"]
        assert len(matches) == len(original_binding["matchedSourceRules"])
        for match in matches:
            assert name == "eventide"
            assert match == {"method": "Player.PickAmmo", "rule": {
                "outputProjectileId": 932, "whenInputProjectileId": 1, "sourceGuardIlOffset": 383}}
    if name != "terra":
        rows = ammo["playerInventoryAmmoRaw"]
        assert [row["inventorySlot"] for row in rows] == [0, 54, 55]
        fields = ("inventorySlot", "type", "shoot", "damage", "knockback")
        assert [tuple(row[key] for key in fields) for row in rows] == [
            tuple(row[key] for key in fields) for row in native["playerInventoryAmmoRaw"]]
        assert all("stack" not in row for row in rows)
        fallback = ammo["fallbackAmmoRaw"]
        assert fallback and all(row["inventorySlot"] == -1 for row in fallback)
        assert [tuple(row[key] for key in fields) for row in fallback] == [
            tuple(row[key] for key in fields) for row in native["fallbackAmmoRaw"]]
        assert ammo["playerInventoryObservation"] == native["playerInventoryObservation"]
        fingerprint = packet["itemA"]["fingerprint"]["ammoRaw"]
        assert fingerprint["playerInventoryObservation"]["reason"] == "no_player"
        assert fingerprint["playerInventoryAmmoRaw"] is None


def _assert_ammo_snapshots(mechanics, native):
    """Resolve references, checking source ownership, without evaluating expressions."""
    snapshots = mechanics["expressions"]["snapshots"]
    definitions = list(_source_nodes(native["projectileSemanticsReference"]))
    identities = {(node["local"], node["sourceStoreIlOffset"], node["scope"])
                  for node in definitions if node.get("kind") == "local_definition"}
    def visit(value, active=()):
        for reference in re.findall(r"\bsnapshot[0-9]+\b", json.dumps(value)):
            assert reference in snapshots, "unresolved snapshot"
            assert reference not in active, "cyclic snapshot"
            snapshot = snapshots[reference]
            assert snapshot["scope"] == "value_at_store"
            assert (snapshot["local"], snapshot["sourceStoreIlOffset"], snapshot["scope"]) in identities
            assert snapshot["method"] == "Player.ItemCheck_Shoot"
            assert snapshot["sourcePath"] == "ammo.projectileSemanticsReference.stages[1]"
            visit(snapshot["value"], (*active, reference))
    visit(mechanics["ammoInputs"])


def _assert_eventide_state(mechanics, native):
    stages = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"]
    assert [stage["method"] for stage in stages] == ["Player.PickAmmo", "Player.ItemCheck_Shoot"]
    assert [len(stage["rules"]) for stage in stages] == [1, 1]
    pick, state = [stage["rules"][0] for stage in stages]
    assert state.keys() == native["projectileSemanticsReference"]["stages"][1]["rules"][0].keys() - {"sourceStoreIlOffset"}
    assert pick == {"outputProjectileId": 932, "whenInputProjectileId": 1, "sourceGuardIlOffset": 383}
    assert state["outputProjectileId"] == 932 and state["sourceGuardIlOffset"] == 10517
    assert state["sourceScope"] == native["projectileSemanticsReference"]["stages"][1]["rules"][0]["sourceScope"]
    match = re.fullmatch(r"not\(bne\((snapshot[0-9]+), 2\)\)", state["whenSourceCondition"])
    assert match is not None, "state-conditioned rewrite became unconditional or changed its predicate"
    snapshot = mechanics["expressions"]["snapshots"][match[1]]
    assert snapshot["sourceStoreIlOffset"] == 10599 and snapshot["scope"] == "value_at_store"
    assert snapshot["value"] == "div(sub(arg0.[Terraria.Player.itemAnimationMax], arg0.[Terraria.Player.itemAnimation]), 2)"
    # Match both old profile references to their distinct surviving rule sites.
    references = native["nativeReplacementProjectileRaw"][0]["sourceReferences"]
    assert len(references) == 2
    for index, reference in enumerate(references):
        assert reference["sourcePath"] == f"projectileSemanticsReference.stages[{index}].rules[0]"
        assert reference["method"] == stages[index]["method"]
        assert reference["sourceFact"] == native["projectileSemanticsReference"]["stages"][index]["rules"][0]
        assert reference["sourceFact"]["sourceStoreIlOffset"] == (396, 10873)[index]
        assert reference["conditionStatus"] == "source_conditions_not_evaluated"
        assert reference["dispatchStatus"] == "source_site_only_not_guaranteed_execution"
        assert stages[index]["rules"][0]["outputProjectileId"] == reference["sourceFact"]["outputProjectileId"]
    profiles = [row for row in mechanics["projectiles"] if row["defaults"].get("type") == 932]
    assert len(profiles) == 1
    profile = profiles[0]
    assert tuple(profile["defaults"][key] for key in ("penetrate", "timeLeft", "extraUpdates")) == (5, 120, 0)
    original = native["nativeReplacementProjectileRaw"][0]
    captures = [row for row in profile["captures"] if row["sourcePath"] == "ammo.nativeReplacementProjectileRaw[0]"]
    # Tagged native source facts stay literal at their own capture: compare the
    # original records, including certificates, condition/dispatch unknowns and
    # source-site order. Do not derive this oracle with the production renderer.
    assert captures == [{"sourcePath": "ammo.nativeReplacementProjectileRaw[0]",
                         **{key: original[key] for key in ("source", "inventorySlot", "profileScope", "sourceReferences")}}]


def _assert_spawn_mechanics(mechanics, native, name):
    stage = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"][1]
    original = native["projectileSemanticsReference"]["stages"][1]
    sites, originals = stage["spawnSites"], original["spawnSites"]
    if name != "eventide":
        for actual_stage, native_stage in zip(mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"],
                                               native["projectileSemanticsReference"]["stages"], strict=True):
            assert actual_stage["rules"] == native_stage["rules"] == []
    expected_offsets = {"eventide": [10958, 10992], "terra": [23695, 23759], "daedalus": [4157]}
    assert [site["sourceSpawnIlOffset"] for site in sites] == expected_offsets[name]
    for site, source in zip(sites, originals, strict=True):
        assert site.keys() == source.keys()
        for key in ("sourceSpawnIlOffset", "sourceGuardIlOffset", "projectileBasis", "nativeItemSpecificDelivery",
                    "scope", "trajectoryReference", "spawnCountBounds", "projectileId"):
            assert site.get(key) == source.get(key)
        inputs = site["spawnInputs"]
        assert inputs.keys() == source["spawnInputs"].keys()
        assert inputs["owner"] == "arg1"
        # These actual fixtures retain the diagnostic envelope literally, including
        # all fields, unresolved paths/reasons, guard coverage and conservative scope.
        assert site["spawnInputCoverage"] == source["spawnInputCoverage"]
        for field, value in source["spawnInputs"].items():
            if value["kind"] == "unknown":
                assert inputs[field] == value  # Also retains full conditional sourceDefinition.
            elif value["kind"] == "constant":
                assert inputs[field] == json.dumps(value["value"])
        if name == "eventide":
            guard = source["whenSourceCondition"]
            assert guard["sourceBranchIlOffset"] == 10886 and guard["opcode"] == "bne"
            assert guard["left"]["kind"] == "unknown" and guard["right"]["value"] == 932
            # Literal unknown operands are deliberately not reinterpreted by Author.
            operand = json.dumps(guard["left"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            predicate = f"bne({operand}, 932)"
            assert site["whenSourceCondition"] == (predicate if guard["taken"] else f"not({predicate})")
        else:
            assert site["whenSourceCondition"] == source["whenSourceCondition"]
    expressions = mechanics["expressions"]
    expected_unknowns = {"eventide": ["address_exposed_local", "branch_entry_value_unknown", "unsupported_stack_operation"],
                         "terra": ["address_exposed_local", "branch_entry_value_unknown"],
                         "daedalus": ["address_exposed_local", "cyclic_source_path"]}
    assert expressions["unknowns"] == expected_unknowns[name]
    if name == "eventide":
        first, second = sites
        damage = list(_source_nodes(first["spawnInputs"]["damage"]))
        assert any(node.get("operator") == "mul" and node["right"].get("value") == 2 for node in damage)
        assert any(node.get("sourceBranchIlOffset") == 10866 for node in damage)
        assert any(node.get("member") == "Terraria.Player.itemAnimationMax" for node in damage)
        velocity = expressions["snapshots"][first["spawnInputs"]["velocity"]]
        assert velocity["sourceStoreIlOffset"] == 10932
        assert velocity["value"].startswith("unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(")
        assert ", 2.0))" in velocity["value"] and ", mul(" in velocity["value"]
        assert expressions["snapshots"][second["spawnInputs"]["velocity"]]["sourceStoreIlOffset"] == 10861
        assert first["spawnInputs"]["position"] == second["spawnInputs"]["position"]
        assert expressions["snapshots"][first["spawnInputs"]["position"]]["sourceStoreIlOffset"] == 10695
        ai = expressions["snapshots"][first["spawnInputs"]["ai1"]]
        assert ai["sourceStoreIlOffset"] == 10906
        assert ai["value"] == "rem(mul(unexecuted Terraria.Player.get_miscCounterNormalized(arg0), 12.0), 1.0)"
        assert second["spawnInputs"]["ai1"] == "0.0"
    elif name == "terra":
        companion, direct = [site["spawnInputs"] for site in sites]
        assert companion["type"] == "984" and direct["ai1"] == "18.0"
        assert direct["velocity"].startswith("unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(")
        assert direct["velocity"].endswith(", 5.0)")
        for inputs in (companion, direct):
            assert inputs["position"] == "unexecuted Terraria.Player.get_MountedCenter(arg0)"
            assert inputs["ai0"] == "mul(conv.r4(arg0.[Terraria.Entity.direction]), arg0.[Terraria.Player.gravDir])"
            assert expressions["snapshots"][inputs["ai2"]]["value"] == "unexecuted Terraria.Player.GetAdjustedItemScale(arg0, arg2)"
    else:
        site, = sites
        assert (site["spawnCountBounds"]["minimum"], site["spawnCountBounds"]["maximum"]) == (2, 4)
        assert stage["spawnOriginSetups"] == original["spawnOriginSetups"]
        assert stage["spawnOriginSetups"][0]["initialYRelativeToMountedCenterPx"] == -600
        assert site["whenSourceCondition"]["reason"] == "cyclic_source_path"
        assert site["spawnInputCoverage"]["fields"]["velocityX"]["unresolved"][0]["reason"] == "cyclic_source_path"


def _assert_exact_ammo_expressions(mechanics, native, name):
    """Literal expression anchors after source-checked reference expansion.

    This observer does not render an AST or interpret an opcode. It only gives
    exact native JSON literals and already validated snapshot aliases readable
    names, then compares the complete remaining strings, not their substrings.
    """
    snapshots = mechanics["expressions"]["snapshots"]
    literals = {}
    for node in _source_nodes(native["projectileSemanticsReference"]):
        if node.get("kind") == "unknown":
            label = f"[[unknown:{node['reason']}:{node.get('local', '-')}@{node['sourceIlOffset']}]]"
        elif node.get("kind") == "branch" and "operands" in node:
            label = f"[[branch:{node['opcode']}@{node['sourceBranchIlOffset']}:{node['taken']}]]"
        else:
            continue
        literal = json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert label not in literals or literals[label] == literal, "ambiguous native literal identity"
        literals[label] = literal

    def observed(value):
        if not isinstance(value, str):
            return value
        assert "[[" not in value, "source tokens are observer-only, not delivered expressions"
        # Larger complete native literals first: their nested facts must not be
        # partially replaced before the full literal equality has been checked.
        for label, literal in sorted(literals.items(), key=lambda row: len(row[1]), reverse=True):
            value = value.replace(literal, label)
        return re.sub(r"\bsnapshot[0-9]+\b", lambda match:
                      f"[[store:{snapshots[match[0]]['sourceStoreIlOffset']}]]", value)

    sites = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"][1]["spawnSites"]
    if name == "eventide":
        inputs = [
            {"position": "[[store:10695]]", "velocity": "[[store:10932]]", "owner": "arg1",
             "ai0": "0.0", "ai1": "[[store:10906]]", "ai2": "0.0"},
            {"position": "[[store:10695]]", "velocity": "[[store:10861]]", "owner": "arg1",
             "ai0": "0.0", "ai1": "0.0", "ai2": "0.0"},
        ]
        values = {
            10599: "div(sub(arg0.[Terraria.Player.itemAnimationMax], arg0.[Terraria.Player.itemAnimation]), 2)",
            10664: {"kind": "unknown", "reason": "unsupported_stack_operation", "sourceIlOffset": 10664},
            10677: "unexecuted Microsoft.Xna.Framework.Vector2.op_Subtraction([[store:10664]], [[unknown:address_exposed_local:134@10670]])",
            10695: "unexecuted Microsoft.Xna.Framework.Vector2.op_Addition([[unknown:address_exposed_local:8@10686]], local138 path_value{when [[branch:brtrue@10666:True]]: [[store:10664]]; when [[branch:brtrue@10666:False]]: [[store:10677]]})",
            10684: "unexecuted Terraria.Main.get_MouseWorld()",
            10800: "unexecuted Terraria.Utils.GetLerpValue(100.0, 40.0, unexecuted Terraria.Utils.Distance([[store:10684]], unexecuted Terraria.Entity.get_Center(arg0)), 1)",
            10721: "unexecuted Terraria.Utils.SafeNormalize(unexecuted Terraria.Utils.DirectionTo([[store:10695]], [[store:10684]]), unexecuted Microsoft.Xna.Framework.Vector2.op_UnaryNegation(unexecuted Microsoft.Xna.Framework.Vector2.get_UnitY()))",
            10769: "unexecuted Terraria.Utils.SafeNormalize(unexecuted Terraria.Utils.DirectionTo(unexecuted Terraria.Entity.get_Center(arg0), unexecuted Microsoft.Xna.Framework.Vector2.op_Addition(unexecuted Terraria.Entity.get_Center(arg0), construct Microsoft.Xna.Framework.Vector2..ctor[2002010c0c]([[unknown:branch_entry_value_unknown:13@10735]], [[unknown:branch_entry_value_unknown:14@10737]]))), unexecuted Microsoft.Xna.Framework.Vector2.op_UnaryNegation(unexecuted Microsoft.Xna.Framework.Vector2.get_UnitY()))",
            10851: "unexecuted Terraria.Utils.SafeNormalize(unexecuted Microsoft.Xna.Framework.Vector2.Lerp([[store:10721]], [[store:10769]], [[store:10800]]), unexecuted Terraria.Utils.SafeNormalize(construct Microsoft.Xna.Framework.Vector2..ctor[2002010c0c]([[unknown:branch_entry_value_unknown:13@10822]], [[unknown:branch_entry_value_unknown:14@10824]]), unexecuted Microsoft.Xna.Framework.Vector2.op_UnaryNegation(unexecuted Microsoft.Xna.Framework.Vector2.get_UnitY())))",
            10861: "unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(local141 path_value{when ble.un([[store:10800]], 0.0): [[store:10721]]; when not(ble.un([[store:10800]], 0.0)): [[store:10851]]}, [[unknown:address_exposed_local:1@10855]])",
            10932: "unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(unexecuted Terraria.Utils.SafeNormalize([[store:10861]], unexecuted Microsoft.Xna.Framework.Vector2.get_Zero()), mul([[unknown:address_exposed_local:1@10920]], 2.0))",
            10906: "rem(mul(unexecuted Terraria.Player.get_miscCounterNormalized(arg0), 12.0), 1.0)",
        }
    elif name == "terra":
        common = {"position": "unexecuted Terraria.Player.get_MountedCenter(arg0)", "owner": "arg1",
                  "ai0": "mul(conv.r4(arg0.[Terraria.Entity.direction]), arg0.[Terraria.Player.gravDir])",
                  "ai2": "[[store:23627]]"}
        inputs = [
            {**common, "velocity": "construct Microsoft.Xna.Framework.Vector2..ctor[2002010c0c](conv.r4(arg0.[Terraria.Entity.direction]), 0.0)",
             "type": "984", "ai1": "conv.r4(arg0.[Terraria.Player.itemAnimationMax])"},
            {**common, "velocity": "unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(construct Microsoft.Xna.Framework.Vector2..ctor[2002010c0c]([[unknown:branch_entry_value_unknown:13@23709]], [[unknown:branch_entry_value_unknown:14@23711]]), 5.0)",
             "ai1": "18.0"},
        ]
        values = {23627: "unexecuted Terraria.Player.GetAdjustedItemScale(arg0, arg2)"}
    else:
        assert name == "daedalus"
        inputs = [{"positionX": "[[unknown:address_exposed_local:8@4118]].[Microsoft.Xna.Framework.Vector2.X]",
                   "positionY": "[[unknown:address_exposed_local:8@4125]].[Microsoft.Xna.Framework.Vector2.Y]",
                   "owner": "arg1", "ai0": "0.0", "ai1": "0.0", "ai2": "0.0"}]
        values = {}
    assert [{key: observed(value) for key, value in site["spawnInputs"].items() if isinstance(value, str)}
            for site in sites] == inputs
    assert len(snapshots) == len(values), "missing or duplicate snapshot ownership"
    assert {row["sourceStoreIlOffset"]: observed(row["value"]) for row in snapshots.values()} == values



def _assert_author_ammo(mechanics, packet, name):
    native = packet["itemA"]["ammoRaw"]
    _assert_ammo_observations(mechanics, packet, name)
    _assert_ammo_snapshots(mechanics, native)
    if name == "eventide":
        _assert_eventide_state(mechanics, native)
    _assert_spawn_mechanics(mechanics, native, name)
    _assert_exact_ammo_expressions(mechanics, native, name)


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_native_state_condition_survives_actual_prepare_author_request(monkeypatch, mode):
    from infini_local.core import llm_config
    path = Path(os.environ.get("INFINI_PARENT_STATE_PACKET", "/missing-native-prepare-packet"))
    if not path.exists():
        pytest.skip("actual native state-conditioned Prepare packet unavailable")
    packet = json.loads(path.read_text())
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    mechanics, _ = _prepare_ammo_mechanics(packet, mode)
    _assert_author_ammo(mechanics, packet, "eventide")


def _arithmetic_variant_fixture(*, item=81234, step=2, threshold=7, maximum=31, prefix=(), mutation=None):
    ops=[('ldarg',2),('ldfld','Terraria.Item.shoot'),('stloc',0),*prefix,
         ('ldarg',2),('ldfld','Terraria.Item.type'),('const',item),('bne','end'),
         ('call',('Terraria.Main.get_rand',0,False,True)),('const',maximum),
         ('call',('Terraria.Utilities.UnifiedRandom.Next',1,True,True)),('const',threshold),('bge','else'),
         ('ldloc',0),('const',step),('add',None),('stloc',0),
         ('ldloc',4),('const',5),('mul',None),('stloc',4),('br','end'),
         ('label','else'),('ldloc',1),('const',2.5),('sub',None),('stloc',1),('label','end'),('ret',None)]
    if mutation: ops=mutation(ops)
    labels={}; n=0
    for op,arg in ops:
        if op=='label': labels[arg]=n
        else:n+=1
    return [VariantInstruction(n,op,labels.get(arg,arg) if isinstance(arg,str) else arg) for n,(op,arg) in enumerate((o for o in ops if o[0]!='label'))]


def _arithmetic_variant_row(code):
    return next(r for r in ammo_method_facts(code,'ItemCheck_Shoot') if r['itemId']==81234)


def test_arbitrary_ids_values_not_weapon_template():
    result=_arithmetic_variant_row(_arithmetic_variant_fixture())
    a,b=result['conditionalArithmeticVariants']
    assert a['projectileOffset']==2 and b['projectileOffset']==0
    assert a['conditionalProbability']['numerator']==7
    assert a['conditionalProbability']['denominator']==31
    assert a['localUpdates'][1]['operand']==5
    assert a['inputBinding']['basis']=='item_shoot_snapshot'
    assert result['unrecognizedProjectileWriteOffsets']


@pytest.mark.parametrize('prefix',[
    [('const',123),('stloc',0)], [('ldloca',0),('call',('Opaque.Write',1,False,False))],
])
def test_unknown_prior_write_withholds_identity_binding_but_retains_source(prefix):
    variants=_arithmetic_variant_row(_arithmetic_variant_fixture(prefix=prefix))['conditionalArithmeticVariants']
    assert all(v['inputBinding'] is None for v in variants)


@pytest.mark.parametrize('exposed_local', [0, 4])
def test_arithmetic_saved_byref_before_initialization_withholds_only_aliased_binding(exposed_local):
    # The alias outlives the Item.shoot initialization. The later stind is an
    # explicit source write, not a hypothetical callback or post-shot hook.
    alias = [('const', 0), ('stloc', exposed_local), ('ldloca', exposed_local), ('stloc', 30)]
    code = _arithmetic_variant_fixture(
        prefix=[('ldloc', 30), ('const', 99), ('stind.i4', None)],
        mutation=lambda ops: alias + ops)
    variants = _arithmetic_variant_row(code)['conditionalArithmeticVariants']
    a, b = variants
    assert [v['projectileOffset'] for v in variants] == [2, 0]
    assert [v['conditionalProbability']['numerator'] for v in variants] == [7, 24]
    assert a['localUpdates'][0]['basis'] == 'local_value_at_branch_entry'
    assert a['localUpdates'][0]['operand'] == 2
    assert b['localUpdates'][0]['operator'] == 'sub'
    if exposed_local == 0:
        assert all(v['inputBinding'] is None for v in variants)
    else:
        assert all(v['inputBinding']['basis'] == 'item_shoot_snapshot' for v in variants)


@pytest.mark.parametrize('mutation',[
    lambda ops:[(op,('Other.Random',1,True,True)) if op=='call' and arg[0].endswith('.Next') else (op,arg) for op,arg in ops],
    lambda ops:[('add.ovf',arg) if op=='add' else (op,arg) for op,arg in ops],
    lambda ops:[('bge.un',arg) if op=='bge' else (op,arg) for op,arg in ops],
    lambda ops:[(op,('Terraria.Utilities.UnifiedRandom.Next',2,True,True)) if op=='call' and arg[0].endswith('.Next') else (op,arg) for op,arg in ops],
])
def test_unknown_shape_refuses_variant(mutation):
    assert 'conditionalArithmeticVariants' not in _arithmetic_variant_row(_arithmetic_variant_fixture(mutation=mutation))


@pytest.mark.parametrize('threshold,maximum',[(-1,100),(101,100),(0,0)])
def test_invalid_rng_bounds_refuse(threshold,maximum):
    assert 'conditionalArithmeticVariants' not in _arithmetic_variant_row(_arithmetic_variant_fixture(threshold=threshold,maximum=maximum))


def test_header_bypass_refuses():
    code=_arithmetic_variant_fixture()
    code.insert(0,VariantInstruction(-1,'br',5))
    assert 'conditionalArithmeticVariants' not in _arithmetic_variant_row(code)


def test_foreign_arm_entry_refuses():
    code=_arithmetic_variant_fixture()
    code.insert(0,VariantInstruction(-1,'br',16))
    assert 'conditionalArithmeticVariants' not in _arithmetic_variant_row(code)


def test_arithmetic_binding_prunes_only_explicit_snapshot_guards():
    prefix = [('ldarg',2),('ldfld','Terraria.Item.useAmmo'),('const',0),('ble','noammo'),
              ('ldloca',0),('call',('Opaque.PickAmmo',1,False,False)),('label','noammo'),
              ('ldarg',2),('ldfld','Terraria.Item.type'),('const',91234),('bne','other'),
              ('const',14),('stloc',0),('label','other')]
    variants = _arithmetic_variant_row(_arithmetic_variant_fixture(prefix=prefix))['conditionalArithmeticVariants']
    assert all(v['inputBinding']['requiredUseAmmoMaximum']==0 for v in variants)
    same_item = [(op,81234 if arg==91234 else arg) for op,arg in prefix]
    assert all(v['inputBinding'] is None for v in _arithmetic_variant_row(_arithmetic_variant_fixture(prefix=same_item))['conditionalArithmeticVariants'])


def test_arithmetic_initializer_foreign_entry_withholds_binding():
    code = _arithmetic_variant_fixture()
    code.insert(0, VariantInstruction(-1,'br',2))
    assert all(v['inputBinding'] is None for v in _arithmetic_variant_row(code)['conditionalArithmeticVariants'])


def test_arithmetic_unreachable_guard_withholds_binding():
    variants = _arithmetic_variant_row(_arithmetic_variant_fixture(prefix=[('ret',None)]))['conditionalArithmeticVariants']
    assert all(v['inputBinding'] is None for v in variants)


def test_arithmetic_local_initialization_is_not_current_value():
    prefix = [('ldarg',2),('ldfld','Terraria.Item.shootSpeed'),('stloc',1),
              ('ldloc',1),('const',7.0),('mul',None),('stloc',1)]
    variants = _arithmetic_variant_row(_arithmetic_variant_fixture(prefix=prefix))['conditionalArithmeticVariants']
    provenance = variants[1]['localUpdates'][0]['initializationProvenance']
    assert provenance['source']=={'kind':'argument_field','argument':2,'field':'Terraria.Item.shootSpeed'}
    assert len(provenance['interveningWriteOrAddressOffsets'])==1
    assert 'does not equate' in provenance['scope']


def _spawn_argument_fixture(*, item=81235, factor=3, threshold=7, mutate=(), prefix=(), entry=None):
    """Arbitrary source identities and locals; branch-entry values stay unknown."""
    from native_hit_status_analysis import Instruction as I
    ops = [('ldarg', 2), ('ldfld', 'Terraria.Item.shoot'), ('stloc', 0), *prefix]
    if entry:
        ops += [('br', entry)]
    ops += [('ldarg', 2), ('ldfld', 'Terraria.Item.type'), ('const', item), ('bne', 'end'),
            ('ldarg', 0), ('ldfld', 'Fixture.Player.maximum'), ('ldarg', 0),
            ('ldfld', 'Fixture.Player.remaining'), ('sub', None), ('const', 2), ('div', None), ('stloc', 23),
            ('label', 'state'), ('ldloc', 23), ('const', threshold), ('bne', 'join'),
            ('ldloc', 14), ('const', factor), ('mul', None), ('stloc', 14),
            ('label', 'join'), *mutate,
            ('ldarg', 0), ('call', ('Fixture.Player.GetPhase', 0, True, True)), ('const', 12.0),
            ('mul', None), ('const', 1.0), ('rem', None), ('stloc', 25),
            ('label', 'arguments'), ('ldloc', 7), ('ldloc', 8), ('ldloc', 9), ('ldloc', 0),
            ('label', 'damage'), ('ldloc', 14), ('ldloc', 15), ('ldarg', 1), ('const', 0.0),
            ('ldloc', 25), ('const', 0.0), ('call', ('Terraria.Projectile.NewProjectile', 10, False, True)),
            ('pop', None), ('label', 'end'), ('ret', None)]
    labels, n = {}, 0
    for op, arg in ops:
        if op == 'label': labels[arg] = n
        else: n += 1
    return [I(n, op, labels.get(arg, arg) if isinstance(arg, str) else arg)
            for n, (op, arg) in enumerate(pair for pair in ops if pair[0] != 'label')]


def _source_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _source_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _source_nodes(child)


@pytest.mark.parametrize('item,factor,threshold', [(81235, 3, 7), (91236, 5, 11)])
def test_spawn_arguments_keep_guarded_updates_and_source_snapshots(item, factor, threshold):
    row, = ammo_method_facts(_spawn_argument_fixture(item=item, factor=factor, threshold=threshold), 'ItemCheck_Shoot')
    spawn, = row['spawnSites']
    inputs = spawn['spawnInputs']
    assert inputs['owner']['kind'] == 'argument' and inputs['owner']['index'] == 1
    damage_nodes = list(_source_nodes(inputs['damage']))
    assert any(n.get('operator') == 'mul' and n['right'].get('value') == factor for n in damage_nodes)
    assert any(n.get('kind') == 'unknown' and n.get('local') == 14 and n.get('reason') == 'branch_entry_value_unknown' for n in damage_nodes)
    assert any(n.get('kind') == 'branch' and n.get('right', {}).get('value') == threshold for n in damage_nodes)
    assert any(n.get('member') == 'Fixture.Player.maximum' for n in damage_nodes)
    assert any(n.get('kind') == 'local_definition' and n.get('scope') == 'value_at_store' for n in damage_nodes)
    ai = list(_source_nodes(inputs['ai1']))
    assert any(n.get('operator') == 'rem' and n['right'].get('value') == 1.0 for n in ai)
    assert any(n.get('member') == 'Fixture.Player.GetPhase' and n.get('evaluation') == 'unresolved_helper_or_hook_output' for n in ai)
    assert spawn['spawnInputCoverage']['fields']['damage']['status'] == 'partial_source_expression'
    assert spawn['spawnInputCoverage']['fields']['owner']['status'] == 'source_expression'


@pytest.mark.parametrize('mutation,reason', [
    ([('ldloca', 14), ('call', ('Opaque.Mutate', 1, False, False))], 'address_exposed_local'),
    ([('ldarg', 0), ('ldfld', 'Fixture.Player.loop'), ('brtrue', 'state')], 'cyclic_source_path'),
    ([('const', 4), ('neg', None), ('stloc', 14)], None),
    ([('const', 4), ('not', None), ('stloc', 14)], 'unsupported_stack_operation'),
])
def test_spawn_arguments_refuse_unproved_values_with_field_diagnostics(mutation, reason):
    row, = ammo_method_facts(_spawn_argument_fixture(mutate=mutation), 'ItemCheck_Shoot')
    spawn, = row['spawnSites']
    field = spawn['spawnInputCoverage']['fields']['damage']
    if reason:
        assert any(issue['reason'] == reason for issue in field['unresolved'])
        assert field['status'] in ('partial_source_expression', 'unknown')
    else:
        assert any(n.get('operator') == 'neg' for n in _source_nodes(spawn['spawnInputs']['damage']))


def test_exact_native_spawn_argument_source_fields():
    from generate_native_ammo_facts import extract
    installed = Path(os.environ.get('INFINI_NATIVE_AMMO_ASSEMBLY', '/missing-native-assembly'))
    if not installed.exists():
        pytest.skip('exact native source assembly unavailable')
    sources = extract(installed)
    rows = {r['itemId']: r for s in sources if s['method'] == 'Player.ItemCheck_Shoot' for r in s['records']}
    a, b = rows[4953]['spawnSites']
    assert (a['sourceSpawnIlOffset'], b['sourceSpawnIlOffset']) == (10958, 10992)
    nodes = list(_source_nodes(a['spawnInputs']['damage']))
    assert any(n.get('operator') == 'mul' and n['right'].get('value') == 2 for n in nodes)
    assert any(n.get('sourceBranchIlOffset') == 10866 for n in nodes)
    assert any(n.get('member') == 'Terraria.Player.itemAnimationMax' for n in nodes)
    velocity = list(_source_nodes(a['spawnInputs']['velocity']))
    assert any(n.get('operator') == 'mul' and n['right'].get('value') == 2.0 for n in velocity)
    assert any(n.get('sourceStoreIlOffset') == 10932 for n in velocity)
    assert any(n.get('sourceBranchIlOffset') == 10886 for n in _source_nodes(a['whenSourceCondition']))
    ai = list(_source_nodes(a['spawnInputs']['ai1']))
    assert any(n.get('operator') == 'rem' for n in ai)
    assert any(n.get('member') == 'Terraria.Player.get_miscCounterNormalized' for n in ai)
    assert b['spawnInputs']['ai1']['value'] == 0.0
    for item in (757, 3029):
        assert all('spawnInputs' in s and 'spawnInputCoverage' in s for s in rows[item]['spawnSites'])
    companion, direct = rows[757]['spawnSites']
    assert companion['spawnInputs']['type']['value'] == 984
    velocity = direct['spawnInputs']['velocity']
    assert velocity['member'] == 'Microsoft.Xna.Framework.Vector2.op_Multiply'
    assert velocity['arguments'][1]['value'] == 5.0
    assert direct['spawnInputs']['ai1']['value'] == 18.0
    rain, = rows[3029]['spawnSites']
    assert (rain['spawnCountBounds']['minimum'], rain['spawnCountBounds']['maximum']) == (2, 4)
    assert rain['spawnInputCoverage']['fields']['velocityX']['unresolved'][0]['reason'] == 'cyclic_source_path'
    assert rain['spawnInputs']['owner']['index'] == 1


def test_spawn_argument_header_entry_cannot_certify_ownership():
    code = _spawn_argument_fixture()
    from native_hit_status_analysis import Instruction as I
    # Existing site discovery admits this header; the additive source reader
    # must refuse its ownership instead of interpreting the forged Item.type.
    code.insert(0, I(-1, 'br', 5))
    row, = ammo_method_facts(code, 'ItemCheck_Shoot')
    spawn, = row['spawnSites']
    assert all(field['status'] == 'unknown' for field in spawn['spawnInputCoverage']['fields'].values())
    assert spawn['spawnInputs']['damage']['reason'] == 'foreign_entry_into_item_header'


def test_spawn_argument_later_store_supersedes_only_prior_local_value():
    row, = ammo_method_facts(_spawn_argument_fixture(mutate=[('const', 41), ('stloc', 14)]), 'ItemCheck_Shoot')
    damage = row['spawnSites'][0]['spawnInputs']['damage']
    assert damage['kind'] == 'local_definition' and damage['value']['value'] == 41
    assert not any(node.get('operator') == 'mul' for node in _source_nodes(damage))


@pytest.mark.parametrize('exposed_local', [14, 15])
def test_spawn_argument_saved_byref_before_guard_refuses_only_aliased_value(exposed_local):
    code = _spawn_argument_fixture(
        prefix=[('const', 0), ('stloc', exposed_local), ('ldloca', exposed_local), ('stloc', 30)],
        mutate=[('const', 41), ('stloc', 14), ('ldloc', 30), ('const', 99), ('stind.i4', None)])
    row, = ammo_method_facts(code, 'ItemCheck_Shoot')
    spawn, = row['spawnSites']
    damage = spawn['spawnInputs']['damage']
    if exposed_local == 14:
        assert damage['kind'] == 'unknown'
        assert damage['reason'] == 'address_exposed_local'
        assert damage['sourceAddressIlOffsets'] == [5]
        # The direct store remains useful source syntax, not the value at load.
        assert damage['sourceDefinition']['value']['value'] == 41
        assert spawn['spawnInputCoverage']['fields']['damage']['status'] == 'unknown'
        issues = spawn['spawnInputCoverage']['fields']['damage']['unresolved']
        assert issues[0]['reason'] == 'address_exposed_local'
        assert all('sourceDefinition' not in issue for issue in issues)
        from infini_local.pipelines.context.mechanics_expression import MechanicsRenderer
        renderer = MechanicsRenderer()
        assert renderer.render(damage) == damage
        assert 'address_exposed_local' in renderer.finish()['unknowns']
    else:
        assert damage['kind'] == 'local_definition' and damage['value']['value'] == 41
        assert spawn['spawnInputCoverage']['fields']['damage'] == {'status': 'source_expression', 'unresolved': []}
    assert spawn['spawnInputs']['owner']['kind'] == 'argument'
    assert spawn['spawnInputs']['ai0']['value'] == 0.0
    assert any(n.get('operator') == 'rem' for n in _source_nodes(spawn['spawnInputs']['ai1']))
    assert any(n.get('member') == 'Fixture.Player.GetPhase' for n in _source_nodes(spawn['spawnInputs']['ai1']))


def test_spawn_argument_condition_reads_keep_original_field_snapshots():
    row, = ammo_method_facts(_spawn_argument_fixture(mutate=[
        ('ldarg', 0), ('const', 0), ('stfld', 'Fixture.Player.remaining')]), 'ItemCheck_Shoot')
    nodes = list(_source_nodes(row['spawnSites'][0]['spawnInputs']['damage']))
    old_read = next(n for n in nodes if n.get('member') == 'Fixture.Player.remaining')
    definition = next(n for n in nodes if n.get('kind') == 'local_definition' and n.get('local') == 23)
    assert old_read['sourceIlOffset'] < definition['sourceStoreIlOffset'] < definition['sourceIlOffset']
    assert definition['scope'] == 'value_at_store'


def test_spawn_argument_prior_hook_reference_does_not_restore_item_defaults():
    from native_hit_status_analysis import Instruction as I
    code = _spawn_argument_fixture()
    prefix = [I(-3, 'ldloca', 14), I(-2, 'call', ('Opaque.PriorHook', 1, False, False)), I(-1, 'nop', None)]
    row, = ammo_method_facts(prefix + code, 'ItemCheck_Shoot')
    nodes = list(_source_nodes(row['spawnSites'][0]['spawnInputs']['damage']))
    assert any(n.get('reason') == 'address_exposed_local' and n.get('local') == 14 for n in nodes)
    assert any(n.get('operator') == 'mul' for n in nodes)
    assert row['spawnSites'][0]['spawnInputs']['damage']['sourceAddressIlOffsets'] == [-3]
    assert not any(n.get('member') == 'Terraria.Item.damage' for n in nodes)


@pytest.mark.parametrize('mode', ['json_schema', 'json_object'])
def test_native_spawn_arguments_survive_actual_prepare_author_request(monkeypatch, mode):
    from infini_local.core import llm_config
    directory = Path(os.environ.get('INFINI_PARENT_SPAWN_PACKET_DIR', '/missing-native-spawn-packets'))
    if not directory.exists():
        pytest.skip('actual native spawn Prepare packets unavailable')
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    for name in ('eventide', 'terra', 'daedalus'):
        packet = json.loads((directory / (name + '.packet.json')).read_text())
        mechanics, _ = _prepare_ammo_mechanics(packet, mode)
        _assert_author_ammo(mechanics, packet, name)


@pytest.fixture(scope="module")
def actual_ammo_observer_inputs():
    from infini_local.core import llm_config
    directory = Path(os.environ.get("INFINI_PARENT_SPAWN_PACKET_DIR", "/missing-native-spawn-packets"))
    if not directory.exists():
        pytest.skip("actual native spawn Prepare packets unavailable")
    result = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
        for name in ("eventide", "terra", "daedalus"):
            packet = json.loads((directory / (name + ".packet.json")).read_text())
            mechanics, literal = _prepare_ammo_mechanics(packet, "json_schema")
            _assert_author_ammo(mechanics, packet, name)  # Establish GREEN before each corruption.
            result[name] = packet, mechanics, literal
    return result


@pytest.mark.parametrize("defect", [
    "pick_rule", "state_rule", "state_guard", "snapshot_missing", "snapshot_value", "snapshot_scope",
    "snapshot_owner", "snapshot_cycle", "replacement_default", "replacement_capture", "ammo_missing",
    "ammo_reordered", "ammo_duplicate", "ammo_damage", "fallback_slot", "final_shot", "source_unknowns",
    "spawn_site", "spawn_duplicate", "spawn_input", "spawn_owner", "spawn_guard", "spawn_coverage",
    "conditional_damage", "ai_remainder", "expression_unknowns", "stage_call_site",
    "stage_method", "hook_order", "hook_duplicate", "category_selector",
    "replacement_references_missing", "replacement_reference_lost", "replacement_reference_reordered",
    "replacement_reference_duplicate", "replacement_reference_owner", "replacement_reference_source_path",
    "replacement_reference_fact", "replacement_reference_condition", "replacement_reference_dispatch",
    "replacement_reference_certificate", "replacement_reference_kind", "replacement_capture_extra_field",
])
def test_actual_author_ammo_observer_rejects_information_loss(actual_ammo_observer_inputs, defect):
    packet, original, _ = actual_ammo_observer_inputs["eventide"]
    mechanics = copy.deepcopy(original)
    ammo = mechanics["ammoInputs"]
    source = ammo["projectileSemanticsReference"]
    stages = source["stages"]
    state = stages[1]["rules"][0]
    snapshots = mechanics["expressions"]["snapshots"]
    state_key = re.fullmatch(r"not\(bne\((snapshot[0-9]+), 2\)\)", state["whenSourceCondition"])[1]
    sites = stages[1]["spawnSites"]
    profile = next(row for row in mechanics["projectiles"] if row["defaults"].get("type") == 932)
    capture = next(row for row in profile["captures"] if row["sourcePath"] == "ammo.nativeReplacementProjectileRaw[0]")
    references = capture["sourceReferences"]
    changes = {
        "replacement_references_missing": lambda: capture.pop("sourceReferences"),
        "replacement_reference_lost": lambda: references.pop(),
        "replacement_reference_reordered": lambda: references.reverse(),
        "replacement_reference_duplicate": lambda: references.append(copy.deepcopy(references[0])),
        "replacement_reference_owner": lambda: references[1].update(method="Player.PickAmmo"),
        "replacement_reference_source_path": lambda: references[1].update(sourcePath=references[0]["sourcePath"]),
        "replacement_reference_fact": lambda: references[1]["sourceFact"].update(outputProjectileId=1),
        "replacement_reference_condition": lambda: references[1].update(conditionStatus="evaluated_true"),
        "replacement_reference_dispatch": lambda: references[1].update(dispatchStatus="guaranteed_execution"),
        "replacement_reference_certificate": lambda: references[1].update(sourceMethodSha256="0" * 64),
        "replacement_reference_kind": lambda: references[1].update(kind="executed_projectile_replacement"),
        "replacement_capture_extra_field": lambda: capture.update(finalShot=True),
        "stage_call_site": lambda: stages[0]["sourceStageCallSites"].clear(),
        "stage_method": lambda: stages[1].update(method="Player.PickAmmo"),
        "hook_order": lambda: stages[0]["hookDispatchTrace"][0]["directHookCalls"].reverse(),
        "hook_duplicate": lambda: stages[0]["hookDispatchTrace"].append(copy.deepcopy(stages[0]["hookDispatchTrace"][0])),
        "category_selector": lambda: stages[0]["defaultProjectileSelection"]["categoryOffsetSelectors"][0].update(operation="ammo_shoot"),
        "pick_rule": lambda: stages[0]["rules"].clear(),
        "state_rule": lambda: stages[1]["rules"].clear(),
        "state_guard": lambda: state.update(whenSourceCondition="true"),
        "snapshot_missing": lambda: snapshots.pop(state_key),
        "snapshot_value": lambda: snapshots[state_key].update(value="2"),
        "snapshot_scope": lambda: snapshots[state_key].update(scope="value_at_read"),
        "snapshot_owner": lambda: snapshots[state_key].update(method="Player.PickAmmo"),
        "snapshot_cycle": lambda: snapshots[state_key].update(value=state_key),
        "replacement_default": lambda: profile["defaults"].pop("penetrate"),
        "replacement_capture": lambda: profile["captures"].clear(),
        "ammo_missing": lambda: ammo["playerInventoryAmmoRaw"].pop(),
        "ammo_reordered": lambda: ammo["playerInventoryAmmoRaw"].reverse(),
        "ammo_duplicate": lambda: ammo["playerInventoryAmmoRaw"].append(copy.deepcopy(ammo["playerInventoryAmmoRaw"][0])),
        "ammo_damage": lambda: ammo["playerInventoryAmmoRaw"][0].update(damage=-1),
        "fallback_slot": lambda: ammo["fallbackAmmoRaw"][0].update(inventorySlot=0),
        "final_shot": lambda: source.update(finalShotOutcome="executed"),
        "source_unknowns": lambda: source["unknowns"].clear(),
        "spawn_site": lambda: sites.pop(),
        "spawn_duplicate": lambda: sites.append(copy.deepcopy(sites[0])),
        "spawn_input": lambda: sites[0]["spawnInputs"].pop("damage"),
        "spawn_owner": lambda: sites[0]["spawnInputs"].update(owner="arg0"),
        "spawn_guard": lambda: sites[0].update(whenSourceCondition=True),
        "spawn_coverage": lambda: sites[0]["spawnInputCoverage"]["fields"].pop("damage"),
        "conditional_damage": lambda: sites[0]["spawnInputs"]["damage"].pop("sourceDefinition"),
        "ai_remainder": lambda: snapshots[sites[0]["spawnInputs"]["ai1"]].update(value="0.0"),
        "expression_unknowns": lambda: mechanics["expressions"]["unknowns"].clear(),
    }
    changes[defect]()
    with pytest.raises((AssertionError, KeyError)):
        _assert_author_ammo(mechanics, packet, "eventide")


@pytest.mark.parametrize("name,defect", [("terra", "companion"), ("terra", "speed"), ("terra", "ai"),
                                          ("daedalus", "count"), ("daedalus", "origin"), ("daedalus", "uncertainty")])
def test_actual_spawn_observer_rejects_information_loss(actual_ammo_observer_inputs, name, defect):
    packet, original, _ = actual_ammo_observer_inputs[name]
    mechanics = copy.deepcopy(original)
    stage = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"][1]
    sites = stage["spawnSites"]
    if defect == "companion":
        sites[0]["spawnInputs"]["type"] = "1"
    elif defect == "speed":
        sites[1]["spawnInputs"]["velocity"] = "5.0"
    elif defect == "ai":
        sites[1]["spawnInputs"]["ai1"] = "0.0"
    elif defect == "count":
        sites[0]["spawnCountBounds"]["maximum"] = 2
    elif defect == "origin":
        stage["spawnOriginSetups"][0]["initialYRelativeToMountedCenterPx"] = 0
    else:
        sites[0]["whenSourceCondition"] = True
    with pytest.raises((AssertionError, KeyError)):
        _assert_author_ammo(mechanics, packet, name)


@pytest.mark.parametrize("defect", ["source_reference", "source_guard", "source_certificate", "scope", "defaults"])
def test_literal_ammo_observer_rejects_information_loss(actual_ammo_observer_inputs, defect):
    packet, _, original = actual_ammo_observer_inputs["eventide"]
    literal = copy.deepcopy(original)
    if defect == "source_reference":
        literal["nativeReplacementProjectileRaw"][0]["sourceReferences"].pop()
    elif defect == "source_guard":
        literal["projectileSemanticsReference"]["stages"][1]["rules"][0].pop("whenSourceCondition")
    elif defect == "source_certificate":
        literal["projectileSemanticsReference"]["stages"][0].pop("sourceMethodSha256")
    elif defect == "scope":
        literal["nativeReplacementProjectileRaw"][0]["profileScope"] = "final shot"
    else:
        literal["nativeReplacementProjectileRaw"][0].pop("penetrate")
    with pytest.raises((AssertionError, KeyError)):
        _assert_literal_prepare_ammo(literal, packet["itemA"]["ammoRaw"])


@pytest.mark.parametrize("name,defect", [
    *[("eventide", f"snapshot_{store}") for store in (10664, 10677, 10695, 10684, 10800, 10721, 10769, 10851, 10861)],
    ("eventide", "velocity_operand"), ("terra", "companion_velocity"), ("terra", "companion_ai1"),
    ("terra", "direct_vector"), ("daedalus", "positionX"), ("daedalus", "positionY"),
    ("terra", "false_pick_rewrite"), ("daedalus", "false_pick_rewrite"),
])
def test_actual_ammo_observer_rejects_transformed_value_loss(actual_ammo_observer_inputs, name, defect):
    packet, original, _ = actual_ammo_observer_inputs[name]
    mechanics = copy.deepcopy(original)
    stages = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"]
    sites = stages[1]["spawnSites"]
    if defect.startswith("snapshot_") or defect == "velocity_operand":
        store = int(defect.removeprefix("snapshot_")) if defect.startswith("snapshot_") else 10932
        snapshot = next(row for row in mechanics["expressions"]["snapshots"].values()
                        if row["sourceStoreIlOffset"] == store)
        snapshot["value"] = ("unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(0.0, mul(0.0, 2.0))"
                             if defect == "velocity_operand" else "0.0")
    elif defect.startswith("companion_"):
        sites[0]["spawnInputs"][defect.removeprefix("companion_")] = "0.0"
    elif defect == "direct_vector":
        sites[1]["spawnInputs"]["velocity"] = "unexecuted Microsoft.Xna.Framework.Vector2.op_Multiply(0.0, 5.0)"
    elif defect == "false_pick_rewrite":
        stages[0]["rules"].append({"outputProjectileId": 932, "whenInputProjectileId": 1, "sourceGuardIlOffset": 383})
    else:
        sites[0]["spawnInputs"][defect] = "0.0"
    with pytest.raises((AssertionError, KeyError)):
        _assert_author_ammo(mechanics, packet, name)


@pytest.mark.parametrize("name,defect", [
    ("eventide", "extra_pick_spawn"), ("terra", "extra_pick_spawn"), ("daedalus", "extra_pick_spawn"),
    ("eventide", "extra_state_condition"), ("eventide", "extra_spawn_predicate"),
])
def test_actual_ammo_observer_rejects_invented_source_facts(actual_ammo_observer_inputs, name, defect):
    packet, original, _ = actual_ammo_observer_inputs[name]
    mechanics = copy.deepcopy(original)
    stages = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"]
    if defect == "extra_pick_spawn":
        stages[0]["spawnSites"].append(copy.deepcopy(stages[1]["spawnSites"][0]))
    elif defect == "extra_state_condition":
        stages[1]["rules"][0]["whenInputProjectileId"] = 77
    else:
        stages[1]["spawnSites"][0]["whenInputProjectileId"] = 77
    with pytest.raises((AssertionError, KeyError)):
        _assert_author_ammo(mechanics, packet, name)


def test_spawn_argument_additions_leave_existing_catalog_facts_unchanged():
    import json
    from generate_native_ammo_facts import extract
    assembly = Path(os.environ.get('INFINI_NATIVE_AMMO_ASSEMBLY', '/missing-native-assembly'))
    baseline = Path(os.environ.get('INFINI_AMMO_BASELINE_REPORT', '/missing-baseline-report'))
    if not assembly.exists() or not baseline.exists():
        pytest.skip('exact assembly and pre-extension catalog report unavailable')
    actual = json.loads(json.dumps(extract(assembly)))
    for source in actual:
        for row in source['records']:
            for spawn in row['spawnSites']:
                for key in ('spawnInputs', 'whenSourceCondition', 'spawnInputCoverage'):
                    spawn.pop(key)
    assert actual == json.loads(baseline.read_text())['sources']


@pytest.mark.parametrize('branches', range(1, 7))
def test_spawn_argument_last_definition_matches_all_source_path_choices(branches):
    from itertools import product
    from native_hit_status_analysis import Instruction as I
    ops = [('ldarg', 2), ('ldfld', 'Terraria.Item.shoot'), ('stloc', 0),
           ('ldarg', 2), ('ldfld', 'Terraria.Item.type'), ('const', 98643), ('bne', None)]
    for b in range(branches):
        start = len(ops)
        ops += [('ldarg', 0), ('ldfld', 'Fixture.flag' + str(b)), ('brfalse', start + 5),
                ('const', b + 10), ('stloc', 20)]
    ops += [('ldloc', 7), ('ldloc', 8), ('ldloc', 9), ('ldloc', 0), ('ldloc', 20),
            ('ldloc', 5), ('ldarg', 1), ('const', 0.0), ('const', 0.0), ('const', 0.0),
            ('call', ('Terraria.Projectile.NewProjectile', 10, False, True)), ('pop', None), ('ret', None)]
    ops[6] = ('bne', len(ops) - 1)
    row, = ammo_method_facts([I(n, op, arg) for n, (op, arg) in enumerate(ops)], 'ItemCheck_Shoot')
    value = row['spawnSites'][0]['spawnInputs']['damage']
    alternatives = value.get('alternatives', [{'whenSourceCondition': True, 'value': value}])

    def evaluate(condition, states):
        if type(condition) is bool:
            return condition
        if condition['kind'] == 'branch':
            flag = int(condition['value']['member'].removeprefix('Fixture.flag'))
            return (not states[flag]) == condition['taken']
        return evaluate(condition['then'] if evaluate(condition['condition'], states) else condition['else'], states)

    for states in product([False, True], repeat=branches):
        selected = [a['value'].get('value', {}).get('value') for a in alternatives if evaluate(a['whenSourceCondition'], states)]
        expected = next((b + 10 for b in range(branches - 1, -1, -1) if states[b]), None)
        assert selected == [expected]


def test_spawn_argument_local_depth_bound_does_not_discard_other_fields():
    mutations = [('const', 1), ('stloc', 40)]
    for local in range(41, 80):
        mutations += [('ldloc', local - 1), ('stloc', local)]
    mutations += [('ldloc', 79), ('stloc', 14)]
    row, = ammo_method_facts(_spawn_argument_fixture(mutate=mutations), 'ItemCheck_Shoot')
    spawn, = row['spawnSites']
    damage = spawn['spawnInputCoverage']['fields']['damage']
    assert any(issue['reason'] in {'source_local_definition_depth_bound', 'source_expression_depth_bound'} for issue in damage['unresolved'])
    assert spawn['spawnInputs']['owner']['kind'] == 'argument'
    assert spawn['spawnInputs']['ai0']['value'] == 0.0
    assert spawn['spawnInputs']['type']['reason'] == 'branch_entry_value_unknown'
