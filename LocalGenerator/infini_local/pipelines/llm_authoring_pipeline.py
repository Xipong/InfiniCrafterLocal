from __future__ import annotations

import copy
import json

import re

from typing import Any

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_stage_messages import (
    ATTRIBUTED_PLANNER_HISTORY_KIND,
    agent_handoff,
    attributed_planner_history,
    attributed_planner_messages,
    planner_history_state,
    stage_chat_message,
)

from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report
from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
from infini_local.core.boundary_models import runtime_plan_boundary_report

from infini_local.core.runtime_authoring.structural import structural_repair_runtime_plan_inplace
from infini_local.core.runtime_promise_truth import validate_runtime_promises
from infini_local.pipelines.combine_genome_contract import combat_genome_required_for
from infini_local.pipelines.llm_authoring_prompt import (
    MECHANIC_BACKING_REF_RULES,
    build_llm_author_payload,
    normalize_behavior_toy_fields,
    normalize_llm_attack_shape,
    runtime_plan_to_attack_genome_patch,
)
from infini_local.pipelines.llm_transport import (
    active_llm_provider,
    apply_llm_common_options,
    llm_answer_max_tokens,
    llm_chat_json,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    resolve_llm_model,
)
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.pipeline_runtime_constants import LLM_RUNTIME_AUTHORING
from infini_local.storage.trace_runtime import _trace_message_summary, log_event, trace_event




# AGENT MAP: LLM JSON authoring and targeted repair boundary.
# The model proposes structured item/runtime data; code then validates/compiles it.
# Repair prompts should be narrow and provenance-visible, not a hidden second author
# that rewrites identity or routes mechanics from prose.


def planner_runtime_promise_gate(plan: dict[str, Any]) -> dict[str, Any]:
    """Reject public gameplay promises that have no executable runtime backing.

    Visual-only wording remains legal inside visual fields.  The probe is copied because
    promise validation deliberately annotates its input for later runtime diagnostics.
    """
    probe = copy.deepcopy(plan)
    patch = runtime_plan_to_attack_genome_patch(probe)
    report = validate_runtime_promises(probe, patch)
    blocking = [
        dict(claim)
        for claim in report.get("claims") or []
        if claim.get("status") in {"unsupported", "partial"}
        and not str(claim.get("source") or "").startswith(("visual.", "runtimePlan.visualIntent"))
    ]
    runtime = runtime_plan(plan)
    result_kind = str(runtime.get("resultKind") or "").strip().lower()
    contract_raw = plan.get("runtimeContract")
    contract: dict[str, Any] = contract_raw if isinstance(contract_raw, dict) else {}
    claims_raw = contract.get("mechanicClaims")
    claims: list[Any] = claims_raw if isinstance(claims_raw, list) else []
    timeline_raw = contract.get("playerViewTimeline")
    timeline: list[Any] = timeline_raw if isinstance(timeline_raw, list) else []
    if result_kind in {"weapon", "ammo", "consumable_weapon", "tool", "accessory", "armor", "potion"}:
        if not claims:
            blocking.append({"kind": "missing_mechanic_claims", "source": "runtimeContract", "status": "unsupported", "backing": "none"})
        if len([step for step in timeline if str(step).strip()]) < 4:
            blocking.append({"kind": "missing_player_view_timeline", "source": "runtimeContract", "status": "unsupported", "backing": "none"})
    calls_raw = runtime.get("engineCalls")
    calls: list[Any] = calls_raw if isinstance(calls_raw, list) else []
    item_stats = next((call for call in calls if isinstance(call, dict) and call.get("fn") == "set_item_stats"), {})
    item_params_raw = item_stats.get("params")
    item_params: dict[str, Any] = item_params_raw if isinstance(item_params_raw, dict) else {}
    has_consumption_call = any(isinstance(call, dict) and call.get("fn") == "consumption_behavior" for call in calls)
    if has_consumption_call and not bool(item_params.get("consumable")):
        blocking.append({"kind": "inert_consumption_behavior", "source": "runtimePlan.engineCalls", "status": "unsupported", "backing": "set_item_stats.consumable=false"})
    return {
        "schema": "infini.planner-promise-gate.v1",
        "ok": not blocking,
        "blockingClaims": blocking[:24],
        "unsupportedPromises": list(report.get("unsupportedPromises") or [])[:24],
    }




