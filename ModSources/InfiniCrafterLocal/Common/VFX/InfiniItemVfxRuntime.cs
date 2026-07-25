#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.IO;
using Terraria;
using Terraria.Audio;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>Exact item-body entity/event VFX with bounded multiplayer relay.</summary>
public static class InfiniItemVfxRuntime
{
    private const byte PacketVersion = 2;
    private static readonly ulong[] LastEventTick = new ulong[Main.maxPlayers];

    public static void ClearUseEventCaches() => Array.Clear(LastEventTick);

    public static void EmitAndSyncEvent(Player player, GeneratedItemData? data, string entityId, string eventName)
    {
        if (player is null || !player.active || data is null || !HasExactSlot(data, entityId, eventName)) return;
        EmitLocal(player, data, entityId, eventName);
        if (player.whoAmI != Main.myPlayer || Main.netMode != NetmodeID.MultiplayerClient || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null) return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
        packet.Write(PacketVersion); packet.Write(data.Id ?? ""); packet.Write(entityId); packet.Write(eventName); packet.Send();
    }

    public static void OnPeriodic(Player player, GeneratedItemData? data, string entityId)
    {
        if (Main.dedServ || player is null || !player.active || data is null) return;
        EmitLocal(player, data, entityId, RuntimeEventKind.Periodic, cadence: true);
    }

    public static void OnVisibleEquipment(Player player, GeneratedItemData? data)
    {
        if (data is null) return;
        OnPeriodic(player, data, data.RuntimeProgram.ItemEntityId);
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
            if (reader.ReadByte() != PacketVersion) return;
            if (Main.netMode == NetmodeID.Server)
            {
                string itemId = (reader.ReadString() ?? "").Trim();
                string entityId = (reader.ReadString() ?? "").Trim();
                string eventName = (reader.ReadString() ?? "").Trim();
                if (whoAmI < 0 || whoAmI >= Main.maxPlayers) return;
                Player player = Main.player[whoAmI];
                if (player?.HeldItem?.ModItem is not GeneratedItem item || !string.Equals(item.Data.Id, itemId, StringComparison.Ordinal) || !HasExactSlot(item.Data, entityId, eventName)) return;
                ulong now = Main.GameUpdateCount;
                if (now - LastEventTick[whoAmI] < (ulong)Math.Clamp(player.HeldItem.useTime, 2, 60)) return;
                LastEventTick[whoAmI] = now;
                var relay = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
                if (relay is null) return;
                relay.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
                relay.Write(PacketVersion); relay.Write((byte)whoAmI); relay.Write(itemId); relay.Write(entityId); relay.Write(eventName); relay.Send(-1, whoAmI);
                return;
            }
            int playerId = reader.ReadByte();
            string remoteItemId = (reader.ReadString() ?? "").Trim();
            string remoteEntityId = (reader.ReadString() ?? "").Trim();
            string remoteEvent = (reader.ReadString() ?? "").Trim();
            if (playerId < 0 || playerId >= Main.maxPlayers) return;
            Player remote = Main.player[playerId];
            GeneratedItemData? data = remote?.HeldItem?.ModItem is GeneratedItem held && string.Equals(held.Data.Id, remoteItemId, StringComparison.Ordinal) ? held.Data : null;
            if (data is null && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.TryGet(remoteItemId, out GeneratedItemData registered) == true) data = registered;
            if (remote is not null && data is not null) EmitLocal(remote, data, remoteEntityId, remoteEvent);
        }
        catch { }
    }

    private static bool HasExactSlot(GeneratedItemData data, string entityId, string eventName)
    {
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
            if (string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) && string.Equals(slot.Event, eventName, StringComparison.Ordinal)) return true;
        return false;
    }

    private static void EmitLocal(Player player, GeneratedItemData data, string entityId, string eventName, bool cadence = false)
    {
        if (Main.dedServ) return;
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
        {
            if (!string.Equals(slot.EntityId, entityId, StringComparison.Ordinal) || !string.Equals(slot.Event, eventName, StringComparison.Ordinal)) continue;
            int repeat = slot.RepeatEvery > 0 ? slot.RepeatEvery : 10;
            if (cadence && (Main.GameUpdateCount + (ulong)Math.Abs(slot.SlotSeed)) % (ulong)Math.Max(1, repeat) != 0) continue;
            Color color = RuntimeColorPolicy.Resolve(data.Visual?.Palette?.Length > 0 ? data.Visual.Palette[0] : "white", Color.White);
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            if (kind == InfiniVfxRendererKind.LightCue) { Lighting.AddLight(player.Center, color.ToVector3() * Math.Clamp(slot.Scale * 0.2f, 0.04f, 1.2f)); continue; }
            if (kind == InfiniVfxRendererKind.SoundCue) { SoundEngine.PlaySound(SoundID.Item1 with { Volume = Math.Clamp(slot.Alpha, 0.05f, 1f) }, player.Center); continue; }
            int count = Math.Clamp(1 + (int)MathF.Round(slot.Density * 7f), 1, 8);
            for (int i = 0; i < count; i++)
            {
                Vector2 velocity = Main.rand.NextVector2Circular(1f + slot.Spread, 1f + slot.Spread);
                Dust dust = Dust.NewDustPerfect(player.Center, DustID.GemDiamond, velocity, 100, color, Math.Clamp(slot.Scale, 0.2f, 3f));
                dust.noGravity = true;
            }
        }
    }
}
