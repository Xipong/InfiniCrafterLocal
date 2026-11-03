using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using MonoMod.RuntimeDetour;

internal static partial class EngineRuntimeChecks
{
    private static void BlinkFeetMatchesNativeTeleportRod()
    {
        using var scope = new MobilityConsumptionNativeScope();
        // The headless harness has no loaded wall/player mod hooks. Keep native
        // rod destination, range and SolidCollision; bypass only external-mod vetoes.
        using var modAdmission = new Hook(typeof(CombinedHooks).GetMethod("CanBeTeleportedTo")!,
            (Func<Player, Vector2, int, int, string, bool>)((_, __, ___, ____, _____) => true));
        int oldHeight = Terraria.Main.screenHeight;
        var failures = new List<string>();
        try {
            Terraria.Main.screenHeight = 600;
            foreach (float gravity in new[] { 1f, -1f })
            foreach (int width in new[] { 20, 21 }) {
                Vector2 expected = default;
                WithPlayer((player, _) => {
                    PrepareBlinkFeetPlayer(player, gravity, width);
                    var rod = new Item(); rod.SetDefaults(ItemID.RodofDiscord);
                    player.inventory[0] = rod;
                    typeof(Player).GetMethod("ItemCheck_UseTeleportRod", BindingFlags.Instance | BindingFlags.NonPublic)!
                        .Invoke(player, new object[] { rod });
                    Equal(1f, player.teleportTime, "native rod really teleported");
                    expected = player.position;
                });
                try {
                    WithPlayer((player, generated) => {
                        PrepareBlinkFeetPlayer(player, gravity, width);
                        Equal(true, generated.TryRunGeneratedMobility(BlinkFeetSpec()), "generated blink accepted");
                        Equal(1f, player.teleportTime, "generated actual native Teleport completed");
                        Equal(expected, player.position, $"gravity={gravity}, width={width}: native rod destination");
                        Equal(60, generated.GeneratedMobilityCooldownTicks, "successful blink cooldown");
                    });
                } catch (Exception error) { failures.Add(error.Message); }
            }
        } finally { Terraria.Main.screenHeight = oldHeight; }
        if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static GameplaySpec BlinkFeetSpec(bool safe = true, int range = 120)
        => new() { MobilityMode = "blink_to_cursor", MobilityRangeTiles = range,
            MobilityCooldownTicks = 60, MobilitySafeTileOnly = safe };

    private static void PrepareBlinkFeetPlayer(Player player, float gravity, int width = 20)
    {
        PrepareMobilityConsumptionPlayer(player);
        player.gravDir = gravity; player.width = width; player.height = 42;
        Terraria.Main.screenPosition = new Vector2(1400, 1400);
        Terraria.Main.mouseX = 200; Terraria.Main.mouseY = 150;
        player.Center = Terraria.Main.MouseWorld - new Vector2(128, 0);
    }

    private static void BlinkFeetSurfaceAndBlockedDestinations()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPersistenceTilemap((_, __) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            bool oldSolid = Terraria.Main.tileSolid[TileID.Stone];
            try {
                Terraria.Main.tileSolid[TileID.Stone] = true;
                foreach (float gravity in new[] { 1f, -1f })
                foreach (bool blocked in new[] { false, true })
                foreach (bool safe in new[] { false, true })
                WithPlayer((player, generated) => {
                    PrepareMobilityConsumptionPlayer(player); player.gravDir = gravity;
                    for (int x = 37; x <= 43; x++) for (int y = 35; y <= 45; y++) Terraria.Main.tile[x,y].ClearEverything();
                    // Exact floor/ceiling boundary; the cursor is at gravity-relative feet.
                    Vector2 foot = new(648, gravity == 1f ? 640 : 656);
                    int row = blocked ? (gravity == 1f ? 39 : 41) : 40;
                    for (int x = 39; x <= 41; x++) {
                        var tile = Terraria.Main.tile[x,row]; tile.HasTile = true; tile.TileType = TileID.Stone;
                    }
                    player.Center = new Vector2(500, 648);
                    Terraria.Main.mouseX = Terraria.Main.mouseY = 0;
                    Terraria.Main.screenPosition = foot - new Vector2(0, gravity == -1f ? Terraria.Main.screenHeight : 0);
                    Vector2 before = player.position;
                    bool expected = !blocked || !safe;
                    Equal(expected, generated.TryRunGeneratedMobility(BlinkFeetSpec(safe)), $"surface gravity={gravity}, blocked={blocked}, safe={safe}");
                    if (expected) {
                        Equal(new Vector2(foot.X - player.width / 2, foot.Y - (gravity == 1f ? player.height : 0)), player.position, "exact requested feet; no nearby-space search");
                        Equal(1f, player.teleportTime, "actual native teleport completed");
                    } else Equal(before, player.position, "solid destination refuses instead of searching nearby");
                    Equal(expected ? 60 : 0, generated.GeneratedMobilityCooldownTicks, "cooldown follows actual success");
                });
            } finally {
                for (int x = 37; x <= 43; x++) for (int y = 35; y <= 45; y++) Terraria.Main.tile[x,y].ClearEverything();
                Terraria.Main.tileSolid[TileID.Stone] = oldSolid;
            }
        });
    }

    private static void BlinkFeetKeepsEventWorldPoint()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (float gravity in new[] { 1f, -1f })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player); player.gravDir = gravity;
            var point = new Vector2(1728, 1500);
            Terraria.Main.screenPosition = new Vector2(200, 300);
            Terraria.Main.mouseX = 73; Terraria.Main.mouseY = 91;
            RunMobilityEvent(player, point, true);
            Equal(point, player.Center, "event target remains a world-space centre, independent of cursor/gravity");
            Equal(1f, player.teleportTime, "actual event Teleport completed");
            Equal(60, generated.GeneratedMobilityCooldownTicks, "event cooldown unchanged");
        });
    }
    private static void BlinkFeetKeepsRangeAndWorldEdges()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (float gravity in new[] { 1f, -1f })
        foreach (bool far in new[] { false, true })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player); player.gravDir = gravity;
            Vector2 start = player.Center;
            Vector2 target = start + new Vector2(far ? 1000 : 48, far ? 750 : 64);
            Terraria.Main.screenPosition = target - new Vector2(0, gravity == -1f ? Terraria.Main.screenHeight : 0);
            Vector2 delta = target - start;
            Vector2 limited = delta.Length() > 160 ? start + Vector2.Normalize(delta) * 160 : target;
            Equal(true, generated.TryRunGeneratedMobility(BlinkFeetSpec(range: 10)), "range-limited blink accepted");
            Equal(new Vector2(limited.X - player.width / 2, limited.Y - (gravity == 1f ? player.height : 0)), player.position,
                "existing authored radius limits target before feet anchoring");
        });
        WithPersistenceTilemap((_, __) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            foreach (float gravity in new[] { 1f, -1f })
            foreach (bool safe in new[] { false, true })
            foreach (string edge in new[] { "left", "top", "right", "bottom" })
            foreach (bool inside in new[] { false, true })
            WithPlayer((player, generated) => {
                PrepareMobilityConsumptionPlayer(player); player.gravDir = gravity;
                float right = (Terraria.Main.maxTilesX - 1) * 16f;
                float bottom = (Terraria.Main.maxTilesY - 1) * 16f;
                Vector2 topLeft = edge switch {
                    "left" => new(inside ? 16 : 15, 640),
                    "top" => new(640, inside ? 16 : 15),
                    "right" => new(right - player.width - (inside ? 1 : 0), 640),
                    _ => new(640, bottom - player.height - (inside ? 1 : 0)),
                };
                Vector2 foot = topLeft + new Vector2(player.width / 2, gravity == 1f ? player.height : 0);
                player.Center = new Vector2(Math.Clamp(foot.X, 128, right - 128), Math.Clamp(foot.Y, 128, bottom - 128));
                Terraria.Main.screenPosition = foot - new Vector2(0, gravity == -1f ? Terraria.Main.screenHeight : 0);
                Vector2 before = player.position;
                Equal(inside, generated.TryRunGeneratedMobility(BlinkFeetSpec(safe)), $"{gravity}/{edge}/{safe}/{inside} entire body bounds");
                Equal(inside ? topLeft : before, player.position, "exact edge success or unchanged refusal");
                Equal(inside ? 60 : 0, generated.GeneratedMobilityCooldownTicks, "bounds refusal preserves cooldown");
            });
        });
    }

    private static void BlinkFeetKeepsLocalAuthorityAndPacketCoordinates()
    {
        using var scope = new MobilityConsumptionNativeScope();
        int packets = 0, packetOwner = -1; Vector2 destination = default;
        Action<int, int, int, Terraria.Localization.NetworkText, int, float, float, float, int, int, int> send =
            (message, remote, ignore, text, number, owner, x, y, style, a, b) => {
                if (message == MessageID.TeleportEntity) { packets++; packetOwner = (int)owner; destination = new Vector2(x, y); }
            };
        using var network = new Hook(typeof(NetMessage).GetMethod(nameof(NetMessage.SendData),
            new[] { typeof(int), typeof(int), typeof(int), typeof(Terraria.Localization.NetworkText), typeof(int),
                typeof(float), typeof(float), typeof(float), typeof(int), typeof(int), typeof(int) })!, send);
        foreach (float gravity in new[] { 1f, -1f })
        foreach (string peer in new[] { "owner", "observer", "server" })
        WithPlayer((player, generated) => {
            PrepareBlinkFeetPlayer(player, gravity);
            Terraria.Main.netMode = peer == "server" ? NetmodeID.Server : NetmodeID.MultiplayerClient;
            if (peer == "observer") Terraria.Main.myPlayer = 0;
            Vector2 before = player.position;
            packets = 0;
            Equal(peer == "owner", generated.TryRunGeneratedMobility(BlinkFeetSpec()), peer + " cursor authority");
            Equal(peer == "owner" ? 1 : 0, packets, peer + " exactly one owner teleport packet");
            if (peer == "owner") {
                Equal(player.whoAmI, packetOwner, "packet identifies actual owner");
                Equal(player.position, destination, "packet publishes the exact applied feet-anchored top left");
                Equal(1f, player.teleportTime, "owner native teleport completed");
            } else {
                Equal(before, player.position, "remote peer cannot replay cursor movement");
                Equal(0, generated.GeneratedMobilityCooldownTicks, "remote refusal has no cooldown debit");
            }
        });
    }

}
