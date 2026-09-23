#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

internal enum GeneratedHeldRenderRole
{
    Generic, Swing, Thrust, Tethered, Ranged, Magic
}


/// <summary>
/// Runtime held-item renderer for generated items.
///
/// tModLoader's vanilla held-item renderer can only draw a ModItem's static Texture.
/// Generated items use per-instance PNG paths, so Tools/potions/weapons with noUseGraphic=true
/// need this custom layer.  The layer intentionally follows Terraria's player.itemLocation
/// and player.itemRotation state: those fields are what vanilla/tML use to place the
/// currently used item in the player's hands, including remote players.
/// </summary>
public sealed class GeneratedHeldItemDrawLayer : PlayerDrawLayer
{
    public const byte PacketSyncGeneratedHeldItemPresentation = InfiniNetPacketIds.SyncGeneratedHeldItemPresentation;
    private const int HeldItemPresentationSyncVersion = 4;
    private const int HeldSyncExpireTicks = 54;
    private const int HeldAssetRetryTicks = 90;

    private sealed class HeldItemPresentationPayload
    {
        public int PlayerId;
        public int SelectedItem;
        public string GeneratedItemId = "";
        public float ItemLocationX;
        public float ItemLocationY;
        public float ItemRotation;
        public int Direction;
        public float GravDir = 1f;
        public bool ActiveUse;
        public byte AnimationRemaining;
        public int ReceivedTick;
        public int ExpireTick;
    }

    private static readonly Dictionary<int, HeldItemPresentationPayload> RemoteHeldPresentations = new();
    private static readonly Dictionary<string, int> HeldAssetRequestTicks = new(StringComparer.OrdinalIgnoreCase);

    public override Position GetDefaultPosition() => new AfterParent(PlayerDrawLayers.HeldItem);

    public override bool GetDefaultVisibility(PlayerDrawSet drawInfo)
    {
        Player player = drawInfo.drawPlayer;
        if (player.dead || player.frozen)
            return false;

        bool hasRemotePayload = TryGetFreshRemotePayload(player, out var remotePayload);
        if (hasRemotePayload && remotePayload?.ActiveUse != true)
            return false;

        Item held = player.HeldItem;
        GeneratedItemData? data = ResolveHeldPresentationData(held, remotePayload);

        if (data is not null && !ShouldDrawHeldSprite(data, player, remotePayload))
            return false;
        if (hasRemotePayload)
            return remotePayload?.ActiveUse == true;
        if (player.itemAnimation <= 0 || held is null || held.IsAir || data is null)
            return false;
        if (!string.IsNullOrWhiteSpace(data.Visual?.SpritePath))
            return held.noUseGraphic || held.useStyle > ItemUseStyleID.None;
        return false;
    }

    private static GeneratedItemData? ResolveHeldPresentationData(Item? held, HeldItemPresentationPayload? payload)
    {
        GeneratedItemData? compact = null;
        string payloadId = (payload?.GeneratedItemId ?? "").Trim();
        string id = payloadId;
        if (held is not null && !held.IsAir && TryGetGeneratedHeldData(held, out var gi) && gi?.Data is not null)
        {
            compact = gi.Data;
            id = (gi.Data.Id ?? "").Trim();
            if (string.IsNullOrWhiteSpace(id))
                id = payloadId;
            if (!GeneratedItemData.IsPlayerSaveReferenceOnly(gi.Data))
                return gi.Data;
        }

        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (!string.IsNullOrWhiteSpace(id) && registry is not null && registry.TryGet(id, out var canonical))
            return canonical;

        if (!string.IsNullOrWhiteSpace(id))
            RequestHeldItemCatchup(id, null);
        return compact;
    }

    private static bool ShouldDrawHeldSprite(GeneratedItemData data, Player player, HeldItemPresentationPayload? payload)
    {
        string releaseTiming = (data.RuntimeProgram?.ItemUse?.ReleaseTiming ?? "").Trim().ToLowerInvariant();
        return releaseTiming != "immediate";
    }

