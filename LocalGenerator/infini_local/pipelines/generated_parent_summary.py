from __future__ import annotations

import json
from typing import Any, Mapping

from infini_local.pipelines.result_identity_policy import normalize_category
from infini_local.pipelines.visual_prompt_contracts import compact_visual_words


def generated_parent_summary_from_data(data: dict[str, Any]) -> dict[str, Any]:
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    effects: list[str] = []
    kinds: list[str] = []
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        kind = str(entity.get("kind") or "")
        if kind and kind != "item_body":
            kinds.append(kind)
        movement = entity.get("movement") if isinstance(entity.get("movement"), Mapping) else {}
        controller = entity.get("controller") if isinstance(entity.get("controller"), Mapping) else {}
        for value in (movement.get("name"), controller.get("name")):
            text = str(value or "").strip()
            if text and text != "none":
                effects.append(text[:64])
        for event in entity.get("events") or []:
            if isinstance(event, Mapping):
                effects.append(f"{event.get('event')}:{event.get('action')}"[:64])
    generated_buff = gameplay.get("generatedBuff") if isinstance(gameplay.get("generatedBuff"), dict) else {}
    if generated_buff and int(generated_buff.get("durationTicks") or 0) > 0:
        effects.append("generated item buff")
    return {
        "name": str(data.get("name") or "")[:80],
        "fantasy": compact_visual_words(concept.get("literalSynthesis") or data.get("tooltip") or data.get("name"), 180),
        "category": normalize_category(data.get("category") or gameplay.get("kind") or "generic"),
        "damageClass": str(gameplay.get("damageClass") or "generic")[:32],
        "runtime": "+".join(sorted(set(kinds)))[:32] if kinds else "item_body_only",
        "visualIdentity": compact_visual_words(visual.get("imagePrompt") or concept.get("literalSynthesis") or data.get("name"), 180),
        "notableEffects": list(dict.fromkeys(effects))[:8],
    }


def attach_generated_parent_summary(data: dict[str, Any]) -> dict[str, Any]:
    data["generatedParentSummary"] = generated_parent_summary_from_data(data)
    data.setdefault("debug", {})["generatedParentSummary"] = json.dumps(data["generatedParentSummary"], ensure_ascii=False)
    return data


__all__ = ["generated_parent_summary_from_data", "attach_generated_parent_summary"]
