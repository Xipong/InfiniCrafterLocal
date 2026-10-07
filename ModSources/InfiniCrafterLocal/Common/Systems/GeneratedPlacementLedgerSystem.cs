#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Systems;

internal enum GeneratedPlacementLayer : byte
{
    Tile = 1,
    Wall = 2,
}

internal readonly record struct GeneratedPlacementKey(GeneratedPlacementLayer Layer, int X, int Y);

/// <summary>
/// World-persistent exact-identity ledger for generated tile and wall placements.
/// Placement identity is authorized from the server-observed GeneratedItem before
/// the world mutation. Client packets announce only layer/coordinates and can never
/// choose the generated id or definition. A broken placement is atomically moved to
/// a durable pending-return queue before delivery is attempted.
/// </summary>
public sealed partial class GeneratedPlacementLedgerSystem : ModSystem
{
    private const int PayloadVersion = 3;
    private const int PlacementProtocolVersion = 5;
    private const string SaveKey = "infiniGeneratedPlacementLedgerV2";
    private const string PendingSaveKey = "infiniGeneratedPlacementReturnsV2";
    private const string QuarantineSaveKey = "infiniGeneratedPlacementReturnQuarantineV1";
    private const string RawQuarantineEnvelopeSaveKey = "infiniGeneratedPlacementRawQuarantineEnvelopesV1";
    private const int MaxGroups = 8192;
    private const int MaxCells = 32768;
    private const int MaxCellsPerGroup = 256;
    private const int AuthorizationRadiusTiles = 16;
    // Commit detection stays in the immediate neighborhood of the announced
    // target; it must never widen to every cell captured in the before snapshot.
    private const int CommitScanRadiusTiles = 3;
    private const int AuthorizationLifetimeTicks = 30;
    private const int RemoteIntentLifetimeTicks = 120;
    private const int PlacementReceiptLifetimeTicks = 8;
    private const int MaxPendingAttemptsPerTick = 8;

    private sealed class PlacementGroup
    {
        public string GroupId { get; init; } = "";
        public string GeneratedItemId { get; init; } = "";
        public string DefinitionJson { get; set; } = "";
        public List<GeneratedPlacementKey> Cells { get; init; } = new();
        // Optional exact opt-in witness; cosmetic corruption never erases material ownership.
        public TagCompound? PlacedBody { get; init; }
        // Legal NBT with a noncompound cosmetic value is retained literally,
        // never interpreted as presentation or a second material owner.
        public TagCompound? RawPlacedBodyEnvelope { get; init; }
    }

    private sealed class PendingReturnRecord
    {
        public string GroupId { get; init; } = "";
        public string GeneratedItemId { get; init; } = "";
        public string DefinitionJson { get; init; } = "";
        public int X { get; init; }
        public int Y { get; init; }
        // Transient attempt count is diagnostic only. World pressure retries
        // durably; deterministic permanent failures leave the retry queue once
        // their raw claim and cause have been retained in world quarantine.
        public int FailedAttempts { get; set; }
        public string FailureCause { get; set; } = "";
        public TagCompound? RawClaim { get; init; }
    }

    private sealed class QuarantinedReturnRecord
    {
        public TagCompound Claim { get; init; } = new();
        public TagCompound? RawEnvelope { get; init; }
        public string Cause { get; init; } = "";
        // Retain the original raw claim even after a validated requeue. This is an
        // idempotence receipt, not another retryable/material owner.
        public bool Requeued { get; set; }
        public string RequeueDefinitionJson { get; set; } = "";
        public string LastFailureCause { get; set; } = "";
    }

    private sealed class PlacementAuthorization
    {
        public int PlayerIndex { get; init; }
        public Player? SourcePlayer { get; init; }
        public GeneratedItemData? SourceData { get; init; }
        public ulong Sequence { get; set; }
        // Allocated by the authority before native mutation; Ready lends this exact
        // identity to the original placing client, never the other way around.
        public string GroupId { get; set; } = "";
        public bool NotifyReceived { get; set; }
        public GeneratedPlacementLayer Layer { get; init; }
        public int TargetX { get; init; }
        public int TargetY { get; init; }
        public int ExpectedType { get; init; }
        public int ExpiresAtTick { get; init; }
        public string GeneratedItemId { get; init; } = "";
        public string DefinitionJson { get; init; } = "";
        public HashSet<long> BeforeExpectedTiles { get; init; } = new();
        public string DefinitionHash { get; init; } = "";
        public int BeforeWallType { get; init; }
        public string PlacementBindingId { get; init; } = "";
        public RuntimePlacementSpec? ExactPlacement { get; init; }
    }

    private sealed class ClientPlacementIntent
    {
        public Player Player { get; init; } = null!;
        public Item Item { get; init; } = null!;
        public GeneratedItemData Data { get; init; } = null!;
        public RuntimePlacementSpec Placement { get; init; } = null!;
        public byte Input { get; init; }
        public int X { get; init; }
        public int Y { get; init; }
        public int ExpiresAtTick { get; init; }
        public ulong Sequence { get; init; }
        public string DefinitionHash { get; init; } = "";
        public bool Ready { get; set; }
        public string GroupId { get; set; } = "";
        public bool NativeRetrySpent { get; set; }
        public bool UseAdmitted { get; set; }
    }

    private sealed class PlacementPeerCursor
    {
        public Player Player { get; init; } = null!;
        public ulong Sequence { get; set; }
        public int LastIntentTick { get; set; } = int.MinValue;
    }

    private static readonly Dictionary<int, ClientPlacementIntent> ClientPlacementIntents = new();
    private static readonly Dictionary<int, ClientPlacementIntent> RetiredClientPlacementIntents = new();
    private static readonly Dictionary<int, PlacementPeerCursor> PlacementPeerCursors = new();
    private static ulong _nextPlacementSequence;

    private static readonly Dictionary<GeneratedPlacementKey, string> Placements = new();
    private static readonly Dictionary<string, PlacementGroup> Groups = new(StringComparer.Ordinal);
    private static readonly List<PendingReturnRecord> PendingReturns = new();
    private static readonly List<QuarantinedReturnRecord> QuarantinedReturns = new();
    private static readonly List<TagCompound> RawQuarantineEnvelopes = new();
    private static readonly Dictionary<int, PlacementAuthorization> PendingAuthorizations = new();
    private static readonly Dictionary<int, int> PlacementReceiptExpiryByPlayer = new();

