"""Shared application recommendations, not provider routing or authored defaults.

Budget/timeouts match the successful Luna Live10 receipts (18k / 600s).
Temperature/effort are the accepted campaign baseline, not a controlled quality
comparison. Explicit user/provider overrides remain authoritative.
"""
from __future__ import annotations

GENERATION_DEFAULTS = {
    'INFINI_LLM_MAX_TOKENS': '18000',
    'INFINI_LLM_TIMEOUT': '600',
    'INFINI_LLM_REASONING_MODE': 'medium',
    'INFINI_LLM_TEMPERATURE': '0.5',
    'INFINI_VISUAL_DIRECTOR_TEMPERATURE': '0.45',
}
