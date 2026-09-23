#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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
public sealed class GeneratedPlacementLedgerSystem : ModSystem
{
    private const int PayloadVersion = 2;
    private const string SaveKey = "infiniGeneratedPlacementLedgerV2";
    private const string PendingSaveKey = "infiniGeneratedPlacementReturnsV2";
    private const int MaxGroups = 8192;
    private const int MaxCells = 32768;
    private const int MaxCellsPerGroup = 256;
    private const int AuthorizationRadiusTiles = 16;
    // Commit detection only needs the immediate neighborhood of the announced
    // target.  A wide scan would absorb same-type tiles another player placed
    // nearby into this group, so keep the committed-cell window tight.
    private const int CommitScanRadiusTiles = 3;
    private const int AuthorizationLifetimeTicks = 30;
    private const int PlacementReceiptLifetimeTicks = 8;
    private const int MaxPendingAttemptsPerTick = 8;

    private sealed class PlacementGroup
    {
        public string GroupId { get; init; } = "";
        public string GeneratedItemId { get; init; } = "";
        public string DefinitionJson { get; init; } = "";
        public List<GeneratedPlacementKey> Cells { get; init; } = new();
    }

    private sealed class PendingReturnRecord
    {
        public string GroupId { get; init; } = "";
        public string GeneratedItemId { get; init; } = "";
        public string DefinitionJson { get; init; } = "";
        public int X { get; init; }
        public int Y { get; init; }
        // Failed spawn attempts (runtime ticks).  Not persisted: a fresh load
        // grants a fresh budget, which is safe because the record itself is
        // durable and each tick re-attempts before quarantining.
        public int FailedAttempts { get; set; }
    }

    private sealed class PlacementAuthorization
    {
        public int PlayerIndex { get; init; }
        public GeneratedPlacementLayer Layer { get; init; }
        public int TargetX { get; init; }
        public int TargetY { get; init; }
        public int ExpectedType { get; init; }
        public int ExpiresAtTick { get; init; }
        public string GeneratedItemId { get; init; } = "";
        public string DefinitionJson { get; init; } = "";
        public HashSet<long> BeforeExpectedTiles { get; init; } = new();
        public int BeforeWallType { get; init; }
    }

    private static readonly Dictionary<GeneratedPlacementKey, string> Placements = new();
    private static readonly Dictionary<string, PlacementGroup> Groups = new(StringComparer.Ordinal);
    private static readonly List<PendingReturnRecord> PendingReturns = new();
    private static readonly Dictionary<int, PlacementAuthorization> PendingAuthorizations = new();
    private static readonly Dictionary<int, int> PlacementReceiptExpiryByPlayer = new();

    public override void ClearWorld()
    {
        Placements.Clear();
        Groups.Clear();
        PendingReturns.Clear();
        PendingAuthorizations.Clear();
        PlacementReceiptExpiryByPlayer.Clear();
    }

