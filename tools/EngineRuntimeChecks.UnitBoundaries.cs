using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using InfiniCrafterLocal.Content.Items;
using Terraria.ID;
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

    private static void ChargeReleaseKeepsAuthoredFlightLifetime()
    {
        WithPersistenceTilemap((_, _) => {
            foreach (int extraUpdates in new[] { 0, 2 })
            foreach (int lifetimeTicks in new[] { 1, 8 })
            foreach (int holdTicks in new[] { 2, 20 })
            {
                using var scope = new SwarmRuntimeScope();
                var data = UnitChargeFixture(4f, 6, 2f, extraUpdates);
                var entity = data.RuntimeProgram.TryGetEntity("root")!;
                entity.LifetimeTicks = lifetimeTicks;
                entity.Events = new[] { new RuntimeEventActionSpec {
                    Id = "flight_expired", Event = RuntimeEventKind.OnExpire,
                    Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
                    RadiusPx = 16, DamageMultiplier = 1f, DelayTicks = 1,
                } };
                data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
                var generated = SwarmHost(data, entity);
                var owner = Terraria.Main.player[0];
                owner.Center = new Vector2(640, 640);
                owner.inventory[0] = new Item(ItemID.WoodenSword);
                AttachItem(new GeneratedItem(), owner.inventory[0], data);
                owner.channel = true;
                generated.Projectile.Center = owner.Center;
                // An existing native type supplies per-type array bounds; its
                // vanilla AI is disabled and the actual attached mod AI runs.
                generated.Projectile.type = ProjectileID.WoodenArrowFriendly;
                generated.Projectile.aiStyle = -1;
                int lifetimeUpdates = lifetimeTicks * (extraUpdates + 1);
                for (int tick = 0; tick < holdTicks; tick++)
                    generated.Projectile.Update(0);
                string label = $"lifetime={lifetimeTicks} hold={holdTicks} extraUpdates={extraUpdates}: ";
                Equal(true, generated.Projectile.active, label + "native charging update stays alive");
                Equal(lifetimeUpdates, generated.Projectile.timeLeft, label + "charging preserves the authored flight budget");
                Equal(0, PendingActions(), label + "charging never emits natural expiry");

                // The installed Update method above owns native subupdates and
                // lifetime decrement. Moving flight needs registered TileLoader
                // hooks, so its remaining clock is checked at the real AI hook
                // with that same post-AI decrement, not claimed as a game loop.
                if (holdTicks == 20) owner.inventory[0] = new Item(ItemID.Wood);
                else owner.channel = false;
                generated.AI();
                Equal(true, generated.Projectile.friendly, label + "release/item switch enables authored damage");
                Equal(lifetimeUpdates, generated.Projectile.timeLeft, label + "release retains the flight budget");
                Equal(lifetimeUpdates == 1 ? 1 : 0, PendingActions(), label + "expiry only on final flight update");
                generated.Projectile.timeLeft--;
                if (lifetimeUpdates > 1)
                {
                    generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
                    Equal(lifetimeUpdates - 1, generated.Projectile.timeLeft, label + "hydration never restarts released lifetime");
                    while (generated.Projectile.timeLeft > 0)
                    {
                        int before = generated.Projectile.timeLeft;
                        generated.AI();
                        Equal(before, generated.Projectile.timeLeft, label + "released AI does not freeze the clock");
                        Equal(before == 1 ? 1 : 0, PendingActions(), label + "exact final flight update emits expiry");
                        generated.Projectile.timeLeft--;
                    }
                }
                generated.OnKill(0);
                Equal(1, PendingActions(), label + "terminal hook does not duplicate expiry");
            }
        });
        foreach (bool ownerInvalid in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope();
            var data = UnitChargeFixture(4f, 6, 2f, 0);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity);
            if (ownerInvalid)
            {
                Terraria.Main.player[0].dead = true;
                generated.AI();
                Equal(false, generated.Projectile.active, "invalid owner still terminates charging immediately");
            }
            else
            {
                entity.Controller = new RuntimeControllerSpec();
                int before = generated.Projectile.timeLeft;
                generated.AI();
                Equal(before, generated.Projectile.timeLeft, "ordinary non-charging AI does not replenish lifetime");
            }
        }
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

}
