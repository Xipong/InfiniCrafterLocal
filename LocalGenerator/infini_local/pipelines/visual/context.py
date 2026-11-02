"""Read-only runtime and renderer facts supplied to the Visual Director."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.visual_contract_schema import front_hand_sprite_requirement, collision_path_source
from infini_local.core.runtime_authoring.wire_views import runtime_event_inventory
from infini_local.pipelines.visual.contract import _visual_item_schema


def _runtime_card(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    from infini_local.core.runtime_authoring.capability_registry import (
        CAPABILITY_REGISTRY,
        CONTROLLER_OPCODE,
        MOVEMENT_OPCODE,
        PROJECTILE_MODIFIER_COMPONENTS,
    )
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    events_by_entity: dict[str, list[str]] = {}
    for row in runtime_event_inventory(data):
        if isinstance(row, Mapping):
            events_by_entity.setdefault(str(row.get("entityId") or ""), []).append(str(row.get("event") or ""))
    rows: list[dict[str, Any]] = []
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        movement = dict(entity["movement"]) if isinstance(entity.get("movement"), Mapping) else {}
        controller = dict(entity["controller"]) if isinstance(entity.get("controller"), Mapping) else {}
        # Explain exact accepted drivers from their canonical owner, not a
        # name/category classifier or a second geometry/representation registry.
        driver_meanings = {}
        for slot, driver, opcodes in (("movement", movement, MOVEMENT_OPCODE), ("controller", controller, CONTROLLER_OPCODE)):
            name = driver.get("name")
            capability = CAPABILITY_REGISTRY.get(name) if type(name) is str else None
            if capability is not None and capability.component_slot == slot and type(driver.get("code")) is int and opcodes.get(capability.name) == driver["code"]:
                driver_meanings[slot] = capability.summary
        rows.append({
            "id": str(entity.get("id") or ""),
            "kind": str(entity.get("kind") or ""),
            "visualRole": str(entity.get("visualRole") or ""),
            "movement": copy.deepcopy(dict(movement)),
            "controller": copy.deepcopy(dict(controller)),
            "driverMeaningReadOnly": driver_meanings,
            **({"spriteDependenciesReadOnly": requirement} if (requirement := front_hand_sprite_requirement(entity)) is not None else {}),
            "modifierMeaningReadOnly": {
                member: CAPABILITY_REGISTRY[fn].summary for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items() if member in entity
            } | ({"whipUsesOwnerGravity": CAPABILITY_REGISTRY["orient_whip_to_owner_gravity"].summary} if entity.get("whipUsesOwnerGravity") is True else {}),
            "events": sorted(set(events_by_entity.get(str(entity.get("id") or ""), []))),
            "bodyGeometrySourcesReadOnly": {"collision_path": collision_path_source(entity), "aimAxisAvailable": isinstance(entity.get("aim"), Mapping)},
            "hitbox": copy.deepcopy(entity.get("hitbox") or {}),
            **{field: copy.deepcopy(entity[field]) for field in ("spawn", "lifetimeTicks", "collision", "hitboxCurve", "light", *PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity") if field in entity},
        })
    return rows


def _presentation_packet_context(data: Mapping[str, Any], runtime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    from infini_local.core.images.contracts import native_held_frame_facts, sprite_contract_for
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), Mapping) else {}
    mechanics = {
        "gameplay": {field: copy.deepcopy(gameplay[field]) for field in ("itemScale", "width", "height", "useTime", "useAnimation", "reuseDelay") if field in gameplay},
        **{field: copy.deepcopy(runtime[field]) for field in ("itemEntityId", "primaryEntityId", "primaryOwner", "itemUse", "itemContact", "bindings") if field in runtime},
    }
    canvases = _visual_item_schema()["properties"]["preferredCanvasSize"]["enum"]
    roles = {"item", *("runtime:" + row["visualRole"] for row in runtime_rows if row["kind"] != "item_body")}
    fill_fields = ("targetFill", "minFill", "maxFill", "marginPx", "cropPadPx", "targetLongAxisPx", "alphaMode")
    fill = {}
    for role in sorted(roles):
        fill[role] = {}
        for canvas in canvases:
            contract = sprite_contract_for(role, canvas)
            fill[role][str(canvas)] = {field: copy.deepcopy(contract[field]) for field in fill_fields}
    return {
        "acceptedPresentationMechanicsReadOnly": mechanics,
        "nativeHeldCanvasReadOnly": native_held_frame_facts(data),
        "spritePresentationReadOnly": {
            "placedVfx": "Accepted placement.placedVfx opt-in bounds are read-only actual top-left native TileFrameY, not an animation schedule. Root PNG is stable physical furniture/art; separate live flames, sparks or glow can be independently generated existing VFX assets later. Later VFX slots are not yet authored: describe intended independent live effects without claiming they exist, inserting slots, changing accepted mechanics or animating/pulsing/rotating the whole root PNG. Existing optional placedBody remains a static root picture; baked flames in it stay static even when off. Do not automatically strip accepted or authored decorative art; compose deliberate stable physical root vs intended independent live effects. VFX Director owns exact slots/assets after Visual.",
            "placedBody": {
                "operation": "placed_sprite",
                **{key: copy.deepcopy(value) for key, value in CAPABILITY_REGISTRY["placed_sprite"].prompt_card().items() if key == "params"},
                "meaning": CAPABILITY_REGISTRY["placed_sprite"].summary,
                "ownership": "Accepted bindings[].usePolicy.action.placement.placedBody transforms are immutable gameplay-owned facts. Visual designs the existing root item PNG only: no additional placed PNG/project, source flag, placement entity, or redesign of these transforms. Its pivotSpace selects frame (also omission) or alpha_bounds of the final selected PNG; alpha_bounds uses nonzero-alpha pixel edges, while frame preserves intentional padding. The whole PNG remains uncropped, its size still counts the full frame, and imagePivot/rotation/flips/offsets remain read-only. A visible base intended to touch ground can use alpha_bounds and imagePivotY=1; this does not promise collision/footprint matching for arbitrary art. The placed pivot is independent of held grip, forwardAngleDegrees and dropped-item worldScale. An absent placedBody is native presentation, never infer this operation from parents or furniture appearance.",
            },
            "units": "R=renderSizePx is the larger complete final frame side in base world pixels, not alpha-bbox, hitbox, requested canvas or physical shaft/tip length. C is the actual loaded final frame max-side. G=gameplay.itemScale, W=item.worldScale, I=item.inventoryScale, D=hitbox.drawScale, E=entity.scale and current P=Projectile.scale are independent dimensionless multipliers; Visual cannot edit G or D.",
            "axis": "forwardAngleDegrees is the final PNG local forward-axis in degrees: 0=+X, positive clockwise in y-down coordinates, before facing/gravity flips. It describes pixels, not AI movement. Describe this pose in the same authored prompt; reuse inherits root pixels and axis, never a second inferred axis.",
            "rotation": "For every selected main PNG, renderer angle = body-forward angle minus flipped PNG forward axis, so visible forward = body-forward. velocity/axis mode sets body angle = velocity/aim direction + offsetRadians (zero velocity uses aim). Offset 0 aligns with travel/aim; pi/2 deliberately draws sideways. PNG forwardAngleDegrees=-90 describes upward pixels, not a way to cancel that offset. Draw the declared PNG axis literally and preserve accepted rotation. spin follows its authored angle/time law. Without a rotation component, body-forward starts at world angle 0 (right); movement drivers update it, while a stationary body retains its last orientation. Aim, attachment and arm pose do not supply body rotation. PNG-axis metadata cannot repair that accepted pose. Native storage angle is an internal driver convention; dedicated impact/asset stamps and explicit geometry axis=rotation keep their separately documented literal raw-angle contract.",
            "heldRootVisibility": {
                "hideUseGraphic": CAPABILITY_REGISTRY["item_use"].params["hideUseGraphic"].description,
                "wireHint": "runtimeProgram.itemUse.hideUseGraphic",
            },
            "formulas": {
                "q": "R / max(actual final PNG frame width, height)",
                "inventory": "s_inventory * min(1, caller inventory frame max-side / C) * I; unchanged, no q",
                "world": "q_item * s_world * W",
                "held": "q_item * player.GetAdjustedItemScale(held) (G already included once)",
                "body": "q_selected * P when accepted hitboxCurve.mirrorToSprite=true or visualScaleCurve is present, with P=D*E*curveScale(active age) from that explicit visual owner; otherwise q_selected * clamp(P, .1, 8). No new curve or mirror is inferred.",
                "liveBodyCopy": "q_selected * clamp(P, .1, 8) * slot.Scale",
                "detachedBodyCopy": "q_selected * existing dimensionless pose/slot multiplier; capture/network pose remains dimensionless",
                "visibleAlphaExtent": "alpha-bbox pixels * q_selected * independent draw multipliers",
                "equalHeldBody": "Shared root guarantees equal base frame size, not final size: with neutral caller modifiers equality requires G == clamp(D*E, .1, 8), or G == D*E*curveScale(active age) for an accepted explicit mirror or visualScaleCurve. An independent hitbox curve does not multiply visual scale. Never change accepted gameplay to force equality.",
            },
            "frontHand": "attachment.anchor=front_hand reads the shared native hand H, with or without its own armPose; armPose alone does not attach a body or require PNG metadata. Read aim, attachment offsets and reach as fixed mechanics, never derive them from art. Sprite modes require selected renderSizePx, forwardAngleDegrees and atomic final-canvas grip: reuse_item_icon selects item.grip with no duplicate entity metadata; distinct baked_sprite selects entity grip. no_asset/runtime_geometry require no PNG grip. Describe the actual contact region; Repair changes only diagnosed owner leaves.",
            "motionWindows": "Read exact component windows: absent means all active updates; phase-only gates are valid. Optional clock/startDelayTicks/durationTicks occur together. active is start-of-step; since_release/since_return are inactive before their latch. released can overlap returning. Preserve seek array order and native counts, not Author seconds.",
            "handContactGeometry": "Native arm stretch changes hand length only from 4 to 10px, not arbitrary reach. With active front_hand attachment, the selected PNG grip adapter compensates attachment offsets only, not reach: reach physically translates that grip relative to the native hand. Offsets still move body center and beam origin. front_arm_pose independently poses the hand; it does not cancel body displacement. owner_mounted reads MountedCenter, not the hand. no_asset/runtime_geometry have no selected PNG grip, and a hidden root PNG's grip does not anchor a separate beam surface. Beam collision, runtime_geometry and VFX share start=body center+axis*(startOffsetPx or zero), end=start+axis*lengthPx, using the same Aim world unit axis (MotionAxis). Signed startOffsetPx translates only the line origin, not length, width, attachment/reach, body physics or PNG scale; historical absence means zero. A moving rigid body's hilt region can slide beneath the palm; projectile.Center is not that grip region. A selected body PNG with a held claim uses the native held-projectile pass, where the front hand can cover it. Detached texturedPath BeforeProjectiles/AfterProjectiles layers do not imply this occlusion or constant grip-point contact. Visual/VFX cannot repair accepted pose or geometry. Compare projected art with collision using formulas.body, never extend mechanics by enlarging the PNG. Parent texture dimensions calibrate art only. Preserve all accepted offsets, pose, motion and unreported art during Repair.",
            "ownership": "Root item owns R/canvas/axis for item_body and reuse_item_icon. A distinct baked entity owns R/canvas/axis. no_asset/runtime_geometry own none. Dedicated impact, overlay, material world widths, textured paths and collision/movement are outside this main-PNG conversion.",
            "fill": "Canonical bake fill/padding below describes artwork span inside the requested frame, not world size. Baked final frame and alpha extent may differ; no post-image axis/bbox inference. Runtime tip anchors remain existing gameplay geometry, not measured PNG tips.",
            "geometryCoverage": "Choose the visible body deliberately. runtime_geometry draws the explicitly authored geometry: a centered body_segment on its selected axis or an existing collision_path, with independent world-pixel dimensions, RGB color and opacity; it does not create a detailed sword, whip skin, taper or surface texture. A baked_sprite/reuse_item_icon is one rigid PNG at the body position, not a skin stretched along a curved path. For an authored textured curve, independent VFX texturedPath can follow supported beam/whip paths with its own generated strip and width/color/opacity profiles. Keeping runtime_geometry also keeps its solid base underneath; no_asset suppresses that base. If choosing no_asset for a visible path body, state that intended full-body texturedPath clearly in animationPlan for the following VFX stage; this is a request, not proof that a slot already exists. no_asset can also mean deliberate invisibility. ownerLink is a separate cosmetic straight connector to projectile.Center: ownerAnchor=mountedCenter reads owner.MountedCenter, while frontHand requires compositeFrontArm.enabled and otherwise refuses; neither invents a curved collision path. Other path sources forbid ownerAnchor. Choose surfaces and effects that make the accepted movement readable at gameplay scale. No automatic sprite stretching, mode conversion, VFX insertion or changes to accepted mechanics.",
            "sourceCalibration": "Use available parent raw.spriteReference loaded texture/currentFrame or generatedParent.visual.renderSizePx as read-only size calibration, not a required copy. Consider chosen renderSizePx together with canonical bake fill/padding and intended visible alpha extent; canvas resolution alone does not set body size. Native projectile spriteReference describes only an observed loaded atlas; framesRaw is a declared default, not proof of the actual draw layout. Custom draw frames, alpha bounds and world extent remain unknown unless observed in draw-source facts. Missing reference or alpha bounds are unknown: never substitute hitbox/collider dimensions, fallback textures or an inferred parent size. Accepted useTime/useAnimation, spawn, lifetimeTicks and collision constrain animation description only; do not change gameplay or frozen Repair fields.",
            "requiredMetadata": "Explicitly choose required presentation fields. No defaults, clamps, inferred axis or rebake.",
        },
        # This selected role roster is a runtime fact, not instruction authority.
        # All other presentation members above are invariant application rules.
        "bakeFillByProcessingRole": fill,
    }
