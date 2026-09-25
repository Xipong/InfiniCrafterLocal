#nullable enable
using InfiniCrafterLocal.Common.VFX;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Presentation-only manifest bound to exact low-level runtime entity/event pairs.
/// Unknown schema, renderer, entity id, event, or JSON field fails closed.
/// </summary>
public sealed class VfxManifestSpec
{
    public const string CurrentSchema = "infini.vfx.runtime-events.v15";

    [JsonRequired] public string Schema { get; set; } = CurrentSchema;
    public string RecipeId { get; set; } = "";
    public string EffectName { get; set; } = "";
    public string[] InspirationNames { get; set; } = Array.Empty<string>();
    public string PlaybackMode { get; set; } = "Realtime";
    public int Seed { get; set; }
    public float Confidence { get; set; } = 1f;
    [JsonRequired] public float EffectMagnitude { get; set; }
    [JsonRequired] public string VisualBudgetClass { get; set; } = "tiny";
    [JsonRequired] public VfxMotifSpec Motif { get; set; } = new();
    public VfxQualityBudgetSpec Budget { get; set; } = new();
    [JsonRequired] public VfxSlotSpec[] Slots { get; set; } = Array.Empty<VfxSlotSpec>();
    public string OverlayPolicy { get; set; } = "LocalOnly";
    public VfxDebugSpec Debug { get; set; } = new();

    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        WriteIndented = false,
    };

    public bool HasSlots => Slots is { Length: > 0 };
    public static VfxManifestSpec Empty() => new() { Slots = Array.Empty<VfxSlotSpec>() };

    public static VfxManifestSpec FromJson(string? json)
    {
        const string boundary = "VfxManifestSpec.FromJson";
        ContractJsonDiagnostics.Clear(boundary);
        if (string.IsNullOrWhiteSpace(json)) return Empty();
        try
        {
            VfxManifestSpec parsed = JsonSerializer.Deserialize<VfxManifestSpec>(json, Options) ?? Empty();
            parsed.NormalizeAndValidate();
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
        try
        {
            NormalizeAndValidate();
            return JsonSerializer.Serialize(this, Options);
        }
        catch (Exception exception)
        {
            ContractJsonDiagnostics.Record(boundary, exception);
            return "";
        }
    }

    public void Normalize() => NormalizeAndValidate();

    public void NormalizeAndValidate()
    {
        Schema = (Schema ?? "").Trim();
        if (!string.Equals(Schema, CurrentSchema, StringComparison.Ordinal))
            throw new InvalidDataException($"Unsupported VFX manifest schema '{Schema}'");
        RecipeId = Safe(RecipeId, 128);
        EffectName = Safe(EffectName, 96);
        InspirationNames ??= Array.Empty<string>();
        PlaybackMode = PlaybackMode is "Realtime" or "Hybrid" or "Baked" ? PlaybackMode : "Realtime";
        Confidence = Math.Clamp(Confidence, 0f, 1f);
        EffectMagnitude = Math.Clamp(EffectMagnitude, 0f, 1f);
        if (VisualBudgetClass is not ("tiny" or "small" or "normal" or "large" or "signature"))
            throw new InvalidDataException($"invalid VFX visualBudgetClass '{VisualBudgetClass}'");
        OverlayPolicy = OverlayPolicy is "LocalOnly" or "AllClients" ? OverlayPolicy : "LocalOnly";
        if (Motif is null) throw new InvalidDataException("VFX motif is required");
        Motif.Normalize();
        Budget ??= new VfxQualityBudgetSpec();
        Budget.Normalize();
        Debug ??= new VfxDebugSpec();
        Debug.Normalize();
        if (Slots is null) throw new InvalidDataException("VFX slots are required");
        if (Slots.Length > 12)
            throw new InvalidDataException("VFX slot count exceeds 12");
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var impactEntityIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (VfxSlotSpec? slot in Slots)
        {
            if (slot is null) throw new InvalidDataException("VFX manifest contains null slot");
            slot.NormalizeAndValidate();
            if (!ids.Add(slot.Id)) throw new InvalidDataException($"duplicate VFX slot id '{slot.Id}'");
            if (slot.RendererKind == "impactSprite" && !impactEntityIds.Add(slot.EntityId))
                throw new InvalidDataException($"duplicate impactSprite entity '{slot.EntityId}'");
        }
    }

    private static string Safe(string? value, int max)
    {
        string text = (value ?? "").Trim();
        return text.Length <= max ? text : text[..max];
    }
}

