"""Visual Director and conditional Repair request/response boundary."""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.generation_defaults import GENERATION_DEFAULTS
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_prompt_cache import (
    with_instruction_segments,
    with_schema_instruction_definitions,
)
from infini_local.core.llm_stage_messages import generation_system_suffix, stage_chat_message
from infini_local.storage.trace_runtime import trace_event, trace_stage_request
from infini_local.pipelines.transport.provider_wire import (
    effective_response_format,
    apply_llm_common_options,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    visual_director_max_tokens,
    with_llm_stage,
)
from infini_local.pipelines.transport.client import llm_chat_json, resolve_llm_model
from infini_local.core.provider_schema import (
    _provider_strict_projection,
    project_provider_nullable_optionals_to_local,
    provider_nullable_transport_rule,
)
from infini_local.pipelines.context.cards import parent_context_for_stage
from infini_local.pipelines.context.presentation import presentation_parent_card_for_llm
from infini_local.pipelines.visual.assets import equipment_overlay_requirement
from infini_local.pipelines.images.prompts import visual_background_transport_rule
from infini_local.pipelines.visual.modes import visual_asset_mode_catalog
from infini_local.pipelines.visual.contract import (
    MalformedVisualDirectorOutput,
    _response_schema,
    _visual_repair_schema,
)
from infini_local.pipelines.visual.context import _presentation_packet_context, _runtime_card
from infini_local.pipelines.visual.repair_scope import (
    _scoped_visual_repair_schema,
    _visual_repair_context,
)
from infini_local.pipelines.visual.repair import _expand_scoped_visual_repair_patch


_VISUAL_STATIC_PREFIX_KEYS = ("task", "assetModeCatalog", "rules", "spritePresentationReadOnly")


