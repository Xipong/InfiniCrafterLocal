using System;
using System.Collections.Generic;
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

    private static void ComposableMotionPhaseOnlySpinAdvancesEveryUpdate()
    {
        foreach (string phase in new[] { "released", "outbound", "returning" })
        foreach (int extraUpdates in new[] { 0, 2 })
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState(); owner.channel = true;
            string trigger = phase == "returning"
                ? "\"returnTrigger\":{\"afterTicks\":4,\"onOwnerRelease\":false,\"onTileCollision\":false,\"disableTileCollisionOnReturn\":false}"
                : "\"charge\":{\"durationTicks\":4,\"autoReleaseAfterActiveTicks\":4}";
            string clock = phase == "returning" ? "since_return" : "since_release";
            GeneratedItemData Definition(bool timed) => MotionDefinition("{" + trigger
                + ",\"rotation\":{\"window\":{\"phase\":\"" + phase + "\""
                + (timed ? ",\"clock\":\"" + clock + "\",\"startDelayTicks\":0,\"durationTicks\":60" : "")
                + "},\"mode\":\"spin\",\"offsetRadians\":0.5,\"radiansPerUpdate\":-0.25}}",
                e => e["collision"]!["extraUpdates"] = extraUpdates);
            var data = Definition(false);
            var wholePhase = MotionActor(data, owner, Vector2.Zero);
            var finite = MotionActor(Definition(true), owner, Vector2.Zero);
            int transitionUpdate = 4 * (extraUpdates + 1);
            for (int update = 1; update < transitionUpdate; update++) {
                wholePhase.Host.AI(); finite.Host.AI();
                Equal(0f, wholePhase.Body.rotation, phase + " spin stays inactive before its latch");
            }
            for (int step = 1; step <= 4; step++) {
                wholePhase.Host.AI(); finite.Host.AI();
                float expected = 0.5f - step * 0.25f;
                Equal(expected, wholePhase.Body.rotation, phase + " phase-only spin step " + step);
                Equal(finite.Body.rotation, wholePhase.Body.rotation,
                    phase + " removing an unexpired timing bound preserves spin rate");
                if (step == 2)
                    wholePhase.Host.Configure(data, data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!,
                        0, 8, Vector2.UnitX, preserveSyncedState: true);
            }
        });
    }
    private static void ComposableMotionTileReturnRelativeWindowRetainsFirstStep()
    {
        foreach (bool legacy in new[] { false, true })
        foreach (int extra in new[] { 0, 2 }) WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            using var peers = new ReviewPeers();
            var data = MotionDefinition("""
              {"returnTrigger":{"onOwnerRelease":false,"onTileCollision":true,"disableTileCollisionOnReturn":true},
               "verticalAcceleration":{"window":{"phase":"returning","clock":"since_return","startDelayTicks":0,"durationTicks":1},"accelerationYPerUpdate":2}}
              """, e => {
                  e["collision"]!["tileCollide"] = true; e["collision"]!["extraUpdates"] = extra;
                  if (legacy) {
                      e.Remove("returnTrigger");
                      e["movement"] = JsonNode.Parse("""
                        {"name":"move_boomerang","code":5,"params":{"returnAfterTicks":60,"returnSpeed":1}}
                        """);
                  }
              });
            peers.Register(data);
            var (host, body) = MotionActor(data, owner, Vector2.UnitX);
            host.AI();
            body.velocity = Vector2.Zero; // native tile collision has already clipped the blocked axis
            Equal(false, host.OnTileCollide(Vector2.UnitX), "explicit return collision retains source");
            var snapshot = ReviewExtra(host);
            var peer = MotionActor(data, owner, body.velocity);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
            peer.Host.ReceiveExtraAI(new BinaryReader(new MemoryStream(snapshot)));
            Equal(true, ProjectileConfigured(peer.Host), "post-tile snapshot admits next-update return clock");
            peer.Host.AI();
            Equal(2f, peer.Body.velocity.Y, "hydrated peer receives the first relative-window force update");
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            if (legacy) {
                host.AI();
                Equal(2f, body.velocity.Y, "retained return also receives the first selected force update");
                return; // Later velocity belongs to the retained return interpolation.
            }
            for (int i = 0; i <= extra; i++) host.AI();
            Equal(2f * (extra + 1), body.velocity.Y,
                "tile-latched one-tick relative window must execute every following AI subupdate; extraUpdates=" + extra);
            float complete = body.velocity.Y;
            host.AI();
            Equal(complete, body.velocity.Y, "relative window ends after one full tick");
            int age = (int)typeof(GeneratedProjectile).GetField("_age", TestInstance)!.GetValue(host)!;
            typeof(GeneratedProjectile).GetField("_returnAge", TestInstance)!.SetValue(host, age + 2);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
            peer.Host.ReceiveExtraAI(new BinaryReader(new MemoryStream(ReviewExtra(host))));
            Equal(false, ProjectileConfigured(peer.Host), "return snapshot cannot invent a clock beyond the next update");
            Equal(false, peer.Host.CanDamage(), "invalid future snapshot remains harmless");
        });
    }

    private static void ComposableMotionFreePresentationDoesNotImplyOwnerCancellation()
    {
        foreach (string state in new[] { "noItems", "CCed", "dead" })
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var ordinary = MotionActor(MotionDefinition("{}"), owner, Vector2.UnitX);
            void SetOwnerState(bool value) {
                owner.noItems = state == "noItems" && value;
                owner.frozen = state == "CCed" && value;
                owner.dead = state == "dead" && value;
            }
            SetOwnerState(true);
            ordinary.Host.AI();
            Equal(true, ordinary.Body.active, "ordinary free body remains live while owner cannot use items");
            SetOwnerState(false);
            var colored = MotionActor(MotionDefinition("""
              {"opacity":{"alpha":137},"verticalAcceleration":{"accelerationYPerUpdate":1},
               "rotation":{"mode":"spin","offsetRadians":0,"radiansPerUpdate":0.25}}
              """), owner, Vector2.UnitX);
            SetOwnerState(true);
            colored.Host.AI();
            Equal(true, colored.Body.active, "independent opacity cannot introduce unauthored owner cancellation");
            Equal(137, colored.Body.alpha, "explicit presentation still applies during owner item lockout");
            Equal(new Vector2(1, 1), colored.Body.velocity, "free force keeps its independently authored acceleration");
            Equal(.25f, colored.Body.rotation, "free spin keeps its independently authored angular rate");
            SetOwnerState(false);
            var controlled = MotionActor(MotionDefinition("""
              {"ownerControl":{"requireHeldItem":false,"requireChannel":false,"requireItemAnimation":true,
                "claimHeldProjectile":false,"animation":"none","lifetime":"authored"}}
              """), owner, Vector2.UnitX);
            owner.itemAnimation = 10; SetOwnerState(true);
            controlled.Host.AI();
            Equal(false, controlled.Body.active, "explicit owner control retains input/death cancellation");
        });
    }

    private static GeneratedItemData ComposableMotionExpiryReceiptData(bool shortWindow = false)
    {
        var root = JsonNode.Parse(ReviewProjectileData("on_expire").ToJson())!.AsObject();
        root.Remove("runtimeContract");
        var actor = root["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "actor")!;
        actor["hitbox"]!["widthPx"] = 40; actor["hitbox"]!["heightPx"] = 18;
        actor["proximity"] = JsonNode.Parse("""
          {"searchRangeTiles":10,"triggerRadiusPx":8,"requireLineOfSight":false,"action":"expire_then_kill"}
          """);
        if (shortWindow) actor["proximity"]!["window"] = JsonNode.Parse("""
          {"phase":"always","clock":"active","startDelayTicks":0,"durationTicks":1}
          """);
        actor["events"] = JsonNode.Parse("""
          [{"id":"expiry_area","event":"on_expire","action":"damage_area_on_event","actionCode":3,
            "radiusPx":16,"damageMultiplier":1,"delayTicks":60}]
          """);
        return ParseMaterialElement(root);
    }
    private static void ComposableMotionExpiryReceiptTarget(GeneratedProjectile source, float distance = 4)
    {
        Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
        Terraria.Main.npc[0] = new NPC { whoAmI=0, active=true, life=100, lifeMax=100, damage=1,
            friendly=false, dontTakeDamage=false, width=10, height=10, Center=source.Projectile.Center + new Vector2(distance,0) };
    }
    private static GeneratedProjectile ComposableMotionNativePeer(GeneratedProjectile owner)
    {
        var body = Terraria.Main.projectile[11] = new Projectile {
            active = true, whoAmI = 11, owner = owner.Projectile.owner, identity = owner.Projectile.identity,
            damage = owner.Projectile.damage, knockBack = owner.Projectile.knockBack };
        var peer = Attach(body); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(body, peer);
        peer.SetDefaults();
        // Native Msg27 assigns top-left before ExtraAI, while proxy dimensions
        // still come from SetDefaults until the exact definition hydrates.
        body.position = owner.Projectile.position; body.velocity = owner.Projectile.velocity;
        return peer;
    }
    private static void ComposableMotionExpiryReceiptNativeOrderAndServerOnceOnly()
    {
        foreach (bool fresh in new[] { false, true })
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            RuntimeDelayedActionScheduler.Clear();
            try {
                var data = ComposableMotionExpiryReceiptData(); peers.Register(data);
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                var owner = peers.Host(data); ComposableMotionExpiryReceiptTarget(owner);
                byte[] initial = ReviewExtra(owner);
                var sends = new List<int>(); byte[]? receipt = null;
                using var transport = PersistenceObserveNetworkSend((message, _) => {
                    sends.Add(message);
                    if (message == MessageID.SyncProjectile) receipt = ReviewExtra(owner);
                });
                owner.AI();
                Equal(false, owner.Projectile.active, "owner performed real proximity expiry and native Kill");
                Equal("27,29", string.Join(",", sends), "native terminal SyncProjectile must be sent synchronously before KillProjectile");
                Equal(true, receipt is not null, "actual terminal sender captures existing ExtraAI wire");
                Equal(0, PendingActions(), "owner cannot run server NPC action");
                Equal(0, peers.Sent.Count, "owner cannot fabricate server-produced expiry VFX");

                peers.Mode(NetmodeID.Server, 255);
                GeneratedProjectile server;
                if (fresh) {
                    server = ComposableMotionNativePeer(owner);
                    ComposableMotionExpiryReceiptTarget(owner); // Real target near sender center, not fresh 12x12 proxy center.
                }
                else {
                    server = peers.Host(data, extra: initial);
                    server.Projectile.position = owner.Projectile.position;
                    ComposableMotionExpiryReceiptTarget(server);
                }
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                AssertVfxNear(owner.Projectile.Center, server.Projectile.Center, "expiry qualification keeps native sender geometry");
                Equal(1, PendingActions(), "authenticated native snapshot with real server proximity schedules one expiry effect");
                Equal(1, peers.Sent.Count, "server emits one expiry VFX relay");
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(initial)));
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                server.OnKill(60); // native packet kill cannot infer or replay the cause
                Equal(1, PendingActions(), "duplicate receipt, stale observation and OnKill cannot repeat expiry gameplay");
                Equal(1, peers.Sent.Count, "duplicate receipt and native kill cannot repeat expiry presentation");
                byte[] relay = peers.Sent.Single();
                peers.Mode(NetmodeID.MultiplayerClient, 2); MaterialClock(120); peers.System.PostUpdateEverything();
                Equal(0, OwnedMaterialQueue().Count, "owner-local expiry material has retired before remote receive");
                peers.Receive(relay); peers.Receive(relay);
                Equal(1, OwnedMaterialQueue().Count, "remote renders exactly one actual server expiry relay");
                Equal(1, PendingActions(), "presentation relay cannot add gameplay actions");
            } finally { RuntimeDelayedActionScheduler.Clear(); }
        });
    }
    private static void ComposableMotionExpiryReceiptRejectsUnsupportedGeometryAndCause()
    {
        foreach (string scenario in new[] { "outside_radius", "outside_search", "unchaseable", "inactive", "kill_only", "future_window", "blocked_sight" })
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            RuntimeDelayedActionScheduler.Clear();
            try {
                var data = ComposableMotionExpiryReceiptData(); peers.Register(data);
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                var owner = peers.Host(data); ComposableMotionExpiryReceiptTarget(owner);
                byte[] initial = ReviewExtra(owner); byte[]? receipt = null;
                using var transport = PersistenceObserveNetworkSend((message, _) => {
                    if (message == MessageID.SyncProjectile) receipt = ReviewExtra(owner);
                });
                owner.AI();
                Equal(true, receipt is not null, "negative observer starts from actual owner expiry wire");
                peers.Mode(NetmodeID.Server, 255);
                var server = peers.Host(data, extra: initial); ComposableMotionExpiryReceiptTarget(server);
                using var sight = scenario == "blocked_sight" ? new MonoMod.RuntimeDetour.Hook(
                    typeof(Collision).GetMethod(nameof(Collision.CanHitLine), new[] { typeof(Vector2), typeof(int), typeof(int), typeof(Vector2), typeof(int), typeof(int) })!,
                    (Func<Vector2, int, int, Vector2, int, int, bool>)((_, __, ___, ____, _____, ______) => false)) : null;
                switch (scenario) {
                    case "outside_radius": Terraria.Main.npc[0].Center = server.Projectile.Center + new Vector2(9,0); break;
                    case "outside_search": Terraria.Main.npc[0].Center = server.Projectile.Center + new Vector2(161,0); break;
                    case "unchaseable": Terraria.Main.npc[0].dontTakeDamage = true; break;
                    case "inactive": Terraria.Main.npc[0].active = false; break;
                    // Server's exact authored cause is the authority; a received terminal flag cannot turn kill into expiry.
                    case "kill_only": data.RuntimeProgram.TryGetEntity("actor")!.Proximity!.Action = "kill"; break;
                    case "future_window": data.RuntimeProgram.TryGetEntity("actor")!.Proximity!.Window = new RuntimeMotionWindowSpec {
                        Phase="always", Clock="active", StartDelayTicks=60, DurationTicks=1 }; break;
                    case "blocked_sight": data.RuntimeProgram.TryGetEntity("actor")!.Proximity!.RequireLineOfSight = true; break;
                }
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                server.OnKill(60);
                Equal(0, PendingActions(), scenario + " cannot authorize terminal expiry gameplay");
                Equal(0, peers.Sent.Count, scenario + " cannot authorize terminal expiry VFX");
                // If rejected receipt was consumed, moving an NPC into range later cannot retroactively authenticate it.
                ComposableMotionExpiryReceiptTarget(server);
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                Equal(0, PendingActions(), scenario + " invalid claim cannot become valid by replaying later");
            } finally { RuntimeDelayedActionScheduler.Clear(); }
        });
    }
    private static void ComposableMotionExpiryReceiptWaitsForActualDefinition()
    {
        foreach (string scenario in new[] { "unchanged", "moved", "retired", "nonfinite" })
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            RuntimeDelayedActionScheduler.Clear();
            var registryProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
            try {
                var data = ComposableMotionExpiryReceiptData(); peers.Register(data);
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                var owner = peers.Host(data); ComposableMotionExpiryReceiptTarget(owner);
                byte[] initial = ReviewExtra(owner); byte[]? receipt = null;
                using var transport = PersistenceObserveNetworkSend((message, _) => {
                    if (message == MessageID.SyncProjectile) receipt = ReviewExtra(owner);
                });
                owner.AI(); Equal(true, receipt is not null, "late hydration uses an actual terminal source receipt");
                peers.Mode(NetmodeID.Server, 255); registryProperty.SetValue(null, null);
                var server = ComposableMotionNativePeer(owner);
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                ComposableMotionExpiryReceiptTarget(owner);
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(initial)));
                Equal(0, PendingActions(), "missing definition is not authority to run a received terminal flag");
                Equal(0, peers.Sent.Count, "missing definition cannot produce expiry presentation");
                Vector2 eventPosition = server.Projectile.position;
                if (scenario == "moved") {
                    server.Projectile.Center += Vector2.UnitX;
                    // Qualifies at the later authored-size center, but that is
                    // not the terminal frame whose observation was received.
                    Terraria.Main.npc[0].Center = owner.Projectile.Center + new Vector2(5, 0);
                }
                if (scenario == "retired") server.Projectile.active = false;
                if (scenario == "nonfinite") server.Projectile.position = new Vector2(float.NaN, eventPosition.Y);
                registryProperty.SetValue(null, peers.Registry);
                server.Configure(data, data.RuntimeProgram.TryGetEntity("actor")!, 0, 0, Vector2.UnitX, preserveSyncedState: true);
                int expected = scenario == "unchanged" ? 1 : 0;
                Equal(expected, PendingActions(), scenario + " deferred hydration must preserve the exact live terminal frame");
                Equal(expected, peers.Sent.Count, scenario + " late hydration cannot guess an expiry relay");
                server.Projectile.active = true; server.Projectile.position = eventPosition;
                ComposableMotionExpiryReceiptTarget(server);
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                Equal(expected, PendingActions(), "hydration plus repeated claim never retries consumed expiry gameplay");
            } finally { registryProperty.SetValue(null, peers.Registry); RuntimeDelayedActionScheduler.Clear(); }
        });
    }

    private static void ComposableMotionExpiryReceiptUsesEventClockWithoutRewindingServer()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            RuntimeDelayedActionScheduler.Clear();
            try {
                var data = ComposableMotionExpiryReceiptData(shortWindow: true); peers.Register(data);
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                var owner = peers.Host(data); ComposableMotionExpiryReceiptTarget(owner);
                byte[] initial = ReviewExtra(owner); byte[]? receipt = null;
                using var transport = PersistenceObserveNetworkSend((message, _) => {
                    if (message == MessageID.SyncProjectile) receipt = ReviewExtra(owner);
                });
                owner.AI(); Equal(true, receipt is not null, "one-tick owner event emits exact terminal snapshot");
                peers.Mode(NetmodeID.Server, 255);
                var server = peers.Host(data, extra: initial); ComposableMotionExpiryReceiptTarget(server);
                for(int i=0; i<3; i++) server.AI();
                int priorAge = (int)typeof(GeneratedProjectile).GetField("_age", TestInstance)!.GetValue(server)!;
                Equal(0, PendingActions(), "server cannot infer terminal cause merely from proximity while ahead");
                server.ReceiveExtraAI(new BinaryReader(new MemoryStream(receipt!)));
                Equal(1, PendingActions(), "actual event was inside its one-tick window despite receiver's newer local age");
                Equal(priorAge, (int)typeof(GeneratedProjectile).GetField("_age", TestInstance)!.GetValue(server)!,
                    "validating event-local clock cannot rewind live server motion clock");
            } finally { RuntimeDelayedActionScheduler.Clear(); }
        });
    }

    private static void ComposableMotionFirstHydratedServerStillProducesSpawnVfx()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var root = JsonNode.Parse(ReviewProjectileData("on_spawn").ToJson())!.AsObject();
            root.Remove("runtimeContract");
            var actor = root["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "actor")!;
            actor["opacity"] = JsonNode.Parse("{\"alpha\":137}");
            var data = ParseMaterialElement(root); peers.Register(data);
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            var owner = peers.Host(data); owner.AI();
            Equal(0, peers.Sent.Count, "owner on_spawn is not an owner-produced relay event");
            byte[] afterFirstAi = ReviewExtra(owner);
            peers.Mode(NetmodeID.Server, 255);
            var server = peers.Host(data, extra: afterFirstAi); server.AI();
            Equal(1, peers.Sent.Count, "first authoritative server hydration must produce on_spawn VFX relay even after owner AI");
        });
    }

}
