// Headless behavioral checks against the actual mod source and tModLoader types.
// This executable never starts Terraria.Main, loads a world, or initializes graphics.
// Run with existing dependencies (no model requests, no tML packaging tasks):
// dotnet run --project tools/EngineRuntimeChecks.csproj \
//   -p:InfiniTmlReferenceDir=<tModLoader-package/lib/net8.0> \
//   -p:InfiniExternalDepsRoot=<ParticleLibrary-and-Luminance-root>
// These method-level regressions do not simulate Terraria's update/network loop.
using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int Main(string[] args)
    {
        string sandbox = System.IO.Directory.CreateTempSubdirectory("icl-engine-checks-").FullName;
        try
        {
            // Main's static world/player path fields require Program.SavePath.
            // Supply an isolated directory, never the player's actual saves.
            Terraria.Program.SavePath = sandbox;
            Terraria.Main.dedServ = true;
            if (args.Length == 2 && args[0] == "--check-filter")
                return RunChecks(args[1]);
            if (args.Length == 2 && args[0] == "--replay-contracts")
                return ReplayGeneratedContracts(args[1]);
            if (args.Length == 2 && args[0] == "--capture-vfx-preview")
            {
                CaptureVfxPreview(args[1]);
                return 0;
            }
            if (args.Length != 0)
                throw new ArgumentException("Expected --replay-contracts <jsonl-path> or --capture-vfx-preview <json-path>");
            return RunChecks();
        }
        finally { System.IO.Directory.Delete(sandbox, recursive: true); }
    }

    private static int RunChecks(string? filter = null)
    {
        (string Name, Action Check)[] checks = {
            ("nearest event damage retains radial native selection and direct-target exclusion", NearestDamageRetainsTheSingleCenterNativeAction),
            ("target bias saved DTO range and native distance-score discount", TargetBiasKeepsSavedDtoDomainAndActualDistanceDiscount),
            ("signed vertical acceleration native DTO active updates and hydration", SignedVerticalAccelerationUsesNativeDtoAndEveryActiveUpdate),
            ("signed vertical acceleration activation delay and update rate", SignedVerticalAccelerationWaitsForActivationThenPreservesAuthoredRate),
            ("sampled launch strict DTO and old saved absence", SampledLaunchDtoRejectsInvalidAndPreservesOldAbsence),
            ("sampled launch raw numeric domain and round trips", SampledVelocityRawNumericDomainAndRoundTrips),
            ("sampled velocity seeded geometry and area moments", SampledVelocitySeededGeometryAndAreaMoments),
            ("sampled velocity native spawn owner authority", SampledVelocityReachesNativeSpawnOnlyOnOwner),
            ("sampled velocity delay ExtraAI and hydration", SampledVelocityDelayExtraAiAndHydrationPreserveChosenVector),
            ("hit target captured hitbox branch endpoints and seed", HitTargetGeometryUsesCapturedHitboxAndExactBranchEndpoints),
            ("hit target delayed native boundary and reservation ownership", HitTargetDelayedNativeBoundaryAndReservationOwnership),
            ("initial NPC exclusion exact incarnation and counter", InitialNpcExclusionUsesExactIncarnationAndCounter),
            ("initial NPC exclusion ExtraAI remaining and v2 absence", InitialNpcExclusionExtraAiPreservesRemainingAndOldAbsence),
            ("explicit spawn transform native boundary", ExplicitSpawnTransformRejectsInvalidBeforeNativeBoundary),
            ("target emission strict wire and old action absence", TargetEmissionWireIsStrictAndOldOpcodesStayAbsent),
            ("target emission anchor and repeat policies", TargetEmissionPlannerUsesExplicitAnchorsAndRepeatPolicy),
            ("target emission inclusive range ties and LOS", TargetEmissionPlannerUsesInclusiveRangeExactTiesAndLos),
            ("target emission real hit authority stats and reservations", TargetEmissionRealHitHookKeepsAuthorityStatsAndReservation),
            ("target emission ordinary refusal and child collision", TargetEmissionNormalRefusalsReturnUnspentPlanBudget),
            ("target emission delayed NPC incarnation and refunds", TargetEmissionDelayedDispatchRequiresSameActiveNpcAndRefundsCancellation),
            ("raw numeric helper signed nullable neutral domains", RawNumericHelperSignedNullableAndNeutralDomains),
            ("hitbox raw numeric outside domain", HitboxRawNumericDomainRefusesOutsideBeforeNarrowing),
            ("hitbox raw numeric serialization cache network", HitboxRawNumericEndpointsSurviveSerializationCacheNetwork),
            ("hitbox raw numeric presence and invalid types", HitboxRawNumericPresenceAndInvalidTypesStayStrict),
            ("hitbox curve actual rectangle and world-tick clock", HitboxCurveActualDamageRectAndWorldTickClock),
            ("hitbox curve explicit visual mirror and hydration", HitboxCurveExplicitVisualMirrorAndLateHydration),
            ("hitbox curve strict DTO presence", HitboxCurveDtoPresenceAndDriverBoundaries),
            ("motion modifiers actual phase and visual hydration", ModifierActualTurnSpeedPhaseAndVisualHydration),
            ("NPC attraction authority falloff and bounds", ModifierNpcAttractionAuthorityFalloffAndBounds),
            ("homing modifier owner selection and speed", ModifierHomingOwnerSelectionAndSpeedPreservation),
            ("whip gravity actual collision polyline", ModifierWhipGravityUsesTheSameCollisionPolyline),
            ("motion modifier strict DTO presence", ModifierStrictDtoPresenceAndOldAbsence),
            ("hitbox mirror exact PNG vertices", HitboxCurveExplicitMirrorReachesSpriteVertices),
            ("hitbox mirror exact primitive vertices", HitboxCurveExplicitMirrorReachesPrimitiveVertices),

            ("bugfix251 grounded native support", GroundedConditionRequiresNativeSupport),
            ("VFX sound selector strict DTO round trips", VfxSoundSelectorStrictDtoRoundTrips),
            ("VFX sound selector native item projectile consumers", VfxSoundSelectorReachesItemAndProjectileNativeBoundary),
            ("VFX sound selector silence and server controls", VfxSoundSelectorPreservesSilentAndServerControls),
            ("VFX explicit sound strict DTO and pitch interval", VfxSoundControlsStrictDtoAndPitchInterval),
            ("VFX explicit sound owns pitch and preserves native policies", VfxSoundControlsOwnPitchAndPreserveNativePolicies),
            ("quality250 NativeDirectUseStackCostIsLiteralUnderSaving", NativeDirectUseStackCostIsLiteralUnderSaving),
            ("own-stack chance one completed activation", NativeOwnStackChanceUsesOneCompletedActivation),
            ("own-stack chance placement isolation", OwnStackChanceRejectsPlacementAndPassiveDtos),
            ("quality250 NativeQuickHealStackCostUsesPrimaryUnderSaving", NativeQuickHealStackCostUsesPrimaryUnderSaving),
            ("RT02 NativeQuickUtilityOpenedVoidPrerequisite", RT02NativeQuickUtilityOpenedVoidPrerequisite),
            ("RT02 NativeQuickUtilityFreshInventoryAndVoidWitness", RT02NativeQuickUtilityFreshInventoryAndVoidWitness),
            ("RT02 NativeQuickUtilityWriterServerRemote", RT02NativeQuickUtilityWriterServerRemote),
            ("RT02 NativeQuickUtilityManualAndSnapshotControls", RT02NativeQuickUtilityManualAndSnapshotControls),
            ("RT02 NativeQuickUtilityAuthorityFences", RT02NativeQuickUtilityAuthorityFences),
            ("RT02 NativeQuickUtilityLifetimeAndCapacity", RT02NativeQuickUtilityLifetimeAndCapacity),
            ("quality250 NativeLiteralStackCostKeepsMobilityAndPlacementGates", NativeLiteralStackCostKeepsMobilityAndPlacementGates),
            ("quality250 NativePickAmmoSavingRemainsIndependentOfDirectStackCost", NativePickAmmoSavingRemainsIndependentOfDirectStackCost),
            ("quality250 NativeFloat32BuffNearNeutralIdentityAndExpiry", NativeFloat32BuffNearNeutralIdentityAndExpiry),
            ("quality250 NativeFloat32BuffAllComponentsAndExactRefresh", NativeFloat32BuffAllComponentsAndExactRefresh),
            ("persistence RemoteEscrowMirrorNeverBecomesSinglePlayerMaterial", RemoteEscrowMirrorNeverBecomesSinglePlayerMaterial),
            ("persistence ScopedRemoteEscrowResponseRequiresExactOrigin", ScopedRemoteEscrowResponseRequiresExactOrigin),
            ("persistence NativePlacementIntentPrecedesMutationAndRejectsLateClaims", NativePlacementIntentPrecedesMutationAndRejectsLateClaims),
            ("persistence PlacementIntentRateReplayExpiryAndBeforeStateControls", PlacementIntentRateReplayExpiryAndBeforeStateControls),
            ("persistence PlacementClientWaitsForServerBeforeSnapshotAndSpendsOnce", PlacementClientWaitsForServerBeforeSnapshotAndSpendsOnce),
            ("persistence LocalPlacementReceiptStillSpendsStackOneExactlyOnce", LocalPlacementReceiptStillSpendsStackOneExactlyOnce),
            ("persistence PermanentlyBrokenPlacementReturnSurvivesReload", PermanentlyBrokenPlacementReturnSurvivesReload),
            ("persistence PlacementQuarantineValidatedRequeueIsIdempotent", PlacementQuarantineValidatedRequeueIsIdempotent),
            ("persistence EmptyLegacyRemoteMarkerDoesNotBrickFreshStationUse", EmptyLegacyRemoteMarkerDoesNotBrickFreshStationUse),
            ("persistence ForeignDormantClaimDoesNotBecomeCurrentAuthorityOrBlockFreshInputs", ForeignDormantClaimDoesNotBecomeCurrentAuthorityOrBlockFreshInputs),
            ("persistence NativeItemCheckRetriesUnstartedPlacementAfterReadyWithoutAutoReuse", NativeItemCheckRetriesUnstartedPlacementAfterReadyWithoutAutoReuse),
            ("persistence MalformedQuarantineEnvelopePreservesHealthyNeighbors", MalformedQuarantineEnvelopePreservesHealthyNeighbors),
            ("persistence QuarantineRequeueReceiptDoesNotCountAsSecondMaterialOwner", QuarantineRequeueReceiptDoesNotCountAsSecondMaterialOwner),
            ("persistence PendingRawMalformedAndOverflowRowsKeepValidNeighbors", PendingRawMalformedAndOverflowRowsKeepValidNeighbors),
            ("persistence UnmutatedAbandonedPlacementDoesNotStallNewTarget", UnmutatedAbandonedPlacementDoesNotStallNewTarget),
            ("persistence PlacementReadyCannotApproveDifferentServerResolvedBinding", PlacementReadyCannotApproveDifferentServerResolvedBinding),
            ("dynamic projectile pierce preserves native maximum and immunity", RuntimeDynamicPierceKeepsNativeMaximumAndImmunity),
            ("generated tooltips describe exact executable bindings", GeneratedTooltipsDescribeExactExecutableBindings),
            ("forge heart name animated gradient", ForgeHeartNameGradientPreservesNativeText),
            ("forge heart native atlas animation", ForgeHeartNativeAnimationUsesAtlas),
            ("forge localization uses native filename prefix", ForgePresentationLocalizationUsesNativePrefix),
            ("forge craft notices use localized native text", ForgePresentationCraftNoticesUseLocalizedText),
            ("forge lane status preserves timers and host facts", ForgePresentationLaneStatusPreservesTimersAndHostFacts),
            ("generated native prefix survives active use", GeneratedItemNativePrefixSurvivesActiveUse),
            ("generated native prefix placement and ammo independence", GeneratedItemNativePrefixPlacementAndAmmoStayIndependent),
            ("generated native prefix compact hydration", GeneratedItemNativePrefixCompactHydration),
            ("generated root combat native lane contexts and query counts", GeneratedRootCombatNativeLanesAndQueryCounts),
            ("generated root combat terminal hold and source fence", GeneratedRootCombatTerminalHoldAndSourceFence),
            ("child combat strict saved wire preserves absent selectors", ChildCombatSavedWireIsStrictAndPreservesAbsence),
            ("child combat immediate events inherit exact current values once", ChildCombatImmediateEventsSelectLiveOrAuthoredStatsExactlyOnce),
            ("child combat delayed and charge events capture at admission", ChildCombatDelayedAndChargeEventsCaptureAtAdmission),
            ("child combat sentry firing and refused spawn reservations", ChildCombatSentryUsesCurrentParentAndRefusalsRefundBudget),
            ("dynamic collision preserves authored choice and return phase", RuntimeCollisionKeepsAuthoredChoiceAndReturnPhase),
            ("swarm charge keeps actual combat basis exactly once", SwarmChargeKeepsCombatBasisOnce),
            ("swarm charge received released ExtraAI never rescales", SwarmChargeReleasedExtraAiDoesNotRescale),
            ("swarm delayed hooks honor world clock and wrap", SwarmDelayedHooksHonorWorldClock),
            ("swarm delayed due pressure keeps per-world-tick budget", SwarmDelayedDuePressureKeepsWorldTickBudget),
            ("swarm delayed eligibility shares canonical dispatch authority", SwarmDelayedAuthorityMatchesImmediateDispatch),
            ("swarm material churn cannot starve independent owners", SwarmMaterialChurnDoesNotStarveFreshOwners),
            ("swarm material ordered admission fans out without replay", SwarmMaterialOrderedAdmissionFansOutWithoutReplay),
            ("local asset downloads keep generator origin separate from sharing URL", LocalAssetDownloadsKeepGeneratorOrigin),
            ("runtime sprite burst bounds resident and deferred resources", RuntimeSpriteBurstBoundsResidentAndDeferredResources),
            ("runtime sprite LRU retains queued borrowers until owner drain", RuntimeSpriteLruRetainsQueuedBorrowersUntilOwnerDrain),
            ("runtime sprite worker Clear and Mod.Unload defer borrowed resources", RuntimeSpriteWorkerClearAndModUnloadDeferBorrowedResources),
            ("runtime sprite same filename invalidation reloads inventory without retiring queued texture", RuntimeSpriteInvalidationReloadsInventoryWithoutRetiringQueuedTexture),
            ("runtime sprite invalidation aliases use selected owner and backoff key", RuntimeSpriteInvalidationAliasesUseSelectedOwnerAndBackoffKey),
            ("runtime sprite invalidation Clear and Dispose fence pending retirement", RuntimeSpriteInvalidationClearAndDisposeFencePendingRetirement),
            ("runtime sprite inventory consumer follows certified asset byte owner", RuntimeSpriteConsumerUsesCertifiedAssetOwner),
            ("runtime sprite conflicting certificates preserve inventory ownership", RuntimeSpriteConflictingCertificatesPreserveInventoryOwnership),
            ("runtime sprite certified lookup has constant hot-path work", RuntimeSpriteCertifiedLookupHasConstantHotPathWork),
            ("runtime sprite selected owner failure backs off and retries", RuntimeSpriteSelectedOwnerFailureBacksOffAndRetries),
            ("individual material projectile owner and transport session reset", MaterialProjectilePeerSessionReset),
            ("individual material Item owner and transport session reset", MaterialItemPeerSessionReset),
            ("individual material projectile churn keeps bounded replay without generation admission cap", MaterialProjectileChurnDoesNotConsumeReplayCapacity),
            ("individual material Item churn keeps bounded replay without generation admission cap", MaterialItemChurnDoesNotConsumeReplayCapacity),
            ("individual material runtime assets require exact ready domain", MaterialAssetsRequireExactReadyStatus),
            ("individual material unresolved Item forwarding retains transport token", MaterialUnresolvedItemForwardingRetainsToken),
            ("individual material nonowner live path and legacy stay local", MaterialNonownerPathAndLegacyRemainLocal),
            ("individual material nonowner lifecycle local before relay exactly once", MaterialNonownerLocalBeforeRelay),
            ("individual material nonowner lifecycle relay before local exactly once", MaterialNonownerRelayBeforeLocal),
            ("individual material dead Item SP world periodic retires", MaterialDeadItemSpWorld),
            ("individual material dead Item SP source periodic retires", MaterialDeadItemSpSource),
            ("individual material dead Item MP-client world periodic retires", MaterialDeadItemClientWorld),
            ("individual material dead Item MP-client source periodic retires", MaterialDeadItemClientSource),
            ("individual material dead Item delay keeps world snapshot and source fence", MaterialDeadItemDelayKeepsWorldSnapshotAndFencesSource),
            ("individual material Item respawn re-registers and keeps exact generation fence", MaterialItemRespawnReregistersAndKeepsGenerationFence),
            ("individual material item periodic positive total is not a group cap", MaterialItemPeriodicPositiveTotalIsNotAGroupCap),
            ("individual material asset uses network roster", MaterialElementAssetUsesNetworkRoster),
            ("individual material strict wire rejects foreign null and dangling", MaterialElementStrictWireRejectsForeignNullAndDangling),
            ("individual material runtime motion and independent profiles", MaterialElementRuntimeMovesAndKeepsIndependentProfiles),
            ("individual material live source periodic final pose and generation", MaterialElementLiveSourcePeriodicUsesFinalPoseAndGeneration),
            ("individual material world delay versus source generation fence", MaterialElementDelayFreezesWorldButFencesSource),
            ("individual material item attachment uses instance identity", MaterialElementItemAttachmentUsesInstanceNotDefinition),
            ("individual material path exact beam whip history and distance UV", MaterialPathUsesActualBeamAndWhipAndUvDistance),
            ("individual material owner hit validated relay remote delivery", MaterialOwnerHitReachesValidatedServerRelayAndRemote),
            ("individual material item snapshot relay immutable pose and instance", MaterialItemSnapshotRelayPreservesPoseAndInstance),
            ("individual material budgets share legacy active detached costs", MaterialBudgetsShareLegacyActiveAndDetachedCosts),
            ("individual material occurrence identity distinguishes hits and replay", MaterialOccurrencesKeepTwoRealHitsButRejectSameOccurrence),
            ("individual material item event total spans element slots", MaterialItemEventTotalIsSharedAcrossElementsAndLegacy),
            ("individual material source hitPoint executes in source frame", MaterialSourceHitAnchorStaysSourceLocal),
            ("individual material peer hydration preserves age and source budget identity", MaterialPeerHydrationKeepsSourceBudgetKeyAndWorldAge),
            ("individual material profiles all curves RGB and zero semantics", MaterialProfilesEvaluateAllCurvesAndCapturedRgb),
            ("individual material path DTO producer and strict payload matrix", MaterialPathDtoRejectsWrongSourceAndPayloads),
            ("individual material attached hit snapshot resists late peer pose", MaterialCapturedSourceHitPointIsNotRebasedToLatePeerPose),
            ("individual material empty zero and missing texture draw controls", MaterialEmptyZeroMissingTextureControls),
            ("individual material drag acceleration spin use world ticks", MaterialMotionUsesDragAccelerationAndSpin),
            ("individual material path client sample and retired history lifecycle", MaterialPathClientOwnerSamplesAndRetiresHistory),
            ("individual material shared Python PNG roster parity", MaterialAssetRosterMatchesSharedPythonDtoFixture),
            ("individual material inherited velocity uses actual projectile world-tick units", MaterialProjectileInheritanceUsesLiveMaxUpdates),
            ("individual material DTO preserves authored axes and asset", MaterialElementDtoPreservesAuthoredAxesAndAsset),
            ("explicit library DTO typed payloads roundtrip and zero", ExplicitLibraryDtoRequiresTypedPayloadAndPreservesZero),
            ("explicit library DTO rejects missing foreign null nonfinite", ExplicitLibraryDtoRejectsMissingForeignAndNonfinite),
            ("explicit ParticleLibrary literal CPU motion and pixel axes", ExplicitLibraryParticleInfoHasLiteralMotionAndPixelAxes),
            ("explicit ParticleLibrary readiness count capture and expiry", ExplicitLibraryReadinessWaitPreservesCountAndExpires),
            ("explicit Luminance captured cue parameters budgets and lifecycle", ExplicitLuminanceCueUsesExactCapturedParametersAndBudget),
            ("explicit Luminance native rumble retires canceled owned cue", ExplicitLuminanceNativeRumbleRetiresCanceledOwnedCue),
            ("spawn damage survives Configure", SpawnDamageSurvivesConfigure),
            ("live combat state survives rehydration", CombatStateSurvivesRehydration),
            ("hitbox sizing preserves spawn center", HitboxSizingPreservesCenter),
            ("activation delay preserves launch velocity", ActivationDelayPreservesVelocity),
            ("activation respects explicit zero motion", ActivationRespectsZeroMotion),
            ("activation does not relaunch live state", ActivationDoesNotRelaunchLiveState),
            ("expiry action waits for final update", ExpiryWaitsForFinalUpdate),
            ("placement ledger restores saved layers", PlacementLedgerRestoresSavedLayers),
            ("accessory defense is applied once", AccessoryDefenseAppliedOnce),
            ("movement buffs are order independent", MovementBuffOrderIndependent),
            ("mining buffs are order independent", MiningBuffOrderIndependent),
            ("equipment visibility uses armor slot", EquipmentVisibilityUsesArmorSlot),
            ("buff caps and refresh remain intact", BuffCapsAndRefreshRemainIntact),
            ("station key is not consumed", StationKeyIsNotConsumed),
            ("rejected held pose does not leak", RejectedHeldPoseDoesNotLeak),
            ("projectile light respects client setting", ProjectileLightRespectsClientSetting),
            ("item light respects client setting", ItemLightRespectsClientSetting),
            ("particle setting controls real dust", ParticleSettingControlsRealDust),
            ("draw setting controls existing budgets", DrawSettingControlsExistingBudgets),
            ("draw budgets reset without world tick", DrawBudgetsResetWithoutWorldTick),
            ("detached layers own sprite batch", DetachedLayersOwnSpriteBatch),
            ("item VFX cadence handles integer seeds", ItemVfxCadenceHandlesIntegerSeeds),
            ("legacy projectileAfterimage runtime_geometry entity selector rejected", () => LegacyTextureProducerRejects("projectileAfterimage", "runtime_geometry", "entity")),
            ("legacy spriteStampTrail no_asset entity selector rejected", () => LegacyTextureProducerRejects("spriteStampTrail", "no_asset", "entity")),
            ("legacy actorAfterimage no_asset projectile selector rejected", () => LegacyTextureProducerRejects("actorAfterimage", "no_asset", "projectile")),
            ("legacy projectileAfterimage mismatched field selector rejected", () => LegacyTextureProducerRejects("projectileAfterimage", "reuse_item_icon", "field")),
            ("legacy selected PNG producer must be ready", LegacyTextureProducerRejectsUnready),
            ("legacy PNG/non-PNG producer controls survive actual DTO and texture selection", LegacyTextureProducerPositiveControls),
            ("primitive impact ring does not require impact texture", PrimitiveImpactRingDoesNotRequireImpactTexture),
            ("VFX events follow actual item and projectile producers", VfxEventReferencesFollowRuntimeProducers),
            ("detached VFX state is bounded and cleared", DetachedVfxStateIsBoundedAndCleared),
            ("legacy detached VFX client cleanup does not require Draw", DetachedVfxClientCleanupDoesNotRequireDraw),
            ("cache-only flag preserves request", CacheOnlyFlagPreservesRequest),
            ("generator delivery requires identity", GeneratorDeliveryRequiresIdentity),
            ("generated parent prefix is request-only", GeneratedParentPrefixIsRequestOnly),
            ("parent native sprite reference reaches prepared request", ParentNativeSpriteReferenceReachesPreparedRequest),
            ("parent native sprite reference absence is honest", ParentNativeSpriteReferenceAbsenceIsHonest),
            ("generated parent sprite reference never uses native proxy", ParentGeneratedSpriteReferenceNeverUsesNativeProxy),
            ("craft identity rejects failed defaults", CraftIdentityRejectsFailedDefaults),
            ("inventory ammo keeps generated definition", InventoryAmmoKeepsGeneratedDefinition),
            ("parent placement facts reach craft snapshot", ParentPlacementFactsReachCraftSnapshot),
            ("literal parent tooltip reaches real craft snapshot", LiteralParentTooltipReachesRealCraftSnapshot),
            ("verified native motion reference reaches craft snapshot", VerifiedNativeMotionReferenceReachesCraftSnapshot),
            ("runtime entity count respects declared limit", RuntimeEntityCountRespectsDeclaredLimit),
            ("run-speed equipment applies after vanilla movement", RunSpeedEquipmentAppliesAfterVanillaMovement),
            ("equipment authored ranges reach player", EquipmentAuthoredRangesReachPlayer),
            ("unit boundary charge release preserves authored speed", ChargeReleasePreservesAuthoredZeroAndFractionalSpeed),
            ("unit boundary charge complete uses exact duration", ChargeCompleteRequiresExactAuthoredDuration),
            ("equipment class damage reaches exact DamageClass", EquipmentClassDamageReachesExactDamageClass),
            ("generated ammo preserves exact projectile on direct use", GeneratedAmmoDirectUseKeepsDeclaredProjectile),
            ("generated ammo preserves exact rocket and solution selection", GeneratedAmmoPickAmmoKeepsExactRocketAndSolution),
            ("generated ammo leaves unrelated category unchanged", GeneratedAmmoPickAmmoRejectsUnrelatedCategoryRewrites),
            ("generated ammo preserves network and save boundaries", GeneratedAmmoNetworkAndSaveBoundaries),
            ("weapon ammo native shot selection conservation and stats", WeaponAmmoNativeShotKeepsSelectionConservationAndStats),
            ("weapon ammo missing ammo and independent use lanes", WeaponAmmoMissingAmmoAndIndependentUseLanes),
            ("weapon ammo native DTO absence and invalid presence", WeaponAmmoNativeDtoPreservesAbsenceAndRejectsInvalidPresence),
            ("generated whip applies same-owner summon source bonus", WhipImpactMarksOnlyItsOwnerForSummonSourceDamage),
            ("generated whip range changes geometry and collision", WhipGeometryTracksEquippedRangeInCollision),
            ("proximity missile expiry VFX matches event lifecycle", ProximityMissileExpireVfxMatchesNaturalExpiry),
            ("peer events preserve observed spawn-budget snapshot", PeerEventDoesNotOverwriteReceivedSpawnBudgetSnapshot),
            ("root binding spawn capacity respects authored count and independent event ledger", RootBindingSpawnCapacityRespectsAuthoredCountAndIndependentEventLedger),
            ("explicit concurrency wire preserves absence and rejects invalid presence", ExplicitConcurrencyWirePreservesAbsenceAndRejectsInvalidPresence),
            ("sentry explicit target policy LOS and hard radius", SentryTargetPolicyUsesExactAssignedNpcAndFilters),
            ("sentry volley native spawn arguments and authority", SentryVolleyUsesAuthoredCountAndSpreadAtNativeBoundary),
            ("sentry targeting strict DTO and retained wire", SentryTargetingDtoPreservesChoicesAndRejectsInvalidPresence),
            ("sentry lifecycle explicit DTO and native projections", SentryLifecycleDtoAndNativeProjection),
            ("sentry lifecycle native resting spot and turret cap", SentryNativeRestingSpotAndTurretCap),
            ("sentry event-only pool retirement", SentryEventOnlyPoolReapsBeforeSaturationRefusal),
            ("sentry descendant pool sustained firing and exact retirement", SentryDescendantPoolRetiresAndSustainsBeyond32),
            ("sentry descendant pool nested and lifetime ancestors", SentryDescendantPoolsPreserveEveryAncestor),
            ("sentry descendant pool pending cancellation and hydration", SentryDescendantPoolPendingAndHydration),
            ("sentry descendant pool native failure refunds exact unused slots", SentryDescendantPoolNativeFailureRefundsUnusedSlots),
                        ("explicit concurrency fences all spawn producers without changing legacy", ExplicitConcurrencyFencesAllSpawnProducersWithoutChangingLegacy),
            ("legacy equipment clamps remain unchanged", LegacyEquipmentClampsRemainUnchanged),
            ("legacy unclamped equipment stats remain intact", LegacyUnclampedEquipmentStatsRemainIntact),
            ("signed accessory defense reaches player", SignedAccessoryDefenseReachesPlayer),
            ("blink authored range reaches teleport", BlinkAuthoredRangeReachesTeleport),
            ("mobility consumption pure native outcome", NativePureMobilityConsumptionFollowsUseOutcome),
            ("mobility consumption mixed native effects once", NativeMixedMobilityRefusalPreservesOtherEffectsOnce),
            ("named item effects select native use and quick use", NamedItemEffectsSelectNativeUseAndQuickUse),
            ("named mobility groups share cooldown and consumption outcome", NamedMobilityGroupsShareCooldownAndConsumptionOutcome),
            ("named held effects refresh exact owner item and bound snapshots", NamedHeldEffectsRefreshExactOwnerItemAndBoundSnapshots),
            ("named item effects DTO roundtrip and invalid presence", NamedItemEffectsDtoRoundTripAndInvalidPresence),
            ("disposed asset download cannot publish", DisposedAssetDownloadCannotPublish),
            ("disposed asset download retires while response body remains withheld", DisposedAssetDownloadRetiresWhileBodyIsWithheld),
            ("disposed asset download retires while every HTTP slot remains held", DisposedAssetDownloadRetiresWhileHttpSlotsAreHeld),
            ("pull modes preserve subject and authority", PullModesPreserveSubjectAndAuthority),
            ("owner hit NPC status uses native sync", OwnerHitNpcEffectsUseNativeSync),
            ("owner projectile hit bridges exact NPC pull", OwnerProjectileHitBridgesNpcPull),
            ("retired projectile hit receipt keeps generation", RetiredProjectileHitKeepsGeneration),
            ("delayed owner hit never retargets replaced NPC", DelayedHitNeverRetargetsReplacedNpc),
            ("rt01 delayed NPC native hook incarnation fence", NativeDelayedNpcIncarnationRejectsInPlaceReuse),
            ("rt01 delayed NPC no area-pull fallback", NativeDelayedNpcPullNeverFallsThroughToArea),
            ("rt01 delayed NPC real status incarnation fence", NativeDelayedNpcStatusRejectsNewIncarnation),
            ("rt01 delayed NPC immediate terminal expiry controls", NativeDelayedNpcFenceKeepsImmediateTerminalAndExpiry),
            ("rt01 delayed NPC reservation refund controls", NativeDelayedNpcFenceKeepsReservationRefunds),
            ("item hit cannot turn into next held item effect", ItemHitCannotSwitchAuthoredSource),
            ("pending hit floods preserve other owner's capacity", PendingHitFloodKeepsOtherOwnerCapacity),
            ("socket-free sender flood preserves second sender", OwnerReceiptFloodDoesNotStarveNextSender),
            ("NPC hit generation survives real Transform", NpcHitGenerationSurvivesTransform),
            ("delayed actions keep original owner", DelayedActionsKeepOriginalOwner),
            ("delayed status keeps original NPC", DelayedStatusKeepsOriginalNpc),
            ("delayed queue honors limits", DelayedQueueHonorsLimits),
            ("event damage uses authored source", EventDamageUsesAuthoredSource),
            ("event spawn zero multiplier is not replaced by one", EventSpawnZeroMultiplierIsNotReplacedByOne),
            ("player save reference requires version markers", PlayerSaveReferenceRequiresVersionMarkers),
            ("applied trace observes projection without changing definition", AppliedTraceObservesProjectionWithoutChangingDefinition),
            ("longer generated report survives parent summary transport", LongerGeneratedReportSurvivesParentSummaryTransport),
            ("expanded scalar report keeps native clone and bounded transport", ExpandedScalarReportKeepsNativeCloneAndBoundedTransport),
            ("neutral item omissions preserve exact Item projection", NeutralItemOmissionsPreserveProjection),
            ("neutral buff omissions reach real player effects", NeutralBuffOmissionsReachRealPlayerEffects),
            ("small generated buffs reach real item/player hooks", SmallGeneratedBuffsReachRealHooks),
            ("generated utility status uses native icons without vanilla mechanics", GeneratedUtilityStatusUsesNativeIconsWithoutBuffMechanics),
            ("generated utility status draws native icon into FNA queue", GeneratedUtilityStatusDrawsNativeIconIntoFnaQueue),
            ("placed body DTO requires explicit lossless transform", PlacedBodyDtoRequiresExplicitLosslessTransform),
            ("placed body ledger selected identity save and network", PlacedBodyLedgerKeepsExplicitIdentityAcrossSaveAndNetwork),
            ("native placed body guards and positions", NativePlacedBodyGuardsAndPositions),
            ("native placed body final call preserves argument effects", NativePlacedBodyFinalCallPreservesArgumentEffects),
            ("native placed body atomic installation and cleanup", NativePlacedBodyAtomicInstallationAndCleanup),
            ("native placed body unsupported admission is explicit", NativePlacedBodyUnsupportedAdmissionIsExplicit),
            ("placed body native poses and independent actor boundary", PlacedBodyUsesActualNativePoseAndRejectsIndependentActors),
            ("placed body cosmetic decoder cannot erase material", PlacedBodyCosmeticDecodeCannotEraseMaterial),
            ("placed body hydration bounded fair and session scoped", PlacedBodyHydrationIsBoundedFairAndSessionScoped),
            ("placed body restore registry exact conflict refusal", PlacedBodyRestoreUsesExistingRegistryWithoutReplacingConflicts),
            ("placed body server stream and snapshot controls", PlacedBodyServerStreamAndSnapshotControls),
            ("placed body PNG native FNA exact transform", PlacedBodySubmitsOneExplicitFullFrameToNativeFna),
            ("pb01 actual placing client retains server identity and removal", PlacingClientRetainsExactServerIdentityThroughCommitAndRemoval),
            ("pb01 Ready group identity is server owned and fenced", PlacementReadyGroupIdentityRemainsServerOwnedAndFenced),
            ("pb02 preparation http to native canonical identity", Pb02PreparationHttpToNative),
            ("pb02 preparation native to http canonical identity", Pb02PreparationNativeToHttp),
            ("pb02 preparation no generator native restamp", Pb02PreparationHttpWithoutGenerator),
            ("pb02 late actual registry hydration http to native", Pb02LateHydrationHttpToNative),
            ("pb02 late actual registry hydration native to http", Pb02LateHydrationNativeToHttp),
            ("pb02 gameplay transform authority Visual VFX PNG identity fences", Pb02IdentityRetainsAuthoredDifferences),
            ("pb02 same ID restoration conflict refusal", Pb02RestoreRefusesSameIdContentConflicts),
            ("pb02 native default identity bytes unchanged", Pb02NativeDefaultHashBytesStayUnchanged),
            ("item impact sprite uses real detached sprite renderer", ItemImpactSpriteUsesDetachedRenderer),
            ("presentation metadata round trips strictly", PresentationMetadataRoundTrips),
            ("sprite size and axis metadata round trip strictly", SpritePresentationMetadataStrictRoundTrips),
            ("held root visibility uses explicit presentation opt-in", HeldRootVisibilityUsesExplicitPresentationOptIn),
            ("textured body uses declared axis and preserves native spin", TexturedBodyUsesDeclaredAxisAndPreservesNativeSpin),
            ("body copies capture selected size and axis without changing network pose", BodyCopiesCaptureSelectedSizeAndAxisWithoutChangingNetworkPose),
            ("item body copies use root size and impact stays independent", ItemBodyCopyUsesRootSizeAndDedicatedImpactStaysIndependent),
            ("native quick use never selects a non-effect binding", NativeQuickUseNeverSelectsNonEffectBinding),
            ("held proxy replaced only by ready instance PNG", HeldProxyIsReplacedOnlyByReadyInstanceSprite),
            ("generated cursor uses exact selected instance", GeneratedCursorUsesExactSelectedInstance),
            ("cursor source shape refuses foreign samples before emission", CursorSourceShapeRefusesForeignSampleBeforeEmission),
            ("held presentation matches engine geometry", HeldPresentationGeometryMatchesEngine),
            ("inventory/world draw preserves geometry and tint", GeneratedItemDrawPreservesEngineGeometryAndTint),
            ("runtime sprite cache premultiplies decoded pixels once", RuntimeSpriteAlphaChecksAtOwnerBoundary),
            ("equipment overlay uses player draw contract", EquipmentOverlayUsesPlayerDrawContract),
            ("equipment overlay respects vanity and slot visibility", EquipmentOverlayUsesVanityAndSlotVisibility),
            ("item VFX respects selectors and budgets", ItemVfxParticleSelectorsAndBudgets),
            ("item VFX sound preserves authored phase", ItemVfxSoundPreservesAuthoredPhase),
            ("item VFX rejects inactive remote source", ItemVfxRemoteRejectsInactiveSource),
            ("item VFX preserves world-clock cadence", ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick),
            ("active VFX primitives use pixel units", ActiveVfxPrimitiveGeometryUsesPixelUnits),
            ("active VFX respects authored blend", ActiveVfxBlendHonorsAuthoredMode),
            ("active VFX sprite trail matches body pose", ActiveVfxSpriteTrailMatchesBodyPose),
            ("runtime geometry uses world pixels and forward axis", RuntimeGeometryUsesWorldPixelsAndForwardAxis),
            ("active VFX none particle stays silent", ActiveVfxNoneParticleDoesNotEmitDust),
            ("active VFX history uses valid samples", ActiveVfxHistoryUsesValidSamples),
            ("item VFX hit positions relay and event budgets", ItemVfxEventPositionsRelayAndBudgets),
            ("item VFX shapes and sprites reach detached queue", ItemShapeAndSpriteEventsReachDetachedQueue),
            ("item explicit effect color reaches light", ItemExplicitEffectColorReachesLight),
            ("beam runtime body matches collision geometry", RuntimeBeamBodyMatchesCollisionGeometry),
            ("beam strict DTO and retained v5 absence", BeamStrictDtoAndRetainedAbsence),
            ("beam live damage and shared body warmup ramps", BeamRampsConsumeLiveDamageAndSharedBodyGeometry),
            ("beam native mana cadence and world clock", BeamSustainUsesNativeManaAndWorldClock),
            ("beam failed mana and control loss terminate", BeamManaFailureAndControlLossTerminateBeforeFurtherPayment),
            ("beam native scan clips collision body and VFX endpoints", BeamLaserScanClipsCollisionBodyAndVfxPathTogether),
            ("ordinary runtime body preserves forward and spin", RuntimeOrdinaryBodyPreservesForwardAndSpinGeometry),
            ("whip runtime body matches live collision points", RuntimeWhipBodyMatchesLiveCollisionPoints),
            ("VFX anchors reach geometry and events", ProjectileVfxAnchorsReachGeometryAndEvents),
            ("VFX shapes respect budgets layers and parameters", ActiveShapesRespectBudgetsLayersAndParameters),
            ("event sprite renderers snapshot authored texture", EventSpriteRenderersSnapshotAuthoredTexture),
            ("event shapes use detached FNA queue", EventShapesUseDetachedFnaQueue),
            ("explicit VFX color overrides legacy presentation", VfxExplicitColorOverridesLegacyPresentation),
            ("tip trail tracks forward tip history", TipTrailTracksForwardTipHistory),
            ("ghost arc queues rotating open sweep", ActiveGhostArcQueuesRotatingOpenSweep),
            ("orbiting motes queue moving points", ActiveOrbitingMotesQueueMovingPoints),
            ("field pulse queues expanding ring", ActiveFieldPulseQueuesExpandingRing),
            ("wavy strip queues animated curve", ActiveWavyStripQueuesAnimatedCurve),
        };
        if (filter is not null)
        {
            int fullCount = checks.Length;
            checks = Array.FindAll(checks, entry => entry.Name.Contains(filter, StringComparison.Ordinal));
            if (string.IsNullOrWhiteSpace(filter) || checks.Length == 0)
                throw new ArgumentException("Check filter must select at least one canonical named check");
            Console.WriteLine($"FILTERED RUN: {checks.Length}/{fullCount} canonical checks selected");
        }
        int failed = 0;
        foreach (var (name, check) in checks)
        {
            try { check(); Console.WriteLine($"PASS: {name}"); }
            catch (Exception error) { failed++; Console.WriteLine($"FAIL: {name}: {error}"); }
        }
        Console.WriteLine($"Engine runtime checks: {checks.Length - failed} passed, {failed} failed");
        return failed == 0 ? 0 : 1;
    }

    private static GeneratedProjectile Attach(Projectile projectile)
    {
        var generated = new GeneratedProjectile();
        // tML normally owns this association. Only wire the real host object;
        // do not replace engine methods, formulas, models or collision types.
        typeof(ModType<Projectile>).GetProperty("Entity",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
            .SetValue(generated, projectile);
        return generated;
    }

    private static RuntimeEntitySpec Entity()
    {
        var entity = new RuntimeEntitySpec();
        entity.Damage.Enabled = true;
        entity.Damage.Damage = 100;
        entity.Damage.DamageClass = "generic";
        entity.Damage.Knockback = 3f;
        return entity;
    }

    private static void Equal<T>(T expected, T actual, string label)
    {
        if (!System.Collections.Generic.EqualityComparer<T>.Default.Equals(expected, actual))
            throw new InvalidOperationException($"{label}: expected {expected}, actual {actual}");
    }

    private static void SpawnDamageSurvivesConfigure()
    {
        foreach (int damage in new[] { 0, 25, 100, 200 })
        {
            // State handed to Configure by NewProjectileDirect after applying
            // the exact event multiplier. Zero damage is deliberate, not absent.
            var projectile = new Projectile { damage = damage, knockBack = 3f };
            Attach(projectile).Configure(new GeneratedItemData(), Entity(), 0, 8, Vector2.UnitX);
            Equal(damage, projectile.damage, "spawn damage");
            Equal(damage, projectile.originalDamage, "spawn originalDamage");
            foreach (bool enabled in new[] { false, true })
            foreach (bool hydrated in new[] { false, true })
            foreach (int delay in new[] { 0, 2 })
            {
                var child = Entity(); child.Kind = RuntimeEntityKind.ChildProjectile;
                child.Damage.Enabled = enabled; child.Damage.Damage = 0;
                child.Spawn.OverTarget.DelayTicks = delay;
                var live = new Projectile { active = true, damage = damage, originalDamage = damage,
                    knockBack = 3f, timeLeft = 60, velocity = Vector2.UnitX };
                var host = Attach(live);
                if (hydrated) typeof(GeneratedProjectile).GetField("_activationDelayTicks",
                    BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(host, delay);
                host.Configure(new GeneratedItemData(), child, 0, 8, Vector2.UnitX, preserveSyncedState: hydrated);
                Equal(enabled && damage > 0 && delay == 0, live.friendly, "live child collision eligibility at configuration");
                for (int tick = 0; tick < delay; tick++) host.AI();
                Equal(enabled && damage > 0, live.friendly, "live child collision eligibility after activation delay");
            }
        }
    }

    private static void ActivationDelayPreservesVelocity()
    {
        foreach (int extraUpdates in new[] { 0, 2 })
        {
            Vector2 velocity = new(6f, -8f);
            var projectile = new Projectile { damage = 100, velocity = velocity };
            var generated = Attach(projectile);
            var entity = Entity();
            entity.Kind = "free_projectile";
            entity.LifetimeTicks = 60;
            entity.Spawn.OverTarget.DelayTicks = 3;
            entity.Spawn.SpeedPxPerTick = 10f;
            entity.Spawn.Aim = "velocity";
            entity.Collision.ExtraUpdates = extraUpdates;
            generated.Configure(new GeneratedItemData(), entity, 0, 8, velocity.SafeNormalize(Vector2.UnitX));
            int delayUpdates = 3 * (extraUpdates + 1);
            for (int update = 0; update < delayUpdates; update++)
            {
                generated.AI();
                Equal(Vector2.Zero, projectile.velocity, "no movement during activation delay");
                projectile.timeLeft--;
            }
            generated.AI();
            Equal(velocity, projectile.velocity, "velocity on first active update");
        }
    }

    private static void ActivationRespectsZeroMotion()
    {
        foreach (var choice in new[] {
            (Kind: "free_projectile", Aim: "none", Speed: 10f),
            (Kind: "free_projectile", Aim: "velocity", Speed: 0f),
            (Kind: "stationary_projectile", Aim: "velocity", Speed: 10f),
        })
        {
            var projectile = new Projectile { damage = 100 };
            var generated = Attach(projectile);
            var entity = Entity();
            entity.Kind = choice.Kind;
            entity.LifetimeTicks = 60;
            entity.Spawn.Aim = choice.Aim;
            entity.Spawn.SpeedPxPerTick = choice.Speed;
            entity.Spawn.OverTarget.DelayTicks = 2;
            generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
            for (int update = 0; update < 3; update++) generated.AI();
            Equal(Vector2.Zero, projectile.velocity, "explicit zero/stationary launch");
        }
    }

    private static void ActivationDoesNotRelaunchLiveState()
    {
        foreach (bool lateHydration in new[] { false, true })
        {
            Vector2 liveVelocity = new(2f, 3f);
            var projectile = new Projectile { damage = 100, velocity = liveVelocity, timeLeft = 100 };
            var generated = Attach(projectile);
            var entity = Entity();
            entity.Kind = "free_projectile";
            entity.Spawn.Aim = "velocity";
            entity.Spawn.SpeedPxPerTick = 10f;
            entity.Spawn.OverTarget.DelayTicks = lateHydration ? 3 : 0;
            // Model the already-received ExtraAI age; no networking is claimed.
            if (lateHydration)
                typeof(GeneratedProjectile).GetField("_age", BindingFlags.Instance | BindingFlags.NonPublic)!
                    .SetValue(generated, 12);
            generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX, preserveSyncedState: lateHydration);
            generated.AI();
            Equal(liveVelocity, projectile.velocity, "no unsolicited velocity reset");
        }
    }

    private static int PendingActions()
        => ((System.Collections.ICollection)typeof(RuntimeDelayedActionScheduler)
            .GetField("Pending", BindingFlags.Static | BindingFlags.NonPublic)!
            .GetValue(null)!).Count;

    private static void ExpiryWaitsForFinalUpdate()
    {
        Player previous = Terraria.Main.player[0];
        // Scheduling only consumes player identity/activity; no inventory,
        // graphics, world or ModPlayer initialization is needed for this seam.
        var owner = (Player)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Player));
        owner.active = true;
        owner.whoAmI = 0;
        Terraria.Main.player[0] = owner;
        RuntimeDelayedActionScheduler.Clear();
        try
        {
            var projectile = new Projectile { damage = 100, owner = 0 };
            var generated = Attach(projectile);
            var entity = Entity();
            entity.LifetimeTicks = 60;
            entity.Events = new[] { new RuntimeEventActionSpec {
                Id = "expiry", Event = RuntimeEventKind.OnExpire,
                ActionCode = RuntimeEventActionCode.DamageArea, DelayTicks = 1, RadiusPx = 16,
            } };
            generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
            // Controllers such as channel beam keep renewing this value.
            for (int update = 0; update < 3; update++)
            {
                projectile.timeLeft = 2;
                generated.AI();
                Equal(0, PendingActions(), "no expiry while lifetime is renewed");
            }
            projectile.timeLeft = 1;
            generated.AI();
            Equal(1, PendingActions(), "expiry action on final update");
            generated.OnKill(0);
            Equal(1, PendingActions(), "expiry action is not duplicated by OnKill");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = previous;
        }
    }

    private static void HitboxSizingPreservesCenter()
    {
        foreach (var size in new[] { (4, 4), (48, 24), (191, 95) })
        {
            var projectile = new Projectile { width = 12, height = 12, damage = 100 };
            Vector2 center = new(320.5f, 160.25f);
            projectile.Center = center;
            var generated = Attach(projectile);
            var entity = Entity();
            entity.Hitbox.WidthPx = size.Item1;
            entity.Hitbox.HeightPx = size.Item2;
            var data = new GeneratedItemData();
            generated.Configure(data, entity, 0, 8, Vector2.UnitX);
            Equal(center, projectile.Center, "spawn center after hitbox configuration");
            Equal(size.Item1, projectile.width, "authored hitbox width");
            Equal(size.Item2, projectile.height, "authored hitbox height");
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal(center, projectile.Center, "rehydrated center");
        }
    }

    private static void CombatStateSurvivesRehydration()
    {
        var projectile = new Projectile { damage = 100, knockBack = 3f };
        var generated = Attach(projectile);
        var data = new GeneratedItemData();
        var entity = Entity();
        generated.Configure(data, entity, 0, 8, Vector2.UnitX);
        // A charged projectile already has updated combat fields when ExtraAI
        // resolves its entity. Reattaching metadata must not undo the charge.
        projectile.damage = 250;
        projectile.knockBack = 7.5f;
        for (int packet = 0; packet < 3; packet++)
        {
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal(250, projectile.damage, "synced damage");
            Equal(100, projectile.originalDamage, "original damage baseline");
            Equal(7.5f, projectile.knockBack, "synced knockback");
        }
    }
}
