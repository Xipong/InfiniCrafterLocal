#nullable enable

namespace InfiniCrafterLocal.Common;

/// <summary>
/// Single source of truth for tModLoader packet ids used by InfiniCrafterLocal.
/// </summary>
public static class InfiniNetPacketIds
{
    public const byte NotifyGeneratedItem = 2;
    public const byte RequestGeneratedRegistry = 3;
    public const byte CraftCommitResult = 4;
    public const byte RequestServerCraft = 5;
    public const byte RequestGeneratedRegistryForceAssets = 6;
    public const byte SyncGeneratedUtilityBuff = 7;
    public const byte SyncGeneratedProjectileVfxEvent = 9;
    public const byte RequestGeneratedItemById = 10;
    public const byte SyncGeneratedHeldItemPresentation = 11;
    public const byte CancelServerCraft = 12;
    public const byte RequestStationEscrow = 14;
    public const byte StationEscrowResult = 15;
    public const byte RequestGeneratedAsset = 16;
    public const byte GeneratedAssetChunk = 17;
    public const byte SyncGeneratedItemVfxEvent = 18;
    public const byte NotifyGeneratedPlacement = 19;
    public const byte SetMultiDevCraftMode = 20;
}
