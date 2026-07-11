#nullable enable
using InfiniCrafterLocal.Common.Models;
using System;

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

    public static string NormalizeKindName(string? rendererKind, string? renderer = null, string? eventName = null)
        => ToWireName(ParseKind(rendererKind));

    public static string NormalizeEventGroup(string? eventGroup, string? eventName)
        => eventGroup is "live" or "hit" or "kill" ? eventGroup : VfxCanonicalVocabulary.EventGroup(eventName);

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

    public static int EstimateDrawCost(InfiniVfxRendererKind kind, VfxSlotSpec slot)
    {
        float d = Math.Clamp(slot?.Density ?? 0.35f, 0f, 1f);
        return kind switch
        {
            InfiniVfxRendererKind.ProjectileAfterimage => Math.Clamp((int)MathF.Round(2 + d * 7), 2, 12),
            InfiniVfxRendererKind.SpriteStampTrail => Math.Clamp((int)MathF.Round(3 + d * 9), 3, 14),
            InfiniVfxRendererKind.TipTrail => Math.Clamp((int)MathF.Round(3 + d * 12), 3, 22),
            InfiniVfxRendererKind.HistoryRibbon => Math.Clamp((int)MathF.Round(4 + d * 18), 4, 28),
            InfiniVfxRendererKind.GhostArc => Math.Clamp((int)MathF.Round(3 + d * 8), 3, 12),
            InfiniVfxRendererKind.WavyStrip => Math.Clamp((int)MathF.Round(8 + d * 16), 8, 32),
            InfiniVfxRendererKind.BeamLine => 2,
            InfiniVfxRendererKind.FieldPulse => 1,
            InfiniVfxRendererKind.OrbitingMotes => Math.Clamp((int)MathF.Round(2 + d * 8), 2, 12),
            InfiniVfxRendererKind.ActorAfterimage => Math.Clamp((int)MathF.Round(1 + d * 4), 1, 5),
            InfiniVfxRendererKind.ImpactRing => Math.Clamp((int)MathF.Round(8 + d * 12), 8, 24),
            InfiniVfxRendererKind.ImpactSprite => (slot?.Variant ?? 0) >= 3 ? 4 : 1,
            InfiniVfxRendererKind.ChildMotes => Math.Clamp((int)MathF.Round(2 + d * 10), 2, 14),
            InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.SoundCue => 0,
            _ => 0,
        };
    }
}
