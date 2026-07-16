from __future__ import annotations

import copy
import inspect
import json

import pytest
from pydantic import ValidationError

from infini_local.core.boundary_models import (
    validate_executable_item_boundary,
    validate_visual_authoring_boundaries,
    validate_visual_kit_boundary,
)
from infini_local.core.runtime_promise_truth import validate_runtime_promises
from infini_local.pipelines import combine_pipeline as COMBINE
from infini_local.pipelines import llm_authoring_pipeline as AUTHOR
from infini_local.pipelines import visual_generation_pipeline as VISUAL
from infini_local.pipelines import pipeline_visual_config as VISUAL_CONFIG
from infini_local.pipelines import llm_transport as LLM_TRANSPORT
from infini_local.pipelines import visual_asset_plan as ASSET_PLAN
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.executable_boundary_projection import project_attack_presentation_fields
from infini_local.pipelines.item_power_knowledge import apply_item_knowledge, canonicalize
from infini_local.pipelines.llm_authoring_pipeline import planner_runtime_promise_gate
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt
from infini_local.services.visual_asset_pipeline import strip_conflicting_sprite_prompt_bits


def _wooden_sword() -> dict:
    return {
        "name": "Деревянный меч",
        "internalName": "WoodenSword",
        "sourceMod": "Terraria",
        "damage": 7,
        "damageClass": "melee",
        "useTime": 20,
        "useAnimation": 20,
        "rare": 0,
        "value": 100,
        "maxStack": 1,
        "material": False,
    }


def _workbench() -> dict:
    return {
        "name": "Верстак",
        "internalName": "WorkBench",
        "sourceMod": "Terraria",
        "damage": -1,
        "damageClass": "none",
        "useTime": 10,
        "useAnimation": 14,
        "rare": 0,
        "value": 150,
        "maxStack": 9999,
        "consumable": True,
        "createTile": 18,
    }


def _carpentry_plan(*, weird_twist: str = "Splinters become bounded secondary projectiles.") -> dict:
    return {
        "name": "Carpentry Blade",
        "tooltip": "A rough wooden blade that throws 3 secondary splinter projectiles on impact.",
        "concept": {
            "fantasy": "A wooden sword reinforced with the structural essence of a workbench.",
            "mergeLogic": "The sword supplies the attack and the workbench supplies wood and joinery.",
            "weirdTwist": weird_twist,
        },
        "runtimeContract": {
            "schema": "infini.runtime-contract.v2",
            "primaryVerb": "swing and release three bounded splinters",
            "controlStyle": "tap",
            "mechanicClaims": [{
                "claim": "A rough wooden blade that throws 3 secondary splinter projectiles on impact.",
                "backing": "spawn_secondary_projectiles count=3",
                "backingRefs": [{
                    "source": "engineCall",
                    "callIndex": 2,
                    "fn": "spawn_secondary_projectiles",
                    "field": "count",
                    "expected": 3,
                }],
                "status": "executable",
            }],
            "playerViewTimeline": ["blade held", "blade swings", "surface collision has no persistent field", "NPC hit releases three splinters", "splinters expire"],
            "executionStatus": "executable",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "melee",
                        "damage": 12,
                        "useTimeTicks": 24,
                        "useAnimationTicks": 24,
                        "knockback": 6,
                        "maxStack": 1,
                    },
                },
                {
                    "fn": "perform_melee_attack",
                    "params": {
                        "family": "broadsword",
                        "speed": 8,
                        "rangeTiles": 3,
                        "lifetimeTicks": 24,
                        "shotCount": 1,
                        "spreadRadians": 0,
                        "pierce": 1,
                        "projectileShape": "wooden broadsword",
                    },
                },
                {
                    "fn": "spawn_secondary_projectiles",
                    "params": {
                        "trigger": "on_hit",
                        "count": 3,
                        "damageMultiplier": 0.35,
                        "projectileShape": "wooden splinter",
                        "material": "wood",
                    },
                },
                {
                    "fn": "spawn_contact_particles",
                    "params": {"effect": "leaf", "amount": 10, "scale": 0.8, "material": "wood"},
                },
            ],
            "visualIntent": {
                "item": "A rough wooden plank sword with a blocky workbench-style guard.",
                "impact": "Wood chips and sawdust.",
                "vfxIntent": "Wood chips and sawdust on impact.",
                "vfxAvoid": "No magical glow or generic steel blade.",
            },
        },
        "visual": {"itemPrompt": "One rough wooden plank broadsword with visible joinery."},
    }


