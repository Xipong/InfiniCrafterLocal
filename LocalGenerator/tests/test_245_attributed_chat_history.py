from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.vfx_director_prompt import build_vfx_director_handoff_messages
from infini_local.core import vfx_manifest as vm
from infini_local.pipelines import llm_authoring_pipeline as lap
from infini_local.pipelines import combine_genome as genome
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines.visual_director_contract import visual_director_context


def _planner_child() -> dict:
    return {
        "name": "Attribution Needle",
        "tooltip": "A narrow runtime probe.",
        "category": "weapon",
        "concept": {"fantasy": "A precise luminous needle.", "mergeLogic": "silver plus starlight"},
        "gameplay": {
            "kind": "weapon", "damage": 8, "useTime": 22,
            "rejectedEngineCalls": [{"receiptLeakSentinel": True}],
        },
        "runtimeContract": {
            "primaryVerb": "shoot", "controlStyle": "tap",
            "finalWireReceipts": [{"wireReceiptLeakSentinel": True}],
        },
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 8, "useTimeTicks": 22, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9, "useTimeTicks": 22}},
            ]
        },
        "attack": {
            "enabled": True, "runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight",
            "soundUseCatalogId": "Item5", "soundImpactCatalogId": "NPCHit4",
            "soundVolume": 0.8, "soundPitch": 0.1, "soundPitchVariance": 0.2,
        },
        "visual": {"palette": ["silver", "cyan"], "projectileImagePrompt": "a silver needle"},
        "visualKit": {
            "styleGuide": "crisp silver pixel art",
            "palette": ["silver", "cyan"],
            "silhouetteSummary": "one narrow needle",
            "projectileSpritePrompt": "one narrow silver needle",
            "bakedAssets": {"projectile": {"mode": "baked_sprite", "reason": "distinct body"}},
            "vfxIntent": "a restrained cyan wake",
            "projectileVfx": "thin cyan wake",
            "vfxAvoid": "no fire",
        },
        "debug": {"repairReport": {"secret": True}, "visualPromptSource": "planner_authored"},
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
    parent_a = {
        "name": "Silver Bullet",
        "nameTokens": ["silver", "bullet"],
        "autoFeatures": ["ammo"],
        "generatedData": {
            "visualKit": {
                "itemIconPrompt": "canonical silver bullet",
                "styleGuide": "clean metal pixel art",
            },
            "visual": {"imagePrompt": "legacy mirror must not cross"},
        },
    }
    parent_b = {"name": "Fallen Star", "nameTokens": ["fallen", "star"], "autoFeatures": ["magic"]}
    messages = build_vfx_director_handoff_messages(_planner_child(), parent_a, parent_b)

    assert messages is not None
    assert [(m["role"], m["name"]) for m in messages] == [
        ("system", "vfx_director_contract"),
        ("user", "pipeline_orchestrator"),
    ]
    assert "authoritative current" in messages[0]["content"].lower()
    assert "earlier" not in messages[0]["content"].lower()
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
    packet = instruction["vfxInputPacket"]
    assert "provenanceContract" not in packet
    parent_card = packet["parentA"]
    forbidden_parent_keys = {
        "nameTokens", "runtimeAutoFeatures", "generatedAuthoredTags", "tagProvenance",
        "tagProvenanceNote", "tags", "parentVfxSignals", "pythonDerivedTags",
    }
    assert forbidden_parent_keys.isdisjoint(parent_card)
    assert parent_card["acceptedVisualAssetKit"]["itemIconPrompt"] == "canonical silver bullet"
    assert "acceptedVisualFacts" not in parent_card
    child_card = packet["childItem"]
    assert child_card["visualAssetKit"] == _planner_child()["visualKit"]
    assert "visual" not in child_card
    assert child_card["acceptedConcept"]["fantasy"] == "A precise luminous needle."
    assert child_card["acceptedRuntimeContract"]["controlStyle"] == "tap"
    assert child_card["audioFacts"] == {
        "soundUseCatalogId": "Item5",
        "soundImpactCatalogId": "NPCHit4",
        "soundVolume": 0.8,
        "soundPitch": 0.1,
        "soundPitchVariance": 0.2,
    }
    assert "debug" not in json.dumps(packet, ensure_ascii=False).lower()
    packet_text = json.dumps(packet, ensure_ascii=False)
    assert "wireReceiptLeakSentinel" not in packet_text
    assert "receiptLeakSentinel" not in packet_text
    assert "legacy mirror must not cross" not in packet_text
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


