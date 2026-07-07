#nullable enable
using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

// AGENT MAP: frozen VFX manifest data contract.
// VFX slots/channels/renderers are normalized data for presentation. Effect names
// and motif prose must not become gameplay routing; projectile gameplay remains in
// AttackSpec/runtime codes.
public sealed class VfxManifestSpec
{

// =============================================================================
// NAV TOC: VfxManifestSpec.cs
// =============================================================================
// NAV: VFX_MANIFEST_CONTRACT          frozen generated VFX manifest root
// NAV: VFX_MANIFEST_JSON_NORMALIZE    JSON load/save and root Normalize()
// NAV: VFX_MOTIF_AND_BUDGET           motif, magnitude, emergency budget
// NAV: VFX_SLOT_CONTRACT              staged slot contract: rendererKind/eventGroup/channel/lane
// NAV: VFX_SLOT_NORMALIZATION         channel/lane/emission/stage/anchor inference fallback
// NAV: VFX_BAKED_COMMAND_CONTRACT     inline baked spawn commands
// NAV: VFX_DEBUG_CONTRACT             debug data emitted by Python selector
// =============================================================================

// =============================================================================
// NAV: VFX_MANIFEST_CONTRACT
// =============================================================================
    public string Schema { get; set; } = "infini.vfx.hybrid.v14";
    public string RecipeId { get; set; } = "";
    public string EffectName { get; set; } = ""; // debug/style only; runtime must not parse this
    public string[] InspirationNames { get; set; } = Array.Empty<string>(); // debug/style only
    public string PlaybackMode { get; set; } = "Hybrid"; // Baked, Realtime, Hybrid, Auto
    public int Seed { get; set; } = 0;
    public float Confidence { get; set; } = 0f;
    public float EffectMagnitude { get; set; } = 0.5f;
    public string VisualBudgetClass { get; set; } = "normal";
    public VfxMotifSpec Motif { get; set; } = new();
    public VfxQualityBudgetSpec Budget { get; set; } = new();
    public VfxSlotSpec[] Slots { get; set; } = Array.Empty<VfxSlotSpec>();
    public string OverlayPolicy { get; set; } = "LocalOnly";
    public VfxDebugSpec Debug { get; set; } = new();


// =============================================================================
// NAV: VFX_MANIFEST_JSON_NORMALIZE
// =============================================================================
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false
    };

    public bool HasSlots => Slots is { Length: > 0 };

    public static VfxManifestSpec Empty() => new();

    public static VfxManifestSpec FromJson(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
            return Empty();
        try
        {
            var parsed = JsonSerializer.Deserialize<VfxManifestSpec>(json, Options) ?? Empty();
            parsed.Normalize();
            return parsed;
        }
        catch
        {
            return Empty();
        }
    }

    public string ToJson()
    {
        Normalize();
        try { return JsonSerializer.Serialize(this, Options); }
        catch { return ""; }
    }

    public void Normalize()
    {
        Schema = string.IsNullOrWhiteSpace(Schema) ? "infini.vfx.hybrid.v14" : Schema;
        RecipeId ??= "";
        EffectName ??= "";
        InspirationNames ??= Array.Empty<string>();
        PlaybackMode = string.IsNullOrWhiteSpace(PlaybackMode) ? "Hybrid" : PlaybackMode;
        Budget ??= new VfxQualityBudgetSpec();
        Budget.Normalize();
        EffectMagnitude = Math.Clamp(EffectMagnitude <= 0f ? Budget.EffectMagnitude : EffectMagnitude, 0f, 1f);
        VisualBudgetClass = string.IsNullOrWhiteSpace(VisualBudgetClass) ? MagnitudeClass(EffectMagnitude) : VisualBudgetClass;
        OverlayPolicy = string.IsNullOrWhiteSpace(OverlayPolicy) ? "LocalOnly" : OverlayPolicy;
        Motif ??= new VfxMotifSpec();
        Motif.Normalize();
        Slots ??= Array.Empty<VfxSlotSpec>();
        Debug ??= new VfxDebugSpec();
        foreach (var slot in Slots)
            slot?.Normalize();
    }

    private static string MagnitudeClass(float value)
    {
        if (value < 0.22f) return "tiny";
        if (value < 0.42f) return "small";
        if (value < 0.66f) return "normal";
        if (value < 0.86f) return "large";
        return "signature";
    }
}



