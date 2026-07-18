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


def _carpentry_plan() -> dict:
    return {
        "name": "Carpentry Blade",
        "concept": {
            "fantasy": "A wooden sword reinforced with the structural essence of a workbench.",
            "mergeLogic": "The sword supplies the attack and the workbench supplies wood and joinery.",
            "coreMechanic": "A heavy wooden slash releases three bounded splinters on hit.",
        },
        "runtimeContract": {
            "primaryVerb": "swing",
            "controlStyle": "tap",
            "playerViewTimeline": [
                {"phase": "use", "description": "The player makes a heavy wooden slash."},
                {"phase": "hit", "description": "Three splinters release from the impact."},
            ],
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "runtimeStateIntent": "No persistent state.",
            "sourceReading": "Sword blade and workbench joinery remain literal physical parts.",
            "balanceIntent": "One finite melee swing and three low-damage splinters per hit.",
            "anomalyFlags": [],
            "sourceRolePreservation": {"itemA": "wooden blade", "itemB": "workbench joinery"},
            "engineCalls": [
                {
                    "callId": "item_stats",
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
                    "callId": "primary_swing",
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
                    "callId": "secondary_splinters",
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
                    "callId": "contact_particles",
                    "fn": "spawn_contact_particles",
                    "params": {"effect": "leaf", "amount": 10, "scale": 0.8, "material": "wood"},
                },
            ],
            "visualIntent": {
                "item": "A rough wooden plank sword with a blocky workbench-style guard.",
                "topology": "connected",
                "parts": ["wooden plank blade", "workbench-style guard", "iron nail"],
                "arrangement": "The guard crosses and touches the lower blade; the nail pins the joint.",
                "projectile": "Three short wooden splinters.",
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
    data = validate_and_repair(_carpentry_plan(), a, b, ca, cb, "wood_workbench_structural_regression")
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def _contract_check_wood_workbench_keeps_visual_intent_out_of_attack_without_code_palette() -> None:
    from infini_local.pipelines.visual_director_contract import visual_director_context

    data = _compiled_carpentry_item()

    assert data["visual"]["palette"] == []
    context = visual_director_context(data, _wooden_sword(), _workbench())
    assert context["parents"][0]["rawFacts"]["internalName"] == "WoodenSword"
    assert context["parents"][1]["rawFacts"]["internalName"] == "WorkBench"
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


def _contract_check_visual_kit_rejects_singleton_text_aliases_without_leaking_invalid_raw_output(monkeypatch) -> None:
    with pytest.raises(ValidationError):
        validate_visual_kit_boundary({
            "qualityNotes": "Keep the wooden material readable.",
            "animationPlan": "short swing then sawdust impact",
            "vfxMaterialHints": "wood",
        })
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
                "vfxMaterialHints": ["wood"],
                "qualityNotes": ["Keep the wood grain readable."],
            }
        })}}]},
    )
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visualKit"]["qualityNotes"] == ["Keep the wood grain readable."]
    assert result["debug"].get("visualDirectorBoundaryRepairs") in (None, [])
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
    repaired = VISUAL.apply_visual_director(repaired_data, _wooden_sword(), _workbench(), {}, {})
    assert repaired is repaired_data
    assert repaired_data["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert "visualKit" not in repaired_data

    invalid_live_shape = {
        "itemIconPrompt": "one rope-bound blade",
        "bakedAssets": {"projectile": "baked_sprite", "vfx": "particle_vfx"},
    }
    valid_typed_replacement = {
        "visualKit": {
            "itemIconPrompt": "one rope-bound blade",
            "projectileSpritePrompt": "one rope-bound blade in flight",
            "bakedAssets": {
                "projectile": {"mode": "baked_sprite", "reason": "distinct in-flight pose", "distinctFromItem": True},
            },
        },
    }
    retry_requests: list[dict] = []
    retry_responses = iter((invalid_live_shape, valid_typed_replacement))

    def invalid_then_valid(req, timeout=None):
        retry_requests.append(req)
        return {"choices": [{"message": {"content": json.dumps(next(retry_responses))}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", invalid_then_valid)
    retried_data = _compiled_carpentry_item()
    retried_result = VISUAL.apply_visual_director(retried_data, _wooden_sword(), _workbench(), {}, {})
    assert retried_result["debug"]["visualDirectorStatus"] == "validated_and_applied"
    assert retried_result["debug"]["visualDirectorRetryCount"] == 1
    assert retried_result["visualKit"]["bakedAssets"]["projectile"]["mode"] == "baked_sprite"
    assert len(retry_requests) == 2
    correction = json.loads(retry_requests[1]["messages"][-1]["content"])
    assert correction["task"].startswith("Replace your invalid Visual Director response")
    assert correction["requiredSchema"]["type"] == "object"

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
    assert invalid_result is invalid_data
    assert "visualKit" not in invalid_data
    assert "THIS INVALID RAW CONTRACT MUST NOT LEAK" not in json.dumps(invalid_data.get("visual") or {}, ensure_ascii=False)
    assert "THIS INVALID RAW CONTRACT MUST NOT LEAK" not in json.dumps(invalid_data.get("attack") or {}, ensure_ascii=False)
    assert invalid_data["debug"]["visualDirectorStatus"] == "visual_director_degraded"

    retry_transport_calls = 0

    def invalid_then_transport_failure(_req, timeout=None):
        nonlocal retry_transport_calls
        retry_transport_calls += 1
        if retry_transport_calls == 1:
            return {"choices": [{"message": {"content": json.dumps(invalid_live_shape)}}]}
        raise RuntimeError("visual retry transport failed")

    monkeypatch.setattr(VISUAL, "llm_chat_json", invalid_then_transport_failure)
    transport_failure_data = _compiled_carpentry_item()
    transport_failure_result = VISUAL.apply_visual_director(
        transport_failure_data, _wooden_sword(), _workbench(), {}, {},
    )
    assert transport_failure_result is transport_failure_data
    assert transport_failure_data["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert "visual retry transport failed" in transport_failure_data["debug"]["visualDirectorError"]
    assert retry_transport_calls == 2
    assert "visualKit" not in transport_failure_data


def _contract_check_initial_visual_director_request_enforces_root_and_baked_role_boundary_without_retry(monkeypatch) -> None:
    requests: list[dict] = []
    required_phrase = 'root object must contain exactly one key named "visualkit"'
    baked_role_phrase = "bakedassets may contain only projectile, impact, child, and field; never item"
    flat_field_phrase = (
        "role prompt and vfx fields belong directly inside visualkit; "
        "never inside bakedassets and never inside a vfx object"
    )

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "visual-root-contract-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")

    def wrapper_sensitive_visual_model(req, timeout=None):
        del timeout
        requests.append(copy.deepcopy(req))
        request_text = "\n".join(
            str(message.get("content") or "")
            for message in req.get("messages") or []
            if isinstance(message, dict)
        ).casefold()
        kit: dict[str, object] = {"itemIconPrompt": "one connected copper crescent tool"}
        if baked_role_phrase not in request_text:
            kit["bakedAssets"] = {"item": {"mode": "baked_sprite"}}
        elif flat_field_phrase not in request_text:
            kit["bakedAssets"] = {
                "projectile": {
                    "mode": "baked_sprite",
                    "projectileSpritePrompt": "one copper crescent projectile",
                }
            }
            kit["vfx"] = {"projectileVfx": "short copper spark trail"}
        content = {"visualKit": kit} if required_phrase in request_text else kit
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", wrapper_sensitive_visual_model)
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})

    assert result["debug"]["visualDirectorStatus"] == "validated_and_applied"
    assert result["debug"]["visualDirectorRetryCount"] == 0
    assert len(requests) == 1
    initial_text = "\n".join(
        str(message.get("content") or "") for message in requests[0]["messages"]
    ).casefold()
    assert required_phrase in initial_text
    assert baked_role_phrase in initial_text
    assert flat_field_phrase in initial_text
    schema = requests[0]["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["visualKit"]
    assert schema["additionalProperties"] is False


def _contract_check_visual_director_retries_extra_root_sibling(monkeypatch) -> None:
    requests: list[dict] = []
    responses = iter((
        {
            "visualKit": {"itemIconPrompt": "one connected copper crescent tool"},
            "extraField": "must not be silently ignored",
        },
        {"visualKit": {"itemIconPrompt": "one connected copper crescent tool"}},
    ))

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "visual-exact-root-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")

    def extra_root_then_exact(req, timeout=None):
        del timeout
        requests.append(copy.deepcopy(req))
        return {"choices": [{"message": {"content": json.dumps(next(responses))}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", extra_root_then_exact)
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})

    assert result["debug"]["visualDirectorStatus"] == "validated_and_applied"
    assert result["debug"]["visualDirectorRetryCount"] == 1
    assert len(requests) == 2
    correction = json.loads(requests[1]["messages"][-1]["content"])
    assert "exactly ['visualKit']" in correction["validationError"]


def _contract_check_baked_role_requires_canonical_visual_kit_prompt_not_legacy_mirror() -> None:
    data = _compiled_carpentry_item()
    data["visual"]["projectileImagePrompt"] = "legacy visual mirror must not satisfy a new baked decision"
    data["attack"]["projectileSpritePrompt"] = "legacy attack mirror must not satisfy a new baked decision"
    kit: dict[str, object] = {
        "bakedAssets": {
            "projectile": {
                "mode": "baked_sprite",
                "reason": "new distinct projectile body",
                "distinctFromItem": True,
            }
        }
    }

    assert VISUAL.visual_kit_projection_errors(kit, data) == [
        "bakedAssets.projectile: mode=baked_sprite requires a role prompt"
    ]
    kit["projectileSpritePrompt"] = "one newly authored copper crescent projectile"
    assert VISUAL.visual_kit_projection_errors(kit, data) == []


def _contract_check_visual_director_role_contract_reaches_every_canonical_asset_slot(monkeypatch) -> None:
    requests: list[dict] = []
    role_prompts = {
        "item": "one connected bronze launcher with a cyan core",
        "projectile": "one cyan bronze dart in right-facing flight",
        "impact": "one compact cyan bronze impact star",
        "child": "one small cyan bronze child mote body",
        "field": "one circular cyan bronze field rune decal",
    }
    role_prompt_fields = {
        "item": "itemIconPrompt",
        "projectile": "projectileSpritePrompt",
        "impact": "impactSpritePrompt",
        "child": "childSpritePrompt",
        "field": "fieldSpritePrompt",
    }

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "visual-role-contract-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_CHILD_FIELD_IMAGES", True)

    full_kit = {
        **{field: role_prompts[role] for role, field in role_prompt_fields.items()},
        "bakedAssets": {
            "projectile": {"mode": "baked_sprite", "reason": "distinct moving body", "distinctFromItem": True},
            "impact": {"mode": "baked_sprite", "reason": "persistent authored impact decal"},
            "child": {"mode": "baked_sprite", "reason": "compiled child body"},
            "field": {"mode": "baked_sprite", "reason": "compiled persistent field decal"},
        },
        "projectileVfx": "short cyan dart streak",
        "impactVfx": "compact bronze chip burst",
        "childVfx": "one restrained cyan child trail",
        "fieldVfx": "slow circular field pulse",
    }

    def full_role_visual_model(req, timeout=None):
        del timeout
        requests.append(copy.deepcopy(req))
        return {"choices": [{"message": {"content": json.dumps({"visualKit": full_kit})}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", full_role_visual_model)
    data = _compiled_carpentry_item()
    data["attack"].update({
        "enabled": True,
        "runtimeFamily": "shoot",
        "delivery": "shoot",
        "maxChildProjectiles": 1,
        "vfxFieldRadiusTiles": 4,
        "vfxFieldLifetimeTicks": 90,
    })
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})

    dossier = json.loads(requests[0]["messages"][1]["content"])
    output_contract = dossier["outputContract"]
    assert output_contract["rootKey"] == "visualKit"
    for role, field in role_prompt_fields.items():
        assert output_contract["roleFields"][role]["promptField"] == field
    attack_facts = dossier["item"]["attackFacts"]
    assert attack_facts["maxChildProjectiles"] == 1
    assert attack_facts["vfxFieldRadiusTiles"] == 4
    assert attack_facts["vfxFieldLifetimeTicks"] == 90

    assert result["debug"]["visualDirectorRetryCount"] == 0
    assert role_prompts["item"] in result["visual"]["imagePrompt"]
    for role, field in role_prompt_fields.items():
        assert role_prompts[role] in result["visualKit"][field]
    for role in ("projectile", "impact", "child", "field"):
        assert result["visualKit"]["bakedAssets"][role]["mode"] == "baked_sprite"
        assert result["visual"][f"{role}Vfx"] == full_kit[f"{role}Vfx"]

    plan_by_role = {row["role"]: row for row in ASSET_PLAN.build_visual_asset_plan(result)}
    assert set(plan_by_role) == {"item", "projectile", "impact", "child", "field"}
    assert role_prompts["item"] in plan_by_role["item"]["prompt"]
    for role in ("projectile", "impact", "child", "field"):
        assert plan_by_role[role]["assetMode"] == "baked_sprite"
        assert role_prompts[role] in plan_by_role[role]["prompt"]


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


def _contract_check_initial_author_does_not_run_its_own_structural_retry(monkeypatch) -> None:
    source = _carpentry_plan()
    calls = copy.deepcopy(source["runtimePlan"]["engineCalls"])
    valid = {
        "name": "Hardened Slime Splinterblade",
        "category": "weapon",
        "concept": {
            "fantasy": "A wooden sword permanently coated in a thick slime sheen.",
            "mergeLogic": "The wooden blade supplies the body while the slime hardens its surface.",
            "coreMechanic": "Swings the blade and releases three bounded wooden splinters on hit.",
        },
        "runtimeContract": {
            "primaryVerb": "swing",
            "controlStyle": "tap",
            "playerViewTimeline": [
                {"phase": "use", "description": "The coated blade swings."},
                {"phase": "npc_hit", "description": "Three wooden splinters release."},
            ],
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "sourceRolePreservation": {"itemA": "wooden blade body", "itemB": "hardened slime coating"},
            "engineCalls": calls,
            "runtimeStateIntent": "No persistent state.",
            "visualIntent": {
                "item": "Wooden sword with a hardened translucent slime coating.",
                "projectile": "Wooden splinter projectile.",
                "impact": "Wood chips and slime droplets.",
                "vfxIntent": "A slight slime sheen and bounded impact droplets.",
                "vfxAvoid": "No beam or laser.",
                "topology": "connected",
                "parts": ["wooden sword", "hardened slime coating"],
                "arrangement": "slime coating wrapped directly around the blade",
            },
            "sourceReading": "Wood supplies the blade; slime supplies the coating.",
            "balanceIntent": "Normal melee cadence and three bounded secondary splinters.",
            "anomalyFlags": [],
        },
    }
    assert planner_runtime_promise_gate(copy.deepcopy(valid))["ok"] is True

    author_payload = AUTHOR.build_llm_author_payload(
        _wooden_sword(), _workbench(), {}, {}, "wood_gel_runtime_shape"
    )
    assert "runtimeArchetype" not in author_payload["requiredJsonShape"]

    requests: list[dict] = []

    def fake_llm(req, timeout=None):
        requests.append(copy.deepcopy(req))
        return {"choices": [{"message": {"content": json.dumps(valid)}}], "_debug": {}}

    monkeypatch.setattr(AUTHOR, "USE_LLM", True)
    monkeypatch.setattr(AUTHOR, "resolve_llm_model", lambda: "single-author-test-model")
    monkeypatch.setattr(AUTHOR, "active_llm_provider", lambda: "local")
    monkeypatch.setattr(AUTHOR, "llm_chat_json", fake_llm)
    monkeypatch.setattr(AUTHOR, "trace_event", lambda *args, **kwargs: None)

    result = AUTHOR.try_llm_plan(
        _wooden_sword(), _workbench(), {}, {}, "wood_gel_single_author"
    )
    assert result is not None
    assert len(requests) == 1
    assert result["concept"]["coreMechanic"] == valid["concept"]["coreMechanic"]
    assert result["debug"]["plannerPromiseGate"]["ok"] is True





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
    assert lower.startswith("topology: connected")
    assert "a thick wooden plank blade" in lower
    assert "foreground colors and materials use" not in lower
    assert "thick wooden plank blade" in lower
    assert "square workbench guard" in lower
    assert "primary authored material:" not in lower
    assert "generic polished steel" not in lower
    assert "single centered object" not in lower
    assert "one usable inventory asset composition" in lower
    assert "preserve authored part count and intentional gaps" in lower
    assert "keep every authored physical part readable inside the canvas" in lower
    renormalized = normalize_asset_prompt(data, "item", prompt, 48).lower()
    assert renormalized.count("one usable inventory asset composition") == 1
    assert "#ff00ff" in lower
    assert "show only the item sprite" not in lower
    assert "palette: gray, white" not in lower


def _contract_check_strict_preflights_run_before_expensive_image_generation() -> None:
    from contract_checks import assert_pipeline_phase_order

    source = (
        inspect.getsource(COMBINE.compile_and_validate_authored_runtime)
        + "\n"
        + inspect.getsource(COMBINE.combine)
    )
    assert_pipeline_phase_order(source, "initial_executable_preflight", "visual_director")
    assert_pipeline_phase_order(source, "recovered_final_wire", "visual_director")
    assert_pipeline_phase_order(
        source,
        "post_visual_executable_preflight",
        "vfx_manifest",
        "asset_runtime_gates",
        "visual_author_boundary",
        "asset_generation",
    )
    assert_pipeline_phase_order(source, "final_projection", "final_executable_boundary")


def _contract_check_visual_director_palette_policy_uses_provenance_not_material_semantics() -> None:
    fallback = _compiled_carpentry_item()
    assert fallback["debug"]["visualPaletteSource"] == "none"
    assert not fallback["visual"].get("palette")
    palette, policy = VISUAL._merge_visual_director_palette(
        fallback,
        fallback["visual"]["palette"],
        ["painted red", "brass"],
    )
    assert palette == ["painted red", "brass"]
    assert policy == "visual_director_authored"

    planner_authored = _carpentry_plan()
    planner_authored["runtimePlan"]["visualIntent"]["palette"] = ["painted blue", "white"]
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
    planner_authored["debug"]["visualPaletteSource"] = "result_and_parent_grounding_tags"
    assert VISUAL._merge_visual_director_palette(
        planner_authored,
        planner_authored["visual"]["palette"],
        ["orange", "black"],
    ) == (palette, policy)


def _contract_check_visual_context_and_generation_depth_ignore_debug_authority() -> None:
    from infini_local.core.item_identity_tools import generation_depth
    from infini_local.pipelines.visual_director_contract import visual_director_context

    data = _compiled_carpentry_item()
    data["visual"]["imagePrompt"] = "debug-sensitive image prompt"
    data["debug"]["visualPromptSource"] = "planner_authored"
    left = visual_director_context(data, _wooden_sword(), _workbench())
    data["debug"]["visualPromptSource"] = "code_fallback"
    right = visual_director_context(data, _wooden_sword(), _workbench())
    assert left == right
    assert "existingVisual" not in left
    assert "sourceRolePreservation" not in left

    parent = {"generatedData": {
        "recipeMeta": {},
        "debug": {"generationDepth": 99},
    }}
    assert generation_depth(parent) == 1
    parent["generatedData"]["debug"]["generationDepth"] = 3
    assert generation_depth(parent) == 1


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

    assert "sourceRolePreservation" not in captured["item"]
    assert "wooden sword remains the handle" not in json.dumps(captured["item"])
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

    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visual"] == before_visual
    assert result["attack"] == before_attack
    assert "visualKit" not in result
    assert result["debug"]["visualDirectorStatus"] == "visual_director_degraded"
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
    monkeypatch.setattr(
        VISUAL,
        "llm_json_response_format",
        lambda name, *, schema, strict: {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": strict, "schema": schema},
        },
    )

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
    assert "never an array" in baked_guide
    assert '"projectile":{"mode":"baked_sprite"' in baked_guide.replace(" ", "")
    vfx_guide = payload["fieldGuide"]["vfxFields"].casefold()
    assert "vfxscalehint is exactly one enum string" in vfx_guide
    assert "vfxrhythmhint is exactly one enum string" in vfx_guide
    assert "vfxavoid is exactly one string" in vfx_guide
    assert "never arrays" in vfx_guide
    lists_guide = payload["fieldGuide"]["lists"].casefold()
    assert "vfxmaterialhints is the only vfx hint field that is an array" in lists_guide

    response_format = req["response_format"]
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["visualKit"]
    visual_properties = schema["properties"]["visualKit"]["properties"]
    for field in ("vfxScaleHint", "vfxRhythmHint"):
        field_schema = visual_properties[field]
        assert field_schema["type"] == "string"
        description = field_schema["description"].casefold()
        assert "exactly one enum string" in description
        assert "never an array" in description
    vfx_avoid_schema = visual_properties["vfxAvoid"]
    assert vfx_avoid_schema["type"] == "string"
    assert "exactly one string" in vfx_avoid_schema["description"].casefold()
    assert "never an array" in vfx_avoid_schema["description"].casefold()
    baked_properties = schema["$defs"]["BakedAssetBoundary"]["properties"]
    mode_schema = baked_properties["mode"]
    assert set(mode_schema["enum"]) == {"baked_sprite", "particle_vfx", "reuse_item_sprite", "none"}
    assert "prompt" not in baked_properties
    baked_schema = schema["properties"]["visualKit"]["properties"]["bakedAssets"]
    assert baked_schema["additionalProperties"] is False
    assert set(baked_schema["properties"]) == {"projectile", "impact", "child", "field"}

def _contract_check_visual_kit_rejects_alias_schema_instead_of_semantic_migration() -> None:
    from infini_local.core.boundary_models import canonical_visual_kit_view

    invalid_shapes = [
        {"bakedAssets": {"projectile": "baked_sprite"}},
        {"bakedAssets": ["item_sprite", "projectile_sprite"]},
        {"bakedAssets": {"item": {"mode": "baked_sprite"}, "vfx": {"mode": "particle_vfx"}}},
        {"vfx": {"vfxIntent": "splinters", "materialHints": ["wood"]}},
    ]
    for invalid in invalid_shapes:
        with pytest.raises((TypeError, ValueError)):
            canonical_visual_kit_view(invalid)


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
    out = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert out is data
    assert data["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert data["visual"] == before
    assert "visualKit" not in data
    assert "no authored visual decision" in data["debug"]["visualDirectorError"]



def _contract_check_visual_director_remote_auto_mode_uses_safe_json_object_and_explicit_schema_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(LLM_TRANSPORT, "LLM_RESPONSE_FORMAT_MODE", "auto")
    monkeypatch.setattr(LLM_TRANSPORT, "active_llm_provider", lambda _context=None: "openai_compat")
    schema = {"type": "object", "additionalProperties": False}
    result = LLM_TRANSPORT.llm_json_response_format("visual_test", schema=schema, strict=True)
    assert result == {"type": "json_object"}

    monkeypatch.setattr(LLM_TRANSPORT, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    result = LLM_TRANSPORT.llm_json_response_format("visual_test", schema=schema, strict=True)
    assert result == {
        "type": "json_schema",
        "json_schema": {"name": "visual_test", "strict": True, "schema": schema},
    }


def _contract_check_visual_director_rejects_legacy_silhouette_alias(monkeypatch) -> None:
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
    out = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert out is data
    assert data["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert "visualKit" not in data


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
        "category": "weapon",
    }
    context_text = json.dumps(context, ensure_ascii=False)
    assert "sword-workbench hybrid" not in context_text
    assert "literal fusion" not in context_text
    assert "shapeAnchors" not in context_text
    assert "existingVisual" not in context
    assert "A whole workbench bolted to a wooden sword." not in context_text
    assert "code-generated technical wrapper" not in context_text

    data["debug"]["visualPromptSource"] = "planner_authored"
    authored_context = visual_director_context(data, _wooden_sword(), _workbench())
    assert "existingVisual" not in authored_context



def _contract_check_visual_director_rejects_nested_baked_prompt_alias(monkeypatch) -> None:
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
    out = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert out is data
    assert data["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert "visualKit" not in data


def _contract_check_visual_authoring_boundary_rejects_legacy_prompt_and_unknown_nested_fields() -> None:
    with pytest.raises(ValidationError):
        validate_visual_authoring_boundaries({
            "visualKit": {
                "bakedAssets": {
                    "impact": {
                        "mode": "baked_sprite",
                        "prompt": "literal authored wood-chip burst",
                    }
                }
            }
        })
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
    fresh = _compiled_carpentry_item()
    assert COMBINE._cached_payload_passes_executable_boundary(
        fresh,
        recipe_key_value="cache_current_structural_payload_accepted",
        source="test",
        **cache_parent_args,
    )
    fake_v3 = copy.deepcopy(fresh)
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
    assert not COMBINE._cached_payload_passes_executable_boundary(
        data,
        recipe_key_value="cache_visual_legacy_rejected",
        source="test",
        **cache_parent_args,
    )
    assert data["visualKit"]["bakedAssets"]["impact"]["prompt"] == "legacy sawdust burst"
    assert "impactSpritePrompt" not in data["visualKit"]

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


# One collected item per contract module; local checks are discovered in source order.
def test_242_live_generation_regressions_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request)
