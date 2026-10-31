#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

internal readonly record struct VfxTrailPose(float Rotation,float Scale,SpriteEffects Effects,float GfxOffY,Vector2 Origin);
internal readonly record struct VfxTrailSample(ulong Tick,Vector2 Position,VfxTrailPose? Pose);
public sealed partial class InfiniVfxState
{
    internal readonly Dictionary<string,List<VfxTrailSample>> TrailHistory=new(StringComparer.Ordinal);
}
public static partial class InfiniVfxRuntime
{
    private static Texture2D? TrailTexture(GeneratedItemData data,string entityId,VfxHistoryTrailSpec trail,out SpritePresentationSelection selected)
    {
        var texture=trail.Texture!;
        if(texture.Source is "asset" or "library") {
            string path=InfiniDetachedVfxSystem.ResolveMaterialTexture(data,entityId,texture);
            selected=new(path,null,null,ImpactTexture:true);
        } else selected=SpritePresentation.Resolve(data,entityId,texture.Source);
        return string.IsNullOrEmpty(selected.Path)?null:InfiniDetachedVfxSystem.MaterialTexture(selected.Path,texture.Source=="library"?texture.AssetId:null);
    }
    private static VfxTrailPose? CaptureTrailPose(Texture2D texture,Projectile projectile,RuntimeEntitySpec? entity,SpritePresentationSelection selected,float scale)
    {
        if(scale<=0)return null;
        if(!selected.ImpactTexture&&(!selected.RenderSizePx.HasValue||!selected.ForwardAngleDegrees.HasValue))return null;
        SpriteEffects effects=projectile.spriteDirection<0?SpriteEffects.FlipHorizontally:SpriteEffects.None;
        float rotation=entity is null?selected.ProjectileRotation(entity,projectile.rotation,effects)
            :GeneratedProjectile.MotionSpriteRotation(entity,selected,projectile.rotation,effects);
        float drawScale=projectile.scale*scale*selected.FrameScale(texture.Width,texture.Height);
        if(!float.IsFinite(drawScale)||drawScale<=0)return null;
        Vector2 axis=projectile.ModProjectile is GeneratedProjectile generated&&generated.TryGetMotionPresentationAxis(out var motionAxis)
            ?motionAxis:projectile.velocity.SafeNormalize(Vector2.UnitX);
        Vector2 origin=entity is null?selected.ProjectileOrigin(entity,texture.Width,texture.Height,drawScale,effects)
            :GeneratedProjectile.MotionSpriteOrigin(entity,selected,texture.Width,texture.Height,drawScale,effects,rotation,axis);
        return new(rotation,drawScale,effects,projectile.gfxOffY,origin);
    }
    internal static bool TryExplicitTrailTip(Projectile projectile,GeneratedItemData data,string entityId,out Vector2 tip)
    {
        var entity=data.RuntimeProgram.TryGetEntity(entityId);
        bool beam=entity?.BeamGeometry is not null||entity?.Controller.Code==RuntimeControllerCode.ChannelBeam;
        bool lash=entity?.LashGeometry is not null||entity?.Movement is {IsConfigured:true,Code:18};
        if(beam||lash) {
            tip=default;
            if(projectile.ModProjectile is not GeneratedProjectile generated
                ||!generated.TryCapturePresentationGeometry(beam?"beam":"whip",out var points))return false;
            tip=points[^1];return true;
        }
        tip=ForwardTip(projectile,data,entityId);return float.IsFinite(tip.X)&&float.IsFinite(tip.Y);
    }
    private static void CaptureExplicitTrails(Projectile projectile,GeneratedItemData data,string entityId,InfiniVfxState state)
    {
        ulong now=Main.GameUpdateCount;
        foreach(var slot in data.VfxManifest.Slots) {
            if(slot.EntityId!=entityId||slot.Trail is not {} trail)continue;
            if(!state.TrailHistory.TryGetValue(slot.Id,out var history))state.TrailHistory[slot.Id]=history=new();
            history.RemoveAll(s=>now<s.Tick||now-s.Tick>=32);
            if(history.Count>0&&history[0].Tick==now)continue;
            Vector2 position=projectile.Center;
            if(trail.Source=="tip"&&!TryExplicitTrailTip(projectile,data,entityId,out position))continue;
            VfxTrailPose? pose=null;
            if(trail.Draw=="sprites"&&TrailTexture(data,entityId,trail,out var selected) is {} texture)
                pose=CaptureTrailPose(texture,projectile,data.RuntimeProgram.TryGetEntity(entityId),selected,trail.Scale!.Value);
            if(history.Count==32)history.RemoveAt(history.Count-1);
            history.Insert(0,new(now,position,pose));
        }
    }
    private static void DrawExplicitTrail(Texture2D pixel,Projectile projectile,GeneratedItemData data,string entityId,VfxSlotSpec slot,VfxManifestSpec manifest,ref InfiniVfxState state)
    {
        if(!projectile.active||!state.TrailHistory.TryGetValue(slot.Id,out var history))return;
        var trail=slot.Trail!;
        Texture2D? texture=null;VfxTrailPose? pose=null;
        if(trail.Draw=="sprites") {
            texture=TrailTexture(data,entityId,trail,out var selected);if(texture is null)return;
            if(trail.Pose=="current")pose=CaptureTrailPose(texture,projectile,data.RuntimeProgram.TryGetEntity(entityId),selected,trail.Scale!.Value);
        }
        var budgetState=state;
        DrawExplicitTrailSamples(pixel,texture,history,trail,slot.Blend!,Main.GameUpdateCount,pose,()=>SpendDraw(manifest,ref budgetState,1));
    }
    internal static void DrawExplicitTrailSamples(Texture2D pixel,Texture2D? texture,IReadOnlyList<VfxTrailSample> history,VfxHistoryTrailSpec trail,string blend,ulong now,VfxTrailPose? currentPose,Func<bool> spend)
    {
        var opacity=VfxNumberRamp.Copy(trail.OpacityProfile);
        VfxTrailSample? previous=null;
        foreach(var sample in history) {
            if(now<sample.Tick)continue;
            ulong age=now-sample.Tick;
            if(age>=(ulong)trail.HistoryTicks||age<(ulong)trail.FirstSampleAgeTicks||(age-(ulong)trail.FirstSampleAgeTicks)%(ulong)trail.SampleStepTicks!=0)continue;
            float alpha=opacity.At(age/(float)trail.HistoryTicks);
            Color color=ApplyBlend(trail.Color.ToColor()*alpha,blend);
            if(trail.Draw=="stroke") {
                if(previous is {} p&&p.Tick>=sample.Tick&&p.Tick-sample.Tick==(ulong)trail.SampleStepTicks&&alpha>0&&trail.WidthPx!.Value>0&&Vector2.DistanceSquared(p.Position,sample.Position)>0) {
                    if(!spend())break;
                    DrawLine(pixel,p.Position-Main.screenPosition,sample.Position-Main.screenPosition,color,trail.WidthPx.Value,preserveWidth:true);
                }
                previous=sample;
            } else {
                var pose=trail.Pose=="sampled"?sample.Pose:currentPose;
                if(texture is null||pose is not {} draw||alpha<=0||trail.Scale<=0)continue;
                if(!spend())break;
                VfxTextureUv.Copy(trail.Texture!.Uv).Draw(Main.spriteBatch,texture,sample.Position-Main.screenPosition+new Vector2(0,draw.GfxOffY),color,
                    draw.Rotation,draw.Origin,new Vector2(draw.Scale),draw.Effects);
            }
        }
    }
}
