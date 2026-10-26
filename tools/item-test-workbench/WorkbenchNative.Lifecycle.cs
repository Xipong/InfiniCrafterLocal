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
        Console.WriteLine("PASS: finite and final-frame player/dummy/projectile/hostile snapshot assertion controls (not gameplay)");
    }
    // Assertions read observed native state/events. They never drive item/projectile logic.
    private static bool WLifecycleKind(string kind) => kind is "entity_spawn_count" or "entity_hit_count_at_least"
        or "entity_peak_active_at_most" or "entity_inactive" or "entity_natural_expiry"
        or "generated_stack_at" or "exhaustion_at";

    private static void WValidateLifecycleAssertion(JsonNode check, GeneratedItemData? data, int ticks)
    {
        string kind=check["kind"]!.GetValue<string>();
        bool timed=kind is "generated_stack_at" or "exhaustion_at";
        bool noValue=kind is "entity_inactive" or "entity_natural_expiry";
        WKeys(check,"lifecycle assertion",timed?new[]{"kind","tick","value"}:noValue?new[]{"kind","entityId"}:new[]{"kind","entityId","value"});
        if(data is null) throw new ArgumentException("Generated lifecycle assertions require a generated item");
        if(!timed && (check["entityId"]?.GetValue<string>() is not string entity || data.RuntimeProgram.TryGetEntity(entity)?.IsProjectileEntity!=true))
            throw new ArgumentException("Lifecycle assertion requires an existing projectile entityId");
        if(!noValue && (check["value"] is null || WInt(check,"value",-1)<0)) throw new ArgumentException("Lifecycle value must be a nonnegative integer");
        if(timed && (WInt(check,"tick",-1)<0 || WInt(check,"tick",-1)>=ticks)) throw new ArgumentException("Lifecycle tick outside scenario");
    }

    private static bool WLifecycleAssertion(string kind,JsonNode check,JsonArray frames,string itemId)
    {
        var post=frames.Where(f=>f!["phase"] is null && f["tick"]!.GetValue<int>()>=0).ToArray();
        var events=frames.SelectMany(f=>f!["events"]!.AsArray()).Where(e=>e is not null).ToArray();
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
        if(kind=="entity_hit_count_at_least")return entityEvents.Count(e=>e!["kind"]!.GetValue<string>()=="hit")>=value;
        if(kind=="entity_natural_expiry")return entityEvents.Any(e=>e!["kind"]!.GetValue<string>()=="kill" && e["nativeLifetimeDepleted"]?.GetValue<bool>()==true && e["generatedExpiryEventRan"]?.GetValue<bool>()!=false);
        if(kind=="entity_inactive")return post.Length>0 && !post[^1]!["projectiles"]!.AsArray().Any(p=>p!["entityId"]?.GetValue<string>()==entity);
        // Include configuration-time counts, catching transient child allocations between snapshots.
        if(kind=="entity_peak_active_at_most")return post.All(f=>f!["projectiles"]!.AsArray().Count(p=>p!["entityId"]?.GetValue<string>()==entity)<=value)
            && entityEvents.Where(e=>e!["kind"]!.GetValue<string>()=="entity_configured").All(e=>e!["activeEntityCount"]!.GetValue<int>()<=value);
        throw new ArgumentException("Unknown lifecycle assertion");
    }
}