def _compiled_carpentry_item() -> dict:
    a = _wooden_sword()
    b = _workbench()
    ca = canonicalize(a)
    cb = canonicalize(b)
    data = validate_and_repair(_carpentry_plan(), a, b, ca, cb, "wood_workbench_live_regression")
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def _compiled_structural_carpentry_item() -> dict:
    a = _wooden_sword()
    b = _workbench()
    ca = canonicalize(a)
    cb = canonicalize(b)
    plan = _carpentry_plan()
    for index, call in enumerate(plan["runtimePlan"]["engineCalls"]):
        call["callId"] = ("item_stats", "primary_swing", "secondary_splinters", "contact_particles")[index]
    plan["concept"]["weirdTwist"] = {
        "text": "The blade releases bounded splinters.",
        "claimIds": ["splinter_release"],
    }
    plan["runtimeContract"] = {
        "schema": "infini.runtime-contract.v3",
        "signatureMode": "mechanic",
        "signatureClaimId": "splinter_release",
        "tooltipClaimIds": ["splinter_release"],
        "mechanicClaims": [{
            "claimId": "splinter_release",
            "playerText": "Throws 3 secondary splinter projectiles on impact.",
            "backingRefs": [{
                "source": "engineCall",
                "callId": "secondary_splinters",
                "field": "count",
                "expected": 3,
            }],
            "status": "executable",
        }],
        "playerViewTimeline": [
            {"phase": "use", "text": "The blade swings.", "claimIds": ["splinter_release"], "presentationOnly": False},
            {"phase": "travel", "text": "The blade travels.", "claimIds": ["splinter_release"], "presentationOnly": False},
            {"phase": "npc_hit", "text": "Three splinters release.", "claimIds": ["splinter_release"], "presentationOnly": False},
            {"phase": "expiry", "text": "The splinters expire.", "claimIds": ["splinter_release"], "presentationOnly": False},
        ],
        "unsupportedPromises": [],
        "executionStatus": "executable",
    }
    data = validate_and_repair(plan, a, b, ca, cb, "wood_workbench_structural_regression")
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def _contract_check_wood_workbench_keeps_visual_intent_out_of_attack_and_grounds_palette() -> None:
    data = _compiled_carpentry_item()

    assert data["visual"]["palette"] == ["brown", "tan", "dark_brown"]
    assert data["visual"]["vfxIntent"] == "Wood chips and sawdust on impact."
    assert data["visual"]["vfxAvoid"] == "No magical glow or generic steel blade."
    assert "vfxIntent" not in data["attack"]
    assert "vfxAvoid" not in data["attack"]

    # Legacy cache payloads are migrated narrowly; arbitrary unknown AttackSpec data
    # remains visible to the strict boundary instead of being silently discarded.
    data["attack"]["vfxIntent"] = "legacy sawdust"
    data["attack"]["vfxMaterialHints"] = ["wood", "sawdust"]
    project_attack_presentation_fields(data, source="test_legacy_cache")
    assert "vfxIntent" not in data["attack"]
    assert "vfxMaterialHints" not in data["attack"]
    assert data["visual"]["vfxIntent"] == "Wood chips and sawdust on impact."
    validate_executable_item_boundary(data)


def _contract_check_visual_kit_repairs_singleton_text_lists_without_leaking_invalid_raw_output(monkeypatch) -> None:
    parsed = validate_visual_kit_boundary({
        "qualityNotes": "Keep the wooden material readable.",
        "animationPlan": "short swing then sawdust impact",
        "vfxMaterialHints": "wood",
    })
    assert parsed["qualityNotes"] == ["Keep the wooden material readable."]
    assert parsed["animationPlan"] == ["short swing then sawdust impact"]
    assert parsed["vfxMaterialHints"] == ["wood"]
    with pytest.raises(ValidationError):
        validate_visual_kit_boundary({"qualityNotes": 42})
    with pytest.raises(ValueError, match="unknown roles"):
        validate_visual_kit_boundary({
            "bakedAssets": {"aura": {"mode": "particle_vfx"}},
        })

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "palette": ["brown", "tan", "dark brown"],
                "itemIconPrompt": "one rough wooden plank sword",
                "vfxIntent": "sawdust burst",
                "vfxAvoid": "no magic glow",
                "vfxMaterialHints": "wood",
                "qualityNotes": "Keep the wood grain readable.",
            }
        })}}]},
    )
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visualKit"]["qualityNotes"] == ["Keep the wood grain readable."]
    assert result["debug"]["visualDirectorBoundaryRepairs"] == [
        "vfxMaterialHints:string_to_singleton_list",
        "qualityNotes:string_to_singleton_list",
    ]
    assert result["visual"]["vfxIntent"] == "sawdust burst"
    assert "vfxIntent" not in result["attack"]
    assert "vfxAvoid" not in result["attack"]
    assert "vfxMaterialHints" not in result["attack"]


    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "itemIconPrompt": "one continuous bow stave with one taut string",
                "itemSilhouetteContract": "One stave forms one arc and one string joins its two tips.",
                "bakedAssets": {
                    "impact": {"mode": "particle_vfx", "distinctFromItem": True},
                    "child": {"mode": "none", "distinctFromItem": False},
                    "field": {"mode": "reuse_item_sprite", "reason": "invalid effect reuse"},
                },
            }
        })}}]},
    )
    repaired_data = _compiled_carpentry_item()
    repaired_result = VISUAL.apply_visual_director(repaired_data, _wooden_sword(), _workbench(), {}, {})
    assert repaired_result["debug"]["visualDirectorStatus"] == "validated_and_applied"
    assert repaired_result["visualKit"]["itemIconPrompt"]
    assert "distinctFromItem" not in repaired_result["visualKit"]["bakedAssets"]["impact"]
    assert "distinctFromItem" not in repaired_result["visualKit"]["bakedAssets"]["child"]
    assert "field" not in repaired_result["visualKit"]["bakedAssets"]
    assert "bakedAssets.impact.distinctFromItem:dropped_role_inapplicable" in repaired_result["debug"]["visualDirectorBoundaryRepairs"]
    assert "bakedAssets.child.distinctFromItem:dropped_role_inapplicable" in repaired_result["debug"]["visualDirectorBoundaryRepairs"]
    assert "bakedAssets.field:dropped_role_inapplicable_reuse_item_sprite" in repaired_result["debug"]["visualDirectorBoundaryRepairs"]

    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "itemSilhouetteContract": "THIS INVALID RAW CONTRACT MUST NOT LEAK",
                "qualityNotes": 42,
            }
        })}}]},
    )
    invalid_data = _compiled_carpentry_item()
    invalid_result = VISUAL.apply_visual_director(invalid_data, _wooden_sword(), _workbench(), {}, {})
    assert "visualKit" not in invalid_result
    assert "THIS INVALID RAW CONTRACT MUST NOT LEAK" not in json.dumps(invalid_result.get("visual") or {}, ensure_ascii=False)
    assert "THIS INVALID RAW CONTRACT MUST NOT LEAK" not in json.dumps(invalid_result.get("attack") or {}, ensure_ascii=False)
    assert "visualDirectorError" in invalid_result["debug"]
    assert "THIS INVALID RAW CONTRACT" in invalid_result["debug"]["visualDirectorRejectedRawOutput"]


