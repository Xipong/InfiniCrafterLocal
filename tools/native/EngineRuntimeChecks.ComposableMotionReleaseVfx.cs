using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Test-first observer: only existing DTO/packet/ExtraAI APIs, including on
    // the frozen product before the owner release transport fix.
    private static GeneratedItemData MotionReleaseVfxData(bool automatic, bool effect = true)
    {
        var root = JsonNode.Parse(ReviewProjectileData("on_release", "channel_complete").ToJson())!.AsObject();
        root.Remove("runtimeContract");
        root["runtimeProgram"]!["itemUse"]!["channel"] = true;
        var actor = root["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "actor")!;
        actor.AsObject().Remove("controller"); // no legacy controller selected; neutral wire name is empty, not "none"
        actor["aim"] = JsonNode.Parse("{\"source\":\"initial\",\"turnOwner\":false}");
        actor["charge"] = JsonNode.Parse(automatic
            ? "{\"durationTicks\":4,\"autoReleaseAfterActiveTicks\":4}"
            : "{\"durationTicks\":4}");
        if (effect) actor["chargeRelease"] = JsonNode.Parse("{\"damageMultiplier\":2,\"knockbackMultiplier\":3,\"speedMultiplier\":2,\"launchSpeed\":6,\"pauseLifetimeWhileCharging\":true}");
        var data = ParseMaterialElement(root);
        // Delayed real child actions expose gameplay replay through both pending
        // actions and the actual activation ledger without spawning native bodies.
        data.RuntimeProgram.TryGetEntity("actor")!.Events = new[] { "on_release", "channel_complete" }
            .SelectMany((ev, i) => new[] {
                new RuntimeEventActionSpec {
                    Id = "release_child_" + i, Event = ev, Action = "spawn_entity_on_event",
                    ActionCode = RuntimeEventActionCode.SpawnEntity, EntityId = "actor", Count = 1,
                    SpreadRadians = 0, DamageMultiplier = 1,
                    DamageBasis = RuntimeChildCombatBasis.AuthoredChild,
                    KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild, DelayTicks = 60,
                },
                // A server-authoritative action catches accidental server gameplay
                // dispatch even though a child action alone would fail authority there.
                new RuntimeEventActionSpec {
                    Id = "release_area_" + i, Event = ev, Action = "damage_area_on_event",
                    ActionCode = RuntimeEventActionCode.DamageArea, RadiusPx = 16,
                    DamageMultiplier = 1, DelayTicks = 60,
                },
            }).ToArray();
        return data;
    }

    private static GeneratedProjectile MotionReleaseVfxOwner(ReviewPeers peers, GeneratedItemData data)
    {
        peers.Register(data); peers.Mode(NetmodeID.MultiplayerClient, 0);
        Terraria.Main.player[0].channel = true;
        var owner = peers.Host(data);
        owner.Configure(data, data.RuntimeProgram.TryGetEntity("actor")!, 0, 8, Vector2.UnitX);
        owner.Projectile.damage = 40; owner.Projectile.knockBack = 2; owner.Projectile.velocity = Vector2.UnitX;
        return owner;
    }

    private static RuntimeSpawnBudget? MotionReleaseBudget(GeneratedProjectile host)
        => (RuntimeSpawnBudget?)typeof(GeneratedProjectile).GetField("_activationSpawnBudget", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(host);

    private static void ComposableMotionManualReleaseVfxRoundtrip()
        => MotionReleaseVfxRoundtrip(automatic: false);

    private static void ComposableMotionAutomaticCompletionVfxRoundtrip()
        => MotionReleaseVfxRoundtrip(automatic: true);

    private static void MotionReleaseVfxRoundtrip(bool automatic)
    {
        foreach (bool effect in new[] { true, false }) WithLighting((_, __) => {
            using var peers = new ReviewPeers(); RuntimeDelayedActionScheduler.Clear();
            try {
                var data = MotionReleaseVfxData(automatic, effect);
                var owner = MotionReleaseVfxOwner(peers, data);
                var initialExtra = ReviewExtra(owner);
                var ledger = MotionReleaseBudget(owner)!;
                if (automatic) for (int i = 0; i < 4; i++) owner.AI();
                else { owner.AI(); Terraria.Main.player[0].channel = false; owner.AI(); }
                int events = automatic ? 2 : 1;
                int damage = effect ? (automatic ? 80 : 60) : 40;
                float knockback = effect ? (automatic ? 6f : 4f) : 2f;
                Equal(events, PendingActions(), "only actual owner release schedules authored children");
                Equal(8 - events, ledger.Remaining, "owner spends one child reservation per real event");
                Equal(damage, owner.Projectile.damage, "release combat multiplier applied once");
                Equal(knockback, owner.Projectile.knockBack, "release knockback multiplier applied once");
                Equal(events, peers.Sent.Count, "actual new-charge release emits owner presentation claim(s)");
                var claims = peers.Sent.ToArray(); var releasedExtra = ReviewExtra(owner);
                owner.ReceiveExtraAI(new BinaryReader(new MemoryStream(initialExtra)));
                owner.ReceiveExtraAI(new BinaryReader(new MemoryStream(releasedExtra)));
                owner.AI();
                Equal(events, peers.Sent.Count, "owner hydration cannot repeat release claims");
                Equal(events, PendingActions(), "owner hydration cannot reschedule gameplay");
                Equal(8 - events, ledger.Remaining, "owner hydration cannot replenish/spend ledger");
                Equal(true, ReferenceEquals(ledger, MotionReleaseBudget(owner)), "owner retains exact mutable ledger");
                Equal(damage, owner.Projectile.damage, "owner hydration cannot multiply damage again");

                // Separate native roster, same world and authenticated owner stream.
                // Divergent peer counters deliberately cannot decide completion.
                RuntimeDelayedActionScheduler.Clear(); peers.Mode(NetmodeID.Server, 255); peers.Sent.Clear();
                var server = peers.Host(data, extra: initialExtra);
                server.Projectile.damage = 40; server.Projectile.knockBack = 2;
                typeof(GeneratedProjectile).GetField("_chargeTicks", BindingFlags.Instance | BindingFlags.NonPublic)!
                    .SetValue(server, automatic ? 0 : 999);
                foreach (var claim in claims) peers.Receive(claim, 0);
                Equal(events, peers.Sent.Count, "server relays only the actual owner event set, not peer charge counters");
                var relays = peers.Sent.ToArray();
                foreach (var claim in claims) peers.Receive(claim, 0);
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(releasedExtra)));
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(initialExtra)));
                server.AI();
                Equal(events, peers.Sent.Count, "duplicate owner packets and ExtraAI cannot re-emit server presentation");
                Equal(0, PendingActions(), "server never replays release gameplay");
                Equal<RuntimeSpawnBudget?>(null, MotionReleaseBudget(server), "server observations grant no spawn ledger");
                Equal(40, server.Projectile.damage, "server relay/hydration cannot apply charge multipliers");
                Equal(2f, server.Projectile.knockBack, "server relay/hydration cannot apply knockback multipliers");

                // Detached world events still reach a remote with no live source.
                // Expire local-owner emissions without resetting stream ownership.
                peers.Mode(NetmodeID.MultiplayerClient, 2); MaterialClock(120); peers.System.PostUpdateEverything();
                Equal(0, OwnedMaterialQueue().Count, "owner-local emissions retired before remote receive");
                foreach (var relay in relays) peers.Receive(relay);
                Equal(events, OwnedMaterialQueue().Count, "remote receives every exact detached owner release/completion event");
                var remote = peers.Host(data, 11, extra: releasedExtra);
                remote.Projectile.damage = damage; remote.Projectile.knockBack = knockback;
                remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(releasedExtra)));
                remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(initialExtra)));
                remote.AI();
                foreach (var relay in relays) peers.Receive(relay);
                Equal(events, OwnedMaterialQueue().Count, "remote relay replay/late hydration cannot duplicate detached emissions");
                Equal(events, peers.Sent.Count, "nonowner hydration does not send owner claims");
                Equal(0, PendingActions(), "remote presentation never schedules gameplay");
                Equal<RuntimeSpawnBudget?>(null, MotionReleaseBudget(remote), "remote observation grants no spawn budget");
                Equal(damage, remote.Projectile.damage, "remote hydration never reapplies release damage");
                Equal(knockback, remote.Projectile.knockBack, "remote hydration never reapplies release knockback");
                Equal(1, Terraria.Main.projectile.Count(p => p.active), "no presentation receive spawned gameplay bodies");
            } finally { RuntimeDelayedActionScheduler.Clear(); }
        });
    }

    private static void ComposableMotionReleaseVfxKeepsAuthenticatedSourceFences()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); RuntimeDelayedActionScheduler.Clear();
            try {
                var data = MotionReleaseVfxData(automatic: false);
                var owner = MotionReleaseVfxOwner(peers, data); var extra = ReviewExtra(owner);
                Terraria.Main.player[0].channel = false; owner.AI();
                Equal(1, peers.Sent.Count, "fence test uses captured actual owner release, never fabricated expected packet");
                var claim = peers.Sent.Single(); RuntimeDelayedActionScheduler.Clear();
                peers.Mode(NetmodeID.Server, 255); peers.Sent.Clear(); var source = peers.Host(data, extra: extra);
                void Rejected(string reason) { peers.Receive(claim, 0); Equal(0, peers.Sent.Count, reason); }
                peers.Receive(claim, 1); Equal(0, peers.Sent.Count, "foreign sender rejected");
                Terraria.Main.player[0].active = false; Rejected("inactive owner rejected"); Terraria.Main.player[0].active = true;
                source.Projectile.active = false; Rejected("inactive source rejected"); source.Projectile.active = true;
                source.Projectile.identity++; Rejected("wrong projectile identity rejected"); source.Projectile.identity--;
                var token = typeof(GeneratedProjectile).GetField("_vfxSourceToken", BindingFlags.Instance | BindingFlags.NonPublic)!;
                long generation = (long)token.GetValue(source)!; token.SetValue(source, generation + 1);
                Rejected("wrong source generation rejected"); token.SetValue(source, generation);
                string world = data.RecipeMeta.WorldId; data.RecipeMeta.WorldId = "foreign_world";
                Rejected("noncurrent world rejected"); data.RecipeMeta.WorldId = world;
                var slots = data.VfxManifest.Slots; data.VfxManifest.Slots = slots.Where(s => s.Event != "on_release").ToArray();
                Rejected("missing exact VFX event slot rejected"); data.VfxManifest.Slots = slots;
                var entity = data.RuntimeProgram.TryGetEntity("actor")!;
                entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
                Rejected("legacy charge producer cannot enter new owner-release relay"); entity.Controller.Code = RuntimeControllerCode.None;
                var charge = typeof(RuntimeEntitySpec).GetField("_charge", BindingFlags.Instance | BindingFlags.NonPublic)!;
                var component = charge.GetValue(entity); charge.SetValue(entity, null);
                Rejected("non-charge producer rejected"); charge.SetValue(entity, component);
                // Corrupt only a captured claim's pose through the existing codec:
                // generic envelope remains valid, exact ordinary-source bounds do not.
                var payload = typeof(GeneratedProjectile).GetMethod("ReadVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!
                    .Invoke(null, new object[] { new BinaryReader(new MemoryStream(claim[1..])) })!;
                var snapshotProperty = payload.GetType().GetProperty("Snapshot")!;
                var snapshot = (InfiniVfxProjectileSnapshot)snapshotProperty.GetValue(payload)!;
                var wrongSnapshot = snapshot with { Pose = snapshot.Pose with { Scale = .05f } };
                Equal(true, wrongSnapshot.IsValid, "negative snapshot stays inside generic wire envelope");
                snapshotProperty.SetValue(payload, wrongSnapshot);
                using (var malformed = new MemoryStream()) {
                    var writer = new BinaryWriter(malformed); writer.Write(claim[0]);
                    typeof(GeneratedProjectile).GetMethod("WriteVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!
                        .Invoke(null, new object[] { writer, payload });
                    peers.Receive(malformed.ToArray(), 0);
                }
                Equal(0, peers.Sent.Count, "snapshot outside exact producer pose bounds rejected");
                peers.Receive(claim, 0); Equal(1, peers.Sent.Count, "refused claims do not consume valid authenticated owner occurrence");
                peers.Receive(claim, 0); Equal(1, peers.Sent.Count, "authenticated owner replay rejected");
                Equal(0, PendingActions(), "all fence paths remain presentation-only");
            } finally { RuntimeDelayedActionScheduler.Clear(); }
        });
    }

    private static void ComposableMotionLegacyChargeVfxKeepsServerRoute()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ReviewProjectileData("on_release", "channel_complete"); peers.Register(data);
            peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0].channel = false;
            var owner = peers.Host(data); var extra = ReviewExtra(owner); owner.AI();
            Equal(0, peers.Sent.Count, "legacy charge emits no owner release/completion relay claims");
            peers.Mode(NetmodeID.Server, 255); peers.Sent.Clear();
            var server = peers.Host(data, extra: extra); server.AI();
            Equal(2, peers.Sent.Count, "legacy server still produces release and completion");
            var relays = peers.Sent.ToArray(); server.AI(); Equal(2, peers.Sent.Count, "legacy server release remains latched");
            peers.Mode(NetmodeID.MultiplayerClient, 2); MaterialClock(120); peers.System.PostUpdateEverything();
            foreach (var relay in relays) peers.Receive(relay);
            Equal(2, OwnedMaterialQueue().Count, "legacy remote receives server-origin detached events");
            foreach (var relay in relays) peers.Receive(relay);
            Equal(2, OwnedMaterialQueue().Count, "legacy server stream replay remains suppressed");
        });
    }
}
