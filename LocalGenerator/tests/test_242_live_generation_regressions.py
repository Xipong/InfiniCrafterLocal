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
        "tooltip": "A rough wooden blade that throws splinters on impact.",
        "concept": {
            "fantasy": "A wooden sword reinforced with the structural essence of a workbench.",
            "mergeLogic": "The sword supplies the attack and the workbench supplies wood and joinery.",
            "weirdTwist": weird_twist,
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


def test_wood_workbench_keeps_visual_intent_out_of_attack_and_grounds_palette() -> None:
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


def test_visual_kit_repairs_singleton_text_lists_without_leaking_invalid_raw_output(monkeypatch) -> None:
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


def test_promise_gate_blocks_fake_platform_and_damaging_field_but_keeps_real_children() -> None:
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


def test_flux2_preserves_authored_literal_workbench_prompt_without_code_material_router(monkeypatch) -> None:
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
    assert lower.startswith("a terraria-like pixel-art item sprite")
    assert "color scheme and materials: brown, tan, dark brown" in lower
    assert "thick wooden plank blade" in lower
    assert "square workbench guard" in lower
    assert "primary authored material:" not in lower
    assert "generic polished steel" not in lower
    assert "show only the item sprite" in lower
    assert "palette: gray, white" not in lower


def test_strict_preflights_run_before_expensive_image_generation() -> None:
    source = inspect.getsource(COMBINE.combine)
    assert source.index("04c_strict_executable_preflight") < source.index("08_visual_director_asset_pack")
    assert source.index("08c_strict_executable_preflight") < source.index("08d_hybrid_vfx_manifest")
    assert source.index("08d_hybrid_vfx_manifest") < source.index("08e_visual_asset_runtime_gates")
    assert source.index("08e_visual_asset_runtime_gates") < source.index("08f_strict_visual_authoring_boundaries")
    assert source.index("08f_strict_visual_authoring_boundaries") < source.index("09_visual_asset_generation")
    assert source.index("11a_project_presentation_out_of_attack") < source.index("11b_strict_executable_boundary")


def test_visual_director_palette_policy_uses_provenance_not_material_semantics() -> None:
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


def test_visual_anchor_and_palette_order_is_deterministic_without_fusion_policy() -> None:
    from infini_local.pipelines.result_identity_policy import palette_from, required_anchors_from_tags

    tags = {"workbench", "wood", "sword", "iron", "placeable"}
    assert required_anchors_from_tags(tags) == required_anchors_from_tags(set(reversed(sorted(tags))))
    assert palette_from(tags) == palette_from(set(reversed(sorted(tags))))
    assert "wooden work bench" in required_anchors_from_tags(tags)
    assert "crafting table" in required_anchors_from_tags(tags)


def test_invalid_cached_attack_contract_is_not_delivered() -> None:
    data = _compiled_carpentry_item()
    data["attack"]["futureImaginaryField"] = 1
    assert COMBINE._cached_payload_passes_executable_boundary(
        data,
        recipe_key_value="bad-cache",
        source="test",
    ) is False


def test_visual_director_receives_planner_fusion_choice_without_code_rewrite(monkeypatch) -> None:
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


def test_prompt_cleanup_preserves_texture_and_grounded_words() -> None:
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


def test_visual_director_projection_is_fully_transactional_on_late_failure(monkeypatch) -> None:
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


def test_visual_director_payload_contains_raw_parent_facts_and_real_schema(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
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
    VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})

    req = captured["request"]
    payload = json.loads(req["messages"][1]["content"])
    parents = payload["item"]["parents"]
    assert parents[0]["rawFacts"]["internalName"] == "WoodenSword"
    assert parents[1]["rawFacts"]["createTile"] == 18
    assert "fusionRecommendation" not in json.dumps(parents)

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


def test_code_parent_anchors_are_context_not_mandatory_authored_anchors() -> None:
    data = _compiled_carpentry_item()
    visual = data["visual"]
    assert visual["requiredAnchors"] == []
    assert "wooden work bench" in visual["parentVisualContext"]
    assert data["debug"]["visualRequiredAnchorsSource"] == "none"


def test_runtime_multishot_does_not_rewrite_authored_projectile_topology(monkeypatch) -> None:
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


