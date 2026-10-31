using System;
using System.Linq;
using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void VfxExpressivityShapeAndSavedParity()
    {
        foreach(string kind in new[]{"line","arc","wave","orbit"}) {
            var slot=ExplicitShapeSlot(kind);var manifest=new VfxManifestSpec{Slots=new[]{slot}};
            string old=manifest.ToJson();Equal(old,VfxManifestSpec.FromJson(old).ToJson(),"saved absent new controls are not materialized");
            slot.Shape!.OpacityCurve="easeOut";slot.Shape.RotationSpeedRadiansPerTick=MathF.Tau;
            if(kind=="wave")slot.Shape.PhaseSpeedRadiansPerTick=-MathF.Tau;
            if(kind=="orbit"){slot.Shape.MoteOrientation="world";slot.Shape.MoteRotationRadians=MathF.PI/3;}
            string wire=manifest.ToJson();Equal(true,wire.Length>0,"expanded angular limits accepted "+kind);
            Equal(wire,VfxManifestSpec.FromJson(wire).ToJson(),"authored new fields preserved");
            var root=JsonNode.Parse(wire)!;root["slots"]![0]!["shape"]!["opacityCurve"]=null;
            Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"explicit null is not saved absence");
            root=JsonNode.Parse(wire)!;root["slots"]![0]!["shape"]!["opacityCurve"]="unknown";
            Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"unknown opacity curve never becomes linear");
            root=JsonNode.Parse(wire)!;root["slots"]![0]!["shape"]!["rotationSpeedRadiansPerTick"]=7;
            Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"expanded angular rate remains bounded");
            root=JsonNode.Parse(wire)!;root["slots"]![0]!["shape"]!["moteOrientation"]=kind=="orbit"?"unknown":"world";
            Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"unknown or foreign mote control rejected");
        }
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            var frame=new VfxSourceFrame(new Vector2(40,60),Vector2.UnitX,Vector2.Zero);
            var line=ExplicitShape();line.ColorStart=line.ColorEnd=Rgb(255,255,255);line.OpacityStart=1;line.OpacityEnd=0;line.OpacityCurve="easeOut";
            InfiniDetachedVfxSystem.DrawExplicitShape(pixel,line,frame,2.5f,10,"alpha",()=>true);
            Equal((byte)143,colors(0)[0].A,"full-life easeOut restores quadratic remaining-life opacity without double application");
        });
    }
    private static void VfxExpressivityOrbitOrientationAndAngularRate()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            var frame=new VfxSourceFrame(new Vector2(40,60),Vector2.UnitX,Vector2.Zero);
            var orbit=ExplicitShape("orbit");orbit.Count=1;orbit.RotationRadians=MathF.PI/4;orbit.MoteOrientation="world";orbit.MoteRotationRadians=0;
            void Draw(VfxShapeSpec s)=>InfiniDetachedVfxSystem.DrawExplicitShape(pixel,s,frame,1,10,"alpha",()=>true);
            Draw(orbit);var first=vertices(0);float worldWidth=first.Max(p=>p.X)-first.Min(p=>p.X);
            orbit.MoteOrientation="orbit";Draw(orbit);var second=vertices(1);float orbitWidth=second.Max(p=>p.X)-second.Min(p=>p.X);
            AssertVfxNear(VfxVertexCenter(first),VfxVertexCenter(second),"mote orientation does not move orbit centers");
            Equal(true,Math.Abs(worldWidth-3)<.001f&&Math.Abs(orbitWidth-3*MathF.Sqrt(2))<.001f,"square rotation independent from orbital position");
            var old=ExplicitShape("orbit");old.Count=1;old.RotationRadians=MathF.PI/4;Draw(old);
            for(int i=0;i<4;i++)Equal(second[i],vertices(2)[i],"saved absent orientation exactly retains previous orbit-relative orientation");
            var line=ExplicitShape();line.RotationSpeedRadiansPerTick=MathF.PI/2;Draw(line);
            AssertVfxNear(new Vector2(0,10),VfxVertexCenter(vertices(3)),"angular rate above1rad/tick executes rather than clamps");
            var wave=ExplicitShape("wave");wave.PhaseSpeedRadiansPerTick=MathF.PI;Draw(wave);
            AssertVfxNear(new Vector2(2.5f,-2.5f),VfxVertexCenter(vertices(4)),"phase rate above1rad/tick executes rather than clamps");
        });
    }
    private static void VfxExpressivityDustDistributionAndSavedParity()
    {
        WithLighting((config,lights)=>{
            var oldDust=Terraria.Main.dust;var oldRandom=Terraria.Main.rand;bool menu=Terraria.Main.gameMenu,gen=WorldGen.gen;
            int max=Terraria.Main.maxDustToDraw,width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;
            Vector2 screen=Terraria.Main.screenPosition;float dCount=Dust.dCount;
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",BindingFlags.Static|BindingFlags.NonPublic)!;object? previous=clock.GetValue(null);
            var system=new InfiniDetachedVfxSystem();
            try {
                Terraria.Main.gameMenu=false;WorldGen.gen=false;Terraria.Main.maxDustToDraw=6000;Terraria.Main.screenWidth=800;Terraria.Main.screenHeight=600;Terraria.Main.screenPosition=Vector2.Zero;
                config.ParticleSpawnMultiplier=1;
                var data=GeneratedItemData.Placeholder();var slot=NativeCueSlot();data.VfxManifest=new(){Slots=new[]{slot}};
                var d=slot.Dust!;d.Count=4;d.SpreadRadians=MathF.Tau;d.InheritVelocity=0;d.AngularDistribution="even";d.DirectionFrame="world";d.AngleOffsetRadians=MathF.PI;
                Vector2[] Emit() {
                    system.OnWorldUnload();MaterialClock(100);Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(7);Dust.dCount=0;
                    Terraria.Main.dust=new Dust[6001];for(int i=0;i<Terraria.Main.dust.Length;i++)Terraria.Main.dust[i]=new Dust{dustIndex=i};
                    InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,slot.EntityId,slot,"parity",new(new Vector2(100,120),Vector2.UnitY,Vector2.Zero));
                    return Terraria.Main.dust.Where(p=>p.active).Select(p=>p.velocity).ToArray();
                }
                var spokes=Emit();Equal(4,spokes.Length,"four exact native spokes");
                for(int i=0;i<4;i++)AssertVfxNear((i*MathF.PI/2).ToRotationVector2()*2,spokes[i],"world radial spoke "+i);
                d.DirectionFrame="source";var relative=Emit();for(int i=0;i<4;i++)AssertVfxNear(spokes[i].RotatedBy(MathF.PI/2),relative[i],"source frame changes direction not distribution");
                d.DirectionFrame="world";d.SpreadRadians=MathF.PI/2;d.AngleOffsetRadians=0;d.Count=3;var cone=Emit();
                for(int i=0;i<3;i++)AssertVfxNear((-MathF.PI/4+i*MathF.PI/4).ToRotationVector2()*2,cone[i],"partial cone includes endpoints");
                d.Count=1;AssertVfxNear(Vector2.UnitX*2,Emit()[0],"one even particle centered");
                slot=NativeCueSlot();data.VfxManifest.Slots=new[]{slot};d=slot.Dust!;d.SpreadRadians=2;d.SpeedMinPxPerTick=1;d.SpeedMaxPxPerTick=3;
                string saved=data.VfxManifest.ToJson();Equal(saved,VfxManifestSpec.FromJson(saved).ToJson(),"saved missing distribution controls remain absent");
                var legacy=Emit();d.AngularDistribution="random";d.DirectionFrame="source";d.AngleOffsetRadians=0;var explicitOld=Emit();
                for(int i=0;i<legacy.Length;i++)Equal(legacy[i],explicitOld[i],"saved random sequence and velocity preserved exactly");
            } finally {
                system.OnWorldUnload();Terraria.Main.dust=oldDust;Terraria.Main.rand=oldRandom;Terraria.Main.gameMenu=menu;WorldGen.gen=gen;
                Terraria.Main.maxDustToDraw=max;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;Terraria.Main.screenPosition=screen;Dust.dCount=dCount;clock.SetValue(null,previous);
            }
        });
    }
    private static void VfxExpressivityLargeSpritesRemainExecutable()
    {
        WithVfxGeometryQueue((batch,texture,count,positions,colors)=>{
            var system=new InfiniDetachedVfxSystem();var tick=Terraria.Main.GameUpdateCount;
            using var borrowedCache=new BorrowedSpriteCache();
            string path=Path.Combine(Terraria.Program.SavePath,"parity-large-material.png");
            borrowedCache.Textures.Add(path,Activator.CreateInstance(borrowedCache.Record,texture,0f,0L)!);
            try {
                system.OnWorldUnload();var wire=MaterialElementWire();var e=wire["vfxManifest"]!["slots"]![0]!["element"]!;
                e["widthPx"]=640;e["heightPx"]=640;e["count"]=1;
                foreach(string profile in new[]{"widthProfile","heightProfile"})foreach(string knot in new[]{"start","middle","end"})e[profile]![knot]=1;
                var data=ParseMaterialElement(wire);var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;data.VfxManifest.Assets![0].SpritePath=path;
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,slot.EntityId,slot,"large",new(new Vector2(100,120),Vector2.UnitX,Vector2.Zero));
                typeof(InfiniDetachedVfxSystem).GetMethod("DrawMaterialSprites",BindingFlags.Static|BindingFlags.NonPublic)!.Invoke(null,new object[]{"BeforeProjectiles",batch,(Action)(()=>{})});
                Equal(1,count(),"640px image enqueues native quad");var v=positions(0);
                Equal(true,Math.Abs(Vector3.Distance(v[0],v[1])-640)<.001f&&Math.Abs(Vector3.Distance(v[0],v[2])-640)<.001f,"old128texture times5 footprint remains expressible");
                var trail=ExplicitTrail("sprites");trail.Scale=5;
                var manifest=new VfxManifestSpec{Slots=new[]{new VfxSlotSpec{Id="trail",EntityId="probe",RendererKind="historyTrail",Event="periodic",Anchor="self",Blend="alpha",Layer="AfterProjectiles",Trail=trail}}};
                Equal(true,VfxManifestSpec.FromJson(manifest.ToJson()).HasSlots,"old trail multiplier5 remains admitted");
                var projectile=new Projectile{rotation=0,scale=1,spriteDirection=1};
                var selected=new SpritePresentationSelection("probe",null,null,ImpactTexture:true);
                var pose=(VfxTrailPose)typeof(InfiniVfxRuntime).GetMethod("CaptureTrailPose",BindingFlags.Static|BindingFlags.NonPublic)!.Invoke(null,new object?[]{texture,projectile,null,selected,5f})!;
                Equal(5f,pose.Scale,"old trail multiplier5 executes without4clamp");
            } finally {borrowedCache.Textures.Clear();system.OnWorldUnload();MaterialClock(tick);}
        });
    }

    private static void VfxExpressivityShortShapeLifetimeAndRotationFrame()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            const BindingFlags flags=BindingFlags.Static|BindingFlags.NonPublic;
            var type=typeof(InfiniDetachedVfxSystem);var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",flags)!;
            object? previous=clock.GetValue(null);var system=new InfiniDetachedVfxSystem();
            var emissions=(System.Collections.IList)type.GetField("ShapeEmissions",flags)!.GetValue(null)!;
            void Invoke(string name,params object[] args)=>type.GetMethod(name,flags)!.Invoke(null,args);
            void Draw(){Invoke("BeginDrawBudgetFrame");Invoke("DrawShapes","AfterProjectiles",pixel,(Action)(()=>{}));}
            try {
                foreach(int duration in new[]{1,2}) {
                    system.OnWorldUnload();MaterialClock(300);
                    var slot=ExplicitShapeSlot();slot.Event="periodic";slot.Duration=duration;slot.RepeatEvery=duration;slot.Shape!.Attachment="source";
                    var data=GeneratedItemData.Placeholder();data.VfxManifest=new(){Slots=new[]{slot}};
                    Equal(true,VfxManifestSpec.FromJson(data.VfxManifest.ToJson()).HasSlots,"short shape duration admitted "+duration);
                    var source=new ShapeSource{Position=new Vector2(40,60)};
                    InfiniDetachedVfxSystem.RegisterPeriodicElements(data,"probe","short-shape",source);
                    for(ulong tick=300;tick<306;tick++) {
                        MaterialClock(tick);Invoke("UpdatePeriodicElements",tick);Invoke("UpdateShapes",tick);
                        Equal(1,emissions.Count,"short cadence neither overlaps nor leaves a gap "+duration+" tick "+tick);
                        int before=count();Draw();Equal(before+1,count(),"single live shape draws once each tick");
                    }
                    source.Live=false;Invoke("UpdateShapes",306UL);Equal(0,emissions.Count,"source retirement still bounds short lifetime");
                }
                system.OnWorldUnload();MaterialClock(400);
                var worldSlot=ExplicitShapeSlot();worldSlot.Shape!.Attachment="source";worldSlot.Shape.RotationFrame="world";worldSlot.Shape.OffsetForwardPx=2;
                var worldData=GeneratedItemData.Placeholder();worldData.VfxManifest=new(){Slots=new[]{worldSlot}};
                var moving=new ShapeSource{Position=new Vector2(40,60)};
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(worldData,"probe",worldSlot,"world-frame",new(moving.Position,moving.Forward,Vector2.Zero),moving);
                int index=count();Draw();AssertVfxNear(new Vector2(12,0),VfxVertexCenter(vertices(index)),"initial source offset and world orientation");
                moving.Forward=Vector2.UnitY;MaterialClock(401);Invoke("UpdateShapes",401UL);index=count();Draw();
                AssertVfxNear(new Vector2(10,2),VfxVertexCenter(vertices(index)),"source turning rotates offset but not world geometry");
                system.OnWorldUnload();var saved=ExplicitShapeSlot();saved.Shape!.Attachment="source";saved.Shape.OffsetForwardPx=2;worldData.VfxManifest.Slots=new[]{saved};
                string beforeWire=worldData.VfxManifest.ToJson();Equal(beforeWire,VfxManifestSpec.FromJson(beforeWire).ToJson(),"saved rotationFrame absence remains absent");
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(worldData,"probe",saved,"saved-frame",new(moving.Position,moving.Forward,Vector2.Zero),moving);
                index=count();Draw();AssertVfxNear(new Vector2(0,12),VfxVertexCenter(vertices(index)),"saved absence retains source-relative angular basis");
                var invalid=JsonNode.Parse(beforeWire)!;invalid["slots"]![0]!["duration"]=0;
                Equal(false,VfxManifestSpec.FromJson(invalid.ToJsonString()).HasSlots,"zero lifetime still invalid");
                var material=MaterialElementWire()["vfxManifest"]!;material["slots"]![0]!["duration"]=1;
                Equal(false,VfxManifestSpec.FromJson(material.ToJsonString()).HasSlots,"shape minimum does not change spriteElement admission");
            } finally {system.OnWorldUnload();clock.SetValue(null,previous);}
        });
    }

}
