#nullable enable
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public static class InfiniRuntimeAuthority
{
    public static bool IsServer => Main.netMode == NetmodeID.Server;
    public static bool IsMultiplayerClient => Main.netMode == NetmodeID.MultiplayerClient;
    public static bool IsSinglePlayer => Main.netMode == NetmodeID.SinglePlayer;
    public static bool IsLocalPlayer(int playerWhoAmI) => Main.myPlayer == playerWhoAmI;
    public static bool IsLocalProjectileOwner(Projectile projectile) => projectile is not null && Main.myPlayer == projectile.owner;

    // Generated projectile side-effects are owner-authoritative, matching the old
    // Projectile.owner == Main.myPlayer guard used by child-spawn/proc code.  Dedicated
    // servers receive/sync projectile state, but should not spawn a second set of child
    // projectiles or run impact mobility in parallel with the owning client.
    public static bool ShouldRunProjectileGameplay(Projectile projectile)
    {
        if (projectile is null) return false;
        if (IsSinglePlayer) return true;
        if (IsServer) return false;
        return IsLocalProjectileOwner(projectile);
    }

    public static bool ShouldRunPlayerGameplay(Player player)
    {
        if (player is null || !player.active) return false;
        if (IsSinglePlayer) return true;
        if (IsServer) return true;
        return IsLocalPlayer(player.whoAmI);
    }

    // Player input/cursor actions must be owner-local. Dedicated servers do not have
    // Main.MouseWorld and should not replay generated item side-effects in parallel with
    // the owning client. The client executes and then syncs the resulting state/teleport.
    public static bool ShouldRunLocalPlayerAction(Player player)
    {
        if (player is null || !player.active) return false;
        if (IsSinglePlayer) return true;
        if (IsServer) return false;
        return IsLocalPlayer(player.whoAmI);
    }

    public static bool ShouldRunVisuals(Entity entity) => entity is not null && !IsServer;

    public static void SyncTeleport(Player player, Microsoft.Xna.Framework.Vector2 destination)
    {
        if (player is null) return;
        if (Main.netMode != NetmodeID.SinglePlayer)
            NetMessage.SendData(MessageID.TeleportEntity, -1, -1, null, 0, player.whoAmI, destination.X, destination.Y, 0);
    }
}
