#nullable enable
using System.ComponentModel;
using Terraria.ModLoader.Config;

namespace InfiniCrafterLocal.Common.Config;

public sealed class InfiniVfxClientConfig : ModConfig
{
    public override ConfigScope Mode => ConfigScope.ClientSide;

    [Header("GeneratedVFX")]
    [DefaultValue(1f)]
    [Range(0f, 2f)]
    [Slider]
    public float ParticleSpawnMultiplier = 1f;

    // v0.4.116: default back to stock intensity. Visual/light leaks are fixed in renderer dispatch and sprite draw, not by dimming user VFX.
    [DefaultValue(1f)]
    [Range(0f, 1.5f)]
    [Slider]
    public float ParticleAlphaMultiplier = 1f;

    [DefaultValue(1f)]
    [Range(0.25f, 2f)]
    [Slider]
    public float DrawBudgetMultiplier = 1f;

    [DefaultValue(1f)]
    [Range(0f, 1f)]
    [Slider]
    public float PresentationLightMultiplier = 1f;

    [DefaultValue(true)]
    public bool EnableScreenCulling = true;

    [DefaultValue(false)]
    public bool EnableGeneratedSpriteSilhouette = false;

    [DefaultValue(true)]
    public bool EnableParticleLibraryBackend = true;

    [DefaultValue(false)]
    public bool EnableLuminanceSoundBackend = false;

    [DefaultValue(false)]
    public bool ForceVanillaDustFallback = false;
}
