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
    private const int HeldItemPresentationSyncVersion = 3;
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

        // Remote player.itemAnimation / selected item can arrive a few ticks after our
        // compact held-presentation packet.  Let a fresh payload draw even while vanilla
        // player state catches up, otherwise generated weapons flicker or disappear on
        // peers during the exact first-use window people notice most.
        if (TryGetFreshRemotePayload(player, out _))
            return true;

        if (player.itemAnimation <= 0)
            return false;
        Item held = player.HeldItem;
        if (held is null || held.IsAir)
            return false;
        if (TryGetGeneratedHeldData(held, out var gi) && gi?.Data is not null)
            return !string.IsNullOrWhiteSpace(gi.Data.Visual?.SpritePath) && (held.noUseGraphic || held.useStyle > ItemUseStyleID.None);
        return false;
    }

    protected override void Draw(ref PlayerDrawSet drawInfo)
    {
        Player player = drawInfo.drawPlayer;
        TryGetFreshRemotePayload(player, out var payload);
        Item? held = player.HeldItem;
        bool hasHeld = held is not null && !held.IsAir;
        if (!hasHeld && payload is null)
            return;

        GeneratedItemData? data = null;
        if (held is not null && !held.IsAir && TryGetGeneratedHeldData(held, out var gi) && gi?.Data is not null)
            data = gi.Data;
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (data is null && payload is not null && !string.IsNullOrWhiteSpace(payload.GeneratedItemId)
            && registry is not null && registry.TryGet(payload.GeneratedItemId, out var registryData))
            data = registryData;

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
            try { texture = ModContent.Request<Texture2D>("InfiniCrafterLocal/Assets/GeneratedItem").Value; }
            catch { return; }
        }

        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        int drawDirection = payload is not null && payload.Direction < 0 ? -1 : payload is not null && payload.Direction > 0 ? 1 : (player.direction < 0 ? -1 : 1);
        float drawGravDir = payload is not null && Math.Abs(payload.GravDir) > 0.1f ? Math.Sign(payload.GravDir) : player.gravDir;
        bool flip = drawDirection < 0;
        SpriteEffects effects = flip ? SpriteEffects.FlipHorizontally : SpriteEffects.None;
        if (drawGravDir == -1f)
            effects |= SpriteEffects.FlipVertically;

        string role = BuildHeldRoleText(data, hasHeld ? held : null);
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
        Vector2 itemLocation = PayloadItemLocation(payload);
        Vector2 position = (itemLocation.LengthSquared() > 4f ? itemLocation : player.itemLocation) - Main.screenPosition + holdOffset;
        if (position.LengthSquared() < 4f)
            position = player.MountedCenter - Main.screenPosition + new Vector2(drawDirection * 8f, -4f * drawGravDir) + holdOffset;
        position += RoleForwardOffset(role, drawDirection, drawGravDir, data?.Gameplay?.InitialOffsetPx ?? 0);

        float rotation = payload is not null ? payload.ItemRotation : player.itemRotation;
        if (drawGravDir == -1f)
            rotation *= -1f;

        Color lightColor = Lighting.GetColor((int)(player.Center.X / 16f), (int)(player.Center.Y / 16f));
        if (data is not null)
            GeneratedItem.AddSoulDrawData(drawInfo.DrawDataCache, texture, position, source, lightColor, rotation, origin, drawScale, effects, data, 1.15f);
        else
            drawInfo.DrawDataCache.Add(new DrawData(texture, position, source, lightColor, rotation, origin, drawScale, effects, 0));
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
        if (!activeUse)
            return;

        int now = (int)Main.GameUpdateCount;
        string key = id + "|" + player.selectedItem + "|r" + QuantizedRotationBucket(player.itemRotation) + "|d" + player.direction;
        int repeatTicks = string.Equals(lastSyncKey, key, StringComparison.Ordinal) ? 18 : 6;
        if (now - lastSyncTick < repeatTicks)
            return;
        lastSyncKey = key;
        lastSyncTick = now;

        var payload = BuildLocalPayload(player, held, data);
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

    private static HeldItemPresentationPayload BuildLocalPayload(Player player, Item held, GeneratedItemData data)
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
                    return false;
            }
        }
        return payload is not null;
    }

    private static bool TryGetGeneratedHeldData(Item held, out GeneratedItem? gi)
    {
        gi = held?.ModItem as GeneratedItem;
        return gi is not null;
    }

    private static string BuildHeldRoleText(GeneratedItemData? data, Item? held)
    {
        var a = data?.Attack;
        var gp = data?.Gameplay;
        return string.Join(" ", new[]
        {
            a?.RuntimeFamily, a?.Delivery, a?.WeaponFamily, a?.WeaponSubfamily, a?.ProjectileFamily, gp?.HandPose, gp?.RotationMode,
            held?.useStyle == ItemUseStyleID.Shoot ? "shoot" : held?.useStyle == ItemUseStyleID.Swing ? "swing" : ""
        }).ToLowerInvariant();
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

    private static Vector2 HeldSpriteOrigin(Texture2D texture, string role, bool flip, float gravDir)
    {
        float x = 0.20f;
        float y = 0.62f;
        if (ContainsAny(role, "gun", "shotgun", "pistol", "musket", "rifle", "launcher", "rocket", "bow", "crossbow", "repeater"))
        {
            x = 0.16f; y = 0.52f;
        }
        else if (ContainsAny(role, "staff", "wand", "book", "magic", "cast", "beam", "laser"))
        {
            x = 0.18f; y = 0.58f;
        }
        else if (ContainsAny(role, "spear", "thrust", "lance", "pike", "trident", "shortsword", "stab"))
        {
            x = 0.10f; y = 0.52f;
        }
        else if (ContainsAny(role, "flail", "yoyo", "whip", "boomerang", "chakram"))
        {
            x = 0.14f; y = 0.56f;
        }
        else if (ContainsAny(role, "swing", "sword", "broadsword", "axe", "hammer", "pickaxe", "tool", "mace"))
        {
            x = 0.20f; y = 0.78f;
        }
        if (flip)
            x = 1f - x;
        if (gravDir == -1f)
            y = 1f - y;
        return new Vector2(texture.Width * x, texture.Height * y);
    }

    private static Vector2 HeldOffset(GeneratedItemData? data, float gravDir)
    {
        int x = data?.Gameplay?.HoldoutOffsetX ?? 0;
        int y = data?.Gameplay?.HoldoutOffsetY ?? 0;
        return new Vector2(x, y * gravDir);
    }

    private static Vector2 RoleForwardOffset(string role, int direction, float gravDir, int authoredInitialOffset)
    {
        float forward = 0f;
        float vertical = 0f;
        if (ContainsAny(role, "spear", "thrust", "lance", "pike", "trident", "shortsword", "stab")) forward = 8f;
        else if (ContainsAny(role, "gun", "shotgun", "launcher", "bow", "crossbow", "repeater")) forward = 5f;
        else if (ContainsAny(role, "staff", "wand", "magic", "book", "laser", "beam")) forward = 4f;
        else if (ContainsAny(role, "swing", "sword", "axe", "hammer", "tool")) { forward = 2f; vertical = -1f; }
        forward += Math.Clamp(authoredInitialOffset, -16, 24) * 0.35f;
        return new Vector2(direction * forward, vertical * gravDir);
    }

    private static bool ContainsAny(string text, params string[] needles)
    {
        if (string.IsNullOrWhiteSpace(text)) return false;
        foreach (string n in needles)
            if (!string.IsNullOrWhiteSpace(n) && text.Contains(n, StringComparison.OrdinalIgnoreCase))
                return true;
        return false;
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
