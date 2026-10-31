using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxSlotSpec NativeCueSlot(bool light=false) {
        var slot=new VfxSlotSpec { Id="cue",EntityId="unavailable_item",Event="on_use",RendererKind=light?"nativeLight":"nativeDust",
            Anchor="self",StartTick=0,RepeatEvery=0,Color=Rgb(17,83,241) };
        if(light)slot.Light=new VfxNativeLightSpec{Intensity=.7f};
        else slot.Dust=new VfxNativeDustSpec{Type="GemDiamond",Count=3,Size=1.25f,SpeedMinPxPerTick=2,SpeedMaxPxPerTick=2,
            SpreadRadians=0,InheritVelocity=.5f,NativeAlpha=37,NoGravity=false};
        return slot;
    }
    private static void NativeCuesRejectMissingAndForeignControls()
    {
        foreach(bool light in new[]{false,true}) {
            var manifest=new VfxManifestSpec{Slots=new[]{NativeCueSlot(light)}};
            string json=manifest.ToJson();Equal(true,VfxManifestSpec.FromJson(json).HasSlots,"native cue roundtrip");
            var root=JsonNode.Parse(json)!; string payload=light?"light":"dust";
            foreach(var field in root["slots"]![0]![payload]!.AsObject().Select(p=>p.Key).ToArray()) {
                var bad=root.DeepClone();bad["slots"]![0]![payload]!.AsObject().Remove(field);
                Equal(false,VfxManifestSpec.FromJson(bad.ToJsonString()).HasSlots,"native cue requires "+field);
            }
            foreach(string field in new[]{"scale","density","alpha","spread","duration","phaseOffset"}) {
                var bad=root.DeepClone();bad["slots"]![0]![field]=0;
                Equal(false,VfxManifestSpec.FromJson(bad.ToJsonString()).HasSlots,"native cue forbids unused "+field);
            }
            var negative=root.DeepClone();negative["slots"]![0]![payload]![light?"intensity":"size"]=-1;
            Equal(false,VfxManifestSpec.FromJson(negative.ToJsonString()).HasSlots,"invalid cue never clamps");
        }
    }
    private static void NativeCuesCaptureFrameAndRespectBudgets()
    {
        WithLighting((config,lights)=> {
            var oldDust=Terraria.Main.dust;var oldRandom=Terraria.Main.rand;bool menu=Terraria.Main.gameMenu,gen=WorldGen.gen;
            int max=Terraria.Main.maxDustToDraw,width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;
            Vector2 screen=Terraria.Main.screenPosition;float dCount=Dust.dCount;
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",BindingFlags.Static|BindingFlags.NonPublic)!;object? previous=clock.GetValue(null);
            var system=new InfiniDetachedVfxSystem();
            try {
                system.OnWorldUnload();Terraria.Main.gameMenu=false;WorldGen.gen=false;Terraria.Main.maxDustToDraw=6000;
                Terraria.Main.screenWidth=800;Terraria.Main.screenHeight=600;Terraria.Main.screenPosition=Vector2.Zero;
                Terraria.Main.dust=new Dust[6001];for(int i=0;i<Terraria.Main.dust.Length;i++)Terraria.Main.dust[i]=new Dust{dustIndex=i};
                Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(7);Dust.dCount=0;MaterialClock(100);
                config.ParticleSpawnMultiplier=1;config.PresentationLightMultiplier=1;
                var data=GeneratedItemData.Placeholder();var slot=NativeCueSlot();data.VfxManifest=new VfxManifestSpec{Slots=new[]{slot}};
                data.VfxManifest.Budget.MaxParticlesPerTick=2;data.VfxManifest.Budget.MaxParticlesTotal=5;
                slot.StartTick=2;
                var frame=new VfxSourceFrame(new Vector2(100,120),Vector2.UnitY,new Vector2(4,0));
                Equal(true,InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,slot.EntityId,slot,"native-cue",frame),"delayed cue admitted");
                slot.Dust!.Count=64;slot.Dust.SpeedMaxPxPerTick=12;slot.Color!.R=255;
                Equal(0,Terraria.Main.dust.Count(d=>d.active),"delay does not emit early");
                MaterialClock(102);system.PostUpdateEverything();
                Equal(2,Terraria.Main.dust.Count(d=>d.active),"actual native dust consumes shared tick ceiling");
                foreach(var dust in Terraria.Main.dust.Where(d=>d.active)) {
                    Equal(new Vector2(100,120),dust.position,"captured position");Equal(new Vector2(2,2),dust.velocity,"explicit forward speed plus inherited velocity");
                    Equal(new Color(17,83,241),dust.color,"snapshot owns copied RGB");Equal(37,dust.alpha,"authored native alpha");Equal(false,dust.noGravity,"authored gravity flag");
                }
                MaterialClock(103);system.PostUpdateEverything();Equal(2,Terraria.Main.dust.Count(d=>d.active),"cue emits once rather than acquiring lifetime");
                var light=NativeCueSlot(true);light.StartTick=2;data.VfxManifest.Slots=new[]{light};
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,light.EntityId,light,"native-light",frame,itemBudget:true);
                light.Light!.Intensity=0;light.Color!.G=0;
                MaterialClock(105);system.PostUpdateEverything();Equal(1,lights.Count,"delayed native light emitted once");
                var actual=(Vector3)lights[0]!.GetType().GetField("Color")!.GetValue(lights[0])!;
                Equal(new Color(17,83,241).ToVector3()*.7f,actual,"same explicit light strength for item and projectile");
                MaterialClock(106);system.PostUpdateEverything();Equal(1,lights.Count,"no hidden light lifetime");
                var zero=NativeCueSlot();zero.Dust!.Count=0;data.VfxManifest.Slots=new[]{zero};
                Equal(false,InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,zero.EntityId,zero,"silent",frame),"zero count is silent");
                Equal(2,Terraria.Main.dust.Count(d=>d.active),"zero does not create fallback dust");
            } finally {
                system.OnWorldUnload();Terraria.Main.dust=oldDust;Terraria.Main.rand=oldRandom;Terraria.Main.gameMenu=menu;WorldGen.gen=gen;
                Terraria.Main.maxDustToDraw=max;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;Terraria.Main.screenPosition=screen;Dust.dCount=dCount;clock.SetValue(null,previous);
            }
        });
    }
    private static void NativeCuePeriodicLightNeedsFunctionalRenewal()
    {
        WithPlayer((player,_)=>WithLighting((config,lights)=> {
            var system=new InfiniDetachedVfxSystem();
            using var actors=new NativeActorState();
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",BindingFlags.Static|BindingFlags.NonPublic)!;object? previous=clock.GetValue(null);
            try {
                system.OnWorldUnload();config.PresentationLightMultiplier=1;
                player.whoAmI=0;player.active=true;Terraria.Main.player[0]=player;
                var data=GeneratedItemData.Placeholder();var slot=NativeCueSlot(true);slot.Event="periodic";slot.RepeatEvery=1;
                data.VfxManifest=new VfxManifestSpec{Slots=new[]{slot}};
                var item=player.inventory[0]=new Item {type=Terraria.ID.ItemID.CopperShortsword,stack=1};player.selectedItem=0;
                AttachItem(new InfiniCrafterLocal.Content.Items.GeneratedItem(),item,data);
                MaterialClock(500);InfiniItemVfxRuntime.OnPeriodic(player,data,slot.EntityId,item);system.PostUpdateEverything();
                Equal(1,lights.Count,"functional periodic light emits");
                MaterialClock(501);system.PostUpdateEverything();Equal(1,lights.Count,"stale item binding is not functional permission");
                MaterialClock(502);InfiniItemVfxRuntime.OnPeriodic(player,data,slot.EntityId,item,allowLightCue:false);system.PostUpdateEverything();
                Equal(1,lights.Count,"vanity callback never renews light permission");
                MaterialClock(503);InfiniItemVfxRuntime.OnPeriodic(player,data,slot.EntityId,item);system.PostUpdateEverything();
                Equal(2,lights.Count,"renewed functional callback resumes explicit cadence");
            } finally {system.OnWorldUnload();clock.SetValue(null,previous);}
        }));
    }

}
