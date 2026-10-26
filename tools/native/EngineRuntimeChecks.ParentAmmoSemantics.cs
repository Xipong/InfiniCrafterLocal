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
        AssertAmmoSourceAgainstNativeShotRequests();
        Equal(23, owner.inventory[54].stack, "capture never selects/consumes ammo");
        string? export = Environment.GetEnvironmentVariable("INFINI_PARENT_AMMO_PACKET");
        if (!string.IsNullOrWhiteSpace(export))
        {
            System.IO.File.WriteAllText(export, new GeneratorClient().Prepare(new Item(2223), new Item(ItemID.DaedalusStormbow), owner).PayloadJson);
            System.IO.File.WriteAllText(export + ".hellwing.json", new GeneratorClient().Prepare(new Item(3019), new Item(4381), owner).PayloadJson);
        }
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
                    Equal(0, ammo.GetProperty("nativeReplacementProjectileRaw").GetArrayLength(), "skipped ModItem spawn cannot supply a replacement profile");
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
