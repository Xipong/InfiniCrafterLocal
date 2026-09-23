from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.item_identity_tools import generated_data_of, name_of


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def generated_parent_summary_from_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return exact recursive context from the final accepted runtime truth.

    The summary never reinterprets mechanics. It exposes the same Author's late
    realization verbatim plus notable effects taken from that realization's own
    program-vs-report self-evaluation. Aligned rows prefer the reported wording;
    mismatched, omitted, or uncertain rows prefer the executable-program account
    so a diagnosed prose error is not propagated recursively. No model-authored
    claims or claim ids are involved.
    """
    result_id = str(data.get("id") or "").strip()
    if not result_id:
        raise ValueError("generatedParentSummary requires the accepted top-level generated id")
    runtime = _mapping(data.get("runtimeProgram"))
    realization = _mapping(data.get("realization"))
    program_vs_report = _mapping(_mapping(realization.get("selfEvaluation")).get("programVsReport"))
    notable_effects: list[str] = []
    for check in _rows(program_vs_report.get("behaviorChecks")):
        result = str(check.get("result") or "").strip()
        reported = str(check.get("reportedBehavior") or "").strip()
        programmed = str(check.get("programBehavior") or "").strip()
        text = (reported or programmed) if result == "aligned" else (programmed or reported)
        if text and text not in notable_effects:
            notable_effects.append(text)
    return {
        "schema": "infini.generated-parent-summary.v2",
        "name": str(data.get("name") or "Generated Item"),
        "identity": "generated:" + result_id,
        "description": str(realization.get("description") or "").strip(),
        "playerExperience": str(realization.get("playerExperience") or "").strip(),
        "notableEffects": notable_effects[:12],
        "runtimePrimaryEntityId": str(runtime.get("primaryEntityId") or runtime.get("itemEntityId") or ""),
        "runtimeEntityIds": [str(row.get("id") or "") for row in _rows(runtime.get("entities")) if str(row.get("id") or "")],
    }


def attach_generated_parent_summary(data: dict[str, Any]) -> dict[str, Any]:
    data["generatedParentSummary"] = generated_parent_summary_from_data(data)
    return data


def generated_parent_summary_of(item: Mapping[str, Any]) -> dict[str, Any]:
    generated = generated_data_of(dict(item))
    summary = generated.get("generatedParentSummary")
    if isinstance(summary, Mapping):
        return copy.deepcopy(dict(summary))
    direct = item.get("generatedParentSummary")
    if isinstance(direct, Mapping):
        return copy.deepcopy(dict(direct))
    return {}


def generated_parent_name(item: Mapping[str, Any]) -> str:
    summary = generated_parent_summary_of(item)
    return str(summary.get("name") or name_of(dict(item))).strip()


__all__ = [
    "attach_generated_parent_summary",
    "generated_parent_name",
    "generated_parent_summary_from_data",
    "generated_parent_summary_of",
]
