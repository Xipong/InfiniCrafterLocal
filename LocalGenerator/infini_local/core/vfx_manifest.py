from __future__ import annotations

"""Finite VFX Director contract over exact runtime entity/event pairs.

Gameplay has already been accepted before this module runs.  VFX slots may only
bind presentation to an existing ``entityId + event`` pair and cannot add or
change gameplay, entities, hitboxes, damage, movement, or lifecycle.
"""

import copy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Callable, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_stage_messages import generation_system_suffix, stage_chat_message
from infini_local.core.repair_merge import json_path_relative, json_values_equal, merge_frozen_subtree
from infini_local.core.runtime_authoring import ENTITY_KIND_REGISTRY, runtime_event_inventory, runtime_visual_roles, strict_schema_errors
from infini_local.core.vfx_material_contract import ASSET_ID_PATTERN, MATERIAL_RENDERERS, NEUTRAL_FIELDS, asset_schema, element_schema, library_particle_schema, material_slot_clauses, material_texture_clauses, path_schema, runtime_asset_schema, screen_shake_schema
from infini_local.core.vfx_manifest_config import (
    VFX_LLM_DIRECTOR_MAX_SLOTS,
    VFX_LLM_DIRECTOR_MAX_TOKENS,
    VFX_LLM_REPAIR_TEMPERATURE,
    VFX_LLM_DIRECTOR_TEMPERATURE,
    VFX_LLM_DIRECTOR_TIMEOUT,
)


VFX_MANIFEST_SCHEMA = "infini.vfx.runtime-events.v15"
VFX_DIRECTOR_SCHEMA = "infini.vfx-director.runtime-events.v2"
VFX_REPAIR_PATCH_SCHEMA = "infini.vfx-repair-patch.runtime-events.v1"
# Project invariant vocabulary from the canonical surface, never a second catalog.
# Unlisted fields stay dynamic, including exact pairs/roles, texture/path sources
# and the output schema derived from the accepted runtime program.
_VFX_RUNTIME_VOCABULARY_KEYS = (
    "schema", "rendererKind", "rendererRequirements", "rendererSemantics",
    "colorPolicy", "heldRootVisibility", "soundId", "backend", "textureRole", "particleRole", "anchor", "channel",
    "lane", "emissionMode", "blend", "layer", "particleSystemId",
    "visualBudgetClass", "numericRanges", "textureDependencyTuples", "maxSlots",
)
VFX_PROMPT_STATIC_KEYS = ("schema", "rules", "runtimeVocabulary")
VFX_REPAIR_PROMPT_STATIC_KEYS = ("task", "rules", "runtimeVocabularyReadOnly")
_ACCEPTED_GAMEPLAY_CONTEXT_RULE = (
    "acceptedGameplayReadOnly, when present, is the exact accepted gameplay, not an edit target. "
    "useTime/useAnimation are base item cadence/animation in world ticks (60/s); itemScale is the "
    "held-root dimensionless multiplier, not a VFX slot scale or PNG frame size. Do not infer "
    "missing values, live attack-speed modifiers or event frequency from names/prose. "
    "runtimePairs owns event availability; acceptedRuntimeProgramReadOnly owns exact bindings/events."
)


@dataclass(frozen=True)
class MalformedVfxDirectorOutput:
    raw_text: str
    error: str


_RENDERERS = (
    "projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail",
    "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes",
    "actorAfterimage", "impactRing", "impactSprite", "childMotes",
    "lightCue", "soundCue", "screenShakeCue", "libraryParticle", *MATERIAL_RENDERERS,
)
SPRITE_TEXTURE_RENDERERS = frozenset({
    "projectileAfterimage", "spriteStampTrail", "actorAfterimage", "impactSprite",
})
# Existing runtime invariants, shared by the model-facing surface/schema and
# semantic diagnostics. These constrain authored fields; they never fill them.
_RENDERER_REQUIREMENTS = {
    "lightCue": {"channel": "light", "lane": "cue"},
    "soundCue": {"channel": "sound", "lane": "cue"},
    "libraryParticle": {**NEUTRAL_FIELDS, "backend": "Particle"},
    "screenShakeCue": {**NEUTRAL_FIELDS, "backend": "Realtime", "channel": "screenShake", "lane": "cue", "duration": 3, "repeatEvery": 0, "alpha": 1, "blend": "alpha", "layer": "BeforeProjectiles"},
    "impactSprite": {"textureRole": "impact"},
    "spriteElement": {**NEUTRAL_FIELDS, "backend": "Sprite"},
    "texturedPath": {**NEUTRAL_FIELDS, "backend": "Primitive", "repeatEvery": 0, "duration": 3},
}
_RENDERER_SEMANTICS = {
    "libraryParticle": "Real ParticleLibrary V3 instanced Star particles, not the legacy pl:* Terraria Dust selectors. Explicit particle controls choose count, motion, dimensions, spin, color and lifetime fade; world-only attachment captures event-time pose. duration is individual lifetime; event startTick is delay/repeatEvery=0, periodic repeatEvery>=1 and item startTick=0. Velocity updates once per world tick as velocity*drag+world acceleration, then position+=velocity. Common alpha multiplies linear endOpacity once; dimensions multiply linear endScaleMultiplier. Explicit alpha/additive blend and exact before/after projectile layer remain choices. Uses existing cadence/occurrence/source budgets; disabled library suppresses this lane with no Dust fallback. No damage, gameplay child, generated PNG or inferred direction.",
    "screenShakeCue": "Explicit nonperiodic local camera cue through Luminance ScreenShakeSystem.StartShakeAtPoint, attenuated from the exact event anchor to the viewer. Six controls are mandatory in screenShake; no implicit damage/weapon-triggered shake. startTick is event-relative delay in world ticks with repeatEvery=0; the captured anchor/forward survive source retirement. duration=3 is neutral, not camera lifetime. strengthPx=0 is silence. Dissipation follows native camera visits, not simulation ticks. Each handle shares the existing instance budgets. Native Luminance/user screenshake settings remain authoritative; a disabled backend suppresses this lane without substitution. No PNG, light, sound or particles are added.",
    "projectileAfterimage": "Periodic projectile: textured history samples 2,5,... in a 20-world-tick history, using body rotation/flip. Projectile event: one fading snapshot of captured body rotation/scale/flip/gfx offset at the resolved event-time anchor; item emission is a directional texture stamp, not a player/held-pose snapshot. No fabricated history.",
    "spriteStampTrail": "Periodic projectile: spaced textured history stamps, same history consumer as projectileAfterimage. Projectile event: one captured body-pose snapshot; item emission: one directional texture stamp.",
    "actorAfterimage": "Textured afterimages of the bound entity, not a copied player animation atlas. Periodic projectile uses history; projectile event freezes body pose; item emission is a directional texture stamp.",
    "historyRibbon": "Connected center-history segments (20 world samples), fading toward the oldest point. Uses actual center history, not a relocated owner trajectory; on_spawn can start a live trail.",
    "tipTrail": "Connected captured geometric tip history: center + forward * projectile.width * projectile.scale/2. Not an image-nose/PCA guess; on_spawn can start a live trail.",
    "wavyStrip": "One animated sine wave: length 48*scale world px, amplitude 6*scale px, thickness max(1,2*scale); 8+round(16*density) segments.",
    "beamLine": "Straight decorative segment, length max(20,48*scale) world px and thickness max(1,2*scale). It does not change beam collision range; runtime_geometry ChannelBeam body separately follows its exact collision segment.",
    "fieldPulse": "Expanding fading ring: radius scale*(6+18*phase) world px, 12+round(20*density) segments, opacity multiplied by 1-phase.",
    "orbitingMotes": "2+round(6*density) square motes, each 3*scale world px, orbiting radius 18*scale px. One revolution per procedural period.",
    "ghostArc": "Rotating open 120-degree arc, radius 24*scale world px; 8+round(12*density) segments, fading from head to tail.",
    "impactRing": "Expanding fading ring: radius scale*(4+28*phase) world px, 12+round(20*density) segments. Selected Terraria particles are independent and can accompany it.",
    "impactSprite": "One dedicated generated impact PNG, lasting duration world ticks with linear fade. Requires its own spritePrompt and impact texture; no inventory/dust substitute.",
    "childMotes": "Bounded particles using the selected Terraria dust ID and existing density/spread rules. Does not spawn gameplay child entities.",
    "lightCue": "World lighting at the resolved anchor, not a drawn sprite; independent of particle selector and particle budget.",
    "soundCue": "Explicit finite Terraria.ID.SoundID sample at the resolved anchor: fresh soundCue requires an explicit soundId from the general palette. Persisted legacy absence keeps SoundID.Item1. Only soundCue may carry soundId; present null, unknown names, aliases and free paths are invalid. alpha controls volume; the existing phase-to-pitch mapping is unchanged. No sound-library/name classifier. Generated items have native Item.UseSound=null: without a soundCue slot there is no generated use sound; useStyle, parent names and damage class do not supply a fallback. Audio is a separate presentation choice: tiny visualBudgetClass and effectMagnitude do not select or mute sound. A soundCue-only slots array is valid without trails, particles, glow or a PNG; bind audio to an exact available runtime pair when intended. Empty slots remains a valid deliberately silent choice; no item is required to have sound. Repair must preserve valid silence and valid sound choices outside its explicit field permissions.",
    "spriteElement": "Owned textured elements, captured immutable dimensions/curves/color/texture identity at emission. World attachment freezes event pose; source attachment uses exact live source generation. Simulation/lifetime use world ticks, never Draw or extraUpdates. duration is individual lifetime; event startTick is delay with repeatEvery=0; periodic repeatEvery>=1, projectile startTick gates age, item startTick=0. Source retirement ends source attachment; delayed world emissions retain event pose. No gameplay or inferred image/PCA axis.",
    "texturedPath": "Projectile-only live periodic/on_spawn connected textured path: actual sampled anchor history or exact accepted collision beam/whip geometry. Physical coverage is a model choice: baked_sprite/reuse_item_icon draw a single PNG at the entity center (whip terminal point), not the full collision curve/beam. If the intended body covers that path, an explicit compatible source=whip/beam slot can coexist with a baked tip/body; runtime_geometry already draws its implemented collision geometry. Selection is not automatic and slots may remain empty for deliberately restrained/invisible presentation. startTick gates live sampling; duration=3 is neutral, repeatEvery=0. History retains at most 32 sections and ages to silence after retirement; geometry ends with source and preserves every collision corner (at most 66 sections including interpolated middle-profile knot). width is authored decorative width, never silently geometry width. Charge each segment against shared caps; skip true gaps, never fabricate/smooth trajectories. repeat UV uses cumulative distance plus world-clock scroll; stretch has no scroll. Read-only gameplay geometry, no generated shader/code.",
}