def _contract_check_visual_handoff_omits_classifier_and_debug_provenance():
    parent = {
        "name": "Tagged Parent",
        "internalName": "TaggedParent",
        "damage": 7,
        "generatedData": {
            "visualKit": {"itemIconPrompt": "canonical tagged parent"},
            "visual": {"imagePrompt": "visual legacy mirror sentinel"},
            "gameplay": {"rejectedEngineCalls": [{"reason": "rejected-call-sentinel"}]},
            "generatedParentSummary": {
                "notableEffects": ["rejected unsupported calls", "summary-sentinel"],
                "visualIdentity": "derived-summary-identity-sentinel",
            },
        },
    }
    context = visual_director_context(
        {
            "name": "Clean Child",
            "category": "weapon",
            "concept": {"fantasy": "accepted fantasy"},
            "runtimePlan": {"resultKind": "weapon", "visualIntent": {"palette": ["blue"]}},
            "attack": {"runtimeFamily": "shoot", "movement": "straight"},
            "visual": {
                "imagePrompt": "accepted planner prompt",
                "palette": ["blue"],
                "parentVisualContext": ["classifier context sentinel"],
            },
            "canonical": {
                "category": "weapon", "headNoun": "classifier noun",
                "hardTags": ["classifier-hard"], "softTags": ["classifier-soft"],
                "shapeAnchors": ["classifier-shape"], "visualAnchors": ["classifier-visual"],
            },
            "debug": {
                "visualPromptSource": "planner_authored",
                "visualPaletteSource": "repair_classifier",
                "visualRequiredAnchorsSource": "debug_classifier",
            },
        },
        parent,
        parent,
        {"category": "weapon", "hardTags": ["parent-tag"], "softTags": ["parent-soft"]},
        {"category": "weapon", "hardTags": ["parent-tag"], "softTags": ["parent-soft"]},
    )
    payload = json.dumps(context, ensure_ascii=False)
    assert "existingVisualProvenance" not in context
    assert "existingVisual" not in context
    assert "sourceRolePreservation" not in context
    for forbidden in (
        "hardTags", "softTags", "headNoun", "shapeAnchors", "visualAnchors",
        "parentVisualContext", "classifier context sentinel",
        "visualPromptSource", "visualPaletteSource", "visualRequiredAnchorsSource",
        "classifier-hard", "classifier-soft", "parent-tag", "parent-soft",
    ):
        assert forbidden not in payload
    parent_card = context["parents"][0]
    assert parent_card["previouslyAcceptedVisualAssetKit"]["itemIconPrompt"] == "canonical tagged parent"
    assert "previouslyAuthoredVisual" not in parent_card
    assert "visual legacy mirror sentinel" not in payload
    assert "generatedParentSummary" not in parent_card
    assert "rejected-call-sentinel" not in payload
    assert "summary-sentinel" not in payload
    assert "derived-summary-identity-sentinel" not in payload

    from infini_local.core.vfx_director_prompt import _vfx_compact_item_for_director
    vfx_parent = {
        "name": "Generated profile parent",
        "fingerprint": {"projectileProfile": {
            "width": 18, "height": 24, "timeLeft": 90,
            "engineMetrics": {"compilerReceipt": "sentinel"},
            "unknownUpstreamMetadata": "must not cross",
        }},
    }
    vfx_card = _vfx_compact_item_for_director(vfx_parent)
    assert vfx_card["projectileProfile"] == {"width": 18, "height": 24, "timeLeft": 90}
    assert "sentinel" not in json.dumps(vfx_card)


def _contract_check_vfx_adapter_rejects_missing_self_contained_messages(monkeypatch):
    calls = []

    def fake_chat(req: dict, timeout: int):
        calls.append(req)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="self-contained VFX stage messages"):
        lap.call_llm_vfx_director(
            "VFX contract", {}, 900, 0.2, 10, messages=None,
        )
    assert calls == []


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
    assert child["debug"]["vfxPath"] == "vfx_director_rejected"


