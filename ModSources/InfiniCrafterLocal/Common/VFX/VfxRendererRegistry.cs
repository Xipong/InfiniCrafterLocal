#nullable enable
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.VFX;

public enum InfiniVfxRendererKind
{
    None, SpriteStampTrail, HistoryRibbon, TipTrail, GhostArc, WavyStrip,
    BeamLine, FieldPulse, OrbitingMotes, ImpactRing, ImpactSprite, ChildMotes,
    LightCue, SoundCue, SpriteElement, TexturedPath, LibraryParticle, ScreenShakeCue
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

    public static bool ConsumesSpriteTexture(InfiniVfxRendererKind kind)
        => kind is InfiniVfxRendererKind.SpriteStampTrail
            or InfiniVfxRendererKind.ImpactSprite;

    public static InfiniVfxRendererKind ParseKind(string? value)
    {
        return value switch
        {
            "libraryParticle" => InfiniVfxRendererKind.LibraryParticle,
            "screenShakeCue" => InfiniVfxRendererKind.ScreenShakeCue,
            "spriteElement" => InfiniVfxRendererKind.SpriteElement,
            "texturedPath" => InfiniVfxRendererKind.TexturedPath,
            "spriteStampTrail" => InfiniVfxRendererKind.SpriteStampTrail,
            "historyRibbon" => InfiniVfxRendererKind.HistoryRibbon,
            "tipTrail" => InfiniVfxRendererKind.TipTrail,
            "ghostArc" => InfiniVfxRendererKind.GhostArc,
            "wavyStrip" => InfiniVfxRendererKind.WavyStrip,
            "beamLine" => InfiniVfxRendererKind.BeamLine,
            "fieldPulse" => InfiniVfxRendererKind.FieldPulse,
            "orbitingMotes" => InfiniVfxRendererKind.OrbitingMotes,
            "impactRing" => InfiniVfxRendererKind.ImpactRing,
            "impactSprite" => InfiniVfxRendererKind.ImpactSprite,
            "childMotes" => InfiniVfxRendererKind.ChildMotes,
            "lightCue" => InfiniVfxRendererKind.LightCue,
            "soundCue" => InfiniVfxRendererKind.SoundCue,
            _ => InfiniVfxRendererKind.None,
        };
    }


    public static string ToWireName(InfiniVfxRendererKind kind) => kind switch
    {
        InfiniVfxRendererKind.LibraryParticle => "libraryParticle",
        InfiniVfxRendererKind.ScreenShakeCue => "screenShakeCue",
        InfiniVfxRendererKind.SpriteElement => "spriteElement",
        InfiniVfxRendererKind.TexturedPath => "texturedPath",
        InfiniVfxRendererKind.SpriteStampTrail => "spriteStampTrail",
        InfiniVfxRendererKind.HistoryRibbon => "historyRibbon",
        InfiniVfxRendererKind.TipTrail => "tipTrail",
        InfiniVfxRendererKind.GhostArc => "ghostArc",
        InfiniVfxRendererKind.WavyStrip => "wavyStrip",
        InfiniVfxRendererKind.BeamLine => "beamLine",
        InfiniVfxRendererKind.FieldPulse => "fieldPulse",
        InfiniVfxRendererKind.OrbitingMotes => "orbitingMotes",
        InfiniVfxRendererKind.ImpactRing => "impactRing",
        InfiniVfxRendererKind.ImpactSprite => "impactSprite",
        InfiniVfxRendererKind.ChildMotes => "childMotes",
        InfiniVfxRendererKind.LightCue => "lightCue",
        InfiniVfxRendererKind.SoundCue => "soundCue",
        _ => "none",
    };

}
