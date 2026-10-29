using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using Terraria.DataStructures;
using Terraria.ModLoader;

// Observation only: native layers select the actual visible item, resolve its
// exact equip_overlay PNG, choose its pivot/scale and append original DrawData.
internal sealed class WNativeEquipmentLayers : IDisposable
{
    const BindingFlags All=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
    readonly Hook observer;
    readonly HashSet<Texture2D> textures=new();
    delegate void Original(GeneratedEquipOverlayDrawLayerBase self,ref PlayerDrawSet draw);
    delegate void Observe(Original orig,GeneratedEquipOverlayDrawLayerBase self,ref PlayerDrawSet draw);
    public WNativeEquipmentLayers(Func<JsonObject> frame)
    {
        PlayerDrawLayer[] layers={new GeneratedEquipOverlayHeadDrawLayer(),new GeneratedEquipOverlayBodyDrawLayer(),new GeneratedEquipOverlayLegsDrawLayer(),new GeneratedEquipOverlayAccessoryDrawLayer(),new GeneratedEquipOverlayFrontAccessoryDrawLayer()};
        foreach(var layer in layers)typeof(PlayerDrawLayerLoader).GetMethod("Add",All)!.Invoke(null,new object[]{layer});
        observer=new Hook(typeof(GeneratedEquipOverlayDrawLayerBase).GetMethod("Draw",All)!,
            (Observe)((Original orig,GeneratedEquipOverlayDrawLayerBase self,ref PlayerDrawSet draw)=>{
                int before=draw.DrawDataCache.Count;orig(self,ref draw);
                var rows=frame()["equipmentOverlayDrawData"]!.AsArray();
                for(int i=before;i<draw.DrawDataCache.Count;i++){
                    var entry=draw.DrawDataCache[i];if(entry.texture is null)throw new InvalidOperationException("Native equipment overlay emitted null texture");textures.Add(entry.texture);
                    rows.Add(new JsonObject{["layer"]=self.GetType().Name,["entrypoint"]="PlayerDrawLayerLoader -> GeneratedEquipOverlayDrawLayerBase.Draw",["drawDataIndex"]=i,
                        ["textureWidth"]=entry.texture.Width,["textureHeight"]=entry.texture.Height,["positionX"]=entry.position.X,["positionY"]=entry.position.Y,
                        ["originX"]=entry.origin.X,["originY"]=entry.origin.Y,["scaleX"]=entry.scale.X,["scaleY"]=entry.scale.Y,["rotation"]=entry.rotation,
                        ["colorR"]=entry.color.R,["colorG"]=entry.color.G,["colorB"]=entry.color.B,["colorA"]=entry.color.A,["effects"]=entry.effect.ToString(),["shader"]=entry.shader});
                }
                frame()["equipmentOverlayDrawCount"]=rows.Count;
            }));
    }
    public bool Owns(Texture2D? texture)=>texture is not null&&textures.Contains(texture);
    public void BeginFrame()=>textures.Clear();
    public void Dispose()=>observer.Dispose();
}
