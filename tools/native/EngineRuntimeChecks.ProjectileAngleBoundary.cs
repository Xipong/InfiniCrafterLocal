using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void ProjectileAngleBoundaryPreservesNativeStorage()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var stationary = MotionDefinition("{}");
            var entity = stationary.RuntimeProgram.TryGetEntity(stationary.RuntimeProgram.PrimaryEntityId)!;
            var (host, body) = MotionActor(stationary, owner, Vector2.Zero);
            Equal(MathHelper.PiOver2, body.rotation, "fresh native Y-axis storage before first AI");
            Equal(0f, SpritePresentation.ProjectileBodyAngle(entity, body.rotation), "fresh stationary semantic forward is world zero, not aim tracking");
            host.AI();
            Equal(MathHelper.PiOver2, body.rotation, "stationary AI retains native encoding");
            foreach (float axis in new[] { -90f, 0f, 37f, 180f })
            foreach (SpriteEffects flip in new[] { SpriteEffects.None, SpriteEffects.FlipHorizontally, SpriteEffects.FlipVertically }) {
                var selected = new SpritePresentationSelection("unused", 40, axis);
                float draw = selected.ProjectileRotation(entity, body.rotation, flip);
                float a = axis * MathHelper.Pi / 180;
                Vector2 local = a.ToRotationVector2();
                if ((flip & SpriteEffects.FlipHorizontally) != 0) local.X = -local.X;
                if ((flip & SpriteEffects.FlipVertically) != 0) local.Y = -local.Y;
                AssertVfxNear(Vector2.UnitX, local.RotatedBy(draw), "declared PNG axis and flip converted once");
            }
            Vector2 velocity = new Vector2(-3, 4);
            body.velocity = velocity; host.AI();
            Equal(velocity.ToRotation() + MathHelper.PiOver2, body.rotation, "ordinary velocity keeps existing native storage");
            float previous = body.rotation; body.velocity = Vector2.Zero; host.AI();
            Equal(previous, body.rotation, "stopped body retains last orientation; not forced to world zero");
            body.rotation = -.731f;
            host.Configure(stationary, entity, 0, 8, Vector2.UnitY, preserveSyncedState: true);
            Equal(-.731f, body.rotation, "hydration preserves received native angle exactly");
            foreach (string spec in new[] {
                "{\"rotation\":{\"mode\":\"spin\",\"offsetRadians\":0.3,\"radiansPerUpdate\":0.25}}",
                "{\"rotation\":{\"mode\":\"velocity\",\"offsetRadians\":0.3}}",
                "{\"aim\":{\"source\":\"initial\",\"turnOwner\":false},\"rotation\":{\"mode\":\"axis\",\"offsetRadians\":0.3}}" }) {
                var data = MotionDefinition(spec); var e = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                var actor = MotionActor(data, owner, velocity); actor.Host.AI();
                float expected = e.Rotation!.Mode == "spin" ? .55f : e.Rotation.Mode == "axis" ? .3f : velocity.ToRotation() + .3f;
                Equal(true, Math.Abs(expected - actor.Body.rotation) < .0001f, "explicit rotation keeps world-angle native storage");
                Equal(actor.Body.rotation, SpritePresentation.ProjectileBodyAngle(e, actor.Body.rotation), "explicit authored angle is not quarter-turned");
            }
        });
    }
    private static void ProjectileAngleFreshRemoteHydration()
    {
        using var peers = new ReviewPeers();
        var data = VisualScaleHydrationData("{}");
        var source = peers.Host(data); source.Projectile.velocity = Vector2.Zero; source.AI();
        var entity = data.RuntimeProgram.TryGetEntity("actor")!;
        byte[] payload = ReviewExtra(source);
        peers.Mode(Terraria.ID.NetmodeID.MultiplayerClient, 1); peers.Register(data);
        var remote = peers.Host(data, extra: payload); remote.Projectile.velocity = Vector2.Zero;
        Equal(true, ProjectileConfigured(remote), "fresh actual ExtraAI peer hydrates");
        Equal(source.Projectile.rotation, remote.Projectile.rotation,
            "first actual ExtraAI hydration initializes the declared stationary body pose");
        remote.AI();
        Equal(source.Projectile.rotation, remote.Projectile.rotation, "stationary observer does not require guessed velocity to correct angle");
        remote.Projectile.rotation = -.731f;
        remote.ReceiveExtraAI(new System.IO.BinaryReader(new System.IO.MemoryStream(payload)));
        Equal(-.731f, remote.Projectile.rotation, "same physical source packet cannot reset evolved local angle");
        ((System.Collections.IDictionary)peers.Registry.GetType().GetField("_byId", TestInstance)!.GetValue(peers.Registry)!).Remove(data.Id);
        var late = peers.Host(data, slot: 4, extra: payload); late.Projectile.velocity = Vector2.Zero;
        Equal(false, ProjectileConfigured(late), "missing definition stays nonpresentable");
        late.ReceiveExtraAI(new System.IO.BinaryReader(new System.IO.MemoryStream(payload)));
        Equal(false, ProjectileConfigured(late), "repeated pending packet does not fabricate definition");
        peers.Register(data);
        typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetMethod("TryHydrate", TestInstance)!.Invoke(late, null);
        Equal(true, ProjectileConfigured(late), "late exact definition hydrates through actual owner");
        Equal(MathHelper.PiOver2, late.Projectile.rotation, "late pose initialized before first AI or draw");
        var replacement = peers.Host(data, slot: 6); replacement.Projectile.velocity = Vector2.Zero;
        remote.ReceiveExtraAI(new System.IO.BinaryReader(new System.IO.MemoryStream(ReviewExtra(replacement))));
        Equal(MathHelper.PiOver2, remote.Projectile.rotation, "new source token same item/entity gets its own initial pose");

    }

}