// =============================================================================
// NAV: VFX_MOTIF_AND_BUDGET
// =============================================================================
public sealed class VfxMotifSpec
{
    public string Element { get; set; } = "neutral";
    public string ShapeLanguage { get; set; } = "generic";
    public string MotionLanguage { get; set; } = "forward";
    public string PaletteRole { get; set; } = "primary";
    public float Rhythm { get; set; } = 1f;
    public float Chaos { get; set; } = 0.25f;

    public void Normalize()
    {
        Element = string.IsNullOrWhiteSpace(Element) ? "neutral" : Element.Trim();
        ShapeLanguage = string.IsNullOrWhiteSpace(ShapeLanguage) ? "generic" : ShapeLanguage.Trim();
        MotionLanguage = string.IsNullOrWhiteSpace(MotionLanguage) ? "forward" : MotionLanguage.Trim();
        PaletteRole = string.IsNullOrWhiteSpace(PaletteRole) ? "primary" : PaletteRole.Trim();
        Rhythm = Math.Clamp(Rhythm <= 0f ? 1f : Rhythm, 0.2f, 3.0f);
        Chaos = Math.Clamp(Chaos, 0f, 1f);
    }
}

public sealed class VfxQualityBudgetSpec
{
    public float EffectMagnitude { get; set; } = 0.5f;
    public string VisualBudgetClass { get; set; } = "normal";
    public bool EmergencyCap { get; set; } = true;
    public int MaxParticlesPerTick { get; set; } = 240;
    public int MaxParticlesTotal { get; set; } = 9000;
    public int MaxDrawCalls { get; set; } = 420;
    public float SpawnRateMultiplier { get; set; } = 1.5f;
    public bool EnableSoftGlow { get; set; } = true;
    public bool EnablePointSparks { get; set; } = true;
    public bool EnablePersistentSmoke { get; set; } = true;

    public void Normalize()
    {
        EffectMagnitude = Math.Clamp(EffectMagnitude <= 0f ? 0.5f : EffectMagnitude, 0f, 1f);
        VisualBudgetClass = string.IsNullOrWhiteSpace(VisualBudgetClass) ? MagnitudeClass(EffectMagnitude) : VisualBudgetClass;
        MaxParticlesPerTick = Math.Clamp(MaxParticlesPerTick <= 0 ? 240 : MaxParticlesPerTick, 0, 512);
        MaxParticlesTotal = Math.Clamp(MaxParticlesTotal <= 0 ? 9000 : MaxParticlesTotal, 0, 20000);
        MaxDrawCalls = Math.Clamp(MaxDrawCalls <= 0 ? 420 : MaxDrawCalls, 0, 1200);
        SpawnRateMultiplier = Math.Clamp(SpawnRateMultiplier <= 0f ? 1.5f : SpawnRateMultiplier, 0f, 4.0f);
    }

    private static string MagnitudeClass(float value)
    {
        if (value < 0.22f) return "tiny";
        if (value < 0.42f) return "small";
        if (value < 0.66f) return "normal";
        if (value < 0.86f) return "large";
        return "signature";
    }
}


