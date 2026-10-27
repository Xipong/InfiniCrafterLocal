using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Scene inputs only. Original NPC.UpdateNPC integrates movement/status and
    // original strike/collision code computes damage; no parallel physics model.
    private static void WValidateTarget(JsonNode? settings)
    {
        if(settings is null)return;
        if(settings["nativeType"]?.GetValue<string>() is string type && type is not ("zombie" or "target_dummy"))throw new ArgumentException("Controlled target nativeType must be zombie or target_dummy");
        if(WInt(settings,"defense",0) is <0 or >1000)throw new ArgumentException("Controlled target defense must be0..1000");
        foreach(string axis in new[]{"vx","vy"})if(Math.Abs(WFloat(settings,axis,0))>8)throw new ArgumentException("Controlled target velocity must be within8px/tick");
        foreach(string dimension in new[]{"width","height"})if(WInt(settings,dimension,32) is <1 or >512)throw new ArgumentException("Controlled target dimensions must be1..512");
    }
    private static void WConfigureTarget(NPC npc,JsonNode? settings)
    {
        npc.defense=WInt(settings,"defense",0);npc.damage=0;
        npc.velocity=new Microsoft.Xna.Framework.Vector2(WFloat(settings,"vx",0),WFloat(settings,"vy",0));
    }
    private static JsonObject WTargetState(NPC npc)
    {
        var effects=RuntimeNpcEffects.GetTotals(npc);
        return new(){["defense"]=npc.defense,["lifeMax"]=npc.lifeMax,["lifeRegen"]=npc.lifeRegen,
        ["generatedEffects"]=new JsonObject{["count"]=effects.Count,["lifeRegenPenalty"]=effects.Regen,["defenseDelta"]=effects.Defense,["contactMultiplier"]=effects.Contact,["velocityRetentionPerTick"]=effects.Retention},
        ["vx"]=WFinite(npc.velocity.X),["vy"]=WFinite(npc.velocity.Y),
        ["nativeBuffs"]=new JsonArray(Enumerable.Range(0,npc.buffType.Length).Where(i=>npc.buffType[i]>0&&npc.buffTime[i]>0).Select(i=>(JsonNode?)new JsonObject{["id"]=npc.buffType[i],["ticks"]=npc.buffTime[i]}).ToArray()),
        ["scope"]="Native state at snapshot boundary. Generated effect totals are active modifiers, not proof of a hit, damage, or contact; defenseDelta is applied via ModifyIncomingHit, not npc.defense. Buff presence is sampled uptime; read aiStyle/noTileCollide and scene intervention receipts for controlled versus genuine training-dummy behavior."};
    }
    private static void WValidateVanillaPerformance(Item item,GeneratedItemData? data,bool client)
    {
        if(data is not null)return;
        if(item.damage<=0 || item.accessory || item.createTile>=0 || item.createWall>=0)throw new NotSupportedException("Vanilla parent is not an admitted damage weapon; noncombat parents are not zero-damage benchmarks");
        if(!item.noMelee&&!client)throw new NotSupportedException("Vanilla parent requires native client melee contact; dedicated full/item_check cannot fairly measure its complete damage");
        if(item.useAmmo!=0 && item.useAmmo!=AmmoID.Arrow && item.useAmmo!=AmmoID.Bullet && item.useAmmo!=AmmoID.Flare && item.useAmmo!=AmmoID.FallenStar)throw new NotSupportedException("Vanilla parent ammo category is outside admitted arrow/bullet/flare/fallen-star provisioning");
    }
    // ApplyItemTime is the native firing/use clock, unlike input-held duration or
    // projectile count (a single use may emit many projectiles).
    private static Hook WObserveUseCadence(Player owner,Action<JsonObject> record)=>new(
        typeof(Player).GetMethod(nameof(Player.ApplyItemTime))!,
        (Action<Action<Player,Item,float,bool?>,Player,Item,float,bool?>)((orig,p,item,multiplier,callUseItem)=>{
            int before=p.itemTime;orig(p,item,multiplier,callUseItem);
            if(ReferenceEquals(p,owner))record(new JsonObject{["kind"]="native_item_time_applied",["itemType"]=item.type,["before"]=before,["after"]=p.itemTime,["itemAnimation"]=p.itemAnimation,["entrypoint"]="Player.ApplyItemTime (original)", ["scope"]="Native use-clock applications, not projectile count or inferred successful damage"});
        }));
}
