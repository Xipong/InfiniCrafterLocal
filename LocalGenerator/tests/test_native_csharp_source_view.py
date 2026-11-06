"""Source-defined handoff fixtures; native PE/decompiler proof has its own CPU checks."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from infini_local.pipelines.author.request import build_initial_author_request
from infini_local.pipelines.context.attack_tables import unpack_attack_tables
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from infini_local.pipelines.context.csharp_source_view import SOURCE_READING, known_native_csharp_context, prune_native_csharp_records
from infini_local.pipelines.context.native_csharp_source import native_csharp_source_for_llm
from infini_local.pipelines.context.presentation import presentation_parent_card_for_llm
from prompt_packet_helpers import expand_native_source_references, request_dossier


def _parent():
    cert = {"method": "Fixture.NativeAI", "sourceModuleVersionId": "fixture-module", "sourceMethodSha256": "a" * 64}
    graph = {**cert, "observations": [{"kind": "call", "call": "Fixture.Emit", "expression": f"Fixture.Emit[{index}]",
        "at": 10 + index, "block": 4, "requiredPredicates": ["b3"]} for index in range(160)],
        "dependencies": {}, "predicates": [{"id": "b3", "at": 3, "block": 0, "op": "brfalse",
            "inputs": ["@Fixture.active"], "successors": [200, 4]}], "symbols": {"Fixture.Emit": "Fixture.Emit(int)"},
        "coverage": "source_only", "unresolved": ["runtime hooks and execution not evaluated"]}
    code = "void NativeAI() {\nif (active) {\n" + "\n".join(f"Emit({index});" for index in range(160)) + "\n}\n}\n"
    record = {**cert, "id": "fixture-source", "metadataToken": 100, "assemblySha256": "b" * 64,
        "decompiler": {"name": "ICSharpCode.Decompiler", "version": "8.2.0.7535", "assemblySha256": "c" * 64,
            "settings": "csharp_default_no_indentation_v1"}, "coverage": "whole_method", "graphPaths": [["motion", "programs", 0]],
        "code": code, "codeSha256": hashlib.sha256(code.encode()).hexdigest(), "entryGuards": [], "coveredWindows": [],
        "locations": [{"ilOffset": 10, "startLine": 3, "endLine": 3}, {"ilOffset": 3, "startLine": 2, "endLine": 2}],
        "unresolved": []}
    reference = {"source": "read_only_native_attack_source", "version": 1, "identityPredicates": {
        "Projectile.type": 1, "Projectile.aiStyle": 1}, "motion": {"programs": [graph]},
        "coverage": {"proved": [], "unresolved": ["runtime execution unknown"], "boundaries": []},
        "nativeCSharpSource": {"source": "verified_decompiled_native_csharp", "version": 1, "records": [record],
            "unresolved": [], "scope": "source-defined fixture, not native PE verification evidence"}}
    call = {**cert, "at": 10, "requiredPredicates": ["b3"], "projectileTypes": [2],
            "unresolved": "spawn_type_requires_runtime_expression_or_unresolved_definition"}
    return {"name": "Source-defined parent", "directProjectileRaw": {"type": 1, "attackReference": reference,
        "referencedProjectiles": {"source": "native_single_hop_projectile_references", "version": 1, "sourceCalls": [call],
            "references": [{"type": 2, "sourceCallIndices": [0], "profile": {"type": 2, "friendly": True}}]}}}


def _parts(parent):
    profile = parent["directProjectileRaw"]
    return profile["attackReference"], profile["referencedProjectiles"]["sourceCalls"]


def test_actual_author_prefers_certified_source_and_keeps_child_predicate_links_bound():
    parent = _parent()
    before = copy.deepcopy(parent)
    reference, calls = _parts(parent)
    request, _, _ = build_initial_author_request(parent, {}, "readable-source", model_name="offline")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    profile = dossier["parents"]["A"]["packet"]["raw"]["directProjectile"]
    source = unpack_attack_tables(profile["attackReference"])
    program = source["motion"]["programs"][0]
    assert program == {"nativeCSharpSourceRef": "s0"}
    assert not {"observations", "dependencies", "predicates", "symbols"}.intersection(program)
    assert source["coverage"] == reference["coverage"]
    assert set(source["nativeCSharpSource"]["records"][0]) == {"id", "method", "code", "coverage", "entryGuards", "unresolved"}
    assert "raw diagnostic capture" in source["nativeCSharpSource"]["scope"]
    assert source["nativeCSharpSource"]["records"][0]["code"] == reference["nativeCSharpSource"]["records"][0]["code"]
    assert known_native_csharp_context(source)
    linked = profile["referencedProjectiles"]
    assert linked["references"] == parent["directProjectileRaw"]["referencedProjectiles"]["references"]
    call = linked["sourceCalls"][0]
    assert {key: value for key, value in call.items() if key != "sourceLocation"} == calls[0]
    assert call["sourceLocation"]["sourceRecord"] == program["nativeCSharpSourceRef"]
    assert call["sourceLocation"]["statement"]["locations"] == [{"ilOffset": 10, "startLine": 3, "endLine": 3}]
    predicate = call["sourceLocation"]["predicates"][0]
    assert predicate["id"] == call["requiredPredicates"][0]
    assert predicate["sourceSites"][0]["locations"] == [{"ilOffset": 3, "startLine": 2, "endLine": 2}]
    assert parent == before


def test_presentation_uses_original_graph_projection_without_author_source_or_location_bloat():
    parent = _parent()
    for stage in ("visual", "vfx"):
        card = presentation_parent_card_for_llm(parent, stage=stage)
        profile = card["raw"]["directProjectile"]
        source = unpack_attack_tables(profile["attackReference"])
        assert "nativeCSharpSource" not in source and "nativeCSharpSourceReading" not in source
        assert not {"motion", "motionDispatch", "collision", "positionIntegration"}.intersection(source)
        assert profile["referencedProjectiles"]["sourceCalls"] == _parts(parent)[1]


def test_source_record_does_not_replace_another_graph_path_with_the_same_method_certificate():
    parent = _parent()
    reference, calls = _parts(parent)
    uncovered = copy.deepcopy(reference["motion"]["programs"][0])
    uncovered["unresolved"].append("separate uncovered graph path")
    for index, row in enumerate(uncovered["observations"]):
        row.update(expression=f"Fixture.Other[{index}]", call="Fixture.Other", at=1000 + index)
    uncovered["symbols"] = {"Fixture.Other": "Fixture.Other(int)"}
    reference["motion"]["programs"].append(uncovered)
    projected, _ = native_csharp_source_for_llm(reference, calls)
    assert projected["motion"]["programs"][0]["nativeCSharpSourceRef"] == "s0"
    assert projected["motion"]["programs"][1] == uncovered


def test_large_whole_method_source_does_not_displace_a_small_bounded_graph():
    reference, calls = _parts(_parent())
    reference["motion"]["programs"][0]["observations"] = reference["motion"]["programs"][0]["observations"][:1]
    projected, linked = native_csharp_source_for_llm(reference, calls)
    assert projected["motion"] == reference["motion"]
    assert "nativeCSharpSource" not in projected
    assert linked == calls
    assert "nativeCSharpSourceReading" not in projected


@pytest.mark.parametrize("mutation", ["module", "method", "method_hash", "code_hash", "record_future", "envelope_future",
    "bool_version", "engine_future", "engine_version", "coverage_shape", "location_future", "location_range",
    "symbol_shape", "argument_shape", "row_future", "windows_shape", "call_future", "bool_path"])
def test_unmatched_or_unfamiliar_source_preserves_the_complete_original_namespace(mutation):
    reference, calls = _parts(_parent())
    envelope = reference["nativeCSharpSource"]
    record, graph = envelope["records"][0], reference["motion"]["programs"][0]
    if mutation == "module": record["sourceModuleVersionId"] = "another-module"
    elif mutation == "method": record["method"] = "Fixture.AnotherMethod"
    elif mutation == "method_hash": record["sourceMethodSha256"] = "d" * 64
    elif mutation == "code_hash": record["codeSha256"] = "d" * 64
    elif mutation == "record_future": record["futureBinding"] = {"graphNode": "b3"}
    elif mutation == "envelope_future": envelope["futureBinding"] = {"graphNode": "b3"}
    elif mutation == "bool_version": envelope["version"] = True
    elif mutation == "engine_future": record["decompiler"]["futureMode"] = "unknown"
    elif mutation == "engine_version": record["decompiler"]["version"] = "8.3.0"
    elif mutation == "coverage_shape": record["coverage"] = {"future": True}
    elif mutation == "location_future": record["locations"][0]["futureBinding"] = "b3"
    elif mutation == "location_range": record["locations"][0]["endLine"] = 1_000_000
    elif mutation == "symbol_shape": graph["symbols"]["Fixture.Emit"] = {"signature": "Fixture.Emit(int)", "future": True}
    elif mutation == "argument_shape": graph["observations"][0]["arguments"] = {"value": {"futureReference": "b3"}}
    elif mutation == "row_future": graph["observations"][0]["futureReference"] = "b3"
    elif mutation == "windows_shape": graph["identityWindows"] = None
    elif mutation == "call_future": calls[0]["futureReference"] = "b3"
    else: record["graphPaths"] = [["motion", "programs", False]]
    before = copy.deepcopy((reference, calls))
    actual, linked = native_csharp_source_for_llm(reference, calls)
    assert json.dumps((actual, linked)) == json.dumps(before)
    assert (reference, calls) == before


def test_every_repeated_identity_window_must_be_covered_before_replacing_an_inline_graph():
    reference, calls = _parts(_parent())
    record = reference["nativeCSharpSource"]["records"][0]
    windows = [{"field": "type", "literal": 1, "guardOffset": 3}, {"field": "type", "literal": 1, "guardOffset": 9}]
    reference["motion"]["programs"][0]["identityWindows"] = windows
    record["coverage"] = "conditional_ast_regions"
    record["entryGuards"] = [{"field": "Terraria.Projectile.type", "operator": "==", "literal": 1, "ilOffset": 3,
                             "scope": "only_if_original_guard_is_reached; enclosing_dispatch_unknown"}]
    record["coveredWindows"] = windows[:1]
    unchanged, linked = native_csharp_source_for_llm(reference, calls)
    assert unchanged == reference and linked == calls
    record["coveredWindows"] = copy.deepcopy(windows)
    projected, _ = native_csharp_source_for_llm(reference, calls)
    assert projected["motion"]["programs"][0]["nativeCSharpSourceRef"] == "s0"
    assert projected["nativeCSharpSource"]["records"][0]["entryGuards"] == [
        {key: value for key, value in guard.items() if key != "ilOffset"} for guard in record["entryGuards"]]


def test_unavailable_source_mappings_bind_each_predicate_id_to_an_explicit_unknown():
    reference, calls = _parts(_parent())
    calls[0]["requiredPredicates"] = ["b3", "b404", "b3"]
    record = reference["nativeCSharpSource"]["records"][0]
    record["locations"] = [{"ilOffset": offset, "unresolved": "decompiler_source_location_unavailable"}
                           for offset in (3, 10, 404)]
    projected, linked = native_csharp_source_for_llm(reference, calls)
    assert linked[0]["sourceLocation"]["statement"]["mapping"] == "unavailable"
    predicates = linked[0]["sourceLocation"]["predicates"]
    assert [row["id"] for row in predicates] == ["b3", "b404", "b3"]
    assert predicates[0]["sourceSites"] == [{"mapping": "unavailable", "ilOffset": 3}]
    assert predicates[1] == {"id": "b404", "sourceSites": [], "mapping": "unavailable"}
    assert "locations" not in projected["nativeCSharpSource"]["records"][0]


def test_unused_source_records_are_pruned_after_an_explicit_stage_omission():
    parent = _parent()
    reference, _ = _parts(parent)
    draw = copy.deepcopy(reference["motion"]["programs"][0])
    draw["method"], draw["sourceMethodSha256"] = "Fixture.NativeDraw", "d" * 64
    reference["draw"] = {"dispatch": copy.deepcopy(reference["motion"]["programs"][0]), "programs": [draw]}
    record = copy.deepcopy(reference["nativeCSharpSource"]["records"][0])
    record.update(id="fixture-draw", method=draw["method"], sourceMethodSha256=draw["sourceMethodSha256"],
                  graphPaths=[["draw", "programs", 0]])
    record["code"] = record["code"].replace("NativeAI", "NativeDraw")
    record["codeSha256"] = hashlib.sha256(record["code"].encode()).hexdigest()
    reference["nativeCSharpSource"]["records"].append(record)
    # Prune only after a separately admitted omission. A method named NativeDraw
    # is not proof that its complete C# body has only presentation effects.
    source = copy.deepcopy(reference)
    for row in source["nativeCSharpSource"]["records"]:
        path = row["graphPaths"][0]
        target = source[path[0]][path[1]][path[2]]
        source[path[0]][path[1]][path[2]] = {**{key: target[key] for key in (
            "method", "sourceModuleVersionId", "sourceMethodSha256")}, "nativeCSharpSourceRef": row["id"], "graphCapture": {}}
    source["nativeCSharpSourceReading"] = SOURCE_READING
    source.pop("draw")
    before = copy.deepcopy(source)
    pruned = prune_native_csharp_records(source)
    assert [record["id"] for record in pruned["nativeCSharpSource"]["records"]] == ["fixture-source"]
    assert known_native_csharp_context(pruned)
    assert source == before


def test_source_choice_accounts_for_exact_sharing_of_duplicate_graphs():
    reference, calls = _parts(_parent())
    reference["motion"]["programs"].append(copy.deepcopy(reference["motion"]["programs"][0]))
    record = reference["nativeCSharpSource"]["records"][0]
    record["graphPaths"].append(["motion", "programs", 1])
    record["code"] += "/*" + "read-only padding " * 1000 + "*/"
    record["codeSha256"] = hashlib.sha256(record["code"].encode()).hexdigest()
    projected, linked = native_csharp_source_for_llm(reference, calls)
    assert projected["motion"] == reference["motion"]
    assert "nativeCSharpSource" not in projected
    assert linked == calls


def test_matching_pe_refusal_preserves_the_graph_and_its_explicit_source_refusal():
    parent = _parent()
    reference, _ = _parts(parent)
    reference["nativeCSharpSource"]["records"] = []
    refusal = {"method": "Fixture.NativeAI", "unresolved": "csharp_matching_pe_bytes_unavailable"}
    reference["nativeCSharpSource"]["unresolved"] = [refusal]
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "source-pe-refusal", model_name="offline")
    dossier = expand_native_source_references(request_dossier(request))
    source = unpack_attack_tables(dossier["parents"]["A"]["packet"]["raw"]["directProjectile"]["attackReference"])
    assert source["nativeCSharpSource"]["unresolved"] == [refusal]
    assert len(source["motion"]["programs"][0]["operations"]) == 161
    assert "nativeCSharpSourceRef" not in source["motion"]["programs"][0]
    assert parent == before


def _specialized_fixture():
    reference, calls = _parts(_parent())
    record = reference["nativeCSharpSource"]["records"][0]
    from infini_local.pipelines.context.csharp_source_view import _IDENTITY_SCOPE
    edges = [{"at": 3, "block": 0, "op": "brfalse", "successor": 4}]
    receipt = {"version": 1, "source": "certified_receiver_identity_cfg", "identityPredicates": reference["identityPredicates"],
               "scope": _IDENTITY_SCOPE, "selectedEdges": edges}
    graph = reference["motion"]["programs"][0]
    graph["identitySelected"] = {**copy.deepcopy(graph), "identitySelection": receipt}
    code = "void NativeAI() { Emit(0); }"
    digest = hashlib.sha256(code.encode()).hexdigest()
    locations = [{"ilOffset": 10, "startLine": 1, "endLine": 1}, {"ilOffset": 3, "unresolved": "excluded_by_identity_proof"}]
    record["identitySpecialized"] = {"id": f'csharp-specialized:{record["id"]}:{digest}:1:1', "code": code,
        "codeSha256": digest, "coverage": "identity_specialized_method", "locations": locations,
        "proof": {**receipt, "version": 1, "source": "certified_receiver_identity_ast", "originalCodeSha256": record["codeSha256"], "removedGuards": [3]},
        "sourceMap": {"kind": "il_source_locations_v1", "original": copy.deepcopy(record["locations"]), "specialized": copy.deepcopy(locations)}}
    return reference, calls, record


def test_specialized_source_remaps_locations_and_preserves_identity():
    reference, calls, record = _specialized_fixture()
    before = copy.deepcopy(reference)
    projected, linked = native_csharp_source_for_llm(reference, calls)
    selected = projected["nativeCSharpSource"]["records"][0]
    assert selected["code"] == record["identitySpecialized"]["code"]
    assert selected["identitySpecialization"]["identityPredicates"] == reference["identityPredicates"]
    assert linked[0]["sourceLocation"]["statement"]["locations"][0]["startLine"] == 1
    assert linked[0]["sourceLocation"]["predicates"][0]["sourceSites"][0]["mapping"] == "unavailable"
    assert known_native_csharp_context(projected)
    assert reference == before


@pytest.mark.parametrize("mutation", ["hash", "identity", "original", "future", "map", "method"])
def test_invalid_specialization_preserves_full_source(mutation):
    reference, calls, record = _specialized_fixture()
    view = record["identitySpecialized"]
    if mutation == "hash": view["codeSha256"] = "f" * 64
    if mutation == "identity": view["proof"]["identityPredicates"] = {"Projectile.type": 2, "Projectile.aiStyle": 1}
    if mutation == "original": view["proof"]["originalCodeSha256"] = "f" * 64
    if mutation == "future": view["proof"]["version"] = 2
    if mutation == "map": view["locations"][0]["startLine"] = 999
    if mutation == "method": reference["motion"]["programs"][0]["method"] = "Other.Method"
    projected, linked = native_csharp_source_for_llm(reference, calls)
    if mutation == "method":
        assert projected == reference and linked == calls
    else:
        assert projected["nativeCSharpSource"]["records"][0]["code"] == record["code"]


@pytest.mark.parametrize("variant", ["valid", "conflict", "absent", "certificate"])
def test_specialization_multiple_same_method_graph_paths(variant):
    from infini_local.pipelines.context.csharp_source_view import _specialized_record
    reference, calls, record = _specialized_fixture()
    graphs = reference["motion"]["programs"]
    for index in range(1, 25):
        graph = copy.deepcopy(graphs[0])
        graph.pop("identitySelected")
        graphs.append(graph)
        record["graphPaths"].append(["motion", "programs", index])
    if variant == "conflict":
        graphs[-1]["identitySelection"] = copy.deepcopy(graphs[0]["identitySelected"]["identitySelection"])
        graphs[-1]["identitySelection"]["identityPredicates"] = {"Projectile.type": 99, "Projectile.aiStyle": 1}
    if variant == "absent": graphs[0].pop("identitySelected")
    if variant == "certificate": graphs[-1]["method"] = "Other.Method"
    candidate = _specialized_record(reference, record)
    assert (candidate is not None) == (variant == "valid")
    projected, _ = native_csharp_source_for_llm(reference, calls)
    if variant == "valid":
        assert projected["nativeCSharpSource"]["records"][0]["coverage"] == "identity_specialized_method"
    elif variant == "certificate":
        assert projected == reference
    else:
        assert projected["nativeCSharpSource"]["records"][0]["code"] == record["code"]


@pytest.mark.parametrize("section", ["playerInventoryProjectileRaw", "fallbackProjectileRaw"])
@pytest.mark.parametrize("envelope", ["root", "fingerprint"])
def test_main_ammo_observations_keep_readable_source_and_profile_links(section, envelope):
    source_parent = _parent()
    profile = source_parent["directProjectileRaw"]
    reference = copy.deepcopy(profile["attackReference"])
    ammo = {"mode": "weapon_uses_ammo", "ammoId": 1,
            "playerInventoryObservation": {"available": True, "observedSlots": [0]},
            section: [profile]}
    parent = {"name": "Main ammo source", "ammoRaw": ammo}
    if envelope == "fingerprint":
        parent = {"name": "Main ammo source", "fingerprint": parent}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "main-ammo-source", model_name="offline")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    result = dossier["parents"]["A"]["packet"]["raw"]["ammo"]
    assert result["playerInventoryObservation"] == ammo["playerInventoryObservation"]
    assert len(result[section]) == 1
    delivered = result[section][0]
    attack = unpack_attack_tables(delivered["attackReference"])
    assert attack["coverage"] == reference["coverage"]
    assert attack["nativeCSharpSource"]["records"][0]["code"] == reference["nativeCSharpSource"]["records"][0]["code"]
    assert delivered["referencedProjectiles"]["references"] == profile["referencedProjectiles"]["references"]
    assert "ammo." + section + "[0]" in dossier["parentBriefs"]["A"]["behavior"]
    assert parent == before