# Exact installed Terraria.ID.SoundID members, shared by schema and vocabulary.
# This general sample palette carries no weapon/entity/category routing.
_SOUND_IDS = (
    "Item1", "Item2", "Item3", "Item4", "Item8", "Item9", "Item14", "Item20", "Item21", "Item29", "Item43",
    "Dig", "Tink", "Grab", "Shatter", "Splash", "Coins", "Unlock", "MaxMana", "ResearchComplete",
)
_BACKENDS = ("Auto", "Realtime", "Primitive", "Sprite", "Particle")
_TEXTURE_ROLES = ("item", "entity", "projectile", "field", "impact", "none")
_ANCHORS = ("self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field")
_CHANNELS = ("motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound", "screenShake")
_LANES = ("primary", "support", "accent", "ornament", "cue")
_EMISSIONS = ("wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "none")
_BLENDS = ("alpha", "additive")
_LAYERS = ("BeforeProjectiles", "AfterProjectiles")
_PARTICLES = ("dust", "pl:glow", "pl:shard", "pl:smoke", "pl:spark", "none")
_BUDGET_CLASSES = ("tiny", "small", "normal", "large", "signature")

# These are annotations on the existing wire fields, not a conversion or an
# alternative semantic contract. Repair reuses the ordinary field schemas.
_VFX_NUMERIC_DESCRIPTIONS = {
    "effectMagnitude": "Engine units: Retained presentation metadata; currently no renderer consumer. Not a physical intensity or budget multiplier.",
    "rhythm": "Engine units: Retained motif metadata; currently no renderer consumer. Not beats per minute or a time unit.",
    "chaos": "Engine units: Retained motif metadata; currently no renderer consumer. Not a probability.",
    "scale": (
        "Engine units: Renderer-specific scale (1 nominal); procedural dimensions/thickness are specified in rendererSemantics. "
        "For projectileAfterimage/spriteStampTrail/actorAfterimage, R=selected renderSizePx from acceptedVisualKit; "
        "q_selected=R/max(actual final PNG frame width, height), not canvas, alpha-bbox or hitbox. "
        "item/reuse_item_icon selects root item R; a distinct baked entity selects its own R; absent R gives q_selected=1. "
        "P=projectile.scale, initial P=D*E (D=hitbox.drawScale, E=accepted entity visual scale); "
        "current P already includes growth, not another E or gameplay.itemScale. "
        "Periodic sprite trail with declared R: clamp(P,0.1,8)*scale*q_selected; absent R: max(0.05,P*scale). "
        "Projectile event body copy: clamp(P,0.1,8)*scale*q_selected, using captured P. "
        "Directional item body stamp: clamp(scale,0.05,8)*q_selected, not a held-pose copy. "
        "Dedicated impactSprite: clamp(scale,0.05,8), no main-PNG conversion. "
        "spriteElement/texturedPath use explicit world-pixel dimensions/profiles, not q_selected; common scale is neutral=1. "
        "Light strength clamp(0.22*scale,0.04,1.2) on projectile or clamp(0.2*scale,0.04,1.2) on item, then client multiplier. "
        "Dust size clamp(scale,0.2,3). Not a universal pixel size."
    ),
    "density": "Engine units: Procedural tessellation/mote count as specified in rendererSemantics. Particle count/cadence remains separate: projectile periodic repeatEvery=0 uses clamp(14-round(8*density),4,18) world ticks; projectile impactRing/childMotes count clamp(2+round(8*density),2,10), item dust count clamp(1+round(7*density),1,8), subject to client scaling and budgets. Not particles per world tick.",
    "duration": "Legacy world ticks: detached sprite and primitive lifetime with linear lifetime fade; procedural periodic animation period when repeatEvery=0. Active history trails and straight beams do not consume duration. Event rings also have their own phase fade. spriteElement: individual lifetime in world ticks, opacityProfile owns lifetime opacity (no extra linear fade). texturedPath: neutral=3, history/source owns lifetime.",
    "alpha": "Engine units: Legacy draw opacity/volume coefficient: sprite/primitive RGB and alpha are scaled together; detached effects fade over lifetime; sound volume clamp(alpha,0.05,1). Additive zeroes vertex alpha after scaling RGB. Dust color paths do not use slot alpha; not universal opacity. spriteElement and texturedPath: multiply alpha by opacityProfile once, apply tint to RGB separately, no extra implicit lifetime fade; explicit zero is silence.",
    "spread": "Engine units: Particle-speed coefficient, not angle or radians: projectile dust speed clamp(0.35+1.7*spread, 0.2, 4) plus inherited velocity; item dust velocity sampled from circular radii 1+spread. Angle is selected separately; not one common physical speed.",
    "jitter": "Engine units: Retained metadata; currently no renderer consumer. No pixel, angle, or time unit.",
    "fadeIn": "Engine units: Retained metadata; currently no renderer consumer. Not seconds, world ticks, or a lifetime fraction.",
    "fadeOut": "Engine units: Retained metadata; currently no renderer consumer. Not seconds, world ticks, or a lifetime fraction; impactSprite has its own fixed linear fade.",
    "budgetWeight": "Engine units: Retained weighting metadata; currently no renderer consumer. Does not multiply an enforced particle/draw budget.",
    "signatureWeight": "Engine units: Retained weighting metadata; currently no renderer consumer. Not an enforced budget fraction.",
    "visualCost": "Engine units: Retained cost metadata; currently no renderer consumer. Not draw calls or an enforced budget fraction.",
    "startTick": "Legacy projectile periodic only: initial particle/cue gate on per-projectile world ticks; also delays periodic procedural wave/ring/arc/orbit visibility. Active history/sprite trails and straight beams retain their existing draw timing. Legacy item periodic and detached/event lifetimes ignore startTick. spriteElement/libraryParticle: nonperiodic event-relative emission delay; periodic projectile age gate, item periodic requires 0. screenShakeCue: nonperiodic event-relative delay in world ticks, not camera lifetime. texturedPath: projectile age gate for live sampling.",
    "repeatEvery": "Legacy world ticks: positive value sets periodic particle/cue cadence and procedural animation period. 0 selects automatic particle cadence (projectile clamp(14-round(8*density),4,18), item 10) and uses duration for procedural period. Item periodic uses global ticks plus seed phase; projectile uses its state world ticks. Event particles do not repeat, but detached procedural shapes may animate within their duration. spriteElement: periodic cadence >=1 world tick, nonperiodic requires 0; overlap is literal and bounded. texturedPath: neutral=0; no repeated detached path emission.",
}


def _stage_accounting(data: dict[str, Any]) -> dict[str, int]:
    debug = data.setdefault("debug", {})
    accounting = debug.setdefault("llmStageAccounting", {})
    for key in (
        "gameplayAuthorCalls", "gameplayRepairCalls", "visualDirectorCalls",
        "visualRepairCalls", "vfxDirectorCalls", "vfxRepairCalls",
    ):
        accounting.setdefault(key, 0)
    return accounting


def _seed(*parts: Any) -> int:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def _rows(source: Mapping[str, Any], key: str) -> list[Any]:
    value = source.get(key)
    return value if isinstance(value, list) else []


def _allowed_pairs(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    inventory: list[Any] = runtime_event_inventory(data)
    for row in inventory:
        if not isinstance(row, Mapping):
            continue
        pair = (str(row.get("entityId") or ""), str(row.get("event") or ""))
        if not all(pair) or pair in seen:
            continue
        seen.add(pair)
        rows.append({"entityId": pair[0], "event": pair[1]})
    return sorted(rows, key=lambda row: (row["entityId"], row["event"]))


def _textured_path_sources(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    rows: list[dict[str, Any]] = []
    for entity in entities or []:
        if not isinstance(entity, Mapping) or not isinstance(entity.get("id"), str) or not isinstance(entity.get("kind"), str):
            continue
        kind = ENTITY_KIND_REGISTRY.get(entity["kind"])
        if kind is None or not kind.projectile:
            continue
        sources = ["anchorHistory"]
        controller, movement = entity.get("controller"), entity.get("movement")
        if isinstance(controller, Mapping) and controller.get("code") == 1:
            if controller.get("name") == "channel_beam" and type(controller["code"]) is int:
                sources.append("beam")  # Colliding gives ChannelBeam precedence over movement.
        elif isinstance(movement, Mapping) and movement.get("name") == "move_whip_lash" and type(movement.get("code")) is int and movement["code"] == 18:
            sources.append("whip")
        rows.append({"entityId": entity["id"], "sources": sources})
    return rows


def _entity_texture_sources(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram")
    raw_entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    entities = raw_entities if isinstance(raw_entities, list) else []
    rows: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, Mapping) or not isinstance(entity.get("id"), str):
            continue
        visual = entity.get("visual")
        mode = visual.get("assetMode") if isinstance(visual, Mapping) else None
        rows.append({"entityId": entity["id"], "assetMode": mode, "sources": ["item", "impact", "asset", *(["entity"] if mode in ("baked_sprite", "reuse_item_icon") else [])]})
    return rows


def vfx_director_surface(data: Mapping[str, Any]) -> dict[str, Any]:
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    return {
        "schema": VFX_DIRECTOR_SCHEMA,
        "rendererKind": list(_RENDERERS),
        "rendererRequirements": copy.deepcopy(_RENDERER_REQUIREMENTS),
        "rendererSemantics": copy.deepcopy(_RENDERER_SEMANTICS),
        "soundId": list(_SOUND_IDS),
        "heldRootVisibility": {
            field: CAPABILITY_REGISTRY["configure_item_use"].params[field].description
            for field in ("hideUseGraphic", "heldSpriteVisibilityHint")
        },
        "colorPolicy": "Explicit Visual effectColor is shared by item, projectile and detached VFX. Its absence preserves legacy color paths. Rich palette prose is not parsed into a color and motif does not override explicit effectColor.",
        "backend": list(_BACKENDS),
        "textureRole": list(_TEXTURE_ROLES),
        "particleRole": list(_TEXTURE_ROLES),
        "anchor": list(_ANCHORS),
        "channel": list(_CHANNELS),
        "lane": list(_LANES),
        "emissionMode": list(_EMISSIONS),
        "blend": list(_BLENDS),
        "layer": list(_LAYERS),
        "particleSystemId": list(_PARTICLES),
        "visualBudgetClass": list(_BUDGET_CLASSES),
        "numericRanges": {
            "effectMagnitude": [0.0, 1.0], "scale": [0.15, 5.0],
            "density": [0.0, 1.0], "duration": [3, 120], "alpha": [0.0, 1.0],
            "spread": [0.0, 2.0], "jitter": [0.0, 1.5], "fadeIn": [0.0, 0.8],
            "fadeOut": [0.0, 0.8], "budgetWeight": [0.1, 4.0],
            "signatureWeight": [0.0, 1.0], "visualCost": [0.0, 1.0],
            "startTick": [0, 120], "repeatEvery": [0, 120],
        },
        "texturedPathSources": _textured_path_sources(data),
        "textureDependencyTuples": {
            "item": "existing accepted item image; assetId empty",
            "entity": "same exact entity baked_sprite/reuse_item_icon image; assetId empty; no_asset/runtime_geometry forbidden; legacy projectile/field aliases require exact bound visualRole and the same mode requirement",
            "impact": "same-entity impactSprite slot must produce the dedicated impact image; assetId empty",
            "asset": "exact declared VFX asset ID; no compensating artwork for a bad reference",
        },
        "entityTextureSources": _entity_texture_sources(data),
        "maxSlots": max(0, min(12, int(VFX_LLM_DIRECTOR_MAX_SLOTS))),
        "runtimePairs": _allowed_pairs(data),
        "runtimeVisualRoles": runtime_visual_roles(data),
    }


def _impact_sprite_background_rule() -> str:
    from infini_local.pipelines.sprite_contracts import sprite_background_positive_clause

    return (
        "The final impact PNG has a transparent background; describe the raw image "
        + sprite_background_positive_clause()
        + ". Local postprocess owns final alpha; do not confuse raw background with final transparency."
    )


def _director_schema(data: Mapping[str, Any], *, require_sound_selection: bool = True) -> dict[str, Any]:
    pairs = _allowed_pairs(data)
    entity_ids = sorted({row["entityId"] for row in pairs})
    events = sorted({row["event"] for row in pairs})
    slot: dict[str, Any] = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
            "entityId": {"type": "string", "enum": entity_ids},
            "event": {"type": "string", "enum": events},
            "rendererKind": {
                "type": "string", "enum": list(_RENDERERS),
                "description": "Select the renderer with the companion fields required by this slot's conditional clauses. lightCue emits world lighting, not a drawn glow sprite or trail. Sound/light cues use lane=cue, not a visual emphasis lane.",
            },
            "backend": {"type": "string", "enum": list(_BACKENDS), "description": "Legacy retained implementation hint; rendererKind selects the implemented Dust/FNA path. Installing ParticleLibrary does not redirect slots. Auto is sufficient for legacy renderers. spriteElement requires Sprite; texturedPath requires Primitive, both use owned stock FNA paths."},
            "textureRole": {
                "type": "string", "enum": list(_TEXTURE_ROLES),
                "description": (
                    "Legacy PNG selector for " + ", ".join(renderer for renderer in _RENDERERS if renderer in SPRITE_TEXTURE_RENDERERS) + ": "
                    "item=accepted item PNG; entity=bound entity baked_sprite/reuse_item_icon PNG "
                    "(no_asset/runtime_geometry cannot supply one); projectile/field alias entity only when equal to bound visualRole, "
                    "with the same mode requirement; impact=same-entity impactSprite producer "
                    "(required companion slot for other sprite renderers); none invalid for sprites. "
                    "Primitive/Dust/cue renderer hints require no PNG. spriteElement and texturedPath require none here "
                    "and consume only their explicit nested texture selector and textureDependencyTuples."
                ),
            },
            "particleRole": {"type": "string", "enum": list(_TEXTURE_ROLES)},
            "anchor": {"type": "string", "enum": list(_ANCHORS), "description": "Primitive/cue/event placement: self/field=bound entity center; owner=active owner center; tip/tipHistory=projectile geometric tip (item uses engine itemLocation); velocity=center with motion axis; hitPoint=captured event point, NPC center for item hit/crit. Item hitPoint without a captured point is silent. Projectile event anchors and sprite pose are frozen at emission and carried through the relay, including after source removal; unavailable owner is silent. History renderers use their named center/tip histories instead of relocating the path."},
            "channel": {"type": "string", "enum": list(_CHANNELS)},
            "lane": {"type": "string", "enum": list(_LANES)},
            "emissionMode": {"type": "string", "enum": list(_EMISSIONS)},
            "blend": {"type": "string", "enum": list(_BLENDS)},
            "layer": {"type": "string", "enum": list(_LAYERS)},
            "particleSystemId": {"type": "string", "enum": list(_PARTICLES), "description": "Exact Terraria dust selectors, not ParticleLibrary instances: dust=GemDiamond, pl:glow=TintableDustLighted, pl:shard=Glass, pl:smoke=Smoke, pl:spark=Electric. none suppresses particles, not independently selected primitive/sprite/light/sound rendering."},
            "scale": {"type": "number", "minimum": 0.15, "maximum": 5.0},
            "density": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "duration": {"type": "integer", "minimum": 3, "maximum": 120},
            "alpha": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "spread": {"type": "number", "minimum": 0.0, "maximum": 2.0},
            "jitter": {"type": "number", "minimum": 0.0, "maximum": 1.5},
            "fadeIn": {"type": "number", "minimum": 0.0, "maximum": 0.8},
            "fadeOut": {"type": "number", "minimum": 0.0, "maximum": 0.8},
            "budgetWeight": {"type": "number", "minimum": 0.1, "maximum": 4.0},
            "signatureWeight": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "visualCost": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "startTick": {"type": "integer", "minimum": 0, "maximum": 120},
            "repeatEvery": {"type": "integer", "minimum": 0, "maximum": 120},
            "spritePrompt": {"type": "string", "maxLength": 1400, "description": _impact_sprite_background_rule()},
            "spriteNegativePrompt": {"type": "string", "maxLength": 700},
            "element": element_schema(),
            "path": path_schema(),
            "screenShake": screen_shake_schema(),
            "particle": library_particle_schema(),
            "soundId": {"type": "string", "enum": list(_SOUND_IDS), "description": "Exact Terraria.ID.SoundID member, selected independently of entity kind, item name, useStyle or damage class. General sample palette, no weapon presets. Only soundCue may carry it; fresh soundCue requires an explicit selection. Persisted legacy absence keeps SoundID.Item1, never an unknown/null replacement."},
        },
        "required": [
            "id", "entityId", "event", "rendererKind", "backend", "textureRole",
            "particleRole", "anchor", "channel", "lane", "emissionMode", "blend",
            "layer", "particleSystemId", "scale", "density", "duration", "alpha", "spread",
            "jitter", "fadeIn", "fadeOut", "budgetWeight", "signatureWeight",
            "visualCost", "startTick", "repeatEvery", "spritePrompt", "spriteNegativePrompt",
        ],
    }
    slot["allOf"] = [
        {
            "if": {"properties": {"rendererKind": {"const": renderer}}, "required": ["rendererKind"]},
            "then": {"properties": {field: {"const": value} for field, value in required.items()}},
        }
        for renderer, required in _RENDERER_REQUIREMENTS.items()
    ]
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    item_ids = [row["id"] for row in entities or [] if isinstance(row, Mapping) and row.get("kind") == "item_body" and isinstance(row.get("id"), str)]
    slot["allOf"].extend(material_slot_clauses(item_ids, [r for r in _RENDERERS if r not in MATERIAL_RENDERERS], events, list(_CHANNELS), _textured_path_sources(data)))
    slot["allOf"].extend(material_texture_clauses(_entity_texture_sources(data)))
    # Fresh model output must choose explicitly; persisted legacy soundCue
    # absence is compatibility-only and is never materialized in Python.
    if require_sound_selection:
        slot["allOf"].append({
            "if": {"properties": {"rendererKind": {"const": "soundCue"}}, "required": ["rendererKind"]},
            "then": {"required": ["soundId"]},
        })
    slot["allOf"].append({
        "if": {"properties": {"rendererKind": {"enum": [renderer for renderer in _RENDERERS if renderer != "soundCue"]}}, "required": ["rendererKind"]},
        "then": {"properties": {"soundId": {"enum": []}}},
    })
    slot["allOf"].extend([
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}}, "required": ["rendererKind"]},
         "then": {"required": ["particle"], "properties": {"channel": {"enum": ["ambientParticles", "impactParticles", "decaySmoke"]}, "lane": {"enum": ["primary", "support", "accent", "ornament"]}}}},
        {"if": {"properties": {"rendererKind": {"enum": [renderer for renderer in _RENDERERS if renderer != "libraryParticle"]}}, "required": ["rendererKind"]},
         "then": {"properties": {"particle": {"enum": []}}}},
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}, "event": {"const": "periodic"}}, "required": ["rendererKind", "event"]},
         "then": {"properties": {"repeatEvery": {"minimum": 1}}}},
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}, "event": {"enum": [event for event in events if event != "periodic"]}}, "required": ["rendererKind", "event"]},
         "then": {"properties": {"repeatEvery": {"const": 0}}}},
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, "required": ["rendererKind", "event", "entityId"]},
         "then": {"properties": {"startTick": {"const": 0}}}},
        {"if": {"properties": {"rendererKind": {"const": "screenShakeCue"}}, "required": ["rendererKind"]},
         "then": {"required": ["screenShake"], "properties": {"event": {"enum": [event for event in events if event != "periodic"]}}}},
        {"if": {"properties": {"rendererKind": {"enum": [renderer for renderer in _RENDERERS if renderer != "screenShakeCue"]}}, "required": ["rendererKind"]},
         "then": {"properties": {"screenShake": {"enum": []}, "channel": {"enum": [channel for channel in _CHANNELS if channel != "screenShake"]}}}},
    ])
    schema: dict[str, Any] = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_DIRECTOR_SCHEMA},
            "effectMagnitude": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "visualBudgetClass": {"type": "string", "enum": list(_BUDGET_CLASSES)},
            "motif": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "element": {"type": "string", "minLength": 1, "maxLength": 48},
                    "shapeLanguage": {"type": "string", "minLength": 1, "maxLength": 96},
                    "motionLanguage": {"type": "string", "minLength": 1, "maxLength": 96},
                    "paletteRole": {"type": "string", "minLength": 1, "maxLength": 48},
                    "rhythm": {"type": "number", "minimum": 0.2, "maximum": 3.0},
                    "chaos": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["element", "shapeLanguage", "motionLanguage", "paletteRole", "rhythm", "chaos"],
            },
            "slots": {"type": "array", "items": slot, "minItems": 0, "maxItems": max(0, min(12, int(VFX_LLM_DIRECTOR_MAX_SLOTS)))},
            "assets": {"type": "array", "items": asset_schema(), "maxItems": 4, "description": "Optional independent VFX ingredients, declared once and reused by exact ID. Absence requests none; null invalid. Every new request must be used. Image pipeline alone writes execution metadata."},
        },
        "required": ["schema", "effectMagnitude", "visualBudgetClass", "motif", "slots"],
    }
    properties = schema["properties"]
    properties["effectMagnitude"]["description"] = _VFX_NUMERIC_DESCRIPTIONS["effectMagnitude"]
    for field in ("rhythm", "chaos"):
        properties["motif"]["properties"][field]["description"] = _VFX_NUMERIC_DESCRIPTIONS[field]
    for field in slot["properties"]:
        if field in _VFX_NUMERIC_DESCRIPTIONS:
            slot["properties"][field]["description"] = _VFX_NUMERIC_DESCRIPTIONS[field]
    return schema


