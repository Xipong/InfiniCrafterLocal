#!/usr/bin/env python3
"""Read-only, offline craft audit. Documentation comes from canonical contracts."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
from infini_local.core.schema_validation import strict_schema_errors

MISSING = object()


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def pointer(parts: tuple) -> str:
    return "#/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def receipt_parts(path: str) -> tuple:
    """Only the canonical dot/index receipt grammar; never evaluate input text."""
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*", path):
        return ()
    return tuple(int(i) if i else key for key, i in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path))


def lookup(value: Any, parts: tuple) -> Any:
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
            value = value[part]
        else:
            return MISSING
    return value


def read_document(path: Path) -> dict:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"Duplicate JSON key: {key!r}")
            out[key] = value
        return out

    def nonfinite(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique, parse_constant=nonfinite)
    # Also rejects exponent overflow (1e999), which parse_constant does not see.
    dump(data)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "data": data}


class SchemaDocs:
    """Conservative schema traversal, not a second validator or rule catalogue."""

    def __init__(self, filename: str):
        self.filename = filename
        self.document = read_document(ROOT / "contracts/schemas" / filename)
        self.root = self.document["data"]

    def select(self, schema: dict, value: Any, path: tuple = ()) -> tuple[dict, tuple]:
        if "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                return {}, path  # Never fetch external references.
            parts = tuple(p.replace("~1", "/").replace("~0", "~") for p in ref[2:].split("/"))
            target = lookup(self.root, parts)
            if not isinstance(target, dict):
                return {}, path
            return self.select(target, value, parts)
        union_key = "oneOf" if "oneOf" in schema else "anyOf"
        branches = schema.get(union_key)
        if branches:
            matches = [i for i, branch in enumerate(branches)
                       if not strict_schema_errors(value, branch, root=self.root, limit=1)]
            # A malformed call still has useful docs when its explicit fn is known.
            if not matches and isinstance(value, dict) and "fn" in value:
                matches = [i for i, branch in enumerate(branches)
                           if branch.get("properties", {}).get("fn", {}).get("const", MISSING) == value["fn"]]
            if len(matches) != 1:
                return {k: v for k, v in schema.items() if k not in ("oneOf", "anyOf")}, path
            index = matches[0]
            selected, selected_path = self.select(branches[index], value, path + (union_key, index))
            return {**{k: v for k, v in schema.items() if k not in ("oneOf", "anyOf")}, **selected}, selected_path
        return schema, path

    def rows(self, value: Any, schema: dict | None = None, parts: tuple = (), schema_path: tuple = ()) -> list[dict]:
        schema, schema_path = self.select(self.root if schema is None else schema, value, schema_path)
        row = {"path": pointer(parts), "parts": list(parts), "value": value,
               "documented": bool(schema), "schema": self.filename + pointer(schema_path),
               "description": schema.get("description", ""), "units": schema.get("x-infini-units", ""),
               "reference": schema.get("x-infini-reference"), "state": "present"}
        # Keep object descriptions (releaseEffect/window) beside the nested leaves.
        rows = [row] if not isinstance(value, (dict, list)) or not value or row["description"] else []
        if isinstance(value, dict):
            props = schema.get("properties", {})
            for key, child in value.items():
                sub = props.get(key, schema.get("additionalProperties", {}))
                rows.extend(self.rows(child, sub if isinstance(sub, dict) else {}, parts + (key,),
                                      schema_path + ("properties", key)))
            for key, sub in props.items():
                if key not in value and "default" in sub:
                    rows.append({"path": pointer(parts + (key,)), "parts": list(parts + (key,)),
                                 "value": sub["default"], "documented": True,
                                 "schema": self.filename + pointer(schema_path + ("properties", key)),
                                 "description": sub.get("description", ""), "units": sub.get("x-infini-units", ""),
                                 "reference": None, "state": "absent_schema_default"})
        elif isinstance(value, list):
            for i, child in enumerate(value):
                rows.extend(self.rows(child, schema.get("items", {}), parts + (i,), schema_path + ("items",)))
        if "default" in schema:
            row["default"] = schema["default"]
        return rows

    def saved_param_docs(self, fn: str, suffix: tuple, *, same_units_only: bool = False) -> dict:
        """Read declared historical names for display, never source admission."""
        from infini_local.core.runtime_authoring.capability_registry import capability_for_saved_receipt
        from infini_local.core.runtime_authoring.receipt_input import receipt_param_spec
        if not suffix or not all(isinstance(part, str) for part in suffix):
            return {}
        cap = capability_for_saved_receipt(fn)
        original = ".".join(suffix)
        canonical = cap.canonical_receipt_param_path(original) if cap is not None else None
        if canonical is None:
            return {}
        if same_units_only and canonical != original:
            leaf = receipt_param_spec(cap, canonical)
            if leaf is None or suffix[-1] not in leaf.previous_author_names:
                return {}  # Old engine-domain units are not v6 Author units.
        return self.param_docs(cap.name, tuple(canonical.split(".")))

    def param_docs(self, fn: str, suffix: tuple) -> dict:
        calls = self.root.get("properties", {}).get("calls", {}).get("items", {}).get("oneOf", [])
        matches = [(i, c) for i, c in enumerate(calls) if c.get("properties", {}).get("fn", {}).get("const") == fn]
        if len(matches) != 1:
            return {}
        i, schema = matches[0]
        sp = ("properties", "calls", "items", "oneOf", i, "properties", "params")
        schema = schema["properties"]["params"]
        for key in suffix:
            # A source-free ambiguous variant is deliberately left unexplained.
            if "$ref" in schema:
                schema, sp = self.select(schema, MISSING, sp)
            if "oneOf" in schema or "anyOf" in schema:
                return {}
            schema = schema.get("properties", {}).get(key, {})
            sp += ("properties", key)
        return {"description": schema.get("description", ""), "units": schema.get("x-infini-units", ""),
                "schema": self.filename + pointer(sp),
                **({"default": schema["default"]} if "default" in schema else {})} if schema else {}


def leaves(value: Any, parts: tuple = ()) -> list[dict]:
    if isinstance(value, dict) and value:
        return [row for key, child in value.items() for row in leaves(child, parts + (key,))]
    if isinstance(value, list) and value:
        return [row for i, child in enumerate(value) for row in leaves(child, parts + (i,))]
    return [{"path": pointer(parts), "parts": list(parts), "value": value}]


def wire_documentation(data: dict, docs: SchemaDocs) -> list[dict]:
    """Index current registry projections; never invert them into lost Author JSON."""
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.technical_lowering import _parameter_outputs, path_matches
    from infini_local.core.runtime_authoring.receipt_input import receipt_param_spec

    index = []
    for fn, cap in CAPABILITY_REGISTRY.items():
        for name, spec in cap.params.items():
            outputs = _parameter_outputs(fn, name)
            for source_name, destination, literal in spec.projection_paths(name):
                if literal:
                    continue
                leaf = receipt_param_spec(cap, source_name)
                for output in outputs:
                    if output.endswith("." + destination):
                        description = docs.param_docs(fn, tuple(source_name.split(".")))
                        if description:
                            index.append((output, {"capability": fn, "parameter": source_name, **description,
                                                   "projection": leaf.wire_projection_card() if leaf else None}))
    rows = leaves(data)
    for row in rows:
        path = "".join(f"[{p}]" if type(p) is int else ("." if i else "") + p for i, p in enumerate(row["parts"]))
        row["documentation"] = [doc for pattern, doc in index if path_matches(pattern, path)]
    return rows


def check(name: str, operation) -> dict:
    try:
        result = operation()
        return {"name": name, "status": "passed" if result.get("ok") is True else "failed", "result": result}
    except (ImportError, ValueError, TypeError, KeyError, IndexError, RuntimeError, OverflowError) as exc:
        return {"name": name, "status": "notRun", "reason": f"{type(exc).__name__}: {exc}"}


def connections(document: dict, author_rows: list[dict], authored: bool) -> dict:
    """Relations from explicit identifiers and schema reference metadata only."""
    program = document.get("runtimeProgram", {})
    if not isinstance(program, dict):
        return {"nodes": [], "edges": []}
    nodes, edges = [], []
    namespaces = {"entities": "entity", "calls": "call", "effectGroups": "effect_group", "bindings": "binding"}
    for key, namespace in namespaces.items():
        rows = program.get(key, [])
        for i, row in enumerate(rows if isinstance(rows, list) else []):
            if isinstance(row, dict):
                nodes.append({"namespace": namespace, "id": row.get("id"), "path": pointer(("runtimeProgram", key, i)),
                              "kind": row.get("fn", row.get("input", row.get("kind", "")))})
    if authored:
        for row in author_rows:
            ref = row.get("reference")
            if ref and row["state"] == "present":
                edges.append({"from": row["path"], "namespace": ref["namespace"], "to": row["value"], "relation": "schema reference"})
            elif row["parts"] and row["parts"][-1] in ("effectGroupId", "heldEffectGroupId") and row["state"] == "present":
                edges.append({"from": row["path"], "namespace": "effect_group", "to": row["value"], "relation": "explicit effect-group reference"})
        # Omitted item-call targets are canonical validator/compiler semantics;
        # no inferred edge is added here.
    else:
        for row in leaves(program, ("runtimeProgram",)):
            key = row["parts"][-1]
            if key in ("targetId", "entityId", "primaryEntityId", "itemEntityId", "effectGroupId", "heldEffectGroupId"):
                edges.append({"from": row["path"], "namespace": "effect_group" if "GroupId" in key else "entity",
                              "to": row["value"], "relation": "explicit wire reference"})
        entities = program.get("entities", [])
        for i, entity in enumerate(entities if isinstance(entities, list) else []):
            if not isinstance(entity, dict):
                continue
            events = entity.get("events", [])
            for j, event in enumerate(events if isinstance(events, list) else []):
                if isinstance(event, dict):
                    nodes.append({"namespace": "event", "id": event.get("id"),
                                  "path": pointer(("runtimeProgram", "entities", i, "events", j)),
                                  "kind": event.get("action", "")})
                    edges.append({"from": pointer(("runtimeProgram", "entities", i)),
                                  "namespace": "event", "to": event.get("id"),
                                  "relation": f"{entity.get('id')}: {event.get('event')} → {event.get('action')}"})
    for edge in edges:
        targets = [n for n in nodes if n["namespace"] == edge["namespace"] and n["id"] == edge["to"]]
        edge["targetPaths"] = [n["path"] for n in targets]
        edge["resolution"] = "resolved" if len(targets) == 1 else "missing_or_ambiguous"
    return {"nodes": nodes, "edges": edges}


def build_report(item: dict, author: dict | None = None, visual: dict | None = None,
                 vfx: dict | None = None, evidence: list[dict] | None = None) -> dict:
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts

    runtime_docs = SchemaDocs("runtime_program_author.schema.json")
    root_docs = SchemaDocs("author_item_response.schema.json")
    inventory = read_document(ROOT / "contracts/schemas/capability_inventory.generated.json")
    data = item["data"]
    program = data.get("runtimeProgram")
    # The exact schema token determines the lane; an unknown version is not guessed.
    author_token = runtime_docs.root["properties"]["schema"]["const"]
    authored = isinstance(program, dict) and program.get("schema") == author_token
    if authored and author is not None and author["data"] != data:
        raise ValueError("--item is already Author JSON; a different --author-source is ambiguous")
    source = item if authored else author
    sources = {"item": item}
    if author is not None:
        sources["author"] = author
    for label, doc in (("visual", visual), ("vfx", vfx)):
        if doc is not None:
            sources[label] = doc
    author_rows = []
    if source is not None:
        author_rows = root_docs.rows(source["data"])
        # Runtime has its own canonical schema and independent provenance hash.
        author_rows = [r for r in author_rows if r["parts"][:1] != ["runtimeProgram"]]
        if "runtimeProgram" in source["data"]:
            author_rows += runtime_docs.rows(source["data"]["runtimeProgram"], parts=("runtimeProgram",))
        old_program = source["data"].get("runtimeProgram")
        if isinstance(old_program, dict) and old_program.get("schema") == "infini.runtime-program.authoring.v6":
            for row in author_rows:
                parts = tuple(row["parts"])
                if parts[:2] != ("runtimeProgram", "calls") or len(parts) <= 4 or parts[3] != "params":
                    continue
                call = lookup(source["data"], parts[:3])
                docs = runtime_docs.saved_param_docs(call.get("fn", ""), parts[4:], same_units_only=True) if isinstance(call, dict) else {}
                if docs:
                    row.update({key: docs[key] for key in ("description", "units", "schema")})
                    row["documented"] = True
                    # Present value/path stay literal; validation below still
                    # rejects v6 as fresh Author and cannot authenticate it.
    checks = []
    if source is not None:
        def validate_author():
            errors = strict_schema_errors(source["data"].get("runtimeProgram"), runtime_docs.root)
            return {"ok": False, "errors": errors, "scope": "runtime_program_author.schema.json"} if errors else validate_runtime_program(source["data"])
        checks.append(check("Текущий Author validator", validate_author))
    else:
        checks.append({"name": "Проверка исходного Author", "status": "notRun", "reason": "Author JSON отсутствует"})
    if authored:
        checks.append({"name": "Текущий wire validator", "status": "notRun", "reason": "Вход — Author, исполняемый wire не передан"})
    else:
        checks.append(check("Текущий wire validator", lambda: validate_runtime_wire(data)))
    contract = data.get("runtimeContract", {})
    receipts = contract.get("finalWireReceipts", []) if isinstance(contract, dict) else []
    receipt_origin = "saved" if receipts else "absent"
    if not receipts and not authored and source is not None:
        # Delivery intentionally strips runtimeContract. Recompute only from an
        # explicitly supplied Author; then compare against the actual saved wire.
        from infini_local.core.runtime_authoring.compiler import compile_runtime_program
        try:
            receipts = compile_runtime_program(source["data"])["runtimeContract"]["finalWireReceipts"]
            receipt_origin = "recomputed_from_supplied_author"
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            checks.append({"name": "Пересчёт сопоставлений из Author", "status": "notRun", "reason": str(exc)})
    receipt_check = None
    if not authored and receipts:
        receipt_check = check("Текущий compiler receipt audit", lambda: audit_compiler_receipts(
            receipts, authored_document=source["data"] if source else None, final_document=data))
        checks.append(receipt_check)
    elif not authored:
        checks.append({"name": "Текущий compiler receipt audit", "status": "notRun", "reason": "Compiler receipts отсутствуют; источник не восстановлен"})
    source_index = {r["path"]: r for r in author_rows if r["state"] == "present"}
    receipt_links = []
    for i, receipt in enumerate(receipts if isinstance(receipts, list) else []):
        if not isinstance(receipt, dict):
            continue
        ap = receipt_parts(receipt.get("authoredPath", ""))
        fp = receipt_parts(receipt.get("finalPath", ""))
        actual = lookup(data, fp) if fp else MISSING
        origin = source_index.get(pointer(ap)) if ap else None
        docs = origin or (runtime_docs.saved_param_docs(receipt.get("fn", ""), ap[4:])
                          if source is None and receipt_origin == "saved"
                          and ap[:2] == ("runtimeProgram", "calls") and len(ap) > 4 and ap[3] == "params"
                          else runtime_docs.param_docs(receipt.get("fn", ""), ap[4:])
                          if ap[:2] == ("runtimeProgram", "calls") and len(ap) > 4 and ap[3] == "params" else {})
        link = {"receiptIndex": i, "receipt": receipt, "wirePath": pointer(fp) if fp else "",
                "wireValuePresent": actual is not MISSING, "wireValue": actual if actual is not MISSING else None,
                "authorPath": pointer(ap) if ap else "", "authorValuePresent": origin is not None,
                "authorValue": origin["value"] if origin else None,
                "description": docs.get("description", ""), "authorUnits": docs.get("units", ""),
                "schema": docs.get("schema", ""),
                "trust": "checked" if receipt_check and receipt_check["status"] == "passed" else "unverified"}
        receipt_links.append(link)
    visuals = []
    schema_documents = [runtime_docs.document, root_docs.document, inventory]
    for label, doc, filename in (("visual", visual, "visual_runtime_entities.schema.json"),
                                 ("vfx", vfx, "vfx_runtime_events.schema.json")):
        if doc is not None:
            sd = SchemaDocs(filename)
            schema_documents.append(sd.document)
            visuals.append({"source": label, "rows": sd.rows(doc["data"])})
    stored = [row for row in leaves(data) if any(str(p) in ("visual", "vfxManifest", "visualKit", "equipOverlay") for p in row["parts"])]
    advisory = [r for r in author_rows if r["parts"][:1] in (["concept"], ["realization"])]
    if source is None:
        # Retained prose is labelled as stored advisory, never recovered Author.
        advisory = [r for r in leaves(data) if r["parts"][:1] in (["concept"], ["realization"])]
    unknown = [{"source": "author", **r} for r in author_rows if not r["documented"]]
    for result in checks:
        if result["name"] == "Текущий wire validator":
            for error in result.get("result", {}).get("errors", []):
                if error.get("kind") == "additional_property" or str(error.get("code", "")).startswith("unknown_"):
                    path = error.get("path", "")
                    value = lookup(data, receipt_parts(path.removeprefix("$.")))
                    unknown.append({"source": "wire", "path": path, "value": value if value is not MISSING else None, "validator": error})
    return {"schema": "infini.offline-craft-audit.v1", "name": data.get("name", "Без имени"),
            "lane": "author" if authored else "wire", "authorAvailable": source is not None,
            "sources": sources, "schemas": [{k: d[k] for k in ("file", "sha256")} for d in schema_documents],
            "codeOwners": [{"file": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in
                           (Path(__file__), ROOT / "LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py",
                            ROOT / "LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py")],
            "advisory": advisory, "authorFields": author_rows, "wireFields": [] if authored else wire_documentation(data, runtime_docs),
            "connections": connections(data, author_rows, authored), "receipts": receipt_links,
            "authorConnections": connections(source["data"], author_rows, True) if source and not authored else None,
            "receiptOrigin": receipt_origin,
            "unknownFields": unknown,
            "checks": checks, "visualSources": visuals, "storedVisualFields": stored,
            "evidence": evidence or [], "capabilities": inventory["data"]["capabilities"],
            "boundaries": ["Статическое чтение JSON и текущие локальные валидаторы; LLM, runtime и игра не запускаются.",
                           "Авторский замысел и realization — advisory, не наблюдения. Утраченный Author не восстанавливается.",
                           "Compiler receipts подтверждают сопоставление только в пределах указанной проверки; без Author — лишь согласованность wire.",
                           "Единицы в описаниях Author не являются единицами wire. Обратная конверсия и расчёт DPS не выполняются.",
                           "Внешние результаты проверок показываются дословно как предоставленные данные; их запуск и принадлежность предмету не удостоверяются.",
                           "PNG, корректность внешности, native gameplay, multiplayer и качество свежей генерации не проверяются."]}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def code(value: Any) -> str:
    return "<code>" + esc(value) + "</code>"


def anchor(path: str) -> str:
    return "p" + hashlib.sha256(path.encode()).hexdigest()[:20]


def raw_details(title: str, value: Any) -> str:
    return f"<details><summary>{esc(title)}</summary><pre>{esc(dump(value))}</pre></details>"


def field_table(rows: list[dict], prefix: str = "") -> str:
    out = ["<table><thead><tr><th>Поле / значение</th><th>Объяснение из схемы</th></tr></thead><tbody>"]
    for row in rows:
        state = row.get("state", "present")
        label = "<b>ОТСУТСТВУЕТ; default схемы, не прочитанное значение</b> " if state != "present" else ""
        description = esc(row.get("description") or ("Описание не задано в схеме" if row.get("documented") else "Нет однозначного описания в подключённой схеме; значение сохранено"))
        units = esc(row.get("units") or "не объявлены")
        default = "<br>Default схемы: " + code(dump(row["default"])) if "default" in row else ""
        out.append(f'<tr id="{anchor(prefix + row["path"])}"><td>{code(row["path"])}<pre>{label}{esc(dump(row["value"]))}</pre></td>'
                   f'<td>{description}<br>Единицы: {units}{default}<small>{esc(row.get("schema", ""))}</small></td></tr>')
    return "".join(out) + "</tbody></table>"


def wire_table(rows: list[dict]) -> str:
    out = ["<table><tr><th>Фактический wire</th><th>Каноническое объяснение</th></tr>"]
    for row in rows:
        notes = []
        for doc in row["documentation"]:
            projection = doc["projection"]
            default_hint = "<br>Default схемы Author (не исходное значение): " + code(dump(doc["default"])) if "default" in doc else ""
            notes.append(f'<p>{code(doc["capability"] + "." + doc["parameter"])}<br>{esc(doc["description"] or "Описание не задано")}'
                         f'<br>Единицы Author: {esc(doc["units"] or "не объявлены")}{default_hint}<small>{esc(doc["schema"])}</small></p>')
            if projection:
                notes.append(raw_details("Правило перевода Author → wire из registry", projection))
        if len(row["documentation"]) > 1:
            notes.insert(0, "<b>Несколько допустимых описаний; исходная capability по этому полю не установлена.</b>")
        out.append(f'<tr><td>{code(row["path"])}<pre>{esc(dump(row["value"]))}</pre></td>'
                   f'<td>{"".join(notes) or "Нет однозначного описания; значение сохранено."}</td></tr>')
    return "".join(out) + "</table>"


def graph_tables(graph: dict, prefix: str = "") -> str:
    out = ["<table><tr><th>Узел</th><th>Тип / управление</th><th>Путь</th></tr>"]
    for node in graph["nodes"]:
        out.append(f'<tr id="{anchor(prefix + node["path"])}"><td>{esc(node["namespace"])}: {code(node["id"])}</td><td>{esc(node["kind"])}</td><td>{code(node["path"])}</td></tr>')
    out.append("</table><table><tr><th>Источник связи</th><th>Назначение</th><th>Основание</th></tr>")
    for edge in graph["edges"]:
        target = esc(edge["to"])
        if len(edge["targetPaths"]) == 1:
            target = f'<a href="#{anchor(prefix + edge["targetPaths"][0])}">{target}</a>'
        out.append(f'<tr><td>{code(edge["from"])}</td><td>{target} ({esc(edge["resolution"])})</td><td>{esc(edge["relation"])}</td></tr>')
    return "".join(out) + "</table>"


def render(report: dict) -> str:
    out = ["<!doctype html><html lang='ru'><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'>",
           "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
           f"<title>{esc(report['name'])} — аудит крафта</title>",
           "<style>body{font:16px/1.5 system-ui,sans-serif;margin:0;overflow-wrap:anywhere;background:#f3f5f8;color:#182339}main{max-width:1120px;margin:auto;padding:32px}"
           "h1{font-size:36px;overflow-wrap:anywhere}h2{margin-top:40px}h3{margin-top:28px}table{table-layout:fixed;border-collapse:collapse;width:100%;background:white;margin:14px 0}"
           "td,th{border:1px solid #d6dce5;text-align:left;padding:12px;vertical-align:top}th{background:#e6edf5}td:first-child{width:45%}"
           "pre,code{font:13px/1.5 ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}pre{margin:8px 0}small{display:block;color:#59677a;overflow-wrap:anywhere}"
           "details{background:white;border:1px solid #d6dce5;padding:12px;margin:12px 0}summary{cursor:pointer;font-weight:600}a{color:#155ca3}"
           ".notice{background:#e4edf8;border-left:4px solid #386fa6;padding:14px}nav{display:flex;flex-wrap:wrap;gap:10px 20px}b{color:#743b08}"
           "@media(max-width:640px){main{padding:16px}body{font-size:14px}td,th{padding:7px}h1{font-size:29px}}</style><main>",
           f"<h1>{esc(report['name'])}</h1><p>Офлайн-аудит сохранённого крафта · вход: {esc(report['lane'])}</p>",
           "<nav><a href='#intent'>Замысел</a><a href='#execution'>Данные</a><a href='#visual'>Внешность</a><a href='#checks'>Проверки</a><a href='#raw'>Источники</a></nav>",
           "<p class='notice'>Это статический отчёт. Значения и описания из схем не являются результатом игрового теста.</p>",
           "<h2 id='intent'>Авторский замысел и пояснения</h2>"]
    if not report["authorAvailable"]:
        out.append("<p><b>Исходный Author JSON отсутствует.</b> Точные исходные значения, пропуски и авторство по wire не восстановлены. Сохранённые concept/realization ниже остаются advisory.</p>")
    highlights = [r for r in report["advisory"] if r["path"] in ("#/concept/coreMechanic", "#/realization/description")]
    for row in highlights:
        out.append(f'<p>{esc(row["value"])}<small>Advisory: {esc(row["path"])}</small></p>')
    out.append("<details><summary>Все сохранённые авторские пояснения и их пути</summary>" + field_table(report["advisory"]) + "</details>")
    out.append("<h2 id='execution'>Управление, сущности, события и эффекты</h2>")
    out.append(graph_tables(report["connections"]))
    if report["authorConnections"]:
        out.append("<details><summary>Связи исходного Author: bindings → entities, calls → targets / effects</summary>" + graph_tables(report["authorConnections"], "source") + "</details>")
    if report["authorAvailable"]:
        out.append("<h3>Выбранные capabilities и их вложенные параметры</h3><p>Числа ниже прочитаны из Author. Отсутствующий default явно отделён от присутствующего значения.</p>")
        calls = lookup((report["sources"].get("author") or report["sources"]["item"])["data"], ("runtimeProgram", "calls"))
        inventory = {row["capability"]: row for row in report["capabilities"]}
        if isinstance(calls, list):
            for i, call in enumerate(calls):
                if not isinstance(call, dict):
                    continue
                out.append(f'<h3>{esc(call.get("id", i))} · {code(call.get("fn"))} → {code(call.get("target", "target не указан"))}</h3>')
                facts = inventory.get(call.get("fn"), {})
                out.append(f'<p>Объявленные emitted events: {code(dump(facts.get("emittedEvents", [])))}. Это возможности capability, не журнал событий.</p>')
                out.append(field_table([r for r in report["authorFields"] if r["parts"][:3] == ["runtimeProgram", "calls", i]], "author"))
        other = [r for r in report["authorFields"] if r["parts"][:2] != ["runtimeProgram", "calls"]
                 and r["parts"][:1] not in (["concept"], ["realization"])]
        out.append(raw_details("Остальные поля Author: значения, пути, неизвестные поля", other))
    out.append("<h3>Сопоставление Author → исполняемый wire</h3><p>Объяснение и единицы относятся к исходному Author-параметру. Wire показан в исходной сериализации после lowering; секундные единицы Author к нему не приписываются.</p>")
    out.append(f'<p>Происхождение сопоставления: {code(report["receiptOrigin"])}. Пересчитанные receipts созданы только в памяти из переданного Author; сохранённый предмет не изменён.</p>')
    if not report["receipts"]:
        out.append("<p>Compiler receipts не переданы. Связи с отсутствующим исходником не восстановлены.</p>")
    out.append("<table><tr><th>Исходный Author</th><th>Фактический wire</th><th>Документация / доверие</th></tr>")
    for link in report["receipts"]:
        av = code(dump(link["authorValue"])) if link["authorValuePresent"] else "Исходное значение отсутствует"
        wv = code(dump(link["wireValue"])) if link["wireValuePresent"] else "Поле отсутствует"
        out.append(f'<tr><td>{code(link["authorPath"])}<br>{av}<br>Единицы Author: {esc(link["authorUnits"] or "не объявлены")}</td>'
                   f'<td>{code(link["wirePath"])}<br>{wv}</td><td>{esc(link["description"] or "Нет однозначного описания")}'
                   f'<small>{esc(link["schema"])}</small><br>receipt #{link["receiptIndex"]}: {esc(link["trust"])}</td></tr>')
    out.append("</table>")
    if report["wireFields"] and not report["authorAvailable"]:
        mechanical = [r for r in report["wireFields"] if r["parts"][:1] in (["runtimeProgram"], ["gameplay"], ["accessory"], ["armor"])
                      and "visual" not in r["parts"]]
        out.append("<h3>Исполняемые значения без исходного Author</h3><p>Объяснения найдены по текущим registry projections. Это сопоставление поля со схемой, а не восстановление исходной композиции. Все числа слева — wire; правила перевода и единицы Author показаны отдельно.</p>" + wire_table(mechanical))
    if report["wireFields"]:
        out.append(raw_details("Все поля сохранённого wire, включая неизвестные и не сопоставленные", report["wireFields"]))
    if report["unknownFields"]:
        out.append("<h3>Неизвестные поля и поля без документации</h3><p>Они сохранены дословно; наличие в этом списке само по себе не определяет валидность.</p>" + field_table(report["unknownFields"], "unknown"))
    out.append("<h2 id='visual'>Визуальная часть отдельно</h2><p>Прочитанные Visual/VFX задания и сохранённые настройки. Изображения и URL не загружаются; внешний вид не оценён.</p>")
    for doc in report["visualSources"]:
        out.append(f'<h3>{esc(doc["source"])}</h3>' + field_table(doc["rows"], doc["source"]))
    out.append(raw_details("Сохранённые visual / vfxManifest", report["storedVisualFields"]))
    out.append("<h2 id='checks'>Результаты проверок и границы</h2>")
    for result in report["checks"]:
        out.append(raw_details(f'{result["name"]}: {result["status"]}', result))
    out.append("<h3>Предоставленные внешние результаты</h3><p>Не перезапускались и не удостоверяют этот предмет автоматически.</p>")
    for doc in report["evidence"]:
        out.append(raw_details(f'{doc["file"]} · SHA256 {doc["sha256"]}', doc["data"]))
    out.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in report["boundaries"]) + "</ul>")
    out.append("<h2 id='raw'>Источники и воспроизводимость</h2>")
    for label, doc in report["sources"].items():
        out.append(raw_details(f'{label}: {doc["file"]} · SHA256 {doc["sha256"]}', doc["data"]))
    out.append(raw_details("Канонические схемы: файлы и SHA256", report["schemas"]))
    out.append(raw_details("Производитель отчёта и код владельцев introspection: SHA256", report["codeOwners"]))
    return "".join(out) + "</main></html>\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item", type=Path, required=True, help="Saved item wire or complete Author JSON")
    parser.add_argument("--author-source", type=Path)
    parser.add_argument("--visual-source", type=Path)
    parser.add_argument("--vfx-source", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[], help="Stored external report, repeatable; never treated as a fresh check")
    parser.add_argument("--out", type=Path, required=True, help="New output directory (never overwrites inputs or reports)")
    args = parser.parse_args(argv)
    try:
        docs = [read_document(path) if path else None for path in
                (args.item, args.author_source, args.visual_source, args.vfx_source)]
        evidence = [read_document(path) for path in args.evidence]
        report = build_report(*docs, evidence=evidence)
        page = render(report)
        encoded = dump(report) + "\n"
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "audit.json").write_text(encoded, encoding="utf-8")
        (args.out / "audit.html").write_text(page, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Audit error: {exc}\n")
    print(args.out / "audit.html")
    # A failed static validation still produces a usable diagnostic report.
    return 1 if any(c["status"] == "failed" for c in report["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
