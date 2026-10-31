using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

internal static partial class EngineRuntimeChecks
{
    private static void LibraryMaterialTypedAuthorityAndBackendIndependence()
    {
        WithVfxGeometryQueue((batch,texture,count,positions,colors)=>WithLighting((config,lights)=>{
            var cacheType=typeof(VfxNativeTextureCache);
            var ready=(Dictionary<string,Texture2D>)cacheType.GetField("Ready",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
            var saved=new Dictionary<string,Texture2D>(ready);var cache=new VfxNativeTextureCache();var system=new InfiniDetachedVfxSystem();
            try {
                cache.Load();ready.Clear();ready["shineFlare"]=texture;
                config.EnableParticleLibraryBackend=false;
                Equal(true,ReferenceEquals(texture,VfxNativeTextureCache.TryGet("shineFlare")),"material native cache independent of instancer backend");
                Equal(true,VfxNativeTextureCache.TryGet("star") is null,"unready selected native resource is not substituted");
                Equal(true,VfxNativeTextureCache.TryGet("../shineFlare") is null,"unknown ID does not touch native resource");
                var data=ParseMaterialElement(MaterialElementWire());var slot=data.VfxManifest.Slots[0];
                slot.Element!.Texture=new(){Source="library",AssetId="shineFlare"};slot.NormalizeAndValidate();
                string path=InfiniDetachedVfxSystem.ResolveMaterialTexture(data,slot.EntityId,slot.Element.Texture);
                Equal("Luminance/Assets/GreyscaleTextures/ShineFlare",path,"library ID selects exact native resource");
                object design=LibraryInvoke("CopyElement",data,slot,path,false)!;
                Equal("shineFlare",(string)design.GetType().GetProperty("LibraryTextureId")!.GetValue(design)!,"native source flag captured in snapshot");
                slot.Element.Texture=new(){Source="asset",AssetId="Shard_A"};
                data.VfxManifest.Assets![0].SpritePath=path;
                var fileDesign=LibraryInvoke("CopyElement",data,slot,path,false)!;
                Equal(true,fileDesign.GetType().GetProperty("LibraryTextureId")!.GetValue(fileDesign) is null,"same-looking file path remains file semantics");
                Equal("shineFlare",(string)design.GetType().GetProperty("LibraryTextureId")!.GetValue(design)!,"mutated selector cannot redirect existing snapshot");
                slot.Element.Texture=new(){Source="library",AssetId="shineFlare"};
                slot.Event="on_hit";slot.RepeatEvery=0;system.OnWorldUnload();
                Equal(true,InfiniDetachedVfxSystem.EnqueueElement(data,slot.EntityId,slot,"native_material",new VfxSourceFrame(new Vector2(10,20),Vector2.UnitX,Vector2.Zero)),"native material admitted while instancer disabled");
                LibraryInvoke("DrawMaterialSprites","BeforeProjectiles",batch,(Action)(()=>{}));
                Equal(2,count(),"real CPU sprite quad consumer draws native resource without generated PNG");
                var pathSpec=OwnerLinkSlot(slot).Path!;pathSpec.OwnerAnchor="mountedCenter";
                object pathDesign=LibraryInvoke("CopyPath",pathSpec,1f,"alpha",path,"BeforeProjectiles","self",512,0)!;
                Equal("shineFlare",(string)pathDesign.GetType().GetProperty("LibraryTextureId")!.GetValue(pathDesign)!,"textured path captures typed native source");
                pathSpec.Texture=new(){Source="item",AssetId=""};
                Equal("shineFlare",(string)pathDesign.GetType().GetProperty("LibraryTextureId")!.GetValue(pathDesign)!,"path snapshot remains native after selector mutation");
                var trail=ExplicitTrail("sprites");trail.Texture=new(){Source="library",AssetId="shineFlare"};
                var method=typeof(InfiniVfxRuntime).GetMethod("TrailTexture",BindingFlags.Static|BindingFlags.NonPublic)!;
                object?[] args={data,slot.EntityId,trail,null};
                Equal(true,ReferenceEquals(texture,method.Invoke(null,args)),"history trail resolves exact native resource too");
                bool rejected=false;try{new VfxTextureSpec{Source="library",AssetId="bad"}.Validate();}catch(InvalidDataException){rejected=true;}
                Equal(true,rejected,"DTO rejects unregistered library texture");
            } finally {system.OnWorldUnload();ready.Clear();foreach(var pair in saved)ready.Add(pair.Key,pair.Value);}
        }));
    }
}
