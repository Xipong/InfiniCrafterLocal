using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentFixedSpawnFactsMatchNativeBranchAndRequest()
    {
        using var scope = new MobilityConsumptionNativeScope();
        var nativeShoot = typeof(Player).GetMethod("ItemCheck_Shoot", RootPrivate)!;
        var vectorSpawn = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
            typeof(IEntitySource), typeof(Vector2), typeof(Vector2), typeof(int), typeof(int), typeof(float),
            typeof(int), typeof(float), typeof(float), typeof(float) })!;
        var scalarSpawn = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
            typeof(IEntitySource), typeof(float), typeof(float), typeof(float), typeof(float), typeof(int), typeof(int),
            typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!;
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            foreach (var (type, count) in new[] {
                (ItemID.TacticalShotgun, 6), (ItemID.PiranhaGun, 3),
                (ItemID.ReleaseDoves, 3), (ItemID.BubbleGun, 3),
            })
            {
                var item = new Item(type); player.inventory[0] = item;
                player.inventory[54] = new Item(ItemID.MusketBall, 99);
                player.itemAnimation = item.useAnimation; player.itemTime = 0;
                var reference = GeneratorClient.CaptureNativeShootReference(item);
                Equal(true, reference is not null, "fixed-loop source shape has a certified row");
                Equal(count, reference!["explicitSpawnCount"]!["minimum"]!.GetValue<int>(), "literal lower count");
                Equal(count, reference["explicitSpawnCount"]!["maximum"]!.GetValue<int>(), "literal upper count");
                Equal("fixed", reference["explicitSpawnCount"]!["distribution"]!.GetValue<string>(), "not a random count distribution");
                Equal(1f, reference["damageMultiplierAtSpawn"]!.GetValue<float>(), "current shot local is unscaled");
                using (var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, player).PayloadJson))
                {
                    var expected = JsonSerializer.SerializeToElement(reference);
                    Equal(CanonicalParentFactJson(expected), CanonicalParentFactJson(request.RootElement.GetProperty("itemA").GetProperty("nativeShootReference")), "exact generated row reaches request capture");
                }
                // Hooks intercept only the terminal spawn boundary. ItemCheck_Shoot
                // and its native loop execute for real; no projectile AI/world runs.
                var captured = new List<int>();
                using var vectorHook = new Hook(vectorSpawn,
                    (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, int>)
                    ((source, position, velocity, projectileType, damage, knockback, owner, a, b, c) => {
                        captured.Add(damage); return 0;
                    }));
                using var scalarHook = new Hook(scalarSpawn,
                    (Func<IEntitySource, float, float, float, float, int, int, float, int, float, float, float, int>)
                    ((source, x, y, vx, vy, projectileType, damage, knockback, owner, a, b, c) => {
                        captured.Add(damage); return 0;
                    }));
                foreach (int seed in new[] { 17, 91, 151 })
                {
                    captured.Clear();
                    Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed);
                    player.itemAnimation = item.useAnimation; player.itemTime = 0;
                    nativeShoot.Invoke(player, new object[] { player.whoAmI, item, 80 });
                    Equal(count, captured.Count, "actual native fixed loop count is independent of spread RNG");
                    int expectedDamage = 80 + (type == ItemID.TacticalShotgun ? player.inventory[54].damage : 0);
                    Equal(true, captured.All(damage => damage == expectedDamage), "native spawn uses current shot damage without multiplier");
                }
            }
        });
    }
}
