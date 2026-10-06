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
    // v3 adds captured event coordinates. v2 is rejected; no legacy migration.
    private const byte PacketVersion = 3;
    private const int MaxRecentEventsPerPlayer = 64;
    private static readonly Dictionary<(string Item, string Entity, string Event), ulong>[] RecentEvents =
        new Dictionary<(string, string, string), ulong>[Main.maxPlayers];

    // Presentation-only throttle: exact events never suppress one another.
    // A bounded per-peer table also limits identity churn; no activation IDs or gameplay authority.
    private static bool AcceptRemoteEvent(Player player, string itemId, string entityId, string eventName)
    {
        int index = player.whoAmI;
        if (index < 0 || index >= RecentEvents.Length) return false;
        var recent = RecentEvents[index] ??= new();
        ulong now = Main.GameUpdateCount;
        var key = (itemId, entityId, eventName);
        if (recent.TryGetValue(key, out ulong last) && now >= last &&
            now - last < (ulong)Math.Clamp(player.HeldItem.useTime, 2, 60)) return false;
        // All stored cooldowns expire within 60 ticks. Prune without evicting live guards.
        foreach (var entry in new List<KeyValuePair<(string, string, string), ulong>>(recent))
            if (now < entry.Value || now - entry.Value >= 60) recent.Remove(entry.Key);
        if (!recent.ContainsKey(key) && recent.Count >= MaxRecentEventsPerPlayer) return false;
        recent[key] = now;
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
        Array.Clear(RecentEvents);
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

    public static void EmitAndSyncEvent(Player player, GeneratedItemData? data, string entityId, string eventName, Vector2? eventPosition = null)
    {
        if (player is null || !player.active || data is null || !HasExactSlot(data, entityId, eventName)) return;
        if (eventPosition.HasValue && !Finite(eventPosition.Value)) return;
        EmitLocal(player, data, entityId, eventName, eventPosition: eventPosition);
        if (player.whoAmI != Main.myPlayer || Main.netMode != NetmodeID.MultiplayerClient || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null) return;
        // Hit producers must supply their captured point; never relay an invented owner-center hit.
        if (eventName is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit && !eventPosition.HasValue) return;
        Vector2 point = eventPosition ?? player.Center;
        if (!Finite(point)) return;
        if(TrySendMaterialItemEvent(player,data,entityId,eventName,point))return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
        packet.Write(PacketVersion); packet.Write(data.Id ?? ""); packet.Write(entityId); packet.Write(eventName);
        packet.Write(point.X); packet.Write(point.Y); packet.Send();
    }

    public static void OnPeriodic(Player player, GeneratedItemData? data, string entityId, Item? sourceItem=null)
    {
        if (Main.dedServ || player is null || !player.active || data is null) return;
        string sourceKey=$"item:{player.whoAmI}:{data.Id}:{entityId}";
        InfiniDetachedVfxSystem.RegisterPeriodicElements(data,entityId,sourceKey,VfxSourceBinding.Capture(player,sourceItem,data),item:true);
        EmitLocal(player, data, entityId, RuntimeEventKind.Periodic, cadence: true);
    }

    public static void OnVisibleEquipment(Player player, GeneratedItemData? data, Item? sourceItem=null)
    {
        if (data is null) return;
        OnPeriodic(player, data, data.RuntimeProgram.ItemEntityId,sourceItem);
        float strength = data.Armor?.Enabled == true ? data.Armor.LightStrength : data.Accessory?.Enabled == true ? data.Accessory.LightStrength : 0f;
        string colorName = data.Armor?.Enabled == true ? data.Armor.LightColorName : data.Accessory?.LightColorName ?? "white";
        if (!Main.dedServ && strength > 0f)
            Lighting.AddLight(player.Center, RuntimeColorPolicy.Resolve(colorName, Color.White).ToVector3() * Math.Clamp(strength, 0f, 1.5f));
    }

    public static void HandleUseEventPacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || Main.netMode == NetmodeID.SinglePlayer) return;
        try
        {
            byte version=reader.ReadByte();
            if(version==MaterialItemPacketVersion){HandleMaterialItemEvent(reader,whoAmI);return;}
            if (version != PacketVersion) return;
            if (Main.netMode == NetmodeID.Server)
            {
                string itemId = (reader.ReadString() ?? "").Trim();
                string entityId = (reader.ReadString() ?? "").Trim();
                string eventName = (reader.ReadString() ?? "").Trim();
                Vector2 point = new(reader.ReadSingle(), reader.ReadSingle());
                if (!Finite(point) || whoAmI < 0 || whoAmI >= Main.maxPlayers) return;
                Player player = Main.player[whoAmI];
                if (player?.active != true || player.HeldItem?.ModItem is not GeneratedItem item || !string.Equals(item.Data.Id, itemId, StringComparison.Ordinal) || !HasExactSlot(item.Data, entityId, eventName)) return;
                if (!AcceptRemoteEvent(player, itemId, entityId, eventName)) return;
                var relay = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
                if (relay is null) return;
                relay.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
                relay.Write(PacketVersion); relay.Write((byte)whoAmI); relay.Write(itemId); relay.Write(entityId); relay.Write(eventName);
                relay.Write(point.X); relay.Write(point.Y); relay.Send(-1, whoAmI);
                return;
            }
            int playerId = reader.ReadByte();
            string remoteItemId = (reader.ReadString() ?? "").Trim();
            string remoteEntityId = (reader.ReadString() ?? "").Trim();
            string remoteEvent = (reader.ReadString() ?? "").Trim();
            Vector2 remotePoint = new(reader.ReadSingle(), reader.ReadSingle());
            if (!Finite(remotePoint) || playerId < 0 || playerId >= Main.maxPlayers) return;
            Player remote = Main.player[playerId];
            GeneratedItemData? data = remote?.HeldItem?.ModItem is GeneratedItem held && string.Equals(held.Data.Id, remoteItemId, StringComparison.Ordinal) ? held.Data : null;
            if (data is null && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.TryGet(remoteItemId, out GeneratedItemData registered) == true) data = registered;
            if (remote?.active == true && data is not null && HasExactSlot(data, remoteEntityId, remoteEvent) &&
                AcceptRemoteEvent(remote, remoteItemId, remoteEntityId, remoteEvent))
                EmitLocal(remote, data, remoteEntityId, remoteEvent,
                    eventPosition: remoteEvent is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit ? remotePoint : null,includeMaterials:false);
        }
        catch { }
    }

    // Same exact authored particle-system mapping as projectile event emission.
    // Keep item density/velocity/color presentation unchanged.
    private static int ItemDustId(VfxSlotSpec slot) => slot.ParticleSystemId switch
    {
        "pl:smoke" => DustID.Smoke,
        "pl:shard" => DustID.Glass,
        "pl:spark" => DustID.Electric,
        "pl:glow" => DustID.TintableDustLighted,
        _ => DustID.GemDiamond,
    };

    private static bool HasExactSlot(GeneratedItemData data, string entityId, string eventName)
    {
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
            if (string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) && string.Equals(slot.Event, eventName, StringComparison.Ordinal)) return true;
        return false;
    }

    private static void EmitLocal(Player player, GeneratedItemData data, string entityId, string eventName, bool cadence = false, Vector2? eventPosition = null,bool includeMaterials=true,MaterialEventAllowance? sharedAllowance=null)
    {
        if (Main.dedServ) return;
        // One synchronous event call owns its total across matching slots. Periodic
        // has only the shared tick ceiling; explicit zero remains silent for both.
        var eventAllowance=sharedAllowance??new MaterialEventAllowance(data.VfxManifest.Budget.MaxParticlesTotal);
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
        {
            if (!string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) || !string.Equals(slot.Event, eventName, StringComparison.Ordinal)) continue;
            if(InfiniDetachedVfxSystem.HasSnapshotVfx(slot)) {
                if(!cadence&&includeMaterials)InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,entityId,slot,$"item:{player.whoAmI}:{data.Id}:{entityId}",
                    VfxSourceBinding.ItemFrame(player,slot.Anchor,eventPosition),VfxSourceBinding.Capture(player,null,data),itemBudget:true,allowance:eventAllowance);
                continue;
            }
            int repeat = slot.RepeatEvery > 0 ? slot.RepeatEvery : 10;
            // The wire contract defines StartTick for projectile age only.
            // Item periodic cadence uses the world clock, not an invented item age.
            if (cadence && (Main.GameUpdateCount + (ulong)Math.Abs((long)slot.SlotSeed)) % (ulong)Math.Max(1, repeat) != 0) continue;
            if (slot.Anchor == "hitPoint" && !eventPosition.HasValue) continue;
            Vector2 center = slot.Anchor == "hitPoint" ? eventPosition!.Value
                : slot.Anchor is "tip" or "tipHistory" ? player.itemLocation : player.Center;
            if (!Finite(center)) continue;
            // Mark only after cadence and anchor eligibility: an invalid held pose
            // must not suppress a later valid equipment path in this same tick.
            if (cadence && !TryMarkPeriodicSlot(player, data, entityId, slot)) continue;
            Color color = InfiniVfxRuntime.PresentationColor(data, RuntimeColorPolicy.Resolve(data.Visual?.Palette?.Length > 0 ? data.Visual.Palette[0] : "white", Color.White));
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
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
                float strength = Math.Clamp(slot.Scale * 0.2f, 0.04f, 1.2f) * InfiniVfxClientOptions.PresentationLightMultiplier;
                if (strength > 0f)
                    Lighting.AddLight(center, color.ToVector3() * strength);
                continue;
            }
            if (kind == InfiniVfxRendererKind.SoundCue) { SoundEngine.PlaySound(SoundID.Item1 with { Volume = Math.Clamp(slot.Alpha, 0.05f, 1f), Pitch = Math.Clamp(slot.PhaseOffset * 0.25f, -0.5f, 0.5f) }, center); continue; }
            // Item-location effects follow the weapon-facing axis; velocity is an
            // explicit alternate anchor, not an implicit replacement for that aim.
            Vector2 forward = player.itemRotation.ToRotationVector2() * player.direction;
            if (slot.Anchor == "velocity") forward = player.velocity.SafeNormalize(forward);
            InfiniVfxRuntime.EmitPrimitive(data, center, forward, slot, data.VfxManifest, sourceKey, color);
            InfiniVfxRuntime.EmitEventSprite(data, entityId, center, forward, slot, data.VfxManifest, sourceKey);
            // Authored particles accompany the shape/snapshot; none disables only this lane.
            if (slot.ParticleSystemId is "none") continue;
            int count = InfiniVfxClientOptions.ScaleParticleCount(Math.Clamp(1 + (int)MathF.Round(slot.Density * 7f), 1, 8));
            for (int i = 0; i < count; i++)
            {
                if ((!cadence && eventAllowance.Remaining <= 0) || !TrySpendItemParticle(sourceKey, data.VfxManifest.Budget)) break;
                if (!cadence) eventAllowance.Remaining--;
                Vector2 velocity = Main.rand.NextVector2Circular(1f + slot.Spread, 1f + slot.Spread);
                Dust dust = Dust.NewDustPerfect(center, ItemDustId(slot), velocity, 100, color, Math.Clamp(slot.Scale, 0.2f, 3f));
                dust.noGravity = slot.ParticleSystemId is not "pl:smoke";
            }
        }
    }
}
