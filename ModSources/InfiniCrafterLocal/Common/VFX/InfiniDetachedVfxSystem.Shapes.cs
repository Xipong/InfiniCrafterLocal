#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;

namespace InfiniCrafterLocal.Common.VFX;

public sealed partial class InfiniDetachedVfxSystem
{
    private sealed record ShapeDesign(VfxShapeSpec Geometry,string Layer,string Blend,int Duration,int MaxDraw);
    private sealed class ShapeEmission
    {
        internal required ShapeDesign Design;
        internal required string SourceKey,Anchor;
        internal VfxSourceFrame Frame;
        internal VfxSourceBinding? Binding;
        internal Vector2 SourceAnchorOffset;
        internal ulong Due;
    }
    private static readonly List<ShapeEmission> ShapeEmissions=new();
    private static ShapeDesign CopyShape(GeneratedItemData data,VfxSlotSpec slot)
        =>new(slot.Shape!.Copy(),slot.Layer!,slot.Blend!,slot.Duration!.Value,data.VfxManifest.Budget.MaxDrawCalls);
    internal static bool EnqueueShape(GeneratedItemData data,VfxSlotSpec slot,string sourceKey,VfxSourceFrame frame,VfxSourceBinding? binding)
        =>EnqueueCopiedShape(CopyShape(data,slot),sourceKey,frame,binding,slot.Anchor,slot.Event==RuntimeEventKind.Periodic?0:slot.StartTick!.Value);
    private static bool EnqueueCopiedShape(ShapeDesign design,string sourceKey,VfxSourceFrame frame,VfxSourceBinding? binding,string anchor,int delay)
    {
        if(Main.dedServ||!frame.Valid||string.IsNullOrEmpty(sourceKey)||OwnedRecordCount>=MaxEmissions)return false;
        bool attached=design.Geometry.Attachment=="source";
        if(attached&&(binding is null||!binding.IsLive))return false;
        var emission=new ShapeEmission{Design=design,SourceKey=sourceKey,Anchor=anchor,Frame=frame,Binding=attached?binding:null,Due=Main.GameUpdateCount+(ulong)delay};
        if(attached&&anchor=="hitPoint") {
            if(!binding!.TryFrame("self",out var source))return false;
            emission.SourceAnchorOffset=frame.Inverse(frame.Position-(frame.SourceCenter??source.Position));
            emission.Anchor="self";
        }
        ShapeEmissions.Add(emission);return true;
    }
    private static void UpdateShapes(ulong now)
    {
        ShapeEmissions.RemoveAll(e=>now>=e.Due+(ulong)e.Design.Duration
            ||e.Design.Geometry.Attachment=="source"&&(e.Binding is null||!e.Binding.IsLive));
        foreach(var e in ShapeEmissions)if(e.Binding is not null&&e.Binding.TryFrame(e.Anchor,out var frame))e.Frame=frame;
    }
    private static void DrawShapes(string layer,Texture2D pixel,Action ensureBegin)
    {
        ulong now=Main.GameUpdateCount;
        foreach(var e in ShapeEmissions) {
            if(e.Design.Layer!=layer||now<e.Due||now-e.Due>=(ulong)e.Design.Duration)continue;
            if(e.Binding is not null&&!e.Binding.TryFrame(e.Anchor,out e.Frame))continue;
            var frame=e.Frame with {Position=e.Frame.Position+e.Frame.Rotate(e.SourceAnchorOffset)};
            DrawExplicitShape(pixel,e.Design.Geometry,frame,(float)(now-e.Due),e.Design.Duration,e.Design.Blend,()=>{
                if(!TrySpendSourceDraw(e.SourceKey,e.Design.MaxDraw,1))return false;
                ensureBegin();return true;
            });
        }
    }
    // Geometry is determined only by authored controls. One draw per segment or
    // square mote; color/opacity interpolate once, no separate lifetime fade.
    internal static void DrawExplicitShape(Texture2D pixel,VfxShapeSpec s,VfxSourceFrame frame,float age,int duration,string blend,Func<bool> spend)
    {
        if(s.Kind=="wave"&&s.LengthPx<=0)return;
        float t=Math.Clamp(age/duration,0,1);
        float opacity=MathHelper.Lerp(s.OpacityStart,s.OpacityEnd,t);
        if(opacity<=0)return;
        Color color=InfiniVfxRuntime.ApplyBlend(new Color(Vector3.Lerp(s.ColorStart.ToColor().ToVector3(),s.ColorEnd.ToColor().ToVector3(),t))*opacity,blend);
        float rotation=frame.Forward.ToRotation()+s.RotationRadians+s.RotationSpeedRadiansPerTick*age;
        Vector2 forward=rotation.ToRotationVector2(),normal=new(-forward.Y,forward.X);
        Vector2 origin=frame.Position+frame.Rotate(new(s.OffsetForwardPx,s.OffsetSidePx))-Main.screenPosition;
        bool Line(Vector2 a,Vector2 b,Color tint,float width) {
            if(width<=0||Vector2.DistanceSquared(a,b)<=0)return true;
            if(!spend())return false;
            InfiniVfxRuntime.DrawLine(pixel,a,b,tint,width,preserveWidth:true);return true;
        }
        if(s.Kind=="line") {Line(origin,origin+forward*s.LengthPx!.Value,color,s.WidthPx!.Value);return;}
        if(s.Kind=="orbit") {
            float radius=MathHelper.Lerp(s.RadiusStartPx!.Value,s.RadiusEndPx!.Value,t),size=s.MoteSizePx!.Value;
            if(size<=0)return;
            for(int i=0;i<s.Count!.Value;i++) {
                if(!spend())break;
                Vector2 pos=origin+(rotation+MathF.Tau*i/s.Count.Value).ToRotationVector2()*radius;
                Main.spriteBatch.Draw(pixel,pos,null,color,rotation,new Vector2(pixel.Width,pixel.Height)*.5f,
                    new Vector2(size/pixel.Width,size/pixel.Height),SpriteEffects.None,0);
            }
            return;
        }
        int segments=s.Segments!.Value;
        Vector2 Point(float u)=>s.Kind=="arc"
            ?origin+(rotation+s.SweepRadians!.Value*u).ToRotationVector2()*MathHelper.Lerp(s.RadiusStartPx!.Value,s.RadiusEndPx!.Value,t)
            :origin+forward*(s.LengthPx!.Value*u)+normal*(s.AmplitudePx!.Value*MathF.Sin(MathF.Tau*s.Cycles!.Value*u+s.PhaseRadians!.Value+s.PhaseSpeedRadiansPerTick!.Value*age));
        Vector2 previous=Point(0);
        for(int i=1;i<=segments;i++) {
            Vector2 next=Point(i/(float)segments);
            float along=s.Kind=="arc"?MathHelper.Lerp(s.TailOpacityStart!.Value,s.TailOpacityEnd!.Value,(i-.5f)/segments):1;
            if(along>0&&!Line(previous,next,color*along,s.WidthPx!.Value))break;
            previous=next;
        }
    }
}
