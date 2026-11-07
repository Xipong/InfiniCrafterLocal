using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private sealed class FrontHandRepairScope : IDisposable
    {
        private readonly NativeActorState actors = new();
        private readonly PropertyInfo registryProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        private readonly object? oldRegistry;
        private readonly GeneratedItemRegistryService registry = new();
        private readonly int mouseX = Terraria.Main.mouseX, mouseY = Terraria.Main.mouseY;
        private readonly Vector2 screen = Terraria.Main.screenPosition;
        internal FrontHandRepairScope()
        {
            oldRegistry = registryProperty.GetValue(null); registryProperty.SetValue(null, registry);
            for (int i = 0; i < Terraria.Main.projectile.Length; i++) Terraria.Main.projectile[i] ??= new Projectile();
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0; Terraria.Main.dedServ = false;
        }
        internal void Register(GeneratedItemData data)
        {
            GeneratedItemRegistryService.StampCurrentWorld(data);
            ((IDictionary)registry.GetType().GetField("_byId", TestInstance)!.GetValue(registry)!)[data.Id] = data;
        }
        public void Dispose()
        {
            registryProperty.SetValue(null, oldRegistry); registry.Dispose(); actors.Dispose();
            Terraria.Main.mouseX = mouseX; Terraria.Main.mouseY = mouseY; Terraria.Main.screenPosition = screen;
        }
    }
    private static void FrontHandRepairOwner(Player owner, GeneratedItemData data)
    {
        owner.active = true; owner.dead = false; owner.whoAmI = 0; owner.direction = 1; owner.gravDir = 1;
        owner.position = new Vector2(300, 300); owner.fullRotation = .27f; owner.fullRotationOrigin = new Vector2(10, 21);
        owner.gfxOffY = 5; owner.selectedItem = 0;
        owner.itemAnimation = owner.itemAnimationMax = owner.itemTime = owner.itemTimeMax = 60;
        var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
        AttachItem(new GeneratedItem(), item, data); data.ApplyToItem(item); owner.inventory[0] = item;
        Terraria.Main.player[0] = owner;
    }
    private static GeneratedProjectile FrontHandRepairActor(Player owner, GeneratedItemData data, int slot, Vector2 initial)
    {
        var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
        var projectile = new Projectile { owner = 0, whoAmI = slot, identity = 71, active = true, Center = owner.MountedCenter };
        var generated = Attach(projectile); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        Terraria.Main.projectile[slot] = projectile; generated.Configure(data, entity, 0, 8, initial);
        return generated;
    }
    private static Vector2 FrontHandRepairMouse(Player owner, int x, int y)
    {
        Terraria.Main.mouseX = x; Terraria.Main.mouseY = y;
        return (Terraria.Main.MouseWorld - owner.MountedCenter).SafeNormalize(new Vector2(owner.direction, 0));
    }
    private static void FrontHandCursorEventuallyPublishesStationaryAim()
    {
        WithPlayer((owner, _) => {
            using var scope = new FrontHandRepairScope();
            Terraria.Main.screenPosition = new Vector2(40, 60);
            foreach (int updates in new[] { 1, 6 }) {
                var root = JsonNode.Parse(FrontHandWire())!.AsObject(); var er = FrontHandEntity(root);
                er["aim"]!["source"] = "cursor"; er["collision"]!["extraUpdates"] = updates - 1;
                var data = FrontHandDefinition(root.ToJsonString()); data.VfxManifest = VfxManifestSpec.Empty();
                scope.Register(data); FrontHandRepairOwner(owner, data);
                Vector2 a = FrontHandRepairMouse(owner, 700, 400);
                var generated = FrontHandRepairActor(owner, data, 7, a); var projectile = generated.Projectile;
                generated.AI(); Equal(true, projectile.netUpdate, "first owner cursor publication updates native netUpdate");
                AssertVfxNear(a, new Vector2(projectile.ai[0], projectile.ai[1]), "first published A");
                for (int u = 1; u < updates; u++) generated.AI();
                projectile.netUpdate = false;
                Vector2 b = FrontHandRepairMouse(owner, 380, 750);
                Equal(true, Vector2.DistanceSquared(a, b) > .1f, "independent cursor A/B witness");
                for (int u = 0; u < updates; u++) generated.AI();
                Equal(false, projectile.netUpdate, "A->B inside six-world-tick throttle does not send early");
                Vector2 handAtB = FrontHandExpected(owner, b, owner.compositeFrontArm.stretch);
                AssertVfxNear(handAtB + b * 17, projectile.Center, "local physical center already uses unsent B");
                owner.ItemCheck_ApplyUseStyle(0, owner.HeldItem, new Rectangle(0, 0, 32, 32));
                AssertVfxNear(handAtB, owner.RotatedRelativePoint(owner.GetFrontHandPosition(owner.compositeFrontArm.stretch,
                    owner.compositeFrontArm.rotation), addGfxOffY: false), "use-style retains local B inside throttle");
                bool sent = false;
                for (int tick = 3; tick <= 7; tick++) {
                    for (int u = 0; u < updates; u++) generated.AI();
                    sent |= projectile.netUpdate;
                }
                Equal(true, sent, "stationary B is eventually published after throttle; updates=" + updates);
                AssertVfxNear(b, new Vector2(projectile.ai[0], projectile.ai[1]), "published native ai carries final B");
                byte[] extra = ReviewExtra(generated); // real existing ExtraAI serializer, mid-cycle age
                var peerProjectile = new Projectile { owner = 0, whoAmI = 7, identity = 71, active = true,
                    position = projectile.position, timeLeft = projectile.timeLeft, damage = projectile.damage };
                // Model native SyncProjectile field delivery only on receiver, never assign owner ai.
                Array.Copy(projectile.ai, peerProjectile.ai, projectile.ai.Length);
                var peer = Attach(peerProjectile); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(peerProjectile, peer);
                // One native actor per simulated world: a duplicate owner actor
                // would incorrectly win the deterministic front-arm writer election.
                Terraria.Main.projectile[7] = peerProjectile; Terraria.Main.myPlayer = 1; Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(extra)));
                Equal(true, peer.Matches(data.Id, data.RuntimeProgram.PrimaryEntityId), "real decoder hydrates explicit composed hand peer");
                for (int u = 0; u < updates; u++) peer.AI();
                Vector2 peerCenter = peerProjectile.Center;
                Terraria.Main.projectile[7] = projectile;
                Terraria.Main.myPlayer = 0; Terraria.Main.netMode = NetmodeID.SinglePlayer;
                for (int u = 0; u < updates; u++) generated.AI();
                AssertVfxNear(projectile.Center, peerCenter, "mid-cycle ai+ExtraAI owner/peer physical C agrees");
                AssertVfxNear(b, peerProjectile.rotation.ToRotationVector2(), "hydrated explicit axis rotation B");
                Console.WriteLine("cursor publication and peer geometry updates=" + updates);
                projectile.active = peerProjectile.active = false;
            }
            // Initial is a separate authored aim choice, not the cursor-positive path.
            var initialData = FrontHandDefinition(); initialData.VfxManifest = VfxManifestSpec.Empty();
            FrontHandRepairOwner(owner, initialData);
            Vector2 initial = .45f.ToRotationVector2(); var control = FrontHandRepairActor(owner, initialData, 7, initial);
            for (int tick = 1; tick <= 8; tick++) {
                FrontHandRepairMouse(owner, tick % 2 == 0 ? 380 : 700, tick % 2 == 0 ? 750 : 400);
                control.Projectile.netUpdate = false; control.AI();
                AssertVfxNear(initial, control.Projectile.rotation.ToRotationVector2(), "initial explicit axis never follows cursor");
                Equal(false, control.Projectile.netUpdate, "initial has no cursor-publication owner");
            }
        });
    }


    private static void FrontHandGameplayEventsRetainSelectedAxis()
    {
        foreach (string aimMode in new[] { "initial", "cursor" })
        foreach (string lane in new[] { "hit", "hit_geometry", "periodic" })
        foreach (int delay in new[] { 0, 2 })
        foreach (int updates in new[] { 1, 6 })
        WithPlayer((owner, _) => {
            using var clock = new RuntimeWorldClockScope();
            using var actors = new Rt01NpcScope(NetmodeID.SinglePlayer);
            using var scope = new FrontHandRepairScope();
            Terraria.Main.screenPosition = Vector2.Zero;
            var data = FrontHandDefinition();
            data.VfxManifest = VfxManifestSpec.Empty();
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            entity.Aim!.Source = aimMode;
            entity.Collision.ExtraUpdates = updates - 1;
            var child = ChildCombatFixture().RuntimeProgram.TryGetEntity("child")!;
            child.Spawn.Aim = "velocity"; child.Spawn.Placement = "item_use_origin";
            child.Spawn.OffsetPx = 0; child.Spawn.OverTarget = new();
            data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Append(child).ToArray();
            var action = new RuntimeEventActionSpec {
                Id = "hand_child", Event = lane == "periodic" ? RuntimeEventKind.Periodic : RuntimeEventKind.OnHit,
                Action = "spawn_entity_on_event", ActionCode = RuntimeEventActionCode.SpawnEntity,
                EntityId = child.Id, Count = 1, SpreadRadians = 0,
                DamageMultiplier = 1, DamageBasis = RuntimeChildCombatBasis.AuthoredChild,
                KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild,
                PeriodTicks = lane == "periodic" ? 6 : 0, DelayTicks = delay,
            };
            if (lane == "hit_geometry") {
                action.HitTargetSpawn = HitGeometry(0);
                action.HitTargetSpawn.AfterFanSpreadRadians = 0;
                action.HitTargetSpawn.InitialIgnoreCountdownUpdates = 0;
            }
            entity.Events = new[] { action };
            data.RuntimeProgram.NormalizeAndValidate();
            scope.Register(data); FrontHandRepairOwner(owner, data);
            Vector2 initial = Vector2.UnitX;
            FrontHandRepairMouse(owner, 700, 400);
            var generated = FrontHandRepairActor(owner, data, 7, initial);
            void ActiveTick() { for (int update = 0; update < updates; update++) generated.AI(); }
            ActiveTick();
            Vector2 turned = FrontHandRepairMouse(owner, 380, 750);
            ActiveTick();
            Vector2 expected = aimMode == "cursor" ? turned : initial;
            string label = $"hand event axis {aimMode}/{lane}/delay={delay}/updates={updates}";
            Equal(true, Vector2.DistanceSquared(initial, turned) > .1f, label + " changed-axis counterproof");
            Equal(Vector2.Zero, generated.Projectile.velocity, label + " no translational velocity");
            AssertVfxNear(expected, generated.Projectile.rotation.ToRotationVector2(), label + " actual explicit axis rotation");
            NPC target = TargetEmissionNpc(0, 500, 500);
            if (lane == "periodic") { ActiveTick(); ActiveTick(); ActiveTick(); }
            Action dispatch = lane == "periodic" ? ActiveTick
                : () => generated.OnHitNPC(target, new NPC.HitInfo(), 1);
            if (delay > 0) {
                dispatch();
                Equal(1, PendingActions(), label + " queued at event admission");
                FrontHandRepairMouse(owner, 50, 150);
                ActiveTick(); // a later cursor turn must not rewrite the queued axis
                AdvanceRuntimeWorldTick();
                Equal(1, PendingActions(), label + " waits for exact due world tick");
                dispatch = AdvanceRuntimeWorldTick;
            }
            int observed = 0;
            using var boundary = TargetEmissionEntry((source, position, velocity, damage, knockback) => {
                observed++;
                AssertVfxNear(expected * child.Spawn.SpeedPxPerTick, velocity, label + " native child velocity");
                Equal(true, source is Terraria.DataStructures.EntitySource_Parent parent
                    && ReferenceEquals(parent.Entity, generated.Projectile), label + " exact event source");
            });
            Equal(true, ObserveTargetEmission(dispatch), label + " reached real native spawn boundary");
            Equal(1, observed, label + " one child emission");
            Equal(0, PendingActions(), label + " no delayed replay");
        });
    }

    private static void FrontHandHistoryAndEventSnapshotPreserveExactBodyScale()
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) => {
            using var actors = new NativeActorState(); using var cache = new BorrowedSpriteCache();
            var system = new InfiniDetachedVfxSystem();
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            try {
                system.OnWorldUnload(); MaterialClock(100);
                Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(CpuTexture(1, 1));
                var root = JsonNode.Parse(FrontHandWire())!.AsObject(); var er = FrontHandEntity(root);
                er["hitbox"]!["drawScale"] = .25; er["visual"]!["scale"] = .25;
                er["visualScaleCurve"] = JsonNode.Parse("{\"startScale\":0.25,\"endScale\":0.25,\"startDelayTicks\":0,\"durationTicks\":12,\"curve\":\"linear\"}");
                string path = Path.Combine(Terraria.Program.SavePath, "exact_hand_frame.png"); root["visual"]!["spritePath"] = path;
                var data = FrontHandDefinition(root.ToJsonString()); var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                data.VfxManifest = VfxManifestSpec.Empty();
                var texture = CpuTexture(64, 16);
                if (!cache.Textures.Contains(cache.Publish(path))) cache.Textures.Add(cache.Publish(path), Activator.CreateInstance(cache.Record, texture, .71f, 0L)!);
                FrontHandRepairOwner(owner, data); Vector2 axis = .6f.ToRotationVector2();
                var generated = FrontHandRepairActor(owner, data, 7, axis); var projectile = generated.Projectile;
                for (int tick = 1; tick <= 6; tick++) generated.AI();
                Equal(.015625f, projectile.scale, "real AI applies .25*.25*constant curve .25");
                int mainIndex = count(); Color light = Color.White; generated.PreDraw(ref light);
                Equal(mainIndex + 1, count(), "one main PNG full-frame quad");
                object mainQuad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(mainIndex)!;
                Vector2 hand = FrontHandExpected(owner, axis, Player.CompositeArmStretchAmount.Full);
                AssertVfxNear(hand - Terraria.Main.screenPosition + new Vector2(0, projectile.gfxOffY),
                    FrontHandQueuedGrip(batch, mainIndex, new ItemGripSpec { NormalizedX = .15625, NormalizedY = .5 }), "main exact-scale grip");
                AssertVfxNear(axis, BodyForwardFromCpuQueue(batch, mainIndex, 23, "main"), "main declared axis");
                float diagonal = positions(mainIndex).SelectMany(a => positions(mainIndex).Select(b => Vector3.Distance(a, b))).Max();
                Equal(true, Math.Abs(diagonal - 32 * .015625f * MathF.Sqrt(1 + 1f / 16)) < .001f, "main selected R/max(frame) exact size");
                int liveIndex = count();
                var sample = DrawCurrentBodyTrail(projectile, data, entity.Id);
                Equal(liveIndex + 1, count(), "current body history submits its sampled pose");
                object liveQuad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(liveIndex)!;
                Equal(true, SameFrontHandPositionUv(mainQuad, liveQuad), "sampled history grip/axis/frame/exact scale agrees");
                var expectedSnapshot = InfiniVfxProjectileSnapshot.Capture(projectile, data, entity.Id);
                // Actual event encoder/decoder retains the bounded native pose, without
                // reviving the retired detached body-copy renderer or opening sockets.
                object payload = typeof(GeneratedProjectile).GetMethod("CaptureVfxPayload", TestInstance)!
                    .Invoke(generated, new object[] { RuntimeEventKind.OnKill, projectile.Center, (byte)0 })!;
                using var wire = new MemoryStream(); var writer = new BinaryWriter(wire);
                typeof(GeneratedProjectile).GetMethod("WriteVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { writer, payload });
                wire.Position = 0;
                object decoded = typeof(GeneratedProjectile).GetMethod("ReadVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!
                    .Invoke(null, new object[] { new BinaryReader(wire) })!;
                var snap = (InfiniVfxProjectileSnapshot)decoded.GetType().GetProperty("Snapshot")!.GetValue(decoded)!;
                Equal(.015625f, snap.Pose.Scale, "actual event wire preserves selected bounded body scale");
                Equal(expectedSnapshot.Center, snap.Center, "event wire preserves native center");
                Equal(expectedSnapshot.Pose, snap.Pose, "event wire preserves exact angle/scale/flip/gfx offset");
                AssertVfxNear(axis, snap.Forward, "event wire preserves selected hand axis");
                // The sampled-pose draw consumer must use frozen sample values, not
                // borrow the subsequently changed live body's grip or frame.
                projectile.scale = 7; projectile.rotation = -2; projectile.Center = Vector2.Zero; projectile.gfxOffY = -30;
                int frozenIndex = count();
                var trail = CurrentBodyTrailManifest(entity.Id).Slots[0].Trail!;
                InfiniVfxRuntime.DrawExplicitTrailSamples(Terraria.GameContent.TextureAssets.MagicPixel.Value,texture,
                    new[] { sample },trail,"alpha",sample.Tick,null,()=>true);
                Equal(frozenIndex + 1,count(),"frozen sampled pose reaches actual native queue");
                object frozenQuad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(frozenIndex)!;
                Equal(true, SameFrontHandPositionUv(mainQuad,frozenQuad),"sampled UV/position retains rigid frame after source mutation");
            } finally { system.OnWorldUnload(); Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        }));
    }

    private static bool SameFrontHandPositionUv(object expected, object actual)
    {
        var ep = CpuVertexValues<Vector3>(expected); var ap = CpuVertexValues<Vector3>(actual);
        var eu = CpuVertexValues<Vector2>(expected); var au = CpuVertexValues<Vector2>(actual);
        return ep.Length == 4 && ap.Length == 4 && eu.SequenceEqual(au)
            && ep.Zip(ap).All(p => Vector3.Distance(p.First, p.Second) < .001f);
    }
}
