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
        try
        {
            if (Main.LocalPlayer is not null)
                Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().AbortTransientCraftForWorldExit();
        }
        catch
        {
            // Best-effort inventory protection on world exit. Avoid throwing while Terraria is unloading.
        }

        catch { }
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
