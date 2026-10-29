using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.DataStructures;
using Terraria.ModLoader;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using System.Collections.Generic;

internal static partial class EngineRuntimeChecks
{
    private sealed class NativeStatParentProbe : ModItem
    {
        public override void SetDefaults()
        {
            Item.damage = 19;
            Item.DamageType = DamageClass.Melee;
            Item.knockBack = 2f;
            Item.useStyle = ItemUseStyleID.Swing;
            Item.useTime = 6;
            Item.useAnimation = 25;
            Item.scale = 1.375f;
            Item.ArmorPenetration = 13;
            Item.useLimitPerAnimation = 2;
        }
    }

    private static void ParentNativeItemStatsSurviveCaptureAndNormalization()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(31);
        var owner = new Player();
        var packets = new List<JsonElement>();
        void Check(int type, bool prefix = false)
        {
            var baseline = new Item(type);
            var item = new Item(type);
            if (prefix)
            {
                Equal(true, item.Prefix(PrefixID.Legendary), "real mod item receives native prefix");
                Equal(false, baseline.scale == item.scale, "prefix control actually changes native scale");
            }
            float originalScale = item.scale;
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, owner).PayloadJson);
            packets.Add(request.RootElement.Clone());
            foreach (string parent in new[] { "itemA", "itemB" })
            {
                var root = request.RootElement.GetProperty(parent);
                foreach (var facts in new[] { root, root.GetProperty("runtimeFacts"), root.GetProperty("fingerprint") })
                {
                    Equal(baseline.scale, facts.GetProperty("itemScale").GetSingle(), "literal base Item.scale survives every envelope");
                    Equal(baseline.ArmorPenetration, facts.GetProperty("armorPenetration").GetInt32(), "native Item armor penetration is independent of projectile defaults");
                    var limit = facts.GetProperty("useLimitPerAnimation");
                    Equal(baseline.useLimitPerAnimation, limit.ValueKind == JsonValueKind.Null ? (int?)null : limit.GetInt32(), "native nullable use limit is not inferred from animation cadence");
                }
                Equal(prefix, root.GetProperty("prefixIgnored").GetBoolean(), "only native prefix is normalized");
                if (baseline.ModItem is not null)
                    Equal(baseline.ModItem.FullName, root.GetProperty("fullName").GetString()!, "actual loader-registered mod parent identity");
            }
            Equal(originalScale, item.scale, "capture cannot change consumed parent scale");
            Equal(baseline.ArmorPenetration, item.ArmorPenetration, "capture cannot change consumed parent penetration");
        }
        foreach (int type in new[] { ItemID.WoodenSword, ItemID.SpaceGun, ItemID.BookStaff, ItemID.FairyQueenMagicItem, ItemID.FairyQueenRangedItem })
            Check(type);
        WithNativeChestRegisteredItem(type => { Check(type); Check(type, prefix: true); }, new NativeStatParentProbe());
        string? path = Environment.GetEnvironmentVariable("INFINI_PARENT_NATIVE_STATS_PACKET");
        if (!string.IsNullOrEmpty(path)) System.IO.File.WriteAllText(path, JsonSerializer.Serialize(packets));
    }

    private static void ParentQuantifiedFactsKeepSnapshotsAndObservationIdentity()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(31);
        var owner = new Player();
        var band = new Item(ItemID.BandofRegeneration);
        var grass = new Item(ItemID.BladeofGrass);
        using var request = JsonDocument.Parse(new GeneratorClient().Prepare(band, grass, owner).PayloadJson);
        var a = request.RootElement.GetProperty("itemA");
        foreach (var facts in new[] { a, a.GetProperty("runtimeFacts"), a.GetProperty("fingerprint") })
            Equal(2, facts.GetProperty("lifeRegen").GetInt32(), "literal Item.lifeRegen contribution is retained, not a guaranteed healed HP/sec");
        var b = request.RootElement.GetProperty("itemB");
        Equal(20, b.GetProperty("directProjectileRaw").GetProperty("armorPenetration").GetInt32(), "native projectile SetDefaults armor penetration");
        Equal(grass.damage, b.GetProperty("damage").GetInt32(), "snapshot collection cannot rebalance parent");
        var effective = typeof(GeneratorClient).GetMethod("EffectiveProjectileRawFromItem", BindingFlags.NonPublic | BindingFlags.Static)!;
        var ammo = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.NonPublic | BindingFlags.Static)!;
        var noShoot = new Item(ItemID.FlareGun) { shoot = 0 };
        foreach (int ammoType in new[] { ItemID.Flare, ItemID.BlueFlare })
        {
            owner.inventory[54] = new Item(ammoType, 99);
            Equal(null, effective.Invoke(null, new object?[] { noShoot, owner }), "inventory cannot manufacture missing weapon shoot identity");
            var observations = JsonSerializer.SerializeToElement(ammo.Invoke(null, new object?[] { noShoot, owner }));
            Equal(ammoType, observations.GetProperty("playerInventoryAmmoRaw")[0].GetProperty("type").GetInt32(), "actual inventory remains a separately scoped observation");
        }
        var gun = new Item(ItemID.FlareGun);
        var own = JsonSerializer.SerializeToElement(effective.Invoke(null, new object?[] { gun, owner }));
        Equal(gun.shoot, own.GetProperty("type").GetInt32(), "own shoot remains separate from selected inventory");
    }

    private static void ParentRandomStatusFactsMatchExclusiveNativeOutcomes()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(41);
        Terraria.Main.player[0] = new Player();
        foreach (var (type, buff, denominator) in new[] {
            (ProjectileID.BladeOfGrass, BuffID.Poisoned, 4), (ProjectileID.Flare, BuffID.OnFire, 3),
        })
        {
            var projectile = new Projectile();
            projectile.SetDefaults(type); projectile.owner = 0;
            var reference = JsonSerializer.SerializeToElement(GeneratorClient.CaptureNativeHitStatusReference(projectile));
            Equal(0, reference.GetProperty("effects").GetArrayLength(), "random facts do not become unconditional effects");
            var choice = reference.GetProperty("randomOutcomes")[0];
            var alternatives = choice.GetProperty("alternatives").EnumerateArray().ToArray();
            Equal(denominator, choice.GetProperty("randomMaximumExclusive").GetInt32(), "exact exclusive random bound");
            Equal(denominator, alternatives.Sum(a => a.GetProperty("probabilityNumerator").GetInt32()), "exclusive alternatives exhaust one RNG draw");
            Equal(true, alternatives.All(a => a.GetProperty("probabilityDenominator").GetInt32() == denominator), "exact probability denominator");
            int[] permittedTicks = alternatives.Select(a => a.GetProperty("effects").GetArrayLength() == 0
                ? 0 : a.GetProperty("effects")[0].GetProperty("durationTicksMin").GetInt32()).ToArray();
            Equal(type == ProjectileID.BladeOfGrass ? "0,420" : "300,600",
                string.Join(",", permittedTicks.OrderBy(x => x)), "conditional absence and discrete durations are not flattened");
            foreach (var alternative in alternatives)
                foreach (var effect in alternative.GetProperty("effects").EnumerateArray())
                    Equal(buff, effect.GetProperty("buffId").GetInt32(), "certified exact native buff ID");
            // Same RNG seed with an independent RNG oracle predicts each actual
            // branch, not a statistical frequency assertion or mocked hit method.
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(101);
            var oracle = new Terraria.Utilities.UnifiedRandom(101);
            for (int trial = 0; trial < 48; trial++)
            {
                int roll = oracle.Next(denominator);
                var expected = alternatives.Single(a => a.GetProperty("randomValues").EnumerateArray().Any(v => v.GetInt32() == roll));
                var target = new NPC { whoAmI = 0, active = true };
                Terraria.Main.npc[0] = target;
                projectile.StatusNPC(0);
                int slot = Array.IndexOf(target.buffType, buff);
                if (expected.GetProperty("effects").GetArrayLength() == 0)
                    Equal(-1, slot, "native empty alternative requests no buff");
                else
                {
                    Equal(true, slot >= 0, "native requests certified buff for this exact roll");
                    Equal(expected.GetProperty("effects")[0].GetProperty("durationTicksMin").GetInt32(), target.buffTime[slot], "native discrete duration matches exact RNG branch");
                }
            }
        }
    }
    private static void ParentAttackCertificatesMatchNativeShootingAndCollision()
    {
        using var scope = new MobilityConsumptionNativeScope();
        var nativeShoot = typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!;
        var spawnMethod = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
            typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float),
            typeof(int), typeof(float), typeof(float), typeof(float) })!;
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            foreach (var (type, crit, factor, minimum, maximum) in new[] {
                (ItemID.BladeofGrass, 0f, .25f, 1, 1), (ItemID.LightsBane, 0f, .5f, 1, 1),
                (ItemID.LightsBane, 100f, 1f, 1, 1), (ItemID.Boomstick, 0f, 1f, 3, 4),
            })
            {
                var item = new Item(type); player.inventory[0] = item;
                player.GetCritChance(DamageClass.Melee) = crit;
                player.inventory[54] = new Item(ItemID.MusketBall, 99);
                player.itemAnimation = item.useAnimation; player.itemTime = 0;
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
                var captured = new List<(int Type, int Damage)>();
                using var hook = new Hook(spawnMethod,
                    (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, int>)
                    ((source, position, velocity, projectileType, damage, knockback, owner, a, b, c) => {
                        captured.Add((projectileType, damage)); return 0;
                    }));
                var scalarSpawn = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
                    typeof(IEntitySource), typeof(float), typeof(float), typeof(float), typeof(float), typeof(int), typeof(int),
                    typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!;
                using var scalarHook = new Hook(scalarSpawn,
                    (Func<IEntitySource, float, float, float, float, int, int, float, int, float, float, float, int>)
                    ((source, x, y, vx, vy, projectileType, damage, knockback, owner, a, b, c) => {
                        captured.Add((projectileType, damage)); return 0;
                    }));
                var reference = GeneratorClient.CaptureNativeShootReference(item)!;
                Equal(true, reference is not null, "loaded native method and module are certified");
                Equal(type == ItemID.LightsBane, reference!["shotDamageLocalMayBeModifiedInBranch"]!.GetValue<bool>(), "crit-conditioned local is not advertised as fixed base multiplier");
                int inputDamage = 80;
                nativeShoot.Invoke(player, new object[] { player.whoAmI, item, inputDamage });
                Equal(true, captured.Count >= minimum && captured.Count <= maximum, type + " actual native branch count " + captured.Count + " matches certificate");
                int expected = (int)((inputDamage + (type == ItemID.Boomstick ? player.inventory[54].damage : 0)) * factor);
                Equal(true, captured.All(p => p.Damage == expected), "actual damage expression preserves shot-local multiplier and critical branch");
                if (type != ItemID.Boomstick)
                    Equal(false, item.noMelee, "projectile does not replace native sword-contact channel");
            }
            var slash = new Projectile(); slash.SetDefaults(ProjectileID.LightsBane);
            slash.Center = new Vector2(500, 500); slash.rotation = 0;
            var collision = GeneratorClient.CaptureNativeCollisionReference(slash)!;
            Equal(46f, collision["halfLengthTimesProjectileScale"]!.GetValue<float>(), "source line half-length retained instead of small default hitbox");
            foreach (float scale in new[] { 1f, 2f })
            {
                slash.scale = scale;
                Equal(true, slash.Colliding(slash.Hitbox, new Rectangle(500 + (int)(40 * scale), 498, 4, 4)), "native line reaches inside scale-dependent endpoint");
                Equal(false, slash.Colliding(slash.Hitbox, new Rectangle(500 + (int)(60 * scale), 498, 4, 4)), "native line refuses beyond scale-dependent endpoint");
            }
            var verify = typeof(GeneratorClient).GetMethod("VerifiedNativeAttackReference", BindingFlags.NonPublic | BindingFlags.Static)!;
            Equal(null, verify.Invoke(null, new object?[] { ItemID.Boomstick, true, "Player.ItemCheck_Shoot", "unknown:module" }), "unknown native certificate never borrows source facts");
            string certificate = GeneratorClient.CaptureNativeShootReference(new Item(ItemID.Boomstick))!["sourceMethodSha256"]!.GetValue<string>()
                + ":" + typeof(Player).Module.ModuleVersionId;
            Equal(null, verify.Invoke(null, new object?[] { ItemID.Boomstick, false, "Player.ItemCheck_Shoot", certificate }), "modded identity cannot borrow vanilla source proof");
        });
    }

    private static void ParentContactStatusFactsKeepNativeItemAndTargetSignature()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var player = new Player(); Terraria.Main.player[0] = player;
        var item = new Item(ItemID.BladeofGrass);
        var reference = JsonSerializer.SerializeToElement(GeneratorClient.CaptureNativeContactHitStatusReference(item));
        Equal("contact", reference.GetProperty("sourceKind").GetString()!, "contact facts do not borrow projectile IDs");
        var choice = reference.GetProperty("randomOutcomes")[0];
        Equal(4, choice.GetProperty("randomMaximumExclusive").GetInt32(), "native item contact poison exact denominator");
        var proc = choice.GetProperty("alternatives")[0];
        Equal(1, proc.GetProperty("probabilityNumerator").GetInt32(), "native contact poison is one in four");
        Equal(BuffID.Poisoned, proc.GetProperty("effects")[0].GetProperty("buffId").GetInt32(), "native contact Poisoned ID");
        Equal(420, proc.GetProperty("effects")[0].GetProperty("durationTicksMin").GetInt32(), "native contact seven seconds");
        Terraria.Main.npc[0] = new NPC { active = true, whoAmI = 0 };
        using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, player).PayloadJson);
        Equal(CanonicalParentFactJson(reference), CanonicalParentFactJson(request.RootElement.GetProperty("itemA").GetProperty("nativeContactHitStatusReference")), "complete contact certificate reaches actual combine request");
        Equal(-1, Array.IndexOf(Terraria.Main.npc[0].buffType, BuffID.Poisoned), "capture never executes native contact hook");
        var status = typeof(Player).GetMethod("StatusToNPC", RootPrivate)!;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(151);
        var oracle = new Terraria.Utilities.UnifiedRandom(151);
        for (int trial = 0; trial < 48; trial++)
        {
            var target = new NPC { active = true, whoAmI = 0 }; Terraria.Main.npc[0] = target;
            bool expected = oracle.Next(4) == 0;
            status.Invoke(player, new object[] { item.type, 0 });
            int slot = Array.IndexOf(target.buffType, BuffID.Poisoned);
            Equal(expected, slot >= 0, "actual StatusToNPC matches each independent oracle roll");
            if (slot >= 0) Equal(420, target.buffTime[slot], "actual contact duration");
        }
        var verify = typeof(GeneratorClient).GetMethod("VerifiedNativeStatusReference", BindingFlags.NonPublic | BindingFlags.Static)!;
        Equal(null, verify.Invoke(null, new object?[] { item.type, true, "projectile", "Terraria/Unknown",
            reference.GetProperty("sourceMethodSha256").GetString(), reference.GetProperty("sourceModuleVersionId").GetString() }), "contact method certificate cannot authorize projectile reference");
        Equal(null, verify.Invoke(null, new object?[] { item.type, true, "contact", "Terraria/Unknown", "unknown", "module" }), "unknown contact method declined");
        var flare = new Projectile(); flare.SetDefaults(ProjectileID.Flare);
        var projectileReference = JsonSerializer.SerializeToElement(GeneratorClient.CaptureNativeHitStatusReference(flare));
        Equal(null, verify.Invoke(null, new object?[] { item.type, true, "contact", "Terraria/Unknown",
            projectileReference.GetProperty("sourceMethodSha256").GetString(), projectileReference.GetProperty("sourceModuleVersionId").GetString() }), "projectile method certificate cannot authorize contact reference");
        player.meleeEnchant = 1;
        var plain = new Item(ItemID.WoodenSword);
        Equal(null, GeneratorClient.CaptureNativeContactHitStatusReference(plain), "player enchantment cannot become an inherent item fact");
        var enchantedTarget = new NPC { active = true, whoAmI = 0 }; Terraria.Main.npc[0] = enchantedTarget;
        status.Invoke(player, new object[] { plain.type, 0 });
        Equal(true, Array.IndexOf(enchantedTarget.buffType, BuffID.Venom) >= 0, "negative observation control has a real player-dependent status, not an inert method");
        typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(item, new ContactFactModItem());
        Equal(null, GeneratorClient.CaptureNativeContactHitStatusReference(item), "modded item cannot borrow native contact certificate");
    }
    private sealed class ContactFactModItem : ModItem { }

}
