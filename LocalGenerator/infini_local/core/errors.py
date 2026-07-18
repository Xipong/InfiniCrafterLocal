from __future__ import annotations

from typing import Any


class PlannerUnavailable(RuntimeError):
    """Raised when no authored LLM result is available for a real craft."""

    def __init__(
        self,
        *args: object,
        author_repair_rejected_domains: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(*args)
        self.author_repair_rejected_domains = list(author_repair_rejected_domains or [])


__all__ = ["PlannerUnavailable"]
