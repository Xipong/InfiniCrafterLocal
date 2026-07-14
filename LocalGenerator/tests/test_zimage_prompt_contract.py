from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import image_backend_pipeline
from infini_local.pipelines import pipeline_visual_config
from infini_local.pipelines.image_backend_pipeline import sdcpp_server_payload
from infini_local.pipelines.visual_prompt_contracts import (
    asset_negative_prompt,
    image_backend_is_zimage,
    normalize_asset_prompt,
)
from infini_local.services.visual_asset_pipeline import strip_conflicting_sprite_prompt_bits
from infini_local.services.visual_asset_pipeline import zimage_pe_clean_text
VISUAL = pipeline_visual_config
IMAGE_BACKEND_PIPELINE = image_backend_pipeline


def _sample_data() -> dict:
    return {
        "id": "test_zimage",
        "name": "Rope Spear",
        "tooltip": "A spearhead tied to rope; throw it and reel it back.",
        "concept": {"fantasy": "A compact spearhead knotted to a coil of rope, used like a hooked lance that snaps back to hand."},
        "attack": {
            "runtimeFamily": "throw",
            "weaponFamily": "harpoon",
            "projectileFamily": "spearhead",
            "projectileShape": "rope-tethered spearhead",
            "projectileMotion": "snaps out and reels back",
        },
        "visual": {
            "palette": ["iron gray", "brown", "tan"],
            "projectileImagePrompt": "Flying spearhead trailing a thin taut rope line back to the player.",
        },
    }


