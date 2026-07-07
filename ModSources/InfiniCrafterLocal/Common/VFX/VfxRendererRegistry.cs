#nullable enable
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using System;

namespace InfiniCrafterLocal.Common.VFX;

public enum InfiniVfxRendererKind
{
    None,
    ProjectileAfterimage,
    SpriteStampTrail,
    HistoryRibbon,
    TipTrail,
    GhostArc,
    WavyStrip,
    BeamLine,
    FieldPulse,
    OrbitingMotes,
    ActorAfterimage,
    ImpactRing,
    ImpactSprite,
    ChildMotes,
    LightCue,
    SoundCue
}

/// <summary>
/// Tiny renderer registry layer for the manifest runtime.
/// It turns fuzzy manifest renderer names into finite renderer ids and draw-cost estimates.
/// C# still contains the actual renderer implementations, but the dispatch table is no longer
/// an ever-growing if/else block inside Draw().
/// </summary>
public static class VfxRendererRegistry
{
    public static InfiniVfxRendererKind Resolve(VfxSlotSpec? slot)
    {
        if (slot is null)
            return InfiniVfxRendererKind.None;
        var parsed = ParseKind(slot.RendererKind);
        return parsed == InfiniVfxRendererKind.None
            ? Resolve(slot.Renderer, slot.Event)
            : parsed;
    }

    public static InfiniVfxRendererKind Resolve(string? renderer, string? eventName = null)
    {
        string r = (renderer ?? "").ToLowerInvariant();
        string e = (eventName ?? "").ToLowerInvariant();

        // Fallback only. New manifests should pass rendererKind so runtime does not depend on fuzzy text.
        // v0.4.117: keep steady light, but do not route fuzzy "light flash" wording
        // into either world-light pulses or blinking impact sprites. Those phrases
        // are visual prose, not an executable light renderer. Real constant light is
        // still allowed through explicit live channel=light / rendererKind=lightCue.
        bool proseLightFlash = (r.Contains("light") || r.Contains("highlight"))
            && (r.Contains("flash") || r.Contains("flicker") || r.Contains("blink") || r.Contains("pulse"));
        if (proseLightFlash) return InfiniVfxRendererKind.None;
        if (r.Contains("sound")) return InfiniVfxRendererKind.SoundCue;
        if (r.Contains("afterimage")) return InfiniVfxRendererKind.ProjectileAfterimage;
        if (r.Contains("stamp")) return InfiniVfxRendererKind.SpriteStampTrail;
        if (r.Contains("tiptrail")) return InfiniVfxRendererKind.TipTrail;
        if (r.Contains("history") || r.Contains("primitive") || r.Contains("ribbon")) return InfiniVfxRendererKind.HistoryRibbon;
        if (r.Contains("ghost")) return InfiniVfxRendererKind.GhostArc;
        if (r.Contains("wavy") || r.Contains("cloth")) return InfiniVfxRendererKind.WavyStrip;
        if (r.Contains("beam")) return InfiniVfxRendererKind.BeamLine;
        if (r.Contains("field")) return InfiniVfxRendererKind.FieldPulse;
        if (r.Contains("orbital") || r.Contains("orbit")) return InfiniVfxRendererKind.OrbitingMotes;
        if (r.Contains("actor") || r.Contains("playerghost")) return InfiniVfxRendererKind.ActorAfterimage;

        if (r.Contains("ring")) return InfiniVfxRendererKind.ImpactRing;
        if (r.Contains("child") || r.Contains("mote")) return InfiniVfxRendererKind.ChildMotes;
        if (r.Contains("flash") || r.Contains("burst") || r.Contains("impact")) return InfiniVfxRendererKind.ImpactSprite;
        if (r == "light" || r == "lightcue" || r == "light_cue" || r.Contains("lightcue") || r.Contains("light_cue")) return InfiniVfxRendererKind.LightCue;

        if (e is "hit" or "impact" or "onhit") return InfiniVfxRendererKind.ImpactSprite;
        return InfiniVfxRendererKind.None;
    }

    public static InfiniVfxRendererKind ParseKind(string? value)
    {
        string v = (value ?? "").Trim().ToLowerInvariant().Replace("_", "").Replace("-", "");
        return v switch
        {
            "projectileafterimage" or "afterimage" => InfiniVfxRendererKind.ProjectileAfterimage,
            "spritestamptrail" or "stamptrail" or "stamp" => InfiniVfxRendererKind.SpriteStampTrail,
            "historyribbon" or "primitiveribbon" or "ribbon" or "history" => InfiniVfxRendererKind.HistoryRibbon,
            "tiptrail" => InfiniVfxRendererKind.TipTrail,
            "ghostarc" or "ghost" => InfiniVfxRendererKind.GhostArc,
            "wavystrip" or "cloth" => InfiniVfxRendererKind.WavyStrip,
            "beamline" or "beam" => InfiniVfxRendererKind.BeamLine,
            "fieldpulse" or "field" => InfiniVfxRendererKind.FieldPulse,
            "orbitingmotes" or "orbitalmotes" or "orbit" => InfiniVfxRendererKind.OrbitingMotes,
            "actorafterimage" or "actorecho" => InfiniVfxRendererKind.ActorAfterimage,
            "impactring" or "ring" => InfiniVfxRendererKind.ImpactRing,
            "impactsprite" or "impact" or "impactflash" or "impactburst" => InfiniVfxRendererKind.ImpactSprite,
            "lightflash" or "highlightflash" or "lightpulse" or "lightflicker" or "blinklight" => InfiniVfxRendererKind.None,
            "childmotes" or "motes" => InfiniVfxRendererKind.ChildMotes,
            "lightcue" or "light" => InfiniVfxRendererKind.LightCue,
            "soundcue" or "sound" => InfiniVfxRendererKind.SoundCue,
            _ => InfiniVfxRendererKind.None
        };
    }

    public static string NormalizeKindName(string? rendererKind, string? renderer, string? eventName = null)
    {
        var kind = ParseKind(rendererKind);
        if (kind == InfiniVfxRendererKind.None)
            kind = Resolve(renderer, eventName);
        return ToWireName(kind);
    }

    public static string NormalizeEventGroup(string? eventGroup, string? eventName)
    {
        string g = (eventGroup ?? "").Trim().ToLowerInvariant();
        if (g is "live" or "hit" or "kill")
            return g;
        string e = (eventName ?? "").Trim().ToLowerInvariant();
        if (e is "hit" or "impact" or "onhit") return "hit";
        if (e is "kill" or "expire" or "decay") return "kill";
        return "live";
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
        _ => "none"
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
            _ => 0
        };
    }
}
