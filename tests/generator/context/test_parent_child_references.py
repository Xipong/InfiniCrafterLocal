"""One-hop native observation handoff; no model/provider or inferred mechanics."""
import copy
import pytest
from infini_local.pipelines.context.parents import compact_projectile_profile
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from infini_local.pipelines.context.parent_stage import parent_context_for_stage
from prompt_packet_helpers import expand_native_source_references


def reference_fixture():
    return {"type": 101, "width": 10, "referencedProjectiles": {
        "source": "native_single_hop_projectile_references", "version": 1,
        "scope": "Conditional defaults/source; actual spawn arguments remain in parent", "profileLimit": 8,
        "sourceCalls": [{"method": "fixture", "at": 20, "requiredPredicates": ["b10"], "projectileTypes": [202]},
                        {"method": "fixture", "at": 40, "requiredPredicates": ["b30"], "projectileTypes": [202]},
                        {"method": "fixture", "at": 60, "projectileTypes": [], "unresolved": "dynamic_type"}],
        "references": [{"type": 202, "sourceCallIndices": [0, 1], "profile": {
            "type": 202, "source": "conditional_native_spawn_candidate", "width": 60, "height": 60,
            "damage": 0, "sourceItemDamage": 0, "itemShootSpeed": 0,
            "attackReference": {"source": "fixture-unknown-native-projection", "scope": "untouched", "state": [30, 60]}}},
            {"type": 303, "sourceCallIndices": [2], "unresolved": "single_hop_profile_count_bound"}]}}


def test_single_hop_preserves_callsites_unknowns_and_no_input_mutation():
    original = reference_fixture(); before = copy.deepcopy(original)
    result = compact_projectile_profile(original)
    assert original == before
    refs = result["referencedProjectiles"]
    assert refs["sourceCalls"] == original["referencedProjectiles"]["sourceCalls"]
    assert refs["references"][0]["sourceCallIndices"] == [0, 1]
    profile = refs["references"][0]["profile"]
    assert (profile["type"], profile["width"], profile["height"], profile["itemShootSpeed"]) == (202, 60, 60, 0)
    assert profile["attackReference"] == before["referencedProjectiles"]["references"][0]["profile"]["attackReference"]
    assert "damage" not in profile and "sourceItemDamage" not in profile
    assert refs["references"][1]["unresolved"] == "single_hop_profile_count_bound"


@pytest.mark.parametrize("kind", ["future", "unavailable", "nested", "bounded_unknown_nested"])
def test_unrecognized_or_incomplete_child_evidence_stays_literal(kind):
    source = reference_fixture(); refs = source["referencedProjectiles"]
    if kind == "future": refs["futureMeaning"] = {"doNotInterpret": True}
    if kind == "unavailable": refs["references"][0]["profile"] = {"type": 202, "unavailable": True, "reason": "capture_failed"}
    if kind in {"nested", "bounded_unknown_nested"}:
        refs["references"][0]["profile"]["referencedProjectiles"] = {"futureNested": True}
    if kind == "bounded_unknown_nested": refs["source"] = "native_bounded_projectile_references"
    before = copy.deepcopy(refs)
    result = compact_projectile_profile(source)["referencedProjectiles"]
    if kind == "future": assert result == before
    else: assert result["references"][0]["profile"] == before["references"][0]["profile"]


def test_author_native_card_reaches_child_without_external_catalog(monkeypatch):
    from infini_local.pipelines.context import parents
    def unavailable(*a, **k): raise AssertionError("request-local references must not require a dump")
    monkeypatch.setattr(parents.runtime_dump_service.RuntimeDumpSnapshot, "lookup",
                        lambda self, kind, *args, **kwargs: unavailable() if kind == "projectile" else {})
    item = {"name": "Fixture", "type": 10, "shoot": 101, "directProjectileRaw": reference_fixture()}
    card = raw_parent_card_for_llm(item)
    dossier = parent_context_for_stage({"A": {"packet": card}, "B": {"packet": copy.deepcopy(card)}}, stage="author")
    expanded = expand_native_source_references(dossier)
    for side in ("A", "B"):
        profile = expanded["parents"][side]["packet"]["raw"]["directProjectile"]["referencedProjectiles"]["references"][0]["profile"]
        assert profile["attackReference"]["state"] == [30, 60]
        assert profile["type"] == 202
    assert item["directProjectileRaw"] == reference_fixture()


