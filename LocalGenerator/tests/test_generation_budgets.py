"""Generation defaults observed through real callers with offline HTTP only."""
from __future__ import annotations
from infini_local.pipelines import vfx_generation_pipeline as vfx_transport

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


GENERATOR_ROOT = Path(__file__).resolve().parents[1]


def observe(overrides=None, *, stages="author", repair="none", corrupt_budget=False):
    # Import-time configuration must never depend on pytest order or operator config.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("INFINI_", "OPENAI_", "OPENROUTER_"))}
    env.update({
        "PYTHONPATH": os.pathsep.join((str(GENERATOR_ROOT), str(GENERATOR_ROOT / "tests"))),
        "INFINI_SKIP_CONFIG_FILE": "1", "INFINI_USE_LLM": "1",
        "INFINI_LLM_PROVIDER": "openrouter", "INFINI_LLM_API_MODE": "chat_completions",
        "INFINI_LLM_RESPONSE_FORMAT": "json_object", "INFINI_LLM_FALLBACK_NETWORK_FAILS": "1",
        "INFINI_OPENROUTER_MODEL": "offline/budget-observer",
        "INFINI_OPENROUTER_API_KEY": "synthetic-offline-key",
        "INFINI_OPENROUTER_BASE_URL": "https://offline.invalid/v1",
        "INFINI_CACHE_DIR": os.environ["INFINI_CACHE_DIR"],
        "INFINI_WORLD_RECIPES_DIR": os.environ["INFINI_WORLD_RECIPES_DIR"],
    })
    env.update(overrides or {})
    options = {"stages": stages, "repair": repair, "corrupt_budget": corrupt_budget}
    run = subprocess.run(
        [sys.executable, "-c", "import json; from test_generation_budgets import _observe; "
         f"print(json.dumps(_observe(**{options!r})))"],
        env=env, cwd=GENERATOR_ROOT, capture_output=True, text=True, timeout=45,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def _observe(*, stages, repair, corrupt_budget):
    from collections import deque
    import copy
    from unittest.mock import patch

    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import llm_transport as transport
    from infini_local.pipelines import gameplay_stage as combine
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.vfx_manifest import attach_vfx_manifest, VFX_REPAIR_PATCH_SCHEMA
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from test_low_level_three_stage_pipeline import _visual_kit, _visual_patch, _vfx_output

    calls, replies = [], deque()
    if corrupt_budget:
        transport.LLM_MAX_TOKENS = "invalid-runtime-scalar"

    def http_reply(url, payload, timeout=10, headers=None):
        expected_url = ("http://offline.invalid:1234/v1/chat/completions"
                        if os.environ["INFINI_LLM_PROVIDER"] == "local"
                        else "https://offline.invalid/v1/chat/completions")
        assert url == expected_url
        assert replies, "unexpected extra model pass"
        calls.append({"tokens": payload["max_tokens"], "temperature": payload["temperature"],
                      "timeout": timeout, "reasoning": payload.get("reasoning"),
                      "reasoning_effort": payload.get("reasoning_effort")})
        value = replies.popleft()
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": value if isinstance(value, str) else json.dumps(value)}}]}

    def refuse_discovery(*args, **kwargs):
        raise AssertionError("offline observer forbids external discovery")

    authored = build_runtime_fixture("workbench_blade")
    original_program = copy.deepcopy(compile_runtime_program(authored)["runtimeProgram"])
    if repair == "format":
        replies.extend([json.dumps(authored)[:-1] + ",}", authored])
    elif repair == "semantic":
        damaged = copy.deepcopy(authored)
        damaged["runtimeProgram"]["calls"][0]["params"].pop("damage")
        replies.extend([damaged, {"callsUpsert": [authored["runtimeProgram"]["calls"][0]],
                                  "note": "restore only missing damage",
                                  "realizationReplacement": authored["realization"]}])
    else:
        replies.append(authored)

    with patch.object(transport, "http_json", http_reply), patch.object(transport, "http_get_json", refuse_discovery):
        data = author.try_llm_plan({}, {}, "budget-observer")
        assert data is not None
        if repair == "semantic":
            data = combine.compile_and_validate_authored_runtime(
                data, {}, {}, "budget-observer",
                run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
        else:
            data = compile_runtime_program(data)
        assert data["runtimeProgram"] == original_program
        if stages == "all":
            kit = _visual_kit(data)
            if repair != "none":
                replies.extend([{"schema": visual.VISUAL_KIT_SCHEMA, "item": {}, "entities": [],
                                 "animationPlan": "frozen animation"}, _visual_patch(data)])
            else:
                replies.append(kit)
            data = visual.apply_visual_director(data, {}, {})
            if repair != "none":
                assert data["visualKit"]["animationPlan"] == "frozen animation"
            vfx = _vfx_output(data)
            if repair != "none":
                broken_vfx = copy.deepcopy(vfx)
                broken_vfx["slots"][0]["alpha"] = 2.0
                replies.extend([broken_vfx, {
                    "schema": VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": vfx["slots"],
                    "note": "restore only invalid alpha"}])
            else:
                replies.append(vfx)
            data = attach_vfx_manifest(data, "budget-observer", llm_director=vfx_transport.call_llm_vfx_director)
            assert data["vfxManifest"]["slots"][0]["id"] == vfx["slots"][0]["id"]
        assert not replies
    return {"calls": calls, "accounting": data["debug"]["llmStageAccounting"]}


def budget_rows(observation):
    rows = []
    for call in observation["calls"]:
        # The physical transport receives the remaining deadline, not a fresh timeout.
        rows.append((call["tokens"], round(call["timeout"]), call["temperature"],
                     (call["reasoning"] or {}).get("effort")))
    return rows


def test_clean_author_emits_recommended_global_budget():
    assert budget_rows(observe()) == [(18000, 600, 0.5, "medium")]


def test_defensive_answer_budget_fallback_uses_canonical_recommendation():
    assert budget_rows(observe(corrupt_budget=True)) == [(18000, 600, 0.5, "medium")]


@pytest.mark.parametrize("overrides,expected", [
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "0.31"}, 0.31),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "9"}, 0.8),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "-1"}, 0.0),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "0"}, 0.0),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": " ", "INFINI_LLM_TEMPERATURE": "0.9"}, 0.12),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "invalid"}, 0.12),
    ({"INFINI_LLM_REPAIR_TEMPERATURE": "nan"}, 0.12),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "0.7", "INFINI_LLM_REPAIR_TEMPERATURE": "0"}, 0.0),
    ({"INFINI_LLM_REPAIR_TEMPERATURE": "9"}, 0.8),
    ({"INFINI_LLM_REPAIR_TEMPERATURE": "-1"}, 0.0),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "0.7", "INFINI_LLM_REPAIR_TEMPERATURE": "0.23"}, 0.23),
    ({"INFINI_LLM_REAUTHOR_TEMPERATURE": "0.7", "INFINI_LLM_REPAIR_TEMPERATURE": " "}, 0.12),
])
def test_gameplay_repair_respects_bounded_gui_alias_and_canonical_precedence(monkeypatch, overrides, expected):
    from test_craft_instruction_segments import stage_packets
    # This scalar is read at request time. Exercise its real semantic request
    # caller without reimporting/compiling all three stages for every value.
    for key in ("INFINI_LLM_REPAIR_TEMPERATURE", "INFINI_LLM_REAUTHOR_TEMPERATURE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    packet, = stage_packets(monkeypatch, "repair", labels=("temperature",))
    assert packet["temperature"] == expected


def test_format_repair_uses_the_same_scoped_default_at_transport():
    assert budget_rows(observe(repair="format")) == [
        (18000, 600, 0.5, "medium"), (18000, 600, 0.12, "medium"),
    ]


def test_all_stage_callers_share_budget_including_the_single_repair():
    result = observe(stages="all", repair="semantic")
    assert budget_rows(result) == [
        (18000, 600, 0.5, "medium"), (18000, 600, 0.12, "medium"),
        (18000, 600, 0.45, "medium"), (18000, 600, 0.12, "medium"),
        (18000, 600, 0.34, "medium"), (18000, 600, 0.12, "medium"),
    ]
    assert result["accounting"] == {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 1,
        "visualDirectorCalls": 1, "visualRepairCalls": 1,
        "vfxDirectorCalls": 1, "vfxRepairCalls": 1,
    }


@pytest.mark.parametrize("stage_value", [None, "invalid"])
def test_unset_blank_vfx_and_visual_budgets_inherit_explicit_global(stage_value):
    overrides = {"INFINI_LLM_MAX_TOKENS": "24000", "INFINI_LLM_TIMEOUT": "720"}
    if stage_value is not None:
        overrides.update({"INFINI_VISUAL_DIRECTOR_MAX_TOKENS": stage_value,
                          "INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS": stage_value,
                          "INFINI_VFX_LLM_DIRECTOR_TIMEOUT": stage_value})
    rows = budget_rows(observe(overrides, stages="all", repair="semantic"))
    assert [(tokens, timeout) for tokens, timeout, _temp, _effort in rows] == [(24000, 720)] * 6


def test_explicit_stage_overrides_win_in_both_director_and_repair():
    overrides = {
        "INFINI_LLM_MAX_TOKENS": "26000", "INFINI_LLM_TIMEOUT": "780",
        "INFINI_LLM_REASONING_MODE": "high", "INFINI_LLM_TEMPERATURE": "0.77",
        "INFINI_LLM_REPAIR_TEMPERATURE": "0.21", "INFINI_LLM_REAUTHOR_TEMPERATURE": "0.6",
        "INFINI_VISUAL_DIRECTOR_MAX_TOKENS": "11000", "INFINI_VISUAL_DIRECTOR_TEMPERATURE": "0.66",
        "INFINI_VISUAL_REPAIR_TEMPERATURE": "0.17",
        "INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS": "13000", "INFINI_VFX_LLM_DIRECTOR_TIMEOUT": "430",
        "INFINI_VFX_LLM_DIRECTOR_TEMPERATURE": "0.44", "INFINI_VFX_LLM_REPAIR_TEMPERATURE": "0.19",
        "INFINI_VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS": "99",
    }
    assert budget_rows(observe(overrides, stages="all", repair="semantic")) == [
        (26000, 780, 0.77, "high"), (26000, 780, 0.21, "high"),
        (11000, 780, 0.66, "high"), (11000, 780, 0.17, "high"),
        (13000, 430, 0.44, "high"), (13000, 430, 0.19, "high"),
    ]


@pytest.mark.parametrize("mode,expected", [("off", None), ("high", "high")])
def test_explicit_reasoning_keeps_visual_vfx_semantics_and_existing_author_floor(mode, expected):
    rows = budget_rows(observe({"INFINI_LLM_REASONING_MODE": mode}, stages="all"))
    assert [row[3] for row in rows] == ["high" if mode == "high" else "medium", expected, expected]


def test_local_provider_never_sends_reasoning_fields():
    result = observe({"INFINI_LLM_PROVIDER": "local", "INFINI_LMSTUDIO_MODEL": "offline-model",
                      "INFINI_LMSTUDIO_URL": "http://offline.invalid:1234"}, stages="all")
    assert budget_rows(result) == [(18000, 600, 0.5, None), (18000, 600, 0.45, None), (18000, 600, 0.34, None)]
    assert all(call["reasoning_effort"] is None for call in result["calls"])


@pytest.mark.parametrize("value,expected", [("0", 512), ("999999", 64000)])
def test_global_numeric_bounds_are_preserved_at_physical_request(value, expected):
    rows = budget_rows(observe({"INFINI_LLM_MAX_TOKENS": value}, stages="all"))
    assert [row[0] for row in rows] == [expected] * 3


def test_blank_global_numeric_values_use_canonical_recommendations():
    rows = budget_rows(observe({"INFINI_LLM_MAX_TOKENS": " ", "INFINI_LLM_TIMEOUT": "",
                               "INFINI_LLM_TEMPERATURE": "", "INFINI_VISUAL_DIRECTOR_TEMPERATURE": " "}, stages="all"))
    assert rows == [(18000, 600, 0.5, "medium"), (18000, 600, 0.45, "medium"), (18000, 600, 0.34, "medium")]
