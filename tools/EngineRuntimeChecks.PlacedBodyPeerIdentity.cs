#nullable enable
using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Headless peer isolation only: exchange the production static field owners,
    // not their contents. The original client's dictionaries/groups/receipts remain
    // untouched while the server runs; no ClearWorld/LoadWorldData/snapshot on resume.
    // DynamicMethod is needed because the collection fields are static readonly.
    // All field names below already exist on the pinned baseline (no new API needed).
    private sealed class PlacedIdentityPeerState : IDisposable
    {
        private static readonly string[] Names = {
            "ClientPlacementIntents", "RetiredClientPlacementIntents", "PlacementPeerCursors", "_nextPlacementSequence",
            "Placements", "Groups", "PendingReturns", "QuarantinedReturns", "RawQuarantineEnvelopes",
            "PendingAuthorizations", "PlacementReceiptExpiryByPlayer", "_placedBodyRevision", "_bodyFootprintMaintenanceCursor",
            "PlacedBodyViews", "BodyHydrationQueue", "BodyHydrationNodes", "_bodyHydrationTick", "_bodyHydrationVisits",
            "_bodyMirrorSocket", "_bodyMirrorSenderBound", "_bodySnapshotReceived",
        };
        private readonly FieldInfo[] fields = Names.Select(name => typeof(GeneratedPlacementLedgerSystem)
            .GetField(name, PersistenceStatic) ?? throw new InvalidOperationException("missing baseline peer field: " + name)).ToArray();
        private readonly Action<object?>[] setters;
        private readonly object?[] original;
        private object?[] client, server;
        private bool onClient = true;

        internal PlacedIdentityPeerState()
        {
            setters = fields.Select(field => {
                var method = new DynamicMethod("PlacedIdentitySwap_" + field.Name, typeof(void), new[] { typeof(object) },
                    typeof(GeneratedPlacementLedgerSystem), skipVisibility: true);
                var il = method.GetILGenerator(); il.Emit(OpCodes.Ldarg_0);
                il.Emit(field.FieldType.IsValueType ? OpCodes.Unbox_Any : OpCodes.Castclass, field.FieldType);
                il.Emit(OpCodes.Stsfld, field); il.Emit(OpCodes.Ret);
                return (Action<object?>)method.CreateDelegate(typeof(Action<object?>));
            }).ToArray();
            original = Capture(); client = (object?[])original.Clone();
            server = fields.Select(field => field.IsInitOnly ? Activator.CreateInstance(field.FieldType)
                : field.FieldType.IsValueType ? Activator.CreateInstance(field.FieldType) : null).ToArray();
        }
        private object?[] Capture() => fields.Select(field => field.GetValue(null)).ToArray();
        private void Install(object?[] values) { for (int i = 0; i < setters.Length; i++) setters[i](values[i]); }
        internal void Client() => Switch(true);
        internal void Server() => Switch(false);
        private void Switch(bool toClient)
        {
            if (onClient == toClient) return;
            if (onClient) client = Capture(); else server = Capture();
            Install(toClient ? client : server); onClient = toClient;
        }
        public void Dispose() => Install(original);
    }

    private static IDictionary PlacedIdentityMap(string field)
        => (IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField(field, PersistenceStatic)!.GetValue(null)!;
    private static ulong PlacedIdentityRevision()
        => (ulong)typeof(GeneratedPlacementLedgerSystem).GetField("_placedBodyRevision", PersistenceStatic)!.GetValue(null)!;
    private static int PlacedIdentityProtocol()
        => (int)typeof(GeneratedPlacementLedgerSystem).GetField("PlacementProtocolVersion", PersistenceStatic)!.GetRawConstantValue()!;
    private static bool PlacedIdentitySuppresses()
        => (bool)typeof(GeneratedPlacementLedgerSystem).GetMethod("ShouldSuppressPlacedBody", PersistenceStatic)!
            .Invoke(null, new object[] { 40, 40 })!;
    private static int PlacedIdentityProjectionCount()
        => ((IEnumerable)typeof(GeneratedPlacementLedgerSystem).GetMethod("VisiblePlacedBodies", PersistenceStatic)!
            .Invoke(null, null)!).Cast<object>().Count();

    // Register this method and this Compile item in the parent-owned runner/project.
    // Baseline compilable: uses existing consumers/helpers, no reference to the fix's new fields.
    private static void PlacingClientRetainsExactServerIdentityThroughCommitAndRemoval()
    {
        PersistenceMatrix(new[] { "selected_tile", "legacy_tile", "legacy_wall" }.Select(scenario =>
            ("placing client real peer identity: " + scenario, (Action)(() => WithPlacedLedger((player, ledger) => {
                using var peers = new ReviewPeers(); using var states = new PlacedIdentityPeerState();
                int x = Player.tileTargetX, y = Player.tileTargetY;
                try {
                    MaterialClock(100); Player.tileTargetX = Player.tileTargetY = 40;
                    var data = scenario == "selected_tile" ? PlacedLedgerData("pb01-selected") : PersistencePlacementData("pb01-" + scenario);
                    var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                    bool tilePlacement = scenario != "legacy_wall";
                    if (scenario == "legacy_tile") { placement.TileId = TileID.Stone; placement.WallId = -1; }
                    peers.Register(data);
                    var serverData = GeneratedItemData.FromJson(data.ToNetworkJson())
                        ?? throw new InvalidOperationException("strict independent server definition invalid");
                    var client = new Player { whoAmI = 0, active = true, position = player.position };
                    var server = new Player { whoAmI = 0, active = true, position = player.position };
                    var generated = ReviewItem(data); client.inventory[0] = generated.Item; server.inventory[0] = ReviewItem(serverData).Item;
                    var cell = Terraria.Main.tile[40,40]; cell.HasTile = false; cell.WallType = 0;
                    peers.Mode(NetmodeID.MultiplayerClient,0); Terraria.Main.player[0] = client;
                    Equal(false, generated.CanUseItem(client), "original client waits for actual server Ready");
                    byte[] intent = peers.Sent.Single(); peers.Sent.Clear();
                    states.Server(); peers.Mode(NetmodeID.Server,255); Terraria.Main.player[0] = server;
                    peers.Receive(intent,0);
                    Equal(1, PlacedIdentityMap("PendingAuthorizations").Count, "server captures genuine native before-state");
                    byte[] ready = peers.Sent.Single(); peers.Sent.Clear();
                    string readyId;
                    using (var payload = new BinaryReader(new MemoryStream(ready))) {
                        Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedPlacementIntentReady,payload.ReadByte(),"actual Ready route");
                        Equal(PlacedIdentityProtocol(),payload.ReadInt32(),"Ready uses explicit placement protocol");
                        payload.ReadUInt64(); Equal(true,payload.ReadBoolean(),"actual server accepts exact intent");
                        payload.ReadString(); readyId = payload.BaseStream.Position < payload.BaseStream.Length ? payload.ReadString() : "";
                        Equal(payload.BaseStream.Length,payload.BaseStream.Position,"complete actual Ready frame consumed");
                    }
                    states.Client(); peers.Mode(NetmodeID.MultiplayerClient,0); Terraria.Main.player[0] = client; peers.Receive(ready);
                    Equal(true, generated.CanUseItem(client), "real activation consumer admits exact Ready");
                    Equal(false, ItemLoader.ConsumeItem(generated.Item,client), "no changed native cell cannot spend");
                    if (tilePlacement) { cell.HasTile = true; cell.TileType = TileID.Stone; cell.TileFrameX = cell.TileFrameY = 0; }
                    else cell.WallType = 1;
                    // UseItem can commit first; Consume must still observe its real one-shot receipt.
                    generated.UseItem(client);
                    Equal(true, ItemLoader.ConsumeItem(generated.Item,client), "original local native receipt spends once");
                    Equal(false, ItemLoader.ConsumeItem(generated.Item,client), "local spend receipt never duplicates");
                    byte[] notify = peers.Sent.Single(); peers.Sent.Clear();
                    using (var payload = new BinaryReader(new MemoryStream(notify))) {
                        Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.NotifyGeneratedPlacement,payload.ReadByte(),"actual Notify route");
                        Equal(PlacedIdentityProtocol(),payload.ReadInt32(),"Notify uses explicit placement protocol");
                        payload.ReadUInt64(); payload.ReadByte(); payload.ReadInt32(); payload.ReadInt32();
                        Equal(payload.BaseStream.Length,payload.BaseStream.Position,"client Notify cannot choose/replace server group GUID");
                    }
                    var clientGroups = PlacedIdentityMap("Groups"); var clientCells = PlacedIdentityMap("Placements");
                    var localRow = PlacedLedgerGroups(ledger).Single(); string localId = localRow.GetString("groupId");
                    object localGroup = clientGroups[localId]!;
                    Equal(scenario == "selected_tile", localRow.ContainsKey("placedBody"), "historical absent-body bindings never opt in");
                    Equal(scenario == "selected_tile", PlacedIdentitySuppresses(), "selected presentation survives absent PNG before authoritative echo");
                    ledger.PostUpdateEverything();
                    Equal(scenario == "selected_tile" ? 1 : 0, PlacedIdentityProjectionCount(), "local selected projection does not require root PNG");
                    states.Server(); peers.Mode(NetmodeID.Server,255); Terraria.Main.player[0] = server;
                    Equal(0, PlacedLedgerGroups(ledger).Count, "server never borrows original client material group");
                    MaterialClock(140); peers.Receive(notify,0); peers.Receive(notify,0);
                    var serverRow = PlacedLedgerGroups(ledger).Single(); string serverId = serverRow.GetString("groupId");
                    byte[] commit = peers.Sent.Single(packet => packet[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
                    peers.Sent.Clear(); ulong commitRevision = PlacedIdentityRevision();
                    Equal(true, GeneratedPlacementLedgerSystem.TryQueueReturn(tilePlacement ? GeneratedPlacementLayer.Tile : GeneratedPlacementLayer.Wall,40,40), "actual server return transition emits removal");
                    byte[] remove = peers.Sent.Single(packet => packet[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
                    ulong removeRevision = PlacedIdentityRevision(); peers.Sent.Clear();
                    Equal(1, PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,
                        "server keeps one durable exact return when native spawning is unavailable");
                    states.Client(); peers.Mode(NetmodeID.MultiplayerClient,0); Terraria.Main.player[0] = client;
                    Equal(true, ReferenceEquals(clientGroups,PlacedIdentityMap("Groups")), "resume exact original client dictionary, no clearing/reload");
                    Equal(true, ReferenceEquals(clientCells,PlacedIdentityMap("Placements")), "resume exact original client cell owner");
                    Equal(true, ReferenceEquals(localGroup,PlacedIdentityMap("Groups")[localId]), "original Consume-created group is still retained");
                    var unrelated = (Terraria.ModLoader.IO.TagCompound)serverRow.Clone();
                    unrelated["groupId"] = localId == new string('f',32) ? new string('e',32) : new string('f',32);
                    peers.Receive(PlacedLedgerLive(commitRevision,unrelated));
                    Equal(true, ReferenceEquals(localGroup,PlacedIdentityMap("Groups")[localId]), "same-coordinate/type unrelated group cannot replace original owner");
                    Equal(0UL, PlacedIdentityRevision(), "unrelated overlap refusal cannot consume server revision");
                    peers.Receive(commit); peers.Receive(commit);
                    ulong appliedCommitRevision = PlacedIdentityRevision();
                    string echoedId = PlacedLedgerGroups(ledger).Single().GetString("groupId");
                    bool echoedSelection = PlacedIdentitySuppresses();
                    ledger.PostUpdateEverything(); int echoedViews = PlacedIdentityProjectionCount();
                    peers.Receive(remove); peers.Receive(commit); peers.Receive(remove);
                    // Ordinary replacement uses the same native type/coordinates. It has no generated owner.
                    if (tilePlacement) { cell.HasTile = false; cell.HasTile = true; cell.TileType = TileID.Stone; }
                    else { cell.WallType = 0; cell.WallType = 1; }
                    ledger.PostUpdateEverything();
                    // Baseline RED is the retained original C after removal of S, not an empty-client stand-in.
                    Equal(0, PlacedLedgerGroups(ledger).Count, "PB-01 authoritative removal must retire the actual original placing-client group");
                    Equal(false, GeneratedPlacementLedgerSystem.Contains(tilePlacement ? GeneratedPlacementLayer.Tile : GeneratedPlacementLayer.Wall,40,40), "ordinary same-type replacement has no generated owner");
                    Equal(false, PlacedIdentitySuppresses(), "ordinary same-type replacement must not remain selected");
                    Equal(0, PlacedIdentityProjectionCount(), "removed original presentation cannot reappear on same-type replacement");
                    Equal(serverId, readyId, "Ready carries the exact subsequently committed server group GUID");
                    Equal(serverId, localId, "placing-client commit uses exact server-allocated group identity");
                    Equal(serverId, echoedId, "actual authoritative echo addresses original group");
                    Equal(commitRevision, appliedCommitRevision, "actual echo accepted, not refused as unrelated overlap");
                    Equal(removeRevision, PlacedIdentityRevision(), "removal advances exact ordered authoritative cursor");
                    Equal(scenario == "selected_tile", echoedSelection, "commit echo preserves selection even without PNG");
                    Equal(scenario == "selected_tile" ? 1 : 0, echoedViews, "echo retains exact hydrated presentation without a transient blank");
                    Equal(0, PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,
                        "client mirror cannot become a material return owner");
                    Equal(false, ItemLoader.ConsumeItem(generated.Item,client), "authoritative echo/removal cannot mint another local spend receipt");
                }
                finally { Player.tileTargetX = x; Player.tileTargetY = y; }
            })))));
    }

    private static byte[] PlacedIdentityRewriteReady(byte[] actual, string scenario)
    {
        using var input = new BinaryReader(new MemoryStream(actual));
        byte packet = input.ReadByte(); int version = input.ReadInt32(); ulong sequence = input.ReadUInt64();
        bool accepted = input.ReadBoolean(); string hash = accepted ? input.ReadString() : "";
        string id = accepted && input.BaseStream.Position < input.BaseStream.Length ? input.ReadString() : "";
        Equal(true, accepted, "fence mutation starts from actual accepted server Ready");
        using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream);
        writer.Write(packet); writer.Write(version); writer.Write(scenario == "old_sequence" ? 0UL : sequence); writer.Write(accepted);
        writer.Write(scenario == "wrong_hash" ? new string('0',64) : hash);
        if (version >= 5) writer.Write(scenario == "malformed_guid" ? new string('g',32)
            : scenario == "changed_guid_replay" ? (id == new string('a',32) ? new string('b',32) : new string('a',32)) : id);
        return stream.ToArray();
    }

    private static void PlacementReadyGroupIdentityRemainsServerOwnedAndFenced()
    {
        WithPlacedLedger((player, ledger) => {
            int x = Player.tileTargetX, y = Player.tileTargetY;
            try {
                PersistenceMatrix(new[] { "valid_replay", "foreign_sender", "malformed_guid", "old_sequence", "wrong_hash", "changed_guid_replay", "expired", "selector_changed" }
                    .Select(scenario => ("Ready group identity fence: " + scenario, (Action)(() => {
                        ledger.ClearWorld(); MaterialClock(100); using var peers = new ReviewPeers(); using var states = new PlacedIdentityPeerState();
                        var data = PlacedLedgerData("pb01-ready-fence"); peers.Register(data);
                        var client = new Player { whoAmI = 0, active = true, position = player.position };
                        var server = new Player { whoAmI = 0, active = true, position = player.position };
                        var generated = ReviewItem(data); client.inventory[0] = generated.Item;
                        server.inventory[0] = ReviewItem(GeneratedItemData.FromJson(data.ToNetworkJson())!).Item;
                        Player.tileTargetX = Player.tileTargetY = 40; var readyCell = Terraria.Main.tile[40,40]; readyCell.HasTile = false;
                        peers.Mode(NetmodeID.MultiplayerClient,0); Terraria.Main.player[0] = client;
                        Equal(false, generated.CanUseItem(client), "real native activation awaits authority");
                        byte[] intent = peers.Sent.Single(); peers.Sent.Clear();
                        using (var payload = new BinaryReader(new MemoryStream(intent))) {
                            Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.RequestGeneratedPlacementIntent,payload.ReadByte(),"actual intent route");
                            Equal(PlacedIdentityProtocol(),payload.ReadInt32(),"explicit current placement protocol");
                            payload.ReadUInt64(); payload.ReadByte(); payload.ReadInt32(); payload.ReadInt32(); payload.ReadUInt64();
                            Equal(payload.BaseStream.Length,payload.BaseStream.Position,"client intent carries no selectable group GUID");
                        }
                        states.Server(); peers.Mode(NetmodeID.Server,255); Terraria.Main.player[0] = server; peers.Receive(intent,0);
                        byte[] ready = peers.Sent.Single(); peers.Sent.Clear();
                        states.Client(); peers.Mode(NetmodeID.MultiplayerClient,0); Terraria.Main.player[0] = client;
                        if (scenario is "valid_replay" or "changed_guid_replay") peers.Receive(ready);
                        if (scenario == "expired") MaterialClock(221);
                        peers.Receive(PlacedIdentityRewriteReady(ready,scenario),scenario == "foreign_sender" ? 0 : 256);
                        if (scenario == "selector_changed") Player.tileTargetX = 41;
                        Equal(scenario == "valid_replay",generated.CanUseItem(client),"only exact server identity/replay with unchanged activation is admitted");
                        Equal(false,Terraria.Main.tile[40,40].HasTile,"refusal/Ready alone never mutates native material");
                        Equal(1,generated.Item.stack,"Ready fence never spends a native stack");
                        Equal(false,ItemLoader.ConsumeItem(generated.Item,client),"unchanged before-state never produces spend receipt");
                        Equal(0,PlacedLedgerGroups(ledger).Count,"Ready/rejection cannot create provisional material group");
                    }))));
            }
            finally { Player.tileTargetX = x; Player.tileTargetY = y; }
        });
    }
}