def try_llm_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Author-first chaos planner.

    v0.3.9 keeps the author-first architecture. The LLM authors the playable item: fantasy,
    category, gameplay numbers, projectile identity, behavior timeline, and visual briefs.
    Python does not choose the item. It only validates JSON, fills trivial serialization
    fields, then clamps catastrophic power/performance after the fact.
    """
    if not USE_LLM:
        return None
    user = build_llm_author_payload(a, b, ca, cb, key)
    try:
        model_name = resolve_llm_model()
        system = (
            "You are the AUTHOR of a Terraria-like generated item. "
            "Use raw parent fields, semantic notes, and engine functions to design one playable result. "
            "Follow the priorityHeader before the detailed API card. "
            "The server validates executable safety only; do not rely on legacy attackPattern/attack.genome. "
            "Return ONLY one JSON object. No reasoning, no markdown, no second JSON."
            + llm_reasoning_system_suffix(model_name)
        )
        planner_user_content = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
        req = {
            "model": model_name,
            "messages": [
                stage_chat_message("system", "item_author_contract", system),
                stage_chat_message("user", "recipe_context", planner_user_content),
            ],
            "temperature": env_float("INFINI_LLM_TEMPERATURE", 0.38, lo=0.0, hi=1.2),
            "response_format": llm_json_response_format("infini_runtime_plan"),
        }
        req = apply_llm_common_options(req, model_name=model_name)
        trace_event("prompt", "LLM:author_plan", f"Planner request: {name_of(a)} + {name_of(b)}", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"), "reasoningEffort": req.get("reasoning_effort"),
            "responseFormat": bool(req.get("response_format")), "messages": _trace_message_summary(req.get("messages")),
        }, prompt=planner_user_content)
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = raw["choices"][0]["message"]["content"]
        transport_debug = raw.get("_debug") if isinstance(raw.get("_debug"), dict) else {}
        trace_event("response", "LLM:author_plan", "Planner response", {"provider": active_llm_provider(), "model": model_name, "chars": len(str(content)), "transport": transport_debug}, response=content)
        parsed_child_json = parse_first_valid_llm_json(content)
        obj = normalize_behavior_toy_fields(normalize_llm_attack_shape(parsed_child_json))
        promise_gate = planner_runtime_promise_gate(obj)
        retry_messages = list(req["messages"])
        max_reauthors = 2
        for reauthor_attempt in range(1, max_reauthors + 1):
            if promise_gate["ok"]:
                break
            retry_instruction = json.dumps({
                "task": "Re-author the complete item. Keep both parent roles, but remove unsupported gameplay promises from name/tooltip/concept/runtimeStateIntent.",
                "agentHandoff": agent_handoff(
                    previous_speaker="item_planner",
                    current_speaker="promise_truth_gate",
                    next_speaker="item_planner",
                    cause_by="unsupported_public_promise",
                    artifact_source="item_planner.item",
                ),
                "attempt": reauthor_attempt,
                "maxAttempts": max_reauthors,
                "blockingClaims": promise_gate["blockingClaims"],
                "backingRefRules": list(MECHANIC_BACKING_REF_RULES),
                "requirements": [
                    "Every gameplay promise in public prose must be backed by a concrete engineCall/runtime executor.",
                    "A purely visual motif may stay only in visual/visualIntent and must not claim gameplay behavior.",
                    "Playable results must keep at least 4 non-empty playerViewTimeline steps in runtimeContract.",
                    "Return one complete replacement item JSON, not a patch.",
                ],
            }, ensure_ascii=False, separators=(",", ":"))
            retry_messages.extend([
                stage_chat_message("assistant", "item_planner", content),
                stage_chat_message("user", "promise_truth_gate", retry_instruction),
            ])
            retry_req = dict(req)
            retry_req["messages"] = list(retry_messages)
            trace_event("prompt", "LLM:author_plan_promise_retry", "Planner promise-truth retry", {
                "provider": active_llm_provider(), "model": model_name, "attempt": reauthor_attempt,
                "maxAttempts": max_reauthors,
                "blockingClaims": [str(x.get("kind") or "") for x in promise_gate["blockingClaims"]],
            }, prompt=retry_instruction)
            retry_raw = llm_chat_json(retry_req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
            retry_content = retry_raw["choices"][0]["message"]["content"]
            retry_transport_debug = retry_raw.get("_debug") if isinstance(retry_raw.get("_debug"), dict) else {}
            trace_event("response", "LLM:author_plan_promise_retry", "Planner promise-truth retry response", {
                "provider": active_llm_provider(), "model": model_name, "attempt": reauthor_attempt,
                "chars": len(str(retry_content)), "transport": retry_transport_debug,
            }, response=retry_content)
            content = retry_content
            parsed_child_json = parse_first_valid_llm_json(retry_content)
            obj = normalize_behavior_toy_fields(normalize_llm_attack_shape(parsed_child_json))
            promise_gate = planner_runtime_promise_gate(obj)
        if not promise_gate["ok"]:
            kinds = sorted({str(x.get("kind") or "unsupported") for x in promise_gate["blockingClaims"]})
            raise PlannerUnavailable(
                f"planner repeated unsupported gameplay promises after {max_reauthors} re-authors: " + ", ".join(kinds)
            )
        obj.setdefault("id", "g_" + stable_hash(key, content, length=16))
        obj.setdefault("recipeKey", key)
        obj.setdefault("schemaVersion", 1)
        obj.setdefault("parentA", name_of(a))
        obj.setdefault("parentB", name_of(b))
        obj.setdefault("sourceMode", "generated")
        obj.setdefault("debug", {})
        obj["debug"]["planner"] = "llm_author_first"
        obj["debug"]["plannerPromiseGate"] = promise_gate
        obj["debug"]["model"] = model_name
        obj["debug"]["promptMode"] = "runtime_authoring_family_contract_v0.4.30_priority_header_placeable_semantics_v0.4.172"
        obj["debug"]["balanceAuthority"] = "llm_authors_numbers_python_clamps_after_authoring"
        obj["debug"]["llmRawOutput"] = content[:12000]
        obj["debug"]["llmTopLevelKeys"] = ",".join(sorted(str(k) for k in obj.keys()))
        obj["debug"]["llmHistoryStored"] = ATTRIBUTED_PLANNER_HISTORY_KIND
        # Runtime-only named Chat Completions history.  Consumers receive one canonical
        # messages[] contract instead of reconstructing roles from parallel string fields.
        obj["_llmHistory"] = attributed_planner_history(system, planner_user_content, content)
        return obj
    except Exception as e:
        trace_event("error", "LLM:author_plan", "Planner failed", {"parents": [name_of(a), name_of(b)]}, error=repr(e))
        log_event("warn", "LLM author-first planner failed", {"error": repr(e)})
        return None


def _runtime_plan_repair_current_item_view(data: dict[str, Any]) -> dict[str, Any]:
    """Lossless current executable view for a runtime-repair delta.

    Identity/prose/visuals remain in attributed Planner history and are immutable here.
    Debug/cache state is excluded because runtime repair cannot own it.
    """
    view: dict[str, Any] = {}
    for key in ["category", "gameplay", "runtimePlan", "attack", "accessory", "armor"]:
        value = data.get(key)
        if value not in (None, ""):
            view[key] = value
    return view


def _failed_runtime_call_contracts(data: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    """Return exact schemas only for engine calls named by validator error paths."""
    plan_raw = data.get("runtimePlan")
    plan: dict[str, Any] = plan_raw if isinstance(plan_raw, dict) else {}
    calls_raw = plan.get("engineCalls")
    calls: list[Any] = calls_raw if isinstance(calls_raw, list) else []
    errors = [str(error) for error in (validation.get("errors") or [])]
    indices = sorted({int(match.group(1)) for error in errors for match in re.finditer(r"engineCalls\.(\d+)", error)})
    out: list[dict[str, Any]] = []
    for index in indices[:6]:
        if index < 0 or index >= len(calls) or not isinstance(calls[index], dict):
            continue
        fn = str(calls[index].get("fn") or "")
        try:
            schema = engine_params_model(fn).model_json_schema()
        except (KeyError, TypeError, ValueError):
            continue
        nested_fields: dict[str, list[str]] = {}
        definitions = schema.get("$defs") if isinstance(schema.get("$defs"), dict) else {}
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for param_name, param_schema in properties.items():
            if not isinstance(param_schema, dict):
                continue
            variants = [param_schema]
            if isinstance(param_schema.get("anyOf"), list):
                variants.extend(item for item in param_schema["anyOf"] if isinstance(item, dict))
            for variant in variants:
                ref = str(variant.get("$ref") or "")
                definition_name = ref.rsplit("/", 1)[-1] if ref else ""
                definition = definitions.get(definition_name) if definition_name else None
                nested = definition.get("properties") if isinstance(definition, dict) and isinstance(definition.get("properties"), dict) else None
                if nested:
                    nested_fields[str(param_name)] = sorted(str(name) for name in nested)
                    break
        out.append({
            "engineCallIndex": index,
            "fn": fn,
            "paramsSchema": schema,
            "allowedNestedFields": nested_fields,
        })
    return out


def _runtime_plan_repair_dossier_core(data: dict[str, Any], validation: dict[str, Any], attempt: int) -> dict[str, Any]:
    """Build the authoritative current-item core of the Runtime Repair dossier."""
    raw_strict_value = validation.get("rawStrictBoundary")
    raw_strict: dict[str, Any] = raw_strict_value if isinstance(raw_strict_value, dict) else {}
    return {
        "task": "Repair only the executable runtime contract so runtimePlan.engineCalls validates. Return repairPatch only. Do not return the complete item.",
        "agentHandoff": agent_handoff(
            previous_speaker="item_planner",
            current_speaker="runtime_validator",
            next_speaker="runtime_repairer",
            cause_by="runtime_contract_validation_failed",
            artifact_source="currentItem",
        ),
        "repairMode": "targeted_runtime_contract_repair",
        "attempt": attempt,
        "validationReport": validation,
        "validatorFeedback": {
            "errors": [str(error) for error in (validation.get("errors") or [])],
            "warnings": [str(warning) for warning in (validation.get("warnings") or [])],
            "rawStrictErrors": [str(error) for error in (raw_strict.get("errors") or [])],
            "instruction": "Fix every listed validator error in the next repairPatch. Do not reinterpret or omit failed paths.",
        },
        "failedCallContracts": _failed_runtime_call_contracts(data, validation),
        "mustFix": [
            "set_item_stats is an engine call, never a gameplay field: put it in repairPatch.runtimePlan.engineCalls, normally as the first call.",
            "Every runtimePlan.engineCalls[].params must be a JSON object, never an array, JSON string, tuple, or key/value list.",
            "If resultKind/category is weapon, ammo, consumable_weapon, tool, accessory or potion, include {\"fn\":\"set_item_stats\",\"params\":{...safe base item stats...}}.",
            "If it is combat-capable, keep or add one concrete primary executable action such as perform_melee_attack, shoot_projectile, fire_ranged_weapon, cast_magic_weapon, spawn_temporary_helper_projectile, or a valid utility/tool/accessory call.",
            "You may replace the whole runtimePlan if that is cleaner, but return it inside repairPatch whenever possible.",
            "Do not use legacy attackPattern or attack.genome. Do not add boss/NPC/mob/enemy spawning.",
            "Do not change name, tooltip, concept, visual identity, parents, id, recipeKey, category, or tags. Runtime repair is not a second item author.",
            "Return exactly one JSON object with repairPatch as its only top-level field; no markdown, explanation, or complete item.",
        ],
        "currentItem": _runtime_plan_repair_current_item_view(data),
        "requiredRepairPatchShape": _runtime_repair_response_schema(),
    }


def _runtime_plan_repair_standalone_packet(
    data: dict[str, Any],
    validation: dict[str, Any],
    attempt: int,
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Build the rich self-contained Runtime Repair v3.1 dossier."""
    packet = _runtime_plan_repair_dossier_core(data, validation, attempt)
    author_payload = build_llm_author_payload(a, b, ca, cb, key)
    packet["parents"] = [raw_parent_card_for_llm(a), raw_parent_card_for_llm(b)]
    packet["engineRuntimeContract"] = author_payload.get("engineRuntimeContract")
    return packet


