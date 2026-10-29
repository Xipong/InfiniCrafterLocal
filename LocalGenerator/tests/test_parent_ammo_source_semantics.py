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
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
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
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
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
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
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