def _contract_check_visual_director_traces_named_request_and_raw_response(monkeypatch) -> None:
    events: list[tuple] = []

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "visual-trace-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(VISUAL, "trace_event", lambda *args, **kwargs: events.append((args, kwargs)), raising=False)
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "palette": ["brown", "tan"],
                "itemIconPrompt": "one rough wooden plank sword with a square workbench guard",
                "vfxIntent": "short sawdust impact",
                "qualityNotes": ["Keep the wood grain readable."],
            }
        })}}]},
    )

    data = _compiled_carpentry_item()
    data["_llmHistory"] = {
        "kind": "attributed_planner_history_v1",
        "messages": [
            {"role": "system", "name": "item_author_contract", "content": "OLD_PLANNER_SYSTEM"},
            {"role": "user", "name": "recipe_context", "content": '{"recipe":"carpentry"}'},
            {"role": "assistant", "name": "item_planner", "content": '{"name":"Carpentry Blade"}'},
        ],
    }
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})

    assert result["debug"]["visualDirectorStatus"] == "validated_and_applied"
    prompt_event = next(row for row in events if row[0][0:2] == ("prompt", "LLM:visual_director"))
    response_event = next(row for row in events if row[0][0:2] == ("response", "LLM:visual_director"))
    assert [message["name"] for message in prompt_event[1]["prompt"]] == [
        "visual_director_contract",
        "visual_director_context",
    ]
    assert "authoritative current" in prompt_event[1]["prompt"][0]["content"].lower()
    assert "OLD_PLANNER_SYSTEM" not in prompt_event[1]["prompt"][0]["content"]
    visual_dossier = json.loads(prompt_event[1]["prompt"][-1]["content"])
    assert visual_dossier["item"]["name"] == "Carpentry Blade"
    assert visual_dossier["agentHandoff"]["artifactSource"] == "item"
    visual_rules = " ".join(visual_dossier["rules"]).lower()
    assert "floating ui" in visual_rules and "localized" in visual_rules
    assert "negativeprompt" in visual_rules and "must not contradict" in visual_rules
    assert "_llmHistory" not in prompt_event[1]["prompt"][-1]["content"]
    assert '"visualKit"' in response_event[1]["response"]


def _contract_check_promise_gate_blocks_fake_platform_and_damaging_field_but_keeps_real_children() -> None:
    platform = _carpentry_plan(
        weird_twist="On hit it creates temporary floating workbench platforms the player can stand on."
    )
    platform_gate = planner_runtime_promise_gate(platform)
    assert platform_gate["ok"] is False
    assert any(row["kind"] == "temporary_platform" for row in platform_gate["blockingClaims"])

    fake_field = _carpentry_plan(
        weird_twist="The splinters linger as a damaging field after the strike."
    )
    field_gate = planner_runtime_promise_gate(fake_field)
    assert field_gate["ok"] is False
    assert any(row["kind"] == "damaging_field" for row in field_gate["blockingClaims"])

    valid = _carpentry_plan(
        weird_twist="On hit it throws three bounded wooden splinter projectiles."
    )
    assert planner_runtime_promise_gate(valid)["ok"] is True


def _contract_check_promise_gate_requires_semantically_matching_ammo_executor() -> None:
    torch_claim = _carpentry_plan()
    torch_claim["tooltip"] = "Consumes torches as ammunition and fires an ignited bolt."
    torch_claim["runtimePlan"]["engineCalls"] = [
        {
            "fn": "set_item_stats",
            "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 8, "useTimeTicks": 28, "maxStack": 1, "ammoFor": "empty"},
        },
        {
            "fn": "fire_ranged_weapon",
            "params": {"family": "bow", "runtimeFamily": "shoot", "delivery": "shoot", "ammoFor": "empty", "projectileFamily": "fire_bolt"},
        },
    ]
    blocked = planner_runtime_promise_gate(torch_claim)
    assert blocked["ok"] is False
    assert any(row["kind"] == "ammo_consumption" for row in blocked["blockingClaims"])

    arrow_claim = copy.deepcopy(torch_claim)
    arrow_claim["tooltip"] = "Consumes arrows as ammunition."
    arrow_claim["runtimePlan"]["engineCalls"][0]["params"]["ammoFor"] = "arrow"
    arrow_claim["runtimePlan"]["engineCalls"][1]["params"]["ammoFor"] = "arrow"
    assert planner_runtime_promise_gate(arrow_claim)["ok"] is True

    no_ammo = copy.deepcopy(torch_claim)
    no_ammo["tooltip"] = "Does not consume ammo."
    assert planner_runtime_promise_gate(no_ammo)["ok"] is True

    contradictory = copy.deepcopy(arrow_claim)
    contradictory["tooltip"] = "Uses no arrows."
    contradictory_gate = planner_runtime_promise_gate(contradictory)
    assert contradictory_gate["ok"] is False
    assert any(row.get("kind") == "ammo_consumption" for row in contradictory_gate["blockingClaims"])

    cross_resource_truth = copy.deepcopy(arrow_claim)
    cross_resource_truth["tooltip"] = "Uses no bullets."
    assert planner_runtime_promise_gate(cross_resource_truth)["ok"] is True

    passive_negation = copy.deepcopy(arrow_claim)
    passive_negation["tooltip"] = "No ammo is consumed."
    passive_gate = planner_runtime_promise_gate(passive_negation)
    assert passive_gate["ok"] is False
    assert any(row.get("kind") == "ammo_consumption" for row in passive_gate["blockingClaims"])

    without_ammo = copy.deepcopy(arrow_claim)
    without_ammo["tooltip"] = "Fires without ammo."
    assert planner_runtime_promise_gate(without_ammo)["ok"] is False

    for truthful_custom_negation in (
        "Does not consume torches.",
        "Uses no torches.",
        "Fires without torches.",
    ):
        custom_negation = copy.deepcopy(arrow_claim)
        custom_negation["tooltip"] = truthful_custom_negation
        truth = validate_runtime_promises(custom_negation, {"ammoFor": "arrow"})
        ammo_claims = [claim for claim in truth["claims"] if claim.get("kind") == "ammo_consumption"]
        assert ammo_claims and all(claim.get("status") == "executable" for claim in ammo_claims)
        assert planner_runtime_promise_gate(custom_negation)["ok"] is True


