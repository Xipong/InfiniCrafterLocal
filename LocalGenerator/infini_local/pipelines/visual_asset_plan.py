from __future__ import annotations

import sys
import json
from typing import Any

from infini_local.pipelines.pipeline_support import (
    CHILD_SPRITE_CANVAS,
    FIELD_SPRITE_CANVAS,
    IMPACT_SPRITE_CANVAS,
    LLM_RUNTIME_AUTHORING,
    VISUAL_GENERATE_CHILD_FIELD_IMAGES,
    VISUAL_GENERATE_IMPACT_IMAGES,
    VISUAL_GENERATE_PROJECTILE_IMAGES,
    runtime_plan,
)
from infini_local.pipelines.visual_prompt_contracts import effective_projectile_canvas


# AGENT MAP: model-authored visual asset mode gates and plan construction.
# It decides which already-authored visual slots get generated; it must not infer
# gameplay from prompt prose.




def _cfg(name: str, default: Any) -> Any:
    facade = sys.modules.get("infini_local.pipelines.visual_generation_pipeline")
    if facade is not None and hasattr(facade, name):
        return getattr(facade, name)
    return default
def should_generate_child_asset(data: dict[str, Any]) -> bool:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    try:
        if int(float(attack.get("splitCount") or 0)) > 0 or int(float(attack.get("maxChildProjectiles") or 0)) > 0:
            return True
    except Exception:
        pass
    onhit = str(attack.get("onHit") or "").lower()
    if onhit in {"split", "starburst", "starfall", "spore_cloud", "mini_missiles", "vortex_spawn", "radial_beams"}:
        return True
    visual = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    return bool(str(visual.get("childSpritePrompt") or visual.get("childVfx") or "").strip())

def should_generate_field_asset(data: dict[str, Any]) -> bool:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    text = " ".join(str(attack.get(k, "")).lower() for k in ["impactStyle", "projectileImpact", "visualMode"])
    visual = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    text += " " + str(visual.get("fieldSpritePrompt") or visual.get("fieldVfx") or "").lower()
    return any(w in text for w in ["field", "trap", "rune", "cloud", "aura", "puddle", "anchor", "sigil", "zone", "mark on ground", "imprint"])

def _visual_kit(data: dict[str, Any]) -> dict[str, Any]:
    kit = data.get("visualKit")
    return kit if isinstance(kit, dict) else {}

def _role_baked_asset_spec(data: dict[str, Any], role: str) -> dict[str, Any]:
    """Model-authored per-role baked asset decision.

    This supports the clearer nested shape:
      visualKit.bakedAssets.projectile = {mode/enabled/prompt/reason}
    while keeping assetModes/projectileAssetMode as compact aliases.  Runtime never
    infers demand from prompt text alone; only these model-authored switches matter.
    """
    role = (role or "").strip().lower()
    for owner in [data.get("visualKit"), data.get("visual"), data]:
        if not isinstance(owner, dict):
            continue
        baked = owner.get("bakedAssets") or owner.get("assetsWanted") or owner.get("visualAssets")
        if isinstance(baked, dict):
            spec = baked.get(role)
            if isinstance(spec, dict):
                return spec
            if isinstance(spec, bool):
                return {"enabled": spec}
            if isinstance(spec, str):
                return {"mode": spec}
    return {}

def _role_asset_prompt(data: dict[str, Any], role: str) -> str:
    spec = _role_baked_asset_spec(data, role)
    for key in ["prompt", "spritePrompt", "imagePrompt"]:
        if isinstance(spec, dict) and spec.get(key):
            return str(spec.get(key) or "").strip()
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    return str(
        visual.get(f"{role}ImagePrompt")
        or attack.get(f"{role}SpritePrompt")
        or ""
    ).strip()

def _asset_mode_from_value(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"baked", "baked_sprite", "sprite", "png", "image", "separate_sprite", "generated_sprite"}:
        return "baked_sprite"
    if raw in {"particle", "particles", "particle_vfx", "vfx", "dust", "vanilla_vfx", "code_vfx", "runtime_vfx"}:
        return "particle_vfx"
    if raw in {"none", "off", "skip", "disabled", "false", "no"}:
        return "none"
    return ""

