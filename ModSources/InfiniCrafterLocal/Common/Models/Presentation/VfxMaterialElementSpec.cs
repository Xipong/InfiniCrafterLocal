#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

// Additive wire branches. These never supply missing authored design.
internal static class VfxMaterialValidation
{
    internal static void Range(float value, float min, float max, string label)
    {
        if (!float.IsFinite(value) || value < min || value > max) throw new InvalidDataException("invalid VFX " + label);
    }
    internal static void Choice(string? value, string label, params string[] choices)
    {
        if (value is null || Array.IndexOf(choices, value) < 0) throw new InvalidDataException("invalid VFX " + label);
    }
    internal static bool AssetId(string? value) => value is not null && Regex.IsMatch(value, @"\A[A-Za-z0-9_-]{1,48}\z");
}

public sealed class VfxAssetSpec
{
    [JsonRequired] public string Id { get; set; } = "";
    [JsonRequired] public string Prompt { get; set; } = "";
    [JsonRequired] public string NegativePrompt { get; set; } = "";
    [JsonRequired] public int CanvasSize { get; set; }
    [JsonRequired] public string Layout { get; set; } = "";
    public string SpritePath { get; set; } = "";
    public string SpriteUrl { get; set; } = "";
    public string SpriteStatus { get; set; } = "";
    public float SpriteTechnicalScore { get; set; }
    internal void Validate()
    {
        if (!VfxMaterialValidation.AssetId(Id)) throw new InvalidDataException("invalid VFX asset id");
        // Transport strips captions but never asset/render identity. Empty captions
        // are admitted only for a hydrated runtime asset, not a new request.
        if (Prompt is null || Prompt.Length > 1400 || (string.IsNullOrWhiteSpace(Prompt) && (Prompt != "" || NegativePrompt != "" || string.IsNullOrEmpty(SpritePath)))
            || NegativePrompt is null || NegativePrompt.Length > 700) throw new InvalidDataException("invalid VFX asset prompt");
        if (CanvasSize is not (16 or 24 or 32 or 48 or 64 or 96 or 128)) throw new InvalidDataException("invalid VFX asset canvas");
        VfxMaterialValidation.Choice(Layout, "asset layout", "cutout", "strip");
        if (SpritePath is null || SpritePath.Length > 500 || SpriteUrl is null || SpriteUrl.Length > 500
            || SpriteStatus is null || SpriteStatus.Length > 48) throw new InvalidDataException("invalid VFX asset execution metadata");
        VfxMaterialValidation.Range(SpriteTechnicalScore, 0, 1, "asset score");
    }
}

public sealed class VfxTextureSpec
{
    [JsonRequired] public string Source { get; set; } = "";
    [JsonRequired] public string AssetId { get; set; } = "";
    internal void Validate()
    {
        VfxMaterialValidation.Choice(Source, "texture source", "item", "entity", "impact", "asset");
        if (Source == "asset" ? !VfxMaterialValidation.AssetId(AssetId) : AssetId != "") throw new InvalidDataException("invalid VFX texture assetId");
    }
}

public sealed class VfxNumericProfileSpec
{
    [JsonRequired] public float Start { get; set; }
    [JsonRequired] public float Middle { get; set; }
    [JsonRequired] public float End { get; set; }
    [JsonRequired] public string Curve { get; set; } = "";
    internal void Validate(float max)
    {
        VfxMaterialValidation.Range(Start, 0, max, "profile start");
        VfxMaterialValidation.Range(Middle, 0, max, "profile middle");
        VfxMaterialValidation.Range(End, 0, max, "profile end");
        VfxMaterialValidation.Choice(Curve, "profile curve", "linear", "easeIn", "easeOut", "smoothStep");
    }
}

public sealed class VfxColorProfileSpec
{
    [JsonRequired] public string Start { get; set; } = "";
    [JsonRequired] public string Middle { get; set; } = "";
    [JsonRequired] public string End { get; set; } = "";
    [JsonRequired] public string Curve { get; set; } = "";
    internal void Validate()
    {
        foreach (string token in new[] { Start, Middle, End }) if (token != "effect") RuntimeColorPolicy.RequireRenderingToken(token);
        VfxMaterialValidation.Choice(Curve, "color curve", "linear", "easeIn", "easeOut", "smoothStep");
    }
}

