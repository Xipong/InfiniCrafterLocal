"""Direct conditional lifecycle source is independent of graph-size selection."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from infini_local.pipelines.author.request import build_initial_author_request
from infini_local.pipelines.context.attack_tables import unpack_attack_tables
from infini_local.pipelines.context.csharp_source_view import project_lifecycle_source, _LIFECYCLE_SCOPE, _LIFECYCLE_CALL_SCOPE
from infini_local.pipelines.context.native_csharp_source import native_csharp_source_for_llm
from prompt_packet_helpers import expand_native_source_references, request_dossier


def _reference():
    cert = {"method": "Terraria.Projectile.Kill", "sourceModuleVersionId": "fixture-module",
            "sourceMethodSha256": "a" * 64}
    condition = "type == 91 || type == 92"
    code = "if (" + condition + ")\n{\nif (owner == Main.myPlayer && ai[0] > 0f)\n{\nNewProjectile(source, x, y, vx, vy, 92, damage / 3, knockBack, owner);\n}\n}\n"
    sha = hashlib.sha256(code.encode()).hexdigest()
    call = {**cert, "at": 10, "projectileTypes": [92], "requiredPredicates": ["b3"],
            "unresolved": _LIFECYCLE_CALL_SCOPE}
    record = {**cert, "id": f"lifecycle:fixture-module:100:{sha}", "metadataToken": 100,
              "assemblySha256": "b" * 64, "decompiler": {"name": "ICSharpCode.Decompiler", "version": "8.2.0.7535",
              "assemblySha256": "d174072a16aa758a39d160f70ce924103898fae2b8506b48f70d6909e25a1fd0",
              "settings": "csharp_default_no_indentation_v1"}, "coverage": "conditional_closed_lexical_region",
              "code": code, "codeSha256": sha, "entryCondition": condition,
              "identityWitnesses": [{"field": "Terraria.Projectile.type", "literal": 91}], "spawnSites": [call],
              "locations": [{"ilOffset": 3, "startLine": 1, "endLine": 1}, {"ilOffset": 10, "startLine": 5, "endLine": 5}]}
    lifecycle = {"source": "verified_conditional_native_lifecycle_csharp", "version": 1, "root": "Kill",
                 "rootCertificate": cert, "relevanceIdentity": {"Projectile.type": 91, "Projectile.aiStyle": 1},
                 "scope": _LIFECYCLE_SCOPE,
                 "records": [record], "unresolved": ["other Kill regions and hooks unresolved"]}
    return {"source": "read_only_native_attack_source", "version": 1,
            "identityPredicates": {"Projectile.type": 91, "Projectile.aiStyle": 1}, "lifecycle": lifecycle}, [call]


def test_direct_source_survives_without_any_graph_or_other_csharp_records():
    reference, calls = _reference()
    before = copy.deepcopy(reference), copy.deepcopy(calls)
    out, linked = native_csharp_source_for_llm(reference, calls)
    assert linked == calls
    assert out["lifecycle"]["source"] == "read_only_conditional_native_lifecycle_csharp"
    record = out["lifecycle"]["records"][0]
    raw = reference["lifecycle"]["records"][0]
    for key in ("code", "entryCondition", "identityWitnesses", "locations", "coverage"):
        assert record[key] == raw[key]
    assert out["lifecycle"]["unresolved"] == reference["lifecycle"]["unresolved"]
    assert not {"identitySelected", "nativeCSharpSourceRef", "observations"}.intersection(record)
    assert (reference, calls) == before
    assert native_csharp_source_for_llm(out, linked) == (out, linked)


def test_direct_source_does_not_change_existing_graph_csharp_choice():
    from tests.generator.context.test_native_csharp_source_view import _parent, _parts

    ordinary, calls = _parts(_parent())
    direct, _ = _reference()
    ordinary["identityPredicates"] = copy.deepcopy(direct["identityPredicates"])
    baseline, baseline_calls = native_csharp_source_for_llm(ordinary, calls)
    combined = copy.deepcopy(ordinary)
    combined["lifecycle"] = copy.deepcopy(direct["lifecycle"])
    actual, actual_calls = native_csharp_source_for_llm(combined, calls)
    assert actual.pop("lifecycle")["source"] == "read_only_conditional_native_lifecycle_csharp"
    assert actual == baseline
    assert actual_calls == baseline_calls


def test_actual_author_keeps_full_conditional_source_and_child_call_multiplicity():
    reference, calls = _reference()
    parent = {"name": "Source parent", "directProjectileRaw": {"type": 91, "attackReference": reference,
              "referencedProjectiles": {"source": "native_single_hop_projectile_references", "version": 1,
                  "sourceCalls": calls, "references": [{"type": 92, "sourceCallIndices": [0], "profile": {"type": 92}}]}}}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "lifecycle-source", model_name="offline")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    profile = dossier["parents"]["A"]["packet"]["raw"]["directProjectile"]
    attack = unpack_attack_tables(profile["attackReference"])
    source = attack["lifecycle"]
    assert len(source["records"]) == 1
    assert source["records"][0]["code"] == reference["lifecycle"]["records"][0]["code"]
    assert source["scope"] == reference["lifecycle"]["scope"]
    assert source["unresolved"] == reference["lifecycle"]["unresolved"]
    assert profile["referencedProjectiles"]["sourceCalls"] == calls
    assert len(profile["referencedProjectiles"]["references"]) == 1
    assert parent == before


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(version=True),
    lambda value: value["rootCertificate"].update(sourceMethodSha256="f" * 64),
    lambda value: value["records"][0].update(code="if (true) {}"),
    lambda value: value["records"][0].update(entryCondition="true"),
    lambda value: value["records"][0].update(identitySelected={}),
    lambda value: value["records"][0]["identityWitnesses"][0].update(literal=92),
    lambda value: value["records"][0]["identityWitnesses"][0].update(field=[]),
    lambda value: value["records"][0]["decompiler"].update(version="future"),
    lambda value: value["records"][0]["spawnSites"][0].update(at=99),
    lambda value: value["records"][0]["spawnSites"].append(copy.deepcopy(value["records"][0]["spawnSites"][0])),
    lambda value: value["records"][0]["spawnSites"][0].update(requiredPredicates=["b999"]),
    lambda value: value["records"][0]["locations"][0].update(endLine=999),
    lambda value: value.update(scope="complete Kill behavior"),
    lambda value: value["records"][0]["spawnSites"][0].update(unresolved="guaranteed child"),
])
def test_incomplete_or_changed_direct_source_is_literal_passthrough(mutation):
    reference, _ = _reference()
    mutation(reference["lifecycle"])
    before = copy.deepcopy(reference)
    assert project_lifecycle_source(reference) == before
    assert reference == before


def test_refusal_only_direct_source_keeps_unknown_without_inventing_code():
    reference, _ = _reference()
    reference["lifecycle"]["records"] = []
    reference["lifecycle"]["unresolved"] += ["lifecycle_region_character_bound", "absence_not_proved"]
    out, _ = native_csharp_source_for_llm(reference)
    assert out["lifecycle"]["records"] == []
    assert out["lifecycle"]["unresolved"] == reference["lifecycle"]["unresolved"]


def test_unknown_outer_schema_is_not_reinterpreted_as_lifecycle_source():
    reference, _ = _reference()
    reference["version"] = 2
    assert project_lifecycle_source(reference) == reference
    reference["version"] = 1
    reference["unknownFutureField"] = {}
    assert project_lifecycle_source(reference) == reference


def _interaction_reference():
    from infini_local.pipelines.context.native_interaction_source import _SCOPE

    reference, _ = _reference()
    reference.pop("lifecycle")
    cert = {"method": "Terraria.Projectile.Damage", "sourceModuleVersionId": "fixture-module", "sourceMethodSha256": "a" * 64}
    def record(code, method, token, coverage):
        sha = hashlib.sha256(code.encode()).hexdigest()
        return {**cert, "method": method, "id": f"interaction:fixture-module:{token}:{sha}", "metadataToken": token,
                "assemblySha256": "b" * 64, "code": code, "codeSha256": sha, "coverage": coverage, "spawnSites": [],
                "decompiler": {"name": "ICSharpCode.Decompiler", "version": "8.2.0.7535",
                    "assemblySha256": "d174072a16aa758a39d160f70ce924103898fae2b8506b48f70d6909e25a1fd0",
                    "settings": "csharp_default_no_indentation_v1"}}
    helper = record("void Effect(int amount) { damage += amount; }", "Terraria.Projectile.Effect", 101,
                    "whole_method_source_only; one_hop_no_call_evaluation")
    region = record("if (type == 91)\n{\nEffect(num3);\n}", cert["method"], 100,
                    "conditional_source_region; external_inputs_explicit")
    region.update(regionIndex=1, entryCondition="type == 91", identityWitnesses=[{"field": "Terraria.Projectile.type", "literal": 91}],
                  externalInputs=[{"name": "num3", "type": "System.Int32", "kind": "external_local",
                                   "scope": "symbolic_entry_value; reaching_definitions_and_current_value_not_captured"}],
                  helperCalls=[{key: helper[key] for key in cert} | {"at": 20}])
    reference["interactionSources"] = {"source": "verified_conditional_native_interaction_csharp", "version": 1,
        "relevanceIdentity": copy.deepcopy(reference["identityPredicates"]), "scope": _SCOPE,
        "roots": [{"root": "Damage", "rootCertificate": cert, "records": [region], "helpers": [helper],
                   "unresolved": ["other_regions_and_callees_unresolved; absence_not_proved"]}]}
    return reference


def test_interaction_source_preserves_locals_helpers_and_actual_author():
    reference = _interaction_reference()
    before = copy.deepcopy(reference)
    view, _ = native_csharp_source_for_llm(reference)
    root = view["interactionSources"]["roots"][0]
    assert view["interactionSources"]["source"] == "read_only_conditional_native_interaction_csharp"
    assert root["records"][0]["helperCalls"][0]["sourceRecord"] == root["helpers"][0]["id"]
    for key in ("code", "externalInputs", "entryCondition", "identityWitnesses", "coverage"):
        assert root["records"][0][key] == reference["interactionSources"]["roots"][0]["records"][0][key]
    assert reference == before
    assert native_csharp_source_for_llm(view)[0] == view
    reference["nativeCSharpSource"] = {"source": "verified_decompiled_native_csharp", "version": 1,
        "records": [], "unresolved": [], "scope": "no graph replacement"}
    parent = {"name": "Interaction source parent", "directProjectileRaw": {"type": 91, "attackReference": reference}}
    request, _, _ = build_initial_author_request(parent, {}, "interaction-source", model_name="offline")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    attack = unpack_attack_tables(dossier["parents"]["A"]["packet"]["raw"]["directProjectile"]["attackReference"])
    assert attack["interactionSources"] == view["interactionSources"]


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(version=True),
    lambda value: value.update(scope="guaranteed executed effect"),
    lambda value: value["roots"][0].update(root=[]),
    lambda value: value["roots"][0].update(root={}),
    lambda value: value.update(source=[]),
    lambda value: value["roots"][0]["records"][0]["externalInputs"][0].update(kind=[]),
    lambda value: value["roots"][0]["records"][0].update(code="if (true) {}"),
    lambda value: value["roots"][0]["records"][0].update(coverage="whole_method"),
    lambda value: value["roots"][0]["records"][0]["identityWitnesses"][0].update(field=[]),
    lambda value: value["roots"][0]["records"][0]["identityWitnesses"][0].update(literal=92),
    lambda value: value["roots"][0]["records"][0]["externalInputs"][0].update(scope="native live damage"),
    lambda value: value["roots"][0]["helpers"][0].update(code="void Effect() {}"),
    lambda value: value["roots"][0]["helpers"].clear(),
])
def test_changed_interaction_source_is_literal_passthrough(mutation):
    from infini_local.pipelines.context.native_interaction_source import project_interaction_source

    reference = _interaction_reference()
    mutation(reference["interactionSources"])
    before = copy.deepcopy(reference)
    assert project_interaction_source(reference) == before
    assert reference == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("location", ["direct", "child", "inventory", "fallback"])
@pytest.mark.parametrize("future", [False, True])
def test_actual_mechanics_author_keeps_interaction_namespace(monkeypatch, mode, location, future):
    from infini_local.core import llm_config

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    reference = _interaction_reference()
    if future:
        reference["interactionSources"]["version"] = 2
    reference["nativeCSharpSource"] = {"source": "verified_decompiled_native_csharp", "version": 1,
        "records": [], "unresolved": [], "scope": "no graph replacement"}
    def profile(kind):
        return {"type": kind, "aiStyle": 1, "mechanicsSource": {"source": "native_mechanics_source", "version": 1,
            "identity": {"type": kind, "aiStyle": 1}, "records": [{"method": "Terraria.Projectile.AI",
                "code": "void AI() { }"}], "unresolved": []}}
    child = profile(91)
    child["attackReference"] = reference
    parent = {"name": "Interaction source", "directProjectileRaw": profile(90)}
    if location == "direct":
        parent["directProjectileRaw"] = child
    elif location == "child":
        cert = reference["interactionSources"]["roots"][0]["rootCertificate"]
        parent["directProjectileRaw"]["referencedProjectiles"] = {"source": "native_single_hop_projectile_references", "version": 1,
            "sourceCalls": [{**cert, "at": 20, "projectileTypes": [91], "requiredPredicates": [], "unresolved": "conditional"}],
            "references": [{"type": 91, "sourceCallIndices": [0], "profile": child}]}
    else:
        field = "playerInventoryProjectileRaw" if location == "inventory" else "fallbackProjectileRaw"
        parent["ammoRaw"] = {field: [child]}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "interaction-mechanics", model_name="offline")
    assert request["response_format"]["type"] == mode
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    raw = dossier["parents"]["A"]["packet"]["raw"]
    assert "mechanics" in raw
    facts = raw["mechanics"]["uncertainty"].get("sourceFacts", [])
    values = [entry["value"] for entry in facts if entry["sourcePath"].endswith(".attackReference.interactionSources")]
    expected = native_csharp_source_for_llm(reference)[0]["interactionSources"]
    assert values == [expected]
    assert values[0]["roots"][0]["records"][0]["externalInputs"][0]["kind"] == "external_local"
    assert parent == before


@pytest.mark.parametrize("reason", [
    "helper_virtual_or_open_generic_dispatch_unknown",
    "interaction_helper_count_bound",
    "interaction_helper_character_bound",
])
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_interaction_refused_overload_does_not_link_colliding_helper(monkeypatch, reason, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.context.native_interaction_source import project_interaction_source

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    reference = _interaction_reference()
    root = reference["interactionSources"]["roots"][0]
    region, helper = root["records"][0], root["helpers"][0]
    # Different overload signatures can have the same method-name/MVID/raw-IL
    # certificate (for example, empty bodies). Refusal cannot inherit the
    # admitted overload's body just because this lossy certificate matches.
    helper["code"] = "void Effect(int amount) { }"
    region["code"] = "if (type == 91)\n{\nEffect(num3);\nEffect();\n}"
    for record in (region, helper):
        record["codeSha256"] = hashlib.sha256(record["code"].encode()).hexdigest()
        record["id"] = f'interaction:fixture-module:{record["metadataToken"]}:{record["codeSha256"]}'
    region["helperCalls"].append({**region["helperCalls"][0], "at": 30, "unresolved": reason})
    reference["nativeCSharpSource"] = {"source": "verified_decompiled_native_csharp", "version": 1,
        "records": [], "unresolved": [], "scope": "no graph replacement"}
    before = copy.deepcopy(reference)
    view = project_interaction_source(reference)
    calls = view["interactionSources"]["roots"][0]["records"][0]["helperCalls"]
    assert calls[0]["sourceRecord"] == "h0"
    assert calls[1] == {"at": 30, "method": "Terraria.Projectile.Effect", "unresolved": reason}
    assert view["interactionSources"]["roots"][0]["records"][0]["code"] == region["code"]
    assert reference == before

    profile = {"type": 91, "aiStyle": 1, "attackReference": reference,
        "mechanicsSource": {"source": "native_mechanics_source", "version": 1,
            "identity": {"type": 91, "aiStyle": 1},
            "records": [{"method": "Terraria.Projectile.AI", "code": "void AI() { }"}], "unresolved": []}}
    request, _, _ = build_initial_author_request({"name": "Colliding overloads", "directProjectileRaw": profile},
        {}, "interaction-refused-overload", model_name="offline")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    facts = dossier["parents"]["A"]["packet"]["raw"]["mechanics"]["uncertainty"]["sourceFacts"]
    values = [fact["value"] for fact in facts if fact["sourcePath"].endswith(".attackReference.interactionSources")]
    assert values == [view["interactionSources"]]


def test_interaction_two_admitted_colliding_helper_certificates_stay_literal():
    from infini_local.pipelines.context.native_interaction_source import project_interaction_source

    reference = _interaction_reference()
    helpers = reference["interactionSources"]["roots"][0]["helpers"]
    overload = copy.deepcopy(helpers[0])
    overload["metadataToken"] += 1
    overload["code"] = "void Effect(float amount) { damage += (int)amount; }"
    overload["codeSha256"] = hashlib.sha256(overload["code"].encode()).hexdigest()
    overload["id"] = f'interaction:fixture-module:{overload["metadataToken"]}:{overload["codeSha256"]}'
    helpers.append(overload)
    before = copy.deepcopy(reference)
    assert project_interaction_source(reference) == before
    assert reference == before
