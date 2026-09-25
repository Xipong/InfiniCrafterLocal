from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.llm_json_tools import (
    json_object_candidates,
    parse_first_valid_llm_json,
    recover_object_with_syntax_only_repairs,
)


def _check_llm_json_tools_parse_fenced_and_duplicate_objects() -> None:
    text = '```json\n{"name":"First"}\n``` trailing {"name":"Second"}'
    assert parse_first_valid_llm_json(text)["name"] == "First"
    assert len(json_object_candidates('{"a":1}{"b":2}')) == 2


def _check_llm_json_tools_respects_string_braces() -> None:
    parsed = parse_first_valid_llm_json('prefix {"text":"brace } inside string", "ok": true} suffix')
    assert parsed["ok"] is True


def _check_llm_json_tools_ignores_private_thought_json() -> None:
    text = '<thought>{"name":"Decoy"}</thought>{"name":"Authored"}'
    assert parse_first_valid_llm_json(text)["name"] == "Authored"
    assert json_object_candidates('<thought>{"name":"unfinished-decoy"}') == []


def _check_lossless_syntax_only_recovery_does_not_modify_string_values() -> None:
    recover = recover_object_with_syntax_only_repairs
    assert recover('{"label":",}", "rows":[{"value":7,},],}') == {
        "label": ",}", "rows": [{"value": 7}],
    }
    assert recover('{"calls":[{"damage":12,\n, "kind":"test"}],"attributes":{speed: 2, mode:true, mark:"speed:2"}}') == {
        "calls": [{"damage": 12, "kind": "test"}],
        "attributes": {"speed": 2, "mode": True, "mark": "speed:2"},
    }
    assert recover('{"missing":') is None
    assert recover('{"item":{"damage":20}') == {"item": {"damage": 20}}
    assert recover('{"item":{"damage":20') is None
    assert recover('{"item":[1,2]') is None
    assert recover('{"damage":42,"damage":43,}') is None
    assert recover('{damage:42,"damage":43}') is None
    assert recover('{"mode":recall_home}') is None
    assert recover('{"array":[1,,2]}') is None
    assert recover('{"array":[,1]}') is None
    assert recover('{"array":[,]}') is None
    assert recover('{"array":[1,,]}') is None
    assert recover('{"missing":,}') is None
    assert recover('{"a":1,,}') == {"a": 1}


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_llm_json_tools_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
