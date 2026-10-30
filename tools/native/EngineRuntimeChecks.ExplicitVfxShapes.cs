using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxShapeSpec ExplicitShape(string kind="line")
    {
        var s=new VfxShapeSpec { Kind=kind,Attachment="world",ColorStart=new(){R=255,G=0,B=0},ColorEnd=new(){R=0,G=0,B=255},OpacityStart=1,OpacityEnd=1 };
        switch(kind) {
            case "line":s.LengthPx=20;s.WidthPx=.5f;break;
            case "arc":s.RadiusStartPx=10;s.RadiusEndPx=20;s.SweepRadians=MathF.Tau;s.WidthPx=2;s.Segments=8;s.TailOpacityStart=1;s.TailOpacityEnd=1;break;
            case "wave":s.LengthPx=20;s.WidthPx=2;s.AmplitudePx=5;s.Cycles=1;s.PhaseRadians=0;s.PhaseSpeedRadiansPerTick=0;s.Segments=4;break;
            case "orbit":s.Count=4;s.RadiusStartPx=10;s.RadiusEndPx=20;s.MoteSizePx=3;break;
        }
        return s;
    }
    private static VfxSlotSpec ExplicitShapeSlot(string kind="line")=>new(){Id="shape",EntityId="probe",Event="on_hit",RendererKind="shape",Anchor="self",Layer="AfterProjectiles",Blend="alpha",StartTick=0,RepeatEvery=0,Duration=10,Shape=ExplicitShape(kind)};
    private static void ExplicitShapeAdmission()
    {
        foreach(string kind in new[]{"line","arc","wave","orbit"}) {
            var manifest=new VfxManifestSpec{RecipeId="shape_probe",Slots=new[]{ExplicitShapeSlot(kind)}};
            string json=manifest.ToJson();Equal(true,json.Length>0,"valid explicit shape "+kind);
            var parsed=VfxManifestSpec.FromJson(json);Equal(1,parsed.Slots.Length,"native shape roundtrip "+kind);
            Equal(json,parsed.ToJson(),"shape roundtrip preserves controls "+kind);
            JsonObject Root()=>JsonNode.Parse(json)!.AsObject();
            void Reject(Action<JsonObject,JsonObject> mutate,string label) {
                var root=Root();var slot=root["slots"]![0]!.AsObject();mutate(slot,slot["shape"]!.AsObject());
                Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,label);
            }
            Reject((slot,s)=>s.Remove("colorEnd"),"missing endpoint rejected");
            Reject((slot,s)=>s["opacityStart"]=2,"opacity out of range rejected");
            Reject((slot,s)=>s["offsetForwardPx"]=null,"null required float rejected");
            Reject((slot,s)=>s["mystery"]=1,"foreign nested field rejected");
            Reject((slot,s)=>s[kind=="orbit"?"widthPx":"moteSizePx"]=1,"foreign shape dimension rejected");
            Reject((slot,s)=>slot["alpha"]=1,"extra alpha cannot add hidden envelope");
            Reject((slot,s)=>slot["phaseOffset"]=0,"even neutral legacy phase forbidden");
            Reject((slot,s)=>slot["scale"]=1,"legacy coupled scale rejected");
            Reject((slot,s)=>slot["repeatEvery"]=1,"discrete event cannot repeat");
            Reject((slot,s)=>{slot["event"]="periodic";slot["repeatEvery"]=0;},"periodic requires positive cadence");
            Reject((slot,s)=>{slot["event"]="on_kill";s["attachment"]="source";},"terminal source attachment rejected");
        }
    }
    private static void ExplicitShapeAuthoredGeometry()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            var frame=new VfxSourceFrame(new Vector2(40,60),Vector2.UnitX,Vector2.Zero);
            int spends=0;
            void Draw(VfxShapeSpec s,float age=0)=>InfiniDetachedVfxSystem.DrawExplicitShape(pixel,s,frame,age,10,"alpha",()=>{spends++;return true;});
            var line=ExplicitShape();line.OffsetForwardPx=3;line.OffsetSidePx=4;Draw(line);
            Equal(1,count(),"line one quad");AssertVfxNear(new Vector2(13,4),VfxVertexCenter(vertices(0)),"line exact offset and length");
            var bounds=vertices(0);Equal(true,Math.Abs(bounds.Max(v=>v.Y)-bounds.Min(v=>v.Y)-.5f)<.001f,"subpixel width not clamped");
            line.WidthPx=0;Draw(line);Equal(1,count(),"zero width stays silent");
            line.WidthPx=1;line.LengthPx=0;Draw(line);Equal(1,count(),"zero line length stays silent");
            var arc=ExplicitShape("arc");arc.OpacityStart=1;arc.OpacityEnd=0;int first=count();Draw(arc,5);
            Equal(first+8,count(),"arc explicitly selected segment count");
            var c=colors(first)[0];Equal(true,c.A>=126&&c.A<=128,"linear opacity once, not squared");
            Equal(true,c.R>=62&&c.R<=65&&c.B>=62&&c.B<=65,"RGB endpoint interpolation before opacity");
            var wave=ExplicitShape("wave");first=count();Draw(wave);Equal(first+4,count(),"wave independent subdivision count");
            AssertVfxNear(new Vector2(2.5f,2.5f),VfxVertexCenter(vertices(first)),"wave uses explicit length amplitude and cycles");
            int beforeSilent=count();wave.LengthPx=0;Draw(wave);Equal(beforeSilent,count(),"zero wave length is silent rather than vertical backtracking");
            wave.LengthPx=20;wave.AmplitudePx=0;Draw(wave);Equal(beforeSilent+4,count(),"zero amplitude preserves a straight line");
            wave.WidthPx=0;Draw(wave);Equal(beforeSilent+4,count(),"zero wave width is silent");
            var orbit=ExplicitShape("orbit");first=count();Draw(orbit,5);Equal(first+4,count(),"orbit explicit count");
            AssertVfxNear(new Vector2(15,0),VfxVertexCenter(vertices(first)),"orbit radius interpolation");
            orbit.Count=0;Draw(orbit);Equal(first+4,count(),"zero count stays silent");
            var rotated=ExplicitShape();rotated.RotationRadians=MathF.PI/2;first=count();Draw(rotated);
            AssertVfxNear(new Vector2(0,10),VfxVertexCenter(vertices(first)),"explicit rotation applies independently");
            Equal(count(),spends,"only actual quads spend draw budget");
        });
    }
    private sealed class ShapeSource : VfxSourceBinding
    {
        internal bool Live=true;
        internal Vector2 Position;
        internal int Age;
        private readonly object generation=new();
        internal override bool IsLive=>Live;
        internal override object Generation=>generation;
        internal override int WorldAge=>Age;
        internal override bool TryFrame(string anchor,out VfxSourceFrame frame) {frame=new(Position,Vector2.UnitX,Vector2.Zero);return Live;}
    }
    private static void ExplicitShapeEmissionLifecycleAndSharedBudget()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            const BindingFlags flags=BindingFlags.Static|BindingFlags.NonPublic;
            Type type=typeof(InfiniDetachedVfxSystem);
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",flags)!;object? oldClock=clock.GetValue(null);bool oldServer=Terraria.Main.dedServ;
            var emissions=(IList)type.GetField("ShapeEmissions",flags)!.GetValue(null)!;
            var system=new InfiniDetachedVfxSystem();
            void Invoke(string name,params object[] args)=>type.GetMethod(name,flags)!.Invoke(null,args);
            void Draw(){Invoke("BeginDrawBudgetFrame");Invoke("DrawShapes","AfterProjectiles",pixel,(Action)(()=>{}));}
            try {
                system.OnWorldUnload();Terraria.Main.dedServ=false;clock.SetValue(null,100u);
                var data=GeneratedItemData.Placeholder();data.VfxManifest=new(){RecipeId="shape",Budget=new(){MaxDrawCalls=1,MaxParticlesPerTick=0,MaxParticlesTotal=0},Slots=new[]{ExplicitShapeSlot()}};
                var slot=data.VfxManifest.Slots[0];slot.StartTick=2;
                var source=new ShapeSource{Position=new Vector2(40,60)};
                var frame=new VfxSourceFrame(source.Position,Vector2.UnitX,Vector2.Zero);
                Equal(true,InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,"probe",slot,"shape-source",frame,source),"snapshot enqueues world shape");
                slot.Shape!.LengthPx=200;slot.Shape.ColorStart.R=0; // captured payload must not alias mutable DTO
                Draw();Equal(0,count(),"event startTick delays drawing");
                clock.SetValue(null,102u);source.Position+=new Vector2(30,0);Draw();Equal(1,count(),"event begins on due tick");
                AssertVfxNear(new Vector2(10,0),VfxVertexCenter(vertices(0)),"world capture freezes pose and authored length");
                Equal((byte)255,colors(0)[0].R,"captured color immutable");
                var attached=ExplicitShapeSlot();attached.Shape!.Attachment="source";
                Equal(true,InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,"probe",attached,"shape-source",frame,source),"source shape admission");
                Draw();Equal(2,count(),"two slots share cap1, not cap each");
                source.Live=false;Invoke("UpdateShapes",102UL);Equal(1,emissions.Count,"retired source deletes attachment only");
                clock.SetValue(null,112u);Invoke("UpdateShapes",112UL);Equal(0,emissions.Count,"world shape expires exactly duration after due");
                // Cadence is emission interval, not phase period; delayed start uses source age.
                source=new ShapeSource{Position=frame.Position,Age=0};slot=ExplicitShapeSlot();slot.Event="periodic";slot.StartTick=2;slot.RepeatEvery=3;slot.Duration=10;data.VfxManifest.Slots=new[]{slot};
                clock.SetValue(null,200u);InfiniDetachedVfxSystem.RegisterPeriodicElements(data,"probe","periodic-shape",source);
                Invoke("UpdatePeriodicElements",200UL);Equal(0,emissions.Count,"periodic gate before age2");
                clock.SetValue(null,202u);Invoke("UpdatePeriodicElements",202UL);Equal(1,emissions.Count,"first emission at age2");
                Invoke("UpdatePeriodicElements",202UL);Equal(1,emissions.Count,"same tick not duplicated");
                clock.SetValue(null,205u);Invoke("UpdatePeriodicElements",205UL);Equal(2,emissions.Count,"cadence emits second independent lifetime");
                system.OnWorldUnload();Equal(0,emissions.Count,"world unload retires shape records");
            } finally {system.OnWorldUnload();clock.SetValue(null,oldClock);Terraria.Main.dedServ=oldServer;}
        });
    }
    private static void ActivePrimitiveSlotsShareBudget()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            var slot=new VfxSlotSpec{RendererKind="wavyStrip",StartTick=0,RepeatEvery=10,Duration=10,Scale=1,Density=0};
            var manifest=new VfxManifestSpec{Budget=new(){MaxDrawCalls=3}};var state=new InfiniVfxState();
            var draw=typeof(InfiniVfxRuntime).GetMethod("DrawActivePrimitive",BindingFlags.Static|BindingFlags.NonPublic)!;
            object[] args={pixel,Vector2.Zero,Vector2.UnitX,slot,manifest,state,Color.White};
            draw.Invoke(null,args);draw.Invoke(null,args);
            Equal(3,count(),"two live primitive slots share exact cap");Equal(3,state.DrawCallsThisFrame,"class alias retains spent budget");
        });
    }
}
