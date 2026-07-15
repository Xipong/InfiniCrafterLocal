from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class StrictBoundaryModel(BaseModel):
    """Strict JSON boundary only; never authors or derives gameplay."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
        populate_by_name=True,
    )


class EngineCallBoundary(StrictBoundaryModel):
    fn: str
    params: dict[str, Any] = Field(default_factory=dict)


class RuntimePlanBoundary(StrictBoundaryModel):
    resultKind: str = "generic"
    sourceRolePreservation: dict[str, str] = Field(default_factory=dict)
    engineCalls: list[EngineCallBoundary]
    runtimeStateIntent: dict[str, Any] | str = Field(default_factory=dict)
    visualIntent: dict[str, Any] = Field(default_factory=dict)
    sourceReading: str = ""
    balanceIntent: str = ""
    anomalyFlags: list[str] = Field(default_factory=list)


class BakedAssetBoundary(StrictBoundaryModel):
    mode: Literal["baked_sprite", "particle_vfx", "reuse_item_sprite", "none"]
    prompt: str = ""
    reason: str = ""
    distinctFromItem: bool | None = None


class AnimeReferenceBoundary(StrictBoundaryModel):
    strength: Literal["subtle", "strong"]
    source: str
    motifs: list[str] = Field(default_factory=list)


class VisualKitBoundary(StrictBoundaryModel):
    styleGuide: str = ""
    palette: list[str] = Field(default_factory=list)
    silhouetteSummary: str = ""
    itemSilhouetteContract: str = ""
    itemIconPrompt: str = ""
    projectileSpritePrompt: str = ""
    childSpritePrompt: str = ""
    impactSpritePrompt: str = ""
    fieldSpritePrompt: str = ""
    bakedAssets: dict[str, BakedAssetBoundary] = Field(default_factory=dict)
    vfxIntent: str = ""
    projectileVfx: str = ""
    impactVfx: str = ""
    childVfx: str = ""
    fieldVfx: str = ""
    vfxScaleHint: Literal["tiny", "small", "normal", "large", "huge"] = "normal"
    vfxRhythmHint: Literal["slow", "normal", "snappy", "delayed", "pulsing"] = "normal"
    vfxMaterialHints: list[str] = Field(default_factory=list)
    vfxAvoid: str = ""
    animationPlan: list[str] = Field(default_factory=list)
    assetDependencies: list[str] = Field(default_factory=list)
    qualityNotes: list[str] = Field(default_factory=list)
    negativePrompt: str = ""
    animeReference: AnimeReferenceBoundary | None = None

    @field_validator("palette", mode="before")
    @classmethod
    def canonicalize_palette_shape(cls, value: Any) -> Any:
        # Shape-only repair for providers that serialize a JSON string instead of
        # a one-dimensional string array. Palette semantics remain authored.
        if isinstance(value, str):
            import re
            return [part.strip() for part in re.split(r"[,;/]", value) if part.strip()]
        return value

    @field_validator("vfxMaterialHints", "animationPlan", "assetDependencies", "qualityNotes", mode="before")
    @classmethod
    def canonicalize_singleton_text_lists(cls, value: Any) -> Any:
        # OpenAI-compatible JSON modes still occasionally serialize a one-entry text
        # list as a plain string.  This is a shape-only canonicalization: no splitting,
        # guessing, or semantic repair.  Other wrong types remain strict failures.
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        return value

    @field_validator("bakedAssets")
    @classmethod
    def validate_baked_roles(cls, value: dict[str, BakedAssetBoundary]) -> dict[str, BakedAssetBoundary]:
        unknown = sorted(set(value) - {"projectile", "impact", "child", "field"})
        if unknown:
            raise ValueError(f"unknown baked asset roles: {unknown}")
        return value


class BuffEntryBoundary(StrictBoundaryModel):
    buffCode: int = 0
    buffTime: int = 0


class GeneratedBuffBoundary(StrictBoundaryModel):
    durationTicks: int = 0
    miningSpeedMultiplier: float = 1.0
    emitLightStrength: float = 0.0
    lightColorName: str = ""
    oreSenseRadiusTiles: int = 0
    movementSpeed: float = 0.0
    jumpBoost: float = 0.0
    manaRegen: int = 0
    lifeRegen: int = 0


class StateMeterBoundary(StrictBoundaryModel):
    id: str = ""
    label: str = ""
    maxValue: int = 3
    initialValue: int = 0
    gainOnUse: int = 0
    gainOnHit: int = 0
    gainOnKill: int = 0
    spendOnUse: int = 0
    spendOnAltUse: int = 0
    decayPerSecond: float = 0.0
    cooldownTicks: int = 0
    modeCount: int = 0


class TriggeredActionBoundary(StrictBoundaryModel):
    trigger: str = ""
    action: str = ""
    meterId: str = ""
    requiredValue: int = 0
    spendValue: int = 0
    cooldownTicks: int = 0
    note: str = ""


class RuntimeStateBoundary(StrictBoundaryModel):
    executionStatus: str = ""
    stateMeters: list[StateMeterBoundary] = Field(default_factory=list)
    triggeredActions: list[TriggeredActionBoundary] = Field(default_factory=list)


class RejectedEngineCallBoundary(StrictBoundaryModel):
    fn: str = ""
    reason: str = ""
    policy: str = ""
    family: str = ""
    action: str = ""


class GameplaySpecBoundary(StrictBoundaryModel):
    kind: str = 'generic'
    stage: str = 'early'
    powerBudget: float = 1.0
    damageClass: str = 'generic'
    damage: int = 0
    knockback: float = 2.0
    useTime: int = 24
    useAnimation: int = 24
    useStyle: int = 1
    autoReuse: bool = True
    consumable: bool = False
    manaCost: int = 0
    rarity: int = 0
    value: int = 100
    maxStack: int = 1
    craftYield: int = 1
    ammoFor: str = ''
    channelUse: bool = False
    consumeChancePercent: int = 100
    width: int = 24
    height: int = 24
    itemScale: float = 1.0
    useTurn: bool = False
    holdoutOffsetX: int = 0
    holdoutOffsetY: int = 0
    heldVisibility: str = ''
    releaseTiming: str = ''
    handPose: str = ''
    initialOffsetPx: int = 0
    healLife: int = 0
    healMana: int = 0
    buffCode: int = 0
    buffTime: int = 0
    extraBuffs: list[BuffEntryBoundary] = Field(default_factory=list)
    generatedBuff: GeneratedBuffBoundary = Field(default_factory=GeneratedBuffBoundary)
    pickPower: int = 0
    axePower: int = 0
    hammerPower: int = 0
    mobilityMode: str = ''
    mobilityRangeTiles: int = 0
    mobilityCooldownTicks: int = 0
    mobilitySafeTileOnly: bool = True
    miningSpeedScale: float = 1.0
    altUseMode: str = ''
    altMobilityMode: str = ''
    altMobilityRangeTiles: int = 0
    altMobilityCooldownTicks: int = 0
    altMobilitySafeTileOnly: bool = True
    altGeneratedBuff: GeneratedBuffBoundary = Field(default_factory=GeneratedBuffBoundary)
    holdGeneratedBuff: GeneratedBuffBoundary = Field(default_factory=GeneratedBuffBoundary)
    holdLightStrength: float = 0
    holdLightColorName: str = ''

    useConditionMode: str = ''
    useConditionMinLife: int = 0
    useConditionMinMana: int = 0
    runtimeState: RuntimeStateBoundary = Field(default_factory=RuntimeStateBoundary)
    rejectedEngineCalls: list[RejectedEngineCallBoundary] = Field(default_factory=list)


class EquipmentStatsBoundary(StrictBoundaryModel):
    maxLife: int = Field(default=0, ge=0, le=100)
    maxMana: int = Field(default=0, ge=0, le=100)
    lifeRegen: int = Field(default=0, ge=0, le=20)
    manaRegen: int = Field(default=0, ge=0, le=20)
    movementSpeed: float = Field(default=0, ge=0, le=1.0)
    maxRunSpeed: float = Field(default=0, ge=0, le=2.0)
    jumpSpeed: float = Field(default=0, ge=0, le=4.0)
    genericDamage: float = Field(default=0, ge=0, le=0.4)
    meleeDamage: float = Field(default=0, ge=0, le=0.4)
    rangedDamage: float = Field(default=0, ge=0, le=0.4)
    magicDamage: float = Field(default=0, ge=0, le=0.4)
    summonDamage: float = Field(default=0, ge=0, le=0.4)
    genericCrit: float = Field(default=0, ge=0, le=20)
    attackSpeed: float = Field(default=0, ge=0, le=0.4)
    knockback: float = Field(default=0, ge=0, le=2.0)
    fallDamageImmune: bool = False
    lavaImmune: bool = False
    waterWalk: bool = False
    minionSlots: int = Field(default=0, ge=0, le=2)
    sentrySlots: int = Field(default=0, ge=0, le=2)
    manaCostReduction: float = Field(default=0, ge=0, le=0.4)
    ammoSaveChance: float = Field(default=0, ge=0, le=0.5)
    aggro: int = Field(default=0, ge=-400, le=400)
    endurance: float = Field(default=0, ge=0, le=0.2)
    armorPenetration: float = Field(default=0, ge=0, le=40)
    lightStrength: float = Field(default=0, ge=0, le=1.5)
    lightColorName: str = ""


class AccessorySpecBoundary(EquipmentStatsBoundary):
    enabled: bool = False
    archetype: str = "generic"
    defense: int = Field(default=0, ge=0, le=20)


class ArmorSpecBoundary(EquipmentStatsBoundary):
    enabled: bool = False
    slot: str = "body"
    setKey: str = ""
    archetype: str = "hybrid"
    defense: int = Field(default=0, ge=0, le=80)
    whipRange: float = Field(default=0, ge=0, le=1.5)
    summonTagDamage: float = Field(default=0, ge=0, le=0.75)
    setBonusText: str = ""
    setBonusGenericDamage: float = Field(default=0, ge=0, le=0.4)
    setBonusMeleeDamage: float = Field(default=0, ge=0, le=0.4)
    setBonusRangedDamage: float = Field(default=0, ge=0, le=0.4)
    setBonusMagicDamage: float = Field(default=0, ge=0, le=0.4)
    setBonusSummonDamage: float = Field(default=0, ge=0, le=0.4)
    setBonusGenericCrit: float = Field(default=0, ge=0, le=20)
    setBonusMovementSpeed: float = Field(default=0, ge=0, le=1.0)
    setBonusLifeRegen: int = Field(default=0, ge=0, le=20)
    setBonusManaRegen: int = Field(default=0, ge=0, le=20)
    setBonusMinionSlots: int = Field(default=0, ge=0, le=2)
    setBonusSentrySlots: int = Field(default=0, ge=0, le=2)
    setBonusManaCostReduction: float = Field(default=0, ge=0, le=0.4)
    setBonusAmmoSaveChance: float = Field(default=0, ge=0, le=0.5)
    setBonusAggro: int = Field(default=0, ge=-400, le=400)
    setBonusEndurance: float = Field(default=0, ge=0, le=0.2)
    setBonusArmorPenetration: float = Field(default=0, ge=0, le=40)


class AttackSpecBoundary(StrictBoundaryModel):
    enabled: bool = False
    delivery: str = 'none'
    runtimeFamily: str = 'none'
    weaponFamily: str = ''
    projectileFamily: str = ''
    ammoKind: str = ''
    useStyleCode: int = 0
    hideUseGraphic: bool = False
    disableItemMeleeHitbox: bool = False
    ownerHitCheck: bool = False
    channelUse: bool = False
    stage: str = 'early'
    powerBudget: float = 1.0
    damageClass: str = 'generic'
    movement: str = 'straight'
    effect: str = 'dust'
    onHit: str = 'none'
    movementCode: int = 0
    effectCode: int = 0
    onHitCode: int = 0
    speed: float = 8.0
    rangeTiles: float = 35.0
    homingStrength: float = 0
    beamWidthPx: float = 14.0
    beamChargeTicks: int = 0
    chargeTicks: int = 45
    chargePowerMultiplier: float = 1.6
    delayTicks: int = 0
    lifetime: int = 90
    pierce: int = 1
    scale: float = 1.0
    projectileWidth: int = 14
    projectileHeight: int = 14
    projectileScale: float = 1.0
    hitboxScale: float = 1.0
    explosionRadius: int = 0
    impactVfxRadiusPx: int = 0
    aoeDamageRadiusPx: int = 0
    contactForgivenessPx: int = 0
    extraUpdates: int = 0
    tileCollide: bool = True
    bounceCount: int = 0
    splitCount: int = 0
    chainCount: int = 0
    pullStrength: float = 0.0
    pullMode: Literal["none", "target_to_owner", "owner_to_target", "target_to_projectile"] = "none"
    immunityCooldown: int = 10
    trailLength: int = 4
    shotCount: int = 1
    spreadRadians: float = 0
    procMode: int = 0
    runtimePlanAuthored: bool = False
    secondaryTrigger: str = 'on_hit'
    secondarySpreadRadians: float = 0.45
    secondaryDamageMultiplier: float = 0.35
    secondaryLifetimeTicks: int = 24
    sentryPlacement: str = 'grounded'
    sentryAttackIntervalTicks: int = 45
    sentryTargetRangeTiles: float = 30.0
    sentryLifetimeTicks: int = 3600
    sameTargetBias: float = 0.0
    debuffHint: str = ''
    debuffTime: int = 0
    secondaryMaterial: str = ''
    secondaryProjectileShape: str = ''
    maxChildProjectiles: int = 16
    maxChildDepth: int = 1
    dustSpawnDenom: int = 3
    burstDustCap: int = 20
    visualMode: str = 'projectile'
    trailStyle: str = 'dust'
    impactStyle: str = 'small_flash'
    primaryColorName: str = 'white'
    runtimeLightStrength: float = 0
    mobilityMode: str = ''
    mobilityRangeTiles: int = 0
    mobilityCooldownTicks: int = 0
    mobilitySafeTileOnly: bool = True
    soundPitch: float = 0
    soundVolume: float = 0.85
    soundPitchVariance: float = 0.18
    pattern: str = 'basic'
    projectileShape: str = ''
    projectileMotion: str = ''
    projectileRotation: str = ''
    projectileTrail: str = ''
    projectileImpact: str = ''
    soundCatalogSource: str = ''
    soundUseCatalogId: str = ''
    soundImpactCatalogId: str = ''
    soundUseCatalogPath: str = ''
    soundImpactCatalogPath: str = ''
    projectileSpritePath: str = ''
    projectileSpriteUrl: str = ''
    projectileSpriteStatus: str = ''
    projectileSpritePrompt: str = ''
    projectileSpriteScore: float = 0
    impactSpritePath: str = ''
    impactSpriteUrl: str = ''
    impactSpriteStatus: str = ''
    impactSpritePrompt: str = ''
    impactSpriteScore: float = 0
    childSpritePath: str = ''
    childSpriteUrl: str = ''
    childSpriteStatus: str = ''
    childSpritePrompt: str = ''
    childSpriteScore: float = 0
    fieldSpritePath: str = ''
    fieldSpriteUrl: str = ''
    fieldSpriteStatus: str = ''
    fieldSpritePrompt: str = ''
    fieldSpriteScore: float = 0
    visualAnimationPlan: str = ''
    vfxManifestJson: str = ''


class VfxMotifBoundary(StrictBoundaryModel):
    element: str = "neutral"
    shapeLanguage: str = "generic"
    motionLanguage: str = "forward"
    paletteRole: str = "primary"
    rhythm: float = 1.0
    chaos: float = 0.25


class VfxQualityBudgetBoundary(StrictBoundaryModel):
    effectMagnitude: float = 0.5
    visualBudgetClass: str = "normal"
    emergencyCap: bool = True
    maxParticlesPerTick: int = 240
    maxParticlesTotal: int = 9000
    maxDrawCalls: int = 420
    spawnRateMultiplier: float = 1.5
    enableSoftGlow: bool = True
    enablePointSparks: bool = True
    enablePersistentSmoke: bool = True


class VfxBakedCommandBoundary(StrictBoundaryModel):
    tick: int = 0
    particleSystemId: str = "dust"
    textureRole: str = ""
    localX: float = 0.0
    localY: float = 0.0
    velocityX: float = 0.0
    velocityY: float = 0.0
    startColor: str = ""
    endColor: str = ""
    scaleX: float = 1.0
    scaleY: float = 1.0
    scaleVelocityX: float = 0.0
    scaleVelocityY: float = 0.0
    rotation: float = 0.0
    rotationVelocity: float = 0.0
    lifespan: int = 18
    alpha: float = 0.65
    seedBucket: int = 0


class VfxDebugBoundary(StrictBoundaryModel):
    pattern: str = ""
    roles: list[str] = Field(default_factory=list)
    selectedScore: float = 0.0
    selectedReasons: list[str] = Field(default_factory=list)
    # Candidate ranking is diagnostic-only and never executable.
    topCandidates: list[Any] = Field(default_factory=list)
    wordProbe: list[str] = Field(default_factory=list)


class VfxSlotBoundary(StrictBoundaryModel):
    event: str = 'tick'
    effectName: str = ''
    eventGroup: str = 'auto'
    stage: str = 'loop'
    backend: str = 'Auto'
    rendererKind: str = 'projectileAfterimage'
    textureRole: str = 'projectile'
    particleRole: str = 'child'
    anchor: str = 'self'
    blend: str = 'alpha'
    layer: str = 'BeforeProjectiles'
    channel: str = 'auto'
    lane: str = 'auto'
    source: str = 'recipe'
    emissionMode: str = 'auto'
    particleSystemId: str = 'auto'
    fadeIn: float = 0.15
    fadeOut: float = 0.35
    curve: str = 'smooth'
    slotSeed: int = 0
    variant: int = 0
    startTick: int = 0
    repeatEvery: int = 0
    scale: float = 1.0
    density: float = 0.35
    duration: int = 10
    alpha: float = 0.65
    spread: float = 0.5
    jitter: float = 0.35
    phaseOffset: float = 0
    budgetWeight: float = Field(default=1.0, ge=0.05, le=8.0)
    importance: str = 'secondary'
    visualCost: float = 0.25
    signatureWeight: float = 0.45
    bakedClipId: str = ''
    bakedClipHash: str = ''
    bakedCommandCount: int = 0
    bakedCommands: list[VfxBakedCommandBoundary] = Field(default_factory=list)


class VfxManifestBoundary(StrictBoundaryModel):
    schemaName: str = Field(default="infini.vfx.hybrid.v14", alias="schema", serialization_alias="schema")
    recipeId: str = ""
    effectName: str = ""
    inspirationNames: list[str] = Field(default_factory=list)
    playbackMode: str = "Hybrid"
    seed: int = 0
    confidence: float = 0.0
    effectMagnitude: float = 0.5
    visualBudgetClass: str = "normal"
    motif: VfxMotifBoundary = Field(default_factory=VfxMotifBoundary)
    budget: VfxQualityBudgetBoundary = Field(default_factory=VfxQualityBudgetBoundary)
    slots: list[VfxSlotBoundary] = Field(default_factory=list)
    overlayPolicy: str = "LocalOnly"
    debug: VfxDebugBoundary = Field(default_factory=VfxDebugBoundary)


ATTACK_DEBUG_ONLY_FIELDS = frozenset({
    "genome", "engineMetrics", "patternSource", "runtimeAuthoringProvenance",
    "primary", "primaryAction", "mechanicClaims", "runtimeContract", "runtimeArchetype",
})
# Historical cache/replay payloads can contain two redundant top-level AttackSpec
# fields.  Damage is owned by GameplaySpec and generated-executor activation is
# owned by AttackSpec.enabled; neither field exists on the strict C# DTO.
ATTACK_LEGACY_NON_WIRE_FIELDS = frozenset({"damage", "useProjectile"})
ATTACK_NON_WIRE_FIELDS = ATTACK_DEBUG_ONLY_FIELDS | ATTACK_LEGACY_NON_WIRE_FIELDS
GAMEPLAY_DEBUG_ONLY_FIELDS = frozenset({"categoryIntent", "powerTransfer", "runtimeOutputKind", "actualAmmoMode", "unsupportedAmmoFor"})
REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS = frozenset({"index", "rawFn", "originalFn", "sourceIndex", "params"})
VFX_MANIFEST_DEBUG_ONLY_FIELDS = frozenset({"parentEffectProfile"})
VFX_BUDGET_DEBUG_ONLY_FIELDS = frozenset({"renderQuality", "quality"})
VFX_DEBUG_ONLY_FIELDS = frozenset({"composition", "effectLineage", "rerollSalt"})
_RUNTIME_PLAN_INTERNAL_KEYS = frozenset({"_normalization"})
_ENGINE_CALL_INTERNAL_KEYS = frozenset({"_index", "_rawFn", "_semanticFn"})


def _errors(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for row in exc.errors(include_url=False):
        loc = ".".join(str(x) for x in row.get("loc") or ())
        out.append(f"{loc}: {row.get('msg', 'invalid')}" if loc else str(row.get("msg") or "invalid"))
    return out


def authored_runtime_plan_view(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    out = {k: v for k, v in plan.items() if k not in _RUNTIME_PLAN_INTERNAL_KEYS}
    calls: list[dict[str, Any]] = []
    for raw in out.get("engineCalls") or []:
        if not isinstance(raw, dict):
            calls.append(raw)
            continue
        calls.append({k: v for k, v in raw.items() if k not in _ENGINE_CALL_INTERNAL_KEYS})
    out["engineCalls"] = calls
    return out


def runtime_plan_boundary_report(data_or_plan: Any) -> dict[str, Any]:
    # Lazy import avoids a package cycle: runtime_authoring.reports imports this
    # boundary module while runtime_authoring.__init__ imports reports.
    from infini_local.core.runtime_authoring.engine_call_contracts import validate_engine_call_params
    from infini_local.core.runtime_authoring.schema import ENGINE_FN_CATALOG_V2

    plan = data_or_plan.get("runtimePlan") if isinstance(data_or_plan, dict) and "runtimePlan" in data_or_plan else data_or_plan
    plan = authored_runtime_plan_view(plan)
    try:
        parsed = RuntimePlanBoundary.model_validate(plan)
    except ValidationError as exc:
        return {"ok": False, "errors": _errors(exc), "unknownParams": []}
    errors: list[str] = []
    unknown_params: list[dict[str, Any]] = []
    typed_params: list[dict[str, Any]] = []
    for index, call in enumerate(parsed.engineCalls):
        if call.fn not in ENGINE_FN_CATALOG_V2:
            errors.append(f"engineCalls.{index}.fn: unknown function {call.fn}")
            continue
        validated, param_errors = validate_engine_call_params(call.fn, call.params)
        if param_errors:
            unknown = sorted(
                str(err).split(":", 1)[0]
                for err in param_errors
                if "Extra inputs are not permitted" in str(err)
            )
            if unknown:
                unknown_params.append({"index": index, "fn": call.fn, "params": unknown})
            errors.extend(f"engineCalls.{index}.params.{err}" for err in param_errors)
            continue
        typed_params.append({"index": index, "fn": call.fn, "params": validated or {}})
    return {"ok": not errors, "errors": errors, "unknownParams": unknown_params, "typedCalls": typed_params}


_VISUAL_ROLE_PROMPT_FIELDS = {
    "projectile": "projectileSpritePrompt",
    "impact": "impactSpritePrompt",
    "child": "childSpritePrompt",
    "field": "fieldSpritePrompt",
}
_VISUAL_PROJECTED_PROMPT_FIELDS = {
    "projectile": ("projectileImagePrompt", "projectileSpritePrompt"),
    "impact": ("impactImagePrompt", "impactSpritePrompt"),
    "child": ("childImagePrompt", "childSpritePrompt"),
    "field": ("fieldImagePrompt", "fieldSpritePrompt"),
}
_VISUAL_LIST_FIELDS = (
    "palette",
    "vfxMaterialHints",
    "animationPlan",
    "assetDependencies",
    "qualityNotes",
)


def canonical_visual_kit_view(value: Any, *, repairs: list[str] | None = None) -> dict[str, Any]:
    """Validate VisualKit and collapse legacy duplicate role prompts.

    New authoring has exactly one prompt field per role at VisualKit top level.
    Old cache/replay payloads may still carry ``bakedAssets.<role>.prompt``; that
    value is migrated only when the canonical role prompt is absent, then removed.
    All repairs are shape/provenance migrations only; no visual meaning is inferred.
    """
    if not isinstance(value, dict):
        raise TypeError("visualKit must be a JSON object")
    raw = copy.deepcopy(value)
    repair_log = repairs if repairs is not None else []

    for legacy_key in ("silhouetteContract", "shapeContract", "itemShapeContract", "iconShapeContract"):
        legacy_value = str(raw.get(legacy_key) or "").strip()
        if legacy_value and not str(raw.get("itemSilhouetteContract") or "").strip():
            raw["itemSilhouetteContract"] = legacy_value
            repair_log.append(f"{legacy_key}:moved_to_itemSilhouetteContract")
        raw.pop(legacy_key, None)

    for field in _VISUAL_LIST_FIELDS:
        field_value = raw.get(field)
        if not isinstance(field_value, str):
            continue
        if field == "palette":
            import re
            raw[field] = [part.strip() for part in re.split(r"[,;/]", field_value) if part.strip()]
            repair_log.append("palette:string_to_list")
        else:
            cleaned = field_value.strip()
            raw[field] = [cleaned] if cleaned else []
            repair_log.append(f"{field}:string_to_singleton_list")

    baked_value = raw.get("bakedAssets")
    baked: dict[str, Any] = dict(baked_value) if isinstance(baked_value, dict) else {}
    unknown_roles = sorted(set(baked) - set(_VISUAL_ROLE_PROMPT_FIELDS))
    if unknown_roles:
        raise ValueError(f"visualKit.bakedAssets contains unknown roles: {unknown_roles}")
    for role, prompt_field in _VISUAL_ROLE_PROMPT_FIELDS.items():
        spec = baked.get(role) if isinstance(baked.get(role), dict) else None
        if not isinstance(spec, dict):
            continue
        legacy_prompt = str(spec.get("prompt") or "").strip()
        canonical_prompt = str(raw.get(prompt_field) or "").strip()
        if legacy_prompt and not canonical_prompt:
            raw[prompt_field] = legacy_prompt
            repair_log.append(f"bakedAssets.{role}.prompt:moved_to_{prompt_field}")
        elif legacy_prompt and canonical_prompt and legacy_prompt != canonical_prompt:
            repair_log.append(f"bakedAssets.{role}.prompt:discarded_duplicate_of_{prompt_field}")
        spec.pop("prompt", None)
        if role != "projectile" and str(spec.get("mode") or "") == "reuse_item_sprite":
            baked.pop(role, None)
            repair_log.append(f"bakedAssets.{role}:dropped_role_inapplicable_reuse_item_sprite")
            continue
        if role != "projectile" and "distinctFromItem" in spec:
            spec.pop("distinctFromItem", None)
            repair_log.append(f"bakedAssets.{role}.distinctFromItem:dropped_role_inapplicable")
        baked[role] = spec
    raw["bakedAssets"] = baked

    parsed = VisualKitBoundary.model_validate(raw)
    out: dict[str, Any] = parsed.model_dump(exclude_none=True)
    out_baked_value = out.get("bakedAssets")
    out_baked: dict[str, Any] = dict(out_baked_value) if isinstance(out_baked_value, dict) else {}
    for role, spec in out_baked.items():
        if not isinstance(spec, dict):
            continue
        spec.pop("prompt", None)
        mode = str(spec.get("mode") or "")
        distinct = spec.get("distinctFromItem")
        if mode == "reuse_item_sprite" and role != "projectile":
            raise ValueError("reuse_item_sprite is valid only for the projectile role")
        if distinct is not None and role != "projectile":
            raise ValueError("distinctFromItem is valid only for the projectile role")
        if distinct is True and mode != "baked_sprite":
            raise ValueError("distinctFromItem=true requires projectile mode=baked_sprite")
    return out


def validate_visual_kit_boundary(value: Any) -> dict[str, Any]:
    return canonical_visual_kit_view(value)


def canonical_vfx_manifest_view(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("vfxManifest must be a JSON object")
    raw = copy.deepcopy(value)
    for field in VFX_MANIFEST_DEBUG_ONLY_FIELDS:
        raw.pop(field, None)
    budget = raw.get("budget")
    if isinstance(budget, dict):
        raw["budget"] = {k: v for k, v in budget.items() if k not in VFX_BUDGET_DEBUG_ONLY_FIELDS}
    debug = raw.get("debug")
    if isinstance(debug, dict):
        raw["debug"] = {k: v for k, v in debug.items() if k not in VFX_DEBUG_ONLY_FIELDS}
    parsed = VfxManifestBoundary.model_validate(raw)
    return parsed.model_dump(exclude_none=True, by_alias=True)


def validate_vfx_manifest_boundary(value: Any) -> dict[str, Any]:
    return canonical_vfx_manifest_view(value)


def validate_visual_authoring_boundaries(data: dict[str, Any]) -> dict[str, Any]:
    """Validate presentation-authoring contracts independently of gameplay DTOs.

    VisualKit and VFX manifest are not C# gameplay-authoring surfaces, so they stay
    outside ``validate_executable_item_boundary``. Fresh crafts and cache hits must
    nevertheless pass the same strict presentation boundaries before delivery.
    """
    normalized: dict[str, Any] = {}
    if "visualKit" in data:
        kit: dict[str, Any] = canonical_visual_kit_view(data.get("visualKit"))
        visual_value = data.get("visual")
        attack_value = data.get("attack")
        visual: dict[str, Any] = visual_value if isinstance(visual_value, dict) else {}
        attack: dict[str, Any] = attack_value if isinstance(attack_value, dict) else {}
        baked_value = kit.get("bakedAssets")
        baked: dict[str, Any] = dict(baked_value) if isinstance(baked_value, dict) else {}
        for role, prompt_field in _VISUAL_ROLE_PROMPT_FIELDS.items():
            spec_value = baked.get(role)
            spec: dict[str, Any] = spec_value if isinstance(spec_value, dict) else {}
            if str(spec.get("mode") or "") != "baked_sprite":
                continue
            prompt = str(
                kit.get(prompt_field)
                or visual.get(f"{role}ImagePrompt")
                or attack.get(f"{role}SpritePrompt")
                or ""
            ).strip()
            if not prompt:
                raise ValueError(
                    f"visualKit.bakedAssets.{role}: baked_sprite requires an authored role prompt"
                )
        normalized["visualKit"] = kit
    if "vfxManifest" in data:
        normalized["vfxManifest"] = validate_vfx_manifest_boundary(data.get("vfxManifest"))
    return normalized


def executable_wire_view(data: dict[str, Any]) -> dict[str, Any]:
    raw_attack = data.get("attack")
    raw_gameplay = data.get("gameplay")
    attack: dict[str, Any] = raw_attack if isinstance(raw_attack, dict) else {}
    gameplay: dict[str, Any] = raw_gameplay if isinstance(raw_gameplay, dict) else {}
    gameplay_wire = {k: v for k, v in gameplay.items() if k not in GAMEPLAY_DEBUG_ONLY_FIELDS}
    rejected = gameplay_wire.get("rejectedEngineCalls")
    if isinstance(rejected, list):
        gameplay_wire["rejectedEngineCalls"] = [
            {k: v for k, v in row.items() if k not in REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS}
            if isinstance(row, dict) else row
            for row in rejected
        ]
    view: dict[str, Any] = {
        "attack": {k: v for k, v in attack.items() if k not in ATTACK_NON_WIRE_FIELDS},
        "gameplay": gameplay_wire,
    }
    if "accessory" in data:
        view["accessory"] = copy.deepcopy(data.get("accessory"))
    if "armor" in data:
        view["armor"] = copy.deepcopy(data.get("armor"))
    return view


_ATTACK_ALWAYS_REQUIRED = frozenset({
    "enabled", "runtimePlanAuthored", "runtimeFamily", "delivery", "damageClass",
    "movement", "movementCode", "effect", "effectCode", "onHit", "onHitCode",
    "speed", "rangeTiles", "lifetime", "pierce", "shotCount", "maxChildProjectiles",
    "maxChildDepth", "dustSpawnDenom",
})
_ATTACK_FAMILY_REQUIRED: dict[str, frozenset[str]] = {
    "charge_release": frozenset({"chargeTicks", "chargePowerMultiplier", "channelUse"}),
    "sentry": frozenset({"sentryPlacement", "sentryAttackIntervalTicks", "sentryTargetRangeTiles", "sentryLifetimeTicks"}),
    "beam": frozenset({"beamWidthPx", "beamChargeTicks", "channelUse"}),
    "overhead_barrage": frozenset({"delayTicks", "secondaryLifetimeTicks"}),
}
_GAMEPLAY_ALWAYS_REQUIRED = frozenset({"kind", "damageClass", "damage", "useTime", "useAnimation", "maxStack"})
_GAMEPLAY_KIND_REQUIRED: dict[str, frozenset[str]] = {
    "tool": frozenset({"pickPower", "axePower", "hammerPower"}),
    "potion": frozenset({"consumable", "healLife", "healMana", "buffCode", "buffTime"}),
    "ammo": frozenset({"consumable", "ammoFor", "craftYield"}),
}


def _require_authored_fields(raw: dict[str, Any], fields: frozenset[str], boundary: str) -> None:
    missing = sorted(field for field in fields if field not in raw)
    if missing:
        raise ValueError(f"{boundary}: compiler-owned fields missing from final projection: {missing}")


def validate_executable_item_boundary(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the final executable view without mutating or authoring it.

    Input/default models remain useful for deserialization, but final compiled
    output must explicitly carry compiler-owned fields.  Missing values are not
    silently replaced with DTO defaults at this boundary.
    """
    view = executable_wire_view(data)
    raw_attack = view["attack"]
    raw_gameplay = view["gameplay"]
    parsed_attack = AttackSpecBoundary.model_validate(raw_attack)
    parsed_gameplay = GameplaySpecBoundary.model_validate(raw_gameplay)
    parsed_accessory = AccessorySpecBoundary.model_validate(view.get("accessory", {}))
    parsed_armor = ArmorSpecBoundary.model_validate(view.get("armor", {}))
    if bool(parsed_attack.enabled):
        required_attack = _ATTACK_ALWAYS_REQUIRED | _ATTACK_FAMILY_REQUIRED.get(parsed_attack.runtimeFamily, frozenset())
        _require_authored_fields(raw_attack, required_attack, "AttackSpec")
    else:
        _require_authored_fields(raw_attack, frozenset({"enabled"}), "AttackSpec")
    required_gameplay = _GAMEPLAY_ALWAYS_REQUIRED | _GAMEPLAY_KIND_REQUIRED.get(parsed_gameplay.kind, frozenset())
    _require_authored_fields(raw_gameplay, required_gameplay, "GameplaySpec")
    if isinstance(view.get("accessory"), dict) and view["accessory"]:
        _require_authored_fields(view["accessory"], frozenset({"enabled"}), "AccessorySpec")
    if isinstance(view.get("armor"), dict) and view["armor"]:
        _require_authored_fields(view["armor"], frozenset({"enabled"}), "ArmorSpec")
    return {
        "attack": parsed_attack.model_dump(),
        "gameplay": parsed_gameplay.model_dump(),
        "accessory": parsed_accessory.model_dump(),
        "armor": parsed_armor.model_dump(),
    }


__all__ = [
    "StrictBoundaryModel", "EngineCallBoundary", "RuntimePlanBoundary",
    "BuffEntryBoundary", "GeneratedBuffBoundary", "RuntimeStateBoundary",
    "VisualKitBoundary", "VfxManifestBoundary", "GameplaySpecBoundary", "AccessorySpecBoundary", "ArmorSpecBoundary", "AttackSpecBoundary",
    "ATTACK_DEBUG_ONLY_FIELDS", "ATTACK_LEGACY_NON_WIRE_FIELDS", "ATTACK_NON_WIRE_FIELDS",
    "GAMEPLAY_DEBUG_ONLY_FIELDS", "REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS",
    "runtime_plan_boundary_report", "canonical_visual_kit_view", "validate_visual_kit_boundary",
    "validate_vfx_manifest_boundary", "validate_visual_authoring_boundaries",
    "validate_executable_item_boundary", "executable_wire_view",
]
