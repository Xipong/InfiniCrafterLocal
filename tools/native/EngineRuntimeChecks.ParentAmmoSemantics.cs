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
            (4381, "replaced", 819), (3052, "replaced", 495), (2223, "replaced", 357),
            (3019, "conditionally_replaced", 485), (4953, "conditionally_replaced", 932),
            (ItemID.DaedalusStormbow, "retained_with_native_item_delivery", 0) })
        {
            var item = new Item(type);
            using var packet = JsonDocument.Parse(new GeneratorClient().Prepare(item, new Item(ItemID.DirtBlock), owner).PayloadJson);
            var raw = packet.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
            Equal(true, raw.TryGetProperty("projectileSemanticsReference", out var reference), "Prepare publishes source-aware ammo semantics");
            for (int i = 0; i < 2; i++)
            {
                Equal(owner.inventory[54 + i].damage, raw.GetProperty("playerInventoryAmmoRaw")[i].GetProperty("damage").GetInt32(), "every weapon configuration retains observed ammo-item damage independently of projectile conversion");
                Equal(owner.inventory[54 + i].knockBack, raw.GetProperty("playerInventoryAmmoRaw")[i].GetProperty("knockback").GetSingle(), "ammo knockback contribution is not projectile identity");
            }
            Equal(relation, reference.GetProperty("ammoProjectileRelation").GetString(), "native projectile identity relation");
            Equal("unknown_without_gameplay_execution", reference.GetProperty("finalShotOutcome").GetString(), "source proof is not live shot evidence");
            Equal(true, reference.GetProperty("unknowns").GetArrayLength() > 0, "ambient and hooks remain explicit");
            if (relation == "replaced")
            {
                Equal(0, raw.GetProperty("playerInventoryProjectileRaw").GetArrayLength(), "proved replacement does not export input arrow projectile mechanics");
                Equal(0, raw.GetProperty("fallbackProjectileRaw").GetArrayLength(), "representative input arrow profiles are also irrelevant to replaced firing");
                Equal(projectile, raw.GetProperty("nativeReplacementProjectileRaw")[0].GetProperty("type").GetInt32(), "source replacement has its own bounded projectile reference");
            }
            if (relation == "conditionally_replaced")
            {
                var bindings = raw.GetProperty("candidateProjectileBindings").EnumerateArray().Where(x => x.GetProperty("candidateSource").GetString()!.Contains("player_inventory")).ToArray();
                Equal(projectile, bindings[0].GetProperty("sourceRuleOutputProjectileId").GetInt32(), "wooden input maps to native replacement");
                bool hasStateCondition = reference.GetProperty("stages").EnumerateArray()
                    .SelectMany(stage => stage.GetProperty("rules").EnumerateArray())
                    .Any(rule => rule.TryGetProperty("whenSourceCondition", out _));
                if (hasStateCondition)
                {
                    Equal(JsonValueKind.Null, bindings[1].GetProperty("sourceRuleOutputProjectileId").ValueKind,
                        "inventory identity cannot decide a source player-state condition");
                    Equal(true, bindings[1].GetProperty("includeInputProjectileProfile").GetBoolean(),
                        "unresolved alternative preserves the original candidate mechanics");
                    Equal(true, raw.GetProperty("nativeReplacementProjectileRaw").EnumerateArray().Any(profile =>
                        profile.GetProperty("sourceReferences").EnumerateArray().Any(source =>
                            source.GetProperty("sourceFact").TryGetProperty("whenSourceCondition", out _))),
                        "state-conditioned alternative retains its own profile and exact source predicate");
                }
                else
                    Equal(ProjectileID.FireArrow, bindings[1].GetProperty("sourceRuleOutputProjectileId").GetInt32(), "special ammo bypasses conditional rewrite");
                Equal(1, raw.GetProperty("playerInventoryProjectileRaw").GetArrayLength(), "only retained special input keeps its projectile profile");
                Equal(ProjectileID.FireArrow, raw.GetProperty("playerInventoryProjectileRaw")[0].GetProperty("type").GetInt32(), "retained special profile is not discarded");
            }
            if (projectile > 0)
            {
                var rule = reference.GetProperty("stages").EnumerateArray().SelectMany(s => s.GetProperty("rules").EnumerateArray()).First();
                Equal(projectile, rule.GetProperty("outputProjectileId").GetInt32(), "literal source output, not inventory arrow");
                var oracle = new Player(); oracle.inventory[54] = new Item(ItemID.WoodenArrow, 4);
                Equal(true, oracle.PickAmmo(item, out int picked, out _, out _, out _, out _, dontConsume: true), "actual native PickAmmo source oracle");
                var pickRules = reference.GetProperty("stages")[0].GetProperty("rules").EnumerateArray().ToArray();
                Equal(pickRules.Length > 0 ? pickRules[0].GetProperty("outputProjectileId").GetInt32() : ProjectileID.WoodenArrowFriendly,
                    picked, "actual native PickAmmo agrees with its own stage, before later ItemCheck rewrites");
                if (relation == "conditionally_replaced")
                {
                    oracle.inventory[54] = new Item(ItemID.FlamingArrow, 4);
                    Equal(true, oracle.PickAmmo(item, out int special, out _, out _, out _, out _, dontConsume: true), "special ammo native oracle");
                    Equal(ProjectileID.FireArrow, special, "special ammo is retained by conditional replacement");
                    Equal(ProjectileID.WoodenArrowFriendly, rule.GetProperty("whenInputProjectileId").GetInt32(), "condition is not discarded");
                }
            }
        }
        AssertSpawnArgumentSourcesReachPrepare();
        AssertAmmoSourceAgainstNativeShotRequests();
        AssertRocketTableSelection();
        Equal(23, owner.inventory[54].stack, "capture never selects/consumes ammo");
        string? export = Environment.GetEnvironmentVariable("INFINI_PARENT_AMMO_PACKET");
        if (!string.IsNullOrWhiteSpace(export))
        {
            System.IO.File.WriteAllText(export, new GeneratorClient().Prepare(new Item(2223), new Item(ItemID.DaedalusStormbow), owner).PayloadJson);
            System.IO.File.WriteAllText(export + ".hellwing.json", new GeneratorClient().Prepare(new Item(3019), new Item(4381), owner).PayloadJson);
        }
    }

    private static void AssertSpawnArgumentSourcesReachPrepare()
    {
        var owner = new Player();
        owner.inventory[0] = new Item(ItemID.WoodenArrow, 17);
        owner.inventory[54] = new Item(ItemID.FlamingArrow, 9);
        owner.inventory[55] = new Item(ItemID.HolyArrow, 5);
        foreach (var (name, type) in new[] { ("eventide", 4953), ("terra", ItemID.TerraBlade), ("daedalus", ItemID.DaedalusStormbow) })
        {
            string json = new GeneratorClient().Prepare(new Item(type), new Item(ItemID.DirtBlock), owner).PayloadJson;
            using var packet = JsonDocument.Parse(json);
            var parent = packet.RootElement.GetProperty("itemA");
            var raw = parent.GetProperty("ammoRaw");
            var reference = raw.GetProperty("projectileSemanticsReference");
            var stage = reference.GetProperty("stages")[1];
            Equal(true, stage.TryGetProperty("sourceVerification", out _), "spawn source requires exact native certificate");
            var sites = stage.GetProperty("spawnSites").EnumerateArray().ToArray();
            Equal(true, sites.Length > 0, "actual source contains native item spawn sites");
            foreach (var site in sites)
            {
                Equal(true, site.TryGetProperty("spawnInputs", out var inputs), "certified argument expressions survive native Prepare");
                Equal(true, inputs.TryGetProperty("owner", out var own), "owner argument remains an explicit source input");
                Equal("argument", own.GetProperty("kind").GetString(), "native owner argument is not player state evaluation");
                Equal(1, own.GetProperty("index").GetInt32(), "native owner keeps ItemCheck argument identity");
                Equal(true, site.GetProperty("spawnInputCoverage").GetProperty("fields").TryGetProperty("damage", out _), "damage extraction coverage is explicit");
                Equal(true, site.TryGetProperty("whenSourceCondition", out _), "native call reachability stays attached");
            }
            Equal("unknown_without_gameplay_execution", reference.GetProperty("finalShotOutcome").GetString(), "argument source is not a final shot");
            Equal(CanonicalParentFactJson(reference), CanonicalParentFactJson(parent.GetProperty("fingerprint").GetProperty("ammoRaw").GetProperty("projectileSemanticsReference")), "player-free fingerprint preserves the same unevaluated source");
            if (type == 4953)
            {
                var source = sites.Single(site => site.GetProperty("sourceSpawnIlOffset").GetInt32() == 10958);
                var damage = SpawnSourceNodes(source.GetProperty("spawnInputs").GetProperty("damage")).ToArray();
                Equal(true, damage.Any(node => node.TryGetProperty("operator", out var op) && op.GetString() == "mul"
                    && node.GetProperty("right").TryGetProperty("value", out var value) && value.GetDouble() == 2), "conditional current-damage multiplication is retained");
                Equal(true, damage.Any(node => node.TryGetProperty("sourceBranchIlOffset", out var offset) && offset.GetInt32() == 10866), "damage state predicate is retained");
                Equal(true, damage.Any(node => node.TryGetProperty("reason", out var reason) && reason.GetString() == "branch_entry_value_unknown"), "hook-modified branch-entry damage is never item base damage");
                Equal(true, SpawnSourceNodes(source.GetProperty("spawnInputs").GetProperty("velocity")).Any(node =>
                    node.TryGetProperty("sourceStoreIlOffset", out var offset) && offset.GetInt32() == 10932), "source velocity reassignment survives");
                Equal(true, SpawnSourceNodes(source.GetProperty("spawnInputs").GetProperty("ai1")).Any(node =>
                    node.TryGetProperty("operator", out var op) && op.GetString() == "rem"), "source AI remainder expression survives");
                Equal(true, SpawnSourceNodes(source.GetProperty("whenSourceCondition")).Any(node =>
                    node.TryGetProperty("sourceBranchIlOffset", out var offset) && offset.GetInt32() == 10886), "projectile-state spawn condition survives");
            }
            if (type != ItemID.TerraBlade)
            {
                Equal("0,54,55", string.Join(",", raw.GetProperty("playerInventoryAmmoRaw").EnumerateArray().Select(row => row.GetProperty("inventorySlot").GetInt32())), "main/ammo inventory candidate multiplicity and order remain unchanged");
                Equal(true, raw.GetProperty("fallbackAmmoRaw").EnumerateArray().All(row => row.GetProperty("inventorySlot").GetInt32() == -1), "fallback source stays separate from observed inventory");
                var fingerprint = parent.GetProperty("fingerprint").GetProperty("ammoRaw");
                Equal("no_player", fingerprint.GetProperty("playerInventoryObservation").GetProperty("reason").GetString(), "fingerprint cannot borrow a live player's inventory");
                Equal(JsonValueKind.Null, fingerprint.GetProperty("playerInventoryAmmoRaw").ValueKind, "no-player is not observed-empty inventory");
            }
            string? export = Environment.GetEnvironmentVariable("INFINI_PARENT_SPAWN_PACKET_DIR");
            if (!string.IsNullOrWhiteSpace(export))
            {
                System.IO.Directory.CreateDirectory(export);
                System.IO.File.WriteAllText(System.IO.Path.Combine(export, name + ".packet.json"), json);
            }
        }
        Equal(17, owner.inventory[0].stack, "source capture never consumes main inventory ammo");
        Equal(9, owner.inventory[54].stack, "source capture never consumes ammo-slot stack");
    }

    private static System.Collections.Generic.IEnumerable<JsonElement> SpawnSourceNodes(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            yield return value;
            foreach (var property in value.EnumerateObject())
                foreach (var node in SpawnSourceNodes(property.Value)) yield return node;
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var child in value.EnumerateArray())
                foreach (var node in SpawnSourceNodes(child)) yield return node;
    }

    private static void AssertRocketTableSelection()
    {
        var owner = new Player();
        foreach (int weaponType in new[] { 1946, 3930 })
            foreach (int ammoType in new[] { 771, 772, 773, 774 })
            {
                var weapon = new Item(weaponType);
                owner.inventory[54] = new Item(ammoType, 20);
                Equal(true, owner.PickAmmo(weapon, out int actual, out _, out _, out _, out _, dontConsume: true), "native rocket selection oracle");
                using var packet = JsonDocument.Parse(new GeneratorClient().Prepare(weapon, new Item(ItemID.DirtBlock), owner).PayloadJson);
                var raw = packet.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
                var binding = raw.GetProperty("candidateProjectileBindings").EnumerateArray().First(x => x.GetProperty("inventorySlot").GetInt32() == 54);
                Equal(actual, binding.GetProperty("sourceRuleOutputProjectileId").GetInt32(), "specific rocket table precedes generic offset");
                Equal(actual, raw.GetProperty("nativeReplacementProjectileRaw")[0].GetProperty("type").GetInt32(), "exported rocket projectile profile agrees with native selection");
            }
        // A live table may be changed by mods. Capture its current entry, then
        // follow only the next arm of the completely certified native chain.
        var table = AmmoID.Sets.SpecificLauncherAmmoProjectileMatches[1946];
        int original = table[772];
        try
        {
            var weapon = new Item(1946); owner.inventory[54] = new Item(772, 20);
            table[772] = ProjectileID.Bee;
            using (var packet = JsonDocument.Parse(new GeneratorClient().Prepare(weapon, new Item(ItemID.DirtBlock), owner).PayloadJson))
            {
                var raw = packet.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
                var binding = raw.GetProperty("candidateProjectileBindings").EnumerateArray().First(x => x.GetProperty("inventorySlot").GetInt32() == 54);
                Equal(ProjectileID.Bee, binding.GetProperty("sourceRuleOutputProjectileId").GetInt32(), "capture observes current table entry");
            }
            table.Remove(772);
            using (var packet = JsonDocument.Parse(new GeneratorClient().Prepare(weapon, new Item(ItemID.DirtBlock), owner).PayloadJson))
            {
                var raw = packet.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
                var binding = raw.GetProperty("candidateProjectileBindings").EnumerateArray().First(x => x.GetProperty("inventorySlot").GetInt32() == 54);
                Equal(true, owner.PickAmmo(weapon, out int actual, out _, out _, out _, out _, dontConsume: true), "native table-miss selection oracle");
                Equal(actual, binding.GetProperty("sourceRuleOutputProjectileId").GetInt32(), "table miss follows certified offset arm");
                Equal(actual, raw.GetProperty("nativeReplacementProjectileRaw")[0].GetProperty("type").GetInt32(), "offset exports native output profile");
            }
        }
        finally { table[772] = original; }
        var flame = new Item(ItemID.Flamethrower); owner.inventory[54] = new Item(ItemID.Gel, 20);
        Equal(0, owner.inventory[54].shoot, "zero ammo.shoot is a valid native input");
        Equal(true, owner.PickAmmo(flame, out int flameType, out _, out _, out _, out _, dontConsume: true), "native zero-shoot ammo oracle");
        using var flamePacket = JsonDocument.Parse(new GeneratorClient().Prepare(flame, new Item(ItemID.DirtBlock), owner).PayloadJson);
        var flameRaw = flamePacket.RootElement.GetProperty("itemA").GetProperty("ammoRaw");
        var flameBinding = flameRaw.GetProperty("candidateProjectileBindings").EnumerateArray().First(x => x.GetProperty("inventorySlot").GetInt32() == 54);
        Equal(flameType, flameBinding.GetProperty("sourceRuleOutputProjectileId").GetInt32(), "non-positive ammo.shoot retains native weapon projectile");
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
            foreach (int type in new[] { ItemID.WoodenBow, 4381, 3052, 2223, 3019, ItemID.DaedalusStormbow })
                foreach (int ammoType in new[] { ItemID.WoodenArrow, ItemID.FlamingArrow })
                {
                    var item = new Item(type); player.inventory[0] = item;
                    var ammo = new Item(ammoType, 20); player.inventory[54] = ammo;
                    requests.Clear(); player.itemAnimation = item.useAnimation; player.itemTime = 0;
                    Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                    Equal(true, player.PickAmmo(item, out int pickType, out _, out int pickDamage, out _, out _, dontConsume: true), "native stage oracle finds ammo");
                    nativeShoot.Invoke(player, new object[] { player.whoAmI, item, player.GetWeaponDamage(item) });
                    Equal(true, requests.Count > 0, "actual native shooting requests exist");
                    var source = AmmoSemantics(item);
                    int expected = pickType;
                    foreach (var stage in source["stages"]!.AsArray().OfType<JsonObject>().Skip(1))
                        foreach (var rule in stage["rules"]!.AsArray().OfType<JsonObject>())
                            if (rule["whenInputProjectileId"] is null || rule["whenInputProjectileId"]!.GetValue<int>() == expected)
                                expected = rule["outputProjectileId"]!.GetValue<int>();
                    Equal(true, requests.All(request => request.Type == expected), "actual native ItemCheck spawn requests agree with exact source-stage predicates");
                    if (type == 2223)
                        Equal(true, requests.All(request => request.Damage == pickDamage), "Pulse conversion retains native ammo damage contribution; identity replacement is not stat suppression");
                    if (type == ItemID.DaedalusStormbow)
                    {
                        Equal(true, requests.Count >= 2 && requests.Count <= 4, "actual native ammo-dependent rain count");
                        Equal(true, requests.All(request => request.Position.Y < player.MountedCenter.Y - 500), "retained arrow uses native aerial origin, not ordinary direct-arrow delivery");
                    }
                }
        });
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
                var binding = ammo.GetProperty("candidateProjectileBindings")[0];
                if (suppress)
                {
                    Equal("suppressed_default_shot", ammo.GetProperty("projectileSemanticsReference").GetProperty("ammoProjectileRelation").GetString(), "summary also respects Global Shoot admission before ModItem");
                    Equal(JsonValueKind.Null, binding.GetProperty("sourceRuleOutputProjectileId").ValueKind, "Global Shoot false skips ModItem Shoot and default spawn");
                    var blockedProfile = ammo.GetProperty("nativeReplacementProjectileRaw").EnumerateArray()
                        .Single(profile => profile.GetProperty("type").GetInt32() == ProjectileID.Bee);
                    Equal(true, blockedProfile.GetProperty("sourceReferences").EnumerateArray().Any(source =>
                        source.GetProperty("dispatchStatus").GetString() == "blocked_by_inspected_global_shoot_suppression"),
                        "skipped ModItem source remains evidence with explicit blocked dispatch, not a candidate outcome");
                    Equal(false, binding.GetProperty("includeReplacementProjectileProfile").GetBoolean(),
                        "suppressed candidate does not claim an executed replacement");
                }
                else
                {
                    Equal(ProjectileID.Bee, binding.GetProperty("sourceRuleOutputProjectileId").GetInt32(), "ModItem fixed Shoot follows all ModifyShootStats, not owner-group array order");
                    Equal(ProjectileID.Bee, ammo.GetProperty("nativeReplacementProjectileRaw")[0].GetProperty("type").GetInt32(), "actual Prepare supplies the explicit ModItem spawn, not prior Global type ref");
                }
                Equal(owner.inventory[54].damage, ammo.GetProperty("playerInventoryAmmoRaw")[0].GetProperty("damage").GetInt32(), "mixed hook projection keeps ammo damage");
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
