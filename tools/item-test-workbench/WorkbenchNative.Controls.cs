using System;
using System.Text.Json.Nodes;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateControls(JsonNode action,bool fullPlayer)
    {
        if(!fullPlayer)throw new NotSupportedException("Movement controls require actual full Player.Update");
        WKeys(action,"controls action","kind","tick","left","right","jump");
        foreach(string key in new[]{"left","right","jump"})
            if(action[key] is not JsonValue value || !value.TryGetValue<bool>(out _))throw new ArgumentException("controls requires explicit boolean left, right and jump");
    }
    private static void WApplyControls(Player owner,JsonNode action)
    {
        owner.controlLeft=action["left"]!.GetValue<bool>();
        owner.controlRight=action["right"]!.GetValue<bool>();
        owner.controlJump=action["jump"]!.GetValue<bool>();
    }
    private static JsonObject WControls(Player owner)=>new(){["left"]=owner.controlLeft,["right"]=owner.controlRight,["jump"]=owner.controlJump,
        ["scope"]="Commanded native input flags; original Player.Update owns acceleration, jump, gravity, collision and friction"};
}
