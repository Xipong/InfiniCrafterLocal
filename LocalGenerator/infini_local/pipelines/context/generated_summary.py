from __future__ import annotations

from typing import Any, Mapping

from infini_local.core.runtime_authoring.program_schema import realization_schema


# .NET String.Trim whitespace (not Python's additional U+001C..U+001F).
_REPORT_WHITESPACE = "\t\n\v\f\r\x85\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"


def _bounded_report(value: Any, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    # Use GeneratedParentSummarySpec.BoundedReport's scalar-length limit, not
    # UTF-16 storage units. Invalid surrogate text is replaced only in this
    # explicitly lossy display/context projection; raw realization stays intact.
    scalars = value.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le", errors="replace")
    return scalars.strip(_REPORT_WHITESPACE)[:maximum]


def generated_parent_summary_from_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Copy optional Author prose as advisory parent context, never runtime truth.

    Runtime identities and mechanics remain in their canonical runtimeProgram;
    self-evaluation verdicts never select or certify a behavior description.
    """
    result_id = str(data.get("id") or "").strip()
    if not result_id:
        raise ValueError("generatedParentSummary requires the accepted top-level generated id")
    realization = data.get("realization")
    realization = {"description": realization} if isinstance(realization, str) else realization if isinstance(realization, Mapping) else {}
    limits = realization_schema()["properties"]
    return {
        "schema": "infini.generated-parent-summary.v2",
        "name": str(data.get("name") or "Generated Item"),
        "identity": "generated:" + result_id,
        "description": _bounded_report(realization.get("description"), limits["description"]["maxLength"]),
        "playerExperience": _bounded_report(realization.get("playerExperience"), limits["playerExperience"]["maxLength"]),
    }


def attach_generated_parent_summary(data: dict[str, Any]) -> dict[str, Any]:
    data["generatedParentSummary"] = generated_parent_summary_from_data(data)
    return data


__all__ = ["attach_generated_parent_summary", "generated_parent_summary_from_data"]
