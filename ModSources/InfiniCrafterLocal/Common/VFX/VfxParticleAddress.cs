#nullable enable
using System;

namespace InfiniCrafterLocal.Common.VFX;

public enum VfxParticleSystemKind { Auto, Glow, Shard, Smoke, Spark, Dust }

public static class VfxParticleAddress
{
    public const string Auto = "auto";
    public const string Glow = "pl:glow";
    public const string Shard = "pl:shard";
    public const string Smoke = "pl:smoke";
    public const string Spark = "pl:spark";
    public const string Dust = "dust";

    public static VfxParticleSystemKind KindFor(string? address) => Canonical(address) switch
    {
        Glow => VfxParticleSystemKind.Glow, Shard => VfxParticleSystemKind.Shard,
        Smoke => VfxParticleSystemKind.Smoke, Spark => VfxParticleSystemKind.Spark,
        Dust => VfxParticleSystemKind.Dust, _ => VfxParticleSystemKind.Auto,
    };

    public static string Canonical(string? address)
    {
        return address is Auto or Glow or Shard or Smoke or Spark or Dust ? address : Auto;
    }

    public static string Resolve(string? requested, string? rendererKind = null, string? channel = null, string? eventName = null, string? blend = null, string? emissionMode = null)
    {
        string explicitId = Canonical(requested);
        if (explicitId != Auto) return explicitId;

        InfiniVfxRendererKind kind = VfxRendererRegistry.ParseKind(rendererKind);
        string c = (channel ?? "").Trim();
        string e = VfxCanonicalVocabulary.Event(eventName);
        string m = VfxCanonicalVocabulary.EmissionMode(emissionMode, kind, c, e);

        if (kind == InfiniVfxRendererKind.SoundCue) return Dust;
        if (kind is InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.BeamLine or InfiniVfxRendererKind.FieldPulse
            or InfiniVfxRendererKind.HistoryRibbon or InfiniVfxRendererKind.TipTrail or InfiniVfxRendererKind.GhostArc
            or InfiniVfxRendererKind.WavyStrip or InfiniVfxRendererKind.ProjectileAfterimage or InfiniVfxRendererKind.SpriteStampTrail)
            return Glow;
        if (kind == InfiniVfxRendererKind.ChildMotes)
        {
            if (c == "decaySmoke" || m == "residue") return Smoke;
            if (c == "impactParticles" || e == "hit") return Shard;
            return Spark;
        }
        if (kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ImpactSprite)
            return c == "impactParticles" ? Shard : Glow;
        if (kind == InfiniVfxRendererKind.OrbitingMotes) return Spark;
        if (e is "kill" or "expire") return Smoke;
        if (e == "hit") return Shard;
        if (c == "ambientParticles") return Spark;
        return Glow;
    }

    public static bool IsPointSystem(string? address) => KindFor(address) == VfxParticleSystemKind.Spark;
}
