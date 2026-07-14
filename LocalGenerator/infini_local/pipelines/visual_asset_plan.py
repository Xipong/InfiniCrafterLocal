from __future__ import annotations

import json
from typing import Any

from infini_local.core.runtime_family_policy import (
    canonical_runtime_family,
    is_canonical_runtime_family,
    is_item_bodied_projectile_family,
    uses_held_projectile_family,
)
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.pipelines.pipeline_runtime_constants import LLM_RUNTIME_AUTHORING
from infini_local.pipelines.pipeline_visual_config import (
    CHILD_SPRITE_CANVAS,
    FIELD_SPRITE_CANVAS,
    IMPACT_SPRITE_CANVAS,
    VISUAL_GENERATE_CHILD_FIELD_IMAGES,
    VISUAL_GENERATE_IMPACT_IMAGES,
    VISUAL_GENERATE_PROJECTILE_IMAGES,
)
from infini_local.pipelines.visual_prompt_contracts import effective_projectile_canvas


# AGENT MAP: model-authored visual asset mode gates and plan construction.
# It decides which already-authored visual slots get generated; it must not infer
# gameplay from prompt prose.


def _visual_kit(data: dict[str, Any]) -> dict[str, Any]:
    kit = data.get("visualKit")
    return kit if isinstance(kit, dict) else {}

def _role_baked_asset_spec(data: dict[str, Any], role: str) -> dict[str, Any]:
    """Return the one canonical model-authored asset decision."""
    kit = _visual_kit(data)
    baked = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
    spec = baked.get((role or "").strip().lower())
    return spec if isinstance(spec, dict) else {}

_ROLE_KIT_PROMPT_FIELDS = {
    "projectile": "projectileSpritePrompt",
    "impact": "impactSpritePrompt",
    "child": "childSpritePrompt",
    "field": "fieldSpritePrompt",
}


def _role_asset_prompt(data: dict[str, Any], role: str) -> str:
    """Resolve the one canonical role prompt, with legacy cache fallback last."""
    role = (role or "").strip().lower()
    kit = _visual_kit(data)
    prompt_field = _ROLE_KIT_PROMPT_FIELDS.get(role, "")
    canonical_prompt = str(kit.get(prompt_field) or "").strip() if prompt_field else ""
    if canonical_prompt:
        return canonical_prompt
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    projected_prompt = str(
        visual.get(f"{role}ImagePrompt")
        or attack.get(f"{role}SpritePrompt")
        or ""
    ).strip()
    if projected_prompt:
        return projected_prompt
    # Old cache/replay payloads can still reach isolated tools without the combine
    # boundary migration. Keep this read-only fallback; fresh authoring never writes it.
    spec = _role_baked_asset_spec(data, role)
    for key in ("prompt", "spritePrompt", "imagePrompt"):
        legacy_prompt = str(spec.get(key) or "").strip() if isinstance(spec, dict) else ""
        if legacy_prompt:
            return legacy_prompt
    return ""

def _asset_mode_from_value(value: Any) -> str:
    raw = str(value or "").strip()
    return raw if raw in {"baked_sprite", "particle_vfx", "reuse_item_sprite", "none"} else ""

def authored_asset_mode(data: dict[str, Any], role: str) -> str:
    role = (role or "").strip().lower()
    spec = _role_baked_asset_spec(data, role)
    return visual_asset_runtime_gate(data, role, _asset_mode_from_value(spec.get("mode")))[0]

