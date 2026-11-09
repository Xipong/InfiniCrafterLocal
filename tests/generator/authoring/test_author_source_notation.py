from __future__ import annotations

import copy
import json
from collections import Counter
import pytest

from infini_local.pipelines.context.author_source_notation import compact_author_parent_context


def expand_notation(value):
    """Independent reader of the inline notation, including order/multiplicity."""
    if isinstance(value, list):
        result = []
        for child in value:
            if isinstance(child, dict) and set(child) == {"context", "method", "reason", "ilOffsets"}:
                result.extend(f"{child['context']}:{child['method']}:effect_source_site@{offset}:{child['reason']}"
                              for offset in child["ilOffsets"])
            else:
                result.append(expand_notation(child))
        return result
    if not isinstance(value, dict):
        return value
    if set(value) == {"id", "ilSites"}:
        sites = []
        for site in value["ilSites"]:
            ranges = site["sourceLines"]
            row = {"mapping": "unavailable" if ranges is None else "source_lines", "ilOffset": site["ilOffset"]}
            if ranges is not None:
                row["locations"] = [{"ilOffset": site["ilOffset"], "startLine": first, "endLine": last}
                                    for first, last in ranges]
            sites.append(row)
        return {"id": value["id"], "sourceSites": sites, "mapping": "raw_predicate_sites"}
    return {key: copy.deepcopy(child) if key in {"generatedParent", "tooltipLines", "tooltipSource"}
            else expand_notation(child) for key, child in value.items() if key != "parentContextNotation"}


def _diagnostic(offset, method="Terraria.Projectile.AI_001"):
    return f"motion_source:{method}:effect_source_site@{offset}:effect_source_site_count_bound"


def _context():
    return {"parents": {"A": {"packet": {"raw": {
        "coverage": {"proved": ["source slice"], "unresolved": [
            *[_diagnostic(n) for n in range(10, 60)], _diagnostic(59),
            "unknown_other_diagnostic", *[_diagnostic(n, "Other.Method") for n in range(10, 60)]]},
        "sourceLocation": {"sourceRecord": "s0", "predicates": [
            {"id": f"b{n}", "mapping": "raw_predicate_sites", "sourceSites": [
                {"mapping": "source_lines", "ilOffset": n, "locations": [
                    {"ilOffset": n, "startLine": 5, "endLine": 8},
                    {"ilOffset": n, "startLine": 5, "endLine": 8}]},
                {"mapping": "unavailable", "ilOffset": n + 1}]}
            for n in range(30)]}}}}}}


def test_roundtrip_preserves_values_order_duplicates_and_input():
    source = _context()
    before = copy.deepcopy(source)
    compact = compact_author_parent_context(source)
    assert source == before
    assert expand_notation(compact) == source
    assert len(json.dumps(compact)) < len(json.dumps(source))
    unknowns = source["parents"]["A"]["packet"]["raw"]["coverage"]["unresolved"]
    restored = expand_notation(compact)["parents"]["A"]["packet"]["raw"]["coverage"]["unresolved"]
    assert Counter(restored) == Counter(unknowns)
    assert restored.count(_diagnostic(59)) == 2
    assert compact_author_parent_context(compact) == compact


def test_future_rows_literals_and_insufficient_savings_stay_unchanged():
    source = _context()
    literals = {"unresolved": [_diagnostic(n) for n in range(100)]}
    source["parents"]["A"]["packet"]["raw"].update(generatedParent=literals, tooltipLines=literals, tooltipSource=literals)
    source["future"] = {"id": "b0", "sourceSites": [{"mapping": "new", "ilOffset": 3}], "mapping": "raw_predicate_sites"}
    source["mixed"] = {"unresolved": [False, 7, None, "motion_source:Method:effect_source_site@01:effect_source_site_count_bound"]}
    compact = compact_author_parent_context(source)
    assert expand_notation(compact) == source
    for name in ("generatedParent", "tooltipLines", "tooltipSource"):
        assert compact["parents"]["A"]["packet"]["raw"][name] == literals
    assert compact["future"] == source["future"]
    assert compact["mixed"] == source["mixed"]
    small = {"unresolved": [_diagnostic(1)]}
    assert compact_author_parent_context(small) == small