public sealed class VfxMotifSpec
{
    [JsonRequired] public string Element { get; set; } = "neutral";
    [JsonRequired] public string ShapeLanguage { get; set; } = "none";
    [JsonRequired] public string MotionLanguage { get; set; } = "none";
    [JsonRequired] public string PaletteRole { get; set; } = "primary";
    [JsonRequired] public float Rhythm { get; set; } = 1f;
    [JsonRequired] public float Chaos { get; set; }
    public void Normalize()
    {
        Element = NormalizeRequiredText(Element, 48, "element");
        ShapeLanguage = NormalizeRequiredText(ShapeLanguage, 96, "shapeLanguage");
        MotionLanguage = NormalizeRequiredText(MotionLanguage, 96, "motionLanguage");
        PaletteRole = NormalizeRequiredText(PaletteRole, 48, "paletteRole");
        Rhythm = Math.Clamp(Rhythm, 0.2f, 3f);
        Chaos = Math.Clamp(Chaos, 0f, 1f);
    }
    private static string NormalizeRequiredText(string? value, int max, string label)
    {
        string text = (value ?? "").Trim();
        if (text.Length == 0)
            throw new InvalidDataException($"invalid VFX motif {label}");
        return text.Length <= max ? text : text[..max];
    }
}

public sealed class VfxQualityBudgetSpec
{
    public float EffectMagnitude { get; set; }
    public string VisualBudgetClass { get; set; } = "tiny";
    public bool EmergencyCap { get; set; } = true;
    public int MaxParticlesPerTick { get; set; } = 32;
    public int MaxParticlesTotal { get; set; } = 1000;
    public int MaxDrawCalls { get; set; } = 64;
    public float SpawnRateMultiplier { get; set; } = 1f;
    public bool EnableSoftGlow { get; set; } = true;
    public bool EnablePointSparks { get; set; } = true;
    public bool EnablePersistentSmoke { get; set; }
    public void Normalize()
    {
        EffectMagnitude = Math.Clamp(EffectMagnitude, 0f, 1f);
        if (VisualBudgetClass is not ("tiny" or "small" or "normal" or "large" or "signature"))
            throw new InvalidDataException($"invalid VFX budget visualBudgetClass '{VisualBudgetClass}'");
        MaxParticlesPerTick = Math.Clamp(MaxParticlesPerTick, 0, 256);
        MaxParticlesTotal = Math.Clamp(MaxParticlesTotal, 0, 12000);
        MaxDrawCalls = Math.Clamp(MaxDrawCalls, 0, 512);
        SpawnRateMultiplier = Math.Clamp(SpawnRateMultiplier, 0f, 4f);
    }
}

public sealed class VfxSlotSpec
{
    [JsonRequired] public string Id { get; set; } = "";
    [JsonRequired] public string EntityId { get; set; } = "";
    [JsonRequired] public string Event { get; set; } = "";
    public string EffectName { get; set; } = "";
    public string EventGroup { get; set; } = "auto";
    public string Stage { get; set; } = "loop";
    [JsonRequired] public string Backend { get; set; } = "Auto";
    [JsonRequired] public string RendererKind { get; set; } = "";
    [JsonRequired] public string TextureRole { get; set; } = "entity";
    [JsonRequired] public string ParticleRole { get; set; } = "entity";
    [JsonRequired] public string Anchor { get; set; } = "self";
    [JsonRequired] public string Blend { get; set; } = "alpha";
    [JsonRequired] public string Layer { get; set; } = "BeforeProjectiles";
    [JsonRequired] public string Channel { get; set; } = "ambientParticles";
    [JsonRequired] public string Lane { get; set; } = "support";
    public string Source { get; set; } = "llm_vfx_director";
    [JsonRequired] public string EmissionMode { get; set; } = "none";
    [JsonRequired] public string ParticleSystemId { get; set; } = "none";
    [JsonRequired] public float FadeIn { get; set; }
    [JsonRequired] public float FadeOut { get; set; }
    public int SlotSeed { get; set; }
    [JsonRequired] public int StartTick { get; set; }
    [JsonRequired] public int RepeatEvery { get; set; }
    [JsonRequired] public float Scale { get; set; } = 1f;
    [JsonRequired] public float Density { get; set; }
    [JsonRequired] public int Duration { get; set; } = 10;
    [JsonRequired] public float Alpha { get; set; } = 0.65f;
    [JsonRequired] public float Spread { get; set; }
    [JsonRequired] public float Jitter { get; set; }
    public float PhaseOffset { get; set; }
    [JsonRequired] public float BudgetWeight { get; set; } = 1f;
    [JsonRequired] public float VisualCost { get; set; }
    [JsonRequired] public float SignatureWeight { get; set; }
    public string BakedClipId { get; set; } = "";
    public string BakedClipHash { get; set; } = "";
    public int BakedCommandCount { get; set; }
    public VfxBakedCommandSpec[] BakedCommands { get; set; } = Array.Empty<VfxBakedCommandSpec>();

