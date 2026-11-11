"""Remove physical single-use indirection without changing native evidence."""
import copy
import json

import pytest

from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts


def test_shared_parent_inlines_its_single_use_descendants_without_replication():
    child = {"code": "float speed = 2.0f; " * 20, "values": [False, 0, 0.0, -0.0]}
    body = {"nested": child, "unknown": {"futureField": [3, 3, 2]}}
    parents = {"A": {"packet": {"raw": {"one": body, "two": copy.deepcopy(body)}}}}
    before = copy.deepcopy(parents)
    actual = share_exact_native_parent_facts(parents)
    assert actual["nativeSourceFacts"] == [body]
    assert actual["parents"]["A"]["packet"]["raw"] == {
        "one": {"sourceSameAs": 0}, "two": {"sourceSameAs": 0}}
    assert parents == before


def _context(pool, raw=None):
    return {"parents": {"A": {"packet": {"raw": raw or {"value": {"sourceSameAs": 0}}}}},
            "nativeSourceFacts": pool}


def test_nested_singletons_preserve_shared_descendants_and_dense_indices():
    from infini_local.pipelines.context.parent_stage import _inline_single_use_native_facts
    from tests.generator.context.native_sharing_oracle import expanded_native_parents
    context = _context([
        {"first": {"sourceSameAs": 1}, "second": {"sourceSameAs": 1}, "once": {"sourceSameAs": 2}},
        {"value": [True, 1, 1.0, -0.0, "unfamiliar", "unfamiliar"]},
        {"last": {"sourceSameAs": 3}}, {"futureFact": "x" * 200},
    ])
    before = copy.deepcopy(context)
    actual = _inline_single_use_native_facts(context)
    assert actual["nativeSourceFacts"] == [context["nativeSourceFacts"][1]]
    assert actual["parents"]["A"]["packet"]["raw"]["value"] == {
        "first": {"sourceSameAs": 0}, "second": {"sourceSameAs": 0}, "once": {"last": {"futureFact": "x" * 200}}}
    assert json.dumps(expanded_native_parents(actual)) == json.dumps(expanded_native_parents(context))
    assert _inline_single_use_native_facts(actual) == actual
    assert context == before
    actual["nativeSourceFacts"][0]["value"].append(5)
    assert context == before


@pytest.mark.parametrize("pool", [
    [{"sourceSameAs": 0}],
    [{"sourceSameAs": 1}, {"sourceSameAs": 0}],
    [{"sourceSameAs": -1}],
    [{"sourceSameAs": True}],
    [{"sourceSameAs": 1}],
    [{"sourceSameAs": "0"}],
    [{"sourceSameAs": 0, "futureEffect": 12}],
    [{"value": "x" * 200}, {"orphanEvidence": "must remain"}],
])
def test_unsafe_or_incompletely_reachable_graph_stays_literal(pool):
    from infini_local.pipelines.context.parent_stage import _inline_single_use_native_facts
    context = _context(pool)
    assert _inline_single_use_native_facts(context) == context


def test_protected_data_and_non_raw_metadata_never_become_reference_roots():
    from infini_local.pipelines.context.parent_stage import _inline_single_use_native_facts
    context = _context([{"futureFact": [False, 0, 0.0]}], {
        "value": {"sourceSameAs": 0}, "tooltipSource": {"sourceSameAs": 500},
        "tooltipLines": [{"opaque": {1, 2, 3}, "sourceSameAs": 0}]})
    context["parents"]["A"]["metadata"] = {"sourceSameAs": 0}
    context["parents"]["B"] = {"packet": {"raw": {
        "generatedParent": {"sourceSameAs": 900}, "acceptedMetadata": {"sourceSameAs": 0}}}}
    actual = _inline_single_use_native_facts(context)
    assert "nativeSourceFacts" not in actual
    assert actual["parents"]["A"]["packet"]["raw"]["value"] == context["nativeSourceFacts"][0]
    assert actual["parents"]["A"]["metadata"] == context["parents"]["A"]["metadata"]
    for key in ("tooltipSource", "tooltipLines"):
        assert actual["parents"]["A"]["packet"]["raw"][key] == context["parents"]["A"]["packet"]["raw"][key]
    assert actual["parents"]["B"] == context["parents"]["B"]
    assert _inline_single_use_native_facts(actual) == actual


def test_pool_local_string_notation_does_not_move_outside_its_scope():
    from infini_local.pipelines.context.parent_stage import _inline_single_use_native_facts
    context = _context([{"sourceTextValueParts": ["x" * 200]}, {"ordinary": "y" * 200}],
                       {"text": {"sourceSameAs": 0}, "other": {"sourceSameAs": 1}})
    actual = _inline_single_use_native_facts(context)
    assert actual["nativeSourceFacts"] == [context["nativeSourceFacts"][0]]
    assert actual["parents"]["A"]["packet"]["raw"] == {
        "text": {"sourceSameAs": 0}, "other": {"ordinary": "y" * 200}}


def test_input_reference_collision_cannot_authorize_renumbering_literal_data():
    body = {"nested": {"code": "unknown source marker belongs to the input; " * 20}}
    parents = {"A": {"packet": {"raw": {
        "literal": {"sourceSameAs": 2}, "one": body, "two": copy.deepcopy(body)}}}}
    assert share_exact_native_parent_facts(parents) == {"parents": parents}


@pytest.mark.parametrize("marker", [
    {"sourceSameAs": 0}, {"sourceSameAs": 1}, {"sourceSameAs": -1},
    {"sourceSameAs": True}, {"sourceSameAs": "0"},
    {"sourceSameAs": 0, "futureField": [False, 0, 0.0]},
])
def test_opaque_source_marker_cannot_become_a_reference_cycle(marker):
    # Pooling this repeated envelope would make pool[0] refer to pool[1],
    # where the input's literal sourceSameAs:0 closes a new reference cycle.
    body = {"nested": {"literal": marker, "code": "opaque native source; " * 20}}
    parents = {"A": {"packet": {"raw": {"one": body, "two": copy.deepcopy(body)}}},
               "B": {"packet": {"raw": {"one": ["unrelated native fact" * 20] * 2}}}}
    before = copy.deepcopy(parents)
    actual = share_exact_native_parent_facts(parents)
    assert actual == {"parents": before}
    assert parents == before
    actual["parents"]["A"]["packet"]["raw"]["one"]["nested"]["literal"]["sourceSameAs"] = "changed"
    actual["parents"]["B"]["packet"]["raw"]["one"].append("changed")
    assert parents == before
