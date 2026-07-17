from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring.schema import ENGINE_FN_CATALOG_V2
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload


PARENT = {"name": "Wooden Sword", "type": 24, "damage": 7, "useTime": 20, "useAnimation": 20}


def _contract_check_critical_numeric_and_sentinel_semantics_survive_prompt_compaction() -> None:
    payload = build_llm_author_payload(PARENT, PARENT, {}, {}, "critical_semantics")
    contract = payload["engineRuntimeContract"]
    critical = contract["criticalValueSemantics"]
    assert critical["pierce"].startswith("-1=infinite hits")
    assert "0 or 1=one target total" in critical["pierce"]
    assert "not extra targets" in critical["pierce"]
    assert "may repeat" in critical["useTiming"]
    assert "any projectile kill" in critical["expire"]
    assert "at most 48" in critical["sentryBudget"].lower()

    functions = contract["availableFunctions"]
    assert "-1=infinite hits" in functions["shoot_projectile"]["params"]["pierce"]
    assert "one action/click" in functions["set_item_stats"]["params"]["useAnimationTicks"]
    assert "beam full immediately" in critical["zero"]
    assert "charge*→charge_release" in critical["families"]
    assert "same-NPC re-hit" in critical["cadence"]
    assert "onHit" in functions["deploy_sentry"]["params"]
    assert "non-child effect only" in functions["deploy_sentry"]["params"]["onHit"]
    assert "shot lifetime; not sentry lifetime" in functions["deploy_sentry"]["params"]["secondaryLifetimeTicks"]


def _contract_check_prompt_does_not_advertise_dead_or_false_primary_controls() -> None:
    shoot = ENGINE_FN_CATALOG_V2["shoot_projectile"]["params"]
    ranged = ENGINE_FN_CATALOG_V2["fire_ranged_weapon"]["params"]
    assert "damageMultiplier" not in shoot
    assert "sentry" not in shoot["runtimeFamily"].split("|")
    assert "rocket" not in ranged["ammoFor"].split("|")


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_prompt_critical_value_semantics_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_critical_numeric_and_sentinel_semantics_survive_prompt_compaction',
            '_contract_check_prompt_does_not_advertise_dead_or_false_primary_controls',
        ),
    )