def _contract_check_failed_vfx_repair_logs_exact_policy_transition(monkeypatch):
    child = _planner_child()
    calls = []
    events = []

    def fake_client(system, user, max_tokens, temperature, timeout, messages=None):
        calls.append({"system": system, "user": user, "messages": messages})
        return {}

    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS", 7)
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
        "policy": "llm_vfx_then_explicit_direct_else_inert",
        "recipeKey": "r_vfx_policy_trace",
        "itemId": "",
        "itemName": "Attribution Needle",
        "historyState": "self_contained",
        "requestMode": "authoritative_stage_dossier_v31",
        "failurePhase": "repair_exhausted",
        "reason": "invalid_after_repair",
        "validationFields": payload["validationFields"],
        "repairAttempts": 1,
        "fallbackTarget": "explicit_runtime_vfx_or_empty_manifest",
    }
    assert payload["validationFields"]


def _contract_check_missing_vfx_authority_freezes_empty_manifest(monkeypatch):
    data = {
        "id": "g_vfx_fallback_trace",
        "name": "Fallback Trace Spear",
        "gameplay": {"powerBudget": 1.0},
        "attack": {
            "enabled": True,
            "pattern": "basic",
            "powerBudget": 1.0,
            "effect": "flame",
            "trailLength": 12,
        },
        "visual": {},
        "visualKit": {},
        "debug": {
            "vfxLlmDirectorFinalFallbackReason": "invalid_after_repair",
        },
    }
    parent_with_forbidden_classifier = {
        "name": "Injected classifier parent",
        "parentVfxSignals": {
            "specialScore": 1.0,
            "effectTags": ["beam", "lunar"],
            "suggestedRenderers": ["beamLine", "historyRibbon"],
        },
    }

    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    monkeypatch.setattr(vm, "_vfx_runtime_plan_direct_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(vm, "try_llm_vfx_director", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        vm,
        "get_vfx_recipes",
        lambda: (_ for _ in ()).throw(AssertionError("deterministic selector must stay unreachable")),
    )

    baseline = vm.attach_hybrid_vfx_manifest(
        json.loads(json.dumps(data)), "r_vfx_inert_baseline",
    )
    injected = vm.attach_hybrid_vfx_manifest(
        json.loads(json.dumps(data)),
        "r_vfx_inert_injected",
        parent_a=parent_with_forbidden_classifier,
    )

    assert baseline["vfxManifest"]["slots"] == []
    assert injected["vfxManifest"] == baseline["vfxManifest"]
    assert baseline["debug"]["vfxPath"] == "empty_no_authored_vfx"
    generator_client = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Common/Services/GeneratorClient.cs"
    ).read_text(encoding="utf-8")
    assert "parentVfxSignals" not in generator_client
    assert "ParentVfxSignalsFromItem" not in generator_client


def _contract_check_explicit_empty_vfx_director_manifest_is_accepted_without_fallback(monkeypatch):
    from infini_local.core import vfx_manifest_config

    calls: list[str] = []

    def empty_vfx_director(*_args, **_kwargs):
        calls.append("vfx_director")
        return {
            "effectMagnitude": 0.0,
            "visualBudgetClass": "tiny",
            "identity": "No visible effect",
            "slots": [],
        }

    def forbidden_runtime_fallback(*_args, **_kwargs):
        raise AssertionError("accepted empty Director manifest must not fall through")

    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    monkeypatch.setattr(vfx_manifest_config, "VFX_SELECTOR_ENABLED", False)
    monkeypatch.setattr(vm, "_vfx_runtime_plan_direct_manifest", forbidden_runtime_fallback)
    out = vm.attach_hybrid_vfx_manifest(
        _planner_child(),
        "explicit-empty-vfx",
        llm_director=empty_vfx_director,
    )

    assert calls == ["vfx_director"]
    assert out["vfxManifest"]["slots"] == []
    assert out["debug"]["vfxPath"] == "llm_director_empty"
    assert json.loads(out["attack"]["vfxManifestJson"])["slots"] == []


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


