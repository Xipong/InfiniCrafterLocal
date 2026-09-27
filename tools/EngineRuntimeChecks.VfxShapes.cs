using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Real dispatch and FNA CPU queues; reuse the GPU-boundary-only observer.
    private static void WithActiveShape(Action<Projectile, VfxSlotSpec, VfxManifestSpec, SpriteBatch, Func<int>, Func<int, Vector3[]>, Func<int, Color[]>> check)
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
                var projectile = new Projectile { width = 40, height = 20, Center = new Vector2(160, 140), velocity = Vector2.UnitX, scale = 1f };
                var slot = new VfxSlotSpec { Id = "shape", EntityId = "probe", Event = RuntimeEventKind.Periodic,
                    RendererKind = "wavyStrip", Scale = 1f, Density = 0.5f, Duration = 24, RepeatEvery = 40,
                    ParticleSystemId = "none", Alpha = 0.5f, Layer = "BeforeProjectiles" };
                var manifest = new VfxManifestSpec { Slots = new[] { slot } };
                manifest.Budget.MaxDrawCalls = 64;
                check(projectile, slot, manifest, batch, count, positions, colors);
            }
            finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        });
    }

    private static void ProjectileVfxAnchorsReachGeometryAndEvents()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            var oldOwner = Terraria.Main.player[0];
            var owner = (Player)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Player));
            owner.active = true; owner.Center = new Vector2(320, 360);
            Terraria.Main.player[0] = owner; projectile.owner = 0;
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var data = new GeneratedItemData();
            try
            {
                foreach (string anchor in new[] { "self", "field", "owner", "tip", "tipHistory", "velocity", "hitPoint" })
                {
                    slot.RendererKind = "beamLine"; slot.Anchor = anchor; slot.Event = RuntimeEventKind.Periodic;
                    var state = new InfiniVfxState();
                    Vector2 expected = anchor == "owner" ? owner.Center : anchor is "tip" or "tipHistory"
                        ? projectile.Center + Vector2.UnitX * 20f : projectile.Center;
                    InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                    Equal(1, count(), anchor + " beam queues one line");
                    AssertVfxNear(expected + Vector2.UnitX * 24f - Terraria.Main.screenPosition, VfxVertexCenter(positions(0)), anchor + " active anchor");
                    batch.End(); batch.Begin();
                    system.OnWorldUnload(); slot.Event = RuntimeEventKind.OnHit; state = new InfiniVfxState();
                    Vector2 hit = new(700, 800);
                    InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, manifest, ref state, hit);
                    Equal(1, queue.Count, anchor + " exact event persists");
                    Vector2 captured = (Vector2)queue[0]!.GetType().GetProperty("Center")!.GetValue(queue[0])!;
                    AssertVfxNear(anchor == "hitPoint" ? hit : expected, captured, anchor + " event anchor captured");
                }
                owner.active = false; slot.Anchor = "owner"; slot.Event = RuntimeEventKind.Periodic;
                var invalid = new InfiniVfxState();
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref invalid, Color.White);
                Equal(0, count(), "missing owner cannot silently become self");
            }
            finally { Terraria.Main.player[0] = oldOwner; system.OnWorldUnload(); }
        });
        WithLighting((config, lights) =>
        {
            var oldOwner = Terraria.Main.player[0];
            var owner = (Player)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Player));
            owner.active = true; owner.Center = new Vector2(320, 360); Terraria.Main.player[0] = owner;
            try
            {
                var data = new GeneratedItemData();
                var manifest = LightManifest("probe", RuntimeEventKind.Periodic);
                manifest.Slots[0].Anchor = "owner";
                var projectile = new Projectile { owner = 0, Center = new Vector2(160, 140) };
                var state = new InfiniVfxState();
                config.PresentationLightMultiplier = 1f; lights.Clear();
                InfiniVfxRuntime.OnTick(projectile, data, "probe", manifest, ref state);
                Equal(1, lights.Count, "owner light queues one real CPU light");
                // Compare the complete engine queue entry against native AddLight at the owner.
                object actual = lights[0]!; lights.Clear();
                Lighting.AddLight(owner.Center, Color.White.ToVector3() * 0.22f);
                Equal(true, actual.Equals(lights[0]), "periodic cue anchor reaches engine lighting queue");
            }
            finally { Terraria.Main.player[0] = oldOwner; }
        });
    }

    private static void ActiveShapesRespectBudgetsLayersAndParameters()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            var data = new GeneratedItemData();
            foreach (string kind in new[] { "wavyStrip", "fieldPulse", "orbitingMotes", "ghostArc", "impactRing" })
            {
                slot.RendererKind = kind; slot.Layer = "AfterProjectiles"; slot.Blend = "additive";
                var state = new InfiniVfxState { Tick = 4 };
                manifest.Budget.MaxDrawCalls = 0;
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                Equal(0, count(), kind + " zero budget queues nothing");
                manifest.Budget.MaxDrawCalls = 2;
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White, InfiniVfxDrawPass.UnderProjectile);
                Equal(0, count(), kind + " over selection does not draw in under pass");
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White, InfiniVfxDrawPass.OverProjectile);
                Equal(2, count(), kind + " exact positive budget consumed");
                Equal(2, state.DrawCallsThisFrame, kind + " one budget charge per quad");
                foreach (Color c in colors(0)) { Equal((byte)0, c.A, "additive alpha stays zero"); Equal(true, c.R > 0, "premultiplied additive RGB remains visible"); }
                slot.Layer = "BeforeProjectiles";
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White, InfiniVfxDrawPass.UnderProjectile);
                Equal(2, count(), "under and over share one allowance, never reset it");
                batch.End(); batch.Begin();
                manifest.Budget.MaxDrawCalls = 64; state.DrawCallsThisFrame = 0;
                slot.StartTick = 8;
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                Equal(0, count(), "authored start gates active geometry");
                slot.StartTick = 0; slot.Density = 0f; slot.Scale = 1f; slot.PhaseOffset = 0f;
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                int sparse = count(); Vector2 first = VfxVertexCenter(positions(0));
                batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0;
                slot.Density = 1f; slot.Scale = 2f; slot.PhaseOffset = 0.25f;
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                Equal(true, count() > sparse, "density raises bounded tessellation/mote count");
                Equal(true, Vector2.Distance(first, VfxVertexCenter(positions(0))) > 1f, "scale and phase reach geometry");
                batch.End(); batch.Begin();
                slot.Density = 0.5f; slot.Scale = 1f; slot.PhaseOffset = 0f;
            }
        });
    }

    private static void EventSpriteRenderersSnapshotAuthoredTexture()
    {
        WithActiveShape((unusedProjectile, unusedSlot, unusedManifest, batch, count, positions, colors) =>
        {
            Texture2D texture = Terraria.GameContent.TextureAssets.MagicPixel.Value;
            const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", flags)!.GetValue(null)!;
            var wrapper = typeof(InfiniDetachedVfxSystem).GetMethod("DrawProjectiles", flags)!;
            var vertices = typeof(SpriteBatch).GetField("vertexInfo", instance)!;
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? oldCache = sprites.GetValue(null);
            var cache = new InfiniCrafterLocal.Common.Services.RuntimeSpriteCache();
            var textures = (System.Collections.IDictionary)cache.GetType().GetField("_textures", instance)!.GetValue(cache)!;
            var recordType = cache.GetType().GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, "authored_snapshot.png");
            var oldView = Terraria.Main.GameViewMatrix;
            object? observed = null;
            Action<Action<SpriteBatch>, SpriteBatch> flush = (orig, self) =>
            {
                if (count() > 0)
                {
                    Equal(1, count(), "one detached sprite consumed");
                    observed = ((Array)vertices.GetValue(batch)!).GetValue(0);
                }
                orig(self);
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!, flush);
            try
            {
                sprites.SetValue(null, cache);
                // Nonzero art-forward metadata must affect impact sprites, not captured body poses.
                textures.Add(path, Activator.CreateInstance(recordType, texture, 0.37f, 0L)!);
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Viewport(0, 0, 800, 600));
                foreach (string kind in new[] { "projectileAfterimage", "spriteStampTrail", "actorAfterimage", "impactSprite" })
                foreach (int facing in new[] { -1, 1 })
                foreach (float sourceScale in new[] { 0.01f, 1.7f, 12f })
                {
                    system.OnWorldUnload();
                    var projectile = new Projectile { owner = 4, width = 40, height = 20, Center = new Vector2(160, 140),
                        velocity = Vector2.UnitX, rotation = 1.1f, scale = sourceScale, spriteDirection = facing, gfxOffY = 7f };
                    var slot = new VfxSlotSpec { Id = "snapshot", EntityId = "probe", RendererKind = kind,
                        Event = RuntimeEventKind.OnKill, TextureRole = "item", Anchor = "self", Scale = 1.5f,
                        Duration = 24, Alpha = 0.5f, ParticleSystemId = "none" };
                    var manifest = new VfxManifestSpec { Slots = new[] { slot } }; manifest.Budget.MaxDrawCalls = 2;
                    var data = new GeneratedItemData(); data.Visual.SpritePath = path; data.Visual.EffectColor = "blue";
                    InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                    data.Id = "snapshot_pose"; data.RuntimeProgram.Entities = new[] { new RuntimeEntitySpec { Id = "probe" } };
                    data.VfxManifest = manifest;
                    var state = new InfiniVfxState();
                    bool impact = kind == "impactSprite";
                    Vector2 expectedCenter = projectile.Center + (impact ? Vector2.Zero : new Vector2(0, 7));
                    float expectedRotation = impact ? 0f : projectile.rotation;
                    float expectedScale = impact ? slot.Scale : Math.Clamp(sourceScale, 0.1f, 8f) * slot.Scale;
                    SpriteEffects expectedEffects = !impact && facing < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
                    Color tint = RuntimeColorPolicy.Resolve("blue", Color.White);
                    batch.Draw(texture, expectedCenter - Terraria.Main.screenPosition, null, tint * slot.Alpha,
                        expectedRotation - (impact ? 0.37f : 0f), new Vector2(texture.Width, texture.Height) * 0.5f,
                        expectedScale, expectedEffects, 0f);
                    object expectedVertices = ((Array)vertices.GetValue(batch)!).GetValue(0)!;
                    batch.End(); batch.Begin(); observed = null;
                    InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, manifest, ref state, projectile.Center);
                    Equal(1, queue.Count, kind + " event creates one fading sprite");
                    object emission = queue[0]!;
                    Equal(path, (string)emission.GetType().GetProperty("TexturePath")!.GetValue(emission)!, "exact authored texture role");
                    Equal(tint, (Color)emission.GetType().GetProperty("Color")!.GetValue(emission)!, "explicit effect color");
                    Equal(slot.Duration, (int)emission.GetType().GetProperty("Duration")!.GetValue(emission)!, "authored duration");
                    Equal(expectedRotation, (float)emission.GetType().GetProperty("Rotation")!.GetValue(emission)!, kind + " captured rotation, not velocity");
                    Equal(expectedScale, (float)emission.GetType().GetProperty("Scale")!.GetValue(emission)!, "body scale clamp then authored VFX multiplier");
                    AssertVfxNear(expectedCenter, (Vector2)emission.GetType().GetProperty("Center")!.GetValue(emission)!, "captured gfx offset");
                    byte[] packet = EncodeProjectileVfxForCheck(data, projectile, slot.Event, projectile.Center);
                    // Mutation/retirement cannot change the queued snapshot.
                    projectile.active = false;
                    projectile.rotation = -2f; projectile.scale = 0.2f; projectile.spriteDirection = -facing;
                    projectile.gfxOffY = -30; projectile.Center = Vector2.Zero; slot.Scale = 4;
                    // Event snapshot owns presentation; active Draw must not duplicate it.
                    InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                    Equal(0, count(), "event sprite has no active duplicate");
                    batch.End();
                    On_Main.orig_DrawProjectiles orig = _ => { };
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(true, expectedVertices.Equals(observed), kind + " consumed FNA vertices and flipped UVs match captured pose");
                    system.OnWorldUnload(); observed = null; slot.Scale = 1.5f;
                    ReceiveProjectileVfxForCheck(data, packet);
                    Equal(1, queue.Count, "decoded snapshot survives source retirement");
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(true, expectedVertices.Equals(observed), kind + " encoder/decoder to detached FNA preserves pose, scale, UV and impact convention");
                    batch.Begin();
                    system.OnWorldUnload(); data.Visual.SpritePath = ""; state = new InfiniVfxState();
                    InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, manifest, ref state, projectile.Center);
                    Equal(0, queue.Count, "missing path stays silent");
                    data.Visual.SpritePath = path;
                    InfiniVfxRuntime.OnDetachedEvent(data, "probe", slot.Event, manifest, projectile.Center, projectile.velocity, "velocity-only");
                    Equal(impact ? 1 : 0, queue.Count, "velocity-only relay cannot invent a body snapshot; directional impact remains available");
                }
            }
            finally
            {
                system.OnWorldUnload(); sprites.SetValue(null, oldCache); Terraria.Main.GameViewMatrix = oldView;
                textures.Clear(); cache.Dispose(); // No GPU resources belong to the constructor-bypassed shell.
            }
        });
        ProjectileEventSnapshotRelayPreservesAnchors();
    }

    private static void EventShapesUseDetachedFnaQueue()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", statics)!.GetValue(null)!;
            var wrapper = typeof(InfiniDetachedVfxSystem).GetMethod("DrawProjectiles", statics)!;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", statics)!;
            uint oldTick = Terraria.Main.GameUpdateCount;
            var oldView = Terraria.Main.GameViewMatrix;
            batch.End();
            var drains = new System.Collections.Generic.List<int>();
            Vector2 observed = Vector2.Zero;
            Action<Action<SpriteBatch>, SpriteBatch> flush = (orig, self) =>
            {
                drains.Add(count());
                if (count() > 0) observed = VfxVertexCenter(positions(0));
                Equal(false, (bool)typeof(SpriteBatch).GetField("beginCalled", instance)!.GetValue(batch)!, "detached End owns batch closure");
                orig(self);
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!, flush);
            try
            {
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Viewport(0, 0, 800, 600));
                foreach (string kind in new[] { "wavyStrip", "fieldPulse", "orbitingMotes", "ghostArc", "impactRing", "beamLine" })
                {
                    system.OnWorldUnload(); clock.SetValue(null, 100u); drains.Clear();
                    slot.RendererKind = kind; slot.Event = RuntimeEventKind.OnHit; slot.Layer = "AfterProjectiles";
                    manifest.Budget.MaxDrawCalls = 3;
                    var state = new InfiniVfxState();
                    var data = new GeneratedItemData(); data.Visual.EffectColor = "blue";
                    Equal(true, InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, manifest, ref state, projectile.Center), "exact event accepted");
                    Equal(1, queue.Count, kind + " persists geometry after event, even with no dust");
                    slot.Scale = 5f; // queue must snapshot accepted values, not hold mutable DTOs.
                    object emission = queue[0]!;
                    Equal(1f, (float)emission.GetType().GetProperty("Scale")!.GetValue(emission)!, "detached scale captured before DTO mutation");
                    Equal(slot.Duration, (int)emission.GetType().GetProperty("Duration")!.GetValue(emission)!, "duration snapshot");
                    On_Main.orig_DrawProjectiles orig = _ => Equal(0, drains.Count, "over layer does not draw before vanilla");
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(kind == "beamLine" ? 1 : 3, drains[0], kind + " real FNA queue honors per-source cap");
                    Vector2 first = observed;
                    drains.Clear(); clock.SetValue(null, 108u);
                    wrapper.Invoke(null, new object?[] { orig, null });
                    if (kind != "beamLine") Equal(true, Vector2.Distance(first, observed) > 0.1f, kind + " detached geometry animates");
                    drains.Clear(); clock.SetValue(null, 124u);
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(0, drains.Count, "duration prunes detached shape before draw");
                    Equal(0, queue.Count, "expired primitive removed from existing queue");
                    slot.Scale = 1f;
                    // Same queue and budget owner across under/over, with lazy Begin.
                    clock.SetValue(null, 200u); drains.Clear(); manifest.Budget.MaxDrawCalls = 0;
                    InfiniVfxRuntime.EmitPrimitive(data, projectile.Center, projectile.velocity, slot, manifest, "shared");
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(0, drains.Count, "zero allowance does not even open a detached batch");
                    system.OnWorldUnload(); manifest.Budget.MaxDrawCalls = 1;
                    slot.Layer = "BeforeProjectiles";
                    InfiniVfxRuntime.EmitPrimitive(data, projectile.Center, projectile.velocity, slot, manifest, "shared");
                    slot.Layer = "AfterProjectiles";
                    InfiniVfxRuntime.EmitPrimitive(data, projectile.Center, projectile.velocity, slot, manifest, "shared");
                    On_Main.orig_DrawProjectiles sharedOrig = _ => Equal(1, drains.Count, "under batch completes before vanilla");
                    wrapper.Invoke(null, new object?[] { sharedOrig, null });
                    Equal(1, drains.Count, "over cannot replenish shared source budget");
                    Equal(1, drains[0], "one admitted quad across both layers");
                }
            }
            finally { system.OnWorldUnload(); clock.SetValue(null, oldTick); Terraria.Main.GameViewMatrix = oldView; }
        });
    }

    private static void VfxExplicitColorOverridesLegacyPresentation()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            slot.RendererKind = "beamLine"; manifest.Motif.Element = "fire";
            var data = new GeneratedItemData(); data.Visual.Palette = new[] { "red" }; data.Visual.EffectColor = "blue";
            var state = new InfiniVfxState();
            InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.Green);
            foreach (Color tint in colors(0)) Equal(RuntimeColorPolicy.Resolve("blue", Color.White) * slot.Alpha, tint, "explicit color beats contradictory palette and fire motif");
            batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0; data = new GeneratedItemData();
            InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.Green);
            foreach (Color tint in colors(0)) Equal(Color.OrangeRed * slot.Alpha, tint, "absent effectColor preserves historical projectile motif color");
            Equal(Color.Green, InfiniVfxRuntime.PresentationColor(null, Color.Green), "null legacy data retains caller color");
        });
    }

    private static void TipTrailTracksForwardTipHistory()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            slot.RendererKind = "tipTrail"; slot.RepeatEvery = 1;
            var state = new InfiniVfxState();
            var data = new GeneratedItemData();
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            uint oldTick = Terraria.Main.GameUpdateCount;
            try
            {
                InfiniVfxRuntime.OnTick(projectile, data, "probe", manifest, ref state);
                projectile.velocity = Vector2.UnitY;
                clock.SetValue(null, oldTick + 1u);
                InfiniVfxRuntime.OnTick(projectile, data, "probe", manifest, ref state);
                // Re-entering an extra update at the same tick must not duplicate history.
                InfiniVfxRuntime.OnTick(projectile, data, "probe", manifest, ref state);
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                Equal(1, count(), "stationary center with rotating forward tip leaves a real segment");
                AssertVfxNear(projectile.Center + new Vector2(10, 10) - Terraria.Main.screenPosition,
                    VfxVertexCenter(positions(0)), "segment connects historical forward tips, not centers plus latest offset");
                Equal(2, state.HistoryCount, "one sample per world tick");
                var rotating = new RuntimeEntitySpec { Id = "probe" }; rotating.Movement.Code = 14;
                data.RuntimeProgram.Entities = new[] { rotating };
                projectile.velocity = Vector2.UnitX; projectile.rotation = MathHelper.PiOver2;
                AssertVfxNear(projectile.Center + Vector2.UnitY * 20f,
                    InfiniVfxRuntime.ForwardTip(projectile, data, "probe"), "explicit rotating motion uses body axis, not travel");
                batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0; slot.RendererKind = "historyRibbon";
                InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White);
                Equal(0, count(), "center history remains stationary independently");
            }
            finally { clock.SetValue(null, oldTick); }
        });
    }

    private static void ActiveGhostArcQueuesRotatingOpenSweep()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            slot.RendererKind = "ghostArc";
            var state = new InfiniVfxState { Tick = 4 };
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(14, count(), "density selects an open segmented arc");
            Vector2 center = projectile.Center - Terraria.Main.screenPosition;
            Vector2 first = VfxVertexCenter(positions(0));
            Vector2 mean = Vector2.Zero;
            for (int i = 0; i < count(); i++) mean += VfxVertexCenter(positions(i));
            Equal(true, Vector2.Distance(center, mean / count()) > 5f, "open arc is not a full ring");
            Equal(true, colors(0)[0].A < colors(count() - 1)[0].A, "arc fades toward trailing end");
            batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0; state.Tick = 9;
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(true, Vector2.Distance(first, VfxVertexCenter(positions(0))) > 1f, "arc sweeps over time");
        });
    }

    private static void ActiveOrbitingMotesQueueMovingPoints()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            slot.RendererKind = "orbitingMotes";
            var state = new InfiniVfxState { Tick = 4 };
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(5, count(), "density 0.5 selects five orbiting quads, not a cross");
            Vector2 center = projectile.Center - Terraria.Main.screenPosition;
            Vector2 first = VfxVertexCenter(positions(0));
            Equal(true, Math.Abs(Vector2.Distance(center, first) - 18f) < 0.001f, "mote lies on 18px orbit");
            batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0; state.Tick = 9;
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(true, Vector2.Distance(first, VfxVertexCenter(positions(0))) > 1f, "mote orbits with clock");
        });
    }

    private static void ActiveFieldPulseQueuesExpandingRing()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            slot.RendererKind = "fieldPulse";
            var state = new InfiniVfxState { Tick = 4 };
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(true, count() >= 12, "pulse is a closed segmented ring, not a cross");
            Vector2 center = projectile.Center - Terraria.Main.screenPosition;
            float radius = Vector2.Distance(center, VfxVertexCenter(positions(0)));
            Vector2 mean = Vector2.Zero;
            for (int i = 0; i < count(); i++) mean += VfxVertexCenter(positions(i));
            AssertVfxNear(center, mean / count(), "ring surrounds anchor");
            byte alpha = colors(0)[0].A;
            batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0; state.Tick = 16;
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(true, Vector2.Distance(center, VfxVertexCenter(positions(0))) > radius, "pulse expands");
            Equal(true, colors(0)[0].A < alpha, "pulse fades with expansion");
        });
    }

    private static void ActiveWavyStripQueuesAnimatedCurve()
    {
        WithActiveShape((projectile, slot, manifest, batch, count, positions, colors) =>
        {
            var state = new InfiniVfxState { Tick = 4 };
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(true, count() >= 8, "wavy strip is segmented, not a beam alias");
            Vector2 first = VfxVertexCenter(positions(0));
            bool curved = false;
            for (int i = 0; i < count(); i++) curved |= Math.Abs(VfxVertexCenter(positions(i)).Y - (projectile.Center.Y - Terraria.Main.screenPosition.Y)) > 1f;
            Equal(true, curved, "wavy strip has lateral displacement");
            batch.End(); batch.Begin(); state.DrawCallsThisFrame = 0; state.Tick = 9;
            InfiniVfxRuntime.Draw(projectile, new GeneratedItemData(), "probe", manifest, ref state, Color.White);
            Equal(true, Vector2.Distance(first, VfxVertexCenter(positions(0))) > 0.1f, "wave moves with simulation ticks");
        });
    }
}
