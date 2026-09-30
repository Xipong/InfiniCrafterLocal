#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

internal readonly record struct VfxNumberRamp(float Start, float Middle, float End, string Curve)
{
    internal static VfxNumberRamp Copy(VfxNumericProfileSpec p) => new(p.Start,p.Middle,p.End,p.Curve);
    internal static float Ease(float t,string curve) => curve switch {
        "easeIn" => t*t, "easeOut" => 1-(1-t)*(1-t), "smoothStep" => t*t*(3-2*t), _ => t };
    internal float At(float age) {
        age=Math.Clamp(age,0,1); bool first=age<=0.5f;
        return MathHelper.Lerp(first?Start:Middle,first?Middle:End,Ease(first?age*2:(age-0.5f)*2,Curve));
    }
}
internal readonly record struct VfxColorRamp(Vector3 Start, Vector3 Middle, Vector3 End, string Curve)
{
    internal static VfxColorRamp Copy(VfxColorProfileSpec p,Color effect) {
        Vector3 Resolve(string token) => (token=="effect" ? effect : token=="white" ? Color.White : RuntimeColorPolicy.Resolve(token,Color.White)).ToVector3();
        return new(Resolve(p.Start),Resolve(p.Middle),Resolve(p.End),p.Curve);
    }
    internal Color At(float age,float opacity,string blend) {
        age=Math.Clamp(age,0,1); bool first=age<=0.5f;
        Vector3 rgb=Vector3.Lerp(first?Start:Middle,first?Middle:End,VfxNumberRamp.Ease(first?age*2:(age-0.5f)*2,Curve));
        return InfiniVfxRuntime.ApplyBlend(new Color(new Vector4(rgb,1))*Math.Clamp(opacity,0,1),blend);
    }
}
internal sealed class MaterialEventAllowance(int remaining) { internal int Remaining=remaining; }

internal readonly record struct VfxSourceFrame(Vector2 Position,Vector2 Forward,Vector2 Velocity)
{
    internal Vector2? SourceCenter { get; init; }
    internal bool Valid => (!SourceCenter.HasValue||float.IsFinite(SourceCenter.Value.X)&&float.IsFinite(SourceCenter.Value.Y))&&float.IsFinite(Position.X)&&float.IsFinite(Position.Y)&&float.IsFinite(Velocity.X)&&float.IsFinite(Velocity.Y)
        &&float.IsFinite(Forward.X)&&float.IsFinite(Forward.Y)&&Math.Abs(Forward.LengthSquared()-1)<0.001f;
    internal Vector2 Rotate(Vector2 local) => Forward*local.X+new Vector2(-Forward.Y,Forward.X)*local.Y;
    internal Vector2 Inverse(Vector2 world) => new(Vector2.Dot(world,Forward),Vector2.Dot(world,new Vector2(-Forward.Y,Forward.X)));
}

