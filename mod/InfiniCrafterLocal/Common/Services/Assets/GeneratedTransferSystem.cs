#nullable enable
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

/// <summary>Ticks the single generated-definition/asset transfer queue on Terraria's main thread.</summary>
public sealed class GeneratedTransferSystem : ModSystem
{
    public override void PostUpdateEverything()
        => global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.UpdateTransfers();
}
