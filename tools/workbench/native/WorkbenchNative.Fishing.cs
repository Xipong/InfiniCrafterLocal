using System;
using System.Linq;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Scene data and observations only. Native ItemCheck and bobber AI own all fishing decisions.
    private sealed class WFishingScene : IDisposable
    {
        readonly Player player;
        readonly bool autoReel, oldText, alternate;
        readonly Terraria.GameContent.ChumBucketProjectileHelper oldChum;
        readonly JsonArray observations;
        bool pulsed, reeled;
        public static void Validate(JsonNode? settings, bool full, int width)
        {
            if(settings is null)return;
            if(!full)throw new ArgumentException("Fishing scene requires full native player update");
            WKeys(settings,"fishing","water","reelOnBite","reelInput");
            if((settings["reelInput"]?.GetValue<string>()??"primary") is not ("primary" or "alt"))throw new ArgumentException("Fishing reelInput must be primary or alt");
            var water=settings["water"];
            if(water is null)return;
            WKeys(water,"fishing water","tileX","tileY","width","height");
            int x=WInt(water,"tileX",-1),y=WInt(water,"tileY",-1),w=WInt(water,"width",0),h=WInt(water,"height",0);
            if(x<1||y<1||w<1||h<1||w>100||h>60||x+w>=width||y+h>=600)throw new ArgumentException("Fishing water must fit initialized world and be at most100x60 tiles");
        }
        public WFishingScene(Player owner, JsonNode settings, JsonObject report)
        {
            player=owner;autoReel=settings["reelOnBite"]?.GetValue<bool>()??false;alternate=settings["reelInput"]?.GetValue<string>()=="alt";
            var water=settings["water"];
            if(water is not null)for(int x=WInt(water,"tileX",0);x<WInt(water,"tileX",0)+WInt(water,"width",0);x++)for(int y=WInt(water,"tileY",0);y<WInt(water,"tileY",0)+WInt(water,"height",0);y++)if(Terraria.Main.tile[x,y].HasTile)throw new ArgumentException("Fishing water overlaps solid scene tiles");
            oldText=Terraria.Main.showItemText;Terraria.Main.showItemText=false;
            oldChum=Terraria.Main.instance.ChumBucketProjectileHelper;
            Terraria.Main.instance.ChumBucketProjectileHelper=new Terraria.GameContent.ChumBucketProjectileHelper();
            observations=new JsonArray();report["fishing"]=new JsonObject{["scope"]="Native fishing in a static water test pool; terrain/liquid artwork not rendered, no forced bite/catch",["water"]=settings["water"]?.DeepClone(),["observations"]=observations};

            if(water is not null)for(int x=WInt(water,"tileX",0);x<WInt(water,"tileX",0)+WInt(water,"width",0);x++)for(int y=WInt(water,"tileY",0);y<WInt(water,"tileY",0)+WInt(water,"height",0);y++){
                var tile=Terraria.Main.tile[x,y];tile.LiquidType=LiquidID.Water;tile.LiquidAmount=255;
            }
        }
        public void BeforeUpdate(int tick)
        {
            if(pulsed){player.controlUseItem=false;pulsed=false;}
            var bobber=Terraria.Main.projectile.FirstOrDefault(p=>p.active&&p.bobber&&p.owner==player.whoAmI);
            if(autoReel&&!reeled&&bobber is not null&&bobber.ai[1]<0){player.controlUseItem=true;player.altFunctionUse=alternate?1:0;pulsed=reeled=true;observations.Add(new JsonObject{["tick"]=tick,["kind"]="natural_bite_reel_input",["bobberId"]=bobber.identity,["ai1"]=bobber.ai[1]});}
        }
        public void Observe(int tick, bool final)
        {
            if(tick%30!=0&&!pulsed&&!final)return;
            observations.Add(new JsonObject{["tick"]=tick,["kind"]="native_state",["mana"]=player.statMana,["dead"]=player.dead,["heldFishingPower"]=player.HeldItem.fishingPole,["heldShoot"]=player.HeldItem.shoot,["bobbers"]=new JsonArray(Terraria.Main.projectile.Where(p=>p.active&&p.bobber&&p.owner==player.whoAmI).Select(p=>(JsonNode?)new JsonObject{["type"]=p.type,["wet"]=p.wet,["ai0"]=p.ai[0],["ai1"]=p.ai[1],["x"]=p.position.X,["y"]=p.position.Y}).ToArray()),["inventory"]=new JsonArray(player.inventory.Select((i,s)=>(i,s)).Where(x=>!x.i.IsAir).Select(x=>(JsonNode?)new JsonObject{["slot"]=x.s,["type"]=x.i.type,["stack"]=x.i.stack,["bait"]=x.i.bait}).ToArray())});
        }
        public void Dispose(){Terraria.Main.showItemText=oldText;Terraria.Main.instance.ChumBucketProjectileHelper=oldChum;}
    }
}
