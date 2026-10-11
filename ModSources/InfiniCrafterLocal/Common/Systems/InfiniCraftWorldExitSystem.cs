#nullable enable
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using InfiniCrafterLocal.Common.VFX;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

public sealed class InfiniCraftWorldExitSystem : ModSystem
{
    public override void OnWorldLoad()
    {
        InfiniItemVfxRuntime.ClearUseEventCaches();
        GeneratedEquipOverlayDrawLayerBase.ClearNetCaches();
        try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.ReloadLocalCacheForCurrentWorld(); }
        catch { }
    }

    public override void OnWorldUnload()
    {
        if (Main.netMode == Terraria.ID.NetmodeID.Server)
        {
            // Each server player owns its workers, including disconnected players
            // whose transient state has not yet been retired. Never refund escrow here.
            foreach (Player player in Main.player)
            {
                try { player?.GetModPlayer<InfiniCraftPlayer>().AbortTransientCraftForWorldExit(); }
                catch { } // One missing/unloading ModPlayer must not strand later owners.
            }
        }
        else
        {
            try { Main.LocalPlayer?.GetModPlayer<InfiniCraftPlayer>().AbortTransientCraftForWorldExit(); }
            catch { } // Best-effort inventory protection while Terraria is unloading.
        }
        try { GeneratedHeldItemDrawLayer.ClearNetCaches(); }
        catch { }
        try { GeneratedEquipOverlayDrawLayerBase.ClearNetCaches(); }
        catch { }
        try { InfiniItemVfxRuntime.ClearUseEventCaches(); }
        catch { }
        try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.Dispose(); }
        catch { }
    }
}
