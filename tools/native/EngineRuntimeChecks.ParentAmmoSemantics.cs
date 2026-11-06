using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static JsonObject AmmoSemantics(Item item)
    {
        var capture = typeof(GeneratorClient).GetMethod("CaptureAmmoProjectileSemantics", BindingFlags.Static | BindingFlags.NonPublic);
        Equal(true, capture is not null, "native ammo source capture exists");
        return (JsonObject)capture!.Invoke(null, new object[] { item })!;
    }

    private static void ParentConditionalShotAlternativesRemainSourceOnly()
    {
        using var state = new NativeActorState();
        var item = new Item(ItemID.NebulaBlaze);
        var semantics = AmmoSemantics(item);
        var variants = semantics["stages"]!.AsArray().OfType<JsonObject>()
            .SelectMany(stage => (stage["conditionalArithmeticVariants"] as JsonArray ?? new JsonArray()).OfType<JsonObject>()).ToArray();
        Equal(2, variants.Length, "both source arithmetic arms retained");
        Equal(20, variants[0]["conditionalProbability"]!["numerator"]!.GetValue<int>(), "source numerator");
        Equal(100, variants[0]["conditionalProbability"]!["denominator"]!.GetValue<int>(), "source denominator");
        Equal(1, variants[0]["projectileOffset"]!.GetValue<int>(), "source projectile arithmetic");
        var speedOrigin = variants[1]["localUpdates"]![0]!["initializationProvenance"]!;
        Equal("Terraria.Item.shootSpeed", speedOrigin["source"]!["field"]!.GetValue<string>(), "speed local has source initializer provenance");
        Equal(true, speedOrigin["interveningWriteOrAddressOffsets"]!.AsArray().Count > 0, "speed initializer is not treated as current speed");
        Equal("unknown_without_gameplay_execution", semantics["finalShotOutcome"]!.GetValue<string>(), "arithmetic is not gameplay execution");
        var capture = typeof(GeneratorClient).GetMethod("CaptureSourceReplacementProjectileProfiles", BindingFlags.Static | BindingFlags.NonPublic)!;
        var profiles = (JsonArray)capture.Invoke(null, new object[] { item, semantics })!;
        Equal(true, profiles.OfType<JsonObject>().Any(p => p["type"]!.GetValue<int>() == ProjectileID.NebulaBlaze2), "conditional alternate profile is present");
        string evidence = profiles.ToJsonString();
        Equal(true, evidence.Contains("conditional_on_source_item_field_snapshots_and_branch"), "input assumptions remain attached");
        Equal(true, evidence.Contains("ModifyShootStats_and_Shoot_may_change_or_suppress"), "later hooks remain uncertain");
        var rawCapture = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        string transported = JsonSerializer.Serialize(rawCapture.Invoke(null, new object?[] { item, null }));
        Equal(true, transported.Contains("weapon_without_ammo_source_alternatives"), "non-ammo source capture gate retains alternatives");
        Equal(true, transported.Contains("conditionalArithmeticVariants"), "source arithmetic survives capture transport");
        item.useAmmo = 1;
        Equal(0, ((JsonArray)capture.Invoke(null, new object[] { item, semantics })!).Count, "unknown ammo input cannot produce projected alternatives");
        item.useAmmo = 0; item.shoot = int.MaxValue;
        Equal(0, ((JsonArray)capture.Invoke(null, new object[] { item, semantics })!).Count, "overflow or unregistered output cannot produce profiles");
    }

    private static void ParentAmmoSourceSemanticsReachPrepare()
    {
        using var state = new NativeActorState();
        var owner = new Player();
        owner.inventory[54] = new Item(ItemID.WoodenArrow, 23);
        owner.inventory[55] = new Item(ItemID.FlamingArrow, 11);
        foreach (var (type, relation, projectile) in new[] {
            (ItemID.WoodenBow, "retained_in_default_ammo_path", 0),
            (ItemID.MoltenFury, "conditionally_replaced", ProjectileID.FireArrow),
            (4381, "replaced", 819), (3052, "replaced", 495), (2223, "replaced", 357),
            (3019, "conditionally_replaced", 485), (4953, "conditionally_replaced", 932),
            (ItemID.DaedalusStormbow, "retained_with_native_item_delivery", 0) })
        {
            var item = new Item(type);
            using var packet = JsonDocument.Parse(new GeneratorClient().Prepare(item, new Item(ItemID.DirtBlock), owner).PayloadJson);
            var raw = packet.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
            Equal(true, raw.TryGetProperty("projectileSemanticsReference", out var reference), "Prepare publishes source-aware ammo semantics");
            AssertWeaponAmmoHasNoCandidates(raw);
            Equal(item.useAmmo, raw.GetProperty("ammoId").GetInt32(), "weapon ammo category remains explicit");
            Equal(relation, reference.GetProperty("ammoProjectileRelation").GetString(), "native projectile identity relation");
            Equal("unknown_without_gameplay_execution", reference.GetProperty("finalShotOutcome").GetString(), "source proof is not live shot evidence");
            Equal(true, reference.GetProperty("unknowns").GetArrayLength() > 0, "ambient and hooks remain explicit");
            if (projectile > 0)
            {
                var rule = reference.GetProperty("stages").EnumerateArray().SelectMany(s => s.GetProperty("rules").EnumerateArray()).First();
                Equal(projectile, rule.GetProperty("outputProjectileId").GetInt32(), "literal source output, not inventory arrow");
                var oracle = new Player(); oracle.inventory[54] = new Item(ItemID.WoodenArrow, 4);
                Equal(true, oracle.PickAmmo(item, out int picked, out _, out _, out _, out _, dontConsume: true), "actual native PickAmmo source oracle");
                var pickRules = reference.GetProperty("stages")[0].GetProperty("rules").EnumerateArray().ToArray();
                Equal(pickRules.Length > 0 ? pickRules[0].GetProperty("outputProjectileId").GetInt32() : ProjectileID.WoodenArrowFriendly,
                    picked, "actual native PickAmmo agrees with its own stage, before later ItemCheck rewrites");
                if (rule.TryGetProperty("whenInputProjectileId", out var inputCondition))
                {
                    oracle.inventory[54] = new Item(ItemID.FlamingArrow, 4);
                    Equal(true, oracle.PickAmmo(item, out int special, out _, out _, out _, out _, dontConsume: true), "special ammo native oracle");
                    Equal(ProjectileID.FireArrow, special, "special ammo is retained by conditional replacement");
                    Equal(ProjectileID.WoodenArrowFriendly, inputCondition.GetInt32(), "condition is not discarded even when another stage is unknown");
                }
            }
        }
        AssertAmmoSourceAgainstNativeShotRequests();
        AssertRocketTableSelection();
        Equal(23, owner.inventory[54].stack, "capture never selects/consumes ammo");
        string? export = Environment.GetEnvironmentVariable("INFINI_PARENT_AMMO_PACKET");
        if (!string.IsNullOrWhiteSpace(export))
        {
            System.IO.File.WriteAllText(export, new GeneratorClient().Prepare(new Item(2223), new Item(ItemID.DaedalusStormbow), owner).PayloadJson);
            System.IO.File.WriteAllText(export + ".state-conditional.json", new GeneratorClient().Prepare(new Item(4953), new Item(ItemID.DirtBlock), owner).PayloadJson);
            System.IO.File.WriteAllText(export + ".molten.json", new GeneratorClient().Prepare(new Item(ItemID.MoltenFury), new Item(ItemID.WoodenArrow), owner).PayloadJson);
            System.IO.File.WriteAllText(export + ".hellwing.json", new GeneratorClient().Prepare(new Item(3019), new Item(4381), owner).PayloadJson);
        }
    }

    private static void AssertRocketTableSelection()
    {
        var owner = new Player();
        foreach (int weaponType in new[] { 1946, 3930 })
        {
            var weapon = new Item(weaponType);
            using var packet = JsonDocument.Parse(new GeneratorClient().Prepare(weapon, new Item(ItemID.DirtBlock), owner).PayloadJson);
            var raw = packet.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
            AssertWeaponAmmoHasNoCandidates(raw);
            var reference = raw.GetProperty("projectileSemanticsReference");
            var selection = reference.GetProperty("stages")[0].GetProperty("defaultProjectileSelection");
            Equal(true, selection.GetProperty("specificMatchLookupFirst").GetBoolean(), "certified symbolic chain keeps table-first precedence");
            Equal(true, selection.GetProperty("categoryOffsetSelectors").GetArrayLength() > 0, "conditional category offsets stay explicit");
            Equal("unknown_without_gameplay_execution", reference.GetProperty("finalShotOutcome").GetString(), "unselected rocket output is not asserted");
            Equal(true, reference.GetProperty("unknowns").EnumerateArray().Any(value => value.GetString()!.Contains("table entries are not resolved")), "unresolved live table entries are disclosed");
        }
        // Changing a live ammo mapping does not manufacture a selected loadout.
        var table = AmmoID.Sets.SpecificLauncherAmmoProjectileMatches[1946];
        int original = table[772];
        try
        {
            var weapon = new Item(1946); owner.inventory[54] = new Item(772, 20);
            string before = AmmoSemantics(weapon).ToJsonString();
            table[772] = ProjectileID.Bee;
            Equal(before, AmmoSemantics(weapon).ToJsonString(), "source-only conversion facts do not choose a live mapping entry");
            Equal(true, owner.PickAmmo(weapon, out int actual, out _, out _, out _, out _, dontConsume: true), "native oracle still selects concrete ammo during actual gameplay");
            Equal(ProjectileID.Bee, actual, "actual native selection differs while source context remains symbolic");
        }
        finally { table[772] = original; }
        var flame = new Item(ItemID.Flamethrower); owner.inventory[54] = new Item(ItemID.Gel, 20);
        Equal(0, owner.inventory[54].shoot, "zero ammo.shoot is a valid native input");
        using var flamePacket = JsonDocument.Parse(new GeneratorClient().Prepare(flame, new Item(ItemID.DirtBlock), owner).PayloadJson);
        var flameRaw = flamePacket.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
        AssertWeaponAmmoHasNoCandidates(flameRaw);
        Equal(flame.shoot, flameRaw.GetProperty("weaponShootFieldProjectileRaw").GetProperty("type").GetInt32(), "weapon own projectile survives without a concrete gel example");
    }

    private static void AssertAmmoSourceAgainstNativeShotRequests()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, craftPlayer) => {
            PrepareMobilityConsumptionPlayer(player);
            var nativeShoot = typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!;
            var vectorSpawn = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
                typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!;
            var scalarSpawn = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
                typeof(IEntitySource), typeof(float), typeof(float), typeof(float), typeof(float), typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!;
            var requests = new System.Collections.Generic.List<(int Type, Vector2 Position, int Damage)>();
            using var hook = new MonoMod.RuntimeDetour.Hook(vectorSpawn,
                (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, int>)
                ((s, pos, vel, type, damage, knock, owner, a, b, c) => { requests.Add((type, pos, damage)); return 0; }));
            using var scalarHook = new MonoMod.RuntimeDetour.Hook(scalarSpawn,
                (Func<IEntitySource, float, float, float, float, int, int, float, int, float, float, float, int>)
                ((s, x, y, vx, vy, type, damage, knock, owner, a, b, c) => { requests.Add((type, new Vector2(x, y), damage)); return 0; }));
            var mismatches = new System.Collections.Generic.List<string>();
            int cases = 0, moltenSpecialRetentionCases = 0;
            foreach (int type in new[] { ItemID.WoodenBow, ItemID.MoltenFury, 4381, 3052, 2223, 3019, ItemID.DaedalusStormbow })
                foreach (int ammoType in new[] { ItemID.WoodenArrow, ItemID.FlamingArrow, ItemID.JestersArrow, ItemID.HolyArrow })
                {
                    var item = new Item(type); player.inventory[0] = item;
                    var ammo = new Item(ammoType, 20); player.inventory[54] = ammo;
                    requests.Clear(); player.itemAnimation = item.useAnimation; player.itemTime = 0;
                    Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                    Equal(true, player.PickAmmo(item, out int pickType, out _, out int pickDamage, out _, out _, dontConsume: true), $"native stage oracle finds ammo (weapon={type}, ammo={ammoType})");
                    nativeShoot.Invoke(player, new object[] { player.whoAmI, item, player.GetWeaponDamage(item) });
                    Equal(true, requests.Count > 0, $"actual native shooting requests exist (weapon={type}, ammo={ammoType})");
                    if (type == ItemID.MoltenFury && ammoType is ItemID.JestersArrow or ItemID.HolyArrow)
                    {
                        Equal(ammo.shoot, pickType, $"Molten Fury retains special ammo in actual PickAmmo (ammo={ammoType})");
                        Equal(true, requests.All(request => request.Type == ammo.shoot),
                            $"Molten Fury retains special ammo in actual ItemCheck_Shoot (ammo={ammoType})");
                        moltenSpecialRetentionCases++;
                    }
                    var source = AmmoSemantics(item);
                    int expected = pickType;
                    foreach (var stage in source["stages"]!.AsArray().OfType<JsonObject>().Skip(1))
                        foreach (var rule in stage["rules"]!.AsArray().OfType<JsonObject>())
                            if (rule["whenInputProjectileId"] is null || rule["whenInputProjectileId"]!.GetValue<int>() == expected)
                                expected = rule["outputProjectileId"]!.GetValue<int>();
                    Console.WriteLine($"AMMO ORACLE weapon={type} ammo={ammoType} pick={pickType} source={expected} actual=[{string.Join(",", requests.Select(request => request.Type))}]");
                    cases++;
                    if (requests.Any(request => request.Type != expected))
                        mismatches.Add($"weapon={type}, ammo={ammoType}, source={expected}, actual=[{string.Join(",", requests.Select(request => request.Type))}]");
                    if (type == 2223)
                        Equal(true, requests.All(request => request.Damage == pickDamage), "Pulse conversion retains native ammo damage contribution; identity replacement is not stat suppression");
                    if (type == ItemID.DaedalusStormbow)
                    {
                        Equal(true, requests.Count >= 2 && requests.Count <= 4, "actual native ammo-dependent rain count");
                        Equal(true, requests.All(request => request.Position.Y < player.MountedCenter.Y - 500), "retained arrow uses native aerial origin, not ordinary direct-arrow delivery");
                    }
                }
            Equal(28, cases, "native shot matrix covers seven weapons with four ammo inputs each");
            Equal(2, moltenSpecialRetentionCases, "Molten Fury Jester and Holy negative conversion cases both execute");
            Equal(0, mismatches.Count, "actual native ItemCheck spawn requests agree with exact source-stage predicates: " + string.Join("; ", mismatches));
            Console.WriteLine($"AMMO ORACLE PASS cases={cases} moltenSpecialRetained={moltenSpecialRetentionCases}");
            int stateCases = 0;
            foreach (int elapsed in new[] { 0, 2, 4, 5, 6, 8 })
                foreach (int ammoType in new[] { ItemID.WoodenArrow, ItemID.FlamingArrow, ItemID.JestersArrow, ItemID.HolyArrow })
                {
                    var item = new Item(4953); player.inventory[0] = item;
                    var ammo = new Item(ammoType, 20); player.inventory[54] = ammo;
                    player.itemAnimationMax = item.useAnimation;
                    player.itemAnimation = item.useAnimation - elapsed; player.itemTime = 0;
                    var source = AmmoSemantics(item);
                    var stage = source["stages"]!.AsArray().OfType<JsonObject>().Single(s => s["method"]!.GetValue<string>() == "Player.ItemCheck_Shoot");
                    var rule = stage["rules"]!.AsArray().OfType<JsonObject>().Single();
                    Equal(0, stage["unrecognizedProjectileWriteOffsets"]!.AsArray().Count, "state-conditioned source write is proved");
                    Equal(true, player.PickAmmo(item, out int picked, out _, out _, out _, out _, dontConsume: true), "state matrix picks actual ammo");
                    var predicate = rule["whenSourceCondition"]!.AsObject();
                    Equal("bne", predicate["opcode"]!.GetValue<string>(), "state condition preserves IL comparison");
                    Equal(false, predicate["taken"]!.GetValue<bool>(), "literal is on equality fallthrough");
                    bool applies = NativeAmmoConditionValue(predicate["left"]!, player) == NativeAmmoConditionValue(predicate["right"]!, player);
                    Equal(elapsed / 2 == 2, applies, "source snapshot expression preserves native integer division, including odd elapsed tick");
                    int expected = applies ? rule["outputProjectileId"]!.GetValue<int>() : picked;
                    requests.Clear(); Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                    nativeShoot.Invoke(player, new object[] { player.whoAmI, item, player.GetWeaponDamage(item) });
                    Equal(true, requests.Count > 0, "state-conditioned native shoot reaches an actual spawn request");
                    Equal(true, requests.All(request => request.Type == expected), $"state source agrees with actual native requests: elapsed={elapsed} ammo={ammoType} expected={expected}");
                    Console.WriteLine($"STATE AMMO ORACLE elapsed={elapsed} ammo={ammoType} pick={picked} source={expected} actual=[{string.Join(",", requests.Select(request => request.Type))}]");
                    stateCases++;
                }
            Equal(24, stateCases, "state-conditioned native matrix covers six states and four ammo identities");
        });
    }

    // Test-only evaluation against deliberately fixed player fields. Production
    // only publishes these source snapshots and never executes a condition.
    private static int NativeAmmoConditionValue(JsonNode node, Player player)
    {
        string kind = node["kind"]!.GetValue<string>();
        if (kind == "constant") return node["value"]!.GetValue<int>();
        if (kind == "local_definition") return NativeAmmoConditionValue(node["value"]!, player);
        if (kind == "field")
        {
            string member = node["member"]!.GetValue<string>();
            Equal("argument", node["receiver"]!["kind"]!.GetValue<string>(), "test field has exact argument receiver");
            Equal(0, node["receiver"]!["index"]!.GetValue<int>(), "test field belongs to player receiver");
            return (int)typeof(Player).GetField(member.Substring(member.LastIndexOf('.') + 1))!.GetValue(player)!;
        }
        if (kind == "binary")
        {
            int left = NativeAmmoConditionValue(node["left"]!, player), right = NativeAmmoConditionValue(node["right"]!, player);
            return node["operator"]!.GetValue<string>() switch { "sub" => left - right, "div" => left / right,
                "add" => left + right, "mul" => left * right, _ => throw new InvalidOperationException("unsupported test expression") };
        }
        throw new InvalidOperationException("unsupported test condition value");
    }

    private sealed class ConstantAmmoHook : ModItem
    {
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = ProjectileID.Bee; }
    }
    private sealed class ConditionalAmmoHook : ModItem
    {
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { if (type == ProjectileID.WoodenArrowFriendly) type = ProjectileID.Bee; }
    }
    private sealed class OpaqueAmmoHook : ModItem
    {
        internal static int Calls;
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { Calls++; type = player.statLife; }
    }
    private sealed class OwnProjectileAmmoHook : ModItem
    {
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        {
            Projectile.NewProjectile(source, position, velocity, ProjectileID.Bee, damage, knockback, player.whoAmI);
            return false;
        }
    }
    private sealed class InvalidOwnProjectileAmmoHook : ModItem
    {
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        {
            Projectile.NewProjectile(source, position, velocity, -1, damage, knockback, player.whoAmI);
            return false;
        }
    }
    private sealed class SuppressedAmmoHook : ModItem
    {
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback) => false;
    }
    private sealed class ConstantPickAmmoHook : ModItem
    {
        public override void PickAmmo(Item weapon, Player player, ref int type, ref float speed, ref StatModifier damage, ref float knockback) { type = ProjectileID.Bee; }
    }
    private sealed class ConstantGlobalAmmoHook : GlobalItem
    {
        public override void ModifyShootStats(Item item, Player player, ref Vector2 position, ref Vector2 velocity, ref int shot, ref int damage, ref float knockback) { shot = ProjectileID.Bee; }
    }
    private sealed class MixedGlobalAmmoHook : GlobalItem
    {
        public override void ModifyShootStats(Item item, Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback) { type = ProjectileID.FireArrow; }
    }
    private sealed class MixedGlobalSuppressHook : GlobalItem
    {
        public override bool Shoot(Item item, Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback) => false;
    }
    private static void ParentAmmoMixedHooksKeepNativePhaseOrder()
    {
        using var state = new NativeActorState();
        var lookup = typeof(Terraria.ModLoader.Core.GlobalTypeLookups<GlobalItem>)
            .GetField("_globalsForType", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? oldLookup = lookup.GetValue(null);
        try
        {
            var globals = new GlobalItem[ItemLoader.ItemCount][];
            for (int i = 0; i < globals.Length; i++) globals[i] = Array.Empty<GlobalItem>();
            var modifier = new MixedGlobalAmmoHook();
            var suppressor = new MixedGlobalSuppressHook();
            var perEntity = typeof(GlobalType<GlobalItem>).GetProperty("PerEntityIndex", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!;
            perEntity.SetValue(modifier, (short)-1);
            perEntity.SetValue(suppressor, (short)-1);
            lookup.SetValue(null, globals);
            foreach (bool suppress in new[] { false, true })
            {
                var weapon = new Item(ItemID.WoodenBow);
                var host = new OwnProjectileAmmoHook();
                typeof(ModType).GetProperty("Mod", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, new TooltipProbeMod());
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, weapon);
                typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(weapon, host);
                typeof(Item).GetField("_globals", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(weapon, Array.Empty<GlobalItem>());
                globals[weapon.type] = suppress ? new GlobalItem[] { modifier, suppressor } : new GlobalItem[] { modifier };
                var owner = new Player(); owner.inventory[54] = new Item(ItemID.WoodenArrow, 17);
                // A manually attached ModItem on a vanilla type is not registered
                // content: Prepare's legitimate default reconstruction would remove
                // it. Exercise the exact production ammo capture owner directly.
                var capture = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.Static | BindingFlags.NonPublic)!;
                var ammo = JsonSerializer.SerializeToElement(capture.Invoke(null, new object[] { weapon, owner }));
                AssertWeaponAmmoHasNoCandidates(ammo);
                ExportWeaponSourceHookFixture(suppress ? "GlobalSuppressedOwnSpawn" : "GlobalAndOwnSpawn", JsonNode.Parse(ammo.GetRawText())!.AsObject());
                var semantics = ammo.GetProperty("projectileSemanticsReference");
                Equal(suppress ? "suppressed_default_shot" : "ignored_replaced_by_hook_projectiles",
                    semantics.GetProperty("ammoProjectileRelation").GetString(), "source summary respects Global Shoot admission before ModItem");
                var hooks = semantics.GetProperty("hooks").EnumerateArray().ToArray();
                Equal(true, hooks.Any(h => h.GetProperty("shape").GetString() == "literal_projectile_replacement"), "Global ModifyShootStats literal is retained as source evidence");
                Equal(true, hooks.Any(h => h.GetProperty("shape").GetString() == "fixed_projectile_spawn_suppresses_default" && h.GetProperty("projectileId").GetInt32() == ProjectileID.Bee), "ModItem own spawn is retained without selecting an outgoing shot");
                Equal(true, semantics.GetProperty("stages")[0].GetProperty("hookDispatchTrace").GetArrayLength() > 0, "certified hook dispatch remains explicit");
                Equal("unknown_without_gameplay_execution", semantics.GetProperty("finalShotOutcome").GetString(), "mixed source hooks do not assert selected final projectile");
                var profiles = ammo.GetProperty("nativeReplacementProjectileRaw").EnumerateArray().ToArray();
                Equal(true, profiles.Any(p => p.GetProperty("type").GetInt32() == ProjectileID.FireArrow), "Global literal has an independent full profile");
                var ownProfile = profiles.Single(p => p.GetProperty("type").GetInt32() == ProjectileID.Bee);
                Equal(suppress ? "blocked_by_inspected_global_shoot_suppression" : "certified_dispatch_order_gameplay_admission_unknown",
                    ownProfile.GetProperty("sourceReferences")[0].GetProperty("dispatchStatus").GetString(),
                    "known own-spawn identity survives with exact dispatch reachability, never a guaranteed shot");
            }
        }
        finally { lookup.SetValue(null, oldLookup); }
    }

    private static void ParentAmmoModHookShapesAreInspectedNotExecuted()
    {
        using var state = new NativeActorState();
        foreach (var (host, relation) in new (ModItem, string)[] {
            (new ConstantAmmoHook(), "replaced_by_inspected_hook"),
            (new ConditionalAmmoHook(), "conditionally_replaced_by_inspected_hook"),
            (new OwnProjectileAmmoHook(), "ignored_replaced_by_hook_projectiles"),
            (new InvalidOwnProjectileAmmoHook(), "unknown_hook_projectile_semantics"),
            (new SuppressedAmmoHook(), "suppressed_default_shot"),
            (new OpaqueAmmoHook(), "unknown_hook_projectile_semantics") })
        {
            var item = new Item(ItemID.WoodenBow);
            typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(item, host);
            var reference = AmmoSemantics(item);
            Equal(relation, reference["ammoProjectileRelation"]!.GetValue<string>(), "bounded mod source shape outcome");
            var hooks = reference["hooks"]!.AsArray().OfType<JsonObject>();
            Equal(true, hooks.Any(h => h["sourceMethodSha256"] is not null && h["sourceModuleVersionId"] is not null), "loaded override provenance travels with source facts");
        }
        Equal(0, OpaqueAmmoHook.Calls, "production inference never executes arbitrary hooks");
        var inspect = typeof(GeneratorClient).GetMethod("InspectAmmoHook", BindingFlags.Static | BindingFlags.NonPublic)!;
        var dynamicModule = System.Reflection.Emit.AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("AmmoBoolSourceProbe"), System.Reflection.Emit.AssemblyBuilderAccess.Run).DefineDynamicModule("source");
        foreach (int literal in new[] { 2, -1 })
        {
            var declaration = typeof(ModItem).GetMethod("Shoot")!;
            var builder = dynamicModule.DefineType("Literal" + (literal < 0 ? "Negative" : "Positive"), TypeAttributes.Public, typeof(ModItem));
            var method = builder.DefineMethod("Shoot", MethodAttributes.Public | MethodAttributes.Virtual, typeof(bool), declaration.GetParameters().Select(p => p.ParameterType).ToArray());
            var il = method.GetILGenerator(); il.Emit(System.Reflection.Emit.OpCodes.Ldc_I4, literal); il.Emit(System.Reflection.Emit.OpCodes.Ret);
            builder.DefineMethodOverride(method, declaration);
            var source = builder.CreateType()!.GetMethod("Shoot")!;
            var fact = (JsonObject)inspect.Invoke(null, new object[] { source })!;
            Equal("opaque", fact["shape"]!.GetValue<string>(), "unsupported CLR bool literal cannot mean suppress-default");
        }
        var globalFact = (JsonObject)inspect.Invoke(null, new object[] { typeof(ConstantGlobalAmmoHook).GetMethod("ModifyShootStats")! })!;
        Equal("literal_projectile_replacement", globalFact["shape"]!.GetValue<string>(), "GlobalItem override is inspectable, with signature slots rather than parameter names");
        var captureAmmo = typeof(GeneratorClient).GetMethod("CaptureAmmoInputHookReference", BindingFlags.Static | BindingFlags.NonPublic);
        Equal(true, captureAmmo is not null, "ammo-owned PickAmmo hook inspection exists");
        var ammo = new Item(ItemID.WoodenArrow);
        var ammoHost = new ConstantPickAmmoHook();
        typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(ammo, ammoHost);
        var ammoFacts = (JsonObject)captureAmmo!.Invoke(null, new object[] { ammo })!;
        Equal("literal_projectile_replacement", ammoFacts["hooks"]![0]!["shape"]!.GetValue<string>(), "PickAmmo belongs to selected ammo, not the weapon");
        var weapon = new Item(ItemID.WoodenBow);
        typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(weapon, ammoHost);
        Equal(0, AmmoSemantics(weapon)["hooks"]!.AsArray().Count, "weapon's own PickAmmo override is not invoked in native firing chain");
    }
}
