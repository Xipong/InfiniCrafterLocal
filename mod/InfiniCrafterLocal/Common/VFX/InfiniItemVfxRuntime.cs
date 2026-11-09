#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.IO;
using System.Collections.Generic;
using Terraria;
using Terraria.Audio;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.Default;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>Exact item-body entity/event VFX with bounded multiplayer relay.</summary>
public static partial class InfiniItemVfxRuntime
{
    // Independent occurrences can legitimately share an event and a world tick.
    // Bound accepted network work without using item useTime as an event identity.
    private const int MaxRemoteEventsPerPlayerPerTick = 64;
    private static readonly (ulong Tick, int Count, Player? Player, object? Socket)[] ServerEvents = new (ulong, int, Player?, object?)[Main.maxPlayers];
    private static readonly (ulong Tick, int Count, Player? Player, object? Socket)[] ClientEvents = new (ulong, int, Player?, object?)[Main.maxPlayers];

    private static bool AdmitRemoteEvent(int owner)
    {
        if (owner < 0 || owner >= Main.maxPlayers) return false;
        var limits = Main.netMode == NetmodeID.Server ? ServerEvents : ClientEvents;
        ulong tick = Main.GameUpdateCount;
        var player = Main.player[owner];
        object? socket = Main.netMode == NetmodeID.Server ? Netplay.Clients[owner]?.Socket : Netplay.Connection?.Socket;
        var entry = limits[owner];
        if (entry.Tick != tick || !ReferenceEquals(entry.Player, player) || !ReferenceEquals(entry.Socket, socket))
            entry = (tick, 0, player, socket);
        if (entry.Count >= MaxRemoteEventsPerPlayerPerTick) return false;
        limits[owner] = (tick, entry.Count + 1, player, socket);
        return true;
    }

    private static bool Finite(Vector2 point) => float.IsFinite(point.X) && float.IsFinite(point.Y);

    // Item bodies have no canonical activation/lifetime boundary. Only keep
    // tick-local particle counts; a persistent total would silence held/equipped
    // items forever while rejected attempts keep the detached ledger alive.
    // Held, functional equipment and visible equipment can visit the same slot
    // in one world tick. This guard owns periodic presentation only, not events.
    private static readonly HashSet<(int Owner, string Item, string Entity, string Slot)> PeriodicSlotsThisTick = new();
    private static ulong PeriodicTick;

    private static bool TryMarkPeriodicSlot(Player player, GeneratedItemData data, string entityId, VfxSlotSpec slot)
    {
        ulong now = Main.GameUpdateCount;
        if (PeriodicTick != now)
        {
            PeriodicTick = now;
            PeriodicSlotsThisTick.Clear();
        }
        return PeriodicSlotsThisTick.Add((player.whoAmI, data.Id, entityId, slot.Id));
    }

    // Witness the actual source in each slot rather than relying on an item’s
    // numeric net version, which can coincide for two independent instances.
    private static readonly Dictionary<string, (Item Item, object Generation)> ItemSlotWitnesses = new();
    private static Player? ItemSlotWitnessPlayer;
    private static object? ItemSlotWitnessSocket;