public sealed partial class InfiniDetachedVfxSystem
{
    private const int MaxMaterialParticles=2048;
    private static readonly Dictionary<(string Source,string Slot,ulong Occurrence),ulong> MaterialOccurrences=new();
    private static ulong NextLocalMaterialOccurrence;
    internal static ulong NewMaterialOccurrence()=>++NextLocalMaterialOccurrence;
    internal static bool TryAdmitMaterialOccurrence(string source,string slot,ulong occurrence)
    {
        ulong now=Main.GameUpdateCount;
        foreach(var key in MaterialOccurrences.Where(p=>now<p.Value||now-p.Value>1200).Select(p=>p.Key).ToArray())MaterialOccurrences.Remove(key);
        var id=(source,slot,occurrence);if(MaterialOccurrences.ContainsKey(id)||MaterialOccurrences.Count>=4096)return false;
        MaterialOccurrences[id]=now;return true;
    }
    private sealed record ElementDesign(string TexturePath,string Layer,string Blend,float Alpha,int Duration,int Count,
        bool Attached,Vector2 Offset,float SpeedMin,float SpeedMax,float Spread,float Inheritance,float Drag,Vector2 Acceleration,
        float Rotation,float Spin,float Width,float Height,VfxNumberRamp WidthRamp,VfxNumberRamp HeightRamp,VfxNumberRamp OpacityRamp,VfxColorRamp ColorRamp,
        int MaxDraw,int MaxPerTick,int MaxTotal,bool ItemBudget,int Seed);
    private sealed class MaterialParticle {
        internal Vector2 Position,Velocity;
        internal float Rotation;
    }
    private sealed class MaterialEmission {
        internal required string SourceKey;
        internal required ElementDesign Design;
        internal VfxSourceFrame Frame,InitialFrame;
        internal ulong Due,Start;
        internal int IntegratedAge;
        internal bool Started;
        internal MaterialParticle[] Particles=Array.Empty<MaterialParticle>();
        internal VfxSourceBinding? Binding;
        internal MaterialEventAllowance? Allowance;
        internal string Anchor="self";
        internal Vector2 SourceAnchorOffset;
    }
    private static readonly List<MaterialEmission> MaterialEmissions=new();
    private sealed class PeriodicElement {
        internal required VfxSourceBinding Binding;
        internal required ElementDesign Design;
        internal required string SourceKey,SlotId,Anchor;
        internal ulong FirstTick,LastTick=ulong.MaxValue;
        internal int StartTick,RepeatEvery,InitialAge;
        internal bool Item;
    }
    private static readonly List<PeriodicElement> PeriodicElements=new();
    internal static void RegisterPeriodicElements(GeneratedItemData data,string entityId,string sourceKey,VfxSourceBinding? binding,bool item=false)
    {
        if(Main.dedServ||binding is null||!binding.IsLive)return;
        foreach(var slot in data.VfxManifest.Slots) {
            if(slot.EntityId!=entityId||slot.Event!=RuntimeEventKind.Periodic||slot.Element is null)continue;
            if(PeriodicElements.Any(e=>ReferenceEquals(e.Binding.Generation,binding.Generation)&&e.SlotId==slot.Id))continue;
            if(PeriodicElements.Count>=MaxEmissions)return;
            string texture=ResolveMaterialTexture(data,entityId,slot.Element.Texture);
            if(string.IsNullOrEmpty(texture))continue;
            PeriodicElements.Add(new PeriodicElement{Binding=binding,Design=CopyElement(data,slot,texture,item),SourceKey=sourceKey,
                SlotId=slot.Id,Anchor=slot.Anchor,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge,StartTick=slot.StartTick,RepeatEvery=Math.Max(1,slot.RepeatEvery),Item=item});
        }
    }
    private static ulong LastMaterialsTick=ulong.MaxValue;
    private static void UpdatePeriodicElements(ulong now)
    {
        PeriodicElements.RemoveAll(e=>!e.Binding.IsLive);
        foreach(var e in PeriodicElements) {
            if(e.LastTick==now)continue;e.LastTick=now;
            ulong age=e.Item?now:now-e.FirstTick+(ulong)Math.Max(0,e.InitialAge);
            if(age<(ulong)e.StartTick||(age-(ulong)e.StartTick)%(ulong)e.RepeatEvery!=0)continue;
            if(e.Binding.TryFrame(e.Anchor,out var frame)) EnqueueCopiedElement(e.Design,e.SourceKey,frame,e.Binding,e.Anchor,0);
        }
    }

