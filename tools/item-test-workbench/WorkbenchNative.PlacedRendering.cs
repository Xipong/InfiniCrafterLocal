using System;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using Terraria;

// Executes the production placed-body renderer over genuine ledger views.
// No native tile body, placement claim, sprite pose or pixels are synthesized.
internal sealed class WNativePlacedBodies : IDisposable
{
    delegate bool DrawOriginal(SpriteBatch batch,Texture2D texture,RuntimePlacedBodySpec body,Rectangle footprint,Vector2 camera,Color color,Rectangle? alphaBounds);
    delegate bool DrawObserver(DrawOriginal orig,SpriteBatch batch,Texture2D texture,RuntimePlacedBodySpec body,Rectangle footprint,Vector2 camera,Color color,Rectangle? alphaBounds);
    readonly GeneratedPlacedBodyDrawSystem system=new();
    readonly Hook observer;
    public int SuccessfulDraws {get;private set;}
    JsonArray current=new();
    public JsonObject Report {get;}=new(){["scope"]="Original GeneratedPlacedBodyDrawSystem.PostDrawTiles over native ledger views; neutral background, not complete terrain/world rendering",["frames"]=new JsonArray()};
    public WNativePlacedBodies()
    {
        if(!GeneratedPlacedBodyNativeAdapter.FeatureAvailable)throw new InvalidOperationException("Native placed-body adapter unavailable: "+GeneratedPlacedBodyNativeAdapter.UnsupportedBoundary);
        observer=new Hook(typeof(GeneratedPlacedBodyDrawSystem).GetMethod("DrawBody",BindingFlags.NonPublic|BindingFlags.Static)!,
            (DrawObserver)((orig,batch,texture,body,footprint,camera,color,alpha)=>{
                bool drawn=orig(batch,texture,body,footprint,camera,color,alpha);
                if(drawn)SuccessfulDraws++;
                current.Add(new JsonObject{["nativeDrawReturned"]=drawn,["footprintX"]=footprint.X,["footprintY"]=footprint.Y,["footprintWidth"]=footprint.Width,["footprintHeight"]=footprint.Height,["textureWidth"]=texture.Width,["textureHeight"]=texture.Height,["renderSizePx"]=body.RenderSizePx,["pivotSpace"]=body.PivotSpace,["imagePivotX"]=body.ImagePivotX,["imagePivotY"]=body.ImagePivotY,["cameraX"]=camera.X,["cameraY"]=camera.Y,["lightR"]=color.R,["lightG"]=color.G,["lightB"]=color.B,["entrypoint"]="Original GeneratedPlacedBodyDrawSystem.DrawBody -> SpriteBatch.Draw"});
                return drawn;
            }));
    }
    public void Draw(int tick)
    {
        current=new JsonArray();system.PostDrawTiles();
        Report["frames"]!.AsArray().Add(new JsonObject{["tick"]=tick,["draws"]=current});
    }
    public void Dispose()=>observer.Dispose();
}

internal sealed partial class WNativeVfxRenderer
{
    WNativePlacedBodies? placedBodies;
    public void SetPlacedBodies(WNativePlacedBodies bodies){placedBodies=bodies;Report["placedBodyRendering"]=bodies.Report;}
}
