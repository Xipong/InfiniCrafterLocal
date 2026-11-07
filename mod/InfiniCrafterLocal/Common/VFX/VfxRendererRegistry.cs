#nullable enable
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.VFX;

public enum InfiniVfxRendererKind
{
    None, NativeDust, NativeLight, NativeEffect, HistoryTrail, Shape, Contours,
    SoundCue, SpriteElement, TexturedPath, LibraryParticle, ScreenShakeCue
}

/// <summary>Exact renderer registry. Runtime never classifies prose or fuzzy renderer text.</summary>
public static class VfxRendererRegistry
{
    public static InfiniVfxRendererKind Resolve(VfxSlotSpec? slot)
        => slot is null ? InfiniVfxRendererKind.None : ParseKind(slot.RendererKind);

    internal static int DustId(string? selector) => selector switch
    {
        "Smoke" => Terraria.ID.DustID.Smoke,
        "Glass" => Terraria.ID.DustID.Glass,
        "Electric" => Terraria.ID.DustID.Electric,
        "TintableDustLighted" => Terraria.ID.DustID.TintableDustLighted,
        "GemDiamond" => Terraria.ID.DustID.GemDiamond,
        _ => throw new System.IO.InvalidDataException("Unknown particle selector"),
    };

    public static InfiniVfxRendererKind ParseKind(string? value)
    {
        return value switch
        {
            "nativeEffect" => InfiniVfxRendererKind.NativeEffect,
            "nativeDust" => InfiniVfxRendererKind.NativeDust,
            "nativeLight" => InfiniVfxRendererKind.NativeLight,
            "historyTrail" => InfiniVfxRendererKind.HistoryTrail,
            "shape" => InfiniVfxRendererKind.Shape,
            "contour" => InfiniVfxRendererKind.Contours,
            "libraryParticle" => InfiniVfxRendererKind.LibraryParticle,
            "screenShakeCue" => InfiniVfxRendererKind.ScreenShakeCue,
            "spriteElement" => InfiniVfxRendererKind.SpriteElement,
            "texturedPath" => InfiniVfxRendererKind.TexturedPath,
            "soundCue" => InfiniVfxRendererKind.SoundCue,
            _ => InfiniVfxRendererKind.None,
        };
    }


    public static string ToWireName(InfiniVfxRendererKind kind) => kind switch
    {
        InfiniVfxRendererKind.NativeEffect => "nativeEffect",
        InfiniVfxRendererKind.NativeDust => "nativeDust",
        InfiniVfxRendererKind.NativeLight => "nativeLight",
        InfiniVfxRendererKind.HistoryTrail => "historyTrail",
        InfiniVfxRendererKind.Shape => "shape",
        InfiniVfxRendererKind.Contours => "contour",
        InfiniVfxRendererKind.LibraryParticle => "libraryParticle",
        InfiniVfxRendererKind.ScreenShakeCue => "screenShakeCue",
        InfiniVfxRendererKind.SpriteElement => "spriteElement",
        InfiniVfxRendererKind.TexturedPath => "texturedPath",
        InfiniVfxRendererKind.SoundCue => "soundCue",
        _ => "none",
    };

}