@pytest.mark.parametrize("invalid", [
    {"ilOffset": True, "startLine": 5, "endLine": 8},
    {"ilOffset": 99, "startLine": 5, "endLine": 8},
    {"ilOffset": 0, "startLine": 0, "endLine": 8},
    {"ilOffset": 0, "startLine": 8, "endLine": 5},
    {"ilOffset": 0, "startLine": 5, "endLine": 8, "future": "keep"},
])
def test_malformed_or_future_source_location_is_not_interpreted(invalid):
    source = _context()
    location = source["parents"]["A"]["packet"]["raw"]["sourceLocation"]
    location["predicates"][0]["sourceSites"][0]["locations"] = [invalid]
    compact = compact_author_parent_context(source)
    assert expand_notation(compact) == source
    assert compact["parents"]["A"]["packet"]["raw"]["sourceLocation"]["predicates"][0] == location["predicates"][0]


def test_missing_offset_or_changed_mapping_is_detected():
    source = _context()
    compact = compact_author_parent_context(source)
    compact["parents"]["A"]["packet"]["raw"]["coverage"]["unresolved"][0]["ilOffsets"].pop()
    assert expand_notation(compact) != source
    compact = compact_author_parent_context(source)
    compact["parents"]["A"]["packet"]["raw"]["sourceLocation"]["predicates"][0]["ilSites"][0]["sourceLines"] = None
    assert expand_notation(compact) != source


@pytest.mark.parametrize("future", [
    {"id": "future", "ilSites": [{"ilOffset": 1, "sourceLines": None}]},
    {"context": "future", "method": "Future.Method", "reason": "unknown", "ilOffsets": [1]},
    {"parentContextNotation": {"future": "must remain literal"}},
])
def test_existing_output_notation_refuses_complete_projection(future):
    source = _context()
    source["future"] = future
    compact = compact_author_parent_context(source)
    assert json.dumps(compact, sort_keys=True) == json.dumps(source, sort_keys=True)
    assert "parentContextNotation" not in compact


@pytest.mark.parametrize("offset", ["9" * 5000, "2147483648"])
@pytest.mark.parametrize("position", [0, 26])
def test_unsupported_il_offsets_stay_literal_and_break_runs(offset, position):
    source = _context()
    unknown = _diagnostic(offset)
    original = [_diagnostic(value) for value in [0, 2147483647, *range(10, 60)]]
    original.insert(position, unknown)
    source["parents"]["A"]["packet"]["raw"]["coverage"]["unresolved"] = original
    before = copy.deepcopy(source)
    compact = compact_author_parent_context(source)
    assert source == before
    assert expand_notation(compact) == source
    rows = compact["parents"]["A"]["packet"]["raw"]["coverage"]["unresolved"]
    literal_index = rows.index(unknown)
    assert any(isinstance(row, dict) and 2147483647 in row["ilOffsets"] for row in rows)
    if position:
        assert isinstance(rows[literal_index - 1], dict)
        assert isinstance(rows[literal_index + 1], dict)


