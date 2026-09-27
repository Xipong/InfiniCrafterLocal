using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ItemShapeAndSpriteEventsReachDetachedQueue()
    {
        WithLighting((config, lights) =>
        {
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem)
                .GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var player = new Player { whoAmI = 4, active = true, direction = -1,
                Center = new Vector2(100, 120), velocity = Vector2.UnitY * 2f, itemRotation = 0f };
            var data = GeneratedItemData.Placeholder();
            data.Visual.EffectColor = "cyan";
            data.Visual.SpritePath = "authored_item_event.png";
            var slot = new VfxSlotSpec { Id = "item_shape", EntityId = data.RuntimeProgram.ItemEntityId,
                Event = RuntimeEventKind.OnHit, Anchor = "hitPoint", ParticleSystemId = "none",
                TextureRole = "none", Duration = 20, Alpha = 0.5f };
            data.VfxManifest.Slots = new[] { slot };
            Vector2 point = new(330, 440);
            try
            {
                foreach (string kind in new[] { "beamLine", "wavyStrip", "fieldPulse", "orbitingMotes", "ghostArc", "impactRing" })
                {
                    system.OnWorldUnload(); slot.RendererKind = kind;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, slot.EntityId, slot.Event, point);
                    Equal(1, queue.Count, "item event reaches primitive queue: " + kind);
                    object emission = queue[0]!;
                    Equal((int)VfxRendererRegistry.ParseKind(kind), (int)(InfiniVfxRendererKind)emission.GetType().GetProperty("PrimitiveKind")!.GetValue(emission)!, "exact renderer preserved");
                    Equal(point, (Vector2)emission.GetType().GetProperty("Center")!.GetValue(emission)!, "captured hit point reaches primitive");
                    Equal(-Vector2.UnitX, (Vector2)emission.GetType().GetProperty("Forward")!.GetValue(emission)!, "stationary weapon-facing axis is not owner movement");
                    Equal(RuntimeColorPolicy.Resolve("cyan", Color.White) * slot.Alpha,
                        (Color)emission.GetType().GetProperty("Color")!.GetValue(emission)!, "explicit item effect color");
                }
                foreach (string kind in new[] { "projectileAfterimage", "spriteStampTrail", "actorAfterimage" })
                {
                    system.OnWorldUnload(); slot.RendererKind = kind; slot.TextureRole = "item";
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, slot.EntityId, slot.Event, point);
                    Equal(1, queue.Count, "item event reaches sprite snapshot queue: " + kind);
                    object emission = queue[0]!;
                    Equal(data.Visual.SpritePath, (string)emission.GetType().GetProperty("TexturePath")!.GetValue(emission)!, "authored texture preserved");
                    Equal(point, (Vector2)emission.GetType().GetProperty("Center")!.GetValue(emission)!, "sprite captures event point");
                }
            }
            finally { system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); }
        });
        ItemPrimitiveAndDustShareLegacyColor();
    }

    private static void ItemPrimitiveAndDustShareLegacyColor()
    {
        WithLighting((config, lights) =>
        {
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var oldDust = Terraria.Main.dust; var oldRandom = Terraria.Main.rand;
            bool oldMenu = Terraria.Main.gameMenu, oldGen = WorldGen.gen;
            int oldMax = Terraria.Main.maxDustToDraw, oldWidth = Terraria.Main.screenWidth, oldHeight = Terraria.Main.screenHeight;
            float oldCount = Dust.dCount; Vector2 oldScreen = Terraria.Main.screenPosition;
            try
            {
                Terraria.Main.gameMenu = false; WorldGen.gen = false; Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenWidth = 800; Terraria.Main.screenHeight = 600; Terraria.Main.screenPosition = Vector2.Zero;
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11); config.ParticleSpawnMultiplier = 1f;
                var player = new Player { active = true, whoAmI = 4, Center = new Vector2(160f), direction = 1 };
                var data = GeneratedItemData.Placeholder(); data.Visual.Palette = new[] { "red" };
                data.VfxManifest.Motif.Element = "ice";
                var slot = new VfxSlotSpec { Id = "color", EntityId = data.RuntimeProgram.ItemEntityId, Event = RuntimeEventKind.OnUse,
                    Anchor = "self", RendererKind = "impactRing", ParticleSystemId = "dust", Alpha = 0.5f, Density = 0f };
                data.VfxManifest.Slots = new[] { slot };
                foreach (string? effectColor in new string?[] { null, "blue" })
                {
                    system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
                    if (effectColor is not null) data.Visual.EffectColor = effectColor;
                    Terraria.Main.dust = new Dust[oldDust.Length];
                    for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust { dustIndex = i };
                    Dust.dCount = 0;
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, slot.EntityId, slot.Event);
                    Equal(1, queue.Count, "item primitive captured");
                    var dust = Terraria.Main.dust.Where(d => d.active).ToArray();
                    Equal(1, dust.Length, "real companion Dust spawned");
                    Color expected = RuntimeColorPolicy.Resolve(effectColor ?? "red", Color.White);
                    Equal(expected, dust[0].color, "item Dust preserves palette unless explicit color authored");
                    object emission = queue[0]!;
                    Equal(expected * slot.Alpha, (Color)emission.GetType().GetProperty("Color")!.GetValue(emission)!,
                        "item primitive shares Dust palette, not conflicting projectile motif");
                }
            }
            finally
            {
                system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
                Terraria.Main.dust = oldDust; Terraria.Main.rand = oldRandom; Terraria.Main.gameMenu = oldMenu; WorldGen.gen = oldGen;
                Terraria.Main.maxDustToDraw = oldMax; Terraria.Main.screenWidth = oldWidth; Terraria.Main.screenHeight = oldHeight;
                Dust.dCount = oldCount; Terraria.Main.screenPosition = oldScreen;
            }
        });
    }

    private static void ItemExplicitEffectColorReachesLight()
    {
        WithLighting((config, lights) =>
        {
            config.PresentationLightMultiplier = 1f;
            var player = new Player { active = true, Center = new Vector2(100, 120) };
            var data = GeneratedItemData.Placeholder();
            data.Visual.Palette = new[] { "red" }; data.Visual.EffectColor = "cyan";
            data.VfxManifest = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnUse);
            data.VfxManifest.Slots[0].Scale = 1f;
            lights.Clear();
            InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnUse);
            Equal(1, lights.Count, "explicit-color light reaches CPU queue");
            object actual = lights[0]!; lights.Clear();
            Lighting.AddLight(player.Center, RuntimeColorPolicy.Resolve("cyan", Color.White).ToVector3() * 0.2f);
            Equal(true, actual.Equals(lights[0]), "explicit effect color overrides old item palette");
            var slot = data.VfxManifest.Slots[0];
            foreach (string anchor in new[] { "self", "owner", "tip", "tipHistory", "hitPoint" })
            foreach (string eventName in new[] { RuntimeEventKind.OnUse, RuntimeEventKind.Periodic })
            foreach (float value in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity, 0f })
            foreach (bool badX in new[] { true, false })
            {
                slot.Anchor = anchor; slot.Event = eventName; slot.RepeatEvery = 1;
                player.Center = new Vector2(160f); player.itemLocation = new Vector2(160f);
                Vector2 point = value == 0f ? Vector2.Zero : badX ? new Vector2(value, 160) : new Vector2(160, value);
                if (anchor is "self" or "owner") player.Center = point;
                if (anchor is "tip" or "tipHistory") player.itemLocation = point;
                lights.Clear();
                if (eventName == RuntimeEventKind.Periodic)
                    InfiniItemVfxRuntime.OnPeriodic(player, data, slot.EntityId);
                else
                    InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, slot.EntityId, slot.Event, anchor == "hitPoint" ? point : null);
                int expected = value == 0f && !(eventName == RuntimeEventKind.Periodic && anchor == "hitPoint") ? 1 : 0;
                Equal(expected, lights.Count, anchor + " " + eventName + " rejects nonfinite position but preserves world zero");
                if (expected == 1)
                {
                    object captured = lights[0]!; lights.Clear();
                    Lighting.AddLight(Vector2.Zero, RuntimeColorPolicy.Resolve("cyan", Color.White).ToVector3() * 0.2f);
                    Equal(true, captured.Equals(lights[0]), "zero anchor reaches actual engine queue unchanged");
                }
            }
        });
    }

    private static void ItemOutgoingVfxRejectsNonfinitePoint()
    {
        WithLighting((config, lights) =>
        {
            var instance = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Instance")!;
            object? oldInstance = instance.GetValue(null);
            int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
            int reached = 0;
            Func<Mod, int, ModPacket> observe = (mod, capacity) =>
            {
                reached++;
                throw new InvalidOperationException("observed real packet allocation boundary");
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(Mod).GetMethod("GetPacket")!, observe);
            try
            {
                instance.SetValue(null, System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod)));
                Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 4;
                var player = new Player { active = true, whoAmI = 4 };
                var data = GeneratedItemData.Placeholder();
                data.VfxManifest = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnUse);
                foreach (bool explicitPoint in new[] { false, true })
                foreach (Vector2 point in new[] { new Vector2(float.NaN, 160), new Vector2(160, float.PositiveInfinity),
                    new Vector2(float.NegativeInfinity, 160), Vector2.Zero })
                {
                    player.Center = explicitPoint ? new Vector2(160f) : point;
                    reached = 0;
                    try { InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, data.RuntimeProgram.ItemEntityId,
                        RuntimeEventKind.OnUse, explicitPoint ? point : null); }
                    catch (InvalidOperationException ex) when (ex.Message == "observed real packet allocation boundary") { }
                    Equal(point == Vector2.Zero ? 1 : 0, reached,
                        "outgoing explicit/fallback coordinates validated before packet allocation; zero remains valid");
                }
            }
            finally { instance.SetValue(null, oldInstance); Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; }
        });
    }

    public static void ItemVfxEventPositionsRelayAndBudgets()
    {
        ItemOutgoingVfxRejectsNonfinitePoint();
        WithLighting((config, lights) =>
        {
            var oldDust = Terraria.Main.dust;
            var random = Terraria.Main.rand;
            var oldPlayer = Terraria.Main.player[4];
            bool menu = Terraria.Main.gameMenu, gen = WorldGen.gen;
            int max = Terraria.Main.maxDustToDraw, width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
            Vector2 screen = Terraria.Main.screenPosition;
            float count = Dust.dCount;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? previous = clock.GetValue(null);
            try
            {
                Terraria.Main.gameMenu = false; WorldGen.gen = false;
                Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenWidth = 800; Terraria.Main.screenHeight = 600;
                Terraria.Main.screenPosition = Vector2.Zero;
                Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 4;
                config.ParticleSpawnMultiplier = 1f; config.PresentationLightMultiplier = 1f;
                Terraria.Main.dust = new Dust[oldDust.Length];
                for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust { dustIndex = i };
                Dust.dCount = 0; Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
                InfiniItemVfxRuntime.ClearUseEventCaches(); clock.SetValue(null, 100u);
                var player = Terraria.Main.player[4] = new Player { whoAmI = 4, active = true, Center = new Vector2(160f) };
                var target = new NPC { active = true, Center = new Vector2(320f, 240f) };
                var data = GeneratedItemData.Placeholder();
                string entity = data.RuntimeProgram.ItemEntityId;
                data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Input = RuntimeInputKind.PrimaryUse,
                    UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true,
                        Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = entity } } } };
                var item = player.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1, useTime = 20 };
                var generated = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity")!.SetValue(generated, item);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                var slot = new VfxSlotSpec { Id = "event", EntityId = entity, Event = RuntimeEventKind.OnHit,
                    Anchor = "hitPoint", RendererKind = "impactRing", ParticleSystemId = "dust", Density = 1f };
                data.VfxManifest.Slots = new[] { slot };
                data.VfxManifest.Budget.MaxParticlesPerTick = 32;
                data.VfxManifest.Budget.MaxParticlesTotal = 3;
                generated.OnHitNPC(player, target, new NPC.HitInfo(), 1);
                Equal(3, Terraria.Main.dust.Count(d => d.active), "event invocation owns its total allowance");
                foreach (Dust dust in Terraria.Main.dust.Where(d => d.active))
                    Equal(target.Center, dust.position, "real hit hook captures target center");
                slot.Event = RuntimeEventKind.OnCrit;
                generated.OnHitNPC(player, target, new NPC.HitInfo { Crit = true }, 1);
                Equal(6, Terraria.Main.dust.Count(d => d.active), "crit owns independent event allowance");
                slot.Event = RuntimeEventKind.Periodic; slot.Anchor = "self"; slot.RepeatEvery = 1;
                InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                Equal(14, Terraria.Main.dust.Count(d => d.active), "periodic has no positive total ceiling");
                data.VfxManifest.Budget.MaxParticlesPerTick = 15;
                InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                Equal(15, Terraria.Main.dust.Count(d => d.active), "events and periodic share source tick ceiling");
                clock.SetValue(null, 101u); data.VfxManifest.Budget.MaxParticlesTotal = 0;
                InfiniItemVfxRuntime.OnPeriodic(player, data, entity);
                Equal(15, Terraria.Main.dust.Count(d => d.active), "explicit zero stays silent");

                // Real decoder, no sockets: validate remote coordinates and exact-event cooldown.
                Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
                data.VfxManifest = LightManifest(entity, RuntimeEventKind.OnHit);
                slot = data.VfxManifest.Slots[0]; slot.Anchor = "hitPoint";
                void Receive(string ev, Vector2 point, byte version = 3, string? id = null)
                {
                    using var stream = new MemoryStream();
                    using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                    { writer.Write(version); writer.Write((byte)4); writer.Write(id ?? data.Id); writer.Write(entity); writer.Write(ev); writer.Write(point.X); writer.Write(point.Y); }
                    stream.Position = 0;
                    using var reader = new BinaryReader(stream);
                    InfiniItemVfxRuntime.HandleUseEventPacket(reader, 4);
                }
                lights.Clear(); Receive(slot.Event, target.Center, 2);
                Equal(0, lights.Count, "old packet fails closed without migration");
                Receive(slot.Event, new Vector2(float.NaN, 240));
                Receive(slot.Event, target.Center, id: "wrong");
                Equal(0, lights.Count, "invalid coordinate and identity rejected");
                Receive(slot.Event, target.Center);
                Equal(1, lights.Count, "real v3 decoder emits light");
                Equal(true, ((Point)lights[0]!.GetType().GetField("Position")!.GetValue(lights[0])!).Equals(target.Center.ToTileCoordinates()), "relay keeps captured hit point");
                lights.Clear(); Receive(slot.Event, target.Center);
                Equal(0, lights.Count, "duplicate exact event is throttled");
                slot.Event = RuntimeEventKind.OnCrit; Receive(slot.Event, target.Center);
                Equal(1, lights.Count, "hit does not suppress crit in same tick");
                lights.Clear(); slot.Event = RuntimeEventKind.OnUse; slot.Anchor = "owner";
                Receive(slot.Event, target.Center);
                Equal(true, ((Point)lights[0]!.GetType().GetField("Position")!.GetValue(lights[0])!).Equals(player.Center.ToTileCoordinates()), "owner anchor ignores remote event point");
                lights.Clear(); clock.SetValue(null, 130u); player.active = false; Receive(slot.Event, target.Center);
                Equal(0, lights.Count, "inactive peer rejected");

                // Actual server decoder without Mod/socket initialization: observe its bounded
                // acceptance table before the absent transport endpoint, not fabricated sends.
                InfiniItemVfxRuntime.ClearUseEventCaches();
                Terraria.Main.netMode = NetmodeID.Server; clock.SetValue(null, 0u);
                var tables = (Array)typeof(InfiniItemVfxRuntime).GetField("RecentEvents", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
                int Accepted() => (tables.GetValue(4) as System.Collections.IDictionary)?.Count ?? 0;
                void ServerReceive(string ev, string? id = null)
                {
                    using var stream = new MemoryStream();
                    using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                    { writer.Write((byte)3); writer.Write(id ?? data.Id); writer.Write(entity); writer.Write(ev); writer.Write(target.Center.X); writer.Write(target.Center.Y); }
                    stream.Position = 0;
                    using var reader = new BinaryReader(stream);
                    InfiniItemVfxRuntime.HandleUseEventPacket(reader, 4);
                }
                ServerReceive(slot.Event); Equal(0, Accepted(), "server rejects inactive sender");
                player.active = true;
                ServerReceive(slot.Event, "wrong"); Equal(0, Accepted(), "server validates held item identity");
                foreach (string ev in new[] { RuntimeEventKind.OnUse, RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit })
                { slot.Event = ev; ServerReceive(ev); }
                Equal(3, Accepted(), "tick-zero use/hit/crit accepted independently by actual server decoder");
                ServerReceive(slot.Event); Equal(3, Accepted(), "same event cannot expand cooldown table");
            }
            finally
            {
                InfiniItemVfxRuntime.ClearUseEventCaches(); clock.SetValue(null, previous);
                Terraria.Main.dust = oldDust; Terraria.Main.rand = random; Terraria.Main.player[4] = oldPlayer;
                Terraria.Main.gameMenu = menu; WorldGen.gen = gen; Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local;
                Terraria.Main.maxDustToDraw = max; Terraria.Main.screenWidth = width; Terraria.Main.screenHeight = height;
                Terraria.Main.screenPosition = screen; Dust.dCount = count;
            }
        });
    }
}
