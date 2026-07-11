from __future__ import annotations


class PlannerUnavailable(RuntimeError):
    """Raised when no authored LLM result is available for a real craft."""


__all__ = ["PlannerUnavailable"]
