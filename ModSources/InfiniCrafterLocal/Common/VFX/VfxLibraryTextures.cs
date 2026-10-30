#nullable enable
using System.Collections.Generic;

namespace InfiniCrafterLocal.Common.VFX;

// Exact bounded resource selection, not a procedural shape or behavior preset.
// star remains the saved-wire name for the same soft radial light mask.
internal static class VfxLibraryTextures
{
    private static readonly Dictionary<string,string> Paths = new(System.StringComparer.Ordinal) {
        ["star"]="ParticleLibrary/Assets/Textures/Star",
        ["solidPixel"]="ParticleLibrary/Assets/Textures/WhitePixel",
        ["bloomCircle"]="Luminance/Assets/GreyscaleTextures/BloomCircleSmall",
        ["bloomFlare"]="Luminance/Assets/GreyscaleTextures/BloomFlare",
        ["bloomLine"]="Luminance/Assets/GreyscaleTextures/BloomLine",
        ["chromaticBurst"]="Luminance/Assets/GreyscaleTextures/ChromaticBurst",
        ["shineFlare"]="Luminance/Assets/GreyscaleTextures/ShineFlare",
    };
    internal static bool TryGetPath(string? id,out string path)
    {
        path="";
        return id is not null && Paths.TryGetValue(id,out path!);
    }
}
