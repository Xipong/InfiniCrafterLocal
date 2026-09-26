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
            if (args.Length == 2 && args[0] == "--replay-contracts")
                return ReplayGeneratedContracts(args[1]);
            if (args.Length != 0)
                throw new ArgumentException("Expected --replay-contracts <jsonl-path>");
            return RunChecks();
        }
        finally { System.IO.Directory.Delete(sandbox, recursive: true); }
    }

    private static int RunChecks()
    {
        (string Name, Action Check)[] checks = {
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
            ("primitive impact ring does not require impact texture", PrimitiveImpactRingDoesNotRequireImpactTexture),
            ("VFX events follow actual item and projectile producers", VfxEventReferencesFollowRuntimeProducers),
            ("detached VFX state is bounded and cleared", DetachedVfxStateIsBoundedAndCleared),
            ("cache-only flag preserves request", CacheOnlyFlagPreservesRequest),
            ("generator delivery requires identity", GeneratorDeliveryRequiresIdentity),
            ("generated parent prefix is request-only", GeneratedParentPrefixIsRequestOnly),
            ("craft identity rejects failed defaults", CraftIdentityRejectsFailedDefaults),
            ("inventory ammo keeps generated definition", InventoryAmmoKeepsGeneratedDefinition),
            ("parent placement facts reach craft snapshot", ParentPlacementFactsReachCraftSnapshot),
            ("runtime entity count respects declared limit", RuntimeEntityCountRespectsDeclaredLimit),
            ("run-speed equipment applies after vanilla movement", RunSpeedEquipmentAppliesAfterVanillaMovement),
            ("equipment authored ranges reach player", EquipmentAuthoredRangesReachPlayer),
            ("equipment class damage reaches exact DamageClass", EquipmentClassDamageReachesExactDamageClass),
            ("generated ammo preserves exact projectile on direct use", GeneratedAmmoDirectUseKeepsDeclaredProjectile),
            ("generated ammo preserves exact rocket and solution selection", GeneratedAmmoPickAmmoKeepsExactRocketAndSolution),
            ("generated ammo leaves unrelated category unchanged", GeneratedAmmoPickAmmoRejectsUnrelatedCategoryRewrites),
            ("generated ammo preserves network and save boundaries", GeneratedAmmoNetworkAndSaveBoundaries),
            ("generated whip applies same-owner summon source bonus", WhipImpactMarksOnlyItsOwnerForSummonSourceDamage),
            ("generated whip range changes geometry and collision", WhipGeometryTracksEquippedRangeInCollision),
            ("proximity missile expiry VFX matches event lifecycle", ProximityMissileExpireVfxMatchesNaturalExpiry),
            ("peer events preserve observed spawn-budget snapshot", PeerEventDoesNotOverwriteReceivedSpawnBudgetSnapshot),
            ("root binding capacity is independent of event-spawn budget", RootBindingSpawnCapacityRespectsAuthoredCountAndIndependentEventLedger),
            ("legacy equipment clamps remain unchanged", LegacyEquipmentClampsRemainUnchanged),
            ("legacy unclamped equipment stats remain intact", LegacyUnclampedEquipmentStatsRemainIntact),
            ("signed accessory defense reaches player", SignedAccessoryDefenseReachesPlayer),
            ("blink authored range reaches teleport", BlinkAuthoredRangeReachesTeleport),
            ("disposed asset download cannot publish", DisposedAssetDownloadCannotPublish),
            ("pull modes preserve subject and authority", PullModesPreserveSubjectAndAuthority),
            ("owner hit NPC status uses native sync", OwnerHitNpcEffectsUseNativeSync),
            ("owner projectile hit bridges exact NPC pull", OwnerProjectileHitBridgesNpcPull),
            ("retired projectile hit receipt keeps generation", RetiredProjectileHitKeepsGeneration),
            ("delayed owner hit never retargets replaced NPC", DelayedHitNeverRetargetsReplacedNpc),
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
            ("neutral item omissions preserve exact Item projection", NeutralItemOmissionsPreserveProjection),
            ("neutral buff omissions reach real player effects", NeutralBuffOmissionsReachRealPlayerEffects),
        };
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

    private static void Equal<T>(T expected, T actual, string label) where T : IEquatable<T>
    {
        if (!expected.Equals(actual))
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