def _number(value: Any, low: float, high: float, path: str, errors: list[dict[str, Any]], *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append({"path": path, "message": "number required"})
        return int(low) if integer else low
    try:
        numeric = float(value)
    except OverflowError:
        errors.append({"path": path, "message": "finite number required"})
        return int(low) if integer else low
    if not math.isfinite(numeric):
        errors.append({"path": path, "message": "finite number required"})
        return int(low) if integer else low
    if numeric < low or numeric > high:
        errors.append({"path": path, "message": f"must be within [{low}, {high}]"})
    return int(value) if integer else numeric


def vfx_png_dependencies(
    data: Mapping[str, Any], manifest: Mapping[str, Any] | None = None, *, require_used: bool = False,
) -> dict[str, Any]:
    """Read-only projection of the PNG producers actually consumed by slots.

    Producer roles name the existing image owners, not another asset registry or
    request. Primitive, Dust and cue renderers consume no PNG, regardless of the
    legacy hint. Admission checks selectors; delivery checks these exact owners'
    execution results. No mode, reference, image request or saved wire is changed.
    """
    if manifest is None:
        raw = data.get("vfxManifest")
        manifest = raw if isinstance(raw, Mapping) else {}
    errors: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    assets = _rows(manifest, "assets")
    known: set[str] = set()
    for index, row in enumerate(assets):
        asset_id = row.get("id") if isinstance(row, Mapping) else None
        if not isinstance(asset_id, str) or re.fullmatch(ASSET_ID_PATTERN, asset_id) is None:
            continue  # Shape/format gates precede lookup; never hash hostile JSON.
        if asset_id in known:
            errors.append({"path": f"$.assets[{index}].id", "message": "duplicate asset id"})
        known.add(asset_id)
    runtime = data.get("runtimeProgram")
    entities = {row["id"]: row for row in _rows(runtime, "entities")
                if isinstance(row, Mapping) and isinstance(row.get("id"), str)} if isinstance(runtime, Mapping) else {}
    slots = _rows(manifest, "slots")
    impacts = {slot["entityId"] for slot in slots if isinstance(slot, Mapping)
               and slot.get("rendererKind") == "impactSprite" and isinstance(slot.get("entityId"), str)}
    used: set[str] = set()
    dangling = False
    for index, slot in enumerate(slots):
        if not isinstance(slot, Mapping):
            continue
        renderer = slot.get("rendererKind")
        if not isinstance(renderer, str):
            continue
        selector = f"$.slots[{index}].textureRole"
        asset_id = ""
        if renderer in MATERIAL_RENDERERS:
            name = "element" if renderer == "spriteElement" else "path"
            payload = slot.get(name)
            texture = payload.get("texture") if isinstance(payload, Mapping) else None
            if not isinstance(texture, Mapping):
                continue
            source = texture.get("source")
            asset_id = texture.get("assetId")
            selector = f"$.slots[{index}].{name}.texture.source"
        elif renderer in SPRITE_TEXTURE_RENDERERS:
            source = slot.get("textureRole")
            if not isinstance(source, str) or source not in _TEXTURE_ROLES:
                errors.append({"path": selector, "message": "exact legacy textureRole enum required"})
                continue
        else:
            continue
        if not isinstance(source, str):
            continue  # Scalar enum/type diagnostics belong to the shape gate.
        entity_id = slot.get("entityId")
        if not isinstance(entity_id, str):
            continue
        if entity_id not in entities and source in ("entity", "projectile", "field", "impact"):
            # Pair validation owns the unresolved entity; it cannot diagnose
            # that entity's mode, alias or impact producer. Independent item/
            # asset references still resolve below, including asset usage.
            continue
        entity = entities.get(entity_id, {})
        raw_visual = entity.get("visual")
        entity_visual = raw_visual if isinstance(raw_visual, Mapping) else {}
        mode = entity_visual.get("assetMode")
        role = ""
        if source == "asset" and renderer in MATERIAL_RENDERERS:
            if not isinstance(asset_id, str) or re.fullmatch(ASSET_ID_PATTERN, asset_id) is None or asset_id not in known:
                dangling = True
                errors.append({"path": selector.removesuffix("source") + "assetId", "message": "exact declared VFX asset id required; repair the reference, never create compensating artwork"})
                # Preserve empty-domain Repair: both selector leaves are broken,
                # never permission to invent a request or redesign valid assets.
                if not known:
                    errors.append({"path": selector, "message": "asset texture source requires a declared VFX asset; repair the reference, never create compensating artwork"})
                continue
            used.add(asset_id)
            role = "vfx:" + asset_id
        elif source == "item":
            role = "item"
        elif source == "impact":
            if entity_id not in impacts:
                errors.append({"path": selector, "message": "impact texture requires a same-entity impactSprite image producer"})
                continue
            role = "impact:" + entity_id
        elif source in ("entity", "projectile", "field"):
            if source != "entity" and source != entity.get("visualRole"):
                errors.append({"path": selector, "message": "textureRole must match the exact bound entity visualRole"})
                continue
            if mode not in ("baked_sprite", "reuse_item_icon"):
                errors.append({"path": selector, "message": "entity texture requires the exact entity baked_sprite/reuse_item_icon producer; no_asset/runtime_geometry provide no PNG"})
                continue
            role = "item" if mode == "reuse_item_icon" or entity.get("kind") == "item_body" else "entity:" + entity_id
        elif source == "none" and renderer in SPRITE_TEXTURE_RENDERERS:
            errors.append({"path": selector, "message": "sprite renderer requires a non-none textureRole"})
            continue
        else:
            continue  # Unsupported enum values already have exact shape errors.
        if source == "asset":
            producer = next(row for row in assets if isinstance(row, Mapping) and row.get("id") == asset_id)
        elif source == "item" or (source in ("entity", "projectile", "field") and mode == "reuse_item_icon"):
            raw_visual = data.get("visual")
            producer = raw_visual if isinstance(raw_visual, Mapping) else {}
        else:
            producer = entity_visual
        prefix = "impactSprite" if source == "impact" else "sprite"
        dependencies.append({"slotId": slot.get("id"), "entityId": entity_id,
                             "source": source, "role": role, "selectorPath": selector,
                             "spritePath": producer.get(prefix + "Path"), "spriteStatus": producer.get(prefix + "Status")})
    # A dangling selector is not permission to delete/redesign a valid request.
    if require_used and not dangling:
        for index, row in enumerate(assets):
            if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] in known - used:
                errors.append({"path": f"$.assets[{index}].id", "message": "unused new asset request"})
    return {"dependencies": dependencies, "errors": errors}


