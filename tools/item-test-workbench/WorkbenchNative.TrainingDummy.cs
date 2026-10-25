using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using ReLogic.Content.Sources;
using Terraria;
using Terraria.DataStructures;
using Terraria.GameContent;
using Terraria.GameContent.Drawing;
using Terraria.GameContent.Tile_Entities;
using Terraria.Graphics;
using Terraria.ObjectData;

// Original object placement, tile entity, NPC AI/frame and tile drawing. No decorative NPC sprite.
internal sealed class WNativeTrainingDummy:IDisposable
{
 readonly int tileX,tileY;
 readonly TETrainingDummy entity;
 AssetRepository? assets;
 Asset<Texture2D>? npcAsset,tileAsset,oldNpcAsset,oldTileAsset;
 TileBatch? batch,oldBatch;
 TileDrawing? oldDrawing;
 TilePaintSystemV2? oldPaint;
 WorldSections? oldSections;
 int oldSectionsX,oldSectionsY;
 bool graphicsReady;
 public NPC Npc=>Main.npc[entity.npc];
 public JsonObject Report {get;}
 public int SuccessfulDrawCalls {get;private set;}
 WNativeTrainingDummy(int x,int y,TETrainingDummy tileEntity)
 {
  tileX=x;tileY=y;entity=tileEntity;
  Report=new JsonObject{["backend"]="native-training-dummy",["placement"]="TileObject.CanPlace / TileObject.Place / TETrainingDummy.Place / TETrainingDummy.Activate",["npcDrawing"]="NPC488 is deliberately not directly drawn; actual TileDrawing renders tile378 using linked NPC frame",["worldRendered"]=false,["scope"]="Native training dummy object and non-solid tile layer in controlled scene; no solid terrain artwork",["tileX"]=x,["tileY"]=y,["tileEntityId"]=entity.ID,["npcSlot"]=entity.npc,["initialState"]=Snapshot()};
 }
 public static WNativeTrainingDummy CreateNativeTarget(int x,int y)
 {
  if(x<2||y<2||x+3>=Main.maxTilesX||y+4>=Main.maxTilesY)throw new InvalidDataException("Native training dummy tile position outside controlled world");
  if(TileEntity.manager is null)TileEntity.InitializeAll();
  TileObjectData data=TileObjectData.GetTileData(378,0)??throw new InvalidOperationException("Native training dummy TileObjectData not initialized");
  if(data.Width!=2||data.Height!=3)throw new InvalidOperationException("Unexpected native training dummy geometry");
  for(int xx=x;xx<x+data.Width;xx++)for(int yy=y;yy<y+data.Height;yy++)if(Main.tile[xx,yy].HasTile)throw new InvalidDataException("Training dummy native placement requires an empty2x3 area");
  if(!TileObject.CanPlace(x+data.Origin.X,y+data.Origin.Y,378,0,1,out TileObject placement)||!TileObject.Place(placement))throw new InvalidOperationException("Actual TileObject placement refused training dummy; require native solid floor under both tiles");
  int id=TETrainingDummy.Find(x,y);
  if(id<0)id=TETrainingDummy.Place(x,y);
  var entity=(TETrainingDummy)TileEntity.ByID[id];
  if(!TETrainingDummy.ValidTile(x,y))throw new InvalidOperationException("Native placement did not produce valid training dummy tile entity anchor");
  entity.Activate();
  if(entity.npc<0||entity.npc>=Main.npc.Length||!Main.npc[entity.npc].active||Main.npc[entity.npc].type!=488)throw new InvalidOperationException("Native training dummy activation failed");
  var result=new WNativeTrainingDummy(x,y,entity);
  if(result.Npc.width!=18||result.Npc.height!=40||result.Npc.aiStyle!=92||!result.Npc.immortal)throw new InvalidOperationException("Native target defaults were unexpectedly changed");
  return result;
 }
 public void InitializeGraphics(WorkbenchGraphicsContext graphics,string assetRoot)
 {
  if(graphicsReady)throw new InvalidOperationException("Training dummy graphics already initialized");
  var readers=new AssetReaderCollection();readers.RegisterReader(new PngReader(graphics.Device),".png");
  assets=new AssetRepository(readers,Array.Empty<IContentSource>());
  var receipts=new JsonArray();
  Asset<Texture2D> Load(string name,string expected)
  {
   string path=Path.GetFullPath(Path.Combine(assetRoot,"Images",name+".png"));
   for(FileSystemInfo? part=new FileInfo(path);part is not null;part=part is FileInfo f?f.Directory:((DirectoryInfo)part).Parent)if(part.LinkTarget is not null)throw new InvalidDataException("Dummy asset symlink refused: "+path);
   if(!File.Exists(path)||new FileInfo(path).Length>4*1024*1024)throw new InvalidDataException("Missing/bounded dummy asset: "+path);
   byte[] bytes=File.ReadAllBytes(path);if(Hash(bytes)!=expected)throw new InvalidDataException("Dummy asset differs from pinned community source: "+name);
   using var stream=new MemoryStream(bytes,writable:false);var asset=assets.CreateUntracked<Texture2D>(stream,name+".png",AssetRequestMode.ImmediateLoad);
   var texture=asset.Value;var pixels=new Color[texture.Width*texture.Height];texture.GetData(pixels);var rgba=new byte[pixels.Length*4];
   for(int i=0;i<pixels.Length;i++){rgba[i*4]=pixels[i].R;rgba[i*4+1]=pixels[i].G;rgba[i*4+2]=pixels[i].B;rgba[i*4+3]=pixels[i].A;}
   receipts.Add(new JsonObject{["sourcePath"]=path,["sha256"]=Hash(bytes),["loadedBytesSha256"]=Hash(bytes),["width"]=texture.Width,["height"]=texture.Height,["gpuPremultipliedRgbaSha256"]=Hash(rgba),["loader"]="Original PngReader from verified immutable memory bytes",["partialAlphaPixels"]=pixels.Count(p=>p.A>0&&p.A<255)});
   return asset;
  }
  npcAsset=Load("NPC_488","d20c5c9375ef6015c2dbccd140e13198b951489648e755b469bd94988f98c797");
  tileAsset=Load("Tiles_378","525fe8e863cbca7e587d42c03a52c8280cbbf1aacc817779bb480492c0ca4583");
  oldNpcAsset=TextureAssets.Npc[488];oldTileAsset=TextureAssets.Tile[378];oldBatch=Main.tileBatch;oldDrawing=Main.instance.TilesRenderer;oldPaint=Main.instance.TilePaintSystem;
  TextureAssets.Npc[488]=npcAsset;TextureAssets.Tile[378]=tileAsset;
  batch=new TileBatch(graphics.Device);Main.tileBatch=batch;
  Main.instance.TilePaintSystem??=new TilePaintSystemV2();
  Main.instance.TilesRenderer??=new TileDrawing(Main.instance.TilePaintSystem);
  oldSections=Main.sectionManager;oldSectionsX=Main.maxSectionsX;oldSectionsY=Main.maxSectionsY;
  Main.maxSectionsX=(Main.maxTilesX-1)/200+1;Main.maxSectionsY=(Main.maxTilesY-1)/150+1;
  Main.sectionManager??=new WorldSections(Main.maxSectionsX,Main.maxSectionsY);
  graphicsReady=true;
  Report["npcFrameCount"]=Main.npcFrameCount[488];Report["loadedNpcTextureHeight"]=npcAsset.Value.Height;Report["nativeCalculatedFrameStride"]=npcAsset.Value.Height/Main.npcFrameCount[488];Report["nativeTileMapperDivisor"]=55;Report["animationCompatibilityVerified"]=false;Report["animationCompatibilityWarning"]="Pinned community NPC texture has height550 and installed native frameCount11, yielding FindFrame stride50; original TileDrawing maps linked NPC.frame.Y using divisor55. Native methods and source bytes are unchanged. Wobble visual parity with an official game installation is not independently verified.";
  Report["assets"]=receipts;Report["assetCommit"]="c835594415e31ed88734dc778661014b48ffb648";Report["assetProvenance"]="Community source-pngs labelled Terraria1.4.4.9, not HD outputs";Report["officialByteIdentityVerified"]=false;
 }
 public JsonObject Snapshot()=>new JsonObject{["npcSlot"]=entity.npc,["tileEntityId"]=entity.ID,["successfulNativeTileDrawingInvocations"]=SuccessfulDrawCalls,["linkedSameNpc"]=entity.npc>=0&&Npc.ai[0]==tileX&&Npc.ai[1]==tileY,["active"]=Npc.active,["x"]=Npc.position.X,["y"]=Npc.position.Y,["width"]=Npc.width,["height"]=Npc.height,["aiStyle"]=Npc.aiStyle,["immortal"]=Npc.immortal,["life"]=Npc.life,["frameX"]=Npc.frame.X,["frameY"]=Npc.frame.Y,["frameWidth"]=Npc.frame.Width,["frameHeight"]=Npc.frame.Height,["hitReactionTicks"]=Npc.localAI[0],["nativeFrameCount"]=Main.npcFrameCount[488],["tileFrameIndexDerivedFromNativeNpcFrameY"]=Npc.frame.Y/55,["tileFrameIndexEvidence"]="Derived from original TileDrawing divisor55; not a direct draw-call observer"};
 public void UpdateNativeTileEntity(){TileEntity.UpdateStart();entity.Update();TileEntity.UpdateEnd();}
 public void Draw()
 {
  if(!graphicsReady)throw new InvalidOperationException("Training dummy genuine textures are not loaded");
  bool oldDrawToScreen=Main.drawToScreen;
  bool tileBegun=false,spriteBegun=false;
  try{
   Main.drawToScreen=true;
   Main.instance.TilesRenderer.PreDrawTiles(false,false,false);
   Main.tileBatch.Begin(Main.Transform);tileBegun=true;
   Main.spriteBatch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,RasterizerState.CullNone,null,Main.Transform);spriteBegun=true;
   Main.instance.TilesRenderer.Draw(false,false,false);
   SuccessfulDrawCalls++;
  }finally{
   if(tileBegun)Main.tileBatch.End();if(spriteBegun)Main.spriteBatch.End();Main.drawToScreen=oldDrawToScreen;
  }
 }
 static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
 public void Dispose()
 {
  if(graphicsReady){TextureAssets.Npc[488]=oldNpcAsset!;TextureAssets.Tile[378]=oldTileAsset!;Main.tileBatch=oldBatch!;Main.instance.TilesRenderer=oldDrawing!;Main.instance.TilePaintSystem=oldPaint!;Main.sectionManager=oldSections!;Main.maxSectionsX=oldSectionsX;Main.maxSectionsY=oldSectionsY;}
  batch?.Dispose();npcAsset?.Dispose();tileAsset?.Dispose();assets?.Dispose();
  if(entity.npc>=0&&entity.npc<Main.npc.Length)Main.npc[entity.npc].active=false;
  TETrainingDummy.Kill(tileX,tileY);
 }
}
