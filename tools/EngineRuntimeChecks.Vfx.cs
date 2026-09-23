using System;
using System.Collections;
using System.Reflection;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.Graphics.Light;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private delegate Texture2D? CacheGetOriginal(RuntimeSpriteCache self, string path, out float angle);
    private delegate Texture2D? CacheGetHook(CacheGetOriginal orig, RuntimeSpriteCache self, string path, out float angle);

    private static void DetachedLayersOwnSpriteBatch()
    {
        WithLighting((config, _) =>
        {
            // CPU shells only: skip constructors which allocate a GraphicsDevice,
            // but run real FNA Begin/Draw/End and vertex queuing. FlushBatch alone
            // is replaced at the GPU boundary by an observer/drain.
            var batch = (SpriteBatch)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
            var texture = (Texture2D)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
            GC.SuppressFinalize(batch);
            GC.SuppressFinalize(texture);
            var flags = BindingFlags.Instance | BindingFlags.NonPublic;
            foreach (string field in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
            {
                var info = typeof(SpriteBatch).GetField(field, flags)!;
                info.SetValue(batch, Array.CreateInstance(info.FieldType.GetElementType()!, 16));
            }
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 16);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 16);
            var begun = typeof(SpriteBatch).GetField("beginCalled", flags)!;
            var queued = typeof(SpriteBatch).GetField("numSprites", flags)!;
            var oldBatch = Terraria.Main.spriteBatch;
            var oldView = Terraria.Main.GameViewMatrix;
            var oldScreen = Terraria.Main.screenPosition;
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? oldCache = sprites.GetValue(null);
            var cache = new RuntimeSpriteCache();
            var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", flags)!.GetValue(cache)!;
            var recordType = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, "cpu_batch_probe.png");
            textures.Add(path, Activator.CreateInstance(recordType, texture, 0f, 0L)!);
            var system = new InfiniDetachedVfxSystem();
            var type = typeof(InfiniDetachedVfxSystem);
            var drawLayer = type.GetMethod("DrawLayer", BindingFlags.Static | BindingFlags.NonPublic)!;
            var wrapper = type.GetMethod("DrawProjectiles", BindingFlags.Static | BindingFlags.NonPublic)!;
            var drains = new System.Collections.Generic.List<int>();
            Action<SpriteBatch> observeFlush = self => {
                Equal(true, ReferenceEquals(batch, self), "only isolated batch reaches GPU boundary");
                Equal(false, (bool)begun.GetValue(self)!, "real End closes batch before flush");
                drains.Add((int)queued.GetValue(self)!);
                queued.SetValue(self, 0); // only the GPU-bound queue drain is substituted
            };
            using var flushHook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", flags)!, observeFlush);
            try
            {
                Terraria.Main.spriteBatch = batch;
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Viewport(0, 0, 800, 600));
                Terraria.Main.GameViewMatrix.Zoom = new Vector2(1.25f);
                Terraria.Main.screenPosition = new Vector2(40, 60);
                sprites.SetValue(null, cache);
                config.DrawBudgetMultiplier = 1f;
                system.OnWorldUnload();
                void Enqueue(string key, string layer, int budget = 8) => InfiniDetachedVfxSystem.Enqueue(
                    key, path, layer, new Vector2(160, 160), 0f, 1f, 1f, Color.White, 5, budget);
                Enqueue("under", "BeforeProjectiles");
                Enqueue("over", "AfterProjectiles");
                int originalCalls = 0;
                On_Main.orig_DrawProjectiles orig = _ => {
                    originalCalls++;
                    Equal(false, (bool)begun.GetValue(batch)!, "under layer closed before vanilla batch");
                    batch.Begin();
                    batch.End();
                };
                wrapper.Invoke(null, new object?[] { orig, null });
                Equal(1, originalCalls, "vanilla callback preserved");
                Equal("1,0,1", string.Join(",", drains), "under / vanilla / over queues are separate");
                Equal(false, (bool)begun.GetValue(batch)!, "over layer closes batch");
                Equal(Terraria.Main.GameViewMatrix.TransformationMatrix, (Matrix)typeof(SpriteBatch).GetField("transformMatrix", flags)!.GetValue(batch)!, "world transform retained");
                Equal(true, ReferenceEquals(BlendState.AlphaBlend, typeof(SpriteBatch).GetField("blendState", flags)!.GetValue(batch)), "world alpha blend retained");
                Equal(true, ReferenceEquals(Terraria.Main.DefaultSamplerState, typeof(SpriteBatch).GetField("samplerState", flags)!.GetValue(batch)), "world sampler retained");

                // Nothing eligible: do not open an unnecessary batch or touch GPU.
                system.OnWorldUnload(); drains.Clear();
                Enqueue("zero", "BeforeProjectiles", 0);
                drawLayer.Invoke(null, new object[] { "BeforeProjectiles" });
                drawLayer.Invoke(null, new object[] { "AfterProjectiles" });
                Equal(0, drains.Count, "zero budget / unmatched layer do not flush");
                system.OnWorldUnload();
                object cachedTexture = textures[path]!;
                textures.Remove(path); // missing local file, no GPU load attempt
                Enqueue("missing", "BeforeProjectiles");
                drawLayer.Invoke(null, new object[] { "BeforeProjectiles" });
                Equal(0, drains.Count, "missing texture does not open a batch");
                textures.Add(path, cachedTexture);

                // A throw after the first queued sprite must still close its batch.
                system.OnWorldUnload(); drains.Clear();
                Enqueue("first", "BeforeProjectiles"); Enqueue("second", "BeforeProjectiles");
                int lookups = 0;
                CacheGetHook failSecondLookup = (CacheGetOriginal original, RuntimeSpriteCache self, string key, out float angle) => {
                    if (++lookups == 2) throw new InvalidOperationException("injected lookup failure");
                    return original(self, key, out angle);
                };
                using (var lookupHook = new MonoMod.RuntimeDetour.Hook(typeof(RuntimeSpriteCache).GetMethod("TryGet", new[] { typeof(string), typeof(float).MakeByRefType() })!, failSecondLookup))
                {
                    bool rejected = false;
                    try { drawLayer.Invoke(null, new object[] { "BeforeProjectiles" }); }
                    catch (TargetInvocationException error) when (error.InnerException?.Message == "injected lookup failure") { rejected = true; }
                    Equal(true, rejected, "original exception propagates");
                }
                Equal("1", string.Join(",", drains), "finally ends partial batch exactly once");
                Equal(false, (bool)begun.GetValue(batch)!, "exception leaves no open batch");
                batch.Begin(); batch.End(); // next vanilla batch still works

                // Never close somebody else's batch if our Begin itself rejects.
                system.OnWorldUnload(); drains.Clear();
                Enqueue("foreign_batch", "BeforeProjectiles");
                batch.Begin();
                try
                {
                    bool rejected = false;
                    try { drawLayer.Invoke(null, new object[] { "BeforeProjectiles" }); }
                    catch (TargetInvocationException error) when (error.InnerException is InvalidOperationException) { rejected = true; }
                    Equal(true, rejected, "already-open foreign batch is not silently reused");
                    Equal(true, (bool)begun.GetValue(batch)!, "failed Begin must not End a foreign batch");
                    Equal(0, drains.Count, "failed Begin causes no flush");
                }
                finally { batch.End(); }
            }
            finally
            {
                system.OnWorldUnload();
                sprites.SetValue(null, oldCache);
                Terraria.Main.spriteBatch = oldBatch;
                Terraria.Main.GameViewMatrix = oldView;
                Terraria.Main.screenPosition = oldScreen;
                textures.Clear(); // CPU-only texture has no graphics resource to dispose
                cache.Dispose();
            }
        });
    }

    private static void DrawBudgetsResetWithoutWorldTick()
    {
        WithLighting((config, _) =>
        {
            config.DrawBudgetMultiplier = 1f;
            var failures = new System.Collections.Generic.List<string>();
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            var system = new InfiniDetachedVfxSystem();
            try
            {
                clock.SetValue(null, 100u);
                try
                {
                    var data = GeneratedItemData.Placeholder();
                    data.VfxManifest = VfxManifestSpec.Empty(); // no texture lookup / GPU draw
                    var entity = Entity();
                    entity.Visual.AssetMode = "no_asset";
                    var projectile = new Projectile { active = true, damage = 37 };
                    var generated = Attach(projectile);
                    generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                    var state = (InfiniVfxState)generated.GetType().GetField("_vfxState", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(generated)!;
                    state.LastGameUpdate = Terraria.Main.GameUpdateCount;
                    state.ParticlesThisTick = 3;
                    state.ParticlesTotal = 7;
                    state.DrawCallsThisFrame = 1;
                    var budget = new VfxManifestSpec();
                    budget.Budget.MaxDrawCalls = 1;
                    var spend = typeof(InfiniVfxRuntime).GetMethod("SpendDraw", BindingFlags.Static | BindingFlags.NonPublic)!;
                    for (int frame = 0; frame < 3; frame++)
                    {
                        Color light = Color.White;
                        Equal(false, generated.PreDraw(ref light), "canonical PreDraw no vanilla proxy sprite");
                        Equal(0, state.DrawCallsThisFrame, "active reset at draw invocation, frozen world tick");
                        Equal(true, (bool)spend.Invoke(null, new object[] { budget, state, 1 })!, "active draw allowance restored");
                        Equal(false, (bool)spend.Invoke(null, new object[] { budget, state, 1 })!, "active allowance shared until next draw");
                        Equal(3, state.ParticlesThisTick, "drawing cannot reset tick particle budget");
                        Equal(7, state.ParticlesTotal, "drawing cannot reset lifetime particle budget");
                        Equal(100u, Terraria.Main.GameUpdateCount, "draw does not advance simulation clock");
                    }
                    clock.SetValue(null, 101u);
                    var beginTick = typeof(InfiniVfxRuntime).GetMethod("BeginWorldTick", BindingFlags.Static | BindingFlags.NonPublic)!;
                    beginTick.Invoke(null, new object[] { projectile, state });
                    Equal(1, state.DrawCallsThisFrame, "simulation tick cannot replenish draw budget");
                    Equal(0, state.ParticlesThisTick, "simulation tick restores particle allowance");
                    Equal(7, state.ParticlesTotal, "simulation tick preserves lifetime allowance");
                }
                catch (Exception error) { failures.Add("active: " + error); }
                clock.SetValue(null, 100u);
                try
                {
                    system.OnWorldUnload();
                    var type = typeof(InfiniDetachedVfxSystem);
                    var emissions = (IList)type.GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
                    InfiniDetachedVfxSystem.Enqueue("frame_probe", "not_loaded.png", "BeforeProjectiles", Vector2.Zero,
                        0f, 1f, 1f, Color.White, 5, 1);
                    object emission = emissions[0]!;
                    emissions.Clear(); // retain real budget record, bypass only texture/draw branches
                    var spend = type.GetMethod("SpendDraw", BindingFlags.Static | BindingFlags.NonPublic)!;
                    var drawHook = type.GetMethod("DrawProjectiles", BindingFlags.Static | BindingFlags.NonPublic)!;
                    var beginFrame = type.GetMethod("BeginDrawBudgetFrame", BindingFlags.Static | BindingFlags.NonPublic)!;
                    for (int frame = 0; frame < 3; frame++)
                    {
                        beginFrame.Invoke(null, null);
                        Equal(true, (bool)spend.Invoke(null, new[] { emission })!, "detached frame boundary restores budget with unchanged game tick");
                        Equal(false, (bool)spend.Invoke(null, new[] { emission })!, "detached boundary does not remove cap");
                    }
                    Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("frame_probe", 1, 2), "detached prior particle spends tick budget");
                    int observedFrames = 0;
                    // The orig callback is an observer, not a simulated SpriteBatch/game loop.
                    On_Main.orig_DrawProjectiles orig = _ => {
                        observedFrames++;
                        Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("frame_probe", 1, 2), "draw reset cannot replenish detached particles");
                        Equal(true, (bool)spend.Invoke(null, new[] { emission })!, "detached resets on each draw-hook invocation");
                        Equal(false, (bool)spend.Invoke(null, new[] { emission })!, "detached cannot double-spend within draw invocation");
                    };
                    for (int frame = 0; frame < 3; frame++)
                    {
                        drawHook.Invoke(null, new object?[] { orig, null });
                        Equal(false, (bool)spend.Invoke(null, new[] { emission })!, "after layer does not reset source budget again");
                    }
                    Equal(3, observedFrames, "draw hook calls original once per invocation");
                    Equal(100u, Terraria.Main.GameUpdateCount, "detached frames use frozen simulation clock");
                    clock.SetValue(null, 101u);
                    Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("frame_probe", 1, 2), "new tick restores detached particle allowance");
                    clock.SetValue(null, 102u);
                    Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("frame_probe", 1, 2), "detached total survives draw and tick resets");
                }
                catch (Exception error) { failures.Add("detached: " + error); }
            }
            finally { clock.SetValue(null, oldClock); system.OnWorldUnload(); }
            if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        });
    }

    private static void DrawSettingControlsExistingBudgets()
    {
        WithLighting((config, _) =>
        {
            var spendActive = typeof(InfiniVfxRuntime).GetMethod("SpendDraw", BindingFlags.Static | BindingFlags.NonPublic)!;
            var detachedType = typeof(InfiniDetachedVfxSystem);
            var spendDetached = detachedType.GetMethod("SpendDraw", BindingFlags.Static | BindingFlags.NonPublic)!;
            var emissions = (IList)detachedType.GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var detached = new InfiniDetachedVfxSystem();
            var failures = new System.Collections.Generic.List<string>();
            foreach (var test in new[] {
                (Authored: 8, Setting: 1f, Allowed: 8),
                (Authored: 8, Setting: 0.25f, Allowed: 2),
                (Authored: 8, Setting: 0.5f, Allowed: 4),
                (Authored: 8, Setting: 2f, Allowed: 16),
                (Authored: 0, Setting: 2f, Allowed: 0),
                (Authored: 512, Setting: 2f, Allowed: 512),
                (Authored: 7, Setting: 0.5f, Allowed: 3),
                (Authored: 1, Setting: 0.25f, Allowed: 0),
                (Authored: 8, Setting: 0f, Allowed: 2),
                (Authored: 8, Setting: 4f, Allowed: 16),
            })
            foreach (bool active in new[] { true, false })
            {
                string label = (active ? "active" : "detached") + " " + test;
                try
                {
                    detached.OnWorldUnload();
                    config.DrawBudgetMultiplier = test.Setting;
                    var manifest = new VfxManifestSpec();
                    manifest.Budget.MaxDrawCalls = test.Authored;
                    string json = manifest.ToJson();
                    var state = new InfiniVfxState();
                    object[] args = { manifest, state, 1 };
                    InfiniDetachedVfxSystem.Enqueue("draw_budget_probe", "not_loaded.png", "BeforeProjectiles", Vector2.Zero,
                        0f, 1f, 1f, Color.White, 5, test.Authored);
                    object emission = emissions[0]!;
                    bool Spend() => active ? (bool)spendActive.Invoke(null, args)! : (bool)spendDetached.Invoke(null, new[] { emission })!;
                    for (int i = 0; i < test.Allowed; i++) Equal(true, Spend(), label + " accepted draw " + i);
                    Equal(false, Spend(), label + " exact boundary rejects");
                    Equal(false, Spend(), label + " repeated rejection cannot refund budget");
                    if (active)
                    {
                        Equal(test.Allowed, state.DrawCallsThisFrame, label + " exact accepted cost");
                        args[2] = 2;
                        Equal(false, Spend(), label + " multi-call request cannot bypass cap");
                        if (test.Allowed > 0)
                        {
                            var partial = new InfiniVfxState { DrawCallsThisFrame = test.Allowed - 1 };
                            args[1] = partial;
                            Equal(false, Spend(), label + " cost two cannot fit in one remaining");
                            Equal(test.Allowed - 1, partial.DrawCallsThisFrame, label + " rejection is atomic");
                            args[2] = 1;
                            Equal(true, Spend(), label + " rejected cost leaves room for one");
                            Equal(test.Allowed, partial.DrawCallsThisFrame, label + " exact final charge");
                        }
                    }
                    else
                    {
                        InfiniDetachedVfxSystem.Enqueue("draw_budget_probe", "second.png", "AfterProjectiles", Vector2.Zero,
                            0f, 1f, 1f, Color.White, 5, test.Authored);
                        Equal(false, (bool)spendDetached.Invoke(null, new[] { emissions[1] })!, label + " same source shares budget across layers");
                        InfiniDetachedVfxSystem.Enqueue("other_source", "third.png", "BeforeProjectiles", Vector2.Zero,
                            0f, 1f, 1f, Color.White, 5, test.Authored);
                        Equal(test.Allowed > 0, (bool)spendDetached.Invoke(null, new[] { emissions[2] })!, label + " other source has independent allowance");
                    }
                    Equal(json, manifest.ToJson(), label + " authored budget not mutated");
                    Equal(test.Authored, (int)emission.GetType().GetProperty("MaxDrawCalls")!.GetValue(emission)!, label + " detached retains authored cap");
                }
                catch (Exception error) { failures.Add(label + ": " + error); }
                finally { detached.OnWorldUnload(); }
            }
            if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        });
    }

    private static void ParticleSettingControlsRealDust()
    {
        WithLighting((config, lights) =>
        {
            Dust[] priorDust = Terraria.Main.dust;
            bool menu = Terraria.Main.gameMenu, gen = WorldGen.gen;
            int maxDust = Terraria.Main.maxDustToDraw, width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            Vector2 screen = Terraria.Main.screenPosition;
            float dCount = Dust.dCount;
            var random = Terraria.Main.rand;
            var detached = new InfiniDetachedVfxSystem();
            var failures = new System.Collections.Generic.List<string>();
            try
            {
                Terraria.Main.gameMenu = false;
                WorldGen.gen = false;
                Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenPosition = Vector2.Zero;
                Terraria.Main.screenWidth = 800;
                Terraria.Main.screenHeight = 600;
                foreach (var choice in new[] { (Setting: -1f, Count: 0), (Setting: 0f, Count: 0), (Setting: 1f, Count: 1), (Setting: 2f, Count: 2), (Setting: 3f, Count: 2) })
                {
                    config.ParticleSpawnMultiplier = choice.Setting;
                    Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(19);
                    var controlRandom = new Terraria.Utilities.UnifiedRandom(19);
                    Equal(choice.Count, InfiniVfxClientOptions.ScaleParticleCount(1), "exact/clamped multiplier");
                    Equal(controlRandom.Next(), Terraria.Main.rand.Next(), "exact multiplier consumes no additional random value");
                }
                config.ParticleSpawnMultiplier = 0.5f;
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(19);
                int roundedUp = 0;
                for (int i = 0; i < 256; i++)
                {
                    int count = InfiniVfxClientOptions.ScaleParticleCount(1);
                    Equal(true, count is 0 or 1, "fractional singleton never emits an invalid count");
                    roundedUp += count;
                }
                Equal(true, roundedUp > 0 && roundedUp < 256, "fractional singleton neither vanishes nor always emits");
                var player = new Player { active = true, Center = new Vector2(160f, 160f) };
                foreach (string route in new[] { "projectile", "projectile_tick", "detached", "item_use", "item_periodic" })
                foreach (float multiplier in new[] { 1f, 0f, 0.5f, 2f })
                foreach (var cap in new[] { (Tick: 32, Total: 1000), (Tick: 3, Total: 1000), (Tick: 32, Total: 3), (Tick: 0, Total: 0) })
                {
                    // Item path has no existing manifest budget consumer; do not imply otherwise.
                    if (route.StartsWith("item") && cap != (32, 1000)) continue;
                    string label = route + " multiplier=" + multiplier + " cap=" + cap;
                    try
                    {
                        detached.OnWorldUnload();
                        Terraria.Main.dust = new Dust[priorDust.Length];
                        for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust { dustIndex = i };
                        Dust.dCount = 0f;
                        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
                        config.ParticleSpawnMultiplier = multiplier;
                        config.PresentationLightMultiplier = 1f;
                        lights.Clear();
                        var data = GeneratedItemData.Placeholder();
                        string entityId = data.RuntimeProgram.ItemEntityId;
                        string eventName = route is "item_periodic" or "projectile_tick" ? RuntimeEventKind.Periodic : RuntimeEventKind.OnUse;
                        var particle = new VfxSlotSpec {
                            Id = "particles_probe", EntityId = entityId, Event = eventName,
                            RendererKind = "impactRing", Density = 1f, RepeatEvery = 1,
                        };
                        var light = LightManifest(entityId, eventName).Slots[0];
                        data.VfxManifest = new VfxManifestSpec { Slots = new[] { particle, light } };
                        data.VfxManifest.Budget.MaxParticlesPerTick = cap.Tick;
                        data.VfxManifest.Budget.MaxParticlesTotal = cap.Total;
                        data.VfxManifest.NormalizeAndValidate();
                        string serialized = data.VfxManifest.ToJson();
                        var projectile = new Projectile { active = true, damage = 37, Center = player.Center, velocity = Vector2.UnitX };
                        var state = new InfiniVfxState();
                        if (route == "projectile")
                            InfiniVfxRuntime.OnEvent(projectile, data, entityId, eventName, data.VfxManifest, ref state, projectile.Center);
                        else if (route == "projectile_tick")
                            InfiniVfxRuntime.OnTick(projectile, data, entityId, data.VfxManifest, ref state);
                        else if (route == "detached")
                            InfiniVfxRuntime.OnDetachedEvent(data, entityId, eventName, data.VfxManifest, player.Center, Vector2.Zero, "dust_probe");
                        else if (route == "item_use")
                            InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entityId, eventName);
                        else
                            InfiniItemVfxRuntime.OnPeriodic(player, data, entityId);
                        int actual = 0;
                        foreach (Dust dust in Terraria.Main.dust)
                            if (dust.active) { actual++; Equal(player.Center, dust.position, label + " spawn position"); }
                        int expected = (int)((route.StartsWith("item") ? 8 : 10) * multiplier);
                        if (!route.StartsWith("item")) expected = Math.Min(expected, Math.Min(cap.Tick, cap.Total));
                        Equal(expected, actual, label + " actual CPU dust count");
                        if (route.StartsWith("projectile")) Equal(expected, state.ParticlesTotal, label + " exact budget charge");
                        Equal(1, lights.Count, label + " light cue independent of particles");
                        Equal(serialized, data.VfxManifest.ToJson(), label + " authored VFX unchanged");
                        Equal(37, projectile.damage, label + " gameplay damage unchanged");
                        Equal(Vector2.UnitX, projectile.velocity, label + " gameplay velocity unchanged");
                    }
                    catch (Exception error) { failures.Add(label + ": " + error); }
                }
            }
            finally
            {
                detached.OnWorldUnload();
                Terraria.Main.dust = priorDust;
                Terraria.Main.gameMenu = menu;
                WorldGen.gen = gen;
                Terraria.Main.maxDustToDraw = maxDust;
                Terraria.Main.screenWidth = width;
                Terraria.Main.screenHeight = height;
                Terraria.Main.screenPosition = screen;
                Dust.dCount = dCount;
                Terraria.Main.rand = random;
            }
            if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        });
    }

    private static void WithLighting(Action<InfiniVfxClientConfig, IList> check)
    {
        // Use Terraria's actual CPU light queue, not a fake lighting engine.
        var engine = new LightingEngine();
        var active = typeof(Lighting).GetField("_activeEngine", BindingFlags.Static | BindingFlags.NonPublic)!;
        var lights = (IList)typeof(LightingEngine).GetField("_perFrameLights", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(engine)!;
        var instance = typeof(ContentInstance<InfiniVfxClientConfig>).GetProperty("Instance")!;
        object? previousEngine = active.GetValue(null), previousConfig = instance.GetValue(null);
        bool previousServer = Terraria.Main.dedServ, previousPaused = Terraria.Main.gamePaused;
        int previousMode = Terraria.Main.netMode;
        var config = new InfiniVfxClientConfig();
        try
        {
            active.SetValue(null, engine);
            instance.SetValue(null, config);
            Terraria.Main.dedServ = false;
            Terraria.Main.gamePaused = false;
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            check(config, lights);
        }
        finally
        {
            active.SetValue(null, previousEngine);
            instance.SetValue(null, previousConfig);
            Terraria.Main.dedServ = previousServer;
            Terraria.Main.gamePaused = previousPaused;
            Terraria.Main.netMode = previousMode;
        }
    }

    private static VfxManifestSpec LightManifest(string entityId, string eventName)
    {
        var manifest = new VfxManifestSpec {
            Slots = new[] { new VfxSlotSpec {
                Id = "light_probe", EntityId = entityId, Event = eventName,
                RendererKind = "lightCue", Channel = "light", Lane = "cue",
                RepeatEvery = 1, Scale = 1f,
            } },
        };
        manifest.NormalizeAndValidate();
        return manifest;
    }

    private static void AssertLightMultiplier(InfiniVfxClientConfig config, IList lights, Action emit, string label)
    {
        config.PresentationLightMultiplier = 1f;
        lights.Clear();
        emit();
        Equal(1, lights.Count, label + " default light count");
        object baseline = lights[0]!;
        var colorField = baseline.GetType().GetField("Color")!;
        var positionField = baseline.GetType().GetField("Position")!;
        var color = (Vector3)colorField.GetValue(baseline)!;
        var position = (Point)positionField.GetValue(baseline)!;
        Equal(true, color.LengthSquared() > 0f, label + " positive baseline");

        config.PresentationLightMultiplier = 0f;
        Equal(0f, InfiniVfxClientOptions.PresentationLightMultiplier, "real config binding");
        lights.Clear();
        emit();
        Equal(0, lights.Count, label + " disabled light count");

        config.PresentationLightMultiplier = 0.5f;
        emit();
        Equal(1, lights.Count, label + " half-strength light count");
        Equal(color * 0.5f, (Vector3)colorField.GetValue(lights[0])!, label + " half-strength RGB");
        Equal(position, (Point)positionField.GetValue(lights[0])!, label + " unchanged location");
    }

    private static void DetachedVfxStateIsBoundedAndCleared()
    {
        var type = typeof(InfiniDetachedVfxSystem);
        var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? previousClock = clock.GetValue(null);
        bool previousServer = Terraria.Main.dedServ;
        var system = new InfiniDetachedVfxSystem();
        var emissions = (IList)type.GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var budgets = (IDictionary)type.GetField("ParticleBudgetsBySource", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var draws = (IDictionary)type.GetField("DrawCallsBySource", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        try
        {
            system.OnWorldUnload();
            Terraria.Main.dedServ = false;
            clock.SetValue(null, 100u);
            void Enqueue(string key, int duration) => InfiniDetachedVfxSystem.Enqueue(key, "test.png", "BeforeProjectiles", Vector2.One, 0f, 1f, 1f, Color.White, duration, 1);
            Enqueue("expired", 3);
            clock.SetValue(null, 103u);
            Enqueue("current", 5);
            Equal(1, emissions.Count, "expired entry pruned on enqueue");
            Equal("current", (string)emissions[0]!.GetType().GetProperty("SourceKey")!.GetValue(emissions[0])!, "live entry survives pruning");
            for (int i = 0; i < 300; i++) Enqueue("bounded_" + i, 5);
            Equal(256, emissions.Count, "detached emission hard cap");
            var spendDraw = type.GetMethod("SpendDraw", BindingFlags.Static | BindingFlags.NonPublic)!;
            Equal(true, (bool)spendDraw.Invoke(null, new[] { emissions[0] })!, "first draw allowed");
            Equal(false, (bool)spendDraw.Invoke(null, new[] { emissions[0] })!, "per-source draw cap");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "first particle");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "second particle");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "per-tick cap");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("b", 2, 3), "independent source budget");
            clock.SetValue(null, 104u);
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "new tick restores tick allowance");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "total cap survives tick change");
            clock.SetValue(null, 105u + (uint)InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeLifetimeTicks);
            system.PostUpdateWorld();
            Equal(0, budgets.Count, "inactive particle budgets expire");
            InfiniDetachedVfxSystem.TrySpendDetachedParticle("fresh", 2, 3);
            system.OnWorldUnload();
            Equal(0, emissions.Count, "world unload clears sprites");
            Equal(0, draws.Count, "world unload clears draw accounting");
            Equal(0, budgets.Count, "world unload clears particle accounting");
        }
        finally
        {
            system.OnWorldUnload();
            clock.SetValue(null, previousClock);
            Terraria.Main.dedServ = previousServer;
        }
    }

    private static void ItemVfxCadenceHandlesIntegerSeeds()
    {
        WithLighting((config, lights) =>
        {
            config.PresentationLightMultiplier = 1f;
            var player = new Player { active = true };
            var data = GeneratedItemData.Placeholder();
            string entityId = data.RuntimeProgram.ItemEntityId;
            var manifest = LightManifest(entityId, RuntimeEventKind.Periodic);
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? previousClock = clock.GetValue(null);
            try
            {
                foreach (int seed in new[] { 0, 1, -1, int.MaxValue, int.MinValue })
                {
                    manifest.Slots[0].SlotSeed = seed;
                    manifest.Slots[0].RepeatEvery = 7;
                    string json = manifest.ToJson();
                    Equal(true, json.Length > 0, "seed serializes under current VFX boundary");
                    data.VfxManifest = VfxManifestSpec.FromJson(json);
                    Equal(true, data.VfxManifest.HasSlots, "serialized seed remains accepted");
                    Equal(seed, data.VfxManifest.Slots[0].SlotSeed, "seed preserved by round trip");
                    lights.Clear();
                    for (uint tick = 0; tick < 7; tick++)
                    {
                        clock.SetValue(null, tick);
                        InfiniItemVfxRuntime.OnPeriodic(player, data, entityId);
                    }
                    Equal(1, lights.Count, "one emission per repeat period, seed=" + seed);
                }
            }
            finally { clock.SetValue(null, previousClock); }
        });
    }

    private static void ItemLightRespectsClientSetting()
    {
        WithLighting((config, lights) =>
        {
            var player = new Player { active = true, Center = new Vector2(160f, 320f) };
            var data = GeneratedItemData.Placeholder();
            string entityId = data.RuntimeProgram.ItemEntityId;
            data.VfxManifest = LightManifest(entityId, RuntimeEventKind.Periodic);
            AssertLightMultiplier(config, lights, () => InfiniItemVfxRuntime.OnPeriodic(player, data, entityId), "item periodic");
            data.VfxManifest.Slots[0].Event = RuntimeEventKind.OnUse;
            AssertLightMultiplier(config, lights, () => InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entityId, RuntimeEventKind.OnUse), "item use");

            // Explicit equipment light is gameplay data, not a VFX lightCue.
            data.VfxManifest = VfxManifestSpec.Empty();
            data.Accessory.Enabled = true;
            data.Accessory.LightStrength = 0.6f;
            data.Accessory.LightColorName = "red";
            config.PresentationLightMultiplier = 1f;
            lights.Clear();
            InfiniItemVfxRuntime.OnVisibleEquipment(player, data);
            Equal(1, lights.Count, "equipment light baseline");
            var field = lights[0]!.GetType().GetField("Color")!;
            var baseline = (Vector3)field.GetValue(lights[0])!;
            config.PresentationLightMultiplier = 0f;
            lights.Clear();
            InfiniItemVfxRuntime.OnVisibleEquipment(player, data);
            Equal(1, lights.Count, "equipment light remains enabled");
            Equal(baseline, (Vector3)field.GetValue(lights[0])!, "equipment light unchanged by VFX setting");
        });
    }

    private static void ProjectileLightRespectsClientSetting()
    {
        WithLighting((config, lights) =>
        {
            var projectile = new Projectile { Center = new Vector2(160f, 320f) };
            var data = new GeneratedItemData();
            var manifest = LightManifest("light_entity", RuntimeEventKind.Periodic);
            AssertLightMultiplier(config, lights, () => {
                var state = new InfiniVfxState();
                InfiniVfxRuntime.OnTick(projectile, data, "light_entity", manifest, ref state);
            }, "projectile periodic");
            manifest.Slots[0].Event = RuntimeEventKind.OnHit;
            AssertLightMultiplier(config, lights, () => {
                var state = new InfiniVfxState();
                InfiniVfxRuntime.OnEvent(projectile, data, "light_entity", RuntimeEventKind.OnHit, manifest, ref state, projectile.Center);
            }, "projectile hit");
            AssertLightMultiplier(config, lights, () => {
                InfiniVfxRuntime.OnDetachedEvent(data, "light_entity", RuntimeEventKind.OnHit, manifest, projectile.Center, Vector2.Zero, "light_probe");
            }, "detached event");
        });
    }
}
