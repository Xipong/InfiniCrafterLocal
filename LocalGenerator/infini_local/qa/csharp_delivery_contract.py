from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping


# AGENT MAP: source-derived Python -> strict C# JSON delivery contract.
# This module reads the real DTO auto-properties and validates already-sanitized
# payloads. It does not author, normalize, migrate, or infer gameplay fields.


_CLASS_RE = re.compile(
    r"\bpublic\s+(?:(?:sealed|partial|abstract|static)\s+)*class\s+(?P<name>[A-Za-z_]\w*)\b"
)
_ENUM_RE = re.compile(
    r"\bpublic\s+(?:(?:sealed|partial)\s+)*enum\s+(?P<name>[A-Za-z_]\w*)\b"
)
_PROPERTY_RE = re.compile(
    r"(?P<attributes>(?:\[[^\]]+\]\s*)*)"
    r"(?P<public>public)\s+"
    r"(?:(?:required|virtual|override|new)\s+)*"
    r"(?P<type>[A-Za-z_][A-Za-z0-9_.<>,?\[\]\s]*)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*"
    r"\{\s*get\s*;\s*(?:set|init)\s*;\s*\}",
    re.MULTILINE,
)
_JSON_PROPERTY_NAME_RE = re.compile(r'JsonPropertyName\s*\(\s*"([^"]+)"\s*\)')

_INTEGER_TYPES = frozenset({
    "byte", "sbyte", "short", "ushort", "int", "uint", "long", "ulong",
    "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64",
})
_NUMBER_TYPES = frozenset({
    "float", "double", "decimal", "Half", "Single", "Double", "Decimal",
})
_LIST_TYPES = frozenset({
    "List", "IList", "IReadOnlyList", "ICollection", "IReadOnlyCollection", "IEnumerable",
})
_DICTIONARY_TYPES = frozenset({"Dictionary", "IDictionary", "IReadOnlyDictionary"})
_ANY_TYPES = frozenset({"object", "JsonElement", "JsonNode", "JsonObject", "JsonArray"})

_INTEGER_RANGES: dict[str, tuple[int, int]] = {
    "byte": (0, 255),
    "sbyte": (-128, 127),
    "short": (-32768, 32767),
    "Int16": (-32768, 32767),
    "ushort": (0, 65535),
    "UInt16": (0, 65535),
    "int": (-2147483648, 2147483647),
    "Int32": (-2147483648, 2147483647),
    "uint": (0, 4294967295),
    "UInt32": (0, 4294967295),
    "long": (-9223372036854775808, 9223372036854775807),
    "Int64": (-9223372036854775808, 9223372036854775807),
    "ulong": (0, 18446744073709551615),
    "UInt64": (0, 18446744073709551615),
}
_NUMBER_MAGNITUDES: dict[str, float] = {
    "Half": 65504.0,
    "float": 3.4028234663852886e38,
    "Single": 3.4028234663852886e38,
    "double": 1.7976931348623157e308,
    "Double": 1.7976931348623157e308,
    "decimal": 7.922816251426433e28,
    "Decimal": 7.922816251426433e28,
}


@dataclass(frozen=True)
class CSharpPropertyContract:
    csharp_name: str
    json_name: str
    type_name: str
    source_path: str
    source_line: int


@dataclass
class CSharpClassContract:
    name: str
    properties: dict[str, CSharpPropertyContract] = field(default_factory=dict)
    extension_data: bool = False
    source_paths: set[str] = field(default_factory=set)

    def property_for_json_name(self, name: str) -> CSharpPropertyContract | None:
        return self.properties.get(name.casefold())

    def json_fields(self) -> frozenset[str]:
        return frozenset(prop.json_name for prop in self.properties.values())