    public override void ClearWorld()
    {
        Placements.Clear();
        Groups.Clear();
        PendingReturns.Clear();
        QuarantinedReturns.Clear();
        RawQuarantineEnvelopes.Clear();
        PendingAuthorizations.Clear();
        PlacementReceiptExpiryByPlayer.Clear();
        ClientPlacementIntents.Clear();
        RetiredClientPlacementIntents.Clear();
        PlacementPeerCursors.Clear();
        _nextPlacementSequence = 0;
        _placedBodyRevision = 0;
        _bodyFootprintMaintenanceCursor = 0;
        PlacedBodyViews.Clear();
        ClearPlacedBodyMirrorState();
    }

    public override void SaveWorldData(TagCompound tag)
    {
        tag[SaveKey] = Groups.Values
            .OrderBy(x => x.GroupId, StringComparer.Ordinal)
            .Select(SavePlacementGroup).ToList();
        tag[PendingSaveKey] = PendingReturns.Select(ReturnClaim).ToList();
        tag[QuarantineSaveKey] = QuarantinedReturns.Select(QuarantineEnvelope).ToList();
        tag[RawQuarantineEnvelopeSaveKey] = RawQuarantineEnvelopes.Select(row => (TagCompound)row.Clone()).ToList();
    }

    private static TagCompound QuarantineEnvelope(QuarantinedReturnRecord record)
    {
        TagCompound row = record.RawEnvelope is null ? new TagCompound() : (TagCompound)record.RawEnvelope.Clone();
        row["claim"] = record.Claim.Clone();
        row["cause"] = record.Cause;
        row["requeued"] = record.Requeued;
        row["requeueDefinitionJson"] = record.RequeueDefinitionJson;
        row["lastFailureCause"] = record.LastFailureCause;
        return row;
    }

    public override void LoadWorldData(TagCompound tag)
    {
        ClearWorld();
        foreach (TagCompound row in tag.GetList<TagCompound>(SaveKey).Take(MaxGroups))
        {
            string groupId = (row.GetString("groupId") ?? "").Trim();
            string generatedItemId = (row.GetString("generatedItemId") ?? "").Trim();
            string definitionJson = row.GetString("definitionJson") ?? "";
            if (groupId.Length == 0 || generatedItemId.Length == 0 || definitionJson.Length == 0)
                continue;
            var cells = new List<GeneratedPlacementKey>();
            foreach (TagCompound cell in row.GetList<TagCompound>("cells").Take(MaxCellsPerGroup))
            {
                int layerValue = cell.GetInt("layer");
                int x = cell.GetInt("x");
                int y = cell.GetInt("y");
                if (layerValue is < byte.MinValue or > byte.MaxValue
                    || !Enum.IsDefined((GeneratedPlacementLayer)layerValue)
                    || !WorldGen.InWorld(x, y, 1))
                    continue;
                var key = new GeneratedPlacementKey((GeneratedPlacementLayer)layerValue, x, y);
                if (Placements.Count >= MaxCells || Placements.ContainsKey(key))
                    continue;
                Placements[key] = groupId;
                cells.Add(key);
            }
            if (cells.Count == 0)
                continue;
            Groups[groupId] = new PlacementGroup
            {
                GroupId = groupId,
                GeneratedItemId = generatedItemId,
                DefinitionJson = definitionJson,
                Cells = cells,
                PlacedBody = row.ContainsKey("placedBody") && row["placedBody"] is TagCompound rawBody
                    ? (TagCompound)rawBody.Clone() : null,
                RawPlacedBodyEnvelope = row.ContainsKey("placedBody") && row["placedBody"] is not TagCompound
                    ? new TagCompound { ["placedBody"] = ((TagCompound)row.Clone())["placedBody"] } : null,
            };
        }
        foreach (TagCompound row in tag.GetList<TagCompound>(PendingSaveKey))
        {
            try
            {
                string id = row.GetString("generatedItemId") ?? "";
                string json = row.GetString("definitionJson") ?? "";
                string groupId = row.GetString("groupId") ?? "";
                int x = row.GetInt("x"), y = row.GetInt("y");
                if (groupId.Length == 0 || id.Length == 0 || json.Length == 0 || !WorldGen.InWorld(x, y, 1)
                    || PendingReturns.Count >= MaxGroups || PendingReturns.Any(p => p.GroupId == groupId) || Groups.ContainsKey(groupId))
                {
                    QuarantinedReturns.Add(new QuarantinedReturnRecord { Claim = (TagCompound)row.Clone(), Cause = "claim_invalid" });
                    continue;
                }
                PendingReturns.Add(new PendingReturnRecord
                {
                    GroupId = groupId, GeneratedItemId = id, DefinitionJson = json, X = x, Y = y,
                    RawClaim = (TagCompound)row.Clone(),
                });
            }
            catch
            {
                QuarantinedReturns.Add(new QuarantinedReturnRecord { Claim = (TagCompound)row.Clone(), Cause = "claim_invalid" });
            }
        }
        foreach (TagCompound row in tag.GetList<TagCompound>(QuarantineSaveKey))
        {
            try
            {
                if (!row.ContainsKey("claim") || row["claim"] is not TagCompound)
                    throw new InvalidDataException("Quarantine envelope has no compound claim");
                // Publish only after every canonical getter succeeded. A corrupt
                // legal NBT row cannot abort or partially admit its healthy tail.
                var record = new QuarantinedReturnRecord
                {
                    Claim = (TagCompound)row.GetCompound("claim").Clone(),
                    Cause = row.GetString("cause"),
                    Requeued = row.GetBool("requeued"),
                    RequeueDefinitionJson = row.GetString("requeueDefinitionJson"),
                    LastFailureCause = row.GetString("lastFailureCause"),
                    RawEnvelope = (TagCompound)row.Clone(),
                };
                QuarantinedReturns.Add(record);
            }
            catch { RawQuarantineEnvelopes.Add((TagCompound)row.Clone()); }
        }
        // This separate versioned raw bucket is never interpreted as recovery
        // authority, including after any number of native save/reload cycles.
        foreach (TagCompound row in tag.GetList<TagCompound>(RawQuarantineEnvelopeSaveKey))
            RawQuarantineEnvelopes.Add((TagCompound)row.Clone());
        RestorePlacedBodyDefinitions(publish: false);
    }

