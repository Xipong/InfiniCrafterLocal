"""Serialized Author/Repair preserves the evidence behind review #333."""
import copy

import pytest

from infini_local.services import runtime_dump_service as dumps
from tests.generator.context.test_mechanics_context import _caller_parent, _profile, _request_parent_views


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("role", ["collision", "motionDispatch", "motion", "motionDispatchEffects", "positionIntegration"])
def test_partial_same_named_source_does_not_hide_symbolic_caller(monkeypatch, mode, role):
    parent = _caller_parent(role)
    profile = parent["directProjectileRaw"]
    profile["mechanicsSource"]["records"].append({
        "method": "Terraria.Projectile.Colliding", "coverage": "approximate_identity_ast_regions",
        "sourceMethodSha256": "a" * 64, "sourceModuleVersionId": "module",
        "code": "if (type == 31) { return false; }", "entryGuards": ["type == 31"]})
    for raw in _request_parent_views(monkeypatch, parent, mode):
        mechanics = raw["mechanics"]
        row, = mechanics["sourceSlices"]
        assert row["role"] == role
        branch, definition, call = row["program"]["operations"]
        assert branch["step"] < definition["step"] < call["step"]
        assert call["arguments"]["length"] == definition["bind"]
        assert definition["requiredPredicates"] == call["requiredPredicates"] == [branch["id"]]
        assert row["program"]["unresolved"] == ["opaque runtime predicate"]
        assert any(source["code"] == "if (type == 31) { return false; }" for source in mechanics["source"])


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("with_profiles", [True, False])
def test_spawn_edges_keep_partial_candidates_guards_and_unresolved_calls(monkeypatch, mode, with_profiles):
    parent = _caller_parent()
    profile = parent["directProjectileRaw"]
    links = {"source": "native_bounded_projectile_references", "version": 1,
        "scope": "candidate profiles only, not guaranteed execution", "profileLimit": 8, "depthLimit": 4,
        "sourceCalls": [
            {"method": "Terraria.Projectile.AI", "at": 12, "requiredPredicates": ["b3"],
             "projectileTypes": [32, 33], "unresolved": "spawn_type_requires_runtime_expression_or_unresolved_definition"},
            {"method": "Terraria.Projectile.AI", "at": 19, "requiredPredicates": ["b8"],
             "projectileTypes": [], "unresolved": "dynamic_type_without_candidates"}],
        "references": [{"type": kind, "sourceCallIndices": [0], **({"profile": _profile(kind)} if with_profiles
                        else {"unresolved": "projectile_reference_profile_bound"})} for kind in (32, 33)]}
    profile["referencedProjectiles"] = links
    for raw in _request_parent_views(monkeypatch, parent, mode):
        mechanics = raw["mechanics"]
        facts = mechanics["uncertainty"]["sourceFacts"]
        envelope, = [row["value"] for row in facts if row["sourcePath"] == "directProjectile.referencedProjectiles"]
        assert envelope["sourceCalls"] == links["sourceCalls"]
        assert envelope["scope"] == links["scope"]
        assert [row["type"] for row in envelope["references"]] == [32, 33]
        captures = {capture["sourcePath"]: row["defaults"] for row in mechanics["projectiles"] for capture in row["captures"]}
        for index, row in enumerate(envelope["references"]):
            assert row["sourceCallIndices"] == [0]
            if with_profiles:
                assert captures[row["profileSourcePath"]]["type"] == row["type"]
                assert "profile" not in row
            else:
                assert row == links["references"][index]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_replacement_candidates_keep_capture_specific_dispatch_and_hook_links(monkeypatch, mode):
    parent = _caller_parent()
    first = _profile(32)
    source = {"source": "ModItem.Shoot", "hookIndex": 0, "conditionStatus": "conditional",
        "dispatchStatus": "blocked_by_inspected_global_shoot_suppression", "blockingHookIndices": [1, 3],
        "sourceMethodSha256": "a" * 64, "sourceModuleVersionId": "module"}
    first["sourceReferences"] = [source, copy.deepcopy(source)]
    second = copy.deepcopy(first)
    second["sourceReferences"] = [{**source, "dispatchStatus": "conditional_hook_dispatch", "blockingHookIndices": []}]
    parent["ammoRaw"] = {"nativeReplacementProjectileRaw": [first, second]}
    for raw in _request_parent_views(monkeypatch, parent, mode):
        rows = raw["mechanics"]["projectiles"]
        captures = {capture["sourcePath"]: capture for row in rows for capture in row["captures"]}
        wanted = {key: value for key, value in source.items() if key not in {"sourceMethodSha256", "sourceModuleVersionId"}}
        assert captures["ammo.nativeReplacementProjectileRaw[0]"]["sourceReferences"] == [wanted, wanted]
        assert captures["ammo.nativeReplacementProjectileRaw[1]"]["sourceReferences"] == [
            {**wanted, "dispatchStatus": "conditional_hook_dispatch", "blockingHookIndices": []}]
        assert all("sourceReferences" not in row["defaults"] for row in rows)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("matched", [False, True])
