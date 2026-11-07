using System;
using System.Text.Json.Nodes;

internal static partial class EngineRuntimeChecks
{
    private static void CheckWorkbenchWorldAssertions()
    {
        var scene=JsonNode.Parse("{\"world\":{\"trackTiles\":[{\"tileX\":54,\"tileY\":46}]}}")!.AsObject();
        JsonObject Check()=>new(){["kind"]="tile_at",["tick"]=0,["tileX"]=54,["tileY"]=46,["hasTile"]=true,["ownedTileKey"]="GeneratedOwned_3x2_open_floor"};
        var valid=Check();WValidateWorldAssertion(valid,scene,1);
        foreach(string key in new[]{"GeneratedOwned_03x2_open_floor","GeneratedOwned_17x2_open_floor","GeneratedOwned_3x2_open_unknown","GeneratedOwned_3x2_platform_floor","unknown"}) {
            var bad=Check();bad["ownedTileKey"]=key;Refuse(bad);
        }
        var mixed=Check();mixed["tileId"]=215;Refuse(mixed);
        var absent=Check();absent["hasTile"]=false;Refuse(absent);
        var missing=Check();missing.Remove("ownedTileKey");Refuse(missing);
        var nil=Check();nil["ownedTileKey"]=null;Refuse(nil);
        var cell=new JsonObject{["tileX"]=54,["tileY"]=46,["hasTile"]=true,["tileId"]=1000,["ownedTileKey"]="GeneratedOwned_3x2_open_floor"};
        var frames=new JsonArray(new JsonObject{["tick"]=0,["world"]=new JsonObject{["tiles"]=new JsonArray(cell)}});
        if(!WWorldAssertion(valid,frames))throw new Exception("Owned tile observer rejected matching symbolic identity");
        cell["tileId"]=1500;
        if(!WWorldAssertion(valid,frames))throw new Exception("Owned tile observer depended on load-order numeric ID");
        cell["ownedTileKey"]="GeneratedOwned_3x2_solid_floor";
        if(WWorldAssertion(valid,frames))throw new Exception("Owned tile observer accepted wrong structural identity");
        cell["ownedTileKey"]=null;cell["tileId"]=215;
        if(WWorldAssertion(valid,frames))throw new Exception("Native campfire substituted for owned tile");
        var native=Check();native.Remove("ownedTileKey");native["tileId"]=215;WValidateWorldAssertion(native,scene,1);
        if(!WWorldAssertion(native,frames))throw new Exception("Native campfire observer rejected native identity");
        void Refuse(JsonObject bad) {
            try { WValidateWorldAssertion(bad,scene,1); }
            catch(ArgumentException) { return; }
            throw new Exception("Invalid tile identity assertion accepted: "+bad.ToJsonString());
        }
    }
}
