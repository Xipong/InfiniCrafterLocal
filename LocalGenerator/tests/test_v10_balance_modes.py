from __future__ import annotations

from infini_local.core.balance_mode import (
    BALANCE_MODE_NORMALIZE,
    BALANCE_MODE_REPORT,
    BALANCE_MODE_SAFETY,
    current_balance_mode,
    normalize_balance_mode,
)
from infini_local.core.balance_report import build_balance_report
from infini_local.pipelines.combine_balance import apply_family_locks_to_genome
from infini_local.pipelines.equipment_stats import apply_accessory_soft_budget
from infini_local.pipelines.llm_authoring_prompt import authored_weapon_damage


def _stage() -> dict:
    return {
        "name": "pre_boss",
        "derivedDamage": 100,
        "powerBudget": 5.0,
        "sourceFastestUseTime": 20,
        "powerTransfer": {},
    }


def _genome() -> dict:
    return {
        "useTimeTicks": 10,
        "shotCount": 4,
        "pierce": 2,
        "lifetimeTicks": 180,
        "aoeRadiusTiles": 0,
        "extraUpdates": 0,
        "rangeTiles": 40,
        "homingStrength": 0,
    }


def _contract_check_balance_mode_has_one_small_exact_owner(monkeypatch) -> None:
    assert normalize_balance_mode(" NORMALIZE ") == BALANCE_MODE_NORMALIZE
    assert normalize_balance_mode("unknown-clever-mode") == BALANCE_MODE_SAFETY
    monkeypatch.setenv("INFINI_BALANCE_MODE", "report")
    assert current_balance_mode() == BALANCE_MODE_REPORT


def _contract_check_safety_preserves_authored_damage_and_reports_soft_advice(monkeypatch) -> None:
    monkeypatch.setenv("INFINI_BALANCE_MODE", "safety")
    debug: dict = {}
    value = authored_weapon_damage(
        {"damage": 120}, fallback=40, max_parent_damage=80,
        stage=_stage(), genome=_genome(), debug=debug,
    )
    assert value == 120
    assert debug["balanceMode"] == BALANCE_MODE_SAFETY
    assert debug["authoredDamageBalanceAdvice"]["applied"] is False
    assert debug["authoredDamageBalanceAdvice"]["to"] < 120
    assert "authoredDamageEnvelopeClamp" not in debug


def _contract_check_normalize_keeps_legacy_soft_envelope_as_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("INFINI_BALANCE_MODE", "normalize")
    debug: dict = {}
    value = authored_weapon_damage(
        {"damage": 120}, fallback=40, max_parent_damage=80,
        stage=_stage(), genome=_genome(), debug=debug,
    )
    assert value < 120
    assert debug["authoredDamageEnvelopeClamp"]["applied"] is True
    assert debug["authoredDamageEnvelopeClamp"]["mode"] == BALANCE_MODE_NORMALIZE


def _contract_check_report_disables_python_runtime_corridor_but_safety_keeps_it(monkeypatch) -> None:
    raw = {
        "shotCount": 20,
        "pierce": 20,
        "lifetimeTicks": 2000,
        "aoeRadiusTiles": 20,
        "rangeTiles": 200,
        "extraUpdates": 8,
        "homingStrength": 1,
    }
    monkeypatch.setenv("INFINI_BALANCE_MODE", "report")
    report_data: dict = {}
    assert apply_family_locks_to_genome(dict(raw), {}, {}, report_data, {"powerBudget": 1}) == raw
    assert report_data["debug"]["runtimeSafetyMode"]["applied"] is False

    monkeypatch.setenv("INFINI_BALANCE_MODE", "safety")
    safety = apply_family_locks_to_genome(dict(raw), {}, {}, {}, {"powerBudget": 1})
    assert safety["shotCount"] == 6
    assert safety["rangeTiles"] == 105.0
    assert safety["extraUpdates"] == 2


def _contract_check_equipment_budget_can_report_without_mutating() -> None:
    raw = {"genericDamage": 1.0, "endurance": 0.5, "defense": 100, "lavaImmune": True}
    kept, report = apply_accessory_soft_budget(raw, {"powerBudget": 1, "rarity": 0}, apply_clamps=False)
    assert kept == raw
    assert report["applied"] is False
    assert report["clamps"] == []
    assert report["suggestedClamps"]


def _contract_check_balance_report_names_active_mode(monkeypatch) -> None:
    monkeypatch.setenv("INFINI_BALANCE_MODE", "safety")
    report = build_balance_report({"category": "weapon", "gameplay": {"damage": 120, "useTime": 10}, "debug": {}}, _stage())
    assert report["balanceMode"] == BALANCE_MODE_SAFETY


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_v10_balance_modes_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_balance_mode_has_one_small_exact_owner',
            '_contract_check_safety_preserves_authored_damage_and_reports_soft_advice',
            '_contract_check_normalize_keeps_legacy_soft_envelope_as_explicit_opt_in',
            '_contract_check_report_disables_python_runtime_corridor_but_safety_keeps_it',
            '_contract_check_equipment_budget_can_report_without_mutating',
            '_contract_check_balance_report_names_active_mode',
        ),
    )
