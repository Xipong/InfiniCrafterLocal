"""Reversible, literal JSON transport; expression strings are never interpreted."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any

_ENCODING = "native_attack_tables_v1"
_LEGEND = (
    "$table list/dict: rows zip with columns; dict keys name rows. "
    "With shapes instead of columns, each row is [shapeIndex,cells]. "
    "All row/field order and duplicates are literal; recursively decode cells. "
    "$certificate: index into certificates; splice its fields at this position. "
    "$module: index into modules. Indices are zero-based; strings stay verbatim."
)
_RESERVED = {"$table", "$certificate", "$module"}
_CERTIFICATE = ("method", "sourceModuleVersionId", "sourceMethodSha256")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _native(value: dict) -> bool:
    return (value.get("source") == "read_only_native_attack_source"
            and type(value.get("version")) is int and value["version"] == 1)


def _collision(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(_RESERVED.intersection(value)) or any(_collision(v) for v in value.values())
    if isinstance(value, list):
        return any(_collision(v) for v in value)
    return False


def _tables(value: Any) -> Any:
    # Semantic render layers are already a named, consumer-facing view. Zipping
    # their fields back into a generic table would hide the useful layer labels.
    if isinstance(value, dict) and isinstance(value.get("renderLayerView"), dict) and value["renderLayerView"].get("version") == 1:
        return deepcopy(value)
    if not isinstance(value, (list, dict)):
        return value
    transformed = ([_tables(v) for v in value] if isinstance(value, list)
                   else {k: _tables(v) for k, v in value.items()})
    rows = list(transformed.values()) if isinstance(transformed, dict) else transformed
    if len(rows) < 2 or not all(isinstance(row, dict) for row in rows):
        return transformed
    shapes = list(dict.fromkeys(tuple(row) for row in rows))
    if any(_RESERVED.intersection(shape) for shape in shapes):
        return transformed
    table: dict[str, Any] = {"$table": "dict" if isinstance(transformed, dict) else "list"}
    if len(shapes) == 1:
        table.update(columns=list(shapes[0]), rows=[list(row.values()) for row in rows])
    else:
        indices = {shape: n for n, shape in enumerate(shapes)}
        table.update(shapes=[list(shape) for shape in shapes],
                     rows=[[indices[tuple(row)], list(row.values())] for row in rows])
    if isinstance(transformed, dict):
        table["keys"] = list(transformed)
    return table if len(_json(table)) < len(_json(transformed)) else transformed


def _walk_objects(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_objects(child)


def _certificate(value: dict) -> tuple | None:
    # Only a literal contiguous prefix may be spliced without changing field order.
    if tuple(value)[:3] == _CERTIFICATE and all(type(value[k]) is str for k in _CERTIFICATE):
        return tuple(value[k] for k in _CERTIFICATE)
    return None


def _references(value: Any, certificates: dict, modules: dict) -> Any:
    if isinstance(value, list):
        return [_references(v, certificates, modules) for v in value]
    if not isinstance(value, dict):
        return value
    cert = _certificate(value)
    result = {}
    if cert in certificates:
        result["$certificate"] = certificates[cert]
    for key, child in value.items():
        if cert in certificates and key in _CERTIFICATE:
            continue
        if key == "sourceModuleVersionId" and type(child) is str and child in modules:
            result[key] = {"$module": modules[child]}
        else:
            result[key] = _references(child, certificates, modules)
    return result


def pack_attack_tables(reference: dict) -> dict:
    """Return a detached packed source only when its complete JSON is smaller.

    Unknown versions/refusals and reserved-key collisions pass through unchanged.
    Sharing is exact string/tuple identity, never a method-name interpretation.
    """
    original = deepcopy(reference)
    if not _native(original) or _collision(original):
        return original
    cert_counts, module_counts = Counter(), Counter()
    for obj in _walk_objects(original):
        cert = _certificate(obj)
        if cert is not None:
            cert_counts[cert] += 1
        module = obj.get("sourceModuleVersionId")
        if type(module) is str:
            module_counts[module] += 1
    certs = [cert for cert, count in cert_counts.items() if count > 1]
    modules = [module for module, count in module_counts.items() if count > 1]
    best, size = original, len(_json(original))
    # Include metadata overhead: pooling and tables need not help small sources.
    for share_certs in (False, True) if certs else (False,):
        for share_modules in (False, True) if modules else (False,):
            cert_index = {cert: n for n, cert in enumerate(certs)} if share_certs else {}
            module_index = {module: n for n, module in enumerate(modules)} if share_modules else {}
            packed = {"encoding": _ENCODING, "legend": _LEGEND,
                      "data": _tables(_references(original, cert_index, module_index))}
            if share_certs:
                packed["certificates"] = _tables([
                    _references(dict(zip(_CERTIFICATE, cert)), {}, module_index) for cert in certs
                ])
            if share_modules:
                packed["modules"] = list(modules)
            candidate_size = len(_json(packed))
            if candidate_size < size:
                best, size = packed, candidate_size
    return best


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError("Invalid native attack tables: " + detail)


def _index(value: Any, pool: list) -> Any:
    _require(type(value) is int and 0 <= value < len(pool), "reference index out of bounds")
    return pool[value]


def _names(value: Any) -> bool:
    return (isinstance(value, list) and all(type(v) is str for v in value)
            and len(set(value)) == len(value))


def _decode_table(value: dict, certificates: list, modules: list) -> Any:
    kind = value["$table"]
    _require(kind in ("list", "dict"), "unknown table kind")
    mixed = "shapes" in value
    schema_key = "shapes" if mixed else "columns"
    expected = {"$table", schema_key, "rows"} | ({"keys"} if kind == "dict" else set())
    _require(set(value) == expected, "table fields")
    shapes = value[schema_key] if mixed else [value[schema_key]]
    _require(isinstance(shapes, list) and bool(shapes), "table shapes")
    for shape in shapes:
        _require(_names(shape) and not _RESERVED.intersection(shape), "table column names")
    rows = value["rows"]
    _require(isinstance(rows, list), "table rows")
    decoded = []
    for row in rows:
        _require(isinstance(row, list), "table row")
        if mixed:
            _require(len(row) == 2, "mixed row must be [shapeIndex,cells]")
            columns = _index(row[0], shapes)
            cells = row[1]
        else:
            columns, cells = shapes[0], row
        _require(isinstance(cells, list) and len(cells) == len(columns), "row column count")
        decoded.append({key: _decode(child, certificates, modules)
                        for key, child in zip(columns, cells)})
    if kind == "dict":
        keys = value["keys"]
        _require(_names(keys) and not _RESERVED.intersection(keys)
                 and len(keys) == len(decoded), "dictionary row keys")
        return dict(zip(keys, decoded))
    return decoded


def _decode(value: Any, certificates: list, modules: list) -> Any:
    if isinstance(value, list):
        return [_decode(v, certificates, modules) for v in value]
    if not isinstance(value, dict):
        return value
    if "$module" in value:
        _require(set(value) == {"$module"}, "module reference fields")
        return _index(value["$module"], modules)
    if "$table" in value:
        return _decode_table(value, certificates, modules)
    result = {}
    for key, child in value.items():
        if key == "$certificate":
            cert = _index(child, certificates)
            _require(not set(cert).intersection(value), "certificate field collision")
            result.update(deepcopy(cert))
        else:
            result[key] = _decode(child, certificates, modules)
    return result


def unpack_attack_tables(reference: dict) -> dict:
    """Decode independently; malformed known encodings raise ``ValueError``.

    Unknown encodings and raw sources/refusals are detached passthroughs. A known
    encoding never guesses missing columns, truncates cells, or accepts negative
    or boolean pool indices. Certificates may reference modules, not certificates.
    """
    original = deepcopy(reference)
    if "source" in original or original.get("encoding") != _ENCODING:
        return original
    _require({"encoding", "legend", "data"} <= set(original)
             <= {"encoding", "legend", "data", "certificates", "modules"}, "envelope fields")
    _require(original["legend"] == _LEGEND, "reading legend")
    modules = original.get("modules", [])
    _require(isinstance(modules, list) and all(type(v) is str for v in modules), "module pool")
    certificates = _decode(original.get("certificates", []), [], modules)
    _require(isinstance(certificates, list), "certificate pool")
    for cert in certificates:
        _require(isinstance(cert, dict) and tuple(cert) == _CERTIFICATE
                 and all(type(v) is str for v in cert.values()), "certificate fields")
    result = _decode(original["data"], certificates, modules)
    _require(isinstance(result, dict) and _native(result), "source identity/version")
    return result
