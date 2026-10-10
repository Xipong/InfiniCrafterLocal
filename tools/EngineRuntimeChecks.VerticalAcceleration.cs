using System;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData VerticalAccelerationWire(float acceleration, int extraUpdates, int delayTicks)
    {
        var data = SwarmGameplayFixture();
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Movement.Name = "move_gravity_arc";
        entity.Movement.Code = 2;
        entity.Movement.Params.GravityPerTick = acceleration;
        entity.Collision.ExtraUpdates = extraUpdates;
        entity.Spawn.OverTarget.DelayTicks = delayTicks;
        entity.Spawn.SpeedPxPerTick = 4;
        // Read raw handoff through the actual strict DTO before any writer clamp.
        return GeneratedItemData.FromJson(JsonSerializer.Serialize(data,
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }))
            ?? throw new InvalidOperationException("signed acceleration fixture rejected");
    }

    private static void SignedVerticalAccelerationUsesNativeDtoAndEveryActiveUpdate()
    {
        foreach (var role in SwarmRoles)
        foreach (int extraUpdates in new[] { 0, 1, 5 })
        foreach (float acceleration in new[] { -2f, -0.125f, -float.Epsilon, 0f, float.Epsilon, 0.125f, 2f })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = VerticalAccelerationWire(acceleration, extraUpdates, 0);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            Equal(acceleration, entity.Movement.Params.GravityPerTick, "strict DTO retains the signed choice");
            var generated = SwarmHost(data, entity);
            generated.Projectile.velocity = new Vector2(4, 0);
            // Real AI calls represent each projectile update, not a replacement
            // gravity implementation. Position/world stepping is not simulated.
            for (int update = 1; update <= 3 * (extraUpdates + 1); update++)
            {
                generated.AI();
                Equal(4f, generated.Projectile.velocity.X, "gravity has no horizontal friction");
                Equal(update * acceleration, generated.Projectile.velocity.Y,
                    $"{role.Name}: per-update signed acceleration at update {update}");
                generated.Projectile.timeLeft--;
            }
            var before = generated.Projectile.velocity;
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal(before, generated.Projectile.velocity, "late hydration does not relaunch the live trajectory");
            generated.AI();
            Equal(before.Y + acceleration, generated.Projectile.velocity.Y, "next update adds exactly once after hydration");
            Equal(before.X, generated.Projectile.velocity.X, "hydration keeps the independent X velocity");
        }
    }

    private static void SignedVerticalAccelerationWaitsForActivationThenPreservesAuthoredRate()
    {
        foreach (var role in SwarmRoles)
        foreach (int extraUpdates in new[] { 0, 1, 5 })
        foreach (float acceleration in new[] { -2f, 0f, 2f })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = VerticalAccelerationWire(acceleration, extraUpdates, 2);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity);
            for (int update = 0; update < 2 * (extraUpdates + 1); update++)
            {
                generated.AI();
                Equal(Vector2.Zero, generated.Projectile.velocity, "telegraph wait applies no acceleration");
                generated.Projectile.timeLeft--;
            }
            generated.AI();
            Equal(new Vector2(4, acceleration), generated.Projectile.velocity,
                "first active update restores launch once and immediately applies the chosen acceleration");
            generated.AI();
            Equal(new Vector2(4, 2 * acceleration), generated.Projectile.velocity,
                "second active update keeps native per-projectile-update rate");
        }
    }
}
