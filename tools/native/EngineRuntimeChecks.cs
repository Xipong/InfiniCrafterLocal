// Headless behavioral checks against the actual mod source and tModLoader types.
// This executable never starts Terraria.Main, loads a world, or initializes graphics.
// Run with existing dependencies (no model requests, no tML packaging tasks):
// dotnet run --project tools/native/EngineRuntimeChecks.csproj \
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
            ("projectile angle fresh remote hydration", ProjectileAngleFreshRemoteHydration),
            ("projectile raw impact native pose witness", ProjectileRawImpactKeepsLiteralNativePose),
            ("projectile angle boundary native storage and authored forward", ProjectileAngleBoundaryPreservesNativeStorage),
            ("parent source graph unresolved identity alternatives", ParentSourceGraphKeepsUnresolvedIdentityAlternatives),
            ("parent source graph native projectile windows", ParentSourceGraphFollowsNativeProjectileWindows),
            ("parent source graph conditional native buff consumers", ParentSourceGraphKeepsConditionalNativeBuffConsumers),
            ("parent source graph conditions events and reachable helpers", ParentSourceGraphKeepsReachabilityConditionsAndEventOwnership),
            ("parent mod hit hook source statements without execution", ParentHitHooksPreserveSourceRequestsWithoutExecution),
            ("parent mod buff source data links without execution", ParentModBuffSourceLinksWithoutExecution),
            ("native parent tooltip hooks", ParentTooltipRunsNativeHooks),
            ("journal lifecycle without draw", JournalSessionRetiresWithoutDrawing),
            ("parent fixed spawn source native oracle", ParentFixedSpawnFactsMatchNativeBranchAndRequest),
            ("parent ammo inventory observation unknown versus empty", ParentAmmoInventoryObservationDistinguishesUnavailableAndEmpty),
            ("parent environment references conditional fail closed", ParentEnvironmentReferencesAreConditionalAndFailClosed),
            ("parent banner registry matches native conditional components", ParentBannerRegistryMatchesConditionalNativeComponents),
            ("parent equipment source pieces and conditional sets", ParentEquipmentFactsSeparatePiecesAndConditionalSets),
            ("parent armor set source mixed and incomplete variants", ParentArmorSetConditionsAgreeWithNativeMixedAndIncompleteSets),
            ("parent contact status native item target signature", ParentContactStatusFactsKeepNativeItemAndTargetSignature),
            ("parent attack source certificates match native shooting collision", ParentAttackCertificatesMatchNativeShootingAndCollision),
            ("parent quantified snapshots and ammo observation identity", ParentQuantifiedFactsKeepSnapshotsAndObservationIdentity),
            ("parent native item scale penetration and use limit", ParentNativeItemStatsSurviveCaptureAndNormalization),
            ("runtime dump shares complete parent and projectile capture", RuntimeDumpSharesCompleteParentAndProjectileCapture),
            ("runtime dump preserves capture failures as explicit unavailable rows", RuntimeDumpKeepsCaptureFailuresAsExplicitRows),
            ("parent complete projectile attack source reaches live and dump", ParentProjectileAttackSemanticsReachPrepareAndDump),
            ("projectile attack source symbolic dependencies and predicates", ProjectileAttackSourceObservationsKeepExpressionsAndPredicates),
            ("projectile attack shared AI selection before source budgets", ProjectileSharedAiCaptureSelectsBeforeSourceBudgets),
            ("projectile attack position integration identity selection", ProjectilePositionIntegrationSelectsEntryIdentity),
            ("projectile attack discarded identity alternatives disclosure", ProjectileDiscardedIdentityAlternativesAreDisclosed),
            ("projectile attack identity specialization receiver and mutation safety", ProjectileAttackIdentitySelectionKeepsUnknownConditions),
            ("projectile attack native dispatch and source sibling controls", ProjectileAttackNativeDispatchAndSiblingWitnesses),
            ("parent identity window refusal diagnostics", ParentIdentityWindowRefusalDiagnostics),
            ("parent native geometry helper semantic equivalence", ParentNativeGeometryHelperRulesMatchSource),
            ("parent native arrow motion source execution oracle", ParentNativeArrowMotionMatchesSelectedSource),
            ("parent native position integration execution oracle", ParentNativePositionIntegrationMatchesLiveGuards),
            ("parent native excluded integration cases execution oracle", ParentNativeExcludedIntegrationCasesMatchDisclosure),
            ("parent native growing arc motion and cone union oracle", ParentNativeGrowingArcMatchesRealMotionAndConeUnion),
            ("parent random status mutually exclusive native outcomes", ParentRandomStatusFactsMatchExclusiveNativeOutcomes),
            ("dropped alpha support exact rotated pixels", DroppedAlphaSupportTracksActualRotatedPixels),
            ("held native owner rejects removed pose controls", HeldNativeOwnerRejectsRemovedPoseControls),
            ("held contact preserves authored projectile reach", HeldContactCorrectionDoesNotCancelAuthoredReach),
            ("journal hotkey trigger lifecycle", JournalHotkeyToleratesTriggerLifecycle),
            ("coincident seek finite motion and exact retirement", CoincidentSeekPreservesFiniteMotionAndExplicitRetirement),
            ("single-active weapon admission without chat warning", SingleActiveWeaponBusyKeepsAdmissionWithoutChatWarning),
            ("composable motion review manual release VFX roundtrip", ComposableMotionManualReleaseVfxRoundtrip),
            ("composable motion review automatic completion VFX roundtrip", ComposableMotionAutomaticCompletionVfxRoundtrip),
            ("composable motion review authenticated release source fences", ComposableMotionReleaseVfxKeepsAuthenticatedSourceFences),
            ("composable motion review legacy charge server route", ComposableMotionLegacyChargeVfxKeepsServerRoute),
            ("composable motion review impact event rotation", ComposableMotionImpactEventRotation),
            ("composable motion review impact event hand attachment", ComposableMotionImpactEventHandAttachment),
            ("composable motion review impact periodic rotation", ComposableMotionImpactPeriodicRotation),
            ("composable motion review impact periodic hand attachment", ComposableMotionImpactPeriodicHandAttachment),
            ("composable motion review impact periodic scale rate", ComposableMotionImpactPeriodicScaleRate),
            ("composable motion review impact periodic hand curve", ComposableMotionImpactPeriodicHandCurve),
            ("composable motion independent hand pose attachment and reach admission", ComposableMotionHandAttachmentAdmission),
            ("lateral oscillation exact u1 and saved legacy", LateralOscillationPreservesU1AndLegacy),
            ("lateral oscillation nonlinear substep matrix", LateralOscillationNonlinearSubstepMatrix),
            ("lateral oscillation world time windows and angular parity", LateralOscillationWorldTimeAndWindow),
            ("lateral oscillation native trajectory convergence", LateralOscillationTrajectoryConvergence),
            ("velocity scale late phases and saved legacy", VelocityScaleLatePhasesAndLegacy),
            ("velocity scale admission and subupdates", VelocityScaleNativeAdmissionAndSubupdates),
            ("composable motion ForcesAndIndependentPresentation", ComposableMotionForcesAndIndependentPresentation),
            ("composable motion AttachmentPoseAndReach", ComposableMotionAttachmentPoseAndReach),
            ("composable motion TimedReturnNoHiddenController", ComposableMotionTimedReturnNoHiddenController),
            ("composable motion FreeBeamAndLashGeometry", ComposableMotionFreeBeamAndLashGeometry),
            ("composable motion PhaseOnlyAttachmentAndReleasedModifiers", ComposableMotionPhaseOnlyAttachmentAndReleasedModifiers),
            ("composable motion OrbitConsumesTilePolicyAndOwnerControl", ComposableMotionOrbitConsumesTilePolicyAndOwnerControl),
            ("composable motion ProximityWithoutSteering", ComposableMotionProximityWithoutSteering),
            ("composable motion ChargeReleaseAndHydration", ComposableMotionChargeReleaseAndHydration),
            ("composable motion phase-only spin advances every update", ComposableMotionPhaseOnlySpinAdvancesEveryUpdate),
            ("composable motion tile return retains first relative update", ComposableMotionTileReturnRelativeWindowRetainsFirstStep),
            ("composable motion free presentation does not cancel with owner", ComposableMotionFreePresentationDoesNotImplyOwnerCancellation),
            ("composable motion ExpiryReceiptNativeOrderAndServerOnceOnly", ComposableMotionExpiryReceiptNativeOrderAndServerOnceOnly),
            ("composable motion ExpiryReceiptRejectsUnsupportedGeometryAndCause", ComposableMotionExpiryReceiptRejectsUnsupportedGeometryAndCause),
            ("composable motion ExpiryReceiptWaitsForActualDefinition", ComposableMotionExpiryReceiptWaitsForActualDefinition),
            ("composable motion ExpiryReceiptUsesEventClockWithoutRewindingServer", ComposableMotionExpiryReceiptUsesEventClockWithoutRewindingServer),
            ("composable motion FirstHydratedServerStillProducesSpawnVfx", ComposableMotionFirstHydratedServerStillProducesSpawnVfx),
            ("projectile first hydration preserves native top-left", FirstProjectileHydrationPreservesNativeTopLeft),
            ("visual scale window local rehydration", VisualScaleWindowLocalRehydration),
            ("visual scale native snapshot fresh and late peers", VisualScaleNativeSnapshotFreshAndLatePeers),
            ("visual scale snapshot authority and replay", VisualScaleSnapshotAuthorityAndReplay),
            ("visual scale snapshot strict component ownership and bounds", VisualScaleSnapshotStrictOwnershipAndBounds),
            ("beam axial origin preserves length and shared consumers", BeamAxialOriginPreservesLengthAndSharedConsumers),
            ("beam axial origin raycast preserves shifted start and length budget", BeamAxialOriginRaycastRetainsOffsetStartAndLengthBudget),
            ("beam axial origin strict admission and historical absence", BeamAxialOriginAdmissionIsStrictAndHistoricalAbsenceRoundtrips),
            ("composable motion beam VFX snapshot uses actual line", ComposableMotionBeamVfxSnapshotUsesActualLine),
            ("composable motion scale-rate snapshot preserves explicit scale", ComposableMotionScaleRateSnapshotPreservesSmallExplicitScale),
            ("free projectile sprite trail preserves explicit body scale", FreeProjectileSpriteTrailPreservesExplicitBodyScale),
            ("composable motion absolute tile policy requires reachable consumer", ComposableMotionAbsoluteTilePolicyRequiresReachableConsumer),
            ("generated use refusal admission and localization", GeneratedUseRefusalsKeepExactAdmissionAndLocalization),
            ("generated use refusal owner throttle and authority", GeneratedUseNoticesThrottlePerOwnerAndRespectAuthority),
            ("UI QoL hotkey input focus and compact journal controls", JournalHotkeyAndCompactControlsStayScoped),
        ("atlas focus ownership overlay resume and world cleanup", AtlasFocusAndOverlayResumeStayScoped),
        ("deferred refund malformed row isolation", DeferredRefundLoadIsolatesMalformedRows),
            ("utility death duration policy and dead snapshot filtering", UtilityDeathClearsContributions),
            ("utility death delayed action retirement", DelayedUtilityCannotCrossLife),
            ("generated buff long and permanent lifetimes", GeneratedBuffLongAndPermanentLifetimes),
            ("generated buff long and permanent duration presentation", GeneratedBuffDurationPresentation),
            ("UI QoL compact tooltip critical inputs and Shift expansion", CompactTooltipsKeepInputsAndLockoutsAndExpandWithEitherShift),
            ("audit escrow take acknowledgement preserves changed cursor", EscrowTakeAcknowledgementPreservesChangedCursor),
            ("audit sentry original damage selected prefixed base", SentryOriginalDamageUsesSelectedPrefixedBase),
            ("charge presentation actual clock ExtraAI and once-only ready cue", ChargePresentationReadsActualClockAndSignalsOnce),
            ("charge presentation localized caption and viewport bounds", ChargePresentationBoundsAndLocalization),
            ("projectile controls independent charge channels and hydration", IndependentChargeScalesThreeChannelsOnce),
            ("projectile controls signed world orbit and extra updates", OrbitWorldRateIsIndependentOfExtraUpdates),
            ("projectile controls collided-axis bounce retention", BounceRetentionChangesOnlyCollidedAxes),
            ("projectile controls strict DTO and retained absence", ProjectileControlDtoRejectsInvalidPresentAndKeepsOldAbsence),
            ("journal world history favorites and responsive bounds", RecipeJournalKeepsWorldIdentityAndFavorites),
            ("atlas drawing native pixel alpha and text alignment", AtlasDrawingUsesBoundedPixelsAndCenteredText),
            ("atlas book controls responsive bounds and scaled hit areas", AtlasBookControlsStayReachableAcrossUiScales),
            ("atlas discovery search favorites filters and exact ancestry", AtlasDiscoverySelectionKeepsSearchFavoritesAndAncestry),
            ("atlas detail lineage navigation restores discovery context", AtlasDetailLineageNavigationPreservesReturnLocation),
            ("lineage exact identity bounded DAG and routing", RecipeLineageUsesExactBoundedDag),
            ("lineage localization native filename prefix", LineageLocalizationUsesNativeFilenamePrefix),
            ("lineage viewport anchored zoom bounded pan and scaled hit targets", LineageViewportKeepsAnchorAndReachableHitTargets),
            ("lineage input overlay release and focus ownership", LineageInputReleasesOwnedFocusAcrossInterruptions),
            ("lineage native hover deferred browser handoff ownership", LineageNativeHoverAndDeferredHandoffKeepOwnership),
            ("lineage bounded adversarial layout cost", LineageBoundedStressReportsActualLayoutCost),
            ("lineage native identity exact registered items", LineageNativeIdentityResolvesOnlyExactRegisteredItems),
            ("input-local independent conditions", InputLocalConditionsStayIndependent),
            ("parent hit status facts certified native source", ParentHitStatusFactsAreCertifiedAndMatchNativeRequests),
            ("parent buff effects source certified and parent local", ParentBuffEffectsAreSourceCertifiedAndParentLocal),
            ("parent ammo source semantics actual Prepare", ParentAmmoSourceSemanticsReachPrepare),
            ("parent ammo mod hook shapes read without execution", ParentAmmoModHookShapesAreInspectedNotExecuted),
            ("parent ammo mixed hooks native phase order", ParentAmmoMixedHooksKeepNativePhaseOrder),
            ("use input scope strict DTO and legacy roundtrip", UseInputScopeDtoRoundtripAndStrictAdmission),
            ("use input scope delayed provenance and authority", UseInputScopeRoutesOnceAndRetainsDelayedAdmission),
            ("use input scope native mana payment", ManaInputScopeUsesNativePaymentOnly),
            ("use input scope preserves prefix and quick-use identity", ManaInputScopeKeepsPrefixAndQuickUseIdentity),
            ("use input scope disjoint static budgets", UseInputScopeBudgetKeepsDisjointUsesIndependent),
            ("target controller authored motion and firing", TargetAndFireCombinesMotionAndFiring),
            ("target controller explicit launch and delayed activation", TargetAndFireLaunchAndDelayKeepExplicitMotion),
            ("target controller cancelled movement cannot fire", TargetAndFireCancelledMovementDoesNotFire),
            ("target controller free-child serialized composition", TargetAndFireAdmitsAndExecutesFreeAndChildMotion),
            ("combat buff lifecycle native stats wire and HUD", GeneratedCombatBuffLifecycleAndWire),
            ("reactive equipment delayed admission authority and cooldown", EquipmentReactionsUseFunctionalHooksAndSharedCooldown),
            ("reaction cooldown presentation functional identity and read-only timers", ReactionCooldownPresentationKeepsFunctionalIdentityAndTimers),
            ("reaction cooldown presentation actual HUD fitted item sprite", ReactionCooldownPresentationReachesActualHudWithFittedSprite),
            ("reactive utility buffs authority aggregation cooldown and exhaustion", ReactiveUtilityBuffUsesEquipmentAuthorityAndCooldown),
            ("reactive utility buffs exact DTO group ownership", ReactiveUtilityBuffDtoKeepsExactGroupOwnership),
            ("reactive utility buffs localized exact tooltip effects", ReactiveBuffTooltipShowsAcceptedEffectsAndCooldown),
            ("reactive utility buffs canonical server snapshot owner correction", ReactiveUtilityCanonicalServerSnapshotSurvivesOwnerCorrection),
            ("equipment periodic gameplay native spawn", EquipmentPeriodicGameplayReachesNativeSpawn),
            ("equipment periodic gameplay authority and delay", EquipmentPeriodicGameplayKeepsAuthorityAndDelay),
            ("equipment presentation carrier native frame bounds", EquipmentCarrierSheetsCoverNativeFrames),
            ("visible vanity slots cannot illuminate world", VisibleVanityCannotEmitWorldLight),
            ("equipment presentation front back native layer tree", EquipmentAccessoryLayersKeepMountsDyesAndVisibility),
            ("equipment presentation native displayed carrier selection", EquipmentNeutralCarrierUsesNativeDisplayedSelection),
            ("equipment presentation native clothes hair and source rectangles", EquipmentNeutralBaseDrawsNativeClothesAndHair),
            ("VFX retired metadata strict refusal", VfxRetiredMetadataRefuses),
            ("persisted v5 historical metadata preserves mechanics", PersistedV5MetadataDoesNotOwnGameplay),
            ("persisted v5 executable VFX15 refuses instead of semantic reconstruction", PersistedV15ExecutableSlotsRefuseWithoutReconstruction),
            ("persisted v5 empty VFX15 ignores motif and effectColor", PersistedV15EmptyMotifAndEffectColorAreOpaque),
            ("persisted v5 current VFX16 preserves baked RGB", PersistedV16BakedColorsStayAuthoritative),
            ("persisted v5 unknown executable fields refuse", PersistedV5UnknownExecutableFieldsStillRefuse),
            ("persisted v5 current exact pass through", PersistedV5CurrentFormatIsExactPassThrough),
            ("persisted v5 registry read only world fence", PersistedV5RegistryLoadsReadOnlyAndKeepsWorldFence),
            ("OwnerLinkWireAdmission", OwnerLinkWireAdmission),
            ("OwnerLinkLiveClientGeometryAndRetirement", OwnerLinkLiveClientGeometryAndRetirement),
            ("OwnerLinkFnaMeshControls", OwnerLinkFnaMeshControls),
            ("VFX branch fields exact presence current selectors and impact canvas", VfxBranchControlsHaveExactPresenceAndCurrentSelectors),
            ("VFX local RGB strict admission serialization and retirement", VfxLocalRgbAdmissionAndSerialization),
            ("VFX local RGB actual native simple consumers", VfxLocalRgbReachesSimpleNativeConsumers),
            ("VFX local RGB textured path native vertices", VfxLocalRgbTexturedPathCopiesIndependentRamp),
            ("Visual descriptive palette Unicode roundtrip", VisualDescriptivePaletteRoundtrip),
            ("played silver final delivery native RGB and captured material consumers", PlayedSilverFinalDeliveryAndNativeColorConsumers),
            ("descriptive parent advisory prose Unicode roundtrip", DescriptiveParentProseRoundtrip),
            ("descriptive authored name Unicode persistence roundtrip", AuthoredNameUnicodePersistenceRoundtrip),
            ("localized generated tooltip width wrapping without content loss", GeneratedTooltipWidthWrapPreservesFullLocalizedFacts),
            ("descriptive art captions Unicode roundtrip", DescriptiveArtCaptionsUnicodeRoundtrip),
            ("two-body pull independent authority target loss and boss resistance", BothPullKeepsIndependentAuthorityAndDirectTarget),
            ("nearby damage deterministic nearest ranking and cap", NearbyDamageRanksNearestWithDeterministicCap),
            ("nearby damage tooltip requires explicit cap without fallback", NearbyDamageTooltipUsesExplicitCapWithoutFallback),
            ("composable NPC effect admission", ComposableNpcEffectAdmission),
            ("composable NPC effect native consumers", ComposableNpcEffectExecutesWithoutStatMutation),
            ("composable NPC effect owner receipt", ComposableNpcEffectOwnerReceipt),
            ("composable NPC effect strict refusals", ComposableNpcEffectStrictRefusals),
            ("composable NPC effect lifecycle and peer synchronization", ComposableNpcEffectLifecycleAndSync),
            ("composable NPC effect probability single admission", ComposableNpcEffectChanceAdmissionAndNoReroll),
            ("composable NPC effect item receipt and delayed fences", ComposableNpcEffectItemReceiptAndDelayedFences),
            ("composable NPC effect compiled wire replay", ComposableNpcEffectCompiledWireReplay),
            ("composable NPC effect tooltip generated semantics", ComposableNpcEffectTooltipUsesGeneratedSemantics),
            ("signed generated buff admission", SignedGeneratedBuffAdmission),
            ("signed generated buff consumers and presentation", SignedGeneratedBuffConsumersAndPresentation),
            ("signed generated buff compiled wire and binary replay", SignedGeneratedBuffCompiledWireAndBinaryReplay),
            ("signed generated buff order-independent aggregation", SignedGeneratedBuffOrderIndependentAggregation),
            ("NPC hit pull preserves projectile origin", NpcHitPullPreservesProjectileOrigin),
            ("nearest event damage retains radial native selection and direct-target exclusion", NearestDamageRetainsTheSingleCenterNativeAction),
            ("target bias saved DTO range and native distance-score discount", TargetBiasKeepsSavedDtoDomainAndActualDistanceDiscount),
            ("signed vertical acceleration native DTO active updates and hydration", SignedVerticalAccelerationUsesNativeDtoAndEveryActiveUpdate),
            ("signed vertical acceleration activation delay and update rate", SignedVerticalAccelerationWaitsForActivationThenPreservesAuthoredRate),
            ("sampled launch strict DTO and old saved absence", SampledLaunchDtoRejectsInvalidAndPreservesOldAbsence),
            ("sampled velocity native spawn owner authority", SampledVelocityReachesNativeSpawnOnlyOnOwner),
            ("sampled velocity delay ExtraAI and hydration", SampledVelocityDelayExtraAiAndHydrationPreserveChosenVector),
            ("late definition retains latest native projectile velocity", LateDefinitionRetainsLatestNativeProjectileVelocity),
            ("repeated projectile hydration retains spent penetration", RepeatedProjectileHydrationRetainsSpentPenetration),
            ("hit target delayed native boundary and reservation ownership", HitTargetDelayedNativeBoundaryAndReservationOwnership),
            ("initial NPC exclusion exact incarnation and counter", InitialNpcExclusionUsesExactIncarnationAndCounter),
            ("retirement projectile old ExtraAI refused and current remaining retained", InitialNpcExclusionExtraAiPreservesRemainingAndOldAbsence),
            ("retirement movement six reserved without renumbering", RetiredMovementSixIsReservedNotRenumbered),
            ("native DTO retirement controller bag and typed cadence", NDTO01RetiredControllerBagRefusesAndTypedCadenceExecutes),
            ("native DTO retirement single buff and current ExtraBuffs", NDTO02SingleBuffRefusesAndCurrentExtraBuffsExecute),
            ("native DTO retirement sound absence and native consumers", NDTO03OldSoundAbsenceRefusesBeforeAudioConsumers),
            ("native DTO retirement current utility snapshot and mirror", NDTO04CurrentUtilitySnapshotAndCopyMirrorRemainSupported),
            ("native DTO retirement dead knowledge and advisory summary", NDTO05RetiredKnowledgeAndSummaryRefuse),
            ("explicit spawn transform native boundary", ExplicitSpawnTransformRejectsInvalidBeforeNativeBoundary),
            ("target emission anchor and repeat policies", TargetEmissionPlannerUsesExplicitAnchorsAndRepeatPolicy),
            ("target emission inclusive range ties and LOS", TargetEmissionPlannerUsesInclusiveRangeExactTiesAndLos),
            ("target emission real hit authority stats and reservations", TargetEmissionRealHitHookKeepsAuthorityStatsAndReservation),
            ("target emission ordinary refusal and child collision", TargetEmissionNormalRefusalsReturnUnspentPlanBudget),
            ("target emission delayed NPC incarnation and refunds", TargetEmissionDelayedDispatchRequiresSameActiveNpcAndRefundsCancellation),
            ("hitbox raw numeric outside domain", HitboxRawNumericDomainRefusesOutsideBeforeNarrowing),
            ("hitbox curve actual rectangle and world-tick clock", HitboxCurveActualDamageRectAndWorldTickClock),
            ("hitbox curve explicit visual mirror and hydration", HitboxCurveExplicitVisualMirrorAndLateHydration),
            ("modifier unified timing admission and roundtrip", ModifierTimingAdmissionAndRoundtrip),
            ("modifier unified timing equivalent and intersection", ModifierUnifiedTimingEquivalentAndIntersection),
            ("modifier unified timing late relative and phase only", ModifierUnifiedTimingLateRelativeAndPhaseOnly),
            ("modifier unified timing NPC consumers", ModifierUnifiedTimingNpcConsumers),
            ("motion modifiers actual phase and visual hydration", ModifierActualTurnSpeedPhaseAndVisualHydration),
            ("NPC attraction authority falloff and bounds", ModifierNpcAttractionAuthorityFalloffAndBounds),
            ("homing modifier owner selection and speed", ModifierHomingOwnerSelectionAndSpeedPreservation),
            ("whip gravity actual collision polyline", ModifierWhipGravityUsesTheSameCollisionPolyline),

            ("bugfix251 grounded native support", GroundedConditionRequiresNativeSupport),
            ("VFX sound selector native item projectile consumers", VfxSoundSelectorReachesItemAndProjectileNativeBoundary),
            ("VFX sound selector silence and server controls", VfxSoundSelectorPreservesSilentAndServerControls),
            ("VFX explicit sound owns pitch and preserves native policies", VfxSoundControlsOwnPitchAndPreserveNativePolicies),
            ("quality250 NativeDirectUseStackCostIsLiteralUnderSaving", NativeDirectUseStackCostIsLiteralUnderSaving),
            ("own-stack chance one completed activation", NativeOwnStackChanceUsesOneCompletedActivation),
            ("quality250 NativeQuickHealStackCostUsesPrimaryUnderSaving", NativeQuickHealStackCostUsesPrimaryUnderSaving),
            ("RT02 NativeQuickUtilityFreshInventoryAndVoidWitness", RT02NativeQuickUtilityFreshInventoryAndVoidWitness),
            ("RT02 NativeQuickUtilityWriterServerRemote", RT02NativeQuickUtilityWriterServerRemote),
            ("RT02 NativeQuickUtilityAuthorityFences", RT02NativeQuickUtilityAuthorityFences),
            ("quality250 NativeLiteralStackCostKeepsMobilityAndPlacementGates", NativeLiteralStackCostKeepsMobilityAndPlacementGates),
            ("quality250 NativePickAmmoSavingRemainsIndependentOfDirectStackCost", NativePickAmmoSavingRemainsIndependentOfDirectStackCost),
            ("quality250 NativeFloat32BuffNearNeutralIdentityAndExpiry", NativeFloat32BuffNearNeutralIdentityAndExpiry),
            ("persistence PlacementPrefixServerSnapshotSurvivesEscrowSaveAndReturn", PlacementPrefixServerSnapshotSurvivesEscrowSaveAndReturn),
            ("persistence PlacementReturnFullPoolKeepsDurableOwnerWithoutAllocation", PlacementReturnFullPoolKeepsDurableOwnerWithoutAllocation),
            ("persistence PlacementPrefixMalformedIdentityIsDurableAndLegacyIsUnprefixed", PlacementPrefixMalformedIdentityIsDurableAndLegacyIsUnprefixed),
            ("cancelled craft reconnect resolves only owned journal", CancelledCraftReconnectResolvesOnlyOwnedJournal),
            ("persistence EscrowSessionTokenRotationAndConcurrentClaimRefused", EscrowSessionTokenRotationAndConcurrentClaimRefused),
            ("persistence EscrowSessionReconnectCommitAndReload", EscrowSessionReconnectCommitAndReload),
            ("persistence EscrowCommitRejectsFullWorldPoolBeforeAllocation", EscrowCommitRejectsFullWorldPoolBeforeAllocation),
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
            ("dynamic projectile pierce preserves native maximum and immunity", RuntimeDynamicPierceKeepsNativeMaximumAndImmunity),
            ("generated tooltips describe exact executable bindings", GeneratedTooltipsDescribeExactExecutableBindings),
            ("played tooltip speeds display only blocks per second", PlayedTooltipSpeedsAreDisplayOnlyBlocksPerSecond),
            ("played secondary tooltips exact delivered combat", PlayedSecondaryTooltipsDescribeExactDeliveredCombat),
            ("secondary tooltips unreachable events and bounded facts", SecondaryTooltipsRejectUnreachableEventsAndStayBounded),
            ("played stats seconds percent native equipment units", PlayedStatsUseSecondsCleanPercentAndNativeEquipmentUnits),
            ("played mobility cooldown independent read only status", PlayedMobilityCooldownIsIndependentReadOnlyStatus),
            ("EX exhaustion EX01DtoPresenceRawScopeAndIdentity", EX01DtoPresenceRawScopeAndIdentity),
            ("EX exhaustion EX02ConsumerSourceGateAndLegacyControls", EX02ConsumerSourceGateAndLegacyControls),
            ("EX exhaustion EX03FiveLabeledSourcesCopiesAndImmutableCapture", EX03FiveLabeledSourcesCopiesAndImmutableCapture),
            ("EX exhaustion EX04ActiveNativeUseKeepsHealCostAndTiming", EX04ActiveNativeUseKeepsHealCostAndTiming),
            ("EX exhaustion EX05HeldSourceAndAlternateCannotBypass", EX05HeldSourceAndAlternateCannotBypass),
            ("EX exhaustion EX06CapacityLifecycleAndActivationAnchor", EX06CapacityLifecycleAndActivationAnchor),
            ("EX exhaustion EX07RealUtilityCodecFiveRowsDiscardAndOwnerCorrection", EX07RealUtilityCodecFiveRowsDiscardAndOwnerCorrection),
            ("EX exhaustion EX08QuickCommitCanonicalPolicyAnchorAndRefusal", EX08QuickCommitCanonicalPolicyAnchorAndRefusal),
            ("EX exhaustion EX09 authoritative snapshot does not echo", EX09AuthoritativeRepeatedSnapshotDoesNotEcho),
            ("EX exhaustion EX10 expired quick buff retains independent fatigue", EX10QuickCommitExpiredBuffRetainsIndependentExhaustion),
            ("EX exhaustion EX11 exhausted quick use cannot revive at Commit", EX11QuickCommitCannotReviveAnExhaustedAttempt),
            ("EX exhaustion EX12 queued quick attempts preserve confirmed refusal", EX12QueuedQuickAttemptsKeepConfirmedExhaustionDecision),
            ("exhaustion presentation five definitions own names and ticks", ExhaustionPresentationFiveDefinitionsKeepOwnNamesAndTicks),
            ("exhaustion presentation exact localized definition tooltips", ExhaustionPresentationTooltipsAreExactLocalizedAndDefinitionScoped),
            ("exhaustion presentation actual HUD inventory draw boundary", ExhaustionPresentationReachesRealHudAndInventoryDrawBoundary),
            ("forge QoL authority observation is read only", ForgeQolAuthorityObservationCannotParkOrRestoreClaims),
            ("forge QoL readiness reports escrow not missing materials", ForgeQolReadinessReportsEscrowNotMissingMaterials),
            ("played mechanics alternate recall native mining isolation and restoration", PlayedAlternateEffectsIsolateAndRestoreNativeMining),
            ("played mechanics combined native tool actions retain all powers", PlayedNativeCombinedToolActionsRemainUsable),
            ("played mechanics native flail yoyo channel and code19 live aim consumers", PlayedFlailChannelAndCode19LiveAimMatchConsumers),
            ("generated native prefix survives active use", GeneratedItemNativePrefixSurvivesActiveUse),
            ("generated native prefix placement and ammo independence", GeneratedItemNativePrefixPlacementAndAmmoStayIndependent),
            ("retirement item old payload refused and current prefix hydration retained", GeneratedItemNativePrefixCompactHydration),
            ("generated root combat native lane contexts and query counts", GeneratedRootCombatNativeLanesAndQueryCounts),
            ("generated root combat terminal hold and source fence", GeneratedRootCombatTerminalHoldAndSourceFence),
            ("child combat current wire requires every active choice", ChildCombatCurrentWireRequiresEveryActiveChoice),
            ("child combat consumer rejects missing choices before budget admission", ChildCombatConsumerRefusesAbsentChoicesBeforeBudgetAdmission),
            ("child combat immediate events inherit exact current values once", ChildCombatImmediateEventsSelectLiveOrAuthoredStatsExactlyOnce),
            ("child combat delayed and charge events capture at admission", ChildCombatDelayedAndChargeEventsCaptureAtAdmission),
            ("child combat sentry firing and refused spawn reservations", ChildCombatSentryUsesCurrentParentAndRefusalsRefundBudget),
            ("dynamic collision preserves authored choice and return phase", RuntimeCollisionKeepsAuthoredChoiceAndReturnPhase),
            ("swarm charge keeps actual combat basis exactly once", SwarmChargeKeepsCombatBasisOnce),
            ("swarm delayed hooks honor world clock and wrap", SwarmDelayedHooksHonorWorldClock),
            ("swarm delayed eligibility shares canonical dispatch authority", SwarmDelayedAuthorityMatchesImmediateDispatch),
            ("local asset downloads keep generator origin separate from sharing URL", LocalAssetDownloadsKeepGeneratorOrigin),
            ("asset lifecycle reference world fence", AssetLifecycleReferenceWorldFence),
            ("asset lifecycle world scoped persistence", AssetLifecycleWorldScopedPersistence),
            ("asset lifecycle certified hydration coalesces", AssetLifecycleCertifiedHydrationCoalesces),
            ("asset lifecycle server descriptor replacement", AssetLifecycleServerDescriptorReplacement),
            ("asset lifecycle malformed definition packets", AssetLifecycleMalformedDefinitionPackets),
            ("runtime sprite LRU retains queued borrowers until owner drain", RuntimeSpriteLruRetainsQueuedBorrowersUntilOwnerDrain),
            ("runtime sprite worker Clear and Mod.Unload defer borrowed resources", RuntimeSpriteWorkerClearAndModUnloadDeferBorrowedResources),
            ("runtime sprite same filename invalidation reloads inventory without retiring queued texture", RuntimeSpriteInvalidationReloadsInventoryWithoutRetiringQueuedTexture),
            ("runtime sprite invalidation aliases use selected owner and backoff key", RuntimeSpriteInvalidationAliasesUseSelectedOwnerAndBackoffKey),
            ("runtime sprite invalidation Clear and Dispose fence pending retirement", RuntimeSpriteInvalidationClearAndDisposeFencePendingRetirement),
            ("runtime sprite inventory consumer follows certified asset byte owner", RuntimeSpriteConsumerUsesCertifiedAssetOwner),
            ("runtime sprite conflicting certificates preserve inventory ownership", RuntimeSpriteConflictingCertificatesPreserveInventoryOwnership),
            ("DOCX image readiness held producer missing and ready", () => HeldProxyIsReplacedOnlyByReadyInstanceSprite(true)),
            ("DOCX image readiness cursor missing and ready", () => CursorDeathRetiresGeneratedPreviewOnly(true)),
            ("DOCX image readiness VFX producer query alias", DocxVfxProducerQueryAliasMatchesAssetOwner),
            ("DOCX image readiness sibling producer status admission", DocxNativeSiblingProducerStatusesMatchDelivery),
            ("DOCX image readiness native producer status admission", DocxNativeItemReadyDomainRejectsUnfinishedProducer),
            ("DOCX image readiness query alias inventory and world", DocxReadyQueryAliasReachesInventoryAndWorld),
            ("DOCX image readiness missing failure and verified recovery", DocxMissingImageSuppressesProxyAndVerifiedCommitRecovers),
            ("DOCX image readiness explicit unavailable fixture controls", DocxExplicitUnavailableAndFixtureKeepDiagnosticProxy),
            ("runtime sprite selected owner failure backs off and retries", RuntimeSpriteSelectedOwnerFailureBacksOffAndRetries),
            ("individual material projectile owner and transport session reset", () => MaterialPeerSessionReset(false)),
            ("individual material Item owner and transport session reset", () => MaterialPeerSessionReset(true)),
            ("individual material runtime assets require exact ready domain", MaterialAssetsRequireExactReadyStatus),
            ("individual material unresolved Item forwarding retains transport token", MaterialUnresolvedItemForwardingRetainsToken),
            ("individual material nonowner live path stays local events await relay", MaterialNonownerPathRemainsLocalEventsAwaitRelay),
            ("individual material dead Item delay keeps world snapshot and source fence", MaterialDeadItemDelayKeepsWorldSnapshotAndFencesSource),
            ("individual material runtime motion and independent profiles", MaterialElementRuntimeMovesAndKeepsIndependentProfiles),
            ("individual material live source periodic final pose and generation", MaterialElementLiveSourcePeriodicUsesFinalPoseAndGeneration),
            ("individual material world delay versus source generation fence", MaterialElementDelayFreezesWorldButFencesSource),
            ("individual material item attachment uses instance identity", MaterialElementItemAttachmentUsesInstanceNotDefinition),
            ("individual material item periodic equipment slot transitions", MaterialItemPeriodicSurvivesEquipmentSlotTransitions),
            ("modded equipment native overlays visibility and dyes", EquipmentModdedAccessoryOverlayPreservesNativeSlots),
            ("modded equipment source VFX exact live slots", MaterialModdedAccessoryBindingUsesExactLiveSlot),
            ("individual material owner hit validated relay remote delivery", MaterialOwnerHitReachesValidatedServerRelayAndRemote),
            ("individual material item snapshot relay immutable pose and instance", MaterialItemSnapshotRelayPreservesPoseAndInstance),
            ("item event occurrences relay simple and mixed", ItemEventOccurrencesRelaySimpleAndMixed),
            ("item event network rate limit", ItemEventNetworkRateLimit),
            ("projectile hit occurrences stay distinct", ProjectileHitOccurrencesStayDistinct),
            ("remote projectile events have one producer", RemoteProjectileEventsHaveOneProducer),
            ("first held item event publishes token before claim", FirstHeldItemEventPublishesTokenBeforeClaim),
            ("individual material budgets share legacy active detached costs", MaterialBudgetsShareLegacyActiveAndDetachedCosts),
            ("individual material occurrence identity distinguishes hits and replay", MaterialOccurrencesKeepTwoRealHitsButRejectSameOccurrence),
            ("texture UV actual FNA full transform matrix", TextureUvActualQuadMatrixPreservesWorldGeometry),
            ("texture UV path repeat and immutable snapshot", TextureUvPathRepeatAndSnapshot),
            ("library material source authority and disabled backend", LibraryMaterialTypedAuthorityAndBackendIndependence),
            ("library palette readiness isolation and shared draw budget", LibraryPaletteReadinessAndSharedDrawBudget),
            ("library palette exact resource and immutable snapshot", LibraryPaletteExactResourceSnapshot),
            ("explicit ParticleLibrary readiness count capture and expiry", ExplicitLibraryReadinessWaitPreservesCountAndExpires),
            ("ParticleLibrary world pass scopes foreign water offset", LibraryWorldPassScopesForeignWaterOffset),
            ("spawn damage survives Configure", SpawnDamageSurvivesConfigure),
            ("live combat state survives rehydration", CombatStateSurvivesRehydration),
            ("hitbox sizing preserves spawn center", HitboxSizingPreservesCenter),
            ("activation delay preserves launch velocity", ActivationDelayPreservesVelocity),
            ("delayed activation runs spawn before native damage", DelayedActivationRunsSpawnBeforeNativeDamage),
            ("weapon ammo activation delay retains native shot and hydration", WeaponAmmoActivationDelayPreservesNativeShotAndHydration),
            ("weapon ammo delayed launch is per instance and producer", WeaponAmmoDelayedLaunchIsPerShotAndDoesNotLeakToOtherProducers),
            ("activation respects explicit zero motion", ActivationRespectsZeroMotion),
            ("activation does not relaunch live state", ActivationDoesNotRelaunchLiveState),
            ("expiry action waits for final update", ExpiryWaitsForFinalUpdate),
            ("placement ledger restores saved layers", PlacementLedgerRestoresSavedLayers),
            ("accessory defense is applied once", AccessoryDefenseAppliedOnce),
            ("generated accessory identity native admission", GeneratedAccessoryIdentityNativeAdmission),
            ("generated accessory identity native controls", GeneratedAccessoryIdentityNativeControls),
            ("generated accessory identity native quick equip", GeneratedAccessoryIdentityNativeQuickEquip),
            ("generated accessory identity native modded quick equip", GeneratedAccessoryIdentityNativeModdedQuickEquip),
            ("generated accessory identity native lifecycle", GeneratedAccessoryIdentityNativeLifecycle),
            ("movement buffs are order independent", MovementBuffOrderIndependent),
            ("mining buffs are order independent", MiningBuffOrderIndependent),
            ("equipment visibility uses armor slot", EquipmentVisibilityUsesArmorSlot),
            ("buff caps and refresh remain intact", BuffCapsAndRefreshRemainIntact),
            ("station key is not consumed", StationKeyIsNotConsumed),
            ("projectile light respects client setting", ProjectileLightRespectsClientSetting),
            ("item light respects client setting", ItemLightRespectsClientSetting),
            ("particle setting controls real dust", ParticleSettingControlsRealDust),
            ("draw setting controls existing budgets", DrawSettingControlsExistingBudgets),
            ("explicit trail saved beam lash tips", ExplicitTrailUsesSavedBeamAndLashTips),
            ("explicit trail world tick capture", ExplicitTrailCapturesWorldTicksWithoutFabrication),
            ("held history remote pending ordering", HeldHistoryRemotePendingOrdering),
            ("held history final pose and fences", HeldHistoryFinalPoseAndFences),
            ("explicit trail strict admission", ExplicitTrailAdmission),
            ("explicit trail geometry and pose", ExplicitTrailGeometryAndPose),
            ("VFX spawn strict admission and uniform projection", VfxSpawnAdmissionAndPureUniformProjection),
            ("VFX spawn element birth and attached coordinates", VfxSpawnElementBirthAndAttachedCoordinates),
            ("VFX spawn library actual birth and velocity", VfxSpawnLibraryActualBirthAndLegacyVelocity),
            ("VFX spawn dust actual birth and velocity", VfxSpawnDustActualBirthAndLegacyVelocity),
            ("VFX expressivity short shapes and rotation frames", VfxExpressivityShortShapeLifetimeAndRotationFrame),
            ("VFX expressivity large sprites", VfxExpressivityLargeSpritesRemainExecutable),
            ("VFX expressivity shape saved parity", VfxExpressivityShapeAndSavedParity),
            ("VFX expressivity orbit orientation and rate", VfxExpressivityOrbitOrientationAndAngularRate),
            ("VFX expressivity dust distribution parity", VfxExpressivityDustDistributionAndSavedParity),
            ("filled sector mesh precedes sprite batch", FilledSectorMeshPrecedesSpriteBatch),
            ("filled sector strict admission", FilledSectorAdmission),
            ("filled sector nonoverlapping geometry", FilledSectorMeshGeometry),
            ("filled sector shared budget sprite isolation", FilledSectorSharedBudgetAndSpriteIsolation),
            ("contour topology and triangulation", ContourTopologyChecks),
            ("contour strict admission", ContourAdmissionChecks),
            ("contour snapshot material lifecycle and budget", ContourSnapshotAndMeshChecks),
            ("explicit shape strict admission", ExplicitShapeAdmission),
            ("explicit shape authored geometry", ExplicitShapeAuthoredGeometry),
            ("explicit shape lifecycle shared budget", ExplicitShapeEmissionLifecycleAndSharedBudget),
            ("active primitive slots share budget", ActivePrimitiveSlotsShareBudget),
            ("draw budgets reset without world tick", DrawBudgetsResetWithoutWorldTick),
            ("detached VFX state is bounded and cleared", DetachedVfxStateIsBoundedAndCleared),
            ("legacy detached VFX client cleanup does not require Draw", DetachedVfxClientCleanupDoesNotRequireDraw),
            ("native craft HTTP timeout default override floor and cancellation", () => CraftHttpTimeoutUsesNativeEnvironmentAsync().GetAwaiter().GetResult()),
            ("cache-only flag preserves request", CacheOnlyFlagPreservesRequest),
            ("generator delivery requires identity", GeneratorDeliveryRequiresIdentity),
            ("parent summary unicode roundtrip", ParentSummaryUnicodeRoundtrip),
            ("generated parent prefix is request-only", GeneratedParentPrefixIsRequestOnly),
            ("parent projectile atlas metadata is observed only", ParentProjectileAtlasMetadataIsObservedOnly),
            ("parent native sprite reference reaches prepared request", ParentNativeSpriteReferenceReachesPreparedRequest),
            ("parent native sprite reference absence is honest", ParentNativeSpriteReferenceAbsenceIsHonest),
            ("generated parent sprite reference never uses native proxy", ParentGeneratedSpriteReferenceNeverUsesNativeProxy),
            ("craft identity rejects failed defaults", CraftIdentityRejectsFailedDefaults),
            ("parent placement facts reach craft snapshot", ParentPlacementFactsReachCraftSnapshot),
            ("parent native fact envelopes preserve exact shape", ParentNativeFactEnvelopesKeepTheirExactShape),
            ("parent ammo facts keep native category and inventory flag", ParentAmmoFactsKeepNativeCategoryAndInventoryFlag),
            ("inventory seeds absent v5 byte and identity compatibility", InventorySeedAbsentDefinitionPreservesBytes),
            ("inventory seeds DTO literal and absence", InventorySeedDtoKeepsLiteralAndAbsence),
            ("inventory seeds native instance locality", InventorySeedNativeHasItemIsInstanceLocal),
            ("inventory seeds actual WorldGen RNG and owner", InventorySeedWorldGenPreservesRandomAndOwner),
            ("placed alpha pivot final bounds uncropped FNA geometry", PlacedAlphaPivotUsesFinalBoundsWithoutCropping),
            ("placed alpha cache one pass selected generation", PlacedAlphaCacheMeasuresOnceAndReturnsSelectedGeneration),
            ("placed alpha DTO optional strict choice", PlacedAlphaDtoKeepsOptionalClosedChoice),
            ("placed alpha ledger projection material physics nonmutation", PlacedAlphaProjectionPreservesMaterialAndPhysics),
            ("placed alpha legacy absence definition network identity", PlacedAlphaLegacyAbsenceKeepsDefinitionAndNetworkIdentity),
            ("VFUI03 status whole block wrapping", VFUI03StatusHoverWrapsWholeBlockForNativeClamp),
            ("VFUI03 native whole cursor block clamp", VFUI03NativeWholeCursorBlockClampsAtAllEdges),
            ("VFUI04 stable countdown and compact numbers", VFUI04StatusCountdownIsStableWholeSecondsAndNumbersStayNonzero),
            ("VFUI14 captured crystal native mana formula", VFUI14CapturedCrystalUsesMultiplierNotFiveFlatMana),
            ("VFUI17 buff order refresh and expiry", VFUI17DistinctBuffsAggregateAndExpireInEitherOrder),
            ("VFUI18 captured keg invisibility preservation", VFUI18CapturedKegDoesNotRemoveInvisibilityBuff),
            ("VFUI19 captured input costs and tooltip", VFUI19CapturedActionsKeepAuthoredManaAndSeparateStackCosts),
            ("VFUI20 stack ID recipe identity", VFUI20StackIdentityUsesIdAndRecipeNotName),
            ("VFX worker world retirement defers GPU disposal", DetachedVfxWorkerRetiresCpuBeforeGraphicsDisposal),
            ("VFX queued disposal preserves next-world generation", DetachedVfxQueuedDisposalCannotRetireNextWorld),
            ("native equipment wire vision", NativeEquipmentWireVision),
            ("native equipment utility flags", NativeEquipmentUtilityFlags),
            ("native equipment rocket flight", NativeEquipmentRocketFlight),
            ("native equipment sprint speed", NativeEquipmentSprintSpeed),
            ("run-speed equipment applies after vanilla movement", RunSpeedEquipmentAppliesAfterVanillaMovement),
            ("equipment authored ranges reach player", EquipmentAuthoredRangesReachPlayer),
            ("unit boundary charge release preserves authored speed", ChargeReleasePreservesAuthoredZeroAndFractionalSpeed),
            ("charge release preserves authored flight lifetime", ChargeReleaseKeepsAuthoredFlightLifetime),
            ("equipment class damage reaches exact DamageClass", () => CheckEquipmentCases(EquipmentDamageClasses)),
            ("generated ammo preserves exact projectile on direct use", GeneratedAmmoDirectUseKeepsDeclaredProjectile),
            ("generated ammo preserves exact rocket and solution selection", GeneratedAmmoPickAmmoKeepsExactRocketAndSolution),
            ("generated ammo leaves unrelated category unchanged", GeneratedAmmoPickAmmoRejectsUnrelatedCategoryRewrites),
            ("weapon ammo native shot selection conservation and stats", WeaponAmmoNativeShotKeepsSelectionConservationAndStats),
            ("weapon ammo missing ammo and independent use lanes", WeaponAmmoMissingAmmoAndIndependentUseLanes),
            ("generated whip applies same-owner summon source bonus", WhipImpactMarksOnlyItsOwnerForSummonSourceDamage),
            ("generated whip range changes geometry and collision", WhipGeometryTracksEquippedRangeInCollision),
            ("proximity missile expiry VFX matches event lifecycle", ProximityMissileExpireVfxMatchesNaturalExpiry),
            ("peer events preserve observed spawn-budget snapshot", PeerEventDoesNotOverwriteReceivedSpawnBudgetSnapshot),
            ("root binding spawn capacity respects authored count and independent event ledger", RootBindingSpawnCapacityRespectsAuthoredCountAndIndependentEventLedger),
            ("sentry explicit target policy LOS and hard radius", SentryTargetPolicyUsesExactAssignedNpcAndFilters),
            ("sentry volley native spawn arguments and authority", SentryVolleyUsesAuthoredCountAndSpreadAtNativeBoundary),
            ("sentry lifecycle native resting spot and turret cap", SentryNativeRestingSpotAndTurretCap),
                        ("explicit concurrency fences all spawn producers without changing legacy", ExplicitConcurrencyFencesAllSpawnProducersWithoutChangingLegacy),
            ("equipment runtime safety bounds apply", EquipmentRuntimeSafetyBoundsApply),
            ("current authored equipment values reach runtime", CurrentAuthoredEquipmentValuesReachRuntime),
            ("signed accessory defense reaches player", SignedAccessoryDefenseReachesPlayer),
            ("blink authored range reaches teleport", BlinkAuthoredRangeReachesTeleport),
            ("mobility consumption pure native outcome", NativePureMobilityConsumptionFollowsUseOutcome),
            ("mobility consumption mixed native effects once", NativeMixedMobilityRefusalPreservesOtherEffectsOnce),
            ("named item effects select native use and quick use", NamedItemEffectsSelectNativeUseAndQuickUse),
            ("named mobility groups share cooldown and consumption outcome", NamedMobilityGroupsShareCooldownAndConsumptionOutcome),
            ("named held effects refresh exact owner item and bound snapshots", NamedHeldEffectsRefreshExactOwnerItemAndBoundSnapshots),
            ("named item effects DTO roundtrip and invalid presence", CheckNamedEffectsDto),
            ("craft cancellation server world unload retires owners without escrow refund", CraftWorldUnloadRetiresServerOwnersWithoutRefundingEscrow),
            ("integrated QoL remote cancellation acknowledgement", IntegratedQolRemoteCancelAcknowledgementUsesActualOutcome),
            ("integrated QoL native proxy capacity recovery", IntegratedQolNativeProxyCapacityRecovery),
            ("integrated QoL station refund capacity recovery", IntegratedQolStationRefundCapacityRecovery),
            ("craft QoL fatal HTTP material presentation", () => CraftQolFatalHttpRefundPresentationTracksDeliveryAsync().GetAwaiter().GetResult()),
            ("craft QoL full pool refund claim", CraftQolRefundFullPoolRetainsExactSavedClaim),
            ("craft QoL partial refund remainder", CraftQolPartialRefundRetainsOnlyRemainder),
            ("craft QoL unknown metadata projection", () => CraftQolUnknownMetadataPreservesAcceptedRoutingAsync().GetAwaiter().GetResult()),
            ("craft QoL hard owned deadline", CraftQolDeadlineRetiresIncompleteWorkers),
            ("craft QoL server deadline durable escrow", CraftQolServerDeadlinePreservesDurableEscrow),
            ("craft QoL exact lane cancel", CraftQolCancellationKeepsIndependentLane),
            ("craft QoL remote cancel retained claim", CraftQolRemoteCancelRetainsClaimUntilHostOutcome),
            ("craft QoL cancel replay committed outcome", CraftQolCancelPacketReplaysCommittedOutcomeWithoutNewRefund),
            ("craft QoL idle lane return policy", CraftQolIdleLaneReturnDoesNotDependOnLaneZero),
            ("craft cancellation interrupts HTTP and recovery", () => CraftCancellationInterruptsHttpAndRecoveryAsync().GetAwaiter().GetResult()),
            ("craft cancellation preserves live retry and delivery", () => CraftCancellationKeepsLiveRetryAndDeliveryAsync().GetAwaiter().GetResult()),
            ("disposed asset download cannot publish", () => CheckDisposedAssetDownloadsAsync().GetAwaiter().GetResult()),
            ("pull modes preserve subject and authority", PullModesPreserveSubjectAndAuthority),
            ("owner hit NPC status uses native sync", OwnerHitNpcEffectsUseNativeSync),
            ("owner projectile hit bridges exact NPC pull", OwnerProjectileHitBridgesNpcPull),
            ("rt01 delayed NPC native hook incarnation fence", NativeDelayedNpcIncarnationRejectsInPlaceReuse),
            ("rt01 delayed NPC real status incarnation fence", NativeDelayedNpcStatusRejectsNewIncarnation),
            ("delayed NPC statuses survive projectile slot reuse", DelayedNpcStatusSurvivesProjectileReuse),
            ("item hit cannot turn into next held item effect", ItemHitCannotSwitchAuthoredSource),
            ("NPC hit generation survives real Transform", NpcHitGenerationSurvivesTransform),
            ("delayed actions keep original owner", DelayedActionsKeepOriginalOwner),
            ("event damage uses authored source", EventDamageUsesAuthoredSource),
            ("event spawn zero multiplier is not replaced by one", EventSpawnZeroMultiplierIsNotReplacedByOne),
            ("player save reference requires version markers", PlayerSaveReferenceRequiresVersionMarkers),
            ("neutral item omissions preserve exact Item projection", NeutralItemOmissionsPreserveProjection),
            ("neutral buff omissions reach real player effects", NeutralBuffOmissionsReachRealPlayerEffects),
            ("small generated buffs reach real item/player hooks", SmallGeneratedBuffsReachRealHooks),
            ("generated buff duration survives native hook order", GeneratedBuffDurationSurvivesNativeHookOrder),
            ("reactive buff light survives late native hook", ReactiveBuffLightSurvivesLateNativeHook),
            ("generated buff light keeps client server scope", GeneratedBuffLightKeepsClientServerScope),
            ("parent native tile state matches actual campfire toggle", ParentNativeTileStateMatchesRealCampfireToggle),
            ("placed vfx exact server mirror late hydration and retirement", PlacedVfxMirrorHydratesExactDefinitionAndRetires),
            ("placed vfx actual Python final delivery native draw", PlacedVfxFinalPythonDeliveryRuns),
            ("placed vfx continuous per-burst budgets", PlacedVfxContinuousBurstBudgets),
            ("placed vfx registration deduplication and viewport delivery", PlacedVfxRegistrationAndViewportRegressions),
            ("placed vfx inactive broad phase preserves retirement", PlacedVfxInactiveLedgerBroadPhaseRetainsRetirement),
            ("placed vfx DTO exact selector admission", PlacedVfxDtoAndSelectorAdmission),
            ("placed vfx two instances state generation FNA draw", PlacedVfxTwoInstancesGateAndGenerationDraw),
            ("placed vfx offscreen lights exact selectors", PlacedVfxOffscreenLightUsesExactSelectors),
            ("placed vfx library light and held exclusion", PlacedVfxLibraryAndLightRealConsumers),
            ("placed light footprint persistence break unload", PlacedLightOwnsFootprintNotPlayerAndPersists),
            ("placed light server mirror exact definition quarantine", PlacedLightMirrorAuthenticatesServerAndExactDefinition),
            ("placed body native profile hash shape and lifecycle", PlacedNativeProfileKeepsExactHashShapeAndLifecycle),
            ("native chest SP native callback outcome", NativeChestSinglePlayerOutcome),
            ("native chest callback fault bounded rollback", NativeChestCallbackFaultRollsBack),
            ("native chest break native contents removal authority", NativeChestBreakWaitsForNativeRemoval),
            ("native chest MP authenticated native outcome", NativeChestMultiplayerAuthenticatedOutcome),
            ("native chest native save load registered contents open", NativeChestNativeSaveLoadAndOpen),
            ("native chest metadata capacity pre-mutation refusal", NativeChestMetadataAndCapacityRefuseBeforeMutation),
            ("native chest ordinary styles preserve native mod hooks", NativeChestCanonicalStylesRespectNativeHooks),
            ("native chest global CanPlace veto stays native", NativeChestGlobalCanPlaceUsesNativeVeto),
            ("native chest support loss malformed contents authority", NativeChestSupportAndMalformedClaimsStayNative),
            ("native chest malformed native save preserves inventory", NativeChestMalformedNativeSaveCannotPruneContents),
            ("native chest callback collision is not provenance", NativeChestCallbackCollisionIsNotCallbackSuccess),
            ("native chest native MP inventory open exclusivity", NativeChestNativeMultiplayerInventoryAndExclusivity),
            ("native chest raw message34 compensation isolation", NativeChestRawMessage34CannotRefundGeneratedSource),
            ("native chest MP refusal rollback replay matrix", NativeChestMultiplayerRefusalMatrix),
            ("native chest receipt exact item player incarnation", NativeChestReceiptCannotSpendAnotherInstance),
            ("native chest live actor replacement incarnation", NativeChestLiveActorReplacementCannotRebind),
            ("native chest exact native return durable pool prefix", NativeChestExactReturnUsesOnlyExistingPendingOwner),
            ("native chest post-load mine before maintenance exact return", NativeChestPostLoadBreakBeforeMaintenance),
            ("native chest untracked player path refused", NativeChestUntrackedPlayerPathCannotCreateStorage),
            ("native chest partial native actor allocation abort", NativeChestPartialActorInitializationRollsBackOwnedSlot),
            ("native chest predictable support refusal before drop", NativeChestUnsupportedGroundRefusesBeforeVanillaDrop),
            ("native chest authored body light VFX actor liveness", NativeChestPreservesAuthoredBodyLightVfxAndActorLiveness),
            ("native chest bounded cached maintenance", NativeChestMaintenanceBoundsNativeActorsAndDefinitionReads),
            ("native chest single family style zero only", NativeChestCanonicalStylesAndRefusals),
            ("generated exact stack and native quick-stack identity", GeneratedQuickStackMatchesExactDefinitionNotProxyType),
            ("generated periodic stable action phase", GeneratedPeriodicActionPhaseIsStable),
            ("native chest admission", NativeChestAdmission),
            ("native chest bare tiles are not storage", NativeChestBareTilesCannotCommit),
            ("placed body snapshot bounded packets preserve large ledger", PlacedBodySnapshotUsesBoundedPacketsWithoutTruncatingLedger),
            ("placed body ledger selected identity save and network", PlacedBodyLedgerKeepsExplicitIdentityAcrossSaveAndNetwork),
            ("placed body cosmetic decoder cannot erase material", PlacedBodyCosmeticDecodeCannotEraseMaterial),
            ("placed body restore registry exact conflict refusal", PlacedBodyRestoreUsesExistingRegistryWithoutReplacingConflicts),
            ("pb01 actual placing client retains server identity and removal", PlacingClientRetainsExactServerIdentityThroughCommitAndRemoval),
            ("pb02 gameplay transform authority Visual VFX PNG identity fences", Pb02IdentityRetainsAuthoredDifferences),
            ("pb02 same ID restoration conflict refusal", Pb02RestoreRefusesSameIdContentConflicts),
            ("native quick use never selects a non-effect binding", NativeQuickUseNeverSelectsNonEffectBinding),
            ("held proxy replaced only by ready instance PNG", HeldProxyIsReplacedOnlyByReadyInstanceSprite),
            ("cursor death retires generated preview only", CursorDeathRetiresGeneratedPreviewOnly),
            ("native effects strict selectors atomic budgets", NativeEffectsStrictSelectorsAndAtomicBudgets),
            ("native effects actual stock delayed snapshot", NativeEffectsActualGoldBurstAndDelayedSnapshot),
            ("native cues functional light renewal", NativeCuePeriodicLightNeedsFunctionalRenewal),
            ("native cues strict consumed controls", NativeCuesRejectMissingAndForeignControls),
            ("native cues snapshot frame budgets and exact emission", NativeCuesCaptureFrameAndRespectBudgets),
            ("explicit body geometry strict admission", ExplicitBodyGeometryAdmission),
            ("explicit body geometry authored dimensions and collision path", ExplicitBodyGeometryDrawsAuthoredDimensionsAndActualPath),
            ("textured body uses declared axis and preserves native spin", TexturedBodyUsesDeclaredAxisAndPreservesNativeSpin),
            ("front_hand fresh wire admission", FrontHandFreshWireAdmission),
            ("front_hand native pose and contact", FrontHandNativePoseAndContact),
            ("played umbrella saved hand grip draw size and damage geometry", PlayedUmbrellaSavedGeometryKeepsHandContactAndReach),
            ("front_hand observer counterproofs", FrontHandObserverCounterproofs),
            ("front_hand cursor eventually publishes stationary aim", FrontHandCursorEventuallyPublishesStationaryAim),
            ("front_hand event direction and delayed snapshot", FrontHandGameplayEventsRetainSelectedAxis),
            ("owner cursor stationary beam", () => OwnerCursorEventuallyPublishesStationaryAim("beam")),
            ("owner cursor stationary yoyo", () => OwnerCursorEventuallyPublishesStationaryAim("yoyo")),
            ("owner cursor stationary forward retract", () => OwnerCursorEventuallyPublishesStationaryAim("forward_retract")),
            ("front_hand detached exact body scale", FrontHandDetachedExactBodyScale),
            ("item VFX preserves world-clock cadence", ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick),
            ("item VFX hit positions relay and event budgets", ItemVfxEventPositionsRelayAndBudgets),
            ("beam live damage and shared body warmup ramps", BeamRampsConsumeLiveDamageAndSharedBodyGeometry),
            ("beam native mana cadence and world clock", BeamSustainUsesNativeManaAndWorldClock),
            ("beam failed mana and control loss terminate", BeamManaFailureAndControlLossTerminateBeforeFurtherPayment),
            ("beam native scan clips collision body and VFX endpoints", BeamLaserScanClipsCollisionBodyAndVfxPathTogether),
        };
        checks = System.Linq.Enumerable.ToArray(
            System.Linq.Enumerable.Concat(checks, ComposableMotionAdmissionChecks()));
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
                Equal(enabled && damage > 0 && delay == 0, live.friendly, "last waiting update remains harmless");
                host.AI();
                Equal(enabled && damage > 0, live.friendly, "live child collision eligibility on first active update");
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

    private static void DelayedActivationRunsSpawnBeforeNativeDamage()
    {
        WithPersistenceTilemap((_, _) => {
            foreach (int delayTicks in new[] { 0, 1, 2 })
            foreach (int extraUpdates in new[] { 0, 2 })
            foreach (bool hydrate in new[] { false, true })
            foreach (bool charge in new[] { false, true })
            {
                using var scope = new SwarmRuntimeScope();
                Terraria.Main.SceneMetrics = new SceneMetrics();
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
                var data = ChildCombatFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
                entity.Events[0].Event = RuntimeEventKind.OnSpawn;
                entity.Events[0].DelayTicks = 1;
                entity.Spawn.OverTarget.DelayTicks = delayTicks;
                entity.Spawn.OverTarget.HeightTiles = 1;
                entity.Spawn.SpeedPxPerTick = 0;
                entity.Collision.TileCollide = false;
                entity.Collision.Pierce = 1;
                entity.Collision.ExtraUpdates = extraUpdates;
                if (charge)
                {
                    entity.Controller.Name = "charge_then_release";
                    entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
                    entity.Controller.Params.ChargeTicks = 60;
                    entity.Controller.Params.PowerMultiplier = 2;
                }
                data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
                var owner = Terraria.Main.player[0];
                owner.inventory[0] = new Item(Terraria.ID.ItemID.WoodenSword);
                AttachItem(new InfiniCrafterLocal.Content.Items.GeneratedItem(), owner.inventory[0], data);
                owner.channel = true;
                var generated = SwarmHost(data, entity);
                var projectile = generated.Projectile;
                projectile.Center = new Vector2(640, 640);
                // An existing type supplies native array bounds. The actual
                // attached mod AI, native Damage and penetration retirement run.
                projectile.type = Terraria.ID.ProjectileID.WoodenArrowFriendly;
                projectile.aiStyle = -1;
                var target = Terraria.Main.npc[0];
                target.SetDefaults(Terraria.ID.NPCID.BlueSlime); target.active = true; target.Center = projectile.Center;
                target.life = target.lifeMax = 10000; target.HideStrikeDamage = true;
                string label = $"delay={delayTicks} extraUpdates={extraUpdates} hydration={hydrate} charge={charge}: ";
                for (int tick = 0; tick < delayTicks; tick++)
                {
                    projectile.Update(0);
                    Equal(10000, target.life, label + "waiting update cannot damage before on_spawn");
                    Equal(true, projectile.active, label + "waiting projectile survives overlapping NPC");
                    Equal(0, PendingActions(), label + "waiting update does not emit on_spawn");
                }
                if (hydrate)
                {
                    generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
                    if (delayTicks > 0)
                        Equal(false, projectile.friendly, label + "hydration cannot arm the final waiting state");
                }
                projectile.Update(0);
                Equal(1, PendingActions(), label + "on_spawn admitted on first active update");
                if (charge)
                {
                    Equal(10000, target.life, label + "charge controller suppresses contact on activation");
                    Equal(true, projectile.active, label + "charge remains alive until release");
                    owner.channel = false;
                    projectile.Update(0);
                }
                Equal(true, target.life < 10000, label + "active native contact deals damage");
                Equal(false, projectile.active, label + "native contact consumes pierce one");
                Equal(1, PendingActions(), label + "native retirement preserves the on_spawn child action");
                Equal(true, ObserveChildCombatBoundary(AdvanceRuntimeWorldTick, projectile, 50, 3f),
                    label + "admitted child reaches native spawn after source retirement");
                Equal(0, PendingActions(), label + "child dispatches once");
            }
        });
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
