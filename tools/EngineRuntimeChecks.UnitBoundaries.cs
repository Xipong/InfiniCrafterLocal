using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData UnitChargeFixture(float speed, int ticks, float power, int extraUpdates)
    {
        var data = SwarmGameplayFixture();
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Spawn.SpeedPxPerTick = speed;
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
        {
            using var scope = new SwarmRuntimeScope();
            var data = UnitChargeFixture(speed, 1, power, extra);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            Equal(speed, entity.Spawn.SpeedPxPerTick, "raw DTO preserves speed");
            var generated = SwarmHost(data, entity);
            Terraria.Main.player[0].channel = false;
            generated.AI();
            float multiplier = 1f + (power - 1f) / (1 + extra);
            float expected = speed * multiplier;
            float actual = generated.Projectile.velocity.Length();
            if (Math.Abs(actual - expected) > 0.00001f)
                throw new InvalidOperationException($"charge speed={speed} power={power} extra={extra}: expected {expected}, got {actual}");
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            generated.AI();
            if (Math.Abs(generated.Projectile.velocity.Length() - expected) > 0.00001f)
                throw new InvalidOperationException("released hydration compounded speed");
        }
    }

    private static void ChargeCompleteRequiresExactAuthoredDuration()
    {
        foreach (int extra in new[] { 0, 1, 5 })
        foreach (bool complete in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope();
            var data = UnitChargeFixture(4, 600, 1, extra);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var child = new RuntimeEntitySpec {
                Id = "completion_child", Kind = RuntimeEntityKind.ChildProjectile,
                VisualRole = "child_projectile",
                Visual = new RuntimeEntityVisualSpec { Role = "child_projectile", AssetMode = "no_asset" },
                Spawn = new RuntimeSpawnSpec { Enabled = true, Count = 1, Aim = "facing", SpeedPxPerTick = 1 },
                LifetimeTicks = 30,
                Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 },
            };
            data.RuntimeProgram.Entities = new[] { data.RuntimeProgram.Entities[0], entity, child };
            entity.Events = new[] { new RuntimeEventActionSpec {
                Id = "completion_spawn", Event = "channel_complete", Action = "spawn_entity_on_event",
                ActionCode = RuntimeEventActionCode.SpawnEntity, EntityId = child.Id, Count = 1,
                DamageMultiplier = 1, DelayTicks = 1,
            } };
            data = SwarmWire(data);
            entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity);
            int duration = 600 * (1 + extra);
            typeof(GeneratedProjectile).GetField("_chargeTicks", BindingFlags.Instance | BindingFlags.NonPublic)!
                .SetValue(generated, duration - (complete ? 1 : 2));
            Terraria.Main.player[0].channel = false;
            generated.AI();
            Equal(complete ? 1 : 0, PendingActions(), $"channel_complete exact threshold extra={extra} complete={complete}");
            Equal(true, (bool)typeof(GeneratedProjectile).GetField("_released", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(generated)!, "ordinary release still occurs");
            generated.AI();
            Equal(complete ? 1 : 0, PendingActions(), "completion queues once, no fake child spawn");
        }
    }
}
