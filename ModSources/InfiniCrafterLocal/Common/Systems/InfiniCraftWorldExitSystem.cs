#nullable enable
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

public sealed class InfiniCraftWorldExitSystem : ModSystem
{
    public override void OnWorldLoad()
    {
        try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.ReloadLocalCacheForCurrentWorld(); }
        catch { }
    }

    public override void OnWorldUnload()
    {
        try
        {
            if (Main.LocalPlayer is not null)
                Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().AbortTransientCraftForWorldExit();
        }
        catch
        {
            // Best-effort inventory protection on world exit. Avoid throwing while Terraria is unloading.
        }

        try { GeneratedProjectile.ClearPresentationSyncCaches(); }
        catch { }
        try { GeneratedHeldItemDrawLayer.ClearNetCaches(); }
        catch { }
        try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.Dispose(); }
        catch { }
    }
}
