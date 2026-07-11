from __future__ import annotations

import math

import json
from typing import Any

from infini_local.core.balance_policy import power_band_for_bucket
from infini_local.core.balance_mode import current_balance_mode
from infini_local.core.result_models import BalanceReportModel


# AGENT MAP: debug balance report shape.
# Reports compare authored vs final values and clamp/repair provenance. They are
# evidence for audits, not gameplay authority and not a place to add mechanics.
BALANCE_REPORT_SCHEMA_VERSION = "infini.balance-report.v1"


def _finite_int(value: Any, default: int = 0) -> int:
    try:
        f = float(value)
    except Exception:
        return int(default)
    if not math.isfinite(f):
        return int(default)
    return int(f)



def json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def compact_json(value: Any, max_chars: int = 6000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return text[:max_chars]



def _final_attack_view(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    out: dict[str, Any] = {}
    for key in (
        "enabled", "runtimePlanAuthored", "runtimeFamily", "delivery", "weaponFamily",
        "projectileFamily", "damageClass", "shotCount", "pierce", "splitCount",
        "chainCount", "speed", "lifetime", "rangeTiles", "homingStrength",
        "aoeRadiusTiles", "extraUpdates", "mobilityMode", "onHit", "effect",
    ):
        if key in genome:
            out[key] = genome.get(key)
        elif key in attack:
            out[key] = attack.get(key)
    return out


def _clamp_taxonomy(debug: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    author_validation = json_obj(debug.get("authorPreservingValidation"))
    taxonomy: dict[str, list[dict[str, Any]]] = {"balance": [], "safety": [], "contract": []}

    if isinstance(author_validation.get("authoredDamageEnvelopeClamp"), dict):
        row = dict(author_validation.get("authoredDamageEnvelopeClamp") or {})
        row.setdefault("kind", "authored_damage_soft_envelope")
        taxonomy["balance"].append(row)
    if isinstance(author_validation.get("authoredDamageBalanceAdvice"), dict):
        row = dict(author_validation.get("authoredDamageBalanceAdvice") or {})
        row.setdefault("kind", "authored_damage_soft_envelope_advice")
        row["applied"] = False
        taxonomy["balance"].append(row)
    if isinstance(author_validation.get("recursiveDamageBalanceAdvice"), dict):
        row = dict(author_validation.get("recursiveDamageBalanceAdvice") or {})
        row.setdefault("kind", "recursive_generated_damage_advice")
        row["applied"] = False
        taxonomy["balance"].append(row)
    if isinstance(author_validation.get("recursiveDamageSoftCap"), dict):
        row = dict(author_validation.get("recursiveDamageSoftCap") or {})
        row.setdefault("kind", "recursive_generated_damage_soft_cap")
        taxonomy["balance"].append(row)
    if isinstance(debug.get("authoredDamageEnvelopeClamp"), dict):
        row = dict(debug.get("authoredDamageEnvelopeClamp") or {})
        row.setdefault("kind", "authored_damage_soft_envelope")
        taxonomy["balance"].append(row)

    runtime_safety = json_obj(debug.get("runtimeSafetyClamps"))
    if runtime_safety:
        taxonomy["safety"].append({"kind": "runtime_safety_clamps", "details": runtime_safety})
    hard_clamps = author_validation.get("llmGenomeHardClamps")
    if isinstance(hard_clamps, list) and hard_clamps:
        taxonomy["safety"].append({"kind": "llm_genome_hard_clamps", "details": hard_clamps[:12]})

    for budget_key, fallback_kind in (("accessoryBudgetReport", "accessory_total_stat_budget"), ("armorBudgetReport", "armor_total_stat_budget")):
        budget_report = json_obj(debug.get(budget_key))
        if budget_report:
            for row in budget_report.get("clamps") or []:
                if isinstance(row, dict):
                    entry = dict(row)
                    entry.setdefault("kind", "balance")
                    entry.setdefault("source", fallback_kind)
                    entry["applied"] = True
                    taxonomy["balance"].append(entry)
            for row in budget_report.get("suggestedClamps") or []:
                if isinstance(row, dict):
                    entry = dict(row)
                    entry.setdefault("kind", "balance_advice")
                    entry.setdefault("source", fallback_kind)
                    entry["applied"] = False
                    taxonomy["balance"].append(entry)
            if budget_report.get("reasons") and not budget_report.get("clamps") and not budget_report.get("suggestedClamps"):
                taxonomy["balance"].append({"kind": fallback_kind, "reasons": budget_report.get("reasons"), "details": budget_report})

    if debug.get("runtimeRepairPath"):
        taxonomy["contract"].append({
            "kind": "runtime_repair_path",
            "path": debug.get("runtimeRepairPath"),
            "repairKind": debug.get("runtimeRepairKind", ""),
        })
    structural = json_obj(debug.get("runtimeStructuralRepair"))
    if structural:
        taxonomy["contract"].append({"kind": "code_structural_runtime_plan_repair", "details": structural})
    repair_patch = json_obj(debug.get("runtimePlanRepairPatchContract"))
    if repair_patch:
        taxonomy["contract"].append({"kind": "runtime_repair_patch_contract", "details": repair_patch})
    validation_after = json_obj(debug.get("runtimePlanValidationAfterRepair"))
    if validation_after and not validation_after.get("ok", True):
        taxonomy["contract"].append({"kind": "runtime_plan_validation_failed", "details": validation_after})

    return {key: value for key, value in taxonomy.items() if value}


def build_balance_report(data: dict[str, Any], stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one compact debug report for balance/repair boundaries.

    This is observability only. It does not author, route, clamp or repair gameplay.
    """
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    stage_obj = stage if isinstance(stage, dict) else json_obj(debug.get("statProfile"))
    gp = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    band = power_band_for_bucket(stage_obj)
    author_validation = json_obj(debug.get("authorPreservingValidation"))
    authored_clamp = author_validation.get("authoredDamageEnvelopeClamp") if isinstance(author_validation.get("authoredDamageEnvelopeClamp"), dict) else {}

    authored: dict[str, Any] = {}
    if authored_clamp:
        authored["damage"] = authored_clamp.get("from")
        authored["useTime"] = authored_clamp.get("useTime")
        authored["shotCount"] = authored_clamp.get("shotCount")
        authored["costMultiplier"] = authored_clamp.get("costMultiplier")
    else:
        if "damage" in gp:
            authored["damage"] = gp.get("damage")
        if "useTime" in gp:
            authored["useTime"] = gp.get("useTime")

    final = {
        "category": data.get("category"),
        "damage": gp.get("damage"),
        "useTime": gp.get("useTime"),
        "rarity": gp.get("rarity"),
        "attack": _final_attack_view(data),
    }
    repair = {
        "path": debug.get("runtimeRepairPath", ""),
        "kind": debug.get("runtimeRepairKind", ""),
        "attemptBudget": debug.get("runtimeRepairAttemptBudget", ""),
        "patchContract": json_obj(debug.get("runtimePlanRepairPatchContract")),
    }
    model = BalanceReportModel(
        schema=BALANCE_REPORT_SCHEMA_VERSION,
        powerBand=str(band.get("powerBand") or "unknown"),
        label=str(band.get("label") or "unknown"),
        authored=authored,
        final=final,
        clamps=_clamp_taxonomy(debug),
        repair=repair,
        extra={
            **{k: v for k, v in band.items() if k not in {"powerBand", "label"}},
            "balanceMode": current_balance_mode(),
            "authority": {
                "author": "LLM writes fantasy/resultKind/runtimePlan/numbers",
                "softBalance": "applied only in INFINI_BALANCE_MODE=normalize; otherwise reported as advice",
                "repair": "code structural repair first; targeted LLM retry only when not executable",
                "runtimeSafety": "compiler/C# hard clamps for Terraria safety",
            },
            "parents": {
                "maxDamage": _finite_int(stage_obj.get("sourceMaxDamage"), 0) if stage_obj else 0,
                "fastestUseTime": _finite_int(stage_obj.get("sourceFastestUseTime"), 0) if stage_obj else 0,
                "generatedDepths": stage_obj.get("parentGeneratedDepths", []) if stage_obj else [],
                "weakAnchor": bool((stage_obj.get("powerTransfer") if isinstance(stage_obj.get("powerTransfer"), dict) else {}).get("weakAnchor")) if stage_obj else False,
            },
        },
    )
    return model.to_dict()

def attach_balance_report(data: dict[str, Any], stage: dict[str, Any] | None = None) -> dict[str, Any]:
    debug = data.setdefault("debug", {})
    report = build_balance_report(data, stage)
    debug["balanceReport"] = compact_json(report)
    return data