REPAIR_PATCH_ALLOWED_TOP_LEVEL = {
    "runtimePlan",
    "attack",
    "gameplay",
    "accessory",
    "armor",
}

# Even inside a gameplay repair patch, keep this surface narrow.  Runtime repair may
# complete executable stats, utility flags and authored runtime affordances, but it must
# not silently re-author identity/prose/visuals or become a second item author.
REPAIR_PATCH_ALLOWED_GAMEPLAY_FIELDS = {
    "kind", "damageClass", "damage", "useTime", "useAnimation", "useStyle", "autoReuse", "useTurn",
    "maxStack", "consumable", "craftYield", "rarity", "value", "manaCost", "knockback",
    "healLife", "healMana", "buffCode", "buffType", "buffTime", "extraBuffs", "generatedBuff",
    "pickPower", "axePower", "hammerPower", "miningSpeedScale", "mobilityMode", "mobilityRangeTiles",
    "mobilityCooldownTicks", "mobilitySafeTileOnly", "altUseMode", "altMobilityMode",
    "altMobilityRangeTiles", "altMobilityCooldownTicks", "altMobilitySafeTileOnly", "altGeneratedBuff",
    "holdGeneratedBuff", "holdLightStrength", "holdLightColorName", "runtimeState", "ammoFor",
    "consumeChancePercent", "useConditionMode", "useConditionMinLife", "useConditionMinMana",
    "extractinatorOutputItemType", "extractinatorOutputStack", "itemScale", "holdoutOffsetX", "holdoutOffsetY",
    "channelUse", "runtimeOutputKind", "actualAmmoMode",
}


