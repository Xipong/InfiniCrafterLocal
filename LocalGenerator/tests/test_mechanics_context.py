"""Producer-backed Author view: useful mechanics and explicit approximation."""
import copy
import json

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

def test_legacy_generated_and_unknown_producers_do_not_gain_approximation():
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


def test_actual_author_request_preserves_catalog_and_emits_mechanics(monkeypatch):
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
        assert len(dossier["runtimeCapabilityContract"]["catalog"]["capabilities"]) == 71
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


def test_item_set_flags_and_unit_views_are_not_lost_with_graph_omission():
    raw = _raw()
    raw["vanillaFlags"] = {"sets": {"countsAsTorch": True, "isLavaImmune": False}}
    raw["runtimeProbe"] = {"observedHits": 2, "scope": "single test observation"}
    raw["sourceMotionUnits"] = {"values": [{"sourcePath": "raw.directProjectile.timeLeft", "value": 60, "units": "projectile updates"}]}
    result = mechanics_context(raw)
    assert result["vanillaFlags"] == raw["vanillaFlags"]
    assert result["runtimeProbe"] == raw["runtimeProbe"]
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
    assert [r["method"] for r in rows] == ["Projectile.AI", "Projectile.VanillaAI", "Projectile.Kill"]
    assert rows[1]["code"] == "if (charge > 120) damage *= 3;"
    assert rows[1]["entryGuards"] == [guard]
    assert rows[2]["entryCondition"] == "type == 31"
    assert rows[2]["entryScope"] == "entry guard must be reached"


def test_exact_profile_alias_is_not_a_source_extraction_failure():
    raw = _raw()
    raw["effectiveProjectile"] = {"sameAs": "raw.directProjectile"}
    gaps = mechanics_context(raw)["mechanics"]["uncertainty"]["sourceGaps"]
    assert not any("effectiveProjectile" in gap for gap in gaps)


def test_compaction_keeps_verified_region_when_legacy_selector_prefers_graph():
    import hashlib
    from test_native_csharp_source_view import _parent
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
    assert "sourceSlices" not in mechanics_context(raw)["mechanics"]


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
    ref = mechanics_context(raw)["mechanics"]["sourceSlices"][0]["program"]["predicateSources"][0]
    assert "mechanicsSourceIndex" not in ref
    assert ref["unresolvedNativeCSharpSourceRef"] == "s1"


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
