#!/usr/bin/env python3
"""Generate a machine-readable registry from actual environment accesses.

The registry is evidence, not a writable configuration authority.  Types,
defaults and bounds are extracted from env_* calls; GUI/config-example presence
is merged as presentation metadata.  New runtime knobs therefore appear by
changing their real owner, not by teaching this checker each field manually.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "LocalGenerator"
OUT = ROOT / "contracts" / "config_registry.json"
NAME_RE = re.compile(r"\bINFINI_[A-Z0-9_]+\b")
CSHARP_ENV_RE = re.compile(r"(?:System\.)?Environment\.GetEnvironmentVariable\(\s*\"(INFINI_[A-Z0-9_]+)\"")
EXAMPLE_RE = re.compile(r"^\s*#?\s*(INFINI_[A-Z0-9_]+)\s*=\s*(.*)$")
SECRET_PARTS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
ENV_FUNCTIONS = {
    "env_str": "string",
    "env_bool": "boolean",
    "env_int": "integer",
    "env_float": "number",
    "env_path": "path",
}


@dataclass(frozen=True)
class Declaration:
    name: str
    type_name: str
    default: Any
    minimum: Any
    maximum: Any
    file: str
    line: int


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _literal(node: ast.AST | None, source: str) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        segment = ast.get_source_segment(source, node)
        return {"expression": segment or ast.dump(node, include_attributes=False)}


def _python_sources() -> list[Path]:
    roots = [LOCAL / "infini_local", ROOT / "tools"]
    direct = [LOCAL / "server.py", LOCAL / "settings_gui.py"]
    rows = [path for root in roots for path in root.rglob("*.py")]
    rows.extend(path for path in direct if path.exists())
    return sorted({p for p in rows if "__pycache__" not in p.parts})


def _extract_python() -> tuple[list[Declaration], dict[str, set[str]]]:
    declarations: list[Declaration] = []
    references: dict[str, set[str]] = defaultdict(set)
    for path in _python_sources():
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        rel = _rel(path)
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        constants: dict[str, Any] = {}
        for top in tree.body:
            if isinstance(top, ast.Assign) and len(top.targets) == 1 and isinstance(top.targets[0], ast.Name):
                try:
                    constants[top.targets[0].id] = ast.literal_eval(top.value)
                except Exception:
                    pass

        def resolved(node: ast.AST | None) -> Any:
            if isinstance(node, ast.Name) and node.id in constants:
                return constants[node.id]
            return _literal(node, source)

        for node in ast.walk(tree):
            env_name: Any = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if isinstance(owner, ast.Name) and owner.id == "os" and node.func.attr == "getenv" and node.args:
                    env_name = resolved(node.args[0])
                elif (
                    isinstance(owner, ast.Attribute)
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "os"
                    and owner.attr == "environ"
                    and node.func.attr in {"get", "pop", "setdefault"}
                    and node.args
                ):
                    env_name = resolved(node.args[0])
                elif (
                    isinstance(owner, ast.Attribute)
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "os"
                    and owner.attr == "environ"
                    and node.func.attr == "update"
                    and node.args
                    and isinstance(node.args[0], ast.Dict)
                ):
                    for key in node.args[0].keys:
                        value = resolved(key)
                        if isinstance(value, str) and value.startswith("INFINI_"):
                            references[value].add(rel)
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "os"
                and node.value.attr == "environ"
            ):
                env_name = resolved(node.slice)
            if isinstance(env_name, str) and env_name.startswith("INFINI_"):
                references[env_name].add(rel)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if fn in {"env_first", "env_first_allow_empty"} and node.args:
                names = resolved(node.args[0])
                default = resolved(node.args[1]) if len(node.args) > 1 else ""
                if isinstance(names, (list, tuple)):
                    for env_name in names:
                        if isinstance(env_name, str) and env_name.startswith("INFINI_"):
                            declarations.append(Declaration(env_name, "string", default, None, None, rel, int(getattr(node, "lineno", 0))))
                            references[env_name].add(rel)
                continue
            if fn not in ENV_FUNCTIONS or not node.args:
                continue
            env_name = resolved(node.args[0])
            if not isinstance(env_name, str) or not env_name.startswith("INFINI_"):
                continue
            default_node = node.args[1] if len(node.args) > 1 else None
            kw = {item.arg: item.value for item in node.keywords if item.arg}
            declarations.append(
                Declaration(
                    name=env_name,
                    type_name=ENV_FUNCTIONS[fn],
                    default=resolved(default_node),
                    minimum=resolved(kw.get("lo")),
                    maximum=resolved(kw.get("hi")),
                    file=rel,
                    line=int(getattr(node, "lineno", 0)),
                )
            )
            references[env_name].add(rel)
    return declarations, references


def _extract_csharp_refs(references: dict[str, set[str]]) -> None:
    for path in (ROOT / "ModSources").rglob("*.cs"):
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        for name in CSHARP_ENV_RE.findall(source):
            references[name].add(_rel(path))


def _example_fields() -> dict[str, dict[str, Any]]:
    path = LOCAL / "config.example.env"
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    section = ""
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("#") and "=" not in stripped:
            label = stripped.lstrip("# ").strip()
            if label and len(label) < 100:
                section = label
        match = EXAMPLE_RE.match(raw)
        if not match:
            continue
        name, value = match.groups()
        rows.setdefault(name, {"default": value.strip(), "line": line_no, "section": section})
    return rows


def _gui_fields() -> tuple[list[str], dict[str, Any]]:
    # Parse rather than import so generation never executes GUI/runtime module code.
    path = LOCAL / "infini_local" / "desktop" / "settings_schema.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=_rel(path))
    values: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {"FIELD_ORDER", "DEFAULTS"}:
                try:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
                except Exception:
                    # DEFAULTS contains platform/path expressions; individual literal
                    # values are optional because source env calls remain canonical.
                    pass
    raw_field_order = values.get("FIELD_ORDER")
    field_order: list[Any] = raw_field_order if isinstance(raw_field_order, list) else []
    raw_defaults = values.get("DEFAULTS")
    defaults: dict[Any, Any] = raw_defaults if isinstance(raw_defaults, dict) else {}
    # FIELD_ORDER is fully literal even when DEFAULTS is not.
    if not field_order:
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "FIELD_ORDER":
                field_order = ast.literal_eval(node.value)
    return [str(x) for x in field_order], {str(k): v for k, v in defaults.items()}


def _fingerprint(entries: list[dict[str, Any]]) -> str:
    raw = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_registry() -> dict[str, Any]:
    declarations, references = _extract_python()
    _extract_csharp_refs(references)
    examples = _example_fields()
    gui_order, gui_defaults = _gui_fields()
    by_name: dict[str, list[Declaration]] = defaultdict(list)
    for row in declarations:
        by_name[row.name].append(row)

    names = sorted((set(references) | set(by_name) | set(examples) | set(gui_order)) - {"INFINI_ENV_MISSING__"})
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for name in names:
        decls = by_name.get(name, [])
        types = sorted({row.type_name for row in decls})
        if len(types) > 1:
            errors.append({"field": name, "kind": "type_conflict", "values": types})
        source_defaults = []
        for row in decls:
            if row.default not in source_defaults:
                source_defaults.append(row.default)
        literal_defaults = [value for value in source_defaults if not isinstance(value, dict)]
        if len({json.dumps(x, sort_keys=True, default=str) for x in literal_defaults}) > 1:
            warnings.append({"field": name, "kind": "context_default_drift", "values": literal_defaults})
        minima = [row.minimum for row in decls if row.minimum is not None]
        maxima = [row.maximum for row in decls if row.maximum is not None]
        secret = any(part in name for part in SECRET_PARTS)
        default = source_defaults[0] if len(source_defaults) == 1 else source_defaults
        if not decls and name in gui_defaults:
            default = gui_defaults[name]
        if secret and default not in (None, "", []):
            default = "<redacted>"
        entry = {
            "name": name,
            "type": types[0] if len(types) == 1 else "unknown" if not types else "conflict",
            "default": default,
            "minimum": minima[0] if len({json.dumps(x, sort_keys=True, default=str) for x in minima}) == 1 and minima else None,
            "maximum": maxima[0] if len({json.dumps(x, sort_keys=True, default=str) for x in maxima}) == 1 and maxima else None,
            "secret": secret,
            "visibility": "gui" if name in gui_order else "documented" if name in examples else "internal",
            "documented": name in examples,
            "gui": name in gui_order,
            "example": None if secret else examples.get(name, {}).get("default"),
            "owners": sorted(references.get(name, set())),
            "declarations": [
                {
                    "file": row.file,
                    "type": row.type_name,
                    "default": "<redacted>" if secret and row.default not in (None, "") else row.default,
                    "minimum": row.minimum,
                    "maximum": row.maximum,
                }
                for row in decls
            ],
        }
        if entry["visibility"] != "internal" and not decls:
            warnings.append({"field": name, "kind": "presented_without_env_helper_declaration"})
        entries.append(entry)

    return {
        "schema": "infini.config-registry.v1",
        "generatedFrom": [
            "env_* calls in LocalGenerator/infini_local and tools",
            "LocalGenerator/infini_local/desktop/settings_schema.py",
            "LocalGenerator/config.example.env",
            "C# INFINI_* references",
        ],
        "authority": "derived-evidence-only",
        "fieldCount": len(entries),
        "guiFieldCount": sum(bool(row["gui"]) for row in entries),
        "documentedFieldCount": sum(bool(row["documented"]) for row in entries),
        "secretFieldCount": sum(bool(row["secret"]) for row in entries),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "entries": entries,
        "fingerprint": _fingerprint(entries),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_registry()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.out.exists() or args.out.read_text(encoding="utf-8") != text:
            print(json.dumps({"ok": False, "error": "config registry is stale", "path": str(args.out)}, ensure_ascii=False))
            return 1
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if args.json or not args.check:
        print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
