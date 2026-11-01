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
using InfiniCrafterLocal.Common.Models;

// Executes original resource loaders, VFX update, and both original draw layers. No particle model lives here.
internal sealed partial class WNativeVfxRenderer : IDisposable
{
    const BindingFlags All=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
    sealed class ResourceMod(string root,string name="ParticleLibrary"):Mod {
        public override string Name=>name;
        public override IContentSource CreateDefaultContentSource()=>new FileSystemContentSource(root);
    }
    readonly WorkbenchGraphicsContext graphics;
    readonly string framesDir,contentRoot;
    readonly int width,height;
    readonly bool capture,drawNativeDust,drawDroppedItems,drawVanillaProjectiles,drawProjectileVfx;
    WNativeActiveVfx? activeVfx;
    public void SetActiveVfx(WNativeActiveVfx value,bool proceduralOnly) {
        if(proceduralOnly!=drawProjectileVfx)throw new InvalidOperationException("Procedural VFX draw scope differs from nativeRender request");
        activeVfx=value;
        Report["activeProjectileVfxEnabled"]=true;
        Report["gpuRenderLifecycleEnabled"]=true;
        Report["captureSemantics"]="Native active projectile GPU draw runs every tick; capture controls PNG export only";
        Report["activeProjectileVfxScope"]=proceduralOnly?"Original InfiniVfxRuntime.Draw under/over passes with live GeneratedProjectile history and budget; authored sprites and player artwork explicitly unrendered":"Original GeneratedProjectile.PreDraw, including its authored sprite and under/over VFX passes";
        if(proceduralOnly){Report["scope"]="Original generated procedural projectile VFX, detached layers and optional native dust; authored item/projectile sprites and player/world artwork unrendered";Report["gpuRenderLifecycleEnabled"]=true;Report["captureSemantics"]="Native procedural GPU draw runs every tick; capture controls PNG export only";}
    }
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
    ResourceMod? luminanceResources;
    readonly ParticleLibrary.ParticleLibrary actualMod;
    readonly ParticleManagerV3 particleManager;
    readonly InfiniDetachedVfxSystem system=new();
    readonly SpriteBatch batch;
    readonly RenderTarget2D target;
    WNativeArtwork? artwork;WNativeTrainingDummy? trainingDummy;WNativeZombieRender? zombie;
    public void SetZombie(WNativeZombieRender value){zombie=value;Report["zombieAssets"]=value.Report.DeepClone();Report["zombieArtworkRendered"]=false;Report["gpuRenderLifecycleEnabled"]=true;Report["captureSemantics"]="Native zombie draw runs every tick; capture controls PNG export only";Report["scope"]="Original native controlled zombie DrawNPC and player/projectile layers on a neutral background; no full world or NPC AI parity";Report["unrenderedArtwork"]=new JsonArray("Terraria tile/world artwork and other NPCs",drawNativeDust?"No additional dust omission":"Native dust sprites");Report["originalDrawEntryPoints"]?.AsArray().Add(JsonValue.Create("Main.DrawNPC (controlled zombie)"));Report["passOrder"]?.AsArray().Insert(0,JsonValue.Create("Original controlled zombie Main.DrawNPC"));}
    public void SetTrainingDummy(WNativeTrainingDummy value){trainingDummy=value;Report["trainingDummy"]=value.Report.DeepClone();Report["scope"]="Original native training dummy tile layer, generated projectile PreDraw/PostDraw and detached VFX, then ordinary native player/held layers; neutral background, no solid terrain/world scene";Report["trainingDummyArtworkRendered"]=false;Report["unrenderedArtwork"]=new JsonArray("Solid terrain/world artwork and other NPCs","native dust sprites");Report["passOrder"]=new JsonArray("TileDrawing non-solid dummy object","InfiniDetachedVfxSystem.DrawProjectiles wrapper / original generated projectile PreDraw/PostDraw","PlayerRenderer.DrawPlayers ordinary unlocked player","Inventory preview (explicit diagnostic UI)");RefreshVanillaReport();}
    public void SetArtwork(WNativeArtwork value) {
        artwork=value;
        Report["artwork"]=value.Report;
        Report["scope"]="Original authored item/projectile PNG draw cores plus original detached VFX layers on neutral background; no Terraria world/player/NPC sprites";
        Report["artworkDrawEnabled"]=capture||drawNativeDust||drawVanillaProjectiles||activeVfx is not null;Report["itemArtworkRendered"]=false;Report["projectileArtworkRendered"]=false;
        Report["partialProjectileHook"]=true;
        Report["fullProjectilePreDrawExecuted"]=false;
        Report["unavailableDrawBranch"]="Full GeneratedProjectile.PreDraw immediate VFX branch requires genuine Terraria Content/Images/MagicPixel.xnb, unavailable; partial mode admits detached libraryParticle/material/impactSprite and unvalidated soundCue; primitive impactRing requires full native hooks";
        Report["unrenderedArtwork"]=new JsonArray("Terraria world/player/NPC artwork","native dust sprites");
        Report["originalDrawEntryPoints"]=new JsonArray("GeneratedHeldItemDrawLayer.GetDefaultVisibility/Draw","GeneratedItem.PreDrawInInventory","GeneratedProjectile.DrawAuthoredEntityVisual","InfiniDetachedVfxSystem.DrawProjectiles (original budget/layer wrapper)");
        if(value.NativePlayerEnabled){Report["scope"]=value.NativeVanillaEnabled?"Original native vanilla PlayerRenderer/item layer; original dust when enabled; native projectile simulation but projectile sprites not rendered":"Original native PlayerRenderer with original generated held layer once, full generated projectile PreDraw/PostDraw and detached VFX; neutral background, no Terraria tiles/NPC sprites";Report["partialProjectileHook"]=false;Report["fullProjectilePreDrawEnabled"]=!value.NativeVanillaEnabled;Report["fullProjectilePreDrawExecuted"]=false;Report["unavailableDrawBranch"]=null;Report["unrenderedArtwork"]=new JsonArray("Terraria tile/NPC/world artwork","native dust sprites");Report["originalDrawEntryPoints"]=value.Report["entrypoints"]?.DeepClone();Report["playerArtworkRendered"]=false;Report["passOrder"]=new JsonArray("InfiniDetachedVfxSystem.DrawProjectiles wrapper / original generated projectile PreDraw/PostDraw","PlayerRenderer.DrawPlayers ordinary unlocked player","Inventory preview (explicit diagnostic UI)");Report["unsupportedDrawPasses"]=new JsonArray("Locked-to-tile players before NPCs","Over-player/over-wire/hidden projectile passes","Full terrain/world scene and native dust sprites");}
        RefreshVanillaReport();
    }
    void RefreshVanillaReport()
    {
        if(artwork?.NativeVanillaEnabled!=true)return;
        Report["scope"]="Original native vanilla player/held-item"+(drawVanillaProjectiles?", Main.DrawProj":"")+(drawNativeDust?", Main.DrawDust":"")+(trainingDummy is not null?", training dummy tile layer":zombie is not null?", controlled zombie Main.DrawNPC":"")+"; controlled neutral background, not full Main.Draw/world";
        Report["vanillaProjectileDrawEnabled"]=drawVanillaProjectiles;
        if(Report["vanillaProjectileDrawExecuted"] is null)Report["vanillaProjectileDrawExecuted"]=false;
        Report["unrenderedArtwork"]=new JsonArray(drawVanillaProjectiles?"No additional projectile omission":"Native projectile sprites (simulation/hits still execute)",trainingDummy is not null?"Solid terrain/world artwork and other NPCs":zombie is not null?"Terraria tile/world artwork and other NPCs":"Terraria tile/NPC/world artwork");
        if(!drawNativeDust)Report["unrenderedArtwork"]!.AsArray().Add(JsonValue.Create("Native dust sprites"));
        Report["originalDrawEntryPoints"]=artwork.Report["entrypoints"]?.DeepClone();
        if(zombie is not null)Report["originalDrawEntryPoints"]?.AsArray().Add(JsonValue.Create("Main.DrawNPC (controlled zombie)"));
        Report["unsupportedDrawPasses"]=new JsonArray("Locked-to-tile players before NPCs","Over-player/over-wire/hidden projectile passes","Full terrain/world scene");
    }
    readonly AssetReaderCollection readers;
    readonly JsonArray frames=new();
    readonly JsonArray snapshots=new();
    bool disposed;
    public JsonObject Report { get; }
    public WNativeVfxRenderer(WorkbenchGraphicsContext graphics,JsonObject settings,string absoluteFramesDir,GeneratedItemData? data)
    {
        string[] libraryTexturePaths=SelectedLibraryTexturePaths(data);
        string[] luminancePaths=libraryTexturePaths.Where(p=>p.StartsWith("Luminance/",StringComparison.Ordinal)).ToArray();
        string? luminanceRoot=Environment.GetEnvironmentVariable("INFINI_LUMINANCE_ASSET_DIR");
        var luminanceHashes=InspectLuminanceResources(luminancePaths,luminanceRoot);
        this.graphics=graphics;framesDir=Path.GetFullPath(absoluteFramesDir);
        foreach(string key in settings.Select(x=>x.Key)) if(key is not ("capture" or "width" or "height" or "cameraX" or "cameraY" or "zoom" or "drawArtwork" or "artworkFiles" or "drawPlayer" or "playerAssetRoot" or "dummyAssetRoot" or "drawNativeDust" or "lightingMode" or "drawPlacedBodies" or "drawDroppedItems" or "drawVanillaProjectiles" or "drawProjectileVfx" or "drawZombie"))throw new ArgumentException("Unknown nativeRender setting: "+key);
        ConfigureScene(settings);drawVanillaProjectiles=settings["drawVanillaProjectiles"]?.GetValue<bool>()??false;drawDroppedItems=settings["drawDroppedItems"]?.GetValue<bool>()??false; if(drawDroppedItems && !(settings["drawArtwork"]?.GetValue<bool>()??false))throw new ArgumentException("drawDroppedItems requires drawArtwork");
        width=settings["width"]?.GetValue<int>()??512;height=settings["height"]?.GetValue<int>()??512;
        drawProjectileVfx=settings["drawProjectileVfx"]?.GetValue<bool>()??false;
        drawNativeDust=settings["drawNativeDust"]?.GetValue<bool>()??false;if(drawNativeDust && !(settings["drawPlayer"]?.GetValue<bool>()??false) && !drawProjectileVfx)throw new ArgumentException("drawNativeDust requires drawPlayer or drawProjectileVfx and genuine loaded Dust texture");capture=settings["capture"]?.GetValue<bool>()??true;zoom=settings["zoom"]?.GetValue<float>()??1;
        camera=new Vector2(settings["cameraX"]?.GetValue<float>()??0,settings["cameraY"]?.GetValue<float>()??0);
        if(width<64||width>1024||height<64||height>1024||!float.IsFinite(zoom)||zoom<=0||zoom>16||!float.IsFinite(camera.X)||!float.IsFinite(camera.Y))throw new ArgumentException("Native render requires width/height64..1024, finite camera and zoom(0,16]");
        string source=Environment.GetEnvironmentVariable("INFINI_PARTICLE_ASSET_DIR")??throw new InvalidOperationException("Set INFINI_PARTICLE_ASSET_DIR to the verified ParticleLibrary resource directory produced by fetch_vfx_assets.py");
        string star=Path.Combine(source,"Assets/Textures/Star.png"),effect=Path.Combine(source,"Assets/Effects/InstancedParticle.xnb");
        if(!File.Exists(star)||!File.Exists(effect))throw new FileNotFoundException("Original ParticleLibrary Star.png and InstancedParticle.xnb required; set INFINI_PARTICLE_ASSET_DIR");
        contentRoot=Directory.CreateTempSubdirectory("icl-vfx-content-").FullName;
        foreach(string file in Directory.EnumerateFiles(Path.Combine(source,"Assets"),"*",SearchOption.AllDirectories).Where(p=>p.EndsWith(".png",StringComparison.OrdinalIgnoreCase)||p.EndsWith(".xnb",StringComparison.OrdinalIgnoreCase))) {
            string destination=Path.Combine(contentRoot,Path.GetRelativePath(source,file));Directory.CreateDirectory(Path.GetDirectoryName(destination)!);File.Copy(file,destination);
        }
        if(luminancePaths.Length>0) {
            // Freeze the exact selected bytes for the native resource loader;
            // the source can otherwise change between receipt and GPU load.
            string root=Path.Combine(contentRoot,"Luminance");
            foreach(string path in luminancePaths) {
                string relative=path.Substring("Luminance/".Length).Replace('/',Path.DirectorySeparatorChar)+".png";
                byte[] bytes=File.ReadAllBytes(Path.Combine(luminanceRoot!,relative));
                if(Hash(bytes)!=luminanceHashes[path])throw new InvalidOperationException("Luminance texture changed during preparation: "+path);
                string targetPath=Path.Combine(root,relative);
                Directory.CreateDirectory(Path.GetDirectoryName(targetPath)!);File.WriteAllBytes(targetPath,bytes);
            }
        }
        registry=(IDictionary<string,Mod>)typeof(ModLoader).GetField("modsByName",All)!.GetValue(null)!;
        if(registry.ContainsKey("ParticleLibrary"))throw new InvalidOperationException("ParticleLibrary already registered; isolated renderer refuses to overwrite an existing mod");
        if(luminancePaths.Length>0 && registry.ContainsKey("Luminance"))throw new InvalidOperationException("Luminance already registered; isolated renderer refuses to overwrite an existing mod");
        game=(Game)typeof(WorkbenchGraphicsContext).GetField("game",All)!.GetValue(graphics)!;
        oldServices=typeof(Game).GetField("<Services>k__BackingField",All)!.GetValue(Main.instance);
        oldGraphics=Main.graphics;oldBatch=Main.spriteBatch;oldView=Main.GameViewMatrix;
        oldWidth=Main.screenWidth;oldHeight=Main.screenHeight;oldCamera=Main.screenPosition;
        Main.graphics=(GraphicsDeviceManager)typeof(WorkbenchGraphicsContext).GetField("manager",All)!.GetValue(graphics)!;
        typeof(Game).GetField("<Services>k__BackingField",All)!.SetValue(Main.instance,game.Services);
        readers=new AssetReaderCollection();readers.RegisterReader(new PngReader(graphics.Device),".png");readers.RegisterReader(new XnbReader(game.Services),".xnb");
        oldReaders=game.Services.GetService(typeof(AssetReaderCollection));if(oldReaders is not null)game.Services.RemoveService(typeof(AssetReaderCollection));game.Services.AddService(typeof(AssetReaderCollection),readers);
        mod=new ResourceMod(contentRoot);typeof(Mod).GetProperty("Logger",All)!.SetValue(mod,log4net.LogManager.GetLogger("WorkbenchParticleLibrary"));
        typeof(Mod).GetMethod("PrepareAssets",All)!.Invoke(mod,null);registry.Add(mod.Name,mod);
        // Only register a resource source when the authored item selects a
        // Luminance texture. This is not Luminance's mod lifecycle or gameplay.
        if(luminancePaths.Length>0) {
            string root=Path.Combine(contentRoot,"Luminance");
            luminanceResources=new ResourceMod(root,"Luminance");
            typeof(Mod).GetProperty("Logger",All)!.SetValue(luminanceResources,log4net.LogManager.GetLogger("WorkbenchLuminanceResources"));
            typeof(Mod).GetMethod("PrepareAssets",All)!.Invoke(luminanceResources,null);
            try {registry.Add(luminanceResources.Name,luminanceResources);}
            catch {luminanceResources.Assets.Dispose();luminanceResources=null;throw;}
        }
        bool oldDedicated=Main.dedServ;Main.dedServ=false;
        try {
            var config=new ParticleLibrary.ParticleLibraryConfig();typeof(Terraria.ModLoader.Config.ModConfig).GetProperty("Mod",All)!.SetValue(config,mod);typeof(Terraria.ModLoader.Config.ConfigManager).GetMethod("Add",All)!.Invoke(null,new object[]{config});
            actualMod=new ParticleLibrary.ParticleLibrary();typeof(Mod).GetProperty("Logger",All)!.SetValue(actualMod,log4net.LogManager.GetLogger("WorkbenchParticleLibrary"));actualMod.Load();
            particleManager=new ParticleManagerV3();typeof(ModType).GetProperty("Mod",All)!.SetValue(particleManager,mod);particleManager.Load();
            Invoke("LoadLibrary");
            // ParticleManager's effect load is itself queued. Production readiness
            // additionally serializes texture requests through one queued owner.
            typeof(Main).GetMethod("ConsumeAllMainThreadActions",All)!.Invoke(null,null);
            if(ParticleManagerV3.InstancedParticleEffect is null)throw new InvalidOperationException("Original ParticleLibrary effect did not load after native main-thread queue");
            PrewarmLibraryTextures(libraryTexturePaths,path=>(bool)Invoke("EnsureLibraryReady",path)!,
                ()=>typeof(Main).GetMethod("ConsumeAllMainThreadActions",All)!.Invoke(null,null));
        } catch {
            if(luminanceResources is not null){registry.Remove(luminanceResources.Name);luminanceResources.Assets.Dispose();luminanceResources=null;}
            throw;
        } finally {Main.dedServ=oldDedicated;}
        batch=new SpriteBatch(graphics.Device);Main.spriteBatch=batch;target=new RenderTarget2D(graphics.Device,width,height);
        if(capture)Directory.CreateDirectory(framesDir);
        Report=new JsonObject{["backend"]="original_mod_draw_layers",["backendDescription"]="Original InfiniDetachedVfxSystem draw layers / FNA3D software OpenGL",["scope"]="VFX-only original mod layers on neutral black background; no Terraria scene artwork",["capture"]=capture,["pngExportEnabled"]=capture,["gpuRenderLifecycleEnabled"]=capture||drawNativeDust||drawVanillaProjectiles,["gpuRenderLifecycleExecuted"]=false,["nativeDustDrawEnabled"]=drawNativeDust,["nativeDustDrawExecuted"]=false,["soundValidated"]=false,["itemArtworkRendered"]=false,["projectileArtworkRendered"]=false,["worldRendered"]=false,["unrenderedArtwork"]=new JsonArray("item artwork","projectile artwork","Terraria world/player/NPC artwork"),["missingVfxAssets"]=new JsonArray(),["resourceReady"]=true,["originalParticleLibraryEffect"]=ParticleManagerV3.InstancedParticleEffect is not null,["libraryBuffers"]=(GetStatic("LibraryBuffers") as Array)?.Length??0,["starSha256"]=Hash(File.ReadAllBytes(Path.Combine(contentRoot,"Assets/Textures/Star.png"))),["effectSha256"]=Hash(File.ReadAllBytes(Path.Combine(contentRoot,"Assets/Effects/InstancedParticle.xnb"))),["loadedAssetSha256"]=JsonSerializer.SerializeToNode(Directory.EnumerateFiles(contentRoot,"*",SearchOption.AllDirectories).OrderBy(p=>p).ToDictionary(p=>Path.GetRelativePath(contentRoot,p),p=>Hash(File.ReadAllBytes(p)))),["particleLibraryAssemblySha256"]=Hash(File.ReadAllBytes(typeof(ParticleManagerV3).Assembly.Location)),["graphics"]=graphics.Provenance.DeepClone(),["width"]=width,["height"]=height,["cameraX"]=camera.X,["cameraY"]=camera.Y,["zoom"]=zoom,["frames"]=frames,["snapshots"]=snapshots};
        Report["readyLibraryTexturePaths"]=JsonSerializer.SerializeToNode(libraryTexturePaths);
        if(luminanceResources is not null)Report["luminanceResources"]=new JsonObject {
            ["scope"]="Resource-only registration; Luminance Load hooks and gameplay are not executed",
            ["selectedTextureSha256"]=JsonSerializer.SerializeToNode(luminanceHashes)
        };
    }
    // Resolve exactly the particle textures selected by this item, through the
    // production registry. No synthetic Star selection for empty/vanilla scenes.
    internal static string[] SelectedLibraryTexturePaths(GeneratedItemData? data)
    {
        var resolve=typeof(InfiniDetachedVfxSystem).Assembly.GetType("InfiniCrafterLocal.Common.VFX.VfxLibraryTextures",throwOnError:true)!.GetMethod("TryGetPath",All)!;
        return (data?.VfxManifest.Slots??Array.Empty<VfxSlotSpec>()).Where(s=>s.Particle is not null)
            .Select(s=>{
                object?[] args={s.Particle!.TextureId,null};
                if(!(bool)resolve.Invoke(null,args)!)throw new NotSupportedException("Unknown selected particle texture: "+s.Particle.TextureId);
                return (string)args[1]!;
            }).Distinct(StringComparer.Ordinal).ToArray();
    }
    // The paths come only from the production texture registry. Check each
    // selected file up front and record its bytes; do not infer a replacement.
    internal static Dictionary<string,string> InspectLuminanceResources(string[] paths,string? root)
    {
        var hashes=new Dictionary<string,string>(StringComparer.Ordinal);
        if(paths.Length>0 && string.IsNullOrWhiteSpace(root))
            throw new InvalidOperationException("Selected Luminance particle textures require INFINI_LUMINANCE_ASSET_DIR pointing to the Luminance source root");
        foreach(string path in paths) {
            if(!path.StartsWith("Luminance/Assets/",StringComparison.Ordinal) || path.Contains("..",StringComparison.Ordinal) || path.Contains('\\'))
                throw new InvalidOperationException("Invalid Luminance texture path: "+path);
            string file=Path.Combine(root!,path.Substring("Luminance/".Length).Replace('/',Path.DirectorySeparatorChar)+".png");
            if(!File.Exists(file))throw new FileNotFoundException("Selected Luminance particle texture is missing: "+path,file);
            hashes[path]=Hash(File.ReadAllBytes(file));
        }
        return hashes;
    }
    internal static void PrewarmLibraryTextures(string[] paths,Func<string,bool> ensure,Action drain)
    {
        foreach(string path in paths) {
            ensure(path);drain();
            if(!ensure(path))throw new InvalidOperationException("Original ParticleLibrary readiness failed for selected texture after native main-thread queue: "+path);
        }
    }
    public void Step(int tick)
    {
        bool oldDedicated=Main.dedServ;Main.dedServ=false;
        int updateWidth=Main.screenWidth,updateHeight=Main.screenHeight;Vector2 updateCamera=Main.screenPosition;var updateView=Main.GameViewMatrix;
        Main.screenWidth=width;Main.screenHeight=height;Main.screenPosition=camera;Main.GameViewMatrix=new Terraria.Graphics.SpriteViewMatrix(graphics.Device){Zoom=new Vector2(zoom)};
        Report["vfxUpdateUsesSceneCamera"]=true;
        try {
            string beforeUpdate=Rng();system.PostUpdateEverything();string afterUpdate=Rng();
            JsonObject snapshot=Snapshot(tick);snapshot["mainRngBeforeUpdate"]=beforeUpdate;snapshot["mainRngAfterUpdate"]=afterUpdate;snapshots.Add(snapshot);
            if(!capture&&!drawNativeDust&&!drawVanillaProjectiles&&activeVfx is null&&zombie is null)return;
            activeVfx?.BeginFrame();
            if(drawNativeDust){snapshot["nativeDustBeforeDraw"]=DustState();ConfigureDustReport();}
            string beforeDraw=Rng();
            int savedWidth=Main.screenWidth,savedHeight=Main.screenHeight;Vector2 savedCamera=Main.screenPosition;var savedView=Main.GameViewMatrix;
            JsonObject? scene = null;
            graphics.Device.SetRenderTarget(target);
            try {Main.screenWidth=width;Main.screenHeight=height;Main.screenPosition=camera;Main.GameViewMatrix=new Terraria.Graphics.SpriteViewMatrix(graphics.Device){Zoom=new Vector2(zoom)};scene=SceneSnapshot();graphics.Device.Clear(Color.Black);artwork?.BeginFrame();placedBodies?.Draw(tick);if(drawDroppedItems)artwork?.DrawDroppedItems();trainingDummy?.Draw();zombie?.Draw();if(artwork?.NativePlayerEnabled!=true)artwork?.DrawHeld();if(artwork is not null) Invoke("DrawProjectiles",new Terraria.On_Main.orig_DrawProjectiles(_=>artwork.DrawProjectiles()),Main.instance);else if(drawProjectileVfx)Invoke("DrawProjectiles",new Terraria.On_Main.orig_DrawProjectiles(_=>activeVfx!.Draw()),Main.instance);else {Invoke("BeginDrawBudgetFrame");Invoke("DrawLayer","BeforeProjectiles");Invoke("DrawLayer","AfterProjectiles");}if(artwork?.NativePlayerEnabled==true)artwork.DrawHeld();if(drawNativeDust)typeof(Main).GetMethod("DrawDust",All)!.Invoke(Main.instance,null);artwork?.DrawInventory();}
            finally {graphics.Device.SetRenderTarget(null);Main.screenWidth=savedWidth;Main.screenHeight=savedHeight;Main.screenPosition=savedCamera;Main.GameViewMatrix=savedView;}
            string afterDraw=Rng();
            Report["gpuRenderLifecycleExecuted"]=true;
            if(activeVfx is not null) {
                snapshot["activeProjectileVfx"]=activeVfx.Frame.DeepClone();
                int segments=activeVfx.Frame["historyRibbonDraws"]!.AsArray().Sum(d=>d!["submittedSegments"]!.GetValue<int>());
                Report["historyRibbonSubmittedSegments"]=(Report["historyRibbonSubmittedSegments"]?.GetValue<int>()??0)+segments;
            }
            if(drawVanillaProjectiles){snapshot["nativeDrawCounters"]=artwork?.Frame.DeepClone();Report["pngExportEnabled"]=capture;Report["captureSemantics"]="Native projectile GPU render lifecycle executes every tick; capture controls PNG encoding/export only";}
            if(artwork is not null){
                if((artwork.Frame["heldItemDrawCount"]?.GetValue<int>()??0)+(artwork.Frame["inventoryPreviewDrawCount"]?.GetValue<int>()??0)>0)Report["itemArtworkRendered"]=true;
                if((artwork.Frame["projectileDrawCount"]?.GetValue<int>()??0)>0){Report["projectileArtworkRendered"]=true;if(artwork.NativeVanillaEnabled)Report["vanillaProjectileDrawExecuted"]=drawVanillaProjectiles;else if(artwork.NativePlayerEnabled)Report["fullProjectilePreDrawExecuted"]=true;}
                if((artwork.Frame["playerRenderAllLayersCalls"]?.GetValue<int>()??0)>0)Report["playerArtworkRendered"]=true;
            }
            if(trainingDummy is not null)Report["trainingDummyArtworkRendered"]=true;
            if(zombie is not null){snapshot["zombie"]=zombie.Frame.DeepClone();if((zombie.Frame["drawCount"]?.GetValue<int>()??0)>0)Report["zombieArtworkRendered"]=true;}
            if(drawNativeDust){snapshot["nativeDustAfterDraw"]=DustState();snapshot["mainRngBeforeDraw"]=beforeDraw;snapshot["mainRngAfterDraw"]=afterDraw;snapshot["nativeDustDrawExecuted"]=true;snapshot["nativeDrawCounters"]=artwork?.Frame.DeepClone();Report["nativeDustDrawExecuted"]=true;}
            if(!capture)return;var pixels=new Color[width*height];target.GetData(pixels);
            string path=Path.Combine(framesDir,$"{tick:000000}.png");using(var stream=File.Create(path))target.SaveAsPng(stream,width,height);
            var frame=new JsonObject{["tick"]=tick,["width"]=width,["height"]=height,["resourcesReady"]=true,["particles"]=snapshot["particleCount"]!.DeepClone(),["records"]=snapshot["materialRecordCount"]!.DeepClone(),["path"]=Path.GetFileName(framesDir)+"/"+Path.GetFileName(path),["sha256"]=Hash(File.ReadAllBytes(path)),["nonblackPixels"]=pixels.Count(p=>p.R!=0||p.G!=0||p.B!=0),["mainRngBeforeDraw"]=beforeDraw,["mainRngAfterDraw"]=afterDraw,["drawChangedMainRng"]=beforeDraw!=afterDraw};
            frame["scene"]=scene;
            if(activeVfx is not null)frame["activeProjectileVfx"]=activeVfx.Frame.DeepClone();
            if(artwork is not null) foreach(var pair in artwork.Frame) frame[pair.Key]=pair.Value?.DeepClone();
            if(artwork is not null) {
                if(frame["heldItemDrawCount"]!.GetValue<int>()+frame["inventoryPreviewDrawCount"]!.GetValue<int>()>0) Report["itemArtworkRendered"]=true;
                if(frame["projectileDrawCount"]!.GetValue<int>()>0){Report["projectileArtworkRendered"]=true;if(artwork.NativeVanillaEnabled)Report["vanillaProjectileDrawExecuted"]=drawVanillaProjectiles;else if(artwork.NativePlayerEnabled)Report["fullProjectilePreDrawExecuted"]=true;}
                if((frame["playerRenderAllLayersCalls"]?.GetValue<int>()??0)>0)Report["playerArtworkRendered"]=true;
            }
            if(trainingDummy is not null){frame["trainingDummy"]=trainingDummy.Snapshot();frame["trainingDummyNativeDrawCalls"]=1;Report["trainingDummyArtworkRendered"]=true;}
            if(zombie is not null)frame["zombie"]=zombie.Frame.DeepClone();
            // Keep complete dust states once, in the same-tick snapshot. Duplicating
            // hundreds of particles per PNG exceeded the portable trace size limit.
            if(drawNativeDust){frame["nativeDustDrawExecuted"]=true;frame["nativeDustStateTick"]=tick;frame["nativeDustBeforeDrawCount"]=snapshot["nativeDustBeforeDraw"]!.AsArray().Count;frame["nativeDustAfterDrawCount"]=snapshot["nativeDustAfterDraw"]!.AsArray().Count;}
            frames.Add(frame);
        } finally {Main.screenWidth=updateWidth;Main.screenHeight=updateHeight;Main.screenPosition=updateCamera;Main.GameViewMatrix=updateView;Main.dedServ=oldDedicated;}
    }
    void ConfigureDustReport(){
        Report["scope"]=artwork?.NativeVanillaEnabled==true?(drawVanillaProjectiles?"Original native vanilla PlayerRenderer/held-item, Main.DrawProj and Main.DrawDust; optional original training dummy tile layer; neutral background, not full Main.Draw/world":"Original native vanilla PlayerRenderer/held-item and Main.DrawDust; projectile simulation executes but native projectile sprites not rendered; neutral background, not full Main.Draw/world"):"Original native player/held, generated projectile PreDraw/PostDraw, detached VFX and Main.DrawDust on neutral background; optional actual training dummy tile layer, not complete Main.Draw/world";
        Report["nativeDustDrawEnabled"]=true;Report["pngExportEnabled"]=capture;Report["captureSemantics"]="Native GPU render lifecycle executes every tick; capture controls PNG encoding/export only in drawNativeDust mode";
        Report["nativeDustDrawEntryPoint"]="Original Main.DrawDust after ordinary player layer and before diagnostic inventory UI";
        Report["nativeDustStateMutation"]="Original DrawDust may deactivate offscreen or black dust; camera is part of the deterministic scene";
        Report["dustAssetAlphaScope"]="Pinned community Dust PNG loaded through genuine PngReader; full sheet has partial alpha and original extraction alpha semantics are not independently certified. No official-byte/pixel parity claim.";
        Report["unrenderedArtwork"]=new JsonArray(artwork?.NativeVanillaEnabled==true&&!drawVanillaProjectiles?"Native projectile sprites (simulation/hits still execute)":"No additional projectile omission",trainingDummy is null?(zombie is null?"Terraria tile/NPC/world artwork":"Terraria tile/world artwork and other NPCs"):"Solid terrain/world artwork and other NPCs");
        Report["unsupportedDrawPasses"]=new JsonArray("Locked-to-tile players before NPCs","Over-player/over-wire/hidden projectile passes","Full terrain/world scene");
        Report["passOrder"]=trainingDummy is null?new JsonArray("Original projectile/VFX wrapper","Ordinary native player/held layers","Original Main.DrawDust","Diagnostic inventory UI"):new JsonArray("Native training dummy non-solid tiles","Original projectile/VFX wrapper","Ordinary native player/held layers","Original Main.DrawDust","Diagnostic inventory UI");
        if(zombie is not null){Report["scope"]="Original native controlled zombie DrawNPC, player/held, projectile/VFX and Main.DrawDust; neutral background, no full world or NPC AI parity";Report["passOrder"]!.AsArray().Insert(0,JsonValue.Create("Original controlled zombie Main.DrawNPC"));}
        if(drawProjectileVfx){Report["scope"]="Original procedural projectile VFX and Main.DrawDust; authored/player/world artwork unrendered";Report["unrenderedArtwork"]=new JsonArray("Authored item and projectile PNGs (no replacements)","Player artwork","Terraria tile/NPC/world artwork");Report["passOrder"]=new JsonArray("Original detached before-projectile layer","Original active projectile VFX under/over passes","Original detached after-projectile layer","Original Main.DrawDust");}
        RefreshVanillaReport();
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
        var paths=new JsonArray();
        foreach(object path in (IEnumerable)GetStatic("MaterialPaths")!) {
            object design=Field(path,"Design")!;
            var history=new JsonArray();foreach(object sample in (IEnumerable)Field(path,"History")!) {
                var position=(Vector2)Field(sample,"Position")!;history.Add(new JsonObject{["x"]=position.X,["y"]=position.Y,["tick"]=Convert.ToUInt64(Field(sample,"Tick"))});
            }
            var geometry=new JsonArray();foreach(Vector2 point in (IEnumerable)Field(path,"Geometry")!)geometry.Add(new JsonObject{["x"]=point.X,["y"]=point.Y});
            paths.Add(new JsonObject{["sourceKey"]=Field(path,"SourceKey")?.ToString(),["slotId"]=Field(path,"SlotId")?.ToString(),["source"]=Field(design,"Source")?.ToString(),["texturePath"]=Field(design,"TexturePath")?.ToString(),["sampleTick"]=Convert.ToUInt64(Field(path,"SampleTick")),["retired"]=(bool)Field(path,"Retired")!,["history"]=history,["geometry"]=geometry});
        }
        var detached=new JsonArray();
        foreach(object emission in (IEnumerable)GetStatic("Emissions")!) {
            var center=(Vector2)Field(emission,"Center")!;
            detached.Add(new JsonObject{["sourceKey"]=Field(emission,"SourceKey")?.ToString(),["texturePath"]=Field(emission,"TexturePath")?.ToString(),["primitiveKind"]=Field(emission,"PrimitiveKind")?.ToString(),["startTick"]=Convert.ToUInt64(Field(emission,"StartUpdate")),["duration"]=Convert.ToInt32(Field(emission,"Duration")),["x"]=center.X,["y"]=center.Y});
        }
        return new JsonObject{["tick"]=tick,["materialRecordCount"]=rows.Count,["particleCount"]=total,["records"]=rows,["pathRecordCount"]=paths.Count,["paths"]=paths,["detachedRecordCount"]=detached.Count,["detached"]=detached};
    }
    public void Dispose()
    {
        if(disposed)return;disposed=true;bool oldDedicated=Main.dedServ;Main.dedServ=false;
        try {system.Unload();particleManager.Unload();actualMod.Unload();mod.Assets.Dispose();registry.Remove(mod.Name);
            if(luminanceResources is not null){luminanceResources.Assets.Dispose();registry.Remove(luminanceResources.Name);}
            foreach(var field in typeof(Terraria.ModLoader.Config.ConfigManager).GetFields(All))if(field.IsStatic&&field.GetValue(null) is IDictionary dictionary&&dictionary.Contains(mod))dictionary.Remove(mod);
        } finally {
            target.Dispose();batch.Dispose();game.Services.RemoveService(typeof(AssetReaderCollection));if(oldReaders is not null)game.Services.AddService(typeof(AssetReaderCollection),oldReaders);
            typeof(Game).GetField("<Services>k__BackingField",All)!.SetValue(Main.instance,oldServices);Main.graphics=oldGraphics;Main.spriteBatch=oldBatch;Main.GameViewMatrix=oldView;Main.screenWidth=oldWidth;Main.screenHeight=oldHeight;Main.screenPosition=oldCamera;Main.dedServ=oldDedicated;
            Directory.Delete(contentRoot,true);
        }
    }
}
