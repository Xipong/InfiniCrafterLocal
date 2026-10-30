"""Literal native-source table transport, independent of source expression syntax."""

import copy
import json

import pytest


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _reference(**fields):
    return {"source": "read_only_native_attack_source", "version": 1, **fields}


def test_uniform_observations_pack_smaller_and_roundtrip_from_json():
    from infini_local.pipelines.native_attack_tables import (
        pack_attack_tables,
        unpack_attack_tables,
    )

    original = _reference(observations=[
        {"kind": "state_write", "at": n, "block": n // 2,
         "requiredPredicates": ["b12", "b12"], "expression": "opaque(ldfld(x);😺)"}
        for n in range(20)
    ])
    before = copy.deepcopy(original)
    packed = pack_attack_tables(original)
    assert len(_json(packed)) < len(_json(original))
    assert packed["encoding"] == "native_attack_tables_v1"
    assert packed["legend"]
    assert packed["data"]["observations"]["columns"] == list(original["observations"][0])
    assert unpack_attack_tables(json.loads(_json(packed))) == original
    assert original == before
    assert pack_attack_tables(packed) == packed
    assert unpack_attack_tables(original) == original


def test_certificates_and_module_identity_are_shared_without_fact_loss():
    from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables

    def certificate(n):
        return {"method": f"Native.Source.Method{n}", "sourceModuleVersionId": "module-" + "a" * 36,
                "sourceMethodSha256": f"{n:064x}"}

    certificates = [certificate(n) for n in range(12)]
    original = _reference(
        sourceMethods=certificates + [copy.deepcopy(certificates[0])],
        programs=[{**cert, "observations": [], "unresolved": ["hook_unknown"]}
                  for cert in certificates],
        unknown={"sourceModuleVersionId": "other-module-" + "b" * 36,
                 "again": {"sourceModuleVersionId": "other-module-" + "b" * 36}},
        expressionNotation="opaque parent-owned notation",
    )
    packed = pack_attack_tables(original)
    assert len(_json(packed)) < len(_json(original)) * 0.7
    assert _json(packed).count("a" * 36) == 1
    assert _json(packed).count(certificates[0]["sourceMethodSha256"]) == 1
    assert _json(unpack_attack_tables(json.loads(_json(packed)))) == _json(original)
    assert packed["certificates"]
    assert packed["modules"]


def test_repeated_mixed_shapes_keep_missing_null_empty_and_order():
    from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables

    rows = []
    for n in range(40):
        row = {"kind": "literal", "at": n, "block": 0, "requiredPredicates": ["b7", "b7"]}
        if n % 2:
            row.update(expression=None, unknown=[False, True, 0, 0.0, -0.0, "", {}, []])
        else:
            row.update(call="opaque_native_call", arguments={}, receiver="")
        rows.append(row)
    original = _reference(observations=rows, dependencies={
        f"local@{n}": {"expression": f"opaque{n}", "at": n, "block": 0,
                       "requiredPredicates": ["b7"]} for n in range(30)
    }, predicates=[{"id": f"b{n}", "at": n, "op": "brtrue", "inputs": ["x", "x"],
                    "successors": [n + 1, n + 2]} for n in range(20)])
    packed = pack_attack_tables(original)
    assert packed["data"]["observations"]["shapes"]
    assert packed["data"]["dependencies"]["keys"] == list(original["dependencies"])
    assert len(_json(packed)) < len(_json(original)) * 0.7
    assert _json(unpack_attack_tables(json.loads(_json(packed)))) == _json(original)


def _envelope(data, **metadata):
    from infini_local.pipelines.native_attack_tables import pack_attack_tables

    specimen = _reference(observations=[{"long_native_column_name": n} for n in range(80)])
    wrapper = pack_attack_tables(specimen)
    return {"encoding": wrapper["encoding"], "legend": wrapper["legend"], "data": data, **metadata}


@pytest.mark.parametrize("bad_table", [
    {"$table": "list", "columns": ["x"], "rows": [[1, 2]]},
    {"$table": "list", "columns": ["x"], "rows": [[]]},
    {"$table": "list", "columns": ["x", "x"], "rows": [[1, 2]]},
    {"$table": "list", "columns": [1], "rows": [[0]]},
    {"$table": "list", "columns": "x", "rows": [[0]]},
    {"$table": "list", "columns": ["$module"], "rows": [[0]]},
    {"$table": "list", "columns": [], "rows": [None]},
    {"$table": "list", "columns": [], "rows": {}},
    {"$table": "dict", "columns": ["x"], "rows": [[1]], "keys": []},
    {"$table": "dict", "columns": ["x"], "rows": [[1], [2]], "keys": ["a", "a"]},
    {"$table": "dict", "columns": ["x"], "rows": [[1]], "keys": [False]},
    {"$table": "dict", "columns": ["x"], "rows": [[1]], "keys": ["$module"]},
    {"$table": "list", "shapes": [["x"]], "rows": [[-1, [1]]]},
    {"$table": "list", "shapes": [["x"]], "rows": [[1, [1]]]},
    {"$table": "list", "shapes": [["x"]], "rows": [[True, [1]]]},
    {"$table": "list", "shapes": [["x"]], "rows": [["0", [1]]]},
    {"$table": "list", "shapes": [["x"]], "rows": [[0, [1, 2]]]},
    {"$table": "list", "shapes": [], "rows": [[0, []]]},
    {"$table": "list", "shapes": [["x"]], "columns": ["x"], "rows": []},
    {"$table": "unknown", "columns": ["x"], "rows": [[1]]},
    {"$table": "list", "columns": ["x"], "rows": [[1]], "extra": "do not discard"},
])
def test_recursive_table_bounds_refuse_instead_of_silently_dropping_facts(bad_table):
    from infini_local.pipelines.native_attack_tables import unpack_attack_tables

    nested = {"$table": "list", "columns": ["nested"], "rows": [[bad_table]]}
    encoded = _envelope(_reference(observations=nested))
    before = copy.deepcopy(encoded)
    with pytest.raises(ValueError):
        unpack_attack_tables(encoded)
    assert encoded == before


