#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
namespace InfiniCrafterLocal.Common.Models;

public sealed class VfxHistoryTrailSpec
{
    [JsonRequired] public string Draw {get;set;}="";
    [JsonRequired] public string Source {get;set;}="";
    [JsonRequired] public int HistoryTicks {get;set;}
    [JsonRequired] public int SampleStepTicks {get;set;}
    [JsonRequired] public int FirstSampleAgeTicks {get;set;}
    [JsonRequired] public VfxNumericProfileSpec OpacityProfile {get;set;}=null!;
    [JsonRequired] public RuntimeRgbSpec Color {get;set;}=null!;
    private float? _widthPx,_scale;
    private VfxTextureSpec? _texture;
    private string? _pose;
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? WidthPx {get=>_widthPx;set=>_widthPx=value??throw new InvalidDataException("trail width cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public float? Scale {get=>_scale;set=>_scale=value??throw new InvalidDataException("trail scale cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public VfxTextureSpec? Texture {get=>_texture;set=>_texture=value??throw new InvalidDataException("trail texture cannot be null");}
    [JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)]
    public string? Pose {get=>_pose;set=>_pose=value??throw new InvalidDataException("trail pose cannot be null");}
    internal static void ValidateSlot(VfxSlotSpec slot,bool hasPhase)
    {
        if(slot.RendererKind!="historyTrail") {
            if(slot.Trail is not null)throw new InvalidDataException("foreign trail payload");
            return;
        }
        if(slot.Trail is not {} t)throw new InvalidDataException("historyTrail requires trail");
        if(slot.Shape is not null||slot.Element is not null||slot.Path is not null||slot.Particle is not null||slot.ScreenShake is not null
            ||slot.Dust is not null||slot.Light is not null||slot.Sound is not null||slot.SoundId is not null||slot.Color is not null
            ||slot.Scale is not null||slot.Density is not null||slot.Alpha is not null||slot.Spread is not null||slot.TextureRole is not null
            ||slot.ParticleSystemId is not null||slot.Duration is not null||slot.RepeatEvery is not null||hasPhase||slot.PlacementBindingId is not null)
            throw new InvalidDataException("historyTrail forbids unused/foreign controls");
        VfxMaterialValidation.Choice(slot.Event,"trail event","on_spawn","periodic");
        VfxMaterialValidation.Choice(slot.Anchor,"trail anchor","self");
        VfxMaterialValidation.Choice(slot.Blend,"trail blend","alpha","additive");
        VfxMaterialValidation.Choice(slot.Layer,"trail layer","BeforeProjectiles","AfterProjectiles");
        if(slot.StartTick is not null)throw new InvalidDataException("trail forbids startTick");
        VfxMaterialValidation.Choice(t.Draw,"trail draw","stroke","sprites");
        VfxMaterialValidation.Choice(t.Source,"trail source","center","tip");
        if(t.HistoryTicks is <2 or >32||t.SampleStepTicks<1||t.SampleStepTicks>32||t.FirstSampleAgeTicks<0||t.FirstSampleAgeTicks>31)
            throw new InvalidDataException("invalid trail history sampling");
        if(t.OpacityProfile is null||t.Color is null)throw new InvalidDataException("trail requires opacity and color");
        t.OpacityProfile.Validate(1);t.Color.Validate();
        if(t.Draw=="stroke") {
            if(t.WidthPx is null||t.Scale is not null||t.Texture is not null||t.Pose is not null)throw new InvalidDataException("stroke requires only widthPx");
            VfxMaterialValidation.Range(t.WidthPx.Value,0,1024,"trail width");
        } else {
            if(t.WidthPx is not null||t.Scale is null||t.Texture is null||t.Pose is null)throw new InvalidDataException("sprites require texture/scale/pose");
            VfxMaterialValidation.Range(t.Scale.Value,0,5,"trail scale");t.Texture.Validate();
            VfxMaterialValidation.Choice(t.Pose,"trail pose","current","sampled");
        }
    }
}
