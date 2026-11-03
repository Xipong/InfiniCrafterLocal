using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ParticleLibrary.Core.V3.Particles;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxSpawnSpec SpawnLine(string frame="world",float length=20)=>new(){Shape="line",LengthPx=length,RotationRadians=0,Frame=frame};
    private sealed class SpawnCountingRandom : Random {internal int Calls;public override double NextDouble(){Calls++;return .25;}}
    private static void VfxSpawnAdmissionAndPureUniformProjection()
    {
        string[] regions={"{\"shape\":\"point\"}","{\"shape\":\"line\",\"lengthPx\":0,\"rotationRadians\":0,\"frame\":\"world\"}","{\"shape\":\"rectangle\",\"widthPx\":10,\"heightPx\":0,\"rotationRadians\":0,\"frame\":\"source\"}","{\"shape\":\"annulus\",\"innerRadiusPx\":2,\"outerRadiusPx\":4}"};
        var manifests=new[]{MaterialElementWire()["vfxManifest"]!.DeepClone(),LibraryManifestWire(),JsonNode.Parse(new VfxManifestSpec{Slots=new[]{NativeCueSlot()}}.ToJson())!};
        string[] owners={"element","particle","dust"};
        for(int i=0;i<3;i++) {
            string saved=VfxManifestSpec.FromJson(manifests[i].ToJsonString()).ToJson();Equal(true,saved.Length>0,"saved spawn-less data admitted");
            Equal(saved,VfxManifestSpec.FromJson(saved).ToJson(),"saved absence remains absent");
            foreach(string region in regions) {
                var root=manifests[i].DeepClone();var owner=root["slots"]![0]![owners[i]]!;owner["spawn"]=JsonNode.Parse(region);
                Equal(true,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"shared variant accepted by "+owners[i]);
                owner["spawn"]!["unknown"]=0;Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"foreign geometry field rejected");
            }
            var bad=manifests[i].DeepClone();bad["slots"]![0]![owners[i]]!["spawn"]=null;
            Equal(false,VfxManifestSpec.FromJson(bad.ToJsonString()).HasSlots,"explicit spawn null is not absence");
            bad["slots"]![0]![owners[i]]!["spawn"]=JsonNode.Parse("{\"shape\":\"annulus\",\"innerRadiusPx\":4,\"outerRadiusPx\":2}");
            Equal(false,VfxManifestSpec.FromJson(bad.ToJsonString()).HasSlots,"inverted annulus rejected");
        }
        var line=SpawnLine("world",10);AssertVfxNear(new Vector2(5,0),VfxSpawnGeometry.FromUnitSquare(line,Vector2.UnitY,1,0),"world line orientation");
        line.Frame="source";AssertVfxNear(new Vector2(0,5),VfxSpawnGeometry.FromUnitSquare(line,Vector2.UnitY,1,0),"source line orientation");
        var rectangle=new VfxSpawnSpec{Shape="rectangle",WidthPx=10,HeightPx=20,RotationRadians=MathF.PI/2,Frame="world"};
        AssertVfxNear(new Vector2(10,5),VfxSpawnGeometry.FromUnitSquare(rectangle,Vector2.UnitX,1,0),"uniform rectangle rotation");
        var annulus=new VfxSpawnSpec{Shape="annulus",InnerRadiusPx=2,OuterRadiusPx=4};
        AssertVfxNear(new Vector2(MathF.Sqrt(10),0),VfxSpawnGeometry.FromUnitSquare(annulus,Vector2.UnitX,0,.5f),"uniform area uses squared-radius interpolation");
        annulus.InnerRadiusPx=annulus.OuterRadiusPx=0;Equal(Vector2.Zero,VfxSpawnGeometry.FromUnitSquare(annulus,Vector2.UnitY,.2f,.8f),"literal zero annulus");
        var placed=ParseMaterialElement(MaterialElementWire()).VfxManifest.Slots[0];var element=placed.Element!;
        element.WidthPx=element.HeightPx=element.OffsetForwardPx=element.OffsetSidePx=element.SpeedMaxPxPerTick=element.AccelerationXPxPerTickSquared=element.AccelerationYPxPerTickSquared=0;
        double before=(double)LibraryInvoke("PlacedVfxReachRadius",placed)!;
        element.Spawn=SpawnLine("world",80);double after=(double)LibraryInvoke("PlacedVfxReachRadius",placed)!;
        Equal(40d,after-before,"placement bound includes sampled spawn region");
        Equal(false,InfiniDetachedVfxSystem.PlacedVfxIntersectsViewport(new Vector2(380,50),before,Vector2.Zero,100,100,Vector2.One),"old point region outside viewport");
        Equal(true,InfiniDetachedVfxSystem.PlacedVfxIntersectsViewport(new Vector2(380,50),after,Vector2.Zero,100,100,Vector2.One),"new region can reach viewport and cannot be culled as a point");
        var random=new SpawnCountingRandom();Equal(Vector2.Zero,VfxSpawnGeometry.SampleWorld(new(){Shape="point"},Vector2.UnitY,random),"point origin");Equal(Vector2.Zero,VfxSpawnGeometry.SampleWorld(null,Vector2.UnitY,random),"saved point origin");Equal(0,random.Calls,"point and absence consume no RNG");
    }
    private static (Vector2 Position,Vector2 Velocity)[] MaterialSpawnSamples()
    {
        var emission=OwnedMaterialQueue()[0]!;var particles=(Array)emission.GetType().GetField("Particles",TestInstance)!.GetValue(emission)!;
        return particles.Cast<object>().Select(p=>((Vector2)p.GetType().GetField("Position",TestInstance)!.GetValue(p)!,(Vector2)p.GetType().GetField("Velocity",TestInstance)!.GetValue(p)!)).ToArray();
    }
    private static void VfxSpawnElementBirthAndAttachedCoordinates()
    {
        WithLighting((config,lights)=>{
            var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;
            try {
                config.ParticleSpawnMultiplier=1;
                var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;slot.Element!.Count=4;slot.Element.OffsetSidePx=0;slot.Element.OffsetForwardPx=3;
                var frame=new VfxSourceFrame(new Vector2(100,120),Vector2.UnitY,new Vector2(4,2));
                (Vector2 Position,Vector2 Velocity)[] Emit(VfxSpawnSpec? spawn) {
                    system.OnWorldUnload();MaterialClock(100);
                    // Construct a new admitted payload for the legacy absence case.
                    slot.Element=ParseMaterialElement(MaterialElementWire()).VfxManifest.Slots[0].Element!;slot.Element.Count=4;slot.Element.OffsetForwardPx=3;slot.Element.OffsetSidePx=0;
                    if(spawn is not null)slot.Element.Spawn=spawn;
                    InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,slot.EntityId,slot,"spawn-element",frame);
                    return MaterialSpawnSamples();
                }
                var legacy=Emit(null);var region=SpawnLine();var sampled=Emit(region);
                var rng=VfxSpawnGeometry.CreateRandom(region,slot.SlotSeed,100);
                for(int i=0;i<4;i++) {
                    Equal(legacy[i].Velocity,sampled[i].Velocity,"spawn cannot alter element velocity RNG");
                    AssertVfxNear(frame.Position+frame.Rotate(new Vector2(3,0))+VfxSpawnGeometry.SampleWorld(region,frame.Forward,rng),sampled[i].Position,"element actual world birth");
                }
                system.OnWorldUnload();MaterialClock(100);slot.StartTick=2;slot.Element.Attachment="source";slot.Element.Spawn=SpawnLine();
                var source=new ShapeSource{Position=frame.Position,Forward=Vector2.UnitY};
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,slot.EntityId,slot,"attached-spawn",frame,source);
                slot.Element.Spawn.LengthPx=512;MaterialClock(102);system.PostUpdateEverything();
                var local=MaterialSpawnSamples();var frozen=SpawnLine();rng=VfxSpawnGeometry.CreateRandom(frozen,slot.SlotSeed,102);
                for(int i=0;i<4;i++)AssertVfxNear(frame.Rotate(new Vector2(3,0))+VfxSpawnGeometry.SampleWorld(frozen,frame.Forward,rng),frame.Rotate(local[i].Position),"world spawn offset inverse-converted into attached frame, copied before delay");
            }finally{system.OnWorldUnload();MaterialClock(tick);}
        });
    }
    private static void VfxSpawnLibraryActualBirthAndLegacyVelocity()
    {
        WithVfxGeometryQueue((batch,texture,count,positions,colors)=>WithLighting((config,lights)=>{
            const BindingFlags flags=BindingFlags.Static|BindingFlags.NonPublic;
            var type=typeof(InfiniDetachedVfxSystem);var field=type.GetField("LibraryBuffers",flags)!;object? old=field.GetValue(null);
            var textures=(Dictionary<string,Texture2D>)type.GetField("LibraryTextures",flags)!.GetValue(null)!;var saved=new Dictionary<string,Texture2D>(textures);
            var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;
            try {
                LibraryInvoke("LoadLibrary");config.EnableParticleLibraryBackend=true;config.ParticleSpawnMultiplier=1;
                field.SetValue(null,Array.CreateInstance(type.GetNestedType("LibraryBuffer",BindingFlags.NonPublic)!,0));textures["ParticleLibrary/Assets/Textures/Star"]=texture;
                var frame=new VfxSourceFrame(new Vector2(100,120),Vector2.UnitY,Vector2.One);
                ParticleInfo[] Emit(VfxSpawnSpec? spawn) {
                    system.OnWorldUnload();MaterialClock(100);var data=LibraryData();var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;slot.Particle!.Count=4;
                    if(spawn is not null)slot.Particle.Spawn=spawn;
                    Equal(true,EnqueueLibraryForCheck(data,"spawn-library",frame),"native library emission admitted");
                    var emission=LibraryOwnerQueue()[0]!;var state=emission.GetType().GetField("Library",TestInstance)!.GetValue(emission)!;
                    return (ParticleInfo[])state.GetType().GetField("Particles",TestInstance)!.GetValue(state)!;
                }
                var legacy=Emit(null);var region=new VfxSpawnSpec{Shape="annulus",InnerRadiusPx=2,OuterRadiusPx=8};var sample=Emit(region);var rng=VfxSpawnGeometry.CreateRandom(region,0,100);
                Equal(4,sample.Length,"spawn does not create extra library particles");
                for(int i=0;i<4;i++) {
                    Equal(legacy[i].Velocity,sample[i].Velocity,"spawn leaves library velocity RNG unchanged");
                    var offset=VfxSpawnGeometry.SampleWorld(region,frame.Forward,rng);
                    AssertVfxNear(frame.Position+offset,new Vector2(sample[i].Position.X,sample[i].Position.Y),"actual instanced ParticleInfo birth");
                }
            }finally{system.OnWorldUnload();field.SetValue(null,old);textures.Clear();foreach(var p in saved)textures.Add(p.Key,p.Value);MaterialClock(tick);}
        }));
    }
    private static void VfxSpawnDustActualBirthAndLegacyVelocity()
    {
        WithLighting((config,lights)=>{
            var oldDust=Terraria.Main.dust;var oldRandom=Terraria.Main.rand;bool menu=Terraria.Main.gameMenu,gen=WorldGen.gen;
            int max=Terraria.Main.maxDustToDraw,width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;Vector2 screen=Terraria.Main.screenPosition;float dCount=Dust.dCount;ulong tick=Terraria.Main.GameUpdateCount;
            var system=new InfiniDetachedVfxSystem();
            try {
                Terraria.Main.gameMenu=false;WorldGen.gen=false;Terraria.Main.maxDustToDraw=6000;Terraria.Main.screenWidth=800;Terraria.Main.screenHeight=600;Terraria.Main.screenPosition=Vector2.Zero;config.ParticleSpawnMultiplier=1;
                var frame=new VfxSourceFrame(new Vector2(100,120),Vector2.UnitY,Vector2.One);
                (Vector2 Position,Vector2 Velocity)[] Emit(VfxSpawnSpec? spawn) {
                    system.OnWorldUnload();MaterialClock(100);Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(7);Dust.dCount=0;
                    Terraria.Main.dust=new Dust[6001];for(int i=0;i<Terraria.Main.dust.Length;i++)Terraria.Main.dust[i]=new Dust{dustIndex=i};
                    var data=GeneratedItemData.Placeholder();var slot=NativeCueSlot();slot.Dust!.Count=4;if(spawn is not null)slot.Dust.Spawn=spawn;data.VfxManifest=new(){Slots=new[]{slot},Budget=new(){MaxParticlesPerTick=2,MaxParticlesTotal=2}};
                    InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,slot.EntityId,slot,"spawn-dust",frame);
                    return Terraria.Main.dust.Where(d=>d.active).Select(d=>(d.position,d.velocity)).ToArray();
                }
                var legacy=Emit(null);var region=new VfxSpawnSpec{Shape="rectangle",WidthPx=20,HeightPx=10,RotationRadians=.3f,Frame="source"};var sample=Emit(region);var rng=VfxSpawnGeometry.CreateRandom(region,0,100);
                Equal(2,sample.Length,"shared particle budget applies before spawn sampling");
                for(int i=0;i<sample.Length;i++) {
                    Equal(legacy[i].Velocity,sample[i].Velocity,"spawn leaves actual native dust velocity unchanged");
                    AssertVfxNear(frame.Position+VfxSpawnGeometry.SampleWorld(region,frame.Forward,rng),sample[i].Position,"actual native dust region position");
                }
            }finally{system.OnWorldUnload();Terraria.Main.dust=oldDust;Terraria.Main.rand=oldRandom;Terraria.Main.gameMenu=menu;WorldGen.gen=gen;Terraria.Main.maxDustToDraw=max;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;Terraria.Main.screenPosition=screen;Dust.dCount=dCount;MaterialClock(tick);}
        });
    }
}