public sealed class VfxSpriteElementSpec
{
    [JsonRequired] public VfxTextureSpec Texture { get; set; } = null!;
    [JsonRequired] public string Attachment { get; set; } = "";
    [JsonRequired] public int Count { get; set; }
    [JsonRequired] public float OffsetForwardPx { get; set; }
    [JsonRequired] public float OffsetSidePx { get; set; }
    [JsonRequired] public float SpeedMinPxPerTick { get; set; }
    [JsonRequired] public float SpeedMaxPxPerTick { get; set; }
    [JsonRequired] public float SpreadRadians { get; set; }
    [JsonRequired] public float InheritVelocity { get; set; }
    [JsonRequired] public float Drag { get; set; }
    [JsonRequired] public float AccelerationXPxPerTickSquared { get; set; }
    [JsonRequired] public float AccelerationYPxPerTickSquared { get; set; }
    [JsonRequired] public float RotationRadians { get; set; }
    [JsonRequired] public float RotationSpeedRadiansPerTick { get; set; }
    [JsonRequired] public float WidthPx { get; set; }
    [JsonRequired] public float HeightPx { get; set; }
    [JsonRequired] public VfxNumericProfileSpec WidthProfile { get; set; } = null!;
    [JsonRequired] public VfxNumericProfileSpec HeightProfile { get; set; } = null!;
    [JsonRequired] public VfxNumericProfileSpec OpacityProfile { get; set; } = null!;
    [JsonRequired] public VfxColorProfileSpec ColorProfile { get; set; } = null!;
    internal void Validate(VfxSlotSpec slot)
    {
        if (Texture is null || WidthProfile is null || HeightProfile is null || OpacityProfile is null || ColorProfile is null)
            throw new InvalidDataException("spriteElement requires texture and all profiles");
        Texture.Validate(); WidthProfile.Validate(4); HeightProfile.Validate(4); OpacityProfile.Validate(1); ColorProfile.Validate();
        VfxMaterialValidation.Choice(Attachment, "attachment", "world", "source");
        if (Attachment == "source" && slot.Event is "on_expire" or "on_kill") throw new InvalidDataException("terminal spriteElement requires world attachment");
        if (Count < 0 || Count > 64) throw new InvalidDataException("invalid VFX element count");
        VfxMaterialValidation.Range(OffsetForwardPx, -128, 128, "offsetForwardPx"); VfxMaterialValidation.Range(OffsetSidePx, -128, 128, "offsetSidePx");
        VfxMaterialValidation.Range(SpeedMinPxPerTick, 0, 24, "speed min"); VfxMaterialValidation.Range(SpeedMaxPxPerTick, SpeedMinPxPerTick, 24, "speed max");
        VfxMaterialValidation.Range(SpreadRadians, 0, MathF.PI * 2, "spreadRadians"); VfxMaterialValidation.Range(InheritVelocity, 0, 1, "inheritVelocity");
        VfxMaterialValidation.Range(Drag, 0, 1, "drag");
        VfxMaterialValidation.Range(AccelerationXPxPerTickSquared, -2, 2, "acceleration X"); VfxMaterialValidation.Range(AccelerationYPxPerTickSquared, -2, 2, "acceleration Y");
        VfxMaterialValidation.Range(RotationRadians, -MathF.PI * 2, MathF.PI * 2, "rotation"); VfxMaterialValidation.Range(RotationSpeedRadiansPerTick, -1, 1, "rotation speed");
        VfxMaterialValidation.Range(WidthPx, 0, 128, "widthPx"); VfxMaterialValidation.Range(HeightPx, 0, 128, "heightPx");
        if (slot.Event == "periodic" ? slot.RepeatEvery < 1 : slot.RepeatEvery != 0) throw new InvalidDataException("invalid spriteElement cadence");
    }
}

public sealed class VfxTexturedPathSpec
{
    [JsonRequired] public VfxTextureSpec Texture { get; set; } = null!;
    [JsonRequired] public string Source { get; set; } = "";
    [JsonRequired] public int HistoryTicks { get; set; }
    [JsonRequired] public float MinDistancePx { get; set; }
    [JsonRequired] public float MaxSegmentLengthPx { get; set; }
    [JsonRequired] public float WidthPx { get; set; }
    [JsonRequired] public VfxNumericProfileSpec WidthProfile { get; set; } = null!;
    [JsonRequired] public VfxNumericProfileSpec OpacityProfile { get; set; } = null!;
    [JsonRequired] public VfxColorProfileSpec ColorProfile { get; set; } = null!;
    [JsonRequired] public string ProfileDomain { get; set; } = "";
    [JsonRequired] public string UvMode { get; set; } = "";
    [JsonRequired] public float RepeatLengthPx { get; set; }
    [JsonRequired] public float ScrollPxPerTick { get; set; }
    internal void Validate(VfxSlotSpec slot)
    {
        if (Texture is null || WidthProfile is null || OpacityProfile is null || ColorProfile is null) throw new InvalidDataException("texturedPath requires texture and profiles");
        Texture.Validate(); WidthProfile.Validate(4); OpacityProfile.Validate(1); ColorProfile.Validate();
        VfxMaterialValidation.Choice(Source, "path source", "anchorHistory", "beam", "whip");
        VfxMaterialValidation.Choice(ProfileDomain, "profile domain", "age", "length"); VfxMaterialValidation.Choice(UvMode, "UV mode", "stretch", "repeat");
        VfxMaterialValidation.Range(MinDistancePx, 0, 16, "minimum sample distance"); VfxMaterialValidation.Range(MaxSegmentLengthPx, 1, 4096, "maximum segment length");
        VfxMaterialValidation.Range(WidthPx, 0, 96, "path width"); VfxMaterialValidation.Range(RepeatLengthPx, 1, 512, "repeat length"); VfxMaterialValidation.Range(ScrollPxPerTick, -32, 32, "UV scroll");
        if (Source == "anchorHistory" ? HistoryTicks is < 2 or > 32 : HistoryTicks != 0 || MinDistancePx != 0 || ProfileDomain != "length") throw new InvalidDataException("invalid VFX path sampling controls");
        if (Source != "anchorHistory" && slot.Anchor != "self") throw new InvalidDataException("geometry path requires anchor=self");
        if (UvMode == "stretch" && (RepeatLengthPx != 1 || ScrollPxPerTick != 0)) throw new InvalidDataException("stretch UV requires neutral repeat/scroll");
        if (slot.Event is not ("periodic" or "on_spawn") || slot.RepeatEvery != 0 || slot.Duration != 3) throw new InvalidDataException("texturedPath requires live periodic/on_spawn and neutral duration/cadence");
    }
}
