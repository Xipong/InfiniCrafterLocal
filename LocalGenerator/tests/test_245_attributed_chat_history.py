from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.vfx_director_prompt import build_vfx_director_handoff_messages
from infini_local.core import vfx_manifest as vm
from infini_local.pipelines import llm_authoring_pipeline as lap
from infini_local.pipelines import llm_transport
from infini_local.pipelines import combine_genome as genome
from infini_local.pipelines import result_identity_policy as identity
from infini_local.pipelines import visual_generation_pipeline as visual


def _planner_child() -> dict:
    return {
        "name": "Attribution Needle",
        "tooltip": "A narrow runtime probe.",
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 8, "useTime": 22},
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 8, "useTimeTicks": 22, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9, "useTimeTicks": 22}},
            ]
        },
        "attack": {"enabled": True, "runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight"},
        "visual": {"palette": ["silver", "cyan"], "projectileImagePrompt": "a silver needle"},
        "_llmHistory": {
            "kind": "attributed_planner_history_v1",
            "messages": [
                {"role": "system", "name": "item_author_contract", "content": "You are the item author."},
                {"role": "user", "name": "recipe_context", "content": '{"recipe":"probe"}'},
                {"role": "assistant", "name": "item_planner", "content": '{"name":"Attribution Needle"}'},
            ],
        },
    }


