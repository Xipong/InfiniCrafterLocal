using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{

    private static GeneratedItemData UnitChargeFixture(float speed, int ticks, float power, int extraUpdates, int delayTicks = 0)
    {
        var data = SwarmGameplayFixture();
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Spawn.SpeedPxPerTick = speed;
        entity.Spawn.OverTarget.HeightTiles = delayTicks > 0 ? 1 : 0;
        entity.Spawn.OverTarget.DelayTicks = delayTicks;
        entity.Collision.ExtraUpdates = extraUpdates;
        entity.Controller.Name = "charge_then_release";
        entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
        entity.Controller.Params.ChargeTicks = ticks;
        entity.Controller.Params.PowerMultiplier = power;
        // Raw serialize before any normalizing writer so bad narrowing cannot hide.
        return GeneratedItemData.FromJson(JsonSerializer.Serialize(data,
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }))
            ?? throw new InvalidOperationException("unit charge fixture rejected");
    }

    private static void ChargeReleasePreservesAuthoredZeroAndFractionalSpeed()
    {
        foreach (float speed in new[] { 0f, 0.25f, 1f, 4f })
        foreach (float power in new[] { 1f, 2f })
        foreach (int extra in new[] { 0, 2 })
        foreach (int delay in new[] { 0, 2 })
        {
            using var scope = new SwarmRuntimeScope();
            var data = UnitChargeFixture(speed, 1, power, extra, delay);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            Equal(speed, entity.Spawn.SpeedPxPerTick, "raw DTO preserves speed");
            var generated = SwarmHost(data, entity);
            Equal<bool?>(false, ProjectileLoader.CanDamage(generated.Projectile), "unreleased charge is inert before controller AI");
            for (int update = 0; update < delay * (extra + 1); update++)
            {
                generated.AI();
                Equal<bool?>(false, ProjectileLoader.CanDamage(generated.Projectile), "activation delay cannot bypass charge contact gate");
            }
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal<bool?>(false, ProjectileLoader.CanDamage(generated.Projectile), "unreleased hydration remains inert before controller AI");
            Terraria.Main.player[0].channel = false;
            generated.AI();
            Equal<bool?>(null, ProjectileLoader.CanDamage(generated.Projectile), "released charge returns to native damage rules");
            float multiplier = 1f + (power - 1f) / (1 + extra);
            float expected = speed * multiplier;
            float actual = generated.Projectile.velocity.Length();
            if (Math.Abs(actual - expected) > 0.00001f)
                throw new InvalidOperationException($"charge speed={speed} power={power} extra={extra}: expected {expected}, got {actual}");
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            generated.AI();
            Equal<bool?>(null, ProjectileLoader.CanDamage(generated.Projectile), "released hydration stays damage eligible");
            if (Math.Abs(generated.Projectile.velocity.Length() - expected) > 0.00001f)
                throw new InvalidOperationException("released hydration compounded speed");
        }
    }

}
