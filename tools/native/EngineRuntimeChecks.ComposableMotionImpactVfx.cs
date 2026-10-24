using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Test-only observer: all product APIs/helpers exist in the pre-fix snapshot.
    // Parent alone compiles/runs this against frozen RED and current GREEN products.
    private static void ComposableMotionImpactEventRotation() => MotionImpactEvent("rotation");
    private static void ComposableMotionImpactEventHandAttachment() => MotionImpactEvent("front_hand");
    private static void ComposableMotionImpactPeriodicRotation() => MotionImpactPeriodic("rotation", .75f);
    private static void ComposableMotionImpactPeriodicHandAttachment() => MotionImpactPeriodic("front_hand", .75f);
    private static void ComposableMotionImpactPeriodicScaleRate() => MotionImpactPeriodic("scale_rate", .01f);
    private static void ComposableMotionImpactPeriodicHandCurve() => MotionImpactPeriodic("hand_curve", .01f);

    private static GeneratedItemData MotionImpactDefinition(string variant)
    {
        string components = variant switch {
            "rotation" => """
                {"rotation":{"mode":"spin","offsetRadians":0,"radiansPerUpdate":0.25}}
                """,
            "front_hand" => """
                {"aim":{"source":"initial","turnOwner":false},
                 "attachment":{"anchor":"front_hand","axisOffsetPx":17,"normalOffsetPx":9}}
                """,
            "scale_rate" => """
                {"visualScaleRate":{"deltaPerUpdate":0,"maxScale":20}}
                """,
            "hand_curve" => """
                {"aim":{"source":"initial","turnOwner":false},
                 "attachment":{"anchor":"front_hand","axisOffsetPx":17,"normalOffsetPx":9},
                 "visualScaleCurve":{"startScale":0.25,"endScale":0.25,"startDelayTicks":0,"durationTicks":12,"curve":"linear"}}
                """,
            _ => throw new InvalidOperationException("unknown impact observer variant"),
        };
        var data = MotionDefinition(components);
        var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
        entity.Visual.ImpactSpritePath = Path.Combine(Terraria.Program.SavePath, "motion_impact_" + variant + ".png");
        return data;
    }

    private static VfxManifestSpec MotionImpactManifest(string entityId, string eventName)
    {
        var manifest = new VfxManifestSpec { Slots = new[] {
            new VfxSlotSpec { Id = "motion_impact_copy", EntityId = entityId, Event = eventName,
                RendererKind = "spriteStampTrail", TextureRole = "impact", Anchor = "self", Layer = "AfterProjectiles",
                Scale = .4f, Alpha = 1, Duration = 24, Color = Rgb(255, 255, 255), Blend = "alpha",
                ParticleSystemId = "none", Density = 0, Spread = 0, RepeatEvery = 0, StartTick = 0 }
        } };
        manifest.Budget.MaxDrawCalls = 8;
        return manifest;
    }

    private static void MotionImpactSelection(SpritePresentationSelection selected)
    {
        Equal(true, selected.ImpactTexture, "actual textureRole=impact resolves dedicated PNG");
        Equal<int?>(null, selected.RenderSizePx, "impact has no main-body render extent");
        Equal<float?>(null, selected.ForwardAngleDegrees, "impact has no main-body forward axis");
        Equal(true, selected.Grip is null, "impact has no body grip");
        Equal(false, selected.FrontHandBody, "impact is not the hand-held body");
    }

    private static void MotionImpactEvent(string variant)
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var system = new InfiniDetachedVfxSystem();
            var queue = (IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            try {
                system.OnWorldUnload(); MaterialClock(100);
                var data = MotionImpactDefinition(variant);
                var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                MotionImpactSelection(SpritePresentation.Resolve(data, entity.Id, "impact"));
                var actor = MotionActor(data, owner, new Vector2(0, 3));
                var body = actor.Body;
                Terraria.Main.dedServ = false;
                body.Center = new Vector2(310, 250); body.rotation = .61f; body.scale = .75f;
                body.spriteDirection = -1; body.gfxOffY = 7;
                var manifest = MotionImpactManifest(entity.Id, RuntimeEventKind.OnKill);
                var state = new InfiniVfxState();
                // Real public event -> snapshot -> EmitEventSprite -> detached queue.
                // No texture is loaded/allocated to admit this event.
                Equal(true, InfiniVfxRuntime.OnEvent(body, data, entity.Id, RuntimeEventKind.OnKill,
                    manifest, ref state, body.Center), variant + " actual event emitted without exception");
                Equal(1, queue.Count, variant + " exactly one detached sprite, not empty emission");
                object emission = queue[0]!;
                object? Field(string name) => emission.GetType().GetProperty(name)!.GetValue(emission);
                Equal(entity.Visual.ImpactSpritePath, (string)Field("TexturePath")!, "queued exact dedicated impact PNG");
                Equal(true, (bool)Field("HasCapturedPose")!, "event freezes raw projectile pose");
                Equal(body.rotation, (float)Field("Rotation")!, "dedicated impact keeps raw native rotation");
                Equal(body.scale * manifest.Slots[0].Scale!.Value, (float)Field("Scale")!, "event retains captured scale times effect-local scale");
                Equal(SpriteEffects.FlipHorizontally, (SpriteEffects)Field("Effects")!, "captured flip remains unchanged");
                AssertVfxNear(body.Center + new Vector2(0, body.gfxOffY), (Vector2)Field("Center")!, "event position remains source center plus gfx offset");
                Equal(true, Field("HandAnchor") is null, "no frozen hand/body origin: detached renderer uses centered impact origin");
                Equal(true, Field("RenderSizePx") is null, "no forced main-body frame scale");
            } finally { system.OnWorldUnload(); }
        });
    }

    private static void MotionImpactPeriodic(string variant, float nativeScale)
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) => {
            using var actors = new NativeActorState(); using var cache = new BorrowedSpriteCache();
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            try {
                Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(CpuTexture(1, 1));
                var data = MotionImpactDefinition(variant);
                var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                var selected = SpritePresentation.Resolve(data, entity.Id, "impact");
                MotionImpactSelection(selected);
                // Constructor-bypassed FNA shell, not a GPU Texture2D allocation.
                var texture = CpuTexture(64, 16);
                cache.Textures.Add(selected.Path, Activator.CreateInstance(cache.Record, texture, 1.27f, 0L)!);
                var actor = MotionActor(data, owner, new Vector2(0, 3)); var body = actor.Body;
                Terraria.Main.dedServ = false;
                body.Center = new Vector2(310, 250); body.rotation = .61f; body.scale = nativeScale;
                body.spriteDirection = -1; body.gfxOffY = 7;
                var manifest = MotionImpactManifest(entity.Id, RuntimeEventKind.Periodic);
                var state = new InfiniVfxState(); for (int n = 0; n < 4; n++) state.Push(body.Center);
                // Same real private draw entry as FrontHandNativePoseAndContact.
                int first = count();
                typeof(InfiniVfxRuntime).GetMethod("DrawSelectedSpriteTrail", BindingFlags.Static | BindingFlags.NonPublic)!
                    .Invoke(null, new object?[] { texture, body, entity, selected, manifest, state, Color.White, manifest.Slots[0].Scale!.Value });
                Equal(first + 1, count(), variant + " periodic selected-impact path submits one real FNA quad");
                MotionImpactQuad(batch, first, positions(first), body, texture, manifest.Slots[0].Scale!.Value, variant);
                // Also exercise public periodic dispatch and real cache selection, not just the adapter.
                int dispatched = count();
                state.DrawCallsThisFrame = 0;
                InfiniVfxRuntime.Draw(body, data, entity.Id, manifest, ref state, Color.White);
                Equal(dispatched + 1, count(), variant + " public periodic spriteStampTrail=impact dispatch draws");
                MotionImpactQuad(batch, dispatched, positions(dispatched), body, texture, manifest.Slots[0].Scale!.Value, variant);
            } finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        }));
    }

    private static void MotionImpactQuad(SpriteBatch batch, int index, Vector3[] vertices,
        Projectile body, Texture2D texture, float effectScale, string label)
    {
        AssertVfxNear(body.Center - Terraria.Main.screenPosition + new Vector2(0, body.gfxOffY),
            VfxVertexCenter(vertices), label + " actual impact quad has centered origin, not grip/attachment offset");
        float scale = Math.Max(.05f, body.scale * effectScale);
        float diagonal = vertices.SelectMany(a => vertices.Select(b => Vector3.Distance(a, b))).Max();
        Equal(true, Math.Abs(diagonal - new Vector2(texture.Width, texture.Height).Length() * scale) < .001f,
            label + " impact retains effect-local pixel scale and historical .05 floor");
        // Paired UV corners observe raw rotation independently of product pose helpers.
        object quad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(index)!;
        var uv = CpuVertexValues<Vector2>(quad); var pos = CpuVertexValues<Vector3>(quad);
        float minU = uv.Min(v => v.X), maxU = uv.Max(v => v.X), minV = uv.Min(v => v.Y);
        int left = Array.FindIndex(uv, v => v.X == minU && v.Y == minV);
        int right = Array.FindIndex(uv, v => v.X == maxU && v.Y == minV);
        Equal(true, left >= 0 && right >= 0, label + " native UV corners exist");
        Vector3 edge = pos[right] - pos[left];
        Vector2 expected = body.rotation.ToRotationVector2() * (body.spriteDirection < 0 ? -1f : 1f);
        AssertVfxNear(expected, new Vector2(edge.X, edge.Y).SafeNormalize(Vector2.Zero), label + " raw rotation with captured horizontal flip");
    }
}
