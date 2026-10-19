namespace InfiniCrafterLocal.Common.UI;

// Presentation only. Saved definitions and runtime parameters keep their declared
// engine units; one Terraria world block is 16 pixels and one second is 60 ticks.
internal static class PlayerDisplayUnits
{
    internal static float Blocks(float worldPixels) => worldPixels / 16f;

    // World-tick contributions use one update. Projectile velocities use
    // extraUpdates + 1 updates per world tick; this is nominal, not final speed.
    internal static float BlocksPerSecond(float pixelsPerUpdate, int updatesPerWorldTick = 1)
        => Blocks(pixelsPerUpdate * 60f * updatesPerWorldTick);
}
