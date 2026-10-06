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

    private static void ExplicitLibraryDtoRequiresTypedPayloadAndPreservesZero()
    {
        foreach(bool shake in new[]{false,true}) {
            var manifest=ParseLibraryManifest(shake);
            string key=shake?"screenShake":"particle";
            var roundtrip=JsonNode.Parse(manifest.ToJson())!["Slots"]![0]!.AsObject();
            Equal(true,roundtrip.ContainsKey(shake?"ScreenShake":"Particle"),"exact typed DTO survives direct serializer");
            var wire=LibraryManifestWire(shake);
            wire["slots"]![0]![key]![shake?"strengthPx":"count"]=0;
            Equal(true,VfxManifestSpec.FromJson(wire.ToJsonString()).HasSlots,"zero is legal, never filled from a preset");
        }
        var itemWire=JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();
        itemWire["vfxManifest"]=LibraryManifestWire();
        var item=GeneratedItemData.FromJson(itemWire.ToJsonString());Equal(true,item is not null,"particle reaches full GeneratedItemData decoder");
        foreach(string json in new[]{item!.ToJson(),item.ToLocalCacheJson(),item.ToNetworkJson()})
            Equal(20f,JsonNode.Parse(json)!["vfxManifest"]!["slots"]![0]!["particle"]!["heightPx"]!.GetValue<float>(),"independent pixel height survives all serializers");
        var legacy=GeneratedItemData.Placeholder();
        foreach(string json in new[]{legacy.ToJson(),legacy.ToLocalCacheJson(),legacy.ToNetworkJson()})foreach(var slot in JsonNode.Parse(json)!["vfxManifest"]!["slots"]!.AsArray()) {
            Equal(false,slot!.AsObject().ContainsKey("particle"),"absent new particle remains absent on legacy wire");
            Equal(false,slot.AsObject().ContainsKey("screenShake"),"absent new cue remains absent on legacy wire");
        }
    }
    private static void ExplicitLibraryDtoRejectsMissingForeignAndNonfinite()
    {
        int cases=0;
        foreach(bool shake in new[]{false,true}) {
            string payload=shake?"screenShake":"particle";
            void Reject(Action<JsonObject> mutation) {
                var wire=LibraryManifestWire(shake);mutation(wire["slots"]![0]!.AsObject());
                Equal(false,VfxManifestSpec.FromJson(wire.ToJsonString()).HasSlots,"strict library reject "+cases++);
            }
            foreach(string key in LibrarySlotWire(shake)[payload]!.AsObject().Select(p=>p.Key).ToArray()) {
                Reject(s=>s[payload]!.AsObject().Remove(key));Reject(s=>s[payload]![key]=null);
            }
            Reject(s=>s[payload]=null);Reject(s=>s.Remove(payload));
            Reject(s=>s[payload]!["foreign"]=1);
            Reject(s=>s[shake?"particle":"screenShake"]=LibrarySlotWire(!shake)[shake?"particle":"screenShake"]!.DeepClone());
            Reject(s=>s["element"]=new JsonObject());Reject(s=>s["path"]=new JsonObject());
            Reject(s=>s["rendererKind"]="childMotes");Reject(s=>s["phaseOffset"]=0.5);Reject(s=>s["scale"]=2);
            Reject(s=>s[payload]![shake?"strengthPx":"speedMinPxPerTick"]="NaN");
            if(shake) {
                Reject(s=>s["event"]="periodic");Reject(s=>s["repeatEvery"]=1);Reject(s=>s["duration"]=4);
                Reject(s=>s["alpha"]=0.5);Reject(s=>s["blend"]="additive");Reject(s=>s["layer"]="AfterProjectiles");
                Reject(s=>s["channel"]="screen");Reject(s=>s[payload]!["taperEndDistancePx"]=100);
            }else {
                Reject(s=>s[payload]!["speedMaxPxPerTick"]=1);Reject(s=>s[payload]!["widthPx"]=129);
                Reject(s=>s[payload]!["textureId"]="Star");Reject(s=>s[payload]!["colorEnd"]="CYAN");
                Reject(s=>s["repeatEvery"]=0);Reject(s=>s["channel"]="coreGlow");
            }
        }
        // Typed in-memory nonfinite controls bypass JSON's own number refusal.
        foreach(bool shake in new[]{false,true}) {
            var manifest=ParseLibraryManifest(shake);var slot=manifest.Slots[0];
            var typed=slot.GetType().GetProperty(shake?"ScreenShake":"Particle")!.GetValue(slot)!;
            typed.GetType().GetProperty(shake?"StrengthPx":"SpeedMinPxPerTick")!.SetValue(typed,float.NaN);
            Equal("",manifest.ToJson(),"nonfinite typed DTO fails before dispatch");
        }
        var itemWire=JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();itemWire["vfxManifest"]=LibraryManifestWire();
        itemWire["vfxManifest"]!["slots"]![0]!["startTick"]=1;
        Equal(true,GeneratedItemData.FromJson(itemWire.ToJsonString()) is null,"item periodic has no invented activation clock");
        Console.WriteLine("DETAIL: explicit library strict cases="+cases);
    }
    private static void ExplicitLibraryParticleInfoHasLiteralMotionAndPixelAxes()
    {
        var slot=ParseLibraryManifest().Slots[0];var frame=new VfxSourceFrame(new Vector2(10,20),Vector2.UnitY,new Vector2(4,6));
        var info=(ParticleInfo)LibraryInvoke("CreateLibraryInfo",slot,frame,Color.Cyan,0.5f,0.5f)!;
        Equal(new System.Numerics.Vector2(4,8),info.Velocity,"initial cone plus captured world-tick velocity");
        Equal(new System.Numerics.Vector2(8,20),info.Scale,"unit quad consumes literal independent pixel axes, not native texture division");
        Equal(12,info.Time,"authored lifetime");
        var args=new object?[]{info};LibraryInvoke("AdvanceLibraryInfo",args);info=(ParticleInfo)args[0]!;
        Equal(new System.Numerics.Vector2(3,3),info.Velocity,"drag then world acceleration");
        Equal(new System.Numerics.Vector2(13,23),info.Position,"position integrates actual world velocity");
        Equal(11,info.Time,"one CPU update is one world tick");
        Equal(true,Math.Abs(info.Rotation-(MathHelper.PiOver2+0.75f))<0.0001f,"captured axis plus authored rotation and spin");
        for(int i=1;i<12;i++){args[0]=info;LibraryInvoke("AdvanceLibraryInfo",args);info=(ParticleInfo)args[0]!;}
        Equal(0,info.Time,"exact expiry, no library lag frame");Equal(Color.Transparent,info.Color,"expired particle contributes no alpha or RGB");
    }
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
    private static void ExplicitLuminanceNativeRumbleRetiresCanceledOwnedCue()
    {
        WithLighting((_,_)=>{
            var owner=new InfiniDetachedVfxSystem();var nativeSystem=new Luminance.Core.Graphics.ScreenShakeSystem();
            var nativeType=typeof(Luminance.Core.Graphics.ScreenShakeSystem);
            var roster=(IList)nativeType.GetField("shakes",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
            var oldRoster=roster.Cast<object>().ToArray();
            var rumbleField=nativeType.GetField("universalRumble",BindingFlags.Static|BindingFlags.NonPublic)!;
            var oldRumble=rumbleField.GetValue(null);
            var configInstance=typeof(Terraria.ModLoader.ContentInstance<Luminance.Core.Config>).GetProperty("Instance")!;
            var oldConfig=configInstance.GetValue(null);
            int local=Terraria.Main.myPlayer;var oldPlayer=Terraria.Main.player[local];
            ulong originalTick=Terraria.Main.GameUpdateCount,tick=originalTick;var oldScreen=Terraria.Main.screenPosition;var oldRandom=Terraria.Main.rand;
            try {
                configInstance.SetValue(null,new Luminance.Core.Config{ScreenshakeModifier=0});
                Terraria.Main.player[local]=new Player{active=true,whoAmI=local,Center=Vector2.Zero};
                Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(71);
                LibraryInvoke("LoadLibrary");
                foreach(bool nativeFirst in new[]{true,false}) {
                    owner.OnWorldUnload();roster.Clear();
                    Luminance.Core.Graphics.ScreenShakeSystem.SetUniversalRumble(0,0,Vector2.UnitX,0.5f);
                    var data=LibraryData(true);var frame=new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero);
                    void Visit() {
                        if(nativeFirst){nativeSystem.ModifyScreenPosition();owner.ModifyScreenPosition();}
                        else{owner.ModifyScreenPosition();nativeSystem.ModifyScreenPosition();}
                        MaterialClock(++tick);owner.PostUpdateEverything();
                    }
                    Equal(true,EnqueueLibraryForCheck(data,"native-normal:"+nativeFirst,frame,true),"native positive cue");
                    var normal=(Luminance.Core.Graphics.ScreenShakeSystem.ShakeInfo)roster[0]!;
                    Visit();Equal(5.5f,normal.ShakeStrength,"real native dissipation, either hook order");
                    Equal(1,LibraryOwnerQueue().Count,"active native cue stays owned");
                    for(int i=1;i<12;i++)Visit();
                    Equal(0f,normal.ShakeStrength,"native normal lifetime ends");
                    Equal(0,LibraryOwnerQueue().Count,"normal native expiry retires owner");
                    roster.Clear();
                    Equal(true,EnqueueLibraryForCheck(data,"native-canceled:"+nativeFirst,frame,true),"positive cancellation control");
                    var canceled=(Luminance.Core.Graphics.ScreenShakeSystem.ShakeInfo)roster[0]!;
                    Luminance.Core.Graphics.ScreenShakeSystem.SetUniversalRumble(7,0,Vector2.UnitX,0.5f);
                    Visit();Equal(0,roster.Count,"real universal rumble clears native roster");
                    Equal(5.5f,canceled.ShakeStrength,"library removes positive handle without zeroing it");
                    Visit();Visit();
                    Equal(0,LibraryOwnerQueue().Count,"native-canceled positive handle cannot retain shared record");
                    var rumble=(Luminance.Core.Graphics.ScreenShakeSystem.ShakeInfo)rumbleField.GetValue(null)!;
                    Equal(5.5f,rumble.ShakeStrength,"owned cleanup does not change universal rumble");
                    Luminance.Core.Graphics.ScreenShakeSystem.SetUniversalRumble(0,0,Vector2.UnitX,0.5f);
                    var foreign=Luminance.Core.Graphics.ScreenShakeSystem.StartShake(3,0,Vector2.UnitX,0.5f);
                    owner.OnWorldUnload();Equal(3f,foreign.ShakeStrength,"foreign native handle untouched");
                    roster.Clear();
                    Equal(true,EnqueueLibraryForCheck(data,"native-after-cancel:"+nativeFirst,frame,true),"new positive admission remains available");
                    owner.OnWorldUnload();
                }
            } finally {
                owner.OnWorldUnload();roster.Clear();foreach(var h in oldRoster)roster.Add(h);
                rumbleField.SetValue(null,oldRumble);configInstance.SetValue(null,oldConfig);
                Terraria.Main.player[local]=oldPlayer;Terraria.Main.screenPosition=oldScreen;Terraria.Main.rand=oldRandom;MaterialClock(originalTick);
            }
        });
    }

    private static void ExplicitLuminanceCueUsesExactCapturedParametersAndBudget()
    {
        WithLighting((config,_)=>{
            var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;int local=Terraria.Main.myPlayer;
            var oldPlayer=Terraria.Main.player[local];var oldMode=Terraria.Main.netMode;
            var shakeType=typeof(Luminance.Core.Graphics.ScreenShakeSystem);
            var native=(IList)shakeType.GetField("shakes",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
            var previous=native.Cast<object>().ToArray();native.Clear();
            var option=config.GetType().GetField("EnableLuminanceScreenShakeBackend")
                ?? throw new InvalidOperationException("new client shake option missing");
            try {
                LibraryInvoke("LoadLibrary");system.OnWorldUnload();Terraria.Main.player[local]=new Player{active=true,whoAmI=local,Center=Vector2.Zero};
                Equal(true,(bool)option.GetValue(config)!,"new client option defaults enabled");
                var data=LibraryData(true);var slot=data.VfxManifest.Slots[0];var frame=new VfxSourceFrame(Vector2.Zero,Vector2.UnitY,Vector2.Zero);
                slot.StartTick=2;var allowance=new MaterialEventAllowance(1);
                Equal(true,EnqueueLibraryForCheck(data,"shake",frame,true,allowance),"cue queues on existing event-relative delayed owner");
                Equal(0,native.Count,"no early Luminance call");
                MaterialClock(tick+1);system.PostUpdateEverything();Equal(0,native.Count,"waits exact delay");
                MaterialClock(tick+2);system.PostUpdateEverything();Equal(1,native.Count,"one exact native StartShakeAtPoint handle");
                var handle=(Luminance.Core.Graphics.ScreenShakeSystem.ShakeInfo)native[0]!;
                Equal(6f,handle.ShakeStrength,"authored pixel strength at taper start");Equal(0.25f,handle.AngularVariance,"authored angular variance");
                Equal(Vector2.UnitY,handle.BaseDirection,"captured forward rotates authored local direction");
                Equal(0.5f,handle.ShakeStrengthDissipationIncrement,"authored per-render-frame dissipation");Equal(0,allowance.Remaining,"one handle costs one shared event instance");
                system.PostUpdateEverything();Equal(1,native.Count,"same world tick cannot start twice");
                MaterialClock(tick+3);system.PostUpdateEverything();Equal(1,LibraryOwnerQueue().Count,"native handle stays owned until native dissipation, not neutral duration=3");
                option.SetValue(config,false);MaterialClock(tick+4);system.PostUpdateEverything();
                Equal(0f,handle.ShakeStrength,"disabled option cancels only owned native handle through all-client update");
                Equal(0,LibraryOwnerQueue().Count,"disabled handle retires without Draw");
                Equal(false,EnqueueLibraryForCheck(data,"disabled",frame),"disabled new cue is silent, not old sound fallback");
                option.SetValue(config,true);slot.StartTick=0;
                data.VfxManifest.Budget.MaxParticlesPerTick=0;
                Equal(false,EnqueueLibraryForCheck(data,"zero-budget",frame),"cue zero tick budget refuses before allocation");
                data.VfxManifest.Budget.MaxParticlesPerTick=1;
                Equal(true,EnqueueLibraryForCheck(data,"limited",frame),"first handle spends exact source budget");
                Equal(true,EnqueueLibraryForCheck(data,"limited",frame),"second queue attempt is presentation-only");
                Equal(2,native.Count,"second same-tick attempt cannot create native handle");
                var second=(Luminance.Core.Graphics.ScreenShakeSystem.ShakeInfo)native[1]!;
                second.ShakeStrength=0;MaterialClock(tick+5);system.PostUpdateEverything();
                Equal(0,LibraryOwnerQueue().Count,"native zero-strength expiry and refused queue are retired without Draw");
                var foreign=Luminance.Core.Graphics.ScreenShakeSystem.StartShake(2);
                system.OnWorldUnload();Equal(2f,foreign.ShakeStrength,"world clear never cancels foreign library users");
                var zero=LibraryManifestWire(true);zero["slots"]![0]!["screenShake"]!["strengthPx"]=0;
                data.VfxManifest=VfxManifestSpec.FromJson(zero.ToJsonString());
                Equal(false,EnqueueLibraryForCheck(data,"zero-strength",frame),"explicit zero cue never starts a native handle");
                data.VfxManifest=ParseLibraryManifest(true);Terraria.Main.netMode=Terraria.ID.NetmodeID.Server;
                Equal(false,EnqueueLibraryForCheck(data,"server",frame),"server cue remains suppressed");
            }finally{
                // Only our handles are zeroed/retired by world clear; foreign native
                // handles are restored without global shake-list mutation in product.
                system.OnWorldUnload();native.Clear();foreach(var handle in previous)native.Add(handle);
                Terraria.Main.player[local]=oldPlayer;Terraria.Main.netMode=oldMode;MaterialClock(tick);
            }
        });
    }
}