def _check_zimage_prompt_uses_positive_contract_not_negative_channel(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "C:/models/z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = _sample_data()
    prompt = normalize_asset_prompt(data, "projectile", data["visual"]["projectileImagePrompt"], 48).lower()
    negative = asset_negative_prompt("projectile")

    assert negative == ""
    assert "z-image prompt" not in prompt
    assert "negative prompt" not in prompt
    assert "a terraria-like pixel-art projectile sprite" in prompt
    assert "#ff00ff" in prompt
    assert "the game renders" not in prompt
    assert "outside this png" not in prompt
    assert "runtime" not in prompt
    assert "short local" in prompt or "local attachment" in prompt
    assert "subject:" not in prompt
    assert "purpose:" not in prompt
    assert "thin taut rope line back to the player" not in prompt
    assert "long rope/chain/tether is not part of the png" not in prompt
    assert "show one projectile body only" in prompt or "short local attachment" in prompt
    assert len(prompt) <= 1800



def _check_zimage_tether_guard_does_not_rewrite_plain_item_icons(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Braided Rope Charm",
        "tooltip": "A decorative braided rope charm.",
        "concept": {"fantasy": "A long braided rope charm with a small metal bead."},
        "attack": {"runtimeFamily": "none", "weaponFamily": "accessory"},
        "visual": {"palette": ["tan", "brown", "brass"]},
    }
    prompt = normalize_asset_prompt(data, "item", "Long ornate braided rope charm with a small brass bead.", 32).lower()

    assert "long ornate braided rope charm" in prompt
    assert "short local" not in prompt
    assert "local attachment" not in prompt

def _check_sdcpp_zimage_payload_clears_negative_prompt(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z_image_turbo-Q4_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_PROMPT_TAGS", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_FILE", "")

    payload = sdcpp_server_payload("subject", "scene, bad", 512, 512, 123, "a1111")

    assert payload["prompt"] == "subject"
    assert payload["negative_prompt"] == ""
    assert payload["zimage_positive_only_prompt"] is True
    assert payload["zimage_prompt_contract"] in {"auto", "1", "true", "on", "force"}


def _check_zimage_prompt_matches_pe_final_description_style(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = _sample_data()
    prompt = normalize_asset_prompt(data, "projectile", "Z-Image prompt: masterpiece 8K flying spearhead", 48).lower()

    assert "z-image prompt" not in prompt
    assert "masterpiece" not in prompt
    assert "8k" not in prompt
    assert "negative prompt" not in prompt
    assert "flying spearhead" in prompt
    assert prompt.endswith(".")


def _check_zimage_prompt_contract_can_be_disabled_or_forced(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "plain-sd-model.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    monkeypatch.setattr(VISUAL, "ZIMAGE_PROMPT_CONTRACT", "0")
    assert image_backend_is_zimage() is False

    monkeypatch.setattr(VISUAL, "ZIMAGE_PROMPT_CONTRACT", "1")
    assert image_backend_is_zimage() is True

    monkeypatch.setattr(VISUAL, "ZIMAGE_POSITIVE_ONLY", False)
    payload = sdcpp_server_payload("subject", "scene, bad", 512, 512, 123, "a1111")
    assert payload["negative_prompt"] == "scene, bad"
    assert payload["zimage_positive_only_prompt"] is False


def _check_visual_director_background_wrapper_keeps_post_colon_subject() -> None:
    raw = (
        "single pixel-art inventory icon on solid magenta key background (#ff00ff): "
        "two silver shurikens crossed slightly offset as a compact twin-star pair, "
        "bright white edge glints, gray metal bevels, text-free"
    )
    cleaned = strip_conflicting_sprite_prompt_bits(raw).lower()

    assert "two silver shurikens crossed slightly offset" in cleaned
    assert "bright white edge glints" in cleaned
    assert "background" not in cleaned
    assert "#ff00ff" not in cleaned


def _check_zimage_final_prompt_preserves_visual_director_subject_after_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Twin Star Shuriken",
        "concept": {"fantasy": "A matched pair of throwing stars spins as one compact constellation."},
        "visual": {"palette": ["silver", "gray", "white"]},
    }
    cleaned = strip_conflicting_sprite_prompt_bits(
        "single pixel-art inventory icon on solid magenta key background (#ff00ff): "
        "two silver shurikens crossed slightly offset as a compact twin-star pair, "
        "bright white edge glints, gray metal bevels, text-free"
    )
    prompt = normalize_asset_prompt(data, "item", cleaned, 48).lower()

    assert "two silver shurikens crossed slightly offset" in prompt
    assert "bright white edge glints" in prompt
    assert prompt.startswith("two silver shurikens")
    assert "appearance:" not in prompt
    assert "the complete item is fully visible" in prompt


def _check_zimage_palette_filters_chroma_key_but_keeps_background_clause(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Star Cactus Blade",
        "concept": {"fantasy": "A cactus blade with a yellow star crystal."},
        "visual": {"palette": ["sage green", "magenta", "#ff00ff", "solid magenta background", "pale gold", "magenta crystal"]},
    }
    prompt = normalize_asset_prompt(data, "item", "green cactus sword with a pale gold star", 48)
    lower = prompt.lower()

    assert "flat #ff00ff magenta chroma-key background" in lower
    assert "foreground colors and materials use sage green, pale gold, magenta crystal" in lower
    assert "color scheme and materials: sage green, magenta," not in lower
    assert "solid magenta background" not in lower


def _check_zimage_tether_guard_is_not_duplicated(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = _sample_data()
    already_guarded = (
        "A spinning four-pointed steel shuriken seen from the side, "
        "visible rope, cord, or chain may appear as a short local attachment, loop, nub, or compact coil attached to the main projectile body, "
        "keep the main projectile silhouette readable and keep all tether detail inside the canvas"
    )
    prompt = normalize_asset_prompt(data, "projectile", already_guarded, 48).lower()

    assert prompt.count("visible rope, cord, or chain may appear") == 1
    assert prompt.count("keep the main projectile silhouette readable") == 1


def _check_zimage_prompt_strips_inline_negative_blocks_and_sd_boilerplate(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Verdant Star",
        "concept": {"fantasy": "A small green crystal star with a brass socket."},
        "visual": {"palette": ["sage green", "brass", "white"]},
    }
    raw = (
        "prompt: masterpiece, best quality, ultra-detailed, centered composition, "
        "small green crystal star with a brass socket, text-free. "
        "negative prompt: watermark, text, logo, blurry, lowres, worst quality"
    )
    prompt = normalize_asset_prompt(data, "item", raw, 48).lower()

    assert "negative prompt" not in prompt
    assert "masterpiece" not in prompt
    assert "best quality" not in prompt
    assert "ultra-detailed" not in prompt
    assert "watermark" not in prompt
    assert "worst quality" not in prompt
    assert "small green crystal star with a brass socket" in prompt
    assert "without letters, logos, or ui marks" not in prompt
    assert "the complete item is fully visible" in prompt



def _check_zimage_no_text_policy_does_not_duplicate_phrase() -> None:
    cleaned = zimage_pe_clean_text("No text, letters, logos, or UI marks.").lower()

    assert cleaned == "without letters, logos, or ui marks"
    assert "ui marks letters" not in cleaned


def _check_zimage_prompt_uses_simpler_canvas_language(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Verdant Star",
        "concept": {"fantasy": "A small green crystal star with a brass socket."},
        "visual": {"palette": ["sage green", "brass", "white"]},
    }
    prompt = normalize_asset_prompt(data, "item", "small green crystal star with a brass socket, text-free", 48).lower()

    assert "16x16 to 32x32" not in prompt
    assert "32x32 to 64x64" not in prompt
    assert "thin safety margin" not in prompt
    assert "unlabeled visual sprite" not in prompt
    assert "the complete item is fully visible" in prompt
    assert "with a thin safety border" not in prompt
    assert "without letters, logos, or ui marks" not in prompt



def _check_role_hygiene_keeps_impact_effect_only(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Throne-Breaker's Splinter",
        "category": "weapon",
        "concept": {"fantasy": "A jagged wooden blade carved from a chair leg and backrest slat."},
        "visual": {"palette": ["oak brown", "dark chocolate"]},
    }
    prompt = normalize_asset_prompt(
        data,
        "impact",
        "A dense puff of brown sawdust and jagged wooden fragments expanding outward.",
        32,
    ).lower()

    assert "dense puff of brown sawdust" in prompt
    assert "hit impact sprite" in prompt
    assert "momentary hit effect" in prompt
    assert "no item or weapon body" in prompt
    assert "jagged wooden blade carved" not in prompt
    assert "no held weapon body" in prompt


def _check_role_hygiene_keeps_weapon_icon_from_placeable_scene(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Chair-Leg Cudgel",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon"},
        "concept": {"fantasy": "A crude weapon made from a broken wooden chair."},
        "visual": {"palette": ["oak brown"], "requiredAnchors": ["chair", "seat", "legs"]},
    }
    prompt = normalize_asset_prompt(
        data,
        "item",
        "A wooden chair silhouette with broken legs turned into a weapon.",
        64,
    ).lower()

    assert "wooden chair silhouette" in prompt
    assert "the complete item is fully visible" in prompt
    assert "handheld or carriable usable item" not in prompt
    assert "furniture placement preview" not in prompt
    assert "preserve authored literal, attached, fused, disassembled" not in prompt


def _check_thrust_projectile_prompt_does_not_force_spear_category(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Splinter Bundle",
        "category": "weapon",
        "concept": {"fantasy": "A bundle of rough wooden fragments used as a close-range jab."},
        "attack": {"runtimeFamily": "thrust", "pattern": "spear_thrust"},
        "visual": {"palette": ["oak brown"], "projectileImagePrompt": "A tight bundle of jagged wooden splinters."},
    }
    prompt = normalize_asset_prompt(data, "projectile", data["visual"]["projectileImagePrompt"], 64).lower()

    assert "tight bundle of jagged wooden splinters" in prompt
    assert "close-range thrust projection texture" in prompt
    assert "forcing a spear or polearm silhouette" in prompt
    assert "held spear/lance" not in prompt
    assert "straight polearm body" not in prompt
    assert "moving hit object texture only" in prompt


def _check_item_prompt_does_not_append_generated_name_as_flux_meta_text(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Twilight's Radiance",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon"},
        "concept": {"fantasy": "A single split-blade broadsword balancing gold light and black shadow."},
        "visual": {"palette": ["gold", "black", "white"]},
    }
    prompt = normalize_asset_prompt(data, "item", "single split-blade broadsword, gold front edge and black back edge", 48).lower()

    assert prompt.startswith("single split-blade broadsword")
    assert "twilight's radiance" not in prompt
    assert "identity context" not in prompt
    assert "without drawn letters or labels" not in prompt
    assert "draw letters" not in prompt


def _check_split_blade_prompt_stays_authored_without_code_shape_router(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Twilight's Radiance",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon"},
        "concept": {"fantasy": "A light-dark split blade made as one fused sword."},
        "visual": {"palette": ["gold", "black", "white"]},
    }
    authored = "single split-blade broadsword with a black rear blade portion"
    prompt = normalize_asset_prompt(data, "item", authored, 48).lower()

    assert authored in prompt
    assert "if the blade is split" not in prompt
    assert "dark/black portion flush" not in prompt

    source = (Path(__file__).resolve().parents[1] / "infini_local" / "pipelines" / "visual_prompt_contracts.py").read_text(encoding="utf-8")
    assert "_FUSED_BLADE_RISK_RE" not in source
    assert "_blade_shape_needs_fused_contour_guard" not in source


def _check_item_prompt_deduplicates_handheld_guard_for_zimage(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Chair-Leg Cudgel",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon"},
        "concept": {"fantasy": "A crude weapon made from a broken chair leg."},
        "visual": {"palette": ["oak brown"]},
    }
    authored = (
        "A wooden chair leg cudgel, depict one handheld or carriable usable item object, "
        "not a placed tile, room scene, furniture placement preview, pedestal, or environment."
    )
    prompt = normalize_asset_prompt(data, "item", authored, 48).lower()

    assert "wooden chair leg cudgel" in prompt
    assert "the complete item is fully visible" in prompt
    assert "handheld or carriable usable item" not in prompt
    assert "furniture placement preview" not in prompt
    assert "preserve authored literal, attached, fused, disassembled" not in prompt

    duplicated = (
        "A wooden chair leg cudgel, depict one handheld or carriable usable item object, "
        "not a placed tile, furniture placement preview, or environment, if furniture or placeable material "
        "is part of the design, show usable parts, fragments, straps, handle, head, blade, tool body, or silhouette cues integrated into the item, "
        "depict one handheld or carriable usable item object, not a placed tile, room scene, furniture placement preview, pedestal, or environment; "
        "if furniture or placeable material is part of the design, show usable parts, fragments, straps, handle, head, blade, tool body, or silhouette cues integrated into the item"
    )
    prompt = normalize_asset_prompt(data, "item", duplicated, 48).lower()

    assert "wooden chair leg cudgel" in prompt
    assert prompt.count("the complete item is fully visible") == 1
    assert "handheld or carriable usable item" not in prompt
    assert "furniture placement preview" not in prompt
    assert "preserve authored literal, attached, fused, disassembled" not in prompt


def _check_item_shape_contract_is_data_authored_not_code_taxonomy(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Shadow-Wreathed Katana",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "damageClass": "melee"},
        "concept": {"fantasy": "A blade forged from dark steel and corrupted jungle flora."},
        "parents": ["Verdant Shadowblade", "Muramasa"],
        "visual": {
            "palette": ["charcoal black", "bone white"],
            "itemSilhouetteContract": "Long slender slightly curved blade, blade length about three times the handle, with a visible tsuka grip and small guard.",
        },
    }
    prompt = normalize_asset_prompt(
        data,
        "item",
        "A katana with a dark serrated steel blade resembling a jagged leaf and a pale cloth hilt.",
        48,
    ).lower()
    assert "long slender slightly curved blade" in prompt
    assert "visible tsuka" in prompt
    assert "not a short knife" not in prompt
    assert prompt.index("long slender slightly curved blade") < prompt.index("a katana with a dark serrated")
    assert prompt.count("the complete item is fully visible") == 1

    no_contract = {
        "name": "Shadow-Wreathed Katana",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "damageClass": "melee"},
        "concept": {"fantasy": "A blade forged from dark steel and corrupted jungle flora."},
        "parents": ["Verdant Shadowblade", "Muramasa"],
        "visual": {"palette": ["charcoal black", "bone white"]},
    }
    plain_prompt = normalize_asset_prompt(
        no_contract,
        "item",
        "A katana with a dark serrated steel blade resembling a jagged leaf and a pale cloth hilt.",
        48,
    ).lower()
    assert "long slender slightly curved blade" not in plain_prompt
    assert "not a short knife" not in plain_prompt

    kit_contract = {
        "name": "Modded Weirdblade",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "damageClass": "melee"},
        "visualKit": {
            "itemSilhouetteContract": "Asymmetric crescent-hook blade whose lower edge joins one continuous wrapped handle."
        },
        "visual": {"palette": ["violet"]},
    }
    kit_prompt = normalize_asset_prompt(
        kit_contract,
        "item",
        "A cursed modded melee weapon made of violet hook-metal.",
        48,
    ).lower()
    assert "asymmetric crescent-hook blade" in kit_prompt
    assert "whose lower edge joins one continuous wrapped handle" in kit_prompt
    assert "no detached lower spur" not in kit_prompt

    source = (Path(__file__).resolve().parents[1] / "infini_local" / "pipelines" / "visual_prompt_contracts.py").read_text(encoding="utf-8")
    guard_body = source.split("def role_visual_prompt_guard", 1)[1].split("def _authored_tether_context", 1)[0]
    assert "_authored_item_silhouette_contract(data)" in guard_body
    assert "_item_shape_contract_clauses" not in source
    assert "katana/tachi silhouette contract" not in source
    assert "Soul-Clockwork Repeater" not in guard_body


