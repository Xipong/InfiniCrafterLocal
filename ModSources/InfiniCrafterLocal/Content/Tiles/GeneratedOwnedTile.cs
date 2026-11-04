#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.Enums;
using Terraria.ModLoader;
using Terraria.ObjectData;

namespace InfiniCrafterLocal.Content.Tiles;

// Registered structure, not a generated class or a clone of a parent's tile.
// Names are stable across reloads; numeric Type is only a live engine address.
[Autoload(false)]
public sealed class GeneratedOwnedTile : ModTile
{
    private readonly RuntimeOwnedTileSpec shape;
    internal GeneratedOwnedTile(RuntimeOwnedTileSpec shape) => this.shape = shape;
    public override string Name => shape.Key;
    // tML requires a loadable texture. PreDraw always declines this registration
    // texture: the exact generated PNG is drawn once by the existing body owner.
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";

    public override void SetStaticDefaults()
    {
        Main.tileFrameImportant[Type] = true;
        Main.tileSolid[Type] = shape.Collision == "solid";
        Main.tileNoAttach[Type] = true;
        TileObjectData.newTile.CopyFrom(TileObjectData.Style1x1);
        TileObjectData.newTile.Width = shape.Width;
        TileObjectData.newTile.Height = shape.Height;
        TileObjectData.newTile.Origin = new Point16(shape.Width / 2, shape.Height - 1);
        TileObjectData.newTile.CoordinateWidth = 16;
        TileObjectData.newTile.CoordinatePadding = 2;
        TileObjectData.newTile.CoordinateHeights = Enumerable.Repeat(16, shape.Height).ToArray();
        TileObjectData.newTile.AnchorBottom = shape.Support == "floor"
            ? new AnchorData(AnchorType.SolidTile | AnchorType.SolidWithTop | AnchorType.Table, shape.Width, 0)
            : AnchorData.Empty;
        TileObjectData.newTile.AnchorTop = AnchorData.Empty;
        TileObjectData.newTile.AnchorLeft = AnchorData.Empty;
        TileObjectData.newTile.AnchorRight = AnchorData.Empty;
        TileObjectData.newTile.AnchorWall = shape.Support == "wall";
        TileObjectData.newTile.WaterDeath = false;
        TileObjectData.newTile.LavaDeath = false;
        TileObjectData.addTile(Type);
    }

    public override bool PreDraw(int i, int j, SpriteBatch spriteBatch) => false;
    public override bool Slope(int i, int j) => false; // Authored rectangle cannot become partial-cell collision.
    public override IEnumerable<Item> GetItemDrops(int i, int j) => Array.Empty<Item>();
    public override void KillMultiTile(int i, int j, int frameX, int frameY)
        => GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile, i, j);
}

internal static class GeneratedOwnedTiles
{
    private static readonly Dictionary<string, GeneratedOwnedTile> Tiles = new(StringComparer.Ordinal);
    internal static void Register(Mod mod)
    {
        Tiles.Clear();
        for (int width = 1; width <= 16; width++)
        for (int height = 1; height <= 16; height++)
        foreach (string collision in new[] { "open", "solid" })
        foreach (string support in new[] { "floor", "wall", "unanchored" })
        {
            var shape = new RuntimeOwnedTileSpec { Width = width, Height = height, Collision = collision, Support = support };
            var tile = new GeneratedOwnedTile(shape);
            mod.AddContent(tile);
            Tiles.Add(shape.Key, tile);
        }
    }
    internal static int Resolve(RuntimePlacementSpec placement)
        => placement.OwnedTile is null ? placement.TileId : Resolve(placement.OwnedTile.Key);
    internal static int Resolve(string key) => Tiles.TryGetValue(key, out var tile) ? tile.Type : -1;
    internal static void Clear() => Tiles.Clear();
}
