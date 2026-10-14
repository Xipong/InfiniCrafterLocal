using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
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
    // These checks reference only APIs already present in the current code20 candidate.
    // The parent compiles check-only first; no production-source reflection substitute.
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
                er["movement"]!["params"]!["aimMode"] = "cursor"; er["collision"]!["extraUpdates"] = updates - 1;
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
                Equal(true, sent, "RED: stationary B is eventually published after throttle; updates=" + updates);
                AssertVfxNear(b, new Vector2(projectile.ai[0], projectile.ai[1]), "published native ai carries final B");
                byte[] extra = ReviewExtra(generated); // real existing ExtraAI serializer, mid-cycle age
                var peerProjectile = new Projectile { owner = 0, whoAmI = 8, identity = 71, active = true,
                    Center = projectile.Center, timeLeft = projectile.timeLeft, damage = projectile.damage };
                // Model native SyncProjectile field delivery only on receiver, never assign owner ai.
                Array.Copy(projectile.ai, peerProjectile.ai, projectile.ai.Length);
                var peer = Attach(peerProjectile); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(peerProjectile, peer);
                Terraria.Main.projectile[8] = peerProjectile; Terraria.Main.myPlayer = 1; Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(extra)));
                Equal(true, peer.Matches(data.Id, data.RuntimeProgram.PrimaryEntityId), "real decoder hydrates explicit code20 peer");
                for (int u = 0; u < updates; u++) peer.AI();
                Vector2 peerCenter = peerProjectile.Center;
                Terraria.Main.myPlayer = 0; Terraria.Main.netMode = NetmodeID.SinglePlayer;
                for (int u = 0; u < updates; u++) generated.AI();
                AssertVfxNear(projectile.Center, peerCenter, "mid-cycle ai+ExtraAI owner/peer physical C agrees");
                AssertVfxNear(b, (peerProjectile.rotation - MathHelper.PiOver2).ToRotationVector2(), "hydrated peer axis B");
                Console.WriteLine("cursor publication and peer geometry updates=" + updates);
                projectile.active = peerProjectile.active = false;
            }
            // Initial is a genuinely separate old contract, not the cursor-positive path.
            var initialData = FrontHandDefinition(); initialData.VfxManifest = VfxManifestSpec.Empty();
            FrontHandRepairOwner(owner, initialData);
            Vector2 initial = .45f.ToRotationVector2(); var control = FrontHandRepairActor(owner, initialData, 7, initial);
            for (int tick = 1; tick <= 8; tick++) {
                FrontHandRepairMouse(owner, tick % 2 == 0 ? 380 : 700, tick % 2 == 0 ? 750 : 400);
                control.Projectile.netUpdate = false; control.AI();
                AssertVfxNear(initial, (control.Projectile.rotation - MathHelper.PiOver2).ToRotationVector2(), "initial axis never follows cursor");
                Equal(false, control.Projectile.netUpdate, "initial has no cursor-publication owner");
            }
        });
    }
    private static void FrontHandLegacyCursorThrottleControl()
    {
        WithPlayer((owner, _) => {
            using var scope = new FrontHandRepairScope(); Terraria.Main.screenPosition = new Vector2(40, 60);
            var data = FrontHandDefinition(); data.VfxManifest = VfxManifestSpec.Empty();
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            // Test-only old driver; no archived definition/recipe is rewritten.
            entity.Movement.Code = 19; entity.Movement.Name = "move_forward_then_retract";
            entity.Movement.Params = new RuntimeParamsSpec { DurationTicks = 60, RangeTiles = 5 };
            FrontHandRepairOwner(owner, data); Vector2 a = FrontHandRepairMouse(owner, 700, 400);
            var generated = FrontHandRepairActor(owner, data, 7, a); generated.AI();
            Equal(true, generated.Projectile.netUpdate, "old driver first-send control"); generated.Projectile.netUpdate = false;
            Vector2 b = FrontHandRepairMouse(owner, 380, 750);
            for (int tick = 2; tick <= 8; tick++) generated.AI();
            AssertVfxNear(b, new Vector2(generated.Projectile.ai[0], generated.Projectile.ai[1]), "old driver retains local ai convention");
            Equal(false, generated.Projectile.netUpdate, "old shared-helper behavior unchanged, not silently repaired");
        });
    }

    private static void FrontHandDetachedExactBodyScale()
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) => {
            using var scope = new FrontHandRepairScope(); using var cache = new BorrowedSpriteCache();
            var system = new InfiniDetachedVfxSystem(); var queue = (IList)typeof(InfiniDetachedVfxSystem)
                .GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel; var oldView = Terraria.Main.GameViewMatrix;
            object? flushed = null; bool recordingDetached = false;
            Action<Action<SpriteBatch>, SpriteBatch> recordFlush = (orig, self) => {
                if (recordingDetached && count() > 0) {
                    Equal(1, count(), "one real detached submission");
                    flushed = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(0);
                }
                orig(self);
            };
            using var recorder = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", TestInstance)!, recordFlush);
            var wrapper = typeof(InfiniDetachedVfxSystem).GetMethod("DrawProjectiles", BindingFlags.Static | BindingFlags.NonPublic)!;
            try {
                Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(CpuTexture(1, 1));
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Viewport(0, 0, 800, 600));
                foreach (bool legacy in new[] { true, false }) {
                    system.OnWorldUnload(); MaterialClock(100);
                    var root = JsonNode.Parse(FrontHandWire())!.AsObject(); var er = FrontHandEntity(root);
                    er["hitbox"]!["drawScale"] = .25; er["visual"]!["scale"] = .25;
                    er["visualScaleCurve"] = JsonNode.Parse("{\"startScale\":0.25,\"endScale\":0.25,\"startDelayTicks\":0,\"durationTicks\":12,\"curve\":\"linear\"}");
                    string path = Path.Combine(Terraria.Program.SavePath, "exact_hand_frame.png"); root["visual"]!["spritePath"] = path;
                    var data = FrontHandDefinition(root.ToJsonString()); var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                    if (legacy) { entity.Movement.Code = 19; entity.Movement.Name = "move_forward_then_retract"; entity.Movement.Params = new RuntimeParamsSpec { DurationTicks = 60, RangeTiles = 5 }; }
                    data.VfxManifest = new VfxManifestSpec { Slots = new[] { new VfxSlotSpec { Id = "exact_scale_copy", EntityId = entity.Id,
                        Event = RuntimeEventKind.OnKill, RendererKind = "projectileAfterimage", TextureRole = "entity", Anchor = "self",
                        Layer = "AfterProjectiles", Scale = 1, Alpha = 1, Duration = 24, ParticleSystemId = "none" } } };
                    data.VfxManifest.Budget.MaxDrawCalls = 8;
                    if (!cache.Textures.Contains(path)) cache.Textures.Add(path, Activator.CreateInstance(cache.Record, CpuTexture(64, 16), .71f, 0L)!);
                    FrontHandRepairOwner(owner, data); Vector2 axis = .6f.ToRotationVector2();
                    var generated = FrontHandRepairActor(owner, data, 7, axis); var projectile = generated.Projectile;
                    for (int tick = 1; tick <= 6; tick++) generated.AI();
                    Equal(.015625f, projectile.scale, "real AI applies .25*.25*constant curve .25");
                    int mainIndex = count(); Color light = Color.White; generated.PreDraw(ref light);
                    Equal(mainIndex + 1, count(), "one main PNG full-frame quad");
                    object mainQuad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(mainIndex)!;
                    if (!legacy) {
                        Vector2 h = FrontHandExpected(owner, axis, Player.CompositeArmStretchAmount.Full);
                        AssertVfxNear(h - Terraria.Main.screenPosition + new Vector2(0, projectile.gfxOffY),
                            FrontHandQueuedGrip(batch, mainIndex, new ItemGripSpec { NormalizedX = .15625, NormalizedY = .5 }), "main exact-scale grip");
                        AssertVfxNear(axis, BodyForwardFromCpuQueue(batch, mainIndex, 23, "main"), "main declared axis");
                        float diagonal = positions(mainIndex).SelectMany(a => positions(mainIndex).Select(b => Vector3.Distance(a, b))).Max();
                        Equal(true, Math.Abs(diagonal - 32 * .015625f * MathF.Sqrt(1 + 1f / 16)) < .001f, "main selected R/max(frame) exact size");
                        var state = new InfiniVfxState(); for (int n = 0; n < 4; n++) state.Push(projectile.Center);
                        var texture = (Texture2D)((Array)typeof(SpriteBatch).GetField("textureInfo", TestInstance)!.GetValue(batch)!).GetValue(mainIndex)!;
                        int liveIndex = count(); typeof(InfiniVfxRuntime).GetMethod("DrawSelectedSpriteTrail", BindingFlags.Static | BindingFlags.NonPublic)!
                            .Invoke(null, new object?[] { texture, projectile, entity, SpritePresentation.Entity(data, entity), data.VfxManifest, state, Color.White, 1f });
                        Equal(liveIndex + 1, count(), "real live copy submitted");
                        object liveQuad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(liveIndex)!;
                        Equal(true, SameFrontHandPositionUv(mainQuad, liveQuad), "live copy grip/axis/frame/exact scale agrees");
                    }
                    generated.OnKill(30); // actual event -> snapshot -> enqueue; no private EmitEventSprite shortcut
                    Equal(1, queue.Count, "native on_kill event captures one body copy");
                    object emission = queue[0]!;
                    Equal(legacy ? .1f : .015625f, (float)emission.GetType().GetProperty("Scale")!.GetValue(emission)!,
                        legacy ? "old-driver event clamp retained" : "RED: new20 detached captures exact dynamic body scale");
                    // Encoder/decoder uses existing scale float. No sockets or Send call.
                    object payload = typeof(GeneratedProjectile).GetMethod("CaptureVfxPayload", TestInstance)!
                        .Invoke(generated, new object[] { RuntimeEventKind.OnKill, projectile.Center, (byte)0 })!;
                    using var wire = new MemoryStream(); var writer = new BinaryWriter(wire);
                    typeof(GeneratedProjectile).GetMethod("WriteVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { writer, payload });
                    wire.Position = 0;
                    object decoded = typeof(GeneratedProjectile).GetMethod("ReadVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!
                        .Invoke(null, new object[] { new BinaryReader(wire) })!;
                    var snap = (InfiniVfxProjectileSnapshot)decoded.GetType().GetProperty("Snapshot")!.GetValue(decoded)!;
                    Equal(legacy ? .1f : .015625f, snap.Pose.Scale, "actual event wire preserves selected bounded body scale");
                    // Retire and replace source before actual detached batch. The queue cannot borrow it.
                    projectile.active = false; Terraria.Main.projectile[7] = new Projectile { whoAmI = 7 };
                    projectile.scale = 7; projectile.rotation = -2; projectile.Center = Vector2.Zero; projectile.gfxOffY = -30;
                    batch.End(); flushed = null; recordingDetached = true; On_Main.orig_DrawProjectiles orig = _ => { };
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(true, flushed is not null, "retired-source detached submission reached real FNA queue");
                    if (!legacy) Equal(true, SameFrontHandPositionUv(mainQuad, flushed!), "detached grip/axis/frame/exact scale equals main after source retirement");
                    system.OnWorldUnload(); flushed = null;
                    InfiniVfxRuntime.OnDetachedEvent(data, entity.Id, RuntimeEventKind.OnKill, data.VfxManifest, snap.Center, Vector2.Zero, "decoded_exact_hand", snap);
                    Equal(1, queue.Count, "decoded event snapshot enqueues without source");
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(true, flushed is not null, "decoded snapshot submits after source retirement");
                    if (!legacy) Equal(true, SameFrontHandPositionUv(mainQuad, flushed!), "decoded detached UV/position exactly retains rigid frame");
                    if (legacy) {
                        system.OnWorldUnload();
                        var invalidLegacy = snap with { Pose = snap.Pose with { Scale = .015625f } };
                        Equal(false, InfiniVfxRuntime.OnDetachedEvent(data, entity.Id, RuntimeEventKind.OnKill,
                            data.VfxManifest, snap.Center, Vector2.Zero, "invalid_legacy_scale", invalidLegacy),
                            "legacy decoder/consumer cannot gain new20 exact-scale envelope");
                        Equal(0, queue.Count, "invalid legacy scale emits nothing");
                    }
                    recordingDetached = false; batch.Begin();
                }
            } finally { system.OnWorldUnload(); Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; Terraria.Main.GameViewMatrix = oldView; }
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
