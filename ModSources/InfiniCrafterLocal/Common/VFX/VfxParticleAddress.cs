#nullable enable
using System;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Canonical addressing layer for ParticleLibrary-backed VFX particles.
/// Recipes/manifests should address particle systems explicitly instead of relying on
/// renderer-string contains checks. The resolver still accepts old fuzzy ids for compat.
/// </summary>
public enum VfxParticleSystemKind
{
    Auto,
    Glow,
    Shard,
    Smoke,
    Spark,
    Dust
}

public static class VfxParticleAddress
{
    public const string Auto = "auto";
    public const string Glow = "pl:glow";
    public const string Shard = "pl:shard";
    public const string Smoke = "pl:smoke";
    public const string Spark = "pl:spark";
    public const string Dust = "dust";

    public static VfxParticleSystemKind KindFor(string? address)
    {
        string id = Canonical(address);
        return id switch
        {
            Glow => VfxParticleSystemKind.Glow,
            Shard => VfxParticleSystemKind.Shard,
            Smoke => VfxParticleSystemKind.Smoke,
            Spark => VfxParticleSystemKind.Spark,
            Dust => VfxParticleSystemKind.Dust,
            _ => VfxParticleSystemKind.Auto
        };
    }

    public static string Canonical(string? address)
    {
        string id = (address ?? "").Trim().ToLowerInvariant();
        if (id.Length == 0 || id == "auto" || id == "default")
            return Auto;

        id = id.Replace("_", "-").Replace(" ", "-");

        return id switch
        {
            "pl:glow" or "particlelibrary:glow" or "glow" or "soft-glow" or "softglow" or "additive" or "additive-glow" or "soul" or "soul-glow" or "magic" or "magic-glow" => Glow,
            "pl:shard" or "particlelibrary:shard" or "shard" or "shards" or "debris" or "fragment" or "fragments" or "burst" or "hit-burst" => Shard,
            "pl:smoke" or "particlelibrary:smoke" or "smoke" or "smoky" or "ash" or "cloud" or "decay" or "residue" or "fog" => Smoke,
            "pl:spark" or "particlelibrary:spark" or "spark" or "sparks" or "point" or "points" or "glint" or "star" or "stars" or "twinkle" => Spark,
            "vanilla:dust" or "dust" or "fallback" => Dust,
            _ => id.StartsWith("pl:", StringComparison.Ordinal) ? id : Auto
        };
    }

    public static string Resolve(string? requested, string? renderer = null, string? channel = null, string? eventName = null, string? blend = null, string? emissionMode = null)
    {
        string canonical = Canonical(requested);
        if (canonical is Glow or Shard or Smoke or Spark)
            return canonical;

        string r = (renderer ?? "").ToLowerInvariant();
        string c = (channel ?? "").ToLowerInvariant();
        string e = (eventName ?? "").ToLowerInvariant();
        string b = (blend ?? "").ToLowerInvariant();
        string m = (emissionMode ?? "").ToLowerInvariant();

        if (r.Contains("sound") || c == "sound")
            return Dust;
        if (r.Contains("light") || c == "light")
            return Glow;
        if (m.Contains("residue") || r.Contains("smoke") || r.Contains("decay") || r.Contains("cloud") || c == "decaysmoke")
            return Smoke;
        if (r.Contains("spark") || r.Contains("glint") || r.Contains("star") || m.Contains("spark"))
            return Spark;
        if ((r.Contains("mote") || r.Contains("particle")) && c == "ambientparticles")
            return Spark;
        if ((r.Contains("mote") || r.Contains("particle")) && c == "decaysmoke")
            return Smoke;
        if (r.Contains("flash") || r.Contains("pulse") || r.Contains("field"))
            return Glow;
        if (r.Contains("ring") && (b.Contains("add") || c == "coreglow" || e is "hit" or "impact"))
            return Glow;
        if (r.Contains("shard") || r.Contains("debris") || r.Contains("burst") || c == "impactparticles")
            return Shard;
        if (b.Contains("add") || r.Contains("glow") || r.Contains("beam") || r.Contains("ribbon") || r.Contains("trail") || c == "coreglow")
            return Glow;
        if (e is "hit" or "impact" or "onhit")
            return Shard;
        if (e is "kill" or "expire" or "decay")
            return Smoke;
        if (c == "ambientparticles")
            return Spark;

        return canonical == Dust ? Dust : Glow;
    }

    public static bool IsPointSystem(string? address) => KindFor(address) == VfxParticleSystemKind.Spark;
}
