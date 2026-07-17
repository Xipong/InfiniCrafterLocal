from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"
sys.path.insert(0, str(LOCAL))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contract_check_llm_prompt_no_longer_receives_parent_relative_soft_balance_caps():
    authoring = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_pipeline.py")
    prompt_owner = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_prompt.py")
    prompt_surface = authoring + prompt_owner
    parent_context = read(LOCAL / "infini_local" / "pipelines" / "parent_context_pipeline.py")
    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")

    assert "source_power_envelope_for_prompt" not in authoring
    assert "source_power_envelope_for_prompt" not in parent_context
    assert "sourceEnvelope" not in prompt_surface
    assert "softDamageCapPerHit" not in prompt_surface
    assert "softAoeTilesCap" not in prompt_surface
    assert "softActiveProjectileCap" not in prompt_surface
    assert "balancePolicy" in prompt_surface
    assert "current_balance_mode" in prompt_surface
    assert "should_apply_soft_normalization" in prompt_surface
    assert "prompt_free_parent_soft_caps_code_owned_balance_audit_v0.4.216" in contracts
    assert "balanceArchitectureAuditContract" in contracts


def _contract_check_payload_exposes_hard_engine_ranges_but_not_dynamic_balance_numbers():
    from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload

    item_a = {"name": "Copper Shortsword", "damage": 5, "useTime": 13, "rare": 0, "value": 100}
    item_b = {"name": "Star Wrath", "damage": 170, "useTime": 16, "rare": 10, "value": 1000000}
    payload = build_llm_author_payload(item_a, item_b, {}, {}, "audit-key")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    assert "balancePolicy" in payload
    contract = payload["engineRuntimeContract"]
    assert contract["availableFunctions"]["set_item_stats"]["params"]["damage"] == "0..cap"
    assert contract["hardEngineLimits"]["maxShotCount"] == 8
    required = contract["requiredAuthorParams"]
    assert required["everyCombatPrimary"] == ["shotCount", "spreadRadians"]
    assert set(required["childProducingOnHit"]) >= {
        "count", "secondaryDamageMultiplier", "secondaryLifetimeTicks",
    }
    assert required["debuffingOnHit"] == ["debuffTime"]
    assert required["stackConsumedWeaponIdentity"] == "consumable_weapon"
    assert required["onePrimaryFunction"] is True
    assert required["temporaryHelperCanFire"] is False
    assert required["turretFunction"] == "deploy_sentry"
    assert required["runtimePlanMetadataTypes"]["anomalyFlags"] == "array[string]"
    assert required["pullOnHitEncoding"] == {
        "onHit": "none", "requiredParams": ["pullStrength", "pullMode"],
    }
    assert set(required["neverOnSetItemStats"]) >= {
        "shotCount", "spreadRadians", "soundUseCatalogId", "soundImpactCatalogId", "soundVolume",
    }
    assert required["runtimeFamilyRequirements"]["overhead_barrage"] == [
        "delayTicks", "secondaryDamageMultiplier", "secondaryLifetimeTicks",
    ]
    assert required["visualTopologyRules"]["connected"]["partCountMin"] == 1
    assert required["visualTopologyRules"]["connected"]["partCountMax"] == 1
    assert required["equipmentLightEncoding"]["forbiddenFunction"] == "emit_light"
    assert "safety" in payload["balancePolicy"]
    assert "softDamageCapPerHit" not in text
    assert "sourceEnvelope" not in text
    assert "terrariaProgressionReference" not in text


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_216_balance_architecture_audit_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_llm_prompt_no_longer_receives_parent_relative_soft_balance_caps',
            '_contract_check_payload_exposes_hard_engine_ranges_but_not_dynamic_balance_numbers',
        ),
    )
