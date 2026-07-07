from __future__ import annotations

"""Typed result dataclasses for internal pipeline report boundaries (Stage 3 groundwork).

These give new helper layers a structured object to return instead of opaque
dict[str, Any], while keeping a stable to_dict() shape for debug/balanceReport
consumption. Old pipeline functions are NOT forced to migrate; the rule is that
*new* reports and helpers either return these typed objects or document their dict
schema explicitly (balance_report.py already documents via BALANCE_REPORT_SCHEMA_VERSION).

Design: frozen dataclasses with explicit fields, a kind tag, a reason, and a
to_dict() that round-trips for JSON debug output. No mutation in place — return a
new record on change. This keeps provenance/clamp records easy to reason about.
"""
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class ClampRecord:
    """One clamp applied during soft-balance or hard-safety post-authoring.

    kind: balance | safety | contract
    source: engineCall fn-name or pipeline stage that produced the value being clamped
    reason: short machine-readable token (e.g. "authored_damage_soft_envelope")
    """
    field: str
    raw: Any
    final: Any
    kind: str
    reason: str
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "field": self.field,
            "raw": self.raw,
            "final": self.final,
            "kind": self.kind,
            "reason": self.reason,
            "source": self.source,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


@dataclass(frozen=True)
class RepairResult:
    """Outcome of a single repair boundary decision.

    kind: code_repaired | retry_attempted | retry_accepted | patch | rejected_fields | fatal
    """
    kind: str
    attempted: bool = False
    accepted: bool = False
    rejected_fields: tuple[str, ...] = ()
    patch: dict[str, Any] | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "attempted": self.attempted,
            "accepted": self.accepted,
            "rejectedFields": list(self.rejected_fields),
            "patch": self.patch,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RuntimeCompileResult:
    """Result of compiling a runtimePlan into a genome patch.

    provenance maps field -> engineCall that authored it (see runtime_authoring).
    errors is a list of compact error dicts (empty on success).
    """
    patch: dict[str, Any]
    provenance: dict[str, Any]
    provenance_source: str = "runtime_plan_provenance_report"
    clamps: tuple[ClampRecord, ...] = ()
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch": self.patch,
            "provenance": self.provenance,
            "provenanceSource": self.provenance_source,
            "clamps": [c.to_dict() for c in self.clamps],
            "errors": list(self.errors),
        }

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class BalanceReportModel:
    """Typed shape mirroring build_balance_report() output in balance_report.py.

    powerBand: {"bucket": str, "min": int, "max": int, ...} from power_band_for_bucket
    label: short human-readable stage label
    authored: {"damage": ..., "useTime": ..., "shotCount": ...}
    final: {"category": ..., "damage": ..., "useTime": ..., "rarity": ...}
    clamps: {"balance": [...], "safety": [...], "contract": [...]} taxonomy
    """
    schema: str = "infini.balance-report.v1"
    power_band: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    authored: dict[str, Any] = field(default_factory=dict)
    final: dict[str, Any] = field(default_factory=dict)
    clamps: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    repair: dict[str, Any] = field(default_factory=dict)
    parents: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": self.schema,
            **self.power_band,
            "label": self.label,
            "authored": self.authored,
            "final": self.final,
            "clamps": self.clamps,
            "repair": self.repair,
            "parents": self.parents,
        }
        return out

    @classmethod
    def from_report_dict(cls, report: dict[str, Any]) -> "BalanceReportModel":
        """Wrap an existing build_balance_report() dict into the typed model."""
        # build_balance_report() spreads **band into the report top level.  band
        # keys are powerBand/label/sourceBucket (not bucket/min/max — those live
        # in POWER_BAND_BY_BUCKET itself).
        band_keys = {"powerBand", "label", "sourceBucket"}
        power_band = {k: report[k] for k in band_keys if k in report}
        return cls(
            schema=report.get("schema", "infini.balance-report.v1"),
            power_band=power_band,
            label=report.get("label", ""),
            authored=report.get("authored", {}),
            final=report.get("final", {}),
            clamps=report.get("clamps", {}),
            repair=report.get("repair", {}),
            parents=report.get("parents", {}),
        )


__all__ = [
    "ClampRecord",
    "RepairResult",
    "RuntimeCompileResult",
    "BalanceReportModel",
]
