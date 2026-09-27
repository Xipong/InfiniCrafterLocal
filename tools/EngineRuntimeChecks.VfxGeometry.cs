using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Real FNA CPU vertices; only FlushBatch is intercepted, before GPU upload.
    private static void WithVfxGeometryQueue(Action<SpriteBatch, Texture2D, Func<int>, Func<int, Vector3[]>, Func<int, Color[]>> check)
    {
        WithLighting((config, _) =>
        {
            const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
            var batch = (SpriteBatch)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
            var texture = (Texture2D)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
            GC.SuppressFinalize(batch); GC.SuppressFinalize(texture);
            foreach (string name in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
            {
                var field = typeof(SpriteBatch).GetField(name, flags)!;
                field.SetValue(batch, Array.CreateInstance(field.FieldType.GetElementType()!, 128));
            }
            // Deliberately not 1x1: scale must convert source texels to pixels.
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 2);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 3);
            var count = typeof(SpriteBatch).GetField("numSprites", flags)!;
            var vertices = typeof(SpriteBatch).GetField("vertexInfo", flags)!;
            var oldBatch = Terraria.Main.spriteBatch;
            var oldScreen = Terraria.Main.screenPosition;
            Action<SpriteBatch> flush = self => count.SetValue(self, 0);
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", flags)!, flush);
            T[] Values<T>(int index)
            {
                var result = new List<T>();
                void Visit(object value)
                {
                    if (value is T typed) { result.Add(typed); return; }
                    foreach (var f in value.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                        if (f.FieldType == typeof(T) || (f.FieldType.IsValueType && !f.FieldType.IsPrimitive && !f.FieldType.IsEnum)) Visit(f.GetValue(value)!);
                }
                Visit(((Array)vertices.GetValue(batch)!).GetValue(index)!);
                return result.ToArray();
            }
            try
            {
                config.DrawBudgetMultiplier = 1f;
                Terraria.Main.spriteBatch = batch;
                Terraria.Main.screenPosition = new Vector2(40, 60);
                batch.Begin();
                check(batch, texture, () => (int)count.GetValue(batch)!, Values<Vector3>, Values<Color>);
            }
            finally
            {
                if ((bool)typeof(SpriteBatch).GetField("beginCalled", flags)!.GetValue(batch)!) batch.End();
                Terraria.Main.spriteBatch = oldBatch;
                Terraria.Main.screenPosition = oldScreen;
            }
        });
    }

    private static void AssertVfxNear(Vector2 expected, Vector2 actual, string label)
        => Equal(true, Vector2.Distance(expected, actual) < 0.001f, label + ": expected " + expected + ", got " + actual);

    private static Vector2 VfxVertexCenter(Vector3[] vertices)
    {
        Equal(4, vertices.Length, "one queued quad has four positions");
        Vector2 result = Vector2.Zero;
        foreach (Vector3 vertex in vertices) result += new Vector2(vertex.X, vertex.Y);
        return result / 4f;
    }

    private static void ActiveVfxPrimitiveGeometryUsesPixelUnits()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            var draw = typeof(InfiniVfxRuntime).GetMethod("DrawLine", BindingFlags.Static | BindingFlags.NonPublic)!;
            foreach (Vector2 delta in new[] { new Vector2(30, 0), new Vector2(0, 30), new Vector2(-18, 24) })
            {
                Vector2 start = new(10, 20), end = start + delta;
                int index = count();
                draw.Invoke(null, new object[] { texture, start, end, Color.White, 4f });
                Equal(index + 1, count(), "line queues exactly one quad");
                Vector3[] points = positions(index);
                AssertVfxNear((start + end) * 0.5f, VfxVertexCenter(points), "line centered on authored segment");
                Vector2 direction = Vector2.Normalize(delta), normal = new(-direction.Y, direction.X);
                float minAlong = float.MaxValue, maxAlong = float.MinValue, minAcross = float.MaxValue, maxAcross = float.MinValue;
                foreach (Vector3 p in points)
                {
                    Vector2 relative = new Vector2(p.X, p.Y) - start;
                    float along = Vector2.Dot(relative, direction), across = Vector2.Dot(relative, normal);
                    minAlong = Math.Min(minAlong, along); maxAlong = Math.Max(maxAlong, along);
                    minAcross = Math.Min(minAcross, across); maxAcross = Math.Max(maxAcross, across);
                }
                Equal(true, Math.Abs(minAlong) < 0.001f && Math.Abs(maxAlong - 30f) < 0.001f, "texel dimensions do not multiply length");
                Equal(true, Math.Abs(minAcross + 2f) < 0.001f && Math.Abs(maxAcross - 2f) < 0.001f, "width centered and measured in pixels");
            }
            int before = count();
            draw.Invoke(null, new object[] { texture, Vector2.One, Vector2.One, Color.White, 4f });
            Equal(before, count(), "zero segment queues nothing");
        });
    }

    private static void ActiveVfxBlendHonorsAuthoredMode()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            // Inject only the CPU texture asset; use the real Draw dispatch and FNA queue.
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            var asset = (ReLogic.Content.Asset<Texture2D>)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(ReLogic.Content.Asset<Texture2D>));
            foreach (var field in asset.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                if (field.FieldType == typeof(Texture2D)) field.SetValue(asset, texture);
            asset.GetType().GetProperty("State")!.SetValue(asset, ReLogic.Content.AssetState.Loaded);
            try
            {
                Terraria.GameContent.TextureAssets.MagicPixel = asset;
                var data = new GeneratedItemData();
                var slot = new VfxSlotSpec { EntityId = "probe", Event = RuntimeEventKind.Periodic, RendererKind = "beamLine", Scale = 1f, Alpha = 0.5f, Layer = "BeforeProjectiles" };
                var manifest = new VfxManifestSpec { Slots = new[] { slot } }; manifest.Budget.MaxDrawCalls = 2;
                var projectile = new Projectile { Center = new Vector2(100, 100), velocity = Vector2.UnitY };
                var state = new InfiniVfxState();
                Color tint = new(200, 100, 50, 255);
                foreach (string blend in new[] { "alpha", "additive" })
                {
                    slot.Blend = blend;
                    int index = count();
                    InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, tint, InfiniVfxDrawPass.UnderProjectile);
                    Equal(index + 1, count(), "authored beam queues one sprite");
                    Color expected = tint * slot.Alpha;
                    if (blend == "additive") expected.A = 0;
                    foreach (Color color in colors(index)) Equal(expected, color, blend + " vertex tint retains opacity-scaled RGB");
                    Equal(4, colors(index).Length, "observe every vertex tint");
                    AssertVfxNear(new Vector2(100, 124) - Terraria.Main.screenPosition, VfxVertexCenter(positions(index)), "beam follows velocity in world space");
                }
                Equal(2, state.DrawCallsThisFrame, "shared budget charged exactly");
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, tint);
                Equal(2, count(), "exhausted allowance cannot queue another sprite");
            }
            finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        });
    }

    private static void ActiveVfxSpriteTrailMatchesBodyPose()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            var draw = typeof(InfiniVfxRuntime).GetMethod("DrawSpriteTrail", BindingFlags.Static | BindingFlags.NonPublic)!;
            var manifest = new VfxManifestSpec(); manifest.Budget.MaxDrawCalls = 1;
            var state = new InfiniVfxState();
            for (int i = 0; i < 3; i++) state.Push(new Vector2(100, 80));
            var projectile = new Projectile { velocity = Vector2.UnitX, rotation = 1.1f, spriteDirection = -1, gfxOffY = 7f, scale = 1f };
            draw.Invoke(null, new object[] { texture, projectile, manifest, state, Color.White, 1f });
            Equal(1, count(), "one populated afterimage sample");
            Vector3[] points = positions(0);
            AssertVfxNear(new Vector2(100, 87) - Terraria.Main.screenPosition, VfxVertexCenter(points), "afterimage uses body gfxOffY");
            // FNA's quad footprint follows current body rotation, not the unrelated velocity angle.
            Vector2 edge = new Vector2(points[1].X - points[0].X, points[1].Y - points[0].Y);
            AssertVfxNear(projectile.rotation.ToRotationVector2() * texture.Width, edge, "afterimage keeps current body pose including spin");
            batch.Draw(texture, new Vector2(100, 87) - Terraria.Main.screenPosition, null, Color.White * 0.9f,
                projectile.rotation, new Vector2(texture.Width, texture.Height) * 0.5f, 1f, SpriteEffects.FlipHorizontally, 0f);
            var queuedVertices = (Array)typeof(SpriteBatch).GetField("vertexInfo", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(batch)!;
            Equal(true, queuedVertices.GetValue(1)!.Equals(queuedVertices.GetValue(0)), "afterimage has body pose and flipped UVs, not only matching bounds");
        });
    }

    private static void RuntimeGeometryUsesWorldPixelsAndForwardAxis()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            var asset = (ReLogic.Content.Asset<Texture2D>)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(ReLogic.Content.Asset<Texture2D>));
            foreach (var field in asset.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                if (field.FieldType == typeof(Texture2D)) field.SetValue(asset, texture);
            asset.GetType().GetProperty("State")!.SetValue(asset, ReLogic.Content.AssetState.Loaded);
            try
            {
                Terraria.GameContent.TextureAssets.MagicPixel = asset;
                foreach (Vector2 direction in new[] { Vector2.UnitX, Vector2.UnitY, -Vector2.UnitX })
                foreach (int movement in new[] { 0, 18, 14, 16, 17 })
                {
                    var projectile = new Projectile { Center = new Vector2(100, 120), velocity = direction, rotation = direction.ToRotation() + MathHelper.PiOver2, scale = 1f };
                    var generated = Attach(projectile);
                    var entity = Entity(); entity.Visual.AssetMode = "runtime_geometry";
                    entity.Movement.Code = movement;
                    entity.Hitbox.WidthPx = 30; entity.Hitbox.HeightPx = 20;
                    generated.Configure(new GeneratedItemData(), entity, 0, 8, direction);
                    var draw = generated.GetType().GetMethod("DrawRuntimeGeometry", BindingFlags.Instance | BindingFlags.NonPublic)!;
                    int index = count();
                    draw.Invoke(generated, new object[] { Color.White });
                    Equal(index + 1, count(), "runtime body queues one quad");
                    Vector3[] points = positions(index);
                    AssertVfxNear(projectile.Center - Terraria.Main.screenPosition, VfxVertexCenter(points), "runtime body is centered, independent of source dimensions");
                    Vector2 edge = new(points[1].X - points[0].X, points[1].Y - points[0].Y);
                    // Whip sets a native-sprite quarter turn too (Executors.Whip).
                    // Only actual rotating motion 14/16/17 owns a distinct rotation.
                    Vector2 expected = movement is 14 or 16 or 17 ? projectile.rotation.ToRotationVector2() : direction;
                    AssertVfxNear(expected * 30f, edge, "primitive forward/spin axis for movement " + movement);
                }
            }
            finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        });
    }

    private static void ActiveVfxNoneParticleDoesNotEmitDust()
    {
        WithLighting((config, lights) =>
        {
            config.ParticleSpawnMultiplier = 1f;
            var data = new GeneratedItemData();
            var projectile = new Projectile { Center = new Vector2(100, 100), velocity = Vector2.UnitX };
            // Observe the real emission entry point without fabricating a Dust result.
            Func<Vector2, int, Vector2?, int, Color, float, Dust> rejectDust = (p, t, v, a, c, s) =>
                throw new InvalidOperationException("authored particleSystemId=none reached Dust.NewDustPerfect");
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(Dust).GetMethod("NewDustPerfect")!, rejectDust);
            foreach (string kind in new[] { "historyRibbon", "tipTrail", "beamLine", "fieldPulse", "projectileAfterimage", "childMotes", "impactRing" })
            {
                var manifest = new VfxManifestSpec { Slots = new[] { new VfxSlotSpec {
                    Id = "no_dust", EntityId = "probe", Event = RuntimeEventKind.Periodic,
                    RendererKind = kind, ParticleSystemId = "none", RepeatEvery = 1,
                } } };
                var state = new InfiniVfxState();
                InfiniVfxRuntime.OnTick(projectile, data, "probe", manifest, ref state);
                Equal(0, state.ParticlesTotal, kind + " none does not spend particle allowance");
                Equal(1, state.LastSlotEmission.Count, kind + " exact event bookkeeping remains live");
                manifest.Slots[0].Event = RuntimeEventKind.OnHit;
                Equal(true, InfiniVfxRuntime.OnEvent(projectile, data, "probe", RuntimeEventKind.OnHit, manifest, ref state, projectile.Center), "event accepted without dust downgrade");
                Equal(0, state.ParticlesTotal, kind + " event none also preserves allowance");
            }
            var lightManifest = LightManifest("probe", RuntimeEventKind.Periodic);
            lightManifest.Slots[0].ParticleSystemId = "none";
            var lightState = new InfiniVfxState();
            lights.Clear();
            InfiniVfxRuntime.OnTick(projectile, data, "probe", lightManifest, ref lightState);
            Equal(1, lights.Count, "none dust does not suppress an independently authored light cue");
        });
    }

    private static void ActiveVfxHistoryUsesValidSamples()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            var trail = typeof(InfiniVfxRuntime).GetMethod("DrawTrail", BindingFlags.Static | BindingFlags.NonPublic)!;
            var manifest = new VfxManifestSpec(); manifest.Budget.MaxDrawCalls = 1;
            var state = new InfiniVfxState();
            state.Push(Vector2.Zero); state.Push(new Vector2(30, 0)); state.Push(new Vector2(30, 0));
            object[] args = { texture, manifest, state, Color.White, 2f };
            trail.Invoke(null, args);
            Equal(1, count(), "origin is a valid sample and duplicate segment does not consume allowance");
            Equal(1, state.DrawCallsThisFrame, "only real quad charged");
            AssertVfxNear(new Vector2(15, 0) - Terraria.Main.screenPosition, VfxVertexCenter(positions(0)), "history is already world-center space");
            var fresh = new InfiniVfxState(); fresh.Push(new Vector2(90, 80));
            args[2] = fresh; trail.Invoke(null, args);
            Equal(1, count(), "uninitialized history cannot create a segment to world origin");
            Equal(0, fresh.DrawCallsThisFrame, "empty history costs no draw");
        });
    }
}
