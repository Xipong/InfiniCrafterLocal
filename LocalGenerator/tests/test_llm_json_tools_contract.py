from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.llm_json_tools import (
    json_object_candidates,
    parse_first_valid_llm_json,
    recover_object_with_trailing_commas,
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


def _check_lossless_trailing_comma_recovery_does_not_modify_string_values() -> None:
    assert recover_object_with_trailing_commas('{"label":",}", "rows":[{"value":7,},],}') == {
        "label": ",}", "rows": [{"value": 7}],
    }
    assert recover_object_with_trailing_commas('{"missing":') is None
    assert recover_object_with_trailing_commas('{"damage":42,"damage":43,}') is None


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_llm_json_tools_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