@pytest.mark.parametrize("marker", ["$module", "$certificate"])
@pytest.mark.parametrize("index", [-1, 1, True, 0.0, "0", None])
def test_pool_indices_are_strict_bounded_in_nested_table_cells(marker, index):
    from infini_local.pipelines.native_attack_tables import unpack_attack_tables

    encoded = _envelope(_reference(observations={
        "$table": "dict", "keys": ["local"], "columns": ["expression"],
        "rows": [[{marker: index}]]
    }), modules=["module"], certificates=[{
        "method": "M", "sourceModuleVersionId": "module", "sourceMethodSha256": "hash"
    }])
    with pytest.raises(ValueError):
        unpack_attack_tables(encoded)


@pytest.mark.parametrize("value", [
    {"$module": 0, "extra": "fact"},
    {"$certificate": 0, "method": "must-not-overwrite"},
    {"method": "must-not-overwrite", "$certificate": 0},
    {"$module": 0, "$certificate": 0},
])
def test_reference_collisions_are_rejected_without_overwriting_fields(value):
    from infini_local.pipelines.native_attack_tables import unpack_attack_tables

    encoded = _envelope(_reference(unknown=value), modules=["m"], certificates=[{
        "method": "M", "sourceModuleVersionId": "m", "sourceMethodSha256": "h"
    }])
    with pytest.raises(ValueError):
        unpack_attack_tables(encoded)


@pytest.mark.parametrize("reference", [
    {"source": "read_only_native_attack_source", "coverage": {"unresolved": "refused"}},
    {"source": "other", "version": 1, "expression": "unmodified(x)"},
    {"source": "read_only_native_attack_source", "version": 2},
    {"source": "read_only_native_attack_source", "version": True},
    {"source": "read_only_native_attack_source", "version": 1.0},
    {"encoding": "native_attack_tables_v2", "data": {"$table": "unknown"}},
    _reference(encoding="native_attack_tables_v1", unknown=[]),
    _reference(unknown={"$table": "literal source field"}),
    _reference(unknown=[{"$certificate": 0}]),
    _reference(unknown={"$module": "literal"}),
    _reference(coverage={"unresolved": []}),
])
def test_unknown_refused_small_and_colliding_sources_pass_through_detached(reference):
    from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables

    before = copy.deepcopy(reference)
    for transform in (pack_attack_tables, unpack_attack_tables):
        result = transform(reference)
        assert _json(result) == _json(before)
        assert result is not reference
    assert reference == before


def _independent_decode(document):
    """Test reader of the published legend, with no production decoder calls."""
    modules = document.get("modules", [])
    certificates = []

    def read(node):
        if isinstance(node, list):
            return [read(child) for child in node]
        if not isinstance(node, dict):
            return node
        if "$module" in node:
            return modules[node["$module"]]
        if "$table" in node:
            rows = []
            for row in node["rows"]:
                fields, cells = (node["shapes"][row[0]], row[1]) if "shapes" in node else (node["columns"], row)
                rows.append({name: read(cell) for name, cell in zip(fields, cells)})
            return dict(zip(node["keys"], rows)) if node["$table"] == "dict" else rows
        pairs = []
        for name, cell in node.items():
            pairs.extend(certificates[cell].items() if name == "$certificate" else [(name, read(cell))])
        return dict(pairs)

    certificates = read(document.get("certificates", []))
    return read(document["data"])


