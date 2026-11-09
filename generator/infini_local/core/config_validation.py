"""Pure current-configuration checks, shared by launchers and offline preflight.

Retired routing keys are refused; inert framing settings warn only.
Neither category is an alias, migration or default.
The configuration file and its unknown keys remain untouched for user correction.
"""
from __future__ import annotations

from typing import Mapping
import warnings


RETIRED_CONFIG_REPLACEMENTS = {
    "INFINI_LLM_REAUTHOR_TEMPERATURE": "INFINI_LLM_REPAIR_TEMPERATURE",
    "INFINI_LLM_FALLBACK_NETWORK_FAILS": "INFINI_LLM_NETWORK_ATTEMPTS",
    **{f"INFINI_LLM_FALLBACK_{suffix}": f"INFINI_LLM_POOL_2_{suffix} (enable the profile explicitly)"
       for suffix in ("PROVIDER", "MODEL", "BASE_URL", "API_KEY", "OPENROUTER_PROVIDER")},
    **{f"INFINI_OPENAI_COMPAT_IMAGE_{suffix}": f"INFINI_IMAGE_API_{suffix}"
       for suffix in ("BASE_URL", "MODEL", "SIZE")},
    "INFINI_OPENAI_COMPAT_IMAGE_API_KEY": "INFINI_IMAGE_API_KEY",
    **{f"INFINI_PIXEL_{suffix}": f"INFINI_COMFYUI_{suffix}"
       for suffix in ("LORA_NAME", "LORA_WEIGHT", "TRIGGER")},
    "INFINI_ITEMS_DUMP": "INFINI_ITEMS_RUNTIME_DUMP",
    "INFINI_PROJECTILES_DUMP": "INFINI_PROJECTILES_RUNTIME_DUMP",
}


def retired_config_errors(values: Mapping[str, str]) -> list[str]:
    """Name retired active keys and their replacements, never their values."""
    return [f"{name}: use {replacement}" for name, replacement in RETIRED_CONFIG_REPLACEMENTS.items()
            if values.get(name, "").strip()]


def reject_retired_config(values: Mapping[str, str]) -> None:
    for role in ("PROJECTILE", "CHILD"):
        name = f"INFINI_{role}_ICON_TARGET_FILL"
        if values.get(name, "").strip():
            warnings.warn(f"{name}: obsolete and ignored; remove this setting (no replacement).",
                          UserWarning)
    errors = retired_config_errors(values)
    if errors:
        raise ValueError("Retired configuration settings; update config.env or the process environment: "
                         + "; ".join(errors))