def _request_visual_kit(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    repair_errors: list[dict[str, Any]] | None = None,
    previous: Any = None,
    repair_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any] | MalformedVisualDirectorOutput:
    runtime_rows = _runtime_card(data)
    entity_ids = [row["id"] for row in runtime_rows]
    item_body_id = next((row["id"] for row in runtime_rows if row["kind"] == "item_body"), "")
    equipment_overlay = equipment_overlay_requirement(data)
    equipment_overlay_required = bool(equipment_overlay["required"])
    item_context = {"name": data.get("name"), "realization": copy.deepcopy(data.get("realization") or {})}
    concept = data.get("concept")
    synthesis = concept.get("literalSynthesis") if isinstance(concept, Mapping) else None
    if isinstance(concept, str):
        item_context["concept"] = concept
    if isinstance(synthesis, str) and synthesis.strip():
        # Carry appearance intent literally, without importing planned mechanics
        # or turning optional prose into an authority over accepted runtime.
        item_context["literalSynthesis"] = synthesis
    repair = repair_errors is not None
    scoped_repair = (repair and isinstance(repair_scope, Mapping) and "fieldPermissions" in repair_scope
                     and not any(error.get("path") == "$" for error in repair_errors or []))
    schema = (
        _scoped_visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id, repair_scope or {}, previous)
        if scoped_repair else _visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id)
        if repair
        else _response_schema(entity_ids, equipment_overlay_required, item_body_id)
    )
    response_format = llm_json_response_format(
        "infini_visual_kit_repair_patch" if repair else "infini_visual_kit_runtime_entities",
        schema=lambda: _provider_strict_projection(schema), strict=True, auto_preference="json_schema",
    )
    sent_schema = response_format["json_schema"]["schema"] if response_format and response_format.get("type") == "json_schema" else schema
    if repair:
        system = (
            "You are the conditional Visual Repair. Return only a narrow patch for exact invalid visual fields/rows. "
            "You may return a complete broken row; deterministic merge freezes every already-valid old field and keeps "
            "the exact repaired or newly missing fields. Extra rewrites are ignored. Runtime gameplay is immutable. "
            "The runtime entity with kind=item_body must use baked_sprite regardless of its entityId; set visualProjectRef=item and omit prompt/silhouette/visualIdentity; root item owns that design. "
            "Only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item; never create a second visual project for it. "
            "Use assetModeCatalog as the exact PNG-delivery and runtime-draw contract. Return JSON only."
        )
        if isinstance(previous, MalformedVisualDirectorOutput):
            system += (
                " The previous response is malformed JSON. Repair its syntax and container only: preserve all "
                "recoverable visual fields and entity choices verbatim from malformedRawText; do not invent "
                "an absent design. Emit the complete broken visual response through the repair patch fields."
            )
        context = _visual_repair_context(previous, repair_scope or {})
        payload: dict[str, Any] = {
            "task": "Patch only exact invalid visualKit fields/rows.",
            "exactErrors": copy.deepcopy(repair_errors or []),
            "malformedRawText": context["malformedRawText"],
            "repairScope": copy.deepcopy(dict(repair_scope or {})),
            "brokenFragments": context["broken"],
            "validGeneratedContext": context["validReadOnly"],
            "parentFactsReadOnly": {
                "parentA": {"packet": presentation_parent_card_for_llm(a, stage="visual")},
                "parentB": {"packet": presentation_parent_card_for_llm(b, stage="visual")},
            },
            "runtimeEntitiesReadOnly": runtime_rows,
            "itemReadOnly": item_context,
            "equipmentOverlayReadOnly": copy.deepcopy(equipment_overlay),
            "assetModeCatalog": visual_asset_mode_catalog(),
            "rules": [
                "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
                visual_background_transport_rule(),
                "already-valid fields and independent rows are frozen; extra rewrites are ignored",
                "preserve already-valid child appearance and the accepted runtime entity set",
                "the runtime entity with kind=item_body must use baked_sprite regardless of its entityId; set visualProjectRef=item and omit prompt/silhouette/visualIdentity; root item owns that design",
                "only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item and must not author a second visual project",
                "when equipmentOverlayReadOnly.required is true, repair equipOverlayPatch as a separate wearable presentation asset",
            ],
            "responseSchema": sent_schema,
        }
    else:
        system = (
            "You are Visual Director for InfiniCrafterLocal. Design appearance only for the accepted runtime entities. "
            "Do not add, remove, merge, rename or reinterpret gameplay entities/events. "
            "Realize the authored concept as a coherent appearance compatible with the accepted mechanics. "
            "Make the relationship between the inventory object, its in-use bodies and its effects readable: physical continuity or deliberate transformation and detachment should be clear to the player. "
            "Collision geometry describes hit placement, not the complete object silhouette; absence of guaranteed hand contact is not itself a reason to design a floating weapon. "
            "For each exact entityId choose one finite assetMode: "
            "baked_sprite, reuse_item_icon, runtime_geometry, or no_asset. The entity with kind=item_body, regardless of its entityId, uses baked_sprite with visualProjectRef=item and only entityId/assetMode/visualProjectRef/scale; root item owns its prompt/silhouette/visualIdentity. "
            "A distinct baked entity uses visualProjectRef=entity and authors prompt/silhouette/visualIdentity. reuse_item_icon uses visualProjectRef=item and omits those fields; runtime_geometry/no_asset use visualProjectRef=none and omit them. "
            "Only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item; never create a second visual project for it. "
            "Use assetModeCatalog as the exact PNG-delivery and runtime-draw contract. "
            "A baked sprite is mandatory delivery: never request or accept a placeholder. Return a strict JSON object with double-quoted JSON object keys and string values; no trailing commas or JavaScript expressions."
        )
        payload = {
            "task": "Author one visualKit for the accepted runtime program.",
            "item": item_context,
            "parents": {
                "parentA": {"packet": presentation_parent_card_for_llm(a, stage="visual")},
                "parentB": {"packet": presentation_parent_card_for_llm(b, stage="visual")},
            },
            "runtimeEntities": runtime_rows,
            "requiredEntityIds": entity_ids,
            "equipmentOverlayReadOnly": copy.deepcopy(equipment_overlay),
            "assetModeCatalog": visual_asset_mode_catalog(),
            "rules": [
                "appearance only; runtime program is immutable",
                "item.literalSynthesis, when present, is advisory authored appearance intent. Develop it into a coherent visual identity compatible with the accepted runtime. Parent visual references inform the design; they do not require copying whole objects. Visual Director owns appearance and asset choices; accepted mechanics remain authoritative.",
                "For a newly designed held item choose item.grip explicitly at its actual handle/contact point on the final item PNG canvas after crop/fit/padding, before facing/gravity flips. Both normalized coordinates are required together. Describe that same contact point in item.prompt; do not infer coordinates from an entityId or request image analysis.",
                "For a newly designed accessory choose equipOverlay.accessoryMount explicitly from chest/back/waist/shoulder/orbit to suit its authored appearance. It attaches the existing single PNG badge to the body pivot; it is not a full armor sheet or a behind-body occlusion guarantee. Optional omission selects the existing orbit presentation; never fill optional metadata during Repair unless its exact path is permitted.",
                "literal furniture, tools and materials may remain literal",
                "movement/controller names describe motion, not a weapon taxonomy",
                "baked_sprite requires a real generated PNG; no placeholder",
                visual_background_transport_rule(),
                "never author impact sprite prompts here; VFX owns them only when it selects rendererKind=impactSprite",
                "the runtime entity with kind=item_body must use baked_sprite regardless of its entityId; set visualProjectRef=item and omit prompt/silhouette/visualIdentity; root item owns that design",
                "only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item and must not author a second visual project",
                "reuse_item_icon carries only entityId, assetMode, visualProjectRef=item and scale; do not duplicate prompt or identity fields",
                "runtime_geometry carries entityId, assetMode, visualProjectRef=none, scale and explicit geometry; no_asset carries the same metadata without geometry. Geometry dimensions/color/opacity/axis are authored presentation, never copied from hitbox/light. collision_path requires an accepted beam/lash path; body_segment aim axis requires accepted aim.",
                "when equipmentOverlayReadOnly.required is true, author equipOverlay as a separate transparent wearable layer for that exact slot, without drawing a player body",
            ],
            "responseSchema": sent_schema,
        }
    response_schema = payload.pop("responseSchema")
    presentation = _presentation_packet_context(data, runtime_rows)
    if scoped_repair:
        permissions = (repair_scope or {})["fieldPermissions"]
        paths = [*(permissions.get("itemPaths") or []), *(permissions.get("equipOverlayPaths") or []),
                 *(path for row in permissions.get("entities") or [] for path in row.get("paths") or [])]
        roots = {path.split(".", 1)[0].split("[", 1)[0] for path in paths}
        design = bool(roots & {"", "prompt", "silhouette", "visualIdentity", "palette", "assetMode", "visualProjectRef"})
        sizing = bool(roots & {"", "renderSizePx", "preferredCanvasSize", "inventoryScale", "worldScale", "scale", "grip", "forwardAngleDegrees", "assetMode", "visualProjectRef"})
        if not design:
            parents = payload.pop("parentFactsReadOnly")
            references = {}
            for key, parent in parents.items():
                card = parent["packet"]
                raw_parent = card.get("raw") or {}
                generated = raw_parent.get("generatedParent") or {}
                references[key] = {
                    **({"spriteReference": copy.deepcopy(raw_parent["spriteReference"])} if "spriteReference" in raw_parent else {}),
                    **({"visual": copy.deepcopy(generated["visual"])} if "visual" in generated else {}),
                    "entities": [{"id": row["id"], **({"visual": copy.deepcopy(row["visual"])} if "visual" in row else {})}
                                 for row in (generated.get("runtimeProgram") or {}).get("entities") or []],
                }
            payload["parentSizeReferencesReadOnly"] = references
        guidance = presentation["spritePresentationReadOnly"]
        selected = {"requiredMetadata"}
        if design:
            selected.update({"ownership", "geometryCoverage", "axis", "rotation"})
        if sizing:
            selected.update({"units", "formulas", "ownership", "sourceCalibration"})
        if roots & {"", "forwardAngleDegrees", "grip"}:
            selected.update({"axis", "rotation"})
        mechanics = presentation["acceptedPresentationMechanicsReadOnly"]
        if sizing and any(isinstance(((row.get("usePolicy") or {}).get("action") or {}).get("placement"), Mapping)
                          and "placedBody" in row["usePolicy"]["action"]["placement"]
                          for row in mechanics.get("bindings") or []):
            selected.add("placedBody")
        if roots & {"", "preferredCanvasSize", "renderSizePx", "grip", "assetMode", "visualProjectRef"}:
            selected.add("fill")
        if roots & {"", "grip", "renderSizePx", "forwardAngleDegrees", "assetMode", "visualProjectRef"} and any("spriteDependenciesReadOnly" in row for row in runtime_rows):
            selected.update({"frontHand", "handContactGeometry", "axis", "motionWindows"})
        presentation["spritePresentationReadOnly"] = {key: value for key, value in guidance.items() if key in selected}
        if not sizing:
            presentation.pop("bakeFillByProcessingRole")
            presentation.pop("acceptedPresentationMechanicsReadOnly")
        else:
            roles = {"item"} if not permissions.get("entities") else set(presentation["bakeFillByProcessingRole"])
            presentation["bakeFillByProcessingRole"] = {key: value for key, value in presentation["bakeFillByProcessingRole"].items() if key in roles}
        if not roots & {"", "assetMode", "visualProjectRef"}:
            payload["assetModeCatalog"] = {}
        payload["rules"] = [
            "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
            "already-valid fields and independent rows are frozen; extra rewrites are ignored; runtime gameplay is immutable",
        ] + ([visual_background_transport_rule()] if design else [])
        system = (
            "You are the conditional Visual Repair. Return only the exact permitted patch leaves and selectors "
            "in responseSchema. Omitted fields are unchanged. Accepted design, independent rows and gameplay "
            "are immutable; extra rewrites are ignored by frozen-first merge. Return JSON only."
        ) if not isinstance(previous, MalformedVisualDirectorOutput) else system
    payload.update(presentation)
    if not scoped_repair:
        payload["rules"].append("Explicitly choose required renderSizePx and forwardAngleDegrees for item and those plus preferredCanvasSize for each distinct baked project; item_body/reuse inherit root and must not duplicate them. Canvas is resolution, not world size; do not use gameplay hitbox dimensions as a bake canvas chooser.")
    parent_key = "parentFactsReadOnly" if repair else "parents"
    if parent_key in payload:
        context = parent_context_for_stage(payload.pop(parent_key), stage="visual")
        payload[parent_key] = context.pop("parents")
        payload.update(context)
    payload["responseSchema"] = response_schema
    # Ordering only: keep every field/value in the same complete JSON object.
    # Entity-specific responseSchema (including its exact ID enums) remains after
    # the boundary, as do all parent, item, error, and Repair context fields.
    payload = {
        **{key: payload[key] for key in _VISUAL_STATIC_PREFIX_KEYS},
        **{key: value for key, value in payload.items() if key not in _VISUAL_STATIC_PREFIX_KEYS},
    }
    system += provider_nullable_transport_rule(response_format)
    model = resolve_llm_model()
    request = {
        "model": model,
        "messages": [
            stage_chat_message("system", "visual_repair_contract" if repair else "visual_director_contract", system + generation_system_suffix() + llm_reasoning_system_suffix(model)),
            stage_chat_message("user", "visual_repair_context" if repair else "visual_director_context", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        ],
        "temperature": (
            env_float("INFINI_VISUAL_REPAIR_TEMPERATURE", 0.12)
            if repair
            else env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", float(GENERATION_DEFAULTS["INFINI_VISUAL_DIRECTOR_TEMPERATURE"]))
        ),
        "max_tokens": visual_director_max_tokens(),
        "response_format": response_format,
    }
    request = apply_llm_common_options(request, model_name=model, default_max_tokens=visual_director_max_tokens())
    request = with_instruction_segments(request, payload, _VISUAL_STATIC_PREFIX_KEYS)
    item_key = "itemPatch" if repair else "item"
    item_path = ("properties", item_key, "anyOf", 0) if repair else ("properties", item_key)
    definition_paths: dict[str, tuple[str | int, ...] | tuple[tuple[str | int, ...], ...]] = {
        item_key: item_path,
    }
    if not repair:
        definition_paths["animationPlan"] = ("properties", "animationPlan")
    # Explicit canonical entity leaves; ownership/ID enums and roster bounds stay
    # inline USER constraints. Both local oneOf and provider anyOf are supported.
    entity_path = ("properties", "entitiesUpsert" if repair else "entities", "items")
    entity_schema = sent_schema["properties"].get(entity_path[1], {}).get("items", {"properties": {}})
    union = "anyOf" if "anyOf" in entity_schema else "oneOf"
    branches = entity_schema.get(union, [entity_schema])
    branch_paths = [entity_path + (union, index) for index in range(len(branches))] if union in entity_schema else [entity_path]
    scale_paths = tuple(path + ("properties", "scale") for path, branch in zip(branch_paths, branches) if "scale" in branch.get("properties", {}))
    if scale_paths:
        definition_paths["entityScale"] = scale_paths
    for field in ("prompt", "silhouette", "visualIdentity"):
        paths = tuple(
            path + ("properties", field) for path, branch in zip(branch_paths, branches)
            if field in branch["properties"]
        )
        if paths:
            definition_paths["entity_" + field] = paths
    if not scoped_repair:
        request = with_schema_instruction_definitions(request, "responseSchema", definition_paths)
    stage_name = "visual_repair" if repair else "visual_director"
    trace_event("prompt", "LLM:" + stage_name, "Visual stage request", {"recipeKey": data.get("recipeKey"), "recipeId": data.get("id")}, prompt=request["messages"])
    trace_stage_request(stage_name, data.get("recipeKey"), request, recipe_id=data.get("id"))
    raw = llm_chat_json(with_llm_stage(request, "visual_repair" if repair else "visual_director"), timeout=env_int("INFINI_LLM_TIMEOUT", int(GENERATION_DEFAULTS["INFINI_LLM_TIMEOUT"])))
    content = raw["choices"][0]["message"]["content"]
    trace_event("response", "LLM:" + stage_name, "Visual stage response", {"recipeKey": data.get("recipeKey"), "recipeId": data.get("id")}, response=content)
    try:
        parsed = parse_first_valid_llm_json(content)
        effective_format = effective_response_format(request, raw)
        # Repair's object-or-null blocks have no semantic discriminator. Select the
        # object branch by container type, not by whether invalid authored leaves
        # happen to validate; those leaves must still reach exact-scope Repair.
        if repair and isinstance(parsed, dict) and effective_format and effective_format.get("type") == "json_schema":
            provider_props = effective_format["json_schema"]["schema"]["properties"]
            for key in ("itemPatch", "equipOverlayPatch"):
                if isinstance(parsed.get(key), dict) and key in schema["properties"]:
                    parsed[key] = project_provider_nullable_optionals_to_local(
                        parsed[key], schema["properties"][key]["anyOf"][0],
                        response_format={"type": "json_schema", "json_schema": {"schema": provider_props[key]["anyOf"][0]}},
                    )
        parsed = project_provider_nullable_optionals_to_local(parsed, schema, response_format=effective_format)
        return _expand_scoped_visual_repair_patch(parsed, previous, repair_scope or {}, entity_ids) if scoped_repair else parsed
    except (ValueError, TypeError) as exc:
        if repair:
            raise PlannerUnavailable(f"Visual Repair returned malformed JSON: {type(exc).__name__}: {exc}") from exc
        return MalformedVisualDirectorOutput(raw_text=str(content), error=f"{type(exc).__name__}: {exc}")