def compiled_child_projectile_needs_sprite(data: dict[str, Any]) -> bool:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    try:
        count = int(float(attack.get("splitCount") or 0))
        max_children = int(float(attack.get("maxChildProjectiles") or 0))
    except (TypeError, ValueError):
        count = max_children = 0
    if count <= 0 and max_children <= 0:
        return False
    return bool(str(attack.get("secondaryProjectileShape") or attack.get("secondaryMaterial") or "").strip())

def authored_asset_mode(data: dict[str, Any], role: str) -> str:
    """Return the model-authored baked-asset mode for a role.

    GUI flags are capability gates only.  They must not force impact/child/field PNGs.
    Only the LLM/visual director can request a separate baked sprite through these
    mode fields; plain prompts are candidate descriptions, not demand.
    """
    role = (role or "").strip().lower()
    if role == "child" and compiled_child_projectile_needs_sprite(data):
        final, _reason = visual_asset_runtime_gate(data, role, "baked_sprite")
        return final or "baked_sprite"
    kit = _visual_kit(data)
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    modes = kit.get("assetModes") if isinstance(kit.get("assetModes"), dict) else {}
    role_spec = _role_baked_asset_spec(data, role)
    candidates = [
        role_spec.get("mode") if isinstance(role_spec, dict) else None,
        role_spec.get("assetMode") if isinstance(role_spec, dict) else None,
        role_spec.get("spriteMode") if isinstance(role_spec, dict) else None,
        role_spec.get("enabled") if isinstance(role_spec, dict) else None,
        modes.get(role),
        kit.get(f"{role}AssetMode"),
        kit.get(f"{role}SpriteMode"),
        visual.get(f"{role}AssetMode"),
        attack.get(f"{role}AssetMode"),
    ]
    # Back-compat with a few natural boolean fields.  These are still model-authored.
    for key in [f"bake{role.capitalize()}Sprite", f"useBaked{role.capitalize()}Sprite", f"{role}BakedSprite"]:
        candidates.extend([kit.get(key), visual.get(key), attack.get(key)])
    for value in candidates:
        if isinstance(value, bool):
            mode = "baked_sprite" if value else "particle_vfx"
            return visual_asset_runtime_gate(data, role, mode)[0]
        mode = _asset_mode_from_value(value)
        if mode:
            return visual_asset_runtime_gate(data, role, mode)[0]
    return ""

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
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = str(attack.get("runtimeFamily") or "").lower()
    delivery = str(attack.get("delivery") or "").lower()
    hide_graphic = bool(attack.get("hideUseGraphic")) or bool(attack.get("disableItemMeleeHitbox"))

    if role == "projectile" and mode == "baked_sprite":
        # Plain broadsword/swing keeps its item/held sprite.  A separate projectile
        # PNG is only useful for emitted/held projectile executors.
        if runtime_family == "swing" and delivery == "swing" and not hide_graphic:
            return "particle_vfx", "melee_swing_uses_item_sprite_no_projectile_asset"

    if role == "field" and mode == "baked_sprite":
        manifest = data.get("vfxManifest") if isinstance(data.get("vfxManifest"), dict) else {}
        slots = manifest.get("slots") if isinstance(manifest.get("slots"), list) else []
        has_field_slot = any(
            isinstance(slot, dict) and any(
                "field" in str(slot.get(k) or "").lower()
                for k in ("rendererKind", "renderer", "textureRole", "particleRole", "channel", "stage")
            )
            for slot in slots
        )
        field_radius = float(attack.get("vfxFieldRadiusTiles") or attack.get("fieldRadiusTiles") or attack.get("fieldRadius") or 0)
        field_lifetime = float(attack.get("vfxFieldLifetimeTicks") or attack.get("fieldLifetimeTicks") or 0)
        if not has_field_slot and field_radius <= 0 and field_lifetime <= 0:
            return "none", "no_compiled_field_runtime_or_vfx_slot"

    return mode, ""

