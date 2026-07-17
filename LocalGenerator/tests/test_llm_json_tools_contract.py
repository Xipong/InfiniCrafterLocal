from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.llm_json_tools import json_object_candidates, parse_first_valid_llm_json


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

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_llm_json_tools_parse_fenced_and_duplicate_objects',
    '_check_llm_json_tools_respects_string_braces',
    '_check_llm_json_tools_ignores_private_thought_json'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_llm_json_tools_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