def _material_slot_errors(slot: Mapping[str, Any], path: str) -> list[dict[str, Any]]:
    relations = {
        "spriteElement": ("element", element_schema, "speedMinPxPerTick", "speedMaxPxPerTick", False),
        "libraryParticle": ("particle", library_particle_schema, "speedMinPxPerTick", "speedMaxPxPerTick", False),
        "screenShakeCue": ("screenShake", screen_shake_schema, "taperStartDistancePx", "taperEndDistancePx", True),
    }
    relation = relations.get(str(slot.get("rendererKind") or ""))
    if relation is None:
        return []
    payload_name, schema_factory, low_name, high_name, strictly_greater = relation
    payload = slot.get(payload_name)
    if not isinstance(payload, Mapping):
        return []
    minimum, maximum = payload.get(low_name), payload.get(high_name)
    properties = schema_factory()["properties"]
    # A scalar failure is not permission to redesign its valid sibling. Compare
    # each operand through its canonical field gate, independently of other leaves.
    if (isinstance(minimum, (int, float)) and isinstance(maximum, (int, float))
            and not strict_schema_errors(minimum, properties[low_name])
            and not strict_schema_errors(maximum, properties[high_name])
            and (maximum < minimum or (strictly_greater and maximum == minimum))):
        operator = ">" if strictly_greater else ">="
        return [{"path": f"{path}.{payload_name}.{high_name}", "message": f"must be {operator} {low_name}"}]
    return []


