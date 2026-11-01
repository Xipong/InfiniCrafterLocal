using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // A controlled standalone phase dispatcher: only the actual tML hook
    // dispatchers are called. The caller supplies original engine updates, and
    // must explicitly report every omitted engine phase; this is not Main.Update.
    private sealed record WLoaderTickOps(Action Players, Action Npcs, Action Projectiles,
        Action? Gores, Action? Items, Action? Dusts, Action? Time, Action? World);

    private static string[] WLoaderTick(WLoaderTickOps ops)
    {
        ArgumentNullException.ThrowIfNull(ops.Players);
        ArgumentNullException.ThrowIfNull(ops.Npcs);
        ArgumentNullException.ThrowIfNull(ops.Projectiles);
        var omitted = new List<string>();
        SystemLoader.PreUpdateEntities();
        SystemLoader.PreUpdatePlayers(); ops.Players(); SystemLoader.PostUpdatePlayers();
        // Main advances its native update count immediately after the player phase.
        MaterialClock(unchecked(Terraria.Main.GameUpdateCount + 1));
        SystemLoader.PreUpdateNPCs(); ops.Npcs(); SystemLoader.PostUpdateNPCs();
        if (ops.Gores is null) omitted.Add("gore");
        else { SystemLoader.PreUpdateGores(); ops.Gores(); SystemLoader.PostUpdateGores(); }
        SystemLoader.PreUpdateProjectiles(); ops.Projectiles(); SystemLoader.PostUpdateProjectiles();
        if (ops.Items is null) omitted.Add("items");
        else { SystemLoader.PreUpdateItems(); ops.Items(); SystemLoader.PostUpdateItems(); }
        if (ops.Dusts is null) omitted.Add("dust");
        else { SystemLoader.PreUpdateDusts(); ops.Dusts(); SystemLoader.PostUpdateDusts(); }
        if (ops.Time is null) omitted.Add("time");
        else { SystemLoader.PreUpdateTime(); ops.Time(); SystemLoader.PostUpdateTime(); }
        // WorldGen.UpdateWorld itself dispatches Pre/PostUpdateWorld. Never
        // surround it with another manually dispatched pair.
        if (ops.World is null) omitted.Add("world"); else ops.World();
        SystemLoader.PostUpdateEverything();
        return omitted.ToArray();
    }

    private delegate void WLoaderHitOriginal(Projectile projectile, NPC npc, in NPC.HitInfo hit, int damage);
    private delegate void WLoaderHitObserver(WLoaderHitOriginal orig, Projectile projectile, NPC npc, in NPC.HitInfo hit, int damage);

    // Narrow opt-in scene over the actual autoloaded IFC assembly. It deliberately
    // refuses assertions and scripted actions for phases it cannot yet model.
    internal static JsonObject RunWorkbenchNativeLoaderScene(string? itemPath, string? nativeItem, string scenarioPath, string sandbox, string itemBoundary, IReadOnlyList<WNativeLoader.ModInput> extraMods)
    {
        if(itemBoundary is not ("fresh" or "local_cache")) throw new ArgumentException("item-boundary must be fresh or local_cache");
        if((itemPath is null)==(nativeItem is null))throw new ArgumentException("Specify exactly one generated JSON or native item identifier");
        if(nativeItem is not null && itemBoundary!="fresh")throw new ArgumentException("item-boundary applies only to generated JSON");
        GeneratedItemData? data=null;
        if(itemPath is not null) {
            string json=File.ReadAllText(itemPath);
            data=(itemBoundary=="fresh"?GeneratedItemData.FromJson(json):GeneratedItemData.FromLocalCacheJson(json))
                ?? throw new InvalidDataException("Item rejected by the requested production reader: "+ContractJsonDiagnostics.LastError);
        }
        var scenario=JsonNode.Parse(File.ReadAllText(scenarioPath))?.AsObject() ?? throw new InvalidDataException("Expected scenario object");
        WKeys(scenario,"native loader scene","ticks","seed","player","dummy","tiles","actions","assertions","worldId","playerUpdate");
        if(scenario["player"] is not JsonObject playerSettings || scenario["dummy"] is not JsonObject targetSettings)throw new ArgumentException("player and dummy objects are required");
        WKeys(playerSettings,"loader scene player","x","y","life","maxLife","mana","manaCrystals");
        WKeys(targetSettings,"loader scene dummy","x","y","width","height","life","nativeType");
        if(targetSettings["nativeType"] is not null && new[]{"width","height","life"}.Any(key=>targetSettings[key] is not null))
            throw new NotSupportedException("Mod NPC targets retain native dimensions and life; do not specify width, height or life");
        foreach(var settings in new[]{playerSettings,targetSettings}) {
            float x=WFloat(settings,"x",-1),y=WFloat(settings,"y",-1);
            if(!float.IsFinite(x)||!float.IsFinite(y)||x<16||x>1500||y<16||y>9500)throw new ArgumentException("Player and target coordinates must fit the isolated world");
        }
        int manaCrystals=WInt(playerSettings,"manaCrystals",9);
        if(manaCrystals is < 0 or > 9)throw new ArgumentException("manaCrystals must be 0..9");
        if(scenario["playerUpdate"]?.GetValue<string>() is string mode && mode!="full") throw new NotSupportedException("Native loader scene requires playerUpdate full");
        int ticks=WInt(scenario,"ticks",120); if(ticks is < 1 or > 600)throw new ArgumentException("ticks must be 1..600");
        var actions=scenario["actions"]?.AsArray() ?? throw new ArgumentException("actions are required");
        var checks=scenario["assertions"]?.AsArray() ?? throw new ArgumentException("assertions are required");
        if(checks.Count==0)throw new ArgumentException("At least one assertion is required");
        foreach(var a in actions) {
            string kind=a?["kind"]?.GetValue<string>() ?? throw new ArgumentException("Action kind is required");
            if(kind is not ("aim" or "primary" or "alt" or "release"))throw new NotSupportedException("Native loader scene does not yet support action: "+kind);
            if(WInt(a,"tick",-1)<0 || WInt(a,"tick",-1)>=ticks)throw new ArgumentException("Action tick outside scenario");
            WKeys(a!,"loader scene action",kind=="aim"?new[]{"kind","tick","x","y"}:new[]{"kind","tick"});
            if(data is not null && kind is ("primary" or "alt")) WRequireBinding(data,kind=="primary"?RuntimeInputKind.PrimaryUse:RuntimeInputKind.AlternateUse,true,false,false);
        }
        foreach(var a in checks) {
            string kind=a?["kind"]?.GetValue<string>() ?? throw new ArgumentException("Assertion kind is required");
            if(kind is not ("spawned" or "dummy_damaged" or "all_inactive" or "no_nonfinite" or "target_effect_at"))
                throw new NotSupportedException("Native loader scene does not yet support assertion: "+kind);
            if(kind=="target_effect_at") WValidateLifecycleAssertion(a!,data,ticks);
            else WKeys(a!,"loader scene assertion","kind");
        }
        string? configured=Environment.GetEnvironmentVariable("INFINI_MOD_SOURCE_ROOT");
        string sourceRoot=!string.IsNullOrWhiteSpace(configured)?Path.GetFullPath(configured):Path.Combine(AppContext.BaseDirectory,"native-mod");
        using var loader=WNativeLoader.Bootstrap(sandbox,sourceRoot,extraMods);
        WPrepareFullWorld();
        Terraria.Main.myPlayer=0; Terraria.Main.netMode=0; Terraria.Main.gameMenu=false;
        Terraria.Main.worldID=WInt(scenario,"worldId",12);
        Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(WInt(scenario,"seed",1));
        Terraria.Main.GameViewMatrix=new Terraria.Graphics.SpriteViewMatrix(null);
        Terraria.Main.screenWidth=1280;Terraria.Main.screenHeight=720;
        Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item()).ToArray();
        Terraria.Main.dust=Enumerable.Range(0,Terraria.Main.maxDust+1).Select(_=>new Dust()).ToArray();
        Terraria.Main.gore=Enumerable.Range(0,Terraria.Main.maxGore+1).Select(_=>new Gore()).ToArray();
        Terraria.Main.npc=Enumerable.Range(0,Terraria.Main.maxNPCs+1).Select(_=>new NPC()).ToArray();
        Terraria.Main.projectile=Enumerable.Range(0,Terraria.Main.maxProjectiles+1).Select(_=>new Projectile()).ToArray();
        Terraria.Main.combatText=Enumerable.Range(0,100).Select(_=>new CombatText{active=true}).ToArray();
        Terraria.GameContent.Creative.CreativePowerManager.Initialize();Terraria.GameInput.PlayerInput.Triggers.Initialize();
        Terraria.Main.guideItem=new Item();Terraria.Recipe.maxRecipes=0;Terraria.Main.autoSave=false;
        typeof(Terraria.Main).GetField("_achievements",TestInstance)!.SetValue(Terraria.Main.instance,new Terraria.Achievements.AchievementManager());
        Terraria.Initializers.AchievementInitializer.Load();
        foreach(string key in new[]{"Stardust","Nebula","Vortex","Solar","MoonLord","BloodMoon","Blizzard","HeatDistortion","Graveyard","Sepia","WaterDistortion","Sandstorm"})
            Terraria.Graphics.Effects.Filters.Scene[key]=new Terraria.Graphics.Effects.Filter(new Terraria.Graphics.Shaders.ScreenShaderData("headless-no-render"),Terraria.Graphics.Effects.EffectPriority.Low);
        Terraria.Main.WaveQuality=0;
        Terraria.Main.tileSolid[TileID.Dirt]=true;
        foreach(var row in scenario["tiles"]?.AsArray() ?? new JsonArray()) {
            WKeys(row!,"tile","tileX","tileY","width","height");
            int x=WInt(row,"tileX",-1),y=WInt(row,"tileY",-1),w=WInt(row,"width",0),h=WInt(row,"height",0);
            if(x<1||y<1||w<1||h<1||(long)x+w>=99||(long)y+h>=599)throw new ArgumentException("Tile rectangle outside isolated world");
            for(int tx=x;tx<x+w;tx++)for(int ty=y;ty<y+h;ty++){var tile=Terraria.Main.tile[tx,ty];tile.HasTile=true;tile.TileType=TileID.Dirt;}
        }
        foreach(var p in Terraria.Main.player)p.active=false;
        SystemLoader.OnWorldLoad();
        try {
            var owner=new Player { whoAmI=0, active=true, isControlledByFilm=true, direction=1, releaseUseItem=true };
            owner.position=new Vector2(WFloat(scenario["player"],"x",640),WFloat(scenario["player"],"y",640));
            owner.statLifeMax=owner.statLifeMax2=WInt(scenario["player"],"maxLife",100);owner.statLife=WInt(scenario["player"],"life",owner.statLifeMax);
            owner.statManaMax=owner.statManaMax2=owner.statMana=WInt(scenario["player"],"mana",200);owner.ConsumedManaCrystals=manaCrystals;
            if(owner.statLifeMax<1||owner.statLife<1||owner.statLife>owner.statLifeMax||owner.statMana<0)throw new ArgumentException("Player health/mana outside valid range");
            owner.fallStart=(int)(owner.position.Y/16);Terraria.Main.player[0]=owner;
            bool? currentWorld=null; int itemType;
            if(data is not null) {
                itemType=ModContent.ItemType<GeneratedItem>();owner.inventory[0].SetDefaults(itemType);
                if(owner.inventory[0].ModItem is not GeneratedItem host)throw new InvalidOperationException("Native Item.SetDefaults did not create registered GeneratedItem");
                currentWorld=InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.IsCurrentWorldData(data);
                if(currentWorld!=true)throw new InvalidDataException("Generated item is not scoped to the scenario worldId; input was not rewritten");
                host.SetData(data);if(!ReferenceEquals(host.Data,data))throw new InvalidDataException("GeneratedItem.SetData rejected the input");
                if(InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is null || !InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGet(data.Id,out var registered) || !ReferenceEquals(data,registered))
                    throw new InvalidOperationException("Generated item was not registered in the scenario world");
            } else {
                if(nativeItem!.Contains('/')) {
                    if(!ModContent.TryFind<ModItem>(nativeItem,out var modItem))throw new InvalidDataException("Native mod item not found: "+nativeItem);
                    itemType=modItem.Type;
                } else itemType=ResolveWorkbenchVanillaItem(nativeItem);
                owner.inventory[0].SetDefaults(itemType);
                if(!owner.inventory[0].noMelee)throw new NotSupportedException("Dedicated native loader scene does not support item-body contact; client geometry is required");
            }
            owner.selectedItem=0;
            string? targetName=scenario["dummy"]?["nativeType"]?.GetValue<string>();int targetType=NPCID.TargetDummy;
            if(!string.IsNullOrWhiteSpace(targetName)) {
                if(!ModContent.TryFind<ModNPC>(targetName,out var modNpc))throw new InvalidDataException("Native mod NPC not found: "+targetName);
                targetType=modNpc.Type;
            }
            int id=NPC.NewNPC(new EntitySource_Misc("native-loader-scene"),(int)WFloat(scenario["dummy"],"x",850),(int)WFloat(scenario["dummy"],"y",640),targetType);
            if(id<0||id>=Terraria.Main.maxNPCs)throw new InvalidOperationException("NPC.NewNPC failed");
            var dummy=Terraria.Main.npc[id];dummy.position=new Vector2(WFloat(scenario["dummy"],"x",850),WFloat(scenario["dummy"],"y",640));
            if(targetName is null){dummy.width=WInt(scenario["dummy"],"width",32);dummy.height=WInt(scenario["dummy"],"height",48);dummy.life=dummy.lifeMax=WInt(scenario["dummy"],"life",10000);dummy.aiStyle=-1;dummy.immortal=false;dummy.dontTakeDamage=false;dummy.noGravity=true;dummy.noTileCollide=true;}
            if(dummy.width<1||dummy.height<1||dummy.life<1)throw new ArgumentException("Target must have positive dimensions and life");
            // As in the established workbench scenes, an omitted aim starts at
            // target center; explicit aim actions can override it on any tick.
            Terraria.Main.mouseX=(int)(dummy.Center.X-Terraria.Main.screenPosition.X);Terraria.Main.mouseY=(int)(dummy.Center.Y-Terraria.Main.screenPosition.Y);
            int initialLife=dummy.life,spawns=0,hits=0;var frames=new JsonArray();var assertions=new JsonArray();
            var tracked=new HashSet<(int slot,int identity,int owner)>();
            using var spawnObserver=new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile),new[]{typeof(IEntitySource),typeof(float),typeof(float),typeof(float),typeof(float),typeof(int),typeof(int),typeof(float),typeof(int),typeof(float),typeof(float),typeof(float)})!,
                (WorkbenchSpawnObserver)((WorkbenchSpawnOriginal orig,IEntitySource source,float x,float y,float vx,float vy,int type,int damage,float kb,int who,float ai0,float ai1,float ai2)=>{
                    bool fromItem=source is EntitySource_ItemUse use&&ReferenceEquals(use.Entity,owner)&&ReferenceEquals(use.Item,owner.inventory[0]);
                    bool fromParent=source is EntitySource_Parent parent&&parent.Entity is Projectile p&&tracked.Contains((p.whoAmI,p.identity,p.owner));
                    int slot=orig(source,x,y,vx,vy,type,damage,kb,who,ai0,ai1,ai2);
                    if(slot>=0&&slot<Terraria.Main.maxProjectiles&&Terraria.Main.projectile[slot].active){
                        tracked.RemoveWhere(entry=>entry.slot==slot);
                        var spawnedProjectile=Terraria.Main.projectile[slot];if((fromItem||fromParent)&&spawnedProjectile.owner==owner.whoAmI){tracked.Add((slot,spawnedProjectile.identity,spawnedProjectile.owner));spawns++;}
                    }
                    return slot;
                }));
            using var hitObserver=new Hook(typeof(CombinedHooks).GetMethod(nameof(CombinedHooks.OnHitNPCWithProj))!,
                (WLoaderHitObserver)((WLoaderHitOriginal orig,Projectile projectile,NPC npc,in NPC.HitInfo hit,int damage)=>{orig(projectile,npc,in hit,damage);if(ReferenceEquals(npc,dummy)&&tracked.Contains((projectile.whoAmI,projectile.identity,projectile.owner)))hits++;}));
            MaterialClock(0);bool altHeld=false;string[] omitted=Array.Empty<string>();
            for(int tick=0;tick<ticks;tick++) {
                foreach(var a in actions.Where(a=>WInt(a,"tick",-1)==tick)) {
                    string kind=a!["kind"]!.GetValue<string>();
                    if(kind=="aim"){Terraria.Main.mouseX=(int)(WFloat(a,"x",owner.Center.X+200)-Terraria.Main.screenPosition.X);Terraria.Main.mouseY=(int)(WFloat(a,"y",owner.Center.Y)-Terraria.Main.screenPosition.Y);}
                    else if(kind=="release"){altHeld=false;owner.controlUseItem=false;owner.channel=false;if(owner.altFunctionUse==1)owner.altFunctionUse=0;}
                    else {altHeld=kind=="alt";if(altHeld && data is null && !ItemLoader.AltFunctionUse(owner.HeldItem,owner))throw new NotSupportedException("Native item has no alternate use");owner.altFunctionUse=altHeld?1:0;owner.controlUseItem=true;owner.channel=owner.HeldItem.channel;}
                }
                if(altHeld && owner.controlUseItem)owner.altFunctionUse=1;
                omitted=WLoaderTick(new WLoaderTickOps(()=>owner.Update(0),()=>{if(dummy.active)dummy.UpdateNPC(id);},()=>{for(int slot=0;slot<Terraria.Main.maxProjectiles;slot++)if(Terraria.Main.projectile[slot].active)Terraria.Main.projectile[slot].Update(slot);},null,null,null,null,null));
                var effect=RuntimeNpcEffects.GetTotals(dummy);
                frames.Add(new JsonObject{["tick"]=tick,["phase"]="post_update",["npcLife"]=dummy.life,["lifeRegen"]=dummy.lifeRegen,["vx"]=WFinite(dummy.velocity.X),["vy"]=WFinite(dummy.velocity.Y),["effectCount"]=effect.Count,["defenseDelta"]=effect.Defense,["lifeRegenPenalty"]=effect.Regen,["contactMultiplier"]=effect.Contact,["velocityRetentionPerTick"]=effect.Retention,["activeProjectiles"]=Terraria.Main.projectile.Count(p=>p.active),["playerFinite"]=WEntityFinite(owner),["npcFinite"]=WEntityFinite(dummy),["projectilesFinite"]=Terraria.Main.projectile.Where(p=>p.active).All(WEntityFinite)});
            }
            foreach(var a in checks) {
                string kind=a!["kind"]!.GetValue<string>();bool ok;
                if(kind=="target_effect_at") {
                    int t=WInt(a,"tick",-1);var f=frames[t]!;string stat=a["stat"]!.GetValue<string>();
                    string field=stat=="count"?"effectCount":stat;
                    if(field is not ("effectCount" or "lifeRegen" or "lifeRegenPenalty" or "defenseDelta" or "contactMultiplier" or "velocityRetentionPerTick" or "vx" or "vy"))throw new NotSupportedException("target_effect_at stat not supported in native loader scene: "+stat);
                    ok=Math.Abs(WReportNumber(f[field]!)-WFloat(a,"value",0))<0.00001f;
                } else ok=kind switch {"spawned"=>spawns>0,"dummy_damaged"=>hits>0&&dummy.life<initialLife,"all_inactive"=>!Terraria.Main.projectile.Any(p=>p.active),"no_nonfinite"=>frames.All(f=>f!["playerFinite"]!.GetValue<bool>()&&f["npcFinite"]!.GetValue<bool>()&&f["projectilesFinite"]!.GetValue<bool>()),_=>false};
                assertions.Add(new JsonObject{["name"]=kind,["request"]=a.DeepClone(),["status"]=ok?"passed":"failed"});
            }
            return new JsonObject{["schemaVersion"]=1,["status"]=assertions.Any(a=>a!["status"]!.GetValue<string>()=="failed")?"failed":"passed",["execution"]=new JsonObject{["backend"]="standalone-tml-loader",["fullGameParity"]=false,["contentCount"]=loader.ContentCount,["productionAssembly"]=loader.Mod.Code.Location,["additionalMod"]=loader.AdditionalMod?.Name,["additionalAssembly"]=loader.AdditionalMod?.Code.Location,["additionalMods"]=new JsonArray(loader.AdditionalMods.Select(m=>(JsonNode?)new JsonObject{["name"]=m.Name,["assembly"]=m.Code.Location}).ToArray()),["missingIfcModDependencies"]=new JsonArray(loader.MissingIfcDependencies.Select(x=>(JsonNode?)JsonValue.Create(x)).ToArray()),["limitations"]=new JsonArray("Dependency versions are not validated", "Source-root mods use reconstructed Mod.File; archive inputs retain original Mod.File", "Asset readers and client lifecycle are incomplete"),["scope"]=targetName is null?"Native IFC/tML autoload and real Player/NPC/Projectile updates with scripted input; controlled stationary NPC; not Main.Update or full game":"Native IFC/tML autoload and real Player/NPC/Projectile updates with scripted input; target uses native mod NPC defaults and AI; not Main.Update or full game",["omittedEnginePhases"]=new JsonArray(omitted.Select(x=>(JsonNode?)JsonValue.Create(x)).ToArray()),["worldRegistered"]=currentWorld},["input"]=new JsonObject{["itemPath"]=itemPath is null?null:Path.GetFullPath(itemPath),["nativeItem"]=nativeItem,["nativeItemType"]=itemType,["nativeNpc"]=targetName,["nativeNpcType"]=targetType,["scenarioPath"]=Path.GetFullPath(scenarioPath),["itemBoundary"]=itemBoundary},["snapshots"]=frames,["assertions"]=assertions,["combat"]=new JsonObject{["spawns"]=spawns,["hits"]=hits,["initialLife"]=initialLife,["finalLife"]=dummy.life}};
        } finally {SystemLoader.OnWorldUnload();}
    }
}
