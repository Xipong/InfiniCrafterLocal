using System;
using System.Linq;
using System.Text.Json.Nodes;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static Hook WObserveDirectNpcDamage(Action<JsonObject> record) => new(
        typeof(Player).GetMethod(nameof(Player.ApplyDamageToNPC))!,
        (Action<Action<Player,NPC,int,float,int,bool,DamageClass,bool>,Player,NPC,int,float,int,bool,DamageClass,bool>)((orig,player,npc,damage,knockback,direction,crit,damageClass,variation)=>{
            int before=npc.life;orig(player,npc,damage,knockback,direction,crit,damageClass,variation);
            record(new JsonObject{["kind"]="native_direct_npc_damage",["npcId"]=npc.whoAmI,["requestedDamage"]=damage,["lifeBefore"]=before,["lifeAfter"]=npc.life,["lifeLost"]=Math.Max(0,before-npc.life),["entrypoint"]="Player.ApplyDamageToNPC (original)",["sourceEntityInferred"]=false});
        }));
    private static bool WNoNonFinite(JsonArray frames)=>!frames.Any(f=>f!["player"]!["nonFinite"]!.GetValue<bool>() || f["dummy"]!["nonFinite"]!.GetValue<bool>()
        || new[]{"projectiles","hostiles"}.Any(key=>(f[key]?.AsArray()??new JsonArray()).Any(e=>e!["nonFinite"]!.GetValue<bool>())));

    // Pure observer regression, deliberately separate from actual-gameplay evidence.
    public static void CheckWorkbenchAssertions()
    {
        JsonObject Sample()=>new(){["player"]=new JsonObject{["nonFinite"]=false},["dummy"]=new JsonObject{["nonFinite"]=false},
            ["projectiles"]=new JsonArray(new JsonObject{["nonFinite"]=false}),["hostiles"]=new JsonArray(new JsonObject{["nonFinite"]=false})};
        if(!WNoNonFinite(new JsonArray(Sample())))throw new Exception("Finite observer control rejected");
        foreach(string key in new[]{"player","dummy","projectiles","hostiles"}) {
            var last=Sample();if(key is "player" or "dummy")last[key]!["nonFinite"]=true;else last[key]![0]!["nonFinite"]=true;
            if(WNoNonFinite(new JsonArray(Sample(),last)))throw new Exception("Final-frame nonfinite observer missed "+key);
        }
        CheckWorkbenchTargetHitAssertions();
        Console.WriteLine("PASS: finite and final-frame player/dummy/projectile/hostile snapshot and target-specific hit assertion controls (not gameplay)");
    }
    // Assertions read observed native state/events. They never drive item/projectile logic.
    private static bool WLifecycleKind(string kind) => kind is "entity_spawn_count" or "entity_hit_count_at_least" or "entity_hit_count"
        or "entity_peak_active_at_most" or "entity_inactive" or "entity_natural_expiry"
        or "generated_stack_at" or "exhaustion_at" or "target_effect_at" or "target_hit_damage_at";

    private static void WValidateLifecycleAssertion(JsonNode check, GeneratedItemData? data, int ticks)
    {
        string kind=check["kind"]!.GetValue<string>();
        if(data is null) throw new ArgumentException("Generated lifecycle assertions require a generated item");
        if(kind is "target_effect_at" or "target_hit_damage_at") {
            if(kind=="target_hit_damage_at") {
                WKeys(check,"target hit assertion","kind","tick","value");
                if(check["value"] is null || WInt(check,"value",-1)<0 || WInt(check,"tick",-1)<0 || WInt(check,"tick",-1)>=ticks)throw new ArgumentException("Target hit assertion requires nonnegative damage and in-range tick");
                return;
            }
            WKeys(check,"target effect assertion","kind","tick","stat","value");
            if(check["stat"]?.GetValue<string>() is not ("count" or "lifeRegenPenalty" or "defenseDelta" or "contactMultiplier" or "velocityRetentionPerTick" or "lifeRegen" or "vx" or "vy"))throw new ArgumentException("Unsupported target effect stat");
            if(check["value"] is null || WInt(check,"tick",-1)<0 || WInt(check,"tick",-1)>=ticks)throw new ArgumentException("Target effect assertion requires value and in-range tick");
            WFloat(check,"value",0); return;
        }
        bool hitCount=kind is "entity_hit_count" or "entity_hit_count_at_least";
        if(hitCount && check["npcId"] is not null && (WInt(check,"npcId",-1)<0 || WInt(check,"npcId",-1)>=Terraria.Main.maxNPCs))
            throw new ArgumentException("Hit assertion npcId must be a valid native NPC slot");
        bool timed=kind is "generated_stack_at" or "exhaustion_at";
        bool noValue=kind is "entity_inactive" or "entity_natural_expiry";
        WKeys(check,"lifecycle assertion",hitCount?new[]{"kind","entityId","value","npcId"}:timed?new[]{"kind","tick","value"}:noValue?new[]{"kind","entityId"}:new[]{"kind","entityId","value"});
        if(!timed && (check["entityId"]?.GetValue<string>() is not string entity || data.RuntimeProgram.TryGetEntity(entity)?.IsProjectileEntity!=true))
            throw new ArgumentException("Lifecycle assertion requires an existing projectile entityId");
        if(!noValue && (check["value"] is null || WInt(check,"value",-1)<0)) throw new ArgumentException("Lifecycle value must be a nonnegative integer");
        if(timed && (WInt(check,"tick",-1)<0 || WInt(check,"tick",-1)>=ticks)) throw new ArgumentException("Lifecycle tick outside scenario");
    }

    private static bool WLifecycleAssertion(string kind,JsonNode check,JsonArray frames,string itemId)
    {
        var post=frames.Where(f=>f!["phase"] is null && f["tick"]!.GetValue<int>()>=0).ToArray();
        var events=frames.SelectMany(f=>f!["events"]!.AsArray()).Where(e=>e is not null).ToArray();
        if(kind=="target_hit_damage_at") {
            var frame=post.LastOrDefault(f=>f!["tick"]!.GetValue<int>()==WInt(check,"tick",-1));
            return frame is not null && frame["events"]!.AsArray().Any(e=>e?["kind"]?.GetValue<string>() is "hit" or "item_hit" && e["npcId"]!.GetValue<int>()==frame["dummy"]!["slot"]!.GetValue<int>() && e["damageDone"]!.GetValue<int>()==WInt(check,"value",0));
        }
        if(kind=="target_effect_at") {
            var frame=post.LastOrDefault(f=>f!["tick"]!.GetValue<int>()==WInt(check,"tick",-1));
            if(frame is null)return false;
            var state=frame["dummy"]!["targetState"]!; string stat=check["stat"]!.GetValue<string>();
            var observed=stat is "lifeRegen" or "vx" or "vy"?state[stat]:state["generatedEffects"]![stat];
            return observed is not null && Math.Abs(WReportNumber(observed)-WFloat(check,"value",0))<0.00001f;
        }
        int value=WInt(check,"value",0);
        if(kind is "generated_stack_at" or "exhaustion_at") {
            var frame=post.LastOrDefault(f=>f!["tick"]!.GetValue<int>()==WInt(check,"tick",-1));
            if(frame is null)return false;
            var player=frame["player"]!;
            if(kind=="generated_stack_at") return new[]{"inventory","armor"}.SelectMany(key=>player[key]!.AsArray())
                .Where(i=>i!["itemId"]?.GetValue<string>()==itemId).Sum(i=>i!["stack"]!.GetValue<int>())==value;
            return player["generatedItemExhaustion"]!.AsArray().Where(e=>e!["itemId"]!.GetValue<string>()==itemId)
                .Select(e=>e!["remainingTicks"]!.GetValue<int>()).DefaultIfEmpty(0).Max()==value;
        }
        string entity=check["entityId"]!.GetValue<string>();
        var entityEvents=events.Where(e=>e!["entityId"]?.GetValue<string>()==entity).ToArray();
        if(kind=="entity_spawn_count")return entityEvents.Where(e=>e!["kind"]!.GetValue<string>()=="entity_configured")
            .Select(e=>e!["projectileId"]!.GetValue<int>()).Distinct().Count()==value;
        if(kind is "entity_hit_count" or "entity_hit_count_at_least") {
            int hits=entityEvents.Count(e=>e!["kind"]!.GetValue<string>()=="hit"
                && (check["npcId"] is null || e["npcId"]?.GetValue<int>()==WInt(check,"npcId",-1)));
            return kind=="entity_hit_count"?hits==value:hits>=value;
        }
        if(kind=="entity_natural_expiry")return entityEvents.Any(e=>e!["kind"]!.GetValue<string>()=="kill" && e["nativeLifetimeDepleted"]?.GetValue<bool>()==true && e["generatedExpiryEventRan"]?.GetValue<bool>()!=false);
        if(kind=="entity_inactive")return post.Length>0 && !post[^1]!["projectiles"]!.AsArray().Any(p=>p!["entityId"]?.GetValue<string>()==entity);
        // Include configuration-time counts, catching transient child allocations between snapshots.
        if(kind=="entity_peak_active_at_most")return post.All(f=>f!["projectiles"]!.AsArray().Count(p=>p!["entityId"]?.GetValue<string>()==entity)<=value)
            && entityEvents.Where(e=>e!["kind"]!.GetValue<string>()=="entity_configured").All(e=>e!["activeEntityCount"]!.GetValue<int>()<=value);
        throw new ArgumentException("Unknown lifecycle assertion");
    }
}
