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
                        detached.PostUpdateWorld();
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
                    { writer.Write((byte)2); writer.Write((byte)4); writer.Write(data.Id); writer.Write(entity); writer.Write(eventName); }
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

    private static void ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick()
    {
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
