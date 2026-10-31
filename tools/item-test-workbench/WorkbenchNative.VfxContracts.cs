using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    // Part of --check-assertions: actual stand policies, not a GPU/gameplay claim.
    private static void CheckWorkbenchVfxContracts()
    {
        void Refused(Action action,string reason) {
            bool rejected=false;
            try{action();}catch(NotSupportedException){rejected=true;}
            if(!rejected)throw new Exception(reason);
        }
        var trail=new VfxSlotSpec{RendererKind="historyTrail",Trail=new VfxHistoryTrailSpec{Draw="stroke",Source="center"}};
        WValidateHistoryTrail(trail,true);
        Refused(()=>WValidateHistoryTrail(trail,false),"historyTrail admitted without full PreDraw");
        trail.Trail.Draw="sprites";
        Refused(()=>WValidateHistoryTrail(trail,true),"Unverified sprite trail admitted");
        trail.Trail.Draw="stroke";trail.Trail.Source="tip";
        Refused(()=>WValidateHistoryTrail(trail,true),"Unverified tip trail admitted");
        Refused(()=>WValidateHistoryTrail(new VfxSlotSpec{RendererKind="historyTrail"},true),"Missing trail payload admitted");

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
