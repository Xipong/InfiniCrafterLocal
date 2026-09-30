using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Actual packet encoder/receiver, registry lookup and detached consumer; no sockets/world loop.
    private static ulong _probeVfxSequence;
    private static byte[] EncodeProjectileVfxForCheck(GeneratedItemData data, Projectile projectile, string eventName, Vector2 eventPoint)
    {
        var type = typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile);
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        var payloadType = type.GetNestedType("VfxEventPayload", BindingFlags.NonPublic)!;
        object payload = Activator.CreateInstance(payloadType, projectile.owner, projectile.identity, 123L,
            data.Id, "probe", eventName, eventPoint, projectile.velocity,
            InfiniVfxProjectileSnapshot.Capture(projectile, data, "probe"))!;
        payloadType.GetProperty("Occurrence")!.SetValue(payload,++_probeVfxSequence);
        using var stream = new System.IO.MemoryStream();
        using (var writer = new System.IO.BinaryWriter(stream, System.Text.Encoding.UTF8, true))
            type.GetMethod("WriteVfxEventPayload", flags)!.Invoke(null, new[] { (object)writer, payload });
        return stream.ToArray();
    }

    private static void ReceiveProjectileVfxForCheck(GeneratedItemData data, byte[] bytes)
    {
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
        var property = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        object? oldRegistry = property.GetValue(null);
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        using var registry = new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService();
        try
        {
            property.SetValue(null, registry);
            ((System.Collections.IDictionary)registry.GetType().GetField("_byId", instance)!.GetValue(registry)!).Add(data.Id, data);
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            using var stream = new System.IO.MemoryStream(bytes);
            using var reader = new System.IO.BinaryReader(stream);
            InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.HandleVfxEventSyncPacket(reader, 256);
        }
        finally { property.SetValue(null, oldRegistry); Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; }
    }

    private static void ProjectileEventSnapshotRelayPreservesAnchors()
    {
        WithLighting((config, lights) =>
        {
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var oldOwner = Terraria.Main.player[4];
            var oldProjectiles = Terraria.Main.projectile;
            try
            {
                var owner = Terraria.Main.player[4] = new Player { whoAmI = 4, active = true, Center = new Vector2(600, 700) };
                var data = GeneratedItemData.Placeholder();
                InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                var entity = new RuntimeEntitySpec { Id = "probe" }; entity.Movement.Code = 14;
                data.RuntimeProgram.Entities = new[] { entity };
                var slot = new VfxSlotSpec { Id = "relay", EntityId = "probe", Event = RuntimeEventKind.OnHit,
                    RendererKind = "beamLine", ParticleSystemId = "none", Scale = 1f, Duration = 24 };
                data.VfxManifest = new VfxManifestSpec { Slots = new[] { slot } };
                foreach (string anchor in new[] { "self", "owner", "tip", "hitPoint", "field", "tipHistory", "velocity" })
                {
                    system.OnWorldUnload(); owner.active = true; owner.Center = new Vector2(600, 700); slot.Anchor = anchor;
                    var projectile = new Projectile { owner = 4, identity = 11, width = 40, height = 20,
                        Center = new Vector2(160, 140), velocity = Vector2.UnitX, rotation = 1.1f, scale = 1.7f, gfxOffY = 7f, spriteDirection = -1 };
                    var state = new InfiniVfxState(); Vector2 hit = new(900, 1000);
                    InfiniVfxRuntime.OnEvent(projectile, data, "probe", slot.Event, data.VfxManifest, ref state, hit);
                    Equal(1, queue.Count, "local anchor witness");
                    object local = queue[0]!;
                    Vector2 expectedCenter = (Vector2)local.GetType().GetProperty("Center")!.GetValue(local)!;
                    Vector2 expectedForward = (Vector2)local.GetType().GetProperty("Forward")!.GetValue(local)!;
                    byte[] packet = EncodeProjectileVfxForCheck(data, projectile, slot.Event, hit);
                    // The remote no longer has a projectile or active source owner.
                    projectile.active = false; projectile.Center = Vector2.Zero; projectile.rotation = -2;
                    owner.active = false; owner.Center = Vector2.Zero; Terraria.Main.projectile = Array.Empty<Projectile>();
                    system.OnWorldUnload(); ReceiveProjectileVfxForCheck(data, packet);
                    Equal(1, queue.Count, anchor + " relay survives removed projectile");
                    object remote = queue[0]!;
                    AssertVfxNear(expectedCenter, (Vector2)remote.GetType().GetProperty("Center")!.GetValue(remote)!, anchor + " relay uses captured anchor, not hit point");
                    AssertVfxNear(expectedForward, (Vector2)remote.GetType().GetProperty("Forward")!.GetValue(remote)!, anchor + " relay uses captured body forward");
                }
                var source = new Projectile { owner = 4, Center = new Vector2(100, 200), velocity = Vector2.UnitX,
                    width = 40, height = 20, scale = 1f, rotation = 0.8f, spriteDirection = -1, gfxOffY = 3f };
                owner.active = true; owner.Center = new Vector2(600, 700);
                slot.Anchor = "self";
                byte[] valid = EncodeProjectileVfxForCheck(data, source, slot.Event, new Vector2(900, 1000));
                Equal((byte)5, valid[0], "snapshot packet is version 5 preserving immutable v3/v4 facts with ordered occurrences");
                int start;
                using (var stream = new System.IO.MemoryStream(valid))
                using (var reader = new System.IO.BinaryReader(stream))
                {
                    reader.ReadByte(); reader.ReadInt32(); reader.ReadInt32(); reader.ReadInt64();
                    reader.ReadString(); reader.ReadString(); reader.ReadString();
                    start = (int)stream.Position; // event point + velocity, then fixed presentation fields
                }
                void Reject(byte[] bytes, string label)
                {
                    system.OnWorldUnload(); ReceiveProjectileVfxForCheck(data, bytes);
                    Equal(0, queue.Count, label);
                }
                var oldVersion = (byte[])valid.Clone(); oldVersion[0] = 2; Reject(oldVersion, "old version rejected");
                Reject(valid[..^1], "truncated pose rejected");
                // Every coordinate/pose float in the wire must reject non-finite values.
                int snapshotStart = start + 16, ownerFlag = snapshotStart + 24;
                int rotationOffset = ownerFlag + 1 + 8, flipOffset = rotationOffset + 8;
                foreach (int offset in new[] { start, start + 4, start + 8, start + 12,
                    snapshotStart, snapshotStart + 4, snapshotStart + 8, snapshotStart + 12,
                    snapshotStart + 16, snapshotStart + 20, ownerFlag + 1, ownerFlag + 5,
                    rotationOffset, rotationOffset + 4, flipOffset + 1 })
                foreach (float bad in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity })
                {
                    var bytes = (byte[])valid.Clone(); BitConverter.GetBytes(bad).CopyTo(bytes, offset);
                    Reject(bytes, "nonfinite packet float rejected at " + offset);
                }
                foreach (int offset in new[] { ownerFlag, flipOffset })
                { var bytes = (byte[])valid.Clone(); bytes[offset] = 2; Reject(bytes, "malformed pose discriminator rejected"); }
                foreach (float scale in new[] { 0f, -1f, 9f })
                {
                    var bytes = (byte[])valid.Clone(); BitConverter.GetBytes(scale).CopyTo(bytes, rotationOffset + 4);
                    Reject(bytes, "out-of-range captured scale rejected");
                }
                var zeroForward = (byte[])valid.Clone(); Array.Clear(zeroForward, snapshotStart + 16, 8);
                Reject(zeroForward, "missing forward axis rejected instead of invented");
                // Absence of an active owner is an exact optional fact, not center fallback.
                owner.active = false; slot.Anchor = "owner";
                byte[] noOwner = EncodeProjectileVfxForCheck(data, source, slot.Event, new Vector2(900, 1000));
                Reject(noOwner, "owner anchor unavailable at capture stays silent");
                slot.Anchor = "self"; ReceiveProjectileVfxForCheck(data, EncodeProjectileVfxForCheck(data, source, slot.Event, new Vector2(900,1000)));
                Equal(1, queue.Count, "missing owner does not suppress independent self anchor");
            }
            finally { system.OnWorldUnload(); Terraria.Main.player[4] = oldOwner; Terraria.Main.projectile = oldProjectiles; }
        });
    }

    private static void ItemVfxParticleSelectorsAndBudgets()
    {
        WithLighting((config, lights) =>
        {
            var oldDust = Terraria.Main.dust;
            var random = Terraria.Main.rand;
            bool menu = Terraria.Main.gameMenu, gen = WorldGen.gen;
            int max = Terraria.Main.maxDustToDraw, width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            Vector2 screen = Terraria.Main.screenPosition;
            float count = Dust.dCount;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            var detached = new InfiniDetachedVfxSystem();
            try
            {
                Terraria.Main.gameMenu = false; WorldGen.gen = false;
                Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenWidth = 800; Terraria.Main.screenHeight = 600;
                Terraria.Main.screenPosition = Vector2.Zero;
                config.ParticleSpawnMultiplier = 1f;
                var player = new Player { whoAmI = 4, active = true, Center = new Vector2(160f) };
                foreach (var choice in new[] { ("dust", DustID.GemDiamond, true), ("pl:smoke", DustID.Smoke, false),
                    ("pl:shard", DustID.Glass, true), ("pl:spark", DustID.Electric, true), ("pl:glow", DustID.TintableDustLighted, true) })
                {
                    detached.OnWorldUnload();
                    InfiniItemVfxRuntime.ClearUseEventCaches();
                    clock.SetValue(null, 100u);
                    Terraria.Main.dust = new Dust[oldDust.Length];
                    for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust { dustIndex = i };
                    Dust.dCount = 0; Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
                    var data = GeneratedItemData.Placeholder();
                    string entity = data.RuntimeProgram.ItemEntityId;
                    var slot = new VfxSlotSpec { Id = "dust_probe", EntityId = entity, Event = RuntimeEventKind.OnUse,
                        RendererKind = "impactRing", ParticleSystemId = choice.Item1, Density = 1f };
                    data.VfxManifest = new VfxManifestSpec { Slots = new[] { slot } };
                    // First isolate the selector with an unrestricted allowance.
                    data.VfxManifest.Budget.MaxParticlesPerTick = 32;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    foreach (Dust dust in Terraria.Main.dust.Where(d => d.active))
                    {
                        Equal(choice.Item2, dust.type, "exact authored item dust selector " + choice.Item1);
                        Equal(choice.Item3, dust.noGravity, "smoke preserves existing gravity semantics");
                        Equal(player.Center, dust.position, "item producer world coordinates");
                    }
                    Equal(8, Terraria.Main.dust.Count(d => d.active), "existing item particle count preserved");
                    slot.ParticleSystemId = "none";
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(8, Terraria.Main.dust.Count(d => d.active), "explicit none does not fall back to diamond dust");
                    slot.ParticleSystemId = choice.Item1;
                    detached.OnWorldUnload();
                    foreach (Dust dust in Terraria.Main.dust) dust.active = false;
                    InfiniItemVfxRuntime.ClearUseEventCaches();
                    data.VfxManifest.Budget.MaxParticlesPerTick = 2;
                    data.VfxManifest.Budget.MaxParticlesTotal = 3;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(2, Terraria.Main.dust.Count(d => d.active), "item per-tick budget");
                    slot.Event = RuntimeEventKind.OnHit;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnHit);
                    Equal(2, Terraria.Main.dust.Count(d => d.active), "different event shares item source budget");
                    clock.SetValue(null, 101u);
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnHit);
                    Equal(4, Terraria.Main.dust.Count(d => d.active), "reused item gets a new tick allowance, not a permanent total cap");
                    slot.Event = RuntimeEventKind.Periodic; slot.RepeatEvery = 1;
                    // Keep touching this exact source beyond detached-budget retention.
                    // Real Dust is reset only for observation, never the source ledger.
                    uint endTick = 102u + (uint)InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeLifetimeTicks;
                    for (uint tick = 102; tick <= endTick; tick++)
                    {
                        clock.SetValue(null, tick);
                        foreach (Dust dust in Terraria.Main.dust) dust.active = false;
                        detached.PostUpdateEverything();
                        InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                        InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                        Equal(2, Terraria.Main.dust.Count(d => d.active), "continuous periodic renews only per-tick allowance tick=" + tick);
                    }
                    slot.Event = RuntimeEventKind.OnUse;
                    clock.SetValue(null, endTick + 1);
                    foreach (Dust dust in Terraria.Main.dust) dust.active = false;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(2, Terraria.Main.dust.Count(d => d.active), "reuse after continuous periodic remains live");
                    var otherPlayer = new Player { whoAmI = 5, active = true, Center = player.Center };
                    InfiniItemVfxRuntime.EmitAndSyncEvent(otherPlayer, data, entity, RuntimeEventKind.OnUse);
                    Equal(4, Terraria.Main.dust.Count(d => d.active), "different player has independent tick allowance");
                    clock.SetValue(null, endTick + 2);
                    data.VfxManifest.Budget.MaxParticlesTotal = 0;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                    Equal(4, Terraria.Main.dust.Count(d => d.active), "explicit zero particle budget stays silent");
                }
            }
            finally
            {
                detached.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); clock.SetValue(null, oldClock);
                Terraria.Main.dust = oldDust; Terraria.Main.rand = random;
                Terraria.Main.gameMenu = menu; WorldGen.gen = gen;
                Terraria.Main.maxDustToDraw = max; Terraria.Main.screenWidth = width; Terraria.Main.screenHeight = height;
                Terraria.Main.screenPosition = screen; Dust.dCount = count;
            }
        });
    }

    private delegate ReLogic.Utilities.SlotId EventSoundObserver(in Terraria.Audio.SoundStyle style,
        Vector2? position, Terraria.Audio.SoundUpdateCallback? callback);

    private static void ItemVfxSoundPreservesAuthoredPhase()
    {
        WithLighting((config, lights) =>
        {
            Terraria.Audio.SoundStyle? observed = null;
            Vector2? location = null;
            EventSoundObserver observer = (in Terraria.Audio.SoundStyle style, Vector2? position,
                Terraria.Audio.SoundUpdateCallback? callback) => {
                observed = style; location = position;
                return ReLogic.Utilities.SlotId.Invalid; // observe API boundary; no audio device
            };
            var play = typeof(Terraria.Audio.SoundEngine).GetMethod("PlaySound", new[] {
                typeof(Terraria.Audio.SoundStyle).MakeByRefType(), typeof(Vector2?), typeof(Terraria.Audio.SoundUpdateCallback) })!;
            using var hook = new MonoMod.RuntimeDetour.Hook(play, observer);
            var player = new Player { active = true, Center = new Vector2(160f) };
            var data = GeneratedItemData.Placeholder();
            string entity = data.RuntimeProgram.ItemEntityId;
            var slot = new VfxSlotSpec { Id = "sound_probe", EntityId = entity, Event = RuntimeEventKind.OnUse,
                RendererKind = "soundCue", Channel = "sound", Lane = "cue", Alpha = 0.4f };
            data.VfxManifest = new VfxManifestSpec { Slots = new[] { slot } };
            foreach (float phase in new[] { -1f, 0f, 1f })
            {
                slot.PhaseOffset = phase; observed = null;
                InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                Equal(true, observed.HasValue, "item sound API reached");
                Equal(phase * 0.25f, observed!.Value.Pitch, "existing authored phase-to-pitch mapping");
                Equal(0.4f, observed.Value.Volume, "authored volume preserved");
                Equal(SoundID.Item1.SoundPath, observed.Value.SoundPath, "no new sound-style mapping");
                Equal(player.Center, location!.Value, "sound stays at producer world position");
            }
            Terraria.Main.dedServ = true; observed = null;
            InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
            Equal(false, observed.HasValue, "dedicated server remains silent");
        });
    }

    private static void ItemVfxRemoteRejectsInactiveSource()
    {
        WithLighting((config, lights) =>
        {
            var old = Terraria.Main.player[4];
            int mode = Terraria.Main.netMode;
            try
            {
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                var player = Terraria.Main.player[4] = new Player { whoAmI = 4, active = true, Center = new Vector2(160f) };
                var data = GeneratedItemData.Placeholder();
                string entity = data.RuntimeProgram.ItemEntityId;
                data.VfxManifest = LightManifest(entity, RuntimeEventKind.OnHit);
                var item = player.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
                var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
                typeof(Terraria.ModLoader.ModType<Item>).GetProperty("Entity")!.SetValue(generated, item);
                typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                void Receive(string eventName)
                {
                    using var stream = new System.IO.MemoryStream();
                    using (var writer = new System.IO.BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                    { writer.Write((byte)3); writer.Write((byte)4); writer.Write(data.Id); writer.Write(entity); writer.Write(eventName); writer.Write(160f); writer.Write(160f); }
                    stream.Position = 0;
                    using var reader = new System.IO.BinaryReader(stream);
                    InfiniItemVfxRuntime.HandleUseEventPacket(reader, 4);
                }
                Receive(RuntimeEventKind.OnHit);
                Equal(1, lights.Count, "valid relay still uses local light consumer");
                lights.Clear(); Receive(RuntimeEventKind.OnCrit);
                Equal(0, lights.Count, "relay cannot substitute a different event");
                player.active = false; Receive(RuntimeEventKind.OnHit);
                Equal(0, lights.Count, "inactive remote source cannot emit a late event");
            }
            finally { Terraria.Main.player[4] = old; Terraria.Main.netMode = mode; }
        });
    }

    // Observe real AI -> slot clock / gameplay scheduler. No world spawning or GPU.
    private static void ProjectilePeriodicVfxIsIndependentOfGameplayActions()
    {
        WithLighting((config, lights) =>
        {
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            var oldOwner = Terraria.Main.player[0]; var oldNpcs = Terraria.Main.npc;
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem)
                .GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var pending = (System.Collections.IList)typeof(InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler)
                .GetField("Pending", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            try
            {
                config.PresentationLightMultiplier = 1f;
                Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, Center = new Vector2(160f) };
                Terraria.Main.npc = new NPC[oldNpcs.Length];
                for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i };
                var npc = Terraria.Main.npc[0] = new NPC { active = true, whoAmI = 0, life = 1000, lifeMax = 1000,
                    knockBackResist = 1f, width = 16, height = 16, Center = new Vector2(176, 160) };
                foreach (bool actions in new[] { true, false })
                foreach (int extra in new[] { 0, 2 })
                {
                    system.OnWorldUnload(); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
                    npc.velocity = Vector2.Zero;
                    var entity = Entity(); entity.Id = "periodic_probe"; entity.Kind = RuntimeEntityKind.StationaryProjectile;
                    entity.LifetimeTicks = 60;
                    entity.Events = actions ? new[] {
                        new RuntimeEventActionSpec { Id = "immediate", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.Pull, PeriodTicks = 6, Mode = "target_to_point", RadiusTiles = 4, Strength = 0.5f },
                        new RuntimeEventActionSpec { Id = "delayed_a", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity, PeriodTicks = 6, DelayTicks = 2, Count = 1 },
                        new RuntimeEventActionSpec { Id = "delayed_b", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity, PeriodTicks = 6, DelayTicks = 3, Count = 1 },
                        new RuntimeEventActionSpec { Id = "delayed_c", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity, PeriodTicks = 12, DelayTicks = 4, Count = 1 },
                    } : Array.Empty<RuntimeEventActionSpec>();
                    var data = GeneratedItemData.Placeholder(); data.RuntimeProgram.Entities = new[] { entity };
                    data.VfxManifest.Slots = new[] {
                        new VfxSlotSpec { Id = "periodic_shape", EntityId = entity.Id, Event = RuntimeEventKind.Periodic,
                            RendererKind = "impactRing", ParticleSystemId = "none", RepeatEvery = 5, StartTick = 0, SlotSeed = 0 },
                        new VfxSlotSpec { Id = "periodic_light", EntityId = entity.Id, Event = RuntimeEventKind.Periodic,
                            RendererKind = "lightCue", ParticleSystemId = "none", RepeatEvery = 5, StartTick = 0, SlotSeed = 0 },
                    };
                    var projectile = new Projectile { active = true, owner = 0, Center = new Vector2(160f), damage = 100 };
                    var generated = Attach(projectile); generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                    projectile.extraUpdates = extra;
                    for (uint tick = 1; tick <= 12; tick++)
                    {
                        clock.SetValue(null, tick); lights.Clear(); projectile.netUpdate = false;
                        for (int update = 0; update <= extra; update++) generated.AI();
                        Equal(actions && tick >= 6 ? tick >= 12 ? 5 : 2 : 0, pending.Count,
                            "gameplay periods remain world-tick based with extraUpdates=" + extra + " tick=" + tick);
                        Equal(actions && tick % 6 == 0, projectile.netUpdate, "delayed spawn reservation keeps netUpdate timing");
                        Equal(actions ? -(float)(tick / 6) * 0.5f : 0f, npc.velocity.X, "real immediate periodic pull executes at authored period");
                        Equal(tick % 5 == 0 ? 1 : 0, lights.Count,
                            "periodic light follows own slot, not gameplay action period; actions=" + actions + " tick=" + tick);
                        Equal(0, queue.Count, "live periodic shape never gains a second detached presentation clock");
                    }
                    if (actions)
                    {
                        string ids = string.Join(",", pending.Cast<object>().Select(p =>
                            ((RuntimeEventActionSpec)p.GetType().GetProperty("Action")!.GetValue(p)!).Id));
                        Equal("delayed_a,delayed_b,delayed_a,delayed_b,delayed_c", ids, "authored scheduler enqueue order unchanged");
                        Equal("2,3,2,3,4", string.Join(",", pending.Cast<object>().Select(p =>
                            (int)p.GetType().GetProperty("Ticks")!.GetValue(p)!)), "authored delays unchanged");
                    }
                    // Exact event lanes remain independent after removing only the periodic relay.
                    data.VfxManifest.Slots = new[] { RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit,
                        RuntimeEventKind.OnExpire, RuntimeEventKind.OnKill }.Select(ev => new VfxSlotSpec {
                            Id = ev, EntityId = entity.Id, Event = ev, RendererKind = "impactRing", ParticleSystemId = "none" }).ToArray();
                    clock.SetValue(null, 13u);
                    generated.OnHitNPC(npc, new NPC.HitInfo { Crit = true }, 1);
                    Equal(2, queue.Count, "actual critical hit keeps both hit and crit presentation");
                    projectile.timeLeft = 1; generated.AI(); generated.OnKill(0);
                    Equal(4, queue.Count, "final AI and kill keep both expire and kill presentation");
                }
            }
            finally
            {
                system.OnWorldUnload(); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
                clock.SetValue(null, oldClock); Terraria.Main.player[0] = oldOwner; Terraria.Main.npc = oldNpcs;
            }
        });
    }

    private static void ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick()
    {
        ItemPeriodicPresentationHasOneWorldTickOwner();
        ProjectilePeriodicVfxIsIndependentOfGameplayActions();
        WithLighting((config, lights) =>
        {
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? previous = clock.GetValue(null);
            try
            {
                var player = new Player { active = true, Center = new Vector2(160f) };
                var data = GeneratedItemData.Placeholder();
                string entity = data.RuntimeProgram.ItemEntityId;
                data.VfxManifest = LightManifest(entity, RuntimeEventKind.Periodic);
                var slot = data.VfxManifest.Slots[0];
                slot.StartTick = 5; slot.RepeatEvery = 3; slot.SlotSeed = 0;
                for (uint tick = 0; tick < 10; tick++)
                {
                    clock.SetValue(null, tick); lights.Clear();
                    InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                    Equal(tick % 3 == 0 ? 1 : 0, lights.Count, "item world-clock cadence ignores projectile-only StartTick tick=" + tick);
                }
                slot.Event = RuntimeEventKind.OnUse;
                clock.SetValue(null, 0u); lights.Clear();
                InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity, RuntimeEventKind.OnUse);
                Equal(1, lights.Count, "nonperiodic event is not filtered by periodic cadence");
            }
            finally { clock.SetValue(null, previous); }
        });
    }
}
