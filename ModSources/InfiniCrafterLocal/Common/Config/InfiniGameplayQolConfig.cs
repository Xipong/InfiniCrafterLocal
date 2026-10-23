#nullable enable
using System.ComponentModel;
using Terraria.ModLoader.Config;

namespace InfiniCrafterLocal.Common.Config;

public sealed class InfiniGameplayQolConfig : ModConfig
{
    public override ConfigScope Mode => ConfigScope.ClientSide;

    [Header("InfiniCraftStationQoL")]
    [DefaultValue(true)]
    public bool PlayCraftCompletionSound = true;

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
    [DefaultValue(40)]
    [Range(25, 100)]
    [Slider]
    public int GeneratedStatusOpacityPercent = 40;

    [DefaultValue(false)]
    public bool DetachedGeneratedStatusHud = false;

    [DefaultValue(5)] [Range(0, 100)] [Slider]
    public int GeneratedStatusHudXPercent = 5;

    [DefaultValue(20)] [Range(0, 100)] [Slider]
    public int GeneratedStatusHudYPercent = 20;

    [DefaultValue(8)] [Range(1, 20)] [Slider]
    public int GeneratedStatusHudColumns = 8;

    [DefaultValue(100)] [Range(75, 150)] [Slider]
    public int GeneratedStatusHudScalePercent = 100;

    [DefaultValue(false)]
    public bool PreviewGeneratedStatusHud = false;

    [DefaultValue(true)]
    public bool PlayChargeReadySound = true;

    [DefaultValue(false)]
    public bool AlwaysExpandGeneratedTooltips = false;

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