def _contract_check_structural_reauthor_preserves_visual_slime_and_repeats_shape_rules(monkeypatch) -> None:
    valid = _carpentry_plan(
        weird_twist="The slime coating provides a slight, purely visual sheen to the weapon."
    )
    valid["tooltip"] = "A wooden sword coated in hardened slime."
    valid["concept"]["fantasy"] = (
        "A basic wooden sword permanently coated in a thick, sticky layer of slime."
    )
    for index, call in enumerate(valid["runtimePlan"]["engineCalls"]):
        call["callId"] = ("item_stats", "primary_swing", "secondary_splinters", "contact_particles")[index]
    valid["concept"]["weirdTwist"] = {
        "text": "The slime coating gives the splintering blade a visual sheen.",
        "claimIds": ["splinter_release"],
    }
    valid["runtimeContract"] = {
        "schema": "infini.runtime-contract.v3",
        "primaryVerb": "swing and release three bounded splinters",
        "controlStyle": "tap",
        "signatureMode": "mechanic",
        "signatureClaimId": "splinter_release",
        "tooltipClaimIds": ["splinter_release", "slime_sheen"],
        "mechanicClaims": [
            {
                "claimId": "splinter_release",
                "playerText": "Throws 3 secondary splinter projectiles on impact.",
                "backingRefs": [{
                    "source": "engineCall",
                    "callId": "secondary_splinters",
                    "field": "count",
                    "expected": 3,
                }],
                "status": "executable",
            },
            {
                "claimId": "slime_sheen",
                "playerText": "Coated in a hardened slime sheen.",
                "backingRefs": [],
                "status": "visual_only",
            },
        ],
        "playerViewTimeline": [
            {"phase": "use", "text": "The blade swings.", "claimIds": ["splinter_release"], "presentationOnly": False},
            {"phase": "travel", "text": "The slime sheen remains visible.", "claimIds": [], "presentationOnly": True},
            {"phase": "npc_hit", "text": "Three splinters release.", "claimIds": ["splinter_release"], "presentationOnly": False},
            {"phase": "expiry", "text": "The splinters expire.", "claimIds": ["splinter_release"], "presentationOnly": False},
        ],
        "unsupportedPromises": [],
        "executionStatus": "executable",
    }
    assert planner_runtime_promise_gate(valid, enforce_public_contract=True, require_structural_v3=True)["ok"] is True

    invalid = copy.deepcopy(valid)
    invalid["runtimeContract"]["mechanicClaims"][0]["backingRefs"][0]["field"] = "missingCount"
    blocked = planner_runtime_promise_gate(invalid, enforce_public_contract=True, require_structural_v3=True)
    assert blocked["ok"] is False
    assert any(row["kind"] == "authored_ref_unresolved" for row in blocked["blockingClaims"])

    author_payload = AUTHOR.build_llm_author_payload(
        _wooden_sword(), _workbench(), {}, {}, "wood_gel_runtime_archetype_shape"
    )
    assert isinstance(author_payload["requiredJsonShape"]["runtimeArchetype"], dict)

    requests: list[dict] = []
    responses = iter((invalid, valid))

    def fake_llm(req, timeout=None):
        requests.append(copy.deepcopy(req))
        return {
            "choices": [{"message": {"content": json.dumps(next(responses))}}],
            "_debug": {},
        }

    monkeypatch.setattr(AUTHOR, "USE_LLM", True)
    monkeypatch.setattr(AUTHOR, "resolve_llm_model", lambda: "promise-retry-test-model")
    monkeypatch.setattr(AUTHOR, "active_llm_provider", lambda: "local")
    monkeypatch.setattr(AUTHOR, "llm_chat_json", fake_llm)
    monkeypatch.setattr(AUTHOR, "trace_event", lambda *args, **kwargs: None)

    result = AUTHOR.try_llm_plan(
        _wooden_sword(), _workbench(), {}, {}, "wood_gel_promise_retry"
    )
    assert result is not None
    retry_packet = json.loads(requests[1]["messages"][-1]["content"])
    retry_rules = " ".join(retry_packet["requirements"]).lower()
    assert "at least 4" in retry_rules and "playerviewtimeline steps" in retry_rules


def _contract_check_flux2_preserves_authored_literal_workbench_prompt_without_code_material_router(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL_CONFIG, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL_CONFIG, "SDCPP_MODEL", "C:/models/flux-2-klein-4b-Q8_0.gguf")
    monkeypatch.setattr(VISUAL_CONFIG, "ZIMAGE_PROMPT_CONTRACT", "auto")

    data = _compiled_carpentry_item()
    prompt = normalize_asset_prompt(
        data,
        "item",
        "A thick wooden plank blade with a square workbench guard and one small iron nail.",
        48,
    )
    lower = prompt.lower()
    assert lower.startswith("a thick wooden plank blade")
    assert "foreground colors and materials use brown, tan, dark brown" in lower
    assert "thick wooden plank blade" in lower
    assert "square workbench guard" in lower
    assert "primary authored material:" not in lower
    assert "generic polished steel" not in lower
    assert "the complete item is fully visible" in lower
    assert "show only the item sprite" not in lower
    assert "palette: gray, white" not in lower