@dataclass(frozen=True)
class CSharpContractGraph:
    classes: Mapping[str, CSharpClassContract]
    enums: frozenset[str]
    source_paths: tuple[str, ...]

    def class_contract(self, name: str) -> CSharpClassContract | None:
        return self.classes.get(_simple_type_name(name))

    def json_fields(self, class_name: str) -> frozenset[str]:
        contract = self.class_contract(class_name)
        if contract is None:
            raise KeyError(f"C# DTO class not found: {class_name}")
        return contract.json_fields()

    def validate(self, payload: Any, *, root_type: str = "GeneratedItemData") -> list[str]:
        errors: list[str] = []
        _validate_value(payload, root_type, "$", self, errors)
        return errors

    def reachable_summary(self, *, root_type: str = "GeneratedItemData") -> dict[str, Any]:
        visited: set[str] = set()
        unresolved: list[str] = []

        def visit_type(type_name: str, owner_path: str) -> None:
            normalized = _normalize_type(type_name)
            if normalized.endswith("?"):
                normalized = normalized[:-1]
            if normalized.endswith("[]"):
                visit_type(normalized[:-2], owner_path + "[]")
                return
            generic = _split_generic(normalized)
            if generic is not None:
                base, args = generic
                if base == "Nullable" and len(args) == 1:
                    visit_type(args[0], owner_path)
                    return
                if base in _LIST_TYPES and len(args) == 1:
                    visit_type(args[0], owner_path + "[]")
                    return
                if base in _DICTIONARY_TYPES and len(args) == 2:
                    if _simple_type_name(args[0].rstrip("?")) not in {"string", "String"}:
                        unresolved.append(f"{owner_path}: unsupported dictionary key type {args[0]}")
                    visit_type(args[1], owner_path + "{}")
                    return

            simple = _simple_type_name(normalized)
            if simple in _ANY_TYPES or simple in _INTEGER_TYPES or simple in _NUMBER_TYPES:
                return
            if simple in {"string", "String", "char", "Char", "bool", "Boolean"} or simple in self.enums:
                return
            contract = self.class_contract(simple)
            if contract is None:
                unresolved.append(f"{owner_path}: unresolved C# contract type {normalized}")
                return
            if contract.name in visited:
                return
            visited.add(contract.name)
            for prop in contract.properties.values():
                visit_type(prop.type_name, f"{contract.name}.{prop.json_name}")

        visit_type(root_type, root_type)
        return {
            "rootType": root_type,
            "classNames": sorted(visited),
            "classCount": len(visited),
            "propertyCount": sum(len(self.classes[name].properties) for name in visited),
            "unresolvedTypes": sorted(set(unresolved)),
        }


class CSharpContractParseError(RuntimeError):
    """Raised when the source DTO graph cannot be extracted unambiguously."""


def default_csharp_models_root() -> Path:
    return Path(__file__).resolve().parents[3] / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models"