    internal static void ObserveItemPresentationSlot(Player player, Item item, bool equipment)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || player.whoAmI != Main.myPlayer
            || !ReferenceEquals(Main.player[Main.myPlayer], player) || Main.clientPlayer is null
            || item.ModItem is not GeneratedItem generated) return;
        object? socket = Netplay.Connection?.Socket;
        if (!ReferenceEquals(ItemSlotWitnessPlayer, player) || !ReferenceEquals(ItemSlotWitnessSocket, socket)) {
            ItemSlotWitnesses.Clear(); ItemSlotWitnessPlayer = player; ItemSlotWitnessSocket = socket;
        }
        string? key = null; Item? baseline = null;
        if (!equipment) {
            int slot = player.selectedItem;
            if (slot >= 0 && slot < player.inventory.Length && slot < Main.clientPlayer.inventory.Length
                && ReferenceEquals(player.inventory[slot], item)) {
                key = "inventory:" + slot; baseline = Main.clientPlayer.inventory[slot];
            }
        } else {
            for (int i = 0; i < player.armor.Length && i < Main.clientPlayer.armor.Length; i++) {
                if (!ReferenceEquals(player.armor[i], item)) continue;
                key = "armor:" + i; baseline = Main.clientPlayer.armor[i]; break;
            }
            if (key is null) {
                foreach (var slot in ModContent.GetContent<ModAccessorySlot>()) {
                    int i = slot.Type;
                    if (i < 0 || i >= player.GetModPlayer<ModAccessorySlotPlayer>().LoadedSlotCount
                        || i >= Main.clientPlayer.GetModPlayer<ModAccessorySlotPlayer>().LoadedSlotCount) continue;
                    Item live;
                    using (new Main.CurrentPlayerOverride(player)) live = slot.FunctionalItem;
                    if (!ReferenceEquals(live, item)) continue;
                    using (new Main.CurrentPlayerOverride(Main.clientPlayer)) baseline = slot.FunctionalItem;
                    key = "mod-accessory:" + i; break;
                }
            }
        }
        if (key is null || baseline is null) return;
        if (ItemSlotWitnesses.TryGetValue(key, out var previous)
            && ReferenceEquals(previous.Item, item) && ReferenceEquals(previous.Generation, generated.PresentationGeneration)) return;
        ItemSlotWitnesses[key] = (item, generated.PresentationGeneration);
        // Only native synchronization transports metadata. Force a version
        // difference if the exact current slot baseline would hide this item.
        if (generated.HasItemEventVfx && !item.IsNetStateDifferent(baseline)) item.NetStateChanged();
    }

    // A replacement may have no GeneratedItem callbacks. Forget witnesses for
    // slots whose content changed, even while they do not produce VFX.
    internal static void RefreshItemPresentationWitnesses(Player player)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !ReferenceEquals(ItemSlotWitnessPlayer, player)
            || player.whoAmI != Main.myPlayer || ItemSlotWitnesses.Count == 0) return;
        Dictionary<int, Item>? currentModSlots = null;
        foreach (string key in ItemSlotWitnesses.Keys) {
            if (!key.StartsWith("mod-accessory:", StringComparison.Ordinal)) continue;
            currentModSlots = new Dictionary<int, Item>();
            foreach (var slot in ModContent.GetContent<ModAccessorySlot>()) {
                int i = slot.Type;
                if (i < 0 || i >= player.GetModPlayer<ModAccessorySlotPlayer>().LoadedSlotCount) continue;
                using (new Main.CurrentPlayerOverride(player)) currentModSlots[i] = slot.FunctionalItem;
            }
            break;
        }
        List<string>? removed = null;
        foreach (var entry in ItemSlotWitnesses) {
            int separator = entry.Key.IndexOf(':');
            if (separator < 0 || !int.TryParse(entry.Key.Substring(separator + 1), out int index)) { (removed ??= new()).Add(entry.Key); continue; }
            var kind = entry.Key.Substring(0, separator);
            Item? current = kind == "inventory" && index >= 0 && index < player.inventory.Length ? player.inventory[index]
                : kind == "armor" && index >= 0 && index < player.armor.Length ? player.armor[index]
                : kind == "mod-accessory" && currentModSlots is not null && currentModSlots.TryGetValue(index, out var modItem) ? modItem : null;
            if (!ReferenceEquals(current, entry.Value.Item)) (removed ??= new()).Add(entry.Key);
        }
        if (removed is not null) foreach (string key in removed) ItemSlotWitnesses.Remove(key);
    }

    public static void ClearUseEventCaches()
    {
        ItemSlotWitnesses.Clear(); ItemSlotWitnessPlayer = null; ItemSlotWitnessSocket = null;
        MaterialItemEventStream.Clear();
        Array.Clear(ItemHistories);
        Array.Clear(PendingItemEvents);
        PendingAirJumpEvents.Clear();
        Array.Clear(HeldEventWitnesses);
        Array.Clear(ServerEvents);
        Array.Clear(ClientEvents);
        PeriodicSlotsThisTick.Clear();
        PeriodicTick = 0;
    }

    private static GeneratedItem? EventSourceItem(Player player, string itemId, string eventName)
        => eventName is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill
            ? player.GetModPlayer<global::InfiniCrafterLocal.Common.Players.InfiniCraftPlayer>().FindReactiveEquipment(itemId)
            : player.HeldItem?.ModItem is GeneratedItem held && held.Data.Id == itemId ? held : null;

    public static void EmitAndSyncEvent(Player player, GeneratedItemData? data, string entityId, string eventName, Vector2? eventPosition = null)
    {
        if (eventName == RuntimeEventKind.OnJump) return; // exact live grant owns this producer
        if (player is null || !player.active || data is null || !HasExactSlot(data, entityId, eventName)) return;
        if (eventPosition.HasValue && !Finite(eventPosition.Value)) return;
        if(eventName=="on_use")BeginHeldHistory(player,data,entityId);
        EmitLocal(player, data, entityId, eventName, eventPosition: eventPosition);
        if (player.whoAmI != Main.myPlayer || Main.netMode != NetmodeID.MultiplayerClient || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null) return;
        // Hit producers must supply their captured point; never relay an invented owner-center hit.
        if (eventName is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit && !eventPosition.HasValue) return;
        Vector2 point = eventPosition ?? player.Center;
        if (!Finite(point)) return;
        SendItemEvent(player,data,entityId,eventName,point);
    }

    public static void OnPeriodic(Player player, GeneratedItemData? data, string entityId, Item? sourceItem=null, bool allowLightCue=true)
    {
        if (Main.dedServ || player is null || !player.active || data is null) return;
        ObserveItemPresentationSlot(player, sourceItem ?? player.HeldItem, sourceItem is not null);
        string sourceKey=$"item:{player.whoAmI}:{data.Id}:{entityId}";
        InfiniDetachedVfxSystem.RegisterPeriodicElements(data,entityId,sourceKey,VfxSourceBinding.Capture(player,sourceItem,data),item:true,allowLightCue:allowLightCue);
        EmitLocal(player, data, entityId, RuntimeEventKind.Periodic, cadence: true, allowLightCue: allowLightCue);
    }

    public static void OnVisibleEquipment(Player player, GeneratedItemData? data, Item? sourceItem=null)
    {
        if (data is null) return;
        // The visible-equipment scan includes vanity armor/accessories. It may
        // draw authored cosmetic VFX, but never illuminate the world. Functional
        // UpdateAccessory/UpdateEquip already own equipment light and nativeLight.
        OnPeriodic(player, data, data.RuntimeProgram.ItemEntityId,sourceItem,allowLightCue:false);
    }

    public static void HandleUseEventPacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || Main.netMode == NetmodeID.SinglePlayer) return;
        try
        {
            // Earlier payloads had no event identity and cannot distinguish
            // two genuine hits from a replay. They are refused, not guessed.
            byte version = reader.ReadByte();
            if (version == MaterialItemPacketVersion) HandleMaterialItemEvent(reader, whoAmI);
            else if (version == AirJumpPacketVersion) HandleAirJumpEvent(reader, whoAmI);
        }
        catch { }
    }

    private static bool HasExactSlot(GeneratedItemData data, string entityId, string eventName)
    {
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
            if (slot.PlacementBindingId is null && string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) && string.Equals(slot.Event, eventName, StringComparison.Ordinal)) return true;
        return false;
    }

    private static void EmitLocal(Player player, GeneratedItemData data, string entityId, string eventName, bool cadence = false, Vector2? eventPosition = null,bool includeMaterials=true,MaterialEventAllowance? sharedAllowance=null, bool allowLightCue=true, VfxSourceBinding? sourceBinding=null, InfiniItemVfxSnapshot? capturedSnapshot=null)
    {
        if (Main.dedServ) return;
        // One synchronous event call owns its total across matching slots. Periodic
        // has only the shared tick ceiling; explicit zero remains silent for both.
        var eventAllowance=sharedAllowance??new MaterialEventAllowance(data.VfxManifest.Budget.MaxParticlesTotal);
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
        {
            if (slot.PlacementBindingId is not null || !string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) || !string.Equals(slot.Event, eventName, StringComparison.Ordinal)) continue;
            if(slot.Trail is not null)continue; // exact-use history is drawn with the native held body
            VfxSourceFrame? eventFrame=capturedSnapshot is {} snapshot
                ?snapshot.Frame(slot.Anchor,eventPosition??snapshot.Center):null;
            if(InfiniDetachedVfxSystem.HasSnapshotVfx(slot)) {
                if(!cadence&&includeMaterials)InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,entityId,slot,$"item:{player.whoAmI}:{data.Id}:{entityId}",
                    eventFrame??VfxSourceBinding.ItemFrame(player,slot.Anchor,eventPosition),sourceBinding??VfxSourceBinding.Capture(player,EventSourceItem(player,data.Id,eventName)?.Item,data),itemBudget:true,allowance:eventAllowance);
                continue;
            }
            int repeat = cadence ? slot.RepeatEvery!.Value : 1;
            // The wire contract defines StartTick for projectile age only.
            // Item periodic cadence uses the world clock, not an invented item age.
            if (cadence && (Main.GameUpdateCount + (ulong)Math.Abs((long)slot.SlotSeed)) % (ulong)Math.Max(1, repeat) != 0) continue;
            if (slot.Anchor == "hitPoint" && !eventPosition.HasValue) continue;
            Vector2 center = eventFrame?.Position ?? (slot.Anchor == "hitPoint" ? eventPosition!.Value
                : slot.Anchor is "tip" or "tipHistory" ? player.itemLocation : player.Center);
            if (!Finite(center)) continue;
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            // Mark only after cadence and anchor eligibility: an invalid held pose
            // must not suppress a later valid equipment path in this same tick.
            if (cadence && !TryMarkPeriodicSlot(player, data, entityId, slot)) continue;
            if (kind == InfiniVfxRendererKind.SoundCue)
            {
                SoundStyle sound = slot.ResolveSoundStyle();
                if (sound.Volume > 0f) SoundEngine.PlaySound(sound, center);
                continue;
            }
        }
    }
}