def _contract_check_strict_preflights_run_before_expensive_image_generation() -> None:
    source = inspect.getsource(COMBINE.combine)
    assert source.index("04c_strict_executable_preflight") < source.index("08_visual_director_asset_pack")
    assert source.index("08c_strict_executable_preflight") < source.index("08d_hybrid_vfx_manifest")
    assert source.index("08d_hybrid_vfx_manifest") < source.index("08e_visual_asset_runtime_gates")
    assert source.index("08e_visual_asset_runtime_gates") < source.index("08f_strict_visual_authoring_boundaries")
    assert source.index("08f_strict_visual_authoring_boundaries") < source.index("09_visual_asset_generation")
    assert source.index("11a_project_presentation_out_of_attack") < source.index("11b_strict_executable_boundary")


def _contract_check_visual_director_palette_policy_uses_provenance_not_material_semantics() -> None:
    fallback = _compiled_carpentry_item()
    assert fallback["debug"]["visualPaletteSource"] == "result_and_parent_grounding_tags"
    palette, policy = VISUAL._merge_visual_director_palette(
        fallback,
        fallback["visual"]["palette"],
        ["painted red", "brass"],
    )
    assert palette == ["painted red", "brass"]
    assert policy == "visual_director_authored"

    planner_authored = _carpentry_plan()
    planner_authored.setdefault("visual", {})["palette"] = ["painted blue", "white"]
    a = _wooden_sword()
    b = _workbench()
    ca = canonicalize(a)
    cb = canonicalize(b)
    planner_authored = validate_and_repair(planner_authored, a, b, ca, cb, "planner_palette")
    assert planner_authored["debug"]["visualPaletteSource"] == "planner_authored"
    palette, policy = VISUAL._merge_visual_director_palette(
        planner_authored,
        planner_authored["visual"]["palette"],
        ["orange", "black"],
    )
    assert palette == ["painted blue", "white", "orange", "black"]
    assert policy == "planner_authored_first"


def _contract_check_visual_anchor_and_palette_order_is_deterministic_without_fusion_policy() -> None:
    from infini_local.pipelines.result_identity_policy import palette_from, required_anchors_from_tags

    tags = {"workbench", "wood", "sword", "iron", "placeable"}
    assert required_anchors_from_tags(tags) == required_anchors_from_tags(set(reversed(sorted(tags))))
    assert palette_from(tags) == palette_from(set(reversed(sorted(tags))))
    assert "wooden work bench" in required_anchors_from_tags(tags)
    assert "crafting table" in required_anchors_from_tags(tags)


def _contract_check_invalid_cached_attack_contract_is_not_delivered() -> None:
    data = _compiled_carpentry_item()
    data["attack"]["futureImaginaryField"] = 1
    parent_a = _wooden_sword()
    parent_b = _workbench()
    assert COMBINE._cached_payload_passes_executable_boundary(
        data,
        recipe_key_value="bad-cache",
        source="test",
        parent_a=parent_a,
        parent_b=parent_b,
        canonical_a=canonicalize(parent_a),
        canonical_b=canonicalize(parent_b),
    ) is False


def _contract_check_visual_director_receives_planner_fusion_choice_without_code_rewrite(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")

    def fake_chat(req, timeout=None):
        captured.update(json.loads(req["messages"][1]["content"]))
        return {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "palette": ["brown", "tan"],
                "itemIconPrompt": "A whole workbench bolted sideways to a wooden sword, used as one absurd club-blade.",
                "itemSilhouetteContract": "The complete rectangular workbench remains visibly bolted to the sword blade.",
            }
        })}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", fake_chat)
    data = _compiled_carpentry_item()
    data["runtimePlan"]["sourceRolePreservation"] = {
        "itemA": "wooden sword remains the handle and striking spine",
        "itemB": "the complete workbench is bolted to the blade",
    }
    data["runtimePlan"]["visualIntent"]["item"] = "A whole workbench bolted to the sword."
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})

    assert captured["item"]["sourceRolePreservation"]["itemB"] == "the complete workbench is bolted to the blade"
    assert captured["item"]["plannerVisualIntent"]["item"] == "A whole workbench bolted to the sword."
    assert "whole workbench bolted" in result["visual"]["imagePrompt"].lower()
    assert "complete rectangular workbench" in result["visual"]["itemSilhouetteContract"].lower()


def _contract_check_prompt_cleanup_preserves_texture_and_grounded_words() -> None:
    cleaned = strip_conflicting_sprite_prompt_bits(
        "rough wooden texture, grounded crystal spike, rune mark on ground, cracked floor decal, clock hands, miniature room inside a glass orb, landscape painted on a shield, no text, black background"
    )
    assert "rough wooden texture" in cleaned
    assert "grounded crystal spike" in cleaned
    assert "rune mark on ground" in cleaned
    assert "cracked floor decal" in cleaned
    assert "clock hands" in cleaned
    assert "miniature room inside a glass orb" in cleaned
    assert "landscape painted on a shield" in cleaned
    assert "no text" not in cleaned
    assert "black background" not in cleaned


def _contract_check_visual_director_projection_is_fully_transactional_on_late_failure(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "palette": ["brown", "tan"],
                "itemIconPrompt": "whole workbench bolted to a wooden sword",
                "itemSilhouetteContract": "complete workbench remains visible",
            }
        })}}]},
    )
    monkeypatch.setattr(
        VISUAL,
        "_merge_visual_director_palette",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("late projection failure")),
    )

    data = _compiled_carpentry_item()
    data["visualKit"] = {"itemIconPrompt": "previous validated prompt"}
    before_visual = copy.deepcopy(data["visual"])
    before_attack = copy.deepcopy(data["attack"])
    before_kit = copy.deepcopy(data["visualKit"])

    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visual"] == before_visual
    assert result["attack"] == before_attack
    assert result["visualKit"] == before_kit
    assert result["debug"]["visualDirectorStatus"] == "rejected_fallback_to_existing_visual"
    assert "late projection failure" in result["debug"]["visualDirectorError"]


