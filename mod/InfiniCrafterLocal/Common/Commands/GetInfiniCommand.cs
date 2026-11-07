#nullable enable
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

/// <summary>
/// Repair/catch-up command for generated item registry and PNG/JSON asset downloads.
/// It does not grant items and does not re-author recipes; it only re-requests the
/// server registry and clears client asset backoff so already-generated items hydrate.
/// </summary>
public sealed class GetInfiniCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "getinfini";
    public override string Description => "Force InfiniCraft generated-item registry and asset catch-up sync.";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        var assetSync = InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync;
        assetSync?.ResetRetryState();
        var registry = InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        int localCount = registry?.Snapshot().Length ?? 0;
        var assetSnapshot = assetSync?.GetDebugSnapshot();
        registry?.RequestFullSyncFromServer(forceAssetRetry: true);

        string assetText = assetSnapshot is null
            ? ""
            : $" Assets: cache {assetSnapshot.CacheFileCount}, queued {assetSnapshot.InFlightCount}, remembered missing {assetSnapshot.KnownMissingCount}.";

        if (Main.netMode == NetmodeID.MultiplayerClient)
            Main.NewText($"InfiniCraft: requested full generated-item registry + forced asset retry from server. Local cache: {localCount} items.{assetText}", 120, 220, 255);
        else
            Main.NewText($"InfiniCraft: refreshed local generated-item assets. Local cache: {localCount} items.{assetText}", 120, 220, 255);
    }
}
