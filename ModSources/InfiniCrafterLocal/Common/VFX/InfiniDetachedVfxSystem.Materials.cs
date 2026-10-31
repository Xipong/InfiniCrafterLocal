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
    internal static VfxColorRamp Copy(VfxColorProfileSpec p)
        => new(p.Start.ToColor().ToVector3(),p.Middle.ToColor().ToVector3(),p.End.ToColor().ToVector3(),p.Curve);
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
    // Replay admission belongs to the existing ordered-stream owner, once per
    // event before slot fanout. Attachment generations are not transport cursors
    // and retired events must not consume a global historical admission budget.
    private static readonly VfxOrderedPeerStream MaterialEventStream=new();
    internal static ulong NewMaterialOccurrence()=>MaterialEventStream.NewLocalOccurrence();
    internal static bool TryAdmitMaterialOccurrence(ulong occurrence,bool relay)
        =>relay?MaterialEventStream.AcceptRelay(occurrence):MaterialEventStream.AcceptLocal(occurrence);
    private sealed record ElementDesign(string TexturePath,string? LibraryTextureId,string Layer,string Blend,float Alpha,int Duration,int Count,
        bool Attached,Vector2 Offset,float SpeedMin,float SpeedMax,float Spread,float Inheritance,float Drag,Vector2 Acceleration,
        float Rotation,float Spin,float Width,float Height,VfxNumberRamp WidthRamp,VfxNumberRamp HeightRamp,VfxNumberRamp OpacityRamp,VfxColorRamp ColorRamp,
        int MaxDraw,int MaxPerTick,int MaxTotal,bool ItemBudget,int Seed,VfxSpawnSpec? Spawn,VfxTextureUv Uv);
    private sealed class MaterialParticle {
        internal Vector2 Position,Velocity;
        internal float Rotation;
    }
    private sealed class MaterialEmission {
        internal required string SourceKey;
        internal ElementDesign? Design;
        internal LibraryEmissionState? Library;
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
        internal ElementDesign? Design;
        internal ShapeDesign? Shape;
        internal ContourDesign? Contours;
        internal NativeCueDesign? NativeCue;
        internal ulong NativeLightAuthorizedTick;
        internal LibraryEmissionState? Library;
        internal required string SourceKey,SlotId,Anchor;
        internal ulong FirstTick,LastTick=ulong.MaxValue;
        internal int StartTick,RepeatEvery,InitialAge;
        internal bool Item;
        internal int? BurstTotal;
        internal double? PlacedReachRadius;
    }
    // Generation is an identity token, not an authored ID or value-equality key.
    private sealed class PeriodicKeyComparer : IEqualityComparer<(object Generation,string SlotId)>
    {
        public bool Equals((object Generation,string SlotId) x,(object Generation,string SlotId) y)
            => ReferenceEquals(x.Generation,y.Generation) && StringComparer.Ordinal.Equals(x.SlotId,y.SlotId);
        public int GetHashCode((object Generation,string SlotId) key)
            => HashCode.Combine(System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(key.Generation),
                StringComparer.Ordinal.GetHashCode(key.SlotId));
    }
    private static readonly Dictionary<(object Generation,string SlotId),PeriodicElement> PeriodicElements=new(new PeriodicKeyComparer());
    private static void PrunePeriodicElements()
    {
        // One bounded sweep per material tick, before admitting placed sources.
        // Removing a distant registration does not retire the source or its live
        // emissions; re-entry resumes the authored world cadence, without replay.
        foreach (var key in PeriodicElements.Where(pair => !pair.Value.Binding.IsLive
            || !PeriodicElementInView(pair.Value)).Select(pair => pair.Key).ToArray())
            PeriodicElements.Remove(key);
    }
    private static bool PeriodicElementInView(PeriodicElement element)
        => element.PlacedReachRadius is not double radius
            || element.Binding.TryFrame(element.Anchor,out var frame) && PlacedVfxInView(frame.Position,radius);
    internal static void RegisterPeriodicElements(GeneratedItemData data,string entityId,string sourceKey,VfxSourceBinding? binding,bool item=false,string? placementBindingId=null,bool allowLightCue=true)
    {
        if(Main.dedServ||binding is null||!binding.IsLive)return;
        VfxSourceFrame placedFrame = default;
        if(placementBindingId is not null && !binding.TryFrame("self",out placedFrame))return;
        foreach(var slot in data.VfxManifest.Slots) {
            if(slot.PlacementBindingId!=placementBindingId||slot.EntityId!=entityId||slot.Event!=RuntimeEventKind.Periodic||(slot.Element is null&&slot.Particle is null&&slot.Shape is null&&slot.Geometry is null&&slot.Dust is null&&slot.Light is null&&slot.NativeEffect is null))continue;
            if(slot.Light is not null&&!allowLightCue)continue;
            var key=(binding.Generation,slot.Id);
            if(PeriodicElements.TryGetValue(key,out var prior)) {
                if(prior.Binding.IsLive) {
                    if(slot.Light is not null)prior.NativeLightAuthorizedTick=Main.GameUpdateCount;
                    continue;
                }
                // Moving the same Item invalidates its old slot even within this
                // tick. Replace that exact registration, not a global sweep.
                PeriodicElements.Remove(key);
            }
            double? placedReach=placementBindingId is null||slot.Light is not null?null:PlacedVfxReachRadius(slot);
            if(placedReach is double radius && !PlacedVfxInView(placedFrame.Position,radius))continue;
            if(PeriodicElements.Count>=MaxEmissions)return;
            if(slot.Dust is not null||slot.Light is not null||slot.NativeEffect is not null) {
                PeriodicElements.Add(key,new PeriodicElement{Binding=binding,NativeCue=CopyNativeCue(data,slot,item),NativeLightAuthorizedTick=Main.GameUpdateCount,SourceKey=sourceKey,
                    SlotId=slot.Id,Anchor=slot.Anchor,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge,StartTick=slot.StartTick!.Value,RepeatEvery=slot.RepeatEvery!.Value,Item=item,PlacedReachRadius=placedReach});
                continue;
            }
            if(slot.Geometry is not null) {
                PeriodicElements.Add(key,new PeriodicElement{Binding=binding,Contours=CopyContours(data,slot),SourceKey=sourceKey,
                    SlotId=slot.Id,Anchor=slot.Anchor,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge,StartTick=slot.StartTick!.Value,RepeatEvery=slot.RepeatEvery!.Value,Item=item,PlacedReachRadius=placedReach});
                continue;
            }
            if(slot.Shape is not null) {
                PeriodicElements.Add(key,new PeriodicElement{Binding=binding,Shape=CopyShape(data,slot),SourceKey=sourceKey,
                    SlotId=slot.Id,Anchor=slot.Anchor,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge,StartTick=slot.StartTick!.Value,RepeatEvery=slot.RepeatEvery!.Value,Item=item,PlacedReachRadius=placedReach});
                continue;
            }
            if(slot.Particle is not null) {
                PeriodicElements.Add(key,new PeriodicElement{Binding=binding,Library=new LibraryEmissionState(CopyLibrary(data,slot,item),0),SourceKey=sourceKey,
                    SlotId=slot.Id,Anchor=slot.Anchor,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge,StartTick=slot.StartTick!.Value,RepeatEvery=slot.RepeatEvery!.Value,Item=item,BurstTotal=placementBindingId is null?null:data.VfxManifest.Budget.MaxParticlesTotal,PlacedReachRadius=placedReach});
                continue;
            }
            string texture=ResolveMaterialTexture(data,entityId,slot.Element!.Texture);
            if(string.IsNullOrEmpty(texture))continue;
            PeriodicElements.Add(key,new PeriodicElement{Binding=binding,Design=CopyElement(data,slot,texture,item),SourceKey=sourceKey,
                SlotId=slot.Id,Anchor=slot.Anchor,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge,StartTick=slot.StartTick!.Value,RepeatEvery=Math.Max(1,slot.RepeatEvery!.Value),Item=item,BurstTotal=placementBindingId is null?null:data.VfxManifest.Budget.MaxParticlesTotal,PlacedReachRadius=placedReach});
        }
    }
    private static void UpdatePlacedSources(ulong now)
    {
        foreach (var source in Common.Systems.GeneratedPlacementLedgerSystem.ActivePlacedVfxSources()) {
            var view = source.View;
            // Permanent placements have no terminal lifetime. Only this opt-in
            // cohort consumes maxParticlesTotal afresh per due burst; the existing
            // per-source tick/draw and global live-instance ceilings still apply.
            RegisterPeriodicElements(view.Data,view.EntityId,source.SourceKey,source.Binding,item:true,placementBindingId:view.BindingId);
            foreach (var slot in view.Data.VfxManifest.Slots) {
                if (slot.PlacementBindingId != view.BindingId || slot.EntityId != view.EntityId
                    || slot.RendererKind != "lightCue" || slot.Event != RuntimeEventKind.Periodic
                    || (now+(ulong)Math.Abs((long)slot.SlotSeed))%(ulong)slot.RepeatEvery!.Value != 0
                    || !source.Binding.TryFrame("self",out var frame)) continue;
                float strength = Math.Clamp(slot.Scale!.Value*.2f,.04f,1.2f)*InfiniVfxClientOptions.PresentationLightMultiplier;
                if (strength>0) Lighting.AddLight(frame.Position,slot.Color!.ToColor().ToVector3()*strength);
            }
        }
    }

    private static ulong LastMaterialsTick=ulong.MaxValue;
    private static void UpdatePeriodicElements(ulong now)
    {
        foreach(var e in PeriodicElements.Values) {
            if(e.LastTick==now)continue;e.LastTick=now;
            // Item light requires this tick's functional/held callback. A retained
            // cosmetic source binding alone is not authorization to illuminate.
            if(e.Item&&e.NativeCue?.Light is not null&&e.NativeLightAuthorizedTick!=now)continue;
            ulong age=e.Item?now:now-e.FirstTick+(ulong)Math.Max(0,e.InitialAge);
            if(age<(ulong)e.StartTick||(age-(ulong)e.StartTick)%(ulong)e.RepeatEvery!=0)continue;
            if(e.Binding.TryFrame(e.Anchor,out var frame)
                && (e.PlacedReachRadius is not double radius || PlacedVfxInView(frame.Position,radius))) {
                var allowance = e.BurstTotal is int total ? new MaterialEventAllowance(total) : null;
                if(e.NativeCue is {} nativeCue)EnqueueCopiedNativeCue(nativeCue,e.SourceKey,frame,0,allowance);
                else if(e.Contours is {} contours)EnqueueCopiedContours(contours,e.SourceKey,frame,e.Binding,e.Anchor,0);
                else if(e.Shape is {} shape)EnqueueCopiedShape(shape,e.SourceKey,frame,e.Binding,e.Anchor,0);
                else if(e.Library is {} library)EnqueueCopiedLibrary(library.Design,e.SourceKey,frame,0,allowance);
                else EnqueueCopiedElement(e.Design!,e.SourceKey,frame,e.Binding,e.Anchor,0,allowance);
            }
        }
    }

    internal static Texture2D? MaterialTexture(string filePath,string? libraryId)
        =>libraryId is null?InfiniCrafterLocalMod.Sprites.TryGet(filePath):VfxNativeTextureCache.TryGet(libraryId);

    internal static string ResolveMaterialTexture(GeneratedItemData data,string entityId,VfxTextureSpec texture)
    {
        if(texture.Source=="library") return VfxLibraryTextures.TryGetPath(texture.AssetId,out var nativePath)?nativePath:"";
        if(texture.Source=="asset") return data.VfxManifest.Assets?.FirstOrDefault(a=>a.Id==texture.AssetId)?.SpritePath??"";
        return SpritePresentation.Resolve(data,entityId,texture.Source).Path;
    }
    internal static bool EnqueueElement(GeneratedItemData data,string entityId,VfxSlotSpec slot,string sourceKey,VfxSourceFrame frame,
        VfxSourceBinding? binding=null,bool itemBudget=false,MaterialEventAllowance? allowance=null)
    {
        if(Main.dedServ||slot.Element is not {} e||!frame.Valid||string.IsNullOrEmpty(sourceKey)) return false;
        string texture=ResolveMaterialTexture(data,entityId,e.Texture);
        if(string.IsNullOrEmpty(texture)||e.Count==0||e.Attachment=="source"&&binding is null) return false;
        if(OwnedRecordCount>=MaxEmissions) return false;
        var design=CopyElement(data,slot,texture,itemBudget);
        return EnqueueCopiedElement(design,sourceKey,frame,binding,slot.Anchor,slot.Event==RuntimeEventKind.Periodic?0:slot.StartTick!.Value,allowance);
    }
    private static ElementDesign CopyElement(GeneratedItemData data,VfxSlotSpec slot,string texture,bool itemBudget)
    {
        var e=slot.Element!;
        var budget=data.VfxManifest.Budget;
        var design=new ElementDesign(texture,e.Texture.Source=="library"?e.Texture.AssetId:null,slot.Layer!,slot.Blend!,slot.Alpha!.Value,slot.Duration!.Value,e.Count,e.Attachment=="source",
            new(e.OffsetForwardPx,e.OffsetSidePx),e.SpeedMinPxPerTick,e.SpeedMaxPxPerTick,e.SpreadRadians,e.InheritVelocity,e.Drag,
            new(e.AccelerationXPxPerTickSquared,e.AccelerationYPxPerTickSquared),e.RotationRadians,e.RotationSpeedRadiansPerTick,
            e.WidthPx,e.HeightPx,VfxNumberRamp.Copy(e.WidthProfile),VfxNumberRamp.Copy(e.HeightProfile),VfxNumberRamp.Copy(e.OpacityProfile),
            VfxColorRamp.Copy(e.ColorProfile),budget.MaxDrawCalls,budget.MaxParticlesPerTick,budget.MaxParticlesTotal,itemBudget,slot.SlotSeed,e.Spawn?.Copy(),VfxTextureUv.Copy(e.Texture.Uv));
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
        var d=emission.Design!;
        if(d.Attached && (emission.Binding is null||!emission.Binding.TryFrame(emission.Anchor,out emission.Frame))) {emission.Started=true;return;}
        emission.Start=emission.Due; emission.Started=true;
        int count=Math.Min(64,InfiniVfxClientOptions.ScaleParticleCount(d.Count));
        count=Math.Min(count,MaxMaterialParticles-OwnedParticleCount);
        var particles=new List<MaterialParticle>(Math.Max(0,count));
        var random=new Random(d.Seed ^ unchecked((int)emission.Start));
        var positions=VfxSpawnGeometry.CreateRandom(d.Spawn,d.Seed,emission.Start);
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
            Vector2 offset=VfxSpawnGeometry.SampleWorld(d.Spawn,emission.Frame.Forward,positions);
            particles.Add(new MaterialParticle { Position=d.Attached?d.Offset+emission.SourceAnchorOffset+emission.Frame.Inverse(offset):emission.Frame.Position+emission.Frame.Rotate(d.Offset)+offset,
                Velocity=d.Attached?velocity:emission.Frame.Rotate(velocity),Rotation=d.Attached?d.Rotation:emission.Frame.Forward.ToRotation()+d.Rotation });
        }
        emission.Particles=particles.ToArray();
    }
    private static void UpdateMaterials()
    {
        ulong now=Main.GameUpdateCount;
        if(LastMaterialsTick==now)return;LastMaterialsTick=now;
        PrunePeriodicElements();
        UpdatePlacedSources(now);
        UpdateMaterialPaths(now);
        UpdatePeriodicElements(now);
        UpdateShapes(now);
        UpdateContours(now);
        UpdateNativeCues(now);
        foreach(var e in MaterialEmissions) {
            if(e.Library is not null){UpdateLibraryEmission(e,now);continue;}
            if(now<e.Due) continue;
            if(!e.Started) StartMaterialEmission(e);
            if(e.Design!.Attached && (e.Binding is null||!e.Binding.TryFrame(e.Anchor,out e.Frame))) {e.Particles=Array.Empty<MaterialParticle>();continue;}
            int age=(int)Math.Min((ulong)e.Design.Duration,now-e.Start);
            for(int t=e.IntegratedAge;t<age;t++) foreach(var p in e.Particles) {
                p.Velocity=p.Velocity*e.Design.Drag+e.Design.Acceleration;
                p.Position+=p.Velocity;p.Rotation+=e.Design.Spin;
            }
            e.IntegratedAge=age;
        }
        MaterialEmissions.RemoveAll(e=>e.Library is not null?LibraryEmissionExpired(e)
            :e.Started&&(e.Particles.Length==0||now-e.Start>=(ulong)e.Design!.Duration)
            ||e.Design!.Attached&&(e.Binding is null||!e.Binding.IsLive));
    }
    private static void DrawMaterialSprites(string layer,SpriteBatch batch,Action ensureBegin)
    {
        foreach(var e in MaterialEmissions) {
            if(e.Library is not null)continue;
            var d=e.Design!;
            if(!e.Started||e.IntegratedAge>=d.Duration||d.Layer!=layer) continue;
            float age=e.IntegratedAge/(float)d.Duration;
            float width=d.Width*d.WidthRamp.At(age),height=d.Height*d.HeightRamp.At(age),opacity=d.Alpha*d.OpacityRamp.At(age);
            if(width<=0||height<=0||opacity<=0) continue;
            Texture2D? texture=MaterialTexture(d.TexturePath,d.LibraryTextureId);
            if(texture is null) continue;
            var tint=d.ColorRamp.At(age,opacity,d.Blend);
            foreach(var p in e.Particles) {
                if(!TrySpendSourceDraw(e.SourceKey,d.MaxDraw,1)) break;
                ensureBegin();
                Vector2 position=d.Attached?e.Frame.Position+e.Frame.Rotate(p.Position):p.Position;
                float rotation=p.Rotation+(d.Attached?e.Frame.Forward.ToRotation():0);
                d.Uv.Draw(batch,texture,position-Main.screenPosition,tint,rotation,new Vector2(texture.Width,texture.Height)*0.5f,
                    new Vector2(width/texture.Width,height/texture.Height),SpriteEffects.None);
            }
        }
    }
    private static void MakeRoomForSimpleEmission()
    {
        if(OwnedRecordCount<MaxEmissions)return;
        if(Emissions.Count>0)Emissions.RemoveAt(0);
        else if(MaterialEmissions.Count>0){if(MaterialEmissions[0].Library?.Shake is {} shake)shake.ShakeStrength=0;MaterialEmissions.RemoveAt(0);}
        else if(MaterialPaths.Count>0)MaterialPaths.RemoveAt(0);
        else if(ShapeEmissions.Count>0)ShapeEmissions.RemoveAt(0);
        else if(ContourEmissions.Count>0)ContourEmissions.RemoveAt(0);
        else if(NativeCueEmissions.Count>0)NativeCueEmissions.RemoveAt(0);
    }
    private static int OwnedRecordCount=>Emissions.Count+MaterialEmissions.Count+MaterialPaths.Count+ShapeEmissions.Count+ContourEmissions.Count+NativeCueEmissions.Count;
    internal static bool TrySpendSourceDraw(string sourceKey,int maxDraw,int cost)
    {
        if(cost<=0) return true;
        int spent=DrawCallsBySource.TryGetValue(sourceKey,out int v)?v:0;
        if(cost>InfiniVfxClientOptions.EffectiveDrawBudget(maxDraw)-spent) return false;
        DrawCallsBySource[sourceKey]=spent+cost;return true;
    }
}