// =============================================================================
// NAV: VFX_SLOT_CONTRACT
// =============================================================================
public sealed class VfxSlotSpec
{
    public string Event { get; set; } = "tick";
    public string EffectName { get; set; } = ""; // optional debug/style label; runtime must not parse this
    public string EventGroup { get; set; } = "auto"; // live/hit/kill; canonical lifecycle group precompiled by Python.
    public string Stage { get; set; } = "loop"; // windup, active, impact, decay, loop
    public string Backend { get; set; } = "Auto"; // Baked, Realtime, Primitive, Sprite, Particle, Auto
    public string Renderer { get; set; } = "projectileAfterimage";
    public string RendererKind { get; set; } = "auto"; // canonical renderer id; runtime should prefer this over fuzzy Renderer text.
    public string TextureRole { get; set; } = "projectile";
    public string ParticleRole { get; set; } = "child";
    public string Anchor { get; set; } = "self"; // self, owner, tip, tipHistory, hitPoint, velocity, field
    public string Blend { get; set; } = "alpha"; // alpha/additive, advisory for future backends
    public string Layer { get; set; } = "BeforeProjectiles";
    public string Channel { get; set; } = "auto"; // motionTrail/coreGlow/ambientParticles/impactShape/impactParticles/decaySmoke/light/sound
    public string Lane { get; set; } = "auto"; // primary/support/accent/ornament/cue; lets multiple compatible slots share a channel without becoming equal-weight spam.
    public string Source { get; set; } = "recipe"; // recipe, macro, blend:<id>, procedural:<kind>; debug only, runtime-safe.
    public string EmissionMode { get; set; } = "auto"; // wake/orbit/residue/burst/cone/ring/spiral
    public string ParticleSystemId { get; set; } = "auto"; // pl:glow/pl:shard/pl:smoke/pl:spark/dust; explicit ParticleLibrary routing address.
    public float FadeIn { get; set; } = 0.15f;
    public float FadeOut { get; set; } = 0.35f;
    public string Curve { get; set; } = "smooth";
    public int SlotSeed { get; set; } = 0;
    public int Variant { get; set; } = 0;
    public int StartTick { get; set; } = 0;
    public int RepeatEvery { get; set; } = 0;
    public float Scale { get; set; } = 1f;
    public float Density { get; set; } = 0.35f;
    public int Duration { get; set; } = 10;
    public float Alpha { get; set; } = 0.65f;
    public float Spread { get; set; } = 0.5f;
    public float Jitter { get; set; } = 0.35f;
    public float PhaseOffset { get; set; } = 0f;
    public float BudgetWeight { get; set; } = 1f;
    public string Importance { get; set; } = "secondary"; // core/secondary/accent/luxury
    public float VisualCost { get; set; } = 0.25f;
    public float SignatureWeight { get; set; } = 0.45f;
    public string BakedClipId { get; set; } = "";
    public string BakedClipHash { get; set; } = "";
    public int BakedCommandCount { get; set; } = 0;
    public VfxBakedCommandSpec[] BakedCommands { get; set; } = Array.Empty<VfxBakedCommandSpec>();