def validate_vfx_director_output(raw: Any, data: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if isinstance(raw, MalformedVfxDirectorOutput):
        return {"ok": False, "errors": [{"path": "$", "message": f"malformed_json: {raw.error}"}]}
    if not isinstance(raw, Mapping):
        return {"ok": False, "errors": [{"path": "$", "message": "object required"}]}
    for schema_error in strict_schema_errors(raw, _director_schema(data)):
        errors.append({
            "path": str(schema_error.get("path") or "$"),
            "message": f"schema {schema_error.get('kind')}: expected {schema_error.get('expected')!r}",
        })
    if str(raw.get("schema") or "") != VFX_DIRECTOR_SCHEMA:
        errors.append({"path": "$.schema", "message": f"expected {VFX_DIRECTOR_SCHEMA}"})
    allowed = {(row["entityId"], row["event"]) for row in _allowed_pairs(data)}
    budget_class = str(raw.get("visualBudgetClass") or "")
    if budget_class not in _BUDGET_CLASSES:
        errors.append({"path": "$.visualBudgetClass", "message": "unsupported budget class"})
    magnitude = _number(raw.get("effectMagnitude"), 0.0, 1.0, "$.effectMagnitude", errors)
    raw_motif = raw.get("motif")
    motif = raw_motif if isinstance(raw_motif, Mapping) else {}
    if not isinstance(raw_motif, Mapping):
        errors.append({"path": "$.motif", "message": "object required"})
    motif_text: dict[str, str] = {}
    for field, maximum in {
        "element": 48,
        "shapeLanguage": 96,
        "motionLanguage": 96,
        "paletteRole": 48,
    }.items():
        value = motif.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            errors.append({"path": f"$.motif.{field}", "message": f"exact non-empty string of at most {maximum} chars required"})
        motif_text[field] = value if isinstance(value, str) else ""
    motif_rhythm = _number(motif.get("rhythm"), 0.2, 3.0, "$.motif.rhythm", errors)
    motif_chaos = _number(motif.get("chaos"), 0.0, 1.0, "$.motif.chaos", errors)
    slots = raw.get("slots")
    if not isinstance(slots, list):
        errors.append({"path": "$.slots", "message": "array required"})
        slots = []
    max_slots = max(0, min(12, int(VFX_LLM_DIRECTOR_MAX_SLOTS)))
    if len(slots) > max_slots:
        errors.append({"path": "$.slots", "message": f"at most {max_slots} slots"})
    seen_ids: set[str] = set()
    impact_sprite_entities: set[str] = set()
    normalized_slots: list[dict[str, Any]] = []
    enum_fields = {
        "rendererKind": _RENDERERS, "backend": _BACKENDS, "textureRole": _TEXTURE_ROLES,
        "particleRole": _TEXTURE_ROLES, "anchor": _ANCHORS, "channel": _CHANNELS,
        "lane": _LANES, "emissionMode": _EMISSIONS, "blend": _BLENDS,
        "layer": _LAYERS,
        "particleSystemId": _PARTICLES,
    }
    number_fields = {
        "scale": (0.15, 5.0, False), "density": (0.0, 1.0, False),
        "duration": (3, 120, True), "alpha": (0.0, 1.0, False),
        "spread": (0.0, 2.0, False), "jitter": (0.0, 1.5, False),
        "fadeIn": (0.0, 0.8, False), "fadeOut": (0.0, 0.8, False),
        "budgetWeight": (0.1, 4.0, False), "signatureWeight": (0.0, 1.0, False),
        "visualCost": (0.0, 1.0, False), "startTick": (0, 120, True),
        "repeatEvery": (0, 120, True),
    }
    for index, slot in enumerate(slots):
        path = f"$.slots[{index}]"
        if not isinstance(slot, Mapping):
            errors.append({"path": path, "message": "object required"})
            continue
        slot_id = str(slot.get("id") or "")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", slot_id) is None:
            errors.append({"path": path + ".id", "message": "exact lowercase runtime id required"})
        elif slot_id in seen_ids:
            errors.append({"path": path + ".id", "message": "duplicate id"})
        seen_ids.add(slot_id)
        entity_id = str(slot.get("entityId") or "")
        event = str(slot.get("event") or "")
        if (entity_id, event) not in allowed:
            errors.append({"path": path, "message": f"entity/event pair {(entity_id, event)!r} is absent from runtimeProgram"})
        clean: dict[str, Any] = {"id": slot_id, "entityId": entity_id, "event": event}
        for field, values in enum_fields.items():
            value = str(slot.get(field) or "")
            if value not in values:
                errors.append({"path": f"{path}.{field}", "message": f"unsupported value {value!r}"})
            clean[field] = value
        for field, (low, high, integer) in number_fields.items():
            clean[field] = _number(slot.get(field), low, high, f"{path}.{field}", errors, integer=integer)
        sprite_prompt = str(slot.get("spritePrompt") or "")
        sprite_negative = str(slot.get("spriteNegativePrompt") or "")
        if clean["rendererKind"] == "impactSprite":
            if not sprite_prompt.strip():
                errors.append({"path": path + ".spritePrompt", "message": "impactSprite requires a dedicated non-empty transparent sprite prompt"})
            if clean["textureRole"] != _RENDERER_REQUIREMENTS["impactSprite"]["textureRole"]:
                errors.append({"path": path + ".textureRole", "message": "impactSprite requires textureRole=impact"})
            if entity_id in impact_sprite_entities:
                errors.append({"path": path + ".entityId", "message": "runtime wire supports at most one impactSprite asset per entity"})
            impact_sprite_entities.add(entity_id)
        else:
            for field, value in (("spritePrompt", sprite_prompt), ("spriteNegativePrompt", sprite_negative)):
                if value:
                    errors.append({"path": f"{path}.{field}", "message": "sprite prompts are owned only by impactSprite slots and must be empty otherwise"})
        clean["spritePrompt"] = sprite_prompt
        clean["spriteNegativePrompt"] = sprite_negative
        if "element" in slot:
            clean["element"] = copy.deepcopy(slot["element"])
        if "path" in slot:
            clean["path"] = copy.deepcopy(slot["path"])
        if "screenShake" in slot:
            clean["screenShake"] = copy.deepcopy(slot["screenShake"])
        if "particle" in slot:
            clean["particle"] = copy.deepcopy(slot["particle"])
        if "soundId" in slot:
            clean["soundId"] = slot["soundId"]
        errors.extend(_material_slot_errors(slot, path))
        for renderer in ("soundCue", "lightCue"):
            required = _RENDERER_REQUIREMENTS[renderer]
            if clean["rendererKind"] == renderer and any(clean[field] != value for field, value in required.items()):
                fields = " and ".join(f"{field}={value}" for field, value in required.items())
                errors.append({"path": path, "message": f"{renderer} requires {fields}"})
        normalized_slots.append(clean)
    errors.extend(vfx_png_dependencies(data, raw, require_used=True)["errors"])
    return {
        "ok": not errors,
        "errors": errors,
        "normalized": {
            "schema": VFX_DIRECTOR_SCHEMA,
            "effectMagnitude": float(magnitude),
            "visualBudgetClass": budget_class,
            "motif": {
                **motif_text,
                "rhythm": float(motif_rhythm),
                "chaos": float(motif_chaos),
            },
            "slots": normalized_slots,
            **({"assets": copy.deepcopy(raw["assets"])} if "assets" in raw else {}),
        },
    }


def validate_vfx_manifest_wire(data: Any) -> dict[str, Any]:
    """Shared persisted-recipe shape gate; image delivery separately owns readiness.

    Reuse Director's additive branch definitions, never strip/coerce authored
    controls or hydrate an image here. Inert legacy PNG selectors fail explicitly;
    collection IDs/pairs are checked before lookup across both renderer domains.
    """
    if not isinstance(data, Mapping) or not isinstance(data.get("vfxManifest"), Mapping):
        return {"ok": False, "errors": [{"path": "$.vfxManifest", "message": "object required"}]}
    manifest = data["vfxManifest"]
    errors: list[dict[str, Any]] = []
    if manifest.get("schema") != VFX_MANIFEST_SCHEMA:
        errors.append({"path": "$.vfxManifest.schema", "message": f"expected {VFX_MANIFEST_SCHEMA}"})
    raw_slots = manifest.get("slots")
    if not isinstance(raw_slots, list):
        errors.append({"path": "$.vfxManifest.slots", "message": "array required"})
    slots = raw_slots if isinstance(raw_slots, list) else []
    # Runtime carries technical fields instead of Director-only image captions.
    slots_schema = _director_schema(data, require_sound_selection=False)["properties"]["slots"]
    if len(slots) > slots_schema["maxItems"]:
        errors.append({"path": "$.vfxManifest.slots", "message": f"at most {slots_schema['maxItems']} slots"})
    slot_schema = slots_schema["items"]
    for field in ("spritePrompt", "spriteNegativePrompt"):
        slot_schema["properties"].pop(field)
        slot_schema["required"].remove(field)
    slot_schema["properties"].update({
        **{field: {"type": "string"} for field in ("eventGroup", "stage", "source", "bakedClipId", "bakedClipHash", "effectName")},
        "slotSeed": {"type": "integer"}, "phaseOffset": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "bakedCommandCount": {"type": "integer", "minimum": 0},
        "bakedCommands": {"type": "array", "maxItems": 0},
    })
    if "assets" in manifest:
        asset_list_schema = {"type": "array", "maxItems": 4, "items": runtime_asset_schema()}
        for error in strict_schema_errors(manifest["assets"], asset_list_schema, path="$.vfxManifest.assets"):
            errors.append({"path": error["path"], "message": f"schema {error['kind']}: expected {error.get('expected')!r}"})
    allowed = {(row["entityId"], row["event"]) for row in _allowed_pairs(data)}
    seen: set[str] = set()
    for index, slot in enumerate(slots):
        path = f"$.vfxManifest.slots[{index}]"
        if not isinstance(slot, Mapping):
            errors.append({"path": path, "message": "object required"})
            continue
        slot_id, entity_id, event = slot.get("id"), slot.get("entityId"), slot.get("event")
        if not isinstance(slot_id, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", slot_id) is None:
            errors.append({"path": path + ".id", "message": "exact lowercase runtime id required"})
        elif slot_id in seen:
            errors.append({"path": path + ".id", "message": "duplicate id"})
        else:
            seen.add(slot_id)
        if not isinstance(entity_id, str):
            errors.append({"path": path + ".entityId", "message": "string required"})
        if not isinstance(event, str):
            errors.append({"path": path + ".event", "message": "string required"})
        if isinstance(entity_id, str) and isinstance(event, str) and (entity_id, event) not in allowed:
            errors.append({"path": path, "message": "entity/event pair absent from runtimeProgram"})
        renderer = slot.get("rendererKind")
        if not isinstance(renderer, str) or renderer not in _RENDERERS:
            errors.append({"path": path + ".rendererKind", "message": "unsupported renderer"})
        if renderer in (*MATERIAL_RENDERERS, "screenShakeCue", "libraryParticle", "soundCue"):
            for error in strict_schema_errors(slot, slot_schema, path=path):
                errors.append({"path": error["path"], "message": f"schema {error['kind']}: expected {error.get('expected')!r}"})
            errors.extend(_material_slot_errors(slot, path))
        else:
            for field in ("element", "path", "screenShake", "particle", "soundId"):
                if field in slot:
                    errors.append({"path": path + "." + field, "message": "foreign payload forbidden"})
    for error in vfx_png_dependencies(data, manifest)["errors"]:
        errors.append({**error, "path": error["path"].replace("$.", "$.vfxManifest.", 1)})
    return {"ok": not errors, "errors": errors}


def _prompt_packet(data: Mapping[str, Any], parent_a: Mapping[str, Any] | None, parent_b: Mapping[str, Any] | None) -> dict[str, Any]:
    realization_raw = data.get("realization")
    realization: Mapping[str, Any] = realization_raw if isinstance(realization_raw, Mapping) else {}
    self_evaluation_raw = realization.get("selfEvaluation")
    self_evaluation: Mapping[str, Any] = self_evaluation_raw if isinstance(self_evaluation_raw, Mapping) else {}
    program_vs_report_raw = self_evaluation.get("programVsReport")
    program_vs_report: Mapping[str, Any] = program_vs_report_raw if isinstance(program_vs_report_raw, Mapping) else {}
    behavior_checks = [
        copy.deepcopy(dict(row))
        for row in program_vs_report.get("behaviorChecks") or []
        if isinstance(row, Mapping)
    ]

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
        }

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
            "behaviorChecks": behavior_checks,
        },
        "parents": [parent_packet(parent_a), parent_packet(parent_b)],
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
            "acceptedRuntimeProgramReadOnly contains the actual accepted mechanics, not another design request. Read its exact movement, controller, lifetime, collision, bindings and event parameters when composing presentation; runtimePairs still owns event availability. Do not invent missing geometry from names or the prose summary. Visual attachment and particle motion never change the source entity's gameplay.",
            "Legacy forms: choose from runtimeVocabulary.rendererSemantics. Procedural phase is fractional age/period: positive repeatEvery sets the period, otherwise duration; projectile periodic forms remain live; item periodic emits bounded detached snapshots on cadence, and event forms expire and fade over duration. Each segment/mote consumes one bounded draw call. Item events share a per-tick particle ceiling and each event has its own total; continuous item periodic does not have an infinite-lifetime total.",
            "Use only enum values and numeric ranges from runtimeVocabulary; each selected rendererKind also requires the exact companion fields in runtimeVocabulary.rendererRequirements (encoded in the slot schema).",
            "projectileAfterimage, spriteStampTrail, and actorAfterimage consume textureRole through the exact bound entity; use item for the item PNG, entity for the bound entity PNG, or its exact visualRole when they match. impactSprite instead consumes its dedicated impact texture.",
            "Legacy Sprite renderers require a non-none textureRole. Legacy primitive and particle renderers do not consume a gameplay PNG.",
            "spriteElement and texturedPath use only their explicit nested texture and runtimeVocabulary.textureDependencyTuples; textureRole=none is neutral, not a request to suppress the selected image. Respect their own timing, opacity profiles, neutral companions and read-only geometry sources in runtimeVocabulary.rendererSemantics, runtimeSurface.texturedPathSources and outputSchema. Beam/whip geometry owns placement and requires neutral anchor=self; anchorHistory keeps its authored anchor.",
            "Only rendererKind=impactSprite authors spritePrompt/spriteNegativePrompt; spritePrompt describes one dedicated impact sprite. Any other sprite renderer using textureRole=impact needs that impactSprite slot for the same entity. Primitive and particle renderers do not consume textureRole; every non-impactSprite slot returns both sprite prompt strings empty.",
            _impact_sprite_background_rule(),
            "Slots may be empty when presentation should be restrained.",
            "assets is optional: request at most four isolated texture ingredients consistent with acceptedVisualKit, declare exact safe IDs once and reuse explicitly through element.texture or path.texture. No filesystem paths/URLs or execution metadata. Never request unused art. cutout fits soft-alpha subjects; strip preserves authored frame/UV through resize without crop/recenter/rotation. Either layout can serve either new renderer; no asset-name or weapon classifier.",
            "Return only one JSON object matching outputSchema.",
        ],
    }
    return {
        **{key: packet[key] for key in VFX_PROMPT_STATIC_KEYS},
        **{key: value for key, value in packet.items() if key not in VFX_PROMPT_STATIC_KEYS},
    }