def test_empty_visual_kit_is_rejected_without_erasing_existing_visual(monkeypatch) -> None:
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



def test_visual_director_remote_auto_mode_uses_real_schema_with_safe_transport_fallback(monkeypatch) -> None:
    monkeypatch.setattr(LLM_TRANSPORT, "LLM_RESPONSE_FORMAT_MODE", "auto")
    monkeypatch.setattr(LLM_TRANSPORT, "active_llm_provider", lambda _context=None: "openai_compat")
    schema = {"type": "object", "additionalProperties": False}
    result = LLM_TRANSPORT.llm_json_response_format("visual_test", schema=schema, strict=True)
    assert result == {
        "type": "json_schema",
        "json_schema": {"name": "visual_test", "strict": True, "schema": schema},
    }


def test_visual_director_legacy_silhouette_alias_and_negative_prompt_are_shape_migrated(monkeypatch) -> None:
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


def test_visual_director_shared_style_reaches_every_asset_prompt(monkeypatch) -> None:
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


def test_field_asset_gate_runs_after_manifest_and_keeps_consumable_authored_sprite() -> None:
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


def test_visual_parent_context_is_bounded_without_semantic_rewrite() -> None:
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



def test_visual_director_context_does_not_present_code_fallback_prompt_as_authored() -> None:
    from infini_local.pipelines.visual_director_contract import visual_director_context

    data = _compiled_carpentry_item()
    data["visual"].update({
        "itemPrompt": "A whole workbench bolted to a wooden sword.",
        "imagePrompt": "pixel art inventory icon with a long code-generated technical wrapper",
    })
    data["debug"]["visualPromptSource"] = "code_fallback"
    context = visual_director_context(data, _wooden_sword(), _workbench())
    assert context["existingVisual"]["itemPrompt"] == "A whole workbench bolted to a wooden sword."
    assert "imagePrompt" not in context["existingVisual"]

    data["debug"]["visualPromptSource"] = "planner_authored"
    authored_context = visual_director_context(data, _wooden_sword(), _workbench())
    assert authored_context["existingVisual"]["imagePrompt"].startswith("pixel art inventory icon")



def test_visual_director_legacy_baked_prompt_migrates_to_single_role_prompt(monkeypatch) -> None:
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


def test_visual_authoring_boundary_canonicalizes_legacy_prompt_and_rejects_unknown_nested_fields() -> None:
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


def test_cached_payload_uses_same_visual_authoring_boundaries_as_fresh_combine() -> None:
    data = _compiled_carpentry_item()
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
    )
    assert data["visualKit"]["impactSpritePrompt"] == "legacy sawdust burst"
    assert "prompt" not in data["visualKit"]["bakedAssets"]["impact"]

    broken_kit = _compiled_carpentry_item()
    broken_kit["visualKit"] = {"bakedAssets": {"impact": {"mode": "magic_png"}}}
    assert not COMBINE._cached_payload_passes_executable_boundary(
        broken_kit,
        recipe_key_value="cache_visual_invalid",
        source="test",
    )

    broken_manifest = _compiled_carpentry_item()
    broken_manifest["vfxManifest"] = {"slots": [{"futureRenderer": "unknown"}]}
    assert not COMBINE._cached_payload_passes_executable_boundary(
        broken_manifest,
        recipe_key_value="cache_vfx_invalid",
        source="test",
    )


def test_visual_asset_gate_debug_is_recomputed_not_left_stale() -> None:
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


def test_baked_asset_mode_requires_a_real_authored_prompt_before_image_generation() -> None:
    data = _compiled_carpentry_item()
    data["visual"].pop("impactImagePrompt", None)
    data["attack"].pop("impactSpritePrompt", None)
    data["visualKit"] = {"bakedAssets": {"impact": {"mode": "baked_sprite"}}}
    with pytest.raises(ValueError, match="baked_sprite requires an authored role prompt"):
        validate_visual_authoring_boundaries(data)

    data["visualKit"]["impactSpritePrompt"] = "literal authored sawdust burst"
    normalized = validate_visual_authoring_boundaries(data)
    assert normalized["visualKit"]["impactSpritePrompt"] == "literal authored sawdust burst"


def test_nonfatal_generated_optional_sprite_remains_deliverable_with_warning(tmp_path) -> None:
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
