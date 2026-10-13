using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Collections;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using ParticleLibrary.Core.V3.Particles;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Reflection keeps this observer compilable against the before source. The
    // first positive DTO assertion is the behavioral RED, not a missing-type error.
    private static JsonObject LibrarySlotWire(bool shake = false)
    {
        var row = JsonSerializer.SerializeToNode(new VfxSlotSpec {
            Id="library",EntityId="unavailable_item",Event=shake?"on_use":"periodic",
            RendererKind=shake?"screenShakeCue":"libraryParticle",Backend=shake?"Realtime":"Particle",
            TextureRole="none",ParticleRole="none",ParticleSystemId="none",EmissionMode="none",
            Channel=shake?"screenShake":"ambientParticles",Lane=shake?"cue":"support",
            Scale=1,Alpha=1,Duration=shake?3:12,RepeatEvery=shake?0:1,
            BudgetWeight=1,Layer="BeforeProjectiles"
        }, new JsonSerializerOptions { PropertyNamingPolicy=JsonNamingPolicy.CamelCase })!.AsObject();
        row[shake?"screenShake":"particle"] = shake ? new JsonObject {
            ["strengthPx"]=6,["angularVarianceRadians"]=0.25,["directionRadians"]=0,
            ["dissipationPxPerFrame"]=0.5,["taperStartDistancePx"]=100,["taperEndDistancePx"]=200
        } : new JsonObject {
            ["textureId"]="star",["count"]=2,["speedMinPxPerTick"]=2,["speedMaxPxPerTick"]=2,
            ["spreadRadians"]=0,["inheritVelocity"]=1,["drag"]=0.5,
            ["accelerationXPxPerTickSquared"]=1,["accelerationYPxPerTickSquared"]=-1,
            ["widthPx"]=8,["heightPx"]=20,["rotationRadians"]=0.25,["rotationSpeedRadiansPerTick"]=0.5,
            ["colorStart"]="white",["colorEnd"]="effect",["endScaleMultiplier"]=2,["endOpacity"]=0
        };
        return row;
    }
    private static JsonObject LibraryManifestWire(bool shake = false)
    {
        var wire=JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!["vfxManifest"]!.AsObject();
        wire["slots"]=new JsonArray(LibrarySlotWire(shake));return wire.DeepClone().AsObject();
    }
    private static VfxManifestSpec ParseLibraryManifest(bool shake = false)
    {
        var manifest=VfxManifestSpec.FromJson(LibraryManifestWire(shake).ToJsonString());
        Equal(true,manifest.HasSlots,"explicit library payload must be accepted");return manifest;
    }
    private static object? LibraryInvoke(string name, params object?[] args)
    {
        var method=typeof(InfiniDetachedVfxSystem).GetMethod(name,BindingFlags.Static|BindingFlags.NonPublic)
            ?? throw new InvalidOperationException("library consumer missing: "+name);
        try{return method.Invoke(null,args);}catch(TargetInvocationException error){throw error.InnerException!;}
    }
    private static IList LibraryOwnerQueue()=>OwnedMaterialQueue();
    private static GeneratedItemData LibraryData(bool shake = false)
    {
        var data=GeneratedItemData.Placeholder();data.VfxManifest=ParseLibraryManifest(shake);return data;
    }
    private static bool EnqueueLibraryForCheck(GeneratedItemData data,string source,VfxSourceFrame frame,bool item = false,MaterialEventAllowance? allowance = null)
        =>(bool)LibraryInvoke("EnqueueLibrary",data,data.VfxManifest.Slots[0],source,frame,item,allowance)!;

    private static void ExplicitLibraryReadinessWaitPreservesCountAndExpires()
    {
        WithLighting((config,_)=>{
            var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;
            int priorMode=Terraria.Main.netMode;
            try {
                LibraryInvoke("LoadLibrary");system.OnWorldUnload();config.EnableParticleLibraryBackend=true;config.ParticleSpawnMultiplier=1;
                var data=LibraryData();var slot=data.VfxManifest.Slots[0];slot.Event="on_hit";slot.RepeatEvery=0;
                Equal(true,EnqueueLibraryForCheck(data,"readiness",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"CPU-only graphics-unready emission queues");
                Equal(1,LibraryOwnerQueue().Count,"new kind reuses canonical delayed record owner");
                config.ParticleSpawnMultiplier=0;MaterialClock(tick+1);system.PostUpdateEverything();
                Equal(1,LibraryOwnerQueue().Count,"readiness retry does not reroll count against changed multiplier");
                MaterialClock(tick+30);system.PostUpdateEverything();Equal(0,LibraryOwnerQueue().Count,"bounded readiness wait expires without Draw");
                var empty=LibraryManifestWire();empty["slots"]![0]!["particle"]!["count"]=0;
                data.VfxManifest=VfxManifestSpec.FromJson(empty.ToJsonString());
                Equal(false,EnqueueLibraryForCheck(data,"zero",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"zero never allocates a pending record");
                data.VfxManifest=ParseLibraryManifest();config.EnableParticleLibraryBackend=false;
                Equal(false,EnqueueLibraryForCheck(data,"disabled",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"disabled backend never falls back to Dust");
                config.EnableParticleLibraryBackend=true;config.ParticleSpawnMultiplier=1;
                data.VfxManifest.Budget.MaxParticlesTotal=0;
                Equal(false,EnqueueLibraryForCheck(data,"zero-total",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"zero total suppresses before pending allocation");
                data.VfxManifest.Budget.MaxParticlesTotal=1000;
                Equal(false,EnqueueLibraryForCheck(data,"nonfinite",new VfxSourceFrame(new Vector2(float.NaN,0),Vector2.UnitX,Vector2.Zero)),"nonfinite captured point never queues");
                system.OnWorldUnload();
                for(int i=0;i<128;i++)Equal(true,EnqueueLibraryForCheck(data,"bounded:"+i,new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"positive pending slot "+i);
                Equal(false,EnqueueLibraryForCheck(data,"overflow",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"exact 128-record cap suppresses overflow, no fallback");
                Equal(128,LibraryOwnerQueue().Count,"pending library resource roster stays bounded");
                system.OnWorldUnload();Equal(0,LibraryOwnerQueue().Count,"world clear retires pending without emission");
                Terraria.Main.netMode=Terraria.ID.NetmodeID.Server;
                Equal(false,EnqueueLibraryForCheck(data,"server",new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero)),"server suppresses new effects even without dedServ");
            }finally{Terraria.Main.netMode=priorMode;system.OnWorldUnload();MaterialClock(tick);}
        });
    }

}