def _vfx_repair_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    return _vfx_repair_schema_from_packet({"outputSchema": _director_schema(data)})


def _build_vfx_repair_scope(raw: Any, errors: list[dict[str, Any]]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    slots = _rows(source, "slots")
    mutable_globals: set[str] = set()
    global_paths: dict[str, set[str]] = {}
    mutable_slot_ids: set[str] = set()
    slot_paths: dict[str, set[str]] = {}
    slot_deletions: dict[str, set[str]] = {}
    delete_indices: set[int] = set()
    assets = _rows(source, "assets")
    asset_paths: dict[str, set[str]] = {}
    asset_deletions: dict[str, set[str]] = {}
    duplicate_asset_indices = {
        int(match.group(1)) for error in errors
        if "duplicate asset id" in str(error.get("message") or "")
        and (match := re.match(r"^\$\.assets\[(\d+)\]\.id$", str(error.get("path") or "")))
    }
    delete_asset_ids: set[str] = set()
    delete_asset_indices: set[int] = set()
    allow_create_assets = not isinstance(raw, Mapping)
    allow_create_slots = not isinstance(raw, Mapping)
    whole_response = not isinstance(raw, Mapping)

    def grant_global(field: str, relative: str) -> None:
        mutable_globals.add(field)
        global_paths.setdefault(field, set()).add(relative.strip("."))

    def grant_slot(slot_id: str, relative: str) -> None:
        if slot_id:
            mutable_slot_ids.add(slot_id)
            slot_paths.setdefault(slot_id, set()).add(relative.strip("."))

    for error in errors:
        path = str(error.get("path") or "$")
        message = str(error.get("message") or "")
        exact_delete = message.startswith("schema additional_property:") or message == "schema enum: expected []"
        if path == "$":
            whole_response = True
        for field in ("effectMagnitude", "visualBudgetClass", "motif"):
            prefix = f"$.{field}"
            relative = json_path_relative(path, prefix)
            if relative is not None:
                grant_global(field, relative)
        match = re.match(r"^\$\.slots\[(\d+)\]", path)
        relative = json_path_relative(path, match.group(0)) if match else None
        if match and relative is not None:
            index = int(match.group(1))
            if 0 <= index < len(slots) and isinstance(slots[index], Mapping):
                slot_id = str(slots[index].get("id") or "")
                if slot_id:
                    if relative:
                        grant_slot(slot_id, relative)
                        if exact_delete:
                            slot_deletions.setdefault(slot_id, set()).add(relative)
                    elif "entity/event pair" in message:
                        # Root-level semantic error, but only the exact pair is
                        # broken. Keep timing, style and already-valid cue data
                        # frozen while allowing the model to retarget the slot.
                        grant_slot(slot_id, "entityId")
                        grant_slot(slot_id, "event")
                    elif "requires channel=" in message and "lane=cue" in message:
                        grant_slot(slot_id, "channel")
                        grant_slot(slot_id, "lane")
                    else:
                        grant_slot(slot_id, "")
                else:
                    delete_indices.add(index)
                    allow_create_slots = True
            else:
                delete_indices.add(index)
                allow_create_slots = True
        if path == "$.slots":
            if "array required" in message or "missing" in message:
                allow_create_slots = True
            if "at most" in message:
                for index, row in enumerate(slots):
                    if isinstance(row, Mapping) and str(row.get("id") or ""):
                        grant_slot(str(row.get("id") or ""), "")
                    else:
                        delete_indices.add(index)
        asset_match = re.match(r"^\$\.assets\[(\d+)\]", path)
        relative = json_path_relative(path, asset_match.group(0)) if asset_match else None
        if asset_match and relative is not None:
            index = int(asset_match.group(1))
            row = assets[index] if 0 <= index < len(assets) else None
            asset_id = row.get("id") if isinstance(row, Mapping) else None
            if index in duplicate_asset_indices:
                delete_asset_indices.add(index)
            elif "unused new asset request" in message and isinstance(asset_id, str):
                delete_asset_ids.add(asset_id)
            elif isinstance(asset_id, str) and re.fullmatch(ASSET_ID_PATTERN, asset_id) is not None:
                asset_paths.setdefault(asset_id, set()).add(relative)
                if exact_delete:
                    asset_deletions.setdefault(asset_id, set()).add(relative)
            else:
                delete_asset_indices.add(index)
        if path == "$.assets":
            if not isinstance(source.get("assets"), list):
                allow_create_assets = True
            elif len(assets) > 4:
                delete_asset_indices.update(range(4, len(assets)))
    if whole_response:
        for field in ("effectMagnitude", "visualBudgetClass", "motif"):
            grant_global(field, "")
        allow_create_slots = True
        allow_create_assets = True
        for index, row in enumerate(assets):
            asset_id = row.get("id") if isinstance(row, Mapping) else None
            if isinstance(asset_id, str) and re.fullmatch(ASSET_ID_PATTERN, asset_id) is not None:
                asset_paths.setdefault(asset_id, set()).add("")
            else:
                delete_asset_indices.add(index)
        for index, row in enumerate(slots):
            if isinstance(row, Mapping) and str(row.get("id") or ""):
                grant_slot(str(row.get("id") or ""), "")
            else:
                delete_indices.add(index)
    return {
        "schema": "infini.vfx-repair-scope.v3",
        "mutableGlobals": sorted(mutable_globals),
        "mutableSlotIds": sorted(mutable_slot_ids),
        "deletableSlotIds": sorted(slot_id for slot_id in mutable_slot_ids if "" in slot_paths[slot_id]),
        "deletableSlotIndices": sorted(delete_indices),
        "allowCreateSlots": allow_create_slots,
        "mutableAssetIds": sorted(asset_paths),
        "deletableAssetIds": sorted(delete_asset_ids),
        "deletableAssetIndices": sorted(delete_asset_indices),
        "allowCreateAssets": allow_create_assets,
        "fieldPermissions": {
            "globals": {field: sorted(paths) for field, paths in sorted(global_paths.items())},
            "slots": [{"slotId": slot_id, "paths": sorted(paths), **({"deletePaths": sorted(slot_deletions[slot_id])} if slot_id in slot_deletions else {})} for slot_id, paths in sorted(slot_paths.items())],
            "assets": [{"assetId": asset_id, "paths": sorted(paths), **({"deletePaths": sorted(asset_deletions[asset_id])} if asset_id in asset_deletions else {})} for asset_id, paths in sorted(asset_paths.items())],
        },
        "errorPaths": [str(row.get("path") or "$") for row in errors],
    }


def _vfx_repair_context(raw: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    mutable_globals = set(str(value) for value in scope.get("mutableGlobals") or [])
    mutable_slot_ids = set(str(value) for value in scope.get("mutableSlotIds") or [])
    slots = _rows(source, "slots")
    mutable_asset_ids = set(scope.get("mutableAssetIds") or [])
    assets = _rows(source, "assets")
    return {
        "malformedRawText": raw.raw_text[:12000] if isinstance(raw, MalformedVfxDirectorOutput) else "",
        "broken": {
            "globals": {field: copy.deepcopy(source.get(field)) for field in mutable_globals},
            "slots": [copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "") in mutable_slot_ids],
            "assets": [copy.deepcopy(row) for row in assets if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] in mutable_asset_ids],
        },
        "validReadOnly": {
            "globals": {field: copy.deepcopy(source.get(field)) for field in ("effectMagnitude", "visualBudgetClass", "motif") if field not in mutable_globals},
            "slots": [copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "") not in mutable_slot_ids],
            "assets": [copy.deepcopy(row) for row in assets if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] not in mutable_asset_ids],
        },
    }


def _vfx_filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {"path": path, "reason": reason, "requested": copy.deepcopy(requested), "preserved": copy.deepcopy(preserved)}


def _vfx_repair_structure(schema: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(schema))
    out.pop("allOf", None)
    if isinstance(out.get("properties"), dict):
        out["properties"] = {name: _vfx_repair_structure(child) for name, child in out["properties"].items()}
    if isinstance(out.get("items"), Mapping):
        out["items"] = _vfx_repair_structure(out["items"])
    return out