def _contract_check_visual_director_payload_contains_raw_parent_facts_and_real_schema(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "image_backend_uses_semantic_prompt_contract", lambda: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")

    def fake_chat(req, timeout=None):
        captured["request"] = req
        return {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "itemIconPrompt": "a whole workbench bolted to a wooden sword",
                "itemSilhouetteContract": "the complete workbench remains attached",
            }
        })}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", fake_chat)
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visual"]["imagePrompt"] == "a whole workbench bolted to a wooden sword"

    req = captured["request"]
    payload = json.loads(req["messages"][1]["content"])
    parents = payload["item"]["parents"]
    assert parents[0]["rawFacts"]["internalName"] == "WoodenSword"
    assert parents[1]["rawFacts"]["createTile"] == 18
    assert "fusionRecommendation" not in json.dumps(parents)
    rules = " ".join(payload["rules"]).casefold()
    system_prompt = req["messages"][0]["content"].casefold()
    assert "physical class and count" in rules
    assert "functional parts and how they connect" in rules
    assert "loose list of nouns" in rules
    assert "materials and base colors" in rules
    assert "literal, attached, fused, disassembled" not in rules
    assert "functional parts" in system_prompt
    baked_guide = payload["fieldGuide"]["bakedAssets"].casefold()
    assert "projectile-only" in baked_guide
    assert "impact, child, and field" in baked_guide

    response_format = req["response_format"]
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["visualKit"]
    baked_properties = schema["$defs"]["BakedAssetBoundary"]["properties"]
    mode_schema = baked_properties["mode"]
    assert set(mode_schema["enum"]) == {"baked_sprite", "particle_vfx", "reuse_item_sprite", "none"}
    assert "prompt" not in baked_properties
    baked_schema = schema["properties"]["visualKit"]["properties"]["bakedAssets"]
    assert baked_schema["additionalProperties"] is False
    assert set(baked_schema["properties"]) == {"projectile", "impact", "child", "field"}


def _contract_check_code_parent_anchors_are_context_not_mandatory_authored_anchors() -> None:
    data = _compiled_carpentry_item()
    visual = data["visual"]
    assert visual["requiredAnchors"] == []
    assert "wooden work bench" in visual["parentVisualContext"]
    assert data["debug"]["visualRequiredAnchorsSource"] == "none"


def _contract_check_runtime_multishot_does_not_rewrite_authored_projectile_topology(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL_CONFIG, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL_CONFIG, "SDCPP_MODEL", "C:/models/flux-2-klein-4b-Q8_0.gguf")
    monkeypatch.setattr(VISUAL_CONFIG, "ZIMAGE_PROMPT_CONTRACT", "auto")
    data = _compiled_carpentry_item()
    data["attack"]["shotCount"] = 2
    prompt = normalize_asset_prompt(
        data,
        "projectile",
        "two linked wooden blades rotating as one connected projectile body",
        48,
    )
    assert "two linked wooden blades" in prompt.lower()
    assert "one connected projectile body" in prompt.lower()


def _contract_check_empty_visual_kit_is_rejected_without_erasing_existing_visual(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": '{"visualKit": {}}'}}]},
    )
    data = _compiled_carpentry_item()
    before = copy.deepcopy(data["visual"])
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visual"] == before
    assert "visualKit" not in result
    assert "no authored visual decision" in result["debug"]["visualDirectorError"]



def _contract_check_visual_director_remote_auto_mode_uses_real_schema_with_safe_transport_fallback(monkeypatch) -> None:
    monkeypatch.setattr(LLM_TRANSPORT, "LLM_RESPONSE_FORMAT_MODE", "auto")
    monkeypatch.setattr(LLM_TRANSPORT, "active_llm_provider", lambda _context=None: "openai_compat")
    schema = {"type": "object", "additionalProperties": False}
    result = LLM_TRANSPORT.llm_json_response_format("visual_test", schema=schema, strict=True)
    assert result == {
        "type": "json_schema",
        "json_schema": {"name": "visual_test", "strict": True, "schema": schema},
    }


def _contract_check_visual_director_legacy_silhouette_alias_and_negative_prompt_are_shape_migrated(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "shapeContract": "whole workbench remains attached to the blade",
                "itemIconPrompt": "whole workbench attached to a wooden sword",
                "negativePrompt": "text, watermark, room background",
            }
        })}}]},
    )
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visualKit"]["itemSilhouetteContract"] == "whole workbench remains attached to the blade"
    assert "shapeContract:moved_to_itemSilhouetteContract" in result["debug"]["visualDirectorBoundaryRepairs"]
    assert result["visual"]["negativePrompt"] == "text, watermark, room background"


def _contract_check_visual_director_shared_style_reaches_every_asset_prompt(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL_CONFIG, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL_CONFIG, "SDCPP_MODEL", "C:/models/flux-2-klein-4b-Q8_0.gguf")
    monkeypatch.setattr(VISUAL_CONFIG, "ZIMAGE_PROMPT_CONTRACT", "auto")
    data = _compiled_carpentry_item()
    data["visualKit"] = {"styleGuide": "rough chunky carpentry shapes with visible nail heads"}
    data["visual"]["styleGuide"] = data["visualKit"]["styleGuide"]
    for role, prompt in [
        ("item", "whole workbench attached to a wooden sword"),
        ("projectile", "one wooden splinter body"),
        ("impact", "sawdust and wood-chip burst"),
    ]:
        normalized = normalize_asset_prompt(data, role, prompt, 48)
        assert "rough chunky carpentry shapes with visible nail heads" in normalized.lower()


