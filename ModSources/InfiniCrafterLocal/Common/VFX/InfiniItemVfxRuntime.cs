#nullable enable
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using System;
using System.IO;
using Terraria;
using Terraria.Audio;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Bounded item/equipment VFX lifecycle. Projectile events remain owned by
/// InfiniVfxRuntime; this consumer executes only exact item events and a small
/// renderer matrix validated by Python. It never routes names, tooltips or prose.
/// </summary>
public static class InfiniItemVfxRuntime
{
    private const byte UseEventSyncVersion = 1;
    private static readonly ulong[] LastServerUseEventTick = new ulong[Main.maxPlayers];
    private static readonly bool[] ServerUseEventSeen = new bool[Main.maxPlayers];

    public static void ClearUseEventCaches()
    {
        Array.Clear(LastServerUseEventTick);
        Array.Clear(ServerUseEventSeen);
    }

    public static void OnLive(Player player, GeneratedItemData? data, string eventName)
    {
        if (Main.dedServ || player is null || !player.active || player.dead || data?.VfxManifest is null)
            return;
        if (eventName is not ("while_held" or "while_equipped"))
            return;

        VfxManifestSpec manifest = data.VfxManifest;
        if (!manifest.HasSlots)
            return;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (slot is null || !string.Equals(slot.Event, eventName, StringComparison.Ordinal))
                continue;
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            if (kind is not (InfiniVfxRendererKind.OrbitingMotes or InfiniVfxRendererKind.ChildMotes or InfiniVfxRendererKind.LightCue))
                continue;
            if (!CadenceAllows(player, slot))
                continue;
            Color color = ResolveColor(data);
            if (kind == InfiniVfxRendererKind.LightCue)
            {
                AddLight(player.Center, color, slot);
                continue;
            }
            EmitLiveMote(player, slot, color, kind == InfiniVfxRendererKind.OrbitingMotes);
        }
    }

    public static void OnVisibleEquipment(Player player, GeneratedItemData? data)
    {
        OnLive(player, data, "while_equipped");
        if (Main.netMode == NetmodeID.Server || player is null || !player.active || player.dead || data is null)
            return;
        float strength = 0f;
        string colorName = "";
        if (data.Armor?.Enabled == true && data.Armor.LightStrength > 0f)
        {
            strength = data.Armor.LightStrength;
            colorName = data.Armor.LightColorName;
        }
        else if (data.Accessory?.Enabled == true && data.Accessory.LightStrength > 0f)
        {
            strength = data.Accessory.LightStrength;
            colorName = data.Accessory.LightColorName;
        }
        if (strength <= 0f)
            return;
        Color color = RuntimeColorPolicy.Resolve(colorName, Color.White);
        strength = Math.Clamp(strength, 0.02f, 1.5f);
        Lighting.AddLight(player.Center, color.R / 255f * strength, color.G / 255f * strength, color.B / 255f * strength);
    }

    public static void EmitAndSyncUse(Player player, GeneratedItemData? data, bool alternateUse)
    {
        OnUse(player, data, alternateUse);
        if (player.whoAmI != Main.myPlayer || !HasUseEvent(data, alternateUse))
            return;
        string itemId = (data!.Id ?? "").Trim();
        if (itemId.Length is <= 0 or > 96)
            return;
        if (Main.netMode == NetmodeID.Server && !Main.dedServ)
        {
            if (TryClaimServerUseEvent(player, data, alternateUse))
                RelayServerUseEvent(player.whoAmI, alternateUse, itemId);
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient
            || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
        packet.Write(UseEventSyncVersion);
        packet.Write(alternateUse);
        packet.Write(itemId);
        packet.Send();
    }

    public static void HandleUseEventPacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || Main.netMode == NetmodeID.SinglePlayer)
            return;
        try
        {
            byte version = reader.ReadByte();
            if (version != UseEventSyncVersion)
                return;

            if (Main.netMode == NetmodeID.Server)
            {
                bool alternateUse = reader.ReadBoolean();
                string itemId = (reader.ReadString() ?? "").Trim();
                if (whoAmI < 0 || whoAmI >= Main.maxPlayers || itemId.Length is <= 0 or > 96)
                    return;
                Player player = Main.player[whoAmI];
                if (player is null || !player.active
                    || player.HeldItem?.ModItem is not global::InfiniCrafterLocal.Content.Items.GeneratedItem generated
                    || !string.Equals(generated.Data?.Id, itemId, StringComparison.Ordinal)
                    || !TryClaimServerUseEvent(player, generated.Data, alternateUse))
                    return;
                RelayServerUseEvent(whoAmI, alternateUse, itemId);
                return;
            }

            int playerId = reader.ReadByte();
            bool remoteAlternateUse = reader.ReadBoolean();
            string remoteItemId = (reader.ReadString() ?? "").Trim();
            if (playerId < 0 || playerId >= Main.maxPlayers || remoteItemId.Length is <= 0 or > 96)
                return;
            Player remotePlayer = Main.player[playerId];
            if (remotePlayer is null || !remotePlayer.active)
                return;
            GeneratedItemData? data = remotePlayer.HeldItem?.ModItem is global::InfiniCrafterLocal.Content.Items.GeneratedItem held
                && string.Equals(held.Data?.Id, remoteItemId, StringComparison.Ordinal)
                ? held.Data
                : null;
            if (data is null
                && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is not null
                && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGet(remoteItemId, out GeneratedItemData registered))
                data = registered;
            OnUse(remotePlayer, data, remoteAlternateUse);
        }
        catch
        {
            // Malformed presentation packets are non-gameplay and fail closed.
        }
    }

    private static bool TryClaimServerUseEvent(Player player, GeneratedItemData? data, bool alternateUse)
    {
        if (player.whoAmI < 0 || player.whoAmI >= Main.maxPlayers || !HasUseEvent(data, alternateUse))
            return false;
        ulong now = Main.GameUpdateCount;
        ulong minimumInterval = (ulong)Math.Clamp(player.HeldItem.useTime, 2, 60);
        int playerId = player.whoAmI;
        if (ServerUseEventSeen[playerId] && now - LastServerUseEventTick[playerId] < minimumInterval)
            return false;
        ServerUseEventSeen[playerId] = true;
        LastServerUseEventTick[playerId] = now;
        return true;
    }

    private static void RelayServerUseEvent(int playerId, bool alternateUse, string itemId)
    {
        if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null)
            return;
        var relay = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        relay.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
        relay.Write(UseEventSyncVersion);
        relay.Write((byte)playerId);
        relay.Write(alternateUse);
        relay.Write(itemId);
        relay.Send(-1, playerId);
    }

    private static bool HasUseEvent(GeneratedItemData? data, bool alternateUse)
    {
        if (data?.VfxManifest?.Slots is not { Length: > 0 } slots)
            return false;
        string eventName = alternateUse ? "on_alt_use" : "on_use";
        foreach (VfxSlotSpec slot in slots)
        {
            if (slot is null || !string.Equals(slot.Event, eventName, StringComparison.Ordinal))
                continue;
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            if (kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ChildMotes
                or InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.SoundCue)
                return true;
        }
        return false;
    }

    private static void OnUse(Player player, GeneratedItemData? data, bool alternateUse)
    {
        if (Main.dedServ || player is null || !player.active || player.dead || data?.VfxManifest is null)
            return;
        string eventName = alternateUse ? "on_alt_use" : "on_use";
        VfxManifestSpec manifest = data.VfxManifest;
        if (!manifest.HasSlots)
            return;
        foreach (VfxSlotSpec slot in manifest.Slots)
        {
            if (slot is null || !string.Equals(slot.Event, eventName, StringComparison.Ordinal))
                continue;
            InfiniVfxRendererKind kind = VfxRendererRegistry.Resolve(slot);
            if (kind is not (InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ChildMotes
                or InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.SoundCue))
                continue;
            Color color = ResolveColor(data);
            if (kind == InfiniVfxRendererKind.LightCue)
                AddLight(player.Center, color, slot);
            else if (kind == InfiniVfxRendererKind.SoundCue)
                PlayUseSound(player, data.Attack, slot);
            else
                EmitUseBurst(player, slot, color, ring: kind == InfiniVfxRendererKind.ImpactRing);
        }
    }

    private static bool CadenceAllows(Player player, VfxSlotSpec slot)
    {
        int repeat = slot.RepeatEvery > 0
            ? Math.Clamp(slot.RepeatEvery, 3, 120)
            : Math.Clamp((int)MathF.Round(14f - slot.Density * 8f), 6, 14);
        long phase = Main.GameUpdateCount + slot.SlotSeed + player.whoAmI * 17L;
        return phase % repeat == 0;
    }

    private static void EmitLiveMote(Player player, VfxSlotSpec slot, Color color, bool orbit)
    {
        float radius = Math.Clamp(14f + slot.Spread * 10f, 10f, 42f);
        float angle = (float)(Main.GameUpdateCount * 0.045 + slot.SlotSeed * 0.0017);
        Vector2 offset = orbit
            ? new Vector2(radius, 0f).RotatedBy(angle)
            : Main.rand.NextVector2Circular(radius * 0.7f, radius);
        Vector2 velocity = orbit
            ? offset.SafeNormalize(Vector2.UnitY).RotatedBy(MathHelper.PiOver2) * 0.35f
            : new Vector2(0f, -0.35f) + Main.rand.NextVector2Circular(0.2f, 0.2f);
        SpawnDust(player.Center + offset, velocity, color, slot, 0.72f);
    }

    private static void EmitUseBurst(Player player, VfxSlotSpec slot, Color color, bool ring)
    {
        int count = Math.Clamp(2 + (int)MathF.Round(slot.Density * 7f), 2, 9);
        float speed = Math.Clamp(0.8f + slot.Spread * 1.2f, 0.6f, 3.8f);
        for (int i = 0; i < count; i++)
        {
            Vector2 velocity = ring
                ? new Vector2(speed, 0f).RotatedBy(MathHelper.TwoPi * i / Math.Max(1, count))
                : Main.rand.NextVector2Circular(speed, speed);
            SpawnDust(player.Center, velocity, color, slot, 1f);
        }
    }

    private static void SpawnDust(Vector2 position, Vector2 velocity, Color color, VfxSlotSpec slot, float scaleMultiplier)
    {
        int dustType = slot.ParticleSystemId switch
        {
            "pl:shard" => DustID.GemSapphire,
            "pl:smoke" => DustID.Smoke,
            "pl:spark" => DustID.Electric,
            "pl:glow" => DustID.MagicMirror,
            "dust" => DustID.MagicMirror,
            _ => DustID.GemDiamond,
        };
        float scale = Math.Clamp(slot.Scale * scaleMultiplier, 0.35f, 2.1f);
        Dust dust = Dust.NewDustPerfect(position, dustType, velocity, 80, color, scale);
        dust.noGravity = slot.ParticleSystemId != "pl:smoke";
        dust.fadeIn = Math.Clamp(scale * 0.45f, 0f, 1.2f);
    }

    private static void AddLight(Vector2 position, Color color, VfxSlotSpec slot)
    {
        if (Main.netMode == NetmodeID.Server)
            return;
        float strength = Math.Clamp(0.14f + slot.Scale * 0.16f + slot.Alpha * 0.18f, 0.12f, 0.8f);
        Lighting.AddLight(position, color.R / 255f * strength, color.G / 255f * strength, color.B / 255f * strength);
    }

    private static void PlayUseSound(Player player, AttackSpec? attack, VfxSlotSpec slot)
    {
        float volume = Math.Clamp((attack?.SoundVolume ?? 0.75f) * Math.Max(0.25f, slot.Alpha), 0.05f, 1f);
        float pitch = Math.Clamp(attack?.SoundPitch ?? 0f, -0.9f, 0.9f);
        SoundEngine.PlaySound(SoundID.Item4 with { Volume = volume, Pitch = pitch }, player.Center);
    }

    private static Color ResolveColor(GeneratedItemData data)
    {
        string colorName = data.Attack?.PrimaryColorName ?? "";
        if (data.Armor?.Enabled == true && !string.IsNullOrWhiteSpace(data.Armor.LightColorName))
            colorName = data.Armor.LightColorName;
        else if (data.Accessory?.Enabled == true && !string.IsNullOrWhiteSpace(data.Accessory.LightColorName))
            colorName = data.Accessory.LightColorName;
        return RuntimeColorPolicy.Resolve(colorName, Color.White);
    }
}
