"""Author keeps strict evidence beside, not replaced by, approximate source."""
import copy
from collections import Counter
import json

from infini_local.pipelines.author.request import build_initial_author_request
from infini_local.pipelines.context.attack_behavior import project_attack_behavior
from infini_local.pipelines.context.parents import _present_replaced_identity_selections
from infini_local.pipelines.context.mechanics_context import mechanics_context
from infini_local.pipelines.context.attack_tables import unpack_attack_tables
from prompt_packet_helpers import expand_native_source_references, request_dossier
from tests.generator.context.test_native_csharp_source_view import _parent, _parts, _specialized_fixture


def test_author_preserves_strict_graph_and_identity_selected_with_readable_source():
    parent = _parent()
    reference, calls, record = _specialized_fixture()
    profile = parent["directProjectileRaw"]
    profile["attackReference"] = reference
    profile["referencedProjectiles"]["sourceCalls"] = calls
    profile["mechanicsSource"] = {
        "source": "native_mechanics_source", "version": 1,
        "identity": {"type": 1, "aiStyle": 1}, "unresolved": ["unknown_runtime_hook"],
        "records": [{"method": record["method"], "code": record["code"]}],
    }
    graph = {"source": "parent_reachable_compiled_source_graph", "version": 1,
             "nodes": [{"id": 0, "coverage": "source_character_bound", "possibleLocalWrites": {"1": ["2"]},
                        "values": {"12": ["ldloc", 17, ["local_entry:17"], 10],
                                   "local_entry:17": ["unresolved_local_entry", {"member": 0}, [], 0]},
                        "diagnosticSecretMarker": "not for Author"}],
             "unresolved": ["strict_graph_unknown"], "diagnosticSecretMarker": "not for Author"}
    parent["parentSourceGraph"] = graph
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "strict-mechanics", model_name="offline")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    raw = dossier["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["parentSourceGraph"]["unresolved"] == ["strict_graph_unknown"]
    assert raw["item"]["parentSourceGraph"]["nodes"][0]["values"] == graph["nodes"][0]["values"]
    assert raw["item"]["parentSourceGraph"]["transportOmissions"]["unknownFieldCount"] == 2
    assert "not reaching definitions or executed values" in raw["item"]["parentSourceGraphReading"]
    assert "diagnosticSecretMarker" not in json.dumps(raw)
    selected = project_attack_behavior(reference)["motion"]["programs"][0]
    facts = unpack_attack_tables(raw["mechanics"]["strictIdentitySelections"])["selections"]
    chosen = next(entry["selectedProgram"] for row in facts for entry in row["selections"])
    for key in ("method", "observations", "dependencies", "predicates", "symbols", "unresolved", "identitySelection"):
        if key in selected:
            assert chosen[key] == selected[key]
    assert "strict_graph_unknown" in json.dumps(raw)
    # Equal code is not equal evidence: keep the independent approximate row
    # and the canonical certified specialization with its exact assumptions.
    # Do not reintroduce its original body or raw proof as a third presentation.
    specialization = record["identitySpecialized"]
    expected_source = [
        {"projectiles": [1], **profile["mechanicsSource"]["records"][0]},
        {"projectiles": [1], "method": record["method"], "code": specialization["code"],
         "coverage": specialization["coverage"], "unresolved": record["unresolved"],
         "entryGuards": record["entryGuards"], "identitySpecialization": {
             key: specialization["proof"][key] for key in ("identityPredicates", "scope")}},
    ]
    assert Counter(json.dumps(row, sort_keys=True) for row in raw["mechanics"]["source"]) == Counter(
        json.dumps(row, sort_keys=True) for row in expected_source)
    assert parent == before


def test_unrecognized_selected_graph_is_explicitly_omitted_and_not_asserted_valid():
    original = {"source": "read_only_native_attack_source", "version": 1,
                "motion": {"programs": [{"method": "Fixture.NativeAI", "coverage": "unknown",
                                          "unresolved": "full_source_unavailable",
                                          "identitySelected": {"unexpectedFutureShape": [0, False, None],
                                                               "unresolved": ["opaque"]}}]}}
    projected = {"motion": {"programs": [{"nativeCSharpSourceRef": "s0"}]}}
    before = copy.deepcopy((original, projected))
    rows = _present_replaced_identity_selections(original, projected)
    assert rows == [{"path": ["motion", "programs", 0], "projection": "unrecognized_identity_selection_omitted",
                     "coverage": "unknown", "unresolved": "full_source_unavailable",
                     "selectedProgram": {"unresolved": ["opaque"], "projectionUnresolved": "identity_selection_shape_not_projected"}}]
    assert _present_replaced_identity_selections(original, original) == []
    assert (original, projected) == before


def test_unrecognized_outer_refusal_never_forwards_diagnostic_objects():
    original = {"motion": {"programs": [{"method": "Fixture.NativeAI", "coverage": "unknown",
        "unresolved": {"diagnosticSecretMarker": "secret"},
        "identitySelected": {"unresolved": ["opaque"]}}]}}
    projected = {"motion": {"programs": [{"nativeCSharpSourceRef": "s0"}]}}
    rows = _present_replaced_identity_selections(original, projected)
    assert rows[0]["coverage"] == "unknown"
    assert rows[0]["unknownRefusalEntriesOmitted"] is True
    assert rows[0]["selectedProgram"]["unresolved"] == ["opaque"]
    assert "diagnosticSecretMarker" not in json.dumps(rows)


def test_empty_refusal_list_is_preserved_as_known_empty():
    original = {"motion": {"programs": [{"method": "Fixture.NativeAI", "coverage": "unknown",
        "unresolved": [], "identitySelected": {"unresolved": ["opaque"]}}]}}
    projected = {"motion": {"programs": [{"nativeCSharpSourceRef": "s0"}]}}
    row = _present_replaced_identity_selections(original, projected)[0]
    assert row["unresolved"] == []
    assert "unknownRefusalEntriesOmitted" not in row


def test_full_method_refusal_is_preserved_with_valid_selected_graph():
    reference, _, _ = _specialized_fixture()
    graph = reference["motion"]["programs"][0]
    reference["motion"]["programs"][0] = {
        **{key: copy.deepcopy(graph[key]) for key in
           ("method", "sourceModuleVersionId", "sourceMethodSha256", "identitySelected")},
        "coverage": "unknown", "unresolved": "full_source_unavailable"}
    projected = {"motion": {"programs": [{"nativeCSharpSourceRef": "s0"}]}}
    row = _present_replaced_identity_selections(reference, projected)[0]
    assert row["projection"] == "gameplay_source_conditions_allowlist"
    assert row["unresolved"] == "full_source_unavailable"
    assert row["selectedProgram"]["identitySelection"]["fullMethodCapture"] == {
        "coverage": "unknown", "unresolved": "full_source_unavailable"}


def test_unrecognized_selection_survives_even_when_same_named_csharp_exists():
    program = {"method": "Terraria.Projectile.AI", "coverage": "unknown", "unresolved": ["opaque_dispatch"],
               "identitySelected": {"unrecognizedFutureShape": [0, False, None], "unresolved": ["nested_opaque"]}}
    raw = {"item": {"parentSourceGraph": {"unresolved": ["unknown_graph"]}},
           "directProjectile": {"type": 1,
               "mechanicsSource": {"source": "native_mechanics_source", "version": 1,
                   "identity": {"type": 1, "aiStyle": 1}, "unresolved": [],
                   "records": [{"method": "Terraria.Projectile.AI", "code": "void AI() {}"}]},
               "attackReference": {"motion": {"programs": [program]}}}}
    before = copy.deepcopy(raw)
    view = mechanics_context(raw)
    assert "parentSourceGraph" not in view["item"]
    assert view["mechanics"]["uncertainty"]["parentSourceGraphOmission"] == {
        "reason": "unrecognized_parent_source_graph_omitted", "unresolved": ["unknown_graph"]}
    presented = view["mechanics"]["sourceSlices"][0]["program"]
    assert presented["method"] == program["method"]
    assert presented["unresolved"] == program["unresolved"]
    assert presented["identitySelectionRefusal"]["unresolved"] == ["nested_opaque"]
    assert presented["unresolvedIdentitySelection"] == "unrecognized_identity_selection_omitted"
    assert "unrecognizedFutureShape" not in json.dumps(view)
    assert raw == before


def test_unrecognized_selection_drops_outer_diagnostic_object():
    raw = {"item": {}, "directProjectile": {"type": 1,
        "mechanicsSource": {"source": "native_mechanics_source", "version": 1,
            "identity": {"type": 1, "aiStyle": 1}, "unresolved": [],
            "records": [{"method": "Terraria.Projectile.AI", "code": "void AI() {}"}]},
        "attackReference": {"motion": {"programs": [{"method": "Terraria.Projectile.AI",
            "coverage": "unknown", "unresolved": {"diagnosticSecretMarker": "secret"},
            "identitySelected": {"unresolved": ["nested_unknown"]}}]}}}}
    view = mechanics_context(raw)
    program = view["mechanics"]["sourceSlices"][0]["program"]
    assert program["identitySelectionRefusal"]["unresolved"] == ["nested_unknown"]
    assert program["unknownRefusalEntriesOmitted"] is True
    assert "diagnosticSecretMarker" not in json.dumps(view)
