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

    private static bool ProjectileConfigured(GeneratedProjectile projectile)
        => (bool)typeof(GeneratedProjectile).GetField("_configured", BindingFlags.Instance | BindingFlags.NonPublic)!
            .GetValue(projectile)!;
}
