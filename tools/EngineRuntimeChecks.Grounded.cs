using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Real Collision methods over private TileData, not a world/update loop.
    private static void GroundedConditionRequiresNativeSupport()
    {
        WithPersistenceTilemap((player, ledger) =>
        {
            bool[] oldSolid = Terraria.Main.tileSolid, oldTop = Terraria.Main.tileSolidTop;
            bool oldUp = Collision.up, oldDown = Collision.down, oldStair = Collision.stair,
                oldFall = Collision.stairFall, oldSloping = Collision.sloping;
            try
            {
                Terraria.Main.tileSolid = (bool[])oldSolid.Clone();
                Terraria.Main.tileSolidTop = (bool[])oldTop.Clone();
                Terraria.Main.tileSolid[TileID.Stone] = true;
                Terraria.Main.tileSolidTop[TileID.Stone] = false;
                Terraria.Main.tileSolid[TileID.Platforms] = true;
                Terraria.Main.tileSolidTop[TileID.Platforms] = true;
                var gameplay = new GameplaySpec { UseConditionMode = "grounded" };
                player.width = 8; player.height = 32; player.velocity = Vector2.Zero;
                player.gravDir = 1f; player.position = new Vector2(644, 608);
                for (int x = 38; x <= 42; x++)
                    for (int y = 36; y <= 43; y++) Terraria.Main.tile[x, y].ClearEverything();
                Equal(false, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0,
                    "zero vertical speed in empty air is not support");
                var tile = Terraria.Main.tile[40, 40];
                tile.HasTile = true; tile.TileType = TileID.Stone;
                Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "solid floor supports normal gravity");
                tile.IsActuated = true;
                Equal(false, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "actuated floor is absent");
                tile.IsActuated = false;
                player.position.Y -= 2;
                Equal(false, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "nearby floor is not contact");
                player.position.Y += 2; player.velocity.Y = -1;
                Equal(false, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "departing jump is not grounded");
                player.velocity = Vector2.Zero;
                tile.TileType = TileID.Platforms; tile.TileFrameY = 0;
                Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "native top platform supports standing player");
                tile.TileFrameY = 18;
                Equal(Vector2.Zero, Collision.TileCollision(player.position, Vector2.UnitY, player.width, player.height),
                    "native solid platform remains a surface at this frame");
                Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "support follows native solid-platform frame behavior");
                tile.TileType = TileID.Stone; tile.TileFrameY = 0; tile.IsHalfBlock = true;
                player.position.Y = 616;
                Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "native half block surface supports player");
                tile.IsHalfBlock = false;
                foreach (SlopeType slope in new[] { SlopeType.SlopeDownRight, SlopeType.SlopeDownLeft })
                {
                    tile.Slope = slope; player.position.Y = 612;
                    // Native sloping resolves this exact narrow-player contact at y=612.
                    Vector4 native = Collision.SlopeCollision(player.position + Vector2.UnitY, Vector2.UnitY, player.width, player.height);
                    Equal(player.position.Y, native.Y, "fixture is exact native floor-slope contact");
                    Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "native floor slope supports player");
                }
                tile.Slope = SlopeType.Solid;
                player.gravDir = -1; player.position.Y = 656;
                Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "solid ceiling supports inverted gravity");
                tile.TileType = TileID.Platforms;
                Equal(false, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "one-way platform underside cannot support inverted player");
                tile.TileType = TileID.Stone;
                foreach (SlopeType slope in new[] { SlopeType.SlopeUpRight, SlopeType.SlopeUpLeft })
                {
                    tile.Slope = slope; player.position.Y = 652;
                    Vector4 native = Collision.SlopeCollision(player.position - Vector2.UnitY, -Vector2.UnitY, player.width, player.height);
                    Equal(player.position.Y, native.Y, "fixture is exact native ceiling-slope contact");
                    Equal(true, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "native ceiling slope supports inverted player");
                }
                tile.ClearEverything();
                player.position = new Vector2(648, 608); player.gravDir = 1;
                var wall = Terraria.Main.tile[41, 38]; wall.HasTile = true; wall.TileType = TileID.Stone;
                Equal(false, GeneratedItem.UseBlockedReason(player, gameplay).Length == 0, "adjacent wall is not ground");
                gameplay.UseConditionMode = "not_wet"; player.wet = false;
                Equal("", GeneratedItem.UseBlockedReason(player, gameplay), "non-grounded condition remains independent of map support");
                player.wet = true;
                Equal("Cannot be used while wet", GeneratedItem.UseBlockedReason(player, gameplay), "wet condition unchanged");
                gameplay.UseConditionMode = "grounded";
                Collision.up = true; Collision.down = false; Collision.stair = true;
                Collision.stairFall = true; Collision.sloping = true;
                Vector2 beforePosition = player.position, beforeVelocity = player.velocity;
                _ = GeneratedItem.UseBlockedReason(player, gameplay);
                Equal(beforePosition, player.position, "support query does not move player");
                Equal(beforeVelocity, player.velocity, "support query does not change velocity");
                Equal(true, Collision.up, "query preserves native up flag");
                Equal(false, Collision.down, "query preserves native down flag");
                Equal(true, Collision.stair, "query preserves native stair flag");
                Equal(true, Collision.stairFall, "query preserves native fall flag");
                Equal(true, Collision.sloping, "query preserves native sloping flag");
            }
            finally
            {
                Terraria.Main.tileSolid = oldSolid; Terraria.Main.tileSolidTop = oldTop;
                Collision.up = oldUp; Collision.down = oldDown; Collision.stair = oldStair;
                Collision.stairFall = oldFall; Collision.sloping = oldSloping;
            }
        });
    }
}
