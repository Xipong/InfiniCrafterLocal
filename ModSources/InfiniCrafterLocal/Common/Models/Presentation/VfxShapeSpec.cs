#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
namespace InfiniCrafterLocal.Common.Models;

// Explicit cosmetic geometry. No scale/density presets or implicit life envelope.
public sealed class VfxShapeSpec
{
    [JsonRequired] public string Kind { get; set; } = "";
    [JsonRequired] public string Attachment { get; set; } = "";
    [JsonRequired] public float OffsetForwardPx { get; set; }
    [JsonRequired] public float OffsetSidePx { get; set; }
    [JsonRequired] public float RotationRadians { get; set; }
    [JsonRequired] public float RotationSpeedRadiansPerTick { get; set; }
    [JsonRequired] public RuntimeRgbSpec ColorStart { get; set; } = null!;
    [JsonRequired] public RuntimeRgbSpec ColorEnd { get; set; } = null!;
    [JsonRequired] public float OpacityStart { get; set; }
    [JsonRequired] public float OpacityEnd { get; set; }
    private float? _LengthPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? LengthPx { get => _LengthPx; set => _LengthPx=value ?? throw new InvalidDataException("shape.LengthPx cannot be null"); }
    private float? _WidthPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? WidthPx { get => _WidthPx; set => _WidthPx=value ?? throw new InvalidDataException("shape.WidthPx cannot be null"); }
    private float? _RadiusStartPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? RadiusStartPx { get => _RadiusStartPx; set => _RadiusStartPx=value ?? throw new InvalidDataException("shape.RadiusStartPx cannot be null"); }
    private float? _RadiusEndPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? RadiusEndPx { get => _RadiusEndPx; set => _RadiusEndPx=value ?? throw new InvalidDataException("shape.RadiusEndPx cannot be null"); }
    private float? _SweepRadians;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? SweepRadians { get => _SweepRadians; set => _SweepRadians=value ?? throw new InvalidDataException("shape.SweepRadians cannot be null"); }
    private int? _Segments;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public int? Segments { get => _Segments; set => _Segments=value ?? throw new InvalidDataException("shape.Segments cannot be null"); }
    private float? _TailOpacityStart;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? TailOpacityStart { get => _TailOpacityStart; set => _TailOpacityStart=value ?? throw new InvalidDataException("shape.TailOpacityStart cannot be null"); }
    private float? _TailOpacityEnd;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? TailOpacityEnd { get => _TailOpacityEnd; set => _TailOpacityEnd=value ?? throw new InvalidDataException("shape.TailOpacityEnd cannot be null"); }
    private float? _AmplitudePx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? AmplitudePx { get => _AmplitudePx; set => _AmplitudePx=value ?? throw new InvalidDataException("shape.AmplitudePx cannot be null"); }
    private float? _Cycles;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? Cycles { get => _Cycles; set => _Cycles=value ?? throw new InvalidDataException("shape.Cycles cannot be null"); }
    private float? _PhaseRadians;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? PhaseRadians { get => _PhaseRadians; set => _PhaseRadians=value ?? throw new InvalidDataException("shape.PhaseRadians cannot be null"); }
    private float? _PhaseSpeedRadiansPerTick;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? PhaseSpeedRadiansPerTick { get => _PhaseSpeedRadiansPerTick; set => _PhaseSpeedRadiansPerTick=value ?? throw new InvalidDataException("shape.PhaseSpeedRadiansPerTick cannot be null"); }
    private int? _Count;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public int? Count { get => _Count; set => _Count=value ?? throw new InvalidDataException("shape.Count cannot be null"); }
    private float? _MoteSizePx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? MoteSizePx { get => _MoteSizePx; set => _MoteSizePx=value ?? throw new InvalidDataException("shape.MoteSizePx cannot be null"); }
    internal VfxShapeSpec Copy()
    {
        var copy=(VfxShapeSpec)MemberwiseClone();
        copy.ColorStart=new RuntimeRgbSpec { R=ColorStart.R,G=ColorStart.G,B=ColorStart.B };
        copy.ColorEnd=new RuntimeRgbSpec { R=ColorEnd.R,G=ColorEnd.G,B=ColorEnd.B };
        return copy;
    }
    internal void Validate(VfxSlotSpec slot)
    {
        VfxMaterialValidation.Choice(Kind,"shape kind","line","arc","wave","orbit");
        VfxMaterialValidation.Choice(Attachment,"shape attachment","world","source");
        VfxMaterialValidation.Range(OffsetForwardPx,-128,128,"shape offsetForwardPx");
        VfxMaterialValidation.Range(OffsetSidePx,-128,128,"shape offsetSidePx");
        VfxMaterialValidation.Range(RotationRadians,-MathF.Tau,MathF.Tau,"shape rotation");
        VfxMaterialValidation.Range(RotationSpeedRadiansPerTick,-1,1,"shape spin");
        VfxMaterialValidation.Range(OpacityStart,0,1,"shape opacity start");
        VfxMaterialValidation.Range(OpacityEnd,0,1,"shape opacity end");
        if(ColorStart is null||ColorEnd is null)throw new InvalidDataException("shape requires colors");
        ColorStart.Validate();ColorEnd.Validate();
        if(Attachment=="source" && slot.Event is "on_expire" or "on_kill")
            throw new InvalidDataException("terminal shape requires world attachment");
        if(slot.Event==RuntimeEventKind.Periodic ? slot.RepeatEvery is null or <1 : slot.RepeatEvery!=0)
            throw new InvalidDataException("invalid shape cadence");
        Check(LengthPx, Kind is "line" or "wave", 0, 512f, "LengthPx");
        Check(WidthPx, Kind is "line" or "arc" or "wave", 0, 128f, "WidthPx");
        Check(RadiusStartPx, Kind is "arc" or "orbit", 0, 256f, "RadiusStartPx");
        Check(RadiusEndPx, Kind is "arc" or "orbit", 0, 256f, "RadiusEndPx");
        Check(SweepRadians, Kind is "arc", -6.283185307179586f, 6.283185307179586f, "SweepRadians");
        Check(Segments, Kind is "arc" or "wave", 1, 64f, "Segments");
        Check(TailOpacityStart, Kind is "arc", 0, 1f, "TailOpacityStart");
        Check(TailOpacityEnd, Kind is "arc", 0, 1f, "TailOpacityEnd");
        Check(AmplitudePx, Kind is "wave", 0, 128f, "AmplitudePx");
        Check(Cycles, Kind is "wave", 0, 8f, "Cycles");
        Check(PhaseRadians, Kind is "wave", -6.283185307179586f, 6.283185307179586f, "PhaseRadians");
        Check(PhaseSpeedRadiansPerTick, Kind is "wave", -1, 1f, "PhaseSpeedRadiansPerTick");
        Check(Count, Kind is "orbit", 0, 64f, "Count");
        Check(MoteSizePx, Kind is "orbit", 0, 128f, "MoteSizePx");
    }
    private static void Check(float? value,bool required,float min,float max,string name)
    {
        if(required!=value.HasValue)throw new InvalidDataException("missing/foreign shape."+name);
        if(value is {} v)VfxMaterialValidation.Range(v,min,max,"shape."+name);
    }
}
