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
    private static readonly Dictionary<string, int> ParticlesThisTick = new(StringComparer.Ordinal);
    private static ulong ParticleTick;
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

    public static void ClearUseEventCaches()
    {
        MaterialItemEventStream.Clear();
        Array.Clear(HeldEventWitnesses);
        Array.Clear(ServerEvents);
        Array.Clear(ClientEvents);
        ParticlesThisTick.Clear();
        ParticleTick = 0;
        PeriodicSlotsThisTick.Clear();
        PeriodicTick = 0;
    }

    private static bool TrySpendItemParticle(string sourceKey, VfxQualityBudgetSpec budget)
    {
        ulong now = Main.GameUpdateCount;
        if (ParticleTick != now)
        {
            ParticleTick = now;
            ParticlesThisTick.Clear();
        }
        // Preserve explicit silence, but do not invent a positive-total lifetime.
        if (budget.MaxParticlesPerTick <= 0 || budget.MaxParticlesTotal <= 0) return false;
        ParticlesThisTick.TryGetValue(sourceKey, out int spent);
        if (spent >= budget.MaxParticlesPerTick) return false;
        if(!InfiniDetachedVfxSystem.TrySpendDetachedParticle(sourceKey,budget.MaxParticlesPerTick,int.MaxValue))return false;
        ParticlesThisTick[sourceKey] = spent + 1;
        return true;
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
        string sourceKey=$"item:{player.whoAmI}:{data.Id}:{entityId}";
        InfiniDetachedVfxSystem.RegisterPeriodicElements(data,entityId,sourceKey,VfxSourceBinding.Capture(player,sourceItem,data),item:true);
        EmitLocal(player, data, entityId, RuntimeEventKind.Periodic, cadence: true, allowLightCue: allowLightCue);
    }

    public static void OnVisibleEquipment(Player player, GeneratedItemData? data, Item? sourceItem=null)
    {
        if (data is null) return;
        // The visible-equipment scan includes vanity armor/accessories. It may
        // draw authored cosmetic VFX, but never illuminate the world. Functional
        // UpdateAccessory/UpdateEquip already own equipment light and lightCue.
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

    private static void EmitLocal(Player player, GeneratedItemData data, string entityId, string eventName, bool cadence = false, Vector2? eventPosition = null,bool includeMaterials=true,MaterialEventAllowance? sharedAllowance=null, bool allowLightCue=true, VfxSourceBinding? sourceBinding=null)
    {
        if (Main.dedServ) return;
        // One synchronous event call owns its total across matching slots. Periodic
        // has only the shared tick ceiling; explicit zero remains silent for both.
        var eventAllowance=sharedAllowance??new MaterialEventAllowance(data.VfxManifest.Budget.MaxParticlesTotal);
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
        {
            if (slot.PlacementBindingId is not null || !string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) || !string.Equals(slot.Event, eventName, StringComparison.Ordinal)) continue;
            if(InfiniDetachedVfxSystem.HasSnapshotVfx(slot)) {
                if(!cadence&&includeMaterials)InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,entityId,slot,$"item:{player.whoAmI}:{data.Id}:{entityId}",
                    VfxSourceBinding.ItemFrame(player,slot.Anchor,eventPosition),sourceBinding??VfxSourceBinding.Capture(player,EventSourceItem(player,data.Id,eventName)?.Item,data),itemBudget:true,allowance:eventAllowance);
                continue;
            }
            int repeat = cadence && slot.RepeatEvery!.Value > 0 ? slot.RepeatEvery!.Value : 10;
            // The wire contract defines StartTick for projectile age only.
            // Item periodic cadence uses the world clock, not an invented item age.
            if (cadence && (Main.GameUpdateCount + (ulong)Math.Abs((long)slot.SlotSeed)) % (ulong)Math.Max(1, repeat) != 0) continue;
            if (slot.Anchor == "hitPoint" && !eventPosition.HasValue) continue;
            Vector2 center = slot.Anchor == "hitPoint" ? eventPosition!.Value
                : slot.Anchor is "tip" or "tipHistory" ? player.itemLocation : player.Center;
            if (!Finite(center)) continue;
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            // Cosmetic/vanity passes must not emit light or consume the
            // periodic slot mark before a legitimate functional equipment hook.
            if (cadence && !allowLightCue && kind == InfiniVfxRendererKind.LightCue) continue;
            // Mark only after cadence and anchor eligibility: an invalid held pose
            // must not suppress a later valid equipment path in this same tick.
            if (cadence && !TryMarkPeriodicSlot(player, data, entityId, slot)) continue;
            if (kind == InfiniVfxRendererKind.SoundCue)
            {
                SoundStyle sound = slot.ResolveSoundStyle();
                if (sound.Volume > 0f) SoundEngine.PlaySound(sound, center);
                continue;
            }
            Color color = slot.Color!.ToColor();
            // Share this tick's allowance across events, slots and periodic presentation.
            string sourceKey = $"item:{player.whoAmI}:{data.Id}:{entityId}";
            if (kind == InfiniVfxRendererKind.ImpactSprite)
            {
                // Concurrent events/slots from this owner's item share one draw
                // allowance, including sprites that outlive the use/contact hook.
                InfiniVfxRuntime.EmitImpactSprite(data, entityId, center, player.velocity,
                    slot, data.VfxManifest, sourceKey);
                continue;
            }
            if (kind == InfiniVfxRendererKind.LightCue)
            {
                float strength = Math.Clamp(slot.Scale!.Value * 0.2f, 0.04f, 1.2f) * InfiniVfxClientOptions.PresentationLightMultiplier;
                if (strength > 0f)
                    Lighting.AddLight(center, color.ToVector3() * strength);
                continue;
            }
            // Item-location effects follow the weapon-facing axis; velocity is an
            // explicit alternate anchor, not an implicit replacement for that aim.
            Vector2 forward = player.itemRotation.ToRotationVector2() * player.direction;
            if (slot.Anchor == "velocity") forward = player.velocity.SafeNormalize(forward);
            InfiniVfxRuntime.EmitPrimitive(data, center, forward, slot, data.VfxManifest, sourceKey);
            InfiniVfxRuntime.EmitEventSprite(data, entityId, center, forward, slot, data.VfxManifest, sourceKey);
            // Authored particles accompany the shape/snapshot; none disables only this lane.
            if (slot.ParticleSystemId is "none") continue;
            int count = InfiniVfxClientOptions.ScaleParticleCount(Math.Clamp(1 + (int)MathF.Round(slot.Density!.Value * 7f), 1, 8));
            for (int i = 0; i < count; i++)
            {
                if ((!cadence && eventAllowance.Remaining <= 0) || !TrySpendItemParticle(sourceKey, data.VfxManifest.Budget)) break;
                if (!cadence) eventAllowance.Remaining--;
                Vector2 velocity = Main.rand.NextVector2Circular(1f + slot.Spread!.Value, 1f + slot.Spread!.Value);
                Dust dust = Dust.NewDustPerfect(center, VfxRendererRegistry.DustId(slot.ParticleSystemId), velocity, 100, color, Math.Clamp(slot.Scale!.Value, 0.2f, 3f));
                dust.noGravity = slot.ParticleSystemId is not "Smoke";
            }
        }
    }
}
