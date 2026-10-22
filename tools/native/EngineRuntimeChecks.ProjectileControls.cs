using System;
using System.IO;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void IndependentChargeScalesThreeChannelsOnce()
    {
        foreach (bool partial in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope();
            var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Controller.Name = "charge_then_release"; entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
            entity.Controller.Params.ChargeTicks = 4; entity.Controller.Params.ChargeDamageMultiplier = 3;
            entity.Controller.Params.KnockbackMultiplier = 0.25f; entity.Controller.Params.SpeedMultiplier = 0.5f;
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity, damage: 100, knockback: 8);
            var owner = Terraria.Main.player[0]; owner.Center = new Vector2(640, 640);
            owner.inventory[0] = new Item(ItemID.WoodenSword); AttachItem(new GeneratedItem(), owner.inventory[0], data);
            owner.channel = true;
            for (int i = 0; i < (partial ? 1 : 3); i++) generated.AI();
            owner.channel = false; generated.AI();
            Equal(partial ? 200 : 300, generated.Projectile.damage, "charge independent full/partial damage");
            Equal(partial ? 5f : 2f, generated.Projectile.knockBack, "charge independent full/partial knockback");
            Equal(true, Math.Abs(generated.Projectile.velocity.Length() - (partial ? 3f : 2f)) < 0.0001f,
                "charge independent full/partial release speed");
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true); generated.AI();
            Equal(partial ? 200 : 300, generated.Projectile.damage, "charge hydration cannot apply multipliers twice");
            Equal(partial ? 5f : 2f, generated.Projectile.knockBack, "charge hydration keeps selected knockback");
        }
    }

    private static void OrbitWorldRateIsIndependentOfExtraUpdates()
    {
        foreach (int updates in new[] { 1, 3, 6 })
        foreach (float rate in new[] { -0.12f, 0f, 0.12f })
        {
            using var scope = new SwarmRuntimeScope();
            var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Movement.Name = "move_orbit"; entity.Movement.Code = 4;
            entity.Movement.Params.RangeTiles = 3; entity.Movement.Params.OrbitRadiansPerUpdate = rate / updates;
            entity.Collision.ExtraUpdates = updates - 1;
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity);
            var owner = Terraria.Main.player[0]; owner.Center = new Vector2(640, 640);
            for (int step = 0; step < 5 * updates; step++)
            {
                generated.AI();
                generated.Projectile.position += generated.Projectile.velocity;
            }
            float expectedAngle = 5 * rate + generated.Projectile.identity * 0.31f;
            Vector2 expected = owner.MountedCenter + expectedAngle.ToRotationVector2() * 48;
            Equal(true, Vector2.Distance(expected, generated.Projectile.Center) < 0.001f,
                "orbit signed world rate has identical angle across update counts");
            Equal(false, generated.Projectile.tileCollide, "orbit preserves its explicit no-tile movement");
            Vector2 before = generated.Projectile.Center;
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal(before, generated.Projectile.Center, "orbit hydration does not reset position or phase");
        }
    }

    private static void BounceRetentionChangesOnlyCollidedAxes()
    {
        foreach (float? retention in new float?[] { null, 0f, 0.5f, 1f })
        {
            using var scope = new SwarmRuntimeScope();
            var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Collision.BounceCount = 2;
            if (retention.HasValue) entity.Collision.BounceSpeedRetention = retention.Value;
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity); var projectile = generated.Projectile;
            projectile.velocity = new Vector2(0, 6);
            Equal(false, generated.OnTileCollide(new Vector2(8, 6)), "first tile contact is retained");
            Equal(new Vector2(-8 * (retention ?? 0.78f), 6), projectile.velocity,
                "bounce restores old collided X with chosen retention and unchanged tangent Y");
            projectile.velocity = Vector2.Zero;
            Equal(false, generated.OnTileCollide(new Vector2(8, 6)), "second tile contact is retained");
            Equal(new Vector2(-8 * (retention ?? 0.78f), -6 * (retention ?? 0.78f)), projectile.velocity,
                "corner bounce reflects both collided axes");
            Equal(true, generated.OnTileCollide(Vector2.One), "next tile contact delegates native death after exact count");
            if (!retention.HasValue) Equal(false, data.ToNetworkJson().Contains("bounceSpeedRetention"), "old definition keeps absent retention marker");
        }
    }

    private static void ProjectileControlDtoRejectsInvalidPresentAndKeepsOldAbsence()
    {
        foreach (string json in new[] { "{\"bounceSpeedRetention\":null}", "{\"bounceSpeedRetention\":1.00000000001}",
            "{\"bounceSpeedRetention\":-0.00000000001}" })
        {
            bool refused = false;
            try { JsonSerializer.Deserialize<RuntimeCollisionSpec>(json, new JsonSerializerOptions { PropertyNameCaseInsensitive = true }); }
            catch (JsonException) { refused = true; }
            Equal(true, refused, "bounce nullable exact raw boundary refuses malformed present value");
        }
        foreach (string field in new[] { "chargeDamageMultiplier", "knockbackMultiplier", "speedMultiplier" })
        foreach (string raw in new[] { "null", "1.0000000001", "0.9999999999", "4.0000000001" })
        {
            bool refused = false;
            try { JsonSerializer.Deserialize<RuntimeParamsSpec>("{\"" + field + "\":" + raw + "}", new JsonSerializerOptions { PropertyNameCaseInsensitive = true }); }
            catch (JsonException) { refused = true; }
            Equal(true, refused, "charge raw domain and neutral narrowing refusal");
        }
        foreach (Action invalid in new Action[] {
            () => new RuntimeParamsSpec { ChargeDamageMultiplier = null },
            () => new RuntimeParamsSpec { SpeedMultiplier = null },
            () => new RuntimeParamsSpec { SpeedMultiplier = 0 },
            () => new RuntimeParamsSpec { KnockbackMultiplier = float.NaN },
            () => new RuntimeParamsSpec { OrbitRadiansPerUpdate = float.PositiveInfinity },
            () => new RuntimeControllerSpec { Name = "charge_then_release", Code = 2, Params = new() { ChargeTicks = 700, ChargeDamageMultiplier = 2, KnockbackMultiplier = 1, SpeedMultiplier = 1 } }.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile),
            () => new RuntimeControllerSpec { Name = "charge_then_release", Code = 2, Params = new() { ChargeTicks = 5, PowerMultiplier = 2, ChargeDamageMultiplier = 2, KnockbackMultiplier = 1, SpeedMultiplier = 1 } }.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile),
            () => new RuntimeMovementSpec { Name = "move_straight", Code = 0, Params = new() { OrbitRadiansPerUpdate = 0.1f } }.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile),
            () => new RuntimeControllerSpec { Name = "charge_then_release", Code = 2, Params = new() { KnockbackMultiplier = 1 } }.NormalizeAndValidate(RuntimeEntityKind.FreeProjectile),
        })
        {
            bool refused = false; try { invalid(); } catch (InvalidDataException) { refused = true; }
            Equal(true, refused, "strict projectile controls reject malformed/foreign/incomplete choice");
        }
        var old = new RuntimeParamsSpec { PowerMultiplier = 2 };
        Equal(false, old.HasIndependentCharge, "old charge has no independently authored marker");
        Equal(false, old.OrbitRadiansPerUpdate.HasValue, "old orbit has no invented rate");
    }
}
