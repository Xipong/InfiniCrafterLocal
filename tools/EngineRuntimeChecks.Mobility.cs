using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.Utilities;

internal static partial class EngineRuntimeChecks
{
    private static void BlinkAuthoredRangeReachesTeleport()
    {
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        int oldMouseX = Terraria.Main.mouseX, oldMouseY = Terraria.Main.mouseY;
        var oldScreen = Terraria.Main.screenPosition;
        var oldProjectiles = Terraria.Main.projectile;
        var oldDust = Terraria.Main.dust;
        var oldPlayer = Terraria.Main.player[0];
        var oldRandom = Terraria.Main.rand;
        var lastPositionField = typeof(PressurePlateHelper).GetField("PlayerLastPosition", BindingFlags.Static | BindingFlags.NonPublic)!;
        var oldLastPositions = lastPositionField.GetValue(null);
        var failures = new List<string>();
        try
        {
            // Isolated CPU state for the REAL Player.Teleport, not a mock teleport.
            // SP authority permits the test player; a different myPlayer skips camera/biome rendering.
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = 0;
            Terraria.Main.player[0] = new Player();
            Terraria.Main.mouseX = Terraria.Main.mouseY = 0;
            Terraria.Main.projectile = new Projectile[1001];
            for (int i = 0; i < Terraria.Main.projectile.Length; i++) Terraria.Main.projectile[i] = new Projectile();
            Terraria.Main.dust = new Dust[6001];
            for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust();
            Terraria.Main.rand = new UnifiedRandom(7);
            var lastPositions = new Vector2[255];
            lastPositionField.SetValue(null, lastPositions);
            // Main's default empty Tilemap is used read-only: no world generation/load/save.
            Equal(true, Terraria.Main.tile.Width > 300 && Terraria.Main.tile.Height > 150, "empty tile storage available");
            foreach (bool wire in new[] { false, true })
            foreach (int authored in new[] { 1, 80, 81, 100, 120, 121 })
            foreach (bool near in new[] { false, true })
            {
                string label = $"wire={wire}, range={authored}, near={near}";
                try
                {
                    WithPlayer((player, generated) =>
                    {
                        player.active = true;
                        player.whoAmI = 1;
                        player.Center = new Vector2(1600f, 1600f);
                        lastPositions[1] = player.position;
                        Vector2 start = player.Center;
                        int bounded = Math.Min(authored, 120);
                        float distance = near ? bounded * 8f : 2500f;
                        Terraria.Main.screenPosition = start + new Vector2(distance, 0f);
                        var data = GeneratedItemData.Placeholder();
                        data.Gameplay.MobilityMode = "blink_to_cursor";
                        data.Gameplay.MobilityRangeTiles = authored;
                        data.Gameplay.MobilityCooldownTicks = 60;
                        data.Gameplay.MobilitySafeTileOnly = true;
                        if (wire)
                        {
                            string json = JsonSerializer.Serialize(data, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
                            data = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("blink fixture rejected");
                            data = GeneratedItemData.FromJson(data.ToNetworkJson()) ?? throw new InvalidOperationException("blink network fixture rejected");
                        }
                        Equal(true, generated.TryRunGeneratedMobility(data.Gameplay), label + " accepted");
                        Equal(1f, player.teleportTime, label + " real Teleport completed, no swallowed partial failure");
                        Equal(start + new Vector2(Math.Min(distance, bounded * 16f), 0f), player.Center, label + " actual player center");
                        if (wire) Equal(bounded, data.Gameplay.MobilityRangeTiles, label + " DTO range");
                        Equal(60, generated.GeneratedMobilityCooldownTicks, label + " successful cooldown");
                        Vector2 arrived = player.Center;
                        Equal(false, generated.TryRunGeneratedMobility(data.Gameplay), label + " cooldown blocks repeat");
                        Equal(arrived, player.Center, label + " blocked repeat does not move player");
                    });
                }
                catch (Exception error) { failures.Add(label + ": " + error.Message); }
            }
            foreach (string reason in new[] { "zero", "unsafe", "dead", "inactive" })
            {
                try
                {
                    WithPlayer((player, generated) =>
                    {
                        player.active = reason != "inactive";
                        player.dead = reason == "dead";
                        player.whoAmI = 1;
                        player.Center = new Vector2(1600f, 1600f);
                        lastPositions[1] = player.position;
                        Vector2 start = player.Center;
                        Terraria.Main.screenPosition = reason == "unsafe" ? new Vector2(8f, 1600f) : start + new Vector2(100f, 0f);
                        var gameplay = new GameplaySpec { MobilityMode = "blink_to_cursor", MobilityRangeTiles = reason == "zero" ? 0 : 120,
                            MobilitySafeTileOnly = true, MobilityCooldownTicks = 60 };
                        Equal(false, generated.TryRunGeneratedMobility(gameplay), reason + " rejected");
                        Equal(start, player.Center, reason + " leaves position unchanged");
                        Equal(0, generated.GeneratedMobilityCooldownTicks, reason + " does not consume cooldown");
                        if (reason == "unsafe") Equal("Unsafe blink destination", generated.LastGeneratedMobilityFailureMessage, "world edge reason");
                    });
                }
                catch (Exception error) { failures.Add(reason + ": " + error.Message); }
            }
        }
        finally
        {
            Terraria.Main.netMode = oldMode;
            Terraria.Main.myPlayer = oldLocal;
            Terraria.Main.mouseX = oldMouseX;
            Terraria.Main.mouseY = oldMouseY;
            Terraria.Main.screenPosition = oldScreen;
            Terraria.Main.projectile = oldProjectiles;
            Terraria.Main.dust = oldDust;
            Terraria.Main.player[0] = oldPlayer;
            Terraria.Main.rand = oldRandom;
            lastPositionField.SetValue(null, oldLastPositions);
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}