def test_actual_snapshot_lookup_keeps_provenance_beside_mechanics(monkeypatch, mode, matched):
    profile = _profile()
    profile["fullName"] = "Example/Bolt"
    provenance = {"status": "verified_snapshot", "snapshotId": "a" * 32, "capturedAtUtc": "2026-11-01T12:00:00Z"}
    snapshot = dumps.RuntimeDumpSnapshot({}, {31: profile}, provenance, {})
    monkeypatch.setattr(dumps, "RUNTIME_DUMP_SNAPSHOT", snapshot)
    parent = {"name": "Current item", "shoot": 31}
    if matched:
        parent["shootProjectileFullName"] = "Example/Bolt"
    for raw in _request_parent_views(monkeypatch, parent, mode):
        captures = {capture["sourcePath"]: capture for row in raw["mechanics"]["projectiles"] for capture in row["captures"]}
        assert captures["directProjectile"]["runtimeDumpProvenance"] == {
            **provenance, "compatibility": "matched_available_identity" if matched else "unverified"}
    assert snapshot.projectiles == {31: profile}


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_spawn_source_location_does_not_leave_an_unbound_display_id(monkeypatch, mode):
    parent = _caller_parent()
    parent["directProjectileRaw"]["referencedProjectiles"] = {
        "source": "native_bounded_projectile_references", "version": 1,
        "sourceCalls": [{"method": "Terraria.Projectile.Colliding", "at": 12, "projectileTypes": [],
            "sourceLocation": {"sourceRecord": "s0", "statement": {"ilOffset": 12, "mapping": "source_lines", "locations": []},
                               "predicates": []}, "unresolved": "dynamic_type"}], "references": []}
    for raw in _request_parent_views(monkeypatch, parent, mode):
        envelope = next(row["value"] for row in raw["mechanics"]["uncertainty"]["sourceFacts"]
                        if row["sourcePath"] == "directProjectile.referencedProjectiles")
        location = envelope["sourceCalls"][0]["sourceLocation"]
        assert "sourceRecord" not in location and "mechanicsSourceIndex" not in location
        assert location["unresolvedNativeCSharpSourceRef"] == "s0"
        assert location["sourceReferenceStatus"] == "no_unique_emitted_source_record"
        assert location["statement"]["ilOffset"] == 12
        assert envelope["sourceCalls"][0]["unresolved"] == "dynamic_type"


@pytest.mark.parametrize("same_body", [False, True])
def test_spawn_source_locations_bind_only_exact_capture_local_source(same_body):
    from infini_local.pipelines.context.mechanics_context import mechanics_context

    raw = {"item": {}}
    for path, kind in (("directProjectile", 31), ("effectiveProjectile", 32)):
        profile = _profile(kind)
        body = f"void AI() {{ Spawn({kind}); }}"
        profile["mechanicsSource"]["records"] = [{"method": "Terraria.Projectile.AI", "code": body}]
        profile["attackReference"] = {"nativeCSharpSource": {
            "source": "read_only_native_csharp_view", "version": 1,
            "records": [{"id": "s0", "method": "Terraria.Projectile.AI", "code": body if same_body else "other body"}]}}
        profile["referencedProjectiles"] = {"source": "native_bounded_projectile_references", "version": 1,
            "sourceCalls": [{"sourceLocation": {"sourceRecord": "s0", "predicates": []}}], "references": []}
        raw[path] = profile
    before = copy.deepcopy(raw)
    mechanics = mechanics_context(raw)["mechanics"]
    for row in mechanics["uncertainty"]["sourceFacts"]:
        location = row["value"]["sourceCalls"][0]["sourceLocation"]
        assert "sourceRecord" not in location
        if same_body:
            kind = raw[row["sourcePath"].split(".")[0]]["type"]
            assert mechanics["source"][location["mechanicsSourceIndex"]]["code"] == f"void AI() {{ Spawn({kind}); }}"
            assert "unresolvedNativeCSharpSourceRef" not in location
        else:
            assert mechanics["source"][location["mechanicsSourceIndex"]]["code"] == "other body"
            assert "unresolvedNativeCSharpSourceRef" not in location
    assert raw == before
