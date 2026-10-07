#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ModLoader.IO;
using Terraria.ObjectData;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    private const int PlacedBodyWitnessVersion = 1;
    private static int _bodyFootprintMaintenanceCursor;

    private static void RetireMissingPlacedBodyFootprints()
    {
        PlacementGroup[] bodies = Groups.Values.Where(group => group.PlacedBody is not null).ToArray();
        if (bodies.Length == 0) { _bodyFootprintMaintenanceCursor = 0; return; }
        int visits = Math.Min(32,bodies.Length);
        for (int i = 0; i < visits; i++)
        {
            PlacementGroup group = bodies[_bodyFootprintMaintenanceCursor++ % bodies.Length];
            if (_bodyFootprintMaintenanceCursor >= bodies.Length) _bodyFootprintMaintenanceCursor = 0;
            // A missing material cell is an authority transition, not an asset/pose
            // failure. No cosmetic parse or texture error may destroy a healthy claim.
            GeneratedPlacementKey? missing = group.Cells.FirstOrDefault(cell =>
                cell.Layer == GeneratedPlacementLayer.Tile && (!WorldGen.InWorld(cell.X,cell.Y,1)
                    || !Main.tile[cell.X,cell.Y].HasTile));
            if (missing is { Layer: GeneratedPlacementLayer.Tile } cell)
                TryQueueReturn(cell.Layer,cell.X,cell.Y);
        }
    }

    private static TagCompound SavePlacementGroup(PlacementGroup group)
    {
        var row = new TagCompound
        {
            ["groupId"] = group.GroupId, ["generatedItemId"] = group.GeneratedItemId,
            ["definitionJson"] = group.DefinitionJson,
            ["cells"] = group.Cells.Select(cell => new TagCompound
            {
                ["layer"] = (int)cell.Layer, ["x"] = cell.X, ["y"] = cell.Y,
            }).ToList(),
        };
        if (group.RawPlacedBodyEnvelope is not null)
            row["placedBody"] = ((TagCompound)group.RawPlacedBodyEnvelope.Clone())["placedBody"];
        else if (group.PlacedBody is not null) row["placedBody"] = group.PlacedBody.Clone();
        return row;
    }

    private static bool SupportsPlacedBodyFootprint(RuntimePlacementSpec placement)
    {
        if (placement.TileId < 0 || placement.WallId >= 0) return false;
        TileObjectData? native = TileObjectData.GetTileData(placement.TileId, placement.PlaceStyle);
        return native is null ? !Main.tileFrameImportant[placement.TileId]
            : native.Width > 0 && native.Height > 0
                && (long)native.Width * native.Height <= MaxCellsPerGroup
                && native.CoordinateWidth > 0 && native.CoordinateFullWidth > 0
                && native.CoordinateFullHeight > 0 && native.CoordinateHeights.Length == native.Height;
    }

    // Material discovery does not call the optional pose/alternate decoder. Native
    // occupancy, exact top-left and before-state alone decide which cells we own.
    private static bool TryResolveMaterialFootprint(int x, int y, int expectedType, int expectedStyle,
        out int originX, out int originY, out int width, out int height)
    {
        originX = originY = width = height = 0;
        if (!WorldGen.InWorld(x, y, 1)) return false;
        Tile tile = Main.tile[x,y];
        if (!tile.HasTile || tile.TileType != expectedType) return false;
        TileObjectData? data = TileObjectData.GetTileData(tile);
        if (data is null)
        {
            if (Main.tileFrameImportant[expectedType]) return false;
            originX = x; originY = y; width = height = 1;
            return true;
        }
        if (TileObjectData.GetTileStyle(tile) != expectedStyle || data.Width < 1 || data.Height < 1
            || (long)data.Width * data.Height > MaxCellsPerGroup
            || data.CoordinateFullWidth <= 0 || data.CoordinateFullHeight <= 0
            || data.CoordinateHeights.Length != data.Height) return false;
        int stride = data.CoordinateWidth + data.CoordinatePadding;
        if (stride < 1 || tile.TileFrameX < 0 || tile.TileFrameY < 0) return false;
        int localX = tile.TileFrameX % data.CoordinateFullWidth;
        if (localX % stride != 0 || localX / stride >= data.Width) return false;
        int localY = tile.TileFrameY % data.CoordinateFullHeight, row = 0;
        while (row < data.Height && localY > 0)
        {
            int rowStride = data.CoordinateHeights[row] + data.CoordinatePadding;
            if (rowStride <= 0) return false;
            localY -= rowStride; row++;
        }
        if (localY != 0 || row >= data.Height) return false;
        var topLeft = TileObjectData.TopLeft(x,y);
        originX = topLeft.X; originY = topLeft.Y; width = data.Width; height = data.Height;
        return WorldGen.InWorld(originX, originY, 1)
            && WorldGen.InWorld(originX + width - 1, originY + height - 1, 1);
    }

    private static bool TryResolveNativeFootprint(int x, int y, int expectedType, int expectedStyle,
        out int originX, out int originY, out int width, out int height, out int alternate)
    {
        alternate = -1;
        if (!TryResolveMaterialFootprint(x,y,expectedType,expectedStyle,
            out originX,out originY,out width,out height)) return false;
        Tile tile = Main.tile[x,y];
        if (TileObjectData.GetTileData(tile) is null) { alternate = 0; return true; }
        int style = -1;
        // This out is a packed style remainder, NOT an alternate registration
        // ordinal. GetTileData(actual tile), never GetTileData(type,style,out), owns geometry.
        TileObjectData.GetTileInfo(tile, ref style, ref alternate);
        return style == expectedStyle && alternate >= 0;
    }

    private static List<GeneratedPlacementKey> FindExactPlacedBodyCells(PlacementAuthorization authorization)
    {
        RuntimePlacementSpec? placement = authorization.ExactPlacement;
        if (placement?.PlacedBody is null || authorization.Layer != GeneratedPlacementLayer.Tile)
            return new();
        if (!TryResolveMaterialFootprint(authorization.TargetX, authorization.TargetY,
            authorization.ExpectedType, placement.PlaceStyle, out int x, out int y,
            out int width, out int height)) return new();
        TileObjectData? materialData = TileObjectData.GetTileData(Main.tile[authorization.TargetX,authorization.TargetY]);
        var result = new List<GeneratedPlacementKey>(width * height);
        for (int i = x; i < x + width; i++)
            for (int j = y; j < y + height; j++)
            {
                if (authorization.BeforeExpectedTiles.Contains(Pack(i,j))
                    || !TryResolveMaterialFootprint(i,j,authorization.ExpectedType,placement.PlaceStyle,
                        out int ox,out int oy,out int w,out int h)
                    || ox != x || oy != y || w != width || h != height
                    || !ReferenceEquals(materialData,TileObjectData.GetTileData(Main.tile[i,j])))
                    return new();
                result.Add(new(GeneratedPlacementLayer.Tile,i,j));
            }
        return result;
    }

    private static TagCompound? CapturePlacedBodyWitness(PlacementAuthorization authorization, List<GeneratedPlacementKey> cells)
    {
        if (authorization.ExactPlacement?.PlacedBody is null) return null;
        // The authored selection is retained even if a cosmetic pose cannot be
        // decoded after native success. Material accounting has already succeeded.
        var witness = new TagCompound
        {
            ["version"] = PlacedBodyWitnessVersion,
            ["bindingId"] = authorization.PlacementBindingId,
            ["definitionHash"] = authorization.DefinitionHash,
            ["tileType"] = authorization.ExpectedType,
            ["nativeStyle"] = authorization.ExactPlacement.PlaceStyle,
        };
        try
        {
            if (!TryResolveNativeFootprint(authorization.TargetX, authorization.TargetY,
                authorization.ExpectedType,authorization.ExactPlacement.PlaceStyle,
                out int x,out int y,out int width,out int height,out int alternate)
                || cells.Count != width * height)
            { witness["failure"] = "native_footprint_unresolved"; return witness; }
            witness["originX"] = x; witness["originY"] = y;
            witness["width"] = width; witness["height"] = height;
            witness["nativeAlternate"] = alternate;
            witness["nativeFrames"] = cells.Select(cell => new TagCompound
            {
                ["x"] = cell.X, ["y"] = cell.Y,
                ["frameX"] = (int)Main.tile[cell.X,cell.Y].TileFrameX,
                ["frameY"] = (int)Main.tile[cell.X,cell.Y].TileFrameY,
            }).ToList();
        }
        catch { witness["failure"] = "native_footprint_decode_error"; }
        return witness;
    }
}
