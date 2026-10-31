using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;

internal static partial class EngineRuntimeChecks
{
    private static void LibraryPaletteExactResourceSnapshot()
    {
        var palette = new[] {
            ("branchingNoise","Luminance/Assets/Noise/DendriticNoiseZoomedOut"),
            ("turbulentNoise","Luminance/Assets/Noise/TurbulentNoise"),
            ("blotchNoise","Luminance/Assets/Noise/WavyBlotchNoise"),
            ("star","ParticleLibrary/Assets/Textures/Star"),
            ("solidPixel","ParticleLibrary/Assets/Textures/WhitePixel"),
            ("bloomCircle","Luminance/Assets/GreyscaleTextures/BloomCircleSmall"),
            ("bloomFlare","Luminance/Assets/GreyscaleTextures/BloomFlare"),
            ("bloomLine","Luminance/Assets/GreyscaleTextures/BloomLine"),
            ("chromaticBurst","Luminance/Assets/GreyscaleTextures/ChromaticBurst"),
            ("shineFlare","Luminance/Assets/GreyscaleTextures/ShineFlare"),
        };
        foreach(var (id,path) in palette) foreach(string blend in new[]{"alpha","additive"}) foreach(string sampling in new[]{"point","linear"}) {
            var wire=LibraryManifestWire();wire["slots"]![0]!["particle"]!["textureId"]=id;wire["slots"]![0]!["blend"]=blend;wire["slots"]![0]!["particle"]!["sampling"]=sampling;
            var data=GeneratedItemData.Placeholder();data.VfxManifest=VfxManifestSpec.FromJson(wire.ToJsonString());
            var slot=data.VfxManifest.Slots[0];Equal(id,slot.Particle!.TextureId,"typed palette identity");
            object snapshot=LibraryInvoke("CopyLibrary",data,slot,false)!;
            object particle=snapshot.GetType().GetProperty("Particle")!.GetValue(snapshot)!;
            Equal(path,(string)particle.GetType().GetProperty("TexturePath")!.GetValue(particle)!,"exact native resource snapshot");
            Equal(sampling,(string)particle.GetType().GetProperty("Sampling")!.GetValue(particle)!,"sampler copied to immutable design");
            Equal(true,ReferenceEquals(sampling=="point"?Microsoft.Xna.Framework.Graphics.SamplerState.PointClamp:Microsoft.Xna.Framework.Graphics.SamplerState.LinearClamp,LibraryInvoke("LibrarySampler",sampling)),"exact native sampler selected");
            Equal(blend,(string)snapshot.GetType().GetProperty("Blend")!.GetValue(snapshot)!,"no silent blend override");
            slot.Particle.TextureId="star";
            Equal(path,(string)particle.GetType().GetProperty("TexturePath")!.GetValue(particle)!,"retained snapshot cannot change texture after author mutation");
        }
        var old=LibraryData();
        Equal(true,old.VfxManifest.Slots[0].Particle!.Sampling is null,"old saved omitted sampler stays absent");
        Equal(false,old.VfxManifest.ToJson().Contains("\"sampling\""),"old wire roundtrip does not materialize sampler");
        var oldDesign=LibraryInvoke("CopyLibrary",old,old.VfxManifest.Slots[0],false)!;
        var oldParticle=oldDesign.GetType().GetProperty("Particle")!.GetValue(oldDesign)!;
        Equal("point",(string)oldParticle.GetType().GetProperty("Sampling")!.GetValue(oldParticle)!,"historical omission executes exact PointClamp");
        var nullSampling=LibraryManifestWire();nullSampling["slots"]![0]!["particle"]!["sampling"]=null;
        Equal(false,VfxManifestSpec.FromJson(nullSampling.ToJsonString()).HasSlots,"explicit null sampler is invalid, not historical omission");
        var invalid=LibraryManifestWire();invalid["slots"]![0]!["particle"]!["textureId"]="../Star";
        Equal(false,VfxManifestSpec.FromJson(invalid.ToJsonString()).HasSlots,"invalid manifest rejected, not replaced by Star");
        var bad=LibraryData().VfxManifest.Slots[0];bad.Particle!.TextureId="../Star";
        bool rejected=false;try{bad.NormalizeAndValidate();}catch(InvalidDataException){rejected=true;}
        Equal(true,rejected,"direct DTO rejects unknown resource without a fallback");
    }
    private static void LibraryPaletteReadinessAndSharedDrawBudget()
    {
        WithVfxGeometryQueue((batch,texture,count,positions,colors)=>WithLighting((config,lights)=>{
            var type=typeof(InfiniDetachedVfxSystem);var flags=BindingFlags.Static|BindingFlags.NonPublic;
            var field=type.GetField("LibraryBuffers",flags)!;object? old=field.GetValue(null);
            var textures=(System.Collections.Generic.Dictionary<string,Microsoft.Xna.Framework.Graphics.Texture2D>)type.GetField("LibraryTextures",flags)!.GetValue(null)!;
            var saved=new System.Collections.Generic.Dictionary<string,Microsoft.Xna.Framework.Graphics.Texture2D>(textures);
            var buffersType=type.GetNestedType("LibraryBuffer",BindingFlags.NonPublic)!;
            var buffers=Array.CreateInstance(buffersType,4);var system=new InfiniDetachedVfxSystem();
            var draws=(System.Collections.Generic.Dictionary<string,int>)type.GetField("DrawCallsBySource",flags)!.GetValue(null)!;
            try {
                LibraryInvoke("LoadLibrary");system.OnWorldUnload();textures.Clear();
                for(int i=0;i<4;i++) {
                    var buffer=System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(buffersType);
                    buffersType.GetField("Instances",BindingFlags.Instance|BindingFlags.NonPublic)!.SetValue(buffer,new ParticleLibrary.Core.V3.Particles.ParticleInstance[2048]);
                    buffers.SetValue(buffer,i);
                }
                field.SetValue(null,buffers);textures["ParticleLibrary/Assets/Textures/Star"]=texture;
                Equal(true,(bool)LibraryInvoke("EnsureLibraryReady","ParticleLibrary/Assets/Textures/Star")!,"loaded texture ready");
                Equal(false,(bool)LibraryInvoke("EnsureLibraryReady","Luminance/Assets/GreyscaleTextures/ShineFlare")!,"other texture missing never substitutes Star");
                Equal(true,(bool)LibraryInvoke("EnsureLibraryReady","ParticleLibrary/Assets/Textures/Star")!,"missing lane did not disable loaded texture");
                textures["ParticleLibrary/Assets/Textures/WhitePixel"]=texture;
                config.EnableParticleLibraryBackend=true;config.ParticleSpawnMultiplier=1;
                var data=LibraryData();data.VfxManifest.Budget.MaxDrawCalls=1;data.VfxManifest.Slots[0].Particle!.Count=1;
                Equal(true,EnqueueLibraryForCheck(data,"palette_shared",new VfxSourceFrame(new Microsoft.Xna.Framework.Vector2(10,0),Microsoft.Xna.Framework.Vector2.UnitX,Microsoft.Xna.Framework.Vector2.Zero)),"star emission");
                data.VfxManifest.Slots[0].Particle!.Sampling="linear";
                Equal(true,EnqueueLibraryForCheck(data,"palette_shared",new VfxSourceFrame(new Microsoft.Xna.Framework.Vector2(20,0),Microsoft.Xna.Framework.Vector2.UnitX,Microsoft.Xna.Framework.Vector2.Zero)),"linear emission");
                data.VfxManifest.Slots[0].Particle!.TextureId="solidPixel";
                Equal(true,EnqueueLibraryForCheck(data,"palette_shared",new VfxSourceFrame(new Microsoft.Xna.Framework.Vector2(30,0),Microsoft.Xna.Framework.Vector2.UnitX,Microsoft.Xna.Framework.Vector2.Zero)),"other texture emission");
                draws.Clear();LibraryInvoke("DrawLibraryParticles","BeforeProjectiles",null);
                Equal(1,draws["palette_shared"],"draw budget not restarted for second sampler group");
                var instances=(ParticleLibrary.Core.V3.Particles.ParticleInstance[])buffersType.GetField("Instances",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(buffers.GetValue(0))!;
                Equal(10f,instances[0].Position_Scale.X,"first group retained; second cannot spend same source budget again");
            }finally {system.OnWorldUnload();field.SetValue(null,old);textures.Clear();foreach(var pair in saved)textures.Add(pair.Key,pair.Value);draws.Clear();}
        }));
    }

}
