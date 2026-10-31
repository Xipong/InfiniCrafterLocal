"""Attributed chat messages for the finite LLM pipeline.

``role`` preserves Chat Completions authority, stage-specific system content and the
latest user packet define model-visible authority/current truth, and ``name`` is a
finite trace/provider hint.
"""

from __future__ import annotations

from infini_local.core import llm_config


def generation_art_direction() -> str:
    """An explicit user-selected art brief, not a gameplay or asset-mode router."""
    if llm_config.PROMPT_STYLE == "Default":
        return ""
    if llm_config.PROMPT_STYLE != "Terraria Like":
        raise ValueError(f"INFINI_PROMPT_STYLE must be Default or Terraria Like, got {llm_config.PROMPT_STYLE!r}")
    return (
        "Terraria Like art direction: aim for a vanilla-Terraria-like item rather than a miniature high-resolution illustration. "
        "Use a readable silhouette, economical pixel clusters, a compact coherent palette, discrete shadow/highlight bands, "
        "and selective material detail readable at 1x gameplay size. Avoid dense grain, many near-identical tones, smooth "
        "painterly gradients, glossy rendering and unrelated ornament. Preserve literal geometry, materials and identity. "
        "Effects should support that identity with coherent colours and clear rhythms; purposeful spectacle is still legal. "
        "Apply crisp-pixel guidance to solid forms, preserving intentional soft-alpha glows, effect textures and required texture layout."
    )


def generation_system_suffix() -> str:
    """Shared target-game guidance, without selecting authored mechanics."""
    direction = generation_art_direction()
    return (
        "\n\nTarget game: Terraria (tModLoader). Create a generated item or its presentation assets for that game, "
        "not a standalone illustration. When creating a new design, draw on relevant parent characteristics "
        "while allowing a coherent transformation. Follow the exact requested output contract. "
        "Art direction is advisory, never permission to change accepted gameplay or frozen fields."
    ) + (f"\n\n{direction}" if direction else "")


# Canonical speaker identities for OpenAI-compatible Chat Completions.  ``role``
# keeps transport authority (system/user/assistant); ``name`` identifies the
# concrete InfiniCrafter pipeline participant for traces and compatible providers.
# Correctness must not depend on the model reading optional ``name`` metadata.
STAGE_MESSAGE_NAMES = frozenset({
    "item_author_contract",
    "recipe_context",
    "author_repair_contract",
    "author_repair_context",
    "visual_director_contract",
    "visual_director_context",
    "visual_repair_contract",
    "visual_repair_context",
    "vfx_director_contract",
    "vfx_director_context",
    "vfx_repair_contract",
    "vfx_repair_context",
})


def stage_chat_message(role: str, name: str, content: str) -> dict[str, str]:
    """Build one attributed Chat Completions message from a finite speaker set."""
    role = str(role or "").strip().lower()
    name = str(name or "").strip()
    content = str(content or "")
    if role not in {"system", "user", "assistant"}:
        raise ValueError(f"unsupported chat role: {role!r}")
    if name not in STAGE_MESSAGE_NAMES:
        raise ValueError(f"unsupported pipeline message name: {name!r}")
    return {"role": role, "name": name, "content": content}


__all__ = [
    "STAGE_MESSAGE_NAMES",
    "generation_system_suffix",
    "generation_art_direction",
    "stage_chat_message",
]