def _runtime_repair_response_schema() -> dict[str, Any]:
    """One finite envelope; executable patch internals retain their exact validators."""
    engine_call_schema = {
        "type": "object",
        "required": ["fn", "params"],
        "additionalProperties": False,
        "properties": {
            "fn": {"type": "string", "minLength": 1},
            "params": {"type": "object", "additionalProperties": True},
        },
    }
    patch_properties = {
        field: {"type": "object", "additionalProperties": True}
        for field in sorted(REPAIR_PATCH_ALLOWED_TOP_LEVEL)
    }
    patch_properties["runtimePlan"] = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "resultKind": {"type": "string"},
            "engineCalls": {
                "type": "array",
                "minItems": 1,
                "items": engine_call_schema,
            },
        },
    }
    return {
        "type": "object",
        "required": ["repairPatch"],
        "additionalProperties": False,
        "properties": {
            "repairPatch": {
                "type": "object",
                "additionalProperties": False,
                "minProperties": 1,
                "properties": patch_properties,
            },
        },
    }


def _repair_patch_payload(repaired: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Accept only the current repairPatch response contract."""
    unexpected = set(repaired) - {"repairPatch", "_runtimeRepairMeta"}
    if unexpected:
        return {}, "unexpected_response_fields"
    if isinstance(repaired.get("repairPatch"), dict):
        return copy.deepcopy(repaired["repairPatch"]), "repairPatch"
    return {}, "missing_repairPatch"


def _filtered_runtime_repair_patch(repaired: dict[str, Any], original: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract a narrow runtime repair patch from an LLM response.

    This is the anti-chaos boundary: targeted repair may fix executable runtime fields,
    but it is not allowed to become a second free-form item author.  Unknown/full-item
    fields are ignored and recorded for debug.
    """
    payload, source = _repair_patch_payload(repaired)
    payload = normalize_llm_attack_shape(payload) if isinstance(payload, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    accepted: dict[str, Any] = {}
    rejected: list[str] = []
    for key, value in payload.items():
        if key == "debug":
            continue
        if key == "runtimePlan" and isinstance(value, dict):
            accepted[key] = copy.deepcopy(value)
            continue
        if key == "attack" and isinstance(value, dict):
            accepted[key] = copy.deepcopy(value)
            continue
        if key == "gameplay" and isinstance(value, dict):
            filtered = {str(k): copy.deepcopy(v) for k, v in value.items() if str(k) in REPAIR_PATCH_ALLOWED_GAMEPLAY_FIELDS}
            dropped = sorted(str(k) for k in value.keys() if str(k) not in REPAIR_PATCH_ALLOWED_GAMEPLAY_FIELDS)
            if filtered:
                accepted[key] = filtered
            rejected.extend(f"gameplay.{k}" for k in dropped[:32])
            continue
        if key in {"accessory", "armor"} and isinstance(value, dict) and isinstance(original.get(key), dict):
            # Only allow targeted completion of an already-authored accessory/armor surface.
            # Repair must not flip a weapon into armor/accessory by returning a full rewrite.
            accepted[key] = copy.deepcopy(value)
            continue
        rejected.append(str(key))
    report = {
        "schema": "infini.runtime-repair-patch-contract.v1",
        "source": source,
        "acceptedTopLevel": sorted(accepted.keys()),
        "rejectedTopLevel": sorted(set(rejected))[:48],
        "note": "Only repairPatch executable fields are accepted; complete-item responses and identity/visual rewrites are rejected.",
    }
    return accepted, report


def _merge_repair_patch_into_candidate(candidate: dict[str, Any], patch: dict[str, Any]) -> None:
    if isinstance(patch.get("runtimePlan"), dict):
        # Replacing runtimePlan is intentional: executable repair is allowed to replace
        # bad engineCalls with a valid authored runtime contract.
        candidate["runtimePlan"] = copy.deepcopy(patch["runtimePlan"])
        candidate.pop("_runtimePlanCompileCache", None)
    for key in ("attack", "gameplay", "accessory", "armor"):
        if isinstance(patch.get(key), dict):
            base = candidate.get(key) if isinstance(candidate.get(key), dict) else {}
            merged = copy.deepcopy(base)
            merged.update(copy.deepcopy(patch[key]))
            candidate[key] = merged



def _adopt_runtime_plan_repair(data: dict[str, Any], repaired: dict[str, Any], *, key: str, content_preview: str = "") -> dict[str, Any]:
    """Adopt only the executable repair patch while preserving item identity.

    The repair LLM is a contract fixer, not a second item author.  Complete-item JSON and
    old patch aliases are outside the current contract and produce an empty repair.
    """
    if not isinstance(repaired, dict):
        return data
    repaired = copy.deepcopy(repaired)
    repaired_debug = repaired.get("_runtimeRepairMeta") if isinstance(repaired.get("_runtimeRepairMeta"), dict) else {}
    patch, patch_report = _filtered_runtime_repair_patch(repaired, data)
    candidate = copy.deepcopy(data)
    original_debug = dict(candidate.get("debug") or {})
    protected = {
        "id": candidate.get("id") or ("g_" + stable_hash(key, candidate.get("name", ""), length=16)),
        "recipeKey": candidate.get("recipeKey") or key,
        "schemaVersion": candidate.get("schemaVersion") or 1,
        "parentA": candidate.get("parentA"),
        "parentB": candidate.get("parentB"),
        "sourceMode": candidate.get("sourceMode") or "generated",
        "_llmHistory": candidate.get("_llmHistory"),
        "itemKnowledge": candidate.get("itemKnowledge"),
        "recipeMeta": candidate.get("recipeMeta"),
        "inheritance": candidate.get("inheritance"),
        "sourceRepresentation": candidate.get("sourceRepresentation"),
        "name": candidate.get("name"),
        "tooltip": candidate.get("tooltip"),
        "concept": candidate.get("concept"),
        "visual": candidate.get("visual"),
        "tags": candidate.get("tags"),
        "category": candidate.get("category"),
    }
    _merge_repair_patch_into_candidate(candidate, patch)
    for k, v in protected.items():
        if v not in (None, ""):
            candidate[k] = v
    merged_debug = dict(original_debug)
    # Keep repair model/attempt metadata, but never let repair debug erase prior debug.
    for k, v in repaired_debug.items():
        merged_debug.setdefault(str(k), v)
    merged_debug["runtimePlanRepairPatchContract"] = json.dumps(patch_report, ensure_ascii=False)[:4000]
    if content_preview:
        merged_debug["runtimePlanRepairRawOutput"] = content_preview[:4000]
    candidate["debug"] = merged_debug
    return candidate


def try_llm_runtime_plan_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, validation: dict[str, Any], attempt: int) -> dict[str, Any] | None:
    """Run Runtime Repairer from one rich authoritative v3.1 stage dossier."""
    if not USE_LLM:
        return None
    try:
        history_state = planner_history_state(data)
        live_planner = str((data.get("debug") or {}).get("planner") or "") == "llm_author_first"
        if history_state == "malformed" or (history_state == "absent" and live_planner):
            data.setdefault("debug", {})["runtimeRepairHistoryStatus"] = (
                "malformed_fail_closed" if history_state == "malformed" else "missing_live_planner_history_fail_closed"
            )
            return None
        model_name = resolve_llm_model()
        user = _runtime_plan_repair_standalone_packet(data, validation, attempt, a, b, ca, cb, key)
        message_mode = (
            "authoritative_stage_dossier_v31"
            if history_state == "valid"
            else "legacy_authoritative_stage_dossier_v31"
        )
        repair_user_content = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
        repair_system = (
            "You are the Runtime Contract Repairer for a Terraria-like item pipeline. "
            "The earlier item_planner response is provenance only; the latest runtime_validator payload and its currentItem are the authoritative current runtime truth. "
            "Repair executable runtimePlan/attack/gameplay fields only; preserve item identity and visuals. "
            "Return exactly one JSON object whose only top-level field is repairPatch."
            + llm_reasoning_system_suffix(model_name)
        )
        messages = [
            stage_chat_message("system", "runtime_repair_contract", repair_system),
            stage_chat_message("user", "runtime_validator", repair_user_content),
        ]
        req = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.12,
            "response_format": llm_json_response_format(
                "infini_runtime_plan_repair",
                schema=_runtime_repair_response_schema(),
                strict=False,
            ),
        }
        req = apply_llm_common_options(req, model_name=model_name, default_max_tokens=min(5000, llm_answer_max_tokens(2400)))
        trace_event("prompt", "LLM:runtime_plan_repair", f"Runtime plan repair attempt {attempt}: {name_of(a)} + {name_of(b)}", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"), "reasoningEffort": req.get("reasoning_effort"),
            "messageMode": message_mode, "messages": _trace_message_summary(req.get("messages")), "errors": validation.get("errors"),
        }, prompt=repair_user_content)
        raw = llm_chat_json(req, timeout=max(18, env_int("INFINI_LLM_REPAIR_TIMEOUT", env_int("INFINI_LLM_TIMEOUT", 95, lo=1, hi=3600), lo=1, hi=3600) // 2))
        content = raw["choices"][0]["message"]["content"]
        transport_debug = raw.get("_debug") if isinstance(raw.get("_debug"), dict) else {}
        trace_event("response", "LLM:runtime_plan_repair", "Runtime plan repair response", {"model": model_name, "chars": len(str(content)), "attempt": attempt, "messageMode": message_mode, "transport": transport_debug}, response=content)
        obj = parse_first_valid_llm_json(content)
        if isinstance(obj, dict):
            obj["_runtimeRepairMeta"] = {
                "runtimePlanRepairModel": model_name,
                "runtimePlanRepairAttempt": attempt,
                "runtimePlanRepairSource": f"llm_{message_mode}",
                "runtimePlanRepairPlannerHistoryReplayed": False,
                "runtimePlanRepairPreviousErrors": json.dumps(validation.get("errors") or [], ensure_ascii=False),
                "runtimePlanRepairRawPreview": str(content)[:2000],
            }
            return obj
    except Exception as e:
        trace_event("error", "LLM:runtime_plan_repair", "Runtime plan repair failed", {"attempt": attempt, "parents": [name_of(a), name_of(b)]}, error=repr(e))
        log_event("warn", "LLM runtimePlan repair failed", {"error": repr(e), "attempt": attempt})
    return None


def _runtime_repair_kind(validation: dict[str, Any], data: dict[str, Any]) -> str:
    errors = [str(e).lower() for e in (validation.get("errors") or [])]
    if not errors:
        return "none"
    if any("missing runtimeplan" in e for e in errors):
        return "dead_missing_runtime_plan_retry_once"
    if any("no accepted executable calls" in e for e in errors):
        return "structural_or_dead_no_executable_calls"
    if any("lacks set_item_stats" in e for e in errors):
        return "executable_missing_stats"
    if any("lacks a primary executable action" in e or "did not compile" in e or "runtimefamily" in e for e in errors):
        return "executable_targeted_retry"
    return "contract_retry"


def _runtime_repair_attempt_budget(repair_kind: str) -> int:
    # Full dead/missing-runtime cases get one classic retry: if the model returns
    # another corpse, fail + debug/refund. More precise executable repairs may get
    # the existing two-turn budget.
    if repair_kind == "dead_missing_runtime_plan_retry_once":
        return 1
    return 2


def _raw_runtime_plan_candidate(data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the author-supplied plan before structural migration/normalization."""
    for name in ("runtimePlan", "enginePlan", "runtimeAuthoring", "engineRuntimePlan", "runtime_plan", "runtime"):
        value = data.get(name)
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)
    return None


def _merge_raw_boundary_errors(
    validation: dict[str, Any],
    raw_boundary: dict[str, Any] | None,
    structural_fixes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Keep raw contract failures visible after deterministic scalar repair.

    Only fields that the structural repair actually changed may stop being blocking.
    This prevents an author-supplied ``_normalization`` marker from bypassing strict
    type/enum validation while preserving the established ``"24 ticks" -> 24`` path.
    """
    if not raw_boundary or raw_boundary.get("ok"):
        return validation
    repaired = {
        (int(row.get("index", -1)), str(row.get("field") or ""))
        for row in (structural_fixes or [])
        if isinstance(row, dict) and row.get("kind") in {"scalar_parse", "scalar_list_parse"}
    }
    validation_errors = [str(error) for error in (validation.get("errors") or [])]
    blocking: list[str] = []
    for error in (str(row) for row in (raw_boundary.get("errors") or [])):
        match = re.match(r"engineCalls\.(\d+)\.params\.([^.:]+)(?:\.[^:]+)?:", error)
        repaired_here = bool(match and (int(match.group(1)), match.group(2)) in repaired)
        still_invalid = bool(match and any(
            (candidate.startswith(f"engineCalls.{match.group(1)}.params.{match.group(2)}:")
            or candidate.startswith(f"engineCalls.{match.group(1)}.params.{match.group(2)}."))
            for candidate in validation_errors
        ))
        if not repaired_here or still_invalid:
            blocking.append(error)
    merged = dict(validation)
    merged["rawStrictBoundary"] = raw_boundary
    if blocking:
        merged["ok"] = False
        merged["errors"] = list(dict.fromkeys([*blocking, *validation_errors]))
    return merged


def repair_runtime_plan_if_needed(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Repair boundary for LLM runtime authoring before C# sees the item.

    Contract:
    - crooked shape with concrete authored data is repaired by code only;
    - formally valid but non-executable runtime is sent to a targeted LLM retry;
    - totally missing/dead runtime gets one classic retry, then fail/debug/refund;
    - C# remains hard safety only, not the repair layer.
    """
    if not LLM_RUNTIME_AUTHORING:
        return data
    debug = data.setdefault("debug", {})
    authored_runtime_plan = copy.deepcopy(data.get("runtimePlan"))
    raw_plan = _raw_runtime_plan_candidate(data)
    raw_boundary = runtime_plan_boundary_report(raw_plan) if raw_plan is not None else None
    if raw_boundary is not None:
        debug["runtimePlanRawStrictBoundary"] = json.dumps(raw_boundary, ensure_ascii=False)[:6000]
    had_runtime_input = raw_plan is not None

    structural = structural_repair_runtime_plan_inplace(data)
    if structural.get("applied"):
        debug["runtimeStructuralRepair"] = json.dumps(structural, ensure_ascii=False)[:6000]
    # runtime_plan_validation_report owns the single normalization pass.  Running
    # normalize first would make semantic expansions (deploy_sentry -> canonical
    # shoot_projectile) look like raw authoring and reject their compiler-owned
    # fields against the public function schema.
    validation = _merge_raw_boundary_errors(runtime_plan_validation_report(data), raw_boundary, structural.get("fixes"))
    debug["runtimePlanValidationBeforeRepair"] = json.dumps(validation, ensure_ascii=False)[:6000]
    if structural.get("applied") and validation.get("ok"):
        debug["runtimeRepairPath"] = "code_structural_repair_only"
        debug["runtimePlanValidationAfterRepair"] = json.dumps(validation, ensure_ascii=False)[:6000]
        return data

    needs_repair = not bool(validation.get("ok")) and (combat_genome_required_for(data) or bool(runtime_plan(data)))
    if not needs_repair:
        debug.setdefault("runtimeRepairPath", "not_needed")
        return data

    repair_kind = _runtime_repair_kind(validation, data)
    if not had_runtime_input and repair_kind == "structural_or_dead_no_executable_calls":
        repair_kind = "dead_missing_runtime_plan_retry_once"
    attempt_budget = _runtime_repair_attempt_budget(repair_kind)
    debug["runtimeRepairKind"] = repair_kind
    debug["runtimeRepairAttemptBudget"] = str(attempt_budget)

    repair_log: list[dict[str, Any]] = []
    # A rejected candidate is useful as feedback context for the next model turn, but
    # it is never an accepted baseline. Each new patch is applied independently to the
    # last accepted item so narrow fields from an invalid attempt cannot accumulate.
    accepted_baseline = copy.deepcopy(data)
    working = data
    for attempt in range(1, attempt_budget + 1):
        patch = try_llm_runtime_plan_repair(working, a, b, ca, cb, key, validation, attempt)
        row = {
            "attempt": attempt,
            "repairKind": repair_kind,
            "errors": validation.get("errors") or [],
            "gotPatch": bool(patch),
        }
        if not patch:
            repair_log.append(row)
            continue
        candidate = _adopt_runtime_plan_repair(accepted_baseline, patch, key=key, content_preview=str((patch.get("_runtimeRepairMeta") or {}).get("runtimePlanRepairRawPreview") or ""))
        candidate_raw = _raw_runtime_plan_candidate(candidate)
        candidate_raw_boundary = runtime_plan_boundary_report(candidate_raw) if candidate_raw is not None else None
        structural_after = structural_repair_runtime_plan_inplace(candidate)
        if structural_after.get("applied"):
            row["structuralAfterPatch"] = structural_after.get("fixes", [])[:12]
        after = _merge_raw_boundary_errors(runtime_plan_validation_report(candidate), candidate_raw_boundary, structural_after.get("fixes"))
        row["okAfter"] = bool(after.get("ok"))
        row["errorsAfter"] = after.get("errors") or []
        repair_log.append(row)
        working = candidate
        validation = after
        if after.get("ok"):
            working.setdefault("debug", {})["runtimeRepairPath"] = "llm_targeted_runtime_contract_repair"
            working["debug"]["runtimeRepairKind"] = repair_kind
            working["debug"]["runtimePlanRepair"] = json.dumps(repair_log, ensure_ascii=False)[:6000]
            working["debug"]["runtimePlanValidationAfterRepair"] = json.dumps(after, ensure_ascii=False)[:6000]
            return working
    if authored_runtime_plan is not None:
        data["runtimePlan"] = authored_runtime_plan
    debug["runtimeRepairPath"] = "targeted_runtime_repair_exhausted"
    debug["runtimeRepairKind"] = repair_kind
    debug["runtimePlanRepair"] = json.dumps(repair_log, ensure_ascii=False)[:6000]
    debug["runtimePlanValidationAfterRepair"] = json.dumps(validation, ensure_ascii=False)[:6000]
    exact_errors = [str(error) for error in (validation.get("errors") or [])]
    got_invalid_candidate = any(bool(row.get("gotPatch")) for row in repair_log)
    live_llm_authored = (
        str(debug.get("planner") or "") == "llm_author_first"
        or attributed_planner_messages(data.get("_llmHistory")) is not None
    )
    if got_invalid_candidate or live_llm_authored:
        raise PlannerUnavailable(
            "runtime repair exhausted with validator errors: "
            + ("; ".join(exact_errors[:8]) if exact_errors else "invalid repairPatch")
        )
    # Offline compiler/golden fixtures may deliberately exercise canonicalization and
    # rejected-call reporting without an LLM backend. Preserve the original artifact for
    # the later strict boundary after the one canonical normalization pass. This branch is
    # unreachable for live Planner-authored data and never adopts a failed model candidate.
    normalize_runtime_plan_inplace(data)
    debug["runtimeRepairPath"] = "repair_backend_unavailable_preserved_for_offline_strict_boundary"
    return data

def call_llm_vfx_director(system: str, user: dict[str, Any], max_tokens: int, temperature: float, timeout: int, messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
    """Small adapter used by vfx_manifest.py.

    Keeps the VFX module from creating a new LLM backend or importing server.py.
    When messages is supplied, the caller already built the authoritative V3.1
    system + VFX dossier. Planner transcript replay is not part of this adapter.
    """
    if not USE_LLM:
        return None
    try:
        model_name = resolve_llm_model()
        if messages is not None:
            req_messages = [
                stage_chat_message(
                    str(m.get("role") or "user"),
                    str(m.get("name") or ""),
                    str(m.get("content") or ""),
                )
                for m in messages
                if isinstance(m, dict) and str(m.get("content") or "").strip()
            ]
            if not req_messages:
                return None
        else:
            standalone_user = dict(user)
            standalone_user.setdefault("agentHandoff", agent_handoff(
                previous_speaker="pipeline_orchestrator",
                current_speaker="vfx_director_context",
                next_speaker="vfx_director",
                cause_by="vfx_manifest_authoring",
                artifact_source="vfxInputPacket.childItem",
            ))
            handoff_value = standalone_user.get("agentHandoff")
            handoff: dict[str, Any] = handoff_value if isinstance(handoff_value, dict) else {}
            current_speaker = str(handoff.get("currentSpeaker") or "vfx_director_context")
            req_messages = [
                stage_chat_message("system", "vfx_director_contract", system + llm_reasoning_system_suffix(model_name)),
                stage_chat_message("user", current_speaker, json.dumps(standalone_user, ensure_ascii=False, separators=(",", ":"))),
            ]
        req = {
            "model": model_name,
            "messages": req_messages,
            "temperature": float(temperature),
            "response_format": llm_json_response_format("infini_vfx"),
        }
        req = apply_llm_common_options(req, model_name=model_name, default_max_tokens=int(max_tokens))
        trace_event("prompt", "LLM:vfx_director", "VFX director request", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"), "reasoningEffort": req.get("reasoning_effort"),
            "messageMode": "authoritative_stage_dossier_v31" if messages is not None else "legacy_no_history_standalone", "messages": _trace_message_summary(req.get("messages")),
        }, prompt=req_messages)
        raw = llm_chat_json(req, timeout=int(timeout))
        content = raw["choices"][0]["message"]["content"]
        transport_debug = raw.get("_debug") if isinstance(raw.get("_debug"), dict) else {}
        trace_event("response", "LLM:vfx_director", "VFX director response", {"model": model_name, "chars": len(str(content)), "transport": transport_debug}, response=content)
        # Return the model artifact exactly. Transport metadata belongs in trace/debug
        # side channels; injecting `_debug` here makes a valid strict VFX object fail its
        # own top-level contract.
        return parse_first_valid_llm_json(content)
    except Exception as e:
        trace_event("error", "LLM:vfx_director", "VFX director failed", error=repr(e))
        log_event("warn", "LLM VFX director failed", {"error": repr(e)})
        return None


# legacy contract marker for tests/documentation: ensure_llm_auth_configured()
