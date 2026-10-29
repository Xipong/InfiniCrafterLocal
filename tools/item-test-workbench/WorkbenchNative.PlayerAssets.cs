using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using ReLogic.Content.Sources;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;

// Native PNG decoding of explicitly supplied community-extracted source sprites; not official byte certification.
internal sealed class WNativePlayerAssets:IDisposable
{
 static readonly Dictionary<string,string> ExpectedHashes=new(StringComparer.Ordinal){
  ["Player_0_0.png"]="95e272aefac3ab5eda8f2bad352f404442820b952872365d444d8c2973c8a5df",
  ["Player_0_1.png"]="ac7f437365b5fdd5bc3025cda82904364ebe68f8d766baba95e12bc5e8999a84",
  ["Player_0_2.png"]="e9ed6edbd5efdb701ea09c1d90e533eb6bddea2f0a9b94c44557f57f1bb6990e",
  ["Player_0_3.png"]="fb597b26dd4f1fe446a59065a9b05db97cc3c1189ad148cff9b1897144f13ffe",
  ["Player_0_4.png"]="2286d978fbeab0f3c95a2e307951f4a29827301beabc089fad40ea3a61e1a4ac",
  ["Player_0_5.png"]="44906bcf01cd976f0d3edd97e58c425b96533f06f375c644ceaae409697bd6b5",
  ["Player_0_6.png"]="040261d619c52e590c0624d4edaf52356b4b0d5dbc6d45922cc9444872b5b873",
  ["Player_0_7.png"]="111430f1920424de74e04241a6ec1db7d0acb3bd9e7d69b24a471c9bbcdbbed3",
  ["Player_0_8.png"]="9a0f52867d6fdd7b6ae3e40bc32d71eb2db995366f02f3425b69b42c3ca0daa8",
  ["Player_0_9.png"]="4f64746d5f795b6af0ce17d3ae485ec3eb02224821cd07d53f1c39d99125de0f",
  ["Player_0_10.png"]="d03a75a6517fc0c6b44fbf8d6ae87aa1d7aa4904e5618e2558b1f961177ca8b0",
  ["Player_0_11.png"]="a5761d1b0d2c4bafef7b1f022e77069b301ae541b1a45af4fbb24fff8061ce51",
  ["Player_0_12.png"]="cbdf494b40ccdb212d6c0ae5e0045db9fe25d75818dec5d48e93b2a42eecf0dc",
  ["Player_0_13.png"]="f9857f1590703def9cede2cf7092ff7d430a098f1ab9f184f2434bf9b237ff93",
  ["Player_0_15.png"]="6fa7df52dbaeca38b2dd43d6d99bee667c12ffd1cad041c3929d90427e24f917",
  ["Player_Hair_1.png"]="8e134925cc78408705b50d99e0d0d752c5454a6acedf08ad9174a3bd270b7104",
  ["Player_HairAlt_1.png"]="4306b8eeb6bfd2b1be7db83d087bbfcb1f96f5add9e4e2979de160880d172d01",
  ["MagicPixel.png"]="43e32609f2d123fc51cafbafab11955153ea545760952a578c3f909bbe88651c",
  ["Dust.png"]="ffb3b9d3a11421600429adf5de97a6369f1c9e5b3533d6b99820aba143147dde",
 };
 const BindingFlags All=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance;
 readonly string stagedRoot;
 readonly AssetRepository assets;
 readonly IAssetRepository oldAssets;
 readonly Asset<Texture2D>[,] oldPlayers;
 readonly Asset<Texture2D>[] oldHair,oldHairAlt;
 readonly Asset<Texture2D> oldPixel,oldDust;
 readonly Effect oldShader;
 readonly Asset<Effect> shader;
 public JsonObject Report {get;}
 public WNativePlayerAssets(WorkbenchGraphicsContext graphics,string assetRoot)
 {
  assetRoot=Path.GetFullPath(assetRoot);
  string content=Environment.GetEnvironmentVariable("INFINI_TML_CONTENT_DIR")??throw new InvalidOperationException("Set INFINI_TML_CONTENT_DIR to the matching installed tModLoader Content directory");
  string shaderPath=Path.Combine(content,"PixelShader.xnb");
  if(!File.Exists(shaderPath))throw new FileNotFoundException("Actual tModLoader PixelShader.xnb required; set INFINI_TML_CONTENT_DIR",shaderPath);
  string[] names=Enumerable.Range(0,14).Append(15).Select(i=>"Player_0_"+i).Concat(new[]{"Player_Hair_1","Player_HairAlt_1","MagicPixel","Dust"}).ToArray();
  var verifiedBytes=new Dictionary<string,byte[]>(StringComparer.Ordinal);
  foreach(string name in names){
   string path=Path.Combine(assetRoot,"Images",name+".png");
   for(FileSystemInfo? component=new FileInfo(path);component is not null;component=component is FileInfo file?file.Directory:((DirectoryInfo)component).Parent)if(component.LinkTarget is not null)throw new InvalidDataException("Player asset symlink path is not admitted: "+path);
   if(!File.Exists(path))throw new FileNotFoundException("Missing exact starter-player source PNG: "+name);
   if(new FileInfo(path).Length>4*1024*1024)throw new InvalidDataException("Player PNG exceeds bounded asset size: "+name);
   byte[] sourceBytes=File.ReadAllBytes(path);
   if(Hash(sourceBytes)!=ExpectedHashes[name+".png"])throw new InvalidDataException("Player PNG does not match pinned community source bytes: "+name);
   verifiedBytes.Add(name,sourceBytes);
  }
  byte[] shaderBytes=File.ReadAllBytes(shaderPath);
  stagedRoot=Path.Combine(Path.GetTempPath(),"ifc-player-assets-"+Guid.NewGuid().ToString("N"));
  Directory.CreateDirectory(Path.Combine(stagedRoot,"Images"));
  bool globalsCaptured=false;
  try {
  foreach(var pair in verifiedBytes)File.WriteAllBytes(Path.Combine(stagedRoot,"Images",pair.Key+".png"),pair.Value);
  var game=(Game)typeof(WorkbenchGraphicsContext).GetField("game",All)!.GetValue(graphics)!;
  var readers=new AssetReaderCollection();readers.RegisterReader(new PngReader(graphics.Device),".png");readers.RegisterReader(new XnbReader(game.Services),".xnb");
  assets=new AssetRepository(readers,new[]{new FileSystemContentSource(stagedRoot)});
  var receipts=new JsonArray();
  foreach(string name in names){
   string path=Path.Combine(assetRoot,"Images",name+".png");var asset=assets.Request<Texture2D>("Images/"+name,AssetRequestMode.ImmediateLoad);
   string stagedPath=Path.Combine(stagedRoot,"Images",name+".png");
   string stagedHash=Hash(File.ReadAllBytes(stagedPath));
   if(stagedHash!=ExpectedHashes[name+".png"])throw new InvalidDataException("Staged player asset integrity changed during native load: "+name);
   Texture2D texture=asset.Value;var pixels=new Color[texture.Width*texture.Height];texture.GetData(pixels);var rgba=new byte[pixels.Length*4];
   for(int i=0;i<pixels.Length;i++){rgba[4*i]=pixels[i].R;rgba[4*i+1]=pixels[i].G;rgba[4*i+2]=pixels[i].B;rgba[4*i+3]=pixels[i].A;}
   receipts.Add(new JsonObject{["asset"]=name,["file"]=path,["sha256"]=Hash(verifiedBytes[name]),["stagedSha256"]=stagedHash,["nativeContentSource"]="Private staging of exactly verified source bytes",["state"]=asset.State.ToString(),["width"]=texture.Width,["height"]=texture.Height,["gpuPremultipliedRgbaSha256"]=Hash(rgba),["partialAlphaPixels"]=pixels.Count(p=>p.A>0&&p.A<255),["loader"]="Original ReLogic PngReader with native alpha premultiplication"});
  }
  using(var stream=new MemoryStream(shaderBytes,writable:false))shader=assets.CreateUntracked<Effect>(stream,"PixelShader.xnb",AssetRequestMode.ImmediateLoad);
  oldAssets=Main.Assets;oldPlayers=TextureAssets.Players;oldHair=TextureAssets.PlayerHair;oldHairAlt=TextureAssets.PlayerHairAlt;oldPixel=TextureAssets.MagicPixel;oldDust=TextureAssets.Dust;oldShader=Main.pixelShader;globalsCaptured=true;
  Main.Assets=assets;
  TextureAssets.Players=new Asset<Texture2D>[PlayerVariantID.Count,PlayerTextureID.Count];
  // Real restricted initializer sets exact15parts plus native Empty slot14; no copied pose/frame logic.
  typeof(Terraria.Initializers.PlayerDataInitializer).GetMethod("LoadStarterMale",All)!.Invoke(null,null);
  TextureAssets.PlayerHair=(Asset<Texture2D>[])oldHair.Clone();TextureAssets.PlayerHairAlt=(Asset<Texture2D>[])oldHairAlt.Clone();
  TextureAssets.PlayerHair[0]=assets.Request<Texture2D>("Images/Player_Hair_1",AssetRequestMode.ImmediateLoad);TextureAssets.PlayerHairAlt[0]=assets.Request<Texture2D>("Images/Player_HairAlt_1",AssetRequestMode.ImmediateLoad);
  TextureAssets.MagicPixel=assets.Request<Texture2D>("Images/MagicPixel",AssetRequestMode.ImmediateLoad);TextureAssets.Dust=assets.Request<Texture2D>("Images/Dust",AssetRequestMode.ImmediateLoad);Main.PixelShaderRef.Value=shader.Value;
  Report=new JsonObject{["scope"]="Native starter male skinVariant0/hair0 assets; no armor, accessories, alternate skins or hairstyle selection",["source"]="Community-extracted Terraria source PNGs, not official byte-certified game assets",["upstreamRepository"]="https://github.com/sullerandras/terraria-hd-textures",["referenceCommit"]="c835594415e31ed88734dc778661014b48ffb648",["referenceVersionClaim"]="Textures from Terraria 1.4.4.9",["officialByteIdentityVerified"]=false,["pinnedCommunityPngHashesVerified"]=true,["pixelMutation"]="No source pixels edited; original native PngReader performs normal premultiplication",["alphaScope"]="Starter player/hair and MagicPixel have binary alpha in verified reference; Dust has partial alpha, upstream straight/premultiplied extraction semantics not independently certified",["pixelShaderPath"]=shaderPath,["pixelShaderSha256"]=Hash(shaderBytes),["textures"]=receipts};
  } catch {
   if(globalsCaptured){Main.Assets=oldAssets;TextureAssets.Players=oldPlayers;TextureAssets.PlayerHair=oldHair;TextureAssets.PlayerHairAlt=oldHairAlt;TextureAssets.MagicPixel=oldPixel;TextureAssets.Dust=oldDust;Main.PixelShaderRef.Value=oldShader;}
   try { shader?.Dispose();assets?.Dispose(); } catch { }
   try {Directory.Delete(stagedRoot,true);} catch { }
   throw;
  }
 }
 static string Hash(byte[] data)=>Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
 public void Dispose(){Main.Assets=oldAssets;TextureAssets.Players=oldPlayers;TextureAssets.PlayerHair=oldHair;TextureAssets.PlayerHairAlt=oldHairAlt;TextureAssets.MagicPixel=oldPixel;TextureAssets.Dust=oldDust;Main.PixelShaderRef.Value=oldShader;shader.Dispose();assets.Dispose();if(Directory.Exists(stagedRoot))Directory.Delete(stagedRoot,true);}
}
