using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolBlinkGeometry()
    {
        WithPersistenceTilemap((_, ledger) => { WithPlayer((player, owner) => {
            var method = owner.GetType().GetMethod("IsSafeBlinkDestination", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
            bool Safe() => (bool)method.Invoke(owner, new object[] { new Microsoft.Xna.Framework.Vector2(640, 640) })!;
            bool oldSolid = Terraria.Main.tileSolid[Terraria.ID.TileID.Stone];
            try {
                player.width = 8; player.height = 8; Terraria.Main.tileSolid[Terraria.ID.TileID.Stone] = true;
                for (int x = 38; x < 44; x++) for (int y = 38; y < 44; y++) Terraria.Main.tile[x,y].ClearEverything();
                var tile = Terraria.Main.tile[40,40]; tile.HasTile = true; tile.TileType = Terraria.ID.TileID.Stone;
                Equal(false, Safe(), "solid collision refuses landing");
                tile.IsActuated = true; Equal(true, Safe(), "actuated passage is usable");
                tile.ClearEverything(); var lava = Terraria.Main.tile[41,40]; lava.LiquidType = Terraria.ID.LiquidID.Lava; lava.LiquidAmount = 255;
                Equal(true, Safe(), "adjacent lava outside body is not a collision");
                tile.LiquidType = Terraria.ID.LiquidID.Lava; tile.LiquidAmount = 255;
                Equal(false, Safe(), "overlapping lava remains unsafe");
            } finally { Terraria.Main.tileSolid[Terraria.ID.TileID.Stone] = oldSolid; }
        }); });
    }
}
