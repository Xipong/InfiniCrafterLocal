#nullable enable
using System;
using InfiniCrafterLocal.Common.Config;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.VFX;

public static class InfiniVfxClientOptions
{
    private static InfiniVfxClientConfig? Config
    {
        get
        {
            if (Main.dedServ)
                return null;
            try { return ModContent.GetInstance<InfiniVfxClientConfig>(); }
            catch { return null; }
        }
    }

    public static float ParticleSpawnMultiplier
        => Math.Clamp(Config?.ParticleSpawnMultiplier ?? 1f, 0f, 2f);

    internal static int ScaleParticleCount(int baseCount)
    {
        float scaled = baseCount * ParticleSpawnMultiplier;
        int count = (int)MathF.Floor(scaled);
        float fraction = scaled - count;
        // Keep fractional singleton emissions proportional in expectation rather
        // than rounding every half-particle permanently to zero or one. Exact
        // counts (including default/disabled settings) consume no extra RNG.
        return count + (fraction > 0f && Main.rand.NextFloat() < fraction ? 1 : 0);
    }

    public static float ParticleAlphaMultiplier
        => Math.Clamp(Config?.ParticleAlphaMultiplier ?? 1f, 0f, 1.5f);

    public static float DrawBudgetMultiplier
        => Math.Clamp(Config?.DrawBudgetMultiplier ?? 1f, 0.25f, 2f);

    internal static int EffectiveDrawBudget(int authoredBudget)
        // Client quality scales the allowance, not the serialized definition.
        // Floor fractional allowances and retain the normalized engine ceiling.
        => Math.Min(512, (int)(Math.Clamp(authoredBudget, 0, 512) * DrawBudgetMultiplier));

    public static float PresentationLightMultiplier
        => Math.Clamp(Config?.PresentationLightMultiplier ?? 1f, 0f, 1f);

    public static bool EnableScreenCulling
        => Config?.EnableScreenCulling ?? true;

    public static bool EnableGeneratedSpriteSilhouette
        => Config?.EnableGeneratedSpriteSilhouette ?? false;

    public static bool EnableParticleLibraryBackend
        => Config?.EnableParticleLibraryBackend ?? true;

    public static bool EnableLuminanceSoundBackend
        => Config?.EnableLuminanceSoundBackend ?? false;

    public static bool ForceVanillaDustFallback
        => Config?.ForceVanillaDustFallback ?? false;
}