    protected override void Draw(ref PlayerDrawSet drawInfo)
    {
        Player player = drawInfo.drawPlayer;
        TryGetFreshRemotePayload(player, out var payload);
        Item? held = player.HeldItem;
        bool hasHeld = held is not null && !held.IsAir;
        if (!hasHeld && payload is null)
            return;

        GeneratedItemData? data = ResolveHeldPresentationData(held, payload);

        string spritePath = data?.Visual?.SpritePath ?? "";
        if (string.IsNullOrWhiteSpace(spritePath))
        {
            RequestHeldItemCatchup(payload?.GeneratedItemId ?? data?.Id, null);
            return;
        }

        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(spritePath);
        if (texture is null)
        {
            RequestHeldItemCatchup(data?.Id ?? payload?.GeneratedItemId, spritePath);
            return;
        }

        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        int drawDirection = payload is not null && payload.Direction < 0 ? -1 : payload is not null && payload.Direction > 0 ? 1 : (player.direction < 0 ? -1 : 1);
        float drawGravDir = payload is not null && Math.Abs(payload.GravDir) > 0.1f ? Math.Sign(payload.GravDir) : player.gravDir;
        bool flip = drawDirection < 0;
        SpriteEffects effects = flip ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
        if (drawGravDir == -1f)
            effects |= SpriteEffects.FlipVertically;

        GeneratedHeldRenderRole role = ResolveHeldRenderRole(data, hasHeld ? held : null);
        // Do not multiply by Gameplay.ItemScale again for real GeneratedItem instances;
        // GetAdjustedItemScale already runs ModItem.ModifyItemScale for real held
        // GeneratedItem instances. Registry fallback gets the same ItemScale from the
        // hydrated definition, not from this cheap pose packet.
        float baseScale = held is not null && !held.IsAir ? player.GetAdjustedItemScale(held) : 1f;
        bool heldHasGeneratedData = held is not null && !held.IsAir && TryGetGeneratedHeldData(held, out var heldGiForScale) && heldGiForScale?.Data is not null;
        float registryScale = data?.Gameplay?.ItemScale ?? 1f;
        float payloadScale = heldHasGeneratedData ? 1f : Math.Clamp(registryScale <= 0f ? 1f : registryScale, 0.55f, 1.55f);
        float drawScale = Math.Clamp(baseScale * payloadScale, 0.45f, 1.85f);
        Vector2 origin = HeldSpriteOrigin(texture, role, flip, drawGravDir);
        Vector2 holdOffset = HeldOffset(data, drawGravDir);
        Vector2 itemLocation = payload is not null ? PayloadItemLocation(payload) : drawInfo.ItemLocation;
        Vector2 position = (itemLocation.LengthSquared() > 4f ? itemLocation : player.itemLocation) - Main.screenPosition + holdOffset;
        if (position.LengthSquared() < 4f)
            position = player.MountedCenter - Main.screenPosition + new Vector2(drawDirection * 8f, -4f * drawGravDir) + holdOffset;
        position += RoleForwardOffset(role, drawDirection, drawGravDir, 0);
        position = new Vector2((int)position.X, (int)position.Y);

        float rotation = payload is not null ? payload.ItemRotation : player.itemRotation;
        if (drawGravDir == -1f)
            rotation *= -1f;

        Color lightColor = Lighting.GetColor((int)(player.Center.X / 16f), (int)(player.Center.Y / 16f));
        Color tint = held is not null && !held.IsAir ? held.GetAlpha(lightColor) : lightColor;
        drawInfo.DrawDataCache.Add(new DrawData(texture, position, source, tint, rotation, origin, drawScale, effects, 0));
    }

    public static void MaybeBroadcastLocalHeldItem(Player player, ref int lastSyncTick, ref string lastSyncKey)
    {
        if (Main.netMode == NetmodeID.SinglePlayer || player is null || player.whoAmI != Main.myPlayer)
            return;
        Item held = player.HeldItem;
        if (held is null || held.IsAir || !TryGetGeneratedHeldData(held, out var gi) || gi?.Data is null)
            return;
        var data = gi.Data;
        string id = (data.Id ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id))
            return;

