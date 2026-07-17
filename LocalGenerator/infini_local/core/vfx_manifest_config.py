from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infini_local.core.env_utils import load_env_file
from infini_local.core.env_utils import env_bool, env_float, env_int


# AGENT MAP: configuration/data ownership for VFX manifest authoring.
# Keep env and JSON library loading here so vfx_manifest.py owns assembly without
# also owning configuration and data loading.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"


def load_json_file(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return fallback


load_env_file(ROOT / "config.env")

# VFX manifest assembly consumes the recipe/config data owned here.
VFX_MORPH_LIBRARY = load_json_file(DATA_DIR / "vfx_morph_recipes.json", {"recipes": []})
VFX_SLOT_MACRO_LIBRARY = load_json_file(DATA_DIR / "vfx_slot_macros.json", {"macros": {}})
VFX_SLOT_MACROS = VFX_SLOT_MACRO_LIBRARY.get("macros", {}) if isinstance(VFX_SLOT_MACRO_LIBRARY, dict) and isinstance(VFX_SLOT_MACRO_LIBRARY.get("macros"), dict) else {}
VFX_MORPH_RECIPES_RAW = [r for r in (VFX_MORPH_LIBRARY.get("recipes") or []) if isinstance(r, dict) and not r.get("disabled")] if isinstance(VFX_MORPH_LIBRARY, dict) else []
VFX_MORPH_RECIPES = VFX_MORPH_RECIPES_RAW  # expanded lazily by get_vfx_recipes(); kept for old debug code.

# v0.3.16+ VFX selector/env knobs.
VFX_SELECTOR_ENABLED = env_bool("INFINI_VFX_SELECTOR", True)
# v0.4.3: when runtimePlan.engineCalls exists, prefer a tiny author-intent manifest over
# legacy recipe roulette. This keeps VFX as execution, not game design.
VFX_RUNTIME_INTENT_FIRST = env_bool("INFINI_VFX_RUNTIME_INTENT_FIRST", True)
VFX_SELECTOR_DEBUG = env_bool("INFINI_VFX_SELECTOR_DEBUG", True)
VFX_SELECTOR_TOP = env_int("INFINI_VFX_SELECTOR_TOP", 5)
VFX_SELECTOR_JITTER = env_float("INFINI_VFX_SELECTOR_JITTER", 18.0)
VFX_SELECTOR_NOVELTY_WEIGHT = env_float("INFINI_VFX_SELECTOR_NOVELTY_WEIGHT", 6.0)

# v0.3.40 optional second-pass LLM VFX Director.
# It authors a concrete frozen manifest surface; Python only validates/clamps it,
# and falls back to the old selector if disabled or invalid. The prompt is intentionally
# limited to parentA, parentB, childItem, vfxSurface and constraints; name-bank words
# must not steer director generation.
VFX_LLM_DIRECTOR_ENABLED = env_bool("INFINI_VFX_LLM_DIRECTOR", False)
VFX_LLM_DIRECTOR_MAX_SLOTS = env_int("INFINI_VFX_LLM_DIRECTOR_MAX_SLOTS", 5)
VFX_LLM_DIRECTOR_MAX_TOKENS = env_int("INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS", 1800)
VFX_LLM_DIRECTOR_TEMPERATURE = env_float("INFINI_VFX_LLM_DIRECTOR_TEMPERATURE", 0.34)
VFX_LLM_DIRECTOR_TIMEOUT = env_int("INFINI_VFX_LLM_DIRECTOR_TIMEOUT", 75)
VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS = env_int("INFINI_VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS", 1)
VFX_EFFECT_NAME_BANK_MAX_CARDS = env_int("INFINI_VFX_EFFECT_NAME_BANK_MAX_CARDS", 8)
VFX_EFFECT_NAME_BANK_MAX_NAMES = env_int("INFINI_VFX_EFFECT_NAME_BANK_MAX_NAMES", 42)
VFX_EFFECT_NAME_BANK_PATH = DATA_DIR / "vfx_effect_name_bank.json"

VFX_PROCEDURAL_COMPOSE = env_bool("INFINI_VFX_PROCEDURAL_COMPOSE", True)
VFX_RECIPE_BLEND_ENABLED = env_bool("INFINI_VFX_RECIPE_BLEND", True)
VFX_PROCEDURAL_MAX_EXTRA_SLOTS = env_int("INFINI_VFX_PROCEDURAL_MAX_EXTRA_SLOTS", 5)
VFX_PROCEDURAL_BLEND_CANDIDATES = env_int("INFINI_VFX_PROCEDURAL_BLEND_CANDIDATES", 2)
VFX_PROCEDURAL_CHANCE = env_float("INFINI_VFX_PROCEDURAL_CHANCE", 0.82)

VFX_PARENT_EFFECT_INHERITANCE = env_bool("INFINI_VFX_PARENT_EFFECT_INHERITANCE", True)
VFX_PARENT_EFFECT_STRONG_THRESHOLD = env_float("INFINI_VFX_PARENT_EFFECT_STRONG_THRESHOLD", 0.48)
VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS = env_int("INFINI_VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS", 3)

VFX_RENDER_QUALITY = "Full"
VFX_EMERGENCY_MAX_PARTICLES_PER_TICK = env_int("INFINI_VFX_EMERGENCY_MAX_PARTICLES_PER_TICK", 240)
VFX_EMERGENCY_MAX_PARTICLES_TOTAL = env_int("INFINI_VFX_EMERGENCY_MAX_PARTICLES_TOTAL", 9000)
VFX_EMERGENCY_MAX_DRAW_CALLS = env_int("INFINI_VFX_EMERGENCY_MAX_DRAW_CALLS", 420)
VFX_MAGNITUDE_JITTER = env_float("INFINI_VFX_MAGNITUDE_JITTER", 0.18)


__all__ = [
    "ROOT",
    "DATA_DIR",
    "load_json_file",
    "VFX_MORPH_LIBRARY",
    "VFX_SLOT_MACRO_LIBRARY",
    "VFX_SLOT_MACROS",
    "VFX_MORPH_RECIPES_RAW",
    "VFX_MORPH_RECIPES",
    "VFX_SELECTOR_ENABLED",
    "VFX_RUNTIME_INTENT_FIRST",
    "VFX_SELECTOR_DEBUG",
    "VFX_SELECTOR_TOP",
    "VFX_SELECTOR_JITTER",
    "VFX_SELECTOR_NOVELTY_WEIGHT",
    "VFX_LLM_DIRECTOR_ENABLED",
    "VFX_LLM_DIRECTOR_MAX_SLOTS",
    "VFX_LLM_DIRECTOR_MAX_TOKENS",
    "VFX_LLM_DIRECTOR_TEMPERATURE",
    "VFX_LLM_DIRECTOR_TIMEOUT",
    "VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS",
    "VFX_EFFECT_NAME_BANK_MAX_CARDS",
    "VFX_EFFECT_NAME_BANK_MAX_NAMES",
    "VFX_EFFECT_NAME_BANK_PATH",
    "VFX_PROCEDURAL_COMPOSE",
    "VFX_RECIPE_BLEND_ENABLED",
    "VFX_PROCEDURAL_MAX_EXTRA_SLOTS",
    "VFX_PROCEDURAL_BLEND_CANDIDATES",
    "VFX_PROCEDURAL_CHANCE",
    "VFX_PARENT_EFFECT_INHERITANCE",
    "VFX_PARENT_EFFECT_STRONG_THRESHOLD",
    "VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS",
    "VFX_RENDER_QUALITY",
    "VFX_EMERGENCY_MAX_PARTICLES_PER_TICK",
    "VFX_EMERGENCY_MAX_PARTICLES_TOTAL",
    "VFX_EMERGENCY_MAX_DRAW_CALLS",
    "VFX_MAGNITUDE_JITTER",
]
