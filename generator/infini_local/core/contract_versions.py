from __future__ import annotations

from typing import Any


# Concrete engine facts exposed by /health for operator diagnostics, not authoring.
TMODLOADER_GREY_ZONE_NOTES: dict[str, str] = {
    "holdoutOffset": "ModItem.HoldoutOffset is relevant for useStyle 5 non-staff held items; other use styles need different draw/hold paths.",
    "heldAnimation": "HoldItemFrame/HoldStyle can affect held animation/location, while projectile movement/rotation lives on the projectile path.",
    "projectileRotation": "Projectile sprites need an explicit rotation policy; the PNG alone does not animate a throw.",
    "projectileNetState": "Projectile.ai fields sync automatically; custom AI state needs SendExtraAI/ReceiveExtraAI or netUpdate.",
}


def build_contract_versions(
    *,
    app_version: str,
    recipe_identity_version: str,
    runtime_api_version: str,
    visual_pipeline_profile: str,
) -> dict[str, Any]:
    """Stamp current executable formats and configured pipeline for diagnostics."""
    return {
        "appVersion": str(app_version),
        "recipeIdentityVersion": str(recipe_identity_version),
        "runtimeApiVersion": str(runtime_api_version),
        "visualPipelineProfile": str(visual_pipeline_profile),
    }
