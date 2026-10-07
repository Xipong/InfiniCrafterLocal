#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    private const int MaxPlacedBodyWitnessBytes = 64 * 1024;
    private const int MaxBodyHydrationVisitsPerTick = 32;
    private static ulong _placedBodyRevision;
    // Derived work only: one removable node per unresolved, currently retained group.
    // No material authority, definition hash or new asset transport lives here.
    private static readonly LinkedList<string> BodyHydrationQueue = new();
    private static readonly Dictionary<string, LinkedListNode<string>> BodyHydrationNodes = new(StringComparer.Ordinal);
    private static ulong? _bodyHydrationTick;
    private static int _bodyHydrationVisits;
    private static object? _bodyMirrorSocket;
    private static bool _bodyMirrorSenderBound, _bodySnapshotReceived;

    private static void ClearPlacedBodyMirrorState()
    {
        BodyHydrationQueue.Clear(); BodyHydrationNodes.Clear();
        _bodyHydrationTick = null; _bodyHydrationVisits = 0;
        _bodyMirrorSocket = null; _bodyMirrorSenderBound = _bodySnapshotReceived = false;
    }

    private static void EnsurePlacedBodyMirrorSender()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient) return;
        object? socket = Netplay.Connection?.Socket;
        if (_bodyMirrorSenderBound && !ReferenceEquals(_bodyMirrorSocket,socket))
        {
            // Ordered TCP bytes/revisions belong to this server connection, not
            // to a world-global historical cursor or the next connection.
            Groups.Clear(); Placements.Clear(); PlacedBodyViews.Clear(); ClearPlacedBodyMirrorState();
            _placedBodyRevision = 0;
        }
        _bodyMirrorSocket = socket; _bodyMirrorSenderBound = true;
    }

    private static void EnqueuePlacedBodyHydration(PlacementGroup group)
    {
        if (group.PlacedBody is null || group.DefinitionJson.Length != 0
            || BodyHydrationNodes.ContainsKey(group.GroupId) || BodyHydrationNodes.Count >= MaxGroups) return;
        BodyHydrationNodes.Add(group.GroupId,BodyHydrationQueue.AddLast(group.GroupId));
    }

    private static void RemovePlacedBodyHydration(string id)
    {
        if (BodyHydrationNodes.Remove(id,out LinkedListNode<string>? node)) BodyHydrationQueue.Remove(node);
    }

    private static bool TryPlacedBodyIdentity(PlacementGroup group, out string identity)
    {
        identity = "";
        if (group.PlacedBody is null || !group.PlacedBody.ContainsKey("definitionHash")
            || group.PlacedBody["definitionHash"] is not string value || value.Length != 64 || !value.All(Uri.IsHexDigit)) return false;
        identity = value; return true;
    }

    private static TagCompound? MirrorPlacedBodyWitness(PlacementGroup group)
        => group.RawPlacedBodyEnvelope is not null ? new TagCompound {
            ["failure"] = "placed_witness_not_compound", ["rawWitnessEnvelope"] = group.RawPlacedBodyEnvelope.Clone(),
        } : group.PlacedBody;

    private static byte[]? EncodeMirrorPlacedBodyWitness(PlacementGroup group)
    {
        TagCompound? body = MirrorPlacedBodyWitness(group);
        if (body is null) return null;
        string failure = "placed_witness_encode_error";
        try
        {
            using var encoded = new MemoryStream(); TagIO.ToStream(body,encoded,compress: true);
            if (encoded.Length <= MaxPlacedBodyWitnessBytes) return encoded.ToArray();
            failure = "placed_witness_size";
        }
        catch { }
        // Preserve the complete raw witness in authoritative NBT, but do not let
        // optional cosmetic serialization prevent a compact material snapshot.
        var diagnostic = new TagCompound { ["failure"] = failure };
        foreach (string key in new[] { "version", "bindingId", "definitionHash", "tileType", "nativeStyle" })
            if (body.ContainsKey(key) && (body[key] is int || body[key] is string text && text.Length <= 96))
                diagnostic[key] = body[key];
        using var fallback = new MemoryStream(); TagIO.ToStream(diagnostic,fallback,compress: true);
        return fallback.ToArray();
    }

    private static void WriteMirrorGroup(BinaryWriter writer, PlacementGroup group)
    {
        byte[]? witness = EncodeMirrorPlacedBodyWitness(group);
        writer.Write(group.GroupId); writer.Write(group.GeneratedItemId);
        writer.Write(group.Cells.Count);
        foreach (GeneratedPlacementKey cell in group.Cells)
        { writer.Write((byte)cell.Layer); writer.Write(cell.X); writer.Write(cell.Y); }
        writer.Write(witness is not null);
        if (witness is null) return;
        writer.Write(witness.Length); writer.Write(witness);
        // Definitions/PNG stay on the existing bounded/chunked registry/asset transport.
        // Never replicate the full definition once per placed cell/group here.
    }

    private static PlacementGroup ReadMirrorGroup(BinaryReader reader)
    {
        string id = reader.ReadString(), generatedId = reader.ReadString();
        int count = reader.ReadInt32();
        if (id.Length != 32 || !id.All(Uri.IsHexDigit) || generatedId.Length is < 1 or > 96
            || count is < 1 or > MaxCellsPerGroup) throw new InvalidDataException("placed group envelope");
        var cells = new List<GeneratedPlacementKey>(count);
        for (int i = 0; i < count; i++)
        {
            var layer = (GeneratedPlacementLayer)reader.ReadByte();
            int x = reader.ReadInt32(), y = reader.ReadInt32();
            var cell = new GeneratedPlacementKey(layer,x,y);
            if (!Enum.IsDefined(layer) || !WorldGen.InWorld(x,y,1) || cells.Contains(cell))
                throw new InvalidDataException("placed group cell");
            cells.Add(cell);
        }
        TagCompound? body = null, rawEnvelope = null;
        if (reader.ReadBoolean())
        {
            int bytes = reader.ReadInt32();
            if (bytes is < 1 or > MaxPlacedBodyWitnessBytes) throw new InvalidDataException("placed witness envelope");
            byte[] data = reader.ReadBytes(bytes);
            if (data.Length != bytes) throw new EndOfStreamException();
            try
            {
                using var input = new MemoryStream(data, writable: false);
                body = TagIO.FromStream(input, compressed: true);
                if (body.ContainsKey("failure") && body["failure"] is string text && text == "placed_witness_not_compound"
                    && body.ContainsKey("rawWitnessEnvelope") && body["rawWitnessEnvelope"] is TagCompound envelope && envelope.ContainsKey("placedBody"))
                { rawEnvelope = (TagCompound)envelope.Clone(); body = null; }
            }
            catch
            {
                // Only the fully framed cosmetic payload failed. Keep the healthy
                // material envelope plus literal compressed bytes for diagnostics.
                body = new TagCompound { ["failure"] = "placed_witness_decode_error", ["rawWitnessBytes"] = data };
            }
        }
        return new PlacementGroup { GroupId = id, GeneratedItemId = generatedId, Cells = cells,
            PlacedBody = body, RawPlacedBodyEnvelope = rawEnvelope };
    }

    private static bool RestorePlacedBodyDefinition(PlacementGroup group, bool publish)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient || !TryPlacedBodyIdentity(group,out string identity)) return false;
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null) return false;
        try
        {
            GeneratedItemData? data = GeneratedItemData.FromJson(group.DefinitionJson);
            if (data is null || data.Id != group.GeneratedItemId || !IsMaterialPlacementDefinition(data)
                || !GeneratedItemRegistryService.IsCurrentWorldData(data)
                || GeneratedItemRegistryService.DefinitionIdentity(data) != identity) return false;
            string bindingId = group.PlacedBody!.GetString("bindingId");
            RuntimeBindingSpec? binding = data.RuntimeProgram.Bindings.SingleOrDefault(b => b.Id == bindingId);
            RuntimePlacementSpec? placement = binding?.UsePolicy.Action.Placement;
            if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem || binding.UsePolicy.StackCost != 1
                || placement?.PlacedBody is null || group.Cells.Any(c => c.Layer != GeneratedPlacementLayer.Tile)
                || placement.TileId != group.PlacedBody.GetInt("tileType")
                || placement.PlaceStyle != group.PlacedBody.GetInt("nativeStyle")) return false;
            if (registry.TryGet(group.GeneratedItemId,out GeneratedItemData existing)
                && GeneratedItemRegistryService.DefinitionIdentity(existing) != identity)
            {
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn(
                    $"[GeneratedPlacementLedger] placed definition registry conflict: item='{group.GeneratedItemId}' group='{group.GroupId}'");
                return false;
            }
            // No unchecked PublishGeneratedItem/RegisterLocal call may replace an
            // existing same-ID definition. The registry remains the hash/transport owner.
            if (publish && Main.netMode == NetmodeID.Server) registry.PublishGeneratedItem(data);
            else registry.RegisterLocal(data,persist: false,ensureAssets: false);
            return true;
        }
        catch { return false; } // Optional presentation must not lose a material claim.
    }

    private static void RestorePlacedBodyDefinitions(bool publish)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient) return;
        var restored = new HashSet<string>(StringComparer.Ordinal);
        foreach (PlacementGroup group in Groups.Values)
            if (!restored.Contains(group.GeneratedItemId) && RestorePlacedBodyDefinition(group,publish))
                restored.Add(group.GeneratedItemId);
    }

    private static void PublishPlacedBodyGroupChange(PlacementGroup group, bool removed)
    {
        if (Main.netMode == NetmodeID.MultiplayerClient) return;
        _placedBodyRevision = checked(_placedBodyRevision + 1);
        if (Main.netMode != NetmodeID.Server) return;
        if (!removed) RestorePlacedBodyDefinition(group,publish: true);
        try
        {
            var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
            if (packet is null) return;
            packet.Write(Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
            packet.Write(PayloadVersion); packet.Write(_placedBodyRevision); packet.Write(removed);
            if (removed) packet.Write(group.GroupId);
            else WriteMirrorGroup(packet, group);
            packet.Send();
        }
        catch
        {
            // Socket/cosmetic serialization failures do not undo the committed
            // material owner/receipt. A later initial snapshot restores the mirror.
        }
    }

    internal static void HandlePlacedBodyLedgerPacket(BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || whoAmI != 256) return;
        int version = reader.ReadInt32(); ulong revision = reader.ReadUInt64(); bool removed = reader.ReadBoolean();
        if (version != PayloadVersion) return;
        PlacementGroup? group = removed ? null : ReadMirrorGroup(reader);
        string id = removed ? reader.ReadString() : group!.GroupId;
        if (id.Length != 32 || !id.All(Uri.IsHexDigit)) return;
        EnsurePlacedBodyMirrorSender();
        if (revision == 0 || revision <= _placedBodyRevision) return;
        Groups.TryGetValue(id,out PlacementGroup? previous);
        if (group is not null && (Groups.Count >= MaxGroups && previous is null
            || (long)Placements.Count - (previous?.Cells.Count ?? 0) + group.Cells.Count > MaxCells
            || group.Cells.Any(cell => Placements.TryGetValue(cell,out string? occupied) && occupied != id))) return;
        // A placing client's Ready-fenced provisional group already owns an exact
        // hydrated definition. Keep those bytes only for the same authoritative
        // group/generated identity/hash; never match an unrelated overlap by cell/type.
        if (group is not null && previous is not null && previous.DefinitionJson.Length != 0
            && group.GeneratedItemId == previous.GeneratedItemId
            && TryPlacedBodyIdentity(group, out string identity)
            && TryPlacedBodyIdentity(previous, out string previousIdentity) && identity == previousIdentity
            && PlacementDefinitionHash(previous.DefinitionJson) == identity)
            group.DefinitionJson = previous.DefinitionJson;
        RemovePlacedBodyHydration(id);
        if (Groups.Remove(id))
            foreach (GeneratedPlacementKey cell in previous!.Cells) Placements.Remove(cell);
        if (group is not null)
        {
            Groups[id] = group;
            foreach (GeneratedPlacementKey cell in group.Cells) Placements[cell] = id;
            EnqueuePlacedBodyHydration(group);
        }
        _placedBodyRevision = revision;
    }

    private static void RefreshPlacedBodyDefinitionMirrors()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient) return;
        EnsurePlacedBodyMirrorSender();
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null) return;
        ulong tick = Main.GameUpdateCount;
        if (_bodyHydrationTick != tick) { _bodyHydrationTick = tick; _bodyHydrationVisits = 0; }
        int visits = Math.Min(MaxBodyHydrationVisitsPerTick - _bodyHydrationVisits,BodyHydrationQueue.Count);
        for (int i = 0; i < visits; i++)
        {
            _bodyHydrationVisits++;
            string id = BodyHydrationQueue.First!.Value; RemovePlacedBodyHydration(id);
            if (!Groups.TryGetValue(id,out PlacementGroup? group) || group.DefinitionJson.Length != 0
                || !TryPlacedBodyIdentity(group,out string identity)) continue;
            try
            {
                if (registry.TryGet(group.GeneratedItemId,out GeneratedItemData definition)
                    && GeneratedItemRegistryService.DefinitionIdentity(definition) == identity)
                    group.DefinitionJson = definition.ToNetworkJson();
                else registry.RequestOneFromServer(group.GeneratedItemId,forceAssetRetry: false,forceDefinitionRefresh: true);
            }
            catch { } // A per-definition failure cannot starve the rest of the queue.
            EnqueuePlacedBodyHydration(group);
        }
    }

    public override void PostUpdateEverything()
    {
        RefreshPlacedBodyDefinitionMirrors();
        RefreshPlacedBodyViews();
    }
}
