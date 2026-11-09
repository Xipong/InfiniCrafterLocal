using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;
using Terraria.ObjectData;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData BarePlacementData(string id, int tileType = TileID.Stone)
    {
        var data = PersistencePlacementData(id);
        var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
        placement.TileId = tileType; placement.WallId = -1;
        Equal(false, placement.HasPlacedFootprint, "bare native placement has no presentation capability");
        return data;
    }

    private static void BarePlacementPacket(int player, bool intent, int x, ulong sequence = 1)
    {
        using var reader = new BinaryReader(new MemoryStream(PlacementPacket(intent, sequence, x, 40, layer: 1)));
        if (intent) GeneratedPlacementLedgerSystem.HandlePlacementIntentPacket(reader, player);
        else GeneratedPlacementLedgerSystem.HandlePlacementPacket(reader, player);
    }

    private static void BarePlacementCannotClaimAdjacentOrdinaryTile()
    {
        foreach (bool targetChanged in new[] { false, true })
        WithPlacedLedger((player, ledger) => {
            MaterialClock(100);
            var data = BarePlacementData("bare-ordinary-neighbor"); player.inventory[0] = ReviewItem(data).Item;
            var target = Terraria.Main.tile[40,40]; var neighbor = Terraria.Main.tile[41,40];
            target.ClearEverything(); neighbor.ClearEverything();
            BarePlacementPacket(0, true, 40);
            Equal(1, PlacedIdentityMap("PendingAuthorizations").Count, "server captures intent before either native mutation");
            neighbor.HasTile = true; neighbor.TileType = TileID.Stone;
            if (targetChanged) { target.HasTile = true; target.TileType = TileID.Stone; }
            MaterialClock(140); BarePlacementPacket(0, false, 40);
            Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Tile,41,40), "ordinary neighbor never joins generated material claim");
            Equal(targetChanged, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Tile,40,40), "only changed exact target creates material claim");
            var rows = PlacedLedgerGroups(ledger);
            Equal(targetChanged ? 1 : 0, rows.Count, "unchanged target cannot authorize a neighbor-only return");
            if (targetChanged) Equal(1, rows.Single().GetList<TagCompound>("cells").Count, "simple native block is exactly one cell");
        });
    }

    private static void BarePlacementSeparatesConcurrentGeneratedNeighbors()
    {
        WithPlacedLedger((player, ledger) => {
            MaterialClock(100);
            var a = BarePlacementData("bare-A"); var b = BarePlacementData("bare-B");
            player.inventory[0] = ReviewItem(a).Item;
            var other = Terraria.Main.player[1] = new Player { whoAmI = 1, active = true, position = player.position };
            other.inventory[0] = ReviewItem(b).Item;
            var target = Terraria.Main.tile[40,40]; var neighbor = Terraria.Main.tile[41,40];
            target.ClearEverything(); neighbor.ClearEverything();
            BarePlacementPacket(0, true, 40);
            BarePlacementPacket(1, true, 41);
            neighbor.HasTile = true; neighbor.TileType = TileID.Stone;
            BarePlacementPacket(1, false, 41);
            Equal(1, PlacedLedgerGroups(ledger).Count, "neighbor B independently commits first");
            target.HasTile = true; target.TileType = TileID.Stone;
            MaterialClock(140); BarePlacementPacket(0, false, 40);
            BarePlacementPacket(0, false, 40); BarePlacementPacket(1, false, 41);
            var rows = PlacedLedgerGroups(ledger);
            Equal(2, rows.Count, "older authorization A does not absorb or collide with B's material");
            foreach (var row in rows) {
                var cell = row.GetList<TagCompound>("cells").Single();
                Equal(row.GetString("generatedItemId") == a.Id ? 40 : 41, cell.GetInt("x"), "each definition owns only its native cell");
            }
            // Exhaust allocation rather than pretending a successful world spawn.
            // The real durable return owner must retain exactly one claim per item.
            var oldItems = Terraria.Main.item;
            try {
                Terraria.Main.item = Array.Empty<Item>();
                foreach (int x in new[] { 40,41 }) {
                    Equal(true, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile,x,40), "first break transfers material owner");
                    Equal(false, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile,x,40), "repeat break cannot return twice");
                }
                var pending = PlacedLedgerSaved(ledger).GetList<TagCompound>("infiniGeneratedPlacementReturnsV2");
                Equal(2, pending.Count, "both exact items retained once for native return retry");
                Equal(true, pending.Select(row => row.GetString("generatedItemId")).OrderBy(id => id)
                    .SequenceEqual(new[] { a.Id,b.Id }.OrderBy(id => id)), "return identities stay distinct");
            }
            finally { Terraria.Main.item = oldItems; }
        });
    }

    private static void BarePlacementUsesExactNativeMultitile()
    {
        WithNativeChestWorld((player, ledger) => {
            const int type = TileID.WorkBenches;
            bool oldFrame = Terraria.Main.tileFrameImportant[type];
            try {
                Terraria.Main.tileFrameImportant[type] = true;
                var data = BarePlacementData("bare-native-workbench", type);
                player.inventory[0] = ReviewItem(data).Item;
                var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,41,40), "native target can be non-origin cell");
                Equal(true, TileObject.Place(new TileObject { xCoord=42,yCoord=40,type=type,style=0,alternate=0 }), "real native neighboring workbench mutation");
                Equal(true, TileObject.Place(new TileObject { xCoord=40,yCoord=40,type=type,style=0,alternate=0 }), "real native target workbench mutation");
                Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "bare multitile material commits");
                var cells = PlacedLedgerGroups(ledger).Single().GetList<TagCompound>("cells");
                Equal(2, cells.Count, "TileObjectData footprint excludes touching second object");
                Equal(true, cells.All(cell => cell.GetInt("x") is 40 or 41 && cell.GetInt("y") == 40), "all and only native object cells belong to claim");
                Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Tile,42,40), "adjacent same-type object remains independent");
            }
            finally { Terraria.Main.tileFrameImportant[type] = oldFrame; }
        });
    }
}
