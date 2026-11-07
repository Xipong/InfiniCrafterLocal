using System;
using System.Linq;
using System.IO;
using InfiniCrafterLocal.Common.VFX;
using Terraria;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Real producer, packet serializer and receiver; only network Send is captured.
    // Both arrival orders must have one remote producer, not tick/position guessing.
    private static void RemoteProjectileEventsHaveOneProducer()
    {
        foreach (string ev in new[] { RuntimeEventKind.OnSpawn, RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit })
        foreach (bool callbackFirst in new[] { true, false })
        WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            var data = ReviewProjectileData(ev);
            data.VfxManifest.Slots = LightManifest("actor", ev).Slots;
            peers.Register(data);
            var emit = typeof(GeneratedProjectile).GetMethod("EmitAndSyncVfxEvent", BindingFlags.Instance | BindingFlags.NonPublic)!;
            void Callback(GeneratedProjectile source) => emit.Invoke(source, new object[] { ev, new Vector2(320, 240) });
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            var owner = peers.Host(data);
            var wire = ReviewExtra(owner);
            int occurrences = ev == RuntimeEventKind.OnSpawn ? 1 : 2;
            if (ev != RuntimeEventKind.OnSpawn)
                for (int i = 0; i < occurrences; i++) Callback(owner);
            var claims = peers.Sent.ToArray(); peers.Sent.Clear();
            peers.Mode(NetmodeID.Server, 255);
            var server = peers.Host(data, extra: wire);
            if (ev == RuntimeEventKind.OnSpawn) Callback(server);
            else foreach (var claim in claims) peers.Receive(claim, 0);
            var relays = peers.Sent.ToArray();
            Equal(occurrences, relays.Length, "distinct same-tick producer occurrences are relayed");
            peers.Mode(NetmodeID.MultiplayerClient, 2);
            var remote = peers.Host(data, extra: wire);
            lights.Clear();
            if (callbackFirst) Callback(remote);
            foreach (var relay in relays) peers.Receive(relay);
            if (!callbackFirst) Callback(remote);
            Equal(occurrences, lights.Count, ev + " callback and relay have exactly one remote producer in either order");
            Callback(remote); foreach (var relay in relays) peers.Receive(relay);
            Equal(occurrences, lights.Count, "repeated native callback and packet replay cannot duplicate remote VFX");
        });
    }
    private static void FirstHeldItemEventPublishesTokenBeforeClaim()
    {
        WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            InfiniItemVfxRuntime.ClearUseEventCaches();
            var data = ReviewContactItemData(); data.Id = "first-held-event";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<VfxAssetSpec>();
            data.Normalize();
            peers.Register(data);
            var ownerPlayer = Terraria.Main.player[0]; ownerPlayer.selectedItem = 2;
            var owner = ReviewItem(data); ownerPlayer.inventory[2] = owner.Item;
            var serverPlayer = new Player { whoAmI = 0, active = true, selectedItem = 0 };
            int syncs = 0, controls = 0;
            using var nativeSync = PersistenceObserveNetworkSend((message, slot) => {
                if (message == MessageID.PlayerControls) { controls++; serverPlayer.selectedItem = ownerPlayer.selectedItem; }
                if (message != MessageID.SyncEquipment) return;
                syncs++;
                // Actual generated compact serializer/decoder at the socket seam.
                var serverItem = ReviewItem(data);
                serverItem.NetReceive(new BinaryReader(new MemoryStream(ReviewItemWire(owner))));
                serverPlayer.inventory[slot] = serverItem.Item;
            });
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            owner.OnHitNPC(ownerPlayer, new NPC { active = true }, new NPC.HitInfo(), 1);
            var first = peers.Sent.Single(); peers.Sent.Clear();
            peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = serverPlayer;
            Equal(1, syncs, "source publication occurs before claim");
            Equal(2, serverPlayer.selectedItem, "native selection publication reaches server");
            var synchronized = (InfiniCrafterLocal.Content.Items.GeneratedItem)serverPlayer.HeldItem.ModItem!;
            Equal(owner.PresentationToken, synchronized.PresentationToken, "published token matches claim");
            Equal(data.Id, synchronized.Data.Id, "native compact publication retains canonical definition");
            peers.Receive(first, 0);
            Equal(1, peers.Sent.Count, "first event with a new token survives without manual prior item synchronization");
            Equal(1, syncs, "only exact source slot is synchronized");
            Equal(1, controls, "selected slot precedes the held-item claim");
            peers.Sent.Clear(); Terraria.Main.player[0] = ownerPlayer;
            // A -> silent B (ordinary controls reached server) -> A before the
            // next end-of-frame sync. No B VFX invalidates the cached A witness.
            serverPlayer.selectedItem = 1;
            peers.Mode(NetmodeID.MultiplayerClient, 0);
            owner.OnHitNPC(ownerPlayer, new NPC { active = true }, new NPC.HitInfo(), 1);
            var second = peers.Sent.Single(); peers.Sent.Clear();
            Equal(1, syncs, "another same-token hit does not resend inventory");
            peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = serverPlayer;
            peers.Receive(second, 0);
            Equal(1, peers.Sent.Count, "return from a silent selected item preserves the distinct same-tick occurrence");
            Equal(2, controls, "selected controls are republished even when the item witness is cached");
            peers.Receive(first, 0); peers.Receive(second, 0);
            Equal(1, peers.Sent.Count, "replays still cannot cross the occurrence fence");
            foreach (bool moveSlot in new[] { false, true })
            {
                Terraria.Main.player[0] = ownerPlayer; peers.Mode(NetmodeID.MultiplayerClient, 0); peers.Sent.Clear();
                if (moveSlot)
                {
                    ownerPlayer.inventory[2] = new Item(); ownerPlayer.selectedItem = 4;
                }
                else owner = ReviewItem(data); // same recipe, new physical generation
                ownerPlayer.inventory[ownerPlayer.selectedItem] = owner.Item;
                owner.OnHitNPC(ownerPlayer, new NPC { active = true }, new NPC.HitInfo(), 1);
                var fresh = peers.Sent.Single(); peers.Sent.Clear();
                Equal(moveSlot ? 3 : 2, syncs, "new instance or native slot republishes its exact witness");
                peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = serverPlayer;
                peers.Receive(fresh, 0); Equal(1, peers.Sent.Count, "new held witness is immediately usable");
                peers.Receive(first, 0); Equal(1, peers.Sent.Count, "old generation stays rejected after replacement");
            }
            InfiniItemVfxRuntime.ClearUseEventCaches();
        });
    }

}
