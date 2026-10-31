#nullable enable
using InfiniCrafterLocal.Common.VFX;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Terraria.Audio;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Presentation-only manifest bound to exact low-level runtime entity/event pairs.
/// Unknown schema, renderer, entity id, event, or JSON field fails closed.
/// </summary>
public sealed class VfxManifestSpec
{
    public const string CurrentSchema = "infini.vfx.runtime-events.v16";

    [JsonRequired] public string Schema { get; set; } = CurrentSchema;
    // PNG asset-plan naming consumes this delivery identity before native hydration.
    [JsonRequired] public string RecipeId { get; set; } = "";
    [JsonRequired] public VfxQualityBudgetSpec Budget { get; set; } = new();
    [JsonRequired] public VfxSlotSpec[] Slots { get; set; } = Array.Empty<VfxSlotSpec>();
    private VfxAssetSpec[]? _assets;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxAssetSpec[]? Assets { get => _assets; set => _assets = value ?? throw new InvalidDataException("VFX assets cannot be null"); }

    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        WriteIndented = false,
    };

    [JsonIgnore] public bool HasSlots => Slots is { Length: > 0 };
    public static VfxManifestSpec Empty() => new() { Slots = Array.Empty<VfxSlotSpec>() };

    public static VfxManifestSpec FromJson(string? json)
    {
        const string boundary = "VfxManifestSpec.FromJson";
        ContractJsonDiagnostics.Clear(boundary);
        if (string.IsNullOrWhiteSpace(json)) return Empty();
        try
        {
            VfxManifestSpec parsed = JsonSerializer.Deserialize<VfxManifestSpec>(json, Options) ?? throw new InvalidDataException("VFX manifest must be an object");
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

    public void NormalizeAndValidate()
    {
        if (!string.Equals(Schema, CurrentSchema, StringComparison.Ordinal))
            throw new InvalidDataException($"Unsupported VFX manifest schema '{Schema}'");
        if (RecipeId is null) throw new InvalidDataException("VFX recipeId must be a string");
        if (Budget is null) throw new InvalidDataException("VFX budget is required");
        Budget.Normalize();
        if (Slots is null) throw new InvalidDataException("VFX slots are required");
        if (Slots.Length > 12)
            throw new InvalidDataException("VFX slot count exceeds 12");
        var declaredAssets = new HashSet<string>(StringComparer.Ordinal);
        if (Assets is not null) {
            if (Assets.Length > 16) throw new InvalidDataException("VFX asset count exceeds 16");
            foreach (var asset in Assets) {
                if (asset is null) throw new InvalidDataException("null VFX asset");
                asset.Validate();
                if (!declaredAssets.Add(asset.Id)) throw new InvalidDataException("duplicate VFX asset id");
            }
        }
        var usedAssets = new HashSet<string>(StringComparer.Ordinal);
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var impactEntityIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (VfxSlotSpec? slot in Slots)
        {
            if (slot is null) throw new InvalidDataException("VFX manifest contains null slot");
            slot.NormalizeAndValidate();
            var texture = slot.Element?.Texture ?? slot.Path?.Texture ?? slot.Trail?.Texture;
            if (texture?.Source == "asset") {
                if (!declaredAssets.Contains(texture.AssetId)) throw new InvalidDataException("dangling VFX asset reference");
                usedAssets.Add(texture.AssetId);
            }
            if (!ids.Add(slot.Id)) throw new InvalidDataException($"duplicate VFX slot id '{slot.Id}'");
            if (slot.RendererKind == "impactSprite" && !impactEntityIds.Add(slot.EntityId))
                throw new InvalidDataException($"duplicate impactSprite entity '{slot.EntityId}'");
        }
        if (!declaredAssets.SetEquals(usedAssets)) throw new InvalidDataException("unused VFX asset request");
    }
}

public sealed class VfxQualityBudgetSpec
{
    [JsonRequired] public int MaxParticlesPerTick { get; set; } = 32;
    [JsonRequired] public int MaxParticlesTotal { get; set; } = 1000;
    [JsonRequired] public int MaxDrawCalls { get; set; } = 64;
    public void Normalize()
    {
        MaxParticlesPerTick = Math.Clamp(MaxParticlesPerTick, 0, 256);
        MaxParticlesTotal = Math.Clamp(MaxParticlesTotal, 0, 12000);
        MaxDrawCalls = Math.Clamp(MaxDrawCalls, 0, 512);
    }
}

public sealed class VfxSlotSpec
{
    [JsonRequired] public string Id { get; set; } = "";
    [JsonRequired] public string EntityId { get; set; } = "";
    [JsonRequired] public string Event { get; set; } = "";
    [JsonRequired] public string RendererKind { get; set; } = "";
    private string? _placementBindingId;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? PlacementBindingId
    {
        get => _placementBindingId;
        set => _placementBindingId = value ?? throw new InvalidDataException("placementBindingId cannot be null");
    }
    private string? _textureRole;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TextureRole { get => _textureRole; set => _textureRole = value ?? throw new InvalidDataException("TextureRole cannot be null"); }
    [JsonRequired] public string Anchor { get; set; } = "self";
    private string? _blend;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Blend { get => _blend; set => _blend = value ?? throw new InvalidDataException("Blend cannot be null"); }
    private string? _layer;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Layer { get => _layer; set => _layer = value ?? throw new InvalidDataException("Layer cannot be null"); }
    private string? _particleSystemId;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ParticleSystemId { get => _particleSystemId; set => _particleSystemId = value ?? throw new InvalidDataException("ParticleSystemId cannot be null"); }
    private string? _soundId;
    // Required for soundCue only; non-sound renderers omit both audio choices.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SoundId { get => _soundId; set => _soundId = value ?? throw new InvalidDataException("soundId cannot be null"); }
    private VfxSoundSpec? _sound;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxSoundSpec? Sound { get => _sound; set => _sound = value ?? throw new InvalidDataException("sound cannot be null"); }
    public int SlotSeed { get; set; }
    private int? _startTick;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? StartTick { get => _startTick; set => _startTick = value ?? throw new InvalidDataException("startTick cannot be null"); }
    private int? _repeatEvery;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? RepeatEvery { get => _repeatEvery; set => _repeatEvery = value ?? throw new InvalidDataException("RepeatEvery cannot be null"); }
    private float? _scale;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? Scale { get => _scale; set => _scale = value ?? throw new InvalidDataException("Scale cannot be null"); }
    private float? _density;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? Density { get => _density; set => _density = value ?? throw new InvalidDataException("Density cannot be null"); }
    private int? _duration;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Duration { get => _duration; set => _duration = value ?? throw new InvalidDataException("Duration cannot be null"); }
    private float? _alpha;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? Alpha { get => _alpha; set => _alpha = value ?? throw new InvalidDataException("Alpha cannot be null"); }
    private float? _spread;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? Spread { get => _spread; set => _spread = value ?? throw new InvalidDataException("Spread cannot be null"); }
    private float _phaseOffset;
    private bool _hasPhaseOffset;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)]
    public float PhaseOffset { get => _phaseOffset; set { _phaseOffset=value; _hasPhaseOffset=true; } }

    private RuntimeRgbSpec? _color;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeRgbSpec? Color { get => _color; set => _color = value ?? throw new InvalidDataException("VFX color cannot be null"); }

    private VfxSpriteElementSpec? _element;
    private VfxTexturedPathSpec? _path;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxSpriteElementSpec? Element { get => _element; set => _element = value ?? throw new InvalidDataException("element cannot be null"); }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxTexturedPathSpec? Path { get => _path; set => _path = value ?? throw new InvalidDataException("path cannot be null"); }

    private VfxLibraryParticleSpec? _particle;
    private VfxScreenShakeSpec? _screenShake;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxLibraryParticleSpec? Particle { get => _particle; set => _particle = value ?? throw new InvalidDataException("particle cannot be null"); }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxScreenShakeSpec? ScreenShake { get => _screenShake; set => _screenShake = value ?? throw new InvalidDataException("screenShake cannot be null"); }

    private VfxShapeSpec? _shape;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public VfxShapeSpec? Shape { get => _shape; set => _shape=value ?? throw new InvalidDataException("shape cannot be null"); }

    private VfxNativeDustSpec? _dust;
    private VfxNativeLightSpec? _light;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public VfxNativeDustSpec? Dust { get => _dust; set => _dust=value ?? throw new InvalidDataException("dust cannot be null"); }
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public VfxNativeLightSpec? Light { get => _light; set => _light=value ?? throw new InvalidDataException("light cannot be null"); }

    private VfxHistoryTrailSpec? _trail;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public VfxHistoryTrailSpec? Trail { get=>_trail; set=>_trail=value??throw new InvalidDataException("trail cannot be null"); }

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
        if (PlacementBindingId is not null)
        {
            if (RuntimeId(PlacementBindingId,"placement binding id") != PlacementBindingId
                || Event != RuntimeEventKind.Periodic || Anchor != "self" || RepeatEvery is null or < 1
                || rendererKind is not (InfiniVfxRendererKind.SpriteElement or InfiniVfxRendererKind.LibraryParticle or InfiniVfxRendererKind.LightCue or InfiniVfxRendererKind.NativeLight))
                throw new InvalidDataException("placed VFX requires exact binding, periodic/self and spriteElement/libraryParticle/lightCue cadence");
        }
        VfxHistoryTrailSpec.ValidateSlot(this,_hasPhaseOffset);
        if(rendererKind==InfiniVfxRendererKind.HistoryTrail)return;
        VfxNativeCueValidation.Validate(this,_hasPhaseOffset);
        if (rendererKind is InfiniVfxRendererKind.NativeDust or InfiniVfxRendererKind.NativeLight) return;
        if (rendererKind == InfiniVfxRendererKind.SoundCue && (SoundId is null || Sound is null))
            throw new InvalidDataException("soundCue requires explicit soundId and sound playback controls");
        if (SoundId is not null) {
            if (rendererKind != InfiniVfxRendererKind.SoundCue) throw new InvalidDataException("soundId is owned only by soundCue");
            _ = ResolveSoundSample(); // exact finite selector; never trim/guess/substitute
        }
        if (Sound is not null) {
            if (rendererKind != InfiniVfxRendererKind.SoundCue) throw new InvalidDataException("sound is owned only by soundCue");
            if (SoundId is null) throw new InvalidDataException("explicit sound requires an exact soundId");
            Sound.NormalizeAndValidate();
        }
        if(rendererKind==InfiniVfxRendererKind.Shape) {
            if(_hasPhaseOffset)throw new InvalidDataException("shape forbids legacy phaseOffset");
            if(Shape is null)throw new InvalidDataException("shape renderer requires shape");
            Shape.Validate(this);
        } else if(Shape is not null)throw new InvalidDataException("foreign shape payload");
        VfxLibraryValidation.Validate(this,rendererKind);
        bool ownsColor = rendererKind is not (InfiniVfxRendererKind.SoundCue or InfiniVfxRendererKind.ScreenShakeCue
            or InfiniVfxRendererKind.SpriteElement or InfiniVfxRendererKind.TexturedPath or InfiniVfxRendererKind.LibraryParticle or InfiniVfxRendererKind.Shape);
        if (ownsColor ? Color is null : Color is not null)
            throw new InvalidDataException(ownsColor ? "VFX renderer requires explicit local color" : "VFX renderer forbids common color");
        Color?.Validate();
        bool materialBranch = rendererKind is InfiniVfxRendererKind.SpriteElement or InfiniVfxRendererKind.TexturedPath;
        if (rendererKind == InfiniVfxRendererKind.SpriteElement) {
            if (Element is null || Path is not null) throw new InvalidDataException("spriteElement requires only element payload");
            Element.Validate(this);
        } else if (rendererKind == InfiniVfxRendererKind.TexturedPath) {
            if (Path is null || Element is not null) throw new InvalidDataException("texturedPath requires only path payload");
            Path.Validate(this);
        } else if (Element is not null || Path is not null) throw new InvalidDataException("foreign VFX material payload");
        bool shape = rendererKind == InfiniVfxRendererKind.Shape;
        bool nestedBranch = shape || materialBranch || rendererKind is InfiniVfxRendererKind.LibraryParticle or InfiniVfxRendererKind.ScreenShakeCue;
        bool shake = rendererKind == InfiniVfxRendererKind.ScreenShakeCue;
        bool sound = rendererKind == InfiniVfxRendererKind.SoundCue;
        bool path = rendererKind == InfiniVfxRendererKind.TexturedPath;
        bool light = rendererKind == InfiniVfxRendererKind.LightCue;
        bool dustOnly = rendererKind == InfiniVfxRendererKind.ChildMotes;
        bool impact = rendererKind == InfiniVfxRendererKind.ImpactSprite;
        bool cadenceOnly = sound || light || impact;
        bool spriteTexture = VfxRendererRegistry.ConsumesSpriteTexture(rendererKind);
        if (!spriteTexture && TextureRole is not null)
            throw new InvalidDataException("non-sprite VFX renderer forbids textureRole");
        if (nestedBranch || sound) {
            if (Scale is not null || (!sound && Density is not null) || Spread is not null || ParticleSystemId is not null || TextureRole is not null)
                throw new InvalidDataException("nested VFX renderer forbids unconsumed common controls");
        } else if (light || impact) {
            if (Spread is not null || ParticleSystemId is not null || (light && TextureRole is not null))
                throw new InvalidDataException("light/impact renderer forbids unconsumed common controls");
            if (Scale is null || (impact && TextureRole is null))
                throw new InvalidDataException("light/impact renderer requires its consumed controls");
            Scale = Math.Clamp(Scale.Value, 0.15f, 5f);
            if (impact) TextureRole = ExactEnumText(TextureRole, "textureRole", "impact");
        } else {
            if (Scale is null || Density is null || Spread is null || ParticleSystemId is null || (spriteTexture && TextureRole is null))
                throw new InvalidDataException("simple VFX renderer requires its common controls");
            if (spriteTexture) TextureRole = ExactEnumText(TextureRole, "textureRole", "item", "entity", "impact", "none");
            ParticleSystemId = ExactEnumText(ParticleSystemId, "particleSystemId", "GemDiamond", "TintableDustLighted", "Glass", "Smoke", "Electric", "none");
            Scale = Math.Clamp(Scale.Value, 0.15f, 5f); Density = Math.Clamp(Density.Value, 0f, 1f);
            Spread = Math.Clamp(Spread.Value, 0f, 2f);
        }
        if (shake || sound || light || dustOnly) {
            if (Alpha is not null || Blend is not null || Layer is not null)
                throw new InvalidDataException("screenShakeCue forbids unconsumed draw controls");
        } else {
            if ((shape ? Alpha is not null : Alpha is null) || Blend is null || Layer is null)
                throw new InvalidDataException("VFX renderer requires alpha, blend and layer");
            if(!shape) Alpha = Math.Clamp(Alpha!.Value, 0f, 1f);
            Blend = ExactEnumText(Blend, "blend", "alpha", "additive");
            Layer = ExactEnumText(Layer, "layer", "BeforeProjectiles", "AfterProjectiles");
        }
        if (cadenceOnly) {
            if (impact) {
                if (Duration is null) throw new InvalidDataException("impactSprite requires duration");
                Duration = Math.Clamp(Duration.Value, 3, 120);
            } else if (Duration is not null) throw new InvalidDataException("soundCue/lightCue forbids duration");
            if (Event != RuntimeEventKind.Periodic) {
                if (StartTick is not null || RepeatEvery is not null || Density is not null)
                    throw new InvalidDataException("event sound/light/impact cue forbids cadence controls");
            } else {
                if (RepeatEvery is null) throw new InvalidDataException("periodic sound/light/impact cue requires repeatEvery");
                RepeatEvery = Math.Clamp(RepeatEvery.Value, 0, 120);
                if (RepeatEvery > 0 && Density is not null) throw new InvalidDataException("explicit cue cadence forbids unused density");
                if (Density is { } density) Density = Math.Clamp(density, 0, 1);
            }
        } else if (dustOnly) {
            if (Duration is not null) throw new InvalidDataException("childMotes forbids duration");
            if (RepeatEvery is null) throw new InvalidDataException("childMotes requires repeatEvery");
            RepeatEvery = Math.Clamp(RepeatEvery.Value, 0, 120);
        } else if (shake || path) {
            if (Duration is not null || RepeatEvery is not null)
                throw new InvalidDataException("VFX renderer forbids unconsumed duration/repeatEvery");
        } else {
            if (Duration is null || RepeatEvery is null)
                throw new InvalidDataException("VFX renderer requires duration and repeatEvery");
            int minimumDuration=shape?1:3;
            if (nestedBranch && (Duration < minimumDuration || Duration > 120 || RepeatEvery is < 0 or > 120))
                throw new InvalidDataException("invalid VFX nested timing");
            Duration = Math.Clamp(Duration.Value, minimumDuration, 120); RepeatEvery = Math.Clamp(RepeatEvery.Value, 0, 120);
        }
        if (nestedBranch && StartTick is < 0 or > 120) throw new InvalidDataException("invalid VFX nested startTick");
        if (rendererKind == InfiniVfxRendererKind.ImpactSprite && TextureRole != "impact")
            throw new InvalidDataException("impactSprite requires textureRole=impact");
        if (VfxRendererRegistry.ConsumesSpriteTexture(rendererKind) && TextureRole == "none")
            throw new InvalidDataException("sprite renderer requires a non-none textureRole");
        Anchor = ExactEnumText(Anchor, "anchor", "self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field");
        if (!cadenceOnly && StartTick is null) throw new InvalidDataException("VFX renderer requires startTick");
        if (StartTick is { } startTick) StartTick = Math.Clamp(startTick, 0, 120);
        _phaseOffset = Math.Clamp(_phaseOffset, -1f, 1f);
    }

    // Shared playback projection for item, projectile and detached occurrences.
    internal SoundStyle ResolveSoundStyle()
    {
        if (Sound is not { } sound)
            throw new InvalidDataException("soundCue requires explicit sound playback controls");
        return sound.ApplyTo(ResolveSoundSample());
    }

    // Exact finite SoundID identity; absent/unknown selectors are never substituted.
    private SoundStyle ResolveSoundSample() => SoundId switch
    {
        "Item1" => SoundID.Item1,
        "Item2" => SoundID.Item2,
        "Item3" => SoundID.Item3,
        "Item4" => SoundID.Item4,
        "Item5" => SoundID.Item5,
        "Item7" => SoundID.Item7,
        "Item8" => SoundID.Item8,
        "Item9" => SoundID.Item9,
        "Item10" => SoundID.Item10,
        "Item11" => SoundID.Item11,
        "Item12" => SoundID.Item12,
        "Item13" => SoundID.Item13,
        "Item14" => SoundID.Item14,
        "Item15" => SoundID.Item15,
        "Item17" => SoundID.Item17,
        "Item20" => SoundID.Item20,
        "Item21" => SoundID.Item21,
        "Item26" => SoundID.Item26,
        "Item28" => SoundID.Item28,
        "Item29" => SoundID.Item29,
        "Item31" => SoundID.Item31,
        "Item33" => SoundID.Item33,
        "Item34" => SoundID.Item34,
        "Item36" => SoundID.Item36,
        "Item37" => SoundID.Item37,
        "Item38" => SoundID.Item38,
        "Item40" => SoundID.Item40,
        "Item41" => SoundID.Item41,
        "Item42" => SoundID.Item42,
        "Item43" => SoundID.Item43,
        "Item44" => SoundID.Item44,
        "Item46" => SoundID.Item46,
        "Item51" => SoundID.Item51,
        "Item54" => SoundID.Item54,
        "Item57" => SoundID.Item57,
        "Item58" => SoundID.Item58,
        "Item60" => SoundID.Item60,
        "Item62" => SoundID.Item62,
        "Item69" => SoundID.Item69,
        "Item70" => SoundID.Item70,
        "Item71" => SoundID.Item71,
        "Item72" => SoundID.Item72,
        "Item73" => SoundID.Item73,
        "Item74" => SoundID.Item74,
        "Item76" => SoundID.Item76,
        "Item77" => SoundID.Item77,
        "Item78" => SoundID.Item78,
        "Item82" => SoundID.Item82,
        "Item83" => SoundID.Item83,
        "Item84" => SoundID.Item84,
        "Item85" => SoundID.Item85,
        "Item88" => SoundID.Item88,
        "Item89" => SoundID.Item89,
        "Item91" => SoundID.Item91,
        "Item93" => SoundID.Item93,
        "Item94" => SoundID.Item94,
        "Item97" => SoundID.Item97,
        "Item98" => SoundID.Item98,
        "Item99" => SoundID.Item99,
        "Item102" => SoundID.Item102,
        "Item103" => SoundID.Item103,
        "Item105" => SoundID.Item105,
        "Item106" => SoundID.Item106,
        "Item107" => SoundID.Item107,
        "Item108" => SoundID.Item108,
        "Item109" => SoundID.Item109,
        "Item110" => SoundID.Item110,
        "Item113" => SoundID.Item113,
        "Item117" => SoundID.Item117,
        "Item123" => SoundID.Item123,
        "Item124" => SoundID.Item124,
        "Item152" => SoundID.Item152,
        "Item157" => SoundID.Item157,
        "Item158" => SoundID.Item158,
        "Item169" => SoundID.Item169,
        "Coins" => SoundID.Coins,
        "Dig" => SoundID.Dig,
        "Grab" => SoundID.Grab,
        "MaxMana" => SoundID.MaxMana,
        "ResearchComplete" => SoundID.ResearchComplete,
        "Shatter" => SoundID.Shatter,
        "Splash" => SoundID.Splash,
        "Tink" => SoundID.Tink,
        "Unlock" => SoundID.Unlock,
        _ => throw new InvalidDataException($"invalid VFX soundId '{SoundId}'"),
    };

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
