#nullable enable
using System;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    public readonly record struct GeneratedHomeDestination(bool Available, bool UsesBed, bool RemovedBed,
        int TileX, int TileY, Vector2 Destination, float DistanceTiles, int CooldownTicks);
    public readonly record struct GeneratedRecallJourney(Vector2 Departure, Vector2 Arrival, bool UsedBed, uint Tick);
    private GeneratedRecallJourney? _lastGeneratedRecall;
    public GeneratedRecallJourney? LastGeneratedRecall => _lastGeneratedRecall;

    // Recheck native bed validity every time; neither a tooltip nor a previous
    // successful recall becomes a cached source of destination authority.
    public GeneratedHomeDestination CaptureGeneratedHomeDestination()
    {
        bool bed = Terraria.Player.CheckSpawn(Player.SpawnX, Player.SpawnY);
        int x = bed ? Player.SpawnX : Main.spawnTileX;
        int y = bed ? Player.SpawnY : Main.spawnTileY;
        Vector2 destination = new(x * 16f + 8f - Player.width / 2f, y * 16f - Player.height);
        bool available = x > 0 && y > 0 && x < Main.maxTilesX - 1 && y < Main.maxTilesY - 1
            && IsBlinkWithinWorld(destination);
        bool removed = !bed && Player.SpawnX > 0 && Player.SpawnY > 0;
        float distance = available && float.IsFinite(Player.position.X) && float.IsFinite(Player.position.Y)
            ? Vector2.Distance(Player.position, destination) / 16f : 0f;
        return new(available, bed, removed, x, y, destination, distance, _generatedMobilityCooldownTicks);
    }
}
