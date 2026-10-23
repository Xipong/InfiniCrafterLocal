#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using Terraria;
using Terraria.ID;
namespace InfiniCrafterLocal.Content.Items;
public partial class GeneratedItem
{
    // Only explicit recovery commands call this. Tooltip and status reads never send requests.
    internal bool RecoverDefinition()
    {
        if (!DefinitionRecoveryView.Capture(Data).CanRecover) return false;
        var registry = InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null) return false;
        if (registry.TryGet(Data.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical)
            && !GeneratedItemData.IsPlayerSaveReferenceOnly(canonical))
        {
            SetData(canonical, ensureAssets: true, registerLocal: false, notifyNetState: false);
            return true;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient) return false;
        registry.RequestOneFromServer(Data.Id, forceAssetRetry: false);
        return true;
    }
}
