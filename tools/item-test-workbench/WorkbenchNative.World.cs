using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void WWriteWorldFixtures(string directory)
    {
        var placement=PersistencePlacementData("workbench-synthetic-campfire");
        placement.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.TileId=TileID.Campfire;
        placement.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.WallId=-1;
        placement.RuntimeProgram.ItemUse.Channel=false;
        placement.Gameplay.UseTime=placement.Gameplay.UseAnimation=20;
        placement.Gameplay.UseStyleName="swing";
        InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(placement);
        System.IO.File.WriteAllText(System.IO.Path.Combine(directory,"synthetic-world-campfire.json"),SwarmWire(placement).ToJson());
        var mining=GeneratedItemData.FromJson(System.IO.File.ReadAllText("tools/item-test-workbench/fixtures/synthetic-client-contact.json"))!;
        mining.Id="workbench-synthetic-mining"; mining.Gameplay.PickPower=59;
        System.IO.File.WriteAllText(System.IO.Path.Combine(directory,"synthetic-world-mining.json"),SwarmWire(mining).ToJson());
    }
    private static WWorldScene? WActiveWorld;
    private static bool WWorldAssertionKind(string kind) => kind is "tile_at" or "placement_groups_at" or "placement_pending_at" or "generated_world_items_at";
    private static void WValidateWorld(JsonObject scenario, bool fullPlayer, bool clientPlayer)
    {
        var world=scenario["world"];
        if(world is null) return;
        if(!fullPlayer) throw new ArgumentException("world scenarios require full Player.Update");
        WKeys(world,"world","trackTiles","walls","updateDroppedItems");
        if(world["trackTiles"] is not JsonArray {Count:>0} cells || cells.Count>256) throw new ArgumentException("world.trackTiles requires 1..256 explicit cells");
        foreach(var cell in cells) { WKeys(cell,"tracked tile","tileX","tileY"); WWorldCoordinates(cell); }
        var walls=world["walls"]?.AsArray()??new JsonArray();
        if(walls.Count>32) throw new ArgumentException("At most32 wall rectangles");
        foreach(var wall in walls) {
            WKeys(wall,"wall rectangle","tileX","tileY","width","height","wallId"); WWorldCoordinates(wall);
            if(WInt(wall,"width",0)<1 || WInt(wall,"height",0)<1 || WInt(wall,"tileX",0)+WInt(wall,"width",0)>=99 || WInt(wall,"tileY",0)+WInt(wall,"height",0)>=599 || WInt(wall,"wallId",0)<=0 || WInt(wall,"wallId",0)>=WallID.Count) throw new ArgumentException("Wall rectangle must fit initialized world and select vanilla wallId");
        }
    }
    private static void WWorldCoordinates(JsonNode? node)
    {
        if(WInt(node,"tileX",-1) is <1 or >98 || WInt(node,"tileY",-1) is <1 or >598) throw new ArgumentException("World target must be inside initialized tilemap margin");
    }
    private static void WValidateWorldAction(JsonNode action, JsonObject scenario)
    {
        if(scenario["world"] is null) throw new ArgumentException("World commands require explicit world settings");
        WKeys(action,"world action","kind","tick","tileX","tileY"); WWorldCoordinates(action);
    }
    private static void WValidateWorldAssertion(JsonNode assertion, JsonObject scenario, int ticks)
    {
        if(scenario["world"] is null) throw new ArgumentException("World assertions require explicit world settings");
        string kind=assertion["kind"]!.GetValue<string>();
        WKeys(assertion,"world assertion",kind=="tile_at"?new[]{"kind","tick","tileX","tileY","hasTile","tileId"}:new[]{"kind","tick","value"});
        if(WInt(assertion,"tick",-1)<0 || WInt(assertion,"tick",-1)>=ticks) throw new ArgumentException("World assertion tick outside scenario");
        if(kind=="tile_at") {
            WWorldCoordinates(assertion);
            if(assertion["hasTile"] is null) throw new ArgumentException("tile_at requires hasTile");
            if(!scenario["world"]!["trackTiles"]!.AsArray().Any(c=>WInt(c,"tileX",-1)==WInt(assertion,"tileX",-2)&&WInt(c,"tileY",-1)==WInt(assertion,"tileY",-2))) throw new ArgumentException("tile_at must name a tracked cell");
            if(assertion["hasTile"]!.GetValue<bool>() && (WInt(assertion,"tileId",-1)<0 || WInt(assertion,"tileId",-1)>=TileID.Count)) throw new ArgumentException("Active tile assertion requires vanilla tileId");
        } else if(WInt(assertion,"value",-1)<0) throw new ArgumentException("World count assertion requires nonnegative value");
    }
    private static bool WWorldAssertion(JsonNode assertion, JsonArray frames)
    {
        var frame=frames.LastOrDefault(f=>WInt(f,"tick",-2)==WInt(assertion,"tick",-1) && f?["phase"] is null);
        var world=frame?["world"]; if(world is null)return false;
        string kind=assertion["kind"]!.GetValue<string>();
        if(kind=="tile_at") {
            var cell=world["tiles"]!.AsArray().Single(c=>WInt(c,"tileX",-1)==WInt(assertion,"tileX",-2)&&WInt(c,"tileY",-1)==WInt(assertion,"tileY",-2));
            bool expected=assertion["hasTile"]!.GetValue<bool>();
            return cell!["hasTile"]!.GetValue<bool>()==expected && (!expected || WInt(cell,"tileId",-1)==WInt(assertion,"tileId",-2));
        }
        string field=kind switch {"placement_groups_at"=>"placementGroups","placement_pending_at"=>"pendingReturns",_=>"generatedWorldItemUnits"};
        return WInt(world,field,-1)==WInt(assertion,"value",-2)
            && (kind!="generated_world_items_at" || WInt(world,"mismatchedReturnedDefinitions",-1)==0);
    }
    private sealed class WWorldScene : IDisposable
    {
        private readonly GeneratedPlacementLedgerSystem ledger;
        private readonly IDisposable boolSerializer=WithPersistenceBoolSerializer();
        private readonly JsonArray cells;
        private readonly string itemId;
        private readonly bool updateDroppedItems;
        private readonly string sourceNetworkDefinitionHash;
        private static string NetworkDefinitionHash(GeneratedItemData data) => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(data.ToNetworkJson()))).ToLowerInvariant();
        private readonly FieldInfo dropField=typeof(TileLoader).GetField("HookCanDrop",PersistenceStatic)!;
        private readonly object? oldDrop;
        private readonly int oldX=Player.tileTargetX, oldY=Player.tileTargetY;
        private readonly bool oldGen=WorldGen.gen,oldMap=Terraria.Main.mapEnabled;
        public WWorldScene(JsonObject settings, GeneratedPlacementLedgerSystem ledger, GeneratedItemData? data, JsonObject report)
        {
            this.ledger=ledger;updateDroppedItems=settings["updateDroppedItems"]?.GetValue<bool>()??false;this.itemId=data?.Id??"";sourceNetworkDefinitionHash=data is null?"":NetworkDefinitionHash(data);cells=settings["trackTiles"]!.AsArray();
            typeof(Terraria.Main).GetMethod("Initialize_TileAndNPCData2",PersistenceStatic)!.Invoke(null,null);
            // The native loader executes the unmodified production GlobalTile callback.
            // No fake CanDrop, placement outcome, return spawn or tile mutation is injected.
            oldDrop=dropField.GetValue(null);
            var hooks=(oldDrop as Func<int,int,int,bool>[]??Array.Empty<Func<int,int,int,bool>>()).ToList();
            hooks.Add(new GeneratedPlacementLedgerTile().CanDrop);dropField.SetValue(null,hooks.ToArray());
            foreach(var wall in settings["walls"]?.AsArray()??new JsonArray())
                for(int x=WInt(wall,"tileX",0);x<WInt(wall,"tileX",0)+WInt(wall,"width",0);x++)
                    for(int y=WInt(wall,"tileY",0);y<WInt(wall,"tileY",0)+WInt(wall,"height",0);y++) Terraria.Main.tile[x,y].WallType=(ushort)WInt(wall,"wallId",0);
            WorldGen.gen=false;Terraria.Main.mapEnabled=false;
            Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
            ledger.PostSetupContent();WActiveWorld=this;
            report["execution"]!["nativeMethods"]!.AsArray().Add(JsonValue.Create("Player.ItemCheck / PlaceThing; WorldGen.KillTile; GeneratedPlacementLedgerTile.CanDrop; GeneratedPlacementLedgerSystem.PostUpdateWorld; Item.NewItem"));
            report["coverage"]!["worldScope"]="Explicit native tile targets, generated placement ledger and tracked material returns; break_tile is external WorldGen.KillTile stimulus, not player mining. Tile/wall artwork, wiring, full world ecology and multiplayer are not certified.";
        }
        public void Action(string kind, JsonNode action, JsonArray events)
        {
            int x=WInt(action,"tileX",0),y=WInt(action,"tileY",0);
            if(kind=="tile_target") {Player.tileTargetX=x;Player.tileTargetY=y;Terraria.Main.mouseX=(int)(x*16+8-Terraria.Main.screenPosition.X);Terraria.Main.mouseY=(int)(y*16+8-Terraria.Main.screenPosition.Y);}
            else WorldGen.KillTile(x,y,fail:false,effectOnly:false,noItem:false);
            events.Add(new JsonObject{["kind"]="world_input",["input"]=kind,["tileX"]=x,["tileY"]=y,["entrypoint"]=kind=="tile_target"?"Native film input tile target and mouse coordinates":"WorldGen.KillTile (external break stimulus)"});
        }
        public void Update()
        {
            ledger.PostUpdateWorld();
            if(updateDroppedItems)for(int i=0;i<Terraria.Main.maxItems;i++)if(Terraria.Main.item[i].active)Terraria.Main.item[i].UpdateItem(i);
        }
        public JsonObject Snapshot()
        {
            var saved=new TagCompound();ledger.SaveWorldData(saved);
            var groups=saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2");
            var pending=saved.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2");
            var items=Terraria.Main.item.Where(i=>i is {active:true,stack:>0} && i.ModItem is GeneratedItem g && g.Data.Id==itemId).ToArray();
            var tiles=new JsonArray();
            foreach(var c in cells) {int x=WInt(c,"tileX",0),y=WInt(c,"tileY",0);var t=Terraria.Main.tile[x,y];tiles.Add(new JsonObject{["tileX"]=x,["tileY"]=y,["hasTile"]=t.HasTile,["tileId"]=(int)t.TileType,["wallId"]=(int)t.WallType,["frameX"]=(int)t.TileFrameX,["frameY"]=(int)t.TileFrameY});}
            return new JsonObject{["droppedItemUpdateScope"]=updateDroppedItems?"Original Item.UpdateItem each active native world item; no complete Main.UpdateWorld ecology":"notRun",["sourceNetworkDefinitionSha256"]=sourceNetworkDefinitionHash,["mismatchedReturnedDefinitions"]=items.Count(i=>NetworkDefinitionHash(((GeneratedItem)i.ModItem).Data)!=sourceNetworkDefinitionHash),["tiles"]=tiles,["targetX"]=Player.tileTargetX,["targetY"]=Player.tileTargetY,["placementGroups"]=groups.Count,["pendingReturns"]=pending.Count,["quarantinedReturns"]=saved.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Count,["returnFailures"]=new JsonArray(saved.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Select(q=>(JsonNode?)JsonValue.Create(q.GetString("cause"))).ToArray()),["generatedWorldItemUnits"]=items.Sum(i=>i.stack),["returnedItems"]=new JsonArray(items.Select(i=>(JsonNode?)new JsonObject{["slot"]=i.whoAmI,["x"]=i.position.X,["y"]=i.position.Y,["vx"]=i.velocity.X,["vy"]=i.velocity.Y,["width"]=i.width,["height"]=i.height,["stack"]=i.stack,["itemId"]=((GeneratedItem)i.ModItem).Data.Id,["networkDefinitionSha256"]=NetworkDefinitionHash(((GeneratedItem)i.ModItem).Data),["definitionMatchesSource"]=NetworkDefinitionHash(((GeneratedItem)i.ModItem).Data)==sourceNetworkDefinitionHash,["definitionSha256"]=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(((GeneratedItem)i.ModItem).Data.ToJson()))).ToLowerInvariant()}).ToArray())};
        }
        public void Dispose(){WActiveWorld=null;ledger.Unload();boolSerializer.Dispose();dropField.SetValue(null,oldDrop);Player.tileTargetX=oldX;Player.tileTargetY=oldY;WorldGen.gen=oldGen;Terraria.Main.mapEnabled=oldMap;}
    }
}
