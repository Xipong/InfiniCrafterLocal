from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.env_utils import env_float
from infini_local.core.item_identity_tools import name_of
from infini_local.core.llm_stage_messages import (
    agent_handoff,
    stage_chat_message,
)
from infini_local.core.parent_role_facts import sole_strong_parent_role_obligation
from infini_local.core.runtime_authoring.schema import (
    COMBAT_EXECUTOR_RESULT_KINDS,
    COMBAT_ROOT_AUTHORED_REQUIRED_PARAMS,
)
from infini_local.pipelines.author_item_contract import (
    author_item_prompt_shape_card,
    author_item_provider_repair_response_schema,
    author_item_provider_response_schema,
    author_item_provider_targeted_repair_delta_schema,
)
from infini_local.pipelines.author_item_repair_scope import (
    FULL_REDESIGN_REQUIRED_PATCH_KEYS,
    FULL_REDESIGN_REQUIRED_PLAN_KEYS,
    _failure_mentions,
    _rejected_call_ids,
    _repair_allowed_patch_keys,
    _repair_targets,
    _resolve_indexed_target_call_owners,
    _targeted_call_id_repair_specs,
    _targeted_param_delete_specs,
    _targeted_provider_delta_scope,
    _targeted_repair_function_cards,
)
from infini_local.pipelines.llm_authoring_prompt import (
    COMBAT_EXECUTOR_RESULT_KIND_RULE,
    EQUIPMENT_LIGHT_ENCODING,
    PULL_ON_HIT_ENCODING,
    ROOT_EXECUTOR_AUTHOR_RULES,
    RUNTIME_PLAN_METADATA_TYPES,
    VISUAL_TOPOLOGY_RULES,
    VISIBLE_ENGINE_FUNCTIONS,
    engine_runtime_capability_contract_for_llm,
)
from infini_local.pipelines.llm_transport import (
    apply_llm_common_options,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    resolve_llm_model,
)


_REPAIR_SCHEMA_CARD_KEYS = (
    "type", "enum", "const", "minLength", "maxLength", "pattern",
    "minimum", "maximum", "minItems", "maxItems",
)


def _repair_schema_constraint_card(schema: dict[str, Any]) -> dict[str, Any]:
    """Project exact wire constraints into the human-visible repair dossier."""
    card = {
        key: copy.deepcopy(schema[key])
        for key in _REPAIR_SCHEMA_CARD_KEYS
        if key in schema
    }
    properties = schema.get("properties")
    if isinstance(properties, dict):
        card["properties"] = {
            str(name): _repair_schema_constraint_card(child)
            for name, child in properties.items()
            if isinstance(child, dict)
        }
    required = schema.get("required")
    if isinstance(required, list) and required:
        card["required"] = [str(value) for value in required]
    items = schema.get("items")
    if isinstance(items, dict):
        card["items"] = _repair_schema_constraint_card(items)
    for union_key in ("anyOf", "oneOf"):
        branches = schema.get(union_key)
        if isinstance(branches, list):
            card[union_key] = [
                _repair_schema_constraint_card(branch)
                for branch in branches
                if isinstance(branch, dict)
            ]
    return card