def load_csharp_contract_graph(source_root: Path | None = None) -> CSharpContractGraph:
    root = (source_root or default_csharp_models_root()).resolve()
    paths = sorted(path for path in root.rglob("*.cs") if path.is_file())
    if not paths:
        raise CSharpContractParseError(f"no C# sources found under {root}")

    classes: dict[str, CSharpClassContract] = {}
    enums: set[str] = set()
    for path in paths:
        source = path.read_text(encoding="utf-8-sig")
        masked = _mask_non_code(source)
        brace_pairs, depth_before = _brace_index(masked, path)
        enums.update(match.group("name") for match in _ENUM_RE.finditer(masked))
        for class_match in _CLASS_RE.finditer(masked):
            class_name = class_match.group("name")
            open_brace = masked.find("{", class_match.end())
            if open_brace < 0 or open_brace not in brace_pairs:
                raise CSharpContractParseError(f"unbalanced class {class_name} in {path}")
            close_brace = brace_pairs[open_brace]
            class_depth = depth_before[open_brace]
            body = source[open_brace + 1 : close_brace]
            body_offset = open_brace + 1
            contract = classes.setdefault(class_name, CSharpClassContract(name=class_name))
            contract.source_paths.add(path.relative_to(root).as_posix())

            for property_match in _PROPERTY_RE.finditer(body):
                public_index = body_offset + property_match.start("public")
                # Keep the original body for JsonPropertyName attributes, but
                # reject declarations whose `public` token is masked as a
                # comment or string literal.
                if masked[public_index : public_index + len("public")] != "public":
                    continue
                if depth_before[public_index] != class_depth + 1:
                    # Do not accidentally attach properties from a nested class to
                    # the containing partial DTO (GeneratedItemData has one).
                    continue
                attributes = property_match.group("attributes") or ""
                if "JsonIgnore" in attributes:
                    continue
                is_extension_data = "JsonExtensionData" in attributes
                if is_extension_data:
                    contract.extension_data = True
                    continue

                csharp_name = property_match.group("name")
                type_name = _normalize_type(property_match.group("type"))
                name_match = _JSON_PROPERTY_NAME_RE.search(attributes)
                json_name = name_match.group(1) if name_match else _lower_camel(csharp_name)
                line = source.count("\n", 0, public_index) + 1
                prop = CSharpPropertyContract(
                    csharp_name=csharp_name,
                    json_name=json_name,
                    type_name=type_name,
                    source_path=path.relative_to(root).as_posix(),
                    source_line=line,
                )
                key = json_name.casefold()
                previous = contract.properties.get(key)
                if previous is not None and (
                    previous.csharp_name != prop.csharp_name or previous.type_name != prop.type_name
                ):
                    raise CSharpContractParseError(
                        f"conflicting JSON property {class_name}.{json_name}: "
                        f"{previous.type_name} at {previous.source_path}:{previous.source_line} vs "
                        f"{prop.type_name} at {prop.source_path}:{prop.source_line}"
                    )
                contract.properties[key] = prop

    if "GeneratedItemData" not in classes:
        raise CSharpContractParseError(f"GeneratedItemData was not found under {root}")
    return CSharpContractGraph(
        classes=classes,
        enums=frozenset(enums),
        source_paths=tuple(path.relative_to(root).as_posix() for path in paths),
    )


def validate_generated_item_delivery(
    payload: Any,
    *,
    graph: CSharpContractGraph | None = None,
    source_root: Path | None = None,
) -> list[str]:
    contract_graph = graph or load_csharp_contract_graph(source_root)
    return contract_graph.validate(payload, root_type="GeneratedItemData")


def _mask_non_code(source: str) -> str:
    """Mask comments and literals while preserving offsets/newlines for brace parsing."""
    chars = list(source)
    out = [" "] * len(chars)
    index = 0
    state = "code"
    while index < len(chars):
        char = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if char in "\r\n":
            out[index] = char
            if state == "line_comment":
                state = "code"
            index += 1
            continue
        if state == "line_comment":
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                index += 2
                state = "code"
            else:
                index += 1
            continue
        if state == "regular_string":
            if char == "\\":
                index += 2
            elif char == '"':
                index += 1
                state = "code"
            else:
                index += 1
            continue
        if state == "verbatim_string":
            if char == '"' and nxt == '"':
                index += 2
            elif char == '"':
                index += 1
                state = "code"
            else:
                index += 1
            continue
        if state == "char":
            if char == "\\":
                index += 2
            elif char == "'":
                index += 1
                state = "code"
            else:
                index += 1
            continue

        if char == "/" and nxt == "/":
            index += 2
            state = "line_comment"
        elif char == "/" and nxt == "*":
            index += 2
            state = "block_comment"
        elif source.startswith('$@"', index) or source.startswith('@$"', index):
            index += 3
            state = "verbatim_string"
        elif source.startswith('@"', index):
            index += 2
            state = "verbatim_string"
        elif source.startswith('$"', index):
            index += 2
            state = "regular_string"
        elif char == '"':
            index += 1
            state = "regular_string"
        elif char == "'":
            index += 1
            state = "char"
        else:
            out[index] = char
            index += 1
    return "".join(out)


