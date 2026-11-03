"""Renderer vocabulary, shared sound contract and VFX result types. No stage calls."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Mapping

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.contours import CONTOUR_SEMANTICS
from infini_local.core.vfx.history import (
    HISTORY_RENDERERS,
    HISTORY_SEMANTICS,
    LEGACY_HISTORY_RENDERERS,
)
from infini_local.core.vfx.materials import MATERIAL_RENDERERS
from infini_local.core.vfx.native_cues import (
    NATIVE_CUE_RENDERERS,
    NATIVE_CUE_TIMING,
    NATIVE_DUST_SEMANTICS,
    NATIVE_LIGHT_SEMANTICS,
)
from infini_local.core.vfx.native_effects import NATIVE_EFFECT_SEMANTICS
from infini_local.core.vfx.shapes import (
    LEGACY_SHAPE_RENDERERS,
    SHAPE_SEMANTICS,
)

VFX_MANIFEST_SCHEMA = "infini.vfx.runtime-events.v16"


VFX_DIRECTOR_SCHEMA = "infini.vfx-director.runtime-events.v4"


VFX_REPAIR_PATCH_SCHEMA = "infini.vfx-repair-patch.runtime-events.v2"


@dataclass(frozen=True)
class MalformedVfxDirectorOutput:
    raw_text: str
    error: str


_RENDERERS = (
    "spriteStampTrail", "historyRibbon", "tipTrail",
    "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes",
    "impactRing", "impactSprite", "childMotes",
    "lightCue", "soundCue", "screenShakeCue", "libraryParticle", "shape", "contour", *HISTORY_RENDERERS, *NATIVE_CUE_RENDERERS, "nativeEffect", *MATERIAL_RENDERERS,
)


_FRESH_RENDERERS = tuple(r for r in _RENDERERS if r not in LEGACY_SHAPE_RENDERERS | LEGACY_HISTORY_RENDERERS | {"childMotes", "lightCue", "impactSprite"})


SPRITE_TEXTURE_RENDERERS = frozenset({
    "spriteStampTrail", "impactSprite",
})


# Existing runtime invariants, shared by the model-facing surface/schema and
# semantic diagnostics. These constrain authored fields; they never fill them.
_RENDERER_REQUIREMENTS = {"impactSprite": {"textureRole": "impact"}}


# These controls have no executor in the selected branch. They are forbidden,
# not optional defaults, and neither validation nor compilation materializes them.
_NESTED_RENDERERS = ("spriteElement", "texturedPath", "libraryParticle", "screenShakeCue", "shape", "contour")


_RENDERER_UNUSED_FIELDS = {
    renderer: frozenset({"scale", "density", "spread", "particleSystemId", "textureRole"})
    | ({"duration", "repeatEvery"} if renderer == "texturedPath" else set())
    | ({"duration", "repeatEvery", "alpha", "blend", "layer"} if renderer == "screenShakeCue" else set())
    for renderer in _NESTED_RENDERERS
}


_RENDERER_UNUSED_FIELDS["shape"] |= {"alpha"}


_RENDERER_UNUSED_FIELDS["contour"] |= {"alpha"}


_RENDERER_UNUSED_FIELDS["historyTrail"] = frozenset({"startTick", "duration", "repeatEvery", "scale", "density", "spread", "alpha", "particleSystemId", "textureRole"})


for _renderer in (*NATIVE_CUE_RENDERERS, "nativeEffect"):
    _RENDERER_UNUSED_FIELDS[_renderer] = frozenset({"scale", "density", "spread", "alpha", "duration", "particleSystemId", "blend", "layer", "textureRole"})


_RENDERER_UNUSED_FIELDS["soundCue"] = frozenset({
    "scale", "spread", "particleSystemId", "textureRole", "duration", "alpha", "blend", "layer",
})


_RENDERER_UNUSED_FIELDS["lightCue"] = frozenset({
    "alpha", "blend", "layer", "duration", "spread", "particleSystemId", "textureRole",
})


_RENDERER_UNUSED_FIELDS["childMotes"] = frozenset({"alpha", "blend", "layer", "duration"})


_RENDERER_UNUSED_FIELDS["impactSprite"] = frozenset({"spread", "particleSystemId"})


for _renderer in _RENDERERS:
    if _renderer not in SPRITE_TEXTURE_RENDERERS:
        _RENDERER_UNUSED_FIELDS[_renderer] = _RENDERER_UNUSED_FIELDS.get(_renderer, frozenset()) | {"textureRole"}


_CADENCE_ONLY_RENDERERS = ("soundCue", "lightCue", "impactSprite")


_COLORLESS_RENDERERS = ("nativeEffect", "soundCue", "screenShakeCue", "libraryParticle", "shape", "contour", "historyTrail", *MATERIAL_RENDERERS)


_RENDERER_SEMANTICS = {
    "shape": SHAPE_SEMANTICS,
    "contour": CONTOUR_SEMANTICS,
    "historyTrail": HISTORY_SEMANTICS,
    "nativeEffect": NATIVE_EFFECT_SEMANTICS,
    "nativeDust": NATIVE_DUST_SEMANTICS + " " + NATIVE_CUE_TIMING,
    "nativeLight": NATIVE_LIGHT_SEMANTICS + " " + NATIVE_CUE_TIMING,
    "libraryParticle": "Real ParticleLibrary V3 instanced particles using the explicit textureId from the registered native palette, separate from Terraria Dust. Star is a soft radial glow, not a star silhouette. Textures have opaque alpha; alpha blend includes black areas, while additive overlap can saturate colors toward white. Spawn controls initial positions independently of velocity spread; count is multiplicity. Explicit particle controls choose count, motion, dimensions, spin, color and lifetime fade; world-only attachment captures event-time pose. duration is individual lifetime; event startTick is delay/repeatEvery=0, periodic repeatEvery>=1 and item startTick=0. Velocity updates once per world tick as velocity*drag+world acceleration, then position+=velocity. Common alpha multiplies linear endOpacity once; dimensions multiply linear endScaleMultiplier. Explicit alpha/additive blend and exact before/after projectile layer remain choices. Uses existing cadence/occurrence/source budgets; disabled library suppresses this lane with no Dust fallback. No damage, gameplay child, generated PNG or inferred direction.",
    "screenShakeCue": "Controls: startTick is event delay, NOT shake lifetime. dissipationPxPerFrame subtracts strength per native camera visit, NOT per world tick or assumed 60 Hz frame. Explicit nonperiodic local camera cue through Luminance ScreenShakeSystem.StartShakeAtPoint, attenuated from the exact event anchor to the viewer. Six controls are mandatory in screenShake; no implicit damage/weapon-triggered shake. startTick is event-relative delay in world ticks; the captured anchor/forward survive source retirement. strengthPx=0 is silence. Dissipation follows native camera visits, not simulation ticks. Each handle shares the existing instance budgets. Native Luminance/user screenshake settings remain authoritative; a disabled backend suppresses this lane without substitution. No PNG, light, sound or particles are added.",
    "spriteStampTrail": "Periodic projectile: textured history stamps at samples 2,5,... in a 20-world-tick history, using body rotation/flip. Projectile event: one fading snapshot of captured body rotation/scale/flip/gfx offset at the resolved event-time anchor; item emission is a directional texture stamp, not a player/held-pose snapshot. No fabricated history.",
    "historyRibbon": "Controls: duration is NOT history length; active history drawing does not consume duration/startTick. Alpha is a draw multiplier (RGB and alpha together), not native reverse-byte alpha. Connected center-history segments (20 world samples), fading toward the oldest point. Uses actual center history, not a relocated owner trajectory; on_spawn can start a live trail.",
    "tipTrail": "Controls: duration is NOT history length; active history drawing does not consume duration/startTick. Connected captured geometric tip history: center + forward * projectile.width * projectile.scale/2. Not an image-nose/PCA guess; on_spawn can start a live trail.",
    "wavyStrip": "One animated sine wave: length 48*scale world px, amplitude 6*scale px, thickness max(1,2*scale); 8+round(16*density) segments.",
    "beamLine": "Controls: live straight-beam drawing ignores duration/startTick; neither is a beam range or gameplay delay. Straight decorative segment, length max(20,48*scale) world px and thickness max(1,2*scale). It does not change beam collision range; runtime_geometry ChannelBeam body separately follows its exact collision segment.",
    "fieldPulse": "Expanding fading ring: radius scale*(6+18*phase) world px, 12+round(20*density) segments, opacity multiplied by 1-phase.",
    "orbitingMotes": "2+round(6*density) square motes, each 3*scale world px, orbiting radius 18*scale px. One revolution per procedural period.",
    "ghostArc": "Rotating open 120-degree arc, radius 24*scale world px; 8+round(12*density) segments, fading from head to tail.",
    "impactRing": "Expanding fading ring: radius scale*(4+28*phase) world px, 12+round(20*density) segments. Selected Terraria particles are independent and can accompany it.",
    "impactSprite": "One dedicated generated impact PNG, lasting duration world ticks with linear fade. Requires its own spritePrompt/spriteNegativePrompt/spriteCanvasSize and impact texture; no inventory/dust substitute, particleSystemId or spread. Nonperiodic events omit startTick/repeatEvery/density. Item periodic requires only repeatEvery; projectile periodic requires startTick/repeatEvery and density only when repeatEvery=0. No Dust accompaniment is emitted by this renderer.",
    "childMotes": "Controls: spread is Dust velocity spread, NOT a cone angle; native Dust owns lifetime/opacity, so duration/alpha are forbidden. Periodic repeatEvery=0 selects automatic cadence, not no-repeat. Bounded particles using the selected Terraria dust ID and existing density/spread/cadence rules. No alpha/blend/layer/duration: native Dust owns its lifetime and drawing. Does not spawn gameplay child entities.",
    "lightCue": "World lighting from local color/scale at the resolved anchor, not a drawn sprite; no alpha/blend/layer/duration/spread/particleSystemId/textureRole. Nonperiodic events omit startTick/repeatEvery/density. Item periodic requires only repeatEvery; projectile periodic requires startTick/repeatEvery and density only when repeatEvery=0. Existing world-clock cadence is unchanged; no particle budget is spent.",
    "soundCue": "Explicit finite Terraria.ID.SoundID sample at the resolved anchor: soundCue requires an explicit soundId from the general palette in both Director output and persisted wire. Item1 is valid only as an explicit selection. Only soundCue may carry soundId or sound; present null, unknown names, aliases and free paths are invalid. Nonperiodic sound omits all scheduling/draw/Dust fields. Item periodic requires repeatEvery>=1 as an exact world-tick interval. Projectile periodic also requires startTick as an age gate. No automatic cadence or density-derived frequency. Every soundCue also requires sound={volume,pitch,pitchVariance}: exact final playback controls, independent of common alpha and phaseOffset. Volume zero is deliberate silence. Pitch is absolute relative to the unpitched sample, not added to native SoundID pitch or Main.musicPitch. Variance is the full random pitch width, not a statistical variance; pitch +/- pitchVariance/2 must remain within [-1,1]. Preserve native asset/variants/weights and instance/pause policies. Missing soundId or sound is invalid and never selects a sample or derives playback controls from alpha/phaseOffset. No sound-library/name classifier. Generated items have native Item.UseSound=null: without a soundCue slot there is no generated use sound; useStyle, parent names and damage class do not supply a fallback. Audio is a separate presentation choice, never selected or muted by visual metadata. A soundCue-only slots array is valid without trails, particles, glow or a PNG; bind audio to an exact available runtime pair when intended. Empty slots remains a valid deliberately silent choice; no item is required to have sound. Repair must preserve valid silence and valid sound choices outside its explicit field permissions.",
    "spriteElement": "Owned textured elements, captured immutable dimensions/curves/color/texture identity at emission. World attachment freezes event pose; source attachment uses exact live source generation. Simulation/lifetime use world ticks, never Draw or extraUpdates. duration is individual lifetime; event startTick is delay with repeatEvery=0; periodic repeatEvery>=1, projectile startTick gates age, item startTick=0. Source retirement ends source attachment; delayed world emissions retain event pose. No gameplay or inferred image/PCA axis.",
    "texturedPath": "Projectile-only live periodic/on_spawn connected textured path: actual sampled anchor history, exact accepted collision beam/whip geometry, or explicit source=ownerLink. ownerLink is a cosmetic straight two-point connector from explicit path.ownerAnchor to projectile.Center, available independently of movement/controller. ownerAnchor is required exactly as mountedCenter (native owner.MountedCenter, not a hand) or frontHand (native composite hand only while compositeFrontArm.enabled). A disabled/unavailable front hand refuses and retires the connector without stale-pose coasting or a center fallback. Every other path source forbids ownerAnchor. It adds no collision or damage and retires with invalid owner/source. A full inventory PNG, hidden root body or head-only projectile does not draw a connecting chain/rope: when intended, author that connector separately with ownerLink and explicit texture/width/UV controls. Physical coverage is a model choice: baked_sprite/reuse_item_icon draw a single PNG at the entity center (whip terminal point), not the full collision curve/beam. Path coverage is independent of PNG-body presentation; source=whip/beam uses that exact accepted geometry. runtime_geometry draws the explicitly selected Visual geometry: collision_path follows collision geometry, while body_segment draws its authored segment independently. Read runtimeSurface.bodyPresentation and its selected geometry before layering paths; assetMode alone does not establish collision-path coverage. Selection is not automatic and slots may remain empty for deliberately restrained/invisible presentation. startTick gates live sampling; history/source owns path lifetime. History retains at most 32 sections and ages to silence after retirement; geometry ends with source and preserves every collision corner (at most 66 sections including interpolated middle-profile knot). width is authored decorative width, never silently geometry width. Charge each segment against shared caps; skip true gaps, never fabricate/smooth trajectories. repeat UV uses cumulative distance plus world-clock scroll; stretch has no scroll. Read-only gameplay geometry, no generated shader/code.",
}


# Exact installed Terraria.ID.SoundID members, shared by schema and vocabulary.
# This general sample palette carries no weapon/entity/category routing.
_SOUND_IDS = (
    "Item1", "Item2", "Item3", "Item4", "Item5", "Item7", "Item8", "Item9",
    "Item10", "Item11", "Item12", "Item13", "Item14", "Item15", "Item17", "Item20",
    "Item21", "Item26", "Item28", "Item29", "Item31", "Item33", "Item34", "Item36",
    "Item37", "Item38", "Item40", "Item41", "Item42", "Item43", "Item44", "Item46",
    "Item51", "Item54", "Item57", "Item58", "Item60", "Item62", "Item69", "Item70",
    "Item71", "Item72", "Item73", "Item74", "Item76", "Item77", "Item78", "Item82",
    "Item83", "Item84", "Item85", "Item88", "Item89", "Item91", "Item93", "Item94",
    "Item97", "Item98", "Item99", "Item102", "Item103", "Item105", "Item106", "Item107",
    "Item108", "Item109", "Item110", "Item113", "Item117", "Item123", "Item124", "Item152",
    "Item157", "Item158", "Item169", "Coins", "Dig", "Grab", "MaxMana", "ResearchComplete",
    "Shatter", "Splash", "Tink", "Unlock",
)


_TEXTURE_ROLES = ("item", "entity", "impact", "none")


_ANCHORS = ("self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field")


_BLENDS = ("alpha", "additive")


_LAYERS = ("BeforeProjectiles", "AfterProjectiles", "BeforePlayer", "AfterPlayer")


_PARTICLES = ("GemDiamond", "TintableDustLighted", "Glass", "Smoke", "Electric", "none")


_VFX_NUMERIC_DESCRIPTIONS = {
    "scale": (
        "Engine units: Renderer-specific scale (1 nominal); procedural dimensions/thickness are specified in rendererSemantics. "
        "For spriteStampTrail, R=selected renderSizePx from acceptedVisualKit; "
        "q_selected=R/max(actual final PNG frame width, height), not canvas, alpha-bbox or hitbox. "
        "item/reuse_item_icon selects root item R; a distinct baked entity selects its own R. "
        "P=projectile.scale, initial P=D*E (D=hitbox.drawScale, E=accepted entity visual scale); "
        "current P already includes growth, not another E or gameplay.itemScale. "
        "Periodic sprite trail: clamp(P,0.1,8)*scale*q_selected. "
        "Projectile event body copy: clamp(P,0.1,8)*scale*q_selected, using captured P. "
        "Exception only for explicit move_front_hand (opcode 20) with hitboxCurve.mirrorToSprite=true or a present visualScaleCurve: "
        "Periodic sprite trail and projectile event body copy use P*scale*q_selected without clamping P. "
        "Other drivers and front-hand without either scale owner keep the formulas above. "
        "Directional item body stamp: clamp(scale,0.05,8)*q_selected, not a held-pose copy. "
        "Dedicated impactSprite: clamp(scale,0.05,8), no main-PNG conversion. "
        "spriteElement/texturedPath use explicit world-pixel dimensions/profiles, not q_selected or common scale. "
        "Light strength clamp(0.22*scale,0.04,1.2) on projectile or clamp(0.2*scale,0.04,1.2) on item, then client multiplier. "
        "Dust size clamp(scale,0.2,3). Not a universal pixel size."
    ),
    "density": "Engine units: Procedural tessellation/mote count as specified in rendererSemantics. Particle count/cadence remains separate: projectile periodic repeatEvery=0 uses clamp(14-round(8*density),4,18) world ticks; projectile impactRing/childMotes count clamp(2+round(8*density),2,10), item dust count clamp(1+round(7*density),1,8), subject to client scaling and budgets. Not particles per world tick.",
    "duration": "World ticks: detached sprite and primitive lifetime with linear lifetime fade; procedural periodic animation period when repeatEvery=0. Active history trails and straight beams do not consume duration. Event rings also have their own phase fade. spriteElement: individual lifetime in world ticks, opacityProfile owns lifetime opacity (no extra linear fade). texturedPath omits duration; history/source owns lifetime.",
    "alpha": "Dimensionless draw multiplier, range 0..1; NOT native Projectile.alpha (reverse byte 0..255) and NOT universal opacity: sprite/primitive RGB and alpha are scaled together; detached effects fade over lifetime; sound.volume alone owns audio volume and alpha does not multiply it. Additive zeroes vertex alpha after scaling RGB. Dust color paths do not use slot alpha; not universal opacity. spriteElement and texturedPath: multiply alpha by opacityProfile once, apply tint to RGB separately, no extra implicit lifetime fade; explicit zero is silence.",
    "spread": "Engine units: Particle-speed coefficient, not angle or radians: projectile dust speed clamp(0.35+1.7*spread, 0.2, 4) plus inherited velocity; item dust velocity sampled from circular radii 1+spread. Angle is selected separately; not one common physical speed.",
    "startTick": "Simple renderer projectile periodic: initial particle/cue gate on per-projectile world ticks; also delays periodic procedural wave/ring/arc/orbit visibility. Active history/sprite trails and straight beams retain their existing draw timing. Simple renderer item periodic and detached/event lifetimes ignore startTick. spriteElement/libraryParticle: nonperiodic event-relative emission delay; periodic projectile age gate, item periodic requires 0. screenShakeCue: nonperiodic event-relative delay in world ticks, not camera lifetime. texturedPath: projectile age gate for live sampling.",
    "repeatEvery": "World ticks: positive value sets periodic particle/cue cadence and procedural animation period. 0 selects automatic particle cadence (projectile clamp(14-round(8*density),4,18), item 10) and uses duration for procedural period. Item periodic uses global ticks plus seed phase; projectile uses its state world ticks. Event particles do not repeat, but detached procedural shapes may animate within their duration. spriteElement: periodic cadence >=1 world tick, nonperiodic requires 0; overlap is literal and bounded. texturedPath omits repeatEvery; no repeated detached path emission.",
}


_FRESH_VFX_NUMERIC_DESCRIPTIONS = {
    "scale": "Renderer-specific sprite size multiplier, not pixels. impactSprite multiplies its dedicated PNG size; spriteStampTrail multiplies accepted body presentation scale, not hitbox. Explicit shape/material payload dimensions are world pixels and omit common scale.",
    "density": "Only a legacy simple-slot cadence/tessellation control where required by its branch. Projectile repeatEvery=0 cadence is clamp(14-round(8*density),4,18) world ticks. New shapes and native cues forbid density and author count, geometry and cadence independently.",
    "duration": "Individual detached lifetime in world ticks: shape 1..120, other duration-owning renderers 3..120. shape uses explicit lifetime endpoints without extra fade; spriteElement uses opacityProfile; libraryParticle uses endOpacity. Live path/history owns its own lifetime and omits duration.",
    "alpha": "Draw multiplier 0..1, not native reverse-alpha byte. Material/library renderers multiply their explicit opacity once. shape owns opacityStart/End instead and forbids alpha. Dust/light/sound omit this field. Additive blend keeps scaled RGB with zero vertex alpha.",
    "spread": "Legacy simple-slot Dust-speed coefficient; fresh accompaniment is forbidden. New nativeDust uses explicit spreadRadians and independent speed bounds.",
    "startTick": "World-tick emission delay for event shape/material/library/native cues; projectile periodic age gate; item periodic requires zero for those emitters. screenShake uses event delay; texturedPath gates sampling; historyTrail instead selects actual sample ages and omits startTick.",
    "repeatEvery": "World-tick emission cadence, not shape motion or lifetime. shape/material/library/native cues require periodic>=1 and event=0. Sound periodic also requires an explicit positive interval; event sound omits scheduling fields. Paths omit it.",
}


def _rows(source: Mapping[str, Any], key: str) -> list[Any]:
    value = source.get(key)
    return value if isinstance(value, list) else []


def _sound_schema() -> dict[str, Any]:
    """One VFX-owned exact playback contract; no gameplay capability or router."""
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "volume": {"type": "number", "minimum": 0.0, "maximum": 1.0,
                       "description": "Final SoundStyle volume multiplier, independent of common alpha and native sample Volume; 0 is deliberate silence. A nonzero choice must remain nonzero in native float32 playback; sub-storage values are rejected, not silenced. Native distance and user volume settings still apply."},
            "pitch": {"type": "number", "minimum": -0.9, "maximum": 0.9,
                      "description": "Exact central pitch relative to the unpitched sample: 0 normal, -1 down one octave, +1 up one octave. No native sample pitch, musicPitch, phaseOffset or seed offset is added. Nonzero pitch must remain nonzero in native float32 storage."},
            "pitchVariance": {"type": "number", "minimum": 0.0, "maximum": 0.6,
                              "description": "Full native random pitch interval width, not statistical variance: random pitch is pitch +/- pitchVariance/2. Zero disables native pitch jitter; a nonzero interval must remain nonzero in native float32 storage. Must be <= 2*(1-abs(pitch)); only this leaf is repairable for a failed interval relation."},
        },
        "required": ["volume", "pitch", "pitchVariance"],
    }


def _native_float32(value: Any) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


def _sound_slot_errors(slot: Mapping[str, Any], path: str, *, persisted_wire: bool = False) -> list[dict[str, Any]]:
    payload = slot.get("sound")
    if slot.get("rendererKind") != "soundCue" or not isinstance(payload, Mapping):
        return []
    properties = _sound_schema()["properties"]
    if persisted_wire:
        properties = {field: {**schema, "x-nativeFloat32Bounds": True} for field, schema in properties.items()}
    errors = []
    for field, schema in properties.items():
        value = payload.get(field)
        if not strict_schema_errors(value, schema) and value != 0 and _native_float32(value) == 0:
            errors.append({"path": path + ".sound." + field,
                           "message": "A nonzero authored sound control must remain nonzero in native float32 playback; choose an explicit representable value or deliberate zero."})
    pitch, variance = payload.get("pitch"), payload.get("pitchVariance")
    if (not strict_schema_errors(pitch, properties["pitch"])
            and not strict_schema_errors(variance, properties["pitchVariance"])):
        interval_end = abs(pitch) + variance / 2
        if persisted_wire:
            # Match VfxSoundSpec's Single operands, division and addition, not a
            # double sum of saved decimals. Fresh Director/Repair stays exact.
            interval_end = _native_float32(abs(_native_float32(pitch)) + _native_float32(_native_float32(variance) / 2))
        if interval_end > 1.0:
            errors.append({"path": path + ".sound.pitchVariance", "message": "pitchVariance must be <= 2*(1-abs(pitch)); preserve valid central pitch"})
    return errors
