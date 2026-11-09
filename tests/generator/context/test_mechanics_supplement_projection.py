"""Certified source presentation must not restore discarded diagnostic bodies."""
import copy
import json

import pytest

from infini_local.pipelines.author.request import build_initial_author_request
from infini_local.pipelines.context.parents import compact_projectile_profile
from infini_local.pipelines.context.mechanics_context import mechanics_context
from prompt_packet_helpers import expand_native_source_references, request_dossier
from tests.generator.context.test_native_csharp_source_view import _parent, _specialized_fixture


def _fixture():
    parent = _parent()
    reference, calls, record = _specialized_fixture()
    profile = parent["directProjectileRaw"]
    profile["attackReference"] = reference
    profile["referencedProjectiles"]["sourceCalls"] = calls
    profile["mechanicsSource"] = {"source": "native_mechanics_source", "version": 1,
        "identity": {"type": 1, "aiStyle": 1}, "unresolved": ["opaque_hook"], "records": []}
    return parent, profile, reference, record


def _source(parent):
    request, _, _ = build_initial_author_request(parent, {}, "supplement-test", model_name="offline")
    return expand_native_source_references(request_dossier(json.loads(json.dumps(request))))[
        "parents"]["A"]["packet"]["raw"]["mechanics"]


def test_selected_specialization_has_one_body_and_exact_source_call_bindings():
    parent, _, _, record = _fixture()
    before = copy.deepcopy(parent)
    mechanics = _source(parent)
    rows = mechanics["source"]
    assert len(rows) == 1
    assert rows[0]["code"] == record["identitySpecialized"]["code"]
    assert rows[0]["coverage"] == "identity_specialized_method"
    assert rows[0]["identitySpecialization"] == {key: record["identitySpecialized"]["proof"][key]
                                                 for key in ("identityPredicates", "scope")}
    assert "identitySpecialized" not in json.dumps(rows)
    bindings = []
    def visit(value):
        if isinstance(value, dict):
            if "mechanicsSourceIndex" in value:
                bindings.append(rows[value["mechanicsSourceIndex"]])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(mechanics)
    assert bindings and all(row == rows[0] for row in bindings)
    assert "opaque_hook" in mechanics["uncertainty"]["sourceGaps"]
    assert parent == before


@pytest.mark.parametrize("invalid", ["code_hash", "identity", "source_map", "future_shape"])
def test_invalid_specialization_cannot_suppress_original_source(invalid):
    parent, _, _, record = _fixture()
    view = record["identitySpecialized"]
    if invalid == "code_hash":
        view["codeSha256"] = "0" * 64
    elif invalid == "identity":
        view["proof"]["identityPredicates"]["Projectile.type"] = 123
    elif invalid == "source_map":
        view["sourceMap"]["original"] = []
    else:
        view["futureConstraint"] = {"keep": False}
    before = copy.deepcopy(parent)
    rows = _source(parent)["source"]
    assert any(row["code"] == record["code"] and row["coverage"] == "whole_method" for row in rows)
    assert all(row.get("coverage") != "identity_specialized_method" for row in rows)
    assert any(row.get("sourceFields", {}).get("identitySpecialized") == view for row in rows)
    assert parent == before


def test_valid_but_unselected_specialization_does_not_choose_another_body():
    _, profile, _, record = _fixture()
    compact = compact_projectile_profile(profile, prefer_readable_source=False)
    rows = mechanics_context({"directProjectile": compact})["mechanics"]["source"]
    assert any(row["code"] == record["code"] and row["coverage"] == "whole_method" for row in rows)
    assert all(row.get("coverage") != "identity_specialized_method" for row in rows)
    assert "identitySpecialized" not in json.dumps(rows)


# Literal producer receipts, intentionally independent of the consumer constant.
# Importing that constant into every fixture hid the current producer mismatch.
@pytest.mark.parametrize("scope", [
    "Source-only identity specialization; unknown runtime conditions retain all paths. Direct target identity writes/address escapes and uncertified target-passing calls before a read prevent selection. Native detours and hidden global effects remain outside capture coverage.",
    "Source-only identity specialization; unknown runtime conditions retain all paths. Direct target identity writes/address escapes and uncertified target-passing calls before a read prevent selection. Native detours/global aliases remain outside capture coverage.",
])
def test_current_and_captured_v1_scope_receipts_bind_and_preserve_exact_limits(scope):
    parent, _, reference, record = _fixture()
    proof = record["identitySpecialized"]["proof"]
    receipt = reference["motion"]["programs"][0]["identitySelected"]["identitySelection"]
    proof["scope"] = receipt["scope"] = scope
    before = copy.deepcopy(parent)
    rows = _source(parent)["source"]
    assert len(rows) == 1 and rows[0]["coverage"] == "identity_specialized_method"
    assert rows[0]["identitySpecialization"]["scope"] == scope
    assert parent == before
    # Both individually recognized strings still need exact AST/CFG agreement.
    receipt["scope"] = (scope.replace("Native detours/global aliases", "Native detours and hidden global effects")
                        if "Native detours/global aliases" in scope
                        else scope.replace("Native detours and hidden global effects", "Native detours/global aliases"))
    assert all(row.get("coverage") != "identity_specialized_method" for row in _source(parent)["source"])
    receipt["scope"] = scope.replace("coverage.", "coverage. changed")
    assert all(row.get("coverage") != "identity_specialized_method" for row in _source(parent)["source"])
    proof["scope"] = receipt["scope"]
    assert all(row.get("coverage") != "identity_specialized_method" for row in _source(parent)["source"])


@pytest.mark.parametrize("scope", [None, False, [], {}, "unknown future scope"])
def test_unknown_or_malformed_scope_cannot_replace_original(scope):
    parent, _, reference, record = _fixture()
    record["identitySpecialized"]["proof"]["scope"] = copy.deepcopy(scope)
    reference["motion"]["programs"][0]["identitySelected"]["identitySelection"]["scope"] = copy.deepcopy(scope)
    rows = _source(parent)["source"]
    assert any(row["code"] == record["code"] and row["coverage"] == "whole_method" for row in rows)
    assert all(row.get("coverage") != "identity_specialized_method" for row in rows)
