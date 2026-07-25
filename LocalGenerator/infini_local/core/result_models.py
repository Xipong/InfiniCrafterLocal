from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# AGENT MAP: typed helper results at contract boundaries. These dataclasses make
# clamps/repair/runtime compile outcomes explicit, but they do not mean the whole
# LocalGenerator pipeline is fully typed; many callers still pass dict[str, Any].
ClampKind = Literal["balance", "safety", "contract"]


@dataclass(slots=True)
class ClampRecord:
    """Canonical record for a bounded value after authoring.

    `raw` is the authored/proposed value, `final` is the value emitted to the
    game-facing schema, and `kind` explains which layer made the change.
    """

    field: str
    raw: Any
    final: Any
    kind: ClampKind
    reason: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RepairResult:
    """Typed summary of the repair boundary without becoming a second author."""

    kind: str
    code_repaired: bool = False
    retry_attempted: bool = False
    retry_accepted: bool = False
    patch: dict[str, Any] = field(default_factory=dict)
    rejected_fields: list[str] = field(default_factory=list)
    fatal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BalanceReportModel:
    """Stable top-level shape for debug.balanceReport."""

    schema: str
    powerBand: str
    label: str
    authored: dict[str, Any]
    final: dict[str, Any]
    clamps: dict[str, list[dict[str, Any]]]
    repair: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema": self.schema,
            **self.extra,
            "powerBand": self.powerBand,
            "label": self.label,
            "authored": dict(self.authored),
            "final": dict(self.final),
            "clamps": dict(self.clamps),
            "repair": dict(self.repair),
        }
        return out


def as_plain_dict(value: Any) -> Any:
    """Convert supported typed helper results to JSON-ready containers."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, list):
        return [as_plain_dict(v) for v in value]
    if isinstance(value, tuple):
        return [as_plain_dict(v) for v in value]
    if isinstance(value, dict):
        return {str(k): as_plain_dict(v) for k, v in value.items()}
    return value
