using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateHostiles(JsonNode? hostiles)
    {
        if(hostiles is null)return;
        if(hostiles is not JsonArray rows || rows.Count>8)throw new ArgumentException("hostiles must be an array of at most eight controlled NPCs");
        foreach(var row in rows){WKeys(row,"controlled hostile","x","y","life","width","height","defense","vx","vy");WValidateTarget(row);if(WFloat(row,"x",-1)<16 || WFloat(row,"x",0)>1500 || WFloat(row,"y",-1)<16 || WFloat(row,"y",0)>9400 || WInt(row,"life",10000) is <1 or >1000000)throw new ArgumentException("Controlled hostile outside bounded scene or invalid life");}
    }
    private static void WInitializeHostiles(JsonNode? hostiles)
    {
        int slot=2;
        foreach(var row in hostiles?.AsArray()??new JsonArray()){
            var npc=Terraria.Main.npc[slot];npc.SetDefaults(NPCID.Zombie);npc.whoAmI=slot++;npc.active=true;
            npc.position=new Microsoft.Xna.Framework.Vector2(WFloat(row,"x",0),WFloat(row,"y",0));npc.life=npc.lifeMax=WInt(row,"life",10000);
            npc.aiStyle=-1;npc.noGravity=true;npc.noTileCollide=true;npc.knockBackResist=0;npc.damage=0;npc.defense=0;WConfigureTarget(npc,row);npc.width=WInt(row,"width",npc.width);npc.height=WInt(row,"height",npc.height);
            new InfiniCrafterLocal.Common.Runtime.RuntimeHitNpcGeneration().OnSpawn(npc,Terraria.Main.player[0].GetSource_Misc("workbench-controlled-hostile"));
        }
    }
    // Controlled hostiles have no client artwork. Keep native NPC integration
    // while skipping its client FindFrame/presentation, never the damage phase.
    private readonly struct WUnrenderedNpcUpdate : IDisposable
    {
        private readonly bool previous;
        public WUnrenderedNpcUpdate(){previous=Terraria.Main.dedServ;Terraria.Main.dedServ=true;}
        public void Dispose(){Terraria.Main.dedServ=previous;}
    }
    private static void WUpdateControlledHostiles(JsonArray events,JsonObject report)
    {
        for(int slot=2;slot<10;slot++) {
            var npc=Terraria.Main.npc[slot];if(!npc.active)continue;
            using(new WUnrenderedNpcUpdate())npc.UpdateNPC(slot);
            events.Add(new JsonObject{["kind"]="native_phase",["phase"]="controlled hostile NPC.UpdateNPC",["npcId"]=slot,
                ["dedServ"]=true,["restoredDedServ"]=Terraria.Main.dedServ,["artworkRendered"]=false,
                ["scope"]="Unrendered controlled NPC; native dedicated update, client FindFrame omitted; projectile damage remains in its own phase"});
            WRequireFinite(npc,"hostile",slot,"after NPC.UpdateNPC",events,report);
        }
    }
    private static JsonArray WHostileSnapshots()=>new(Terraria.Main.npc.Skip(2).Take(8).Where(n=>n.type==NPCID.Zombie).Select(n=>(JsonNode?)new JsonObject{
        ["targetState"]=WTargetState(n),["slot"]=n.whoAmI,["nativeType"]=n.type,["active"]=n.active,["life"]=n.life,["x"]=WFinite(n.position.X),["y"]=WFinite(n.position.Y),["width"]=n.width,["height"]=n.height,["nonFinite"]=!WEntityFinite(n),["controlledAiStyle"]=n.aiStyle}).ToArray());
    private static bool WReactionAction(string kind)=>kind is "hurt_player" or "strike_hostile";
    private static void WValidateReactionAction(JsonNode action,bool full,bool client)
    {
        if(!full || client)throw new NotSupportedException("Reaction stimuli require full CPU Player.Update; rendered enemy/player damage effects are not admitted");
        WKeys(action,"reaction stimulus","kind","tick","damage");
        if(WInt(action,"damage",0) is < 1 or > 10000)throw new ArgumentException("reaction stimulus damage must be 1..10000");
    }
    // The isolated loader must own both globals for the entire scene, before
    // NPC defaults are created. Runtime effects use real tML hook dispatch.
    private sealed class WNpcGlobals : IDisposable
    {
        public WNpcGlobals()
        {
            if(GlobalList<GlobalNPC>.Globals.Length!=0)throw new NotSupportedException("Workbench requires an isolated empty GlobalNPC registry");
            Register(new RuntimeHitNpcGeneration());
            Register(new GeneratedEquipmentKillGlobalNPC());
            typeof(GlobalList<GlobalNPC>).GetMethod("FinishLoading",PersistenceStatic)!.Invoke(null,new object[]{NPCLoader.NPCCount});
            typeof(NPCLoader).GetMethod("FinishSetup",PersistenceStatic)!.Invoke(null,null);
        }
        private static void Register<T>(T global) where T : GlobalNPC
        {
            var indices=((short,short))typeof(GlobalList<GlobalNPC>).GetMethod("Register",PersistenceStatic)!.Invoke(null,new object[]{global})!;
            typeof(GlobalType<NPC,GlobalNPC>).GetProperty("StaticIndex")!.SetValue(global,indices.Item1);
            typeof(GlobalType<NPC,GlobalNPC>).GetProperty("PerEntityIndex")!.SetValue(global,indices.Item2);
            typeof(ContentInstance<T>).GetProperty("Instance")!.SetValue(null,global);
        }
        public void Dispose(){typeof(GlobalList<GlobalNPC>).GetMethod("Reset",PersistenceStatic)!.Invoke(null,null);typeof(NPCLoader).GetMethod("UpdateHookLists",PersistenceStatic)!.Invoke(null,null);}
    }
    // Native dispatch executes OnKill; this hook observes it without replacing it.
    private sealed class WReactionScene : IDisposable
    {
        private readonly Hook observer;
        private readonly Action<JsonObject> record;
        public WReactionScene(Action<JsonObject> record)
        {
            this.record=record;
            Terraria.Main.BestiaryTracker=new Terraria.GameContent.Bestiary.BestiaryUnlocksTracker();
            // This controlled hostile certifies death/credit/equipment callbacks,
            // not vanilla loot tables. The original resolver runs an empty table.
            Terraria.Main.ItemDropsDB=new Terraria.GameContent.ItemDropRules.ItemDropDatabase();
            Terraria.Main.ItemDropSolver=new Terraria.GameContent.ItemDropRules.ItemDropResolver(Terraria.Main.ItemDropsDB);
            ContentSamples.NpcBestiaryCreditIdsByNpcNetIds[NPCID.Zombie]=NPCID.Search.GetName(NPCID.Zombie);
            Terraria.Main.gore=Enumerable.Range(0,Terraria.Main.maxGore+1).Select(_=>new Gore()).ToArray();
            observer=new Hook(typeof(GeneratedEquipmentKillGlobalNPC).GetMethod(nameof(GeneratedEquipmentKillGlobalNPC.OnKill))!,
                (Action<Action<GeneratedEquipmentKillGlobalNPC,NPC>,GeneratedEquipmentKillGlobalNPC,NPC>)((orig,self,npc)=>{
                    record(new JsonObject{["kind"]="native_equipment_kill_callback",["npcId"]=npc.whoAmI,["npcType"]=npc.type,["life"]=npc.life,["lastInteraction"]=npc.lastInteraction,["entrypoint"]="NPC death -> NPCLoader.OnKill -> GeneratedEquipmentKillGlobalNPC.OnKill"});
                    orig(self,npc);
                }));
        }
        public void Apply(Player owner,JsonNode action)
        {
            int damage=WInt(action,"damage",1);
            if(action["kind"]!.GetValue<string>()=="hurt_player"){
                int before=owner.statLife;
                double dealt=owner.Hurt(PlayerDeathReason.ByCustomReason(Terraria.Localization.NetworkText.FromLiteral("Workbench controlled damage stimulus")),damage,0,pvp:false,quiet:true);
                record(new JsonObject{["kind"]="native_player_hurt",["requestedDamage"]=damage,["nativeDamage"]=dealt,["lifeBefore"]=before,["lifeAfter"]=owner.statLife,["dead"]=owner.dead,["immune"]=owner.immune,["entrypoint"]="Player.Hurt with native defense, immunity and PostHurt dispatch"});
                return;
            }
            const int slot=1;
            if(Terraria.Main.npc[slot].active)throw new InvalidOperationException("Previous controlled hostile remains active; strike_hostile will not silently overwrite it");
            var victim=Terraria.Main.npc[slot]=new NPC();
            victim.SetDefaults(NPCID.Zombie); // Native global attachment/type applicability.
            victim.whoAmI=slot;victim.active=true;victim.life=victim.lifeMax=1;victim.damage=victim.defense=0;
            victim.position=owner.position+new Microsoft.Xna.Framework.Vector2(80,0);victim.aiStyle=-1;
            victim.noGravity=victim.noTileCollide=true;victim.knockBackResist=0;victim.realLife=-1;victim.HideStrikeDamage=true;victim.value=0;
            // Apply actual native interaction attribution, damage and death.
            owner.StrikeNPCDirect(victim,new NPC.HitInfo{Damage=damage,Knockback=0,HitDirection=0});
            record(new JsonObject{["kind"]="native_hostile_strike",["npcId"]=slot,["npcType"]=victim.type,["requestedDamage"]=damage,["lifeAfter"]=victim.life,["activeAfter"]=victim.active,["lastInteraction"]=victim.lastInteraction,["entrypoint"]="Player.StrikeNPCDirect -> NPC.StrikeNPC / checkDead",["lootScope"]="Native resolver with explicitly empty controlled-scene table; vanilla drops not certified"});
        }
        public void Dispose()=>observer.Dispose();
    }
}
