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
    "soundCue", "screenShakeCue", "libraryParticle", "shape", "contour",
    *HISTORY_RENDERERS, *NATIVE_CUE_RENDERERS, "nativeEffect", *MATERIAL_RENDERERS,
)


# These controls have no executor in the selected branch. They are forbidden,
# not optional defaults, and neither validation nor compilation materializes them.
_NESTED_RENDERERS = ("spriteElement", "texturedPath", "libraryParticle", "screenShakeCue", "shape", "contour")


_RENDERER_UNUSED_FIELDS = {
    renderer: frozenset({"duration", "repeatEvery"} if renderer == "texturedPath" else ())
    | ({"duration", "repeatEvery", "alpha", "blend", "layer"} if renderer == "screenShakeCue" else set())
    for renderer in _NESTED_RENDERERS
}
_RENDERER_UNUSED_FIELDS["shape"] |= {"alpha"}
_RENDERER_UNUSED_FIELDS["contour"] |= {"alpha"}
_RENDERER_UNUSED_FIELDS["historyTrail"] = frozenset({"startTick", "duration", "repeatEvery", "alpha"})
for _renderer in (*NATIVE_CUE_RENDERERS, "nativeEffect", "soundCue"):
    _RENDERER_UNUSED_FIELDS[_renderer] = frozenset({"alpha", "duration", "blend", "layer"})


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
    "soundCue": "Explicit finite Terraria.ID.SoundID sample at the resolved anchor: soundCue requires an explicit soundId from the general palette in both Director output and persisted wire. Item1 is valid only as an explicit selection. Only soundCue may carry soundId or sound; present null, unknown names, aliases and free paths are invalid. Nonperiodic sound omits all scheduling/draw/Dust fields. Item periodic requires repeatEvery>=1 as an exact world-tick interval. Projectile periodic also requires startTick as an age gate. No automatic cadence or density-derived frequency. Every soundCue also requires sound={volume,pitch,pitchVariance}: exact final playback controls, independent of common alpha. Volume zero is deliberate silence. Pitch is absolute relative to the unpitched sample, not added to native SoundID pitch or Main.musicPitch. Variance is the full random pitch width, not a statistical variance; pitch +/- pitchVariance/2 must remain within [-1,1]. Preserve native asset/variants/weights and instance/pause policies. Missing soundId or sound is invalid and never selects a sample or derives playback controls from other controls. No sound-library/name classifier. Generated items have native Item.UseSound=null: without a soundCue slot there is no generated use sound; useStyle, parent names and damage class do not supply a fallback. Audio is a separate presentation choice, never selected or muted by visual metadata. A soundCue-only slots array is valid without trails, particles, glow or a PNG; bind audio to an exact available runtime pair when intended. Empty slots remains a valid deliberately silent choice; no item is required to have sound. Repair must preserve valid silence and valid sound choices outside its explicit field permissions.",
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


_ANCHORS = ("self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field")


_BLENDS = ("alpha", "additive")


_LAYERS = ("BeforeProjectiles", "AfterProjectiles", "BeforePlayer", "AfterPlayer")


_VFX_NUMERIC_DESCRIPTIONS = {
    "duration": "Individual detached lifetime in world ticks: shape 1..120, other duration-owning renderers 3..120. shape uses explicit lifetime endpoints without extra fade; spriteElement uses opacityProfile; libraryParticle uses endOpacity. Live path/history owns its own lifetime and omits duration.",
    "alpha": "Draw multiplier 0..1, not native reverse-alpha byte. Material/library renderers multiply their explicit opacity once. shape owns opacityStart/End instead and forbids alpha. Dust/light/sound omit this field. Additive blend keeps scaled RGB with zero vertex alpha.",
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
                      "description": "Exact central pitch relative to the unpitched sample: 0 normal, -1 down one octave, +1 up one octave. No native sample pitch, musicPitch or seed offset is added. Nonzero pitch must remain nonzero in native float32 storage."},
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