def expand_source_text(context):
    """Independent reader; preserve every other field and all existing references."""
    shared = context.get("nativeSourceText", [])

    def visit(value):
        if isinstance(value, list):
            return [visit(child) for child in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, child in value.items():
            if key in {"generatedParent", "tooltipLines", "tooltipSource"}:
                result[key] = copy.deepcopy(child)
            elif key == "sourceTextParts":
                result["code"] = "".join(shared[part["sourceText"]] if isinstance(part, dict) else part
                                         for part in child)
            else:
                result[key] = visit(child)
        return result

    return {key: visit(child) for key, child in context.items()
            if key not in {"nativeSourceText", "sourceTextNotation"}}


def _source_text_context():
    prefix = "using Terraria;\r\nprivate void NativeMethod()\r\n{\r\n" + "// начало\r\n" * 20
    suffix = "DoSourceWork(unknownState);\r\n" * 150 + "}\r\n"
    rows = [{"method": "Terraria.Projectile.NativeMethod", "coverage": "identity_specialized_method",
             "code": prefix + middle + suffix, "projectiles": [identity],
             "entryGuards": ["runtimeUnknown", "runtimeUnknown"],
             "sourceMap": [{"startLine": 24, "endLine": 25}],
             "futureMetadata": {"unresolved": ["unknown", "unknown"]}}
            for identity, middle in [(7, ";\r\n"), (8, "if (unknownState) { ChangeState(); }\r\n")]]
    return {"parents": {"A": {"packet": {"raw": {"source": rows,
            "reused": {"sourceSameAs": 0}, "reusedAgain": {"sourceSameAs": 0}}}}},
            "nativeSourceFacts": [copy.deepcopy(rows[0])]}


def test_shared_code_roundtrip_metadata_maps_references_and_no_mutation():
    source = _source_text_context()
    before = copy.deepcopy(source)
    projected = compact_author_parent_context(source)
    assert source == before
    assert expand_notation(expand_source_text(projected)) == source
    assert len(json.dumps(projected, ensure_ascii=False)) < len(json.dumps(source, ensure_ascii=False))
    assert compact_author_parent_context(projected) == projected
    records = projected["parents"]["A"]["packet"]["raw"]["source"]
    assert all(len(row["sourceTextParts"]) <= 3 for row in records)
    assert records[0]["projectiles"] != records[1]["projectiles"]
    assert projected["parents"]["A"]["packet"]["raw"]["reused"] == {"sourceSameAs": 0}
    assert expand_source_text(projected)["nativeSourceFacts"] == source["nativeSourceFacts"]
    # Mutation controls: losing one code byte or one repeated guard must fail.
    broken = copy.deepcopy(projected)
    broken["nativeSourceText"][0] = broken["nativeSourceText"][0][1:]
    assert expand_source_text(broken) != source
    broken = copy.deepcopy(projected)
    broken["parents"]["A"]["packet"]["raw"]["source"][0]["entryGuards"].pop()
    assert expand_source_text(broken) != source


@pytest.mark.parametrize("key", ["sourceTextParts", "nativeSourceText", "sourceTextNotation", "sourceText"])
def test_source_text_future_notation_collisions_stay_literal(key):
    source = _source_text_context()
    source["future"] = {key: "unrecognized existing literal"}
    assert compact_author_parent_context(source) == source


def test_source_text_literal_generated_packets_and_unknown_coverage_are_not_interpreted():
    source = _source_text_context()
    rows = source["parents"]["A"]["packet"]["raw"]["source"]
    for key in ("tooltipLines", "tooltipSource", "generatedParent"):
        source[key] = copy.deepcopy(rows)
    source["future"] = [{**row, "coverage": "unknown_future_capture"} for row in rows]
    projected = compact_author_parent_context(source)
    assert expand_source_text(projected) == source
    for key in ("tooltipLines", "tooltipSource", "generatedParent", "future"):
        assert projected[key] == source[key]


def test_source_text_short_or_unrelated_code_does_not_add_notation():
    source = _source_text_context()
    source.pop("nativeSourceFacts")
    for row, code in zip(source["parents"]["A"]["packet"]["raw"]["source"], ["same\nA\n", "same\nB\n"]):
        row["code"] = code
    assert compact_author_parent_context(source) == source


def test_source_text_and_location_notation_compose_without_changing_line_maps():
    source = _context()
    source.update(_source_text_context())
    source["locations"] = _context()["parents"]["A"]["packet"]["raw"]["sourceLocation"]
    projected = compact_author_parent_context(source)
    assert "parentContextNotation" in projected and "nativeSourceText" in projected
    assert expand_notation(expand_source_text(projected)) == source
