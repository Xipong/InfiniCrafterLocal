using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void ComposableMotionBeamVfxSnapshotUsesActualLine()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("""
              {"aim":{"source":"initial","turnOwner":false},
               "beamGeometry":{"lengthPx":120,"widthPx":8,"raycastTiles":false}}
              """);
            var actor = MotionActor(data, owner, new Vector2(0, 2));
            actor.Host.AI();
            var snapshot = InfiniVfxProjectileSnapshot.Capture(actor.Body, data, data.RuntimeProgram.PrimaryEntityId);
            AssertVfxNear(Vector2.UnitX, snapshot.Forward, "VFX follows explicit motion axis, not unrelated velocity");
            AssertVfxNear(actor.Body.Center + new Vector2(120, 0), snapshot.Tip, "VFX uses actual beam endpoint, not body AABB");
        });
    }

    private static void ComposableMotionScaleRateSnapshotPreservesSmallExplicitScale()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("{\"visualScaleRate\":{\"deltaPerUpdate\":0,\"maxScale\":20}}");
            var actor = MotionActor(data, owner, Vector2.UnitX);
            actor.Body.scale = 0.01f;
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            var snapshot = InfiniVfxProjectileSnapshot.Capture(actor.Body, data, entity.Id);
            Equal(0.01f, snapshot.Pose.Scale, "explicit scale-rate body is not clamped to old implicit scale");
            Equal(true, snapshot.IsValidFor(entity), "new declared lower scale remains valid in VFX transport");
            var ordinary = MotionDefinition("{}");
            Equal(false, snapshot.IsValidFor(ordinary.RuntimeProgram.TryGetEntity(ordinary.RuntimeProgram.PrimaryEntityId)),
                "new envelope does not weaken ordinary historical body policy");
        });
    }

    private static void FreeProjectileSpriteTrailPreservesExplicitBodyScale()
    {
        // Both extremes exercise accepted authored values; the controls verify
        // ordinary and collision-only curves keep their historical clamp.
        var cases = new[] {
            (Curve: "visualScaleCurve", Mirror: false, Factor: 2f, Base: 4f, Expected: 32f),
            (Curve: "visualScaleCurve", Mirror: false, Factor: .25f, Base: .25f, Expected: .015625f),
            (Curve: "hitboxCurve", Mirror: true, Factor: 2f, Base: 4f, Expected: 32f),
            (Curve: "hitboxCurve", Mirror: true, Factor: .25f, Base: .25f, Expected: .015625f),
            (Curve: "hitboxCurve", Mirror: false, Factor: 2f, Base: 4f, Expected: 8f),
            (Curve: "ordinary", Mirror: false, Factor: 1f, Base: 4f, Expected: 8f),
        };
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) => {
            using var actors = new NativeActorState(); using var cache = new BorrowedSpriteCache();
            var system = new InfiniDetachedVfxSystem();
            var queue = (IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            try {
                Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(CpuTexture(1, 1));
                var texture = CpuTexture(64, 16);
                foreach (var c in cases) {
                    system.OnWorldUnload(); MaterialClock(100);
                    string components = c.Curve switch {
                        "visualScaleCurve" => "{\"visualScaleCurve\":{\"startScale\":" + c.Factor.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"endScale\":" + c.Factor.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"startDelayTicks\":0,\"durationTicks\":12,\"curve\":\"linear\"}}",
                        "hitboxCurve" => "{\"hitboxCurve\":{\"startScale\":" + c.Factor.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"endScale\":" + c.Factor.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"startDelayTicks\":0,\"durationTicks\":12,\"curve\":\"linear\",\"mirrorToSprite\":" + (c.Mirror ? "true" : "false") + "}}",
                        _ => "{}",
                    };
                    var data = MotionDefinition(components, body => {
                        body["visual"]!["assetMode"] = "reuse_item_icon";
                        body["visual"]!["scale"] = c.Base;
                        body["hitbox"]!["drawScale"] = c.Base;
                    });
                    string path = Path.Combine(Terraria.Program.SavePath, "free-scale.png");
                    data.Visual.SpritePath = path; data.Visual.RenderSizePx = 32; data.Visual.ForwardAngleDegrees = 0;
                    if (!cache.Textures.Contains(path)) cache.Textures.Add(path, Activator.CreateInstance(cache.Record, texture, 1f, 0L)!);
                    var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                    var actor = MotionActor(data, owner, Vector2.UnitX);
                    actor.Host.AI(); Terraria.Main.dedServ = false;
                    var projectile = actor.Body;
                    var snapshot = InfiniVfxProjectileSnapshot.Capture(projectile, data, entity.Id);
                    Equal(c.Expected, snapshot.Pose.Scale, c.Curve + " snapshot matches authored-body policy");
                    Equal(true, snapshot.IsValidFor(entity), "captured scale is admissible for its source entity");
                    Equal(false, (snapshot with { Pose = snapshot.Pose with { Scale = 128.01f } }).IsValidFor(entity),
                        "even explicit scale cannot exceed the existing network envelope");
                    Equal(false, (snapshot with { Pose = snapshot.Pose with { Scale = .009f } }).IsValidFor(entity),
                        "even explicit scale cannot go below the existing network envelope");
                    if (c.Expected is < .1f or > 8f) {
                        var ordinary = MotionDefinition("{}");
                        Equal(false, snapshot.IsValidFor(ordinary.RuntimeProgram.TryGetEntity(ordinary.RuntimeProgram.PrimaryEntityId)),
                            "an unrelated entity without authored scale cannot accept the expanded envelope");
                    }
                    int bodyIndex = count(); Color light = Color.White;
                    actor.Host.PreDraw(ref light);
                    Equal(bodyIndex + 1, count(), "native body submits one sprite quad");
                    float bodyDiagonal = positions(bodyIndex).SelectMany(a => positions(bodyIndex).Select(b => Vector3.Distance(a, b))).Max();
                    Equal(true, Math.Abs(bodyDiagonal - 32f * c.Expected * MathF.Sqrt(1f + 1f / 16f)) < .01f,
                        "native body uses the expected authored scale");
                    var slot = new VfxSlotSpec { Id = "free_scale", EntityId = entity.Id, Event = RuntimeEventKind.OnHit,
                        RendererKind = "spriteStampTrail", TextureRole = "entity", Anchor = "self", Layer = "AfterProjectiles",
                        Scale = 1, Alpha = 1, Duration = 24, Color = Rgb(255, 255, 255), Blend = "alpha",
                        ParticleSystemId = "none", Density = 0, Spread = 0, RepeatEvery = 0, StartTick = 0 };
                    var manifest = new VfxManifestSpec { Slots = new[] { slot } }; manifest.Budget.MaxDrawCalls = 8;
                    var state = new InfiniVfxState(); for (int i = 0; i < 4; i++) state.Push(projectile.Center);
                    int before = count();
                    typeof(InfiniVfxRuntime).GetMethod("DrawSelectedSpriteTrail", BindingFlags.Static | BindingFlags.NonPublic)!
                        .Invoke(null, new object?[] { texture, projectile, entity, SpritePresentation.Entity(data, entity), manifest, state, Color.White, 1f });
                    Equal(before + 1, count(), "live sprite trail submits a native quad");
                    float diagonal = positions(before).SelectMany(a => positions(before).Select(b => Vector3.Distance(a, b))).Max();
                    Equal(true, Math.Abs(diagonal - 32f * c.Expected * MathF.Sqrt(1f + 1f / 16f)) < .01f, "live trail uses the same body scale");
                    Equal(true, Math.Abs(diagonal - bodyDiagonal) < .01f, "live trail matches the real body quad");
                    Equal(true, InfiniVfxRuntime.OnEvent(projectile, data, entity.Id, RuntimeEventKind.OnHit, manifest, ref state, projectile.Center), "event emitted");
                    Equal(1, queue.Count, "event queues exactly one sprite");
                    Equal(c.Expected, (float)queue[0]!.GetType().GetProperty("Scale")!.GetValue(queue[0])!, "detached event uses same body scale");
                }
            } finally { system.OnWorldUnload(); Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        }));
    }

    private static void ComposableMotionAbsoluteTilePolicyRequiresReachableConsumer()
    {
        foreach (string component in new[] { "attachment", "lashGeometry" }) {
            var root = MotionAdmissionWire(component);
            FrontHandEntity(root)["collision"]!["tileCollide"] = true;
            MotionRefuses(root, component + " cannot promise unexecuted native tile collision");
            FrontHandEntity(root)["collision"]!["tileCollide"] = false;
            MotionAdmits(root, component + " explicit supported tile policy");
        }
        var phased = MotionAdmissionWire("attachment");
        FrontHandEntity(phased)["attachment"]!["window"] = JsonNode.Parse(
            "{\"phase\":\"always\",\"clock\":\"active\",\"startDelayTicks\":0,\"durationTicks\":12}");
        FrontHandEntity(phased)["collision"]!["tileCollide"] = true;
        MotionAdmits(phased, "finite attachment retains collision for its separate free-flight interval");
    }
}