def _contract_check_post_author_visual_stages_are_stateless_and_use_accepted_product(monkeypatch):
    malformed = {"kind": "attributed_planner_history_v1", "messages": []}

    assert visual.is_llm_planner({"runtimePlan": {"engineCalls": [{"fn": "set_item_stats"}]}})
    assert not visual.is_llm_planner({"debug": {"planner": "llm_author_first"}})

    llm_without_authored_prompt = {
        "name": "Promptless LLM Item",
        "category": "weapon",
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats"}]},
        "visual": {},
    }
    visual.attach_visual(llm_without_authored_prompt, {}, {}, {}, {})
    assert "imagePrompt" not in llm_without_authored_prompt["visual"]

    explicit_dev_fallback = {"name": "Dev Fallback Item", "category": "generic", "visual": {}}
    visual.attach_visual(explicit_dev_fallback, {}, {}, {}, {})
    assert explicit_dev_fallback["visual"]["imagePrompt"]

    from infini_local.core.vfx_composition_parent import _vfx_manifest_from_parent_item

    debug_only_manifest = {
        "debug": {
            "vfxManifest": json.dumps({"effectMagnitude": 1.0, "slots": [{"rendererKind": "debug-only-sentinel"}]})
        }
    }
    assert _vfx_manifest_from_parent_item(debug_only_manifest) == {}
    accepted_manifest = {"effectMagnitude": 0.3, "slots": [{"rendererKind": "lightCue"}]}
    assert _vfx_manifest_from_parent_item({"vfxManifest": accepted_manifest}) == accepted_manifest

    vfx_child = _planner_child()
    vfx_child["_llmHistory"] = malformed
    vfx_calls = []
    monkeypatch.setattr(vm, "VFX_LLM_DIRECTOR_ENABLED", True)
    assert vm.try_llm_vfx_director(
        {}, {}, vfx_child, "r_bad_vfx_history", lambda *a, **k: vfx_calls.append(True) or None
    ) is None
    assert vfx_calls
    assert "vfxLlmDirectorHistoryFallbackReason" not in vfx_child["debug"]

    missing_live_vfx = _planner_child()
    missing_live_vfx.pop("_llmHistory")
    missing_live_vfx["debug"] = {"planner": "stale_debug_must_not_route"}
    missing_live_calls = []
    assert vm.try_llm_vfx_director(
        {}, {}, missing_live_vfx, "r_missing_live_vfx_history",
        lambda *a, **k: missing_live_calls.append(True) or None,
    ) is None
    assert missing_live_calls
    assert "vfxLlmDirectorHistoryFallbackReason" not in missing_live_vfx["debug"]

    genome_child = _planner_child()
    genome_child.update({"debug": {"planner": "llm_author_first"}, "_llmHistory": malformed})
    genome_calls = []
    monkeypatch.setattr(genome, "llm_chat_json", lambda *a, **k: genome_calls.append(True))
    assert genome.try_llm_genome_repair(genome_child, {}, {}, {}, {}, "r_bad_genome_history", ["missing movement"], 1) is None
    assert genome_calls == []

    visual_child = _planner_child()
    visual_child.update({"debug": {"planner": "stale_debug_must_not_route"}, "_llmHistory": malformed})
    visual_calls = []
    monkeypatch.setattr(visual, "USE_LLM", True)
    monkeypatch.setattr(visual, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(visual, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(visual, "llm_chat_json", lambda *a, **k: visual_calls.append(True) or None)
    out = visual.apply_visual_director(visual_child, {}, {}, {}, {})
    assert visual_calls
    assert out["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert "history" not in out["debug"]["visualDirectorError"].lower()


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_245_attributed_chat_history_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_vfx_handoff_reaches_client_with_named_speakers_and_explicit_next_stage',
            '_contract_check_visual_handoff_omits_classifier_and_debug_provenance',
            '_contract_check_vfx_adapter_rejects_missing_self_contained_messages',
            '_contract_check_invalid_vfx_continuation_does_not_retry_as_standalone',
            '_contract_check_failed_vfx_repair_logs_exact_policy_transition',
            '_contract_check_missing_vfx_authority_freezes_empty_manifest',
            '_contract_check_explicit_empty_vfx_director_manifest_is_accepted_without_fallback',

            '_contract_check_genome_repair_retargets_history_and_uses_delta',
            '_contract_check_post_author_visual_stages_are_stateless_and_use_accepted_product',
        ),
    )
