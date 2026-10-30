using System;
using System.Text.Json.Nodes;

internal static partial class EngineRuntimeChecks
{
    // Observer-only controls. Allocating a child or hitting another NPC must not
    // certify that a projectile reached the requested downstream target.
    private static void CheckWorkbenchTargetHitAssertions()
    {
        JsonObject Hit(string entity, int npc) => new() {
            ["kind"]="hit", ["entityId"]=entity, ["npcId"]=npc
        };
        var frames=new JsonArray(new JsonObject {
            ["tick"]=0, ["events"]=new JsonArray(
                Hit("child",0), Hit("root",2), Hit("child",2),
                new JsonObject { ["kind"]="entity_configured", ["entityId"]="child", ["npcId"]=3 })
        });
        var check=new JsonObject { ["kind"]="entity_hit_count", ["entityId"]="child", ["npcId"]=2, ["value"]=1 };
        if(!WLifecycleAssertion("entity_hit_count",check,frames,"item"))throw new Exception("Target-specific child hit missed");
        check["value"]=2;
        if(WLifecycleAssertion("entity_hit_count",check,frames,"item"))throw new Exception("Other entity or target counted as requested child hit");
        check["npcId"]=3;check["value"]=0;
        if(!WLifecycleAssertion("entity_hit_count",check,frames,"item"))throw new Exception("Allocation counted as a hit");
        check["value"]=1;
        if(WLifecycleAssertion("entity_hit_count_at_least",check,frames,"item"))throw new Exception("Missing downstream hit accepted");
        check.Remove("npcId");check["value"]=2;
        if(!WLifecycleAssertion("entity_hit_count",check,frames,"item"))throw new Exception("Unfiltered entity hit total changed");

        var data=ChildCombatFixture();
        WValidateLifecycleAssertion(check,data,2);
        foreach(int slot in new[]{-1,Terraria.Main.maxNPCs}) {
            check["npcId"]=slot;
            bool rejected=false;
            try { WValidateLifecycleAssertion(check,data,2); } catch(ArgumentException) { rejected=true; }
            if(!rejected)throw new Exception("Invalid native target slot accepted");
        }
        check["npcId"]=2;check["kind"]="entity_spawn_count";
        bool wrongKindRejected=false;
        try { WValidateLifecycleAssertion(check,data,2); } catch(ArgumentException) { wrongKindRejected=true; }
        if(!wrongKindRejected)throw new Exception("Target filter accepted on unrelated assertion");
    }
}
