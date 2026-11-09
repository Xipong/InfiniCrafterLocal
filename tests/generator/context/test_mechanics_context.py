"""Producer-backed Author view: useful mechanics and explicit approximation."""
import copy
import json

import pytest

from infini_local.pipelines.context.mechanics_context import mechanics_context
from infini_local.pipelines.context.parent_stage import parent_context_for_stage
from infini_local.pipelines.context.parents import compact_projectile_profile


def _profile(kind=31):
    return {
        "type": kind, "extraUpdates": 1, "penetrate": -1, "tileCollide": False,
        "usesLocalNPCImmunity": True, "localNPCHitCooldown": 7,
        "mechanicsSource": {"source": "native_mechanics_source", "version": 1,
            "identity": {"type": kind, "aiStyle": 5}, "unresolved": ["opaque_hook"],
            "records": [{"method": "Projectile.AI", "sourceMethodSha256": "sha",
                "sourceModuleVersionId": "module", "excludedCallOffsets": [40],
                "coverage": "approximate_identity_view", "code": "if (wet) damage *= 2;"}]},
    }


def _raw():
    return {"item": {"damage": 24, "tooltipLines": ["Exact  text", ""],
        "parentSourceGraph": {"diagnosticSecretMarker": "full_graph"},
        "nativeContactHitStatusReference": {"effects": [{"buff": 24, "duration": 180}]}},
        "directProjectile": _profile(), "ammo": {"playerInventoryAmmoRaw": [],
            "fallbackAmmoRaw": [{"type": 40, "damage": 3}, {"type": 40, "damage": 3}]}}


def test_actual_stage_projects_only_author_and_keeps_diagnostic_input():
    raw = _raw()
    before = copy.deepcopy(raw)
    output = parent_context_for_stage({"A": {"packet": {"name": "arbitrary", "raw": raw}}}, stage="author")
    view = output["parents"]["A"]["packet"]["raw"]
    # Expand exact presentation sharing if a field became an alias.
    def expand(v):
        if isinstance(v, dict):
            if set(v) == {"sourceSameAs"}:
                return expand(output["nativeSourceFacts"][v["sourceSameAs"]])
            return {k: expand(x) for k, x in v.items()}
        return [expand(x) for x in v] if isinstance(v, list) else v
    view = expand(view)
    assert "parentSourceGraph" not in view["item"]
    assert view["item"]["tooltipLines"] == before["item"]["tooltipLines"]
    mechanics = view["mechanics"]
    assert mechanics["source"][0]["code"] == "if (wet) damage *= 2;"
    assert mechanics["projectiles"][0]["defaults"]["localNPCHitCooldown"] == 7
    assert mechanics["projectiles"][0]["defaults"]["tileCollide"] is False
    assert mechanics["ammoInputs"]["playerInventoryAmmoRaw"] == []
    assert mechanics["ammoInputs"]["fallbackAmmoRaw"] == before["ammo"]["fallbackAmmoRaw"]
    assert mechanics["itemRules"]["nativeContactHitStatusReference"]["effects"][0]["duration"] == 180
    assert mechanics["uncertainty"]["sourceGaps"] == ["opaque_hook"]
    assert "assumes" in mechanics["reading"]
    assert raw == before
    for stage in ("visual", "vfx"):
        other = parent_context_for_stage({"A": {"packet": {"raw": raw}}}, stage=stage)
        assert "mechanics" not in other["parents"]["A"]["packet"]["raw"]
        assert "parentSourceGraph" in other["parents"]["A"]["packet"]["raw"]["item"]


