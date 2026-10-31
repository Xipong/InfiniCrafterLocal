#nullable enable
using Microsoft.Xna.Framework;
using ResonanceLattice.Core;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ObjectData;

namespace ResonanceLattice.Content.Tiles;

/// <summary>
/// The conductor node of the lattice. Placeable via <see cref="Items.ResonantConduitItem"/>;
/// placement/removal hooks feed the lattice registry, and the tile emits light proportional
/// to its node's charge, so a charged network visibly glows in the world.
/// </summary>
public sealed class ResonantCrystalTile : ModTile
{
    public override void SetStaticDefaults()
    {
        Main.tileLighted[Type] = true;
        Main.tileFrameImportant[Type] = true;
        Main.tileSolid[Type] = false;
        Main.tileNoAttach[Type] = true;
        TileID.Sets.DisableSmartCursor[Type] = true;
        TileID.Sets.InteractibleByNPCs[Type] = false;

        DustType = DustID.Enchanted_Pink;
        MinPick = 30;

        RegisterItemDrop(ModContent.ItemType<Items.ResonantConduitItem>());

        TileObjectData.newTile.CopyFrom(TileObjectData.Style1x1);
        TileObjectData.newTile.StyleHorizontal = true;
        TileObjectData.addTile(Type);

        AddMapEntry(new Color(120, 220, 255), this.GetLocalization("MapEntry"));
    }

    public override void PlaceInWorld(int i, int j, Item item)
    {
        // Fires on the machine that placed the tile (player action). The server discovers
        // remotely placed nodes through its periodic bounded scan instead.
        Tile tile = Framing.GetTileSafely(i, j);
        if (tile.HasTile && tile.TileType == Type)
            ResonanceLattice.NotifyNodePlaced(new Point16(i, j));
    }

    public override void KillTile(int i, int j, ref bool fail, ref bool effectOnly, ref bool noItem)
    {
        if (!fail && !effectOnly)
            ResonanceLattice.NotifyNodeRemoved(new Point16(i, j));
    }

    public override void ModifyLight(int i, int j, ref float r, ref float g, ref float b)
    {
        LatticeNetwork? network = ResonanceLattice.NetworkAtTile(new Point16(i, j));
        if (network is null || !LatticeWorldSystem.Nodes.TryGetValue(new Point16(i, j), out LatticeNode? node))
            return;
        float fraction = MathHelper.Clamp(node.Charge / LatticeLimits.NodeCapacity, 0f, 1f);
        if (fraction <= 0.01f)
            return;
        // Cyan-white glow that brightens with charge; surging networks flash warm.
        if (network.IsSurging)
        {
            r = 1f * fraction; g = 0.55f * fraction; b = 0.35f * fraction;
        }
        else
        {
            r = 0.35f * fraction; g = 0.85f * fraction; b = 1f * fraction;
        }
    }
}
