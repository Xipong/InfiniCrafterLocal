using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
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
}