def test_bounded_graph_projects_nested_profiles_and_keeps_repeat_and_bound_edges():
    source = reference_fixture()
    links = source['referencedProjectiles']
    links.update(source='native_bounded_projectile_references', depthLimit=4)
    child = links['references'][0]['profile']
    nested = copy.deepcopy(links)
    nested['references'] = [
        {'type': 202, 'sourceCallIndices': [0], 'profileRefType': 202},
        {'type': 404, 'sourceCallIndices': [1], 'profile': {
            'type': 404, 'width': 5, 'damage': 99, 'itemShootSpeed': 0,
            'onHitStatusReference': {'source': 'fixture', 'effects': [7]}}},
        {'type': 505, 'sourceCallIndices': [2], 'unresolved': 'projectile_reference_depth_bound'}]
    child['referencedProjectiles'] = nested
    before = copy.deepcopy(source)
    result = compact_projectile_profile(source)
    actual = result['referencedProjectiles']['references'][0]['profile']['referencedProjectiles']
    assert actual['references'][0] == nested['references'][0]
    assert actual['references'][2] == nested['references'][2]
    assert actual['sourceCalls'] == nested['sourceCalls']
    assert actual['references'][1]['profile']['onHitStatusReference'] == {'source': 'fixture', 'effects': [7]}
    assert 'damage' not in actual['references'][1]['profile']
    assert source == before


def test_bounded_graph_shared_profile_survives_excluded_first_edge_without_cycles():
    from infini_local.pipelines.context.mechanics_context import mechanics_context
    profile = {"type": 101, "mechanicsSource": {"source": "native_mechanics_source", "version": 1,
        "identity": {"type": 101}, "unresolved": [], "records": [{"method": "Fixture", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module",
                     "code": "void Fixture() {}", "excludedCallOffsets": [10]}]}}
    calls = [{"method": "Fixture", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module",
              "at": at, "projectileTypes": [202]} for at in (10, 20)]
    links = {"source": "native_bounded_projectile_references", "version": 1, "profileLimit": 8, "depthLimit": 4,
             "sourceCalls": calls, "references": []}
    leaf = {"type": 202, "width": 12, "referencedProjectiles": {**links, "references": [
        {"type": 202, "sourceCallIndices": [1], "profileRefType": 202}]}}
    links['references'] = [
        {"type": 202, "sourceCallIndices": [0], "profile": leaf},
        {"type": 202, "sourceCallIndices": [1], "profileRefType": 202}]
    profile['referencedProjectiles'] = links
    raw = {"item": {}, "directProjectile": profile}
    before = copy.deepcopy(raw)
    result = mechanics_context(raw)['mechanics']
    assert [row['defaults']['type'] for row in result['projectiles']] == [101, 202]
    assert result['projectiles'][1]['captures'][0]['sourcePath'] == \
        'directProjectile.referencedProjectiles.references[0].profile'
    assert result['uncertainty']['excludedChildProfiles'][0]['child'] == 202
    assert raw == before


@pytest.mark.parametrize("invalid", [{}, [], None, 1])
def test_malformed_graph_source_and_candidate_scope_remain_unrecognized(invalid):
    from infini_local.pipelines.context.native_references import known_projectile_references
    from infini_local.pipelines.context.mechanics_context import mechanics_context
    links = reference_fixture()['referencedProjectiles']
    links['source'] = invalid
    assert known_projectile_references(links) is False
    source = {"source": "native_mechanics_source", "version": 1,
        "identity": {"type": 101}, "unresolved": [], "records": [{"method": "Fixture",
        "sourceMethodSha256": "sha", "sourceModuleVersionId": "module", "code": "void Fixture() {}",
        "spawnTypeCandidates": [{"at": 10, "projectileTypes": [202], "scope": invalid}]}]}
    call = {"method": "Fixture", "sourceMethodSha256": "sha", "sourceModuleVersionId": "module", "at": 10}
    raw = {"item": {}, "directProjectile": {"type": 101, "mechanicsSource": source,
        "referencedProjectiles": {"sourceCalls": [call], "references": [
            {"type": 303, "sourceCallIndices": [0], "profile": {"type": 303}}]}}}
    result = mechanics_context(raw)['mechanics']
    assert [row['defaults']['type'] for row in result['projectiles']] == [101, 303]