    public void Normalize() => NormalizeAndValidate();
    public void NormalizeAndValidate()
    {
        Id = RuntimeId(Id, "slot id");
        EntityId = RuntimeId(EntityId, "entity id");
        Event = (Event ?? "").Trim().ToLowerInvariant();
        if (!RuntimeEventKind.IsKnown(Event)) throw new InvalidDataException($"unknown VFX event '{Event}'");
        InfiniVfxRendererKind rendererKind = VfxRendererRegistry.ParseKind(RendererKind);
        if (rendererKind == InfiniVfxRendererKind.None)
            throw new InvalidDataException($"unknown VFX renderer '{RendererKind}'");
        RendererKind = VfxRendererRegistry.ToWireName(rendererKind);
        Backend = ExactEnumText(Backend, "backend", "Auto", "Realtime", "Primitive", "Sprite", "Particle");
        TextureRole = ExactEnumText(TextureRole, "textureRole", "item", "entity", "projectile", "field", "impact", "none");
        if (rendererKind == InfiniVfxRendererKind.ImpactSprite && TextureRole != "impact")
            throw new InvalidDataException("impactSprite requires textureRole=impact");
        if (VfxRendererRegistry.ConsumesSpriteTexture(rendererKind) && TextureRole == "none")
            throw new InvalidDataException("sprite renderer requires a non-none textureRole");
        ParticleRole = ExactEnumText(ParticleRole, "particleRole", "item", "entity", "projectile", "field", "impact", "none");
        Anchor = ExactEnumText(Anchor, "anchor", "self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field");
        Channel = ExactEnumText(Channel, "channel", "motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound");
        Lane = ExactEnumText(Lane, "lane", "primary", "support", "accent", "ornament", "cue");
        EmissionMode = ExactEnumText(EmissionMode, "emissionMode", "wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "none");
        Blend = ExactEnumText(Blend, "blend", "alpha", "additive");
        ParticleSystemId = ExactEnumText(ParticleSystemId, "particleSystemId", "dust", "pl:glow", "pl:shard", "pl:smoke", "pl:spark", "none");
        if (RendererKind == "soundCue" && (Channel != "sound" || Lane != "cue")) throw new InvalidDataException("soundCue requires sound/cue");
        if (RendererKind == "lightCue" && (Channel != "light" || Lane != "cue")) throw new InvalidDataException("lightCue requires light/cue");
        Layer = ExactEnumText(Layer, "layer", "BeforeProjectiles", "AfterProjectiles");
        EffectName = Safe(EffectName, 96); EventGroup = Safe(EventGroup, 24); Stage = Safe(Stage, 24);
        Source = Safe(Source, 64);
        FadeIn = Math.Clamp(FadeIn, 0f, 0.8f); FadeOut = Math.Clamp(FadeOut, 0f, 0.8f);
        StartTick = Math.Clamp(StartTick, 0, 120); RepeatEvery = Math.Clamp(RepeatEvery, 0, 120);
        Scale = Math.Clamp(Scale, 0.15f, 5f); Density = Math.Clamp(Density, 0f, 1f);
        Duration = Math.Clamp(Duration, 3, 120); Alpha = Math.Clamp(Alpha, 0f, 1f);
        Spread = Math.Clamp(Spread, 0f, 2f); Jitter = Math.Clamp(Jitter, 0f, 1.5f);
        PhaseOffset = Math.Clamp(PhaseOffset, -1f, 1f); BudgetWeight = Math.Clamp(BudgetWeight, 0.1f, 4f);
        SignatureWeight = Math.Clamp(SignatureWeight, 0f, 1f); VisualCost = Math.Clamp(VisualCost, 0f, 1f);
        BakedClipId = Safe(BakedClipId, 96); BakedClipHash = Safe(BakedClipHash, 128);
        BakedCommands ??= Array.Empty<VfxBakedCommandSpec>();
        if (BakedCommands.Length > 120) throw new InvalidDataException("too many baked VFX commands");
        foreach (VfxBakedCommandSpec command in BakedCommands) command.Normalize();
        BakedCommandCount = BakedCommands.Length;
    }

    private static string RuntimeId(string? value, string label)
    {
        string text = Safe(value, 64);
        if (text.Length == 0 || !char.IsLower(text[0]) || text.Any(c => !(char.IsLower(c) || char.IsDigit(c) || c == '_')))
            throw new InvalidDataException($"invalid VFX {label} '{text}'");
        return text;
    }
    private static string ExactEnumText(string? value, string label, params string[] allowed)
    {
        string text = value ?? "";
        if (!allowed.Contains(text, StringComparer.Ordinal))
            throw new InvalidDataException($"invalid VFX {label} '{text}'");
        return text;
    }
    private static string Safe(string? value, int max)
    {
        string text = (value ?? "").Trim();
        return text.Length <= max ? text : text[..max];
    }
}

public sealed class VfxBakedCommandSpec
{
    public int Tick { get; set; }
    public string ParticleSystemId { get; set; } = "none";
    public string TextureRole { get; set; } = "";
    public float LocalX { get; set; }
    public float LocalY { get; set; }
    public float VelocityX { get; set; }
    public float VelocityY { get; set; }
    public string StartColor { get; set; } = "";
    public string EndColor { get; set; } = "";
    public float ScaleX { get; set; } = 1f;
    public float ScaleY { get; set; } = 1f;
    public float ScaleVelocityX { get; set; }
    public float ScaleVelocityY { get; set; }
    public float Rotation { get; set; }
    public float RotationVelocity { get; set; }
    public int Lifespan { get; set; } = 18;
    public float Alpha { get; set; } = 0.65f;
    public int SeedBucket { get; set; }
    public void Normalize()
    {
        Tick = Math.Clamp(Tick, 0, 600); LocalX = Math.Clamp(LocalX, -8f, 8f); LocalY = Math.Clamp(LocalY, -8f, 8f);
        VelocityX = Math.Clamp(VelocityX, -12f, 12f); VelocityY = Math.Clamp(VelocityY, -12f, 12f);
        ScaleX = Math.Clamp(ScaleX, 0.03f, 8f); ScaleY = Math.Clamp(ScaleY, 0.03f, 8f);
        ScaleVelocityX = Math.Clamp(ScaleVelocityX, -2f, 2f); ScaleVelocityY = Math.Clamp(ScaleVelocityY, -2f, 2f);
        Rotation = Math.Clamp(Rotation, -32f, 32f); RotationVelocity = Math.Clamp(RotationVelocity, -8f, 8f);
        Lifespan = Math.Clamp(Lifespan, 1, 240); Alpha = Math.Clamp(Alpha, 0f, 1f);
    }
}

public sealed class VfxDebugSpec
{
    public string Pattern { get; set; } = "";
    public string[] Roles { get; set; } = Array.Empty<string>();
    public float SelectedScore { get; set; }
    public string[] SelectedReasons { get; set; } = Array.Empty<string>();
    public object[] TopCandidates { get; set; } = Array.Empty<object>();
    public string[] WordProbe { get; set; } = Array.Empty<string>();
    public void Normalize()
    {
        Pattern = (Pattern ?? "").Trim(); Roles ??= Array.Empty<string>(); SelectedReasons ??= Array.Empty<string>(); TopCandidates ??= Array.Empty<object>(); WordProbe ??= Array.Empty<string>();
    }
}