    public void Normalize()
    {
        Event = string.IsNullOrWhiteSpace(Event) ? "tick" : Event;
        EffectName ??= "";
        EventGroup = VfxRendererRegistry.NormalizeEventGroup(EventGroup, Event);
        Stage = string.IsNullOrWhiteSpace(Stage) ? StageForEvent(Event) : Stage;
        Backend = string.IsNullOrWhiteSpace(Backend) ? "Auto" : Backend;
        Renderer = string.IsNullOrWhiteSpace(Renderer) ? "projectileAfterimage" : Renderer;
        RendererKind = VfxRendererRegistry.NormalizeKindName(RendererKind, Renderer, Event);
        TextureRole = string.IsNullOrWhiteSpace(TextureRole) ? "projectile" : TextureRole;
        ParticleRole = string.IsNullOrWhiteSpace(ParticleRole) ? TextureRole : ParticleRole;
        Anchor = string.IsNullOrWhiteSpace(Anchor) ? AnchorForRenderer(Renderer, Event) : Anchor;
        Blend = string.IsNullOrWhiteSpace(Blend) ? "alpha" : Blend;
        Layer = string.IsNullOrWhiteSpace(Layer) ? "BeforeProjectiles" : Layer;
        Channel = NormalizeChannel(Channel, Renderer, Event);
        Lane = NormalizeLane(Lane, Channel, Importance, Renderer, Event);
        Source = string.IsNullOrWhiteSpace(Source) ? "recipe" : Source.Trim();
        EmissionMode = NormalizeEmissionMode(EmissionMode, Renderer, Event);
        ParticleSystemId = VfxParticleAddress.Resolve(ParticleSystemId, Renderer, Channel, Event, Blend, EmissionMode);
        FadeIn = Math.Clamp(FadeIn <= 0f ? 0.15f : FadeIn, 0f, 0.95f);
        FadeOut = Math.Clamp(FadeOut <= 0f ? 0.35f : FadeOut, 0f, 0.95f);
        Curve = string.IsNullOrWhiteSpace(Curve) ? "smooth" : Curve.Trim().ToLowerInvariant();
        SlotSeed = SlotSeed == 0 ? StableSlotSeed(Renderer, Event, Channel, Lane, Variant) : SlotSeed;
        StartTick = Math.Clamp(StartTick, 0, 600);
        RepeatEvery = Math.Clamp(RepeatEvery, 0, 600);
        Scale = Math.Clamp(Scale <= 0f ? 1f : Scale, 0.05f, 8f);
        Density = Math.Clamp(Density, 0f, 1f);
        Duration = Math.Clamp(Duration <= 0 ? 10 : Duration, 1, 240);
        Alpha = Math.Clamp(Alpha <= 0f ? 0.65f : Alpha, 0f, 1f);
        Spread = Math.Clamp(Spread, 0f, 3f);
        Jitter = Math.Clamp(Jitter, 0f, 2f);
        PhaseOffset = Math.Clamp(PhaseOffset, -2f, 2f);
        BudgetWeight = Math.Clamp(BudgetWeight <= 0f ? 1f : BudgetWeight, 0.05f, 8f);
        Importance = NormalizeImportance(Importance);
        VisualCost = Math.Clamp(VisualCost, 0f, 1f);
        SignatureWeight = Math.Clamp(SignatureWeight, 0f, 1f);
        BakedClipId ??= "";
        BakedClipHash ??= "";
        BakedCommands ??= Array.Empty<VfxBakedCommandSpec>();
        BakedCommandCount = BakedCommandCount <= 0 ? BakedCommands.Length : Math.Max(BakedCommandCount, BakedCommands.Length);
        foreach (var cmd in BakedCommands)
            cmd?.Normalize();
    }


// =============================================================================
// NAV: VFX_SLOT_NORMALIZATION
// =============================================================================
    private static string NormalizeChannel(string? channel, string? renderer, string? ev)
    {
        string c = string.IsNullOrWhiteSpace(channel) ? "auto" : channel.Trim().ToLowerInvariant();
        return c switch
        {
            "motiontrail" or "trail" or "motion" => "motionTrail",
            "coreglow" or "glow" or "core" => "coreGlow",
            "ambientparticles" or "ambient" or "particles" => "ambientParticles",
            "impactshape" or "impact" or "shape" => "impactShape",
            "impactparticles" or "hitparticles" => "impactParticles",
            "decaysmoke" or "decay" or "smoke" => "decaySmoke",
            "light" => "light",
            "sound" => "sound",
            _ => InferChannel(renderer, ev)
        };
    }

    private static string InferChannel(string? renderer, string? ev)
    {
        var kind = VfxRendererRegistry.Resolve(renderer, ev);
        if (kind == InfiniVfxRendererKind.SoundCue) return "sound";
        if (kind == InfiniVfxRendererKind.LightCue) return "light";
        if (kind is InfiniVfxRendererKind.ProjectileAfterimage or InfiniVfxRendererKind.SpriteStampTrail or InfiniVfxRendererKind.HistoryRibbon or InfiniVfxRendererKind.TipTrail or InfiniVfxRendererKind.GhostArc or InfiniVfxRendererKind.WavyStrip or InfiniVfxRendererKind.BeamLine)
            return "motionTrail";
        if (kind is InfiniVfxRendererKind.FieldPulse or InfiniVfxRendererKind.OrbitingMotes or InfiniVfxRendererKind.ActorAfterimage)
            return "coreGlow";
        if (kind == InfiniVfxRendererKind.ChildMotes)
            return IsHitLike(ev) ? "impactParticles" : "ambientParticles";
        if (kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ImpactSprite)
            return IsKillLike(ev) ? "impactShape" : "impactShape";
        return IsHitLike(ev) ? "impactShape" : "motionTrail";
    }

