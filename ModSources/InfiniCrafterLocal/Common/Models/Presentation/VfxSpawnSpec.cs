#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
namespace InfiniCrafterLocal.Common.Models;

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxSpawnSpec
{
    [JsonRequired] public string Shape {get;set;}="";
    private float? _length,_width,_height,_rotation,_inner,_outer;
    private string? _frame;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public float? LengthPx {get=>_length;set=>_length=value??throw new InvalidDataException("spawn length cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public float? WidthPx {get=>_width;set=>_width=value??throw new InvalidDataException("spawn width cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public float? HeightPx {get=>_height;set=>_height=value??throw new InvalidDataException("spawn height cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public float? RotationRadians {get=>_rotation;set=>_rotation=value??throw new InvalidDataException("spawn rotation cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public float? InnerRadiusPx {get=>_inner;set=>_inner=value??throw new InvalidDataException("spawn inner radius cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public float? OuterRadiusPx {get=>_outer;set=>_outer=value??throw new InvalidDataException("spawn outer radius cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] public string? Frame {get=>_frame;set=>_frame=value??throw new InvalidDataException("spawn frame cannot be null");}
    internal VfxSpawnSpec Copy()=>(VfxSpawnSpec)MemberwiseClone();
    internal void Validate()
    {
        VfxMaterialValidation.Choice(Shape,"spawn shape","point","line","rectangle","annulus");
        bool oriented=Shape is "line" or "rectangle";
        Check(LengthPx,Shape=="line",0,512,"length");
        Check(WidthPx,Shape=="rectangle",0,512,"width");Check(HeightPx,Shape=="rectangle",0,512,"height");
        Check(RotationRadians,oriented,-MathF.Tau,MathF.Tau,"rotation");
        Check(InnerRadiusPx,Shape=="annulus",0,256,"inner radius");Check(OuterRadiusPx,Shape=="annulus",0,256,"outer radius");
        if(oriented!=(Frame is not null))throw new InvalidDataException("missing/foreign spawn frame");
        if(Frame is not null)VfxMaterialValidation.Choice(Frame,"spawn frame","world","source");
        if(InnerRadiusPx>OuterRadiusPx)throw new InvalidDataException("inverted spawn annulus");
    }
    private static void Check(float? value,bool required,float min,float max,string name)
    {
        if(required!=value.HasValue)throw new InvalidDataException("missing/foreign spawn "+name);
        if(value is {} v)VfxMaterialValidation.Range(v,min,max,"spawn "+name);
    }
}
