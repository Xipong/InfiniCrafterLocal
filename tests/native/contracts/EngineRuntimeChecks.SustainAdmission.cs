using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Activation at age one precedes the first world deadline. A seven-update
    // period aligns its first event with the six-world-tick recurring payment.
    private const int SustainEventPeriodTicks = 7;
    // Actual AI -> current strict wire event -> native child-spawn API. Only
    // allocation, Kill teardown and sockets are intercepted. Cancellation, event
    // admission and native CheckMana remain real. Nearby damage no longer admits
    // periodic/on_spawn; use a damaging child with the current spawn contract.
    private static GeneratedItemData SustainEventFixture(bool beam, string eventName, int extra = 0, bool sustain = true, bool controlled = true)
    {
        var data = BeamFixture(sustain);
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Collision.ExtraUpdates = extra;
        if (!beam) {
            var wire = System.Text.Json.Nodes.JsonNode.Parse(data.ToNetworkJson())!.AsObject();
            var body = FrontHandEntity(wire);
            foreach (string key in new[] { "beamGeometry", "beamRamp", "ownerControl", "manaSustain" }) body.Remove(key);
            body["movement"] = System.Text.Json.Nodes.JsonNode.Parse("{\"name\":\"move_straight\",\"code\":0}");
            body["visual"]!["assetMode"] = "no_asset";
            body["visual"]!.AsObject().Remove("geometry");
            data = GeneratedItemData.FromJson(wire.ToJsonString())
                ?? throw new InvalidOperationException("sustain fixture refused: " + ContractJsonDiagnostics.LastError);
            entity = data.RuntimeProgram.TryGetEntity("root")!;
            if (sustain) entity.ManaSustain = new() { Cadence = "held_item_use_time" };
            if (controlled) entity.OwnerControl = new RuntimeOwnerControlSpec {
                RequireHeldItem = true, RequireChannel = true, Animation = "none", Lifetime = "authored",
            };
        }
        var child = ChildCombatFixture().RuntimeProgram.TryGetEntity("child")!;
        child.Spawn.Placement = "item_use_origin"; child.Spawn.Aim = "velocity";
        child.Spawn.OffsetPx = 0; child.Spawn.OverTarget = new();
        data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(child).ToArray();
        entity.Events = new[] { new RuntimeEventActionSpec {
            Id = "sustain_event", Action = "spawn_entity_on_event", ActionCode = RuntimeEventActionCode.SpawnEntity,
            Event = eventName, PeriodTicks = eventName == RuntimeEventKind.Periodic ? SustainEventPeriodTicks : 0,
            EntityId = child.Id, Count = 1, SpreadRadians = 0, DamageMultiplier = 1,
            DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild,
        } };
        return SwarmWire(data);
    }

    private static Hook SustainKillBoundary()
        => new Hook(typeof(Projectile).GetMethod(nameof(Projectile.Kill), Type.EmptyTypes)!,
            (Action<Projectile>)(projectile => projectile.active = false));

    private static Hook SustainSpawnBoundary(GeneratedProjectile host, Action observe)
        => new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, ai0, ai1, ai2) => {
                Equal(true, source is EntitySource_Parent parent && ReferenceEquals(parent.Entity, host.Projectile),
                    "sustain event retains exact parent source at native gameplay boundary");
                Equal(true, damage > 0, "positive control requests a damaging authored child");
                observe();
                return new Projectile(); // no registered world allocation is claimed
            }));

    private static void SustainCancellationPrecedesNativeEvents(bool beam)
    {
        foreach (int mode in new[] { NetmodeID.SinglePlayer })
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
            int attempts = 0; using var spawn = SustainSpawnBoundary(host, () => attempts++);
            if (when == RuntimeEventKind.Periodic) BeamAge(host, SustainEventPeriodTicks - 1);
            if (reason == "release") owner.channel = false;
            if (reason == "different_item") owner.inventory[0] = new Item();
            if (reason == "inactive") owner.active = false;
            if (reason == "CCed") owner.frozen = true;
            if (reason == "dead") owner.dead = true;
            if (reason == "noItems") owner.noItems = true;
            if (reason == "animation") owner.itemAnimation = 0;
            MaterialClock(100); host.AI();
            Equal(0, attempts, $"{mode}/{beam}/{reason}/{when}: cancellation precedes native gameplay event");
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
            int attempts = 0; using var spawn = SustainSpawnBoundary(host, () => attempts++);
            MaterialClock(100); host.AI();
            Equal(true, host.Projectile.active, "native initial item payment covers first activation");
            BeamAge(host, SustainEventPeriodTicks * (extra + 1) - 1);
            MaterialClock(106); host.AI();
            Equal(0, attempts, $"beam={beam}/extra={extra}: failed sustain cannot produce last free native gameplay action");
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
            int attempts = 0, calls = 0;
            using var spawn = SustainSpawnBoundary(host, () => {
                Equal(1, calls, "native recurring payment already completed before native child-spawn boundary");
                Equal(95, owner.statMana, "gameplay observes the paid mana balance, not a later debit");
                attempts++;
            });
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
            Equal(pays ? 1 : 0, attempts, "one native gameplay event at exact periodic age; owner-only spawn authority retained");
        }
    }

    private static void SustainFreeProjectileKeepsUncontrolledEvents()
    {
        using var scope = new SwarmRuntimeScope(); using var kill = SustainKillBoundary();
        var data = SustainEventFixture(false, RuntimeEventKind.OnSpawn, sustain: false, controlled: false);
        var host = BeamHost(data); var owner = Terraria.Main.player[0];
        owner.channel = false; owner.inventory[0] = new Item(); owner.statMana = 0;
        int attempts = 0; using var spawn = SustainSpawnBoundary(host, () => attempts++); MaterialClock(100); host.AI();
        Equal(true, host.Projectile.active, "free projectile does not gain implicit channel/held cancellation");
        Equal(1, attempts, "uncontrolled on_spawn still reaches native damaging child-spawn API");
    }
}
