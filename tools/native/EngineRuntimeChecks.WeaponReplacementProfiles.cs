using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Microsoft.Xna.Framework;
using Terraria.DataStructures;
using MonoMod.RuntimeDetour;

internal static partial class EngineRuntimeChecks
{
    private static JsonObject WeaponSourceAmmo(Item weapon, Player? player = null)
    {
        var raw = JsonSerializer.SerializeToNode(typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, new object?[] { weapon, player }))!.AsObject();
        // Isolate the source supplement; original main inventory tests separately
        // assert observations, availability, multiplicity and fingerprint scope.
        foreach (string key in new[] { "playerInventoryObservation", "playerInventoryAmmoRaw",
            "playerInventoryProjectileRaw", "fallbackAmmoRaw", "fallbackProjectileRaw", "candidateProjectileBindings" })
            raw.Remove(key);
        var profiles = raw["nativeReplacementProjectileRaw"]!.AsArray()
            .OfType<JsonObject>().Where(profile => profile["sourceReferences"] is JsonArray)
            .Select(profile => profile.DeepClone()).ToArray();
        raw["nativeReplacementProjectileRaw"] = new JsonArray(profiles);
        return raw;
    }

    private static void ExportWeaponSourceHookFixture(string name, JsonObject raw)
    {
        string? export = Environment.GetEnvironmentVariable("INFINI_REPLACEMENT_PROFILE_DIR");
        if (string.IsNullOrWhiteSpace(export)) return;
        Directory.CreateDirectory(export);
        File.WriteAllText(Path.Combine(export, "hook-" + name + ".ammo.json"), raw.ToJsonString());
        File.WriteAllText(Path.Combine(export, "hook-" + name + ".source.json"), new JsonObject {
            ["fixtureKind"] = "source_defined_hooks_not_loaded_mod_capture",
            ["captureMethod"] = "GeneratorClient.AmmoRawFromItem",
            ["fixtureName"] = name,
            ["scope"] = "Native producer output from explicitly attached headless source-defined hook fixtures, not full Prepare or a live installed mod roster. Source inspection never executes the shooting hooks."
        }.ToJsonString());
    }

    private static void AssertCompleteWeaponSourceProfile(JsonObject profile, Item weapon)
    {
        int type = profile["type"]!.GetValue<int>();
        var expected = JsonSerializer.SerializeToNode(GeneratorClient.ProjectileRawSnapshot(type, weapon.shootSpeed,
            "source_inspected_replacement_projectile_identity_not_final_shot", weapon, -1))!.AsObject();
        expected.Remove("itemShootSpeed");
        var mechanics = (JsonObject)profile.DeepClone();
        mechanics.Remove("sourceReferences"); mechanics.Remove("profileScope");
        Equal(true, JsonNode.DeepEquals(expected, mechanics), "replacement keeps every canonical projectile field, source mechanic, status and child reference");
        Equal(true, profile["sourceReferences"]!.AsArray().Count > 0, "profile identity is tied to exact weapon source evidence");
        Equal(false, profile.ContainsKey("itemShootSpeed"), "source profile does not pretend to know the final launch speed");
    }

    private static void WeaponReplacementProfilesPreserveNativeMechanics()
    {
        using var state = new NativeActorState();
        foreach (var (itemType, outputType) in new[] {
            (ItemID.MoltenFury, ProjectileID.FireArrow), (4381, 819), (3052, 495), (2223, 357),
            (3019, 485), (4953, 932), (3930, 714),
            (ItemID.WoodenBow, 0), (ItemID.DaedalusStormbow, 0), (1946, 0) })
        {
            var weapon = new Item(itemType);
            var raw = WeaponSourceAmmo(weapon);
            var profiles = raw["nativeReplacementProjectileRaw"]!.AsArray().OfType<JsonObject>().ToArray();
            Equal(outputType == 0 ? 0 : 1, profiles.Length, "literal output profiles only; pass-through/table selection does not guess ammunition");
            using var element = JsonDocument.Parse(raw.ToJsonString());
            Equal(true, element.RootElement.TryGetProperty("projectileSemanticsReference", out _), "source supplement retains certificate");
            Equal("unknown_without_gameplay_execution", raw["projectileSemanticsReference"]!["finalShotOutcome"]!.GetValue<string>(), "native profile is not the final shot");
            if (outputType == 0) continue;
            var profile = profiles.Single();
            Equal(outputType, profile["type"]!.GetValue<int>(), "actual weapon source literal selects the profile without an ammo sample");
            AssertCompleteWeaponSourceProfile(profile, weapon);
            var reference = profile["sourceReferences"]![0]!.AsObject();
            Equal(true, reference["sourceVerification"] is JsonObject && reference["sourceMethodSha256"] is JsonValue
                && reference["sourceModuleVersionId"] is JsonValue, "native rule provenance and verification are retained");
            Equal("source_conditions_not_evaluated", reference["conditionStatus"]!.GetValue<string>(), "profile does not evaluate its branch");
            if (itemType is ItemID.MoltenFury or 3019 or 4953)
                Equal(ProjectileID.WoodenArrowFriendly, reference["sourceFact"]!["whenInputProjectileId"]!.GetValue<int>(), "conditional input predicate survives unresolved");
            if (itemType == 4953)
            {
                Equal(2, profile["sourceReferences"]!.AsArray().Count, "one full profile preserves both input and player-state source sites");
                Equal(true, profile["sourceReferences"]!.AsArray().OfType<JsonObject>().Any(r => r["sourceFact"]?["whenSourceCondition"] is JsonObject), "state predicate survives into exact profile provenance");
            }
            if (itemType == 3930)
                Equal("native_fixed_projectile_spawn", reference["kind"]!.GetValue<string>(), "own fixed spawn uses certified source identity, not launcher table");
            if (itemType == ItemID.MoltenFury)
            {
                Equal(1, profile["penetrate"]!.GetValue<int>(), "Molten Fury converted fire arrow penetration restored");
                Equal(1200, profile["timeLeft"]!.GetValue<int>(), "Molten Fury converted fire arrow lifetime restored");
                Equal(0, profile["extraUpdates"]!.GetValue<int>(), "Molten Fury converted fire arrow update count restored");
                Equal(true, profile["attackReference"] is JsonObject && profile.ContainsKey("collisionReference"), "attack/collision source contract restored including observed nulls");
                var outcome = profile["onHitStatusReference"]!["randomOutcomes"]![0]!["alternatives"]![0]!;
                Equal(1, outcome["probabilityNumerator"]!.GetValue<int>(), "fire status chance numerator restored");
                Equal(3, outcome["probabilityDenominator"]!.GetValue<int>(), "fire status chance denominator restored");
                Equal(BuffID.OnFire, outcome["effects"]![0]!["buffId"]!.GetValue<int>(), "native fire status identity restored");
                Equal(180, outcome["effects"]![0]!["durationTicksMin"]!.GetValue<int>(), "native fire status duration restored");
            }
            var owner = new Player(); owner.inventory = null!;
            Equal(true, JsonNode.DeepEquals(raw, WeaponSourceAmmo(weapon, owner)), "profile requires no accessible inventory");
        }
        WeaponReplacementProfilesKeepUnresolvedNativeLiteralEvidence();
    }

    private static void WeaponReplacementProfilesKeepUnresolvedNativeLiteralEvidence()
    {
        // Synthetic source-only catalog fixture: never execute altered game IL.
        // Only applicability/ownership metadata changes, and the catalog is
        // restored even if an assertion fails.
        var weapon = new Item(ItemID.MoltenFury);
        var before = WeaponSourceAmmo(weapon);
        var nativeStage = before["projectileSemanticsReference"]!["stages"]!.AsArray().OfType<JsonObject>()
            .Single(stage => stage["method"]!.GetValue<string>() == "Player.ItemCheck_Shoot");
        string key = "Player.ItemCheck_Shoot:" + nativeStage["sourceMethodSha256"]!.GetValue<string>()
            + ":" + nativeStage["sourceModuleVersionId"]!.GetValue<string>();
        var catalog = NativeAmmoFactsCatalog.Sources[key];
        string original = catalog[weapon.type];
        try
        {
            foreach (string ownership in new[] { "proved_item_guard", "unproved_item_guard" })
            {
                var facts = JsonNode.Parse(original)!.AsObject();
                var literal = facts["rules"]!.AsArray().OfType<JsonObject>().Single().DeepClone().AsObject();
                literal.Remove("whenInputProjectileId");
                literal["applicability"] = "unknown";
                literal["reason"] = "unknown_enclosing_guard";
                literal["ownershipStatus"] = ownership;
                facts["rules"] = new JsonArray();
                facts["unresolvedLiteralWrites"] = new JsonArray(literal);
                catalog[weapon.type] = facts.ToJsonString();
                var raw = WeaponSourceAmmo(weapon);
                var semantics = raw["projectileSemanticsReference"]!;
                Equal("unknown_native_projectile_semantics", semantics["ammoProjectileRelation"]!.GetValue<string>(),
                    "synthetic unresolved native literal never certifies replacement or retention");
                Equal("unknown_without_gameplay_execution", semantics["finalShotOutcome"]!.GetValue<string>(),
                    "synthetic source-only literal is not a final fired projectile");
                var stage = semantics["stages"]!.AsArray().OfType<JsonObject>()
                    .Single(row => row["method"]!.GetValue<string>() == "Player.ItemCheck_Shoot");
                Equal(0, stage["rules"]!.AsArray().Count, "unresolved literal is not promoted to a certified rule");
                Equal(true, JsonNode.DeepEquals(literal, stage["unresolvedLiteralWrites"]![0]),
                    "synthetic unresolved literal and its ownership/guard evidence remain visible");
                var profiles = raw["nativeReplacementProjectileRaw"]!.AsArray();
                Equal(ownership == "proved_item_guard" ? 1 : 0, profiles.Count,
                    "only proved item ownership permits an unresolved literal projectile profile");
                if (profiles.Count == 0) continue;
                string? export = Environment.GetEnvironmentVariable("INFINI_REPLACEMENT_PROFILE_DIR");
                if (!string.IsNullOrWhiteSpace(export))
                {
                    Directory.CreateDirectory(export);
                    File.WriteAllText(Path.Combine(export, "native-unknown-outer-guard.ammo.json"), raw.ToJsonString());
                    File.WriteAllText(Path.Combine(export, "native-unknown-outer-guard.source.json"), new JsonObject {
                        ["fixtureKind"] = "synthetic_source_only_native_catalog_metadata",
                        ["captureMethod"] = "GeneratorClient.AmmoRawFromItem",
                        ["fixtureName"] = "native-unknown-outer-guard",
                        ["scope"] = "Actual native producer output after temporary source-catalog metadata mutation of the certified Molten Fury row. Ownership is proved; enclosing-guard applicability is deliberately unknown. No altered game IL or shot is executed. Catalog restored after fixture."
                    }.ToJsonString());
                }
                var profile = profiles[0]!.AsObject();
                Equal(ProjectileID.FireArrow, profile["type"]!.GetValue<int>(), "proved source identity survives unknown applicability");
                AssertCompleteWeaponSourceProfile(profile, weapon);
                var reference = profile["sourceReferences"]!.AsArray().Single()!;
                Equal(true, reference["sourcePath"]!.GetValue<string>().EndsWith(".unresolvedLiteralWrites[0]", StringComparison.Ordinal),
                    "profile references unresolved evidence rather than a certified rule");
                Equal("native_literal_write_unresolved_applicability", reference["kind"]!.GetValue<string>(), "unresolved profile kind does not claim replacement");
                Equal("source_applicability_unresolved", reference["conditionStatus"]!.GetValue<string>(), "unresolved applicability remains explicit on the profile");
                Equal(true, JsonNode.DeepEquals(literal, reference["sourceFact"]), "profile preserves exact unresolved source fact");
                Equal(true, reference["sourceVerification"] is JsonObject && reference["sourceMethodSha256"] is JsonValue
                    && reference["sourceModuleVersionId"] is JsonValue, "unresolved profile retains source provenance");
                facts["rules"] = JsonNode.Parse(original)!["rules"]!.DeepClone();
                catalog[weapon.type] = facts.ToJsonString();
                var mixed = WeaponSourceAmmo(weapon);
                var mixedSemantics = mixed["projectileSemanticsReference"]!;
                Equal("unknown_native_projectile_semantics", mixedSemantics["ammoProjectileRelation"]!.GetValue<string>(),
                    "certified rules do not hide unresolved native applicability");
                Equal(true, mixedSemantics["unknowns"]!.AsArray().Any(value =>
                    value!.GetValue<string>().Contains("unresolved applicability", StringComparison.Ordinal)),
                    "mixed certified and unresolved writes explicitly disclose partial applicability");
                Equal(2, mixed["nativeReplacementProjectileRaw"]![0]!["sourceReferences"]!.AsArray().Count,
                    "same literal retains both certified and unresolved source sites without conflation");
            }
            var opaqueFacts = JsonNode.Parse(original)!.AsObject();
            opaqueFacts["unrecognizedProjectileWriteOffsets"] = new JsonArray(123456);
            opaqueFacts["unresolvedLiteralWrites"] = new JsonArray();
            catalog[weapon.type] = opaqueFacts.ToJsonString();
            var opaqueRaw = WeaponSourceAmmo(weapon);
            Equal("unknown_native_projectile_semantics", opaqueRaw["projectileSemanticsReference"]!["ammoProjectileRelation"]!.GetValue<string>(),
                "certified rule plus an opaque write offset cannot certify an aggregate mapping");
            Equal(true, JsonNode.DeepEquals(before["nativeReplacementProjectileRaw"], opaqueRaw["nativeReplacementProjectileRaw"]),
                "opaque write uncertainty preserves the exact independent known projectile profile");
            var opaqueStage = opaqueRaw["projectileSemanticsReference"]!["stages"]!.AsArray().OfType<JsonObject>()
                .Single(stage => stage["method"]!.GetValue<string>() == "Player.ItemCheck_Shoot");
            Equal(123456, opaqueStage["unrecognizedProjectileWriteOffsets"]![0]!.GetValue<int>(),
                "synthetic opaque source offset remains visible with the certified rule");
        }
        finally { catalog[weapon.type] = original; }
        Equal(true, JsonNode.DeepEquals(before, WeaponSourceAmmo(weapon)), "synthetic catalog fixture restores native source evidence exactly");
    }

    private sealed class ChildOutputAmmoHook : ModItem
    {
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = 617; }
    }
    private sealed class InvalidOutputAmmoHook : ModItem
    {
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = -1; }
    }
    private sealed class UnknownAfterLiteralAmmoHook : ModItem
    {
        internal static int Calls;
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = ProjectileID.Bee; }
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        { Calls++; return player.statLife > 20; }
    }
    private sealed class DuplicateLiteralAmmoHook : ModItem
    {
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = ProjectileID.Bee; }
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        { Projectile.NewProjectile(source, position, velocity, ProjectileID.Bee, damage, knockback, player.whoAmI); return false; }
    }

    private static void WeaponReplacementProfilesKeepConditionalAndOpaqueHookEvidence()
    {
        using var state = new NativeActorState();
        OpaqueAmmoHook.Calls = UnknownAfterLiteralAmmoHook.Calls = 0;
        foreach (var (host, output) in new (ModItem Host, int Output)[] {
            (new ConstantAmmoHook(), ProjectileID.Bee), (new ConditionalAmmoHook(), ProjectileID.Bee),
            (new OwnProjectileAmmoHook(), ProjectileID.Bee), (new ChildOutputAmmoHook(), 617),
            (new UnknownAfterLiteralAmmoHook(), ProjectileID.Bee), (new DuplicateLiteralAmmoHook(), ProjectileID.Bee),
            (new InvalidOutputAmmoHook(), 0), (new InvalidOwnProjectileAmmoHook(), 0),
            (new OpaqueAmmoHook(), 0), (new SuppressedAmmoHook(), 0) })
        {
            var weapon = new Item(ItemID.WoodenBow);
            typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(weapon, host);
            var raw = WeaponSourceAmmo(weapon);
            ExportWeaponSourceHookFixture(host.GetType().Name, raw);
            var profiles = raw["nativeReplacementProjectileRaw"]!.AsArray();
            Equal(output == 0 ? 0 : 1, profiles.Count, "only safely inspected literal identities become profiles");
            if (output == 0)
            {
                if (host is not SuppressedAmmoHook)
                    Equal("unknown_hook_projectile_semantics", raw["projectileSemanticsReference"]!["ammoProjectileRelation"]!.GetValue<string>(), "invalid or opaque source keeps unknown semantics");
                if (host is InvalidOutputAmmoHook or InvalidOwnProjectileAmmoHook)
                    Equal(true, raw["projectileSemanticsReference"]!["hooks"]![0]!["unresolved"] is JsonValue, "invalid identity has an explicit reason, not evidence of no conversion");
                continue;
            }
            var profile = profiles[0]!.AsObject();
            Equal(output, profile["type"]!.GetValue<int>(), "hook literal profile uses real registered defaults");
            AssertCompleteWeaponSourceProfile(profile, weapon);
            var references = profile["sourceReferences"]!.AsArray();
            Equal(host is DuplicateLiteralAmmoHook ? 2 : 1, references.Count, "one profile retains every distinct source site without duplicates");
            foreach (var reference in references)
                Equal(true, reference!["sourceFact"]!["sourceMethodSha256"] is JsonValue
                    && reference["sourceFact"]!["sourceModuleVersionId"] is JsonValue, "inspected hook certificate survives");
            if (host is ConditionalAmmoHook)
                Equal(ProjectileID.WoodenArrowFriendly, references[0]!["sourceFact"]!["whenInputProjectileId"]!.GetValue<int>(), "conditional hook profile survives unresolved ammo input");
            if (host is UnknownAfterLiteralAmmoHook)
                Equal("unknown_hook_projectile_semantics", raw["projectileSemanticsReference"]!["ammoProjectileRelation"]!.GetValue<string>(), "surrounding opaque admission remains unknown without deleting the literal profile");
            if (host is ChildOutputAmmoHook)
                Equal(618, profile["referencedProjectiles"]!["references"]![0]!["type"]!.GetValue<int>(), "full source output profile preserves its canonical single-hop children");
        }
        Equal(0, OpaqueAmmoHook.Calls + UnknownAfterLiteralAmmoHook.Calls, "no inspected shooting hook is executed by profile capture");
        AssertWeaponReplacementRosterHasNoSampleLimit();
        AssertWeaponReplacementUnavailableDefaultsAreExplicit();
    }

    private static void AssertWeaponReplacementUnavailableDefaultsAreExplicit()
    {
        var weapon = new Item(ItemID.WoodenBow);
        typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(weapon, new ConstantAmmoHook());
        using var defaults = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.SetDefaults), new[] { typeof(int) })!,
            (Action<Action<Projectile, int>, Projectile, int>)((original, projectile, type) => {
                if (type == ProjectileID.Bee) throw new InvalidOperationException("source-defined unavailable defaults fixture");
                original(projectile, type);
            }));
        var raw = WeaponSourceAmmo(weapon);
        ExportWeaponSourceHookFixture("UnavailableProjectileDefaults", raw);
        var profile = raw["nativeReplacementProjectileRaw"]![0]!.AsObject();
        Equal(ProjectileID.Bee, profile["type"]!.GetValue<int>(), "unavailable defaults do not erase the known source identity");
        Equal(true, profile["unavailable"]!.GetValue<bool>(), "default capture failure remains explicit");
        Equal("projectile_defaults_snapshot_unavailable", profile["unresolved"]!.GetValue<string>(), "capture failure has a specific reason");
        Equal(1, profile["sourceReferences"]!.AsArray().Count, "unavailable profile still has complete source provenance");
        Equal(false, profile.ContainsKey("timeLeft") || profile.ContainsKey("extraUpdates") || profile.ContainsKey("attackReference"),
            "missing mechanics and clocks stay missing rather than gaining fabricated defaults");
    }

    private sealed class FirstLiteralGlobalAmmoHook : GlobalItem
    {
        public override void ModifyShootStats(Item item, Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = 1; }
    }
    private sealed class SecondLiteralGlobalAmmoHook : GlobalItem
    {
        public override void ModifyShootStats(Item item, Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = 2; }
    }
    private sealed class ThirdLiteralGlobalAmmoHook : GlobalItem
    {
        public override void ModifyShootStats(Item item, Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = 617; }
    }
    private sealed class FourthLiteralGlobalAmmoHook : GlobalItem
    {
        public override void ModifyShootStats(Item item, Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = 974; }
    }

    private static void AssertWeaponReplacementRosterHasNoSampleLimit()
    {
        var lookup = typeof(Terraria.ModLoader.Core.GlobalTypeLookups<GlobalItem>)
            .GetField("_globalsForType", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? previous = lookup.GetValue(null);
        try
        {
            var weapon = new Item(ItemID.WoodenBow);
            typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(weapon, new ConditionalAmmoHook());
            var globals = new GlobalItem[ItemLoader.ItemCount][];
            for (int i = 0; i < globals.Length; i++) globals[i] = Array.Empty<GlobalItem>();
            globals[weapon.type] = new GlobalItem[] { new FirstLiteralGlobalAmmoHook(), new SecondLiteralGlobalAmmoHook(),
                new ThirdLiteralGlobalAmmoHook(), new FourthLiteralGlobalAmmoHook(), new ConstantGlobalAmmoHook() };
            var perEntity = typeof(GlobalType<GlobalItem>).GetProperty("PerEntityIndex", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!;
            foreach (var global in globals[weapon.type]) perEntity.SetValue(global, (short)-1);
            typeof(Item).GetField("_globals", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(weapon, Array.Empty<GlobalItem>());
            lookup.SetValue(null, globals);
            var owner = new Player(); owner.inventory[54] = new Item(ItemID.FlamingArrow, 7);
            var raw = WeaponSourceAmmo(weapon, owner);
            ExportWeaponSourceHookFixture("FiveOutputRoster", raw);
            var profiles = raw["nativeReplacementProjectileRaw"]!.AsArray().OfType<JsonObject>().ToArray();
            Equal(5, profiles.Length, "all five own source output profiles survive; no old three-ammo sample bound");
            Equal(true, profiles.Select(profile => profile["type"]!.GetValue<int>()).SequenceEqual(new[] { ProjectileID.Bee, 1, 2, 617, 974 }),
                "source inspection order remains deterministic without pretending to execute dispatch");
            Equal(2, profiles[0]["sourceReferences"]!.AsArray().Count, "same literal retains ModItem condition and GlobalItem site separately");
            Equal(1, profiles[0]["sourceReferences"]![0]!["sourceFact"]!["whenInputProjectileId"]!.GetValue<int>(),
                "conditional literal survives even when present ammo does not match its predicate");
            Equal(true, profiles.Single(profile => profile["type"]!.GetValue<int>() == 1)["motionReference"] is JsonObject,
                "known source profile retains real positive native arrow motion reference");
            Equal(true, profiles.Single(profile => profile["type"]!.GetValue<int>() == 974)["collisionReference"] is JsonObject,
                "known source profile retains real positive native collision reference");
            Equal(618, profiles.Single(profile => profile["type"]!.GetValue<int>() == 617)["referencedProjectiles"]!["references"]![0]!["type"]!.GetValue<int>(),
                "known source profile retains actual native single-hop child mechanics");
            foreach (var profile in profiles) AssertCompleteWeaponSourceProfile(profile, weapon);
            owner.inventory = null!;
            Equal(true, JsonNode.DeepEquals(raw, WeaponSourceAmmo(weapon, owner)), "five-output source roster is entirely independent of ammo presence");
            // The normal entrypoint reconstructs Item defaults, so the manually
            // attached ModItem is intentionally lost. Registered lookup globals
            // remain attached to the reconstructed vanilla host in this fixture.
            var prepared = new GeneratorClient().PrepareDeferred(new Item(ItemID.WoodenBow), new Item(ItemID.Boomstick), new Player());
            PumpParentAnalysis(Task.Run(prepared.CompleteAnalysis));
            var packet = JsonNode.Parse(prepared.PayloadJson)!;
            Equal(5, packet["itemA"]!["ammoRaw"]!["nativeReplacementProjectileRaw"]!.AsArray().Count,
                "actual deferred Prepare retains all five source-defined GlobalItem outputs");
            AssertParentFingerprintNativeFacts(packet["itemA"]!["ammoRaw"], packet["itemA"]!["fingerprint"]!["ammoRaw"],
                "actual source-defined roster packet root/fingerprint parity", requireRootView: true);
            string? export = Environment.GetEnvironmentVariable("INFINI_REPLACEMENT_PROFILE_DIR");
            if (!string.IsNullOrWhiteSpace(export))
            {
                File.WriteAllText(Path.Combine(export, "source-defined-roster.json"), prepared.PayloadJson);
                File.WriteAllText(Path.Combine(export, "source-defined-roster.source.json"), new JsonObject {
                    ["fixtureKind"] = "source_defined_global_hooks_not_loaded_mod_capture",
                    ["captureMethod"] = "GeneratorClient.PrepareDeferred and CompleteAnalysis",
                    ["scope"] = "Actual full deferred packet with five explicitly attached headless GlobalItem source fixtures and real native projectile defaults/source. Not a live installed mod roster."
                }.ToJsonString());
            }
        }
        finally { lookup.SetValue(null, previous); }
    }

    private static void WeaponReplacementProfilesMatchDeferredAndCancelledCapture()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var client = new GeneratorClient();
        string? export = Environment.GetEnvironmentVariable("INFINI_REPLACEMENT_PROFILE_DIR");
        if (!string.IsNullOrWhiteSpace(export)) Directory.CreateDirectory(export);
        foreach (int type in new[] { ItemID.MoltenFury, 2223, 3019, 4381, 3930, ItemID.DaedalusStormbow })
        {
            var item = new Item(type); var other = new Item(ItemID.Boomstick); var owner = new Player();
            var expected = JsonNode.Parse(client.Prepare(item, other, owner).PayloadJson)!;
            var deferred = client.PrepareDeferred(item, other, owner);
            item.damage += 99; owner.inventory = null!;
            PumpParentAnalysis(Task.Run(deferred.CompleteAnalysis));
            var actual = JsonNode.Parse(deferred.PayloadJson)!;
            Equal(true, JsonNode.DeepEquals(expected, actual), "replacement profiles have exact synchronous/deferred parity with frozen inputs");
            AssertParentFingerprintNativeFacts(actual["itemA"]!["ammoRaw"], actual["itemA"]!["fingerprint"]!["ammoRaw"],
                "root/fingerprint share every replacement mechanic and condition", requireRootView: true);
            Equal(false, deferred.PayloadJson.Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "replacement profiles cannot leak unresolved source markers");
            if (!string.IsNullOrWhiteSpace(export)) File.WriteAllText(Path.Combine(export, type + ".json"), deferred.PayloadJson);
        }
        var cancelled = client.PrepareDeferred(new Item(ItemID.MoltenFury), new Item(ItemID.Boomstick), new Player());
        cancelled.Cancel();
        Equal(true, Task.Run(() => client.GeneratePreparedBlocking(cancelled)).GetAwaiter().GetResult() is null, "cancelled replacement source capture never reaches transport");
        bool withheld = false;
        try { _ = cancelled.PayloadJson; } catch (InvalidOperationException) { withheld = true; }
        Equal(true, withheld, "cancelled replacement snapshot cannot publish partial facts");
        var recovered = client.PrepareDeferred(new Item(ItemID.MoltenFury), new Item(ItemID.Boomstick), new Player());
        PumpParentAnalysis(Task.Run(recovered.CompleteAnalysis));
        Equal(ProjectileID.FireArrow, JsonNode.Parse(recovered.PayloadJson)!["itemA"]!["ammoRaw"]!["nativeReplacementProjectileRaw"]![0]!["type"]!.GetValue<int>(), "cancelled capture does not poison the next replacement profile");
    }
}