def visual_asset_runtime_gate(data: dict[str, Any], role: str, authored_mode: str) -> tuple[str, str]:
    """Runtime-truth gate for optional baked assets.

    The visual director may request extra PNGs, but Python must not spend image
    compute or ship assets that no compiled runtime path can use.  This is a
    structural gate over compiled fields/VFX slots, not a prompt-word router.
    """
    mode = _asset_mode_from_value(authored_mode) or ""
    if not mode:
        return "", ""
    role = (role or "").lower()
    attack_raw = data.get("attack")
    attack: dict[str, Any] = attack_raw if isinstance(attack_raw, dict) else {}
    raw_runtime_family = attack.get("runtimeFamily")
    runtime_family = canonical_runtime_family(raw_runtime_family)
    if str(raw_runtime_family or "").strip() and not is_canonical_runtime_family(raw_runtime_family):
        return "none", "noncanonical_runtime_family"
    delivery = str(attack.get("delivery") or "").lower()
    hide_graphic = bool(attack.get("hideUseGraphic")) or bool(attack.get("disableItemMeleeHitbox"))

    if role == "projectile" and mode == "baked_sprite":
        role_spec = _role_baked_asset_spec(data, "projectile")
        distinct_from_item = bool(role_spec.get("distinctFromItem"))
        held_item_body = is_item_bodied_projectile_family(runtime_family) and uses_held_projectile_family(runtime_family)
        if is_item_bodied_projectile_family(runtime_family) and (held_item_body or not distinct_from_item):
            reason = "held_item_bodied_runtime_reuses_item_sprite" if held_item_body else "item_bodied_runtime_reuses_item_sprite"
            return "reuse_item_sprite", reason
        # Plain broadsword/swing keeps its single generated item sprite for inventory
        # and held drawing. A separate projectile PNG is only useful for a distinct body.
        # PNG is only useful for emitted/held projectile executors.
        if runtime_family == "swing" and delivery == "swing" and not hide_graphic:
            return "particle_vfx", "melee_swing_uses_item_sprite_no_projectile_asset"

    if role == "child" and mode == "baked_sprite":
        child_manifest_raw = data.get("vfxManifest")
        child_manifest: dict[str, Any] = child_manifest_raw if isinstance(child_manifest_raw, dict) else {}
        child_slots_raw = child_manifest.get("slots")
        child_slots: list[Any] = child_slots_raw if isinstance(child_slots_raw, list) else []
        has_child_vfx_slot = any(
            isinstance(slot, dict) and (
                str(slot.get("textureRole") or "").strip().lower() == "child"
                or str(slot.get("particleRole") or "").strip().lower() == "child"
            )
            for slot in child_slots
        )
        if int(attack.get("maxChildProjectiles") or 0) <= 0 and not has_child_vfx_slot:
            return "none", "no_compiled_child_runtime_or_vfx_slot"

    if role == "field" and mode == "baked_sprite":
        field_manifest_raw = data.get("vfxManifest")
        field_manifest: dict[str, Any] = field_manifest_raw if isinstance(field_manifest_raw, dict) else {}
        field_slots_raw = field_manifest.get("slots")
        field_slots: list[Any] = field_slots_raw if isinstance(field_slots_raw, list) else []
        has_field_slot = any(
            isinstance(slot, dict) and any(
                "field" in str(slot.get(k) or "").lower()
                for k in ("rendererKind", "renderer", "textureRole", "particleRole", "channel", "stage")
            )
            for slot in field_slots
        )
        field_radius = float(attack.get("vfxFieldRadiusTiles") or attack.get("fieldRadiusTiles") or attack.get("fieldRadius") or 0)
        field_lifetime = float(attack.get("vfxFieldLifetimeTicks") or attack.get("fieldLifetimeTicks") or 0)
        if not has_field_slot and field_radius <= 0 and field_lifetime <= 0:
            return "none", "no_compiled_field_runtime_or_vfx_slot"

    return mode, ""

def apply_visual_asset_runtime_gates(data: dict[str, Any], kit: dict[str, Any]) -> None:
    if not isinstance(kit, dict):
        return
    baked_value = kit.get("bakedAssets")
    baked: dict[str, Any] = baked_value if isinstance(baked_value, dict) else {}
    debug = data.setdefault("debug", {})
    authored_modes = {
        role: _asset_mode_from_value(spec.get("mode"))
        for role, spec in baked.items()
        if isinstance(spec, dict) and _asset_mode_from_value(spec.get("mode"))
    }
    if authored_modes and "visualAssetAuthoredModes" not in debug:
        debug["visualAssetAuthoredModes"] = authored_modes

    canonical: dict[str, dict[str, Any]] = {}
    reports: list[dict[str, str]] = []
    for role in ["projectile", "impact", "child", "field"]:
        spec_value = baked.get(role)
        spec: dict[str, Any] = spec_value if isinstance(spec_value, dict) else {}
        authored = _asset_mode_from_value(spec.get("mode"))
        final, reason = visual_asset_runtime_gate(data, role, authored)
        if final:
            row: dict[str, Any] = dict(spec)
            row["mode"] = final
            if final != "baked_sprite":
                row.pop("distinctFromItem", None)
            canonical[role] = row
        if reason:
            reports.append({"role": role, "authoredMode": authored, "finalMode": final, "reason": reason})
    if canonical:
        kit["bakedAssets"] = canonical
    else:
        kit.pop("bakedAssets", None)

    final_modes = {
        role: str(spec.get("mode") or "")
        for role, spec in canonical.items()
        if isinstance(spec, dict) and str(spec.get("mode") or "")
    }
    if final_modes:
        debug["visualAssetFinalModes"] = final_modes
    else:
        debug.pop("visualAssetFinalModes", None)
    if reports:
        debug["visualAssetRuntimeGates"] = json.dumps(reports, ensure_ascii=False)
    else:
        debug.pop("visualAssetRuntimeGates", None)

