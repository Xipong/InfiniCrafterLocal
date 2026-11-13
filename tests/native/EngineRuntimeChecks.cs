// Headless behavioral checks against the actual mod source and tModLoader types.
// This executable never starts Terraria.Main, loads a world, or initializes graphics.
// Run with existing dependencies (no model requests, no tML packaging tasks):
// dotnet run --project tests/native/EngineRuntimeChecks.csproj \
//   -p:InfiniTmlReferenceDir=<tModLoader-package/lib/net8.0> \
//   -p:InfiniExternalDepsRoot=<ParticleLibrary-and-Luminance-root>
// These method-level regressions do not simulate Terraria's update/network loop.
using System;
using System.Linq;
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
            typeof(Terraria.Program).GetProperty("SavePathShared", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)!
                .SetValue(null, sandbox);
            Terraria.Main.dedServ = true;
            if (args.Length == 2 && args[0] == "--verify-native-target")
            {
                VerifyNativeSourcePackTarget(args[1]);
                return 0;
            }
            if (args.Length == 2 && args[0] == "--build-native-source-pack")
            {
                BuildNativeSourcePack(args[1]);
                return 0;
            }
            if (args.Length == 3 && args[0] == "--capture-parent-panel")
            {
                CaptureParentPanel(args[1], args[2]);
                return 0;
            }
            if (args.Length == 3 && args[0] == "--profile-populated-parent-panel")
            {
                ProfilePopulatedParentPanel(args[1], args[2]);
                return 0;
            }
            if (args.Length == 2 && args[0] == "--capture-parent-context")
            {
                CaptureParentContext(args[1]);
                return 0;
            }
            if (args.Length == 1 && args[0] == "--profile-parent-analysis")
            {
                ParentAnalysisFrameProfiling();
                return 0;
            }
            if (args.Length == 2 && args[0] == "--profile-parent-craft")
            {
                ParentCraftFrameProfiling(args[1]);
                return 0;
            }
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
                throw new ArgumentException("Expected --profile-populated-parent-panel <manifest> <output>, --check-filter <filter>, --replay-contracts <jsonl-path>, --capture-vfx-preview <json-path>, --verify-native-target <manifest.json>, --build-native-source-pack <output.zip>, --profile-parent-analysis or --profile-parent-craft <plain|mixed|ammo|nebula-prism|eventide>");
            return RunChecks();
        }
        finally { System.IO.Directory.Delete(sandbox, recursive: true); }
    }

    private static int RunChecks(string? filter = null)
    {
        (string Name, Action Check)[] checks = {
            ("issue345 ReturnOne ACK delayed authority refund", Issue345ReturnOneAckDelayedAuthorityRefundIsOneTime),
            ("issue345 projectile-only native Goblin reset and roll", ProjectileOnlyNativeReforgeResetAndRoll),
            ("issue345 projectile-only native multiple-root rounding", ProjectileOnlyNativePrefixMultipleRoots),
            ("issue345 escrow nested history isolation", Issue345EscrowNestedHistoryCannotRestoreRetiredFields),
            ("issue345 escrow refund one-time save", Issue345EscrowRefundDeliveredOnlyOnce),
            ("issue345 escrow favorites current save", Issue345EscrowFavoritesRemainCurrent),
            ("issue345 projectile-only native prefix attack", ProjectileOnlyNativePrefixEligibilityAndAttack),
            ("issue345 projectile-only native prefix guards", ProjectileOnlyNativePrefixGuards),
            ("issue345 projectile-only bridge lifecycle", ProjectileOnlyNativePrefixBridgeLifecycle),
            ("issue345 sprite local path upper bound", SpriteLocalPathsRetainUpperBound),
            ("issue345 sprite short local path loader and draw", () => SpriteLocalPathsShareLoaderAndDrawLimits(false)),
            ("issue345 sprite long local path loader and draw", () => SpriteLocalPathsShareLoaderAndDrawLimits(true)),
            ("audit251 bare placement ordinary neighbor", BarePlacementCannotClaimAdjacentOrdinaryTile),
            ("audit251 bare placement generated neighbors", BarePlacementSeparatesConcurrentGeneratedNeighbors),
            ("audit251 bare placement native multitile", BarePlacementUsesExactNativeMultitile),
            ("audit251 late owner action liveness", LateOwnerActionsRejectDeadAndZeroLife),
            ("audit251 late owner healing cap", LateOwnerHealCapsNativeAmountToMissingLife),
            ("audit251 late owner delayed life boundary", LateOwnerActionsCannotCrossDeathAndRespawn),
            ("identity reach rows scanning and work-bound parity", IdentityReachRowsMatchScanningOracle),
            ("identity reach rows bounded allocations", IdentityReachRowsReduceAllocations),
            ("REA guard memo scanning parity", ReaGuardMemoMatchesScanningOracle),
            ("REA Entity accessor decoded-owner parity", ReaEntityMemoTracksDecodedBody),
            ("REA attachment grouping exact identity parity", ReaAttachmentGroupingMatchesScanning),
            ("hook output selection preserves direct ref stores", ParentHookOutputsSurviveStateWrites),
            ("hook output selection preserves return values", ParentHookReturnOutputsSurviveStateWrites),
            ("hook output selection preserves aliases and constructor bindings", ParentHookOutputsKeepAliasesAndConstructors),
            ("hook output selection rejects unproved addresses and cosmetic helpers", ParentHookOutputsRejectUnprovedAddresses),
            ("hook output selection preserves optional return priority", ParentHookOutputSelectionPreservesReturnPriority),
            ("hook output selection reaches native fact capture", ParentHookOutputsReachNativeFactCapture),
            ("mechanics source preserves effects and unknowns", MechanicsSourcePreservesEffectsAndUnknowns),
            ("mechanics source binds explicit native roots", MechanicsSourceBindsExplicitNativeRoots),
            ("mechanics source excludes only unreachable identity writes", MechanicsSourceExcludesOnlyUnreachableIdentityWrites),
            ("projectile identity initialization continuation is contextual", ProjectileIdentityInitializationContinuationIsContextual),
            ("mechanics source call index scanning parity", MechanicsCallIndexMatchesScanningOracle),
            ("parent capture panel validates offline inputs", ParentCapturePanelValidation),
            ("parent composite summon construction and follower source", ParentCompositeSummonRetainsConstructionAndFollowerSource),
            ("shared defaults remain conditional source", SharedDefaultsRemainConditionalSource),
            ("shared defaults reach composite parent", SharedDefaultsReachCompositeParent),
            ("shared defaults recording preserves source", SharedDefaultsRecordingPreservesSource),
            ("populated parent profiler preserves source and cold state", PopulatedParentProfilerPreservesSourceAndColdState),
            ("parent item dispatcher source actual Prepare", ParentItemDispatcherSourceReachesPrepare),
            ("parent item shooting dispatcher source actual Prepare", ParentItemShootingDispatcherSourceReachesPrepare),
            ("parent item identity helper source actual Prepare", ParentItemIdentityHelpersReachPrepare),
            ("parent item identity helper strict bindings and bounds", ParentItemIdentityHelpersRejectUnprovedBindings),
            ("parent item dispatcher source guards bounds and cancellation", ParentItemDispatcherBoundsStayUnknown),
            ("projectile lifecycle conditional native source", ProjectileLifecycleKeepsConditionalNativeSource),
            ("projectile interaction source explicit unknown boundaries", ProjectileInteractionSourceKeepsExplicitUnknowns),
            ("projectile interaction native hit and movement source", ProjectileInteractionSourceKeepsNativeHitAndBounce),
            ("projectile lifecycle closed regions and unknown boundaries", ProjectileLifecycleRefusesIncompleteRegions),
            ("projectile lifecycle fingerprint preserves source identity", ProjectileLifecycleFingerprintKeepsNativeIdentity),
            ("bundled decompiler exact binary and official resource packaging", BundledDecompilerUsesOfficialResourcePackaging),
            ("weapon replacement profiles preserve native mechanics", WeaponReplacementProfilesPreserveNativeMechanics),
            ("weapon replacement profiles conditional opaque hook evidence", WeaponReplacementProfilesKeepConditionalAndOpaqueHookEvidence),
            ("weapon replacement profiles deferred cancellation parity", WeaponReplacementProfilesMatchDeferredAndCancelledCapture),
            ("parent source sparse locals match dense oracle", ParentSourceSparseLocalsMatchDenseOracle),
            ("projectile attack source expanded dependency bound", ProjectileAttackSourceExpandedDependencyBound),
            ("parent source graph native spawn candidate provenance", ParentSourceGraphRetainsNativeSpawnCandidateProvenance),
            ("native CSharp closed exception region admission", NativeCSharpClosedExceptionRegions),
            ("native CSharp token separates overloads and modules", NativeCSharpTokenSeparatesOverloads),
            ("native CSharp source exact PE identity and no execution", NativeCSharpSourceVerifiesExactPeWithoutExecution),
            ("native CSharp source semantic method header verification", NativeCSharpSourceVerifiesMethodHeader),
            ("native CSharp source complete exception descriptor verification", NativeCSharpSourceVerifiesExceptionRegions),
            ("native CSharp source whole exception source retains graph refusal", NativeCSharpWholeExceptionSourceKeepsGraphRefusal),
            ("native CSharp source actual exception helpers retain source and unknowns", NativeCSharpExceptionHelpersReachActualCapture),
            ("native CSharp source compound regions preserve full condition", NativeCSharpCompoundRegionsRetainFullGuardWithoutPruning),
            ("native CSharp source closed regions and all windows", NativeCSharpRegionsKeepAllWindowsAndRefuseNonlocalDependencies),
            ("native CSharp source actual Last Prism helper inline and links", NativeCSharpLastPrismRetainsReadableHelperAndInlineEffects),
            ("source performance documents rendering", SourcePerformanceDocumentsRendering),
            ("source performance documents LRU and lifetime", SourcePerformanceDocumentsLruAndLifetime),
            ("source performance documents verify cache hits", SourcePerformanceDocumentsVerifyCacheHits),
            ("source buffers UTF-8 exact bytes", SourceBuffersHashUtf8MatchesExactBytes),
            ("source buffers concurrent hashing independence", SourceBuffersHashUtf8ConcurrencyKeepsIndependentState),
            ("source buffers cancellation and retry", SourceBuffersCancellationDoesNotPoisonReuse),
            ("source pack dependencies release images before next resolve", NativeSourcePackDependenciesReleaseImagesBeforeNextResolve),
            ("source pack dependencies release images on failure and cancellation", NativeSourcePackDependenciesReleaseImagesOnFailureAndCancellation),
            ("source pack resolver repeated resolution after release", NativeSourcePackResolverRepeatedResolutionSurvivesEarlyRelease),
            ("indexed bit sets traversal oracle", IndexedBitSetTraversalMatchesHashSetOracle),
            ("parent source compact rows graph oracle", ParentSourceCompactRowsMatchGraphOracle),
            ("parent source compact rows atomic publication", ParentSourceCompactRowsPublishAtomically),
            ("native source pack deduplicates content without aliasing complete keys", NativeSourcePackDeduplicatesContentWithoutAliasingKeys),
            ("native source pack short methods bypass live decompilation", NativeSourcePackIncludesShortNativeMethods),
            ("native source pack complete projection input keys", NativeSourcePackKeysCoverProjectionInputs),
            ("native source pack exact renderer bytes and cancellation", NativeSourcePackReaderPreservesBytesAndCancellation),
            ("native source pack manifest identity and entry integrity", NativeSourcePackReaderRejectsIdentityAndCorruption),
            ("native source pack verified hits reject method header mismatch", NativeSourcePackHitsVerifyMethodHeaders),
            ("native source pack recording conflicts fail atomically", NativeSourcePackRecorderRejectsConflictsAtomically),
            ("raw observation cache isolation", RawObservationCacheIsolation),
            ("source programs incremental LRU count and characters", SourceProgramsEvictLeastRecentlyUsed),
            ("source programs late completion invalidation and eviction", SourceProgramsFenceLateCompletion),
            ("source programs cancelled owner retry and borrower isolation", SourceProgramsRetryCancelledOwnersAndBorrowers),
            ("source programs clone mutation isolation and native parity", SourceProgramsCloneIsolation),
            ("projectile inline mutable effects source and work bounds", ProjectileInlineEffectsRetainMutableSource),
            ("projectile inline last prism admission scan and opacity", ProjectileInlineLastPrismSourceRetainsAdmissionAndScan),
            ("finite integer source alternatives and unknowns", SourceFiniteIntegersPreserveAlternativesAndUnknowns),
            ("finite integer source bounds and overflow", SourceFiniteIntegersBoundWorkAndOverflow),
            ("finite integer spawn native vilethorn reference", ProjectileFiniteSpawnVilethornReference),
            ("projectile helper spawn native last prism reference", ProjectileHelperSpawnLastPrismReference),
            ("projectile helper spawn conditional unknown control flow", ProjectileHelperSpawnSlicesKeepUnknownControlFlow),
            ("projectile helper spawn independent budget refusals", ProjectileHelperSpawnSlicesKeepBudgetRefusals),
            ("projectile helper spawn exact source table merge", ProjectileHelperSpawnExactMergeIsLossless),
            ("parent conditional shot alternatives source only", ParentConditionalShotAlternativesRemainSourceOnly),
            ("parent non-ammo item-specific source facts survive capture", ParentNonAmmoSourceFactsArePreserved),
            ("craft gzip transport preserves cache and generation payloads", () => CraftGzipTransportPreservesRequestAsync().GetAwaiter().GetResult()),
            ("craft prepared transport reuse invalidation and ownership", () => CraftPreparedTransportReuseAsync().GetAwaiter().GetResult()),
            ("parent child snapshots one handoff preserves bounds", ParentChildSnapshotsOneHandoff),
            ("parent fingerprint excludes readable source view metadata", ParentFingerprintExcludesReadableSourceViews),
            ("audit native pure definition projections", AuditProjectionsDoNotNormalizeSource),
            ("audit native failed network copy refusal", AuditNetworkCopyFailureNeverAliasesOriginal),
            ("audit native atlas All early return", AuditAtlasAllSkipsEffectTraversal),
            ("audit native durable compact save", AuditDiskFailureCannotProduceCompactOnlySave),
            ("audit native craft manual mute", AuditCraftKeepsManualMute),
            ("audit native queued draw preparation", AuditDrawQueuesColdTexturePreparation),
            ("atlas layout native discovery grid centered on full page", AtlasLayoutNativeGrid),
            ("atlas layout native diagram captions centered on wells", AtlasLayoutNativeCaptions),
            ("atlas layout native atlas text glyph callbacks center labels", () => AtlasLayoutNativeText(false)),
            ("atlas layout native forge text glyph callbacks center labels", () => AtlasLayoutNativeText(true)),
            ("atlas header visible glyph centering and safe inset", AtlasHeaderUsesVisibleGlyphsAndInsetControls),
            ("atlas packaged skin alpha matches PNG loading", AtlasPackagedSkinPixelsMatchPngAlpha),
            ("atlas unload graphics stay on main thread across reload", AtlasUnloadRetiresOwnedGraphicsOnMainThread),
            ("atlas unload disposal failures preserve later cleanup", AtlasUnloadIsolatesDisposalFailures),
            ("parent source export plan exact clone oracle", ParentSourceExportPlanMatchesCloneOracle),
            ("parent source dependency indexes exact output and isolation", ParentSourceDependencyIndexesPreserveProjection),
            ("parent source dependency indexes bounded retention", ParentSourceDependencyIndexesStayBounded),
            ("parent source projection memo exact output and slice isolation", ParentSourceProjectionMemoPreservesExactOutput),
            ("parent source projection memo bounds concurrency and retirement", ParentSourceProjectionMemoIsBoundedAndRetired),
            ("parent source revisits preserve edges without frame waits", ParentSourceRevisitsPreserveEdgesWithoutFrameWaits),
            ("parent source projection template exact graph indices and character boundary", ParentSourceProjectionTemplateUsesExactGraphIndices),
            ("audit251 primary held and animation ownership", Audit251PrimaryOwnerAdmission),
            ("audit251 graph depth includes every root", Audit251AllRootGraphDepthAdmission),
            ("sustain admission beam cancellation before native events", () => SustainCancellationPrecedesNativeEvents(true)),
            ("sustain admission composed cancellation before native events", () => SustainCancellationPrecedesNativeEvents(false)),
            ("sustain admission beam payment before periodic damage", () => SustainPaymentPrecedesNativePeriodicDamage(true)),
            ("sustain admission composed payment before periodic damage", () => SustainPaymentPrecedesNativePeriodicDamage(false)),
            ("sustain admission clock and authority", SustainSuccessfulPaymentKeepsClockAndAuthority),
            ("sustain admission uncontrolled event positive", SustainFreeProjectileKeepsUncontrolledEvents),
            ("parent metadata native item clone", ParentMetadataSurvivesNativeClone),
            ("parent metadata definition transport", ParentMetadataSurvivesDefinitionTransport),
            ("parent metadata placed world save", ParentMetadataSurvivesPlacedWorldSave),
            ("parent metadata registry and compact reference hydration", ParentMetadataSurvivesRegistryAndReferenceHydration),
            ("studio menu native visibility scale and launch admission", StudioMenuAdmission),
            ("projectile angle fresh remote hydration", ProjectileAngleFreshRemoteHydration),
            ("projectile angle boundary native storage and authored forward", ProjectileAngleBoundaryPreservesNativeStorage),
            ("air jump final buff tick movement and presentation", AirJumpLastBuffTickKeepsMovementPresentation),
            ("air jump prediction independent component confirmation", AirJumpPredictionReconcilesIndependentComponents),
            ("air jump prediction retirement fences", AirJumpPredictionCannotRebindRetiredLifetime),
            ("air jump prediction ambiguous old confirmation", AirJumpPredictionRejectsAmbiguousOldConfirmation),
            ("air jump prediction new authority history", AirJumpPredictionNewWorldResetsAuthorityHistory),
            ("air jump held one-tick network lifetime", AirJumpHeldOneTickNetworkLifetime),
            ("air jump held two-tick network lifetime", AirJumpHeldTwoTickNetworkLifetime),
            ("air jump held ten-tick network lifetime", AirJumpHeldTenTickNetworkLifetime),
            ("air jump buff snapshot before equip tick", AirJumpBuffSnapshotAdmitsBeforeEquipTick),
            ("air jump equipment sync before equip tick", AirJumpEquipmentSyncAdmitsBeforeEquipTick),
            ("air jump source expiry exhaustion and retirement", AirJumpNetworkRetiresExpiredAndExhaustedSources),
            ("air jump held continuation exact source", AirJumpHeldContinuationRequiresExactSource),
            ("air jump network authority replay and budgets", AirJumpNetworkRejectsUnownedClaimsAndPreservesBudgets),
            ("air jump VFX producer and bounded snapshot wire", AirJumpVfxProducerAndPacketContract),
            ("air jump VFX exact live-source admission", AirJumpVfxLiveSourceAdmission),
            ("air jump VFX native owner callback and relay once", AirJumpVfxNativeStartAndRelayHaveOneOwnerOccurrence),
            ("air jump VFX gravity local and live frame", AirJumpVfxGravityLocalAndLiveFrame),
            ("air jump VFX gravity captured relay", AirJumpVfxGravityCapturedRelay),
            ("air jump VFX gravity source attachment", AirJumpVfxGravitySourceAttachment),
            ("player effect timed buff actual cooldown hit", PlayerEffectBuffReducesActualCooldownOnHit),
            ("player effect weapon event actual cooldown", PlayerEffectWeaponActionMutatesNativeTimer),
            ("player effect equipment pickup and potion hooks", PlayerEffectNativeEquipmentAndPickup),
            ("player effect typed snapshot roundtrip", PlayerEffectSnapshotRetainsNumericMechanics),
            ("player effect automatic mana native lifecycle", PlayerEffectAutomaticManaUsesNativeLifecycle),
            ("player effect hurt immunity actual slot", PlayerEffectHurtImmunityUsesActualSlot),
            ("player effect remote passive state no actions", PlayerEffectRemotePassiveStateDoesNotExecuteActions),
            ("player effect malformed snapshot preserves state", PlayerEffectMalformedStatePreservesAcceptedSnapshot),
            ("existing player stats shared equipment consumers", ExistingPlayerStatsShareEquipmentConsumer),
            ("existing buff stats condition before aggregate cap", ExistingBuffStatsFilterBeforeTheirAggregateCap),
            ("player traversal composition wall equipment", NativeTraversalWallGrantsComposeAfterEquipment),
            ("player traversal composition wall buff", NativeTraversalWallBuffComposesBeforeFinalGrant),
            ("player traversal composition buoyancy equipment", NativeTraversalBuoyancyEquipmentDoesNotGrantFlipper),
            ("player traversal composition buoyancy buff", NativeTraversalBuoyancyBuffDoesNotGrantFlipper),
            ("air jump native renderer anchor admission", AirJumpNativeRenderersShareAnchorAdmission),
            ("player traversal native fields and reset", PlayerTraversalUsesNativeFieldsAndReset),
            ("player traversal timed buff physics and codec", PlayerTraversalBuffPhysicsAndCodec),
            ("player traversal actual buff source snapshot and charges", PlayerTraversalBuffRetainsSourceAndSpentCharges),
            ("authored air jump native duration and movement", AuthoredAirJumpUsesNativeDurationAndMovement),
            ("authored air jump preserves downstream native movement", AuthoredAirJumpPreservesDownstreamMovement),
            ("authored air jump source retirement before native impulse", AuthoredAirJumpRetiresSourceBeforeNativeImpulse),
            ("authored air jump equipment swap preserves consumption", AuthoredAirJumpCannotRefillFromEquipmentSwap),
            ("authored air jump VFX source lifetime", AuthoredAirJumpSourceLifetimeRetiresVfx),
            ("authored air jump duration retains native mod hooks", AuthoredAirJumpDurationPreservesNativeHooks),
            ("authored air jump independent same-item components", AuthoredAirJumpComponentsKeepIndependentCharges),
            ("parent source graph preserves raw source after identity proof bound", ParentSourceGraphKeepsRawSourceWhenIdentityProofIsBounded),
            ("parent source graph core survives optional expansion", ParentSourceGraphNeverReplacesCoreWithUtilityPrefix),
            ("parent source graph preserves omitted callsite refusals", ParentSourceGraphKeepsOmittedCallsiteRefusals),
            ("parent source graph preserves conditions on possible ref writes", ParentSourceGraphRefWritesPreserveTheirConditions),
            ("parent source graph retains opaque vector provenance", ParentSourceGraphRetainsOpaqueVectorProvenance),
            ("parent source graph keeps helpers feeding mechanical guards", ParentSourceGraphKeepsHelpersFeedingMechanicalGuards),
            ("parent source graph bounds shared alias traversal", ParentSourceGraphBoundsSharedAliasTraversal),
            ("parent source graph native core omits presentation noise", ParentSourceGraphNativeCoreOmitsUnrelatedPresentation),
            ("parent source graph preserves larger mechanical bundles", ParentSourceGraphKeepsLargeMechanicalBundle),
            ("parent source graph specializes each native actor context", ParentSourceGraphSpecializesEachNativeActorContext),
            ("parent source graph rejects foreign native actor binding", ParentSourceGraphDoesNotBindForeignNativeActor),
            ("parent source graph retains native identity hazards", ParentSourceGraphRetainsNativeIdentityHazards),
            ("parent source graph caller invocation crosses static helpers", ParentSourceGraphCarriesCallerInvocationAcrossStaticHelpers),
            ("parent source graph groups ref local outputs", ParentSourceGraphGroupsRefLocalOutputs),
            ("parent source graph actor state precedes cosmetic arrays", ParentSourceGraphActorStatePrecedesCosmeticArrays),
            ("parent source graph resolves captured virtual receiver", ParentSourceGraphResolvesCapturedVirtualReceiver),
            ("parent source graph GlobalBuff separates captured receivers", ParentSourceGraphGlobalBuffSeparatesCapturedReceivers),
            ("parent source graph GlobalBuff keeps dispatch boundaries", ParentSourceGraphGlobalBuffKeepsDispatchBoundaries),
            ("parent source graph separates concrete receiver contexts", ParentSourceGraphSeparatesReceiverContexts),
            ("parent source graph keeps virtual dispatch boundaries", ParentSourceGraphKeepsVirtualDispatchBoundaries),
            ("parent source graph excludes unlinked global player context", ParentSourceGraphExcludesUnlinkedPlayerContext),
            ("parent source graph retains item-conditioned player context", ParentSourceGraphRetainsItemConditionedPlayerContext),
            ("parent source graph preserves opaque and identity player context", ParentSourceGraphPreservesOpaqueAndIdentityPlayerContext),
            ("parent source graph retains state-linked player context", ParentSourceGraphRetainsStateLinkedPlayerContext),
            ("parent source graph consumer resolves inherited concrete state", ParentSourceGraphDiscoversInheritedFieldConsumers),
            ("parent source graph consumer preserves unknown receiver", ParentSourceGraphConsumerKeepsUnknownReceiver),
            ("parent source graph consumer preserves direct base calls", ParentSourceGraphConsumerKeepsDirectBaseCall),
            ("parent source graph consumer preserves declaration assembly boundary", ParentSourceGraphConsumerKeepsDeclarationAssemblyBoundary),
            ("parent source graph geometry precedes utility inventory", ParentSourceGraphRetainsGeometryBeforeUtilityInventory),
            ("parent source graph specific state promotions revisit consumer priority", ParentSourceGraphRevisitsSpecificStatePromotions),
            ("parent source graph mutable static reads preserve state lifecycle", ParentSourceGraphFollowsMutableStaticReads),
            ("parent source graph combines direct and helper state reads", ParentSourceGraphCombinesDirectAndHelperStateReads),
            ("parent source graph deferred consumer focus follows later state writes", ParentSourceGraphRefreshesDeferredConsumerFocus),
            ("parent source graph cyclic helpers retain a root path under edge pressure", ParentSourceGraphKeepsCyclesRootedUnderEdgePressure),
            ("parent source graph edge budget retains causal bodies", ParentSourceGraphBudgetsFanoutWithoutDroppingBodies),
            ("parent source graph shared helper keeps alternative retained caller", ParentSourceGraphUsesAlternativeRetainedParent),
            ("parent source graph causal selection survives generic hook crowding", ParentSourceGraphPrioritizesCausalPathsOverGeneralHooks),
            ("parent source graph discovery precedes export and preserves guards", ParentSourceGraphDiscoversBeforeExportAndPreservesGuards),
            ("parent source graph selection preserves conditional state consumers", ParentSourceGraphRetainsConditionalStateConsumers),
            ("parent source graph unresolved identity alternatives", ParentSourceGraphKeepsUnresolvedIdentityAlternatives),
            ("parent source graph native projectile windows", ParentSourceGraphFollowsNativeProjectileWindows),
            ("parent source graph conditional native buff consumers", ParentSourceGraphKeepsConditionalNativeBuffConsumers),
            ("parent source graph conditions events and reachable helpers", ParentSourceGraphKeepsReachabilityConditionsAndEventOwnership),
            ("parent weapon crit native dispatch chain", ParentWeaponCritNativeDispatchIsExplicit),
            ("parent weapon crit ModItem actual native capture", ParentModItemCritSourceReachesCapture),
            ("parent weapon crit GlobalItem actual native capture", ParentGlobalItemCritSourceReachesCapture),
            ("parent weapon crit ModPlayer actual native capture", ParentModPlayerCritSourceReachesCapture),
            ("parent mod hit hook source statements without execution", ParentHitHooksPreserveSourceRequestsWithoutExecution),
            ("parent mod buff source data links without execution", ParentModBuffSourceLinksWithoutExecution),
            ("native parent tooltip hooks", ParentTooltipRunsNativeHooks),
            ("client tooltip wire bounds and pending persistence", ClientTooltipWireBoundsAndPersistence),
            ("client tooltip server escrow end-to-end", ClientTooltipServerCraftEscrowEndToEnd),
            ("client tooltip corrupt save cancellation recovery", ClientTooltipCorruptSaveCancellationRecovery),
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
            ("parent analysis worker snapshots and cancellation", ParentAnalysisWorkerSnapshotsAndCancellation),
            ("parent source cancellation cannot poison shared projectile cache", ProjectileSourceCancellationDoesNotPoisonSharedCache),
            ("parent analysis export cancellation and world retirement", ParentAnalysisExportCancellationAndWorldRetirement),
            ("runtime dump writer exact UTF8 record and disk bounds", RuntimeDumpWriterExactByteAndRowBounds),
            ("runtime dump streams past former file ceiling", RuntimeDumpStreamsPastFormerFileCeiling),
            ("runtime dump failed publication preserves diagnostic files", RuntimeDumpFailedPublicationPreservesDiagnosticFiles),
            ("runtime dump disk probe uses destination filesystem", RuntimeDumpDiskProbeUsesDestinationFilesystem),
            ("runtime dump current vanilla sample incremental capture", RuntimeDumpCurrentVanillaSampleUsesIncrementalExport),
            ("runtime dump canonical definitions exclude redirected aliases", RuntimeDumpCanonicalDefinitionsExcludeRedirectedAliases),
            ("parent deferred craft complete synchronous parity", ParentDeferredCraftMatchesSynchronousFacts),
            ("parent shared source cache bounds and invalidation", ParentSharedSourceCacheBoundsAndInvalidation),
            ("parent source memo budget and projection parity", ParentSourceMemoBudgetBoundsRetainedControlFacts),
            ("runtime dump resolves complete source before publication", RuntimeDumpResolvesSourceBeforePublication),
            ("runtime dump incremental capture main thread bounded queue and publication", RuntimeDumpIncrementalCaptureAndPublication),
            ("runtime dump incremental budget cancellation and IO failure", RuntimeDumpIncrementalBudgetCancellationAndFailure),
            ("parent source graph empty watched fields skip unrelated consumer scan", ParentSourceGraphSkipsUnneededConsumerScan),
            ("parent source graph export cache preserves source and refusals", ParentSourceGraphCacheReusesOnlyCompiledSource),
            ("runtime dump Nebula Rainbow available content roundtrip", RuntimeDumpNebulaRainbowAvailableContentRoundTrip),
            ("runtime dump atomic paired manifest and failed publication", RuntimeDumpPublishesImmutablePairAndPreservesPreviousOnFailure),
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
            ("parent effect slice clocks predicates and loops", ParentEffectSliceKeepsConditionsClocksAndLoops),
            ("parent bounded projectile source references", ParentBoundedProjectileReferences),
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
            ("composable motion independent hand pose attachment and reach admission", ComposableMotionHandAttachmentAdmission),
            ("lateral oscillation single-update law", LateralOscillationPreservesSingleUpdateLaw),
            ("lateral oscillation nonlinear substep matrix", LateralOscillationNonlinearSubstepMatrix),
            ("lateral oscillation world time windows and angular parity", LateralOscillationWorldTimeAndWindow),
            ("lateral oscillation native trajectory convergence", LateralOscillationTrajectoryConvergence),
            ("velocity scale late phases", VelocityScaleLatePhases),
            ("velocity scale admission and subupdates", VelocityScaleNativeAdmissionAndSubupdates),
            ("composable motion ForcesAndIndependentPresentation", ComposableMotionForcesAndIndependentPresentation),
            ("composable motion AttachmentPoseAndReach", ComposableMotionAttachmentPoseAndReach),
            ("composable motion TimedReturnNoHiddenController", ComposableMotionTimedReturnNoHiddenController),
            ("composable motion nearest NPC seek publishes owner velocity", ComposableMotionNpcSeekPublishesOwnerVelocity),
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
            ("audit251 utility snapshot after respawn boundary", UtilitySnapshotAfterRespawnBoundary),
            ("utility respawn correlated life acknowledgement", UtilityRespawnCorrelationRejectsOtherLives),
            ("utility respawn exhaustion and sender authority", UtilityRespawnRetiresExhaustionAndRejectsSpoof),
            ("utility respawn scope and pending activation retirement", UtilityRespawnScopeAndPendingActivations),
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
            ("atlas drawing native pixel alpha", AtlasDrawingUsesBoundedPremultipliedPixels),
            ("atlas book controls responsive bounds and scaled hit areas", AtlasBookControlsStayReachableAcrossUiScales),
            ("atlas discovery search favorites filters and exact ancestry", AtlasDiscoverySelectionKeepsSearchFavoritesAndAncestry),
            ("atlas detail lineage navigation restores discovery context", AtlasDetailLineageNavigationPreservesReturnLocation),
            ("atlas detail generation uses known ancestry", AtlasDetailGenerationUsesKnownAncestry),
            ("lineage exact identity bounded DAG and routing", RecipeLineageUsesExactBoundedDag),
            ("lineage localization native filename prefix", LineageLocalizationUsesNativeFilenamePrefix),
            ("lineage viewport anchored zoom bounded pan and scaled hit targets", LineageViewportKeepsAnchorAndReachableHitTargets),
            ("lineage input overlay release and focus ownership", LineageInputReleasesOwnedFocusAcrossInterruptions),
            ("lineage native hover deferred browser handoff ownership", LineageNativeHoverAndDeferredHandoffKeepOwnership),
            ("lineage bounded adversarial layout cost", LineageBoundedStressReportsActualLayoutCost),
            ("lineage native identity exact registered items", LineageNativeIdentityResolvesOnlyExactRegisteredItems),
            ("lineage current store without inference", LineageLoadsOnlyCurrentStoreWithoutInference),
            ("lineage replacement preserves explicit metadata", LineageRegistrationDoesNotRecoverPriorMetadata),
            ("input-local independent conditions", InputLocalConditionsStayIndependent),
            ("parent hit status facts certified native source", ParentHitStatusFactsAreCertifiedAndMatchNativeRequests),
            ("parent buff effects source certified and parent local", ParentBuffEffectsAreSourceCertifiedAndParentLocal),
            ("parent ammo source semantics actual Prepare", ParentAmmoSourceSemanticsReachPrepare),
            ("parent ammo mod hook shapes read without execution", ParentAmmoModHookShapesAreInspectedNotExecuted),
            ("parent ammo mixed hooks native phase order", ParentAmmoMixedHooksKeepNativePhaseOrder),
            ("use input scope strict DTO and legacy roundtrip", UseInputScopeDtoRoundtripAndStrictAdmission),
            ("use input scope delayed provenance and authority", UseInputScopeRoutesOnceAndRetainsDelayedAdmission),
            ("use input scope native mana payment", ManaInputScopeUsesNativePaymentOnly),
            ("native active input serialized owner server remote", NativeUseSnapshotSerializedPeers),
            ("native fishing readiness witness bounds", NativeFishingReadinessWitnessAndBounds),
            ("native active input quick use preserves held intent", NativeUseSnapshotQuickUseKeepsHeldIntent),
            ("native active input cursor inventory boundary", NativeUseSnapshotCursorInventoryBoundary),
            ("native active input connection generation reset", NativeUseSnapshotConnectionGenerationReset),
            ("native active input A B A ordered switching", NativeUseSnapshotSwitchBackKeepsOwnerOrder),
            ("native active input lifecycle and malformed payloads", NativeUseSnapshotLifecycleAndMalformedInputs),
            ("native active input compact hydration and refusals", NativeUseSnapshotCompactHydrationAndRefusals),
            ("native fishing strict action admission", NativeFishingWireAdmission),
            ("native fishing and weapon ammo selected projections", NativeFishingAndWeaponAmmoSwitchIndependently),
            ("native fishing primary projection and reel costs", NativeFishingProjectionAndReelCosts),
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
            ("generated native prefix survives active use", GeneratedItemNativePrefixSurvivesActiveUse),
            ("generated native prefix placement and ammo independence", GeneratedItemNativePrefixPlacementAndAmmoStayIndependent),
            ("generated native reforge categories follow each shared-type instance", GeneratedItemNativeReforgeSharedTypeCategories),
            ("generated native reforge reset and random roll preserve definition and stats", GeneratedItemNativeReforgeResetAndRoll),
            ("generated native reforge leaves other mods and vanilla unchanged", GeneratedItemNativeReforgeForeignItemsUnchanged),
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
            ("shared image stable readable ownership", SharedImagesStableReadableOwnership),
            ("shared image index containment", SharedImagesIndexContainment),
            ("shared image rejected indexed bytes never render", SharedImagesRejectUncertifiedIndexedBytes),
            ("shared image local reuse and safe legacy migration", SharedImagesCurrentStoreOnly),
            ("shared image unchanged packet transport", SharedImagesPacketTransport),
            ("shared image external source boundary", SharedImagesExternalSourceBoundary),
            ("shared image warm reconnect requests manifest", SharedImagesWarmReconnectRequestsManifest),
            ("shared image late HTTP world retirement", () => SharedImagesLateHttpWorldRetirement().GetAwaiter().GetResult()),
            ("local asset downloads keep generator origin separate from sharing URL", LocalAssetDownloadsKeepGeneratorOrigin),
            ("server asset preparation current external indexed store", () => ServerAssetsPrepareCurrentGeneratorStoreAsync().GetAwaiter().GetResult()),
            ("server asset preparation invalid cancellation and world retirement", () => ServerAssetsRefuseInvalidAndRetiredDownloadsAsync().GetAwaiter().GetResult()),
            ("server asset preparation fresh and cached generation boundary", () => ServerCraftAwaitsAssetsOnFreshAndCachePathsAsync().GetAwaiter().GetResult()),
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
            ("item event waits for authoritative token", ItemEventWaitsForAuthoritativeToken),
            ("item token native sync cycles", ItemTokenNativeSyncCycles),
            ("mod accessory item token native sync", ModAccessoryItemTokenNativeSync),
            ("projectile hit occurrences stay distinct", ProjectileHitOccurrencesStayDistinct),
            ("projectile hit VFX admits retired source", ProjectileHitVfxAdmitsRetiredSource),
            ("remote projectile events have one producer", RemoteProjectileEventsHaveOneProducer),
            ("first held item event publishes token before claim", FirstHeldItemEventPublishesTokenBeforeClaim),
            ("individual material budgets share legacy active detached costs", MaterialBudgetsShareTrailAndDetachedCosts),
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
            ("particle setting controls real dust", ParticleSettingControlsRealDust),
            ("draw setting controls existing budgets", DrawSettingControlsExistingBudgets),
            ("explicit trail world tick capture", ExplicitTrailCapturesWorldTicksWithoutFabrication),
            ("held history remote pending ordering", HeldHistoryRemotePendingOrdering),
            ("held history final pose and fences", HeldHistoryFinalPoseAndFences),
            ("explicit trail strict admission", ExplicitTrailAdmission),
            ("explicit trail geometry and pose", ExplicitTrailGeometryAndPose),
            ("VFX spawn strict admission and uniform projection", VfxSpawnAdmissionAndPureUniformProjection),
            ("VFX spawn element birth and attached coordinates", VfxSpawnElementBirthAndAttachedCoordinates),
            ("VFX spawn library actual birth and velocity", VfxSpawnLibraryBirthPreservesIndependentVelocity),
            ("VFX spawn dust actual birth and velocity", VfxSpawnDustBirthPreservesIndependentVelocity),
            ("VFX expressivity short shapes and rotation frames", VfxExpressivityShortShapeLifetimeAndRotationFrame),
            ("VFX expressivity large sprites", VfxExpressivityLargeSpritesRemainExecutable),
            ("VFX expressivity shape saved parity", VfxShapeCurvesAndAngularBounds),
            ("VFX expressivity orbit orientation and rate", VfxExpressivityOrbitOrientationAndAngularRate),
            ("VFX expressivity dust distribution parity", VfxDustDistributionAndFrames),
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
            ("inventory seeds DTO literal and absence", InventorySeedDtoKeepsLiteralAndAbsence),
            ("inventory seeds native instance locality", InventorySeedNativeHasItemIsInstanceLocal),
            ("inventory seeds actual WorldGen RNG and owner", InventorySeedWorldGenPreservesRandomAndOwner),
            ("placed alpha pivot final bounds uncropped FNA geometry", PlacedAlphaPivotUsesFinalBoundsWithoutCropping),
            ("placed alpha cache one pass selected generation", PlacedAlphaCacheMeasuresOnceAndReturnsSelectedGeneration),
            ("placed alpha DTO optional strict choice", PlacedAlphaDtoKeepsOptionalClosedChoice),
            ("placed alpha ledger projection material physics nonmutation", PlacedAlphaProjectionPreservesMaterialAndPhysics),
            ("VFUI03 status whole block wrapping", VFUI03StatusHoverWrapsWholeBlockForNativeClamp),
            ("VFUI03 native whole cursor block clamp", VFUI03NativeWholeCursorBlockClampsAtAllEdges),
            ("VFUI04 stable countdown and compact numbers", VFUI04StatusCountdownIsStableWholeSecondsAndNumbersStayNonzero),
            ("VFUI14 captured crystal native mana formula", VFUI14CurrentAccessoryUsesManaMultiplier),
            ("VFUI17 buff order refresh and expiry", VFUI17DistinctBuffsAggregateAndExpireInEitherOrder),
            ("VFUI18 captured keg invisibility preservation", VFUI18CurrentUtilityPreservesInvisibilityBuff),
            ("VFUI19 captured input costs and tooltip", VFUI19CurrentInputsKeepAuthoredManaAndStackCosts),
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
            ("safe blink native body collision", SafeBlinkUsesNativeBodyCollision),
            ("blink feet native rod oracle", BlinkFeetMatchesNativeTeleportRod),
            ("blink feet surface and blocked destinations", BlinkFeetSurfaceAndBlockedDestinations),
            ("blink feet event point stays world centre", BlinkFeetKeepsEventWorldPoint),
            ("blink feet range and world edges", BlinkFeetKeepsRangeAndWorldEdges),
            ("blink feet owner authority and packet coordinates", BlinkFeetKeepsLocalAuthorityAndPacketCoordinates),
            ("blink authored range reaches teleport", BlinkAuthoredRangeReachesTeleport),
            ("mobility bounds native consumption", MobilityBoundsRejectBeforeNativeConsumption),
            ("mobility event bounds and unsafe semantics", EventMobilityBoundsPreserveCooldownAndUnsafeSolids),
            ("mobility recall native bed validity", RecallUsesNativeBedValidityAndRejectsInvalidSpawn),
            ("utility use costs native exhaustion", UtilityExhaustionRefusesNativeCosts),
            ("utility use costs capacity admission", UtilityCapacityRefusesNativeCosts),
            ("utility use costs mixed effects", UtilityRefusalPreservesMixedActions),
            ("utility use costs actual outcome", UtilityUseStackFollowsActualOutcome),
            ("utility use costs input scope", UtilityExhaustionRespectsEventInputScope),
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
            ("craft transient HTTP exhaustion retains diagnostics", () => CraftExhaustedTransientFailureRetainsDiagnosticsAsync(false).GetAwaiter().GetResult()),
            ("craft transient transport exhaustion retains diagnostics", () => CraftExhaustedTransientFailureRetainsDiagnosticsAsync(true).GetAwaiter().GetResult()),
            ("craft successful cache recovery and retry clear diagnostics", () => CraftSuccessfulRecoveryClearsFailureStateAsync().GetAwaiter().GetResult()),
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
            ("owned tile exact shape and symbolic identity", OwnedTileShapeAndSymbolicIdentityStayExact),
            ("owned tile authored structural registration", OwnedTileStructuralRegistrationUsesAuthoredShape),
            ("owned tile legacy world refusal preserves saves", OwnedTileLegacyWorldRefusesWithoutSaveLoss),
            ("native semantic catalogs dependency-specific admission", NativeSemanticCatalogsMatchLoadedContracts),
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
            ("native chest authored light VFX actor liveness", NativeChestPreservesLightVfxAndActorLiveness),
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
            ("front_hand observer counterproofs", FrontHandObserverCounterproofs),
            ("front_hand cursor eventually publishes stationary aim", FrontHandCursorEventuallyPublishesStationaryAim),
            ("front_hand event direction and delayed snapshot", FrontHandGameplayEventsRetainSelectedAxis),
            ("front_hand history and event snapshot exact body scale", FrontHandHistoryAndEventSnapshotPreserveExactBodyScale),
            ("item VFX preserves world-clock cadence", ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick),
            ("item VFX hit positions relay and event budgets", ItemVfxEventPositionsRelayAndBudgets),
            ("beam live damage, collision ramps and explicit body width", BeamRampsConsumeLiveDamageAndSharedBodyGeometry),
            ("beam native mana cadence and world clock", BeamSustainUsesNativeManaAndWorldClock),
            ("beam failed mana and control loss terminate", BeamManaFailureAndControlLossTerminateBeforeFurtherPayment),
            ("generated channel child death preserves root ownership", GeneratedChannelChildDeathDoesNotCancelAndRootDeathDoes),
            ("generated channel retired root never cancels new use", GeneratedChannelRetiredRootCannotCancelNewUse),
            ("generated channel native control and mana termination", GeneratedChannelNativeTerminationPreservesControlAndMana),
            ("beam native scan clips collision body and VFX endpoints", BeamLaserScanClipsCollisionBodyAndVfxPathTogether),
        };
        checks = System.Linq.Enumerable.ToArray(
            System.Linq.Enumerable.Concat(checks, ComposableMotionAdmissionChecks()));
        // Validate actual compiled registrations, not a Python regex reconstruction of C# syntax.
        var names = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
        foreach (var entry in checks)
            if (string.IsNullOrWhiteSpace(entry.Name) || !names.Add(entry.Name))
                throw new InvalidOperationException("Native check names must be nonempty and unique");
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
                    TestChargeComponents(data, entity, 60, 2, 2, 2, 0);
                    // Current absence, not an explicit null component.
                    var wire = System.Text.Json.Nodes.JsonNode.Parse(data.ToJson())!;
                    wire["runtimeProgram"]!["entities"]!.AsArray()
                        .Single(row => row!["id"]!.GetValue<string>() == entity.Id)!.AsObject().Remove("attachment");
                    data = InfiniCrafterLocal.Common.Models.GeneratedItemData.FromJson(wire.ToJsonString())
                        ?? throw new InvalidOperationException("current unbound charge fixture refused");
                    entity = data.RuntimeProgram.TryGetEntity("root")!;
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
                ActionCode = RuntimeEventActionCode.DamageNearby, DelayTicks = 1, RadiusPx = 16, MaxTargets = 1,
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