def test_independent_reader_fresh_process_and_detached_nested_values():
    import subprocess
    import sys

    from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables

    cert = {"method": "Native.M", "sourceModuleVersionId": "m" * 40, "sourceMethodSha256": "h" * 64}
    original = _reference(
        sourceMethods=[cert, copy.deepcopy(cert)],
        programs=[{**cert, "observations": [
            {"kind": "literal", "at": n, "block": n, "requiredPredicates": ["b1", "b1"],
             "expression": "source_block(3,requires=[b1],value=opaque( x ));😺\n"}
            for n in range(40)]}],
        extra={"literal-marker-value": "$table", "scalars": [1, True, 1.0, -0.0, None]},
        expressionNotation={"grammar": "owned elsewhere", "missingMeans": None},
    )
    before = copy.deepcopy(original)
    packed = pack_attack_tables(original)
    packed_wire = _json(packed)
    assert _json(_independent_decode(json.loads(packed_wire))) == _json(original)
    process = subprocess.run(
        [sys.executable, "-c", "import json,sys; "
         "from infini_local.pipelines.native_attack_tables import unpack_attack_tables; "
         "print(json.dumps(unpack_attack_tables(json.load(sys.stdin)),ensure_ascii=False,separators=(',',':')))"],
        input=packed_wire, text=True, encoding="utf-8", capture_output=True, check=True, timeout=30,
    )
    assert process.stdout.rstrip("\n") == _json(original)
    decoded = unpack_attack_tables(json.loads(packed_wire))
    assert _json(unpack_attack_tables(decoded)) == _json(original)
    assert _json(pack_attack_tables(json.loads(packed_wire))) == packed_wire
    decoded["sourceMethods"][0]["method"] = "changed"
    assert decoded["sourceMethods"][1]["method"] == "Native.M"
    packed["data"]["extra"]["scalars"].append("changed")
    assert original == before


def test_deterministic_json_tree_corpus_preserves_scalar_types_and_field_order():
    import random

    from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables

    rng = random.Random(401)
    atoms = [None, True, False, 0, 1, 1.0, -0.0, "", "$certificate", "текст😺"]

    def tree(depth):
        if depth == 0:
            return copy.deepcopy(rng.choice(atoms))
        choice = rng.randrange(3)
        if choice == 0:
            return [tree(depth - 1) for _ in range(rng.randrange(5))]
        if choice == 1:
            names = ["unknown", "expression", "predicates", "null", "nested"]
            rng.shuffle(names)
            return {name: tree(depth - 1) for name in names[:rng.randrange(6)]}
        return tree(0)

    for _ in range(60):
        original = _reference(observations=[{
            "kind": "source", "at": n, "block": 0, "requiredPredicates": [],
            "unknown": tree(3), "expression": "opaque statement unchanged"
        } for n in range(15)], extra=tree(4))
        before = _json(original)
        packed = pack_attack_tables(original)
        packed_wire = _json(packed)
        decoded = unpack_attack_tables(json.loads(packed_wire))
        assert _json(decoded) == before
        assert _json(original) == before
        assert len(packed_wire) <= len(before)
        if "encoding" in packed:
            assert _json(_independent_decode(json.loads(packed_wire))) == before


@pytest.mark.parametrize("change", [
    {"legend": None}, {"legend": "unknown rules"}, {"extra": "fact"},
    {"modules": None}, {"modules": [0]}, {"certificates": {}},
    {"certificates": [{"$certificate": 0}]},
    {"certificates": [{"method": "M", "sourceModuleVersionId": {"$module": 0}, "sourceMethodSha256": "h"}]},
    {"certificates": [{"method": "M", "sourceModuleVersionId": "m", "sourceMethodSha256": "h", "extra": "fact"}]},
    {"data": {"source": "read_only_native_attack_source", "version": 2}},
    {"data": {"source": "read_only_native_attack_source", "coverage": "refused"}},
    {"data": []},
])
def test_known_envelope_never_discards_unknown_metadata_or_invents_source(change):
    from infini_local.pipelines.native_attack_tables import unpack_attack_tables

    encoded = _envelope(_reference())
    encoded.update(change)
    with pytest.raises(ValueError):
        unpack_attack_tables(encoded)


def test_size_gate_counts_envelope_legend_and_pools():
    from infini_local.pipelines.native_attack_tables import pack_attack_tables

    # A local column table saves characters, but not its complete reading legend.
    original = _reference(observations=[{"a_repeated_column_name": n} for n in range(5)])
    assert _json(pack_attack_tables(original)) == _json(original)


def test_certificate_identity_uses_full_literal_tuple_and_retains_unknown_fields():
    from infini_local.pipelines.native_attack_tables import pack_attack_tables, unpack_attack_tables

    cert = {"method": "Native.SameMethod", "sourceModuleVersionId": "a" * 40,
            "sourceMethodSha256": "h" * 64}
    variants = [cert, {**cert, "sourceModuleVersionId": "b" * 40},
                {**cert, "sourceMethodSha256": "i" * 64},
                dict(reversed(list(cert.items()))),
                {"unknownBefore": None, **cert},
                {**cert, "unknownAfter": {"empty": [], "null": None}}]
    original = _reference(sourceMethods=[copy.deepcopy(variant) for _ in range(12) for variant in variants])
    packed = pack_attack_tables(original)
    assert len(_json(packed)) < len(_json(original))
    assert _json(unpack_attack_tables(json.loads(_json(packed)))) == _json(original)
    assert _json(_independent_decode(json.loads(_json(packed)))) == _json(original)
