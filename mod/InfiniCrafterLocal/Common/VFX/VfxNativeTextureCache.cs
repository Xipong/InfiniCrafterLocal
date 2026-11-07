#nullable enable
using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.VFX;

// Native resource access is selected by typed library ID, never inferred from a file path.
// Independent of ParticleLibrary instancing, backend option, buffers and shader readiness.
public sealed class VfxNativeTextureCache : ModSystem
{
    private static readonly Dictionary<string,Texture2D> Ready=new(StringComparer.Ordinal);
    private static readonly HashSet<string> Attempted=new(StringComparer.Ordinal);
    private static readonly object Gate=new();
    private static int Epoch;
    private static bool Unloaded;
    internal static Texture2D? TryGet(string id)
    {
        if(Main.dedServ||!VfxLibraryTextures.TryGetPath(id,out var path))return null;
        int epoch;
        lock(Gate) {
            if(Unloaded)return null;
            if(Ready.TryGetValue(id,out var texture))return texture;
            if(Main.graphics?.GraphicsDevice is null||!Attempted.Add(id))return null;
            epoch=Epoch;
        }
        Main.QueueMainThreadAction(()=>{
            try {
                lock(Gate)if(Unloaded||epoch!=Epoch)return;
                var texture=ModContent.Request<Texture2D>(path,AssetRequestMode.ImmediateLoad).Value;
                lock(Gate)if(!Unloaded&&epoch==Epoch)Ready[id]=texture;
            } catch(Exception error) {
                InfiniCrafterLocalMod.Instance?.Logger.Warn("Explicit material library texture "+path+" unavailable; no fallback: "+error.Message);
            }
        });
        return null;
    }
    public override void Load() {lock(Gate){Unloaded=false;Epoch++;Attempted.Clear();}}
    public override void Unload() {lock(Gate){Unloaded=true;Epoch++;Ready.Clear();Attempted.Clear();}}
    // ModContent owns/disposes these textures. World transitions may safely retain them.
}
