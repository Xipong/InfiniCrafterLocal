using System;
using System.Text.Json.Nodes;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateRecallSpawn(JsonNode? spawn, bool fullPlayer)
    {
        if(spawn is null)return;
        if(!fullPlayer)throw new NotSupportedException("Recall spawn scene requires full native Player.Update");
        WKeys(spawn,"recall spawn","worldTileX","worldTileY","playerTileX","playerTileY");
        foreach(string key in new[]{"worldTileX","worldTileY"})
            if(spawn[key] is null)throw new ArgumentException("Recall spawn scene requires both world tile coordinates");
        foreach(string key in new[]{"worldTileX","playerTileX"})
            if(spawn[key] is not null && (WInt(spawn,key,-2)<(key=="worldTileX"?0:-1)||WInt(spawn,key,0)>98))throw new ArgumentException("Recall spawn X outside controlled native world");
        foreach(string key in new[]{"worldTileY","playerTileY"})
            if(spawn[key] is not null && (WInt(spawn,key,-2)<(key=="worldTileY"?0:-1)||WInt(spawn,key,0)>598))throw new ArgumentException("Recall spawn Y outside controlled native world");
        if((spawn["playerTileX"] is null)!=(spawn["playerTileY"] is null))throw new ArgumentException("Recall player spawn override requires both coordinates");
    }
    private sealed class WRecallSpawn : IDisposable
    {
        private readonly Player owner;
        private readonly int worldX=Terraria.Main.spawnTileX,worldY=Terraria.Main.spawnTileY,playerX,playerY;
        public WRecallSpawn(Player owner,JsonNode? spawn,JsonObject scene)
        {
            this.owner=owner;playerX=owner.SpawnX;playerY=owner.SpawnY;
            if(spawn is null)return;
            Terraria.Main.spawnTileX=WInt(spawn,"worldTileX",0);Terraria.Main.spawnTileY=WInt(spawn,"worldTileY",0);
            owner.SpawnX=WInt(spawn,"playerTileX",-1);owner.SpawnY=WInt(spawn,"playerTileY",-1);
            scene["recallSpawn"]=new JsonObject{["worldTileX"]=Terraria.Main.spawnTileX,["worldTileY"]=Terraria.Main.spawnTileY,["playerTileX"]=owner.SpawnX,["playerTileY"]=owner.SpawnY,
                ["scope"]="Explicit spawn coordinates only; production TryRecallHome selects them and invokes original Player.Teleport. No Player.Spawn, bed validation or world safety simulation."};
        }
        public void Dispose(){Terraria.Main.spawnTileX=worldX;Terraria.Main.spawnTileY=worldY;owner.SpawnX=playerX;owner.SpawnY=playerY;}
    }
}
