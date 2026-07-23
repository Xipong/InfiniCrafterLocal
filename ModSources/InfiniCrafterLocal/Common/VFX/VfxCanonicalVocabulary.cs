#nullable enable
namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Exact current VFX wire vocabulary. This class validates finite enum-like fields only.
/// It never classifies prose, names, tags, materials or legacy spellings.
/// </summary>
public static class VfxCanonicalVocabulary
{
    public static string Event(string? value)
        => value is "travel" or "active" or "tick" or "hit" or "kill" or "expire"
            or "while_held" or "while_equipped" or "on_use" or "on_alt_use" ? value : "tick";

    public static string EventGroup(string? eventName)
        => Event(eventName) switch
        {
            "while_held" or "while_equipped" => "item_live",
            "on_use" or "on_alt_use" => "item_use",
            "hit" => "hit",
            "kill" or "expire" => "kill",
            _ => "live",
        };

    public static string Stage(string? eventName)
        => Event(eventName) switch
        {
            "on_use" or "on_alt_use" => "active",
            "while_held" or "while_equipped" => "loop",
            "active" => "active",
            "hit" => "impact",
            "kill" or "expire" => "decay",
            _ => "loop",
        };

    public static string Channel(string? value, InfiniVfxRendererKind kind, string? eventName)
    {
        if (value is "motionTrail" or "coreGlow" or "ambientParticles" or "impactShape" or
            "impactParticles" or "decaySmoke" or "light" or "sound")
            return value;

        if (kind == InfiniVfxRendererKind.SoundCue) return "sound";
        if (kind == InfiniVfxRendererKind.LightCue) return "light";
        if (kind is InfiniVfxRendererKind.ProjectileAfterimage or InfiniVfxRendererKind.SpriteStampTrail or
            InfiniVfxRendererKind.HistoryRibbon or InfiniVfxRendererKind.TipTrail or InfiniVfxRendererKind.GhostArc or
            InfiniVfxRendererKind.WavyStrip or InfiniVfxRendererKind.BeamLine)
            return "motionTrail";
        if (kind is InfiniVfxRendererKind.FieldPulse or InfiniVfxRendererKind.OrbitingMotes or InfiniVfxRendererKind.ActorAfterimage)
            return "coreGlow";
        if (kind == InfiniVfxRendererKind.ChildMotes)
            return EventGroup(eventName) is "live" or "item_live" ? "ambientParticles" : EventGroup(eventName) == "kill" ? "decaySmoke" : "impactParticles";
        if (kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ImpactSprite)
            return "impactShape";
        return EventGroup(eventName) is "live" or "item_live" ? "motionTrail" : "impactShape";
    }

    public static string Importance(string? value)
        => value is "core" or "secondary" or "accent" or "luxury" ? value : "secondary";

    public static string Lane(string? value, string channel, string importance, InfiniVfxRendererKind kind)
    {
        if (value is "primary" or "support" or "accent" or "ornament" or "cue")
            return value;
        if (channel is "light" or "sound" || kind is InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.SoundCue)
            return "cue";
        return Importance(importance) switch
        {
            "core" => "primary",
            "secondary" => "support",
            "accent" => "accent",
            "luxury" => "ornament",
            _ => "support",
        };
    }

    public static string EmissionMode(string? value, InfiniVfxRendererKind kind, string channel, string? eventName)
    {
        if (value is "wake" or "orbit" or "residue" or "burst" or "cone" or "ring" or "spiral" or "point")
            return value;
        if (kind == InfiniVfxRendererKind.OrbitingMotes) return "orbit";
        if (kind == InfiniVfxRendererKind.ImpactRing) return "ring";
        if (EventGroup(eventName) == "kill" || channel == "decaySmoke") return "residue";
        if (EventGroup(eventName) == "hit") return "burst";
        return "wake";
    }

    public static string Anchor(string? value, InfiniVfxRendererKind kind, string channel, string? eventName)
    {
        if (value is "self" or "owner" or "tip" or "tipHistory" or "hitPoint" or "velocity" or "field")
            return value;
        if (EventGroup(eventName) is not ("live" or "item_live")) return "hitPoint";
        if (kind is InfiniVfxRendererKind.TipTrail or InfiniVfxRendererKind.HistoryRibbon or InfiniVfxRendererKind.GhostArc)
            return "tipHistory";
        if (kind == InfiniVfxRendererKind.BeamLine) return "velocity";
        if (kind == InfiniVfxRendererKind.FieldPulse) return "field";
        return channel == "motionTrail" ? "tip" : "self";
    }

    public static string Curve(string? value)
        => value is "smooth" or "linear" or "sharp" ? value : "smooth";

    public static string Blend(string? value, InfiniVfxRendererKind kind, string channel)
    {
        if (value is "alpha" or "additive") return value;
        return channel is "coreGlow" or "light" || kind is InfiniVfxRendererKind.BeamLine or InfiniVfxRendererKind.LightCue
            ? "additive" : "alpha";
    }

    public static string Backend(string? value)
        => value is "Auto" or "Baked" or "Realtime" or "Primitive" or "Sprite" or "Particle" ? value : "Auto";
}
