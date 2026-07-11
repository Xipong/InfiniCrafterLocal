from __future__ import annotations

from typing import Any

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
    mode: str
    prompt: str = ""
    reason: str = ""
    distinctFromItem: bool | None = None


class AnimeReferenceBoundary(StrictBoundaryModel):
    strength: str
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
    vfxScaleHint: str = "normal"
    vfxRhythmHint: str = "normal"
    vfxMaterialHints: list[str] = Field(default_factory=list)
    vfxAvoid: str = ""
    animationPlan: list[str] = Field(default_factory=list)
    assetDependencies: list[str] = Field(default_factory=list)
    qualityNotes: list[str] = Field(default_factory=list)
    negativePrompt: str = ""
    animeReference: AnimeReferenceBoundary | None = None

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
    useFantasy: str = ''
    heldVisibility: str = ''
    releaseTiming: str = ''
    handPose: str = ''
    spawnStyle: str = ''
    rotationMode: str = ''
    trailMode: str = ''
    projectileSizePolicy: str = ''
    drawDuringUse: bool = False
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
    extractinatorOutputItemType: int = 0
    extractinatorOutputStack: int = 0
    useConditionMode: str = ''
    useConditionMinLife: int = 0
    useConditionMinMana: int = 0
    runtimeState: RuntimeStateBoundary = Field(default_factory=RuntimeStateBoundary)
    rejectedEngineCalls: list[RejectedEngineCallBoundary] = Field(default_factory=list)


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


ATTACK_DEBUG_ONLY_FIELDS = frozenset({"genome", "engineMetrics", "patternSource", "runtimeAuthoringProvenance"})
GAMEPLAY_DEBUG_ONLY_FIELDS = frozenset({"categoryIntent", "powerTransfer"})
REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS = frozenset({"index", "rawFn", "originalFn", "sourceIndex", "params"})
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


def validate_visual_kit_boundary(value: Any) -> dict[str, Any]:
    parsed = VisualKitBoundary.model_validate(value)
    return parsed.model_dump(exclude_none=True)


def validate_vfx_manifest_boundary(value: Any) -> dict[str, Any]:
    parsed = VfxManifestBoundary.model_validate(value)
    return parsed.model_dump(exclude_none=True, by_alias=True)


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
    return {
        "attack": {k: v for k, v in attack.items() if k not in ATTACK_DEBUG_ONLY_FIELDS},
        "gameplay": gameplay_wire,
    }


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
    if bool(parsed_attack.enabled):
        required_attack = _ATTACK_ALWAYS_REQUIRED | _ATTACK_FAMILY_REQUIRED.get(parsed_attack.runtimeFamily, frozenset())
        _require_authored_fields(raw_attack, required_attack, "AttackSpec")
    else:
        _require_authored_fields(raw_attack, frozenset({"enabled"}), "AttackSpec")
    required_gameplay = _GAMEPLAY_ALWAYS_REQUIRED | _GAMEPLAY_KIND_REQUIRED.get(parsed_gameplay.kind, frozenset())
    _require_authored_fields(raw_gameplay, required_gameplay, "GameplaySpec")
    return {"attack": parsed_attack.model_dump(), "gameplay": parsed_gameplay.model_dump()}


__all__ = [
    "StrictBoundaryModel", "EngineCallBoundary", "RuntimePlanBoundary",
    "BuffEntryBoundary", "GeneratedBuffBoundary", "RuntimeStateBoundary",
    "VisualKitBoundary", "VfxManifestBoundary", "GameplaySpecBoundary", "AttackSpecBoundary",
    "ATTACK_DEBUG_ONLY_FIELDS", "GAMEPLAY_DEBUG_ONLY_FIELDS", "REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS",
    "runtime_plan_boundary_report", "validate_visual_kit_boundary",
    "validate_vfx_manifest_boundary", "validate_executable_item_boundary", "executable_wire_view",
]