def test_child_omission_requires_every_site_and_exact_method_certificate():
    raw = _raw()
    profile = raw["directProjectile"]
    calls = [{"at": 40, "method": "Projectile.AI", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module"},
             {"at": 41, "method": "Projectile.AI", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module"},
             {"at": 40, "method": "Projectile.AI", "sourceMethodSha256": "other", "sourceModuleVersionId": "module"}]
    profile["referencedProjectiles"] = {"sourceCalls": calls, "references": [
        {"type": 32, "sourceCallIndices": [0], "profile": _profile(32)},
        {"type": 33, "sourceCallIndices": [0, 1], "profile": _profile(33)},
        {"type": 34, "sourceCallIndices": [2], "profile": _profile(34)},
        {"type": 35, "sourceCallIndices": [], "profile": _profile(35)},
    ]}
    card = mechanics_context(raw)["mechanics"]
    assert [r["defaults"]["type"] for r in card["projectiles"]] == [31, 33, 34, 35]
    assert [r["child"] for r in card["uncertainty"]["excludedChildProfiles"]] == [32]



def test_child_type_filter_requires_complete_literal_union_and_exact_call():
    raw = _raw()
    profile = raw["directProjectile"]
    record = profile["mechanicsSource"]["records"][0]
    record["spawnTypeCandidates"] = [{"at": 41, "projectileTypes": [0, 32],
        "scope": "all_surviving_local_writes_are_integer_literals; conservative_union_not_execution"}]
    call = {"at": 41, "method": "Projectile.AI", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module"}
    profile["referencedProjectiles"] = {"sourceCalls": [call], "references": [
        {"type": kind, "sourceCallIndices": [0], "profile": _profile(kind)} for kind in (32, 33)]}
    before = copy.deepcopy(raw)
    card = mechanics_context(raw)["mechanics"]
    assert [r["defaults"]["type"] for r in card["projectiles"]] == [31, 32]
    assert card["uncertainty"]["excludedChildProfiles"][0]["child"] == 33
    assert raw == before
    for mutate in (
        lambda r, c: c.update(at=42),
        lambda r, c: c.update(sourceMethodSha256="other"),
        lambda r, c: c.pop("sourceModuleVersionId"),
        lambda r, c: r.pop("sourceMethodSha256"),
        lambda r, c: r["spawnTypeCandidates"][0].update(scope="unknown"),
        lambda r, c: r["spawnTypeCandidates"][0].update(projectileTypes=[]),
        lambda r, c: r["spawnTypeCandidates"][0].update(projectileTypes=[True]),
        lambda r, c: r["spawnTypeCandidates"].append({"at": 41, "projectileTypes": [33]}),
    ):
        candidate = copy.deepcopy(before)
        p = candidate["directProjectile"]
        mutate(p["mechanicsSource"]["records"][0], p["referencedProjectiles"]["sourceCalls"][0])
        assert [r["defaults"]["type"] for r in mechanics_context(candidate)["mechanics"]["projectiles"]] == [31, 32, 33]
    # A candidate supplied by both known and unknown calls must survive.
    mixed = copy.deepcopy(before)
    links = mixed["directProjectile"]["referencedProjectiles"]
    links["sourceCalls"].append({**call, "at": 42})
    for child in links["references"]:
        child["sourceCallIndices"] = [0, 1]
    assert [r["defaults"]["type"] for r in mechanics_context(mixed)["mechanics"]["projectiles"]] == [31, 32, 33]
    links["sourceCalls"][1]["at"] = 40  # Already excluded whole call, so both proofs now exclude 33.
    assert [r["defaults"]["type"] for r in mechanics_context(mixed)["mechanics"]["projectiles"]] == [31, 32]



def test_excluded_child_keeps_canonical_capture_used_by_an_exact_alias():
    raw = _raw()
    profile = raw["directProjectile"]
    profile["referencedProjectiles"] = {"sourceCalls": [
        {"at": 40, "method": "Projectile.AI", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module"}],
        "references": [{"type": 32, "sourceCallIndices": [0], "profile": _profile(32)}]}
    raw["effectiveProjectile"] = {"sameAs": "raw.directProjectile.referencedProjectiles.references[0].profile"}
    card = mechanics_context(raw)["mechanics"]
    assert [r["defaults"].get("type") for r in card["projectiles"]] == [31, 32, None]
    assert card["uncertainty"]["excludedChildProfiles"] == []
    assert card["projectiles"][-1]["defaults"]["sameDefaultsAsSourcePath"] == \
        "directProjectile.referencedProjectiles.references[0].profile"

def test_absent_generated_and_unknown_source_contracts_do_not_gain_approximation():
    raw = _raw()
    raw["directProjectile"].pop("mechanicsSource")
    assert mechanics_context(raw) is None
    raw = _raw()
    raw["generatedParent"] = {"runtimeProgram": {"exact": True}}
    assert mechanics_context(raw) is None
    raw = _raw()
    raw["directProjectile"]["mechanicsSource"]["version"] = True
    assert mechanics_context(raw) is None


def test_capture_contract_survives_profile_compaction_without_mutation():
    raw = _profile()
    before = copy.deepcopy(raw)
    compact = compact_projectile_profile(raw)
    assert compact["mechanicsSource"] == raw["mechanicsSource"]
    assert raw == before


def test_wrong_identity_and_malformed_exclusion_receipts_do_not_activate():
    for mutate in (
        lambda v: v["identity"].update(type=999),
        lambda v: v.update(unresolved=None),
        lambda v: v["records"][0].update(excludedCallOffsets=[True]),
    ):
        raw = _raw()
        mutate(raw["directProjectile"]["mechanicsSource"])
        assert mechanics_context(raw) is None


def test_actual_author_request_delivers_mechanics_without_mutating_parent(monkeypatch):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier, expand_native_source_references
    raw = _raw()
    parent = {**raw["item"], "name": "test", "directProjectileRaw": raw["directProjectile"], "ammoRaw": raw["ammo"]}
    before = copy.deepcopy(parent)
    for mode in ("json_schema", "json_object"):
        monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
        request, _, _ = build_initial_author_request(parent, {"name": "Material"}, "local-only", model_name="offline")
        dossier = expand_native_source_references(request_dossier(request))
        view = dossier["parents"]["A"]["packet"]["raw"]
        assert "mechanics" in view
        assert "diagnosticSecretMarker" not in json.dumps(dossier)
        assert "parentSourceGraph" not in view["item"]
        assert view["mechanics"]["source"][0]["code"] == "if (wet) damage *= 2;"
        assert parent == before


def test_native_object_refusals_remain_explicit_in_mechanics_view():
    raw = _raw()
    source = raw["directProjectile"]["mechanicsSource"]
    source["unresolved"] = [{"method": "Projectile.Helper", "unresolved": "character_bound"}]
    source["strictSourceRefusals"] = [{"method": "Projectile.Kill", "unresolved": "source_unavailable"}]
    assert mechanics_context(raw)["mechanics"]["uncertainty"]["sourceGaps"] == [
        "Projectile.Helper:character_bound", "Projectile.Kill:source_unavailable"]


def test_only_exclusively_presentation_records_are_omitted_and_equal_code_is_shared():
    raw = _raw()
    original = raw["directProjectile"]["mechanicsSource"]["records"][0]
    raw["directProjectile"]["mechanicsSource"]["records"] = [
        {**original, "method": "Draw", "graphPaths": [["draw", "programs", 0]]},
        {**original, "method": "Update", "graphPaths": [["positionIntegration"]]},
        {**original, "method": "Mixed", "graphPaths": [["draw"], ["motion"]]},
    ]
    raw["effectiveProjectile"] = copy.deepcopy(raw["directProjectile"])
    raw["effectiveProjectile"]["type"] = 88
    raw["effectiveProjectile"]["mechanicsSource"]["identity"]["type"] = 88
    source = mechanics_context(raw)["mechanics"]["source"]
    assert [row["method"] for row in source] == ["Update", "Mixed"]
    assert all(row["projectiles"] == [31, 88] for row in source)
    assert all(row["code"] == original["code"] for row in source)


def test_equal_defaults_share_values_but_keep_every_candidate_slot_and_role():
    raw = _raw()
    raw["ammo"]["playerInventoryProjectileRaw"] = [
        {**_profile(), "source": "inventory", "inventorySlot": 3},
        {**_profile(), "source": "inventory", "inventorySlot": 4},
    ]
    profiles = mechanics_context(raw)["mechanics"]["projectiles"]
    assert len(profiles) == 1
    assert profiles[0]["defaults"]["extraUpdates"] == 1
    assert profiles[0]["captures"] == [
        {"sourcePath": "directProjectile"},
        {"sourcePath": "ammo.playerInventoryProjectileRaw[0]", "source": "inventory", "inventorySlot": 3},
        {"sourcePath": "ammo.playerInventoryProjectileRaw[1]", "source": "inventory", "inventorySlot": 4},
    ]


def test_malformed_child_keeps_following_capture_index_and_style_mismatch_refuses():
    raw = _raw()
    raw["directProjectile"]["referencedProjectiles"] = {"references": [None, {"profile": _profile(91)}]}
    card = mechanics_context(raw)["mechanics"]
    assert card["projectiles"][1]["captures"][0]["sourcePath"].endswith("references[1].profile")
    assert card["uncertainty"]["sourceGaps"][0].startswith("malformed_child_reference:")
    raw["directProjectile"]["aiStyle"] = 7
    assert mechanics_context(raw) is None


def test_current_item_flags_and_unit_views_survive_without_retired_runtime_probe():
    raw = _raw()
    raw["vanillaFlags"] = {"accessory": True, "defense": 7}
    raw["runtimeProbe"] = {"observedHits": 2, "scope": "single test observation"}
    raw["sourceMotionUnits"] = {"values": [{"sourcePath": "raw.directProjectile.timeLeft", "value": 60, "units": "projectile updates"}]}
    result = mechanics_context(raw)
    assert result is not None
    assert result["vanillaFlags"] == raw["vanillaFlags"]
    assert "runtimeProbe" not in result
    assert result["sourceMotionUnits"] == raw["sourceMotionUnits"]


def test_partial_mechanics_keeps_verified_dispatcher_and_lifecycle_regions():
    raw = _raw()
    guard = {"field": "Terraria.Projectile.aiStyle", "literal": 84}
    raw["directProjectile"]["attackReference"] = {
        "nativeCSharpSource": {"source": "read_only_native_csharp_view", "version": 1, "records": [
            {"id": "beam", "method": "Projectile.VanillaAI", "code": "if (charge > 120) damage *= 3;", "coverage": "conditional_ast_regions", "entryGuards": [guard]},
            {"id": "hold", "method": "Projectile.AI", "code": "unselected larger body", "coverage": "whole_method"},
            {"id": "draw", "method": "Projectile.Draw", "code": "DrawColor();", "coverage": "whole_method"},
        ]},
        "motion": {"nativeCSharpSourceRef": "beam"},
        "draw": {"nativeCSharpSourceRef": "draw"},
        "lifecycle": {"source": "read_only_conditional_native_lifecycle_csharp", "version": 1, "scope": "entry guard must be reached", "unresolved": [], "records": [
            {"method": "Projectile.Kill", "code": "SpawnChild(8);", "coverage": "conditional_ast_regions", "entryCondition": "type == 31"}]},
    }
    rows = mechanics_context(raw)["mechanics"]["source"]
    assert [r["method"] for r in rows] == ["Projectile.AI", "Projectile.VanillaAI", "Projectile.AI", "Projectile.Kill"]
    assert rows[2]["code"] == "unselected larger body"
    assert rows[2]["coverage"] == "whole_method"
    assert rows[1]["code"] == "if (charge > 120) damage *= 3;"
    assert rows[1]["entryGuards"] == [guard]
    assert rows[3]["entryCondition"] == "type == 31"
    assert rows[3]["entryScope"] == "entry guard must be reached"


def test_exact_profile_alias_is_not_a_source_extraction_failure():
    raw = _raw()
    raw["effectiveProjectile"] = {"sameAs": "raw.directProjectile"}
    gaps = mechanics_context(raw)["mechanics"]["uncertainty"]["sourceGaps"]
    assert not any("effectiveProjectile" in gap for gap in gaps)


def test_compaction_keeps_verified_region_when_strict_source_view_prefers_graph():
    import hashlib
    from tests.generator.context.test_native_csharp_source_view import _parent
    from infini_local.pipelines.context.native_csharp_source import native_csharp_source_for_llm
    parent = _parent()
    profile = parent["directProjectileRaw"]
    reference = profile["attackReference"]
    window = {"field": "type", "literal": 1, "guardOffset": 3}
    reference["motion"]["programs"][0]["identityWindows"] = [window]
    reference["motion"]["programs"].append(copy.deepcopy(reference["motion"]["programs"][0]))
    record = reference["nativeCSharpSource"]["records"][0]
    record.update(coverage="conditional_ast_regions", coveredWindows=[window], entryGuards=[{
        "field": "Terraria.Projectile.type", "operator": "==", "literal": 1, "ilOffset": 3,
        "scope": "only_if_original_guard_is_reached; enclosing_dispatch_unknown"}])
    record["graphPaths"].append(["motion", "programs", 1])
    record["code"] += "/*" + "source-only fixture padding " * 1000 + "*/"
    record["codeSha256"] = hashlib.sha256(record["code"].encode()).hexdigest()
    legacy, _ = native_csharp_source_for_llm(reference, profile["referencedProjectiles"]["sourceCalls"])
    assert "nativeCSharpSource" not in legacy
    profile["mechanicsSource"] = {**_profile(1)["mechanicsSource"], "records": []}
    compact = compact_projectile_profile(profile)
    rows = mechanics_context({"directProjectile": compact})["mechanics"]["source"]
    assert any(row["code"] == record["code"] and row["entryGuards"] == record["entryGuards"] for row in rows)
    # A failed hash is not admitted as the verified supplement.
    record["codeSha256"] = "0" * 64
    profile["mechanicsSource"]["verifiedSourceRecords"] = [copy.deepcopy(record)]
    invalid = compact_projectile_profile(profile)
    assert "verifiedSourceRecords" not in invalid["mechanicsSource"]
    assert not mechanics_context({"directProjectile": invalid})["mechanics"]["source"]


def test_graph_extraction_failure_remains_visible_when_graph_is_not_sent():
    raw = _raw()
    raw["directProjectile"]["attackReference"] = {"coverage": {
        "unresolved": ["motion_source:Projectile.Helper():exception_regions"]}}
    result = mechanics_context(raw)
    assert "motion_source:Projectile.Helper():exception_regions" in result["mechanics"]["uncertainty"]["sourceGaps"]
    assert "attackReference" not in str(result["mechanics"]["projectiles"])


def test_repeated_source_site_gaps_cannot_hide_distinct_coverage_refusals():
    raw = _raw()
    method = "motion_source:Projectile.ArbitraryHelper"
    sites = [f"{method}:effect_source_site@{offset}:effect_source_site_count_bound"
             for offset in range(20, 35)]
    distinct = [f"{method}:unspecialized_spawn_site_not_captured; bounded_source_only",
                *[f"future_source_failure_{index}_with_its_full_detail" for index in range(14)]]
    source = raw["directProjectile"]["mechanicsSource"]
    source["unresolved"] = [*sites, *distinct]
    before = copy.deepcopy(raw)
    card = mechanics_context(raw)["mechanics"]
    gaps = card["uncertainty"]
    assert gaps["sourceGaps"] == sorted(distinct)
    assert gaps["sourceGapSites"] == [{"source": method, "reason": "effect_source_site_count_bound",
                                       "ilOffsets": list(range(20, 35))}]
    reconstructed = [f"{row['source']}:effect_source_site@{offset}:{row['reason']}"
                     for row in gaps["sourceGapSites"] for offset in row["ilOffsets"]]
    assert sorted([*gaps["sourceGaps"], *reconstructed]) == sorted(source["unresolved"])
    assert raw == before
    # Future diagnostic syntax remains literal instead of being guessed/grouped.
    source["unresolved"] = [f"{method}:effect_source_site@20:future_refusal"]
    assert mechanics_context(raw)["mechanics"]["uncertainty"]["sourceGaps"] == source["unresolved"]


def test_position_integration_gates_survive_while_draw_only_source_is_omitted():
    raw = _raw()
    records = raw["directProjectile"]["mechanicsSource"]["records"]
    records.extend([
        {"method": "Projectile.UpdatePosition", "code": "void UpdatePosition() { return; }",
         "graphPaths": [["positionIntegration"]]},
        {"method": "Projectile.Draw", "code": "DrawPixels();", "graphPaths": [["draw", "dispatch"]]},
    ])
    code = mechanics_context(raw)["mechanics"]["source"]
    assert any(row["method"] == "Projectile.UpdatePosition" and "return;" in row["code"] for row in code)
    assert not any(row["method"] == "Projectile.Draw" for row in code)


def test_equal_projectile_defaults_share_without_losing_capture_shoot_speeds():
    raw = _raw()
    raw["directProjectile"]["itemShootSpeed"] = 6.1
    raw["ammo"]["playerInventoryProjectileRaw"] = [copy.deepcopy(raw["directProjectile"])]
    ammo_profile = raw["ammo"]["playerInventoryProjectileRaw"][0]
    ammo_profile.update(itemShootSpeed=3, inventorySlot=54, source="ammo.shoot")
    before = copy.deepcopy(raw)
    rows = mechanics_context(raw)["mechanics"]["projectiles"]
    assert len(rows) == 1
    assert "itemShootSpeed" not in rows[0]["defaults"]
    assert rows[0]["captures"] == [
        {"sourcePath": "directProjectile", "itemShootSpeed": 6.1},
        {"sourcePath": "ammo.playerInventoryProjectileRaw[0]", "source": "ammo.shoot",
         "inventorySlot": 54, "itemShootSpeed": 3},
    ]
    assert raw == before
    ammo_profile["penetrate"] = 2
    assert len(mechanics_context(raw)["mechanics"]["projectiles"]) == 2


def test_missing_readable_caller_keeps_connected_slice_not_just_its_helper():
    raw = _raw()
    helper = raw["directProjectile"]["mechanicsSource"]["records"][0]
    helper.update(method="Terraria.Utils.ConeHelper", code="bool ConeHelper(float length) { return opaque; }")
    program = {"method": "T.Projectile.Colliding",
        "observations": [{"kind": "collision_call", "call": "Utils.ConeHelper", "arguments": {"length": "d0"},
                          "requiredPredicates": ["b0"], "step": 2}],
        "dependencies": {"d0": {"expression": "(90*scale)", "requiredPredicates": ["b0"], "step": 1}},
        "predicates": [{"id": "b0", "op": "brfalse", "inputs": ["opaque"], "successors": [9, 1], "step": 0}],
        "symbols": {"Utils.ConeHelper": "T.Utils.ConeHelper(float)"}, "unresolved": ["opaque"]}
    raw["directProjectile"]["attackReference"] = {
        "collision": program, "scope": "conditional_source_only", "expressionNotation": "symbolic"}
    before = copy.deepcopy(raw)
    card = mechanics_context(raw)["mechanics"]
    assert card["sourceSlices"] == [{"projectiles": [31], "role": "collision", "program": program,
                                     "scope": "conditional_source_only", "expressionNotation": "symbolic"}]
    assert raw == before
    raw["directProjectile"]["mechanicsSource"]["records"].append({
        "method": "Terraria.Projectile.Colliding", "code": "bool Colliding() { return ConeHelper(90 * scale); }"})
    assert mechanics_context(raw)["mechanics"]["sourceSlices"][0]["program"] == program


def test_slice_source_refs_bind_to_emitted_indices_with_profile_local_ids():
    raw = _raw()
    for field, kind, helper in (("directProjectile", 31, "First"), ("effectiveProjectile", 88, "Second")):
        profile = _profile(kind)
        record = {"id": "s1", "method": f"Terraria.Utils.{helper}",
                  "code": f"bool {helper}() {{ return true; }}", "coverage": "whole_method"}
        profile["mechanicsSource"]["records"] = [copy.deepcopy(record)]
        profile["attackReference"] = {
            "nativeCSharpSource": {"source": "read_only_native_csharp_view", "version": 1,
                                  "records": [record]},
            "collision": {"method": "T.Projectile.Colliding", "observations": [],
                          "predicateSources": [{"nativeCSharpSourceRef": "s1", "scope": "conditional"},
                                               {"nativeCSharpSourceRef": "missing"}]}}
        raw[field] = profile
    before = copy.deepcopy(raw)
    card = mechanics_context(raw)["mechanics"]
    assert raw == before
    for index, (kind, helper) in enumerate(((31, "First"), (88, "Second"))):
        row = card["sourceSlices"][index]
        assert row["projectiles"] == [kind]
        refs = row["program"]["predicateSources"]
        assert refs[0]["mechanicsSourceIndex"] == index
        assert refs[0]["scope"] == "conditional"
        assert "nativeCSharpSourceRef" not in refs[0]
        assert card["source"][refs[0]["mechanicsSourceIndex"]]["method"] == f"Terraria.Utils.{helper}"
        assert refs[1]["unresolvedNativeCSharpSourceRef"] == "missing"
        assert refs[1]["sourceReferenceStatus"] == "no_unique_emitted_source_record"
    assert "mechanicsSourceIndex" in card["reading"]


def test_slice_ref_does_not_bind_a_different_body_with_the_same_method():
    raw = _raw()
    profile = raw["directProjectile"]
    profile["mechanicsSource"]["records"] = [
        {"method": "Terraria.Utils.Helper", "code": "selected partial body"}]
    profile["attackReference"] = {
        "nativeCSharpSource": {"source": "read_only_native_csharp_view", "version": 1,
                              "records": [{"id": "s1", "method": "Terraria.Utils.Helper", "code": "other body"}]},
        "collision": {"method": "T.Projectile.Colliding", "observations": [],
                      "predicateSources": [{"nativeCSharpSourceRef": "s1"}]}}
    mechanics = mechanics_context(raw)["mechanics"]
    ref = mechanics["sourceSlices"][0]["program"]["predicateSources"][0]
    assert mechanics["source"][ref["mechanicsSourceIndex"]]["code"] == "other body"
    assert "unresolvedNativeCSharpSourceRef" not in ref


def test_capture_speed_alias_resolution_preserves_unknown_and_explicit_values():
    raw = _raw()
    raw["directProjectile"]["itemShootSpeed"] = 6.1
    raw["effectiveProjectile"] = {"sameAs": "raw.directProjectile", "source": "effective"}
    raw["ammo"]["nativeReplacementProjectileRaw"] = [
        {"sameAs": "raw.effectiveProjectile"},
        {"sameAs": "raw.directProjectile", "itemShootSpeed": 0},
        {"sameAs": "raw.notCaptured"},
        {"sameAs": "raw.ammo.nativeReplacementProjectileRaw[4]"},
        {"sameAs": "raw.ammo.nativeReplacementProjectileRaw[3]"},
    ]
    before = copy.deepcopy(raw)
    card = mechanics_context(raw)["mechanics"]
    captures = {v["sourcePath"]: v for row in card["projectiles"] for v in row["captures"]}
    assert captures["effectiveProjectile"]["itemShootSpeed"] == 6.1
    assert captures["ammo.nativeReplacementProjectileRaw[0]"]["itemShootSpeed"] == 6.1
    assert captures["ammo.nativeReplacementProjectileRaw[1]"]["itemShootSpeed"] == 0
    for index in (2, 3, 4):
        assert "itemShootSpeed" not in captures[f"ammo.nativeReplacementProjectileRaw[{index}]"]
    aliases = [row["defaults"]["sameDefaultsAsSourcePath"] for row in card["projectiles"]
               if "sameDefaultsAsSourcePath" in row["defaults"]]
    assert "notCaptured" in aliases
    assert "ammo.nativeReplacementProjectileRaw[4]" in aliases
    assert "ammo.nativeReplacementProjectileRaw[3]" in aliases
    assert raw == before


def _caller_parent(role="collision"):
    profile = _profile()
    profile["mechanicsSource"]["records"] = [{"method": "Terraria.Utils.ConeHelper",
        "code": "bool ConeHelper(float length) { return opaque; }", "coverage": "approximate_identity_view"}]
    graph = {"method": "Terraria.Projectile.Colliding", "sourceModuleVersionId": "module",
        "sourceMethodSha256": "a" * 64,
        "observations": [{"kind": "collision_call", "call": "Utils.ConeHelper", "arguments": {"length": "l7@10"},
                          "at": 12, "block": 4, "requiredPredicates": ["b3"]}],
        "dependencies": {"l7@10": {"expression": "mul(90,ldfld(Projectile.scale,this))",
                                   "at": 10, "block": 4, "requiredPredicates": ["b3"]}},
        "predicates": [{"id": "b3", "at": 3, "block": 0, "op": "brfalse",
                        "inputs": ["ldfld(Projectile.wet,this)"], "successors": [20, 4]}],
        "symbols": {"Utils.ConeHelper": "T.Utils.ConeHelper(float)"}, "unresolved": ["opaque runtime predicate"]}
    profile["attackReference"] = {"source": "read_only_native_attack_source", "version": 1,
        "identityPredicates": {"Projectile.type": 31, "Projectile.aiStyle": 5},
        role: {"programs": [graph]} if role == "motion" else [graph] if role == "motionDispatchEffects" else graph,
        "coverage": {"proved": [], "unresolved": [], "boundaries": []}}
    return {"name": "source-only caller", "directProjectileRaw": profile}


def _request_parent_views(monkeypatch, parent, mode):
    """Both production requests; Repair also executes its frozen transaction."""
    from infini_local.core import llm_config
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.pipelines.author.request import build_initial_author_request, build_gameplay_repair_dossier
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from prompt_packet_helpers import expand_native_source_references, request_dossier
    from repair_test_helpers import repair_with_response, assert_delivery

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "offline", model_name="offline")
    assert request["response_format"]["type"] == mode
    author = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    doc = build_runtime_fixture("workbench_blade")
    stats = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "item_stats")
    stats["params"].pop("manaCost")  # Accepted absence must remain frozen too.
    good = copy.deepcopy(doc)
    incoming = copy.deepcopy(stats)
    incoming["params"]["knockback"] = 5.0  # Schema-valid, but out-of-scope.
    stats["params"]["damage"] = -1
    broken = copy.deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    baseline = build_gameplay_repair_dossier(doc, {}, {}, failure_report=report)
    repaired, request = repair_with_response(monkeypatch, doc,
        {"note": "correct only invalid damage", "callsUpsert": [incoming]}, mode, parents=(parent, {}))
    repair = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    assert repair["repairScope"] == baseline["repairScope"]
    assert repair["acceptedItemContext"]["runtimeProgram"] == broken["runtimeProgram"]
    assert repaired["runtimeProgram"] == good["runtimeProgram"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert validate_runtime_program(repaired)["ok"]
    assert_delivery(repaired)
    assert doc == broken and parent == before
    return [author["parents"]["A"]["packet"]["raw"], repair["parents"]["a"]["packet"]["raw"]]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("role", ["collision", "motion", "motionDispatch", "motionDispatchEffects", "positionIntegration"])
def test_production_requests_keep_ordered_caller_arguments_and_control_flow(monkeypatch, mode, role):
    for raw in _request_parent_views(monkeypatch, _caller_parent(role), mode):
        row, = raw["mechanics"]["sourceSlices"]
        assert row["role"] == role
        program = row["program"]
        assert program["method"] == "Terraria.P.Colliding" and program["nativeNames"] == 1
        assert "P=Projectile" in row["behaviorView"]["scope"]
        branch, definition, call = program["operations"]
        assert "Projectile.wet" in branch["inputs"][0]
        assert branch["successors"] == [20, 4]
        assert branch["step"] < definition["step"] < call["step"]
        assert "90" in definition["expression"] and "Projectile.scale" in definition["expression"]
        assert call["arguments"]["length"] == definition["bind"]
        assert call["requiredPredicates"] == definition["requiredPredicates"] == [branch["id"]]
        assert "ConeHelper" in call["call"] and "ConeHelper" in json.dumps(program["symbols"])
        assert program["unresolved"] == ["opaque runtime predicate"]
        assert row["branchTests"]["brfalse"]
        assert "sourceFacts" not in raw["mechanics"]["uncertainty"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("variant", ["child_refusal", "graph_refusal", "unknown_attack", "unknown_record", "record_collision"])
def test_production_requests_keep_owned_refusals_and_unfamiliar_conditions(monkeypatch, mode, variant):
    parent = _caller_parent()
    profile = parent["directProjectileRaw"]
    marker = "source_condition_not_established"
    if variant == "child_refusal":
        marker = "single_hop_profile_count_bound"
        profile["referencedProjectiles"] = {"source": "native_single_hop_projectile_references", "version": 1,
            "sourceCalls": [], "references": [{"type": 32, "sourceCallIndices": [], "unresolved": marker}]}
    elif variant == "graph_refusal":
        from tests.generator.context.test_native_csharp_source_view import _parent
        parent = _parent()
        profile = parent["directProjectileRaw"]
        profile["mechanicsSource"] = _profile(1)["mechanicsSource"]
        marker = "UNIQUE_SELECTION_WORK_BOUND:257>192"
        profile["attackReference"]["motion"]["programs"][0]["identitySelectionUnavailable"] = marker
    elif variant == "unknown_attack":
        profile["attackReference"]["futureMovementGate"] = {"unresolved": marker, "dependsOn": "b3"}
    elif variant == "unknown_record":
        profile["mechanicsSource"]["records"][0]["futureEntryConstraint"] = {"unresolved": marker, "enabled": False}
    else:
        profile["mechanicsSource"]["records"][0]["projectiles"] = {"unresolved": marker, "sourceFields": [False, 0, None]}
    for raw in _request_parent_views(monkeypatch, parent, mode):
        mechanics = raw["mechanics"]
        if variant == "unknown_record":
            assert mechanics["source"][0]["sourceFields"]["futureEntryConstraint"] == {"unresolved": marker, "enabled": False}
        elif variant == "record_collision":
            assert mechanics["source"][0]["projectiles"] == [31]
            assert mechanics["source"][0]["sourceFields"]["projectiles"] == {"unresolved": marker, "sourceFields": [False, 0, None]}
        else:
            facts = mechanics["uncertainty"]["sourceFacts"]
            owned = [row for row in facts if marker in json.dumps(row["value"])]
            assert len(owned) == 1
            assert owned[0]["sourcePath"].startswith("directProjectile.")
            if variant == "child_refusal":
                assert owned[0]["sourcePath"] == "directProjectile.referencedProjectiles"
                assert owned[0]["value"]["references"] == profile["referencedProjectiles"]["references"]
            elif variant == "graph_refusal":
                assert owned[0]["sourcePath"] == "directProjectile.attackReference.motion.programs[0].graphCapture"
                assert owned[0]["value"]["identitySelectionUnavailable"] == marker
            else:
                # Unknown conditions can refer to the original graph namespace.
                assert owned[0]["value"]["futureMovementGate"]["dependsOn"] == "b3"
                assert owned[0]["value"]["collision"]["predicates"][0]["id"] == "b3"
                program = mechanics["sourceSlices"][0]["program"]
                assert "operations" not in program
                assert program["observations"][0]["arguments"]["length"] in program["dependencies"]
                assert program["observations"][0]["requiredPredicates"] == [program["predicates"][0]["id"]]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_production_requests_correlate_reads_but_not_distinct_method_stores(monkeypatch, mode):
    parent = _caller_parent()
    value = {"kind": "local_definition", "local": 326, "sourceIlOffset": 23689,
        "sourceStoreIlOffset": 23627, "scope": "value_at_store", "value": {"kind": "call",
        "member": "Terraria.Player.GetAdjustedItemScale", "arguments": [{"kind": "argument", "index": 0}],
        "evaluation": "unresolved_helper_or_hook_output", "sourceIlOffset": 23622}}
    parent["ammoRaw"] = {"projectileSemanticsReference": {"stages": [
        {"method": method, "sourceMethodSha256": "a" * 64, "sourceModuleVersionId": "module",
         "spawnSites": [{"spawnInputs": {"ai2": value}},
                        {"spawnInputs": {"ai2": {**value, "sourceIlOffset": 23753}}}]}
        for method in ("Player.ItemCheck_Shoot", "Other.ItemCheck_Shoot")]}}
    for raw in _request_parent_views(monkeypatch, parent, mode):
        mechanics = raw["mechanics"]
        first, second = mechanics["ammoInputs"]["projectileSemanticsReference"]["stages"]
        aliases = [row["spawnInputs"]["ai2"] for row in first["spawnSites"]]
        other = [row["spawnInputs"]["ai2"] for row in second["spawnSites"]]
        assert aliases[0] == aliases[1]
        assert other[0] == other[1] and other[0] != aliases[0]
        snapshots = mechanics["expressions"]["snapshots"]
        assert len(snapshots) == 2
        assert snapshots[aliases[0]]["value"] == snapshots[other[0]]["value"]
        assert "unexecuted Terraria.Player.GetAdjustedItemScale" in snapshots[aliases[0]]["value"]


@pytest.mark.parametrize("variant", ["absent", "version", "identity", "readable_caller"])
def test_production_requests_keep_partial_source_and_readable_caller_controls(monkeypatch, variant):
    parent = _caller_parent()
    profile = parent["directProjectileRaw"]
    if variant == "absent":
        profile.pop("mechanicsSource")
    elif variant == "version":
        profile["mechanicsSource"]["version"] = 2
    elif variant == "identity":
        profile["mechanicsSource"]["identity"]["type"] = 999
    else:
        profile["mechanicsSource"]["records"].append({"method": "Terraria.Projectile.Colliding",
            "code": "bool Colliding() { return wet && ConeHelper(90 * scale); }"})
    for raw in _request_parent_views(monkeypatch, parent, "json_object"):
        if variant == "readable_caller":
            assert raw["mechanics"]["sourceSlices"][0]["program"]["unresolved"] == ["opaque runtime predicate"]
        else:
            assert "mechanics" not in raw
        assert "ConeHelper" in json.dumps(raw)


def test_partial_finite_spawn_candidates_never_exclude_other_child_profiles():
    raw = _raw()
    profile = raw["directProjectile"]
    call = {"at": 41, "method": "Projectile.AI", "sourceMethodSha256": "sha",
        "sourceModuleVersionId": "module", "projectileTypes": [1009, 1010],
        "requiredPredicates": ["b7"], "unresolved": "finite_integer_cycle"}
    profile["referencedProjectiles"] = {"sourceCalls": [call], "references": [
        {"type": kind, "sourceCallIndices": [0], "profile": _profile(kind)} for kind in (1009, 1010, 1011)]}
    before = copy.deepcopy(raw)
    result = mechanics_context(raw)["mechanics"]
    assert [row["defaults"]["type"] for row in result["projectiles"]] == [31, 1009, 1010, 1011]
    assert not result["uncertainty"].get("excludedChildProfiles")
    assert raw == before


@pytest.mark.parametrize("coverage", ["whole_method", "conditional_ast_regions"])
@pytest.mark.parametrize("readable", [True, False])
def test_compaction_keeps_distinct_verified_coverage_of_same_method(coverage, readable):
    import hashlib
    from collections import Counter
    from tests.generator.context.test_native_csharp_source_view import _parent

    profile = _parent()["directProjectileRaw"]
    reference = profile["attackReference"]
    record = reference["nativeCSharpSource"]["records"][0]
    if coverage == "conditional_ast_regions":
        window = {"field": "type", "literal": 1, "guardOffset": 3}
        reference["motion"]["programs"][0]["identityWindows"] = [window]
        record.update(coverage=coverage, coveredWindows=[window], entryGuards=[{
            "field": "Terraria.Projectile.type", "operator": "==", "literal": 1, "ilOffset": 3,
            "scope": "only_if_original_guard_is_reached; enclosing_dispatch_unknown"}])
        # Exercise the path where the strict view keeps the smaller graph.
        record["code"] += "/*" + "source fixture " * 2000 + "*/"
        record["codeSha256"] = hashlib.sha256(record["code"].encode()).hexdigest()
    partial = {"method": record["method"], "coverage": "approximate_identity_ast_regions",
               "code": "if (wet) damage *= 2;", "entryGuards": ["wet"],
               "sourceMethodSha256": record["sourceMethodSha256"],
               "sourceModuleVersionId": record["sourceModuleVersionId"]}
    profile["mechanicsSource"] = {**_profile(1)["mechanicsSource"], "records": [partial]}
    before = copy.deepcopy(profile)
    compact = compact_projectile_profile(profile, prefer_readable_source=readable)
    rows = mechanics_context({"directProjectile": compact})["mechanics"]["source"]
    assert Counter(row["code"] for row in rows) == Counter([partial["code"], record["code"]])
    verified, = [row for row in rows if row["code"] == record["code"]]
    assert verified["coverage"] == coverage
    assert verified["entryGuards"] == record["entryGuards"]
    assert profile == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("same_code", [False, True])
def test_author_and_repair_keep_verified_whole_body_beside_same_named_region(monkeypatch, mode, same_code):
    from collections import Counter
    from tests.generator.context.test_native_csharp_source_view import _parent

    parent = _parent()
    profile = parent["directProjectileRaw"]
    record = profile["attackReference"]["nativeCSharpSource"]["records"][0]
    partial = {"method": record["method"], "coverage": "approximate_identity_ast_regions",
               "code": record["code"] if same_code else "if (wet) damage *= 2;", "entryGuards": ["wet"]}
    profile["mechanicsSource"] = {**_profile(1)["mechanicsSource"], "records": [partial]}
    for raw in _request_parent_views(monkeypatch, parent, mode):
        rows = raw["mechanics"]["source"]
        assert Counter(row["code"] for row in rows) == Counter([partial["code"], record["code"]])
        whole, = [row for row in rows if row["coverage"] == "whole_method"]
        assert whole["entryGuards"] == []
        links, = [row["value"] for row in raw["mechanics"]["uncertainty"]["sourceFacts"]
                  if row["sourcePath"] == "directProjectile.referencedProjectiles"]
        location = links["sourceCalls"][0]["sourceLocation"]
        assert "unresolvedNativeCSharpSourceRef" not in location
        assert rows[location["mechanicsSourceIndex"]] == whole
        assert location["predicates"][0]["id"] == "b3"
