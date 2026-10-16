from __future__ import annotations

from typing import Any, Mapping


def generated_parent_summary_from_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Copy optional Author prose as advisory parent context, never runtime truth.

    Runtime identities and mechanics remain in their canonical runtimeProgram;
    self-evaluation verdicts never select or certify a behavior description.
    """
    result_id = str(data.get("id") or "").strip()
    if not result_id:
        raise ValueError("generatedParentSummary requires the accepted top-level generated id")
    realization = data.get("realization")
    realization = realization if isinstance(realization, Mapping) else {}
    return {
        "schema": "infini.generated-parent-summary.v2",
        "name": str(data.get("name") or "Generated Item"),
        "identity": "generated:" + result_id,
        "description": realization.get("description") if isinstance(realization.get("description"), str) else "",
        "playerExperience": realization.get("playerExperience") if isinstance(realization.get("playerExperience"), str) else "",
    }


def attach_generated_parent_summary(data: dict[str, Any]) -> dict[str, Any]:
    data["generatedParentSummary"] = generated_parent_summary_from_data(data)
    return data


__all__ = ["attach_generated_parent_summary", "generated_parent_summary_from_data"]
