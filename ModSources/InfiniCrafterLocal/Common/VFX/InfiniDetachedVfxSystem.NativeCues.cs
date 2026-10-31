#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

public sealed partial class InfiniDetachedVfxSystem
{
    private sealed record NativeCueDesign(VfxNativeDustSpec? Dust,float? Light,VfxNativeEffectSpec? Effect,Color Color,int Seed,int MaxPerTick,int MaxTotal,bool Item);
    private sealed record NativeCueEmission(NativeCueDesign Design,string SourceKey,VfxSourceFrame Frame,ulong Due,MaterialEventAllowance? Allowance);
    private static readonly List<NativeCueEmission> NativeCueEmissions=new();
    private static NativeCueDesign CopyNativeCue(GeneratedItemData data,VfxSlotSpec slot,bool item)
        =>new(slot.Dust?.Copy(),slot.Light?.Intensity,slot.NativeEffect?.Copy(),slot.Color?.ToColor()??Color.Transparent,slot.SlotSeed,
            data.VfxManifest.Budget.MaxParticlesPerTick,data.VfxManifest.Budget.MaxParticlesTotal,item);
    private static bool EnqueueNativeCue(GeneratedItemData data,VfxSlotSpec slot,string sourceKey,VfxSourceFrame frame,bool item,MaterialEventAllowance? allowance)
        =>EnqueueCopiedNativeCue(CopyNativeCue(data,slot,item),sourceKey,frame,slot.Event==RuntimeEventKind.Periodic?0:slot.StartTick!.Value,allowance);
    private static bool EnqueueCopiedNativeCue(NativeCueDesign design,string sourceKey,VfxSourceFrame frame,int delay,MaterialEventAllowance? allowance)
    {
        if(Main.dedServ||design.Effect is not null&&Main.netMode==Terraria.ID.NetmodeID.Server||!frame.Valid||string.IsNullOrWhiteSpace(sourceKey)||OwnedRecordCount>=MaxEmissions)return false;
        if(design.Dust is { } d&&(d.Count==0||d.Size==0)||design.Light==0)return false;
        var emission=new NativeCueEmission(design,sourceKey,frame,Main.GameUpdateCount+(ulong)delay,allowance);
        if(delay==0)EmitNativeCue(emission);else NativeCueEmissions.Add(emission);
        return true;
    }
    private static void UpdateNativeCues(ulong now)
    {
        for(int i=NativeCueEmissions.Count-1;i>=0;i--) {
            var e=NativeCueEmissions[i];if(now<e.Due)continue;
            EmitNativeCue(e);NativeCueEmissions.RemoveAt(i);
        }
    }
    private static void EmitNativeCue(NativeCueEmission emission)
    {
        var design=emission.Design;
        if(design.Effect is {} effect) { EmitNativeEffect(emission,effect); return; }
        if(design.Light is { } intensity) {
            float strength=intensity*InfiniVfxClientOptions.PresentationLightMultiplier;
            if(strength>0)Lighting.AddLight(emission.Frame.Position,design.Color.ToVector3()*strength);
            return;
        }
        var d=design.Dust!;
        int count=Math.Min(64,InfiniVfxClientOptions.ScaleParticleCount(d.Count));
        var random=new Random(design.Seed^unchecked((int)emission.Due));
        var positions=VfxSpawnGeometry.CreateRandom(d.Spawn,design.Seed,emission.Due);
        for(int i=0;i<count;i++) {
            if(design.MaxTotal<=0||emission.Allowance is {Remaining:<=0}
                ||!TrySpendDetachedParticle(emission.SourceKey,design.MaxPerTick,design.Item?int.MaxValue:design.MaxTotal))break;
            if(emission.Allowance is { } allowance)allowance.Remaining--;
            float angle=d.AngularDistribution=="even"
                ? count<=1?0:-d.SpreadRadians*.5f+i*d.SpreadRadians/(d.SpreadRadians>=MathF.Tau?count:count-1)
                :((float)random.NextDouble()-.5f)*d.SpreadRadians;
            angle+=d.AngleOffsetRadians??0;
            float speed=MathHelper.Lerp(d.SpeedMinPxPerTick,d.SpeedMaxPxPerTick,(float)random.NextDouble());
            Vector2 velocity=(d.DirectionFrame=="world"?Vector2.UnitX:emission.Frame.Forward).RotatedBy(angle)*speed+emission.Frame.Velocity*d.InheritVelocity;
            Vector2 position=emission.Frame.Position+VfxSpawnGeometry.SampleWorld(d.Spawn,emission.Frame.Forward,positions);
            Dust dust=Dust.NewDustPerfect(position,VfxRendererRegistry.DustId(d.Type),velocity,d.NativeAlpha,design.Color,d.Size);
            dust.noGravity=d.NoGravity;
        }
    }
}
