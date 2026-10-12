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
        rows = request["messages"][index:index + 2]
        assert [row["role"] for row in rows] == ["developer", "user"]
        static, dynamic = [row["content"] for row in rows]
        assert not json.loads(static).keys() & json.loads(dynamic).keys()
        return static[:-1] + "," + dynamic[1:]
    return request["messages"][1]["content"]


def request_dossier(request, *, declaration=None):
    return json.loads(dossier_text(request, declaration=declaration))
