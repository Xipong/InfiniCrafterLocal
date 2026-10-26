using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using Terraria.GameContent;
using Terraria.ID;

// Render resources only. Native Terraria owns motion, damage, AI and sprite transforms.
internal sealed class WNativeVanillaProjectileAssets:IDisposable
{
    static readonly Dictionary<int,string> ExpectedHashes=new()
    {
        [ProjectileID.WoodenArrowFriendly]="b5c1a2ef77f365d3458a5c2d6317ab640792822d8cc35ebec48d81393f233663",
        [ProjectileID.Bullet]="9a649ba443ca84851800d0001ae28bbce1ba3309dc6d93f4a1d6c832dd385859",
        [91]="a53165811a311f3452d4e078bae6b1d5eb0a031116f9f3c9c410a333282e06ed",
        [92]="fe122c614056f359c8c0b39deffc2c3770c362b3a0c45badc62e43e8ce845962",
        [357]="c2153f77e11087fcb078ae38527fa83bef29791e3700e30cc87fec4405a66d0f",
        [485]="f2ecdee1b0a9b47d52f3bebfa491ef3fa5b5c8354c6fb70140e3efff122e62c3",
    };
    readonly Dictionary<int,Asset<Texture2D>> original=new();
    readonly Dictionary<int,Asset<Texture2D>> loaded=new();
    readonly AssetRepository assets;
    public static bool Supports(int id)=>ExpectedHashes.ContainsKey(id);
    public JsonObject Report {get;}=new(){["entrypoint"]="Main.DrawProj (original)",["sourceCommit"]="c835594415e31ed88734dc778661014b48ffb648",["source"]="Pinned community Terraria 1.4.4.9 source PNGs, not HD outputs",["officialByteIdentityVerified"]=false,["textures"]=new JsonArray()};
    public WNativeVanillaProjectileAssets(WorkbenchGraphicsContext graphics,string root)
    {
        var readers=new AssetReaderCollection();
        readers.RegisterReader(new PngReader(graphics.Device),".png");
        assets=new AssetRepository(readers);
        try{
            foreach(var entry in ExpectedHashes){
                string path=Path.GetFullPath(Path.Combine(root,"Images","Projectile_"+entry.Key+".png"));
                for(FileSystemInfo? part=new FileInfo(path);part is not null;part=part is FileInfo file?file.Directory:((DirectoryInfo)part).Parent)
                    if(part.LinkTarget is not null)throw new InvalidDataException("Vanilla projectile asset must not traverse symlinks");
                if(!File.Exists(path)||new FileInfo(path).Length>4*1024*1024)throw new InvalidDataException("Missing/bounded vanilla projectile PNG: "+entry.Key);
                byte[] bytes=File.ReadAllBytes(path);
                string hash=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
                if(hash!=entry.Value)throw new InvalidDataException("Vanilla projectile PNG differs from pinned community source: "+entry.Key);
                using var input=new MemoryStream(bytes,writable:false);
                var texture=assets.CreateUntracked<Texture2D>(input,"Projectile_"+entry.Key+".png",AssetRequestMode.ImmediateLoad);
                loaded.Add(entry.Key,texture);
                if(texture.State!=AssetState.Loaded)throw new InvalidDataException("Vanilla projectile texture is not loaded: "+entry.Key);
                original.Add(entry.Key,TextureAssets.Projectile[entry.Key]);TextureAssets.Projectile[entry.Key]=texture;
                // Receipt and decoder consume the same verified bytes, never a second path read.
                Report["textures"]!.AsArray().Add(new JsonObject{["nativeType"]=entry.Key,["path"]=path,["sha256"]=hash,["loadedBytesSha256"]=hash,["state"]=texture.State.ToString(),["width"]=texture.Value.Width,["height"]=texture.Value.Height});
            }
        }catch{Dispose();throw;}
    }
    public void Dispose(){foreach(var p in original)TextureAssets.Projectile[p.Key]=p.Value;original.Clear();foreach(var p in loaded)p.Value.Dispose();loaded.Clear();assets.Dispose();}
}
