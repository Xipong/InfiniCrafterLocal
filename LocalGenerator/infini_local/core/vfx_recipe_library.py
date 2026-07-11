from __future__ import annotations

from typing import Any

from infini_local.core.vfx_manifest_config import VFX_MORPH_RECIPES_RAW, VFX_SLOT_MACROS


# AGENT MAP: VFX recipe macro expansion and compact macro cards.
# Manifest composition remains in vfx_manifest.py; this module only owns recipe-library expansion.

_VFX_EXPANDED_RECIPE_CACHE: list[dict[str, Any]] | None = None

def _vfx_deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Tiny JSON-object merge for slot macros. Dict values merge; other values override."""
    out = dict(base or {})
    for key, value in (override or {}).items():
        if key == "macro":
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _vfx_deep_merge(out[key], value)
        else:
            out[key] = value
    return out

def _vfx_expand_slot_macro(slot: Any, recipe_id: str = "") -> dict[str, Any] | None:
    """Expand one slot. Supports {"macro": "name", ...overrides} and plain slot dicts.

    This intentionally keeps macro expansion in Python/generation time, not in C# runtime.
    The final vfxManifest remains frozen and contains only compiled concrete slots.
    """
    if isinstance(slot, str):
        slot = {"macro": slot}
    if not isinstance(slot, dict):
        return None
    macro_id = str(slot.get("macro") or "").strip()
    if not macro_id:
        return dict(slot)
    macro = VFX_SLOT_MACROS.get(macro_id)
    if not isinstance(macro, dict):
        # Keep a harmless debug-ish slot out; linter will report the missing macro through recipe expansion reports.
        return {k: v for k, v in slot.items() if k != "macro"}
    expanded = _vfx_deep_merge(macro, slot)
    expanded["macroId"] = macro_id
    return expanded

def _vfx_expand_recipe_macros(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of recipe with useMacros/macro slots expanded into concrete slots."""
    if not isinstance(recipe, dict):
        return {}
    out = dict(recipe)
    slots: list[dict[str, Any]] = []
    for macro_ref in recipe.get("useMacros") or []:
        expanded = _vfx_expand_slot_macro(macro_ref, str(recipe.get("id") or ""))
        if expanded:
            slots.append(expanded)
    for raw in recipe.get("slots") or []:
        expanded = _vfx_expand_slot_macro(raw, str(recipe.get("id") or ""))
        if expanded:
            slots.append(expanded)
    out["slots"] = slots
    out["expandedFromMacros"] = bool(recipe.get("useMacros") or any(isinstance(x, dict) and x.get("macro") for x in (recipe.get("slots") or [])))
    return out

def get_vfx_recipes(expand_macros: bool = True) -> list[dict[str, Any]]:
    global _VFX_EXPANDED_RECIPE_CACHE
    if not expand_macros:
        return VFX_MORPH_RECIPES_RAW
    if _VFX_EXPANDED_RECIPE_CACHE is None:
        _VFX_EXPANDED_RECIPE_CACHE = [_vfx_expand_recipe_macros(r) for r in VFX_MORPH_RECIPES_RAW]
    return _VFX_EXPANDED_RECIPE_CACHE

def compact_vfx_macro_card(macro_id: str, macro: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": macro_id,
        "event": macro.get("event", ""),
        "stage": macro.get("stage", ""),
        "backend": macro.get("backend", ""),
        "rendererKind": macro.get("renderer", ""),
        "textureRole": macro.get("textureRole", ""),
        "particleRole": macro.get("particleRole", ""),
        "scale": macro.get("scale"),
        "density": macro.get("density"),
        "duration": macro.get("duration"),
        "variants": macro.get("variants", []),
    }

__all__ = [
    "_vfx_deep_merge",
    "_vfx_expand_slot_macro",
    "_vfx_expand_recipe_macros",
    "get_vfx_recipes",
    "compact_vfx_macro_card",
]