        bool activeUse = player.itemAnimation > 0 || player.controlUseItem || player.controlUseTile;
        string activeKeyPrefix = id + "|active|";
        bool wasActive = lastSyncKey.StartsWith(activeKeyPrefix, StringComparison.Ordinal)
            || lastSyncKey.Contains("|active|", StringComparison.Ordinal);
        if (!activeUse && !wasActive)
            return;

        int now = (int)Main.GameUpdateCount;
        string key = activeUse
            ? activeKeyPrefix + player.selectedItem + "|r" + QuantizedRotationBucket(player.itemRotation) + "|d" + player.direction
            : id + "|inactive|" + player.selectedItem;
        int repeatTicks = string.Equals(lastSyncKey, key, StringComparison.Ordinal) ? 18 : 6;
        if (now - lastSyncTick < repeatTicks)
            return;
        lastSyncKey = key;
        lastSyncTick = now;

        var payload = BuildLocalPayload(player, held, data, activeUse);
        SendHeldItemPresentationPayload(payload, toClient: -1, ignoreClient: -1);
    }

    public static void HandleHeldItemPresentationSyncPacket(BinaryReader reader, int whoAmI)
    {
        HeldItemPresentationPayload payload;
        try { payload = ReadHeldItemPresentationPayload(reader); }
        catch { return; }
        if (payload.PlayerId < 0 || payload.PlayerId >= Main.maxPlayers)
            return;

        if (Main.netMode == NetmodeID.Server)
        {
            // Local player -> server -> other clients.  Never trust the player id from the
            // client payload: stamp it from the packet sender so one client cannot draw a
            // fake generated weapon in another player's hands.
            payload.PlayerId = Math.Clamp(whoAmI, 0, Main.maxPlayers - 1);
            bool authoritativeGenerated = false;
            try
            {
                Player sender = Main.player[payload.PlayerId];
                if (sender is not null && sender.active)
                {
                    payload.SelectedItem = Math.Clamp(sender.selectedItem, 0, 58);
                    if (sender.HeldItem?.ModItem is GeneratedItem authoritative && authoritative.Data is not null)
                    {
                        payload.GeneratedItemId = ShortNet(authoritative.Data.Id, 96);
                        authoritativeGenerated = !string.IsNullOrWhiteSpace(payload.GeneratedItemId);
                    }
                }
            }
            catch { }
            if (!authoritativeGenerated)
                return;
            SendHeldItemPresentationPayload(payload, toClient: -1, ignoreClient: whoAmI);
            return;
        }

        payload.ReceivedTick = (int)Main.GameUpdateCount;
        payload.ExpireTick = payload.ReceivedTick + HeldSyncExpireTicks;
        lock (RemoteHeldPresentations)
            RemoteHeldPresentations[payload.PlayerId] = payload;
        RequestHeldItemCatchup(payload.GeneratedItemId, null);
    }

    private static HeldItemPresentationPayload BuildLocalPayload(Player player, Item held, GeneratedItemData data, bool activeUse)
    {
        return new HeldItemPresentationPayload
        {
            PlayerId = player.whoAmI,
            SelectedItem = player.selectedItem,
            GeneratedItemId = ShortNet(data.Id, 96),
            ItemLocationX = player.itemLocation.X,
            ItemLocationY = player.itemLocation.Y,
            ItemRotation = player.itemRotation,
            Direction = player.direction < 0 ? -1 : 1,
            GravDir = player.gravDir == -1f ? -1f : 1f,
            ActiveUse = activeUse,
            AnimationRemaining = (byte)Math.Clamp((int)MathF.Round(
                Math.Clamp(player.itemAnimation / (float)Math.Max(1, player.itemAnimationMax), 0f, 1f) * 255f), 0, 255),
        };
    }

    private static void WriteHeldItemPresentationPayload(BinaryWriter writer, HeldItemPresentationPayload payload)
    {
        writer.Write(HeldItemPresentationSyncVersion);
        writer.Write((byte)Math.Clamp(payload.PlayerId, 0, Main.maxPlayers - 1));
        writer.Write((byte)Math.Clamp(payload.SelectedItem, 0, 58));
        writer.Write(ShortNet(payload.GeneratedItemId, 96));
        writer.Write(Math.Clamp(payload.ItemLocationX, -2_000_000f, 2_000_000f));
        writer.Write(Math.Clamp(payload.ItemLocationY, -2_000_000f, 2_000_000f));
        writer.Write(Math.Clamp(payload.ItemRotation, -MathHelper.TwoPi * 4f, MathHelper.TwoPi * 4f));
        writer.Write(Math.Clamp(payload.Direction, -1, 1));
        writer.Write(payload.GravDir < 0f ? -1f : 1f);
        writer.Write(payload.ActiveUse);
        writer.Write(payload.AnimationRemaining);
    }

    private static HeldItemPresentationPayload ReadHeldItemPresentationPayload(BinaryReader reader)
    {
        int version = reader.ReadInt32();
        if (version != HeldItemPresentationSyncVersion)
            throw new InvalidDataException($"Unsupported held item presentation sync version {version}; expected {HeldItemPresentationSyncVersion}.");
        return new HeldItemPresentationPayload
        {
            PlayerId = reader.ReadByte(),
            SelectedItem = reader.ReadByte(),
            GeneratedItemId = reader.ReadString(),
            ItemLocationX = reader.ReadSingle(),
            ItemLocationY = reader.ReadSingle(),
            ItemRotation = reader.ReadSingle(),
            Direction = reader.ReadInt32(),
            GravDir = reader.ReadSingle(),
            ActiveUse = reader.ReadBoolean(),
            AnimationRemaining = reader.ReadByte(),
        };
    }

    private static void SendHeldItemPresentationPayload(HeldItemPresentationPayload payload, int toClient, int ignoreClient)
    {
        if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null || Main.netMode == NetmodeID.SinglePlayer)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketSyncGeneratedHeldItemPresentation);
        WriteHeldItemPresentationPayload(packet, payload);
        if (Main.netMode == NetmodeID.Server)
            packet.Send(toClient, ignoreClient);
        else
            packet.Send();
    }

    private static bool TryGetFreshRemotePayload(Player player, out HeldItemPresentationPayload? payload)
    {
        payload = null;
        if (player is null || player.whoAmI == Main.myPlayer)
            return false;
        lock (RemoteHeldPresentations)
        {
            if (!RemoteHeldPresentations.TryGetValue(player.whoAmI, out payload) || payload is null)
                return false;
            int now = (int)Main.GameUpdateCount;
            if (payload.ExpireTick < now)
            {
                RemoteHeldPresentations.Remove(player.whoAmI);
                payload = null;
                return false;
            }
            if (payload.SelectedItem != player.selectedItem)
            {
                bool remoteHeldMissing = player.HeldItem is null || player.HeldItem.IsAir || player.HeldItem.ModItem is not GeneratedItem;
                bool firstUseGrace = now - payload.ReceivedTick <= 30;
                if (!remoteHeldMissing && !firstUseGrace)
                {
                    payload = null;
                    return false;
                }
            }
        }
        return payload is not null;
    }

    private static bool TryGetGeneratedHeldData(Item held, out GeneratedItem? gi)
    {
        gi = held?.ModItem as GeneratedItem;
        return gi is not null;
    }

    private static GeneratedHeldRenderRole ResolveHeldRenderRole(GeneratedItemData? data, Item? held)
    {
        // Presentation pose is derived only from the explicitly authored item-use
        // component. It is not a gameplay family/classifier.
        string pose = (data?.RuntimeProgram?.ItemUse?.HandPose ?? "").Trim().ToLowerInvariant();
        string style = (data?.RuntimeProgram?.ItemUse?.UseStyle ?? "").Trim().ToLowerInvariant();
        if (pose == "staff" || style == "hold_up") return GeneratedHeldRenderRole.Magic;
        if (pose == "held_out" || style == "shoot") return GeneratedHeldRenderRole.Ranged;
        if (style is "thrust" or "rapier") return GeneratedHeldRenderRole.Thrust;
        if (style == "swing") return GeneratedHeldRenderRole.Swing;
        return GeneratedHeldRenderRole.Generic;
    }

    private static Vector2 PayloadItemLocation(HeldItemPresentationPayload? payload)
    {
        if (payload is null) return Vector2.Zero;
        if (float.IsNaN(payload.ItemLocationX) || float.IsNaN(payload.ItemLocationY)) return Vector2.Zero;
        if (Math.Abs(payload.ItemLocationX) > 2_000_000f || Math.Abs(payload.ItemLocationY) > 2_000_000f) return Vector2.Zero;
        return new Vector2(payload.ItemLocationX, payload.ItemLocationY);
    }

    private static int QuantizedRotationBucket(float rotation)
    {
        if (float.IsNaN(rotation) || float.IsInfinity(rotation)) return 0;
        return (int)MathF.Round(rotation * 8f);
    }

    public static void ClearNetCaches()
    {
        lock (RemoteHeldPresentations) RemoteHeldPresentations.Clear();
        lock (HeldAssetRequestTicks) HeldAssetRequestTicks.Clear();
    }

    private static Vector2 HeldSpriteOrigin(Texture2D texture, GeneratedHeldRenderRole role, bool flip, float gravDir)
    {
        (float x, float y) = role switch
        {
            GeneratedHeldRenderRole.Ranged => (0.16f, 0.52f),
            GeneratedHeldRenderRole.Magic => (0.18f, 0.58f),
            GeneratedHeldRenderRole.Thrust => (0.10f, 0.52f),
            GeneratedHeldRenderRole.Tethered => (0.14f, 0.56f),
            GeneratedHeldRenderRole.Swing => (0.20f, 0.78f),
            _ => (0.20f, 0.62f),
        };
        if (flip)
            x = 1f - x;
        if (gravDir == -1f)
            y = 1f - y;
        return new Vector2(texture.Width * x, texture.Height * y);
    }

    private static Vector2 HeldOffset(GeneratedItemData? data, float gravDir)
    {
        int x = data?.RuntimeProgram?.ItemUse?.HoldoutOffsetX ?? 0;
        int y = data?.RuntimeProgram?.ItemUse?.HoldoutOffsetY ?? 0;
        return new Vector2(x, y * gravDir);
    }

    private static Vector2 RoleForwardOffset(GeneratedHeldRenderRole role, int direction, float gravDir, int authoredInitialOffset)
    {
        float forward = role switch
        {
            GeneratedHeldRenderRole.Thrust => 8f,
            GeneratedHeldRenderRole.Ranged => 5f,
            GeneratedHeldRenderRole.Magic => 4f,
            GeneratedHeldRenderRole.Swing => 2f,
            _ => 0f,
        };
        float vertical = role == GeneratedHeldRenderRole.Swing ? -1f : 0f;
        forward += Math.Clamp(authoredInitialOffset, -16, 24) * 0.35f;
        return new Vector2(direction * forward, vertical * gravDir);
    }

    private static void RequestHeldItemCatchup(string? generatedItemId, string? spritePath)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        string id = (generatedItemId ?? "").Trim();
        string asset = HasPngPath(spritePath) ? GeneratedAssetSyncService.FileNameFromPath(spritePath) : "";
        string key = !string.IsNullOrWhiteSpace(id) ? "item:" + id : "asset:" + asset;
        if (string.IsNullOrWhiteSpace(key) || key == "asset:")
            return;
        int now = (int)Main.GameUpdateCount;
        lock (HeldAssetRequestTicks)
        {
            if (HeldAssetRequestTicks.TryGetValue(key, out int last) && now - last < HeldAssetRetryTicks)
                return;
            HeldAssetRequestTicks[key] = now;
        }
        if (!string.IsNullOrWhiteSpace(id))
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: true);
        else
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer(forceAssetRetry: true);
    }

    private static bool HasPngPath(string? value)
    {
        string s = (value ?? "").Trim();
        return s.EndsWith(".png", StringComparison.OrdinalIgnoreCase) || s.Contains(".png", StringComparison.OrdinalIgnoreCase);
    }

    private static string ShortNet(string? value, int max)
    {
        if (string.IsNullOrEmpty(value) || max <= 0) return "";
        return value.Length <= max ? value : value[..max];
    }
}