def finalize_visual_asset_runtime_gates(data: dict[str, Any]) -> dict[str, Any]:
    """Apply structural asset gates after the VFX manifest has been compiled."""
    kit = _visual_kit(data)
    if kit:
        apply_visual_asset_runtime_gates(data, kit)
    return data


def _runtime_gate_reason(data: dict[str, Any], role: str) -> str:
    debug_raw = data.get("debug")
    debug: dict[str, Any] = debug_raw if isinstance(debug_raw, dict) else {}
    raw = debug.get("visualAssetRuntimeGates", "")
    try:
        reports = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return ""
    if not isinstance(reports, list):
        return ""
    for report in reports:
        if isinstance(report, dict) and str(report.get("role") or "") == role:
            return str(report.get("reason") or "")
    return ""


def build_visual_asset_plan(data: dict[str, Any]) -> list[dict[str, Any]]:
    kit = _visual_kit(data)
    if kit:
        apply_visual_asset_runtime_gates(data, kit)
    attack = data.setdefault("attack", {})
    visual = data.setdefault("visual", {})
    base = str(data.get("id") or "sprite")
    plan: list[dict[str, Any]] = []
    # Item icon is generated by maybe_generate_sprite(), but include it in the manifest.
    plan.append({"role": "item", "assetId": base, "canvas": int(visual.get("preferredCanvasSize") or 32), "prompt": str(visual.get("imagePrompt") or ""), "required": True, "handledBy": "maybe_generate_sprite", "authoringPolicy": "ai_primary_non_procedural", "assetMode": "baked_sprite"})
    if isinstance(attack, dict) and attack.get("enabled"):
        runtime_authored = bool(LLM_RUNTIME_AUTHORING and runtime_plan(data))
        projectile_mode = authored_asset_mode(data, "projectile")
        projectile_prompt = _role_asset_prompt(data, "projectile")
        if projectile_mode == "reuse_item_sprite":
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": False, "status": "reuses_item_sprite", "skipReason": "item-bodied runtime uses the generated item sprite unless a distinct flight form is explicitly authored", "authoringPolicy": "ai_primary_non_procedural", "assetMode": "reuse_item_sprite", "assetDecisionBy": "runtime_asset_contract"})
        elif VISUAL_GENERATE_PROJECTILE_IMAGES and projectile_mode == "baked_sprite":
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": not runtime_authored, "authoringPolicy": "ai_primary_non_procedural", "assetMode": "baked_sprite", "assetDecisionBy": "model"})
        else:
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": False, "status": "skipped_not_authored_baked" if VISUAL_GENERATE_PROJECTILE_IMAGES else "skipped_disabled_by_settings", "skipReason": "projectile prompt is not demand; explicit baked_sprite mode required", "authoringPolicy": "ai_primary_non_procedural", "assetMode": projectile_mode or "particle_vfx", "assetDecisionBy": "model"})

        for role, allow, canvas in [
            ("impact", VISUAL_GENERATE_IMPACT_IMAGES, IMPACT_SPRITE_CANVAS),
            ("child", VISUAL_GENERATE_CHILD_FIELD_IMAGES, CHILD_SPRITE_CANVAS),
            ("field", VISUAL_GENERATE_CHILD_FIELD_IMAGES, FIELD_SPRITE_CANVAS),
        ]:
            prompt = _role_asset_prompt(data, role)
            mode = authored_asset_mode(data, role)
            entry = {"role": role, "assetId": base + "_" + role, "canvas": canvas, "prompt": prompt, "required": False, "authoringPolicy": "ai_primary_non_procedural", "assetMode": mode or "particle_vfx", "assetDecisionBy": "model"}
            if allow and mode == "baked_sprite":
                plan.append(entry)
            else:
                gate_reason = _runtime_gate_reason(data, role)
                if allow and gate_reason.startswith("no_compiled_"):
                    entry["status"] = "skipped_runtime_unused"
                    entry["skipReason"] = gate_reason
                else:
                    entry["status"] = "skipped_not_authored_baked" if allow else "skipped_disabled_by_settings"
                    entry["skipReason"] = f"{role} prompt is not demand; explicit baked_sprite mode required" if allow else f"{role} baked images disabled by settings"
                plan.append(entry)
    return plan


__all__ = [
    "_visual_kit",
    "_role_baked_asset_spec",
    "_role_asset_prompt",
    "_asset_mode_from_value",
    "authored_asset_mode",
    "visual_asset_runtime_gate",
    "apply_visual_asset_runtime_gates",
    "finalize_visual_asset_runtime_gates",
    "build_visual_asset_plan",
]
