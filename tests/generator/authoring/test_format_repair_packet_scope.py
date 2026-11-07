"""Local syntax Fix preserves the sole design source and the real Repair budget."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_json_tools import parse_llm_json_with_syntax_fix
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.author import request as author
from infini_local.pipelines.author.stage import compile_and_validate_authored_runtime
from infini_local.pipelines.visual import stage as visual
from infini_local.pipelines.visual.contract import VISUAL_REPAIR_PATCH_SCHEMA
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from prompt_packet_helpers import request_dossier
from tests.generator.authoring.test_low_level_three_stage_pipeline import _visual_kit, wire_transport


@pytest.mark.parametrize("stage", ["author", "visual"])
@pytest.mark.parametrize("semantic_error", [False, True], ids=["syntax-only", "syntax-then-scoped-repair"])
def test_local_syntax_fix_keeps_raw_design_and_one_meaningful_repair(wire_transport, stage, semantic_error):
    responses, requests = wire_transport
    authored = build_runtime_fixture("workbench_blade")
    data = compile_runtime_program(authored)
    source = copy.deepcopy(authored if stage == "author" else _visual_kit(data))
    if stage == "author":
        # Debug notes remain literal and cannot become acceptance requirements.
        source["concept"] = "  Exact idea 雪\r\n  "
        source["realization"] = {"description": "  literal  ", "selfEvaluation": "д" * 5500}
        broken = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "item_stats")
        correction = copy.deepcopy(broken)
        if semantic_error:
            broken["params"]["damage"] = True
            correction["params"]["knockback"] = 999  # Frozen sibling rewrite is ignored.
        patch = {"note": "damage type only", "callsUpsert": [correction]}
    else:
        if semantic_error:
            source["item"]["inventoryScale"] = 0
        patch = {"schema": VISUAL_REPAIR_PATCH_SCHEMA, "note": "scale only",
                 "itemPatch": {"inventoryScale": 1.0, "visualIdentity": "hostile rewrite"}}
    raw = json.dumps(source, ensure_ascii=False)[:-1] + ",}"
    responses.append(raw)
    if semantic_error:
        responses.append(patch)
    if stage == "author":
        result = author.try_llm_plan({}, {}, "syntax-source")
        assert result is not None
        assert result["debug"]["llmRawOutput"] == raw[:12000]
        assert result["debug"]["gameplaySyntaxFix"] == {"reason": "fix:llm_json_syntax", "sourceChars": len(raw)}
        assert result["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 0
        assert result["concept"] == source["concept"] and result["realization"] == source["realization"]
        result = compile_and_validate_authored_runtime(result, {}, {}, "syntax-source",
            run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
        assert result["gameplay"]["damage"] == data["gameplay"]["damage"]
        assert result["gameplay"]["knockback"] == data["gameplay"]["knockback"]
        names, counter = ["planner"], "gameplayRepairCalls"
    else:
        result = visual.apply_visual_director(data, {}, {})
        assert result["debug"]["visualDirectorRawText"] == raw
        assert result["debug"]["visualSyntaxFix"] == {"reason": "fix:llm_json_syntax", "sourceChars": len(raw)}
        assert result["visualKit"]["item"]["visualIdentity"] == source["item"]["visualIdentity"]
        assert result["visualKit"]["animationPlan"] == source["animationPlan"]
        names, counter = ["visual_director"], "visualRepairCalls"
    if semantic_error:
        names.append("author_repair" if stage == "author" else "visual_repair")
        packet = request_dossier(requests[1])
        assert not packet.get("malformedRawText"), "semantic Repair gets parsed fragments, not another format request"
    assert [request["_infini_stage"] for request in requests] == names
    assert result["debug"]["llmStageAccounting"][counter] == int(semantic_error)
    assert not responses


@pytest.mark.parametrize("stage", ["author", "visual"])
@pytest.mark.parametrize("raw", ['{"missing":}', '{"a":1,"a":2,}', '{"values":[1,,2]}',
    '{"a":1,}{"b":2,}', '{"value":NaN}', '{"root":{"missing":}'])
def test_unrecoverable_source_fails_without_model_repair(wire_transport, stage, raw):
    responses, requests = wire_transport
    responses.append(raw)
    with pytest.raises(PlannerUnavailable):
        if stage == "author":
            author.try_llm_plan({}, {}, "refuse")
        else:
            visual.apply_visual_director(compile_runtime_program(build_runtime_fixture("workbench_blade")), {}, {})
    assert len(requests) == 1 and not responses


@pytest.mark.parametrize("identity", ["unknown_operation", None, 7])
def test_syntax_fix_never_guesses_a_missing_or_unknown_function(wire_transport, identity):
    responses, requests = wire_transport
    source = build_runtime_fixture("workbench_blade")
    source["runtimeProgram"]["calls"][0]["fn"] = identity
    responses.append(json.dumps(source)[:-1] + ",}")
    result = author.try_llm_plan({}, {}, "invalid-identity")
    assert result is not None
    assert result["runtimeProgram"] == source["runtimeProgram"]
    assert not validate_runtime_program(result)["ok"]
    assert len(requests) == 1 and not responses


def test_clean_json_has_no_fix_receipt_and_missing_root_brace_has_one():
    assert parse_llm_json_with_syntax_fix('{"item":{"value":7}}') == ({"item": {"value": 7}}, None)
    source = '{"item":{"value":7}'
    assert parse_llm_json_with_syntax_fix(source) == (
        {"item": {"value": 7}}, {"reason": "fix:llm_json_syntax", "sourceChars": len(source)})
