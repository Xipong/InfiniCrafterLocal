#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxNativeDustSpec
{
    private VfxSpawnSpec? _spawn;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public VfxSpawnSpec? Spawn {get=>_spawn;set=>_spawn=value??throw new InvalidDataException("spawn cannot be null");}

    [JsonRequired] public string Type { get; set; } = "";
    [JsonRequired] public int Count { get; set; }
    [JsonRequired] public float Size { get; set; }
    [JsonRequired] public float SpeedMinPxPerTick { get; set; }
    [JsonRequired] public float SpeedMaxPxPerTick { get; set; }
    [JsonRequired] public float SpreadRadians { get; set; }
    [JsonRequired] public float InheritVelocity { get; set; }
    [JsonRequired] public int NativeAlpha { get; set; }
    [JsonRequired] public bool NoGravity { get; set; }
    private string? _angularDistribution,_directionFrame;
    private float? _angleOffsetRadians;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public string? AngularDistribution { get=>_angularDistribution; set=>_angularDistribution=value??throw new InvalidDataException("dust angularDistribution cannot be null"); }
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public string? DirectionFrame { get=>_directionFrame; set=>_directionFrame=value??throw new InvalidDataException("dust directionFrame cannot be null"); }
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? AngleOffsetRadians { get=>_angleOffsetRadians; set=>_angleOffsetRadians=value??throw new InvalidDataException("dust angleOffsetRadians cannot be null"); }
    internal VfxNativeDustSpec Copy() { var copy=(VfxNativeDustSpec)MemberwiseClone(); if(Spawn is not null)copy.Spawn=Spawn.Copy();return copy; }
    internal void Validate()
    {
        Spawn?.Validate();
        _ = VfxRendererRegistry.DustId(Type);
        if(AngularDistribution is not null)VfxMaterialValidation.Choice(AngularDistribution,"dust distribution","random","even");
        if(DirectionFrame is not null)VfxMaterialValidation.Choice(DirectionFrame,"dust frame","world","source");
        if(AngleOffsetRadians is {} offset)VfxMaterialValidation.Range(offset,-MathF.Tau,MathF.Tau,"dust angle offset");
        if (Count is < 0 or > 64 || NativeAlpha is < 0 or > 255) throw new InvalidDataException("Invalid native dust count/alpha");
        VfxNativeCueValidation.Range(Size,0,3); VfxNativeCueValidation.Range(SpeedMinPxPerTick,0,24);
        VfxNativeCueValidation.Range(SpeedMaxPxPerTick,SpeedMinPxPerTick,24);
        VfxNativeCueValidation.Range(SpreadRadians,0,MathF.Tau); VfxNativeCueValidation.Range(InheritVelocity,0,1);
    }
}
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxNativeLightSpec
{
    [JsonRequired] public float Intensity { get; set; }
    internal void Validate() => VfxNativeCueValidation.Range(Intensity,0,1.2f);
}
internal static class VfxNativeCueValidation
{
    internal static void Range(float value,float min,float max)
    {
        if(!float.IsFinite(value)||value<min||value>max) throw new InvalidDataException("Invalid native cue numeric range");
    }
    internal static void Validate(VfxSlotSpec slot,bool phasePresent)
    {
        bool dust=slot.RendererKind=="nativeDust",light=slot.RendererKind=="nativeLight";
        if(!dust&&!light) {
            if(slot.Dust is not null||slot.Light is not null)throw new InvalidDataException("Foreign native cue payload");
            return;
        }
        if(dust?(slot.Dust is null||slot.Light is not null):(slot.Light is null||slot.Dust is not null))throw new InvalidDataException("Native cue requires exact payload");
        slot.Dust?.Validate(); slot.Light?.Validate();
        if(slot.Color is null)throw new InvalidDataException("Native cue requires color");
        slot.Color.Validate();
        if(slot.StartTick is null or <0 or >120 || slot.RepeatEvery is null or <0 or >120
            || (slot.Event==RuntimeEventKind.Periodic ? slot.RepeatEvery<1 : slot.RepeatEvery!=0))throw new InvalidDataException("Native cue requires exact cadence");
        if(slot.Anchor is not ("self" or "owner" or "tip" or "tipHistory" or "hitPoint" or "velocity" or "field"))throw new InvalidDataException("Invalid native cue anchor");
        if(phasePresent||slot.Scale is not null||slot.Density is not null||slot.Spread is not null||slot.Alpha is not null||slot.Duration is not null
            ||slot.ParticleSystemId is not null||slot.Blend is not null||slot.Layer is not null||slot.TextureRole is not null
            ||slot.Shape is not null||slot.Element is not null||slot.Path is not null||slot.Particle is not null||slot.ScreenShake is not null
            ||slot.Sound is not null||slot.SoundId is not null)throw new InvalidDataException("Native cue forbids unrelated controls");
    }
}
