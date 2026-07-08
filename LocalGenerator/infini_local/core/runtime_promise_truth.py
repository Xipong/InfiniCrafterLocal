from __future__ import annotations

import json
import re
from typing import Any

from infini_local.core.runtime_contracts import normalize_runtime_contract

PROMISE_TRUTH_SCHEMA = "infini.runtime-promise-truth.v1"

CLAIM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("return_to_thrower", re.compile(r"\b(return|returns|returning|boomerang|comes back)\b", re.I)),
    ("channel_beam", re.compile(r"\b(channel|channeled|channelled|beam|laser|ray)\b", re.I)),
    ("charge_release", re.compile(r"\b(charge|charged|release)\b", re.I)),
    ("starfall", re.compile(r"\b(starfall|rain(?:s|ing)?\s+stars|falling\s+stars|stars?\s+from\s+the\s+sky|meteor)\b", re.I)),
    ("sticky_puddle", re.compile(r"\b(sticky|puddle|slowing field|slow field)\b", re.I)),
    ("heat_jam", re.compile(r"\b(heat|overheat|jam|cooldown)\b", re.I)),
    ("lifesteal", re.compile(r"\b(lifesteal|life steal|drain life|heals? on hit)\b", re.I)),
    ("feline_bounce", re.compile(r"\b(feline|cats?|bouncing cats?|meowmere)\b", re.I)),
    ("projectile_bounce", re.compile(r"\b(bounc(?:e|es|ing|y)|rebound(?:s|ing)?)\b", re.I)),
    ("paired_dual", re.compile(r"\b(paired|dual|twin|offhand|two swords|second sword)\b", re.I)),
    ("burst", re.compile(r"\b(bursts?|explode|explosion|nova)\b", re.I)),
    ("burn_on_hit", re.compile(r"\b(burn|ignite|on-hit burn|sets? on fire)\b", re.I)),
    ("alternating_phase", re.compile(r"\b(alternate|alternates|cycle|light.dark|dark.light|phase)\b", re.I)),
]


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _append_unique_list(data: dict[str, Any], key: str, values: list[str]) -> None:
    current = data.get(key) if isinstance(data.get(key), list) else []
    merged = list(dict.fromkeys([str(x) for x in current if x] + [str(x) for x in values if x]))
    data[key] = merged[:32]


def _engine_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    return [c for c in calls if isinstance(c, dict)]


def _params(call: dict[str, Any]) -> dict[str, Any]:
    p = call.get("params") if isinstance(call.get("params"), dict) else call
    return p if isinstance(p, dict) else {}


