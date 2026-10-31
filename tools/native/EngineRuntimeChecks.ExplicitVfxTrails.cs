using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxHistoryTrailSpec ExplicitTrail(string draw="stroke")
    {
        var trail=new VfxHistoryTrailSpec{Draw=draw,Source="center",HistoryTicks=8,SampleStepTicks=2,FirstSampleAgeTicks=0,
            OpacityProfile=new(){Start=1,Middle=1,End=1,Curve="linear"},Color=new(){R=255,G=255,B=255}};
        if(draw=="stroke")trail.WidthPx=.25f;
        else {trail.Texture=new(){Source="impact",AssetId=""};trail.Scale=1;trail.Pose="sampled";}
        return trail;
    }
    private static void ExplicitTrailAdmission()
    {
        foreach(string draw in new[]{"stroke","sprites"}) {
            var manifest=new VfxManifestSpec{RecipeId="trail",Slots=new[]{new VfxSlotSpec{Id="trail",EntityId="probe",RendererKind="historyTrail",Event="periodic",Anchor="self",Blend="alpha",Layer="AfterProjectiles",Trail=ExplicitTrail(draw)}}};
            string json=manifest.ToJson();Equal(true,json.Length>0,"explicit trail admission "+draw);
            Equal(json,VfxManifestSpec.FromJson(json).ToJson(),"trail exact roundtrip");
            void Reject(Action<JsonObject,JsonObject> change,string label) {
                var root=JsonNode.Parse(json)!;var slot=root["slots"]![0]!.AsObject();change(slot,slot["trail"]!.AsObject());
                Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,label);
            }
            Reject((slot,t)=>slot["startTick"]=0,"unconsumed start gate rejected");
            Reject((slot,t)=>slot["event"]="on_hit","instantaneous historical path rejected");
            Reject((slot,t)=>slot["anchor"]="tip","source owns trajectory not ambiguous anchor");
            Reject((slot,t)=>t.Remove("firstSampleAgeTicks"),"sampling origin must be authored");
            Reject((slot,t)=>t["sampleStepTicks"]=33,"stride out of history rejected");
            Reject((slot,t)=>t["firstSampleAgeTicks"]=32,"first sample outside history rejected");
            Reject((slot,t)=>t[draw=="stroke"?"scale":"widthPx"]=1,"foreign draw controls rejected");
            Reject((slot,t)=>slot["alpha"]=1,"no second opacity authority");
        }
    }
    private static void ExplicitTrailGeometryAndPose()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            var samples=new List<VfxTrailSample>();
            for(int i=0;i<8;i++)samples.Add(new(100UL-(ulong)i,new Vector2(40+i*10,60),null));
            var trail=ExplicitTrail();trail.FirstSampleAgeTicks=1;
            InfiniDetachedVfxSystem.BeginActiveDraw("trail-test");
            int spends=0;
            void Draw(VfxHistoryTrailSpec t,IReadOnlyList<VfxTrailSample> h,VfxTrailPose? pose=null)=>InfiniVfxRuntime.DrawExplicitTrailSamples(pixel,pixel,h,t,"alpha",100,pose,()=>{spends++;return true;});
            Draw(trail,samples);Equal(3,count(),"ages1,3,5,7 form3 explicit segments");
            AssertVfxNear(new Vector2(20,0),VfxVertexCenter(vertices(0)),"first age and stride select exact samples");
            float min=float.MaxValue,max=float.MinValue;foreach(var p in vertices(0)){min=Math.Min(min,p.Y);max=Math.Max(max,p.Y);}Equal(true,Math.Abs(max-min-.25f)<.001f,"stroke width remains subpixel");
            var gap=new[]{samples[1],samples[5]};int beforeGap=count();Draw(trail,gap);Equal(beforeGap,count(),"missing selected sample breaks stroke rather than inventing a bridge");
            trail.FirstSampleAgeTicks=31;Draw(trail,samples);Equal(beforeGap,count(),"first age outside available history is explicit silence");trail.FirstSampleAgeTicks=1;
            trail.WidthPx=0;Draw(trail,samples);Equal(3,count(),"explicit zero stroke is silent");
            trail.WidthPx=1;Draw(trail,Array.Empty<VfxTrailSample>());Equal(3,count(),"no fabricated missing history");
            var stamp=ExplicitTrail("sprites");stamp.SampleStepTicks=1;
            var capture=typeof(InfiniVfxRuntime).GetMethod("CaptureTrailPose",BindingFlags.Static|BindingFlags.NonPublic)!;
            var projectile=new Projectile{rotation=0,scale=1,spriteDirection=1,gfxOffY=2};
            var selected=new SpritePresentationSelection("test",null,null,ImpactTexture:true);
            VfxTrailPose Capture()=>(VfxTrailPose)capture.Invoke(null,new object?[]{pixel,projectile,null,selected,1f})!;
            VfxTrailPose old=Capture();projectile.rotation=MathF.PI/2;projectile.scale=2;projectile.spriteDirection=-1;projectile.gfxOffY=6;VfxTrailPose current=Capture();
            var h=new[]{new VfxTrailSample(100,new Vector2(40,60),current),new VfxTrailSample(99,new Vector2(60,60),old)};
            int first=count();Draw(stamp,h,current);Equal(first+2,count(),"sampled stamps have actual recorded poses");
            AssertVfxNear(new Vector2(0,6),VfxVertexCenter(vertices(first)),"new pose uses new gfx offset");
            AssertVfxNear(new Vector2(20,2),VfxVertexCenter(vertices(first+1)),"older pose retains old gfx offset");
            Equal(SpriteEffects.None,old.Effects,"captured old flip remains immutable");Equal(SpriteEffects.FlipHorizontally,current.Effects,"current flip captured");
            Equal(1f,old.Scale,"old scale retained");Equal(2f,current.Scale,"new scale captured");
            stamp.Pose="current";first=count();Draw(stamp,h,current);
            AssertVfxNear(new Vector2(20,6),VfxVertexCenter(vertices(first+1)),"current mode intentionally uses live pose for old center");
            stamp.OpacityProfile.Start=stamp.OpacityProfile.Middle=stamp.OpacityProfile.End=0;Draw(stamp,h,current);Equal(first+2,count(),"zero opacity does not consume a draw");
            Equal(count(),spends,"every visible segment or stamp debits budget once");
        });
    }
    private static void ExplicitTrailCapturesWorldTicksWithoutFabrication()
    {
        WithLighting((config,_)=>{
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",BindingFlags.Static|BindingFlags.NonPublic)!;
            object? previous=clock.GetValue(null);bool server=Terraria.Main.dedServ;
            try {
                Terraria.Main.dedServ=false;
                var data=GeneratedItemData.Placeholder();
                var trail=ExplicitTrail();trail.Source="tip";
                data.VfxManifest=new(){RecipeId="trail",Slots=new[]{new VfxSlotSpec{Id="trail",EntityId="probe",RendererKind="historyTrail",Event="on_spawn",Anchor="self",Blend="alpha",Layer="AfterProjectiles",Trail=trail}}};
                var projectile=new Projectile{active=true,width=10,height=10,scale=1,velocity=Vector2.UnitX};
                var state=new InfiniVfxState();
                for(uint tick=1;tick<=40;tick++) {
                    clock.SetValue(null,tick);projectile.Center=new Vector2(tick*10,0);
                    InfiniVfxRuntime.OnTick(projectile,data,"probe",data.VfxManifest,ref state);
                    InfiniVfxRuntime.OnTick(projectile,data,"probe",data.VfxManifest,ref state);
                }
                var history=state.TrailHistory["trail"];
                Equal(32,history.Count,"bounded32 real samples despite repeated callbacks");
                Equal(40UL,history[0].Tick,"newest tick exact");Equal(9UL,history[31].Tick,"oldest retained tick exact");
                AssertVfxNear(new Vector2(405,0),history[0].Position,"tip captures actual geometric endpoint");
                clock.SetValue(null,45u);projectile.Center=new Vector2(450,0);InfiniVfxRuntime.OnTick(projectile,data,"probe",data.VfxManifest,ref state);
                Equal(28,history.Count,"missing world ticks never filled with invented points");
                Equal(40UL,history[1].Tick,"gap stays a gap");
            } finally {clock.SetValue(null,previous);Terraria.Main.dedServ=server;}
        });
    }

    private static void ExplicitTrailUsesSavedBeamAndLashTips()
    {
        WithPlayer((owner,_)=>{
            using var actors=new NativeActorState();
            const BindingFlags flags=BindingFlags.Static|BindingFlags.NonPublic;
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",flags)!;
            object? previous=clock.GetValue(null);bool server=Terraria.Main.dedServ;
            try {
                Terraria.Main.dedServ=false;owner.active=true;owner.whoAmI=0;Terraria.Main.player[0]=owner;
                var data=GeneratedItemData.Placeholder();
                var entity=new RuntimeEntitySpec{Id="probe",Kind=RuntimeEntityKind.FreeProjectile,LifetimeTicks=120};
                entity.Visual.AssetMode="no_asset";entity.Hitbox.WidthPx=10;entity.Hitbox.HeightPx=10;
                data.RuntimeProgram.Entities=new[]{entity};
                var trail=ExplicitTrail();trail.Source="tip";
                data.VfxManifest=new(){RecipeId="saved-tip",Slots=new[]{new VfxSlotSpec{Id="trail",EntityId="probe",RendererKind="historyTrail",Event="periodic",Anchor="self",Blend="alpha",Layer="AfterProjectiles",Trail=trail}}};
                var projectile=new Projectile{owner=0,active=true,Center=new Vector2(150,180),velocity=Vector2.UnitX};
                var generated=Attach(projectile);typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile,generated);generated.Configure(data,entity,0,8,Vector2.UnitX);
                entity.Movement.Code=18;entity.Movement.Name="move_whip";
                var build=generated.GetType().GetMethod("BuildLashPoints",TestInstance)!;
                build.Invoke(generated,new object[]{new Vector2(30,40),Vector2.UnitX,.35f,96f,16,-1.2f,1.2f,.2f,1f,1,1f});
                foreach(string scenario in new[]{"saved_lash","saved_beam","beam_over_lash"}) {
                    entity.Movement.Code=scenario=="saved_beam"?0:18;entity.Movement.Name=scenario=="saved_beam"?"":"move_whip";
                    entity.Controller.Code=scenario=="saved_lash"?0:RuntimeControllerCode.ChannelBeam;
                    entity.Controller.Params.RangeTiles=10;entity.Controller.Params.WidthPx=2;entity.Controller.Params.RaycastTiles=false;
                    string kind=scenario=="saved_lash"?"whip":"beam";
                    Equal(true,generated.TryCapturePresentationGeometry(kind,out var points),"saved native producer available "+scenario);
                    Equal(true,InfiniVfxRuntime.TryExplicitTrailTip(projectile,data,"probe",out var tip),"new trail resolves saved producer "+scenario);
                    AssertVfxNear(points[^1],tip,"new trail actual endpoint "+scenario);
                    Equal(true,Vector2.Distance(tip,InfiniVfxRuntime.ForwardTip(projectile,data,"probe"))>1,"fixture distinguishes old width tip "+scenario);
                    var state=new InfiniVfxState();clock.SetValue(null,100u);
                    InfiniVfxRuntime.OnTick(projectile,data,"probe",data.VfxManifest,ref state);
                    AssertVfxNear(points[^1],state.TrailHistory["trail"][0].Position,"capture uses actual endpoint "+scenario);
                }
                entity.Controller.Code=0;entity.Movement.Code=18;entity.Movement.Name="move_whip";
                ((List<Vector2>)generated.GetType().GetField("_whipPoints",TestInstance)!.GetValue(generated)!).Clear();
                Equal(false,InfiniVfxRuntime.TryExplicitTrailTip(projectile,data,"probe",out var unavailableTip),"missing declared lash geometry is not replaced by width tip");
            } finally {clock.SetValue(null,previous);Terraria.Main.dedServ=server;}
        });
    }

}