def apply_visual_asset_runtime_gates(data: dict[str, Any], kit: dict[str, Any]) -> None:
    if not isinstance(kit, dict):
        return
    modes = kit.get("assetModes") if isinstance(kit.get("assetModes"), dict) else {}
    gated: dict[str, str] = {}
    reports: list[dict[str, str]] = []
    baked = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
    for role in ["projectile", "impact", "child", "field"]:
        authored = _asset_mode_from_value(modes.get(role) if isinstance(modes, dict) else "") or _asset_mode_from_value(kit.get(f"{role}AssetMode"))
        if not authored and isinstance(baked, dict):
            spec = baked.get(role)
            if isinstance(spec, dict):
                authored = _asset_mode_from_value(spec.get("mode") or spec.get("assetMode") or spec.get("enabled"))
        final, reason = visual_asset_runtime_gate(data, role, authored)
        if final:
            gated[role] = final
            kit[f"{role}AssetMode"] = final
            if isinstance(baked, dict) and isinstance(baked.get(role), dict):
                baked[role]["mode"] = final
        if reason:
            reports.append({"role": role, "authoredMode": authored, "finalMode": final, "reason": reason})
    if gated:
        kit["assetModes"] = {**(modes if isinstance(modes, dict) else {}), **gated}
    if reports:
        data.setdefault("debug", {})["visualAssetRuntimeGates"] = json.dumps(reports, ensure_ascii=False)

def legacy_projectile_baked_sprite_fallback(data: dict[str, Any]) -> bool:
    """Legacy prompt-only projectile PNG demand is intentionally disabled.

    New worlds do not need to support old visual-director outputs.  A projectile image
    is generated only when the model explicitly authors projectileAssetMode=baked_sprite
    or visualKit.bakedAssets.projectile.enabled=true.
    """
    return False

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
        runtime_authored = bool(_cfg('LLM_RUNTIME_AUTHORING', LLM_RUNTIME_AUTHORING) and runtime_plan(data))
        projectile_mode = authored_asset_mode(data, "projectile")
        projectile_prompt = _role_asset_prompt(data, "projectile")
        if _cfg('VISUAL_GENERATE_PROJECTILE_IMAGES', VISUAL_GENERATE_PROJECTILE_IMAGES) and projectile_mode == "baked_sprite":
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": not runtime_authored, "authoringPolicy": "ai_primary_non_procedural", "assetMode": "baked_sprite", "assetDecisionBy": "model"})
        else:
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": False, "status": "skipped_not_authored_baked" if _cfg('VISUAL_GENERATE_PROJECTILE_IMAGES', VISUAL_GENERATE_PROJECTILE_IMAGES) else "skipped_disabled_by_settings", "skipReason": "projectile prompt is not demand; explicit baked_sprite mode required", "authoringPolicy": "ai_primary_non_procedural", "assetMode": projectile_mode or "particle_vfx", "assetDecisionBy": "model"})

        for role, allow, canvas in [
            ("impact", _cfg('VISUAL_GENERATE_IMPACT_IMAGES', VISUAL_GENERATE_IMPACT_IMAGES), _cfg('IMPACT_SPRITE_CANVAS', IMPACT_SPRITE_CANVAS)),
            ("child", _cfg('VISUAL_GENERATE_CHILD_FIELD_IMAGES', VISUAL_GENERATE_CHILD_FIELD_IMAGES), _cfg('CHILD_SPRITE_CANVAS', CHILD_SPRITE_CANVAS)),
            ("field", _cfg('VISUAL_GENERATE_CHILD_FIELD_IMAGES', VISUAL_GENERATE_CHILD_FIELD_IMAGES), _cfg('FIELD_SPRITE_CANVAS', FIELD_SPRITE_CANVAS)),
        ]:
            prompt = _role_asset_prompt(data, role)
            mode = authored_asset_mode(data, role)
            entry = {"role": role, "assetId": base + "_" + role, "canvas": canvas, "prompt": prompt, "required": False, "authoringPolicy": "ai_primary_non_procedural", "assetMode": mode or "particle_vfx", "assetDecisionBy": "model"}
            if allow and mode == "baked_sprite":
                plan.append(entry)
            else:
                entry["status"] = "skipped_not_authored_baked" if allow else "skipped_disabled_by_settings"
                entry["skipReason"] = f"{role} prompt is not demand; explicit baked_sprite mode required" if allow else f"{role} baked images disabled by settings"
                plan.append(entry)
    return plan


__all__ = [
    "should_generate_child_asset",
    "should_generate_field_asset",
    "_visual_kit",
    "_role_baked_asset_spec",
    "_role_asset_prompt",
    "_asset_mode_from_value",
    "compiled_child_projectile_needs_sprite",
    "authored_asset_mode",
    "visual_asset_runtime_gate",
    "apply_visual_asset_runtime_gates",
    "legacy_projectile_baked_sprite_fallback",
    "build_visual_asset_plan",
]