def _collect_structured_text(data: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if data.get("tooltip"):
        out.append(("tooltip", _text(data.get("tooltip"))))
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    if concept.get("fantasy"):
        out.append(("concept.fantasy", _text(concept.get("fantasy"))))
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    if rp.get("runtimeStateIntent"):
        out.append(("runtimePlan.runtimeStateIntent", _text(rp.get("runtimeStateIntent"))))
    vi = rp.get("visualIntent") if isinstance(rp.get("visualIntent"), dict) else {}
    for key in ["item", "projectile", "impact", "vfxIntent"]:
        if vi.get(key):
            out.append((f"runtimePlan.visualIntent.{key}", _text(vi.get(key))))
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    for key in ["itemPrompt", "projectilePrompt", "impactPrompt", "notes"]:
        if visual.get(key):
            out.append((f"visual.{key}", _text(visual.get(key))))
    contract = normalize_runtime_contract(data.get("runtimeContract") if isinstance(data.get("runtimeContract"), dict) else {})
    for i, claim in enumerate(contract.get("mechanicClaims") or []):
        if claim.get("claim"):
            out.append((f"runtimeContract.mechanicClaims[{i}]", _text(claim.get("claim"))))
    return out


def _claim_status(kind: str, source: str, text: str, data: dict[str, Any], patch: dict[str, Any]) -> tuple[str, str]:
    arch = data.get("runtimeArchetype") if isinstance(data.get("runtimeArchetype"), dict) else {}
    family = str(arch.get("family") or "")
    runtime_family = str(patch.get("runtimeFamily") or "")
    movement = str(patch.get("movement") or "")
    on_hit = str(patch.get("onHit") or "")
    calls = _engine_calls(data)
    visual_source = source.startswith("visual.") or source.startswith("runtimePlan.visualIntent")

    if kind == "return_to_thrower":
        if family == "boomerang" or runtime_family == "returning" or movement in {"boomerang", "returning_glaive"}:
            return "executable", "runtimeArchetype/AttackSpec returning executor"
        return ("visual_only", "visual wording only") if visual_source else ("unsupported", "no returning executor")
    if kind == "lifesteal":
        return ("executable", "apply_on_hit_effect.lifesteal") if on_hit == "lifesteal" else ("unsupported", "no lifesteal onHit executor")
    if kind == "burst":
        if on_hit == "burst":
            cap = int(float(patch.get("burstDustCap") or 0))
            return ("partial", "burst onHit without burstDustCap feedback") if cap <= 0 else ("executable", "apply_on_hit_effect.burst")
        return ("visual_only", "visual burst wording") if visual_source else ("unsupported", "no burst onHit executor")
    if kind == "channel_beam":
        if family == "channel_beam":
            return "unsupported", "channel_beam archetype preserved; no finite beam executor in this patch"
        if visual_source:
            return "visual_only", "beam wording is visual-only"
        return "unsupported", "no channel beam executor"
    if kind == "starfall":
        if on_hit == "starfall":
            return "executable", "apply_on_hit_effect.starfall"
        if family == "delayed_starfall":
            return "unsupported", "delayed_starfall archetype preserved; finite path is onHit=starfall"
        return ("visual_only", "starfall image/VFX wording only") if visual_source else ("unsupported", "no starfall onHit executor")
    if kind == "projectile_bounce":
        if movement == "bounce":
            return "executable", "movement=bounce"
        return ("visual_only", "bounce wording without bounce movement") if visual_source else ("unsupported", "no bounce movement executor")
    if kind == "feline_bounce":
        # Do not confuse ordinary projectile bounce with Meowmere-like feline bounce.
        has_state = any(str(c.get("fn") or "") in {"state_meter", "triggered_action"} for c in calls)
        if visual_source:
            return "visual_only", "visual wording only"
        return ("partial", "state intent preserved, no feline bounce executor") if has_state else ("unsupported", "no feline bounce executor")
    if kind in {"sticky_puddle", "heat_jam", "paired_dual", "alternating_phase"}:
        # state_meter/triggered_action may preserve state, but does not execute these mechanics by itself.
        has_state = any(str(c.get("fn") or "") in {"state_meter", "triggered_action"} for c in calls)
        if kind == "sticky_puddle" and str(patch.get("effect") or "") == "slime":
            return "partial", "slime effect present; sticky field/puddle still not a full executor"
        if visual_source:
            return "visual_only", "visual wording only"
        return ("partial", "state intent preserved, no gameplay executor") if has_state else ("unsupported", "no finite executor")
    if kind == "burn_on_hit":
        return ("executable", "apply_on_hit_effect.burn") if on_hit == "burn" else (("visual_only", "burn wording only") if visual_source else ("unsupported", "no burn onHit executor"))
    if kind == "charge_release":
        has_state = any(str(c.get("fn") or "") in {"state_meter", "triggered_action"} for c in calls)
        if bool(patch.get("channelUse")):
            return "partial", "channel/charge feel exists but no full charge-release executor"
        return ("partial", "state intent preserved") if has_state else ("unsupported", "no charge-release executor")
    return "ambiguous", "unclassified promise"


def validate_runtime_promises(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    patch = patch or {}
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source, text in _collect_structured_text(data):
        for kind, pattern in CLAIM_PATTERNS:
            if not pattern.search(text or ""):
                continue
            key = (kind, source, pattern.search(text).group(0).lower() if pattern.search(text) else "")
            if key in seen:
                continue
            seen.add(key)
            status, backing = _claim_status(kind, source, text, data, patch)
            claims.append({
                "kind": kind,
                "source": source,
                "claim": text[:220],
                "status": status,
                "backing": backing,
            })

    warnings: list[str] = []
    unsupported: list[str] = []
    for claim in claims:
        if claim["status"] == "unsupported":
            unsupported.append("unsupported:" + claim["kind"])
        if claim["kind"] == "burst" and claim["status"] == "partial":
            warnings.append("burst_without_burstDustCap_or_impact_feedback")
        if claim["status"] == "visual_only" and not str(claim.get("source", "")).startswith("visual."):
            warnings.append(f"{claim['kind']}_promise_downgraded_to_visual_only")

    contract_raw = data.get("runtimeContract") if isinstance(data.get("runtimeContract"), dict) else {}
    if contract_raw:
        contract = normalize_runtime_contract(contract_raw)
        for mechanic in contract.get("mechanicClaims") or []:
            text = str(mechanic.get("claim") or "")
            matched = next((c for c in claims if c.get("source", "").startswith("runtimeContract.mechanicClaims") and c.get("claim") == text), None)
            if matched:
                mechanic["status"] = matched["status"]
                mechanic["backing"] = mechanic.get("backing") or matched["backing"]
        statuses = {c.get("status") for c in claims}
        if any(s == "executable" for s in statuses) and any(s in {"unsupported", "partial"} for s in statuses):
            contract["executionStatus"] = "partial"
        elif any(s == "unsupported" for s in statuses):
            contract["executionStatus"] = "unsupported"
        elif statuses and statuses <= {"visual_only"}:
            contract["executionStatus"] = "visual_only"
        elif any(s == "executable" for s in statuses):
            contract["executionStatus"] = "executable"
        data["runtimeContract"] = contract

    if unsupported:
        _append_unique_list(data, "unsupportedPromises", list(dict.fromkeys(unsupported)))
    debug = data.setdefault("debug", {}) if isinstance(data.get("debug"), dict) else data.setdefault("debug", {})
    report = {
        "schema": PROMISE_TRUTH_SCHEMA,
        "claims": claims[:48],
        "warnings": list(dict.fromkeys(warnings))[:24],
        "unsupportedPromises": list(dict.fromkeys(unsupported))[:24],
        "note": "Promise truth validates consistency only; it never creates gameplay from prose, tooltip, or visual prompts.",
    }
    debug["runtimePromiseTruth"] = json.dumps(report, ensure_ascii=False)[:8000]
    return report
