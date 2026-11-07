#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxNativeDustSpec
{
    [JsonRequired] public VfxSpawnSpec Spawn { get; set; } = null!;

    [JsonRequired] public string Type { get; set; } = "";
    [JsonRequired] public int Count { get; set; }
    [JsonRequired] public float Size { get; set; }
    [JsonRequired] public float SpeedMinPxPerTick { get; set; }
    [JsonRequired] public float SpeedMaxPxPerTick { get; set; }
    [JsonRequired] public float SpreadRadians { get; set; }
    [JsonRequired] public float InheritVelocity { get; set; }
    [JsonRequired] public int NativeAlpha { get; set; }
    [JsonRequired] public bool NoGravity { get; set; }
    [JsonRequired] public string AngularDistribution { get; set; } = "";
    [JsonRequired] public string DirectionFrame { get; set; } = "";
    [JsonRequired] public float AngleOffsetRadians { get; set; }
    internal VfxNativeDustSpec Copy() { var copy=(VfxNativeDustSpec)MemberwiseClone(); copy.Spawn=Spawn.Copy();return copy; }
    internal void Validate()
    {
        if (Spawn is null) throw new InvalidDataException("spawn is required");
        Spawn.Validate();
        _ = VfxRendererRegistry.DustId(Type);
        VfxMaterialValidation.Choice(AngularDistribution,"dust distribution","random","even");
        VfxMaterialValidation.Choice(DirectionFrame,"dust frame","world","source");
        VfxMaterialValidation.Range(AngleOffsetRadians,-MathF.Tau,MathF.Tau,"dust angle offset");
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
    internal static void Validate(VfxSlotSpec slot)
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
        if(slot.Alpha is not null||slot.Duration is not null
            ||slot.Blend is not null||slot.Layer is not null||slot.Shape is not null||slot.Element is not null||slot.Path is not null||slot.Particle is not null||slot.ScreenShake is not null
            ||slot.Sound is not null||slot.SoundId is not null)throw new InvalidDataException("Native cue forbids unrelated controls");
    }
}
