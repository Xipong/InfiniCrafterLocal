using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private const string FiniteVisualScaleCurve = """
        {"visualScaleCurve":{"startScale":1,"endScale":4,"curve":"linear","startDelayTicks":0,"durationTicks":4,
          "window":{"phase":"always","clock":"active","startDelayTicks":0,"durationTicks":4}}}
        """;

    private static GeneratedItemData VisualScaleHydrationData(string components, int extraUpdates = 0)
    {
        var basis = ReviewProjectileData("on_spawn"); basis.VfxManifest = VfxManifestSpec.Empty();
        var root = JsonNode.Parse(basis.ToJson())!.AsObject();
        var actor = root["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "actor")!;
        foreach (var pair in JsonNode.Parse(components)!.AsObject()) actor[pair.Key] = pair.Value?.DeepClone();
        actor["collision"]!["extraUpdates"] = extraUpdates;
        return ParseMaterialElement(root);
    }

    private static int VisualScaleAge(GeneratedProjectile host)
        => (int)typeof(GeneratedProjectile).GetField("_age", TestInstance)!.GetValue(host)!;

    private static void VisualScaleWindowLocalRehydration()
    {
        foreach (int extra in new[] { 0, 2 }) {
            using var peers = new ReviewPeers();
            var data = VisualScaleHydrationData(FiniteVisualScaleCurve, extra);
            var source = peers.Host(data);
            for (int i = 0; i < 6 * (extra + 1); i++) source.AI();
            Equal(4f, source.Projectile.scale, "real AI reaches and holds the completed visual window");
            source.Configure(data, data.RuntimeProgram.TryGetEntity("actor")!, 0, 0, Vector2.UnitX, preserveSyncedState: true);
            Equal(4f, source.Projectile.scale, "same-source metadata reconfiguration retains the terminal scale");
            Equal(6 * (extra + 1), VisualScaleAge(source), "metadata does not restart the active clock");
        }
    }

    private static void VisualScaleNativeSnapshotFreshAndLatePeers()
    {
        foreach (int extra in new[] { 0, 2 })
        foreach (string components in new[] { FiniteVisualScaleCurve,
            """{"visualScaleRate":{"deltaPerUpdate":0.125,"maxScale":20,"window":{"phase":"always","clock":"active","startDelayTicks":0,"durationTicks":4}}}""",
            """{"visualScaleRate":{"deltaPerUpdate":0.125,"maxScale":20,"window":{"phase":"always","clock":"active","startDelayTicks":0,"durationTicks":2}},"visualScaleCurve":{"startScale":1,"endScale":4,"curve":"linear","startDelayTicks":0,"durationTicks":4,"window":{"phase":"always","clock":"active","startDelayTicks":2,"durationTicks":2}}}""",
            """{"visualScaleCurve":{"startScale":1,"endScale":4,"curve":"linear","startDelayTicks":0,"durationTicks":4,"window":{"phase":"outbound"}},"returnTrigger":{"onOwnerRelease":false,"onTileCollision":true,"disableTileCollisionOnReturn":true}}""" }) {
            using var peers = new ReviewPeers();
            var data = VisualScaleHydrationData(components, extra);
            var source = peers.Host(data);
            for (int i = 0; i < 2 * (extra + 1); i++) source.AI();
            if (data.RuntimeProgram.TryGetEntity("actor")!.ReturnTrigger is not null)
                Equal(false, source.OnTileCollide(Vector2.UnitX), "actual tile transition closes the outbound curve");
            for (int i = 0; i < 4 * (extra + 1); i++) source.AI();
            float expected = source.Projectile.scale;
            Equal(true, expected > 1f, "real AI produced a distinct retained scale");
            byte[] payload = ReviewExtra(source);
            peers.Mode(NetmodeID.MultiplayerClient, 1); peers.Register(data);
            var fresh = peers.Host(data, extra: payload);
            Equal(true, ProjectileConfigured(fresh), "fresh observer hydrates the exact source");
            Equal(expected, fresh.Projectile.scale, "native ExtraAI transfers scale absent from native SyncProjectile");
            fresh.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
            Equal(expected, fresh.Projectile.scale, "repeating the same snapshot never compounds scale");
            fresh.AI();
            Equal(expected, fresh.Projectile.scale, "closed window stays closed on the first observer update");

            ((System.Collections.IDictionary)peers.Registry.GetType().GetField("_byId", TestInstance)!
                .GetValue(peers.Registry)!).Remove(data.Id);
            var pending = peers.Host(data, slot: 4, extra: payload);
            Equal(false, ProjectileConfigured(pending), "missing exact definition stays pending");
            byte[] relayedPending = ReviewExtra(pending);
            peers.Register(data); pending.AI();
            Equal(expected, pending.Projectile.scale, "late definition retains the received completed scale");
            var relayed = peers.Host(data, slot: 5, extra: relayedPending);
            Equal(true, ProjectileConfigured(relayed), "pending source can relay its validated snapshot");
            Equal(expected, relayed.Projectile.scale, "pending relay does not replace scale with proxy defaults");
        }

        // Native tile collision follows AI, so entering return does not advance
        // active age. Reversed delivery must preserve that transition while the
        // exact definition is still missing, not reopen the outbound curve.
        using var phasePeers = new ReviewPeers();
        var phaseData = VisualScaleHydrationData("""
            {"visualScaleCurve":{"startScale":1,"endScale":4,"curve":"linear","startDelayTicks":0,"durationTicks":4,"window":{"phase":"outbound"}},
             "returnTrigger":{"onOwnerRelease":false,"onTileCollision":true,"disableTileCollisionOnReturn":true}}
            """);
        var phaseSource = phasePeers.Host(phaseData); phaseSource.AI(); phaseSource.AI();
        byte[] outbound = ReviewExtra(phaseSource);
        Equal(false, phaseSource.OnTileCollide(Vector2.UnitX), "tile callback latches return without advancing AI age");
        byte[] returning = ReviewExtra(phaseSource); float phaseScale = phaseSource.Projectile.scale;
        phasePeers.Mode(NetmodeID.MultiplayerClient, 1);
        var pendingPhase = phasePeers.Host(phaseData, extra: returning);
        pendingPhase.ReceiveExtraAI(new BinaryReader(new MemoryStream(outbound)));
        phasePeers.Register(phaseData); pendingPhase.AI();
        Equal(phaseScale, pendingPhase.Projectile.scale, "same-age earlier phase cannot reopen a pending scale window");
        Equal(false, pendingPhase.Projectile.tileCollide, "pending same-age return retains authored tile policy");
    }

    private static void VisualScaleSnapshotAuthorityAndReplay()
    {
        foreach (float delta in new[] { .125f, -.125f }) {
            using var peers = new ReviewPeers();
            var data = VisualScaleHydrationData("{\"visualScaleRate\":{\"deltaPerUpdate\":"
                + delta.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"maxScale\":20}}");
            peers.Register(data); peers.Mode(NetmodeID.MultiplayerClient, 0);
            var owner = peers.Host(data);
            for (int i = 0; i < 3; i++) owner.AI();
            byte[] old = ReviewExtra(owner);
            for (int i = 0; i < 2; i++) owner.AI();
            float latest = owner.Projectile.scale;
            byte[] current = ReviewExtra(owner);
            owner.ReceiveExtraAI(new BinaryReader(new MemoryStream(old)));
            Equal(latest, owner.Projectile.scale, "owner ignores a relay of its older scale");
            Equal(5, VisualScaleAge(owner), "owner retains its local active clock");

            peers.Mode(NetmodeID.Server, 255);
            var remote = peers.Host(data, extra: old);
            Equal(1f + 3 * delta, remote.Projectile.scale, "fresh server receives accumulated scale");
            remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(current)));
            Equal(latest, remote.Projectile.scale, "newer observation advances peer scale");
            remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(old)));
            Equal(latest, remote.Projectile.scale, "older observation cannot rewind growing or shrinking scale");
            Equal(5, VisualScaleAge(remote), "older observation cannot rewind active clock");
            remote.AI();
            Equal(latest + delta, remote.Projectile.scale, "next AI applies the rate exactly once");
            remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(current)));
            Equal(latest + delta, remote.Projectile.scale, "repeat sync does not replay past rate steps");

            peers.Mode(NetmodeID.MultiplayerClient, 0);
            owner.ReceiveExtraAI(new BinaryReader(new MemoryStream(ReviewExtra(remote))));
            Equal(latest, owner.Projectile.scale, "server prediction cannot overwrite authoritative owner scale");
            owner.AI();
            Equal(latest + delta, owner.Projectile.scale, "owner resumes with one rate step");
            var replacement = peers.Host(data, slot: 4, identity: 72);
            peers.Mode(NetmodeID.Server, 255);
            remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(ReviewExtra(replacement))));
            Equal(1f, remote.Projectile.scale, "new physical generation owns its independent initial scale");
            Equal(0, VisualScaleAge(remote), "new physical generation owns its independent clock");

            ((System.Collections.IDictionary)peers.Registry.GetType().GetField("_byId", TestInstance)!
                .GetValue(peers.Registry)!).Remove(data.Id);
            peers.Mode(NetmodeID.MultiplayerClient, 1);
            var pending = peers.Host(data, extra: current);
            pending.ReceiveExtraAI(new BinaryReader(new MemoryStream(old)));
            peers.Register(data); pending.AI();
            Equal(latest + delta, pending.Projectile.scale, "late metadata cannot admit an older pending scale");
            Equal(6, VisualScaleAge(pending), "pending observations preserve newest scale and clock together");
        }
    }

    private static void VisualScaleSnapshotStrictOwnershipAndBounds()
    {
        using var peers = new ReviewPeers();
        var data = VisualScaleHydrationData(FiniteVisualScaleCurve); peers.Register(data);
        byte[] current = ReviewExtra(peers.Host(data));
        Equal((byte)7, current[0], "only a stateful scale owner chooses the new ExtraAI variant");
        byte[] WithScale(float scale)
        {
            var wire = (byte[])current.Clone(); BitConverter.GetBytes(scale).CopyTo(wire, wire.Length - sizeof(float)); return wire;
        }
        void Refuses(byte[] bytes, string label)
        {
            var peer = peers.Host(data, extra: bytes); peer.AI();
            Equal(false, ProjectileConfigured(peer), label + " rejects hydration");
            Equal<bool?>(false, peer.CanDamage(), label + " remains harmless");
        }
        peers.Mode(NetmodeID.MultiplayerClient, 1);
        foreach (float invalid in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity, .009f, 128.01f })
            Refuses(WithScale(invalid), "non-finite/out-of-envelope scale " + invalid);
        Refuses(current[..^1], "truncated scale state");
        var missing = current[..^sizeof(float)]; missing[0] = 6;
        Refuses(missing, "older packet missing required state");
        foreach (float boundary in new[] { .01f, 128f }) {
            var peer = peers.Host(data, extra: WithScale(boundary));
            Equal(true, ProjectileConfigured(peer), "finite scale envelope boundary admits");
            Equal(boundary, peer.Projectile.scale, "admitted scale is not clamped or reconstructed");
        }

        var ordinary = VisualScaleHydrationData("{}"); peers.Register(ordinary);
        Equal((byte)4, ReviewExtra(peers.Host(ordinary))[0], "unaffected native wire remains v4");
        Refuses(current, "unowned scale state on ordinary entity");
        var stateless = VisualScaleHydrationData("""{"visualScaleCurve":{"startScale":1,"endScale":4,"curve":"linear","startDelayTicks":0,"durationTicks":4}}""");
        peers.Register(stateless);
        Equal((byte)4, ReviewExtra(peers.Host(stateless))[0], "unwindowed curve retains age-derived v4 hydration");
        Refuses(current, "unowned state on an unwindowed scale curve");
        var composable = VisualScaleHydrationData("{\"opacity\":{\"alpha\":137}}"); peers.Register(composable);
        Equal((byte)6, ReviewExtra(peers.Host(composable))[0], "unaffected composable wire remains v6");
        Refuses(current, "unowned scale state on unrelated motion entity");
        ((System.Collections.IDictionary)peers.Registry.GetType().GetField("_byId", TestInstance)!
            .GetValue(peers.Registry)!).Remove(data.Id);
        var pending = peers.Host(data, extra: current);
        Equal(false, ProjectileConfigured(pending), "unknown definition defers ownership validation");
        peers.Register(ordinary); pending.AI();
        Equal(false, ProjectileConfigured(pending), "late exact definition must also own stateful scale");
        Equal<bool?>(false, pending.CanDamage(), "late unowned state remains harmless");
    }

    private static void LateDefinitionRetainsLatestNativeProjectileVelocity()
    {
        using var peers = new ReviewPeers();
        var data = ReviewProjectileData("on_spawn");
        data.VfxManifest = VfxManifestSpec.Empty();
        var original = peers.Host(data);
        byte[] payload = ReviewExtra(original);
        peers.Mode(NetmodeID.MultiplayerClient, 1);
        var remote = peers.Host(data, extra: payload);
        var projectile = remote.Projectile;
        var target = new NPC { active = true };
        Equal(false, ProjectileConfigured(remote), "missing definition stays pending");
        Equal(Vector2.UnitX, projectile.velocity, "first native velocity retained while pending");
        Equal(false, remote.ShouldUpdatePosition(), "pending projectile cannot advance position");
        Equal(false, projectile.friendly, "pending projectile cannot deal contact damage");
        Equal<bool?>(false, remote.CanHitNPC(target), "pending projectile cannot hit NPCs");
        Equal<bool?>(false, remote.Colliding(projectile.Hitbox, target.Hitbox), "pending collision disabled");

        // Terraria's native SyncProjectile fields arrive before ModProjectile ExtraAI.
        // A second packet may carry a changed velocity before the definition is ready.
        Vector2 latest = new(12f, -3f);
        projectile.velocity = latest;
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
        remote.AI();
        Equal(latest, projectile.velocity, "repeated pending packet retains newest native velocity");
        Equal(false, remote.ShouldUpdatePosition(), "repeated pending packet remains stationary");
        peers.Register(data);
        remote.AI();
        Equal(true, ProjectileConfigured(remote), "late definition configures exact actor");
        Equal(latest, projectile.velocity, "late hydration resumes exact latest native velocity");
        Equal(true, remote.ShouldUpdatePosition(), "configured free projectile advances position");

        // Rehydration can begin on an already configured actor. Native tile
        // collision runs before ShouldUpdatePosition, so stale collision must stop too.
        Equal(true, projectile.tileCollide, "configured actor uses authored tile collision");
        ((System.Collections.IDictionary)peers.Registry.GetType().GetField("_byId",
            BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(peers.Registry)!).Remove(data.Id);
        projectile.velocity = latest;
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
        Equal(false, ProjectileConfigured(remote), "configured actor can wait for missing definition");
        Equal(false, projectile.tileCollide, "pending rehydration disables native tile collision");
        Equal(false, remote.ShouldUpdatePosition(), "pending rehydration disables position integration");
        Equal(latest, projectile.velocity, "pending rehydration retains newest native velocity");
        peers.Register(data);
        remote.AI();
        Equal(true, projectile.tileCollide, "successful rehydration restores authored tile collision");
        Equal(latest, projectile.velocity, "successful rehydration retains newest native velocity");

        // Existing definitions take the immediate path; an explicit zero is a valid snapshot.
        projectile.velocity = Vector2.Zero;
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
        remote.AI();
        Equal(Vector2.Zero, projectile.velocity, "zero native velocity is not replaced with authored launch");
        Equal(true, ProjectileConfigured(remote), "cached definition remains configured");

        // Invalid payloads retain their independent fail-closed path even with a cached definition.
        projectile.velocity = latest;
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(new byte[] { 255 })));
        remote.AI();
        Equal(false, ProjectileConfigured(remote), "malformed payload cannot hydrate");
        Equal(Vector2.Zero, projectile.velocity, "malformed payload still stops velocity");
        Equal(false, remote.ShouldUpdatePosition(), "rejected projectile cannot advance position");
        Equal(false, projectile.friendly, "rejected projectile cannot deal contact damage");
    }

    private static void RepeatedProjectileHydrationRetainsSpentPenetration()
    {
        using var peers = new ReviewPeers();
        var data = ReviewProjectileData("on_spawn");
        data.VfxManifest = VfxManifestSpec.Empty();
        var entity = data.RuntimeProgram.TryGetEntity("actor")!;
        // Same admitted finite-pierce lane as the captured Jester musket (3).
        // The test owns only metadata hydration, not a simulated NPC hit count.
        entity.Collision.Pierce = 3;
        peers.Register(data);
        var original = peers.Host(data);
        byte[] payload = ReviewExtra(original);
        peers.Mode(NetmodeID.MultiplayerClient, 1);
        var remote = peers.Host(data, extra: payload);
        var projectile = remote.Projectile;
        Equal(true, ProjectileConfigured(remote), "initial cached definition hydrates");
        Equal(3, projectile.penetrate, "first hydration initializes authored finite penetration");
        Equal(3, projectile.maxPenetrate, "native immunity keeps authored initial penetration");

        // Native damage owns the remaining counter. ExtraAI carries runtime
        // metadata, not a grant of fresh hits to this already configured source.
        projectile.penetrate = 2;
        projectile.localNPCImmunity[5] = 27;
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
        Equal(2, projectile.penetrate, "same-source ExtraAI cannot refill spent penetration");
        Equal(3, projectile.maxPenetrate, "rehydration retains native initial-penetration semantics");
        Equal(27, projectile.localNPCImmunity[5], "rehydration never clears native local immunity");

        ((System.Collections.IDictionary)peers.Registry.GetType().GetField("_byId",
            BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(peers.Registry)!).Remove(data.Id);
        projectile.penetrate = 1;
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(payload)));
        Equal(false, ProjectileConfigured(remote), "same source can wait for an evicted definition");
        peers.Register(data);
        remote.AI();
        Equal(1, projectile.penetrate, "late rehydration cannot refill the same live source either");
        Equal(27, projectile.localNPCImmunity[5], "late rehydration retains local NPC immunity");

        var replacement = peers.Host(data, slot: 4, identity: 72);
        remote.ReceiveExtraAI(new BinaryReader(new MemoryStream(ReviewExtra(replacement))));
        Equal(3, projectile.penetrate, "a genuinely new source initializes its own authored allowance");
        projectile.penetrate = 1;
        remote.Configure(data, entity, 0, 0, Vector2.UnitX);
        Equal(3, projectile.penetrate, "explicit fresh local Configure initializes its own allowance");
    }

    private static bool ProjectileConfigured(GeneratedProjectile projectile)
        => (bool)typeof(GeneratedProjectile).GetField("_configured", BindingFlags.Instance | BindingFlags.NonPublic)!
            .GetValue(projectile)!;
    private static void FirstProjectileHydrationPreservesNativeTopLeft()
    {
        foreach (bool composable in new[] { false, true }) {
        using var peers = new ReviewPeers();
        var root = JsonNode.Parse(ReviewProjectileData("on_spawn").ToJson())!.AsObject();
        root.Remove("runtimeContract");
        var actor = root["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "actor")!;
        if (composable) actor["opacity"] = JsonNode.Parse("{\"alpha\":137}");
        actor["hitbox"]!["widthPx"] = 40; actor["hitbox"]!["heightPx"] = 18;
        var data = ParseMaterialElement(root); peers.Register(data);
        peers.Mode(NetmodeID.MultiplayerClient, 0);
        var owner = peers.Host(data);
        owner.Projectile.Center = new Vector2(100.25f, 150.75f);
        byte[] extra = ReviewExtra(owner);
        Equal((byte)(composable ? 6 : 4), extra[0], "both retained and composable packets use native top-left");
        Vector2 nativePosition = owner.Projectile.position;
        peers.Mode(NetmodeID.Server, 255);
        var body = Terraria.Main.projectile[11] = new Projectile {
            active = true, whoAmI = 11, owner = 0, identity = owner.Projectile.identity,
            damage = owner.Projectile.damage, knockBack = owner.Projectile.knockBack,
        };
        var receiver = Attach(body);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(body, receiver);
        receiver.SetDefaults(); // actual fresh proxy dimensions before native Msg27 body fields
        Equal(12, body.width, "fresh proxy default width is distinct from admitted authored width");
        body.position = nativePosition; // exact native Msg27 contract: top-left, not center
        body.velocity = owner.Projectile.velocity;
        receiver.ReceiveExtraAI(new BinaryReader(new MemoryStream(extra)));
        Equal(true, ProjectileConfigured(receiver), "fresh native snapshot hydrates the exact definition");
        Equal(40, body.width, "authored hitbox width hydrates");
        Equal(18, body.height, "authored hitbox height hydrates");
        AssertVfxNear(nativePosition, body.position, "metadata must not reinterpret native top-left using old default dimensions");
        AssertVfxNear(owner.Projectile.Center, body.Center, "first hydrated center matches actual owner fractional center");
        }
    }
}
