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
