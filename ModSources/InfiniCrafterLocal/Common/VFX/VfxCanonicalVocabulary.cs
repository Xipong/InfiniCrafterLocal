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

}