def _filter_vfx_repair_patch(
    data: Mapping[str, Any],
    previous: Any,
    patch: Any,
    scope: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from infini_local.core.runtime_authoring import strict_schema_errors

    shape_schema = _vfx_repair_schema(data)
    # Renderer compatibility applies to the merged slot. Before frozen-first
    # filtering, an unrelated rewrite may contradict a valid frozen companion;
    # it must be ignored, not cancel an otherwise useful repair. Keep structural
    # validation here and the full renderer/schema gate after the merge.
    shape_schema["properties"]["slotsUpsert"]["items"] = _vfx_repair_structure(shape_schema["properties"]["slotsUpsert"]["items"])
    schema_errors = strict_schema_errors(patch, shape_schema)
    patch_mapping: Mapping[str, Any] = patch if isinstance(patch, Mapping) else {}
    if isinstance(patch, MalformedVfxDirectorOutput):
        schema_errors.insert(0, {
            "path": "$",
            "kind": "malformed_json",
            "expected": "strict VFX Repair JSON object",
            "actual": patch.error,
        })
    filtered: dict[str, Any] = {
        "schema": VFX_REPAIR_PATCH_SCHEMA,
        "effectMagnitude": None,
        "visualBudgetClass": None,
        "motif": None,
        "slotsUpsert": [],
        "slotIdsDelete": [],
        "slotIndicesDelete": [],
        "assetsUpsert": [],
        "assetIdsDelete": [],
        "assetIndicesDelete": [],
        "note": str(patch_mapping.get("note") or "deterministically filtered VFX Repair"),
    }
    if schema_errors:
        return filtered, {"schema": "infini.vfx-repair-filter-report.v1", "ok": False, "errors": schema_errors, "acceptedPaths": [], "ignoredChanges": []}

    source = previous if isinstance(previous, Mapping) else {}
    mutable_globals = set(str(value) for value in scope.get("mutableGlobals") or [])
    mutable_slot_ids = set(str(value) for value in scope.get("mutableSlotIds") or [])
    deletable_slot_ids = set(str(value) for value in scope.get("deletableSlotIds") or [])
    deletable_indices = set(int(value) for value in scope.get("deletableSlotIndices") or [])
    raw_permission_root = scope.get("fieldPermissions")
    permission_root = raw_permission_root if isinstance(raw_permission_root, Mapping) else {}
    raw_global_permissions = permission_root.get("globals")
    global_permissions = raw_global_permissions if isinstance(raw_global_permissions, Mapping) else {}
    slot_permissions = {
        str(row.get("slotId") or ""): tuple(str(value) for value in row.get("paths") or [])
        for row in permission_root.get("slots") or [] if isinstance(row, Mapping)
    }
    slot_delete_permissions = {str(row.get("slotId") or ""): tuple(row.get("deletePaths") or []) for row in permission_root.get("slots") or [] if isinstance(row, Mapping)}
    ignored: list[dict[str, Any]] = []
    accepted: list[str] = []

    for field in ("effectMagnitude", "visualBudgetClass", "motif"):
        candidate = patch_mapping.get(field)
        if candidate is None:
            continue
        path = f"$.{field}"
        original = source.get(field)
        if field not in mutable_globals:
            ignored.append(_vfx_filter_ignored(path, candidate, original, "valid_global_frozen"))
            continue
        if isinstance(original, Mapping) and isinstance(candidate, Mapping):
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original, candidate, mutable_paths=global_permissions.get(field) or (), audit_path=path, allow_additions=False,
            )
            filtered[field] = merged
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
        else:
            filtered[field] = copy.deepcopy(candidate)
            accepted.append(path)

    slots = _rows(source, "slots")
    for index, slot_id in enumerate(patch_mapping.get("slotIdsDelete") or []):
        path = f"$.slotIdsDelete[{index}]"
        if str(slot_id) in deletable_slot_ids:
            filtered["slotIdsDelete"].append(str(slot_id))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, slot_id, slot_id, "valid_slot_delete_ignored"))
    for index, source_index in enumerate(patch_mapping.get("slotIndicesDelete") or []):
        path = f"$.slotIndicesDelete[{index}]"
        numeric = int(source_index)
        if numeric in deletable_indices:
            filtered["slotIndicesDelete"].append(numeric)
            accepted.append(path)
        else:
            preserved = slots[numeric] if 0 <= numeric < len(slots) else None
            ignored.append(_vfx_filter_ignored(path, numeric, preserved, "valid_slot_index_delete_ignored"))

    by_id = {str(row.get("id") or ""): row for row in slots if isinstance(row, Mapping) and str(row.get("id") or "")}
    for index, candidate in enumerate(patch_mapping.get("slotsUpsert") or []):
        slot_id = str(candidate.get("id") or "")
        path = f"$.slotsUpsert[{index}]"
        original = by_id.get(slot_id)
        if original is not None:
            if slot_id not in mutable_slot_ids:
                if not json_values_equal(dict(candidate), dict(original)):
                    ignored.append(_vfx_filter_ignored(path, candidate, original, "independent_valid_slot_frozen"))
                continue
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original, candidate, mutable_paths=slot_permissions.get(slot_id, ()), audit_path=path, allow_additions=False,
                delete_paths=slot_delete_permissions.get(slot_id, ()),
            )
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
            if not json_values_equal(merged, original):
                filtered["slotsUpsert"].append(merged)
            continue
        if scope.get("allowCreateSlots"):
            filtered["slotsUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, candidate, None, "new_slot_not_required"))

    asset_permissions = {
        row["assetId"]: tuple(row.get("paths") or [])
        for row in permission_root.get("assets") or [] if isinstance(row, Mapping)
    }
    asset_delete_permissions = {row["assetId"]: tuple(row.get("deletePaths") or []) for row in permission_root.get("assets") or [] if isinstance(row, Mapping)}
    raw_assets = source.get("assets")
    assets = raw_assets if isinstance(raw_assets, list) else []
    # First occurrence owns ID-based leaf edits; later duplicates are index-only deletions.
    asset_by_id = {row["id"]: row for row in reversed(assets) if isinstance(row, Mapping) and isinstance(row.get("id"), str)}
    if "assets" in source and not isinstance(raw_assets, list) and scope.get("allowCreateAssets") and "assetsUpsert" in patch_mapping:
        accepted.append("$.assets")  # Explicit empty correction, never omission/default insertion.
    for index, asset_id in enumerate(patch_mapping.get("assetIdsDelete") or []):
        path = f"$.assetIdsDelete[{index}]"
        if asset_id in (scope.get("deletableAssetIds") or []):
            filtered["assetIdsDelete"].append(asset_id)
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, asset_id, asset_id, "valid_asset_delete_ignored"))
    for index, source_index in enumerate(patch_mapping.get("assetIndicesDelete") or []):
        path = f"$.assetIndicesDelete[{index}]"
        if source_index in (scope.get("deletableAssetIndices") or []):
            filtered["assetIndicesDelete"].append(source_index)
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, source_index, assets[source_index] if source_index < len(assets) else None, "valid_asset_index_delete_ignored"))
    for index, candidate in enumerate(patch_mapping.get("assetsUpsert") or []):
        asset_id = candidate["id"]
        path = f"$.assetsUpsert[{index}]"
        original = asset_by_id.get(asset_id)
        if original is not None:
            if asset_id not in asset_permissions:
                if not json_values_equal(candidate, original):
                    ignored.append(_vfx_filter_ignored(path, candidate, original, "independent_valid_asset_frozen"))
                continue
            permissions = asset_permissions[asset_id]
            merged, row_ignored, row_accepted = merge_frozen_subtree(original, candidate, mutable_paths=permissions, audit_path=path, allow_additions=False, delete_paths=asset_delete_permissions.get(asset_id, ()))
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
            if not json_values_equal(merged, original):
                filtered["assetsUpsert"].append(merged)
        elif scope.get("allowCreateAssets"):
            filtered["assetsUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, candidate, None, "new_asset_not_required"))
    return filtered, {
        "schema": "infini.vfx-repair-filter-report.v1",
        "ok": True,
        "errors": [],
        "acceptedPaths": sorted(set(accepted)),
        "ignoredChanges": ignored,
        "filteredPatch": copy.deepcopy(filtered),
    }


def _apply_vfx_repair_patch(
    data: Mapping[str, Any],
    previous: Any,
    patch: Any,
    scope: Mapping[str, Any],
    *,
    return_audit: bool = False,
) -> Any:
    filtered, audit = _filter_vfx_repair_patch(data, previous, patch, scope)
    if not audit.get("ok"):
        raise PlannerUnavailable("VFX Repair patch shape rejected: " + json.dumps(audit.get("errors", [])[:16], ensure_ascii=False))

    source = previous if isinstance(previous, Mapping) else {}
    out = copy.deepcopy(dict(source))
    out["schema"] = VFX_DIRECTOR_SCHEMA
    for field in ("effectMagnitude", "visualBudgetClass", "motif"):
        if filtered.get(field) is not None:
            out[field] = copy.deepcopy(filtered[field])
    if any(filtered.get(key) for key in ("slotsUpsert", "slotIdsDelete", "slotIndicesDelete")):
        slots = _rows(out, "slots")
        doomed_indices = set(filtered["slotIndicesDelete"])
        doomed_ids = set(filtered["slotIdsDelete"])
        slots = [row for index, row in enumerate(slots) if index not in doomed_indices
                 and not (isinstance(row, Mapping) and str(row.get("id") or "") in doomed_ids)]
        # Keep every untouched row (including invalid/idless rows) in its original
        # position. Omission/empty edits are no-ops, never implicit normalization.
        for row in filtered["slotsUpsert"]:
            slot_id = str(row.get("id") or "")
            index = next((i for i, old in enumerate(slots)
                          if isinstance(old, Mapping) and str(old.get("id") or "") == slot_id), None)
            if index is None:
                slots.append(copy.deepcopy(row))
            else:
                slots[index] = copy.deepcopy(row)
        out["slots"] = slots
    if any(filtered.get(key) for key in ("assetsUpsert", "assetIdsDelete", "assetIndicesDelete")) or "$.assets" in audit["acceptedPaths"]:
        raw_assets = out.get("assets")
        assets = raw_assets if isinstance(raw_assets, list) else []
        doomed_ids = set(filtered["assetIdsDelete"])
        doomed_indices = set(filtered["assetIndicesDelete"])
        assets = [row for index, row in enumerate(assets) if index not in doomed_indices and not (isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] in doomed_ids)]
        for row in filtered["assetsUpsert"]:
            index = next((i for i, old in enumerate(assets) if isinstance(old, Mapping) and old.get("id") == row["id"]), None)
            if index is None:
                assets.append(copy.deepcopy(row))
            else:
                assets[index] = copy.deepcopy(row)
        out["assets"] = assets
    return (out, audit) if return_audit else out



def _director_system(*, repair: bool = False) -> str:
    if repair:
        return (
            "You are the conditional VFX Repair. Repair only the explicit broken VFX fields. You may return a complete "
            "broken slot; deterministic merge freezes already-valid old values and ignores extra rewrites. Bind only accepted "
            "runtime entity/event pairs. Gameplay is immutable. Return strict JSON only."
        ) + generation_system_suffix()
    return (
        "You are the VFX Director. Author finite Terraria presentation only for accepted low-level runtime entity/event pairs. "
        "Gameplay is immutable. Do not infer or create weapon families. Return strict JSON only."
    ) + generation_system_suffix()


