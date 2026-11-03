using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;

internal static partial class EngineRuntimeChecks
{
    private static void MobilityBoundsRejectBeforeNativeConsumption()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (bool safe in new[] { false, true })
        foreach (string edge in new[] { "left", "top", "right", "bottom", "nan", "infinity" })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player);
            Vector2 target = MobilityInvalidTarget(edge, player);
            Vector2 before = player.position;
            var data = MobilityConsumptionFixture("blink_to_cursor", 1);
            data.Gameplay.MobilitySafeTileOnly = safe;
            var host = MobilityConsumptionHost(data);
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), $"{edge}/{safe} native item admission before target sampling");
            Terraria.Main.screenPosition = target;
            scope.RunNativeSuffix(player);
            Equal(before, player.position, $"{edge}/{safe} refused target cannot reach Teleport");
            Equal(1, host.Item.stack, $"{edge}/{safe} native refusal preserves stack");
            Equal(0, generated.GeneratedMobilityCooldownTicks, $"{edge}/{safe} refusal preserves cooldown");
            Equal(1, host.UseCalls, $"{edge}/{safe} exactly one native use attempt");
            Equal(true, player.itemTime > 0, $"{edge}/{safe} no zero-time native retry loop");
        });
    }

    private static Vector2 MobilityInvalidTarget(string edge, Player player)
    {
        float right = (Terraria.Main.maxTilesX - 1) * 16f;
        float bottom = (Terraria.Main.maxTilesY - 1) * 16f;
        if (edge == "right") player.Center = new Vector2(right - 100, 1600);
        if (edge == "bottom") player.Center = new Vector2(1600, bottom - 100);
        return edge switch {
            "left" => new Vector2(8, player.Center.Y),
            "top" => new Vector2(player.Center.X, 8),
            "right" => new Vector2(right, player.Center.Y),
            "bottom" => new Vector2(player.Center.X, bottom),
            "nan" => new Vector2(float.NaN, player.Center.Y),
            _ => new Vector2(player.Center.X, float.PositiveInfinity),
        };
    }

    private static void EventMobilityBoundsPreserveCooldownAndUnsafeSolids()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (bool safe in new[] { false, true })
        foreach (string edge in new[] { "left", "top", "right", "bottom", "nan", "infinity" })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player);
            Vector2 target = MobilityInvalidTarget(edge, player);
            Vector2 before = player.position;
            RunMobilityEvent(player, target, safe);
            Equal(before, player.position, $"event {edge}/{safe} target refused");
            Equal(0, generated.GeneratedMobilityCooldownTicks, $"event {edge}/{safe} cooldown not spent");
        });

        // Unsafe is still a deliberate authored choice: the hard world guard does
        // not add solid or lava avoidance to either low-level mobility operation.
        WithPersistenceTilemap((_, __) => {
        Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
        bool oldSolid = Terraria.Main.tileSolid[Terraria.ID.TileID.Stone];
        Tile tile = Terraria.Main.tile[40, 40];
        try {
            Terraria.Main.tileSolid[Terraria.ID.TileID.Stone] = true;
            tile.ClearEverything(); tile.HasTile = true; tile.TileType = Terraria.ID.TileID.Stone;
            foreach (bool eventAction in new[] { false, true })
            WithPlayer((player, generated) => {
                PrepareMobilityConsumptionPlayer(player);
                player.Center = new Vector2(500, 648);
                Vector2 target = new(648, 648);
                if (eventAction) RunMobilityEvent(player, target, false);
                else {
                    Terraria.Main.screenPosition = target;
                    Equal(true, generated.TryRunGeneratedMobility(new GameplaySpec {
                        MobilityMode = "blink_to_cursor", MobilityRangeTiles = 120,
                        MobilityCooldownTicks = 60, MobilitySafeTileOnly = false }), "unsafe item solid teleport accepted");
                }
                Equal(target, player.Center, "unsafe solid destination retains authored meaning");
                Equal(60, generated.GeneratedMobilityCooldownTicks, "successful unsafe move consumes cooldown");
            });
        }
        finally { Terraria.Main.tileSolid[Terraria.ID.TileID.Stone] = oldSolid; }
        });
    }

    private static void RunMobilityEvent(Player player, Vector2 target, bool safe)
    {
        var action = new RuntimeEventActionSpec {
            ActionCode = RuntimeEventActionCode.MoveOwner, Mode = "blink_to_event_position",
            RangeTiles = 120, CooldownTicks = 60, SafeTileOnly = safe };
        int budget = 0;
        RuntimeProgramExecutor.ExecuteAction(GeneratedItemData.Placeholder(), new RuntimeEntitySpec(), action,
            player, new EntitySource_Misc("mobility boundary regression"), target,
            Vector2.UnitX, null, 0, 0, ref budget);
    }

    private static void RecallUsesNativeBedValidityAndRejectsInvalidSpawn()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (string bed in new[] { "removed", "negative", "outside" })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player);
            // Empty native tile storage cannot contain a bed at these coordinates.
            player.SpawnX = bed == "removed" ? 200 : bed == "negative" ? -1 : int.MaxValue;
            player.SpawnY = bed == "removed" ? 100 : bed == "negative" ? -1 : int.MaxValue;
            player.velocity = new Vector2(18, 24);
            var host = MobilityConsumptionHost(MobilityConsumptionFixture("recall_home", 1));
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), bed + " recall admission");
            scope.RunNativeSuffix(player);
            Equal(new Vector2(1608 - player.width / 2f, 1760 - player.height), player.position,
                bed + " actual native teleport uses world spawn rather than stale bed coordinates");
            Equal(Vector2.Zero, player.velocity, bed + " recall clears falling or dash velocity");
            Equal(player.fallStart, player.fallStart2, bed + " both native fall samples reset");
            Equal(0, host.Item.stack, bed + " successful native use consumes once");
            Equal(60, generated.GeneratedMobilityCooldownTicks, bed + " successful native use cooldown");
        });
        WithPersistenceTilemap((_, __) => {
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            bool oldSolid = Terraria.Main.tileSolid[Terraria.ID.TileID.Stone];
            bool oldWall = Terraria.Main.wallHouse[Terraria.ID.WallID.Wood];
            // Native room scanning is real. Preserve its process-static scratch
            // state as well as the isolated tile storage owned by this fixture.
            var roomState = new System.Collections.Generic.Dictionary<System.Reflection.FieldInfo, object?>();
            foreach (var field in typeof(WorldGen).GetFields(System.Reflection.BindingFlags.Static
                | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic))
                if (field.Name.StartsWith("room", StringComparison.OrdinalIgnoreCase)
                    || field.Name is "houseTile" or "canSpawn" or "numRoomTiles" or "lastMaxTilesY")
                {
                    object? value = field.GetValue(null);
                    roomState[field] = value is Array array ? array.Clone() : value;
                }
            try {
                typeof(WorldGen).GetField("lastMaxTilesY", System.Reflection.BindingFlags.Static
                    | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic)!
                    .SetValue(null, Terraria.Main.maxTilesY);
                Terraria.Main.tileSolid[Terraria.ID.TileID.Stone] = true;
                Terraria.Main.wallHouse[Terraria.ID.WallID.Wood] = true;
                for (int x = 30; x <= 50; x++)
                for (int y = 30; y <= 40; y++) {
                    Tile cell = Terraria.Main.tile[x, y]; cell.ClearEverything();
                    cell.WallType = Terraria.ID.WallID.Wood;
                    if (x == 30 || x == 50 || y == 30 || y == 40) {
                        cell.HasTile = true; cell.TileType = Terraria.ID.TileID.Stone;
                    }
                }
                for (int x = 38; x <= 41; x++)
                for (int y = 38; y <= 39; y++) {
                    Tile cell = Terraria.Main.tile[x, y]; cell.HasTile = true;
                    cell.TileType = Terraria.ID.TileID.Beds;
                    cell.TileFrameX = (short)((x - 38) * 18); cell.TileFrameY = (short)((y - 38) * 18);
                }
                Equal(true, Player.CheckSpawn(40, 40), "real enclosed room and bed satisfy native CheckSpawn");
                foreach (string scenario in new[] { "valid", "removed", "left", "right", "top", "bottom" })
                WithPlayer((player, generated) => {
                    PrepareMobilityConsumptionPlayer(player);
                    Terraria.Main.spawnTileX = Terraria.Main.spawnTileY = 60;
                    player.Center = new Vector2(900, 900);
                    player.SpawnX = scenario == "left" ? 1 : scenario == "right" ? Terraria.Main.maxTilesX - 2 : 40;
                    player.SpawnY = scenario == "top" ? 1 : scenario == "bottom" ? Terraria.Main.maxTilesY - 2 : 40;
                    if (scenario == "removed")
                        for (int x = 38; x <= 41; x++) for (int y = 38; y <= 39; y++)
                            { Tile cell = Terraria.Main.tile[x, y]; cell.HasTile = false; }
                    Equal(scenario == "valid", Player.CheckSpawn(player.SpawnX, player.SpawnY),
                        scenario + " native bed validity, including near-world-edge coordinates");
                    var host = MobilityConsumptionHost(MobilityConsumptionFixture("recall_home", 1));
                    player.inventory[0] = host.Item;
                    Equal(true, host.CanUseItem(player), scenario + " bed recall admission");
                    scope.RunNativeSuffix(player);
                    int spawn = scenario == "valid" ? 40 : 60;
                    Equal(new Vector2(spawn * 16 + 8 - player.width / 2f, spawn * 16 - player.height),
                        player.position, scenario + " native recall selects bed only while valid");
                    Equal(0, host.Item.stack, scenario + " successful native recall consumes once");
                    Equal(60, generated.GeneratedMobilityCooldownTicks, scenario + " successful recall cooldown");
                });
            }
            finally {
                Terraria.Main.tileSolid[Terraria.ID.TileID.Stone] = oldSolid;
                Terraria.Main.wallHouse[Terraria.ID.WallID.Wood] = oldWall;
                foreach (var entry in roomState)
                    if (entry.Value is Array array && entry.Key.GetValue(null) is Array current)
                        Array.Copy(array, current, array.Length);
                    else if (!entry.Key.IsInitOnly) entry.Key.SetValue(null, entry.Value);
            }
        });
        foreach (int spawn in new[] { 0, 1, int.MaxValue })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player);
            player.SpawnX = player.SpawnY = -1;
            Terraria.Main.spawnTileX = Terraria.Main.spawnTileY = spawn;
            var host = MobilityConsumptionHost(MobilityConsumptionFixture("recall_home", 1));
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "invalid spawn admission before execution");
            Vector2 before = player.position;
            scope.RunNativeSuffix(player);
            Equal(before, player.position, "invalid spawn cannot teleport outside body bounds");
            Equal(1, host.Item.stack, "invalid spawn preserves native stack");
            Equal(0, generated.GeneratedMobilityCooldownTicks, "invalid spawn preserves cooldown");
        });
    }
}
