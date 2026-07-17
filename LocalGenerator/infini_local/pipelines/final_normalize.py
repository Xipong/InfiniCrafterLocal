from __future__ import annotations

"""Final normalization seam for generated item JSON.

This module is the single owner of delivery-time normalization. It may make
emitted data consistent and debuggable, but must not invent mechanics after
runtimePlan validation.
"""

from typing import Any, Callable

from infini_local.core.config_bootstrap import APP_VERSION
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION

from infini_local.pipelines.presentation_sound import presentation_from_genome

from infini_local.pipelines.result_identity_policy import (
    bad_result_name,
)
from infini_local.pipelines.result_knowledge_card import build_result_item_card


def final_normalize(data: dict[str, Any]) -> dict[str, Any]:
    data.pop("_llmHistory", None)
    data.pop("_runtimePlanCompileCache", None)
    data.setdefault("schemaVersion", 1)
    # Runtime API/engine-call contract version is intentionally separate from the
    # project build version. C# can reject future unsupported executable contracts
    # instead of silently losing behavior.
    data.setdefault("runtimeApiVersion", ENGINE_RUNTIME_API_VERSION)
    data.setdefault("itemKnowledge", {})
    visual = data.setdefault("visual", {})
    if isinstance(visual.get("palette"), list):
        visual["palette"] = [str(x) for x in visual.get("palette", []) if str(x).strip()][:8]
    if not isinstance(data.get("presentationGenome"), dict) or not data.get("presentationGenome"):
        data["presentationGenome"] = presentation_from_genome(data)


    if isinstance(data["itemKnowledge"], dict) and "resultCard" not in data["itemKnowledge"]:
        data["itemKnowledge"]["resultCard"] = build_result_item_card(data, {}, {})
    parent_a_for_name = {"name": data.get("parentA", "")}
    parent_b_for_name = {"name": data.get("parentB", "")}
    if bad_result_name(data.get("name"), parent_a_for_name, parent_b_for_name):
        raise PlannerUnavailable("final result name is invalid after validation; craft failed and ingredients must be refunded")
    data.setdefault("debug", {})
    data["debug"].setdefault("generator", "InfiniCrafterLocal")
    data["debug"].setdefault("version", APP_VERSION)
    # C# JsonSerializer uses PascalCase properties but is case-insensitive; camelCase is fine.
    return data


def normalize_generated_item_json(
    data: dict[str, Any],
    *,
    normalize_category: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    out = dict(data)
    if normalize_category is not None:
        out["category"] = normalize_category(out.get("category"))
        gp = out.get("gameplay") if isinstance(out.get("gameplay"), dict) else None
        if gp is not None and gp.get("kind"):
            gp["kind"] = normalize_category(gp.get("kind"))
    out.setdefault("debug", {})
    out.setdefault("recipeMeta", {})
    return out


__all__ = ["final_normalize", "normalize_generated_item_json"]
