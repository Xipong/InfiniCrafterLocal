using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateNativeDust(VfxSlotSpec slot,bool nativeDraw)
    {
        if(!nativeDraw || slot.Dust is not {Type:"TintableDustLighted" or "Glass" or "GemDiamond" or "Electric"})
            throw new NotSupportedException("nativeDust requires verified native draw and evidenced TintableDustLighted/Glass/GemDiamond/Electric selector");
    }

    private static void WValidateShape(VfxSlotSpec slot,bool fullNativeDraw)
    {
        if(!fullNativeDraw || !(slot.Shape is {Kind:"arc" or "sector",Attachment:"world" or "source",RotationFrame:"world" or "source"}
            or {Kind:"orbit",Attachment:"source",RotationFrame:"world",MoteOrientation:"world" or "orbit"}
            or {Kind:"orbit",Attachment:"world",RotationFrame:"world" or "source",MoteOrientation:"orbit"}))
            throw new NotSupportedException("shape currently requires proven world/source arc or sector, source-bound world-frame orbit with world- or orbit-oriented motes, or world-fixed world/source-frame orbit with orbit-oriented motes, plus full native draw with original MagicPixel");
    }

    private static void CheckWorkbenchVfxRecorder()
    {
        WNativeActiveVfx.CheckRecorderContract();
        WithLighting((_,_)=>{
            var system=new InfiniDetachedVfxSystem();
            try {
                system.OnWorldUnload();
                var empty=WNativeVfxRenderer.Snapshot(0);
                foreach(string key in new[]{"records","paths","shapes","contours"})
                    if(empty[key]!.AsArray().Count!=0)throw new Exception("Empty current VFX queue invented "+key);
                if(empty.ContainsKey("detached")||empty.ContainsKey("detachedRecordCount"))
                    throw new Exception("Retired detached emission projection survived");
                var data=ParseMaterialElement(MaterialElementWire());
                var element=data.VfxManifest.Slots[0];element.Event="on_hit";element.RepeatEvery=0;
                var frame=new VfxSourceFrame(new Vector2(100,120),Vector2.UnitX,Vector2.Zero);
                if(!InfiniDetachedVfxSystem.EnqueueElement(data,element.EntityId,element,"recorder-element",frame))
                    throw new Exception("Current material recorder fixture was not admitted");
                var shape=ExplicitShapeSlot("arc");
                shape.EntityId=element.EntityId;shape.Duration=12;shape.Shape!.RotationFrame="world";
                shape.NormalizeAndValidate();
                if(!InfiniDetachedVfxSystem.EnqueueShape(data,shape,"recorder-shape",frame,null))
                    throw new Exception("Current shape recorder fixture was not admitted");
                var snapshot=WNativeVfxRenderer.Snapshot(1);
                var record=snapshot["records"]!.AsArray().Single()!;
                if(record["renderer"]!.GetValue<string>()!="spriteElement"||record["texturePath"]!.GetValue<string>()!="recipe_vfx_Shard_A.png"
                    ||record["particleCount"]!.GetValue<int>()!=2||record["particles"]!.AsArray().Count!=2)
                    throw new Exception("Current material source/particle evidence lost");
                var geometry=snapshot["shapes"]!.AsArray().Single()!;
                if(geometry["kind"]!.GetValue<string>()!="arc"||geometry["x"]!.GetValue<float>()!=100||geometry["y"]!.GetValue<float>()!=120)
                    throw new Exception("Current native shape evidence lost");
            }finally{system.OnWorldUnload();}
        });
        Console.WriteLine("PASS: current VFX recorder reflection closure and real material/shape snapshots (CPU only, not GPU)");
    }

    // Part of --check-assertions: actual stand policies, not a GPU/gameplay claim.
    private static void CheckWorkbenchVfxContracts()
    {
        CheckWorkbenchVfxRecorder();
        void Refused(Action action,string reason) {
            bool rejected=false;
            try{action();}catch(NotSupportedException){rejected=true;}
            if(!rejected)throw new Exception(reason);
        }
        var dust=new VfxSlotSpec{RendererKind="nativeDust",Dust=new VfxNativeDustSpec{Type="TintableDustLighted"}};
        WValidateNativeDust(dust,true);
        Refused(()=>WValidateNativeDust(dust,false),"Dust admitted without native draw");
        dust.Dust.Type="Glass";WValidateNativeDust(dust,true);
        dust.Dust.Type="GemDiamond";WValidateNativeDust(dust,true);
        dust.Dust.Type="Electric";WValidateNativeDust(dust,true);
        dust.Dust.Type="Smoke";
        Refused(()=>WValidateNativeDust(dust,true),"Unproven dust admitted");
        Refused(()=>WValidateNativeDust(new VfxSlotSpec{RendererKind="nativeDust"},true),"Missing dust admitted");
        var shape=new VfxSlotSpec{RendererKind="shape",Shape=new VfxShapeSpec{Kind="arc",Attachment="world",RotationFrame="world"}};
        WValidateShape(shape,true);
        Refused(()=>WValidateShape(shape,false),"Shape admitted without full native draw");
        shape.Shape.Attachment="source";
        WValidateShape(shape,true);
        shape.Shape.Attachment="world";shape.Shape.Kind="sector";
        WValidateShape(shape,true);
        shape.Shape.Attachment="source";WValidateShape(shape,true);
        shape.Shape.RotationFrame="source";WValidateShape(shape,true);
        shape.Shape.Attachment="world";WValidateShape(shape,true);
        shape.Shape.Kind="line";Refused(()=>WValidateShape(shape,true),"Unverified line renderer admitted");
        shape.Shape.Kind="arc";shape.Shape.RotationFrame="source";
        WValidateShape(shape,true);
        Refused(()=>WValidateShape(new VfxSlotSpec{RendererKind="shape"},true),"Missing shape admitted");
        var orbit=new VfxSlotSpec{RendererKind="shape",Shape=new VfxShapeSpec{Kind="orbit",Attachment="source",RotationFrame="world",MoteOrientation="world"}};
        WValidateShape(orbit,true);
        orbit.Shape.MoteOrientation="orbit";WValidateShape(orbit,true);
        orbit.Shape.Attachment="world";orbit.Shape.MoteOrientation="orbit";WValidateShape(orbit,true);
        orbit.Shape.RotationFrame="source";WValidateShape(orbit,true);
        Refused(()=>WValidateShape(orbit,false),"World/source orbit admitted without full native draw");
        orbit.Shape.Attachment="source";Refused(()=>WValidateShape(orbit,true),"Unproven source-bound source-frame orbit admitted");
        orbit.Shape.Attachment="world";
        orbit.Shape.RotationFrame="world";orbit.Shape.MoteOrientation="radial";Refused(()=>WValidateShape(orbit,true),"Unproven orbit mote orientation admitted");
        var trail=new VfxSlotSpec{RendererKind="historyTrail",Trail=new VfxHistoryTrailSpec{Draw="stroke",Source="center"}};
        WValidateHistoryTrail(trail,true);
        Refused(()=>WValidateHistoryTrail(trail,false),"historyTrail admitted without full PreDraw");
        trail.Trail.Draw="sprites";trail.Trail.Texture=new(){Source="entity",AssetId=""};trail.Trail.Pose="sampled";
        WValidateHistoryTrail(trail,true);
        trail.Trail.Texture.Source="library";
        Refused(()=>WValidateHistoryTrail(trail,true),"Unverified sprite material admitted");
        trail.Trail.Texture.Source="entity";trail.Trail.Pose="current";
        Refused(()=>WValidateHistoryTrail(trail,true),"Unverified current-pose trail admitted");
        trail.Trail.Draw="stroke";trail.Trail.Source="tip";
        Refused(()=>WValidateHistoryTrail(trail,true),"Unverified tip trail admitted");
        Refused(()=>WValidateHistoryTrail(new VfxSlotSpec{RendererKind="historyTrail"},true),"Missing trail payload admitted");

        var heldData=GeneratedItemData.Placeholder();
        var held=new VfxSlotSpec{EntityId=heldData.RuntimeProgram.ItemEntityId,Event="on_use",RendererKind="historyTrail",Layer="AfterPlayer",Trail=new VfxHistoryTrailSpec{Draw="stroke",Source="tip"}};
        WValidateHistoryTrail(held,true,heldData);
        Refused(()=>WValidateHistoryTrail(held,false,heldData),"Held history without final native player draw admitted");
        held.Trail.Draw="sprites";held.Trail.Texture=new(){Source="item",AssetId=""};
        WValidateHistoryTrail(held,true,heldData);
        held.Trail.Texture.Source="library";
        Refused(()=>WValidateHistoryTrail(held,true,heldData),"Unverified alternate held history texture admitted");
        held.Trail.Texture.Source="item";held.Layer="AfterProjectiles";
        Refused(()=>WValidateHistoryTrail(held,true,heldData),"Held history routed through projectile layer");

        VfxSlotSpec Particle(string id)=>new(){RendererKind="libraryParticle",Particle=new VfxLibraryParticleSpec{TextureId=id}};
        var data=new GeneratedItemData();
        if(WNativeVfxRenderer.SelectedLibraryTexturePaths(null).Length!=0 || WNativeVfxRenderer.SelectedLibraryTexturePaths(data).Length!=0)
            throw new Exception("Empty scene invented a particle texture");
        data.VfxManifest.Slots=new[]{Particle("solidPixel"),Particle("star"),Particle("solidPixel")};
        var paths=WNativeVfxRenderer.SelectedLibraryTexturePaths(data);
        if(!paths.SequenceEqual(new[]{"ParticleLibrary/Assets/Textures/WhitePixel","ParticleLibrary/Assets/Textures/Star"}))
            throw new Exception("Selected texture mapping/deduplication changed");
        data.VfxManifest.Slots=new[]{Particle("bloomCircle")};
        if(WNativeVfxRenderer.SelectedLibraryTexturePaths(data).Single()!="Luminance/Assets/GreyscaleTextures/BloomCircleSmall")
            throw new Exception("Production registry mapping was replaced by ParticleLibrary-only guessing");
        // Luminance is optional until the item selects it; the actual selected
        // file must exist and its bytes are recorded for the render receipt.
        string[] luminance={"Luminance/Assets/GreyscaleTextures/BloomCircleSmall"};
        if(WNativeVfxRenderer.InspectLuminanceResources(Array.Empty<string>(),null).Count!=0)
            throw new Exception("Empty selection required Luminance resources");
        bool missingRoot=false;
        try{WNativeVfxRenderer.InspectLuminanceResources(luminance,null);}catch(InvalidOperationException){missingRoot=true;}
        if(!missingRoot)throw new Exception("Missing Luminance root silently passed");
        string root=Path.Combine(Path.GetTempPath(),"icl-vfx-contract-"+Guid.NewGuid().ToString("N"));
        try {
            Directory.CreateDirectory(Path.Combine(root,"Assets","GreyscaleTextures"));
            bool missingFile=false;
            try{WNativeVfxRenderer.InspectLuminanceResources(luminance,root);}catch(FileNotFoundException){missingFile=true;}
            if(!missingFile)throw new Exception("Missing selected Luminance texture silently passed");
            File.WriteAllText(Path.Combine(root,"Assets","GreyscaleTextures","BloomCircleSmall.png"),"abc");
            var hashes=WNativeVfxRenderer.InspectLuminanceResources(luminance,root);
            if(hashes[luminance[0]]!="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
                throw new Exception("Luminance receipt did not preserve selected bytes");
        } finally {if(Directory.Exists(root))Directory.Delete(root,true);}
        data.VfxManifest.Slots=new[]{Particle("unknown")};
        Refused(()=>WNativeVfxRenderer.SelectedLibraryTexturePaths(data),"Unknown particle texture silently substituted");

        // Emulate only the asynchronous resource boundary: real stand code must
        // drain each selected request before asking the production owner again.
        var ready=new HashSet<string>();string? queued=null;int drains=0;
        bool Ensure(string path){if(ready.Contains(path))return true;if(queued is not null)throw new Exception("Parallel readiness request lost a texture");queued=path;return false;}
        WNativeVfxRenderer.PrewarmLibraryTextures(paths,Ensure,()=>{drains++;ready.Add(queued!);queued=null;});
        if(drains!=2 || !ready.SetEquals(paths))throw new Exception("Selected textures not individually prewarmed");
        WNativeVfxRenderer.PrewarmLibraryTextures(Array.Empty<string>(),_=>throw new Exception("Empty scene selected texture"),()=>throw new Exception("Empty scene queued texture"));
        bool missingRejected=false;
        try{WNativeVfxRenderer.PrewarmLibraryTextures(paths,_=>false,()=>{});}catch(InvalidOperationException error){missingRejected=error.Message.Contains(paths[0]);}
        if(!missingRejected)throw new Exception("Missing selected resource silently passed readiness");

        bool saved=Terraria.Main.dedServ;
        try {
            foreach(bool previous in new[]{false,true}) {
                Terraria.Main.dedServ=previous;
                using(new WUnrenderedNpcUpdate())if(!Terraria.Main.dedServ)throw new Exception("Controlled NPC requested client artwork");
                if(Terraria.Main.dedServ!=previous)throw new Exception("Controlled NPC leaked dedServ");
                try{using(new WUnrenderedNpcUpdate())throw new InvalidOperationException("scope control");}catch(InvalidOperationException){}
                if(Terraria.Main.dedServ!=previous)throw new Exception("Failed NPC update leaked dedServ into damage/render phase");
            }
        }finally{Terraria.Main.dedServ=saved;}
        Console.WriteLine("PASS: workbench trail admission, exact selected texture readiness/queue controls and controlled NPC dedicated-scope restoration (not GPU/gameplay)");
    }
}
