from __future__ import annotations

from typing import Any, Iterable


# AGENT MAP: code-owned soft balance policy.
# Balance clamps are diagnostics and bounded normalization, not a second design pass.
# Keep clamp reasons explicit so C# applied traces and agent audits can explain changes.
# Single Python-side source of truth for coarse balance power bands.
# These are NOT progression gates and are NOT sent to the LLM as dynamic caps.
# They are labels for post-authoring validation/reporting only.
POWER_BAND_BY_BUCKET: dict[str, tuple[str, str]] = {
    "wood": ("power_00", "wood/basic-like"),
    "early": ("power_01", "early-like"),
    "pre_boss": ("power_02", "pre-boss-like"),
    "pre_hardmode_late": ("power_03", "late pre-Hardmode-like"),
    "hardmode_early": ("power_04", "early Hardmode-like"),
    "mech": ("power_05", "mechanical-boss-like"),
    "plantera": ("power_06", "Plantera/post-mech-like"),
    "lunar": ("power_07", "lunar-like"),
    "endgame": ("power_08", "endgame-like"),
}

# Single code-owned numeric balance layer.
# v0.4.215 intentionally sits above a vanilla-like baseline: generated items should
# feel spicy first and be easy to nerf later, while still staying bounded.
VANILLA_LIKE_WEAPON_ENVELOPES: dict[str, dict[str, float]] = {
    "wood": {"min": 4, "max": 24, "dps": 80, "weak_bonus": 14},
    "early": {"min": 5, "max": 40, "dps": 130, "weak_bonus": 18},
    "pre_boss": {"min": 7, "max": 62, "dps": 215, "weak_bonus": 24},
    "pre_hardmode_late": {"min": 14, "max": 94, "dps": 330, "weak_bonus": 32},
    "hardmode_early": {"min": 22, "max": 155, "dps": 560, "weak_bonus": 42},
    "mech": {"min": 30, "max": 215, "dps": 820, "weak_bonus": 56},
    "plantera": {"min": 40, "max": 310, "dps": 1200, "weak_bonus": 72},
    "lunar": {"min": 55, "max": 440, "dps": 1780, "weak_bonus": 92},
    "endgame": {"min": 70, "max": 640, "dps": 2750, "weak_bonus": 120},
}

ENDGAME_BUCKET_ALIASES: set[str] = {
    "post_moonlord", "post_moon_lord", "superboss", "devourer", "auric",
    "exo_yharon_plus", "shadowspec", "calamity_red_prefix",
}

DEFAULT_POWER_BUCKET = "pre_boss"
ENDGAME_POWER_BUCKET = "endgame"


def _raw_bucket_name(stage: dict[str, Any] | str | None) -> str:
    if isinstance(stage, dict):
        raw = stage.get("name") or stage.get("stage") or DEFAULT_POWER_BUCKET
    else:
        raw = stage or DEFAULT_POWER_BUCKET
    return str(raw).strip() or DEFAULT_POWER_BUCKET


def canonical_power_bucket(stage: dict[str, Any] | str | None, *, extra_endgame_aliases: Iterable[str] = ()) -> str:
    name = _raw_bucket_name(stage)
    if name.endswith("_influenced"):
        return ENDGAME_POWER_BUCKET
    if name in VANILLA_LIKE_WEAPON_ENVELOPES:
        return name
    extra = {str(x) for x in extra_endgame_aliases}
    if name in ENDGAME_BUCKET_ALIASES or name in extra:
        return ENDGAME_POWER_BUCKET
    return DEFAULT_POWER_BUCKET


def power_band_for_bucket(stage: dict[str, Any] | str | None) -> dict[str, str]:
    bucket = canonical_power_bucket(stage)
    band, label = POWER_BAND_BY_BUCKET.get(bucket, POWER_BAND_BY_BUCKET[DEFAULT_POWER_BUCKET])
    return {"powerBand": band, "label": label, "sourceBucket": bucket}


def weapon_envelope_for_bucket(stage: dict[str, Any] | str | None, *, extra_endgame_aliases: Iterable[str] = ()) -> dict[str, float]:
    bucket = canonical_power_bucket(stage, extra_endgame_aliases=extra_endgame_aliases)
    return dict(VANILLA_LIKE_WEAPON_ENVELOPES[bucket], name=bucket)
