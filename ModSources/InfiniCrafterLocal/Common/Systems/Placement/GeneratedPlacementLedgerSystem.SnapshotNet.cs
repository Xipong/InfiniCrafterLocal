#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    // Frames leave ample room for tML's ushort-length packet header. A single
    // legal witness may exceed a packet, so fragmentation is byte-, not row-based.
    private const int SnapshotChunkBytes = 32 * 1024;
    private const int MaxMirrorGroupBytes = MaxPlacedBodyWitnessBytes + MaxCellsPerGroup * 9 + 512;
    private enum SnapshotFrame : byte { Request, Begin, Group, End }
    private static bool _bodySnapshotRequested;
    private static Dictionary<string, PlacementGroup>? _snapshotGroups;
    private static HashSet<GeneratedPlacementKey>? _snapshotCells;
    private static MemoryStream? _snapshotGroupBytes;
    private static int _snapshotGroupLength, _snapshotGroupCount;
    private static ulong _snapshotRevision;

    private static void ClearPlacedBodySnapshot()
    {
        _snapshotGroups = null; _snapshotCells = null;
        _snapshotGroupBytes?.Dispose(); _snapshotGroupBytes = null;
        _snapshotGroupLength = _snapshotGroupCount = 0;
        _snapshotRevision = 0;
    }

    private static void RequestPlacedBodySnapshot()
    {
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if (packet is null) return;
        packet.Write(Common.InfiniNetPacketIds.GeneratedPlacedBodySnapshot);
        packet.Write(PayloadVersion); packet.Write((byte)SnapshotFrame.Request);
        packet.Send();
        _bodySnapshotRequested = true;
    }

    private static byte[] SnapshotPacket(SnapshotFrame frame, Action<BinaryWriter> write)
    {
        using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream);
        writer.Write(PayloadVersion); writer.Write((byte)frame); write(writer);
        return stream.ToArray();
    }

    // Enumerated synchronously on the network/game thread: no tick or placement
    // delta can interleave the begin/group/end sequence. Only one group is encoded
    // at a time; neither a WorldData-sized cap nor a second giant byte[] is needed.
    internal static IEnumerable<byte[]> PlacedBodySnapshotPackets()
    {
        RestorePlacedBodyDefinitions(publish: true);
        ulong revision = _placedBodyRevision;
        yield return SnapshotPacket(SnapshotFrame.Begin, w => { w.Write(revision); w.Write(Groups.Count); });
        int index = 0;
        foreach (PlacementGroup group in Groups.Values.OrderBy(g => g.GroupId, StringComparer.Ordinal))
        {
            using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream);
            WriteMirrorGroup(writer, group);
            byte[] bytes = stream.ToArray();
            if (bytes.Length > MaxMirrorGroupBytes) throw new InvalidDataException("placement mirror group capacity");
            for (int offset = 0; offset < bytes.Length; offset += SnapshotChunkBytes)
            {
                int start = offset, length = Math.Min(SnapshotChunkBytes, bytes.Length - offset);
                yield return SnapshotPacket(SnapshotFrame.Group, w => {
                    w.Write(index); w.Write(bytes.Length); w.Write(start); w.Write(length); w.Write(bytes, start, length);
                });
            }
            index++;
        }
        yield return SnapshotPacket(SnapshotFrame.End, w => w.Write(revision));
    }

    internal static void HandlePlacedBodySnapshotPacket(BinaryReader reader, int whoAmI)
    {
        int version = reader.ReadInt32(); var frame = (SnapshotFrame)reader.ReadByte();
        if (version != PayloadVersion) return;
        if (Main.netMode == NetmodeID.Server)
        {
            if (frame != SnapshotFrame.Request || whoAmI < 0 || whoAmI >= Main.maxPlayers) return;
            foreach (byte[] bytes in PlacedBodySnapshotPackets())
            {
                var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
                if (packet is null) return;
                packet.Write(Common.InfiniNetPacketIds.GeneratedPlacedBodySnapshot); packet.Write(bytes); packet.Send(whoAmI);
            }
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient || whoAmI != 256) return;
        EnsurePlacedBodyMirrorSender();
        try
        {
            switch (frame)
            {
                case SnapshotFrame.Begin:
                    ClearPlacedBodySnapshot();
                    _snapshotRevision = reader.ReadUInt64(); _snapshotGroupCount = reader.ReadInt32();
                    if (_snapshotGroupCount < 0 || _snapshotGroupCount > MaxGroups)
                        throw new InvalidDataException("placement snapshot group capacity");
                    _snapshotGroups = new(StringComparer.Ordinal); _snapshotCells = new();
                    break;
                case SnapshotFrame.Group:
                    if (_snapshotGroups is null || _snapshotCells is null) return;
                    int index = reader.ReadInt32(), total = reader.ReadInt32(), offset = reader.ReadInt32(), length = reader.ReadInt32();
                    if (index != _snapshotGroups.Count || index >= _snapshotGroupCount || total < 1 || total > MaxMirrorGroupBytes
                        || offset < 0 || length < 1 || length > SnapshotChunkBytes || (long)offset + length > total
                        || offset != (_snapshotGroupBytes?.Length ?? 0) || (_snapshotGroupBytes is not null && total != _snapshotGroupLength))
                        throw new InvalidDataException("placement snapshot fragment order/size");
                    _snapshotGroupBytes ??= new MemoryStream(total); _snapshotGroupLength = total;
                    byte[] bytes = reader.ReadBytes(length);
                    if (bytes.Length != length) throw new EndOfStreamException();
                    _snapshotGroupBytes.Write(bytes, 0, bytes.Length);
                    if (_snapshotGroupBytes.Length != total) break;
                    _snapshotGroupBytes.Position = 0;
                    using (var groupReader = new BinaryReader(_snapshotGroupBytes, System.Text.Encoding.UTF8, true))
                    {
                        PlacementGroup group = ReadMirrorGroup(groupReader);
                        if (_snapshotGroupBytes.Position != total || !_snapshotGroups.TryAdd(group.GroupId, group)
                            || group.Cells.Any(cell => !_snapshotCells.Add(cell)) || _snapshotCells.Count > MaxCells)
                            throw new InvalidDataException("placement snapshot identity/overlap/capacity");
                    }
                    _snapshotGroupBytes.Dispose(); _snapshotGroupBytes = null;
                    break;
                case SnapshotFrame.End:
                    ulong revision = reader.ReadUInt64();
                    if (_snapshotGroups is null || _snapshotGroups.Count != _snapshotGroupCount
                        || _snapshotGroupBytes is not null || revision != _snapshotRevision)
                        throw new InvalidDataException("incomplete placement snapshot");
                    if (revision >= _placedBodyRevision && (!_bodySnapshotReceived || revision != _placedBodyRevision))
                    {
                        Groups.Clear(); Placements.Clear(); PlacedBodyViews.Clear();
                        BodyHydrationQueue.Clear(); BodyHydrationNodes.Clear();
                        foreach (PlacementGroup group in _snapshotGroups.Values)
                        {
                            Groups[group.GroupId] = group;
                            foreach (GeneratedPlacementKey cell in group.Cells) Placements[cell] = group.GroupId;
                            EnqueuePlacedBodyHydration(group);
                        }
                        _placedBodyRevision = revision; _bodySnapshotReceived = true;
                    }
                    ClearPlacedBodySnapshot(); _bodySnapshotRequested = false;
                    // Ordered server sends normally cannot be overtaken. If a newer
                    // delta did arrive, do not let the stale snapshot erase it.
                    if (!_bodySnapshotReceived) RequestPlacedBodySnapshot();
                    break;
                default:
                    throw new InvalidDataException("placement snapshot frame");
            }
        }
        catch (Exception ex) when (ex is IOException || ex is InvalidDataException)
        {
            ClearPlacedBodySnapshot(); _bodySnapshotRequested = false;
            // Retain the last complete mirror; no partial snapshot is authoritative.
        }
    }
}
