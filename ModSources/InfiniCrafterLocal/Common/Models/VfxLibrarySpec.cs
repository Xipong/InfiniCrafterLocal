#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

// Strict additive payloads, no recipe migration or library-motion presets.
public sealed class VfxLibraryParticleSpec
{
    [JsonRequired] public string TextureId { get; set; } = "";
    [JsonRequired] public int Count { get; set; }
    [JsonRequired] public float SpeedMinPxPerTick { get; set; }
    [JsonRequired] public float SpeedMaxPxPerTick { get; set; }
    [JsonRequired] public float SpreadRadians { get; set; }
    [JsonRequired] public float InheritVelocity { get; set; }
    [JsonRequired] public float Drag { get; set; }
    [JsonRequired] public float AccelerationXPxPerTickSquared { get; set; }
    [JsonRequired] public float AccelerationYPxPerTickSquared { get; set; }
    [JsonRequired] public float WidthPx { get; set; }
    [JsonRequired] public float HeightPx { get; set; }
    [JsonRequired] public float RotationRadians { get; set; }
    [JsonRequired] public float RotationSpeedRadiansPerTick { get; set; }
    [JsonRequired] public string ColorStart { get; set; } = "";
    [JsonRequired] public string ColorEnd { get; set; } = "";
    [JsonRequired] public float EndScaleMultiplier { get; set; }
    [JsonRequired] public float EndOpacity { get; set; }

    internal void Validate()
    {
        VfxMaterialValidation.Choice(TextureId,"particle.textureId","star");
        if(Count is <0 or >64)throw new InvalidDataException("invalid VFX particle.count");
        VfxMaterialValidation.Range(SpeedMinPxPerTick,0,24,"particle.speedMinPxPerTick");
        VfxMaterialValidation.Range(SpeedMaxPxPerTick,0,24,"particle.speedMaxPxPerTick");
        if(SpeedMaxPxPerTick<SpeedMinPxPerTick)throw new InvalidDataException("inverted VFX particle speed interval");
        VfxMaterialValidation.Range(SpreadRadians,0,MathF.Tau,"particle.spreadRadians");
        VfxMaterialValidation.Range(InheritVelocity,0,1,"particle.inheritVelocity");
        VfxMaterialValidation.Range(Drag,0,1,"particle.drag");
        VfxMaterialValidation.Range(AccelerationXPxPerTickSquared,-2,2,"particle.accelerationXPxPerTickSquared");
        VfxMaterialValidation.Range(AccelerationYPxPerTickSquared,-2,2,"particle.accelerationYPxPerTickSquared");
        VfxMaterialValidation.Range(WidthPx,0,128,"particle.widthPx");
        VfxMaterialValidation.Range(HeightPx,0,128,"particle.heightPx");
        VfxMaterialValidation.Range(RotationRadians,-MathF.Tau,MathF.Tau,"particle.rotationRadians");
        VfxMaterialValidation.Range(RotationSpeedRadiansPerTick,-1,1,"particle.rotationSpeedRadiansPerTick");
        ValidateColor(ColorStart);ValidateColor(ColorEnd);
        VfxMaterialValidation.Range(EndScaleMultiplier,0,4,"particle.endScaleMultiplier");
        VfxMaterialValidation.Range(EndOpacity,0,1,"particle.endOpacity");
    }
    private static void ValidateColor(string token)=>VfxMaterialValidation.Choice(token,"particle.color", "white","gray","brown","tan","red","orange","yellow","gold","green","cyan","blue","purple","pink","black","effect");
}

public sealed class VfxScreenShakeSpec
{
    [JsonRequired] public float StrengthPx { get; set; }
    [JsonRequired] public float AngularVarianceRadians { get; set; }
    [JsonRequired] public float DirectionRadians { get; set; }
    [JsonRequired] public float DissipationPxPerFrame { get; set; }
    [JsonRequired] public float TaperStartDistancePx { get; set; }
    [JsonRequired] public float TaperEndDistancePx { get; set; }
    internal void Validate()
    {
        VfxMaterialValidation.Range(StrengthPx,0,16,"screenShake.strengthPx");
        VfxMaterialValidation.Range(AngularVarianceRadians,0,MathF.Tau,"screenShake.angularVarianceRadians");
        VfxMaterialValidation.Range(DirectionRadians,-MathF.Tau,MathF.Tau,"screenShake.directionRadians");
        VfxMaterialValidation.Range(DissipationPxPerFrame,0.01f,16,"screenShake.dissipationPxPerFrame");
        VfxMaterialValidation.Range(TaperStartDistancePx,0,4096,"screenShake.taperStartDistancePx");
        VfxMaterialValidation.Range(TaperEndDistancePx,1,8192,"screenShake.taperEndDistancePx");
        if(TaperEndDistancePx<=TaperStartDistancePx)throw new InvalidDataException("inverted VFX screenShake taper interval");
    }
}

internal static class VfxLibraryValidation
{
    internal static bool HasPayload(VfxSlotSpec slot)=>slot.Particle is not null||slot.ScreenShake is not null;
    internal static void Validate(VfxSlotSpec slot,InfiniVfxRendererKind kind)
    {
        bool particle=kind==InfiniVfxRendererKind.LibraryParticle;
        bool shake=kind==InfiniVfxRendererKind.ScreenShakeCue;
        if(!particle&&!shake) {
            if(HasPayload(slot))throw new InvalidDataException("foreign VFX library payload");return;
        }
        if(slot.Element is not null||slot.Path is not null||particle&&(slot.Particle is null||slot.ScreenShake is not null)
            ||shake&&(slot.ScreenShake is null||slot.Particle is not null))throw new InvalidDataException("library renderer requires only its exact typed payload");
        if(slot.Scale!=1||slot.Density!=0||slot.Spread!=0||slot.Jitter!=0||slot.FadeIn!=0||slot.FadeOut!=0
            ||slot.PhaseOffset!=0||slot.SignatureWeight!=0||slot.VisualCost!=0||slot.BudgetWeight!=1||slot.EmissionMode!="none"
            ||slot.ParticleRole!="none"||slot.ParticleSystemId!="none"||slot.TextureRole!="none")throw new InvalidDataException("library renderer requires neutral unconsumed common controls");
        if(slot.StartTick is <0 or >120)throw new InvalidDataException("invalid VFX library startTick");
        if(particle) {
            if(slot.Backend!="Particle"||slot.Duration is <3 or >120||slot.Channel is not ("ambientParticles" or "impactParticles" or "decaySmoke")
                ||slot.Lane is not ("primary" or "support" or "accent" or "ornament")
                ||(slot.Event==RuntimeEventKind.Periodic?slot.RepeatEvery is <1 or >120:slot.RepeatEvery!=0))throw new InvalidDataException("invalid VFX library particle controls");
            VfxMaterialValidation.Range(slot.Alpha,0,1,"library alpha");slot.Particle!.Validate();
        }else {
            if(slot.Backend!="Realtime"||slot.Event==RuntimeEventKind.Periodic||slot.RepeatEvery!=0||slot.Duration!=3||slot.Alpha!=1
                ||slot.Blend!="alpha"||slot.Layer!="BeforeProjectiles"||slot.Channel!="screenShake"||slot.Lane!="cue")throw new InvalidDataException("invalid VFX screenShake cue controls");
            slot.ScreenShake!.Validate();
        }
    }
}