def _brace_index(masked: str, path: Path) -> tuple[dict[int, int], list[int]]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    depth_before = [0] * (len(masked) + 1)
    depth = 0
    for index, char in enumerate(masked):
        depth_before[index] = depth
        if char == "{":
            stack.append(index)
            depth += 1
        elif char == "}":
            if not stack:
                raise CSharpContractParseError(f"unexpected closing brace in {path}:{masked.count(chr(10), 0, index) + 1}")
            open_brace = stack.pop()
            depth -= 1
            pairs[open_brace] = index
    depth_before[len(masked)] = depth
    if stack:
        first = stack[-1]
        raise CSharpContractParseError(f"unclosed brace in {path}:{masked.count(chr(10), 0, first) + 1}")
    return pairs, depth_before


def _normalize_type(type_name: str) -> str:
    value = re.sub(r"\s+", "", type_name)
    return value.replace("global::", "")


def _lower_camel(name: str) -> str:
    return name[:1].lower() + name[1:] if name else name


def _simple_type_name(type_name: str) -> str:
    value = type_name.strip()
    return value.rsplit(".", 1)[-1]


def _split_generic(type_name: str) -> tuple[str, list[str]] | None:
    lt = type_name.find("<")
    if lt < 0 or not type_name.endswith(">"):
        return None
    base = type_name[:lt]
    body = type_name[lt + 1 : -1]
    args: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(body):
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(body[start:index])
            start = index + 1
    args.append(body[start:])
    return _simple_type_name(base), [arg for arg in args if arg]


def _allows_null(type_name: str, graph: CSharpContractGraph) -> bool:
    if type_name.endswith("?"):
        return True
    if type_name.endswith("[]"):
        return True
    generic = _split_generic(type_name)
    if generic is not None:
        base, _ = generic
        return base in _LIST_TYPES or base in _DICTIONARY_TYPES
    simple = _simple_type_name(type_name)
    return simple == "string" or simple in _ANY_TYPES or graph.class_contract(simple) is not None


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _append_kind_error(errors: list[str], path: str, expected: str, value: Any) -> None:
    errors.append(f"{path}: expected {expected}, got {_json_kind(value)}")