def _check_starfall_projectile_and_child_prompts_are_semantic_role_contracts(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Astral Wrath Blade",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "damageClass": "melee"},
        "attack": {"runtimeFamily": "swing", "onHit": "overhead_barrage", "effect": "star"},
        "visual": {"palette": ["white", "gold"], "projectileImagePrompt": "a falling five-point star slash", "childImagePrompt": "small falling gold star projectile"},
    }
    projectile_prompt = normalize_asset_prompt(data, "projectile", data["visual"]["projectileImagePrompt"], 48).lower()
    child_prompt = normalize_asset_prompt(data, "child", data["visual"]["childImagePrompt"], 24).lower()

    assert "moving hit object texture only" in projectile_prompt
    assert "inventory-view framing" in projectile_prompt
    assert "not the inventory weapon icon" not in projectile_prompt
    assert "five-point star" in projectile_prompt
    assert "overhead-descending hit body" in projectile_prompt
    assert "role contract" in projectile_prompt
    assert "small falling gold star projectile" in child_prompt
    assert "child damaging projectile" in child_prompt
    assert "not a decorative background sparkle field" in child_prompt


def _check_sword_projectile_prompt_allows_same_blade_silhouette_with_attack_framing(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    data = {
        "name": "Twilight Zenith Blade",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "damageClass": "melee"},
        "attack": {"runtimeFamily": "swing", "delivery": "swing", "weaponFamily": "sword"},
        "visual": {"projectileImagePrompt": "the same long split broadsword blade silhouette, angled as the active slash body"},
    }

    prompt = normalize_asset_prompt(data, "projectile", data["visual"]["projectileImagePrompt"], 64).lower()

    assert "same long split broadsword blade silhouette" in prompt
    assert "same weapon shape may be reused" in prompt
    assert "attack-frame/projectile-body framing" in prompt
    assert "not the inventory weapon icon" not in prompt