def _contract_check_field_asset_gate_runs_after_manifest_and_keeps_consumable_authored_sprite() -> None:
    data = _compiled_carpentry_item()
    data["visualKit"] = {
        "fieldSpritePrompt": "one persistent sawdust workbench-rune decal",
        "bakedAssets": {
            "field": {
                "mode": "baked_sprite",
                "reason": "field slot consumes the decal",
            }
        },
    }
    data["vfxManifest"] = {
        "slots": [
            {
                "event": "hit",
                "stage": "field",
                "rendererKind": "fieldSprite",
                "textureRole": "field",
            }
        ]
    }
    ASSET_PLAN.finalize_visual_asset_runtime_gates(data)
    assert data["visualKit"]["bakedAssets"]["field"]["mode"] == "baked_sprite"


def _contract_check_visual_parent_context_is_bounded_without_semantic_rewrite() -> None:
    from infini_local.pipelines.visual_director_contract import compact_visual_parent_card

    parent = {
        "name": "Generated parent",
        "generatedData": {
            "visual": {
                "imagePrompt": "whole literal workbench " + ("x" * 5000),
                "requiredAnchors": [f"anchor-{i}" for i in range(40)],
            }
        },
    }
    card = compact_visual_parent_card(parent)
    authored = card["previouslyAuthoredVisual"]
    assert authored["imagePrompt"].startswith("whole literal workbench")
    assert len(authored["imagePrompt"]) <= 900
    assert len(authored["requiredAnchors"]) == 12



def _contract_check_visual_director_context_does_not_present_code_fallback_prompt_as_authored() -> None:
    from infini_local.pipelines.visual_director_contract import visual_director_context

    data = _compiled_carpentry_item()
    data["canonical"] = {
        "headNoun": "sword-workbench hybrid",
        "shapeAnchors": ["wooden sword", "complete workbench", "bolted joint"],
        "hardTags": ["literal fusion"],
    }
    data["visual"].update({
        "itemPrompt": "A whole workbench bolted to a wooden sword.",
        "imagePrompt": "pixel art inventory icon with a long code-generated technical wrapper",
    })
    data["debug"]["visualPromptSource"] = "code_fallback"
    context = visual_director_context(data, _wooden_sword(), _workbench())
    assert context["finalIdentity"] == {
        "resultKind": "weapon",
        "headNoun": "sword-workbench hybrid",
        "shapeAnchors": ["wooden sword", "complete workbench", "bolted joint"],
        "hardTags": ["literal fusion"],
    }
    assert context["existingVisual"]["itemPrompt"] == "A whole workbench bolted to a wooden sword."
    assert "imagePrompt" not in context["existingVisual"]

    data["debug"]["visualPromptSource"] = "planner_authored"
    authored_context = visual_director_context(data, _wooden_sword(), _workbench())
    assert authored_context["existingVisual"]["imagePrompt"].startswith("pixel art inventory icon")



def _contract_check_visual_director_legacy_baked_prompt_migrates_to_single_role_prompt(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "bakedAssets": {
                    "impact": {"mode": "baked_sprite", "prompt": "wood chips and sawdust burst"}
                }
            }
        })}}]},
    )
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visualKit"]["impactSpritePrompt"].startswith("wood chips and sawdust burst")
    assert "prompt" not in result["visualKit"]["bakedAssets"]["impact"]
    assert "bakedAssets.impact.prompt:moved_to_impactSpritePrompt" in result["debug"]["visualDirectorBoundaryRepairs"]


def _contract_check_visual_authoring_boundary_canonicalizes_legacy_prompt_and_rejects_unknown_nested_fields() -> None:
    normalized = validate_visual_authoring_boundaries({
        "visualKit": {
            "bakedAssets": {
                "impact": {
                    "mode": "baked_sprite",
                    "prompt": "literal authored wood-chip burst",
                }
            }
        }
    })
    kit = normalized["visualKit"]
    assert kit["impactSpritePrompt"] == "literal authored wood-chip burst"
    assert "prompt" not in kit["bakedAssets"]["impact"]

    with pytest.raises(ValidationError):
        validate_visual_authoring_boundaries({
            "visualKit": {
                "bakedAssets": {
                    "impact": {"mode": "baked_sprite", "futureRenderer": "unknown"}
                }
            }
        })
    with pytest.raises(ValidationError):
        validate_visual_authoring_boundaries({
            "vfxManifest": {
                "slots": [{"futureRenderer": "unknown"}]
            }
        })


def _contract_check_cached_payload_uses_same_visual_authoring_boundaries_as_fresh_combine() -> None:
    parent_a = _wooden_sword()
    parent_b = _workbench()
    cache_parent_args = {
        "parent_a": parent_a,
        "parent_b": parent_b,
        "canonical_a": canonicalize(parent_a),
        "canonical_b": canonicalize(parent_b),
    }
    legacy = _compiled_carpentry_item()
    assert not COMBINE._cached_payload_passes_executable_boundary(
        legacy,
        recipe_key_value="cache_structural_v2_rejected",
        source="test",
        **cache_parent_args,
    )
    fake_v3 = copy.deepcopy(legacy)
    fake_v3["runtimeContract"] = {"schema": "infini.runtime-contract.v3"}
    assert not COMBINE._cached_payload_passes_executable_boundary(
        fake_v3,
        recipe_key_value="cache_empty_structural_v3_rejected",
        source="test",
        **cache_parent_args,
    )

    data = _compiled_structural_carpentry_item()
    data["visualKit"] = {
        "bakedAssets": {
            "impact": {
                "mode": "baked_sprite",
                "prompt": "legacy sawdust burst",
            }
        }
    }
    assert COMBINE._cached_payload_passes_executable_boundary(
        data,
        recipe_key_value="cache_visual_migration",
        source="test",
        **cache_parent_args,
    )
    assert data["visualKit"]["impactSpritePrompt"] == "legacy sawdust burst"
    assert "prompt" not in data["visualKit"]["bakedAssets"]["impact"]

    broken_kit = _compiled_structural_carpentry_item()
    broken_kit["visualKit"] = {"bakedAssets": {"impact": {"mode": "magic_png"}}}
    assert not COMBINE._cached_payload_passes_executable_boundary(
        broken_kit,
        recipe_key_value="cache_visual_invalid",
        source="test",
        **cache_parent_args,
    )

    broken_manifest = _compiled_structural_carpentry_item()
    broken_manifest["vfxManifest"] = {"slots": [{"futureRenderer": "unknown"}]}
    assert not COMBINE._cached_payload_passes_executable_boundary(
        broken_manifest,
        recipe_key_value="cache_vfx_invalid",
        source="test",
        **cache_parent_args,
    )


