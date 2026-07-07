from __future__ import annotations

from typing import Any

# Stable runtime on-hit ids that visibly call BurstDust in the C# executor.
# Keep this as a semantic policy, not per-item exception data.
ONHIT_BURST = 1
ONHIT_AURA_PULSE = 10
ONHIT_LIFESTEAL = 17
BURST_DUST_FEEDBACK_ONHIT_CODES = frozenset({
    ONHIT_BURST,
    ONHIT_AURA_PULSE,
    ONHIT_LIFESTEAL,
})
BURST_DUST_FEEDBACK_ONHIT_NAMES = frozenset({
    "burst",
    "aura_pulse",
    "lifesteal",
    "heal",
})


def _int_code(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def onhit_uses_burst_dust_feedback(onhit: Any, onhit_code: Any) -> bool:
    """Return whether this on-hit executor needs visible BurstDust feedback.

    This mirrors GeneratedProjectile.Visuals.cs::OnHitUsesBurstDustFallback.
    The predicate is deliberately tiny: broad visual styles belong in VFX manifests,
    not in an ever-growing item/keyword exception table.
    """
    key = str(onhit or "").strip().lower()
    if key in BURST_DUST_FEEDBACK_ONHIT_NAMES:
        return True
    return _int_code(onhit_code) in BURST_DUST_FEEDBACK_ONHIT_CODES
