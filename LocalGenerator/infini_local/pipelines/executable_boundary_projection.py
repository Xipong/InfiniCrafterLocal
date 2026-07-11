from __future__ import annotations

from typing import Any


# Presentation-only authoring hints historically lived in attack for convenience.
# AttackSpec is now a strict executable Python <-> C# DTO, so these fields must be
# projected back to the visual owner before boundary validation or delivery.
ATTACK_PRESENTATION_ONLY_FIELDS = frozenset({
    "vfxIntent",
    "projectileVfx",
    "impactVfx",
    "childVfx",
    "fieldVfx",
    "vfxScaleHint",
    "vfxRhythmHint",
    "vfxAvoid",
    "vfxMaterialHints",
})


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def project_attack_presentation_fields(
    data: dict[str, Any],
    *,
    source: str = "pipeline",
) -> dict[str, Any]:
    """Move known visual-only legacy fields out of ``attack``.

    The projection is intentionally narrow: unknown fields stay in ``attack`` so the
    strict executable boundary can reject them.  Existing non-empty visual values win;
    this helper never re-authors presentation or gameplay.
    """
    if not isinstance(data, dict):
        return data
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else None
    if not attack:
        return data
    visual = data.setdefault("visual", {})
    if not isinstance(visual, dict):
        visual = {}
        data["visual"] = visual

    moved: list[str] = []
    preserved_visual: list[str] = []
    for key in sorted(ATTACK_PRESENTATION_ONLY_FIELDS):
        if key not in attack:
            continue
        value = attack.pop(key)
        if _is_empty(visual.get(key)) and not _is_empty(value):
            visual[key] = value
        elif not _is_empty(value):
            preserved_visual.append(key)
        moved.append(key)

    if moved:
        debug = data.setdefault("debug", {})
        if not isinstance(debug, dict):
            debug = {}
            data["debug"] = debug
        rows = debug.setdefault("attackPresentationProjection", [])
        if not isinstance(rows, list):
            rows = []
            debug["attackPresentationProjection"] = rows
        rows.append({
            "source": str(source or "pipeline"),
            "moved": moved,
            "visualValuePreserved": preserved_visual,
        })
        del rows[:-12]
    return data


__all__ = ["ATTACK_PRESENTATION_ONLY_FIELDS", "project_attack_presentation_fields"]
