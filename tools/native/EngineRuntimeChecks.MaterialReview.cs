using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Collections;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem ReviewItem(GeneratedItemData data)
    {
        var item = new Item { type = 1, stack = 1 };
        var generated = new GeneratedItem();
        AttachItem(generated, item, data);
        return generated;
    }

    // Real Mod.GetPacket and production HandlePacket. Only socket Send is intercepted.
    private sealed class ReviewPeers : IDisposable
    {
        internal readonly InfiniDetachedVfxSystem System = new();
        internal readonly InfiniMod Mod = new();
        internal readonly GeneratedItemRegistryService Registry = new();
        internal readonly List<byte[]> Sent = new();
        private readonly Dictionary<ModPacket, int> starts = new();
        private readonly PropertyInfo modProperty = typeof(InfiniMod).GetProperty("Instance")!;
        private readonly PropertyInfo registryProperty = typeof(InfiniMod).GetProperty("GeneratedItems")!;
        private readonly FieldInfo netMods = typeof(Mod).Assembly.GetType("Terraria.ModLoader.ModNet")!.GetField("netMods", BindingFlags.Static | BindingFlags.NonPublic)!;
        private readonly object? previousMod, previousRegistry, previousNetMods;
        private readonly NativeActorState state = new();
        private readonly MonoMod.RuntimeDetour.Hook packetHook, sendHook;
        internal ReviewPeers()
        {
            previousMod = modProperty.GetValue(null); previousRegistry = registryProperty.GetValue(null); previousNetMods = netMods.GetValue(null);
            System.OnWorldUnload(); MaterialClock(100);
            Terraria.Main.player = Enumerable.Range(0, Terraria.Main.maxPlayers).Select(i => new Player { whoAmI = i, active = i < 3, direction = 1 }).ToArray();
            typeof(Mod).GetField("netID", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(Mod, (short)0);
            netMods.SetValue(null, new Mod[] { Mod }); modProperty.SetValue(null, Mod); registryProperty.SetValue(null, Registry);
            VfxGetPacketHook get = (orig, self, capacity) => { var p = orig(self, capacity); starts[p] = (int)p.BaseStream.Position; return p; };
            Action<ModPacket, int, int> send = (p, to, ignore) => Sent.Add(((MemoryStream)p.BaseStream).ToArray()[starts[p]..]);
            packetHook = new MonoMod.RuntimeDetour.Hook(typeof(Mod).GetMethod("GetPacket")!, get);
            sendHook = new MonoMod.RuntimeDetour.Hook(typeof(ModPacket).GetMethod("Send")!, send);
            Mode(NetmodeID.SinglePlayer, 0);
        }
        internal void Mode(int netMode, int myPlayer)
        {
            Terraria.Main.netMode = netMode; Terraria.Main.myPlayer = myPlayer; Terraria.Main.dedServ = netMode == NetmodeID.Server;
            Terraria.Main.projectile = Enumerable.Range(0, 16).Select(i => new Projectile { whoAmI = i }).ToArray();
        }
        internal void Register(GeneratedItemData data)
        {
            GeneratedItemRegistryService.StampCurrentWorld(data);
            ((IDictionary)Registry.GetType().GetField("_byId", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(Registry)!)[data.Id] = data;
        }
        internal GeneratedProjectile Host(GeneratedItemData data, int slot = 3, int owner = 0, int identity = 71, byte[]? extra = null)
        {
            var host = Terraria.Main.projectile[slot] = new Projectile { whoAmI = slot, owner = owner, identity = identity, active = true,
                Center = new Vector2(100, 150), velocity = Vector2.UnitX, timeLeft = 90, scale = 1 };
            var generated = Attach(host); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(host, generated);
            if (extra is null) generated.Configure(data, data.RuntimeProgram.TryGetEntity("actor")!, 0, 0, Vector2.UnitX);
            else generated.ReceiveExtraAI(new BinaryReader(new MemoryStream(extra)));
            return generated;
        }
        internal void Receive(byte[] bytes, int sender = 256) => Mod.HandlePacket(new BinaryReader(new MemoryStream(bytes)), sender);
        public void Dispose()
        {
            sendHook.Dispose(); packetHook.Dispose(); System.OnWorldUnload(); Registry.Dispose();
            netMods.SetValue(null, previousNetMods); modProperty.SetValue(null, previousMod); registryProperty.SetValue(null, previousRegistry);
            state.Dispose();
        }
    }
    private static byte[] ReviewExtra(GeneratedProjectile generated)
    {
        using var memory = new MemoryStream(); generated.SendExtraAI(new BinaryWriter(memory)); return memory.ToArray();
    }
    private static GeneratedItemData ReviewProjectileData(params string[] events)
    {
        var data = ParseMaterialElement(MaterialElementWire()); data.Id = "material_review";
        var actor = Entity(); actor.Id = "actor"; actor.Kind = RuntimeEntityKind.FreeProjectile; actor.LifetimeTicks = 90;
        actor.Visual.AssetMode = "no_asset"; actor.VisualRole = "projectile"; actor.Visual.Role = "projectile"; actor.Spawn.Enabled = true;
        actor.Movement.Name = "move_straight"; actor.Movement.Code = 0; actor.Collision.TileCollide = true;
        if (events.Contains("on_release") || events.Contains("channel_complete")) {
            actor.Controller.Name = "charge_then_release"; actor.Controller.Code = RuntimeControllerCode.ChargeThenRelease; actor.Controller.Params.ChargeTicks = 1;
        }
        data.RuntimeProgram.Entities = data.RuntimeProgram.Entities.Concat(new[] { actor }).ToArray();
        var template = data.VfxManifest.Slots[0];
        data.VfxManifest.Slots = events.Select((ev, i) => {
            var slot = System.Text.Json.JsonSerializer.Deserialize<VfxSlotSpec>(System.Text.Json.JsonSerializer.Serialize(template))!;
            slot.Id = "review" + i; slot.EntityId = actor.Id; slot.Event = ev; slot.RepeatEvery = ev == "periodic" ? 1 : 0; slot.Duration = 12; slot.Element!.Count = 1; slot.Element.WidthPx = i + 1; return slot;
        }).ToArray();
        return ParseMaterialElement(JsonNode.Parse(data.ToJson())!.AsObject());
    }

    private static void MaterialNonownerPathRemainsLocalEventsAwaitRelay()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ReviewProjectileData("on_spawn");
            var template = data.VfxManifest.Slots[0];
            var path = new VfxSlotSpec { Id = "live_path", EntityId = "actor", Event = "on_spawn", RendererKind = "texturedPath", Path = new VfxTexturedPathSpec { Texture = template.Element!.Texture, Source = "anchorHistory", HistoryTicks = 8, MinDistancePx = 0, MaxSegmentLengthPx = 100,
                    WidthPx = 8, WidthProfile = template.Element.WidthProfile, OpacityProfile = template.Element.OpacityProfile, ColorProfile = template.Element.ColorProfile,
                    ProfileDomain = "age", UvMode = "stretch", RepeatLengthPx = 1, ScrollPxPerTick = 0 }, Blend = "alpha", Layer = "BeforeProjectiles", Alpha = 1, StartTick = 0 };
            var legacy = new VfxSlotSpec { Id = "legacy", EntityId = "actor", Event = "on_spawn", RendererKind = "impactRing", Color = Rgb(255, 255, 255), ParticleSystemId = "none", Duration = 12, Blend = "alpha", Layer = "BeforeProjectiles", Scale = 1, Density = 0, Spread = 0, RepeatEvery = 0, Alpha = .65f, StartTick = 0 };
            data.VfxManifest.Slots = new[] { path, legacy }; peers.Register(data);
            peers.Mode(NetmodeID.MultiplayerClient, 2); var remote = peers.Host(data, 5);
            typeof(GeneratedProjectile).GetMethod("EmitAndSyncVfxEvent", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(remote, new object[] { "on_spawn", remote.Projectile.Center });
            var paths = (IList)typeof(InfiniDetachedVfxSystem).GetField("MaterialPaths", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var emissions = (IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            Equal(1, paths.Count, "nonowner actual local spawn event still registers its live path without a relay");
            Equal(0, emissions.Count, "remote discrete presentation awaits its validated relay");
            typeof(GeneratedProjectile).GetMethod("EmitAndSyncVfxEvent", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(remote, new object[] { "on_spawn", remote.Projectile.Center });
            Equal(1, paths.Count, "live path registration deduplicates the same generation"); Equal(0, emissions.Count, "repeated callback cannot bypass relay ownership");
        });
    }

    private static void ItemEventOccurrencesRelaySimpleAndMixed()
    {
        // Native inventory publication is independently exercised by FirstHeldItemEventPublishesTokenBeforeClaim.
        // This socket-free fixture observes the event stream, not Terraria socket buffers.
        using var equipmentPublication = PersistenceObserveNetworkSend((_, __) => { });
        foreach (bool mixed in new[] { false, true }) WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            InfiniItemVfxRuntime.ClearUseEventCaches();
            var data = ReviewContactItemData(); data.Id = mixed ? "mixed_event" : "simple_event";
            var material = data.VfxManifest.Slots[0]; material.Anchor = "hitPoint";
            var simple = LightManifest(material.EntityId, RuntimeEventKind.OnHit).Slots[0];
            simple.Id = "simple_hit"; simple.Anchor = "hitPoint";
            data.VfxManifest.Slots = mixed ? new[] { material, simple } : new[] { simple };
            if (!mixed) data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>();
            data.Normalize();
            peers.Register(data);
            var player = Terraria.Main.player[0]; player.selectedItem = 0; player.Center = new Vector2(200,200);
            var owner = ReviewItem(data); player.inventory[0] = owner.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            var points = new[] { new Vector2(320,240), new Vector2(320,240), new Vector2(640,240) };
            foreach (var point in points) owner.OnHitNPC(player, new NPC { active = true, Center = point }, new NPC.HitInfo(), 1);
            Equal(3, peers.Sent.Count, "same-coordinate and distinct hits each send a distinct event");
            var claims = peers.Sent.ToArray(); peers.Sent.Clear();
            using var wire = new MemoryStream(); owner.NetSend(new BinaryWriter(wire));
            wire.Position = 0; Equal(8, new BinaryReader(wire).ReadInt32(), "simple events also synchronize presentation token");
            var server = ReviewItem(data); wire.Position = 0; server.NetReceive(new BinaryReader(wire)); player.inventory[0] = server.Item;
            Equal(owner.PresentationToken, server.PresentationToken, "event source identity survives native item sync");
            peers.Mode(NetmodeID.Server, 255);
            peers.Receive(claims[0], 1); Equal(0, peers.Sent.Count, "other owner cannot send this event");
            player.inventory[0] = ReviewItem(data).Item;
            peers.Receive(claims[0], 0); Equal(0, peers.Sent.Count, "stale item generation is rejected");
            player.inventory[0] = server.Item;
            foreach (var claim in claims) peers.Receive(claim, 0);
            Equal(3, peers.Sent.Count, "server relays each distinct occurrence");
            foreach (var claim in claims) peers.Receive(claim, 0);
            Equal(3, peers.Sent.Count, "replayed owner occurrences do not relay");
            var relays = peers.Sent.ToArray(); peers.Sent.Clear();
            peers.System.OnWorldUnload();
            var remote = ReviewItem(data); wire.Position = 0; remote.NetReceive(new BinaryReader(wire)); player.inventory[0] = remote.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 2); lights.Clear();
            foreach (var relay in relays) peers.Receive(relay);
            Equal(3, lights.Count, "simple effect emitted for each real occurrence");
            Equal(points[0].ToTileCoordinates(), (Point)lights[0]!.GetType().GetField("Position")!.GetValue(lights[0])!, "first hit coordinate retained");
            Equal(points[2].ToTileCoordinates(), (Point)lights[2]!.GetType().GetField("Position")!.GetValue(lights[2])!, "different hit coordinate retained");
            Equal(mixed ? 3 : 0, OwnedMaterialQueue().Count, "mixed material and simple effects stay in sync");
            foreach (var relay in relays) peers.Receive(relay);
            Equal(3, lights.Count, "replayed relay occurrence does not emit simple effect");
            Equal(mixed ? 3 : 0, OwnedMaterialQueue().Count, "replayed relay occurrence does not emit material effect");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
    }

    private static void ItemEventNetworkRateLimit()
    {
        // Native inventory publication is independently exercised by FirstHeldItemEventPublishesTokenBeforeClaim.
        // This socket-free fixture observes the event stream, not Terraria socket buffers.
        using var equipmentPublication = PersistenceObserveNetworkSend((_, __) => { });
        WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            InfiniItemVfxRuntime.ClearUseEventCaches();
            var data = ReviewContactItemData(); data.Id = "item_event_limit";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>();
            data.Normalize();
            peers.Register(data);
            var player = Terraria.Main.player[0]; player.selectedItem = 0; player.Center = new Vector2(200,200);
            var owner = ReviewItem(data); player.inventory[0] = owner.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            for (int i = 0; i < 65; i++) owner.OnHitNPC(player, new NPC { active = true, Center = new Vector2(320,240) }, new NPC.HitInfo(), 1);
            Equal(65, peers.Sent.Count, "all real producer events get distinct occurrences");
            var claims = peers.Sent.ToArray(); peers.Sent.Clear();
            using var wire = new MemoryStream(); owner.NetSend(new BinaryWriter(wire));
            var server = ReviewItem(data); wire.Position = 0; server.NetReceive(new BinaryReader(wire)); player.inventory[0] = server.Item;
            peers.Mode(NetmodeID.Server, 255);
            foreach (var claim in claims) peers.Receive(claim, 0);
            Equal(64, peers.Sent.Count, "server caps per-owner relay work in one world tick");
            // Reconnecting a player is a new transport/owner session, even if
            // it reuses the same numeric owner slot in the same world tick.
            var rejoined = new Player { active = true, whoAmI = 0, selectedItem = 0 };
            rejoined.inventory[0] = server.Item; Terraria.Main.player[0] = rejoined;
            peers.Sent.Clear(); peers.Receive(ReviewReplaceOccurrence(claims[0], true, 1), 0);
            Equal(1, peers.Sent.Count, "new player session does not inherit old per-tick rate count");
            Terraria.Main.player[0] = player; peers.Sent.Clear();
            MaterialClock(Terraria.Main.GameUpdateCount + 1);
            peers.Mode(NetmodeID.MultiplayerClient, 0); player.inventory[0] = owner.Item;
            owner.OnHitNPC(player, new NPC { active = true, Center = new Vector2(320,240) }, new NPC.HitInfo(), 1);
            var next = peers.Sent.Last(); peers.Sent.Clear(); player.inventory[0] = server.Item;
            peers.Mode(NetmodeID.Server, 255); peers.Receive(next, 0);
            Equal(1, peers.Sent.Count, "server restores capacity next tick");

            // A remote client enforces its own per-owner tick ceiling too.
            InfiniItemVfxRuntime.ClearUseEventCaches(); peers.Mode(NetmodeID.MultiplayerClient, 2);
            MaterialClock(200); lights.Clear();
            for (ulong i = 1; i <= 65; i++) peers.Receive(ReviewReplaceOccurrence(claims[0], true, i));
            Equal(64, lights.Count, "remote caps admitted occurrences per owner and tick");
            MaterialClock(201); peers.Receive(ReviewReplaceOccurrence(claims[0], true, 66));
            Equal(65, lights.Count, "remote restores capacity next tick");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
    }

    private static void ProjectileHitOccurrencesStayDistinct()
    {
        WithLighting((_, lights) => {
            var data = ReviewProjectileData("on_hit"); var entity = data.RuntimeProgram.TryGetEntity("actor")!;
            data.VfxManifest.Slots = LightManifest(entity.Id, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Slots[0].Anchor = "hitPoint";
            var source = new Projectile { active = true, owner = 0, identity = 71, scale = 1, Center = new Vector2(100,150), velocity = Vector2.UnitX };
            var state = new InfiniVfxState(); lights.Clear();
            InfiniVfxRuntime.OnEvent(source, data, entity.Id, RuntimeEventKind.OnHit, data.VfxManifest, ref state, new Vector2(320,240));
            InfiniVfxRuntime.OnEvent(source, data, entity.Id, RuntimeEventKind.OnHit, data.VfxManifest, ref state, new Vector2(320,240));
            InfiniVfxRuntime.OnEvent(source, data, entity.Id, RuntimeEventKind.OnHit, data.VfxManifest, ref state, new Vector2(640,240));
            Equal(3, lights.Count, "each native projectile hit is distinct even at the same point");
            data.VfxManifest.Slots[0].Event = RuntimeEventKind.OnKill;
            InfiniVfxRuntime.OnEvent(source, data, entity.Id, RuntimeEventKind.OnKill, data.VfxManifest, ref state, source.Center);
            InfiniVfxRuntime.OnEvent(source, data, entity.Id, RuntimeEventKind.OnKill, data.VfxManifest, ref state, source.Center);
            Equal(4, lights.Count, "duplicate lifecycle event remains guarded within the tick");
        });
    }

    private static void ItemEventWaitsForAuthoritativeToken()
    {
        // The native publication route is covered separately; this fixture tests
        // pending claims without opening a Terraria network connection.
        using var equipmentPublication = PersistenceObserveNetworkSend((_, __) => { });
        WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            var data = ReviewContactItemData(); data.Id = "delayed_item_token";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>(); data.Normalize(); peers.Register(data);
            var player = Terraria.Main.player[0]; player.selectedItem = 0;
            var owner = ReviewItem(data); player.inventory[0] = owner.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            Item prior = owner.Item.Clone();
            Equal(false, owner.Item.IsNetStateDifferent(prior), "same native type and state initially need no sync");
            owner.OnHitNPC(player, new NPC { active = true, Center = new Vector2(320,240) }, new NPC.HitInfo(), 1);
            Equal(true, owner.Item.IsNetStateDifferent(prior), "new presentation token marks native item metadata dirty");
            prior = owner.Item.Clone();
            owner.OnHitNPC(player, new NPC { active = true, Center = new Vector2(640,240) }, new NPC.HitInfo(), 1);
            Equal(false, owner.Item.IsNetStateDifferent(prior), "same token does not mark native item dirty repeatedly");
            var claims = peers.Sent.ToArray(); peers.Sent.Clear();
            using var wire = new MemoryStream(); owner.NetSend(new BinaryWriter(wire));
            var server = ReviewItem(data); player.inventory[0] = server.Item;
            peers.Mode(NetmodeID.Server, 255);
            peers.Receive(claims[0], 1); Equal(0, peers.Sent.Count, "wrong sender cannot enqueue a token wait");
            peers.Receive(claims[0], 0); peers.Receive(claims[1], 0);
            peers.Receive(claims[0], 0); Equal(0, peers.Sent.Count, "events wait without modifying server item");
            if (server.PresentationToken == owner.PresentationToken) throw new InvalidOperationException("test needs different tokens");
            wire.Position = 0; server.NetReceive(new BinaryReader(wire));
            peers.System.PostUpdateEverything();
            Equal(2, peers.Sent.Count, "authoritative item sync releases both independent hits once");
            var relays = peers.Sent.ToArray(); peers.Sent.Clear();
            peers.Receive(claims[0], 0); peers.System.PostUpdateEverything();
            Equal(0, peers.Sent.Count, "replay after pending drain is refused");
            peers.Mode(NetmodeID.MultiplayerClient, 2); lights.Clear();
            foreach (var relay in relays) peers.Receive(relay);
            Equal(2, lights.Count, "remote sees both hit snapshots in transport order");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ReviewContactItemData(); data.Id = "ordered_item_tokens";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>(); data.Normalize(); peers.Register(data);
            var player = Terraria.Main.player[0]; player.selectedItem = 0;
            var first = ReviewItem(data); player.inventory[0] = first.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            first.OnHitNPC(player, new NPC { active = true, Center = new Vector2(320,240) }, new NPC.HitInfo(), 1);
            var later = ReviewItem(data); player.inventory[0] = later.Item;
            later.OnHitNPC(player, new NPC { active = true, Center = new Vector2(640,240) }, new NPC.HitInfo(), 1);
            var claims=peers.Sent.ToArray(); peers.Sent.Clear();
            using var wire = new MemoryStream(); later.NetSend(new BinaryWriter(wire));
            var server=ReviewItem(data); wire.Position=0; server.NetReceive(new BinaryReader(wire)); player.inventory[0]=server.Item;
            peers.Mode(NetmodeID.Server, 255); MaterialClock(100); peers.Receive(claims[0], 0);
            MaterialClock(120); peers.Receive(claims[1], 0);
            Equal(1, peers.Sent.Count, "new authoritative token supersedes an older mismatched claim without delay");
            using var firstWire = new MemoryStream(); first.NetSend(new BinaryWriter(firstWire));
            firstWire.Position=0; server.NetReceive(new BinaryReader(firstWire));
            peers.System.PostUpdateEverything();
            Equal(1, peers.Sent.Count, "superseded claim is not revived by a later old-token sync");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ReviewContactItemData(); data.Id = "replay_item_tokens";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>(); data.Normalize(); peers.Register(data);
            var player=Terraria.Main.player[0]; player.selectedItem=0;
            var old=ReviewItem(data); player.inventory[0]=old.Item; peers.Mode(NetmodeID.MultiplayerClient, 0);
            old.OnHitNPC(player,new NPC { active=true, Center=new Vector2(320,240) },new NPC.HitInfo(),1);
            var newer=ReviewItem(data); player.inventory[0]=newer.Item;
            newer.OnHitNPC(player,new NPC { active=true, Center=new Vector2(640,240) },new NPC.HitInfo(),1);
            var claims=peers.Sent.ToArray(); peers.Sent.Clear();
            using var oldWire=new MemoryStream(); old.NetSend(new BinaryWriter(oldWire));
            using var newWire=new MemoryStream(); newer.NetSend(new BinaryWriter(newWire));
            var server=ReviewItem(data); oldWire.Position=0; server.NetReceive(new BinaryReader(oldWire)); player.inventory[0]=server.Item;
            peers.Mode(NetmodeID.Server,255); peers.Receive(claims[0],0); Equal(1,peers.Sent.Count,"valid earlier source relays");
            peers.Sent.Clear(); peers.Receive(claims[1],0); peers.Receive(claims[0],0);
            Equal(0,peers.Sent.Count,"replay of old matching source does not supersede a newer pending claim");
            newWire.Position=0; server.NetReceive(new BinaryReader(newWire)); peers.System.PostUpdateEverything();
            Equal(1,peers.Sent.Count,"pending newer claim survives rejected replay");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            WithPlayer((player,modPlayer) => {
                player.active=true; player.whoAmI=0; player.selectedItem=0; Terraria.Main.player[0]=player;
                var accessory=ReactiveUtilityItem(); var equipment=accessory.Data; equipment.Id="pending_equipment";
                equipment.VfxManifest.Slots=LightManifest(equipment.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnHurt).Slots;
                equipment.VfxManifest.Assets=Array.Empty<VfxAssetSpec>(); equipment.Normalize(); peers.Register(equipment);
                var heldData=ReviewContactItemData(); heldData.Id="ready_held";
                heldData.VfxManifest.Slots=LightManifest(heldData.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnHit).Slots;
                heldData.VfxManifest.Assets=Array.Empty<VfxAssetSpec>(); heldData.Normalize(); peers.Register(heldData);
                var held=ReviewItem(heldData); player.inventory[0]=held.Item; modPlayer.RegisterReactiveEquipment(accessory);
                peers.Mode(NetmodeID.MultiplayerClient,0);
                InfiniItemVfxRuntime.EmitAndSyncEvent(player,equipment,equipment.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnHurt,player.Center);
                held.OnHitNPC(player,new NPC { active=true, Center=new Vector2(320,240) },new NPC.HitInfo(),1);
                var claims=peers.Sent.ToArray(); peers.Sent.Clear();
                Equal(2,claims.Length,"independent equipment and held events both send");
                using var equipWire=new MemoryStream(); accessory.NetSend(new BinaryWriter(equipWire));
                using var heldWire=new MemoryStream(); held.NetSend(new BinaryWriter(heldWire));
                var serverAccessory=ReviewItem(equipment); var serverHeld=ReviewItem(heldData);
                heldWire.Position=0; serverHeld.NetReceive(new BinaryReader(heldWire)); player.inventory[0]=serverHeld.Item;
                modPlayer.ResetEffects(); modPlayer.RegisterReactiveEquipment(serverAccessory);
                peers.Mode(NetmodeID.Server,255); peers.Receive(claims[0],0); peers.Receive(claims[1],0);
                Equal(1,peers.Sent.Count,"ready held event bypasses unsynced reactive equipment");
                equipWire.Position=0; serverAccessory.NetReceive(new BinaryReader(equipWire)); peers.System.PostUpdateEverything();
                Equal(2,peers.Sent.Count,"held event does not discard independent pending equipment");
                InfiniItemVfxRuntime.ClearUseEventCaches();
            });
        });
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ReviewContactItemData(); data.Id = "stale_item_token";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>(); data.Normalize(); peers.Register(data);
            var player = Terraria.Main.player[0]; player.selectedItem = 0;
            var owner = ReviewItem(data); player.inventory[0] = owner.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            owner.OnHitNPC(player, new NPC { active = true, Center = new Vector2(320,240) }, new NPC.HitInfo(), 1);
            var claim = peers.Sent[0]; peers.Sent.Clear();
            var server = ReviewItem(data); player.inventory[0] = server.Item;
            peers.Mode(NetmodeID.Server, 255); peers.Receive(claim, 0);
            MaterialClock(161); peers.System.PostUpdateEverything();
            using var wire = new MemoryStream(); owner.NetSend(new BinaryWriter(wire));
            wire.Position = 0; server.NetReceive(new BinaryReader(wire)); peers.System.PostUpdateEverything();
            Equal(0, peers.Sent.Count, "expired mismatched claim is not revived by later token sync");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ReviewContactItemData(); data.Id = "bounded_item_token";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>(); data.Normalize(); peers.Register(data);
            var player = Terraria.Main.player[0]; player.selectedItem = 0;
            var owner = ReviewItem(data); player.inventory[0] = owner.Item;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            for (int i=0; i<65; i++)
                owner.OnHitNPC(player, new NPC { active = true, Center = new Vector2(320,240) }, new NPC.HitInfo(), 1);
            var claims=peers.Sent.ToArray(); peers.Sent.Clear();
            var server=ReviewItem(data); player.inventory[0]=server.Item;
            peers.Mode(NetmodeID.Server, 255);
            foreach (var claim in claims) peers.Receive(claim, 0);
            var pending=(Array)typeof(InfiniItemVfxRuntime).GetField("PendingItemEvents",BindingFlags.NonPublic|BindingFlags.Static)!.GetValue(null)!;
            Equal(64, ((IList)pending.GetValue(0)!).Count, "pending claims are bounded per owner");
            var rejoined=new Player { active=true, whoAmI=0, selectedItem=0 };
            rejoined.inventory[0]=server.Item; Terraria.Main.player[0]=rejoined;
            peers.System.PostUpdateEverything();
            Equal(null, pending.GetValue(0), "old player session cannot retain pending events");
            Equal(0, peers.Sent.Count, "old session events never relay after reconnect");
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
    }

    private static void ItemTokenNativeSyncCycles()
    {
        using var peers = new ReviewPeers();
        var data = ReviewContactItemData(); data.Id="sync_cycles";
        data.VfxManifest.Slots=LightManifest(data.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnHit).Slots;
        data.VfxManifest.Assets=Array.Empty<VfxAssetSpec>(); data.Normalize(); peers.Register(data);
        var player=Terraria.Main.player[0]; player.selectedItem=0;
        var owner=ReviewItem(data); player.inventory[0]=owner.Item; peers.Mode(NetmodeID.MultiplayerClient,0);
        Item snapshot=owner.Item.Clone(); owner.Item.NetStateChanged(); int sends=0;
        for(int tick=0;tick<8;tick++) {
            if(owner.Item.IsNetStateDifferent(snapshot)) {
                using var memory=new MemoryStream(); Terraria.ModLoader.IO.ItemIO.Send(owner.Item,new BinaryWriter(memory),true,false); sends++;
            }
            snapshot=owner.Item.Clone();
        }
        Equal(1,sends,"first NetSend mints token and subsequent native comparison/clone cycles settle");
        var oldBaseline=Terraria.Main.clientPlayer;
        try {
            Terraria.Main.clientPlayer=new Player();
            var another=ReviewItem(data);
            // Both items have minted identities but equal numeric versions.
            another.Item.NetStateChanged(); using(var m=new MemoryStream()) Terraria.ModLoader.IO.ItemIO.Send(another.Item,new BinaryWriter(m),true,false);
            Equal(false,another.Item.IsNetStateDifferent(snapshot),"fixture has equal native versions");
            if(another.PresentationToken==owner.PresentationToken)throw new InvalidOperationException("fixture requires distinct tokens");
            Terraria.Main.clientPlayer.inventory[0]=snapshot;
            InfiniItemVfxRuntime.ClearUseEventCaches();
            InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,owner.Item,false);
            Terraria.Main.clientPlayer.inventory[0]=owner.Item.Clone();
            player.inventory[0]=another.Item;
            InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,another.Item,false);
            Equal(true,another.Item.IsNetStateDifferent(Terraria.Main.clientPlayer.inventory[0]),"A to B sends same-version identity");
            Terraria.Main.clientPlayer.inventory[0]=another.Item.Clone();
            int before=another.Item.NetStateVersion;
            for(int i=0;i<8;i++)InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,another.Item,false);
            Equal(before,another.Item.NetStateVersion,"steady state does not repeatedly dirty");
            // An intervening slot occupant need not have any generated-item hooks.
            player.inventory[0]=new Item { type=1, stack=1 };
            InfiniItemVfxRuntime.RefreshItemPresentationWitnesses(player);
            Terraria.Main.clientPlayer.inventory[0]=another.Item.Clone();
            player.inventory[0]=another.Item;
            InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,another.Item,false);
            Equal(true,another.Item.IsNetStateDifferent(Terraria.Main.clientPlayer.inventory[0]),"replacement without callbacks invalidates witness");
            Terraria.Main.clientPlayer.inventory[0]=another.Item.Clone();
            while(owner.Item.NetStateVersion<another.Item.NetStateVersion)owner.Item.NetStateChanged();
            player.inventory[0]=owner.Item;
            InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,owner.Item,false);
            Equal(true,owner.Item.IsNetStateDifferent(Terraria.Main.clientPlayer.inventory[0]),"B to A also defeats equal baseline");
            Terraria.Main.clientPlayer.armor[3]=another.Item.Clone(); player.armor[3]=owner.Item;
            while(owner.Item.NetStateVersion<another.Item.NetStateVersion)owner.Item.NetStateChanged();
            InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,owner.Item,true);
            Equal(true,owner.Item.IsNetStateDifferent(Terraria.Main.clientPlayer.armor[3]),"independent equipment baseline");
            Terraria.Main.clientPlayer.armor[3]=owner.Item.Clone();
            InfiniItemVfxRuntime.ClearUseEventCaches();
            InfiniItemVfxRuntime.ObserveItemPresentationSlot(player,owner.Item,true);
            Equal(true,owner.Item.IsNetStateDifferent(Terraria.Main.clientPlayer.armor[3]),"new session syncs identity");
        } finally { Terraria.Main.clientPlayer=oldBaseline; InfiniItemVfxRuntime.ClearUseEventCaches(); }
    }

    private static void ProjectileHitVfxAdmitsRetiredSource()
    {
        WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            InfiniCrafterLocal.Common.Runtime.RuntimeHitPullBridge.Clear();
            var data = ReviewProjectileData("on_hit"); peers.Register(data);
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            var owner = peers.Host(data);
            for (int i = 0; i < 3; i++)
                owner.OnHitNPC(new NPC { active = true, Center = new Vector2(320 + 16 * i, 240) }, new NPC.HitInfo(), 1);
            Equal(3, peers.Sent.Count, "owner emits three hit occurrences");
            var claims = peers.Sent.ToArray(); peers.Sent.Clear();
            var extra = ReviewExtra(owner);
            peers.Mode(NetmodeID.Server, 255);
            Terraria.Main.projectile = Enumerable.Range(0, Terraria.Main.maxProjectiles)
                .Select(i => new Projectile { whoAmI = i }).ToArray();
            var server = peers.Host(data, extra: extra);
            server.Projectile.active = false;
            peers.Receive(claims[0], 0);
            Equal(0, peers.Sent.Count, "inactive projectile without retirement proof is refused");
            server.Projectile.active = true;
            server.OnKill(10);
            server.Projectile.active = false;
            peers.Receive(claims[0], 0);
            Equal(1, peers.Sent.Count, "retired exact source relays owner hit");
            var relay = peers.Sent[0]; peers.Sent.Clear();
            peers.Receive(claims[0], 0);
            Equal(0, peers.Sent.Count, "replayed retired event is refused");
            peers.Receive(claims[1], 1);
            Equal(0, peers.Sent.Count, "another sender cannot claim retired hit");
            MaterialClock(161); peers.Receive(claims[1], 0);
            Equal(0, peers.Sent.Count, "retirement proof expires after bounded window");
            MaterialClock(200); server.Projectile.active = true; server.OnKill(10); server.Projectile.active = false;
            Terraria.Main.projectile[server.Projectile.whoAmI] = new Projectile { whoAmI = server.Projectile.whoAmI };
            peers.Receive(claims[2], 0);
            Equal(0, peers.Sent.Count, "reused slot cannot validate old generation");
            peers.Mode(NetmodeID.MultiplayerClient, 2); lights.Clear();
            int before = OwnedMaterialQueue().Count;
            peers.Receive(relay);
            Equal(before + 1, OwnedMaterialQueue().Count, "remote renders captured hit without a live projectile");
            InfiniCrafterLocal.Common.Runtime.RuntimeHitPullBridge.Clear();
        });
    }

    private static void MaterialUnresolvedItemForwardingRetainsToken()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = ParseMaterialElement(MaterialElementWire()); data.Id = "forward_material"; peers.Register(data);
            var owner = ReviewItem(data);
            using var first = new MemoryStream(); owner.NetSend(new BinaryWriter(first));
            first.Position = 0; Equal(8, new BinaryReader(first).ReadInt32(), "hydrated material item uses v8 with native prefix");
            var registryProperty = typeof(InfiniMod).GetProperty("GeneratedItems")!; registryProperty.SetValue(null, null);
            var unresolved = ReviewItem(GeneratedItemData.Placeholder()); first.Position = 0; unresolved.NetReceive(new BinaryReader(first));
            Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(unresolved.Data), "middle peer has only compact definition reference");
            using var forwarded = new MemoryStream(); unresolved.NetSend(new BinaryWriter(forwarded));
            forwarded.Position = 0; Equal(8, new BinaryReader(forwarded).ReadInt32(), "unresolved item keeps received material transport capability");
            registryProperty.SetValue(null, peers.Registry);
            var onward = ReviewItem(GeneratedItemData.Placeholder()); forwarded.Position = 0; onward.NetReceive(new BinaryReader(forwarded));
            Equal(data.Id, onward.Data.Id, "onward receiver hydrates exact canonical definition");
            Equal(owner.PresentationToken, onward.PresentationToken, "original token survives unresolved forwarding and late hydration");
            var legacy = ReviewItem(GeneratedItemData.Placeholder()); Equal(true, legacy.PresentationToken != 0, "legacy local token exists");
            using var oldWire = new MemoryStream(); legacy.NetSend(new BinaryWriter(oldWire)); oldWire.Position = 0;
            Equal(7, new BinaryReader(oldWire).ReadInt32(), "non-material items use v7 after local token allocation");
            oldWire.Position = 0; unresolved.NetReceive(new BinaryReader(oldWire));
            using var replacedWire = new MemoryStream(); unresolved.NetSend(new BinaryWriter(replacedWire)); replacedWire.Position = 0;
            Equal(7, new BinaryReader(replacedWire).ReadInt32(), "receiving a non-material replacement clears old material capability");
        });
    }

    private static void MaterialAssetsRequireExactReadyStatus()
    {
        int observations = 0;
        foreach (bool stripped in new[] { false, true })
        foreach (string status in new[] { "generated", "generated_warn_invalid", "failed", "prompt_only", "skipped", "not_required", "pending", "FAILED", "Generated", " generated", "generated ", "generated_warn_invalid ", "placeholder", "backend_config_error", "", "unknown" }) {
            var wire = MaterialElementWire(); var asset = wire["vfxManifest"]!["assets"]![0]!;
            asset["spriteStatus"] = status;
            if (stripped) { asset["prompt"] = ""; asset["negativePrompt"] = ""; }
            bool expected = status is "generated" or "generated_warn_invalid";
            Equal(expected, GeneratedItemData.FromJson(wire.ToJsonString()) is not null, $"runtime ingredient admission status='{status}' stripped={stripped}"); observations++;
        }
        var full = ParseMaterialElement(MaterialElementWire());
        var network = GeneratedItemData.FromJson(full.ToNetworkJson())!;
        Equal("", network.VfxManifest.Assets![0].Prompt, "ready network captions remain stripped");
        Equal("one isolated soft shard", full.VfxManifest.Assets![0].Prompt, "full ready captions stay intact");
        var legacy = GeneratedItemData.Placeholder();
        Equal(true, GeneratedItemData.FromJson(legacy.ToJson()) is not null, "old absent ingredients still admit");
        Equal(false, JsonNode.Parse(legacy.ToJson())!["vfxManifest"]!.AsObject().ContainsKey("assets"), "legacy absence is not populated");
        Console.WriteLine($"DETAIL: exact-ready material admission cases={observations}");
    }

    private static GeneratedItemData ReviewContactItemData()
    {
        var data = ParseMaterialElement(MaterialElementWire()); data.Id = "material_item_churn";
        var entity = data.RuntimeProgram.Entities[0]; var slot = data.VfxManifest.Slots[0]; slot.Event = "on_hit"; slot.RepeatEvery = 0; slot.Duration = 3; slot.Element!.Count = 1;
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Id = "primary", Role = RuntimeEntityRole.Primary, Input = RuntimeInputKind.PrimaryUse,
            UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true, Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = entity.Id } } } };
        data.RuntimeProgram.ItemUse.Configured = true; data.RuntimeProgram.ItemUse.DisableMeleeHitbox = false;
        return ParseMaterialElement(JsonNode.Parse(data.ToJson())!.AsObject());
    }
    private static byte[] ReviewItemWire(GeneratedItem generated)
    {
        using var memory = new MemoryStream(); generated.NetSend(new BinaryWriter(memory)); return memory.ToArray();
    }

    private static byte[] ReviewReplaceOccurrence(byte[] packet, bool item, ulong sequence)
    {
        var type = item ? typeof(InfiniItemVfxRuntime) : typeof(GeneratedProjectile);
        var payload = type.GetMethod(item ? "ReadMaterialItemEvent" : "ReadVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, new object[] { new BinaryReader(new MemoryStream(packet[(item ? 2 : 1)..])) })!;
        payload.GetType().GetProperty("Occurrence")!.SetValue(payload, sequence);
        using var memory = new MemoryStream(); var writer = new BinaryWriter(memory); writer.Write(packet[0]);
        type.GetMethod(item ? "WriteMaterialItemEvent" : "WriteVfxEventPayload", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { writer, payload });
        return memory.ToArray();
    }
    private static void MaterialPeerSessionReset(bool item)
    {
        // Native inventory publication is independently exercised by FirstHeldItemEventPublishesTokenBeforeClaim.
        // This socket-free fixture observes the event stream, not Terraria socket buffers.
        using var equipmentPublication = PersistenceObserveNetworkSend((_, __) => { });
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var data = item ? ReviewContactItemData() : ReviewProjectileData("on_hit"); data.VfxManifest.Slots[0].Duration = 3; peers.Register(data);
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            byte[] Produce(int owner, int identity, out byte[] hostWire) {
                peers.Sent.Clear(); Terraria.Main.myPlayer = owner;
                if (item) {
                    var source = ReviewItem(data); var player = Terraria.Main.player[owner]; player.selectedItem = 0; player.inventory[0] = source.Item;
                    source.OnHitNPC(player, new NPC { active = true }, new NPC.HitInfo(), 1); hostWire = ReviewItemWire(source);
                } else {
                    var source = peers.Host(data, 3, owner, identity); source.OnHitNPC(new NPC { active = true }, new NPC.HitInfo(), 1); hostWire = ReviewExtra(source);
                }
                return peers.Sent.Single();
            }
            void Hydrate(int owner, int identity, byte[] wire) {
                if (item) { var source = ReviewItem(data); source.NetReceive(new BinaryReader(new MemoryStream(wire))); Terraria.Main.player[owner].inventory[0] = source.Item; }
                else peers.Host(data, 11, owner, identity, wire);
            }
            var original = Produce(0, 71, out var originalWire);
            var senderTwo = Produce(1, 81, out var secondWire);
            var restarted = Produce(0, 72, out var restartedWire);
            peers.System.OnWorldUnload(); peers.Mode(NetmodeID.Server, 255); peers.Sent.Clear();
            Hydrate(0, 71, originalWire); var oldClaim = ReviewReplaceOccurrence(original, item, 500); peers.Receive(oldClaim, 0);
            Equal(1, peers.Sent.Count, "initial owner stream admitted");
            Hydrate(1, 81, secondWire); peers.Receive(ReviewReplaceOccurrence(senderTwo, item, 1), 1);
            Equal(2, peers.Sent.Count, "one sender's high sequence cannot starve another sender");
            var oldOwner = Terraria.Main.player[0]; var oldBuffer = NetMessage.buffer[0];
            try {
                NetMessage.buffer[0] = new MessageBuffer(); var client = new RemoteClient { Id = 0, IsActive = true, State = 10 }; client.Reset();
                Equal(false, ReferenceEquals(oldOwner, Terraria.Main.player[0]), "installed RemoteClient.Reset replaces owner session");
                Terraria.Main.player[0].whoAmI = 0; Terraria.Main.player[0].active = true; Terraria.Main.player[0].direction = 1;
                Hydrate(0, 72, restartedWire); var freshClaim = ReviewReplaceOccurrence(restarted, item, 1); peers.Receive(freshClaim, 0);
                Equal(3, peers.Sent.Count, "new owner connection admits a restarted producer sequence");
                peers.Receive(oldClaim, 0); peers.Receive(freshClaim, 0); Equal(3, peers.Sent.Count, "retired claim and new-session duplicate remain rejected");
            } finally { NetMessage.buffer[0] = oldBuffer; }
            var relays = peers.Sent.ToArray(); peers.Mode(NetmodeID.MultiplayerClient, 2);
            foreach (var packet in relays) peers.Receive(packet);
            Equal(3, OwnedMaterialQueue().Count, "server outbound sequence survives owner restart with unchanged remote Player");
            foreach (var packet in relays) peers.Receive(packet); Equal(3, OwnedMaterialQueue().Count, "all relay replays rejected");
            // Keep the actual decoder, change only an opaque socket identity. These
            // constructor-bypassed shells never create/connect/read/write a socket.
            var connection = Netplay.Connection; var previousSocket = connection.Socket;
            try {
                var lowRelay = ReviewReplaceOccurrence(relays[2], item, 1);
                MaterialClock(104); peers.System.PostUpdateEverything(); Equal(0, OwnedMaterialQueue().Count, "old session visuals expired");
                peers.Receive(lowRelay); Equal(0, OwnedMaterialQueue().Count, "same transport cannot rewind its trusted server stream");
                connection.Socket = (Terraria.Net.Sockets.ISocket)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Net.Sockets.TcpSocket));
                peers.Receive(lowRelay); Equal(1, OwnedMaterialQueue().Count, "fresh server transport session can restart its own sequence");
                peers.Receive(lowRelay); Equal(1, OwnedMaterialQueue().Count, "new transport replay suppressed too");
            } finally { connection.Socket = previousSocket; }
        });
    }

    private static int ReviewParticleCount(object emission)
        => ((Array)emission.GetType().GetField("Particles", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(emission)!).Length;

    private static GeneratedItemData ReviewItemLifecycleData(string attachment, bool hit = false)
    {
        var data = hit ? ReviewContactItemData() : ParseMaterialElement(MaterialElementWire(attachment));
        data.Id = "material_item_lifecycle";
        var slot = data.VfxManifest.Slots[0]; slot.Duration = 3; slot.Element!.Attachment = attachment; slot.Element.Count = 1;
        slot.Element.OffsetForwardPx = 0; slot.Element.OffsetSidePx = 0;
        slot.Element.SpeedMinPxPerTick = 0; slot.Element.SpeedMaxPxPerTick = 0; slot.Element.InheritVelocity = 0;
        data.VfxManifest.Budget.MaxParticlesPerTick = 256; data.VfxManifest.Budget.MaxParticlesTotal = 12000;
        return ParseMaterialElement(JsonNode.Parse(data.ToJson())!.AsObject());
    }

    private static void MaterialDeadItemDelayKeepsWorldSnapshotAndFencesSource()
    {
        // Native inventory publication is independently exercised by FirstHeldItemEventPublishesTokenBeforeClaim.
        // This socket-free fixture observes the event stream, not Terraria socket buffers.
        using var equipmentPublication = PersistenceObserveNetworkSend((_, __) => { });
        WithLighting((config, _) => {
            using var peers = new ReviewPeers(); config.ParticleSpawnMultiplier = 1;
            foreach (int mode in new[] { NetmodeID.SinglePlayer, NetmodeID.MultiplayerClient })
            foreach (string attachment in new[] { "world", "source" }) {
                peers.System.OnWorldUnload(); MaterialClock(100); peers.Mode(mode, 0);
                var data = ReviewItemLifecycleData(attachment, hit: true); data.VfxManifest.Slots[0].StartTick = 2;
                data = ParseMaterialElement(JsonNode.Parse(data.ToJson())!.AsObject()); peers.Register(data);
                var owner = Terraria.Main.player[0]; owner.dead = false; owner.selectedItem = 0; owner.Center = new Vector2(100, 200);
                var item = ReviewItem(data); owner.inventory[0] = item.Item;
                Vector2 captured = owner.Center;
                item.OnHitNPC(owner, new NPC { active = true, Center = new Vector2(117, 223) }, new NPC.HitInfo(), 1);
                Equal(1, OwnedMaterialQueue().Count, "actual item hit captures one delayed event");
                Equal(0, OwnedMaterialQueue().Cast<object>().Sum(ReviewParticleCount), "delayed event spends no particles at capture");
                owner.dead = true; owner.Center = new Vector2(700, 800); data.VfxManifest.Slots[0].Element!.WidthPx = 99;
                MaterialClock(102); peers.System.PostUpdateEverything();
                Equal(attachment == "world" ? 1 : 0, OwnedMaterialQueue().Count, "world snapshot survives death while exact source attachment retires");
                if (attachment == "world") {
                    object emission = OwnedMaterialQueue()[0]!;
                    var frame = (VfxSourceFrame)emission.GetType().GetField("Frame", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(emission)!;
                    Equal(captured, frame.Position, "delayed world event retains event-time owner coordinates after death/motion");
                    Equal(1, ReviewParticleCount(emission), "delayed world event starts at authored due tick");
                    object design = emission.GetType().GetField("Design", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(emission)!;
                    Equal(8f, (float)design.GetType().GetProperty("Width")!.GetValue(design)!, "delayed world design remains copied before mutation");
                }
                MaterialClock(105); peers.System.PostUpdateEverything();
                Equal(0, OwnedMaterialQueue().Count, "delayed world lifetime still expires at due+duration");
            }
        });
    }

}
