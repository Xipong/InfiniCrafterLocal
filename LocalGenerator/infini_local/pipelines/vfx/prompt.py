"""VFX model instructions and context assembly over accepted runtime and visuals."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.llm_stage_messages import generation_system_suffix
from infini_local.core.vfx.repair import (
    _vfx_repair_context,
    _vfx_scoped_repair_schema,
    _vfx_scoped_repair_vocabulary,
)
from infini_local.core.vfx.schema import _director_schema
from infini_local.core.vfx.surface import vfx_director_surface
from infini_local.pipelines.context.cards import parent_context_for_stage
from infini_local.pipelines.context.presentation import presentation_parent_card_for_llm

# Project invariant vocabulary from the canonical surface, never a second catalog.
# Unlisted fields stay dynamic, including exact pairs/roles, texture/path sources
# and the output schema derived from the accepted runtime program.
_VFX_RUNTIME_VOCABULARY_KEYS = (
    "schema", "rendererKind", "rendererRequirements", "rendererSemantics",
    "colorPolicy", "heldRootVisibility", "soundId", "sound", "anchor",
    "blend", "layer", "numericRanges", "textureDependencyTuples", "maxSlots",
)


VFX_PROMPT_STATIC_KEYS = ("schema", "rules", "runtimeVocabulary")


VFX_REPAIR_PROMPT_STATIC_KEYS = ("task", "rules", "runtimeVocabularyReadOnly")


_ACCEPTED_GAMEPLAY_CONTEXT_RULE = (
    "acceptedGameplayReadOnly, when present, is the exact accepted gameplay, not an edit target. "
    "useTime/useAnimation are base item cadence/animation in world ticks (60/s); itemScale is the "
    "held-root dimensionless multiplier, not a VFX slot scale or PNG frame size. Do not infer "
    "missing values, live attack-speed modifiers or event frequency from names/prose. "
    "runtimePairs owns event availability; acceptedRuntimeProgramReadOnly owns exact bindings/events and "
    "independent motion fields, including ordered seek. attachment reads an anchor; armPose alone does not "
    "attach a body. bodyPresentation.frame carries only present native wire operands: distances are world pixels, "
    "not Gameplay Author blocks; durations are world ticks. While its window is active, the attachment step sets body center to "
    "anchor + aimAxis*(axisOffsetPx + active reachOffsetPx) + normal*normalOffsetPx; normal is aimAxis rotated +pi/2. "
    "reach and armPose curves sample clamped active world age/durationTicks; windows gate them, not restart them. "
    "Reach translates the rigid body and is not canceled by PNG grip. armPose writes a native pose, not a body anchor. "
    "For beamGeometry, beamStart.anchor is the base pivot: start=projectile.Center+axis*startOffsetPx, "
    "end=start+axis*lengthPx, on the same Aim world unit axis (MotionAxis). "
    "Read startOffsetPx only when present in frame.beamGeometry; historical absence means zero and stays absent. "
    "The signed offset changes only line origin, never length, width, attachment/reach, body physics or PNG scale; "
    "explicit tile raycast may clip length from that start. Retained controller beamStart keeps its native anchor/offset. "
    "A beam texturedPath follows this exact shared line and beamAxis, not inventory grip or a guessed hand contact; "
    "no_asset still permits explicit path decoration without an underlying body. These facts do not guarantee hand contact. "
    "A window may be phase-only or include clock/startDelayTicks/durationTicks together. "
    "Absent window means all active updates; since_release/since_return are inactive before their latch, "
    "released may overlap returning. Native counts stay native counts. Read-only motion creates no slots, "
    "events, textures or Repair permissions."
)


_PLACED_VFX_RULE = "Optional placementBindingId selects only an exact runtimeSurface.placementBindings entry of this item_body: periodic/self spriteElement/libraryParticle/nativeLight. Omit selector for ordinary item/projectile effects; placed-selected slots never emit in hand/equipment. Bounds are read-only actual top-left native TileFrameY, not animation age. self is footprint center, forward=right, side=down, velocity=0. Offset separate flame ingredients with element.offsetForwardPx/offsetSidePx; reuse existing assets for live flames while root PNG stays stable physical furniture. Source attachment retires on off/removal; world particles finish bounded life. Only this placed-selected cohort uses maxParticlesTotal as a fresh allowance per due emission burst, not a cumulative lifetime cap; maxParticlesPerTick and global live-instance/draw caps remain. Light emits only on due world ticks: repeatEvery=1 means steady light; no automatic cadence rewrite. No new gameplay or automatic slot insertion."


_READABILITY_RULE = (
    "Compose presentation readable at gameplay zoom for intended visible attacks and secondary effects; "
    "sound-only is not a visible gameplay cue. Consider the accepted delayed area action's event anchor, "
    "radiusPx and delayTicks, and actual child bodies' size, contrast, lifetime and movement separately. "
    "A few tiny fading particles or dark small PNGs can be technically valid yet unreadable. "
    "Choose count, world-pixel dimensions, opacity and lifetime together using actual renderer controls, "
    "not prose metadata. "
    "For delayed cues shape/spriteElement/libraryParticle/nativeDust/nativeLight use event-relative startTick. "
    "An on_hit cue starts from that hit occurrence, not automatically from a gameplay action's delayed execution; "
    "match the accepted delay explicitly only with a renderer that consumes it. "
    "For a physical child's visibility, prefer accents on that exact child's available spawn/periodic/hit pairs "
    "rather than decorative debris that could be mistaken for additional damaging bodies. "
    "Keep accents consistent with actual coverage: do not invent damage, extra gameplay projectiles or a larger damaging area. "
    "There is no automatic VFX insertion or minimum brightness: deliberate absence/zero remains valid; "
    "in Repair this guidance applies only inside diagnosed permissions and never opens frozen slots or mechanics."
)


def _prompt_packet(data: Mapping[str, Any], parent_a: Mapping[str, Any] | None, parent_b: Mapping[str, Any] | None) -> dict[str, Any]:
    realization_raw = data.get("realization")
    realization: Mapping[str, Any] = {"description": realization_raw} if isinstance(realization_raw, str) else realization_raw if isinstance(realization_raw, Mapping) else {}

    def parent_packet(parent: Mapping[str, Any] | None) -> dict[str, Any]:
        source: Mapping[str, Any] = parent if isinstance(parent, Mapping) else {}
        generated_raw = source.get("generatedData")
        generated: Mapping[str, Any] = generated_raw if isinstance(generated_raw, Mapping) else {}
        summary_raw = generated.get("generatedParentSummary")
        if not isinstance(summary_raw, Mapping):
            summary_raw = source.get("generatedParentSummary")
        return {
            "name": str(source.get("name") or source.get("displayName") or ""),
            "internalName": str(source.get("internalName") or ""),
            "sourceMod": str(source.get("sourceMod") or ""),
            "generatedParentSummary": copy.deepcopy(dict(summary_raw)) if isinstance(summary_raw, Mapping) else {},
            "packet": presentation_parent_card_for_llm(dict(source), stage="vfx"),
        }

    parent_context = parent_context_for_stage([parent_packet(parent_a), parent_packet(parent_b)], stage="vfx")
    runtime = data.get("runtimeProgram")
    mechanics = copy.deepcopy(dict(runtime)) if isinstance(runtime, Mapping) else {}
    for entity in mechanics.get("entities") or []:
        if isinstance(entity, dict):
            entity.pop("visual", None)
    surface = vfx_director_surface(data)
    packet = {
        "schema": "infini.vfx-director-input.runtime-events.v1",
        "item": {
            "id": str(data.get("id") or ""), "name": str(data.get("name") or ""),
            "description": str(realization.get("description") or ""),
            "playerExperience": str(realization.get("playerExperience") or ""),
        },
        **parent_context,
        "acceptedVisualKit": copy.deepcopy(data.get("visualKit") or {}),
        **({"acceptedGameplayReadOnly": copy.deepcopy(data["gameplay"])} if "gameplay" in data else {}),
        "acceptedRuntimeProgramReadOnly": mechanics,
        "runtimeVocabulary": {key: surface[key] for key in _VFX_RUNTIME_VOCABULARY_KEYS},
        "runtimeSurface": {key: value for key, value in surface.items() if key not in _VFX_RUNTIME_VOCABULARY_KEYS},
        "outputSchema": _director_schema(data),
        "rules": [
            "Bind every slot to one exact runtimeSurface.runtimePairs entityId+event pair.",
            "Do not add gameplay, entities, events, hitboxes, damage, movement, child spawning, or status effects.",
            _ACCEPTED_GAMEPLAY_CONTEXT_RULE,
            _READABILITY_RULE,
            "acceptedRuntimeProgramReadOnly contains the actual accepted mechanics, not another design request. Read its exact movement, controller, lifetime, collision, bindings and event parameters when composing presentation; runtimePairs still owns event availability. Do not invent missing geometry from names or the prose summary. Visual attachment and particle motion never change the source entity's gameplay.",
            "shape composes explicit bounded line/arc/wave/orbit/sector instances. Duration is lifetime and repeatEvery is emission cadence, never geometric animation period. Only authored color/opacity/radius endpoints and angular speeds animate them; no extra fade or Dust accompaniment. Each segment/mote consumes one shared draw call. nativeDust and nativeLight are independent slots with explicit emission controls.",
            "Use only enum values and numeric ranges from runtimeVocabulary; each selected rendererKind also requires the exact companion fields in runtimeVocabulary.rendererRequirements (encoded in the slot schema).",
            "spriteElement and texturedPath use only their explicit nested texture and runtimeVocabulary.textureDependencyTuples; omit common scale/density/spread/particleSystemId/textureRole. Respect their own timing, opacity profiles and read-only geometry sources in runtimeVocabulary.rendererSemantics, runtimeSurface.texturedPathSources and outputSchema. Beam/whip/ownerLink current geometry owns placement and requires neutral anchor=self, historyTicks=0, minDistancePx=0 and profileDomain=length; anchorHistory keeps its authored anchor. ownerLink is an explicit optional cosmetic connector to projectile.Center, not automatic from movement, item names or categories. Require path.ownerAnchor=mountedCenter or frontHand only on ownerLink; omit it on all other sources. mountedCenter reads native owner.MountedCenter, not a hand. frontHand requires a currently enabled compositeFrontArm; when unavailable the connector is refused/retired, never guessed from body frames or changed to center.",
            "Compose a coherent visible body, motion and impact from acceptedVisualKit, including its advisory animationPlan. runtimeSurface.bodyPresentation states what is already drawn: solid_untextured is a plain line, not a shaded weapon or textured skin; VFX cannot remove it. no_body has no underlying image. A texturedPath can carry an explicitly authored material along the actual beam/whip curve using a generated strip, width/color/opacity profiles and UV choice. Do not stretch a full inventory icon into a rope or mistake an impact spark for body coverage. Keep these choices deliberate; restrained presentation may still use empty slots.",
            _PLACED_VFX_RULE,
            "assets is optional: request at most sixteen isolated texture ingredients consistent with acceptedVisualKit, declare exact safe IDs once and reuse explicitly through element.texture, path.texture, trail.texture or geometry.draws[].material.texture. No filesystem paths/URLs or execution metadata. Never request unused art. cutout fits soft-alpha subjects; strip preserves authored frame/UV through resize without crop/recenter/rotation. Either layout can serve either new renderer; no asset-name or weapon classifier.",
            "Return only one JSON object matching outputSchema.",
        ],
    }
    return {
        **{key: packet[key] for key in VFX_PROMPT_STATIC_KEYS},
        **{key: value for key, value in packet.items() if key not in VFX_PROMPT_STATIC_KEYS},
    }


def _director_system(*, repair: bool = False) -> str:
    if repair:
        return (
            "You are the conditional VFX Repair. Repair only the explicit broken VFX fields. You may return a complete "
            "broken slot; deterministic merge freezes already-valid old values and ignores extra rewrites. Bind only accepted "
            "runtime entity/event pairs. Gameplay is immutable. Return strict JSON only."
        ) + generation_system_suffix()
    return (
        "You are the VFX Director. Author finite Terraria presentation only for accepted low-level runtime entity/event pairs. "
        "Make the accepted item’s body, motion, timing and impacts legible as one coherent design. "
        "Preserve its intended physical identity: a held, floating or detached body should read as a deliberate part of the "
        "composition, not an unexplained visual gap. Collision geometry describes coverage; it does not require the "
        "visible object to resemble a bare collision primitive. Work within the accepted Visual and gameplay choices. "
        "Gameplay is immutable. Return strict JSON only."
    ) + generation_system_suffix()


def build_vfx_repair_packet(
    packet: Mapping[str, Any],
    previous: Any,
    repair_scope: Mapping[str, Any],
    repair_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble only diagnosed repair context; never broaden frozen permissions."""
    context = _vfx_repair_context(previous, repair_scope or {})
    user = {
        "task": "Patch only exact invalid VFX fields/slots.",
        "item": copy.deepcopy(packet.get("item") or {}),
        "acceptedVisualKitReadOnly": copy.deepcopy(packet.get("acceptedVisualKit") or {}),
        **({"acceptedGameplayReadOnly": copy.deepcopy(packet["acceptedGameplayReadOnly"])} if "acceptedGameplayReadOnly" in packet else {}),
        "acceptedRuntimeProgramReadOnly": copy.deepcopy(packet.get("acceptedRuntimeProgramReadOnly") or {}),
        "runtimeVocabularyReadOnly": copy.deepcopy(packet.get("runtimeVocabulary") or {}),
        "runtimeSurfaceReadOnly": copy.deepcopy(packet.get("runtimeSurface") or {}),
        # The single Repair must see every diagnosis behind its permissions.
        "exactErrors": copy.deepcopy(repair_errors),
        "repairScope": copy.deepcopy(dict(repair_scope or {})),
        "brokenFragments": context["broken"],
        "malformedRawText": context["malformedRawText"],
        "validGeneratedContext": context["validReadOnly"],
        "outputSchema": _vfx_scoped_repair_schema(packet, previous, repair_scope or {}),
        "rules": [
            "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
            "already-valid fields and independent slots are frozen; extra rewrites are ignored",
            "Only exact validator-diagnosed foreign/additional leaves listed in deletePaths may be deleted by omission from an upsert; all other omissions are no-change. Delete duplicate asset rows only by diagnosed original assetIndicesDelete, never by a shared asset ID.",
            "schema and note are required; omit unchanged edit fields as no-ops, including assetsUpsert/assetIdsDelete/assetIndicesDelete. Present arrays may not be null. Valid asset prompts, layout, canvas, references and optional absence are frozen. Repair a bad reference only; never create compensating artwork.",
            "bind only exact runtimeSurfaceReadOnly.runtimePairs entityId+event pairs; runtimeVocabularyReadOnly owns the read-only enum values, numeric ranges, rendererRequirements, rendererSemantics and textureDependencyTuples",
            "presentation only; gameplay is immutable",
            _PLACED_VFX_RULE,
            _ACCEPTED_GAMEPLAY_CONTEXT_RULE,
            _READABILITY_RULE,
        ],
    }
    # Parent ancestry informs new artwork, not corrections to an accepted
    # effect's numeric limits or exact references. The accepted child visual
    # and runtime stay available for every repair; ancestry never widens scope.
    permissions = (repair_scope or {}).get("fieldPermissions") or {}
    design_paths = {"slots": {"", "rendererKind", "spritePrompt", "spriteNegativePrompt"},
                    "assets": {"", "prompt", "negativePrompt"}}
    design = any((repair_scope or {}).get(key) for key in ("allowCreateSlots", "allowCreateAssets")) or any(
        path.split(".", 1)[0].split("[", 1)[0] in design_paths[kind]
        for kind in design_paths for row in permissions.get(kind) or []
        for path in row.get("paths") or [] if path not in (row.get("deletePaths") or [])
    )
    if design:
        user["parentFactsReadOnly"] = copy.deepcopy(packet.get("parents") or [])
        for key in ("parentBriefs", "parentBriefRule"):
            if key in packet:
                user[key] = copy.deepcopy(packet[key])
    user["runtimeVocabularyReadOnly"] = _vfx_scoped_repair_vocabulary(
        user["runtimeVocabularyReadOnly"], previous, repair_scope or {},
    )
    if user["runtimeVocabularyReadOnly"] != packet.get("runtimeVocabulary"):
        user["rules"] = user["rules"][:4] + [
            "outputSchema owns the exact editable numeric/domain limits and companion relations. Read-only source facts never open additional field permissions.",
            "presentation only; gameplay is immutable",
            _PLACED_VFX_RULE,
            _ACCEPTED_GAMEPLAY_CONTEXT_RULE,
        ]
    user = {
        **{key: user[key] for key in VFX_REPAIR_PROMPT_STATIC_KEYS},
        **{key: value for key, value in user.items() if key not in VFX_REPAIR_PROMPT_STATIC_KEYS},
    }
    return user
