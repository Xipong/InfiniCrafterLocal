"""Source wiring guards; native behavior belongs to EngineRuntimeChecks.

These checks do not execute C# or simulate Terraria's damage loop.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.DamageGate.cs"


def _code() -> str:
    return " ".join(re.sub(r"//[^\n]*", "", SOURCE.read_text(encoding="utf-8")).split())


def test_contact_gate_uses_native_hook_without_forcing_damage() -> None:
    code = _code()
    assert "public override bool? CanDamage()" in code
    assert "return null;" in code
    assert "return true;" not in code


def test_pending_disabled_and_delayed_proxies_cannot_damage() -> None:
    assert (
        "if (!_configured || _entity is null || !_entity.Damage.Enabled || _activationDelayTicks > 0) return false;"
        in _code()
    )


def test_unreleased_charge_is_blocked_independently_of_friendly() -> None:
    assert (
        "if (_entity.Controller.Code == RuntimeControllerCode.ChargeThenRelease && !_released) return false;"
        in _code()
    )


def test_beam_gate_reuses_live_warmup_progress_and_inclusive_threshold() -> None:
    assert (
        "if (_entity.Controller.Code == RuntimeControllerCode.ChannelBeam "
        "&& ChannelBeamWarmupProgress() < (_entity.Controller.Params.DamageStartProgress ?? 1d)) return false;"
        in _code()
    )
