from __future__ import annotations

"""Canonical bootstrap/config surface for the local generator runtime.

This module owns process-env loading, root paths, cache directories, and public
bootstrap constants. Pipeline and HTTP layers import these values instead of
redeclaring bootstrap state locally.
"""

from pathlib import Path

from infini_local.core.env_utils import env_path, env_str, load_env_file

APP_VERSION = "0.4.237"

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.env"
DATA_DIR = ROOT / "data"

load_env_file(CONFIG_PATH)

RECIPE_IDENTITY_VERSION = env_str("INFINI_RECIPE_IDENTITY_VERSION", "recipe_v4_25_no_item_family_routing")
CACHE_DIR = env_path("INFINI_CACHE_DIR", ROOT / "cache")
SPRITE_DIR = CACHE_DIR / "sprites"
WORLD_RECIPES_DIR = env_path("INFINI_WORLD_RECIPES_DIR", CACHE_DIR / "world_recipes")

CACHE_DIR.mkdir(parents=True, exist_ok=True)
SPRITE_DIR.mkdir(parents=True, exist_ok=True)
WORLD_RECIPES_DIR.mkdir(parents=True, exist_ok=True)

# Public URL other Terraria clients should use to fetch generated assets from this generator.
# Leave empty to let the tModLoader host advertise its own configured/guessed URL.
ASSET_PUBLIC_BASE_URL = env_str("INFINI_ASSET_PUBLIC_BASE_URL", "").rstrip("/")
TERRARIA_PORT = env_str("INFINI_TERRARIA_PORT", "7777") or "7777"

__all__ = [
    "APP_VERSION",
    "RECIPE_IDENTITY_VERSION",
    "ROOT",
    "CONFIG_PATH",
    "DATA_DIR",
    "CACHE_DIR",
    "SPRITE_DIR",
    "WORLD_RECIPES_DIR",
    "ASSET_PUBLIC_BASE_URL",
    "TERRARIA_PORT",
]
