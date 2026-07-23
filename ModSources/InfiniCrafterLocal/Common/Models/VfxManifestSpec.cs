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
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        WriteIndented = false
    };

    public bool HasSlots => Slots is { Length: > 0 };

    public static VfxManifestSpec Empty() => new();

    public static VfxManifestSpec FromJson(string? json)
    {
        const string boundary = "VfxManifestSpec.FromJson";
        ContractJsonDiagnostics.Clear(boundary);
        if (string.IsNullOrWhiteSpace(json))
            return Empty();
        try
        {
            var parsed = JsonSerializer.Deserialize<VfxManifestSpec>(json, Options) ?? Empty();
            parsed.Normalize();
            return parsed;
        }
        catch (Exception exception)
        {
            ContractJsonDiagnostics.Record(boundary, exception);
            return Empty();
        }
    }

    public string ToJson()
    {
        const string boundary = "VfxManifestSpec.ToJson";
        ContractJsonDiagnostics.Clear(boundary);
        Normalize();
        try { return JsonSerializer.Serialize(this, Options); }
        catch (Exception exception)
        {
            ContractJsonDiagnostics.Record(boundary, exception);
            return "";
        }
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
    public string EventGroup { get; set; } = "auto"; // live/hit/kill/item_live/item_use; canonical lifecycle group precompiled by Python.
    public string Stage { get; set; } = "loop"; // windup, active, impact, decay, loop
    public string Backend { get; set; } = "Auto"; // Baked, Realtime, Primitive, Sprite, Particle, Auto
    public string RendererKind { get; set; } = "projectileAfterimage"; // exact canonical renderer id.
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
        Event = VfxCanonicalVocabulary.Event(Event);
        EffectName ??= "";
        EventGroup = VfxCanonicalVocabulary.EventGroup(Event);
        Stage = VfxCanonicalVocabulary.Stage(Event);
        Backend = VfxCanonicalVocabulary.Backend(Backend);
        RendererKind = VfxRendererRegistry.NormalizeKindName(RendererKind);
        InfiniVfxRendererKind rendererKind = VfxRendererRegistry.ParseKind(RendererKind);
        if (rendererKind == InfiniVfxRendererKind.None)
        {
            RendererKind = "projectileAfterimage";
            rendererKind = InfiniVfxRendererKind.ProjectileAfterimage;
        }
        TextureRole = string.IsNullOrWhiteSpace(TextureRole) ? "projectile" : TextureRole;
        ParticleRole = string.IsNullOrWhiteSpace(ParticleRole) ? TextureRole : ParticleRole;
        Channel = VfxCanonicalVocabulary.Channel(Channel, rendererKind, Event);
        Importance = VfxCanonicalVocabulary.Importance(Importance);
        Lane = VfxCanonicalVocabulary.Lane(Lane, Channel, Importance, rendererKind);
        Anchor = VfxCanonicalVocabulary.Anchor(Anchor, rendererKind, Channel, Event);
        Blend = VfxCanonicalVocabulary.Blend(Blend, rendererKind, Channel);
        Layer = Layer is "BeforeProjectiles" or "AfterProjectiles" ? Layer : "BeforeProjectiles";
        Source = string.IsNullOrWhiteSpace(Source) ? "recipe" : Source.Trim();
        EmissionMode = VfxCanonicalVocabulary.EmissionMode(EmissionMode, rendererKind, Channel, Event);
        ParticleSystemId = VfxParticleAddress.Resolve(ParticleSystemId, RendererKind, Channel, Event, Blend, EmissionMode);
        FadeIn = Math.Clamp(FadeIn <= 0f ? 0.15f : FadeIn, 0f, 0.95f);
        FadeOut = Math.Clamp(FadeOut <= 0f ? 0.35f : FadeOut, 0f, 0.95f);
        Curve = VfxCanonicalVocabulary.Curve(Curve);
        SlotSeed = SlotSeed == 0 ? StableSlotSeed(RendererKind, Event, Channel, Lane, Variant) : SlotSeed;
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
