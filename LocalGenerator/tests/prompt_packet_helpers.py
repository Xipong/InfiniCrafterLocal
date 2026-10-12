"""Read the derived dossier view in semantic tests; authority tests inspect rows."""
import json


def dossier_text(request, *, declaration=None):
    source = declaration if declaration is not None else request
    if declaration is not None:
        assert request["messages"] == declaration["messages"]
    marker = source.get("_infini_prompt_cache")
    if isinstance(marker, dict) and "instructionMessageIndex" in marker:
        from infini_local.core.llm_prompt_cache import instruction_segment_index
        index = instruction_segment_index(source)
        assert index is not None
        rows = request["messages"][index:index + 2]
        if "staticDataMessageIndex" in marker:
            static, definitions, dynamic = [json.loads(row["content"]) for row in request["messages"][index:index + 3]]
            assert [row["role"] for row in request["messages"][index:index + 3]] == ["developer", "user", "user"]
            assert static["rules"].pop().startswith("The output schema's #/$defs/ references resolve against the preceding USER schemaDefinitions.$defs;")
            def inline(node):
                if isinstance(node, dict):
                    if set(node) == {"$ref"} and node["$ref"].startswith("#/$defs/"):
                        return inline(definitions["schemaDefinitions"]["$defs"][node["$ref"][len("#/$defs/"):]])
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
