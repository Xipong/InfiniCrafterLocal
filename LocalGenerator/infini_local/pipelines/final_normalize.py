from __future__ import annotations

"""Final normalization seam for generated item JSON.

This module is the single owner of delivery-time normalization. It may make
emitted data consistent and debuggable, but must not invent mechanics after
runtimeProgram validation.
"""

from typing import Any

from infini_local.core.config_bootstrap import APP_VERSION
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION


from infini_local.pipelines.result_identity_policy import (
    bad_result_name,
)


def final_normalize(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("schemaVersion", 5)
    # Runtime API/engine-call contract version is intentionally separate from the
    # project build version. C# can reject future unsupported executable contracts
    # instead of silently losing behavior.
    data.setdefault("runtimeApiVersion", RUNTIME_PROGRAM_API_VERSION)
    visual = data.setdefault("visual", {})
    if isinstance(visual.get("palette"), list):
        visual["palette"] = [str(x) for x in visual.get("palette", []) if str(x).strip()][:8]

    parent_a_for_name = {"name": data.get("parentA", "")}
    parent_b_for_name = {"name": data.get("parentB", "")}
    if bad_result_name(data.get("name"), parent_a_for_name, parent_b_for_name):
        raise PlannerUnavailable("final result name is invalid after validation; craft failed and ingredients must be refunded")
    data.setdefault("debug", {})
    data["debug"].setdefault("generator", "InfiniCrafterLocal")
    data["debug"].setdefault("version", APP_VERSION)
    # C# JsonSerializer uses PascalCase properties but is case-insensitive; camelCase is fine.
    return data


__all__ = ["final_normalize"]
