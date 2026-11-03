using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Actual AI -> strict wire event -> native NPC damage. Kill's world teardown
    // and socket sends are intercepted. The payment observer invokes native
    // CheckMana; cancellation, event admission and NPC damage remain real.
    private static GeneratedItemData SustainEventFixture(bool beam, string eventName, int extra = 0, bool sustain = true, bool controlled = true)
    {
        var data = BeamFixture();
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Collision.ExtraUpdates = extra;
        if (!beam) {
            entity.Controller = new RuntimeControllerSpec();
            entity.Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 };
            if (sustain) entity.ManaSustain = new RuntimeManaSustainSpec { Cadence = "held_item_use_time" };
            if (controlled) entity.OwnerControl = new RuntimeOwnerControlSpec {
                RequireHeldItem = true, RequireChannel = true, Animation = "none", Lifetime = "authored",
            };
        }
        entity.Events = new[] { new RuntimeEventActionSpec {
            Id = "sustain_event", Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
            Event = eventName, PeriodTicks = eventName == RuntimeEventKind.Periodic ? 6 : 0, RadiusPx = 128, DamageMultiplier = .5f,
        } };
        return SwarmWire(data);
    }

    private static Hook SustainKillBoundary()
        => new Hook(typeof(Projectile).GetMethod(nameof(Projectile.Kill), Type.EmptyTypes)!,
            (Action<Projectile>)(projectile => projectile.active = false));

    private static NPC SustainTarget(GeneratedProjectile host)
    {
        Terraria.Main.SceneMetrics = new SceneMetrics();
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
        return Terraria.Main.npc[0] = EventDomainNpc(0, host.Projectile.Center, 40);
    }

    private static void SustainCancellationPrecedesNativeEvents(bool beam)
    {
        foreach (int mode in beam ? new[] { NetmodeID.SinglePlayer, NetmodeID.Server } : new[] { NetmodeID.SinglePlayer })
        foreach (string reason in new[] { "release", "different_item", "inactive", "dead", "noItems", "CCed", "animation" })
        foreach (string when in new[] { RuntimeEventKind.OnSpawn, RuntimeEventKind.Periodic }) {
            if (beam && reason == "animation") continue; // channel beam has no animation requirement
            using var scope = new SwarmRuntimeScope(mode, mode == NetmodeID.Server ? 255 : 0);
            using var kill = SustainKillBoundary();
            using var network = PersistenceObserveNetworkSend((_, _) => { });
            var data = SustainEventFixture(beam, when, sustain: false);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            if (!beam) {
                entity.OwnerControl = new RuntimeOwnerControlSpec {
                    RequireChannel = true, RequireHeldItem = true, RequireItemAnimation = true,
                    Animation = "none", Lifetime = "authored",
                };
                data = SwarmWire(data);
            }
            var host = BeamHost(data); var owner = Terraria.Main.player[0]; owner.itemAnimation = 20;
            var npc = SustainTarget(host);
            if (when == RuntimeEventKind.Periodic) BeamAge(host, 5);
            if (reason == "release") owner.channel = false;
            if (reason == "different_item") owner.inventory[0] = new Item();
            if (reason == "inactive") owner.active = false;
            if (reason == "CCed") owner.frozen = true;
            if (reason == "dead") owner.dead = true;
            if (reason == "noItems") owner.noItems = true;
            if (reason == "animation") owner.itemAnimation = 0;
            MaterialClock(100); host.AI();
            Equal(1000, npc.life, $"{mode}/{beam}/{reason}/{when}: cancelled AI cannot damage NPC before retirement");
            Equal(false, host.Projectile.active, "cancelled projectile retires");
        }
    }

    private static void SustainPaymentPrecedesNativePeriodicDamage(bool beam)
    {
        foreach (int extra in new[] { 0, 2 }) {
            using var scope = new SwarmRuntimeScope(); using var kill = SustainKillBoundary();
            var data = SustainEventFixture(beam, RuntimeEventKind.Periodic, extra);
            var host = BeamHost(data); var owner = Terraria.Main.player[0];
            owner.statMana = 0; owner.manaFlower = false; owner.HeldItem.mana = 10; owner.HeldItem.useTime = 6;
            var npc = SustainTarget(host);
            MaterialClock(100); host.AI();
            Equal(true, host.Projectile.active, "native initial item payment covers first activation");
            BeamAge(host, 6 * (extra + 1) - 1);
            MaterialClock(106); host.AI();
            Equal(1000, npc.life, $"beam={beam}/extra={extra}: failed sustain cannot produce last free native hit");
            Equal(false, host.Projectile.active || host.Projectile.friendly, "failed sustain cannot remain contact damaging");
        }
    }

    private static void SustainSuccessfulPaymentKeepsClockAndAuthority()
    {
        foreach (var role in SwarmRoles)
        foreach (bool beam in new[] { true, false })
        foreach (int extra in new[] { 0, 2 })
        foreach (uint origin in new[] { 100u, uint.MaxValue - 2 }) {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local); using var kill = SustainKillBoundary();
            using var network = PersistenceObserveNetworkSend((_, _) => { });
            var data = SustainEventFixture(beam, RuntimeEventKind.Periodic, extra);
            var host = BeamHost(data); var owner = Terraria.Main.player[0];
            owner.statMana = 100; owner.manaCost = .5f; owner.manaFlower = false;
            owner.HeldItem.mana = 10; owner.HeldItem.useTime = 6;
            var npc = SustainTarget(host); int calls = 0;
            using var payment = new Hook(typeof(Player).GetMethod(nameof(Player.CheckMana),
                new[] { typeof(Item), typeof(int), typeof(bool), typeof(bool) })!,
                (Func<Func<Player, Item, int, bool, bool, bool>, Player, Item, int, bool, bool, bool>)
                ((orig, player, item, amount, pay, quick) => { calls++; return orig(player, item, amount, pay, quick); }));
            for (uint tick = 0; tick <= 6; tick++) {
                MaterialClock(unchecked(origin + tick));
                for (int update = 0; update <= extra; update++) host.AI();
            }
            bool pays = role.Name is "SP" or "owner-client";
            Equal(pays ? 1 : 0, calls, "one native payment at world deadline; no peer or extra-update debit");
            Equal(pays ? 95 : 100, owner.statMana, "native manaCost retained");
            Equal(true, host.Projectile.active, "successful paid/peer AI remains active");
            Equal(role.Name is "SP" or "server", npc.life < 1000, "NPC event authority retained on admitted ticks");
        }
    }

    private static void SustainFreeProjectileKeepsUncontrolledEvents()
    {
        using var scope = new SwarmRuntimeScope(); using var kill = SustainKillBoundary();
        var data = SustainEventFixture(false, RuntimeEventKind.OnSpawn, sustain: false, controlled: false);
        var host = BeamHost(data); var owner = Terraria.Main.player[0];
        owner.channel = false; owner.inventory[0] = new Item(); owner.statMana = 0;
        var npc = SustainTarget(host); MaterialClock(100); host.AI();
        Equal(true, host.Projectile.active, "free projectile does not gain implicit channel/held cancellation");
        Equal(true, npc.life < 1000, "uncontrolled on_spawn still executes actual native damage");
    }
}
