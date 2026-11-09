using System;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void SafeBlinkUsesNativeBodyCollision()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPersistenceTilemap((_, __) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            bool oldSolid = Terraria.Main.tileSolid[TileID.Stone];
            bool oldTop = Terraria.Main.tileSolidTop[TileID.Stone];
            var failures = new System.Collections.Generic.List<string>();
            try {
                Terraria.Main.tileSolid[TileID.Stone] = true;
                Terraria.Main.tileSolidTop[TileID.Stone] = false;
                foreach (string shape in new[] { "empty", "solid", "actuated", "half-above", "half-inside", "lava-adjacent", "lava-inside" })
                foreach (bool safe in new[] { true, false }) {
                    try {
                        for (int x = 36; x <= 44; x++) for (int y = 35; y <= 44; y++) Terraria.Main.tile[x,y].ClearEverything();
                        Vector2 destination = new(640, shape.StartsWith("half-", StringComparison.Ordinal) ? 602 : 600);
                        if (shape is "solid" or "actuated" or "half-above" or "half-inside") {
                            var tile = Terraria.Main.tile[40, shape.StartsWith("half-", StringComparison.Ordinal) ? 40 : 38];
                            tile.HasTile = true; tile.TileType = TileID.Stone;
                            tile.IsActuated = shape == "actuated";
                            tile.IsHalfBlock = shape.StartsWith("half-", StringComparison.Ordinal);
                            if (shape == "half-inside") destination.Y = 610;
                        }
                        if (shape.StartsWith("lava-", StringComparison.Ordinal)) {
                            var tile = Terraria.Main.tile[shape == "lava-adjacent" ? 42 : 40, 38];
                            tile.LiquidAmount = byte.MaxValue; tile.LiquidType = LiquidID.Lava;
                        }
                        WithPlayer((player, generated) => {
                            PrepareMobilityConsumptionPlayer(player);
                            player.width = 20; player.height = 42; player.gravDir = 1f;
                            player.Center = destination - new Vector2(128, 0);
                            bool nativeSafe = !Collision.SolidCollision(destination, player.width, player.height)
                                && !Collision.LavaCollision(destination, player.width, player.height);
                            Equal(shape is not ("solid" or "half-inside" or "lava-inside"), nativeSafe, shape + " independent native fixture oracle");
                            bool expected = !safe || nativeSafe;
                            Terraria.Main.mouseX = Terraria.Main.mouseY = 0;
                            Terraria.Main.screenPosition = destination + new Vector2(player.width / 2, player.height);
                            Vector2 before = player.position;
                            Equal(expected, generated.TryRunGeneratedMobility(BlinkFeetSpec(safe)), shape + "/" + safe + " actual blink result");
                            Equal(expected ? destination : before, player.position, shape + " exact destination or refusal");
                            Equal(expected ? 60 : 0, generated.GeneratedMobilityCooldownTicks, shape + " cooldown only on success");
                        });
                    } catch (Exception error) { failures.Add(shape + "/" + safe + ": " + error.Message); }
                }
            } finally {
                for (int x = 36; x <= 44; x++) for (int y = 35; y <= 44; y++) Terraria.Main.tile[x,y].ClearEverything();
                Terraria.Main.tileSolid[TileID.Stone] = oldSolid;
                Terraria.Main.tileSolidTop[TileID.Stone] = oldTop;
            }
            if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        });
    }
}