def _contract_check_visual_asset_gate_debug_is_recomputed_not_left_stale() -> None:
    data = _compiled_carpentry_item()
    data["visualKit"] = {
        "bakedAssets": {"projectile": {"mode": "baked_sprite"}}
    }
    ASSET_PLAN.finalize_visual_asset_runtime_gates(data)
    assert "visualAssetRuntimeGates" in data["debug"]

    data["visualKit"] = {
        "bakedAssets": {"impact": {"mode": "particle_vfx"}}
    }
    ASSET_PLAN.finalize_visual_asset_runtime_gates(data)
    assert "visualAssetRuntimeGates" not in data["debug"]


def _contract_check_baked_asset_mode_requires_a_real_authored_prompt_before_image_generation() -> None:
    data = _compiled_carpentry_item()
    data["visual"].pop("impactImagePrompt", None)
    data["attack"].pop("impactSpritePrompt", None)
    data["visualKit"] = {"bakedAssets": {"impact": {"mode": "baked_sprite"}}}
    with pytest.raises(ValueError, match="baked_sprite requires an authored role prompt"):
        validate_visual_authoring_boundaries(data)

    data["visualKit"]["impactSpritePrompt"] = "literal authored sawdust burst"
    normalized = validate_visual_authoring_boundaries(data)
    assert normalized["visualKit"]["impactSpritePrompt"] == "literal authored sawdust burst"


def _contract_check_nonfatal_generated_optional_sprite_remains_deliverable_with_warning(tmp_path) -> None:
    from infini_local.pipelines import visual_delivery_gate as DELIVERY

    sprite = tmp_path / "impact.png"
    sprite.write_bytes(b"not-decoded-here")
    data = _compiled_carpentry_item()
    data["attack"].update({
        "impactSpriteStatus": "generated_warn_invalid",
        "impactSpritePath": str(sprite),
    })
    report = DELIVERY.visual_delivery_report(data, check_backend_config=False)
    impact = next(row for row in report["slots"] if row["role"] == "impact")
    assert impact["usable"] is True
    assert any(row["code"] == "impact_sprite_generated_warn_invalid" for row in report["warnings"])


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_242_live_generation_regressions_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_wood_workbench_keeps_visual_intent_out_of_attack_and_grounds_palette',
            '_contract_check_visual_kit_repairs_singleton_text_lists_without_leaking_invalid_raw_output',
            '_contract_check_visual_director_traces_named_request_and_raw_response',
            '_contract_check_promise_gate_blocks_fake_platform_and_damaging_field_but_keeps_real_children',
            '_contract_check_promise_gate_requires_semantically_matching_ammo_executor',
            '_contract_check_structural_reauthor_preserves_visual_slime_and_repeats_shape_rules',
            '_contract_check_flux2_preserves_authored_literal_workbench_prompt_without_code_material_router',
            '_contract_check_strict_preflights_run_before_expensive_image_generation',
            '_contract_check_visual_director_palette_policy_uses_provenance_not_material_semantics',
            '_contract_check_visual_anchor_and_palette_order_is_deterministic_without_fusion_policy',
            '_contract_check_invalid_cached_attack_contract_is_not_delivered',
            '_contract_check_visual_director_receives_planner_fusion_choice_without_code_rewrite',
            '_contract_check_prompt_cleanup_preserves_texture_and_grounded_words',
            '_contract_check_visual_director_projection_is_fully_transactional_on_late_failure',
            '_contract_check_visual_director_payload_contains_raw_parent_facts_and_real_schema',
            '_contract_check_code_parent_anchors_are_context_not_mandatory_authored_anchors',
            '_contract_check_runtime_multishot_does_not_rewrite_authored_projectile_topology',
            '_contract_check_empty_visual_kit_is_rejected_without_erasing_existing_visual',
            '_contract_check_visual_director_remote_auto_mode_uses_real_schema_with_safe_transport_fallback',
            '_contract_check_visual_director_legacy_silhouette_alias_and_negative_prompt_are_shape_migrated',
            '_contract_check_visual_director_shared_style_reaches_every_asset_prompt',
            '_contract_check_field_asset_gate_runs_after_manifest_and_keeps_consumable_authored_sprite',
            '_contract_check_visual_parent_context_is_bounded_without_semantic_rewrite',
            '_contract_check_visual_director_context_does_not_present_code_fallback_prompt_as_authored',
            '_contract_check_visual_director_legacy_baked_prompt_migrates_to_single_role_prompt',
            '_contract_check_visual_authoring_boundary_canonicalizes_legacy_prompt_and_rejects_unknown_nested_fields',
            '_contract_check_cached_payload_uses_same_visual_authoring_boundaries_as_fresh_combine',
            '_contract_check_visual_asset_gate_debug_is_recomputed_not_left_stale',
            '_contract_check_baked_asset_mode_requires_a_real_authored_prompt_before_image_generation',
            '_contract_check_nonfatal_generated_optional_sprite_remains_deliverable_with_warning',
        ),
    )
