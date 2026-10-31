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
    private float? _InnerRadiusStartPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? InnerRadiusStartPx { get=>_InnerRadiusStartPx; set=>_InnerRadiusStartPx=value??throw new InvalidDataException("shape.InnerRadiusStartPx cannot be null"); }
    private float? _InnerRadiusEndPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? InnerRadiusEndPx { get=>_InnerRadiusEndPx; set=>_InnerRadiusEndPx=value??throw new InvalidDataException("shape.InnerRadiusEndPx cannot be null"); }
    private float? _OuterRadiusStartPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? OuterRadiusStartPx { get=>_OuterRadiusStartPx; set=>_OuterRadiusStartPx=value??throw new InvalidDataException("shape.OuterRadiusStartPx cannot be null"); }
    private float? _OuterRadiusEndPx;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? OuterRadiusEndPx { get=>_OuterRadiusEndPx; set=>_OuterRadiusEndPx=value??throw new InvalidDataException("shape.OuterRadiusEndPx cannot be null"); }
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
    private string? _opacityCurve,_moteOrientation,_rotationFrame;
    private float? _moteRotationRadians;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public string? RotationFrame { get=>_rotationFrame; set=>_rotationFrame=value??throw new InvalidDataException("shape rotationFrame cannot be null"); }
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public string? OpacityCurve { get=>_opacityCurve; set=>_opacityCurve=value??throw new InvalidDataException("shape opacityCurve cannot be null"); }
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public string? MoteOrientation { get=>_moteOrientation; set=>_moteOrientation=value??throw new InvalidDataException("shape moteOrientation cannot be null"); }
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? MoteRotationRadians { get=>_moteRotationRadians; set=>_moteRotationRadians=value??throw new InvalidDataException("shape moteRotationRadians cannot be null"); }
    internal VfxShapeSpec Copy()
    {
        var copy=(VfxShapeSpec)MemberwiseClone();
        copy.ColorStart=new RuntimeRgbSpec { R=ColorStart.R,G=ColorStart.G,B=ColorStart.B };
        copy.ColorEnd=new RuntimeRgbSpec { R=ColorEnd.R,G=ColorEnd.G,B=ColorEnd.B };
        return copy;
    }
    internal void Validate(VfxSlotSpec slot)
    {
        VfxMaterialValidation.Choice(Kind,"shape kind","line","arc","wave","orbit","sector");
        VfxMaterialValidation.Choice(Attachment,"shape attachment","world","source");
        VfxMaterialValidation.Range(OffsetForwardPx,-128,128,"shape offsetForwardPx");
        VfxMaterialValidation.Range(OffsetSidePx,-128,128,"shape offsetSidePx");
        VfxMaterialValidation.Range(RotationRadians,-MathF.Tau,MathF.Tau,"shape rotation");
        VfxMaterialValidation.Range(RotationSpeedRadiansPerTick,-MathF.Tau,MathF.Tau,"shape spin");
        VfxMaterialValidation.Range(OpacityStart,0,1,"shape opacity start");
        VfxMaterialValidation.Range(OpacityEnd,0,1,"shape opacity end");
        if(ColorStart is null||ColorEnd is null)throw new InvalidDataException("shape requires colors");
        ColorStart.Validate();ColorEnd.Validate();
        if(RotationFrame is not null)VfxMaterialValidation.Choice(RotationFrame,"shape rotation frame","world","source");
        if(OpacityCurve is not null)VfxMaterialValidation.Choice(OpacityCurve,"shape opacity curve","linear","easeIn","easeOut","smoothStep");
        if(Kind!="orbit"&&(MoteOrientation is not null||MoteRotationRadians is not null))throw new InvalidDataException("foreign shape mote orientation");
        if(MoteOrientation is not null)VfxMaterialValidation.Choice(MoteOrientation,"shape mote orientation","world","orbit");
        if(MoteRotationRadians is {} moteRotation)VfxMaterialValidation.Range(moteRotation,-MathF.Tau,MathF.Tau,"shape mote rotation");
        if(Attachment=="source" && slot.Event is "on_expire" or "on_kill")
            throw new InvalidDataException("terminal shape requires world attachment");
        if(slot.Event==RuntimeEventKind.Periodic ? slot.RepeatEvery is null or <1 : slot.RepeatEvery!=0)
            throw new InvalidDataException("invalid shape cadence");
        Check(LengthPx, Kind is "line" or "wave", 0, 512f, "LengthPx");
        Check(WidthPx, Kind is "line" or "arc" or "wave", 0, 128f, "WidthPx");
        Check(RadiusStartPx, Kind is "arc" or "orbit", 0, 256f, "RadiusStartPx");
        Check(RadiusEndPx, Kind is "arc" or "orbit", 0, 256f, "RadiusEndPx");
        Check(SweepRadians, Kind is "arc" or "sector", -6.283185307179586f, 6.283185307179586f, "SweepRadians");
        Check(Segments, Kind is "arc" or "wave" or "sector", Kind=="sector"?3:1, 64f, "Segments");
        Check(InnerRadiusStartPx, Kind=="sector", 0, 256, "InnerRadiusStartPx");
        Check(InnerRadiusEndPx, Kind=="sector", 0, 256, "InnerRadiusEndPx");
        Check(OuterRadiusStartPx, Kind=="sector", 0, 256, "OuterRadiusStartPx");
        Check(OuterRadiusEndPx, Kind=="sector", 0, 256, "OuterRadiusEndPx");
        if(Kind=="sector"&&(InnerRadiusStartPx>OuterRadiusStartPx||InnerRadiusEndPx>OuterRadiusEndPx))throw new InvalidDataException("sector inner radius exceeds outer radius");
        Check(TailOpacityStart, Kind is "arc", 0, 1f, "TailOpacityStart");
        Check(TailOpacityEnd, Kind is "arc", 0, 1f, "TailOpacityEnd");
        Check(AmplitudePx, Kind is "wave", 0, 128f, "AmplitudePx");
        Check(Cycles, Kind is "wave", 0, 8f, "Cycles");
        Check(PhaseRadians, Kind is "wave", -6.283185307179586f, 6.283185307179586f, "PhaseRadians");
        Check(PhaseSpeedRadiansPerTick, Kind is "wave", -MathF.Tau, MathF.Tau, "PhaseSpeedRadiansPerTick");
        Check(Count, Kind is "orbit", 0, 64f, "Count");
        Check(MoteSizePx, Kind is "orbit", 0, 128f, "MoteSizePx");
    }
    private static void Check(float? value,bool required,float min,float max,string name)
    {
        if(required!=value.HasValue)throw new InvalidDataException("missing/foreign shape."+name);
        if(value is {} v)VfxMaterialValidation.Range(v,min,max,"shape."+name);
    }
}