def _request(
    llm_director: Callable[..., Any],
    packet: dict[str, Any],
    *,
    repair_errors: list[dict[str, Any]] | None = None,
    previous: Any = None,
    repair_scope: Mapping[str, Any] | None = None,
) -> Any:
    messages = None
    if repair_errors is not None:
        context = _vfx_repair_context(previous, repair_scope or {})
        user = {
            "task": "Patch only exact invalid VFX fields/slots.",
            "item": copy.deepcopy(packet.get("item") or {}),
            "acceptedVisualKitReadOnly": copy.deepcopy(packet.get("acceptedVisualKit") or {}),
            **({"acceptedGameplayReadOnly": copy.deepcopy(packet["acceptedGameplayReadOnly"])} if "acceptedGameplayReadOnly" in packet else {}),
            "acceptedRuntimeProgramReadOnly": copy.deepcopy(packet.get("acceptedRuntimeProgramReadOnly") or {}),
            "runtimeVocabularyReadOnly": copy.deepcopy(packet.get("runtimeVocabulary") or {}),
            "runtimeSurfaceReadOnly": copy.deepcopy(packet.get("runtimeSurface") or {}),
            "exactErrors": copy.deepcopy(repair_errors[:24]),
            "repairScope": copy.deepcopy(dict(repair_scope or {})),
            "brokenFragments": context["broken"],
            "malformedRawText": context["malformedRawText"],
            "validGeneratedContext": context["validReadOnly"],
            "outputSchema": _vfx_repair_schema_from_packet(packet),
            "rules": [
                "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
                "already-valid fields and independent slots are frozen; extra rewrites are ignored",
                "Only exact validator-diagnosed foreign/additional leaves listed in deletePaths may be deleted by omission from an upsert; all other omissions are no-change. Delete duplicate asset rows only by diagnosed original assetIndicesDelete, never by a shared asset ID.",
                "schema and note are required; omit unchanged edit fields as no-ops, including assetsUpsert/assetIdsDelete/assetIndicesDelete. Present arrays may not be null. Valid asset prompts, layout, canvas, references and optional absence are frozen. Repair a bad reference only; never create compensating artwork.",
                "bind only exact runtimeSurfaceReadOnly.runtimePairs entityId+event pairs; runtimeVocabularyReadOnly owns the read-only enum values, numeric ranges, rendererRequirements, rendererSemantics and textureDependencyTuples",
                "presentation only; gameplay is immutable",
                _ACCEPTED_GAMEPLAY_CONTEXT_RULE,
            ],
        }
        user = {
            **{key: user[key] for key in VFX_REPAIR_PROMPT_STATIC_KEYS},
            **{key: value for key, value in user.items() if key not in VFX_REPAIR_PROMPT_STATIC_KEYS},
        }
        messages = [
            stage_chat_message("system", "vfx_repair_contract", _director_system(repair=True)),
            stage_chat_message("user", "vfx_repair_context", json.dumps(user, ensure_ascii=False, separators=(",", ":"))),
        ]
        return llm_director(
            _director_system(repair=True), user, int(VFX_LLM_DIRECTOR_MAX_TOKENS),
            float(VFX_LLM_REPAIR_TEMPERATURE), int(VFX_LLM_DIRECTOR_TIMEOUT), messages=messages,
        )
    user = copy.deepcopy(packet)
    return llm_director(
        _director_system(repair=False), user, int(VFX_LLM_DIRECTOR_MAX_TOKENS),
        float(VFX_LLM_DIRECTOR_TEMPERATURE), int(VFX_LLM_DIRECTOR_TIMEOUT), messages=messages,
    )


def _vfx_repair_schema_from_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    # The packet's full output schema already contains the exact runtime pair enums.
    full = packet.get("outputSchema") if isinstance(packet.get("outputSchema"), Mapping) else {}
    if not full:
        return {"schema": VFX_REPAIR_PATCH_SCHEMA}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_REPAIR_PATCH_SCHEMA},
            "effectMagnitude": {"anyOf": [copy.deepcopy(full["properties"]["effectMagnitude"]), {"type": "null"}]},
            "visualBudgetClass": {"anyOf": [copy.deepcopy(full["properties"]["visualBudgetClass"]), {"type": "null"}]},
            "motif": {"anyOf": [copy.deepcopy(full["properties"]["motif"]), {"type": "null"}]},
            "slotsUpsert": {"type": "array", "items": copy.deepcopy(full["properties"]["slots"]["items"]), "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIdsDelete": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": max(0, full["properties"]["slots"]["maxItems"] * 2)}, "maxItems": max(1, full["properties"]["slots"]["maxItems"] * 2)},
            "assetsUpsert": {"type": "array", "items": copy.deepcopy(full["properties"]["assets"]["items"]), "maxItems": 4},
            "assetIdsDelete": {"type": "array", "items": copy.deepcopy(full["properties"]["assets"]["items"]["properties"]["id"]), "maxItems": 4},
            "assetIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 8}, "maxItems": 8},
            "note": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["schema", "note"],
    }


def _compile_manifest(data: Mapping[str, Any], authored: Mapping[str, Any], recipe_key_value: str) -> dict[str, Any]:
    magnitude = float(authored["effectMagnitude"])
    budget_class = str(authored["visualBudgetClass"])
    slots: list[dict[str, Any]] = []
    for source in authored["slots"]:
        slot = copy.deepcopy(dict(source))
        # Director-only captions are consumed into RuntimeEntityVisualSpec below;
        # VfxSlotSpec is a fail-closed runtime DTO and must not carry them.
        slot.pop("spritePrompt", None)
        slot.pop("spriteNegativePrompt", None)
        slot.update({
            "eventGroup": "auto", "stage": "loop",
            "source": "llm_vfx_director",
            "slotSeed": _seed(recipe_key_value, slot.get("id")),
            "bakedClipId": "", "bakedClipHash": "", "bakedCommandCount": 0,
            "bakedCommands": [], "effectName": "",
        })
        slots.append(slot)
    return {
        "schema": VFX_MANIFEST_SCHEMA,
        "recipeId": str(recipe_key_value or data.get("id") or ""),
        "effectName": "runtime_entity_events",
        "inspirationNames": [],
        "playbackMode": "Realtime",
        "seed": _seed(recipe_key_value, data.get("id"), "vfx"),
        "confidence": 1.0,
        "effectMagnitude": magnitude,
        "visualBudgetClass": budget_class,
        "motif": copy.deepcopy(authored["motif"]),
        "budget": {
            "effectMagnitude": magnitude, "visualBudgetClass": budget_class,
            "emergencyCap": True,
            "maxParticlesPerTick": max(16, min(256, 32 + len(slots) * 24)),
            "maxParticlesTotal": max(256, min(12000, 1000 + len(slots) * 1200)),
            "maxDrawCalls": max(32, min(512, 64 + len(slots) * 36)),
            "spawnRateMultiplier": 1.0,
            "enableSoftGlow": True, "enablePointSparks": True,
            "enablePersistentSmoke": budget_class in {"large", "signature"},
        },
        "slots": slots,
        **({"assets": [{**copy.deepcopy(row), "spritePath": "", "spriteUrl": "", "spriteStatus": "pending", "spriteTechnicalScore": 0.0} for row in authored["assets"]]} if "assets" in authored else {}),
        "overlayPolicy": "LocalOnly",
        "debug": {
            "pattern": "runtime_entity_events", "roles": [str(row.get("visualRole") or "") for row in runtime_visual_roles(data)],
            "selectedScore": 1.0, "selectedReasons": ["exact_entity_event_binding"],
            "topCandidates": [], "wordProbe": [],
        },
    }


def _hydrate_vfx_asset_prompts(data: dict[str, Any], authored: Mapping[str, Any]) -> None:
    """Losslessly move selected VFX captions into the known entity visual DTO."""

    runtime_raw = data.get("runtimeProgram")
    runtime: Mapping[str, Any] = runtime_raw if isinstance(runtime_raw, Mapping) else {}
    by_id = {
        str(row.get("id") or ""): row
        for row in runtime.get("entities") or []
        if isinstance(row, dict) and str(row.get("id") or "")
    }
    for source in authored.get("slots") or []:
        if not isinstance(source, Mapping) or str(source.get("rendererKind") or "") != "impactSprite":
            continue
        entity = by_id.get(str(source.get("entityId") or ""))
        if not isinstance(entity, dict):
            continue
        visual = entity.setdefault("visual", {})
        visual.update({
            "impactPrompt": str(source.get("spritePrompt") or "")[:1400],
            "impactNegativePrompt": str(source.get("spriteNegativePrompt") or "")[:700],
            "impactSpritePath": "",
            "impactSpriteUrl": "",
            "impactSpriteStatus": "pending",
            "impactSpriteTechnicalScore": 0.0,
        })


def _development_manifest(data: Mapping[str, Any], recipe_key_value: str) -> dict[str, Any]:
    return _compile_manifest(data, {
        "effectMagnitude": 0.0,
        "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none", "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0},
        "slots": [],
    }, recipe_key_value)


def attach_hybrid_vfx_manifest(
    data: dict[str, Any],
    recipe_key_value: str,
    reroll_salt: Any = "",
    parent_a: dict[str, Any] | None = None,
    parent_b: dict[str, Any] | None = None,
    llm_director: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run one VFX Director call and at most one conditional VFX Repair."""
    del reroll_salt
    if llm_director is None:
        data["vfxManifest"] = _development_manifest(data, recipe_key_value)
        data.setdefault("debug", {})["vfxDirectorStatus"] = "development_inert_manifest"
        return data

    packet = _prompt_packet(data, parent_a, parent_b)
    accounting = _stage_accounting(data)
    accounting["vfxDirectorCalls"] += 1
    raw = _request(llm_director, packet)
    report = validate_vfx_director_output(raw, data)
    if not report["ok"]:
        accounting["vfxRepairCalls"] += 1
        repair_scope = _build_vfx_repair_scope(raw, report["errors"])
        patch = _request(llm_director, packet, repair_errors=report["errors"], previous=raw, repair_scope=repair_scope)
        repaired, repair_audit = _apply_vfx_repair_patch(data, raw, patch or {}, repair_scope, return_audit=True)
        report = validate_vfx_director_output(repaired, data)
        if not report["ok"]:
            raise PlannerUnavailable("VFX Repair did not produce an exact entity/event manifest: " + json.dumps(report["errors"][:16], ensure_ascii=False))
        raw = repaired
        data.setdefault("debug", {})["vfxRepairRawPatch"] = copy.deepcopy(patch)
        data["debug"]["vfxRepairPatch"] = copy.deepcopy(repair_audit.get("filteredPatch") or {})
        data["debug"]["vfxRepairFilterAudit"] = copy.deepcopy(repair_audit)
        data["debug"]["vfxRepairScope"] = copy.deepcopy(repair_scope)
    _hydrate_vfx_asset_prompts(data, report["normalized"])
    data["vfxManifest"] = _compile_manifest(data, report["normalized"], recipe_key_value)
    debug = data.setdefault("debug", {})
    debug["vfxDirectorStatus"] = "validated_and_compiled"
    debug["vfxDirectorRaw"] = copy.deepcopy(raw)
    debug["vfxRuntimePairs"] = _allowed_pairs(data)
    return data


# The former recipe/macro selector is intentionally absent from production.  A
# compact surface is retained only for diagnostics and tests.
def compact_vfx_recipe_card(recipe: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": str(recipe.get("id") or ""), "status": "retired_recipe_macro"}


def vfx_director_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    """Public generated schema owned by the VFX Director contract module."""

    return _director_schema(data)


def vfx_repair_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    """Public generated schema for the bounded VFX Repair patch."""

    return _vfx_repair_schema(data)


__all__ = [
    "VFX_DIRECTOR_SCHEMA", "VFX_REPAIR_PATCH_SCHEMA", "VFX_MANIFEST_SCHEMA", "MalformedVfxDirectorOutput", "attach_hybrid_vfx_manifest",
    "VFX_PROMPT_STATIC_KEYS", "VFX_REPAIR_PROMPT_STATIC_KEYS",
    "compact_vfx_recipe_card", "validate_vfx_director_output", "vfx_director_schema", "vfx_director_surface",
    "vfx_repair_schema", "validate_vfx_manifest_wire", "vfx_png_dependencies",
]