def _contract_check_vfx_handoff_reaches_client_with_named_speakers_and_explicit_next_stage(monkeypatch):
    parent_a = {"name": "Silver Bullet", "nameTokens": ["silver", "bullet"], "autoFeatures": ["ammo"]}
    parent_b = {"name": "Fallen Star", "nameTokens": ["fallen", "star"], "autoFeatures": ["magic"]}
    messages = build_vfx_director_handoff_messages(_planner_child(), parent_a, parent_b)

    assert messages is not None
    assert [(m["role"], m["name"]) for m in messages] == [
        ("system", "vfx_director_contract"),
        ("user", "pipeline_orchestrator"),
    ]
    assert "authoritative current" in messages[0]["content"].lower()
    assert "provenance" in messages[0]["content"].lower()
    instruction = json.loads(messages[-1]["content"])
    assert instruction["agentHandoff"] == {
        "schema": "infini.llm-handoff.v1",
        "previousSpeaker": "item_planner",
        "currentSpeaker": "pipeline_orchestrator",
        "nextSpeaker": "vfx_director",
        "causeBy": "vfx_manifest_authoring_stage",
        "artifactSource": "vfxInputPacket.childItem",
    }
    assert "authoritative current" in instruction["continuationMode"].lower()
    parent_card = instruction["vfxInputPacket"]["parentA"]
    assert parent_card["nameTokens"] == ["silver", "bullet"]
    assert "pythonDerivedTags" not in parent_card
    assert parent_card["tags"] == []
    captured = {}

    def fake_llm_chat_json(req, timeout=10):
        captured["request"] = req
        return {"choices": [{"message": {"content": '{"effectMagnitude":0.2,"visualBudgetClass":"tiny","slots":[]}'}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "vfx-test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)

    out = lap.call_llm_vfx_director("unused", {}, 900, 0.2, 10, messages=messages)
    assert out is not None
    assert "_debug" not in out
    assert [m.get("name") for m in captured["request"]["messages"]] == [
        "vfx_director_contract",
        "pipeline_orchestrator",
    ]


def _contract_check_legacy_no_history_vfx_handoff_points_to_current_child_item(monkeypatch):
    captured = {}

    def fake_chat(req: dict, timeout: int):
        captured["req"] = req
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)

    lap.call_llm_vfx_director(
        "VFX contract",
        {"vfxInputPacket": {"childItem": {"name": "Legacy Probe"}}},
        900,
        0.2,
        10,
        messages=None,
    )

    user_packet = json.loads(captured["req"]["messages"][-1]["content"])
    assert user_packet["agentHandoff"]["artifactSource"] == "vfxInputPacket.childItem"


def _contract_check_invalid_vfx_continuation_does_not_retry_as_standalone(monkeypatch):
    child = _planner_child()
    calls = []

    def fake_client(system, user, max_tokens, temperature, timeout, messages=None):
        calls.append({"system": system, "user": user, "messages": messages})
        return {}

    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS", 0)

    out = vm.try_llm_vfx_director({}, {}, child, "r_vfx_no_second_prompt", fake_client)

    assert out is None
    assert len(calls) == 1
    assert calls[0]["messages"] is not None
    assert calls[0]["messages"][0]["name"] == "vfx_director_contract"
    assert child["debug"]["vfxPath"] == "deterministic_recipe_fallback"


def _contract_check_failed_vfx_repair_logs_exact_policy_transition(monkeypatch):
    child = _planner_child()
    calls = []
    events = []

    def fake_client(system, user, max_tokens, temperature, timeout, messages=None):
        calls.append({"system": system, "user": user, "messages": messages})
        return {}

    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS", 1)
    monkeypatch.setattr(vm, "log_event", lambda level, message, payload=None: events.append((level, message, payload)), raising=False)

    out = vm.try_llm_vfx_director({}, {}, child, "r_vfx_policy_trace", fake_client)

    assert out is None
    assert len(calls) == 2
    policy_events = [event for event in events if event[1] == "VFX Director fallback policy activated"]
    assert len(policy_events) == 1
    level, _, payload = policy_events[0]
    assert level == "warn"
    assert payload == {
        "schema": "infini.vfx-fallback-trace.v1",
        "policy": "llm_vfx_optional_then_procedural_safety_net",
        "recipeKey": "r_vfx_policy_trace",
        "itemId": "",
        "itemName": "Attribution Needle",
        "historyState": "valid",
        "requestMode": "authoritative_stage_dossier_v31",
        "failurePhase": "repair_exhausted",
        "reason": "invalid_after_repair",
        "validationFields": payload["validationFields"],
        "repairAttempts": 1,
        "fallbackTarget": "procedural_vfx_recipe_selector",
    }
    assert payload["validationFields"]


def _contract_check_procedural_vfx_safety_net_logs_selected_manifest(monkeypatch):
    data = {
        "id": "g_vfx_fallback_trace",
        "name": "Fallback Trace Spear",
        "gameplay": {"powerBudget": 1.0},
        "attack": {"enabled": True, "pattern": "basic", "powerBudget": 1.0},
        "visual": {},
        "visualKit": {},
        "debug": {
            "vfxPath": "deterministic_recipe_fallback",
            "vfxLlmDirectorFinalFallbackReason": "invalid_after_repair",
        },
    }
    events = []

    monkeypatch.setattr(vm, "VFX_SELECTOR_ENABLED", True)
    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    monkeypatch.setattr(vm, "_vfx_runtime_plan_direct_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(vm, "try_llm_vfx_director", lambda *args, **kwargs: None)
    monkeypatch.setattr(vm, "log_event", lambda level, message, payload=None: events.append((level, message, payload)), raising=False)

    out = vm.attach_hybrid_vfx_manifest(data, "r_vfx_selected_trace")

    manifest = out["vfxManifest"]
    selected_events = [event for event in events if event[1] == "VFX procedural safety net selected manifest"]
    assert len(selected_events) == 1
    level, _, payload = selected_events[0]
    assert level == "info"
    assert payload["schema"] == "infini.vfx-fallback-selected.v1"
    assert payload["policy"] == "llm_vfx_optional_then_procedural_safety_net"
    assert payload["recipeKey"] == "r_vfx_selected_trace"
    assert payload["itemId"] == "g_vfx_fallback_trace"
    assert payload["failureReason"] == "invalid_after_repair"
    assert payload["recipeId"] == manifest["recipeId"]
    assert payload["slotCount"] == len(manifest["slots"])
    assert payload["compositionMode"] in {
        "authored_cues_plus_recipe",
        "mundane_guard",
        "recipe_blend_plus_procedural",
        "recipe_only",
    }


def _contract_check_name_repair_retargets_valid_planner_history(monkeypatch):
    data = _planner_child()
    data["name"] = "Generated Hybrid"
    data["debug"] = {"planner": "llm_author_first"}
    captured = {}

    def fake_chat(req, timeout=10):
        captured["request"] = req
        return {"choices": [{"message": {"content": '{"name":"Starlit Needle"}'}}]}

    monkeypatch.setattr(llm_transport, "resolve_llm_model", lambda: "name-test-model")
    monkeypatch.setattr(llm_transport, "llm_chat_json", fake_chat)

    name = identity.try_llm_name_repair(
        data,
        {"name": "Silver Bullet"},
        {"name": "Fallen Star"},
        {},
        {},
        "r_name_retarget",
        {"weapon", "star"},
        "weapon",
    )

    assert name == "Starlit Needle"
    messages = captured["request"]["messages"]
    assert [message["name"] for message in messages] == ["name_repair_contract", "name_repair_context"]
    assert "authoritative current" in messages[0]["content"].lower()
    dossier = json.loads(messages[-1]["content"])
    assert dossier["currentItem"]["name"] == "Generated Hybrid"
    assert [parent["name"] for parent in dossier["parents"]] == ["Silver Bullet", "Fallen Star"]
    assert "_llmHistory" not in messages[-1]["content"]


def _contract_check_genome_repair_retargets_history_and_uses_delta(monkeypatch):
    data = _planner_child()
    data["attack"]["genome"] = {"delivery": "shoot"}
    data["debug"] = {"planner": "llm_author_first"}
    captured = {}

    def fake_chat(req, timeout=10):
        captured["request"] = req
        return {"choices": [{"message": {"content": '{"attack":{"genome":{"delivery":"shoot"}}}'}}]}

    monkeypatch.setattr(genome, "resolve_llm_model", lambda: "genome-test-model")
    monkeypatch.setattr(genome, "llm_chat_json", fake_chat)

    out = genome.try_llm_genome_repair(
        data,
        {"name": "Silver Bullet"},
        {"name": "Fallen Star"},
        {},
        {},
        "r_genome_retarget",
        ["missing movement"],
        1,
    )

    assert out is not None
    messages = captured["request"]["messages"]
    assert [message["name"] for message in messages] == ["genome_repair_contract", "genome_validator"]
    assert "authoritative current" in messages[0]["content"].lower()
    packet = json.loads(messages[-1]["content"])
    assert packet["agentHandoff"]["nextSpeaker"] == "genome_repairer"
    assert packet["currentItem"]["attackGenomeCurrent"]["delivery"] == "shoot"
    assert [parent["name"] for parent in packet["parents"]] == ["Silver Bullet", "Fallen Star"]


def _contract_check_malformed_history_never_downgrades_post_planner_stages_to_standalone(monkeypatch):
    malformed = {"kind": "attributed_planner_history_v1", "messages": []}

    vfx_child = _planner_child()
    vfx_child["_llmHistory"] = malformed
    vfx_calls = []
    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    assert vm.try_llm_vfx_director({}, {}, vfx_child, "r_bad_vfx_history", lambda *a, **k: vfx_calls.append(True)) is None
    assert vfx_calls == []
    assert vfx_child["debug"]["vfxPath"] == "deterministic_recipe_fallback"

    missing_live_vfx = _planner_child()
    missing_live_vfx.pop("_llmHistory")
    missing_live_vfx["debug"] = {"planner": "llm_author_first"}
    missing_live_calls = []
    assert vm.try_llm_vfx_director(
        {}, {}, missing_live_vfx, "r_missing_live_vfx_history", lambda *a, **k: missing_live_calls.append(True)
    ) is None
    assert missing_live_calls == []
    assert missing_live_vfx["debug"]["vfxLlmDirectorHistoryFallbackReason"] == "missing_live_planner_history_fail_closed"

    name_child = _planner_child()
    name_child.update({"name": "Generated Hybrid", "debug": {"planner": "llm_author_first"}, "_llmHistory": malformed})
    name_calls = []
    monkeypatch.setattr(llm_transport, "llm_chat_json", lambda *a, **k: name_calls.append(True))
    assert identity.try_llm_name_repair(name_child, {}, {}, {}, {}, "r_bad_name_history", {"weapon"}, "weapon") is None
    assert name_calls == []

    genome_child = _planner_child()
    genome_child.update({"debug": {"planner": "llm_author_first"}, "_llmHistory": malformed})
    genome_calls = []
    monkeypatch.setattr(genome, "llm_chat_json", lambda *a, **k: genome_calls.append(True))
    assert genome.try_llm_genome_repair(genome_child, {}, {}, {}, {}, "r_bad_genome_history", ["missing movement"], 1) is None
    assert genome_calls == []

    visual_child = _planner_child()
    visual_child.update({"debug": {"planner": "llm_author_first"}, "_llmHistory": malformed})
    visual_calls = []
    monkeypatch.setattr(visual, "USE_LLM", True)
    monkeypatch.setattr(visual, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(visual, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(visual, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(visual, "llm_chat_json", lambda *a, **k: visual_calls.append(True))
    out = visual.apply_visual_director(visual_child, {}, {}, {}, {})
    assert visual_calls == []
    assert out["debug"]["visualDirectorStatus"] == "rejected_fallback_to_existing_visual"
    assert "refusing standalone fallback" in out["debug"]["visualDirectorError"]


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_245_attributed_chat_history_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_vfx_handoff_reaches_client_with_named_speakers_and_explicit_next_stage',
            '_contract_check_legacy_no_history_vfx_handoff_points_to_current_child_item',
            '_contract_check_invalid_vfx_continuation_does_not_retry_as_standalone',
            '_contract_check_failed_vfx_repair_logs_exact_policy_transition',
            '_contract_check_procedural_vfx_safety_net_logs_selected_manifest',
            '_contract_check_name_repair_retargets_valid_planner_history',
            '_contract_check_genome_repair_retargets_history_and_uses_delta',
            '_contract_check_malformed_history_never_downgrades_post_planner_stages_to_standalone',
        ),
    )
