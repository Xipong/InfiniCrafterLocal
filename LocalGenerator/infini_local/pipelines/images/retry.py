"""Image retry instructions from concrete technical diagnostics."""

from __future__ import annotations

from typing import Any


from infini_local.core.env_utils import env_int
from infini_local.pipelines.images.prompts import image_generation_prompt_suffix
from infini_local.services.visual_asset_pipeline import compact_zimage_asset_prompt
from infini_local.core.images.contracts import (
    chroma_name,
    image_backend_is_zimage,
    role_contract_prompt_clause,
    sprite_background_positive_clause,
    uses_key_background,
)


def validation_retry_notes(validation: dict[str, Any] | None, role: str = "item") -> str:
    if not isinstance(validation, dict):
        return ""
    reasons = [str(x) for x in (validation.get("reasons") or []) if str(x).strip()]
    bbox = validation.get("bboxStats") if isinstance(validation.get("bboxStats"), dict) else {}
    notes: list[str] = []
    keyed = uses_key_background()
    key_left = (
        f"keep the {chroma_name()} perfectly flat and do not paint the key color into the object"
        if keyed
        else "request native alpha on a transparent background, not a solid key"
    )
    missing_alpha = (
        f"keep the {chroma_name()} with a cleanly separated object"
        if keyed
        else "use native alpha with empty transparent space around the authored subject"
    )
    dense_area = (
        "remove any white/pink poster card or inner background; only the actual sprite body may remain outside the configured key"
        if keyed
        else "remove any opaque poster card or inner background; preserve only the authored sprite body and native alpha"
    )
    mapping = [
        ("core_silhouette_too_small", "make the main subject noticeably larger inside the frame"),
        ("core_silhouette_too_large", "shrink the subject slightly so a thin safety border remains"),
        ("effect_extent_too_large", "keep glows or residue tighter to the subject"),
        ("object_touches_edges", "do not touch the image edges; leave a thin border"),
        ("magenta_key_background_left", key_left),
        ("almost_no_transparency_after_bg_removal", missing_alpha),
        ("too_few_opaque_pixels", "use a more solid readable silhouette with less emptiness"),
        ("very_dense_opaque_area", dense_area),
        ("empty_alpha_bbox", "draw the authored role asset, not an empty image"),
        (
            "projectile_forward_axis_misaligned",
            "use canonical local +X: leading tip/nose screen-right and tail/trail screen-left; runtime rotates this axis to world velocity",
        ),
    ]
    for raw, msg in mapping:
        if any(str(r).startswith(raw) for r in reasons):
            notes.append(msg)
    core_long = bbox.get("core_long_axis") if isinstance(bbox, dict) else None
    if core_long:
        notes.append(f"current visible core long axis is about {core_long}px after postprocess; improve role readability")
    return "; ".join(dict.fromkeys(notes))[:700]


def build_retry_prompt_from_validation(prompt: str, validation: dict[str, Any] | None, role: str, attempt: int, canvas: int) -> str:
    # Compact the same historical subject/technical core in both styles, then
    # append the explicit brief. It must not consume the core's existing budget
    # or disappear when the final technical diagnostic is reserved by Z-Image.
    guidance = image_generation_prompt_suffix()
    prompt = str(prompt or "")
    if prompt.endswith(guidance):
        prompt = prompt[: -len(guidance)]
    bg = sprite_background_positive_clause()
    contract = role_contract_prompt_clause(role, canvas)
    notes = validation_retry_notes(validation, role)
    if image_backend_is_zimage():
        retry_parts = [
            str(prompt or ""),
            f"Revision {attempt}: preserve the same exact {role} subject, quantity, action, state, materials, and colors.",
            f"Composition correction: keep the authored {role} components within the sprite bounds and make their physical arrangement clearer.",
            str(contract),
            f"Background correction: {bg}.",
            ("Technical correction: " + notes) if notes else "",
        ]
        return compact_zimage_asset_prompt(retry_parts, role, limit=env_int("INFINI_ZIMAGE_RETRY_PROMPT_LIMIT", 2200)) + guidance
    extra = (
        f" STRICT RETRY {attempt}: draw the authored {role} physical arrangement, keep visible components within the sprite bounds, make it readable, "
        f"{contract}, {bg}, "
        "no checkerboard, no UI, no text, no scene, no ground, no shadow, no crop"
    )
    if notes:
        extra += ", fix these technical issues: " + notes
    return (str(prompt or "") + ", " + extra)[:2800] + guidance