def _author_item_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Return only the model-owned object, never compiler/debug projections."""
    raw = data.get("_authorItemRaw")
    candidate = raw if isinstance(raw, dict) else data
    schema = author_item_provider_response_schema()
    properties = schema.get("properties")
    keys = properties.keys() if isinstance(properties, dict) else ()
    snapshot = {
        str(field): copy.deepcopy(candidate[field])
        for field in keys
        if field in candidate
    }
    contract_candidate = snapshot.get("runtimeContract")
    if isinstance(contract_candidate, dict):
        snapshot["runtimeContract"] = {
            field: copy.deepcopy(contract_candidate[field])
            for field in ("primaryVerb", "controlStyle", "playerViewTimeline")
            if field in contract_candidate
        }
    return snapshot


def _scoped_repair_candidate(patch: dict[str, Any]) -> dict[str, Any]:
    """Project the compact repair response into model-owned AuthorItem domains."""
    candidate: dict[str, Any] = {}
    for field in ("name", "category"):
        if field in patch:
            candidate[field] = copy.deepcopy(patch[field])
    concept = {
        field: copy.deepcopy(patch[field])
        for field in ("fantasy", "mergeLogic", "coreMechanic")
        if field in patch
    }
    if concept:
        candidate["concept"] = concept
    contract = {
        field: copy.deepcopy(patch[field])
        for field in ("primaryVerb", "controlStyle", "playerViewTimeline")
        if field in patch
    }
    if contract:
        candidate["runtimeContract"] = contract
    plan = copy.deepcopy(patch["runtimePlan"]) if isinstance(patch.get("runtimePlan"), dict) else {}
    for field in ("sourceRolePreservation", "visualIntent"):
        if field in patch:
            plan[field] = copy.deepcopy(patch[field])
    if plan:
        candidate["runtimePlan"] = plan
    return candidate


def _scoped_repair_context(current_item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    concept_candidate = current_item.get("concept")
    concept: dict[str, Any] = concept_candidate if isinstance(concept_candidate, dict) else {}
    plan_candidate = current_item.get("runtimePlan")
    plan: dict[str, Any] = plan_candidate if isinstance(plan_candidate, dict) else {}
    current_runtime_plan = {
        field: copy.deepcopy(plan[field])
        for field in (
            "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
            "balanceIntent", "anomalyFlags",
        )
        if field in plan
    }
    preserved_context = {
        "name": current_item.get("name"),
        "fantasy": concept.get("fantasy"),
        "mergeLogic": concept.get("mergeLogic"),
        "visualIntent": copy.deepcopy(plan.get("visualIntent")),
        "sourceRolePreservation": copy.deepcopy(plan.get("sourceRolePreservation")),
    }
    return current_runtime_plan, preserved_context


def build_same_author_repair_request(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    failure_report: dict[str, Any],
) -> tuple[dict[str, Any], str, str, bool, dict[str, Any]]:
    """Build one bounded, concept-preserving same-author repair request."""
    current_item = _author_item_snapshot(data)
    current_runtime_plan, preserved_context = _scoped_repair_context(current_item)
    targeted_repair = not _failure_mentions(
        failure_report,
        "executor_not_representable",
        "unsupported_mechanic_family",
        "unrepresentable_mechanic",
        "combat result lacks set_item_stats",
        "runtime supports one root executor",
    )
    model_name = resolve_llm_model()
    allowed_patch_keys = _repair_allowed_patch_keys(failure_report, targeted_repair)
    capability = engine_runtime_capability_contract_for_llm(a, b)
    available_function_cards = capability.get("availableFunctions")
    available_cards: dict[str, Any] = (
        available_function_cards if isinstance(available_function_cards, dict) else {}
    )
    invalid_targets = _resolve_indexed_target_call_owners(
        _repair_targets(failure_report),
        current_runtime_plan,
    )
    if targeted_repair and any(
        str(target.get("kind") or "").strip().lower()
        in {"additional_property", "extra_forbidden"}
        and not (
            ".engineCalls[" in str(target.get("path") or "")
            and "].params." in str(target.get("path") or "")
        )
        for target in invalid_targets
    ):
        # Targeted deltas have an exact delete primitive for rejected engine params,
        # but intentionally no arbitrary Author-object delete API. A whole same-author
        # redesign is the bounded way to remove unknown nested Author keys.
        targeted_repair = False
        allowed_patch_keys = _repair_allowed_patch_keys(failure_report, False)
    if targeted_repair and any(
        str(target.get("kind") or "") == "structural_call_rejected"
        for target in invalid_targets
    ):
        targeted_repair = False
        allowed_patch_keys = _repair_allowed_patch_keys(failure_report, False)
    call_id_repair_specs: list[dict[str, Any]] = []
    param_delete_specs: list[dict[str, Any]] = []
    repair_function_cards: dict[str, Any] = {}
    provider_author_field_schemas: dict[str, dict[str, Any]] = {}
    provider_runtime_metadata_fields: set[str] = set()
    provider_identity_field_schemas: dict[str, dict[str, Any]] = {}
    if targeted_repair:
        call_id_repair_specs = _targeted_call_id_repair_specs(
            current_runtime_plan,
            invalid_targets,
        )
        param_delete_specs = _targeted_param_delete_specs(
            current_runtime_plan,
            invalid_targets,
        )
        repair_function_cards = _targeted_repair_function_cards(
            current_runtime_plan,
            invalid_targets,
            available_cards,
        )
        (
            provider_author_field_schemas,
            provider_runtime_metadata_fields,
            provider_identity_field_schemas,
        ) = _targeted_provider_delta_scope(
            current_item,
            invalid_targets,
            allowed_patch_keys,
        )
        if not (
            repair_function_cards
            or provider_author_field_schemas
            or provider_runtime_metadata_fields
            or provider_identity_field_schemas
            or call_id_repair_specs
            or param_delete_specs
        ):
            # A call-level rejection (for example a second root executor) has no
            # honest leaf delta. Spend the same single repair call on the existing
            # full same-author redesign contract instead of aborting with an empty
            # provider grammar or inventing deterministic call surgery.
            targeted_repair = False
            allowed_patch_keys = _repair_allowed_patch_keys(failure_report, False)
    if not targeted_repair:
        repair_function_cards = {
            fn: copy.deepcopy(available_cards[fn])
            for fn in sorted(set(VISIBLE_ENGINE_FUNCTIONS))
            if fn in available_cards
        }
        provider_author_field_schemas = {}
        provider_runtime_metadata_fields = set()
        provider_identity_field_schemas = {}
        call_id_repair_specs = []
        param_delete_specs = []
    mandatory_redesign_contracts: list[dict[str, Any]] = []
    category_by_result_kind = {
        "weapon": "weapon",
        "consumable_weapon": "weapon",
        "tool": "tool",
        "accessory": "accessory",
        "armor": "armor",
        "potion": "potion",
    }
    required_function_by_result_kind = {
        "weapon": "one root executable action",
        "consumable_weapon": "one root executable action",
        "tool": "tool_capability",
        "accessory": "accessory_effect",
        "armor": "armor_effect",
        "potion": "apply_player_effect_on_use",
    }
    for target in invalid_targets:
        expected_kind = str(target.get("expectedResultKind") or "").strip()
        if expected_kind == "furniture" and isinstance(target.get("placeableParents"), list):
            mandatory_redesign_contracts.append({
                "category": "furniture",
                "resultKind": "furniture",
                "requiredEngineFunction": "placeable_behavior",
                "exactParentPlacementCandidates": copy.deepcopy(target.get("placeableParents") or []),
                "furnitureStats": {"consumable": True, "maxStack": ">1"},
            })
            continue
        if expected_kind not in category_by_result_kind:
            continue
        contract: dict[str, Any] = {
            "category": category_by_result_kind[expected_kind],
            "resultKind": expected_kind,
            "requiredEngineFunction": required_function_by_result_kind[expected_kind],
            "rawParentStrongRole": str(target.get("parentStrongRole") or ""),
        }
        if expected_kind == "armor":
            contract["exactArmorSlots"] = copy.deepcopy(target.get("expectedArmorSlots") or [])
        mandatory_redesign_contracts.append(contract)
    raw_parent_role = sole_strong_parent_role_obligation(a, b)
    raw_expected_kind = str(raw_parent_role.get("expectedResultKind") or "")
    if (
        raw_parent_role.get("applicable")
        and raw_expected_kind in category_by_result_kind
        and not any(
            contract.get("resultKind") == raw_expected_kind
            for contract in mandatory_redesign_contracts
        )
    ):
        raw_contract: dict[str, Any] = {
            "category": category_by_result_kind[raw_expected_kind],
            "resultKind": raw_expected_kind,
            "requiredEngineFunction": required_function_by_result_kind[raw_expected_kind],
            "rawParentStrongRole": str((raw_parent_role.get("strongParentRoles") or [""])[0]),
        }
        if raw_expected_kind == "armor":
            raw_contract["exactArmorSlots"] = copy.deepcopy(
                raw_parent_role.get("expectedArmorSlots") or []
            )
        mandatory_redesign_contracts.append(raw_contract)
    metadata_shape = author_item_prompt_shape_card().get("runtimeContract")
    visual_intent_rule = (
        "visualIntent is a top-level patch key; never place it inside runtimePlan."
        if "visualIntent" in allowed_patch_keys
        else "Do not return visualIntent because it is not in allowedPatchKeys."
    )
    redesign_rules = [
        COMBAT_EXECUTOR_RESULT_KIND_RULE,
        (
            "Every combat root engine call MUST include "
            f"{', '.join(COMBAT_ROOT_AUTHORED_REQUIRED_PARAMS)} explicitly; "
            "for one emitted body/projectile use shotCount=1 and spreadRadians=0."
        ),
        "A full redesign must remove non-representable calls instead of restating their params.",
        (
            "For passive armor/accessory light, use only armor_effect.stats or "
            "accessory_effect.stats with both lightStrength and lightColorName; omit "
            "set_alt_use_mode and emit_light."
        ),
        (
            "set_alt_use_mode mode=light is an active non-equipment utility and requires "
            "a positive emit_light call plus durationTicks."
        ),
    ]
    if mandatory_redesign_contracts:
        redesign_rules.insert(
            0,
            "A full redesign MUST satisfy mandatoryRedesignContracts and must not preserve the rejected result identity.",
        )
    system = (
        "You are the scoped repair pass of the SAME ITEM AUTHOR ROLE. "
        "Return only a compact JSON patch using allowedPatchKeys; never repeat the full AuthorItem. "
        "Repair only invalidTargets. Preserve identity, fantasy, fusion, physical parts, and visual topology from preservedConceptContext. "
        "For targeted repair, accepted engine calls remain byte-equivalent unless their callId is invalid. "
        "For full_redesign, redesign gameplay only; the compiler still does not choose mechanics. "
        + " ".join(redesign_rules)
        + " "
        "No reasoning, markdown, wrapper, proof graph, receipts, or DTO paths."
        + llm_reasoning_system_suffix(model_name)
    )
    dossier = {
        "task": "Repair only the rejected authored domain and return a compact patch.",
        "agentHandoff": agent_handoff(
            previous_speaker="item_planner",
            current_speaker="authoring_contract_gate",
            next_speaker="item_planner",
            cause_by="authoring_domain_rejected",
            artifact_source="current_authored_item",
        ),
        "repairMode": "targeted_domain_repair" if targeted_repair else "full_redesign",
        "contextOnlyParentNames": {"itemA": name_of(a), "itemB": name_of(b)},
        "allowedPatchKeys": allowed_patch_keys,
        "allowedEngineFunctions": list(VISIBLE_ENGINE_FUNCTIONS),
        "rootExecutorRules": dict(ROOT_EXECUTOR_AUTHOR_RULES),
        "combatRootRequiredParams": list(COMBAT_ROOT_AUTHORED_REQUIRED_PARAMS),
        "combatExecutorResultKinds": sorted(COMBAT_EXECUTOR_RESULT_KINDS),
        "runtimePlanMetadataTypes": dict(RUNTIME_PLAN_METADATA_TYPES),
        "pullOnHitEncoding": dict(PULL_ON_HIT_ENCODING),
        "visualTopologyRules": copy.deepcopy(VISUAL_TOPOLOGY_RULES),
        "equipmentLightEncoding": copy.deepcopy(EQUIPMENT_LIGHT_ENCODING),
        "redesignRules": redesign_rules,
        "mandatoryRedesignContracts": mandatory_redesign_contracts,
        "requiredPatchKeys": sorted(FULL_REDESIGN_REQUIRED_PATCH_KEYS),
        "requiredRuntimePlanKeys": sorted(FULL_REDESIGN_REQUIRED_PLAN_KEYS),
        "repairFunctionCards": repair_function_cards,
        "repairMetadataShape": copy.deepcopy(metadata_shape) if isinstance(metadata_shape, dict) else {},
        "patchRules": [
            visual_intent_rule,
            "Return every requiredPatchKeys and requiredRuntimePlanKeys field; use an authored empty string/list only when the field is intentionally empty.",
            "runtimePlan.resultKind must match set_item_stats.params.resultKind; top category is weapon only for consumable_weapon, otherwise it equals that resultKind.",
            "Every runtimePlan.engineCalls replacement entry is a complete call with callId, fn, and params.",
            "Every fn must be one of allowedEngineFunctions; never invent or alias an engine function.",
            "Keep exactly one primary function; temporary helpers cannot fire or act as turrets; deploy_sentry is the only turret function.",
        ],
        "invalidTargets": invalid_targets,
        "currentRuntimePlan": current_runtime_plan,
        "currentCoreMechanic": (
            (current_item.get("concept") or {}).get("coreMechanic")
            if isinstance(current_item.get("concept"), dict)
            else ""
        ),
        "currentPlayerViewTimeline": (
            (current_item.get("runtimeContract") or {}).get("playerViewTimeline")
            if isinstance(current_item.get("runtimeContract"), dict)
            else []
        ),
        "preservedConceptContext": preserved_context,
    }
    response_schema = author_item_provider_repair_response_schema(set(allowed_patch_keys))
    response_schema_name = "infini_author_item_scoped_repair_v1"
    response_format_preference = "json_object"
    if targeted_repair:
        system = (
            "You are the SAME item_planner who authored the accepted item below. "
            "The item is a finished accepted product except for the exact rejected leaves. "
            "Calibrate only those leaves against the complete accepted item. "
            "Return only a TargetedRepairDelta JSON object: changed params only, never a runtimePlan wrapper, never a repeated AuthorItem, and never unchanged calls or params. "
            "Use engineCallParamPatches for ordinary value fixes. Use engineCallParamDeletes only for exact invalidTargets marked additional_property or compiler_provenance_dropped. Use engineCallIdPatches only for an exact rejected callId leaf. Structural call replacement, addition, and removal are not part of targeted repair. "
            "Do not change accepted callId/fn pairs, identity, concept, visual topology, or metadata except an exact leaf explicitly listed in invalidTargets. "
            "No reasoning, markdown, proof graph, receipts, or DTO paths."
            + llm_reasoning_system_suffix(model_name)
        )
        rejected_call_ids = sorted(_rejected_call_ids(failure_report, current_runtime_plan))
        targeted_delta_shape: dict[str, Any] = {}
        if provider_identity_field_schemas:
            targeted_delta_shape["identity"] = {
                "category": "current or exact authorized value",
                "resultKind": "current or exact authorized value",
            }
        if provider_author_field_schemas:
            targeted_delta_shape["authorFields"] = {
                field: _repair_schema_constraint_card(schema)
                for field, schema in sorted(provider_author_field_schemas.items())
            }
        if provider_runtime_metadata_fields:
            targeted_delta_shape["runtimeMetadata"] = sorted(
                provider_runtime_metadata_fields
            )
        if repair_function_cards:
            targeted_delta_shape["engineCallParamPatches"] = [{
                "callId": "existing rejected callId",
                "fn": "same accepted fn",
                "params": {"changedParamOnly": "new typed value"},
            }]
        if param_delete_specs:
            targeted_delta_shape["engineCallParamDeletes"] = copy.deepcopy(
                param_delete_specs
            )
        if call_id_repair_specs:
            targeted_delta_shape["engineCallIdPatches"] = [{
                "callIndex": "exact rejected index",
                "currentCallId": "exact rejected id",
                "fn": "same accepted fn",
                "newCallId": "new valid snake_case id",
            }]
        dossier = {
            "task": "Repair only the exact rejected leaves in your otherwise accepted finished item.",
            "agentHandoff": agent_handoff(
                previous_speaker="authoring_contract_gate",
                current_speaker="item_planner",
                next_speaker="authoring_contract_gate",
                cause_by="exact_authored_leaves_rejected",
                artifact_source="acceptedAuthorItem",
            ),
            "repairMode": "targeted_leaf_delta",
            "acceptedAuthorItem": current_item,
            "invalidTargets": invalid_targets,
            "rejectedCallIds": rejected_call_ids,
            "allowedAuthorDomains": allowed_patch_keys,
            "repairFunctionCards": repair_function_cards,
            "paramDeleteSpecs": param_delete_specs,
            "targetedRepairDeltaShape": targeted_delta_shape,
            "deltaRules": [
                "Return the smallest sufficient delta; omit every unchanged top-level key.",
                "Patch every repairFunctionCards.requiredParamPaths leaf. Use every repairFunctionCards.requiredValues value exactly. Params otherwise contain changed leaves only; return each requiredTogether group in full and repeat an unchanged sibling.",
                "A params patch must repeat the existing callId and fn exactly.",
                "An engineCallParamDeletes entry must return every exact paramDeleteSpecs.paramPaths leaf and no other path.",
                "An engineCallIdPatches entry changes only the rejected callId and must repeat callIndex, currentCallId, and fn exactly.",
                "If identity changes, return identity.category and identity.resultKind together and keep set_item_stats.params.resultKind equal.",
                "Do not add, remove, replace, or repeat accepted calls.",
            ],
        }
        response_schema = author_item_provider_targeted_repair_delta_schema(
            repair_function_cards,
            allowed_author_field_schemas=provider_author_field_schemas,
            allowed_runtime_metadata_fields=provider_runtime_metadata_fields,
            identity_field_schemas=provider_identity_field_schemas,
            allowed_call_id_repairs=call_id_repair_specs,
            allowed_param_deletes=param_delete_specs,
        )
        response_schema_name = "infini_author_item_targeted_repair_delta_v1"
        response_format_preference = "json_schema"
    user_content = json.dumps(dossier, ensure_ascii=False, separators=(",", ":"))
    req = {
        "model": model_name,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "final_wire_compiler", user_content),
        ],
        "temperature": env_float(
            "INFINI_LLM_REAUTHOR_TEMPERATURE",
            env_float("INFINI_LLM_TEMPERATURE", 0.38, lo=0.0, hi=1.2),
            lo=0.0,
            hi=1.2,
        ),
        "response_format": llm_json_response_format(
            response_schema_name,
            schema=response_schema,
            strict=True,
            auto_preference=response_format_preference,
        ),
    }
    return (
        apply_llm_common_options(req, model_name=model_name),
        user_content,
        system,
        targeted_repair,
        current_item,
    )
