#nullable enable
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.VFX;

public enum InfiniVfxRendererKind
{
    None, ProjectileAfterimage, SpriteStampTrail, HistoryRibbon, TipTrail, GhostArc, WavyStrip,
    BeamLine, FieldPulse, OrbitingMotes, ActorAfterimage, ImpactRing, ImpactSprite, ChildMotes,
    LightCue, SoundCue
}

/// <summary>Exact renderer registry. Runtime never classifies prose or fuzzy renderer text.</summary>
public static class VfxRendererRegistry
{
    public static InfiniVfxRendererKind Resolve(VfxSlotSpec? slot)
        => slot is null ? InfiniVfxRendererKind.None : ParseKind(slot.RendererKind);

    public static InfiniVfxRendererKind Resolve(string? rendererKind, string? eventName = null)
        => ParseKind(rendererKind);

    public static InfiniVfxRendererKind ParseKind(string? value)
    {
        return value switch
        {
            "projectileAfterimage" => InfiniVfxRendererKind.ProjectileAfterimage,
            "spriteStampTrail" => InfiniVfxRendererKind.SpriteStampTrail,
            "historyRibbon" => InfiniVfxRendererKind.HistoryRibbon,
            "tipTrail" => InfiniVfxRendererKind.TipTrail,
            "ghostArc" => InfiniVfxRendererKind.GhostArc,
            "wavyStrip" => InfiniVfxRendererKind.WavyStrip,
            "beamLine" => InfiniVfxRendererKind.BeamLine,
            "fieldPulse" => InfiniVfxRendererKind.FieldPulse,
            "orbitingMotes" => InfiniVfxRendererKind.OrbitingMotes,
            "actorAfterimage" => InfiniVfxRendererKind.ActorAfterimage,
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
        InfiniVfxRendererKind.ProjectileAfterimage => "projectileAfterimage",
        InfiniVfxRendererKind.SpriteStampTrail => "spriteStampTrail",
        InfiniVfxRendererKind.HistoryRibbon => "historyRibbon",
        InfiniVfxRendererKind.TipTrail => "tipTrail",
        InfiniVfxRendererKind.GhostArc => "ghostArc",
        InfiniVfxRendererKind.WavyStrip => "wavyStrip",
        InfiniVfxRendererKind.BeamLine => "beamLine",
        InfiniVfxRendererKind.FieldPulse => "fieldPulse",
        InfiniVfxRendererKind.OrbitingMotes => "orbitingMotes",
        InfiniVfxRendererKind.ActorAfterimage => "actorAfterimage",
        InfiniVfxRendererKind.ImpactRing => "impactRing",
        InfiniVfxRendererKind.ImpactSprite => "impactSprite",
        InfiniVfxRendererKind.ChildMotes => "childMotes",
        InfiniVfxRendererKind.LightCue => "lightCue",
        InfiniVfxRendererKind.SoundCue => "soundCue",
        _ => "none",
    };

}
