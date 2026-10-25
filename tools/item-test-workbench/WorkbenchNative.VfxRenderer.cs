using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using ReLogic.Content.Sources;
using Terraria;
using Terraria.ModLoader;
using ParticleLibrary.Core.V3;
using InfiniCrafterLocal.Common.VFX;

// Executes original resource loaders, VFX update, and both original draw layers. No particle model lives here.
internal sealed class WNativeVfxRenderer : IDisposable
{
    const BindingFlags All=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
    sealed class ResourceMod(string root):Mod {
        public override string Name=>"ParticleLibrary";
        public override IContentSource CreateDefaultContentSource()=>new FileSystemContentSource(root);
    }
    readonly WorkbenchGraphicsContext graphics;
    readonly string framesDir,contentRoot;
    readonly int width,height;
    readonly bool capture,drawNativeDust;
    readonly Vector2 camera;
    readonly float zoom;
    readonly Game game;
    readonly object? oldServices,oldReaders;
    readonly GraphicsDeviceManager oldGraphics;
    readonly SpriteBatch oldBatch;
    readonly Terraria.Graphics.SpriteViewMatrix oldView;
    readonly int oldWidth,oldHeight;
    readonly Vector2 oldCamera;
    readonly IDictionary<string,Mod> registry;
    readonly ResourceMod mod;
    readonly ParticleLibrary.ParticleLibrary actualMod;
    readonly ParticleManagerV3 particleManager;
    readonly InfiniDetachedVfxSystem system=new();
    readonly SpriteBatch batch;
    readonly RenderTarget2D target;
    WNativeArtwork? artwork;WNativeTrainingDummy? trainingDummy;
    public void SetTrainingDummy(WNativeTrainingDummy value){trainingDummy=value;Report["trainingDummy"]=value.Report.DeepClone();Report["scope"]="Original native training dummy tile layer, generated projectile PreDraw/PostDraw and detached VFX, then ordinary native player/held layers; neutral background, no solid terrain/world scene";Report["trainingDummyArtworkRendered"]=false;Report["unrenderedArtwork"]=new JsonArray("Solid terrain/world artwork and other NPCs","native dust sprites");Report["passOrder"]=new JsonArray("TileDrawing non-solid dummy object","InfiniDetachedVfxSystem.DrawProjectiles wrapper / original generated projectile PreDraw/PostDraw","PlayerRenderer.DrawPlayers ordinary unlocked player","Inventory preview (explicit diagnostic UI)");}
    public void SetArtwork(WNativeArtwork value) {
        artwork=value;
        Report["artwork"]=value.Report;
        Report["scope"]="Original authored item/projectile PNG draw cores plus original detached VFX layers on neutral background; no Terraria world/player/NPC sprites";
        Report["artworkDrawEnabled"]=capture||drawNativeDust;Report["itemArtworkRendered"]=false;Report["projectileArtworkRendered"]=false;
        Report["partialProjectileHook"]=true;
        Report["fullProjectilePreDrawExecuted"]=false;
        Report["unavailableDrawBranch"]="Full GeneratedProjectile.PreDraw immediate VFX branch requires genuine Terraria Content/Images/MagicPixel.xnb, unavailable; admitted manifests contain only detached libraryParticle and unvalidated soundCue";
        Report["unrenderedArtwork"]=new JsonArray("Terraria world/player/NPC artwork","native dust sprites");
        Report["lighting"]=new JsonObject{["backend"]="Original Lighting.LightTiles",["gameMenu"]=false,["mapEnabled"]=false,["pointLightTileX"]=50,["pointLightTileY"]=45,["pointLightRgb"]=new JsonArray(1,1,1),["warmupNativePhases"]=4,["nativePhasesPerTick"]=1,["drawAndNoDrawIdenticalUpdate"]=true,["nativeDustUpdatePerTick"]=true};
        Report["originalDrawEntryPoints"]=new JsonArray("GeneratedHeldItemDrawLayer.GetDefaultVisibility/Draw","GeneratedItem.PreDrawInInventory","GeneratedProjectile.DrawAuthoredEntityVisual","InfiniDetachedVfxSystem.DrawProjectiles (original budget/layer wrapper)");
        if(value.NativePlayerEnabled){Report["scope"]="Original native PlayerRenderer with original generated held layer once, full generated projectile PreDraw/PostDraw and detached VFX; neutral background, no Terraria tiles/NPC sprites";Report["partialProjectileHook"]=false;Report["fullProjectilePreDrawEnabled"]=true;Report["fullProjectilePreDrawExecuted"]=false;Report["unavailableDrawBranch"]=null;Report["unrenderedArtwork"]=new JsonArray("Terraria tile/NPC/world artwork","native dust sprites");Report["originalDrawEntryPoints"]=value.Report["entrypoints"]!.DeepClone();Report["playerArtworkRendered"]=false;Report["passOrder"]=new JsonArray("InfiniDetachedVfxSystem.DrawProjectiles wrapper / original generated projectile PreDraw/PostDraw","PlayerRenderer.DrawPlayers ordinary unlocked player","Inventory preview (explicit diagnostic UI)");Report["unsupportedDrawPasses"]=new JsonArray("Locked-to-tile players before NPCs","Over-player/over-wire/hidden projectile passes","Full terrain/world scene and native dust sprites");}

    }
    readonly AssetReaderCollection readers;
    readonly JsonArray frames=new();
    readonly JsonArray snapshots=new();
    bool disposed;
    public JsonObject Report { get; }
    public WNativeVfxRenderer(WorkbenchGraphicsContext graphics,JsonObject settings,string absoluteFramesDir)
    {
        this.graphics=graphics;framesDir=Path.GetFullPath(absoluteFramesDir);
        foreach(string key in settings.Select(x=>x.Key)) if(key is not ("capture" or "width" or "height" or "cameraX" or "cameraY" or "zoom" or "drawArtwork" or "artworkFiles" or "drawPlayer" or "playerAssetRoot" or "dummyAssetRoot" or "drawNativeDust"))throw new ArgumentException("Unknown nativeRender setting: "+key);
        width=settings["width"]?.GetValue<int>()??512;height=settings["height"]?.GetValue<int>()??512;
        drawNativeDust=settings["drawNativeDust"]?.GetValue<bool>()??false;if(drawNativeDust && !(settings["drawPlayer"]?.GetValue<bool>()??false))throw new ArgumentException("drawNativeDust requires drawPlayer=true and genuine loaded Dust texture");capture=settings["capture"]?.GetValue<bool>()??true;zoom=settings["zoom"]?.GetValue<float>()??1;
        camera=new Vector2(settings["cameraX"]?.GetValue<float>()??0,settings["cameraY"]?.GetValue<float>()??0);
        if(width<64||width>1024||height<64||height>1024||!float.IsFinite(zoom)||zoom<=0||zoom>16||!float.IsFinite(camera.X)||!float.IsFinite(camera.Y))throw new ArgumentException("Native render requires width/height64..1024, finite camera and zoom(0,16]");
        string source=Environment.GetEnvironmentVariable("INFINI_PARTICLE_ASSET_DIR")??throw new InvalidOperationException("Set INFINI_PARTICLE_ASSET_DIR to the verified ParticleLibrary resource directory produced by fetch_vfx_assets.py");
        string star=Path.Combine(source,"Assets/Textures/Star.png"),effect=Path.Combine(source,"Assets/Effects/InstancedParticle.xnb");
        if(!File.Exists(star)||!File.Exists(effect))throw new FileNotFoundException("Original ParticleLibrary Star.png and InstancedParticle.xnb required; set INFINI_PARTICLE_ASSET_DIR");
        contentRoot=Directory.CreateTempSubdirectory("icl-vfx-content-").FullName;
        foreach(string file in Directory.EnumerateFiles(Path.Combine(source,"Assets"),"*",SearchOption.AllDirectories).Where(p=>p.EndsWith(".png",StringComparison.OrdinalIgnoreCase)||p.EndsWith(".xnb",StringComparison.OrdinalIgnoreCase))) {
            string destination=Path.Combine(contentRoot,Path.GetRelativePath(source,file));Directory.CreateDirectory(Path.GetDirectoryName(destination)!);File.Copy(file,destination);
        }
        game=(Game)typeof(WorkbenchGraphicsContext).GetField("game",All)!.GetValue(graphics)!;
        oldServices=typeof(Game).GetField("<Services>k__BackingField",All)!.GetValue(Main.instance);
        oldGraphics=Main.graphics;oldBatch=Main.spriteBatch;oldView=Main.GameViewMatrix;
        oldWidth=Main.screenWidth;oldHeight=Main.screenHeight;oldCamera=Main.screenPosition;
        Main.graphics=(GraphicsDeviceManager)typeof(WorkbenchGraphicsContext).GetField("manager",All)!.GetValue(graphics)!;
        typeof(Game).GetField("<Services>k__BackingField",All)!.SetValue(Main.instance,game.Services);
        readers=new AssetReaderCollection();readers.RegisterReader(new PngReader(graphics.Device),".png");readers.RegisterReader(new XnbReader(game.Services),".xnb");
        oldReaders=game.Services.GetService(typeof(AssetReaderCollection));if(oldReaders is not null)game.Services.RemoveService(typeof(AssetReaderCollection));game.Services.AddService(typeof(AssetReaderCollection),readers);
        registry=(IDictionary<string,Mod>)typeof(ModLoader).GetField("modsByName",All)!.GetValue(null)!;
        if(registry.ContainsKey("ParticleLibrary"))throw new InvalidOperationException("ParticleLibrary already registered; isolated renderer refuses to overwrite an existing mod");
        mod=new ResourceMod(contentRoot);typeof(Mod).GetProperty("Logger",All)!.SetValue(mod,log4net.LogManager.GetLogger("WorkbenchParticleLibrary"));
        typeof(Mod).GetMethod("PrepareAssets",All)!.Invoke(mod,null);registry.Add(mod.Name,mod);
        bool oldDedicated=Main.dedServ;Main.dedServ=false;
        try {
            var config=new ParticleLibrary.ParticleLibraryConfig();typeof(Terraria.ModLoader.Config.ModConfig).GetProperty("Mod",All)!.SetValue(config,mod);typeof(Terraria.ModLoader.Config.ConfigManager).GetMethod("Add",All)!.Invoke(null,new object[]{config});
            actualMod=new ParticleLibrary.ParticleLibrary();typeof(Mod).GetProperty("Logger",All)!.SetValue(actualMod,log4net.LogManager.GetLogger("WorkbenchParticleLibrary"));actualMod.Load();
            particleManager=new ParticleManagerV3();typeof(ModType).GetProperty("Mod",All)!.SetValue(particleManager,mod);particleManager.Load();
            Invoke("LoadLibrary");Invoke("EnsureLibraryReady");typeof(Main).GetMethod("ConsumeAllMainThreadActions",All)!.Invoke(null,null);
            if(!(bool)Invoke("EnsureLibraryReady")!)throw new InvalidOperationException("Original ParticleLibrary readiness did not succeed after native main-thread queue");
        } finally {Main.dedServ=oldDedicated;}
        batch=new SpriteBatch(graphics.Device);Main.spriteBatch=batch;target=new RenderTarget2D(graphics.Device,width,height);
        if(capture)Directory.CreateDirectory(framesDir);
        Report=new JsonObject{["backend"]="original_mod_draw_layers",["backendDescription"]="Original InfiniDetachedVfxSystem draw layers / FNA3D software OpenGL",["scope"]="VFX-only original mod layers on neutral black background; no Terraria scene artwork",["capture"]=capture,["pngExportEnabled"]=capture,["gpuRenderLifecycleEnabled"]=capture||drawNativeDust,["gpuRenderLifecycleExecuted"]=false,["nativeDustDrawEnabled"]=drawNativeDust,["nativeDustDrawExecuted"]=false,["soundValidated"]=false,["itemArtworkRendered"]=false,["projectileArtworkRendered"]=false,["worldRendered"]=false,["unrenderedArtwork"]=new JsonArray("item artwork","projectile artwork","Terraria world/player/NPC artwork"),["missingVfxAssets"]=new JsonArray(),["resourceReady"]=true,["originalParticleLibraryEffect"]=ParticleManagerV3.InstancedParticleEffect is not null,["libraryBuffers"]=(GetStatic("LibraryBuffers") as Array)?.Length??0,["starSha256"]=Hash(File.ReadAllBytes(Path.Combine(contentRoot,"Assets/Textures/Star.png"))),["effectSha256"]=Hash(File.ReadAllBytes(Path.Combine(contentRoot,"Assets/Effects/InstancedParticle.xnb"))),["loadedAssetSha256"]=JsonSerializer.SerializeToNode(Directory.EnumerateFiles(contentRoot,"*",SearchOption.AllDirectories).OrderBy(p=>p).ToDictionary(p=>Path.GetRelativePath(contentRoot,p),p=>Hash(File.ReadAllBytes(p)))),["particleLibraryAssemblySha256"]=Hash(File.ReadAllBytes(typeof(ParticleManagerV3).Assembly.Location)),["graphics"]=graphics.Provenance.DeepClone(),["width"]=width,["height"]=height,["cameraX"]=camera.X,["cameraY"]=camera.Y,["zoom"]=zoom,["frames"]=frames,["snapshots"]=snapshots};
    }
    public void Step(int tick)
    {
        bool oldDedicated=Main.dedServ;Main.dedServ=false;
        try {
            string beforeUpdate=Rng();system.PostUpdateEverything();string afterUpdate=Rng();
            JsonObject snapshot=Snapshot(tick);snapshot["mainRngBeforeUpdate"]=beforeUpdate;snapshot["mainRngAfterUpdate"]=afterUpdate;snapshots.Add(snapshot);
            if(!capture&&!drawNativeDust)return;
            if(drawNativeDust){snapshot["nativeDustBeforeDraw"]=DustState();ConfigureDustReport();}
            string beforeDraw=Rng();
            int savedWidth=Main.screenWidth,savedHeight=Main.screenHeight;Vector2 savedCamera=Main.screenPosition;var savedView=Main.GameViewMatrix;
            graphics.Device.SetRenderTarget(target);
            try {Main.screenWidth=width;Main.screenHeight=height;Main.screenPosition=camera;Main.GameViewMatrix=new Terraria.Graphics.SpriteViewMatrix(graphics.Device){Zoom=new Vector2(zoom)};graphics.Device.Clear(Color.Black);artwork?.BeginFrame();trainingDummy?.Draw();if(artwork?.NativePlayerEnabled!=true)artwork?.DrawHeld();if(artwork is not null) Invoke("DrawProjectiles",new Terraria.On_Main.orig_DrawProjectiles(_=>artwork.DrawProjectiles()),Main.instance);else {Invoke("BeginDrawBudgetFrame");Invoke("DrawLayer","BeforeProjectiles");Invoke("DrawLayer","AfterProjectiles");}if(artwork?.NativePlayerEnabled==true)artwork.DrawHeld();if(drawNativeDust)typeof(Main).GetMethod("DrawDust",All)!.Invoke(Main.instance,null);artwork?.DrawInventory();}
            finally {graphics.Device.SetRenderTarget(null);Main.screenWidth=savedWidth;Main.screenHeight=savedHeight;Main.screenPosition=savedCamera;Main.GameViewMatrix=savedView;}
            string afterDraw=Rng();
            Report["gpuRenderLifecycleExecuted"]=true;
            if(artwork is not null){
                if((artwork.Frame["heldItemDrawCount"]?.GetValue<int>()??0)+(artwork.Frame["inventoryPreviewDrawCount"]?.GetValue<int>()??0)>0)Report["itemArtworkRendered"]=true;
                if((artwork.Frame["projectileDrawCount"]?.GetValue<int>()??0)>0){Report["projectileArtworkRendered"]=true;if(artwork.NativePlayerEnabled)Report["fullProjectilePreDrawExecuted"]=true;}
                if((artwork.Frame["playerRenderAllLayersCalls"]?.GetValue<int>()??0)>0)Report["playerArtworkRendered"]=true;
            }
            if(trainingDummy is not null)Report["trainingDummyArtworkRendered"]=true;
            if(drawNativeDust){snapshot["nativeDustAfterDraw"]=DustState();snapshot["mainRngBeforeDraw"]=beforeDraw;snapshot["mainRngAfterDraw"]=afterDraw;snapshot["nativeDustDrawExecuted"]=true;snapshot["nativeDrawCounters"]=artwork?.Frame.DeepClone();Report["nativeDustDrawExecuted"]=true;}
            if(!capture)return;var pixels=new Color[width*height];target.GetData(pixels);
            string path=Path.Combine(framesDir,$"{tick:000000}.png");using(var stream=File.Create(path))target.SaveAsPng(stream,width,height);
            var frame=new JsonObject{["tick"]=tick,["width"]=width,["height"]=height,["resourcesReady"]=true,["particles"]=snapshot["particleCount"]!.DeepClone(),["records"]=snapshot["materialRecordCount"]!.DeepClone(),["path"]=Path.GetFileName(framesDir)+"/"+Path.GetFileName(path),["sha256"]=Hash(File.ReadAllBytes(path)),["nonblackPixels"]=pixels.Count(p=>p.R!=0||p.G!=0||p.B!=0),["mainRngBeforeDraw"]=beforeDraw,["mainRngAfterDraw"]=afterDraw,["drawChangedMainRng"]=beforeDraw!=afterDraw};
            if(artwork is not null) foreach(var pair in artwork.Frame) frame[pair.Key]=pair.Value?.DeepClone();
            if(artwork is not null) {
                if(frame["heldItemDrawCount"]!.GetValue<int>()+frame["inventoryPreviewDrawCount"]!.GetValue<int>()>0) Report["itemArtworkRendered"]=true;
                if(frame["projectileDrawCount"]!.GetValue<int>()>0){Report["projectileArtworkRendered"]=true;if(artwork.NativePlayerEnabled)Report["fullProjectilePreDrawExecuted"]=true;}
                if((frame["playerRenderAllLayersCalls"]?.GetValue<int>()??0)>0)Report["playerArtworkRendered"]=true;
            }
            if(trainingDummy is not null){frame["trainingDummy"]=trainingDummy.Snapshot();frame["trainingDummyNativeDrawCalls"]=1;Report["trainingDummyArtworkRendered"]=true;}
            if(drawNativeDust){frame["nativeDustDrawExecuted"]=true;frame["nativeDustBeforeDraw"]=snapshot["nativeDustBeforeDraw"]!.DeepClone();frame["nativeDustAfterDraw"]=snapshot["nativeDustAfterDraw"]!.DeepClone();}
            frames.Add(frame);
        } finally {Main.dedServ=oldDedicated;}
    }
    void ConfigureDustReport(){
        Report["scope"]="Original native player/held, generated projectile PreDraw/PostDraw, detached VFX and Main.DrawDust on neutral background; optional actual training dummy tile layer, not complete Main.Draw/world";
        Report["nativeDustDrawEnabled"]=true;Report["pngExportEnabled"]=capture;Report["captureSemantics"]="Native GPU render lifecycle executes every tick; capture controls PNG encoding/export only in drawNativeDust mode";
        Report["nativeDustDrawEntryPoint"]="Original Main.DrawDust after ordinary player layer and before diagnostic inventory UI";
        Report["nativeDustStateMutation"]="Original DrawDust may deactivate offscreen or black dust; camera is part of the deterministic scene";
        Report["dustAssetAlphaScope"]="Pinned community Dust PNG loaded through genuine PngReader; full sheet has partial alpha and original extraction alpha semantics are not independently certified. No official-byte/pixel parity claim.";
        Report["unrenderedArtwork"]=new JsonArray(trainingDummy is null?"Terraria tile/NPC/world artwork":"Solid terrain/world artwork and other NPCs");
        Report["unsupportedDrawPasses"]=new JsonArray("Locked-to-tile players before NPCs","Over-player/over-wire/hidden projectile passes","Full terrain/world scene");
        Report["passOrder"]=trainingDummy is null?new JsonArray("Original projectile/VFX wrapper","Ordinary native player/held layers","Original Main.DrawDust","Diagnostic inventory UI"):new JsonArray("Native training dummy non-solid tiles","Original projectile/VFX wrapper","Ordinary native player/held layers","Original Main.DrawDust","Diagnostic inventory UI");
    }
    static JsonArray DustState()=>new JsonArray(Main.dust.Select((d,i)=>new{d,i}).Where(v=>v.d.active).Select(v=>(JsonNode?)new JsonObject{["slot"]=v.i,["type"]=v.d.type,["x"]=v.d.position.X,["y"]=v.d.position.Y,["vx"]=v.d.velocity.X,["vy"]=v.d.velocity.Y,["scale"]=v.d.scale,["alpha"]=v.d.alpha,["rotation"]=v.d.rotation,["fadeIn"]=v.d.fadeIn,["noGravity"]=v.d.noGravity,["noLight"]=v.d.noLight,["colorR"]=v.d.color.R,["colorG"]=v.d.color.G,["colorB"]=v.d.color.B,["colorA"]=v.d.color.A,["shaderType"]=v.d.shader?.GetType().FullName,["customDataType"]=v.d.customData?.GetType().FullName,["frameX"]=v.d.frame.X,["frameY"]=v.d.frame.Y,["frameWidth"]=v.d.frame.Width,["frameHeight"]=v.d.frame.Height}).ToArray());
    static object? Invoke(string name,params object[] args)=>typeof(InfiniDetachedVfxSystem).GetMethod(name,All)!.Invoke(null,args);
    static object? GetStatic(string name)=>typeof(InfiniDetachedVfxSystem).GetField(name,All)!.GetValue(null);
    static object? Field(object value,string name)=>value.GetType().GetField(name,All)?.GetValue(value)??value.GetType().GetProperty(name,All)?.GetValue(value);
    static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string Rng()=>Hash(System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(typeof(Terraria.Utilities.UnifiedRandom).GetFields(All).Where(f=>!f.IsStatic).OrderBy(f=>f.Name).ToDictionary(f=>f.Name,f=>f.GetValue(Main.rand)))));
    static JsonObject Snapshot(int tick)
    {
        var rows=new JsonArray();int total=0;
        foreach(object emission in (IEnumerable)GetStatic("MaterialEmissions")!) {
            object? library=Field(emission,"Library");object design=library is null?Field(emission,"Design")!:Field(library,"Design")!;
            var particles=(Array)(Field(library??emission,"Particles")??Array.Empty<object>());total+=particles.Length;var states=new JsonArray();
            foreach(object particle in particles) {var state=new JsonObject();foreach(string name in new[]{"Position","Velocity","Rotation","Scale","LifeTime","TimeLeft","Time","Duration","Depth","InitialScale","InitialColor","Opacity","Color"}) {object? value=Field(particle,name);if(value is not null)state[name]=JsonSerializer.SerializeToNode(value,value.GetType(),new JsonSerializerOptions{IncludeFields=true});}states.Add(state);}
            rows.Add(new JsonObject{["sourceKey"]=Field(emission,"SourceKey")?.ToString(),["renderer"]=library is null?"material":"libraryParticle",["started"]=(bool)Field(emission,"Started")!,["startTick"]=Convert.ToUInt64(Field(emission,"Start")),["dueTick"]=Convert.ToUInt64(Field(emission,"Due")),["integratedAge"]=Convert.ToInt32(Field(emission,"IntegratedAge")),["durationTicks"]=design is null?null:JsonValue.Create(Convert.ToInt32(Field(design,"Duration"))),["particleCount"]=particles.Length,["particles"]=states});
        }
        return new JsonObject{["tick"]=tick,["materialRecordCount"]=rows.Count,["particleCount"]=total,["records"]=rows};
    }
    public void Dispose()
    {
        if(disposed)return;disposed=true;bool oldDedicated=Main.dedServ;Main.dedServ=false;
        try {system.Unload();particleManager.Unload();actualMod.Unload();mod.Assets.Dispose();registry.Remove(mod.Name);
            foreach(var field in typeof(Terraria.ModLoader.Config.ConfigManager).GetFields(All))if(field.IsStatic&&field.GetValue(null) is IDictionary dictionary&&dictionary.Contains(mod))dictionary.Remove(mod);
        } finally {
            target.Dispose();batch.Dispose();game.Services.RemoveService(typeof(AssetReaderCollection));if(oldReaders is not null)game.Services.AddService(typeof(AssetReaderCollection),oldReaders);
            typeof(Game).GetField("<Services>k__BackingField",All)!.SetValue(Main.instance,oldServices);Main.graphics=oldGraphics;Main.spriteBatch=oldBatch;Main.GameViewMatrix=oldView;Main.screenWidth=oldWidth;Main.screenHeight=oldHeight;Main.screenPosition=oldCamera;Main.dedServ=oldDedicated;
            Directory.Delete(contentRoot,true);
        }
    }
}
