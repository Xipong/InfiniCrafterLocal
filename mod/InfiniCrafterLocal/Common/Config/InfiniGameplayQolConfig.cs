#nullable enable
using System.ComponentModel;
using Terraria.ModLoader.Config;

namespace InfiniCrafterLocal.Common.Config;

public sealed class InfiniGameplayQolConfig : ModConfig
{
    public override ConfigScope Mode => ConfigScope.ClientSide;

    [Header("InfiniCraftStationQoL")]
    [DefaultValue(true)]
    public bool EnableInventoryAssetPrefetch = true;

    [DefaultValue(120)]
    [Range(30, 600)]
    [Slider]
    public int InventoryAssetPrefetchIntervalTicks = 120;

    [DefaultValue(24)]
    [Range(4, 64)]
    [Slider]
    public int InventoryAssetPrefetchMaxItems = 24;

    [Header("GeneratedGameplayQoL")]
    [DefaultValue(true)]
    public bool EnableGeneratedMeleeOnHitEffects = true;

    [Header("GeneratedRuntimeAssetQoL")]
    [DefaultValue(512)]
    [Range(64, 2048)]
    [Slider]
    public int RuntimeSpriteCacheMaxTextures = 512;

    [DefaultValue(192)]
    [Range(32, 512)]
    [Slider]
    public int RuntimeSpriteMaxDimensionPixels = 192;

    [DefaultValue(8)]
    [Range(1, 64)]
    [Slider]
    public int RuntimeSpriteMaxPngFileMegabytes = 8;
}
