using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Test-only patch intentionally compiles on the frozen pre-component product.
    // No new DTO names or private implementation entrypoints in these observers.
    private static GeneratedItemData MotionDefinition(string components, Action<JsonObject>? edit = null)
    {
        var root = JsonNode.Parse(FrontHandWire())!.AsObject();
        root.Remove("runtimeContract");
        var body = FrontHandEntity(root);
        body["movement"] = JsonNode.Parse("{\"name\":\"move_straight\",\"code\":0,\"params\":{}}");
        body["visual"]!["assetMode"] = "no_asset";
        foreach (var pair in JsonNode.Parse(components)!.AsObject()) body[pair.Key] = pair.Value?.DeepClone();
        // These synthetic charge observers explicitly choose native channel input.
        if (body.ContainsKey("charge")) root["runtimeProgram"]!["itemUse"]!["channel"] = true;
        edit?.Invoke(body);
        var data = GeneratedItemData.FromJson(root.ToJsonString());
        if (data is null) throw new InvalidOperationException("independent motion must admit: " + ContractJsonDiagnostics.LastError);
        data.VfxManifest = VfxManifestSpec.Empty();
        return data;
    }
    private static (GeneratedProjectile Host, Projectile Body) MotionActor(GeneratedItemData data, Player owner, Vector2 velocity)
    {
        var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
        owner.active = true; owner.dead = false; owner.whoAmI = 0;
        if (owner.direction == 0) owner.direction = 1;
        Terraria.Main.player[0] = owner; Terraria.Main.myPlayer = 0;
        Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.dedServ = true;
        var body = new Projectile { active = true, owner = owner.whoAmI, whoAmI = 7, damage = 40, knockBack = 2, Center = owner.MountedCenter + new Vector2(100, 0), velocity = velocity };
        var host = Attach(body);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(body, host);
        Terraria.Main.projectile[7] = body;
        host.Configure(data, entity, 0, 8, Vector2.UnitX);
        return (host, body);
    }
    private static void ComposableMotionForcesAndIndependentPresentation()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("""
              {"verticalAcceleration":{"accelerationYPerUpdate":2},"velocityRetention":{"multiplierPerUpdate":0.5},
               "oscillation":{"law":"angular_sine","frequencyRadiansPerUpdate":0,"phaseRadians":0,"amplitude":1},
               "opacity":{"alpha":137},"rotation":{"mode":"spin","offsetRadians":0,"radiansPerUpdate":0.25}}
              """);
            var (host, body) = MotionActor(data, owner, new Vector2(8, 0)); host.AI();
            AssertVfxNear(new Vector2(4, 1), body.velocity, "gravity then retention, no hidden NPC steering");
            Equal(137, body.alpha, "opacity is independent of wobble");
            Equal(true, Math.Abs(body.rotation - .25f) < .0001, "selected rotation is not overwritten by velocity alignment");
            Equal(true, host.ShouldUpdatePosition(), "one native integration remains for free body");
            Equal(true, body.active, "independent force law does not choose lifetime");
            var zero = MotionDefinition("{\"velocityRetention\":{\"multiplierPerUpdate\":0}}");
            var stopped = MotionActor(zero, owner, new Vector2(8, 3)); stopped.Host.AI();
            Equal(Vector2.Zero, stopped.Body.velocity, "new explicit retention zero is not legacy identity");
        });
    }
    private static void ComposableMotionAttachmentPoseAndReach()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState(); owner.direction = 1; owner.active = true;
            owner.itemAnimation = owner.itemAnimationMax = 60;
            var data = MotionDefinition("""
             {"aim":{"source":"initial","turnOwner":false},
              "attachment":{"anchor":"front_hand","axisOffsetPx":5,"normalOffsetPx":3},
              "armPose":{"durationTicks":12,"startStretch":"quarter","peakStretch":"quarter","endStretch":"quarter","peakProgress":0.25},
              "reach":{"durationTicks":12,"startOffsetPx":0,"peakOffsetPx":24,"endOffsetPx":0,"peakProgress":0.25}}
             """);
            var (host, body) = MotionActor(data, owner, Vector2.Zero);
            for (int i = 0; i < 3; i++) host.AI();
            var hand = FrontHandExpected(owner, Vector2.UnitX, Player.CompositeArmStretchAmount.Quarter);
            AssertVfxNear(hand + new Vector2(29, 3), body.Center, "physical body reads constant pose plus asymmetric reach");
            Equal(false, host.ShouldUpdatePosition(), "absolute attachment has no second integration");
            for (int i = 0; i < 13; i++) host.AI();
            Equal(true, body.active, "reach cycle does not secretly kill");
            Equal(Player.CompositeArmStretchAmount.Quarter, owner.compositeFrontArm.stretch, "constant pose remains constant");
        });
    }
    private static void ComposableMotionTimedReturnNoHiddenController()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState(); owner.channel = false;
            var data = MotionDefinition("""
             {"returnTrigger":{"afterTicks":2,"onOwnerRelease":false,"onTileCollision":false,"disableTileCollisionOnReturn":false},
              "seek":[{"window":{"phase":"returning","clock":"since_return","startDelayTicks":0,"durationTicks":60},
                "target":"owner_center","maxSpeed":12,"velocityLerpPerUpdate":1,"limitSpeedToDistance":false}]}
             """, e => e["collision"]!["tileCollide"] = true);
            var (host, body) = MotionActor(data, owner, new Vector2(8, 0));
            host.AI(); Equal(new Vector2(8, 0), body.velocity, "no forced release-return on click-to-throw");
            host.AI();
            AssertVfxNear((owner.Center - body.Center).SafeNormalize(Vector2.UnitX) * 12, body.velocity, "independent return seek");
            Equal(true, body.tileCollide, "return does not infer tile policy");
            Equal(true, host.ShouldUpdatePosition(), "return velocity integrates natively once");
            Equal(true, Math.Abs(body.rotation - body.velocity.ToRotation() - MathHelper.PiOver2) < .001, "return does not infer spin");
        });
    }
    private static void ComposableMotionFreeBeamAndLashGeometry()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState(); owner.channel = false;
            var beam = MotionDefinition("""
             {"aim":{"source":"initial","turnOwner":false},"beamGeometry":{"lengthPx":120,"widthPx":8,"raycastTiles":false},
              "beamRamp":{"warmupTicks":4,"initialWidthMultiplier":0.5,"initialDamageMultiplier":0.25,"damageStartProgress":0.5}}
             """);
            var (host, body) = MotionActor(beam, owner, new Vector2(2, 0));
            host.AI(); Equal(false, host.CanDamage(), "beam ramp pre-threshold damage gate");
            host.AI(); Equal<bool?>(null, host.CanDamage(), "beam ramp reaches threshold without channel");
            Equal(true, host.ShouldUpdatePosition(), "line geometry does not attach moving body");
            object?[] args = { null, null, null };
            typeof(GeneratedProjectile).GetMethod("GetChannelBeamGeometry", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(host, args);
            AssertVfxNear(body.Center, (Vector2)args[0]!, "new beam line starts at free body");
            AssertVfxNear(body.Center + new Vector2(120, 0), (Vector2)args[1]!, "new beam line uses explicit aim");
            Equal(true, body.active, "beam geometry does not infer owner cancellation");
            var lash = MotionDefinition("""
             {"aim":{"source":"initial","turnOwner":false},
              "lashGeometry":{"clock":"active","durationTicks":12,"anchor":"owner_center","reachPx":100,"segments":8,
                "sweepStartRadians":0,"sweepEndRadians":0,"bendRatio":0,"useOwnerGravity":false,"useOwnerWhipRangeMultiplier":false}}
             """);
            var l = MotionActor(lash, owner, Vector2.Zero); for(int i=0;i<6;i++) l.Host.AI();
            AssertVfxNear(owner.Center + new Vector2(100, 0), l.Body.Center, "independent lash shares physical tip geometry");
            Equal(false, l.Host.IsGeneratedWhipTagSource, "lash geometry does not imply whip tag");
            Equal(false, l.Host.ShouldUpdatePosition(), "lash tip is sole position owner");
        });
    }
    private static void ComposableMotionPhaseOnlyAttachmentAndReleasedModifiers()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState(); owner.channel = true;
            var data = MotionDefinition("""
             {"aim":{"source":"initial","turnOwner":false},
              "attachment":{"window":{"phase":"charging"},"anchor":"owner_center","axisOffsetPx":4,"normalOffsetPx":0},
              "charge":{"durationTicks":2,"autoReleaseAfterActiveTicks":2},
              "chargeRelease":{"damageMultiplier":1,"knockbackMultiplier":1,"speedMultiplier":1,"launchSpeed":12,"pauseLifetimeWhileCharging":false},
              "turnModifier":{"window":{"phase":"released"},"turnRadiansPerUpdate":0.25,"startDelayTicks":0,"durationTicks":60},
              "speedModifier":{"window":{"phase":"released"},"speedMultiplierPerUpdate":0.8,"maxSpeed":80,"startDelayTicks":0,"durationTicks":60}}
             """, e => e["collision"]!["extraUpdates"] = 2);
            var (host, body) = MotionActor(data, owner, new Vector2(8, 0));
            for(int i=0;i<5;i++) host.AI();
            AssertVfxNear(owner.Center + new Vector2(4,0), body.Center, "phase-only charging attachment");
            Equal(false, host.ShouldUpdatePosition(), "absolute owner only while charging");
            host.AI();
            Equal(true, host.ShouldUpdatePosition(), "released free flight resumes native integration");
            AssertVfxNear(new Vector2(MathF.Cos(.25f), MathF.Sin(.25f)) * (12f * .8f), body.velocity, "released PR148 turn then speed execute on transition subupdate");
            int lifetime = body.timeLeft;
            for(int i=0;i<20;i++) host.AI();
            Equal(lifetime, body.timeLeft, "components do not secretly keep lifetime alive");
        });
    }
    private static void ComposableMotionOrbitConsumesTilePolicyAndOwnerControl()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("""
             {"orbit":{"anchor":"owner_center","radiusPx":32,"radiansPerUpdate":0,"phaseRadians":0,"identityPhaseRadians":0}}
             """, e => e["collision"]!["tileCollide"] = true);
            var (host, body) = MotionActor(data, owner, Vector2.Zero); Vector2 before = body.Center;
            host.AI();
            Equal(before, body.Center, "orbit computes target velocity, not an absolute teleport");
            AssertVfxNear(owner.Center + new Vector2(32,0) - before, body.velocity, "orbit target velocity");
            Equal(true, host.ShouldUpdatePosition(), "actual native tile/integration consumer remains reachable");
            Equal(true, body.tileCollide, "independent orbit never forces tileoff");
            var control = MotionDefinition("""
             {"ownerControl":{"requireHeldItem":false,"requireChannel":false,"requireItemAnimation":false,
                "claimHeldProjectile":true,"animation":"keep_alive","lifetime":"keep_alive"}}
             """);
            var c = MotionActor(control, owner, new Vector2(3,0)); owner.itemAnimation = owner.itemTime = 0;
            c.Host.AI(); Equal(2, c.Body.timeLeft, "only explicit lifetime owner keeps alive");
            Equal(2, owner.itemAnimation, "explicit animation keep-alive");
            Equal(c.Body.whoAmI, owner.heldProj, "explicit primary held claim");
            Equal(new Vector2(3,0), c.Body.velocity, "owner control has no hidden translation");
        });
    }
    private static void ComposableMotionProximityWithoutSteering()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
            var data = MotionDefinition("""
             {"proximity":{"searchRangeTiles":10,"triggerRadiusPx":8,"requireLineOfSight":false,"action":"expire_then_kill"}}
             """);
            var (host, body) = MotionActor(data, owner, new Vector2(3,4));
            Terraria.Main.npc[0] = new NPC { whoAmI=0, active=true, life=100, lifeMax=100, damage=1,
                friendly=false, dontTakeDamage=false, width=10, height=10, Center=body.Center + new Vector2(20,0) };
            host.AI(); Equal(new Vector2(3,4), body.velocity, "proximity does not imply homing");
            Terraria.Main.npc[0].Center = body.Center + new Vector2(4,0);
            host.AI(); Equal(false, body.active, "proximity independently expires body");
            Equal(true, (bool)typeof(GeneratedProjectile).GetField("_expireEventRan", TestInstance)!.GetValue(host)!, "proximity latches expiry before kill");
        });
    }
    private static void ComposableMotionChargeReleaseAndHydration()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState(); owner.channel = true;
            var data = MotionDefinition("""
             {"aim":{"source":"initial","turnOwner":false},"charge":{"durationTicks":4,"autoReleaseAfterActiveTicks":4},
              "chargeRelease":{"damageMultiplier":2,"knockbackMultiplier":3,"speedMultiplier":2,"launchSpeed":6,"pauseLifetimeWhileCharging":true},
              "contactGate":{"window":{"phase":"charging","clock":"active","startDelayTicks":0,"durationTicks":60},"enabled":false},
              "velocityRetention":{"window":{"phase":"released","clock":"since_release","startDelayTicks":0,"durationTicks":60},"multiplierPerUpdate":0.5}}
             """);
            var (host, body) = MotionActor(data, owner, Vector2.Zero);
            Equal(false, host.CanDamage(), "explicit charging contact gate holds before first AI");
            for(int i=0;i<4;i++) host.AI();
            Equal(80, body.damage, "full charge scales live combat once");
            AssertVfxNear(new Vector2(6, 0), body.velocity, "release launch then independent released retention");
            using var stream = new MemoryStream(); using(var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) host.SendExtraAI(writer);
            Equal((byte)6, stream.ToArray()[0], "relative phase clocks use a new transport variant");
            var peer = MotionActor(data, owner, body.velocity);
            peer.Body.damage = body.damage; peer.Body.knockBack = body.knockBack;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
            stream.Position = 0;
            using(var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true)) peer.Host.ReceiveExtraAI(reader);
            var definition = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            peer.Host.Configure(data, definition, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            peer.Host.AI();
            Equal(80, peer.Body.damage, "actual ExtraAI late hydration never reapplies release combat");
            AssertVfxNear(new Vector2(3,0), peer.Body.velocity, "actual ExtraAI restores released relative clock");
            Equal<bool?>(null, peer.Host.CanDamage(), "late hydrated released contact is live");
            using(var truncated = new MemoryStream(stream.ToArray()[..^1]))
            using(var reader = new BinaryReader(truncated)) peer.Host.ReceiveExtraAI(reader);
            Equal<bool?>(false, peer.Host.CanDamage(), "truncated new phase payload fails closed");
            Equal(false, peer.Host.ShouldUpdatePosition(), "rejected definition suspends native integration");
            int damage = body.damage, life = body.timeLeft;
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            host.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            host.AI(); Equal(damage, body.damage, "hydrate never replays release multiplier");
            Equal(life, body.timeLeft, "hydrate preserves remaining lifetime");
        });
    }
}
