#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Terraria.ModLoader;

namespace InfiniCrafterLocal;

// AGENT MAP: root composition and packet router for the C# runtime.
// Load() owns the long-lived services; HandlePacket() is the single packet
// demux; Call() is the small public API for other mods. Do not add gameplay
// authoring here — generated behavior must already be explicit GeneratedItemData.
public sealed class InfiniCrafterLocalMod : Mod
{
    public const string ModVersion = "0.4.239";
    public static InfiniCrafterLocalMod Instance { get; private set; } = null!;
    public static GeneratorClient Generator { get; private set; } = null!;
    public static RuntimeSpriteCache Sprites { get; private set; } = null!;
    public static GeneratedAssetSyncService AssetSync { get; private set; } = null!;
    public static GeneratedItemRegistryService GeneratedItems { get; private set; } = null!;

    public override void Load()
    {
        Instance = this;
        Generator = new GeneratorClient();
        Sprites = new RuntimeSpriteCache();
        AssetSync = new GeneratedAssetSyncService();
        GeneratedItems = new GeneratedItemRegistryService();
    }


    public override void HandlePacket(System.IO.BinaryReader reader, int whoAmI)
    {
        byte packetType = reader.ReadByte();
        if (packetType == InfiniNetPacketIds.RequestGeneratedAsset)
        {
            AssetSync?.HandleAssetRequestPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.GeneratedAssetChunk)
        {
            AssetSync?.HandleAssetChunkPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.RequestServerCraft)
        {
            InfiniCraftPlayer.HandleRequestServerCraftPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.CancelServerCraft)
        {
            InfiniCraftPlayer.HandleCancelServerCraftPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.RequestStationEscrow)
        {
            InfiniCraftPlayer.HandleStationEscrowRequestPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.StationEscrowResult)
        {
            InfiniCraftPlayer.HandleStationEscrowResultPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.CraftCommitResult)
        {
            InfiniCraftPlayer.HandleCraftCommitResultPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.SyncGeneratedUtilityBuff)
        {
            InfiniCraftPlayer.HandleGeneratedUtilityBuffSyncPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.RequestGeneratedAltUse)
        {
            InfiniCraftPlayer.HandleGeneratedAltUseRequestPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.NotifyGeneratedItem || packetType == InfiniNetPacketIds.RequestGeneratedRegistry || packetType == InfiniNetPacketIds.RequestGeneratedRegistryForceAssets || packetType == InfiniNetPacketIds.RequestGeneratedItemById)
        {
            GeneratedItems?.HandlePacket(packetType, reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.SyncGeneratedProjectileVisual)
        {
            GeneratedProjectile.HandleProjectileVisualSyncPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent)
        {
            GeneratedProjectile.HandleProjectileVfxEventSyncPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.SyncGeneratedHeldItemPresentation)
        {
            GeneratedHeldItemDrawLayer.HandleHeldItemPresentationSyncPacket(reader, whoAmI);
            return;
        }
        if (packetType == InfiniNetPacketIds.SyncGeneratedItemVfxEvent)
        {
            InfiniItemVfxRuntime.HandleUseEventPacket(reader, whoAmI);
            return;
        }
    }


    public override object? Call(params object[] args)
    {
        if (args is null || args.Length <= 0) return null;
        string command = args[0]?.ToString() ?? "";
        if (string.Equals(command, "IsGeneratedItem", System.StringComparison.OrdinalIgnoreCase))
            return args.Length > 1 && args[1] is Terraria.Item item && item.ModItem is Content.Items.GeneratedItem;
        if (string.Equals(command, "TryGetGeneratedItemData", System.StringComparison.OrdinalIgnoreCase))
            return args.Length > 1 && args[1] is Terraria.Item item2
                ? item2.ModItem is Content.Items.GeneratedItem gi ? gi.Data
                : null
                : null;
        if (string.Equals(command, "GetGeneratedSummary", System.StringComparison.OrdinalIgnoreCase))
            return args.Length > 1 && args[1] is Terraria.Item item3
                ? item3.ModItem is Content.Items.GeneratedItem gi2 ? gi2.Data.GeneratedParentSummary
                : null
                : null;
        if (string.Equals(command, "RegisterGeneratedParentHint", System.StringComparison.OrdinalIgnoreCase))
            return false; // reserved stable API hook; no runtime mutation yet.
        return null;
    }

    public override void Unload()
    {
        InfiniCraftPlayer.ClearServerCommitCache();
        GeneratedProjectile.ClearPresentationSyncCaches();
        GeneratedHeldItemDrawLayer.ClearNetCaches();
        GeneratedEquipOverlayDrawLayerBase.ClearNetCaches();
        InfiniItemVfxRuntime.ClearUseEventCaches();
        GeneratedItems?.Dispose();
        AssetSync?.Dispose();
        Sprites?.Dispose();
        GeneratedItems = null!;
        AssetSync = null!;
        Sprites = null!;
        Generator = null!;
        Instance = null!;
    }
}
