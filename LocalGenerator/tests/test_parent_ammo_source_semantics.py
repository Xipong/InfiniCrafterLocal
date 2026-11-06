"""Ammo identity is an input; native source rules are separate read-only evidence."""
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
    import json
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    directory = Path(os.environ.get('INFINI_PARENT_SPAWN_PACKET_DIR', '/missing-native-spawn-packets'))
    if not directory.exists():
        pytest.skip('actual native spawn Prepare packets unavailable')
    monkeypatch.setattr(llm_config, 'LLM_RESPONSE_FORMAT_MODE', mode)
    for name in ('eventide', 'terra', 'daedalus'):
        packet = json.loads((directory / (name + '.packet.json')).read_text())
        before = copy.deepcopy(packet)
        request, _, _ = build_initial_author_request(packet['itemA'], packet['itemB'], 'spawn-source-roundtrip', model_name='offline-test-model')
        raw = expand_native_source_references(request_dossier(request))['parents']['A']['packet']['raw']['ammo']
        assert raw['projectileSemanticsReference'] == packet['itemA']['ammoRaw']['projectileSemanticsReference']
        sites = raw['projectileSemanticsReference']['stages'][1]['spawnSites']
        assert sites and all('spawnInputs' in s and 'spawnInputCoverage' in s for s in sites)
        if name == 'eventide':
            assert any(n.get('operator') == 'mul' and n['right'].get('value') == 2 for n in _source_nodes(sites[0]['spawnInputs']['damage']))
            assert any(n.get('sourceBranchIlOffset') == 10866 for n in _source_nodes(sites[0]['spawnInputs']['damage']))
            assert any(n.get('operator') == 'rem' for n in _source_nodes(sites[0]['spawnInputs']['ai1']))
        if name != 'terra':
            assert [r['inventorySlot'] for r in raw['playerInventoryAmmoRaw']] == [0, 54, 55]
            assert all(r['inventorySlot'] == -1 for r in raw['fallbackAmmoRaw'])
            fingerprint = packet['itemA']['fingerprint']['ammoRaw']
            assert fingerprint['playerInventoryObservation']['reason'] == 'no_player'
            assert fingerprint['playerInventoryAmmoRaw'] is None
        assert packet == before


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