    private static bool IsHitLike(string? ev)
    {
        string e = (ev ?? "").ToLowerInvariant();
        return e is "hit" or "impact" or "onhit";
    }

    private static bool IsKillLike(string? ev)
    {
        string e = (ev ?? "").ToLowerInvariant();
        return e is "kill" or "expire" or "decay";
    }

    private static string NormalizeLane(string? lane, string? channel, string? importance, string? renderer, string? ev)
    {
        string l = string.IsNullOrWhiteSpace(lane) ? "auto" : lane.Trim().ToLowerInvariant();
        return l switch
        {
            "main" or "primary" or "core" => "primary",
            "support" or "secondary" => "support",
            "accent" => "accent",
            "ornament" or "luxury" or "extra" => "ornament",
            "cue" => "cue",
            _ => InferLane(channel, importance, renderer, ev)
        };
    }

    private static string InferLane(string? channel, string? importance, string? renderer, string? ev)
    {
        string c = (channel ?? "").Trim();
        string i = (importance ?? "").Trim().ToLowerInvariant();
        var kind = VfxRendererRegistry.Resolve(renderer, ev);
        if (c == "light" || c == "sound" || kind is InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.SoundCue)
            return "cue";
        if (i == "core")
            return "primary";
        if (i == "secondary")
            return "support";
        if (i == "luxury")
            return "ornament";
        if (i == "accent")
            return "accent";
        if (kind is InfiniVfxRendererKind.ImpactRing or InfiniVfxRendererKind.ImpactSprite)
            return "support";
        if (kind is InfiniVfxRendererKind.ChildMotes or InfiniVfxRendererKind.OrbitingMotes)
            return "accent";
        return "primary";
    }

    private static string NormalizeEmissionMode(string? value, string? renderer, string? ev)
    {
        string v = string.IsNullOrWhiteSpace(value) ? "auto" : value.Trim().ToLowerInvariant();
        if (v is "wake" or "orbit" or "residue" or "burst" or "cone" or "ring" or "spiral" or "point")
            return v;
        string r = (renderer ?? "").ToLowerInvariant();
        string e = (ev ?? "").ToLowerInvariant();
        if (r.Contains("orbital") || r.Contains("orbit")) return "orbit";
        if (e is "hit" or "impact" or "onhit") return r.Contains("ring") ? "ring" : "burst";
        if (e is "kill" or "expire" or "decay") return "residue";
        if (r.Contains("beam")) return "wake";
        return "wake";
    }

    private static int StableSlotSeed(string? renderer, string? ev, string? channel, string? lane, int variant)
    {
        unchecked
        {
            int h = 17;
            foreach (char c in (renderer ?? "")) h = h * 31 + c;
            foreach (char c in (ev ?? "")) h = h * 31 + c;
            foreach (char c in (channel ?? "")) h = h * 31 + c;
            foreach (char c in (lane ?? "")) h = h * 31 + c;
            h = h * 31 + variant;
            h &= 0x7fffffff;
            return h == 0 ? 1337 : h;
        }
    }

    private static string StageForEvent(string? ev)
    {
        string e = (ev ?? "").ToLowerInvariant();
        if (e is "hit" or "impact" or "onhit") return "impact";
        if (e is "kill" or "expire" or "decay") return "decay";
        if (e is "active" or "slash" or "beam") return "active";
        if (e is "spawn" or "windup") return "windup";
        return "loop";
    }

