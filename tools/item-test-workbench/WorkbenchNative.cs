using InfiniCrafterLocal.Common.Players;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private delegate void ContactGeometryOriginal(Item item,Player player,ref Rectangle box,ref bool disabled);
    private delegate void ContactGeometryObserver(ContactGeometryOriginal orig,Item item,Player player,ref Rectangle box,ref bool disabled);
    private delegate void ContactItemHitOriginal(Item item,Player player,NPC npc,in NPC.HitInfo hit,int damage);
    private delegate void ContactItemHitObserver(ContactItemHitOriginal orig,Item item,Player player,NPC npc,in NPC.HitInfo hit,int damage);
    private delegate int WorkbenchSpawnOriginal(IEntitySource source,float x,float y,float vx,float vy,int type,int damage,float kb,int owner,float ai0,float ai1,float ai2);
    private delegate int WorkbenchSpawnObserver(WorkbenchSpawnOriginal orig,IEntitySource source,float x,float y,float vx,float vy,int type,int damage,float kb,int owner,float ai0,float ai1,float ai2);
    private delegate void WorkbenchHitOriginal(Projectile projectile, NPC npc, in NPC.HitInfo hit, int damageDone);
    private delegate void WorkbenchHitObserver(WorkbenchHitOriginal orig, Projectile projectile, NPC npc, in NPC.HitInfo hit, int damageDone);
    public static int ResolveWorkbenchVanillaItem(string value)
    {
        if(!int.TryParse(value,out int id) && !ItemID.Search.TryGetId(value,out id)) throw new ArgumentException("Unknown vanilla item: "+value);
        if(id<=0 || id>=ItemID.Count) throw new ArgumentException("Vanilla item ID outside native registry");
        return id;
    }
    private static readonly Dictionary<int,int> WorkbenchSpawnSequences = new();
    public static void WriteWorkbenchFixtures(string directory)
    {
        Directory.CreateDirectory(directory);
        WWriteWorldFixtures(directory);
        foreach(string category in new[]{"arrow","bullet","fallen_star"}) foreach(string speedBasis in new[]{"authored_spawn","native_shot"}) {
            var weaponAmmo=WeaponAmmoFixture(category,speedBasis); weaponAmmo.Id="workbench-synthetic-ammo-"+category+"-"+speedBasis; weaponAmmo.SourceMode="test_fixture";
            weaponAmmo.RuntimeProgram.Bindings=weaponAmmo.RuntimeProgram.Bindings.Where(b=>b.Input==RuntimeInputKind.PrimaryUse).ToArray();
            weaponAmmo.RuntimeProgram.TryGetEntity("root")!.LifetimeTicks=90;
            weaponAmmo.RuntimeProgram.TryGetEntity("root")!.Collision.TileCollide=false;
            File.WriteAllText(Path.Combine(directory,"synthetic-ammo-"+category+"-"+speedBasis+".json"),SwarmWire(weaponAmmo).ToJson());
        }
        var straight = SwarmGameplayFixture();
        straight.Id = "workbench-synthetic-straight"; straight.SourceMode = "test_fixture";
        var root = straight.RuntimeProgram.TryGetEntity("root")!;
        root.LifetimeTicks = 90; root.Collision.TileCollide = false;
        root.Collision.Pierce = 1; root.Spawn.SpeedPxPerTick = 8;
        straight.RuntimeProgram.ItemUse.Channel = false;
        File.WriteAllText(Path.Combine(directory,"synthetic-straight.json"),SwarmWire(straight).ToJson());
        var npcEffect = SwarmWire(straight); npcEffect.Id="workbench-synthetic-npc-effect";
        npcEffect.RuntimeProgram.TryGetEntity("root")!.Events = new[]{NpcEffectAction(duration:30)};
        File.WriteAllText(Path.Combine(directory,"synthetic-npc-effect.json"),SwarmWire(npcEffect).ToJson());
        var wall = SwarmWire(straight); wall.Id="workbench-synthetic-wall";
        wall.RuntimeProgram.TryGetEntity("root")!.Collision.TileCollide=true;
        File.WriteAllText(Path.Combine(directory,"synthetic-wall.json"),SwarmWire(wall).ToJson());
        var mana = SwarmWire(straight); mana.Id="workbench-synthetic-mana"; mana.Gameplay.ManaCost=10;
        File.WriteAllText(Path.Combine(directory,"synthetic-mana.json"),SwarmWire(mana).ToJson());
        var charge = UnitChargeFixture(8,12,2,0);
        charge.Id = "workbench-synthetic-charge"; charge.SourceMode = "test_fixture";
        charge.RuntimeProgram.TryGetEntity("root")!.Collision.TileCollide = false;
        File.WriteAllText(Path.Combine(directory,"synthetic-charge.json"),SwarmWire(charge).ToJson());
        var alternate = RootCombatFixture(40,2,"generic");
        alternate.Id = "workbench-synthetic-alt"; alternate.SourceMode = "test_fixture";
        alternate.RuntimeProgram.Bindings = alternate.RuntimeProgram.Bindings.Where(b => b.Input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse).ToArray();
        foreach(var entity in alternate.RuntimeProgram.Entities.Where(e=>e.IsProjectileEntity)) {
            entity.Kind = RuntimeEntityKind.FreeProjectile; entity.Visual.Role = entity.VisualRole = "projectile";
            entity.Spawn.SpeedPxPerTick = 8; entity.LifetimeTicks = 90;
            entity.Collision.TileCollide = false; entity.Collision.Pierce = 1;
            entity.Movement.Name = "move_straight"; entity.Movement.Code = 0;
        }
        File.WriteAllText(Path.Combine(directory,"synthetic-alt.json"),SwarmWire(alternate).ToJson());
        var returning = MotionDefinition("""
            {"returnTrigger":{"afterTicks":12,"onOwnerRelease":false,"onTileCollision":false,"disableTileCollisionOnReturn":false},
             "seek":[{"window":{"phase":"returning","clock":"since_return","startDelayTicks":0,"durationTicks":60},
              "target":"owner_center","maxSpeed":8,"velocityLerpPerUpdate":1,"limitSpeedToDistance":true}]}
            """, e => { e["kind"]="free_projectile"; e["visualRole"]="projectile"; e["visual"]!["role"]="projectile"; e["lifetimeTicks"]=60; e["spawn"]!["speedPxPerTick"]=8; e["collision"]!["tileCollide"]=false; });
        returning.Id="workbench-synthetic-return"; returning.SourceMode="test_fixture";
        File.WriteAllText(Path.Combine(directory,"synthetic-return.json"),SwarmWire(returning).ToJson());
    }
    public static JsonObject RunWorkbench(string? itemPath, string scenarioPath, int? vanillaItemId = null, string? outputPath = null, string itemBoundary = "fresh")
    {
        if(itemBoundary is not ("fresh" or "local_cache")) throw new ArgumentException("item-boundary must be fresh or local_cache");
        GeneratedItemData? data = itemPath is null ? null : (itemBoundary=="local_cache"?GeneratedItemData.FromLocalCacheJson(File.ReadAllText(itemPath)):GeneratedItemData.FromJson(File.ReadAllText(itemPath))) ?? throw new InvalidDataException("Item rejected by actual "+(itemBoundary=="local_cache"?"GeneratedItemData.FromLocalCacheJson":"GeneratedItemData.FromJson")+": " + ContractJsonDiagnostics.LastError);
        var scenario = JsonNode.Parse(File.ReadAllText(scenarioPath))!.AsObject();
        WKeys(scenario,"scenario","ticks","seed","player","dummy","tiles","actions","assertions","playerUpdate","inventory","worldId","nativeRender","itemStack","hostiles","world","vanillaAssetRoot");
        int worldId=WInt(scenario,"worldId",0);
        WValidateAmmoInventory(scenario);
        WValidateHostiles(scenario["hostiles"]);
        WKeys(scenario["player"],"player","x","y","mana","life","maxLife","manaCrystals","direction","gravityDirection","gravitationPotion");
        string dummyMode=scenario["dummy"]?["mode"]?.GetValue<string>()??"controlled";
        if(dummyMode is not ("controlled" or "native_training_dummy"))throw new ArgumentException("dummy.mode must be controlled or native_training_dummy");
        bool nativeDummy=dummyMode=="native_training_dummy";
        if(nativeDummy)WKeys(scenario["dummy"],"native training dummy","mode","tileX","tileY");else WKeys(scenario["dummy"],"dummy","mode","x","y","width","height","life","noTileCollide","nativeType","defense","vx","vy");
        WValidateTarget(scenario["dummy"]);
        bool dummyNoTileCollide=scenario["dummy"]?["noTileCollide"]?.GetValue<bool>() ?? true;
        foreach(var rect in scenario["tiles"]?.AsArray() ?? new JsonArray()) WKeys(rect,"tile rectangle","tileX","tileY","width","height");
        string playerUpdate=scenario["playerUpdate"]?.GetValue<string>() ?? "item_check";
        if(playerUpdate is not ("item_check" or "full" or "client" or "client_hybrid" or "client_vfx")) throw new ArgumentException("playerUpdate must be item_check, full, client, client_hybrid, or client_vfx");
        bool renderClient=playerUpdate=="client_vfx";
        bool drawPlacedBodies=scenario["nativeRender"]?["drawPlacedBodies"]?.GetValue<bool>()??false;
        bool drawArtwork=scenario["nativeRender"]?["drawArtwork"]?.GetValue<bool>()??false;
        bool drawPlayer=scenario["nativeRender"]?["drawPlayer"]?.GetValue<bool>()??false;
        bool drawZombie=scenario["nativeRender"]?["drawZombie"]?.GetValue<bool>()??false;
        bool drawProjectileVfx=scenario["nativeRender"]?["drawProjectileVfx"]?.GetValue<bool>()??false;
        bool historyRibbon=data?.VfxManifest.Slots.Any(s=>s.RendererKind=="historyRibbon")==true;
        bool historyTrail=data?.VfxManifest.Slots.Any(s=>s.RendererKind=="historyTrail")==true;
        if(drawProjectileVfx && (!renderClient || drawArtwork || data is null))throw new ArgumentException("drawProjectileVfx requires a generated item, client_vfx and drawArtwork=false; artwork mode owns its full PreDraw");
        bool drawVanillaProjectiles=scenario["nativeRender"]?["drawVanillaProjectiles"]?.GetValue<bool>()??false;
        if(drawVanillaProjectiles && (data is not null || !drawPlayer))throw new NotSupportedException("drawVanillaProjectiles requires a vanilla item and drawPlayer=true");
        if((scenario["nativeRender"]?["drawNativeDust"]?.GetValue<bool>()??false)&&!drawPlayer&&!drawProjectileVfx)throw new ArgumentException("drawNativeDust requires drawPlayer or drawProjectileVfx with verified native assets");
        if(nativeDummy&&!drawPlayer)throw new ArgumentException("native_training_dummy requires nativeRender.drawPlayer=true");
        if(drawZombie && (!renderClient || !drawPlayer || nativeDummy || scenario["dummy"]?["nativeType"]?.GetValue<string>()!="zombie"))
            throw new ArgumentException("drawZombie requires client_vfx, drawPlayer=true and dummy.nativeType=zombie");
        if(!nativeDummy&&scenario["nativeRender"]?["dummyAssetRoot"] is not null)throw new ArgumentException("dummyAssetRoot requires native_training_dummy");
        if(drawPlayer&&!drawArtwork)throw new ArgumentException("drawPlayer requires drawArtwork=true");
        if(!drawPlayer&&!drawProjectileVfx&&scenario["nativeRender"]?["playerAssetRoot"] is not null)throw new ArgumentException("playerAssetRoot requires drawPlayer or drawProjectileVfx");
        if(drawPlacedBodies && (!drawArtwork || scenario["world"] is null))throw new ArgumentException("drawPlacedBodies requires drawArtwork and explicit world scene");
        if(drawArtwork && !renderClient) throw new ArgumentException("drawArtwork requires client_vfx");
        if(!drawArtwork && scenario["nativeRender"]?["artworkFiles"] is not null) throw new ArgumentException("artworkFiles requires drawArtwork=true");
        bool hybridClient=playerUpdate is "client_hybrid" or "client_vfx";
        bool clientPlayer=playerUpdate is "client" or "client_hybrid" or "client_vfx";
        int initialDirection=WInt(scenario["player"],"direction",1);
        int initialGravity=WInt(scenario["player"],"gravityDirection",1);
        bool gravityPotion=scenario["player"]?["gravitationPotion"]?.GetValue<bool>()??false;
        if(initialGravity is not (-1 or 1) || initialGravity==-1 && !gravityPotion)throw new ArgumentException("gravityDirection must be +/-1; inverted gravity requires explicit gravitationPotion=true");
        if(initialDirection is not (-1 or 1)) throw new ArgumentException("player.direction must be -1 or1");
        if(data is null && drawArtwork && !drawPlayer)throw new NotSupportedException("Vanilla artwork requires actual native drawPlayer; partial generated layer cannot substitute it");
        if(scenario["vanillaAssetRoot"] is not null && (data is not null || !clientPlayer))throw new ArgumentException("vanillaAssetRoot applies only to vanilla client/client_hybrid contact");
        bool fullPlayer=playerUpdate is "full" or "client" or "client_hybrid" or "client_vfx";
        using var graphics=clientPlayer?new WorkbenchGraphicsContext(Path.Combine(AppContext.BaseDirectory,"native-assets","GeneratedItem.png"),outputPath is null?null:Path.Combine(Path.GetDirectoryName(Path.GetFullPath(outputPath))!,"native-proxy-preview.png")):null;
        foreach(string actor in new[]{"player","dummy"}) foreach(string coordinate in new[]{"x","y"}) WFloat(scenario[actor],coordinate,0);
        int manaCrystals=WInt(scenario["player"],"manaCrystals",9);
        if(manaCrystals<0 || manaCrystals>9) throw new ArgumentException("manaCrystals must be 0..9");
        if(fullPlayer && WInt(scenario["player"],"maxLife",100)!=100) throw new NotSupportedException("Full player currently uses native initial maxLife100; custom life-crystal progression not yet admitted");
        int ticks = WInt(scenario, "ticks", 120), seed = WInt(scenario, "seed", 1);
        if (ticks < 1 || ticks > 14400) throw new ArgumentException("ticks must be 1..14400 (four minutes at 60 ticks/s)");
        if(WInt(scenario,"itemStack",1) is < 1 or > 9999) throw new ArgumentException("itemStack must be 1..9999");
        if(renderClient && (ticks>600 || scenario["nativeRender"] is not JsonObject || outputPath is null)) throw new ArgumentException("client_vfx requires nativeRender settings, output path, and at most600 ticks");
        if(!renderClient && scenario["nativeRender"] is not null) throw new ArgumentException("nativeRender requires playerUpdate client_vfx");
        if(WInt(scenario["player"],"mana",200) is < 0 or > 400) throw new ArgumentException("player.mana must be0..400");
        if(fullPlayer && WInt(scenario["player"],"mana",200)>20+20*manaCrystals) throw new ArgumentException("player.mana exceeds native mana-crystal capacity");
        if(WInt(scenario["player"],"maxLife",100) is < 1 or > 500) throw new ArgumentException("player.maxLife must be 1..500");
        if(WInt(scenario["dummy"],"width",32) is < 1 or > 512 || WInt(scenario["dummy"],"height",48) is < 1 or > 512 || WInt(scenario["dummy"],"life",10000) is < 1 or > 10000000)
            throw new ArgumentException("dummy requires width/height1..512 and life1..10000000");
        WValidateWorld(scenario,fullPlayer,clientPlayer);
        var actions = scenario["actions"]?.AsArray() ?? throw new ArgumentException("actions array is required");
        foreach(var action in actions) {
            string kind=action?["kind"]?.GetValue<string>() ?? throw new ArgumentException("Action kind required");
            if(kind=="aim") { WKeys(action,"aim action","kind","tick","x","y"); if(action!["x"]==null||action["y"]==null) throw new ArgumentException("aim requires x and y"); if(Math.Abs(WFloat(action,"x",0))>1000000 || Math.Abs(WFloat(action,"y",0))>1000000) throw new ArgumentException("Aim coordinates must be within +/-1000000px"); }
            else if(clientPlayer && !drawPlayer && kind is "select_slot" or "equip" or "unequip" or "vanity") throw new NotSupportedException("Client item mode does not yet load native empty-item/equipment presentation contexts");
            else if(kind=="select_slot") { WKeys(action,"slot action","kind","tick","slot"); if(!fullPlayer || WInt(action,"slot",-1) is < 0 or > 1) throw new ArgumentException("select_slot requires full player and slot0 or1"); }
            else if(kind is "equip" or "unequip" or "vanity") { WKeys(action,"equipment action","kind","tick"); if(!fullPlayer || data is null || (!data.Accessory.Enabled && !data.Armor.Enabled) || data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped)?.UsePolicy.Action.Kind!=RuntimeBindingAction.EquipPassive) throw new NotSupportedException("Equipment commands require full player and generated passive accessory or armor"); }
            else if(kind is "tile_target" or "break_tile") WValidateWorldAction(action!,scenario);
            else if(kind=="controls") WValidateControls(action!,fullPlayer);
            else if(WReactionAction(kind)) WValidateReactionAction(action!,fullPlayer,clientPlayer);
            else if(kind is "primary" or "alt" or "release") WKeys(action,"input action","kind","tick");
            else throw new ArgumentException("Unknown action kind: "+kind);
        }
        foreach(var check in scenario["assertions"]?.AsArray() ?? new JsonArray()) {
            string kind=check?["kind"]?.GetValue<string>() ?? throw new ArgumentException("Assertion kind required");
            if(WLifecycleKind(kind)) WValidateLifecycleAssertion(check!,data,ticks);
            else if(kind=="placed_body_draw_count_at_least") {WKeys(check,"placed-body draw assertion","kind","minimum");if(!drawPlacedBodies || WInt(check,"minimum",0)<1)throw new ArgumentException("placed_body_draw_count_at_least requires drawPlacedBodies and positive minimum");}
            else if(WWorldAssertionKind(kind)) WValidateWorldAssertion(check!,scenario,ticks);
            else if(kind is "inventory_stack" or "ammo_consumed_count" or "ammo_source_spawn_count") { WKeys(check,"ammo assertion",kind=="inventory_stack"?new[]{"kind","slot","itemId","value"}:new[]{"kind","itemId","value"}); if(check!["value"] is null || check["itemId"] is null || WInt(check,"value",-1)<0 || WInt(check,"itemId",-1)<0 || WInt(check,"itemId",0)>=ItemID.Count || (kind=="inventory_stack" && WInt(check,"slot",-1) is < 0 or > 57)) throw new ArgumentException("Ammo assertion requires valid itemId, nonnegative value and inventory slot"); }
            else if(kind is "player_stat_at" or "player_stat_never_above") { WKeys(check,"player stat assertion",kind=="player_stat_at"?new[]{"kind","stat","tick","value"}:new[]{"kind","stat","value"}); if(check!["stat"]?.GetValue<string>() is not ("maxMana" or "manaCost" or "maxLife" or "defense" or "moveSpeed" or "lifeRegen" or "genericCrit" or "generatedBuffTicks")) throw new ArgumentException("Unsupported player stat"); if(check["value"] is null) throw new ArgumentException("Player stat assertion requires value"); WFloat(check,"value",0); if(kind=="player_stat_at" && (WInt(check,"tick",-1)<0 || WInt(check,"tick",-1)>=ticks)) throw new ArgumentException("Player stat assertion tick outside scenario"); }
            else if(kind is "native_buff_seen" or "native_projectile_seen" or "native_projectile_active") { WKeys(check,"assertion","kind","id"); if(WInt(check,"id",0)<=0) throw new ArgumentException(kind+" requires positive id"); }
            else if(kind is "hit_count_at_least" or "jump_boost_seen") { WKeys(check,"assertion","kind","minimum"); if(check!["minimum"]==null) throw new ArgumentException("assertion requires minimum"); WFloat(check,"minimum",0); }
            else if(kind is "spawn_count" or "mana_equals" or "life_equals" or "mana_debited" or "direct_healing" or "teleport_count" or "jump_boost_equals" or "item_hit_count" or "projectile_hit_count") { WKeys(check,"assertion","kind","value"); if(check!["value"]==null) throw new ArgumentException(kind+" requires value"); WFloat(check,"value",0); }
            else if(kind is "spawned" or "dummy_damaged" or "all_inactive" or "natural_expiry" or "released" or "returned" or "no_nonfinite" or "tile_collision" or "dummy_undamaged" or "generated_buff_seen" or "generated_buff_expired" or "mobility_cooldown_expired" or "item_contact_observed" or "no_item_contact") WKeys(check,"assertion","kind");
            else throw new ArgumentException("Unknown assertion kind: "+kind);
        }
        if (actions.Count > 256) throw new ArgumentException("At most 256 scripted actions");
        foreach (var action in actions) if (WInt(action,"tick",-1) < 0 || WInt(action,"tick",-1) >= ticks) throw new ArgumentException("Every action tick must be within the scenario");
        string[] testedInputs=actions.Select(a=>a!["kind"]!.GetValue<string>()).Where(k=>k is "primary" or "alt" or "equip")
            .Select(k=>k=="equip"?RuntimeInputKind.Equipped:k=="primary"?RuntimeInputKind.PrimaryUse:RuntimeInputKind.AlternateUse).Distinct().ToArray();
        if(hybridClient && !renderClient && data is not null && data.VfxManifest.Slots.Length!=0) throw new NotSupportedException("Client hybrid currently requires an empty VFX manifest; global VFX update/render lifecycle is not validated");
        if(hybridClient && data is not null) WValidateHybridEvents(data,renderClient);
        if(renderClient && data is not null) {
            if(data.VfxManifest.Slots.Any(s=>s.RendererKind is not ("libraryParticle" or "soundCue" or "spriteElement" or "texturedPath" or "impactSprite" or "impactRing" or "historyRibbon" or "historyTrail")))
                throw new NotSupportedException("client_vfx requires an explicitly admitted original renderer; unsupported VFX renderer kind");
            foreach(var slot in data.VfxManifest.Slots.Where(s=>s.RendererKind=="historyTrail")) WValidateHistoryTrail(slot,drawPlayer);
            if(data.VfxManifest.Slots.Any(s=>s.RendererKind is "spriteElement" or "texturedPath" or "impactSprite") && !drawArtwork)
                throw new NotSupportedException("Authored material/impact VFX require drawArtwork=true with every exact publication PNG");
            if(historyRibbon && !drawPlayer && !drawProjectileVfx)
                throw new NotSupportedException("historyRibbon requires drawPlayer or drawProjectileVfx with original MagicPixel and live native history");
            if(data.VfxManifest.Slots.Any(s=>s.RendererKind=="impactRing") && (!(drawPlayer||drawProjectileVfx) || !(scenario["nativeRender"]?["drawNativeDust"]?.GetValue<bool>()??false)))
                throw new NotSupportedException("impactRing requires drawPlayer or drawProjectileVfx, plus drawNativeDust=true and original MagicPixel/Dust assets");
        }
        if(clientPlayer && data?.RuntimeProgram.BindingForInput(RuntimeInputKind.Hold)?.UsePolicy.Action.Kind==RuntimeBindingAction.SpawnEntity) throw new NotSupportedException("Client item contact mode currently refuses held projectile spawning");
        if(data is not null) {
        if (data.Gameplay.AmmoCategory.Length != 0 || (data.RuntimeProgram.WeaponAmmo is { } ammoSpec && ammoSpec.AmmoCategory is not ("arrow" or "bullet" or "flare" or "fallen_star")))
            throw new NotSupportedException("Only generated weapons with vanilla arrow/bullet/flare/fallen-star ammo are admitted; generated ammo items and other categories remain unsupported");
        if (!hybridClient && data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)?.Events.Length > 0 && !(fullPlayer && WEquipmentBodyEventsSupported(data)))
            throw new NotSupportedException("Item-body events require complete item update hooks; projectile-only scene refuses them");
        if (!fullPlayer && data.RuntimeProgram.HeldEffectGroupId is not null)
            throw new NotSupportedException("Held generated buffs require full Player.Update/ModPlayer effect and expiry clocks");
        if (!fullPlayer && (data.Gameplay.PickPower>0 || data.Gameplay.AxePower>0 || data.Gameplay.HammerPower>0))
            throw new NotSupportedException("Mining/tool powers require the full player equipment/reset and mining-world lifecycle");
        if(data.RuntimeProgram.Entities.Any(e=>e.Movement.Code==18))
            throw new NotSupportedException("Legacy whip tag gameplay requires registered GeneratedWhipTagGlobalNPC callbacks");
        if (!fullPlayer && data.RuntimeProgram.Entities.Any(e=>e.NativeSentry==true))
            throw new NotSupportedException("Native sentry ownership/count maintenance requires the full player update lifecycle");
        if (data.RuntimeProgram.Entities.SelectMany(e=>e.Events).Any(e=>e.ActionCode==RuntimeEventActionCode.MoveOwner
            || e.ActionCode==RuntimeEventActionCode.Pull && e.Mode is "owner_to_target" or "both"))
            throw new NotSupportedException("Owner movement/pull events require native player integration and mobility cooldown clocks");
        foreach(var input in testedInputs) {
            if(data.RuntimeProgram.BindingForInput(input)?.UsePolicy.Action.Kind==RuntimeBindingAction.PlaceItem && scenario["world"] is null) throw new NotSupportedException("Placement requires explicit world scene with native ledger lifecycle");
            WRequireBinding(data,input,fullPlayer,clientPlayer,hybridClient,renderClient);
        }
        }
        if (scenario["assertions"] is not JsonArray { Count: > 0 }) throw new ArgumentException("At least one explicit assertion is required");
        var frames = new JsonArray(); var assertions = new JsonArray(); var events = new JsonArray();
        var report = new JsonObject {
            ["schemaVersion"] = 1, ["status"] = "running",
            ["timeline"]=new JsonObject { ["requestedTicks"]=ticks,["completedTicks"]=0,["complete"]=false },
            ["coverage"]=new JsonObject { ["wholeItemValidated"]=false,["verdictScope"]="Only the supplied scenario and explicit assertions; untested bindings are not validated",
                ["testedInputs"]=new JsonArray(testedInputs.Select(x=>(JsonNode?)JsonValue.Create(x)).ToArray()),
                ["ammoScope"]="Vanilla arrow/bullet/flare/fallen-star inventory and native PickAmmo through ItemCheck; spawn source identifies selected ammo. Consumption callback count is not itself stack debit; pair with inventory_stack. No generated-ammo-as-item or random conservation accessory coverage",
                ["equipmentControlScope"]="Single generated accessory or head/body/legs armor; commands move the same instance between inventory0 and its native functional/vanity slot; native Player.Update applies/resets effects. Scripted damage/death stimuli use native Player.Hurt and Player.StrikeNPCDirect; no inventory UI, armor-set or multi-item certification",
                ["untestedBindings"]=new JsonArray((data?.RuntimeProgram.Bindings ?? Array.Empty<RuntimeBindingSpec>()).Where(b=>!testedInputs.Contains(b.Input)).Select(b=>(JsonNode?)new JsonObject { ["id"]=b.Id,["input"]=b.Input,["action"]=b.UsePolicy.Action.Kind,["status"]=WBindingRefusal(data!,b.Input,fullPlayer,clientPlayer,hybridClient,renderClient) is null?"untested":"unsupported",["reason"]=WBindingRefusal(data!,b.Input,fullPlayer,clientPlayer,hybridClient,renderClient) }).ToArray()) },
            ["execution"] = new JsonObject {
                ["backend"] = renderClient?"native-client-vfx-update":hybridClient?"native-client-hybrid-update":clientPlayer?"native-client-item-update":fullPlayer?"native-player-update":"native-projectile-update", ["scope"] = renderClient?"Native player/item/projectile updates and explicitly recorded original draw entrypoints; not complete Terraria world/client parity":fullPlayer?"native Player.Update and registered mod-player effects with projectile/NPC update; no rendering or complete game loop":"projectile-world; native item-check and projectile/NPC update; not complete world parity", ["fullGameParity"] = false,
                ["nativeMethods"] = data is null ? new JsonArray("Item.SetDefaults",fullPlayer?"Player.Update":"Player.ItemCheck","Projectile.Update","NPC.UpdateNPC","Projectile.NewProjectile","CombinedHooks.OnHitNPCWithProj","Projectile.Kill") : new JsonArray(itemBoundary=="local_cache"?"GeneratedItemData.FromLocalCacheJson":"GeneratedItemData.FromJson", fullPlayer?"Player.Update":"Player.ItemCheck", "GeneratedItem.CanUseItem", "GeneratedItem.Shoot", "GeneratedProjectile.SpawnRuntimeEntity", "Projectile.Update", "NPC.UpdateNPC", "RuntimeHitNpcGeneration.OnSpawn (scene creation)", "NPCLoader registered RuntimeHitNpcGeneration (update/hit hooks, when invoked by the scene)", "Projectile.NewProjectile", "RuntimeDelayedActionScheduler.Update"),
                ["interventions"] = new JsonArray(fullPlayer?"Isolated 100x600 native tilemap, surface80/rock200; actual native player physics; NPC AI disabled; no world generation":"Isolated 100x100 native tilemap; fixed player and target dummy; no world generation", data is null?"Vanilla item instantiated with actual Item.SetDefaults; no generated item substituted":"Actual GeneratedItem and GeneratedProjectile registered through native loaders; selected production root-combat bridge loaded, not all mod content", hybridClient?"Client Player.Update and generated Projectile.Update/delayed actions use actual client branches; only stationary TargetDummy maintenance remains dedicated, with explicit phase flags":clientPlayer?"Client Player.Update uses real offscreen proxy texture; dedicated NPC/projectile maintenance remains separate, with explicit per-phase flags":fullPlayer?"Native Player.Update with film-scripted controls (native local keyboard/input polling skipped), registered InfiniCraftPlayer and native accessory-slot context; CPU-only filters/achievement context; no GPU":"Use commands set native controls; actual native ResetProjectileCaches/UpdateProjectileCaches and Player.ItemCheck run every tick, with production GeneratedRootCombatSystem bridge loaded", "Combat text pool is full to suppress font/GPU use; combat remains native"),
                ["unsupported"] = new JsonArray(drawPlayer?"Terraria tile/NPC/world and native dust sprite rendering; non-default character appearances and vanilla equipment atlases; full Main.Draw":drawArtwork?"Terraria world/player/NPC/dust sprite rendering; full projectile PreDraw unavailable without genuine MagicPixel asset":clientPlayer?"Terraria world rendering and custom per-instance generated art (only actual native proxy texture is loaded)":"GPU rendering and generated assets", "Multiplayer/network timing", fullPlayer?"NPC AI deliberately disabled; terrain/world systems and equipment scenarios are not fully simulated":"Full Player.Update (movement, regen, buff/equipment/environment clocks); NPC AI deliberately disabled for stationary dummy", drawPlayer?"VFX renderer kinds outside the explicit admission list, runtime_geometry/no_asset entity admission, Terraria world/NPCs/dust rendering, sound audibility, complete Main.Draw and networking":drawArtwork?"VFX renderer kinds outside the explicit admission list, runtime_geometry/no_asset entity rendering, Terraria scene, sound audibility, complete Projectile.PreDraw/Main.Draw, networking":renderClient?"VFX renderer kinds outside the explicit admission list, unrendered authored item/projectile art and Terraria scene, sound audibility, complete Main.Draw, networking":hybridClient?"Nonempty VFX manifests, body events outside on_use/on_hit/on_crit spawn and hit healing/NPC effects, projectile event effects outside explicit admission, held spawning, vanilla items and equipment presentation without full native player artwork":clientPlayer?"Projectile hybrids/held spawning, vanilla items, item-body events and equipment presentation without full native player artwork":fullPlayer?"Generated ammo items and non-arrow/bullet/flare/fallen-star ammo, dedicated item-body contact, armor sets, prefixes and multi-accessory combinations":"Generated ammo items and non-arrow/bullet/flare/fallen-star ammo, item-body contact, held/equipped effects, prefixes and equipment bonuses") },
            ["input"] = new JsonObject { ["boundary"]=data is null?"Item.SetDefaults":itemBoundary=="local_cache"?"GeneratedItemData.FromLocalCacheJson":"GeneratedItemData.FromJson",["localCacheReadReceipt"]=System.Text.Json.JsonSerializer.SerializeToNode(data?.LocalCacheReadReceipt ?? Array.Empty<string>()), ["source"]=data is null?"vanilla":"generated", ["path"] = itemPath is null?null:Path.GetFullPath(itemPath), ["sha256"] = itemPath is null?null:Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(itemPath))).ToLowerInvariant(), ["nativeItemId"]=vanillaItemId, ["nativeItemName"]=vanillaItemId.HasValue?ItemID.Search.GetName(vanillaItemId.Value):null, ["scenario"] = Path.GetFullPath(scenarioPath), ["scenarioSha256"] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(scenarioPath))).ToLowerInvariant(), ["seed"] = seed, ["itemId"] = data?.Id },
            ["snapshots"] = frames, ["assertions"] = assertions
        };
        if(clientPlayer) {
            var provenance=(JsonObject)graphics!.Provenance.DeepClone();provenance["nativeClientBranch"]=true;provenance["netMode"]=0;
            provenance["phaseFlags"]=new JsonObject{["Player.Update.dedServ"]=false,["NPC.UpdateNPC.dedServ"]=!nativeDummy,["Projectile.Update.dedServ"]=!hybridClient,["RuntimeDelayedActionScheduler.Update.dedServ"]=!hybridClient};
            provenance["scope"]=hybridClient?"Actual client Player.Update, contact and generated Projectile.Update/delayed actions; dedicated-server TargetDummy maintenance; no complete Terraria client/world renderer":"Actual client Player.Update including ItemCheck, use-style, native contact geometry and hit; dedicated-server TargetDummy maintenance; no complete Terraria client/world renderer";
            provenance["selectedItemInitialization"]="Actual HeldItem.Clone initializes lastVisualizedSelectedItem once, replacing bookkeeping omitted by film-scripted input; native ItemCheck maintains it thereafter";
            report["execution"]!["clientGraphics"]=provenance;
            report["execution"]!["scope"]=provenance["scope"]!.DeepClone();
            foreach(string method in new[]{"Item.GetDrawHitbox","Player.ItemCheck_ApplyUseStyle","ItemLoader.UseItemHitbox","Player.ItemCheck_MeleeHitNPCs","ItemLoader.OnHitNPC"}) report["execution"]!["nativeMethods"]!.AsArray().Add((JsonNode?)JsonValue.Create(method));
        }
        if(nativeDummy){
            report["execution"]!["scope"]="Actual client Player.Update, generated Projectile.Update and native training dummy NPC.UpdateNPC/AI92/FindFrame; original native object tile drawing plus supported player/item/VFX layers, not complete world/Main.Draw";
            report["execution"]!["interventions"]=new JsonArray("Controlled 100x600 native tilemap with explicit floor; no world generation", "Native TileObject placement and TETrainingDummy activation; untouched NPC488 defaults and dynamic slot", "Native tile entity UpdateStart/Update/UpdateEnd after projectile phase; world spread/wiring outside scope", "Film-scripted player input and production generated-item initialization; combat text pool full to avoid font rendering");
            report["execution"]!["unsupported"]=new JsonArray("Solid terrain/world artwork, native dust sprites, complete Main.Draw and networking", "Other NPC AI, target reactivation/respawn scenarios, other tile entities", "Non-default player appearances and vanilla equipment atlases, authored VFX outside the explicit renderer admission list");
            report["execution"]!["clientGraphics"]!["scope"]=report["execution"]!["scope"]!.DeepClone();
        }
        report["execution"]!["vfxCoverage"]=new JsonObject{["authoredRendererKinds"]=new JsonArray((data?.VfxManifest.Slots ?? Array.Empty<VfxSlotSpec>()).Select(x=>x.RendererKind).Distinct().Select(x=>(JsonNode?)JsonValue.Create(x)).ToArray()),["globalVfxUpdateExecuted"]=renderClient,["vfxRenderingValidated"]=false,["callbackDispatch"]="Canonical callbacks run normally when triggered; individual VFX slot execution is not separately asserted"};
        if(scenario["hostiles"] is JsonArray {Count:>0})report["execution"]!["controlledHostiles"]=new JsonObject{
            ["artworkRendered"]=false,["NPC.UpdateNPC.dedServ"]=true,
            ["scope"]="Native controlled NPC update with dedicated presentation branch; prior dedServ restored before projectile/damage/render phases. NPC AI remains disabled by scene setup; no client NPC FindFrame or artwork claim"};
        var terrain = new JsonArray();
        foreach (var rect in scenario["tiles"]?.AsArray() ?? new JsonArray()) {
            int x=WInt(rect,"tileX",-1), y=WInt(rect,"tileY",-1), width=WInt(rect,"width",0), height=WInt(rect,"height",0);
            if (x<1 || y<1 || width<1 || height<1 || x+width>=99 || y+height>=(fullPlayer?599:99)) throw new ArgumentException("Tile rectangles must fit inside the declared native tilemap margin");
            terrain.Add(new JsonObject { ["x"]=x*16,["y"]=y*16,["width"]=width*16,["height"]=height*16,["nativeTileType"]=TileID.Dirt });
        }
        report["scene"] = new JsonObject { ["worldWidth"]=1600,["worldHeight"]=fullPlayer?9600:1600,["worldSurfaceTiles"]=fullPlayer?80:null,["rockLayerTiles"]=fullPlayer?200:null,["tiles"]=terrain };
        WorkbenchSpawnSequences.Clear(); WSourceParentIds.Clear();
        int spawned = 0, hitCount = 0, itemHitCount=0, contactQueries=0, naturalExpiries = 0, tileCollisions = 0, manaPaid=0, healed=0, teleports=0, heldNativeTicks=0;
        WithPersistenceTilemap((_, worldLedger) => {
            using var scope = new SwarmRuntimeScope();
            using var worldIdentity=new WWorldIdentity(worldId);
            report["scene"]!["worldId"]=Terraria.Main.worldID;
            report["scene"]!["sourceWorldId"]=data?.RecipeMeta.WorldId;
            report["scene"]!["sourceWorldScoped"]=data?.RecipeMeta.WorldScoped;
            report["scene"]!["currentWorldSource"]=data is null?null:InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.IsCurrentWorldData(data);
            typeof(Terraria.Main).GetMethod("Initialize_TileAndNPCData1",PersistenceStatic)!.Invoke(null,null);
            foreach(var player in Terraria.Main.player) player.active=false;
            if(fullPlayer) WPrepareFullWorld();
            Terraria.Main.tileSolid[TileID.Dirt] = true;
            foreach (var rect in terrain) {
                int x=WInt(rect,"x",0)/16,y=WInt(rect,"y",0)/16,w=WInt(rect,"width",0)/16,h=WInt(rect,"height",0)/16;
                for(int tx=x;tx<x+w;tx++) for(int ty=y;ty<y+h;ty++) { var tile=Terraria.Main.tile[tx,ty]; tile.HasTile=true; tile.TileType=TileID.Dirt; }
            }
            WithPlayer((owner, modPlayer) => {
                Terraria.Main.player[0] = owner; owner.whoAmI = 0; owner.active = true; owner.direction = initialDirection; owner.gravDir=initialGravity; if(gravityPotion)owner.AddBuff(BuffID.Gravitation,ticks+1);
                report["scene"]!["activePlayerCount"]=Terraria.Main.player.Count(p=>p.active);
                if(Terraria.Main.player.Count(p=>p.active)!=1) throw new InvalidOperationException("Workbench must contain exactly one active player");
                owner.position = new Vector2(WFloat(scenario["player"], "x", fullPlayer?800:640), WFloat(scenario["player"], "y", fullPlayer?700:640));
                owner.statLifeMax = owner.statLifeMax2 = WInt(scenario["player"], "maxLife", 100);
                owner.statLife = WInt(scenario["player"], "life", owner.statLifeMax);
                if(owner.statLife<1 || owner.statLife>owner.statLifeMax) throw new ArgumentException("Player life must be positive and <= maxLife");
                owner.statMana = owner.statManaMax = owner.statManaMax2 = WInt(scenario["player"], "mana", 200);
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed);
                Terraria.Main.SceneMetrics = new SceneMetrics();
                Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null);
                Terraria.Main.screenWidth = 1280; Terraria.Main.screenHeight = 720;
                Lighting.Initialize();
                Terraria.Main.screenPosition = Vector2.Zero;
                Terraria.Main.mouseX = (int)owner.Center.X + 200; Terraria.Main.mouseY = (int)owner.Center.Y;
                var item = data is null ? new Item(vanillaItemId!.Value) : new Item { stack=1 };
                GeneratedItem? host = null;
                if(data is not null) {
                    host=AttachItem(WCreateItemHost(data),item,data);
                    int registeredItemType=(int)typeof(ItemLoader).GetMethod("Register",PersistenceStatic)!.Invoke(null,new object[]{host})!;
                    item.type=registeredItemType; WRegisterItemSingleton(host);
                }
                WValidateVanillaPerformance(item,data,clientPlayer);
                owner.inventory[0]=item; owner.selectedItem=0; owner.releaseUseItem=true;
                using var npcGlobals=new WNpcGlobals();
                NPC dummy=null!;int initialLife=0;
                if(!nativeDummy){dummy = Terraria.Main.npc[0]; dummy.SetDefaults(scenario["dummy"]?["nativeType"]?.GetValue<string>()=="zombie"?NPCID.Zombie:NPCID.TargetDummy);
                dummy.active = true; dummy.dontTakeDamage = false; dummy.immortal = false;
                dummy.aiStyle = -1; dummy.noGravity = true; dummy.noTileCollide = dummyNoTileCollide; dummy.knockBackResist = 0;
                dummy.position = new Vector2(WFloat(scenario["dummy"], "x", fullPlayer?1000:850), WFloat(scenario["dummy"], "y", fullPlayer?700:640));
                dummy.width = WInt(scenario["dummy"], "width", 32); dummy.height = WInt(scenario["dummy"], "height", 48);
                dummy.life = dummy.lifeMax = WInt(scenario["dummy"], "life", 10000);initialLife=dummy.life;WConfigureTarget(dummy,scenario["dummy"]);}
                RuntimeHitNpcGeneration.Clear();
                WInitializeHostiles(scenario["hostiles"]);
                if(!nativeDummy)new RuntimeHitNpcGeneration().OnSpawn(dummy,owner.GetSource_Misc("item-test-workbench-scene"));
                System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(ProjectileID.Sets).TypeHandle);
                var template = Attach(new Projectile());
                int registeredType = (int)typeof(ProjectileLoader).GetMethod("Register", PersistenceStatic)!.Invoke(null,new object[]{template})!;
                template.Projectile.type = registeredType;
                typeof(ContentInstance<GeneratedProjectile>).GetProperty("Instance")!.SetValue(null,template);
                System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(ItemID.Sets).TypeHandle);
                System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(AmmoID.Sets).TypeHandle);
                System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(Terraria.GameContent.Prefixes.PrefixLegacy.ItemSets).TypeHandle);
                WInitializeNestedStatics(typeof(TileID));
                if(renderClient) WInitializeNestedStatics(typeof(WallID));
                WInitializeNestedStatics(typeof(BuffID));
                var pylonsField = typeof(Terraria.Main).GetField("PylonSystem",PersistenceStatic)!;
                if (pylonsField.GetValue(null) is null) pylonsField.SetValue(null,Activator.CreateInstance(pylonsField.FieldType));
                var pylons = pylonsField.GetValue(null)!;
                var pylonMetrics = pylons.GetType().GetField("_sceneMetrics",TestInstance)!;
                if (pylonMetrics.GetValue(pylons) is null) pylonMetrics.SetValue(pylons,new SceneMetrics());
                SetFactory.ResizeArrays(false);
                typeof(ItemLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{false});
                typeof(ProjectileLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{false});
                Terraria.ObjectData.TileObjectData.Initialize();
                typeof(TileLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{false});
                if(renderClient) typeof(WallLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{false});
                typeof(BuffLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,null);
                using var equipmentRegistration=new WEquipmentRegistration(host);
                template.SetStaticDefaults(); if(host is not null){int nativeType=item.type;host.SetStaticDefaults();string expectedClone=data!.CloneForItemInstance().ToJson();item=new Item();owner.inventory[0]=item;item.SetDefaults(nativeType);host=(GeneratedItem)item.ModItem;if(host.Data.ToJson()!=expectedClone)throw new InvalidOperationException("Native Item.SetDefaults clone differs from canonical CloneForItemInstance");host.SetData(data);if(host.Data.ToJson()!=data.ToJson())throw new InvalidOperationException("Native GeneratedItem.SetData changed canonical definition");report["execution"]!["itemInitialization"]=new JsonObject{["method"]="Item.SetDefaults(registeredType) -> native ResetStats and ItemLoader/GeneratedItem defaults -> GeneratedItem.SetData (production craft creation sequence)",["canonicalCloneEqual"]=true,["nativeGlowMask"]=item.glowMask};}
                if(WInt(scenario,"itemStack",1)>item.maxStack) throw new ArgumentException("itemStack exceeds native item maxStack");
                item.stack=WInt(scenario,"itemStack",1);
                using var trainingDummy=nativeDummy?WNativeTrainingDummy.CreateNativeTarget(WInt(scenario["dummy"],"tileX",51),WInt(scenario["dummy"],"tileY",44)):null;
                if(trainingDummy is not null){dummy=trainingDummy.Npc;initialLife=dummy.life;new RuntimeHitNpcGeneration().OnSpawn(dummy,owner.GetSource_Misc("item-test-workbench-native-training-dummy"));Terraria.Main.mouseX=(int)dummy.Center.X;Terraria.Main.mouseY=(int)dummy.Center.Y;report["scene"]!["dummy"]=trainingDummy.Report;}
                if(clientPlayer){Terraria.GameContent.TextureAssets.Item[item.type]=data is null?graphics!.LoadVanillaItemTexture(item.type,scenario["vanillaAssetRoot"]?.GetValue<string>()??throw new ArgumentException("Vanilla client contact requires vanillaAssetRoot with pinned Item_<id>.png")):graphics!.ItemTexture;Terraria.GameContent.TextureAssets.Projectile[registeredType]=graphics.ProjectileTexture;
                    if(item.consumable || data?.RuntimeProgram.Bindings.Any(b=>b.UsePolicy.StackCost>0)==true || drawPlayer && actions.Any(a=>a!["kind"]!.GetValue<string>() is "equip" or "unequip" or "vanity" or "select_slot")) Terraria.GameContent.TextureAssets.Item[0]=graphics.LoadEmptyItemTexture(scenario["nativeRender"]?["playerAssetRoot"]?.GetValue<string>()??Environment.GetEnvironmentVariable("INFINI_PLAYER_ASSET_DIR")??throw new InvalidOperationException("Native client consumption requires INFINI_PLAYER_ASSET_DIR with original Item_0.png"));}
                WProvisionAmmoInventory(owner,scenario);
                using var ammoObserver=WObserveAmmoConsumption(owner,e=>events.Add(e));
                owner.ownedProjectileCounts=new int[ProjectileLoader.ProjectileCount];
                using var itemEventObserver=WObserveItemEvents(e=>events.Add(e));
                using var sourceObserver=WObserveParentSources(nameof(Terraria.Entity.GetSource_FromThis));
                using var aiSourceObserver=WObserveParentSources(nameof(Terraria.Entity.GetSource_FromAI));
                using var allocation = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile),new[]{typeof(IEntitySource),typeof(float),typeof(float),typeof(float),typeof(float),typeof(int),typeof(int),typeof(float),typeof(int),typeof(float),typeof(float),typeof(float)})!,
                    (WorkbenchSpawnObserver)((orig,source,x,y,vx,vy,type,damage,kb,player,ai0,ai1,ai2) => {
                        int? parentId=WSourceParentIds.TryGetValue(source,out int capturedParentId)?capturedParentId:null;
                        int slot=orig(source,x,y,vx,vy,type,damage,kb,player,ai0,ai1,ai2);
                        if(slot>=0 && slot<Terraria.Main.maxProjectiles && Terraria.Main.projectile[slot].active) {
                            var body=Terraria.Main.projectile[slot];
                            WorkbenchSpawnSequences[slot]=spawned++;
                            events.Add(new JsonObject { ["kind"]="spawn",["projectileId"]=WProjectileId(body),["nativeType"]=body.type,["nativeIdentity"]=body.identity,["sourceType"]=source.GetType().Name,["sourceContext"]=source.Context,["sourceItemIsLiveInventoryReference"]=source is EntitySource_ItemUse useSource?(bool?)owner.inventory.Any(i=>ReferenceEquals(i,useSource.Item)):null,["sourceItemDataId"]=source is EntitySource_ItemUse dataSource && dataSource.Item.ModItem is GeneratedItem sourceGenerated?sourceGenerated.Data.Id:null,["sourceItemStack"]=source is EntitySource_ItemUse stackSource?(int?)stackSource.Item.stack:null,["parentProjectileId"]=parentId,["parentLineage"]=parentId.HasValue?"observed_at_native_source_creation":"not_observed",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["ammoItemIdUsed"]=source is EntitySource_ItemUse_WithAmmo ammoSource?ammoSource.AmmoItemIdUsed:(int?)null,["initialX"]=body.Center.X,["initialY"]=body.Center.Y,["requestedSpawnX"]=x,["requestedSpawnY"]=y,["initialDamage"]=body.damage,["initialKnockback"]=body.knockBack,["initialVx"]=body.velocity.X,["initialVy"]=body.velocity.Y });
                        }
                        return slot;
                    }));
                using var useObserver=WObserveUseCadence(owner,e=>events.Add(e));
                using var configureObserver=WObserveConfiguration(e=>events.Add(e));
                using var directDamageObserver=WObserveDirectNpcDamage(e=>events.Add(e));
                using var hitFeedbackObserver=renderClient && (scenario["nativeRender"]?["drawNativeDust"]?.GetValue<bool>()??false)?new WNativeHitFeedback(e=>events.Add(e)):null;
                using var hitObserver = new Hook(typeof(CombinedHooks).GetMethod(nameof(CombinedHooks.OnHitNPCWithProj))!,
                    (WorkbenchHitObserver)((WorkbenchHitOriginal orig,Projectile projectile,NPC target,in NPC.HitInfo hit,int damageDone) => {
                        hitCount++; events.Add(new JsonObject { ["kind"]="hit", ["projectileId"]=WProjectileId(projectile),["entityId"]=WProjectileEntity(projectile),["childDepth"]=WProjectileDepth(projectile),["npcId"]=target.whoAmI,["damageDone"]=damageDone,["lifeAfterDamage"]=target.life,["crit"]=hit.Crit,["hitKnockback"]=hit.Knockback,["targetOwnerImmunity"]=target.immune[projectile.owner],["projectileLocalImmunity"]=projectile.localNPCImmunity[target.whoAmI],["playerMeleeCooldown"]=Terraria.Main.player[projectile.owner].meleeNPCHitCooldown[target.whoAmI],["nativeDamage"]=projectile.damage,["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["observationStage"]="after_native_damage_before_mod_hit_callbacks" });
                        orig(projectile,target,in hit,damageDone);
                    }));
                using var tileObserver = new Hook(typeof(GeneratedProjectile).GetMethod(nameof(GeneratedProjectile.OnTileCollide))!,
                    (Func<Func<GeneratedProjectile,Vector2,bool>,GeneratedProjectile,Vector2,bool>)((orig,projectile,oldVelocity) => {
                        tileCollisions++;
                        bool kill=orig(projectile,oldVelocity);
                        events.Add(new JsonObject { ["kind"]="tile_collision",["projectileId"]=WProjectileId(projectile.Projectile),["oldVx"]=oldVelocity.X,["oldVy"]=oldVelocity.Y,["nativeKillDecision"]=kill });
                        return kill;
                    }));
                using var deathObserver = new Hook(typeof(Projectile).GetMethod(nameof(Projectile.Kill),Type.EmptyTypes)!,
                    (Action<Action<Projectile>,Projectile>)((orig,projectile) => {
                        bool active=projectile.active;
                        int timeLeft=projectile.timeLeft, lifetimeId=WProjectileId(projectile), nativeType=projectile.type;
                        string killedEntity=WProjectileEntity(projectile);
                        bool? expired=projectile.ModProjectile is GeneratedProjectile generated ? WState<bool>(generated,"_expireEventRan") : null;
                        var beforeKill=WBeforeKill(projectile,owner);
                        orig(projectile);
                        if(active) events.Add(new JsonObject { ["preKill"]=beforeKill,["entityId"]=killedEntity,["kind"]="kill",["projectileId"]=lifetimeId,["nativeType"]=nativeType,["timeLeftBeforeKill"]=timeLeft,["nativeLifetimeDepleted"]=timeLeft<=0,["generatedExpiryEventRan"]=expired });
                        if(active && timeLeft<=0 && expired!=false) naturalExpiries++;
                    }));
                using var teleportObserver = new Hook(typeof(Player).GetMethod(nameof(Player.Teleport))!,
                    (Action<Action<Player,Vector2,int,int>,Player,Vector2,int,int>)((orig,p,destination,style,extra) => {
                        Vector2 before=p.position; orig(p,destination,style,extra);
                        if(ReferenceEquals(p,owner)) { teleports++; events.Add(new JsonObject { ["kind"]="native_teleport",["beforeX"]=before.X,["beforeY"]=before.Y,["afterX"]=p.position.X,["afterY"]=p.position.Y,["style"]=style }); }
                    }));
                using var manaObserver = new Hook(typeof(Player).GetMethod(nameof(Player.CheckMana),new[]{typeof(Item),typeof(int),typeof(bool),typeof(bool)})!,
                    (Func<Func<Player,Item,int,bool,bool,bool>,Player,Item,int,bool,bool,bool>)((orig,p,used,amount,pay,blockQuickMana) => {
                        int before=p.statMana; bool accepted=orig(p,used,amount,pay,blockQuickMana);
                        if(ReferenceEquals(p,owner) && pay) { int spent=Math.Max(0,before-p.statMana); manaPaid+=spent;
                            events.Add(new JsonObject { ["kind"]="native_mana_payment",["accepted"]=accepted,["before"]=before,["after"]=p.statMana,["spent"]=spent }); }
                        return accepted;
                    }));
                using var healObserver = new Hook(typeof(Player).GetMethod(nameof(Player.Heal),new[]{typeof(int)})!,
                    (Action<Action<Player,int>,Player,int>)((orig,p,amount)=> {
                        int before=p.statLife; orig(p,amount);
                        if(ReferenceEquals(p,owner)) { int gain=p.statLife-before; healed+=gain;
                            events.Add(new JsonObject { ["kind"]="native_heal",["requested"]=amount,["before"]=before,["after"]=p.statLife,["gained"]=gain }); }
                    }));
                using var finiteObserver = new Hook(typeof(GeneratedProjectile).GetMethod(nameof(GeneratedProjectile.AI))!,
                    (Action<Action<GeneratedProjectile>,GeneratedProjectile>)((orig,projectile) => {
                        orig(projectile);
                        WRequireFinite(projectile.Projectile,"projectile",WProjectileId(projectile.Projectile),
                            "after GeneratedProjectile.AI; before native position integration",events,report);
                    }));
                if(renderClient) report["execution"]!["uiFeedback"]=new JsonObject{["scope"]="Generated use-refusal and native achievement-completion text only",["adapter"]="Text-only RemadeChatMonitor.NewText sink inside original NotifyGeneratedUseRefusal",["nativeMainNewTextPreserved"]=true,["nativeChatFontLayoutExecuted"]=false,["nativeSoundDispatchPreserved"]=true,["chatRendered"]=false};
                bool generatedFeedbackActive=false, achievementFeedbackActive=false;
                using var feedbackScope=renderClient?new Hook(typeof(InfiniCraftPlayer).GetMethod("NotifyGeneratedUseRefusal",TestInstance)!,
                    (Action<Action<InfiniCraftPlayer,string>,InfiniCraftPlayer,string>)((orig,p,message)=>{bool previous=generatedFeedbackActive;generatedFeedbackActive=true;try{orig(p,message);}finally{generatedFeedbackActive=previous;}})):null;
                using var achievementFeedbackScope=renderClient?new Hook(typeof(Terraria.Initializers.AchievementInitializer).GetMethod("OnAchievementCompleted",PersistenceStatic)!,
                    (Action<Action<Terraria.Achievements.Achievement>,Terraria.Achievements.Achievement>)((orig,achievement)=>{bool previous=achievementFeedbackActive;achievementFeedbackActive=true;try{events.Add(new JsonObject{["kind"]="native_achievement_completed",["name"]=achievement.Name,["chatRendered"]=false});orig(achievement);}finally{achievementFeedbackActive=previous;}})):null;
                using var chatSink=renderClient?new Hook(typeof(Terraria.GameContent.UI.Chat.RemadeChatMonitor).GetMethod("NewText",new[]{typeof(string),typeof(byte),typeof(byte),typeof(byte)})!,
                    (Action<Action<Terraria.GameContent.UI.Chat.RemadeChatMonitor,string,byte,byte,byte>,Terraria.GameContent.UI.Chat.RemadeChatMonitor,string,byte,byte,byte>)((orig,monitor,text,r,g,b)=>{
                        if(!generatedFeedbackActive && !achievementFeedbackActive){orig(monitor,text,r,g,b);return;}
                        events.Add(new JsonObject{["kind"]="native_ui_message",["text"]=text,["r"]=r,["g"]=g,["b"]=b,["gameUpdateCount"]=(long)Terraria.Main.GameUpdateCount,["source"]=achievementFeedbackActive?"Native AchievementInitializer.OnAchievementCompleted -> Main.NewText -> RemadeChatMonitor.NewText":"InfiniCraftPlayer.NotifyGeneratedUseRefusal -> Main.NewText -> RemadeChatMonitor.NewText",["chatRendered"]=false,["unresolvedLocalizationKey"]=text.StartsWith("Mods.InfiniCrafterLocal.",StringComparison.Ordinal),["adapter"]="Text-only chat sink; original Main.NewText continues native sound call"});
                    })):null;
                if(fullPlayer) WPrepareFullPlayer(owner,modPlayer,manaCrystals);
                using var worldScene=scenario["world"] is JsonObject worldSettings?new WWorldScene(worldSettings,worldLedger,data,report):null;
                using var nativeRenderer=renderClient?new WNativeVfxRenderer(graphics!,scenario["nativeRender"]!.AsObject(),Path.Combine(Path.GetDirectoryName(outputPath!)!,"native-frames"),data):null;
                if(renderClient){Terraria.TimeLogger.Initialize();Terraria.Main.gameMenu=false;Terraria.Main.mapEnabled=false;
                for(int lightingPhase=0;lightingPhase<4;lightingPhase++){nativeRenderer!.StepLighting();}}
                using var playerAssets=(drawPlayer||drawProjectileVfx)?new WNativePlayerAssets(graphics!,scenario["nativeRender"]?["playerAssetRoot"]?.GetValue<string>()??Environment.GetEnvironmentVariable("INFINI_PLAYER_ASSET_DIR")??throw new ArgumentException("Native procedural/player draw requires playerAssetRoot or INFINI_PLAYER_ASSET_DIR")):null;
                using var zombie=drawZombie?new WNativeZombieRender(graphics!,dummy,scenario["nativeRender"]?["playerAssetRoot"]?.GetValue<string>()??Environment.GetEnvironmentVariable("INFINI_PLAYER_ASSET_DIR")??throw new ArgumentException("drawZombie requires playerAssetRoot or INFINI_PLAYER_ASSET_DIR")):null;
                using var pixelAssets=renderClient&&!drawPlayer&&!drawProjectileVfx?new WNativeMagicPixelAssets(graphics!,scenario["nativeRender"]?["playerAssetRoot"]?.GetValue<string>()??Environment.GetEnvironmentVariable("INFINI_PLAYER_ASSET_DIR")??throw new ArgumentException("Native VFX requires playerAssetRoot or INFINI_PLAYER_ASSET_DIR for genuine MagicPixel")):null;
                if(pixelAssets is not null)nativeRenderer!.Report["magicPixelResource"]=pixelAssets.Report.DeepClone();
                if(trainingDummy is not null)trainingDummy.InitializeGraphics(graphics!,scenario["nativeRender"]?["dummyAssetRoot"]?.GetValue<string>()??Environment.GetEnvironmentVariable("INFINI_DUMMY_ASSET_DIR")??scenario["nativeRender"]?["playerAssetRoot"]?.GetValue<string>()??Environment.GetEnvironmentVariable("INFINI_PLAYER_ASSET_DIR")??throw new ArgumentException("native_training_dummy requires dummyAssetRoot or playerAssetRoot containing genuine dummy assets"));
                using var artwork=drawArtwork?new WNativeArtwork(data!,owner,(scenario["nativeRender"]?["artworkFiles"]?.AsArray()??throw new ArgumentException("drawArtwork requires artworkFiles")).Select(f=>f!.GetValue<string>()).ToArray(),WProjectileId):null;
                using var activeVfx=(drawProjectileVfx||(historyRibbon||historyTrail)&&drawPlayer)?new WNativeActiveVfx(artwork is not null):null;
                if(activeVfx is not null)nativeRenderer!.SetActiveVfx(activeVfx,drawProjectileVfx);
                using var vanillaProjectileAssets=drawVanillaProjectiles?new WNativeVanillaProjectileAssets(graphics!,scenario["vanillaAssetRoot"]!.GetValue<string>()):null;
                using var placedBodies=drawPlacedBodies?new WNativePlacedBodies():null;
                if(placedBodies is not null)nativeRenderer!.SetPlacedBodies(placedBodies);
                if(nativeRenderer!=null) {
                    if(playerAssets is not null)nativeRenderer.Report["playerAssets"]=playerAssets.Report;
                    if(activeVfx is not null)report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create("InfiniVfxRuntime.Draw under/over passes with native GeneratedProjectile history; DrawTrail/SpriteBatch submissions observed"));
                    if(artwork is not null) {if(drawPlayer){artwork.EnableNativePlayer();if(drawVanillaProjectiles)artwork.EnableNativeVanillaProjectiles(vanillaProjectileAssets!);report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create(data is null?"Main.PlayerRenderer.DrawPlayers / native vanilla held-item DrawData":"Main.PlayerRenderer.DrawPlayers / PlayerDrawLayerLoader / GeneratedItem.ModifyItemDraw / ProjectileLoader.PreDraw/PostDraw"));}nativeRenderer.SetArtwork(artwork);if(playerAssets is not null)nativeRenderer.Report["playerAssets"]=playerAssets.Report;report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create(data is null?"PlayerDrawLayers.DrawPlayer_27_HeldItem / Dust.UpdateDust / Lighting.LightTiles":"GeneratedHeldItemDrawLayer.Draw / GeneratedItem.PreDrawInInventory / GeneratedProjectile.DrawAuthoredEntityVisual / InfiniDetachedVfxSystem.DrawProjectiles / Dust.UpdateDust / Lighting.LightTiles"));}
                    if(scenario["nativeRender"]?["drawNativeDust"]?.GetValue<bool>()??false){
                        report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create("Main.DrawDust (original stateful native rendering; capture controls PNG export only)"));
                        var unsupported=report["execution"]!["unsupported"]!.AsArray();for(int u=0;u<unsupported.Count;u++)unsupported[u]=unsupported[u]!.GetValue<string>().Replace(" and native dust sprites","").Replace("native dust sprites, ","").Replace("native dust sprite rendering", "complete world rendering").Replace("/dust rendering", "/world rendering");
                    }
                    if(drawVanillaProjectiles){nativeRenderer.Report["vanillaProjectileAssets"]=vanillaProjectileAssets!.Report;report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create("Main.DrawProj (original vanilla projectile rendering)"));}
                    report["nativeRender"]=nativeRenderer.Report;if(trainingDummy is not null)nativeRenderer.SetTrainingDummy(trainingDummy);
                    if(zombie is not null){nativeRenderer.SetZombie(zombie);report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create("NPC.FindFrame / Main.DrawNPC (original controlled zombie)"));
                        report["execution"]!["scope"]="Actual client Player.Update, projectile simulation and controlled zombie NPC.UpdateNPC with AI disabled; original NPC.FindFrame and Main.DrawNPC; no full world or NPC AI parity";
                        report["execution"]!["clientGraphics"]!["scope"]=report["execution"]!["scope"]!.DeepClone();
                        var unsupported=report["execution"]!["unsupported"]!.AsArray();for(int u=0;u<unsupported.Count;u++)unsupported[u]=unsupported[u]!.GetValue<string>().Replace("tile/NPC/world","tile/world and other NPC").Replace("world/NPCs/","world/other NPCs/");}
                    report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create("InfiniDetachedVfxSystem.PostUpdateEverything / BeginDrawBudgetFrame / DrawLayer (BeforeProjectiles,AfterProjectiles)"));
                    if(!drawArtwork) nativeRenderer.Report["unrenderedArtwork"]=new JsonArray((data?.RuntimeProgram.Entities ?? Array.Empty<RuntimeEntitySpec>()).Select(e=>(JsonNode?)new JsonObject{["entityId"]=e.Id,["kind"]=e.Kind,["path"]=e.Visual.SpritePath,["reason"]="VFX-only draw scope; authored entity artwork is not rendered or substituted"}).ToArray());
                }

                if(clientPlayer) { owner.lastVisualizedSelectedItem=owner.HeldItem.Clone(); }
                using var poseObserver = new Hook(typeof(Player).GetMethod(nameof(Player.ItemCheck_ApplyUseStyle))!, (Action<Action<Player,float,Item,Rectangle>,Player,float,Item,Rectangle>)((orig,p,offset,i,frame)=>{orig(p,offset,i,frame);WRequireFinite(p,"player",p.whoAmI,"after actual native use-style; before contact",events,report);}));
                using var geometryObserver = new Hook(typeof(ItemLoader).GetMethod(nameof(ItemLoader.UseItemHitbox))!, (ContactGeometryObserver)((ContactGeometryOriginal orig,Item i,Player p,ref Rectangle box,ref bool disabled)=>{var before=box;orig(i,p,ref box,ref disabled);WRequireFinite(p,"player",p.whoAmI,"after native UseItemHitbox",events,report);if(!disabled && (box.Width<=0 || box.Height<=0)) throw new WorkbenchInvariantException("Native enabled contact produced nonpositive rectangle");events.Add(new JsonObject{["kind"]="item_contact_geometry",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["native"]=WContactRect(before),["final"]=WContactRect(box),["noHitbox"]=disabled,["itemType"]=i.type});}));
                using var contactObserver = new Hook(typeof(Player).GetMethod("ItemCheck_MeleeHitNPCs",TestInstance)!, (Action<Action<Player,Item,Rectangle,int,float>,Player,Item,Rectangle,int,float>)((orig,p,i,rect,damage,kb)=> { contactQueries++; events.Add(new JsonObject { ["kind"]="item_contact_query",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["x"]=rect.X,["y"]=rect.Y,["width"]=rect.Width,["height"]=rect.Height,["damage"]=damage,["itemType"]=i.type,["itemAnimation"]=p.itemAnimation,["itemTime"]=p.itemTime,["itemX"]=p.itemLocation.X,["itemY"]=p.itemLocation.Y }); orig(p,i,rect,damage,kb); }));
                using var itemHitObserver = new Hook(typeof(ItemLoader).GetMethod(nameof(ItemLoader.OnHitNPC))!, (ContactItemHitObserver)((ContactItemHitOriginal orig,Item i,Player p,NPC target,in NPC.HitInfo hit,int damage)=>{hitCount++; itemHitCount++; events.Add(new JsonObject{["kind"]="item_hit",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["itemType"]=i.type,["damageDone"]=damage,["npcId"]=target.whoAmI,["lifeAfterDamage"]=target.life,["crit"]=hit.Crit,["hitKnockback"]=hit.Knockback,["targetOwnerImmunity"]=target.immune[p.whoAmI],["playerMeleeCooldown"]=p.meleeNPCHitCooldown[target.whoAmI],["observationStage"]="ItemLoader.OnHitNPC_entry"});orig(i,p,target,in hit,damage);}));
                using var reactionScene=actions.Any(a=>WReactionAction(a!["kind"]!.GetValue<string>()))?new WReactionScene(e=>events.Add(e)):null;
                var rootBridge = new InfiniCrafterLocal.Common.Systems.GeneratedRootCombatSystem(); rootBridge.Load();
                try {
                    nativeRenderer?.ApplyNativeViewport();
                    Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed);
                    report["execution"]!["rng"] = new JsonObject{["seed"]=seed,["resetBoundary"]="After all scene/asset/loader initialization, immediately before initial snapshot and gameplay tick0",["scope"]="Same initial native random stream; weapon effects and graphics may consume it differently"};
                    frames.Add(WSnapshot(-1, owner, dummy, new JsonArray()));
                    // Scripted use commands are held until release or another use command.
                    // The engine clears altFunctionUse at the end of an animation, so
                    // reassert the scripted alternate intent on every held tick.
                    bool alternateHeld = false;
                    for (int tick = 0; tick < ticks; tick++) {
                        MaterialClock((uint)tick);
                        foreach (var action in (scenario["actions"]?.AsArray() ?? new JsonArray()).Where(a => WInt(a, "tick", -1) == tick)) {
                            string kind = action!["kind"]!.GetValue<string>();
                            if (kind == "aim") { Terraria.Main.mouseX = (int)(WFloat(action,"x",owner.Center.X+200)-Terraria.Main.screenPosition.X); Terraria.Main.mouseY=(int)(WFloat(action,"y",owner.Center.Y)-Terraria.Main.screenPosition.Y); events.Add(new JsonObject { ["kind"]="input",["input"]="aim" }); }
                            else if (kind is "equip" or "unequip" or "vanity") { WPlaceEquipment(owner,item,kind); events.Add(new JsonObject { ["kind"]="input",["input"]=kind,["instanceConserved"]=true }); }
                            else if (kind == "select_slot") { owner.selectedItem=WInt(action,"slot",0); events.Add(new JsonObject { ["kind"]="input",["input"]="select_slot",["slot"]=owner.selectedItem }); }
                            else if (kind is "tile_target" or "break_tile") {worldScene!.Action(kind,action!,events);}
                            else if (kind == "controls") { WApplyControls(owner,action); events.Add(new JsonObject{["kind"]="input",["input"]="controls",["nativeControls"]=WControls(owner)}); }
                            else if (kind == "release") { alternateHeld = false; owner.channel = false; owner.controlUseItem = false; if(owner.altFunctionUse==1) owner.altFunctionUse=0; events.Add(new JsonObject { ["kind"]="input",["input"]="release" }); }
                            else if (kind == "primary" || kind == "alt") {
                                if(data is not null) {
                                    WRequireBinding(data,kind=="alt"?RuntimeInputKind.AlternateUse:RuntimeInputKind.PrimaryUse,fullPlayer,clientPlayer,hybridClient,renderClient);
                                } else if(kind=="alt" && !ItemLoader.AltFunctionUse(item,owner)) throw new NotSupportedException("Selected vanilla item has no alternate use");
                                alternateHeld = kind == "alt";
                                owner.altFunctionUse = alternateHeld ? 1 : 0;
                                owner.controlUseItem = true; owner.channel = item.channel;
                                events.Add(new JsonObject { ["kind"]="input", ["input"]=kind });
                            } else if(!WReactionAction(kind)) throw new NotSupportedException("Unknown action: " + kind);
                        }
                        if (alternateHeld && owner.controlUseItem) owner.altFunctionUse = 1;
                        if (events.Count > 0) { var before = WSnapshot(tick,owner,dummy,events); before["phase"]="after_input_before_update"; frames.Add(before); events = new JsonArray(); }
                        if(ReferenceEquals(owner.HeldItem,item)) heldNativeTicks++;
                        if(fullPlayer) { if(clientPlayer) { Terraria.Main.dedServ=false;events.Add(new JsonObject{["kind"]="native_phase",["phase"]="Player.Update",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode}); } try {owner.Update(0);} finally {if(clientPlayer) Terraria.Main.dedServ=true;} } else {
                            typeof(Player).GetMethod("ResetProjectileCaches",TestInstance)!.Invoke(owner,null);
                            typeof(Player).GetMethod("UpdateProjectileCaches",TestInstance)!.Invoke(owner,new object[]{owner.whoAmI});
                            owner.ItemCheck();
                        }
                        if(clientPlayer && !hybridClient && Terraria.Main.projectile.Any(p=>p.active)) throw new NotSupportedException("Pure client contact scene unexpectedly spawned a projectile; hybrid scope not admitted");
                        WRequireFinite(owner,"player",owner.whoAmI,"after Player update",events,report);
                        foreach(var stimulus in actions.Where(a=>WInt(a,"tick",-1)==tick && WReactionAction(a!["kind"]!.GetValue<string>()))) reactionScene!.Apply(owner,stimulus!);
                        if(nativeDummy)Terraria.Main.dedServ=false;
                        if(clientPlayer) events.Add(new JsonObject{["kind"]="native_phase",["phase"]="NPC.UpdateNPC",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["active"]=dummy.active});
                        if(dummy.active) dummy.UpdateNPC(dummy.whoAmI);
                        zombie?.UpdateFrame();
                        WUpdateControlledHostiles(events,report);
                        WRequireFinite(dummy,"npc",dummy.whoAmI,"after NPC.UpdateNPC",events,report);
                        if(hybridClient) Terraria.Main.dedServ=false;
                        try {
                            if(clientPlayer) events.Add(new JsonObject{["kind"]="native_phase",["phase"]="Projectile.Update",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["activeCount"]=Terraria.Main.projectile.Count(p=>p.active)});
                            for (int slot = 0; slot < Terraria.Main.maxProjectiles; slot++)
                                if (Terraria.Main.projectile[slot].active) { Terraria.Main.projectile[slot].Update(slot); WRequireFinite(Terraria.Main.projectile[slot],"projectile",WProjectileId(Terraria.Main.projectile[slot]),"after Projectile.Update",events,report); }
                            if(clientPlayer) events.Add(new JsonObject{["kind"]="native_phase",["phase"]="RuntimeDelayedActionScheduler.Update",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode});
                            RuntimeDelayedActionScheduler.Update();
                            if(renderClient){events.Add(new JsonObject{["kind"]="native_phase",["phase"]="Dust.UpdateDust / Lighting.LightTiles",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode});Dust.UpdateDust();
                            nativeRenderer!.StepLighting();}
                            if(trainingDummy is not null){events.Add(new JsonObject{["kind"]="native_phase",["phase"]="TileEntity.UpdateStart / TETrainingDummy.Update / TileEntity.UpdateEnd",["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode});trainingDummy.UpdateNativeTileEntity();if(!ReferenceEquals(dummy,trainingDummy.Npc))throw new NotSupportedException("Native target reactivation changed NPC identity; dynamic respawn scene not yet admitted");}
                            nativeRenderer?.Step(tick);
                        } finally {if(hybridClient) Terraria.Main.dedServ=true;}
                        for(int hostileSlot=2;hostileSlot<10;hostileSlot++)if(Terraria.Main.npc[hostileSlot].type==NPCID.Zombie)WRequireFinite(Terraria.Main.npc[hostileSlot],"hostile",hostileSlot,"after projectile/delayed/render updates",events,report);
                        worldScene?.Update();
                        frames.Add(WSnapshot(tick, owner, dummy, events)); events = new JsonArray();
                        report["timeline"]!["completedTicks"]=tick+1;
                    }
                    report["timeline"]!["complete"]=true;
                    foreach (var assertion in scenario["assertions"]?.AsArray() ?? new JsonArray()) {
                        string name = assertion!["kind"]!.GetValue<string>();
                        bool pass = name=="placed_body_draw_count_at_least" ? placedBodies!.SuccessfulDraws>=WInt(assertion,"minimum",1) : WWorldAssertionKind(name) ? WWorldAssertion(assertion,frames) : WLifecycleKind(name) ? WLifecycleAssertion(name,assertion,frames,data!.Id) : name switch { "inventory_stack" or "ammo_consumed_count" or "ammo_source_spawn_count" => WAmmoAssertion(name,assertion,owner,frames), "spawned" => spawned > 0, "projectile_hit_count" => hitCount-itemHitCount==WInt(assertion,"value",0), "item_hit_count" => itemHitCount==WInt(assertion,"value",0), "item_contact_observed"=>contactQueries>0, "no_item_contact"=>contactQueries==0, "player_stat_at" => WStatAt(frames,assertion), "player_stat_never_above" => frames.All(f=>WReportNumber(f!["player"]![assertion["stat"]!.GetValue<string>()]!)<=WFloat(assertion,"value",0)+0.00001f), "native_projectile_active" => Terraria.Main.projectile.Any(p=>p.active && p.type==WInt(assertion,"id",0)), "native_buff_seen" => frames.Any(f=>f!["player"]!["nativeBuffs"]!.AsArray().Any(b=>b!["id"]!.GetValue<int>()==WInt(assertion,"id",0))), "native_projectile_seen" => frames.Any(f=>f!["projectiles"]!.AsArray().Any(p=>p!["nativeType"]!.GetValue<int>()==WInt(assertion,"id",0))), "jump_boost_equals" => Math.Abs(owner.jumpSpeedBoost-WFloat(assertion,"value",0))<0.00001f, "teleport_count" => teleports==WInt(assertion,"value",0), "mobility_cooldown_expired" => frames.Any(f=>f!["player"]!["mobilityCooldownTicks"]!.GetValue<int>()>0) && owner.GetModPlayer<InfiniCrafterLocal.Common.Players.InfiniCraftPlayer>().GeneratedMobilityCooldownTicks==0, "mana_debited" => manaPaid==WInt(assertion,"value",0), "direct_healing" => healed==WInt(assertion,"value",0), "generated_buff_seen" => frames.Any(f=>f!["player"]!["generatedBuffTicks"]!.GetValue<int>()>0), "generated_buff_expired" => frames.Any(f=>f!["player"]!["generatedBuffTicks"]!.GetValue<int>()>0) && WBuffTicks(owner)==0, "jump_boost_seen" => frames.Any(f=>f!["player"]!["jumpSpeedBoost"]!.GetValue<float>()>=WFloat(assertion,"minimum",0)), "tile_collision" => tileCollisions>0, "dummy_undamaged" => dummy.life==initialLife && hitCount==0, "dummy_damaged" => dummy.life < initialLife && (hitCount > 0 || frames.SelectMany(f=>f!["events"]!.AsArray()).Any(e=>e?["kind"]?.GetValue<string>()=="native_direct_npc_damage" && e["npcId"]!.GetValue<int>()==dummy.whoAmI && e["lifeLost"]!.GetValue<int>()>0)), "all_inactive" => !Terraria.Main.projectile.Any(p=>p.active), "natural_expiry" => naturalExpiries > 0, "hit_count_at_least" => hitCount >= WInt(assertion,"minimum",1), "spawn_count" => spawned == WInt(assertion,"value",1), "mana_equals" => owner.statMana == WInt(assertion,"value",0), "life_equals" => owner.statLife == WInt(assertion,"value",0), "released" => frames.Any(f=>f!["projectiles"]!.AsArray().Any(p=>p!["released"]?.GetValue<bool>()==true)), "returned" => frames.Any(f=>f!["projectiles"]!.AsArray().Any(p=>p!["returning"]?.GetValue<bool>()==true)), "no_nonfinite" => WNoNonFinite(frames), _ => throw new NotSupportedException("Unknown assertion: "+name) };
                        assertions.Add(new JsonObject { ["name"] = name, ["request"]=assertion.DeepClone(), ["status"] = pass?"passed":"failed", ["detail"] = $"spawned={spawned}, hits={hitCount}, dummyLife={dummy.life}, initialLife={initialLife}, mana={owner.statMana}, life={owner.statLife}, naturalExpiries={naturalExpiries}, tileCollisions={tileCollisions}, manaDebited={manaPaid}, teleports={teleports}, directHealing={healed}, buffTicks={WBuffTicks(owner)}, mobilityCooldownTicks={owner.GetModPlayer<InfiniCrafterLocal.Common.Players.InfiniCraftPlayer>().GeneratedMobilityCooldownTicks}, jumpBoost={owner.jumpSpeedBoost}" });
                    }
                    report["status"] = assertions.Any(a=>a!["status"]!.GetValue<string>() == "failed") ? "failed" : "passed";
                } catch (Exception ex) {
                    while (ex is TargetInvocationException && ex.InnerException != null) ex = ex.InnerException;
                    report["status"] = ex is WorkbenchInvariantException ? "failed" : "error"; report["error"] = ex.ToString();
                    if(ex is WorkbenchInvariantException) assertions.Add(new JsonObject { ["name"]="native_state_finite",["status"]="failed",["detail"]=ex.Message });
                    frames.Add(WSnapshot((int)Terraria.Main.GameUpdateCount,owner,dummy,events));
                } finally { rootBridge.Unload(); }
            });
        });
        report["coverage"]!["heldItemNativeTicks"]=heldNativeTicks;
        report["coverage"]!["heldEffectsObserved"]=fullPlayer && data?.RuntimeProgram.HeldEffectGroupId is not null && frames.Any(f=>f!["player"]!["generatedBuffTicks"]!.GetValue<int>()>0);
        report["combat"]=new JsonObject{["itemHits"]=itemHitCount,["projectileHits"]=hitCount-itemHitCount,["totalHits"]=hitCount,["directNpcDamageCalls"]=frames.SelectMany(f=>f!["events"]!.AsArray()).Count(e=>e?["kind"]?.GetValue<string>()=="native_direct_npc_damage"),["hitCountScope"]="Item/projectile native hit callbacks; direct NPC damage calls reported separately",["nativeContactQueries"]=contactQueries};
        report["resources"]=new JsonObject { ["observedManaDebited"]=manaPaid,["observedDirectHealing"]=healed,["directHealingObserverScope"]="Actual Player.Heal calls only, not regeneration or direct life assignment",["observedTeleports"]=teleports };
        return report;
    }
    private static JsonObject WSnapshot(int tick, Player owner, NPC dummy, JsonArray events)
    {
        var nativeBuffs = new JsonArray();
        for(int slot=0;slot<owner.buffType.Length;slot++) if(owner.buffType[slot]>0 && owner.buffTime[slot]>0) nativeBuffs.Add(new JsonObject { ["id"]=owner.buffType[slot],["ticks"]=owner.buffTime[slot] });
        var projectiles = new JsonArray();
        foreach (var p in Terraria.Main.projectile.Where(p=>WorkbenchSpawnSequences.ContainsKey(p.whoAmI))) {
            var generated=p.ModProjectile as GeneratedProjectile;
            string entityId=generated is not null && generated.TryGetHitSource(out _,out var entity)?entity.Id:"vanilla:"+p.type;
            JsonObject? chargeStatus=generated is not null && generated.TryCaptureChargeStatus(owner,out var charge)?new JsonObject{["chargeUpdates"]=charge.ChargeUpdates,["durationUpdates"]=charge.DurationUpdates,["progress"]=charge.Progress,["ready"]=charge.Ready,["source"]= "GeneratedProjectile.TryCaptureChargeStatus"}:null;
            projectiles.Add(new JsonObject { ["chargeStatus"]=chargeStatus,["id"]=WProjectileId(p),["nativeIdentity"]=p.identity,["slot"]=p.whoAmI,["entityId"]=entityId,["childDepth"]=WProjectileDepth(p),["x"]=WFinite(p.position.X),["y"]=WFinite(p.position.Y),["width"]=p.width,["height"]=p.height,["vx"]=WFinite(p.velocity.X),["vy"]=WFinite(p.velocity.Y),["active"]=p.active,["timeLeft"]=p.timeLeft,["rotation"]=WFinite(p.rotation),["nonFinite"]=!WEntityFinite(p),["damage"]=p.damage,["usesLocalNPCImmunity"]=p.usesLocalNPCImmunity,["localNpcImmunityTarget"]=p.localNPCImmunity[dummy.whoAmI], ["nativeType"]=p.type, ["nativeImmunityOwner0"]=dummy.immune[0], ["released"]=generated is null?(bool?)null:WState<bool>(generated,"_released"), ["returning"]=generated is null?(bool?)null:WState<bool>(generated,"_returning"), ["chargeTicks"]=generated is null?(int?)null:WState<int>(generated,"_chargeTicks"), ["age"]=generated is null?(int?)null:WState<int>(generated,"_age") });
        }
        return new JsonObject { ["world"]=WActiveWorld?.Snapshot(),["tick"]=tick,["substep"]=-1,["hostiles"]=WHostileSnapshots(),["nativeActiveDust"]=Terraria.Main.dust.Count(d=>d!=null && d.active),["player"]=new JsonObject { ["x"]=WFinite(owner.position.X),["y"]=WFinite(owner.position.Y),["vx"]=WFinite(owner.velocity.X),["vy"]=WFinite(owner.velocity.Y),["nonFinite"]=!WEntityFinite(owner),["width"]=owner.width,["height"]=owner.height,["life"]=owner.statLife,["meleeNpcHitCooldownTarget"]=owner.meleeNPCHitCooldown[dummy.whoAmI],["dead"]=owner.dead,["mana"]=owner.statMana,["itemPose"]=new JsonObject{["x"]=WFinite(owner.itemLocation.X),["y"]=WFinite(owner.itemLocation.Y),["rotation"]=WFinite(owner.itemRotation),["direction"]=owner.direction,["useStyle"]=owner.HeldItem.useStyle,["itemAnimation"]=owner.itemAnimation,["itemTime"]=owner.itemTime},["maxMana"]=owner.statManaMax2,["manaCost"]=owner.manaCost,["maxLife"]=owner.statLifeMax2,["defense"]=(int)owner.statDefense,["genericCrit"]=owner.GetCritChance(DamageClass.Generic),["inventory"]=WInventory(owner.inventory,false),["armor"]=WInventory(owner.armor,true),["generatedBuffTicks"]=WBuffTicks(owner),["generatedItemExhaustion"]=WExhaustion(owner),["itemProjection"]=WItemProjection(owner.HeldItem),["lifeRegen"]=owner.lifeRegen,["mobilityCooldownTicks"]=owner.GetModPlayer<InfiniCrafterLocal.Common.Players.InfiniCraftPlayer>().GeneratedMobilityCooldownTicks,["jumpSpeedBoost"]=owner.jumpSpeedBoost,["moveSpeed"]=owner.moveSpeed,["pickSpeed"]=owner.pickSpeed,["nativeBuffs"]=nativeBuffs,["channel"]=owner.channel,["itemAnimation"]=owner.itemAnimation,["itemTime"]=owner.itemTime,["controlUseItem"]=owner.controlUseItem,["movementControls"]=WControls(owner),["selectedSlot"]=owner.selectedItem,["aimX"]=Terraria.Main.MouseWorld.X,["aimY"]=Terraria.Main.MouseWorld.Y },["dummy"]=new JsonObject { ["slot"]=dummy.whoAmI,["nativeType"]=dummy.type,["aiStyle"]=dummy.aiStyle,["immortal"]=dummy.immortal,["dontTakeDamage"]=dummy.dontTakeDamage,["frameX"]=dummy.frame.X,["frameY"]=dummy.frame.Y,["frameWidth"]=dummy.frame.Width,["frameHeight"]=dummy.frame.Height,["localAI"]=new JsonArray(dummy.localAI.Select(x=>(JsonNode?)JsonValue.Create(x)).ToArray()),["x"]=WFinite(dummy.position.X),["y"]=WFinite(dummy.position.Y),["vx"]=WFinite(dummy.velocity.X),["vy"]=WFinite(dummy.velocity.Y),["nonFinite"]=!WEntityFinite(dummy),["width"]=dummy.width,["height"]=dummy.height,["life"]=dummy.life,["active"]=dummy.active,["targetState"]=WTargetState(dummy),["noTileCollide"]=dummy.noTileCollide,["ownerImmunity"]=dummy.immune[owner.whoAmI] },["projectiles"]=projectiles,["events"]=events };
    }
    private static JsonObject WBeforeKill(Projectile p,Player owner){
        var result=new JsonObject{["centerX"]=WFinite(p.Center.X),["centerY"]=WFinite(p.Center.Y),["ownerCenterX"]=WFinite(owner.Center.X),["ownerCenterY"]=WFinite(owner.Center.Y),["ownerMountedX"]=WFinite(owner.MountedCenter.X),["ownerMountedY"]=WFinite(owner.MountedCenter.Y),["damage"]=p.damage,["causeInferred"]=false};
        if(p.ModProjectile is GeneratedProjectile gp){result["released"]=WState<bool>(gp,"_released");result["returning"]=WState<bool>(gp,"_returning");
            if(gp.TryGetHitSource(out _,out var entity)&&entity.Arrival is {} arrival){
                bool window=(bool)typeof(GeneratedProjectile).GetMethods(TestInstance).Single(m=>m.Name=="MotionWindowActive"&&m.GetParameters().Length==1).Invoke(gp,new object?[]{arrival.Window})!;
                Vector2 anchor=arrival.Target=="owner_mounted"?owner.MountedCenter:owner.Center;
                float distance=p.Distance(anchor);result["arrivalTarget"]=arrival.Target;result["arrivalRadiusPx"]=arrival.RadiusPx;result["distanceToArrivalTargetPx"]=WFinite(distance);result["nativeArrivalWindowActive"]=window;result["arrivalConditionAtKill"]=window&&distance<arrival.RadiusPx;
            }
        }return result;
    }
    private static JsonObject WContactRect(Rectangle r)=>new JsonObject{["x"]=r.X,["y"]=r.Y,["width"]=r.Width,["height"]=r.Height};
    private static bool WEntityFinite(Entity entity) => float.IsFinite(entity.position.X) && float.IsFinite(entity.position.Y)
        && (entity is not Player owner || (float.IsFinite(owner.itemLocation.X) && float.IsFinite(owner.itemLocation.Y) && float.IsFinite(owner.itemRotation)))
        && float.IsFinite(entity.velocity.X) && float.IsFinite(entity.velocity.Y) && (entity is not Projectile p || float.IsFinite(p.rotation));
    private static void WRequireFinite(Entity entity,string kind,int id,string boundary,JsonArray events,JsonObject report)
    {
        if(WEntityFinite(entity)) return;
        var bad=new JsonObject();
        foreach(var entry in new (string Name,float Value)[]{("x",entity.position.X),("y",entity.position.Y),("vx",entity.velocity.X),("vy",entity.velocity.Y)})
            if(!float.IsFinite(entry.Value)) bad[entry.Name]=entry.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        if(entity is Player owner) foreach(var entry in new (string Name,float Value)[]{("itemPose.x",owner.itemLocation.X),("itemPose.y",owner.itemLocation.Y),("itemPose.rotation",owner.itemRotation)}) if(!float.IsFinite(entry.Value)) bad[entry.Name]=entry.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        if(entity is Projectile p && !float.IsFinite(p.rotation)) bad["rotation"]=p.rotation.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var evidence=new JsonObject { ["kind"]="invalid_native_state",["actorKind"]=kind,["actorId"]=id,["tick"]=(int)Terraria.Main.GameUpdateCount,["boundary"]=boundary,["fields"]=bad };
        if(kind=="projectile") evidence["projectileId"]=id;
        events.Add(evidence); report["failure"]=evidence.DeepClone();
        throw new WorkbenchInvariantException("Native "+kind+" produced nonfinite state; simulation stopped at first observed invalid result");
    }
    private static void WInitializeNestedStatics(Type type)
    {
        System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(type.TypeHandle);
        foreach(var child in type.GetNestedTypes(BindingFlags.Public|BindingFlags.NonPublic)) WInitializeNestedStatics(child);
    }
    private static int WProjectileId(Projectile p) => WorkbenchSpawnSequences.TryGetValue(p.whoAmI,out int sequence) ? sequence : -1;
    private sealed class WorkbenchInvariantException(string message) : Exception(message) { }
    private static JsonNode? WFinite(float value) => float.IsFinite(value) ? JsonValue.Create(value) : null;
    private static void WKeys(JsonNode? node,string context,params string[] allowed)
    {
        if(node==null) return;
        foreach(var key in node.AsObject().Select(k=>k.Key)) if(!allowed.Contains(key)) throw new ArgumentException("Unknown "+context+" field: "+key);
    }
    private static T WState<T>(GeneratedProjectile host,string name) => (T)typeof(GeneratedProjectile).GetField(name,TestInstance)!.GetValue(host)!;
    private static int WInt(JsonNode? node,string name,int fallback) => node?[name]?.GetValue<int>() ?? fallback;
    private static float WFloat(JsonNode? node,string name,float fallback)
    {
        float value=node?[name]?.GetValue<float>() ?? fallback;
        if(!float.IsFinite(value)) throw new ArgumentException(name+" must be finite");
        return value;
    }
}
