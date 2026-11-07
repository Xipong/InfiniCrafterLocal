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

    private static void EnqueueProbeShape(string sourceKey, int duration, int maxDraw)
    {
        var data = GeneratedItemData.Placeholder();
        var slot = ExplicitShapeSlot(); slot.Duration = duration;
        data.VfxManifest = new() { Budget = new() { MaxDrawCalls = maxDraw }, Slots = new[] { slot } };
        InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, sourceKey,
            new VfxSourceFrame(Vector2.One, Vector2.UnitX, Vector2.Zero));
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
                        Equal(100u, Terraria.Main.GameUpdateCount, "draw does not advance simulation clock");
                    }
                    clock.SetValue(null, 101u);
                    var beginTick = typeof(InfiniVfxRuntime).GetMethod("BeginWorldTick", BindingFlags.Static | BindingFlags.NonPublic)!;
                    beginTick.Invoke(null, new object[] { projectile, state });
                    Equal(1, state.DrawCallsThisFrame, "simulation tick cannot replenish draw budget");
                }
                catch (Exception error) { failures.Add("active: " + error); }
                clock.SetValue(null, 100u);
                try
                {
                    system.OnWorldUnload();
                    var type = typeof(InfiniDetachedVfxSystem);
                    var drawHook = type.GetMethod("DrawProjectiles", BindingFlags.Static | BindingFlags.NonPublic)!;
                    var beginFrame = type.GetMethod("BeginDrawBudgetFrame", BindingFlags.Static | BindingFlags.NonPublic)!;
                    for (int frame = 0; frame < 3; frame++)
                    {
                        beginFrame.Invoke(null, null);
                        Equal(true, InfiniDetachedVfxSystem.TrySpendSourceDraw("frame_probe", 1, 1), "detached frame boundary restores budget with unchanged game tick");
                        Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("frame_probe", 1, 1), "detached boundary does not remove cap");
                    }
                    Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("frame_probe", 1, 2), "detached prior particle spends tick budget");
                    int observedFrames = 0;
                    // The orig callback is an observer, not a simulated SpriteBatch/game loop.
                    On_Main.orig_DrawProjectiles orig = _ => {
                        observedFrames++;
                        Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("frame_probe", 1, 2), "draw reset cannot replenish detached particles");
                        Equal(true, InfiniDetachedVfxSystem.TrySpendSourceDraw("frame_probe", 1, 1), "detached resets on each draw-hook invocation");
                        Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("frame_probe", 1, 1), "detached cannot double-spend within draw invocation");
                    };
                    for (int frame = 0; frame < 3; frame++)
                    {
                        drawHook.Invoke(null, new object?[] { orig, null });
                        Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("frame_probe", 1, 1), "after layer does not reset source budget again");
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
            var detached = new InfiniDetachedVfxSystem();
            var failures = new System.Collections.Generic.List<string>();
            foreach (var test in new[] {
                (Authored: 8, Setting: 1f, Allowed: 8),
                (Authored: 8, Setting: 0.25f, Allowed: 2),
                (Authored: 8, Setting: 0.5f, Allowed: 4),
                (Authored: 8, Setting: 2f, Allowed: 16),
                (Authored: 0, Setting: 2f, Allowed: 0),
                (Authored: 512, Setting: 2f, Allowed: 1024),
                (Authored: 2048, Setting: 1f, Allowed: 2048),
                (Authored: 2048, Setting: 2f, Allowed: 2048),
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
                    bool Spend() => active ? (bool)spendActive.Invoke(null, args)! : InfiniDetachedVfxSystem.TrySpendSourceDraw("draw_budget_probe", test.Authored, 1);
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
                        Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("draw_budget_probe", test.Authored, 1), label + " same source shares budget across layers");
                        Equal(test.Allowed > 0, InfiniDetachedVfxSystem.TrySpendSourceDraw("other_source", test.Authored, 1), label + " other source has independent allowance");
                    }
                    Equal(json, manifest.ToJson(), label + " authored budget not mutated");
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
                foreach (string route in new[] { "projectile", "detached", "item_use" })
                foreach (float multiplier in new[] { 1f, 0f, 0.5f, 2f })
                foreach (var cap in new[] { (Tick: 32, Total: 1000), (Tick: 3, Total: 1000), (Tick: 32, Total: 3), (Tick: 0, Total: 0) })
                {
                    // Item tick-budget/lifetime semantics have a separate dedicated check.
                    if (route.StartsWith("item") && cap != (32, 1000)) continue;
                    string label = route + " multiplier=" + multiplier + " cap=" + cap;
                    try
                    {
                        detached.OnWorldUnload();
                        InfiniItemVfxRuntime.ClearUseEventCaches();
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
                            RendererKind = "nativeDust", Color = Rgb(17, 83, 241), RepeatEvery = 0, StartTick = 0,
                            Dust = new() { Type="GemDiamond", Count=10, Size=1, AngularDistribution="even", DirectionFrame="source", AngleOffsetRadians=0, Spawn=new(){Shape="point"}, SpreadRadians=MathF.Tau, SpeedMinPxPerTick=1, SpeedMaxPxPerTick=1, NativeAlpha=100, NoGravity=true } };
                        var light = LightManifest(entityId, eventName, projectile: route == "projectile_tick").Slots[0];
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
                            InfiniVfxRuntime.OnDetachedEvent(data, entityId, eventName, data.VfxManifest, player.Center, Vector2.Zero, "dust_probe", InfiniVfxProjectileSnapshot.Capture(projectile,data,entityId));
                        else if (route == "item_use")
                            InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entityId, eventName);
                        else
                            InfiniItemVfxRuntime.OnPeriodic(player, data, entityId);
                        int actual = 0;
                        foreach (Dust dust in Terraria.Main.dust)
                            if (dust.active) { actual++; Equal(player.Center, dust.position, label + " spawn position"); Equal(new Color(17,83,241), dust.color, label + " exact local RGB reaches real Dust"); }
                        int expected = (int)(10 * multiplier);
                        if (!route.StartsWith("item")) expected = Math.Min(expected, Math.Min(cap.Tick, cap.Total));
                        Equal(expected, actual, label + " actual CPU dust count");
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
                InfiniItemVfxRuntime.ClearUseEventCaches();
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
            InfiniItemVfxRuntime.ClearUseEventCaches();
            check(config, lights);
        }
        finally
        {
            active.SetValue(null, previousEngine);
            InfiniItemVfxRuntime.ClearUseEventCaches();
            instance.SetValue(null, previousConfig);
            Terraria.Main.dedServ = previousServer;
            Terraria.Main.gamePaused = previousPaused;
            Terraria.Main.netMode = previousMode;
        }
    }

    private static VfxManifestSpec LightManifest(string entityId, string eventName, bool projectile = false)
    {
        var manifest = new VfxManifestSpec {
            Slots = new[] { new VfxSlotSpec {
                Id = "light_probe", EntityId = entityId, Event = eventName,
                RendererKind = "nativeLight", Color = Rgb(255, 255, 255), Light = new() { Intensity = .2f }, StartTick = 0, RepeatEvery = eventName == RuntimeEventKind.Periodic ? 1 : 0 } },
        };
        if (eventName == RuntimeEventKind.Periodic) {
            manifest.Slots[0].RepeatEvery = 1;
            if (projectile) manifest.Slots[0].StartTick = 0;
        }
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

    // Real current queue/budget consumers in MP-client mode; no Draw or new emission at expiry.
    private static void DetachedVfxClientCleanupDoesNotRequireDraw()
    {
        var type = typeof(InfiniDetachedVfxSystem);
        var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? previousClock = clock.GetValue(null);
        bool previousServer = Terraria.Main.dedServ;
        int previousMode = Terraria.Main.netMode;
        var system = new InfiniDetachedVfxSystem();
        var emissions = (IList)type.GetField("ShapeEmissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var budgets = (IDictionary)type.GetField("ParticleBudgetsBySource", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var draws = (IDictionary)type.GetField("DrawCallsBySource", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        void Enqueue() => EnqueueProbeShape("client", 3, 1);
        try
        {
            system.OnWorldUnload();
            Terraria.Main.dedServ = false; Terraria.Main.netMode = Terraria.ID.NetmodeID.MultiplayerClient;
            clock.SetValue(null, 100u); Enqueue();
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("client", 1, 2), "client particle budget is populated");
            Equal(true, InfiniDetachedVfxSystem.TrySpendSourceDraw("client", 1, 1), "draw budget is populated");
            system.PostUpdateEverything(); system.PostUpdateEverything();
            Equal(1, emissions.Count, "same-tick client cleanup preserves live snapshot");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("client", 1, 2), "cleanup does not replenish same-tick particles");
            Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("client", 1, 1), "cleanup does not replenish draw allowance");
            clock.SetValue(null, 103u); system.PostUpdateEverything();
            Equal(0, emissions.Count, "MP client expires queue without Draw or enqueue");
            Equal(1, budgets.Count, "snapshot expiry does not retire unexpired source budget");
            clock.SetValue(null, 101u + (uint)InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeLifetimeTicks);
            system.PostUpdateEverything();
            Equal(0, budgets.Count, "MP client expires inactive budget without Draw or emission");
            Enqueue();
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("client", 1, 2), "new source allowance after retention");
            Terraria.Main.dedServ = true; Terraria.Main.netMode = Terraria.ID.NetmodeID.Server;
            clock.SetValue(null, 102u + 2u * (uint)InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeLifetimeTicks);
            system.PostUpdateEverything(); Enqueue();
            Equal(1, emissions.Count, "dedicated server neither prunes nor enqueues presentation");
            Equal(1, budgets.Count, "dedicated-server update leaves presentation budgets untouched");
            system.OnWorldUnload();
            Equal(0, emissions.Count, "unload clears queue even on dedicated server");
            Equal(0, budgets.Count, "unload clears particle budgets");
            Equal(0, draws.Count, "unload clears draw budgets");
        }
        finally
        {
            system.OnWorldUnload(); clock.SetValue(null, previousClock);
            Terraria.Main.dedServ = previousServer; Terraria.Main.netMode = previousMode;
        }
    }

    private static void DetachedVfxStateIsBoundedAndCleared()
    {
        var type = typeof(InfiniDetachedVfxSystem);
        var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? previousClock = clock.GetValue(null);
        bool previousServer = Terraria.Main.dedServ;
        var system = new InfiniDetachedVfxSystem();
        var emissions = (IList)type.GetField("ShapeEmissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var budgets = (IDictionary)type.GetField("ParticleBudgetsBySource", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var draws = (IDictionary)type.GetField("DrawCallsBySource", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        try
        {
            system.OnWorldUnload();
            Terraria.Main.dedServ = false;
            clock.SetValue(null, 100u);
            void Enqueue(string key, int duration) => EnqueueProbeShape(key, duration, 1);
            Enqueue("expired", 3);
            clock.SetValue(null, 103u);
            system.PostUpdateEverything();
            Enqueue("current", 5);
            Equal(1, emissions.Count, "expired entry pruned on enqueue");
            Equal("current", (string)emissions[0]!.GetType().GetField("SourceKey", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(emissions[0])!, "live entry survives pruning");
            for (int i = 0; i < 300; i++) Enqueue("bounded_" + i, 5);
            Equal(256, emissions.Count, "detached emission hard cap");
                Equal(true, InfiniDetachedVfxSystem.TrySpendSourceDraw("client", 1, 1), "first draw allowed");
            Equal(false, InfiniDetachedVfxSystem.TrySpendSourceDraw("client", 1, 1), "per-source draw cap");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "first particle");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "second particle");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "per-tick cap");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("b", 2, 3), "independent source budget");
            clock.SetValue(null, 104u);
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "new tick restores tick allowance");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("a", 2, 3), "total cap survives tick change");
            clock.SetValue(null, 105u + (uint)InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeLifetimeTicks);
            system.PostUpdateEverything();
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





}
