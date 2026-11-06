"""Read the derived dossier view in semantic tests; authority tests inspect rows."""
import copy
import json
import re
from typing import Any


def dossier_text(request, *, declaration=None):
    source = declaration if declaration is not None else request
    marker = source.get("_infini_prompt_cache")
    if isinstance(marker, dict) and "instructionMessageIndex" in marker:
        from infini_local.core.llm_prompt_cache import instruction_segment_index
        index = instruction_segment_index(source)
        assert index is not None
        if declaration is not None and request["messages"] != declaration["messages"]:
            original = declaration["messages"]
            prefix = original[:index + 1]
            merged = {"role": "system", "content": "\n\n".join(
                row["content"] if row["role"] == "system" else "Developer instructions:\n" + row["content"]
                for row in prefix
            )}
            if "name" in prefix[0]:
                merged["name"] = prefix[0]["name"]
            assert request["messages"] == [merged, *original[index + 1:]]
        rows = source["messages"][index:index + 2]
        static, dynamic = [json.loads(row["content"]) for row in rows]
        if "schemaDefinitions" in static:
            definitions = static.pop("schemaDefinitions")
            assert [row["role"] for row in rows] == ["developer", "user"]
            assert static["rules"].pop().startswith("The output schema's #/$defs/ references resolve against DEVELOPER schemaDefinitions.$defs;")
            def inline(node):
                if isinstance(node, dict):
                    if set(node) == {"$ref"} and node["$ref"].startswith("#/$defs/"):
                        return inline(definitions["$defs"][node["$ref"][len("#/$defs/"):]])
                    return {key: inline(value) for key, value in node.items()}
                if isinstance(node, list):
                    return [inline(value) for value in node]
                return node
            dynamic = inline(dynamic)
            assert not static.keys() & dynamic.keys()
            return json.dumps({**static, **dynamic}, ensure_ascii=False, separators=(",", ":"))
        assert [row["role"] for row in rows] == ["developer", "user"]
        static, dynamic = [row["content"] for row in rows]
        assert not json.loads(static).keys() & json.loads(dynamic).keys()
        return static[:-1] + "," + dynamic[1:]
    if declaration is not None:
        assert request["messages"] == declaration["messages"]
    return request["messages"][1]["content"]


def request_dossier(request, *, declaration=None):
    dossier = json.loads(dossier_text(request, declaration=declaration))
    # Canonical Visual framing separates invariant presentation instructions
    # from the runtime-selected bake roster. Semantic observers retain the
    # original nested view; authority tests inspect the actual message rows.
    if "bakeFillByProcessingRole" in dossier:
        assert "bakeFillByProcessingRole" not in dossier["spritePresentationReadOnly"]
        dossier["spritePresentationReadOnly"]["bakeFillByProcessingRole"] = dossier.pop("bakeFillByProcessingRole")
    return dossier


def expand_catalog_targets(cards: list[dict[str, Any]], target_sets: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Resolve model-only shared kind lists before comparing to the registry."""
    result = copy.deepcopy(cards)
    for card in result:
        if "targetsRef" in card:
            assert "targets" not in card
            card["targets"] = copy.deepcopy(target_sets[card.pop("targetsRef")])
    return result


def expand_native_source_references(dossier: dict[str, Any]) -> dict[str, Any]:
    """Independent lossless check; request_dossier deliberately stays literal."""
    def expand(value: Any, active: tuple[int, ...] = ()) -> Any:
        if isinstance(value, dict):
            if set(value) == {"sourceSameAs"}:
                index = value["sourceSameAs"]
                assert type(index) is int and 0 <= index < len(dossier["nativeSourceFacts"])
                assert index not in active, "cyclic native source reference"
                return expand(dossier["nativeSourceFacts"][index], (*active, index))
            return {key: expand(child, active) for key, child in value.items()}
        if isinstance(value, list):
            return [expand(child, active) for child in value]
        return copy.deepcopy(value)
    return expand(dossier)


def expand_native_identifier_aliases(value: Any) -> Any:
    """Independent observer for marked, already table-decoded source programs."""
    aliases = {"P": "Projectile", "E": "Entity", "Vec": "Vector2"}

    def names(text: str) -> str:
        def token(match):
            atom = match[0]
            return atom if atom.startswith('"') else '.'.join(aliases.get(part, part) for part in atom.split('.'))
        return re.sub(r'"(?:\\.|[^"\\])*"|(?<![A-Za-z0-9_#`])[A-Za-z_][A-Za-z0-9_@.#`]*', token, text)

    def expand(node):
        if isinstance(node, list):
            return [expand(child) for child in node]
        if not isinstance(node, dict):
            return copy.deepcopy(node)
        result = {key: expand(child) for key, child in node.items()}
        if type(result.get('nativeNames')) is not int or result['nativeNames'] != 1:
            return result
        result.pop('nativeNames')
        if isinstance(result.get('method'), str):
            result['method'] = names(result['method'])
        if isinstance(result.get('symbols'), dict):
            result['symbols'] = {names(key): names(child) for key, child in result['symbols'].items()}
        for row in result.get('operations', []):
            for key in ('expression', 'receiver', 'call'):
                if isinstance(row.get(key), str):
                    row[key] = names(row[key])
            if isinstance(row.get('arguments'), dict):
                row['arguments'] = {key: names(child) for key, child in row['arguments'].items()}
            if isinstance(row.get('inputs'), list):
                row['inputs'] = [names(child) for child in row['inputs']]
        return result

    return expand(value)
