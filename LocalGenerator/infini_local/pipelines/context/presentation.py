"""Stage-relevant parent appearance references; accepted child mechanics own behavior."""
from __future__ import annotations

import copy
from typing import Any

from infini_local.pipelines.context.attack_tables import pack_attack_tables, unpack_attack_tables
from infini_local.pipelines.context.cards import known_attack_context_schema, raw_parent_card_for_llm


def presentation_attack_reference(reference: dict[str, Any], *, stage: str) -> dict[str, Any]:
    """Select known native-v1 appearance facts, retaining unknown reference schemas.

    Native draw layers retain their own equations, bindings and conditions. The
    parent's attack/movement/collision implementation is not a child design
    template: these stages already receive accepted child runtime mechanics.
    """
    if stage not in {"visual", "vfx"}:
        raise ValueError(f"Unknown presentation stage: {stage}")
    try:
        source = unpack_attack_tables(reference)
    except (TypeError, ValueError):
        return copy.deepcopy(reference)
    if not known_attack_context_schema(source):
        return copy.deepcopy(reference)
    for key in ("motionDispatch", "motion", "collision", "positionIntegration"):
        source.pop(key, None)
    source["presentationScope"] = (
        "Parent appearance reference: native drawing, its equations/conditions and coverage remain. "
        "Parent attack, motion and collision implementations are omitted here; accepted child runtime "
        "owns geometry, timing and behavior. Parent appearance is inspiration, not a required copy."
    )
    return pack_attack_tables(source)


def presentation_parent_card_for_llm(item: dict[str, Any], *, stage: str) -> dict[str, Any]:
    """Keep existing literal appearance/scalar facts and project known attack roles."""
    if stage not in {"visual", "vfx"}:
        raise ValueError(f"Unknown presentation stage: {stage}")
    card = raw_parent_card_for_llm(item, include_visual_reference=True)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in list(value.items()):
                if key == "attackReference" and isinstance(child, dict):
                    value[key] = presentation_attack_reference(child, stage=stage)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(card)
    return card