    internal static string ResolveMaterialTexture(GeneratedItemData data,string entityId,VfxTextureSpec texture)
    {
        if(texture.Source=="asset") return data.VfxManifest.Assets?.FirstOrDefault(a=>a.Id==texture.AssetId)?.SpritePath??"";
        return InfiniVfxRuntime.ResolveTexturePath(data,entityId,texture.Source);
    }
    internal static bool EnqueueElement(GeneratedItemData data,string entityId,VfxSlotSpec slot,string sourceKey,VfxSourceFrame frame,
        VfxSourceBinding? binding=null,bool itemBudget=false,MaterialEventAllowance? allowance=null)
    {
        if(Main.dedServ||slot.Element is not {} e||!frame.Valid||string.IsNullOrEmpty(sourceKey)) return false;
        string texture=ResolveMaterialTexture(data,entityId,e.Texture);
        if(string.IsNullOrEmpty(texture)||e.Count==0||e.Attachment=="source"&&binding is null) return false;
        if(OwnedRecordCount>=MaxEmissions) return false;
        var design=CopyElement(data,slot,texture,itemBudget);
        return EnqueueCopiedElement(design,sourceKey,frame,binding,slot.Anchor,slot.Event==RuntimeEventKind.Periodic?0:slot.StartTick,allowance);
    }
    private static ElementDesign CopyElement(GeneratedItemData data,VfxSlotSpec slot,string texture,bool itemBudget)
    {
        var e=slot.Element!;
        var budget=data.VfxManifest.Budget;
        var fallback=itemBudget?RuntimeColorPolicy.Resolve(data.Visual?.Palette?.Length>0?data.Visual.Palette[0]:"white",Color.White)
            :InfiniVfxRuntime.LegacyPresentationColor(data.VfxManifest,Color.White);
        var effect=InfiniVfxRuntime.PresentationColor(data,fallback);
        var design=new ElementDesign(texture,slot.Layer,slot.Blend,slot.Alpha,slot.Duration,e.Count,e.Attachment=="source",
            new(e.OffsetForwardPx,e.OffsetSidePx),e.SpeedMinPxPerTick,e.SpeedMaxPxPerTick,e.SpreadRadians,e.InheritVelocity,e.Drag,
            new(e.AccelerationXPxPerTickSquared,e.AccelerationYPxPerTickSquared),e.RotationRadians,e.RotationSpeedRadiansPerTick,
            e.WidthPx,e.HeightPx,VfxNumberRamp.Copy(e.WidthProfile),VfxNumberRamp.Copy(e.HeightProfile),VfxNumberRamp.Copy(e.OpacityProfile),
            VfxColorRamp.Copy(e.ColorProfile,effect),budget.MaxDrawCalls,budget.MaxParticlesPerTick,budget.MaxParticlesTotal,itemBudget,slot.SlotSeed);
        return design;
    }
    private static bool EnqueueCopiedElement(ElementDesign design,string sourceKey,VfxSourceFrame frame,VfxSourceBinding? binding,string anchor,int delay,MaterialEventAllowance? allowance=null)
    {
        if(OwnedRecordCount>=MaxEmissions)return false;
        var emission=new MaterialEmission{SourceKey=sourceKey,Design=design,Frame=frame,InitialFrame=frame,Binding=design.Attached?binding:null,
            Anchor=anchor,Due=Main.GameUpdateCount+(ulong)delay,Allowance=allowance};
        if(design.Attached&&anchor=="hitPoint") {
            if(binding is null||!binding.TryFrame("self",out var source))return false;
            emission.SourceAnchorOffset=frame.Inverse(frame.Position-(frame.SourceCenter??source.Position));
            if(!float.IsFinite(emission.SourceAnchorOffset.X)||!float.IsFinite(emission.SourceAnchorOffset.Y))return false;
            emission.Frame=source;emission.Anchor="self";
        }
        MaterialEmissions.Add(emission);
        if(delay==0)StartMaterialEmission(emission);
        return true;
    }
    private static void StartMaterialEmission(MaterialEmission emission)
    {
        var d=emission.Design;
        if(d.Attached && (emission.Binding is null||!emission.Binding.TryFrame(emission.Anchor,out emission.Frame))) {emission.Started=true;return;}
        emission.Start=emission.Due; emission.Started=true;
        int count=Math.Min(64,InfiniVfxClientOptions.ScaleParticleCount(d.Count));
        count=Math.Min(count,MaxMaterialParticles-MaterialEmissions.Sum(e=>e.Particles.Length));
        var particles=new List<MaterialParticle>(Math.Max(0,count));
        var random=new Random(d.Seed ^ unchecked((int)emission.Start));
        for(int i=0;i<count;i++) {
            // Items have no activation/lifetime clock: positive periodic totals
            // are not a per-group cap. Event totals use the shared allowance;
            // projectile totals remain owned by the source lifetime ledger.
            if(d.MaxTotal<=0||emission.Allowance is{Remaining:<=0})break;
            if(!TrySpendDetachedParticle(emission.SourceKey,d.MaxPerTick,d.ItemBudget?int.MaxValue:d.MaxTotal)) break;
            if(emission.Allowance is {} allowance)allowance.Remaining--;
            float angle=((float)random.NextDouble()-0.5f)*d.Spread;
            var velocity=new Vector2(MathF.Cos(angle),MathF.Sin(angle))*MathHelper.Lerp(d.SpeedMin,d.SpeedMax,(float)random.NextDouble());
            velocity+=emission.InitialFrame.Inverse(emission.InitialFrame.Velocity)*d.Inheritance;
            particles.Add(new MaterialParticle { Position=d.Attached?d.Offset+emission.SourceAnchorOffset:emission.Frame.Position+emission.Frame.Rotate(d.Offset),
                Velocity=d.Attached?velocity:emission.Frame.Rotate(velocity),Rotation=d.Attached?d.Rotation:emission.Frame.Forward.ToRotation()+d.Rotation });
        }
        emission.Particles=particles.ToArray();
    }
    private static void UpdateMaterials()
    {
        ulong now=Main.GameUpdateCount;
        if(LastMaterialsTick==now)return;LastMaterialsTick=now;
        UpdateMaterialPaths(now);
        UpdatePeriodicElements(now);
        foreach(var e in MaterialEmissions) {
            if(now<e.Due) continue;
            if(!e.Started) StartMaterialEmission(e);
            if(e.Design.Attached && (e.Binding is null||!e.Binding.TryFrame(e.Anchor,out e.Frame))) {e.Particles=Array.Empty<MaterialParticle>();continue;}
            int age=(int)Math.Min((ulong)e.Design.Duration,now-e.Start);
            for(int t=e.IntegratedAge;t<age;t++) foreach(var p in e.Particles) {
                p.Velocity=p.Velocity*e.Design.Drag+e.Design.Acceleration;
                p.Position+=p.Velocity;p.Rotation+=e.Design.Spin;
            }
            e.IntegratedAge=age;
        }
        MaterialEmissions.RemoveAll(e=>e.Started&&(e.Particles.Length==0||now-e.Start>=(ulong)e.Design.Duration)
            ||e.Design.Attached&&(e.Binding is null||!e.Binding.IsLive));
    }
    private static void DrawMaterialSprites(string layer,SpriteBatch batch,Action ensureBegin)
    {
        foreach(var e in MaterialEmissions) {
            var d=e.Design;
            if(!e.Started||e.IntegratedAge>=d.Duration||d.Layer!=layer) continue;
            float age=e.IntegratedAge/(float)d.Duration;
            float width=d.Width*d.WidthRamp.At(age),height=d.Height*d.HeightRamp.At(age),opacity=d.Alpha*d.OpacityRamp.At(age);
            if(width<=0||height<=0||opacity<=0) continue;
            Texture2D? texture=InfiniCrafterLocalMod.Sprites.TryGet(d.TexturePath);
            if(texture is null) continue;
            var tint=d.ColorRamp.At(age,opacity,d.Blend);
            foreach(var p in e.Particles) {
                if(!TrySpendSourceDraw(e.SourceKey,d.MaxDraw,1)) break;
                ensureBegin();
                Vector2 position=d.Attached?e.Frame.Position+e.Frame.Rotate(p.Position):p.Position;
                float rotation=p.Rotation+(d.Attached?e.Frame.Forward.ToRotation():0);
                batch.Draw(texture,position-Main.screenPosition,null,tint,rotation,new Vector2(texture.Width,texture.Height)*0.5f,
                    new Vector2(width/texture.Width,height/texture.Height),SpriteEffects.None,0);
            }
        }
    }
    private static void MakeRoomForLegacyEmission()
    {
        if(OwnedRecordCount<MaxEmissions)return;
        if(Emissions.Count>0)Emissions.RemoveAt(0);
        else if(MaterialEmissions.Count>0)MaterialEmissions.RemoveAt(0);
        else if(MaterialPaths.Count>0)MaterialPaths.RemoveAt(0);
    }
    private static int OwnedRecordCount=>Emissions.Count+MaterialEmissions.Count+MaterialPaths.Count;
    internal static bool TrySpendSourceDraw(string sourceKey,int maxDraw,int cost)
    {
        if(cost<=0) return true;
        int spent=DrawCallsBySource.TryGetValue(sourceKey,out int v)?v:0;
        if(cost>InfiniVfxClientOptions.EffectiveDrawBudget(maxDraw)-spent) return false;
        DrawCallsBySource[sourceKey]=spent+cost;return true;
    }
}