def _check_projectile_fantasy_context_is_runtime_family_aware(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL, "SDCPP_MODEL", "z-image-turbo-Q6_K.gguf")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_COMMAND_TEMPLATE", "")
    monkeypatch.setattr(VISUAL, "SDCPP_SERVER_EXTRA_ARGS", "")

    gun = {
        "name": "Clockwork Bloom Rifle",
        "concept": {"fantasy": "A large brass flower rifle with a walnut stock and winding key."},
        "attack": {"runtimeFamily": "shoot", "weaponFamily": "gun", "projectileShape": "small copper bullet"},
        "visual": {"projectileImagePrompt": "one small copper bullet with a blue spark tail"},
    }
    boomerang = {
        "name": "Jade Crescent",
        "concept": {"fantasy": "A jade crescent boomerang bound with gold wire."},
        "attack": {"runtimeFamily": "returning", "weaponFamily": "boomerang", "projectileShape": "jade crescent"},
        "visual": {"projectileImagePrompt": "the same jade crescent weapon body in flight"},
    }

    gun_prompt = normalize_asset_prompt(gun, "projectile", gun["visual"]["projectileImagePrompt"], 32).lower()
    boomerang_prompt = normalize_asset_prompt(boomerang, "projectile", boomerang["visual"]["projectileImagePrompt"], 48).lower()

    assert "one small copper bullet" in gun_prompt
    assert "large brass flower rifle" not in gun_prompt
    assert "walnut stock" not in gun_prompt
    assert "jade crescent boomerang bound with gold wire" in boomerang_prompt

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_zimage_prompt_uses_positive_contract_not_negative_channel',
    '_check_zimage_tether_guard_does_not_rewrite_plain_item_icons',
    '_check_sdcpp_zimage_payload_clears_negative_prompt',
    '_check_zimage_prompt_matches_pe_final_description_style',
    '_check_zimage_prompt_contract_can_be_disabled_or_forced',
    '_check_visual_director_background_wrapper_keeps_post_colon_subject',
    '_check_zimage_final_prompt_preserves_visual_director_subject_after_wrapper',
    '_check_zimage_palette_filters_chroma_key_but_keeps_background_clause',
    '_check_zimage_tether_guard_is_not_duplicated',
    '_check_zimage_prompt_strips_inline_negative_blocks_and_sd_boilerplate',
    '_check_zimage_no_text_policy_does_not_duplicate_phrase',
    '_check_zimage_prompt_uses_simpler_canvas_language',
    '_check_role_hygiene_keeps_impact_effect_only',
    '_check_role_hygiene_keeps_weapon_icon_from_placeable_scene',
    '_check_thrust_projectile_prompt_does_not_force_spear_category',
    '_check_item_prompt_does_not_append_generated_name_as_flux_meta_text',
    '_check_split_blade_prompt_stays_authored_without_code_shape_router',
    '_check_item_prompt_deduplicates_handheld_guard_for_zimage',
    '_check_item_shape_contract_is_data_authored_not_code_taxonomy',
    '_check_starfall_projectile_and_child_prompts_are_semantic_role_contracts',
    '_check_sword_projectile_prompt_allows_same_blade_silhouette_with_attack_framing',
    '_check_projectile_fantasy_context_is_runtime_family_aware'
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


def test_zimage_prompt_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