    private static TagCompound ReturnClaim(PendingReturnRecord pending)
        => pending.RawClaim is not null ? (TagCompound)pending.RawClaim.Clone() : new TagCompound
        {
            ["groupId"] = pending.GroupId,
            ["generatedItemId"] = pending.GeneratedItemId,
            ["definitionJson"] = pending.DefinitionJson,
            ["x"] = pending.X,
            ["y"] = pending.Y,
        };

    internal static bool TryRequeueQuarantinedReturn(string groupId, string definitionJson)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient || string.IsNullOrEmpty(groupId))
            return false;
        QuarantinedReturnRecord[] matches = QuarantinedReturns.Where(q => q.Claim.ContainsKey("groupId") && q.Claim["groupId"] is string exactGroupId && exactGroupId == groupId).ToArray();
        if (matches.Length != 1)
            return false;
        QuarantinedReturnRecord record = matches[0];
        if (!record.Claim.ContainsKey("generatedItemId") || record.Claim["generatedItemId"] is not string id
            || !record.Claim.ContainsKey("x") || record.Claim["x"] is not int x
            || !record.Claim.ContainsKey("y") || record.Claim["y"] is not int y)
            return false;
        GeneratedItemData? data = GeneratedItemData.FromJson(definitionJson);
        if (data is null || id.Length == 0 || !string.Equals(data.Id, id, StringComparison.Ordinal)
            || !IsMaterialPlacementDefinition(data)
            || !GeneratedItemRegistryService.IsCurrentWorldData(data) || !WorldGen.InWorld(x, y, 1))
            return false;
        if (record.Requeued)
            return string.Equals(record.RequeueDefinitionJson, definitionJson, StringComparison.Ordinal);
        if (Groups.Count + PendingReturns.Count >= MaxGroups
            || Groups.ContainsKey(groupId) || PendingReturns.Any(p => p.GroupId == groupId))
            return false;
        PendingReturns.Add(new PendingReturnRecord
        {
            GroupId = groupId, GeneratedItemId = id, DefinitionJson = definitionJson, X = x, Y = y,
        });
        record.Requeued = true;
        record.RequeueDefinitionJson = definitionJson;
        return true;
    }

    public override void NetSend(BinaryWriter writer)
    {
        RestorePlacedBodyDefinitions(publish: true);
        writer.Write(PayloadVersion);
        writer.Write(_placedBodyRevision);
        writer.Write(Groups.Count);
        foreach (PlacementGroup group in Groups.Values.OrderBy(x => x.GroupId, StringComparer.Ordinal))
            WriteMirrorGroup(writer, group);
    }

    public override void NetReceive(BinaryReader reader)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            throw new InvalidDataException("placement snapshots are server-to-client only");
        int version = reader.ReadInt32();
        if (version != PayloadVersion)
            throw new InvalidDataException($"Unsupported generated placement ledger payload {version}");
        ulong revision = reader.ReadUInt64();
        int count = reader.ReadInt32();
        if (count < 0 || count > MaxGroups) throw new InvalidDataException("placement snapshot group capacity");
        var incoming = new Dictionary<string, PlacementGroup>(StringComparer.Ordinal);
        var occupied = new HashSet<GeneratedPlacementKey>();
        for (int index = 0; index < count; index++)
        {
            PlacementGroup group = ReadMirrorGroup(reader);
            if (!incoming.TryAdd(group.GroupId, group) || group.Cells.Any(cell => !occupied.Add(cell)) || occupied.Count > MaxCells)
                throw new InvalidDataException("placement snapshot identity/overlap/capacity");
        }
        EnsurePlacedBodyMirrorSender();
        if (revision < _placedBodyRevision || (_bodySnapshotReceived && revision == _placedBodyRevision)) return;
        Groups.Clear(); Placements.Clear();
        BodyHydrationQueue.Clear(); BodyHydrationNodes.Clear();
        foreach (PlacementGroup group in incoming.Values)
        {
            Groups[group.GroupId] = group;
            foreach (GeneratedPlacementKey cell in group.Cells) Placements[cell] = group.GroupId;
            EnqueuePlacedBodyHydration(group);
        }
        _placedBodyRevision = revision;
        _bodySnapshotReceived = true;
    }

    public override void PostUpdateWorld()
    {
        int now = (int)Main.GameUpdateCount;
        foreach (int playerIndex in PendingAuthorizations.Keys.ToArray())
        {
            PlacementAuthorization authorization = PendingAuthorizations[playerIndex];
            if (now > authorization.ExpiresAtTick)
            {
                PendingAuthorizations.Remove(playerIndex);
                continue;
            }
            if (playerIndex >= 0 && playerIndex < Main.maxPlayers && Main.player[playerIndex] is { active: true } player
                && (authorization.Sequence == 0 || authorization.NotifyReceived))
                TryCommitAuthorizedPlacement(player);
        }

        foreach (int playerIndex in ClientPlacementIntents.Where(p => p.Value.ExpiresAtTick < now).Select(p => p.Key).ToArray())
            ClientPlacementIntents.Remove(playerIndex);
        foreach (int playerIndex in PlacementReceiptExpiryByPlayer.Where(x => x.Value < now).Select(x => x.Key).ToArray())
            PlacementReceiptExpiryByPlayer.Remove(playerIndex);

        if (Main.netMode == NetmodeID.MultiplayerClient)
            return;
        RetireMissingPlacedBodyFootprints();
        int attempts = Math.Min(MaxPendingAttemptsPerTick, PendingReturns.Count);
        for (int index = attempts - 1; index >= 0; index--)
        {
            PendingReturnRecord pending = PendingReturns[index];
            PendingSpawnOutcome outcome = TrySpawnPendingReturn(pending);
            if (outcome == PendingSpawnOutcome.Spawned)
            {
                PendingReturns.RemoveAt(index);
                continue;
            }
            if (outcome == PendingSpawnOutcome.TransientFailure)
            {
                // Ordinary world pressure (full item slots) is not a broken record.
                // Rotate to the back so one full inventory cannot starve the queue,
                // and never quarantine a durable return: the placed generated item
                // must come back. The record retries on a later update forever.
                pending.FailedAttempts++;
                if (index == PendingReturns.Count - 1)
                    continue;
                PendingReturns.RemoveAt(index);
                PendingReturns.Add(pending);
                continue;
            }
            // Retire retry ownership only after retaining the exact raw claim and
            // diagnosed cause in world save. Never substitute a vanilla/proxy item.
            QuarantinedReturnRecord? priorQuarantine = QuarantinedReturns.FirstOrDefault(q => q.Requeued
                && q.Claim.ContainsKey("groupId") && q.Claim["groupId"] is string exactGroupId
                && string.Equals(exactGroupId, pending.GroupId, StringComparison.Ordinal));
            if (priorQuarantine is not null)
            {
                priorQuarantine.Requeued = false;
                priorQuarantine.LastFailureCause = pending.FailureCause;
            }
            else
                QuarantinedReturns.Add(new QuarantinedReturnRecord
                {
                    Claim = ReturnClaim(pending), Cause = pending.FailureCause,
                });
            PendingReturns.RemoveAt(index);
            try
            {
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn(
                    $"[GeneratedPlacementLedger] pending return quarantined after {pending.FailedAttempts} failed attempts: "
                    + $"item='{pending.GeneratedItemId}' at ({pending.X}, {pending.Y}) cause='{pending.FailureCause}'");
            }
            catch { }
        }
    }

    internal static bool AuthorizePlacement(Player player, GeneratedItemData data, RuntimePlacementSpec placement)
        => AuthorizePlacement(player, data, placement, Player.tileTargetX, Player.tileTargetY);

    internal static bool AuthorizePlacement(
        Player player,
        GeneratedItemData data,
        RuntimePlacementSpec placement,
        int targetX,
        int targetY)
    {
        if (player is null || data is null || placement is null || player.whoAmI < 0 || player.whoAmI >= Main.maxPlayers)
            return false;
        bool tile = placement.TileId >= 0 && placement.WallId < 0;
        bool wall = placement.WallId >= 0 && placement.TileId < 0;
        if (!tile && !wall)
            return false;
        if (!AdmitPlacedBodyNativeBoundary(placement)) return false;
        bool replacesExistingAuthorization = PendingAuthorizations.ContainsKey(player.whoAmI);
        int reservedAuthorizationCount = PendingAuthorizations.Count + (replacesExistingAuthorization ? 0 : 1);
        if ((long)Groups.Count + PendingReturns.Count + QuarantinedReturns.Count(record => !record.Requeued)
                + RawQuarantineEnvelopes.Count > MaxGroups - reservedAuthorizationCount
            || Placements.Count > MaxCells - reservedAuthorizationCount * MaxCellsPerGroup)
            return false;

        var layer = tile ? GeneratedPlacementLayer.Tile : GeneratedPlacementLayer.Wall;
        int expectedType = tile ? placement.TileId : placement.WallId;
        if (!WorldGen.InWorld(targetX, targetY, AuthorizationRadiusTiles) || !WithinPlacementReach(player, targetX, targetY))
            return false;
        if (PendingAuthorizations.TryGetValue(player.whoAmI, out PlacementAuthorization? existing)
            && (int)Main.GameUpdateCount <= existing.ExpiresAtTick)
        {
            if (ReferenceEquals(existing.SourcePlayer, player) && ReferenceEquals(existing.SourceData, data)
                && existing.TargetX == targetX && existing.TargetY == targetY
                && existing.Layer == layer && string.Equals(existing.GeneratedItemId, data.Id, StringComparison.Ordinal)) return true;
            // Nonzero remote activations require explicit ordered supersession at
            // the server packet boundary below. Local abandoned uses may retire
            // only while their native before-state is still unchanged.
            if (existing.Sequence != 0 || !CanSupersedeAuthorization(existing, player)) return false;
        }
        if (layer == GeneratedPlacementLayer.Wall && Main.tile[targetX, targetY].WallType == expectedType)
            return false;
        try
        {
            RuntimeBindingSpec? exactBinding = data.RuntimeProgram.Bindings.SingleOrDefault(binding =>
                ReferenceEquals(binding.UsePolicy.Action.Placement, placement));
            if (placement.PlacedBody is not null && (exactBinding is null || !SupportsPlacedBodyFootprint(placement)))
                return false;
            string definitionJson = data.ToNetworkJson();
            string definitionHash = PlacementDefinitionHash(definitionJson);
            if (definitionHash.Length == 0) return false;
            var before = new HashSet<long>();
            if (layer == GeneratedPlacementLayer.Tile)
            {
                ForEachAuthorizationCell(targetX, targetY, (x, y) =>
                {
                    Tile cell = Main.tile[x, y];
                    if (cell.HasTile && cell.TileType == expectedType)
                        before.Add(Pack(x, y));
                });
            }
            PendingAuthorizations[player.whoAmI] = new PlacementAuthorization
            {
                PlayerIndex = player.whoAmI,
                SourcePlayer = player,
                SourceData = data,
                GroupId = Main.netMode == NetmodeID.MultiplayerClient ? "" : Guid.NewGuid().ToString("N"),
                Layer = layer,
                TargetX = targetX,
                TargetY = targetY,
                ExpectedType = expectedType,
                ExpiresAtTick = (int)Main.GameUpdateCount
                    + (Main.netMode == NetmodeID.Server ? RemoteIntentLifetimeTicks : AuthorizationLifetimeTicks),
                GeneratedItemId = data.Id,
                DefinitionJson = definitionJson,
                DefinitionHash = definitionHash,
                BeforeExpectedTiles = before,
                BeforeWallType = Main.tile[targetX, targetY].WallType,
                PlacementBindingId = exactBinding?.Id ?? "",
                ExactPlacement = placement,
            };
            return true;
        }
        catch
        {
            return false;
        }
    }

    internal static bool TryCommitAuthorizedPlacement(Player player)
        => TryCommitAuthorizedPlacement(player, announcedLayer: null, announcedX: 0, announcedY: 0);

    private static bool CanSupersedeAuthorization(PlacementAuthorization authorization, Player player)
    {
        if (!ReferenceEquals(authorization.SourcePlayer, player) || authorization.NotifyReceived) return false;
        if (authorization.Layer == GeneratedPlacementLayer.Wall)
            return Main.tile[authorization.TargetX, authorization.TargetY].WallType == authorization.BeforeWallType;
        bool unchanged = true;
        ForEachAuthorizationCell(authorization.TargetX, authorization.TargetY, (x, y) =>
        {
            Tile cell = Main.tile[x, y];
            if ((cell.HasTile && cell.TileType == authorization.ExpectedType)
                != authorization.BeforeExpectedTiles.Contains(Pack(x, y))) unchanged = false;
        });
        return unchanged;
    }

    private static string PlacementDefinitionHash(string definitionJson)
    {
        GeneratedItemData? snapshot = GeneratedItemData.FromJson(definitionJson);
        return snapshot is null ? "" : GeneratedItemRegistryService.DefinitionIdentity(snapshot);
    }

    private static bool TryCommitAuthorizedPlacement(
        Player player,
        GeneratedPlacementLayer? announcedLayer,
        int announcedX,
        int announcedY)
    {
        if (player is null || !PendingAuthorizations.TryGetValue(player.whoAmI, out PlacementAuthorization? authorization)
            || !ReferenceEquals(authorization.SourcePlayer, player)
            || (Main.netMode == NetmodeID.Server && authorization.Sequence != 0 && !authorization.NotifyReceived))
            return false;
        if ((int)Main.GameUpdateCount > authorization.ExpiresAtTick)
        {
            PendingAuthorizations.Remove(player.whoAmI);
            return false;
        }
        if (announcedLayer.HasValue
            && (announcedLayer.Value != authorization.Layer
                || announcedX != authorization.TargetX
                || announcedY != authorization.TargetY))
            return false;
        if (!WithinPlacementReach(player, authorization.TargetX, authorization.TargetY))
            return false;

        List<GeneratedPlacementKey> committedCells = authorization.ExactPlacement?.PlacedBody is not null
            ? FindExactPlacedBodyCells(authorization) : FindCommittedCells(authorization);
        if (committedCells.Count == 0 || committedCells.Count > MaxCellsPerGroup)
            return false;
        if (!Guid.TryParseExact(authorization.GroupId, "N", out _)
            || Groups.ContainsKey(authorization.GroupId)
            || Groups.Count >= MaxGroups
            || Placements.Count > MaxCells - committedCells.Count
            || committedCells.Any(Placements.ContainsKey))
            return false;
        string groupId = authorization.GroupId;
        var group = new PlacementGroup
        {
            GroupId = groupId,
            GeneratedItemId = authorization.GeneratedItemId,
            DefinitionJson = authorization.DefinitionJson,
            Cells = committedCells,
            PlacedBody = CapturePlacedBodyWitness(authorization, committedCells),
        };
        Groups[groupId] = group;
        foreach (GeneratedPlacementKey key in committedCells)
            Placements[key] = groupId;
        PendingAuthorizations.Remove(player.whoAmI);
        RecordPlacementReceipt(player);
        // Commit the sole material owner/receipt before optional registry or packet work.
        PublishPlacedBodyGroupChange(group, removed: false);
        if (Main.netMode == NetmodeID.MultiplayerClient)
            SendPlacementToServer(authorization.Sequence, authorization.Layer, authorization.TargetX, authorization.TargetY);
        ClientPlacementIntents.Remove(player.whoAmI);
        return true;
    }

    private static List<GeneratedPlacementKey> FindCommittedCells(PlacementAuthorization authorization)
    {
        if (authorization.Layer == GeneratedPlacementLayer.Wall)
        {
            Tile cell = Main.tile[authorization.TargetX, authorization.TargetY];
            if (cell.WallType == authorization.ExpectedType && authorization.BeforeWallType != authorization.ExpectedType)
                return new List<GeneratedPlacementKey>
                {
                    new(GeneratedPlacementLayer.Wall, authorization.TargetX, authorization.TargetY),
                };
            return new List<GeneratedPlacementKey>();
        }

        // Scan the placed object's actual footprint.  The wide authorization
        // snapshot exists to prove "something appeared", but committing cells
        // from the full radius would absorb same-type tiles a different player
        // placed nearby during the 30-tick window.  The footprint comes from
        // TileObjectData when the tile type declares one (multi-tile objects are
        // larger than any fixed neighborhood window); otherwise it falls back to
        // the immediate 7x7 neighborhood.
        var changed = new HashSet<long>();
        int scanMinX = Math.Max(1, authorization.TargetX - CommitScanRadiusTiles);
        int scanMaxX = Math.Min(Main.maxTilesX - 2, authorization.TargetX + CommitScanRadiusTiles);
        int scanMinY = Math.Max(1, authorization.TargetY - CommitScanRadiusTiles);
        int scanMaxY = Math.Min(Main.maxTilesY - 2, authorization.TargetY + CommitScanRadiusTiles);
        var objectData = Terraria.ObjectData.TileObjectData.GetTileData(authorization.ExpectedType, 0);
        if (objectData is not null)
        {
            // The announced target may be any cell of the object; cover every
            // origin candidate that could place ExpectedType overlapping target.
            scanMinX = Math.Max(1, scanMinX - objectData.Width + 1);
            scanMaxX = Math.Min(Main.maxTilesX - 2, scanMaxX + objectData.Width - 1);
            scanMinY = Math.Max(1, scanMinY - objectData.Height + 1);
            scanMaxY = Math.Min(Main.maxTilesY - 2, scanMaxY + objectData.Height - 1);
        }
        for (int x = scanMinX; x <= scanMaxX; x++)
        {
            for (int y = scanMinY; y <= scanMaxY; y++)
            {
                Tile cell = Main.tile[x, y];
                long packed = Pack(x, y);
                if (cell.HasTile && cell.TileType == authorization.ExpectedType && !authorization.BeforeExpectedTiles.Contains(packed))
                    changed.Add(packed);
            }
        }
        if (changed.Count == 0)
            return new List<GeneratedPlacementKey>();
        // Deterministic seed: closest to the target, ties broken by coordinates.
        // HashSet order must never influence which connected component commits,
        // otherwise server and client ledgers diverge.  Distance and coordinates
        // are separate tuple keys: a packed-coordinate term inside one integer
        // would outweigh the distance weight (a 1-tile coordinate change moves
        // the packed term by 2^20 while the distance penalty is only 10^6).
        long seed = changed
            .OrderBy(value =>
            {
                Unpack(value, out int ux, out int uy);
                return (Math.Abs((long)ux - authorization.TargetX) + Math.Abs((long)uy - authorization.TargetY),
                    (long)(uint)ux,
                    (long)(uint)uy);
            })
            .First();
        var component = new List<GeneratedPlacementKey>();
        var queue = new Queue<long>();
        queue.Enqueue(seed);
        changed.Remove(seed);
        while (queue.Count > 0 && component.Count < MaxCellsPerGroup)
        {
            long current = queue.Dequeue();
            Unpack(current, out int x, out int y);
            component.Add(new GeneratedPlacementKey(GeneratedPlacementLayer.Tile, x, y));
            foreach ((int dx, int dy) in new[] { (-1, 0), (1, 0), (0, -1), (0, 1) })
            {
                long neighbor = Pack(x + dx, y + dy);
                if (changed.Remove(neighbor))
                    queue.Enqueue(neighbor);
            }
        }
        return component;
    }

    private static void SendPlacementToServer(ulong sequence, GeneratedPlacementLayer layer, int x, int y)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        ModPacket? packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if (packet is null)
            return;
        packet.Write(Common.InfiniNetPacketIds.NotifyGeneratedPlacement);
        packet.Write(PlacementProtocolVersion);
        packet.Write(sequence);
        packet.Write((byte)layer);
        packet.Write(x);
        packet.Write(y);
        packet.Send();
    }

    internal static bool PreparePlacement(Player player, GeneratedItemData data, RuntimePlacementSpec placement)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return AuthorizePlacement(player, data, placement);
        if (!AdmitPlacedBodyNativeBoundary(placement)) return false;
        int x = Player.tileTargetX, y = Player.tileTargetY, now = (int)Main.GameUpdateCount;
        if (player.whoAmI != Main.myPlayer || player.HeldItem is null || player.HeldItem.IsAir
            || !WorldGen.InWorld(x, y, AuthorizationRadiusTiles) || !WithinPlacementReach(player, x, y)) return false;
        byte input = (byte)(player.altFunctionUse == 2 ? 1 : 0);
        if (ClientPlacementIntents.TryGetValue(player.whoAmI, out ClientPlacementIntent? intent))
        {
            if (!ReferenceEquals(intent.Player, player) || !ReferenceEquals(intent.Item, player.HeldItem)
                || !ReferenceEquals(intent.Data, data) || !ReferenceEquals(intent.Placement, placement)
                || intent.Input != input || intent.X != x || intent.Y != y || now > intent.ExpiresAtTick)
            {
                if (PendingAuthorizations.TryGetValue(player.whoAmI, out PlacementAuthorization? prior)
                    && !CanSupersedeAuthorization(prior, player)) return false;
                RetiredClientPlacementIntents[player.whoAmI] = intent;
                ClientPlacementIntents.Remove(player.whoAmI);
                PendingAuthorizations.Remove(player.whoAmI);
                return false;
            }
            if (intent.Ready && !string.Equals(intent.DefinitionHash, PlacementDefinitionHash(data.ToNetworkJson()), StringComparison.Ordinal))
            {
                RetiredClientPlacementIntents[player.whoAmI] = intent;
                ClientPlacementIntents.Remove(player.whoAmI);
                return false;
            }
            if (!intent.Ready || !Guid.TryParseExact(intent.GroupId, "N", out _)
                || !AuthorizePlacement(player, data, placement, x, y)) return false;
            PendingAuthorizations[player.whoAmI].Sequence = intent.Sequence;
            PendingAuthorizations[player.whoAmI].GroupId = intent.GroupId;
            intent.UseAdmitted = true;
            return true;
        }
        if (_nextPlacementSequence == ulong.MaxValue) return false;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if (packet is null) return false;
        ulong sequence = ++_nextPlacementSequence;
        string definitionHash = PlacementDefinitionHash(data.ToNetworkJson());
        if (definitionHash.Length == 0) return false;
        ulong supersedes = RetiredClientPlacementIntents.Remove(player.whoAmI, out ClientPlacementIntent? retired)
            && ReferenceEquals(retired.Player, player) ? retired.Sequence : 0;
        ClientPlacementIntents[player.whoAmI] = new ClientPlacementIntent
        {
            Player = player, Item = player.HeldItem, Data = data, Placement = placement,
            Input = input, X = x, Y = y, Sequence = sequence, ExpiresAtTick = now + RemoteIntentLifetimeTicks,
            DefinitionHash = definitionHash,
        };
        packet.Write(Common.InfiniNetPacketIds.RequestGeneratedPlacementIntent);
        packet.Write(PlacementProtocolVersion); packet.Write(sequence); packet.Write(input); packet.Write(x); packet.Write(y);
        packet.Write(supersedes);
        try { packet.Send(); }
        catch { ClientPlacementIntents.Remove(player.whoAmI); return false; }
        // Do not let vanilla mutate/consume until the server captured real before-state.
        return false;
    }

    internal static void RefreshPlacementInput(Player player)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || player.whoAmI != Main.myPlayer
            || !ClientPlacementIntents.TryGetValue(player.whoAmI, out ClientPlacementIntent? intent)) return;
        var held = player.HeldItem?.ModItem as GeneratedItem;
        RuntimeBindingSpec? binding = held?.Data.RuntimeProgram.BindingForInput(intent.Input == 1
            ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse);
        if (!ReferenceEquals(intent.Player, player) || !ReferenceEquals(Main.player[player.whoAmI], player)
            || !player.active || player.dead || !ReferenceEquals(intent.Item, player.HeldItem)
            || !ReferenceEquals(intent.Data, held?.Data) || !ReferenceEquals(intent.Placement, binding?.UsePolicy.Action.Placement)
            || intent.Input != (byte)(player.altFunctionUse == 2 ? 1 : 0)
            || intent.X != Player.tileTargetX || intent.Y != Player.tileTargetY
            || (int)Main.GameUpdateCount > intent.ExpiresAtTick
            || !WithinPlacementReach(player, intent.X, intent.Y)
            || (!intent.UseAdmitted && !player.controlUseItem))
        {
            ClientPlacementIntents.Remove(player.whoAmI);
            // An admitted completion retains its original before-state. Only an
            // unstarted/finished-empty activation can be explicitly superseded.
            if ((!intent.UseAdmitted || (player.itemAnimation == 0 && player.itemTime == 0))
                && (!PendingAuthorizations.TryGetValue(player.whoAmI, out PlacementAuthorization? prior)
                    || CanSupersedeAuthorization(prior, player)))
            {
                RetiredClientPlacementIntents[player.whoAmI] = intent;
                PendingAuthorizations.Remove(player.whoAmI);
            }
            return;
        }
        // ItemCheck consumes releaseUseItem even when CanUseItem refused the
        // first press. Re-arm only this unchanged, still-held unstarted intent
        // once after Ready, never authored autoReuse or a released activation.
        if (intent.Ready && !intent.UseAdmitted && !intent.NativeRetrySpent
            && player.controlUseItem && player.itemAnimation == 0 && player.itemTime == 0 && player.reuseDelay == 0
            && string.Equals(intent.DefinitionHash, PlacementDefinitionHash(intent.Data.ToNetworkJson()), StringComparison.Ordinal))
        {
            intent.NativeRetrySpent = true;
            player.releaseUseItem = true;
        }
    }

    internal static void HandlePlacementReadyPacket(BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || whoAmI != 256) return;
        if (reader.ReadInt32() != PlacementProtocolVersion) throw new InvalidDataException("Unsupported placement ready protocol");
        ulong sequence = reader.ReadUInt64(); bool accepted = reader.ReadBoolean();
        string definitionHash = accepted ? reader.ReadString() : "";
        string groupId = accepted ? reader.ReadString() : "";
        if (!ClientPlacementIntents.TryGetValue(Main.myPlayer, out ClientPlacementIntent? intent)
            || intent.Sequence != sequence || (int)Main.GameUpdateCount > intent.ExpiresAtTick) return;
        if (accepted && Guid.TryParseExact(groupId, "N", out _)
            && (!intent.Ready || string.Equals(intent.GroupId, groupId, StringComparison.Ordinal))
            && string.Equals(definitionHash, intent.DefinitionHash, StringComparison.Ordinal)
            && string.Equals(definitionHash, PlacementDefinitionHash(intent.Data.ToNetworkJson()), StringComparison.Ordinal))
        {
            intent.GroupId = groupId;
            intent.Ready = true;
        }
        else
        {
            RetiredClientPlacementIntents[Main.myPlayer] = intent;
            ClientPlacementIntents.Remove(Main.myPlayer);
        }
    }

    internal static void HandlePlacementIntentPacket(BinaryReader reader, int whoAmI)
    {
        if (reader.ReadInt32() != PlacementProtocolVersion) throw new InvalidDataException("Unsupported placement intent protocol");
        ulong sequence = reader.ReadUInt64(); byte input = reader.ReadByte(); int x = reader.ReadInt32(), y = reader.ReadInt32();
        ulong supersedes = reader.ReadUInt64();
        if (Main.netMode != NetmodeID.Server || whoAmI < 0 || whoAmI >= Main.maxPlayers
            || Main.player[whoAmI] is not { active: true } player || input > 1 || sequence == 0
            || !WorldGen.InWorld(x, y, AuthorizationRadiusTiles) || !WithinPlacementReach(player, x, y)) return;
        if (!PlacementPeerCursors.TryGetValue(whoAmI, out PlacementPeerCursor? cursor) || !ReferenceEquals(cursor.Player, player))
            PlacementPeerCursors[whoAmI] = cursor = new PlacementPeerCursor { Player = player };
        if (sequence <= cursor.Sequence) return;
        cursor.Sequence = sequence;
        int now = (int)Main.GameUpdateCount;
        bool accepted = false;
        PendingAuthorizations.TryGetValue(whoAmI, out PlacementAuthorization? prior);
        if (cursor.LastIntentTick != now)
        {
            cursor.LastIntentTick = now;
            // Input chooses only a registered binding on the server-observed held
            // instance. No client id, definition, type or before-state is admitted.
            if (player.HeldItem is { IsAir: false, stack: > 0 } item && item.ModItem is GeneratedItem held
                && held.Data is not null)
            {
                RuntimeBindingSpec? binding = held.Data.RuntimeProgram.BindingForInput(input == 1
                    ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse);
                RuntimePlacementSpec? placement = binding?.UsePolicy?.Action?.Placement;
                if (binding?.UsePolicy?.Action?.Kind == RuntimeBindingAction.PlaceItem
                    && binding.UsePolicy.StackCost == 1 && placement is not null
                    && string.IsNullOrEmpty(GeneratedItem.UseBlockedReason(player, held.Data.Gameplay)))
                {
                    // A newer ordered request names the exact abandoned intent.
                    // Never discard a notify or a native mutation, and never let
                    // a late old notify reconstruct the retired snapshot.
                    bool mayAuthorize = prior is null || now > prior.ExpiresAtTick || prior.Sequence == 0;
                    if (!mayAuthorize && supersedes == prior!.Sequence && sequence > prior.Sequence
                        && CanSupersedeAuthorization(prior, player))
                    {
                        PendingAuthorizations.Remove(whoAmI);
                        mayAuthorize = true;
                    }
                    if (mayAuthorize && AuthorizePlacement(player, held.Data, placement, x, y))
                    {
                        PendingAuthorizations[whoAmI].Sequence = sequence;
                        accepted = true;
                    }
                }
            }
        }
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if (packet is null) return;
        packet.Write(Common.InfiniNetPacketIds.GeneratedPlacementIntentReady);
        packet.Write(PlacementProtocolVersion); packet.Write(sequence); packet.Write(accepted);
        if (accepted)
        {
            packet.Write(PendingAuthorizations[whoAmI].DefinitionHash);
            packet.Write(PendingAuthorizations[whoAmI].GroupId);
        }
        packet.Send(whoAmI);
    }

    internal static void HandlePlacementPacket(BinaryReader reader, int whoAmI)
    {
        if (reader.ReadInt32() != PlacementProtocolVersion) throw new InvalidDataException("Unsupported placement notify protocol");
        ulong sequence = reader.ReadUInt64(); var layer = (GeneratedPlacementLayer)reader.ReadByte();
        int x = reader.ReadInt32(), y = reader.ReadInt32();
        if (Main.netMode != NetmodeID.Server || !Enum.IsDefined(typeof(GeneratedPlacementLayer), layer)
            || whoAmI < 0 || whoAmI >= Main.maxPlayers || Main.player[whoAmI] is not { active: true } player
            || !WorldGen.InWorld(x, y, AuthorizationRadiusTiles) || !WithinPlacementReach(player, x, y)
            || !PendingAuthorizations.TryGetValue(whoAmI, out PlacementAuthorization? authorization)
            || authorization.Sequence == 0 || authorization.Sequence != sequence
            || authorization.Layer != layer || authorization.TargetX != x || authorization.TargetY != y) return;
        authorization.NotifyReceived = true;
        // A late notify can only finish an already server-owned before snapshot.
        // It can never synthesize a new authorization from an existing cell.
        TryCommitAuthorizedPlacement(player, layer, x, y);
    }

    private static bool WithinPlacementReach(Player player, int x, int y)
    {
        Microsoft.Xna.Framework.Point center = player.Center.ToTileCoordinates();
        return Math.Abs(center.X - x) <= 20 && Math.Abs(center.Y - y) <= 20;
    }

    private static void ForEachAuthorizationCell(int targetX, int targetY, Action<int, int> action)
        => ForEachAuthorizationCell(targetX, targetY, AuthorizationRadiusTiles, action);

    private static void ForEachAuthorizationCell(int targetX, int targetY, int radiusTiles, Action<int, int> action)
    {
        int minX = Math.Max(1, targetX - radiusTiles);
        int maxX = Math.Min(Main.maxTilesX - 2, targetX + radiusTiles);
        int minY = Math.Max(1, targetY - radiusTiles);
        int maxY = Math.Min(Main.maxTilesY - 2, targetY + radiusTiles);
        for (int x = minX; x <= maxX; x++)
            for (int y = minY; y <= maxY; y++)
                action(x, y);
    }

    private static long Pack(int x, int y) => ((long)x << 32) | (uint)y;

    private static void Unpack(long value, out int x, out int y)
    {
        x = (int)(value >> 32);
        y = (int)value;
    }

    private static void RecordPlacementReceipt(Player player)
    {
        if (player.whoAmI >= 0 && player.whoAmI < Main.maxPlayers)
            PlacementReceiptExpiryByPlayer[player.whoAmI] = (int)Main.GameUpdateCount + PlacementReceiptLifetimeTicks;
    }

    internal static bool TryConsumePlacementReceipt(Player player)
    {
        if (player is null || !PlacementReceiptExpiryByPlayer.Remove(player.whoAmI, out int expiry))
            return false;
        return (int)Main.GameUpdateCount <= expiry;
    }

    internal static bool Contains(GeneratedPlacementLayer layer, int x, int y)
        => Placements.ContainsKey(new GeneratedPlacementKey(layer, x, y));

    internal static bool TryQueueReturn(GeneratedPlacementLayer layer, int x, int y)
    {
        var key = new GeneratedPlacementKey(layer, x, y);
        if (!Placements.TryGetValue(key, out string? groupId) || !Groups.TryGetValue(groupId, out PlacementGroup? group))
            return false;
        if (Main.netMode == NetmodeID.MultiplayerClient)
            return true;
        foreach (GeneratedPlacementKey cell in group.Cells)
            Placements.Remove(cell);
        Groups.Remove(groupId);
        var pending = new PendingReturnRecord
        {
            GroupId = group.GroupId,
            GeneratedItemId = group.GeneratedItemId,
            DefinitionJson = group.DefinitionJson,
            X = x,
            Y = y,
        };
        PendingReturns.Add(pending);
        PublishPlacedBodyGroupChange(group, removed: true);
        if (TrySpawnPendingReturn(pending) == PendingSpawnOutcome.Spawned)
            PendingReturns.Remove(pending);
        return true;
    }

    private enum PendingSpawnOutcome
    {
        Spawned,
        // Slot allocation or world-state pressure: retry later, never quarantine.
        TransientFailure,
        // Deterministically broken record (bad definition, id mismatch, wrong mod item).
        PermanentFailure,
    }

    private static PendingSpawnOutcome TrySpawnPendingReturn(PendingReturnRecord pending)
    {
        try { return TrySpawnPendingReturnCore(pending); }
        catch { return PendingSpawnOutcome.TransientFailure; }
    }

    private static bool IsMaterialPlacementDefinition(GeneratedItemData data)
        => data.SourceMode is not ("player_save_ref" or "corrupt_reference")
            && data.Id != "placeholder"
            && data.RuntimeProgram.Bindings.Any(binding => binding.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem
                && binding.UsePolicy.StackCost == 1 && binding.UsePolicy.Action.Placement is not null);

    private static PendingSpawnOutcome TrySpawnPendingReturnCore(PendingReturnRecord pending)
    {
        // The raw durable definition owns this claim. Do not borrow a registry
        // definition merely because its id matches a permanently broken record.
        GeneratedItemData? data = GeneratedItemData.FromJson(pending.DefinitionJson);
        if (data is null)
        {
            pending.FailureCause = "definition_invalid";
            return PendingSpawnOutcome.PermanentFailure;
        }
        if (!string.Equals(data.Id, pending.GeneratedItemId, StringComparison.Ordinal))
        {
            pending.FailureCause = "identity_mismatch";
            return PendingSpawnOutcome.PermanentFailure;
        }

        if (!IsMaterialPlacementDefinition(data))
        {
            pending.FailureCause = "definition_not_material_placement";
            return PendingSpawnOutcome.PermanentFailure;
        }
        bool asArmorProxy = GeneratedArmorItemTypes.CanRepresent(data);
        int itemType = asArmorProxy
            ? GeneratedArmorItemTypes.ItemTypeFor(data)
            : ModContent.ItemType<GeneratedItem>();
        int index = Item.NewItem(
            WorldGen.GetItemSource_FromTileBreak(pending.X, pending.Y),
            pending.X * 16,
            pending.Y * 16,
            16,
            16,
            itemType,
            1,
            noBroadcast: true);
        if (index < 0 || index >= Main.maxItems)
            return PendingSpawnOutcome.TransientFailure;
        // Configure the instance NewItem actually created.  Overwriting
        // Main.item[index] with a separately defaulted instance would leave a
        // stale whoAmI and skip vanilla spawn initialization.
        Item spawned = Main.item[index];
        if (spawned.ModItem is not GeneratedItem generated)
        {
            spawned.TurnToAir();
            pending.FailureCause = "proxy_invalid";
            return PendingSpawnOutcome.PermanentFailure;
        }
        generated.SetData(data);
        if (!string.Equals(generated.Data.Id, pending.GeneratedItemId, StringComparison.Ordinal))
        {
            spawned.TurnToAir();
            pending.FailureCause = "projection_identity_mismatch";
            return PendingSpawnOutcome.PermanentFailure;
        }
        spawned.stack = 1;
        if (Main.netMode == NetmodeID.Server)
        {
            try { NetMessage.SendData(MessageID.SyncItem, -1, -1, null, index); }
            catch { }
        }
        return PendingSpawnOutcome.Spawned;
    }
}

public sealed class GeneratedPlacementLedgerTile : GlobalTile
{
    public override bool CanDrop(int i, int j, int type)
    {
        if (!GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Tile, i, j))
            return true;
        GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile, i, j);
        return false;
    }
}

public sealed class GeneratedPlacementLedgerWall : GlobalWall
{
    public override bool Drop(int i, int j, int type, ref int dropType)
    {
        if (!GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, i, j))
            return true;
        GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Wall, i, j);
        return false;
    }
}