    public override void SaveWorldData(TagCompound tag)
    {
        tag[SaveKey] = Groups.Values
            .OrderBy(x => x.GroupId, StringComparer.Ordinal)
            .Select(group => new TagCompound
            {
                ["groupId"] = group.GroupId,
                ["generatedItemId"] = group.GeneratedItemId,
                ["definitionJson"] = group.DefinitionJson,
                ["cells"] = group.Cells.Select(cell => new TagCompound
                {
                    ["layer"] = (int)cell.Layer,
                    ["x"] = cell.X,
                    ["y"] = cell.Y,
                }).ToList(),
            }).ToList();
        tag[PendingSaveKey] = PendingReturns.Select(pending => new TagCompound
        {
            ["groupId"] = pending.GroupId,
            ["generatedItemId"] = pending.GeneratedItemId,
            ["definitionJson"] = pending.DefinitionJson,
            ["x"] = pending.X,
            ["y"] = pending.Y,
        }).ToList();
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
            };
        }
        foreach (TagCompound row in tag.GetList<TagCompound>(PendingSaveKey).Take(MaxGroups))
        {
            string id = (row.GetString("generatedItemId") ?? "").Trim();
            string json = row.GetString("definitionJson") ?? "";
            int x = row.GetInt("x");
            int y = row.GetInt("y");
            if (id.Length == 0 || json.Length == 0 || !WorldGen.InWorld(x, y, 1))
                continue;
            PendingReturns.Add(new PendingReturnRecord
            {
                GroupId = (row.GetString("groupId") ?? Guid.NewGuid().ToString("N")).Trim(),
                GeneratedItemId = id,
                DefinitionJson = json,
                X = x,
                Y = y,
            });
        }
    }

    public override void NetSend(BinaryWriter writer)
    {
        writer.Write(PayloadVersion);
        writer.Write(Groups.Count);
        foreach (PlacementGroup group in Groups.Values.OrderBy(x => x.GroupId, StringComparer.Ordinal))
        {
            writer.Write(group.GroupId);
            writer.Write(group.GeneratedItemId);
            writer.Write(group.Cells.Count);
            foreach (GeneratedPlacementKey cell in group.Cells)
            {
                writer.Write((byte)cell.Layer);
                writer.Write(cell.X);
                writer.Write(cell.Y);
            }
        }
    }

    public override void NetReceive(BinaryReader reader)
    {
        int version = reader.ReadInt32();
        if (version != PayloadVersion)
            throw new InvalidDataException($"Unsupported generated placement ledger payload {version}");
        Placements.Clear();
        Groups.Clear();
        int groupCount = Math.Clamp(reader.ReadInt32(), 0, MaxGroups);
        for (int groupIndex = 0; groupIndex < groupCount; groupIndex++)
        {
            string groupId = reader.ReadString();
            string generatedItemId = reader.ReadString();
            int cellCount = Math.Clamp(reader.ReadInt32(), 0, MaxCellsPerGroup);
            var cells = new List<GeneratedPlacementKey>();
            for (int cellIndex = 0; cellIndex < cellCount; cellIndex++)
            {
                var layer = (GeneratedPlacementLayer)reader.ReadByte();
                int x = reader.ReadInt32();
                int y = reader.ReadInt32();
                if (!Enum.IsDefined(typeof(GeneratedPlacementLayer), layer) || !WorldGen.InWorld(x, y, 1) || Placements.Count >= MaxCells)
                    continue;
                var key = new GeneratedPlacementKey(layer, x, y);
                Placements[key] = groupId;
                cells.Add(key);
            }
            if (groupId.Length > 0 && generatedItemId.Length > 0 && cells.Count > 0)
                // Client-side mirror groups intentionally carry no DefinitionJson:
                // returns are server-only (TryQueueReturn exits early on clients),
                // so the definition is never needed here.  Do not start reading
                // Groups[...].DefinitionJson on a client without extending NetSend.
                Groups[groupId] = new PlacementGroup
                {
                    GroupId = groupId,
                    GeneratedItemId = generatedItemId,
                    Cells = cells,
                };
        }
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
            if (playerIndex >= 0 && playerIndex < Main.maxPlayers && Main.player[playerIndex].active)
                TryCommitAuthorizedPlacement(Main.player[playerIndex]);
        }

        foreach (int playerIndex in PlacementReceiptExpiryByPlayer.Where(x => x.Value < now).Select(x => x.Key).ToArray())
            PlacementReceiptExpiryByPlayer.Remove(playerIndex);

        if (Main.netMode == NetmodeID.MultiplayerClient)
            return;
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
            // Deterministically broken record (unparseable definition, missing id).
            // Quarantine it so it cannot starve the rest of the queue; the placed
            // item is lost but the world log keeps the reason.
            PendingReturns.RemoveAt(index);
            try
            {
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn(
                    $"[GeneratedPlacementLedger] pending return quarantined after {pending.FailedAttempts} failed attempts: "
                    + $"item='{pending.GeneratedItemId}' at ({pending.X}, {pending.Y})");
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
        bool replacesExistingAuthorization = PendingAuthorizations.ContainsKey(player.whoAmI);
        int reservedAuthorizationCount = PendingAuthorizations.Count + (replacesExistingAuthorization ? 0 : 1);
        if (Groups.Count > MaxGroups - reservedAuthorizationCount
            || Placements.Count > MaxCells - reservedAuthorizationCount * MaxCellsPerGroup)
            return false;

        var layer = tile ? GeneratedPlacementLayer.Tile : GeneratedPlacementLayer.Wall;
        int expectedType = tile ? placement.TileId : placement.WallId;
        if (!WorldGen.InWorld(targetX, targetY, AuthorizationRadiusTiles) || !WithinPlacementReach(player, targetX, targetY))
            return false;
        try
        {
            string definitionJson = data.ToNetworkJson();
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
                Layer = layer,
                TargetX = targetX,
                TargetY = targetY,
                ExpectedType = expectedType,
                ExpiresAtTick = (int)Main.GameUpdateCount + AuthorizationLifetimeTicks,
                GeneratedItemId = data.Id,
                DefinitionJson = definitionJson,
                BeforeExpectedTiles = before,
                BeforeWallType = Main.tile[targetX, targetY].WallType,
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

    private static bool TryCommitAuthorizedPlacement(
        Player player,
        GeneratedPlacementLayer? announcedLayer,
        int announcedX,
        int announcedY)
    {
        if (player is null || !PendingAuthorizations.TryGetValue(player.whoAmI, out PlacementAuthorization? authorization))
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

        List<GeneratedPlacementKey> committedCells = FindCommittedCells(authorization);
        if (committedCells.Count == 0 || committedCells.Count > MaxCellsPerGroup)
            return false;
        if (Groups.Count >= MaxGroups
            || Placements.Count > MaxCells - committedCells.Count
            || committedCells.Any(Placements.ContainsKey))
            return false;
        string groupId = Guid.NewGuid().ToString("N");
        var group = new PlacementGroup
        {
            GroupId = groupId,
            GeneratedItemId = authorization.GeneratedItemId,
            DefinitionJson = authorization.DefinitionJson,
            Cells = committedCells,
        };
        Groups[groupId] = group;
        foreach (GeneratedPlacementKey key in committedCells)
            Placements[key] = groupId;
        PendingAuthorizations.Remove(player.whoAmI);
        RecordPlacementReceipt(player);
        if (Main.netMode == NetmodeID.MultiplayerClient)
            SendPlacementToServer(authorization.Layer, authorization.TargetX, authorization.TargetY);
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

    private static void SendPlacementToServer(GeneratedPlacementLayer layer, int x, int y)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        ModPacket? packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if (packet is null)
            return;
        packet.Write(Common.InfiniNetPacketIds.NotifyGeneratedPlacement);
        packet.Write(PayloadVersion);
        packet.Write((byte)layer);
        packet.Write(x);
        packet.Write(y);
        packet.Send();
    }

    internal static void HandlePlacementPacket(BinaryReader reader, int whoAmI)
    {
        int version = reader.ReadInt32();
        if (version != PayloadVersion)
            throw new InvalidDataException($"Unsupported generated placement packet {version}");
        var layer = (GeneratedPlacementLayer)reader.ReadByte();
        int x = reader.ReadInt32();
        int y = reader.ReadInt32();
        if (Main.netMode != NetmodeID.Server
            || !Enum.IsDefined(typeof(GeneratedPlacementLayer), layer)
            || whoAmI < 0
            || whoAmI >= Main.maxPlayers
            || !Main.player[whoAmI].active)
            return;
        Player player = Main.player[whoAmI];
        if (TryCommitAuthorizedPlacement(player, layer, x, y))
            return;
        // Dedicated server: the authorization lives in the client's process, so the
        // first notification arrives without server-local state. Establish it from
        // the server's own view of the player's held item - the packet never carries
        // the item identity, the server derives everything it accepts.
        TryAuthorizePlacementFromHeldItem(player, layer, x, y);
        TryCommitAuthorizedPlacement(player, layer, x, y);
    }

    private static void TryAuthorizePlacementFromHeldItem(Player player, GeneratedPlacementLayer layer, int x, int y)
    {
        if (player.HeldItem?.ModItem is not GeneratedItem held || held.Data is null)
            return;
        GeneratedItemData data = held.Data;
        bool isTile = layer == GeneratedPlacementLayer.Tile;
        Tile cell = Main.tile[x, y];
        int observedType = isTile ? cell.TileType : cell.WallType;
        if (observedType < 0)
            return;
        foreach (RuntimeBindingSpec binding in data.RuntimeProgram.Bindings)
        {
            if (binding.UsePolicy?.Action?.Kind != RuntimeBindingAction.PlaceItem)
                continue;
            RuntimePlacementSpec? placement = binding.UsePolicy.Action.Placement;
            if (placement is null)
                continue;
            int authoredType = isTile ? placement.TileId : placement.WallId;
            if (authoredType != observedType)
                continue;
            if (!AuthorizePlacement(player, data, placement, x, y))
                return;
            // One placement authorization per player; the first matching binding wins.
            return;
        }
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

    private static PendingSpawnOutcome TrySpawnPendingReturnCore(PendingReturnRecord pending)
    {
        GeneratedItemData? data = null;
        GeneratedItemRegistryService? registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is not null
            && registry.TryGet(pending.GeneratedItemId, out GeneratedItemData canonical)
            && GeneratedItemRegistryService.IsCurrentWorldData(canonical))
            data = canonical;
        data ??= GeneratedItemData.FromJson(pending.DefinitionJson);
        if (data is null || !string.Equals(data.Id, pending.GeneratedItemId, StringComparison.Ordinal))
            return PendingSpawnOutcome.PermanentFailure;

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
            return PendingSpawnOutcome.PermanentFailure;
        generated.SetData(data);
        if (!string.Equals(generated.Data.Id, pending.GeneratedItemId, StringComparison.Ordinal))
            return PendingSpawnOutcome.PermanentFailure;
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
