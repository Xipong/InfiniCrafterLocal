#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

// AGENT MAP: server-authoritative multiplayer craft protocol.
// Client side only sends a request id plus compact references to two local input
// items. Host/server reconstructs and consumes real inventory slots, runs the
// same GeneratorClient path, commits the generated item, then sends ACK/FAIL.
// Never add a client-authored GeneratedItemData commit path here.
public sealed partial class InfiniCraftPlayer
{

    private bool BeginRemoteServerCraft(Item a, Item b)
    {
        if (HasPendingCraft)
            return false;

        CaptureAudioSettingsSnapshot();

        string requestId = Guid.NewGuid().ToString("N");
        string parentA = LocalParentName(a);
        string parentB = LocalParentName(b);

        var refundA = a.Clone();
        refundA.stack = 1;
        var refundB = b.Clone();
        refundB.stack = 1;

        _request = new GeneratorClient.PreparedGenerationRequest
        {
            PayloadJson = "{}",
            ParentA = parentA,
            ParentB = parentB,
            RefundA = refundA,
            RefundB = refundB
        };
        _label = $"{parentA} + {parentB}";
        _ticksLeft = CraftDurationTicks;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _generationAttempt = 0;
        _retryWaitTicks = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        _serverRequestId = requestId;
        _awaitingServerCommit = true;
        _serverCraftWaitTicks = 0;
        _task = null;

        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketRequestServerCraft);
        packet.Write(requestId);
        WriteCraftItemRef(packet, a);
        WriteCraftItemRef(packet, b);
        packet.Send();

        CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, "InfiniCraft: запрос крафта отправлен хосту");
        return true;
    }

    private bool BeginServerAuthoritativeCraft(GeneratorClient.PreparedGenerationRequest request, string label, string requestId)
    {
        if (HasPendingCraft)
            return false;

        _request = request;
        _label = label;
        _ticksLeft = CraftDurationTicks;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _generationAttempt = 0;
        _retryWaitTicks = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        _serverRequestId = requestId ?? "";
        _awaitingServerCommit = false;
        _serverCraftWaitTicks = 0;
        _task = null;

        StartGenerationTask("server_authoritative");
        return true;
    }



    private void WriteGeneratedBuffState(System.IO.BinaryWriter writer)
    {
        writer.Write((byte)Player.whoAmI);
        writer.Write((byte)1); // state version
        writer.Write(_generatedBuffTicks);
        writer.Write(_generatedMiningSpeedMultiplier);
        writer.Write(_generatedLightStrength);
        writer.Write(_generatedLightColorName ?? "");
        writer.Write(_generatedOreSenseRadiusTiles);
        writer.Write(_generatedMovementSpeed);
        writer.Write(_generatedJumpBoost);
        writer.Write(_generatedManaRegen);
        writer.Write(_generatedLifeRegen);
        writer.Write(_generatedMobilityCooldownTicks);
    }

    private void ReadGeneratedBuffState(System.IO.BinaryReader reader)
    {
        _ = reader.ReadByte(); // version
        _generatedBuffTicks = reader.ReadInt32();
        _generatedMiningSpeedMultiplier = reader.ReadSingle();
        _generatedLightStrength = reader.ReadSingle();
        _generatedLightColorName = reader.ReadString();
        _generatedOreSenseRadiusTiles = reader.ReadInt32();
        _generatedMovementSpeed = reader.ReadSingle();
        _generatedJumpBoost = reader.ReadSingle();
        _generatedManaRegen = reader.ReadInt32();
        _generatedLifeRegen = reader.ReadInt32();
        _generatedMobilityCooldownTicks = reader.ReadInt32();
        ClampGeneratedBuffState();
    }

    private void ClampGeneratedBuffState()
    {
        _generatedBuffTicks = Math.Clamp(_generatedBuffTicks, 0, 21600);
        _generatedMiningSpeedMultiplier = Math.Clamp(_generatedMiningSpeedMultiplier <= 0f ? 1f : _generatedMiningSpeedMultiplier, 0.25f, 4f);
        _generatedLightStrength = Math.Clamp(_generatedLightStrength, 0f, 1.5f);
        _generatedLightColorName = string.IsNullOrWhiteSpace(_generatedLightColorName) ? "" : _generatedLightColorName.Trim()[..Math.Min(_generatedLightColorName.Trim().Length, 32)];
        _generatedOreSenseRadiusTiles = Math.Clamp(_generatedOreSenseRadiusTiles, 0, 60);
        _generatedMovementSpeed = Math.Clamp(_generatedMovementSpeed, -0.5f, 2f);
        _generatedJumpBoost = Math.Clamp(_generatedJumpBoost, 0f, 8f);
        _generatedManaRegen = Math.Clamp(_generatedManaRegen, 0, 120);
        _generatedLifeRegen = Math.Clamp(_generatedLifeRegen, 0, 120);
        _generatedMobilityCooldownTicks = Math.Clamp(_generatedMobilityCooldownTicks, 0, 36000);
    }

    private bool GeneratedBuffStateDiffers(InfiniCraftPlayer other)
    {
        if (other is null) return true;

        bool activeNow = _generatedBuffTicks > 0;
        bool activeOld = other._generatedBuffTicks > 0;
        bool cooldownNow = _generatedMobilityCooldownTicks > 0;
        bool cooldownOld = other._generatedMobilityCooldownTicks > 0;

        // Do not sync every countdown tick. Remote clients can decrement their local
        // copy after one start/end packet; per-tick SendClientChanges would spam MP.
        if (activeNow != activeOld || cooldownNow != cooldownOld)
            return true;
        if (Math.Abs(_generatedBuffTicks - other._generatedBuffTicks) > 30)
            return true;
        if (Math.Abs(_generatedMobilityCooldownTicks - other._generatedMobilityCooldownTicks) > 30)
            return true;

        return Math.Abs(_generatedMiningSpeedMultiplier - other._generatedMiningSpeedMultiplier) > 0.001f
            || Math.Abs(_generatedLightStrength - other._generatedLightStrength) > 0.001f
            || !string.Equals(_generatedLightColorName, other._generatedLightColorName, StringComparison.Ordinal)
            || _generatedOreSenseRadiusTiles != other._generatedOreSenseRadiusTiles
            || Math.Abs(_generatedMovementSpeed - other._generatedMovementSpeed) > 0.001f
            || Math.Abs(_generatedJumpBoost - other._generatedJumpBoost) > 0.001f
            || _generatedManaRegen != other._generatedManaRegen
            || _generatedLifeRegen != other._generatedLifeRegen;
    }

    private void SendGeneratedBuffState(int toWho = -1, int fromWho = -1)
    {
        if (Main.netMode == NetmodeID.SinglePlayer)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketSyncGeneratedUtilityBuff);
        WriteGeneratedBuffState(packet);
        packet.Send(toWho, fromWho);
    }

    public override void SyncPlayer(int toWho, int fromWho, bool newPlayer)
    {
        SendGeneratedBuffState(toWho, fromWho);
    }

    public override void CopyClientState(ModPlayer targetCopy)
    {
        if (targetCopy is InfiniCraftPlayer clone)
        {
            clone._generatedBuffTicks = _generatedBuffTicks;
            clone._generatedMiningSpeedMultiplier = _generatedMiningSpeedMultiplier;
            clone._generatedLightStrength = _generatedLightStrength;
            clone._generatedLightColorName = _generatedLightColorName;
            clone._generatedOreSenseRadiusTiles = _generatedOreSenseRadiusTiles;
            clone._generatedMovementSpeed = _generatedMovementSpeed;
            clone._generatedJumpBoost = _generatedJumpBoost;
            clone._generatedManaRegen = _generatedManaRegen;
            clone._generatedLifeRegen = _generatedLifeRegen;
            clone._generatedMobilityCooldownTicks = _generatedMobilityCooldownTicks;
        }
    }

    public override void SendClientChanges(ModPlayer clientPlayer)
    {
        if (clientPlayer is InfiniCraftPlayer oldState && GeneratedBuffStateDiffers(oldState))
            SendGeneratedBuffState();
    }

    public static void HandleGeneratedUtilityBuffSyncPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        byte playerId = reader.ReadByte();
        if (playerId >= Main.maxPlayers) return;
        if (Main.netMode == NetmodeID.Server && playerId != whoAmI) return;
        Player player = Main.player[playerId];
        if (player is null || !player.active) return;
        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        modPlayer.ReadGeneratedBuffState(reader);
        if (Main.netMode == NetmodeID.Server)
            modPlayer.SendGeneratedBuffState(-1, whoAmI);
    }


    private bool IsServerAuthoritativeCraft => Main.netMode == NetmodeID.Server && !_awaitingServerCommit && !string.IsNullOrWhiteSpace(_serverRequestId);

    private void SendServerAuthoritativeResultIfNeeded(bool success, string itemName, string message)
    {
        if (!IsServerAuthoritativeCraft)
            return;
        if (success)
            RememberServerCraftCommit(ServerCraftKey(Player.whoAmI, _serverRequestId), string.IsNullOrWhiteSpace(itemName) ? "Generated Item" : itemName);
        SendCraftCommitResult(Player.whoAmI, _serverRequestId, success, itemName ?? "", message ?? "");
    }


    public void HandleCraftCommitResult(string requestId, bool success, string itemName, string message)
    {
        if (!_awaitingServerCommit || !string.Equals(_serverRequestId, requestId, StringComparison.Ordinal))
            return;

        if (success)
        {
            CombatText.NewText(Player.Hitbox, Color.Cyan, $"Discovered: {(string.IsNullOrWhiteSpace(itemName) ? "Generated Item" : itemName)}");
            ClearCraft();
            return;
        }

        // In multiplayer the server is authoritative for ingredient ownership.
        // Do not refund the client's transient UI escrow here: if the host rejected
        // before taking real slots, its inventory state will resync; if it already
        // took slots, it refunds server-side. Local refund here would reopen dup paths.
        CombatText.NewText(Player.Hitbox, Color.OrangeRed, string.IsNullOrWhiteSpace(message)
            ? "InfiniCraft: сервер отклонил крафт"
            : $"InfiniCraft: {message}");
        ClearCraft();
    }

    private static void RunLocalCraftReveal(Player player, GeneratedItemData data)
    {
        if (player is null || data is null) return;
        string name = string.IsNullOrWhiteSpace(data.Name) ? "Generated Item" : data.Name;

        if (!global::InfiniCrafterLocal.Content.Items.GeneratedItem.VisualSoulAuraEligible(data))
        {
            CombatText.NewText(player.Hitbox, Color.Cyan, $"Discovered: {name}");
            return;
        }

        Color soulColor = global::InfiniCrafterLocal.Content.Items.GeneratedItem.VisualSoulColor(data, Color.Cyan);
        CombatText.NewText(player.Hitbox, soulColor, $"✦ Discovered: {name} ✦");
        if (Main.netMode == NetmodeID.Server)
            return;

        float glow = Math.Clamp(global::InfiniCrafterLocal.Content.Items.GeneratedItem.VisualSoulAuraGlow(data), 0.20f, 1.0f);
        Lighting.AddLight(player.Center, soulColor.R / 255f * glow * 1.35f, soulColor.G / 255f * glow * 1.35f, soulColor.B / 255f * glow * 1.35f);
        int dustCount = 18 + (int)Math.Round(glow * 28f);
        for (int i = 0; i < dustCount; i++)
        {
            float angle = MathHelper.TwoPi * i / Math.Max(1, dustCount) + Main.rand.Next(-20, 21) / 100f;
            float speed = 1.0f + (float)Main.rand.NextDouble() * (1.5f + glow);
            Vector2 velocity = new Vector2((float)Math.Cos(angle), (float)Math.Sin(angle)) * speed;
            int idx = Dust.NewDust(player.Center + new Vector2(Main.rand.Next(-10, 11), Main.rand.Next(-16, 8)), 4, 4, DustID.Torch, velocity.X, velocity.Y, 110, soulColor, 0.85f + glow * 0.55f);
            if (idx >= 0 && idx < Main.maxDust)
            {
                Main.dust[idx].noGravity = true;
                Main.dust[idx].velocity *= 0.85f;
            }
        }
        Terraria.Audio.SoundEngine.PlaySound(SoundID.Item4, player.Center);
    }

    public static void HandleCraftCommitResultPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;

        string requestId = reader.ReadString();
        bool success = reader.ReadBoolean();
        string itemName = reader.ReadString();
        string message = reader.ReadString();
        Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().HandleCraftCommitResult(requestId, success, itemName, message);
    }

    public static void HandleRequestServerCraftPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        if (whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;

        string requestId = reader.ReadString();
        CraftItemRef aRef = ReadCraftItemRef(reader);
        CraftItemRef bRef = ReadCraftItemRef(reader);
        if (string.IsNullOrWhiteSpace(requestId))
        {
            SendCraftCommitResult(whoAmI, requestId, false, "", "пустой requestId");
            return;
        }

        string dedupeKey = "servercraft:" + whoAmI + ":" + requestId;
        lock (ServerCommittedCraftRequestsLock)
        {
            if (ServerCommittedCraftRequests.TryGetValue(dedupeKey, out string? knownName))
            {
                SendCraftCommitResult(whoAmI, requestId, true, knownName ?? "", "duplicate ack");
                return;
            }
        }

        Player player = Main.player[whoAmI];
        if (player is null || !player.active)
        {
            SendCraftCommitResult(whoAmI, requestId, false, "", "игрок неактивен");
            return;
        }

        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        if (modPlayer.HasPendingCraft)
        {
            SendCraftCommitResult(whoAmI, requestId, false, "", "у игрока уже есть активный InfiniCraft");
            return;
        }
        if (IsServerCraftCancelled(whoAmI, requestId))
        {
            SendCraftCommitResult(whoAmI, requestId, false, "", "запрос уже отменён клиентом");
            return;
        }

        var spentSlots = new HashSet<int>();
        if (!TryTakeServerSideIngredient(player, aRef, spentSlots, out Item itemA, out string errorA))
        {
            SendCraftCommitResult(whoAmI, requestId, false, "", "сервер не нашёл первый ингредиент: " + errorA);
            return;
        }
        if (!TryTakeServerSideIngredient(player, bRef, spentSlots, out Item itemB, out string errorB))
        {
            modPlayer.RefundOne(itemA);
            SendCraftCommitResult(whoAmI, requestId, false, "", "сервер не нашёл второй ингредиент: " + errorB);
            return;
        }

        GeneratorClient.PreparedGenerationRequest request;
        try
        {
            request = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.Prepare(itemA, itemB, player);
        }
        catch (Exception ex)
        {
            modPlayer.RefundOne(itemA);
            modPlayer.RefundOne(itemB);
            SendCraftCommitResult(whoAmI, requestId, false, "", "хост не подготовил запрос: " + ex.Message);
            return;
        }
        if (!modPlayer.BeginServerAuthoritativeCraft(request, $"{request.ParentA} + {request.ParentB}", requestId))
        {
            modPlayer.RefundOne(itemA);
            modPlayer.RefundOne(itemB);
            SendCraftCommitResult(whoAmI, requestId, false, "", "хост не начал server-authoritative craft");
            return;
        }
    }


    public static void HandleCancelServerCraftPacket(System.IO.BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        if (whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;

        string requestId = reader.ReadString();
        try { _ = reader.ReadString(); } catch { } // optional cancel reason, protocol v0.4.218
        if (!HasCraftRequestId(requestId))
            return;

        MarkServerCraftCancelled(whoAmI, requestId);
        Player player = Main.player[whoAmI];
        if (player is null || !player.active)
            return;
        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        if (modPlayer.IsServerAuthoritativeCraft && string.Equals(modPlayer._serverRequestId, requestId, StringComparison.Ordinal))
            modPlayer.CancelActiveServerAuthoritativeCraft("client cancelled/timeout");
        else
            SendCraftCommitResult(whoAmI, requestId, false, "", "запрос отменён");
    }

    private void SendRemoteServerCraftCancel(string reason)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !_awaitingServerCommit || !HasCraftRequestId(_serverRequestId))
            return;
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketCancelServerCraft);
            packet.Write(_serverRequestId);
            packet.Write(reason ?? "client_cancel");
            packet.Send();
        }
        catch { }
    }

    private void CancelActiveServerAuthoritativeCraft(string reason)
    {
        if (!IsServerAuthoritativeCraft)
            return;
        RefundIngredients();
        SendServerAuthoritativeResultIfNeeded(false, "", string.IsNullOrWhiteSpace(reason) ? "server craft cancelled" : reason);
        ClearCraft();
    }

    private static string ServerCraftKey(int playerId, string requestId)
        => "servercraft:" + playerId + ":" + NormalizeCraftRequestId(requestId);

    private static void RememberServerCraftCommit(string key, string itemName)
    {
        lock (ServerCommittedCraftRequestsLock)
        {
            if (!ServerCommittedCraftRequests.ContainsKey(key))
                ServerCommittedCraftRequestOrder.Enqueue(key);
            ServerCommittedCraftRequests[key] = itemName;
            while (ServerCommittedCraftRequestOrder.Count > MaxServerCraftRequestCacheEntries)
                ServerCommittedCraftRequests.Remove(ServerCommittedCraftRequestOrder.Dequeue());
        }
    }

    private static void MarkServerCraftCancelled(int playerId, string requestId)
    {
        if (!HasCraftRequestId(requestId))
            return;
        lock (ServerCommittedCraftRequestsLock)
        {
            string key = ServerCraftKey(playerId, requestId);
            if (ServerCancelledCraftRequests.Add(key))
                ServerCancelledCraftRequestOrder.Enqueue(key);
            while (ServerCancelledCraftRequestOrder.Count > MaxServerCraftRequestCacheEntries)
                ServerCancelledCraftRequests.Remove(ServerCancelledCraftRequestOrder.Dequeue());
        }
    }

    private static bool IsServerCraftCancelled(int playerId, string requestId)
    {
        if (!HasCraftRequestId(requestId))
            return false;
        lock (ServerCommittedCraftRequestsLock)
            return ServerCancelledCraftRequests.Contains(ServerCraftKey(playerId, requestId));
    }

    private readonly struct CraftItemRef
    {
        public CraftItemRef(int type, int prefix, int stack, string generatedId, string displayName)
        {
            Type = type;
            Prefix = prefix;
            Stack = stack;
            GeneratedId = generatedId ?? "";
            DisplayName = displayName ?? "";
        }

        public int Type { get; }
        public int Prefix { get; }
        public int Stack { get; }
        public string GeneratedId { get; }
        public string DisplayName { get; }
    }

    private static string LocalParentName(Item item)
    {
        try
        {
            if (item?.ModItem is GeneratedItem generated && !string.IsNullOrWhiteSpace(generated.Data?.Name))
                return generated.Data.Name;
            return string.IsNullOrWhiteSpace(item?.Name) ? "Unknown" : item.Name;
        }
        catch { return "Unknown"; }
    }

    private static void WriteCraftItemRef(System.IO.BinaryWriter writer, Item item)
    {
        string generatedId = "";
        string displayName = "";
        try
        {
            displayName = LocalParentName(item);
            if (item?.ModItem is GeneratedItem generated)
                generatedId = generated.Data?.Id ?? "";
        }
        catch { }

        writer.Write(item?.type ?? ItemID.None);
        writer.Write((int)(item?.prefix ?? InfiniTerrariaSentinels.NoPrefix));
        writer.Write(NormalizeCraftStack(item?.stack ?? 1));
        writer.Write(generatedId ?? "");
        writer.Write(displayName ?? "");
    }

    private static CraftItemRef ReadCraftItemRef(System.IO.BinaryReader reader)
    {
        return new CraftItemRef(
            reader.ReadInt32(),
            reader.ReadInt32(),
            reader.ReadInt32(),
            reader.ReadString(),
            reader.ReadString());
    }

    private static bool TryReconstructCraftItem(CraftItemRef itemRef, out Item item, out string error)
    {
        item = new Item();
        item.TurnToAir();
        error = "";
        try
        {
            if (!IsValidIncomingCraftItemType(itemRef.Type))
            {
                error = "пустой item type";
                return false;
            }

            item.SetDefaults(itemRef.Type);
            item.stack = NormalizeCraftStack(itemRef.Stack);

            if (!string.IsNullOrWhiteSpace(itemRef.GeneratedId))
            {
                if (item.ModItem is not GeneratedItem generated)
                {
                    error = "generated id пришёл не для GeneratedItem";
                    return false;
                }
                if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is null ||
                    !global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGet(itemRef.GeneratedId, out GeneratedItemData data))
                {
                    error = "generated parent отсутствует в registry хоста: " + itemRef.GeneratedId;
                    return false;
                }
                generated.SetData(data);
            }

            // Prefixes are intentionally ignored by GeneratorClient.Prepare for recipe identity,
            // but keeping the incoming prefix on the temporary Item helps display/debug parity.
            if (HasReforgePrefix(itemRef.Prefix))
            {
                try { item.Prefix(itemRef.Prefix); } catch { }
            }
            return !item.IsAir;
        }
        catch (Exception ex)
        {
            error = ex.Message;
            return false;
        }
    }


    private static bool TryTakeServerSideIngredient(Player player, CraftItemRef itemRef, HashSet<int> excludedSlots, out Item ingredient, out string error)
    {
        ingredient = new Item();
        ingredient.TurnToAir();
        error = "";
        if (player is null || !player.active)
        {
            error = "игрок неактивен";
            return false;
        }
        if (!IsValidIncomingCraftItemType(itemRef.Type))
        {
            error = "пустой item type";
            return false;
        }

        bool sawFavorite = false;
        bool sawGeneratedMismatch = false;
        for (int i = 0; i < 50 && i < player.inventory.Length; i++)
        {
            if (excludedSlots.Contains(i))
                continue;
            Item slot = player.inventory[i];
            if (slot is null || slot.IsAir || slot.stack <= 0 || slot.type != itemRef.Type)
                continue;
            if (slot.favorited)
            {
                sawFavorite = true;
                continue;
            }
            if (!InfiniCore.IsValidIngredient(slot))
                continue;
            if (!GeneratedIdentityMatches(slot, itemRef.GeneratedId, out bool generatedMismatch))
            {
                sawGeneratedMismatch |= generatedMismatch;
                continue;
            }

            ingredient = slot.Clone();
            ingredient.stack = 1;
            slot.stack -= 1;
            if (slot.stack <= 0)
                slot.TurnToAir();
            slot.NetStateChanged();
            if (Main.netMode == NetmodeID.Server)
                NetMessage.SendData(MessageID.SyncEquipment, -1, -1, null, player.whoAmI, i);
            excludedSlots.Add(i);
            return true;
        }

        if (sawFavorite) error = "совпадающий предмет находится в favorite-слоте";
        else if (sawGeneratedMismatch) error = "generated id не совпал с registry/server inventory";
        else error = "нет совпадающего предмета в server-side inventory slots 0..49";
        return false;
    }

    private static bool GeneratedIdentityMatches(Item slot, string generatedId, out bool generatedMismatch)
    {
        generatedMismatch = false;
        string expected = (generatedId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(expected))
            return slot.ModItem is not GeneratedItem && slot.ModItem is not global::InfiniCrafterLocal.Content.Items.GeneratedExtractinatorMaterial;

        string actual = "";
        if (slot.ModItem is GeneratedItem generated)
            actual = generated.Data?.Id ?? "";
        else if (slot.ModItem is global::InfiniCrafterLocal.Content.Items.GeneratedExtractinatorMaterial extractinator)
            actual = extractinator.Data?.Id ?? "";
        else
        {
            generatedMismatch = true;
            return false;
        }
        bool ok = string.Equals(actual, expected, StringComparison.Ordinal);
        generatedMismatch = !ok;
        return ok;
    }

    public static void ClearServerCommitCache()
    {
        lock (ServerCommittedCraftRequestsLock)
        {
            ServerCommittedCraftRequests.Clear();
            ServerCancelledCraftRequests.Clear();
            ServerCommittedCraftRequestOrder.Clear();
            ServerCancelledCraftRequestOrder.Clear();
        }
    }

    private static void SendCraftCommitResult(int toClient, string requestId, bool success, string itemName, string message)
    {
        if (Main.netMode != NetmodeID.Server)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketCraftCommitResult);
        packet.Write(requestId ?? "");
        packet.Write(success);
        packet.Write(itemName ?? "");
        packet.Write(message ?? "");
        packet.Send(toClient);
    }

    private static void StampHostAssetSyncMetadata(GeneratedItemData data)
    {
        // Server-authoritative MP craft: the host owns LocalGenerator and the
        // source item/projectile dumps. Clients receive the finished generated
        // item plus final asset filenames/base URL, then hydrate PNG/JSON from
        // the host over HTTP automatically.
        if (data is null)
            return;

        data.RecipeMeta ??= new RecipeMetaSpec();
        // Transport metadata is not gameplay authorship.  Always restamp it on the
        // host before MP commit so old localhost/Radmin URLs from earlier sessions do
        // not strand already-generated sprites on friends.
        data.RecipeMeta.AssetBaseUrl = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.AssetBaseUrlForSharing();

        var files = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
        if (files.Length > 0)
            data.RecipeMeta.AssetFiles = files;
    }

    private static bool SpawnGeneratedItemServerSide(Player player, GeneratedItemData data, out string error)
    {
        error = "";
        try
        {
            if (data is null)
            {
                error = "пустой предмет";
                return false;
            }

            StampHostAssetSyncMetadata(data);

            bool asExtractinatorProxy = global::InfiniCrafterLocal.Content.Items.GeneratedExtractinatorMaterial.CanRepresent(data);
            bool asArmorProxy = !asExtractinatorProxy && global::InfiniCrafterLocal.Content.Items.GeneratedArmorItemTypes.CanRepresent(data);
            int itemType = asExtractinatorProxy
                ? ModContent.ItemType<global::InfiniCrafterLocal.Content.Items.GeneratedExtractinatorMaterial>()
                : asArmorProxy
                    ? global::InfiniCrafterLocal.Content.Items.GeneratedArmorItemTypes.ItemTypeFor(data)
                    : ModContent.ItemType<GeneratedItem>();
            int index = Item.NewItem(player.GetSource_Misc("InfiniCraft"), player.Hitbox, itemType);
            if (index < 0 || index >= Main.maxItems)
            {
                error = "Item.NewItem не вернул предмет";
                return false;
            }

            if (asExtractinatorProxy)
            {
                if (Main.item[index].ModItem is not global::InfiniCrafterLocal.Content.Items.GeneratedExtractinatorMaterial proxy)
                {
                    error = "Item.NewItem не вернул GeneratedExtractinatorMaterial";
                    return false;
                }
                proxy.SetData(data);
            }
            else
            {
                if (Main.item[index].ModItem is not GeneratedItem generated)
                {
                    error = "Item.NewItem не вернул GeneratedItem";
                    return false;
                }
                generated.SetData(data);
            }
            int craftYield = Math.Clamp(data.Gameplay?.CraftYield ?? 1, 1, Math.Max(1, data.Gameplay?.MaxStack ?? 1));
            Main.item[index].stack = craftYield;

            // Commit order: registry first, asset notice second, vanilla item sync third,
            // explicit transaction ACK last. Asset notice contains only filenames +
            // host HTTP base URL; clients automatically call /get_asset in background.
            // If the ACK is seen, the item was already committed server-side.
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.PublishGeneratedItem(data);
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.NotifyNewItemCrafted(data);
            if (Main.netMode != NetmodeID.SinglePlayer)
                NetMessage.SendData(MessageID.SyncItem, -1, -1, null, index);
            return true;
        }
        catch (Exception ex)
        {
            error = ex.Message;
            return false;
        }
    }

}