    private static string NormalizeImportance(string? value)
    {
        string q = string.IsNullOrWhiteSpace(value) ? "secondary" : value.Trim().ToLowerInvariant();
        return q switch
        {
            "core" or "main" => "core",
            "secondary" or "support" => "secondary",
            "accent" or "decor" => "accent",
            "luxury" or "extra" => "luxury",
            _ => "secondary"
        };
    }

    private static string AnchorForRenderer(string? renderer, string? ev)
    {
        string r = (renderer ?? "").ToLowerInvariant();
        string e = (ev ?? "").ToLowerInvariant();
        if (e is "hit" or "impact" or "onhit") return "hitPoint";
        if (r.Contains("tip") || r.Contains("ribbon") || r.Contains("slash")) return "tipHistory";
        if (r.Contains("beam")) return "velocity";
        if (r.Contains("field")) return "field";
        return "self";
    }
}


// =============================================================================
// NAV: VFX_BAKED_COMMAND_CONTRACT
// =============================================================================
public sealed class VfxBakedCommandSpec
{
    public int Tick { get; set; } = 0;
    public string ParticleSystemId { get; set; } = "dust";
    public string TextureRole { get; set; } = "";
    public float LocalX { get; set; } = 0f;
    public float LocalY { get; set; } = 0f;
    public float VelocityX { get; set; } = 0f;
    public float VelocityY { get; set; } = 0f;
    public string StartColor { get; set; } = "";
    public string EndColor { get; set; } = "";
    public float ScaleX { get; set; } = 1f;
    public float ScaleY { get; set; } = 1f;
    public float ScaleVelocityX { get; set; } = 0f;
    public float ScaleVelocityY { get; set; } = 0f;
    public float Rotation { get; set; } = 0f;
    public float RotationVelocity { get; set; } = 0f;
    public int Lifespan { get; set; } = 18;
    public float Alpha { get; set; } = 0.65f;
    public int SeedBucket { get; set; } = 0;

    public void Normalize()
    {
        Tick = Math.Clamp(Tick, 0, 600);
        ParticleSystemId = VfxParticleAddress.Resolve(ParticleSystemId);
        TextureRole ??= "";
        LocalX = Math.Clamp(LocalX, -8f, 8f);
        LocalY = Math.Clamp(LocalY, -8f, 8f);
        VelocityX = Math.Clamp(VelocityX, -12f, 12f);
        VelocityY = Math.Clamp(VelocityY, -12f, 12f);
        StartColor ??= "";
        EndColor ??= "";
        ScaleX = Math.Clamp(ScaleX <= 0f ? 1f : ScaleX, 0.03f, 8f);
        ScaleY = Math.Clamp(ScaleY <= 0f ? 1f : ScaleY, 0.03f, 8f);
        ScaleVelocityX = Math.Clamp(ScaleVelocityX, -2f, 2f);
        ScaleVelocityY = Math.Clamp(ScaleVelocityY, -2f, 2f);
        Rotation = Math.Clamp(Rotation, -32f, 32f);
        RotationVelocity = Math.Clamp(RotationVelocity, -8f, 8f);
        Lifespan = Math.Clamp(Lifespan <= 0 ? 18 : Lifespan, 1, 240);
        Alpha = Math.Clamp(Alpha <= 0f ? 0.65f : Alpha, 0f, 1f);
        SeedBucket = Math.Clamp(SeedBucket, -100000000, 100000000);
    }
}


// =============================================================================
// NAV: VFX_DEBUG_CONTRACT
// =============================================================================
public sealed class VfxDebugSpec
{
    public string Pattern { get; set; } = "";
    public string[] Roles { get; set; } = Array.Empty<string>();
    public float SelectedScore { get; set; } = 0f;
    public string[] SelectedReasons { get; set; } = Array.Empty<string>();
    public object[] TopCandidates { get; set; } = Array.Empty<object>();
    public string[] WordProbe { get; set; } = Array.Empty<string>();
}