def _child_path(path: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_]\w*", key):
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _validate_value(
    value: Any,
    type_name: str,
    path: str,
    graph: CSharpContractGraph,
    errors: list[str],
) -> None:
    normalized = _normalize_type(type_name)
    if value is None:
        if not _allows_null(normalized, graph):
            _append_kind_error(errors, path, _expected_kind(normalized, graph), value)
        return

    if normalized.endswith("?"):
        normalized = normalized[:-1]

    if normalized.endswith("[]"):
        if not isinstance(value, list):
            _append_kind_error(errors, path, "array", value)
            return
        element_type = normalized[:-2]
        for index, item in enumerate(value):
            _validate_value(item, element_type, f"{path}[{index}]", graph, errors)
        return

    generic = _split_generic(normalized)
    if generic is not None:
        base, args = generic
        if base == "Nullable" and len(args) == 1:
            _validate_value(value, args[0], path, graph, errors)
            return
        if base in _LIST_TYPES and len(args) == 1:
            if not isinstance(value, list):
                _append_kind_error(errors, path, "array", value)
                return
            for index, item in enumerate(value):
                _validate_value(item, args[0], f"{path}[{index}]", graph, errors)
            return
        if base in _DICTIONARY_TYPES and len(args) == 2:
            if not isinstance(value, dict):
                _append_kind_error(errors, path, "object", value)
                return
            key_type = _simple_type_name(args[0].rstrip("?"))
            if key_type not in {"string", "String"}:
                errors.append(f"{path}: unsupported C# JSON dictionary key type {args[0]}")
                return
            for key, item in value.items():
                if not isinstance(key, str):
                    errors.append(f"{path}: expected string dictionary key, got {type(key).__name__}")
                    continue
                _validate_value(item, args[1], _child_path(path, key), graph, errors)
            return

    simple = _simple_type_name(normalized)
    if simple in _ANY_TYPES:
        _validate_any_json(value, path, errors)
        return
    if simple in {"string", "String", "char", "Char"}:
        if not isinstance(value, str):
            _append_kind_error(errors, path, "string", value)
        return
    if simple in {"bool", "Boolean"}:
        if not isinstance(value, bool):
            _append_kind_error(errors, path, "boolean", value)
        return
    if simple in _INTEGER_TYPES or simple in graph.enums:
        if not isinstance(value, int) or isinstance(value, bool):
            _append_kind_error(errors, path, "integer", value)
            return
        minimum, maximum = _INTEGER_RANGES.get(simple, _INTEGER_RANGES["int"])
        if value < minimum or value > maximum:
            errors.append(
                f"{path}: integer {value} out of range for {simple} [{minimum}, {maximum}]"
            )
        return
    if simple in _NUMBER_TYPES:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            _append_kind_error(errors, path, "number", value)
            return
        try:
            numeric = float(value)
        except (OverflowError, ValueError):
            errors.append(f"{path}: number {value!r} out of range for {simple}")
            return
        if not math.isfinite(numeric):
            errors.append(f"{path}: non-finite number {numeric} is invalid for {simple}")
            return
        magnitude = _NUMBER_MAGNITUDES.get(simple)
        if magnitude is not None and abs(numeric) > magnitude:
            errors.append(
                f"{path}: number {numeric} out of range for {simple} [{-magnitude}, {magnitude}]"
            )
        return

    contract = graph.class_contract(simple)
    if contract is None:
        errors.append(f"{path}: unresolved C# contract type {normalized}")
        return
    if not isinstance(value, dict):
        _append_kind_error(errors, path, "object", value)
        return
    supplied_properties: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            errors.append(f"{path}: expected string object key, got {type(key).__name__}")
            continue
        prop = contract.property_for_json_name(key)
        child_path = _child_path(path, key)
        if prop is None:
            if not contract.extension_data:
                errors.append(f"{child_path}: unknown field for {contract.name}")
            else:
                _validate_any_json(item, child_path, errors)
            continue
        property_key = prop.json_name.casefold()
        previous_key = supplied_properties.get(property_key)
        if previous_key is not None:
            errors.append(
                f"{child_path}: duplicate field for {contract.name}.{prop.json_name} "
                f"(already supplied as {_child_path(path, previous_key)})"
            )
            continue
        supplied_properties[property_key] = key
        _validate_value(item, prop.type_name, child_path, graph, errors)


def _validate_any_json(value: Any, path: str, errors: list[str]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            errors.append(f"{path}: non-finite number {value} is not valid JSON")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_any_json(item, f"{path}[{index}]", errors)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                errors.append(f"{path}: expected string object key, got {type(key).__name__}")
                continue
            _validate_any_json(item, _child_path(path, key), errors)
        return
    errors.append(f"{path}: expected any JSON value, got {_json_kind(value)}")


def _expected_kind(type_name: str, graph: CSharpContractGraph) -> str:
    normalized = type_name.rstrip("?")
    if normalized.endswith("[]"):
        return "array"
    generic = _split_generic(normalized)
    if generic is not None:
        base, _ = generic
        if base in _LIST_TYPES:
            return "array"
        if base in _DICTIONARY_TYPES:
            return "object"
    simple = _simple_type_name(normalized)
    if simple in {"string", "String", "char", "Char"}:
        return "string"
    if simple in {"bool", "Boolean"}:
        return "boolean"
    if simple in _INTEGER_TYPES or simple in graph.enums:
        return "integer"
    if simple in _NUMBER_TYPES:
        return "number"
    if simple in _ANY_TYPES:
        return "any JSON value"
    if graph.class_contract(simple) is not None:
        return "object"
    return normalized


__all__ = [
    "CSharpClassContract",
    "CSharpContractGraph",
    "CSharpContractParseError",
    "CSharpPropertyContract",
    "default_csharp_models_root",
    "load_csharp_contract_graph",
    "validate_generated_item_delivery",
]
