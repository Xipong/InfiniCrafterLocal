using MonoMod.RuntimeDetour;
using Terraria.ModLoader;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Text.Json;
using System.Text;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using InfiniCrafterLocal;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Projectiles;
internal sealed partial class WNativeArtwork:IDisposable {
 const BindingFlags All=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
 readonly RuntimeSpriteCache cache=new();readonly GeneratedAssetSyncService sync=new();readonly Player owner;
 readonly object? oldCache,oldSync;readonly GeneratedHeldItemDrawLayer layer=new();readonly Func<Projectile,int> projectileId;
 readonly HashSet<Texture2D> heldTextures=new();
 WNativeEquipmentLayers? equipmentLayers;
 bool nativePlayer;Hook? heldObserver,playerObserver,proxyObserver,projectileObserver;
 public bool NativePlayerEnabled=>nativePlayer;
 public bool NativeVanillaEnabled=>reviewData is null;
 bool drawVanillaProjectiles;
 public bool NativeVanillaProjectilesEnabled=>drawVanillaProjectiles;
 public void EnableNativeVanillaProjectiles(){
  if(!NativeVanillaEnabled||!nativePlayer)throw new NotSupportedException("Native projectile sprites require a vanilla item and full native player artwork");
  drawVanillaProjectiles=true;
  Report["vanillaProjectileRendering"]="Original Main.DrawProj with pinned native projectile textures; other types refuse";
  Report["entrypoints"]=Entrypoints();
 }
 delegate bool ProxyOriginal(InfiniCrafterLocal.Content.Items.GeneratedItem self,ref PlayerDrawSet draw,ref DrawData item,ref DrawData? colored,ref DrawData? glow);
 delegate bool ProxyObserver(ProxyOriginal orig,InfiniCrafterLocal.Content.Items.GeneratedItem self,ref PlayerDrawSet draw,ref DrawData item,ref DrawData? colored,ref DrawData? glow);
 delegate bool ProjectileDrawOriginal(GeneratedProjectile self,ref Color color);
 delegate bool ProjectileDrawObserver(ProjectileDrawOriginal orig,GeneratedProjectile self,ref Color color);
 delegate void HeldOriginal(GeneratedHeldItemDrawLayer self,ref PlayerDrawSet draw);
 delegate void HeldObserver(HeldOriginal orig,GeneratedHeldItemDrawLayer self,ref PlayerDrawSet draw);
 delegate void PlayerOriginal(ref PlayerDrawSet draw);
 delegate void PlayerObserver(PlayerOriginal orig,ref PlayerDrawSet draw);
 public void EnableNativePlayer(){
  projectileObserver=new Hook(typeof(GeneratedProjectile).GetMethod(nameof(GeneratedProjectile.PreDraw))!,
   (ProjectileDrawObserver)((ProjectileDrawOriginal orig,GeneratedProjectile self,ref Color color)=>{
    bool result=orig(self,ref color);RecordProjectile(self.Projectile,self.Projectile.whoAmI==owner.heldProj?"Native PlayerDrawLayers -> Main.DrawProj -> GeneratedProjectile.PreDraw":"ProjectileLoader.PreDraw -> GeneratedProjectile.PreDraw");return result;
   }));
  if(owner.skinVariant!=0||owner.hair!=0)throw new NotSupportedException("Native player artwork currently requires actual default skinVariant0/hair0");
  typeof(PlayerDrawLayerLoader).GetMethod("Add",All)!.Invoke(null,new object[]{layer});
  equipmentLayers=new WNativeEquipmentLayers(()=>Frame);
  typeof(PlayerDrawLayerLoader).GetMethod("ResizeArrays",All)!.Invoke(null,null);
  heldObserver=new Hook(typeof(GeneratedHeldItemDrawLayer).GetMethod("Draw",All)!, (HeldObserver)((HeldOriginal orig,GeneratedHeldItemDrawLayer self,ref PlayerDrawSet draw)=>{
   int count=draw.DrawDataCache.Count;orig(self,ref draw);for(int i=count;i<draw.DrawDataCache.Count;i++) RecordHeld(draw.DrawDataCache[i]);
  }));
  playerObserver=new Hook(typeof(PlayerDrawLayers).GetMethod("DrawPlayer_RenderAllLayers",All)!, (PlayerObserver)((PlayerOriginal orig,ref PlayerDrawSet draw)=>{
   Frame["playerRenderAllLayersCalls"]=(Frame["playerRenderAllLayersCalls"]?.GetValue<int>()??0)+1;
   Frame["nativePlayerDrawDataCount"]=draw.DrawDataCache.Count;Frame["nativeGeneratedHeldDrawDataCount"]=draw.DrawDataCache.Count(d=>d.texture is not null&&heldTextures.Contains(d.texture));
   var nativeData=new JsonArray();foreach(var entry in draw.DrawDataCache){
    if(entry.texture is not null&&heldTextures.Contains(entry.texture))RecordHeldGeometry(entry);
    if(NativeVanillaEnabled&&ReferenceEquals(entry.texture,Terraria.GameContent.TextureAssets.Item[owner.HeldItem.type].Value)){RecordHeldGeometry(entry);Increment("heldItemDrawCount");}
    string textureIdentity=entry.texture is not null&&heldTextures.Contains(entry.texture)?"generated_held_item":"other";for(int part=0;part<Terraria.ID.PlayerTextureID.Count;part++)if(ReferenceEquals(entry.texture,Terraria.GameContent.TextureAssets.Players[owner.skinVariant,part]?.Value))textureIdentity="Player_"+owner.skinVariant+"_"+part;
    if(ReferenceEquals(entry.texture,Terraria.GameContent.TextureAssets.PlayerHair[owner.hair].Value))textureIdentity="Player_Hair_"+(owner.hair+1);
    if(ReferenceEquals(entry.texture,Terraria.GameContent.TextureAssets.PlayerHairAlt[owner.hair].Value))textureIdentity="Player_HairAlt_"+(owner.hair+1);
    if(ReferenceEquals(entry.texture,Terraria.GameContent.TextureAssets.Item[owner.HeldItem.type].Value))textureIdentity=NativeVanillaEnabled?"native_vanilla_item":"native_item_proxy";
    if(equipmentLayers?.Owns(entry.texture)==true)textureIdentity="generated_equip_overlay";
    nativeData.Add(new JsonObject{["textureIdentity"]=textureIdentity,["textureWidth"]=entry.texture?.Width,["textureHeight"]=entry.texture?.Height,["positionX"]=entry.position.X,["positionY"]=entry.position.Y,["originX"]=entry.origin.X,["originY"]=entry.origin.Y,["scaleX"]=entry.scale.X,["scaleY"]=entry.scale.Y,["rotation"]=entry.rotation,["sourceX"]=entry.sourceRect?.X,["sourceY"]=entry.sourceRect?.Y,["sourceWidth"]=entry.sourceRect?.Width,["sourceHeight"]=entry.sourceRect?.Height,["effects"]=entry.effect.ToString(),["shader"]=entry.shader});
   }Frame["nativePlayerDrawData"]=nativeData;
   Frame["nativeProxyDrawDataCount"]=draw.DrawDataCache.Count(d=>ReferenceEquals(d.texture,Terraria.GameContent.TextureAssets.Item[owner.HeldItem.type].Value));
   Frame["nativePlayerDrawSet"]=new JsonObject{["itemX"]=draw.ItemLocation.X,["itemY"]=draw.ItemLocation.Y,["positionX"]=draw.Position.X,["positionY"]=draw.Position.Y,["bodyFrameX"]=draw.drawPlayer.bodyFrame.X,["bodyFrameY"]=draw.drawPlayer.bodyFrame.Y,["legFrameX"]=draw.drawPlayer.legFrame.X,["legFrameY"]=draw.drawPlayer.legFrame.Y};
   orig(ref draw);
  }));
  proxyObserver=new Hook(typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetMethod("ModifyItemDraw",All)!, (ProxyObserver)((ProxyOriginal orig,InfiniCrafterLocal.Content.Items.GeneratedItem self,ref PlayerDrawSet draw,ref DrawData item,ref DrawData? colored,ref DrawData? glow)=>{
   Frame["nativeProxyBeforeVeto"]=new JsonObject{["positionX"]=item.position.X,["positionY"]=item.position.Y,["originX"]=item.origin.X,["originY"]=item.origin.Y,["rotation"]=item.rotation};bool result=orig(self,ref draw,ref item,ref colored,ref glow);
   if(!result)Frame["nativeProxyVetoCount"]=(Frame["nativeProxyVetoCount"]?.GetValue<int>()??0)+1;
   return result;
  }));
  nativePlayer=true;Report["scope"]="Original native PlayerRenderer body/layer ordering, generated held layer once and full generated projectile PreDraw/PostDraw; separate inventory preview; no Terraria tile/NPC/world renderer";Report["entrypoints"]=Entrypoints();Report["nativePlayerRenderer"]="Main.PlayerRenderer.DrawPlayers / LegacyPlayerRenderer";Report["equipmentOverlayScope"]="Original five GeneratedEquipOverlay draw layers; actual equip/vanity selection and exact authored overlay PNG; no full armor atlas substitution";Report["fullProjectilePreDrawEnabled"]=true;Report["fullProjectilePreDrawExecuted"]=false;Report["missingFullPreDrawAsset"]=null;if(NativeVanillaEnabled){Report["scope"]="Original native PlayerRenderer and vanilla held-item layer using pinned actual item texture; no generated draw substitution";Report["fullProjectilePreDrawEnabled"]=false;}
 }
 public JsonObject Report {get;}=new();
 public JsonObject Frame {get;private set;}=new();
 public WNativeArtwork(GeneratedItemData? data,Player owner,string[] files,Func<Projectile,int>? projectileId=null) {
  this.owner=owner;reviewData=data;this.projectileId=projectileId??(p=>p.identity);
  oldCache=typeof(InfiniCrafterLocalMod).GetProperty("Sprites")!.GetValue(null);oldSync=typeof(InfiniCrafterLocalMod).GetProperty("AssetSync")!.GetValue(null);
  if(data is null){
   if(files.Length!=0)throw new ArgumentException("Vanilla artwork requires no generated artworkFiles; its pinned item PNG comes from vanillaAssetRoot");
   Report=new JsonObject{["scope"]="Original native vanilla PlayerRenderer and item layer; no generated item substituted",["nativeVanillaItemType"]=owner.HeldItem.type,["fullProjectilePreDrawExecuted"]=false,["vanillaProjectileRendering"]="notRun: projectile simulation/hits execute, but this pose review does not substitute missing native projectile textures",["inventoryPreviewRendering"]="notRun: no diagnostic vanilla inventory surrogate"};
   geometryObserver=new WNativeVisualGeometry();BeginFrame();return;
  }
  var rootIdentity=new[]{data.Id,"item","",data.Id};
  var selected=new List<(string Role,SpritePresentationSelection Selection,string[] Identity)>{("item",SpritePresentation.Root(data),rootIdentity)};
  foreach(var entity in data.RuntimeProgram.Entities) {
   if(entity.Visual.AssetMode is "runtime_geometry" or "no_asset")continue; // Native geometry/VFX owns this body; no PNG is selected or substituted.
   if(entity.Visual.AssetMode is not ("baked_sprite" or "reuse_item_icon"))throw new NotSupportedException("Authored PNG artwork requires baked_sprite/reuse_item_icon, not "+entity.Visual.AssetMode+" for "+entity.Id);
   selected.Add((entity.Id,SpritePresentation.Entity(data,entity),entity.Kind==RuntimeEntityKind.ItemBody||entity.Visual.AssetMode=="reuse_item_icon"?rootIdentity:new[]{data.Id,"runtime:"+RuntimeEntityKind.VisualRoleFor(entity.Kind),entity.Id,data.Id+"_"+entity.Id}));
  }
  // Only explicitly authored texture references are admitted; never invent a missing visual.
  foreach(var entity in data.RuntimeProgram.Entities)
   if(data.VfxManifest.Slots.Any(slot=>slot.EntityId==entity.Id && (slot.RendererKind=="impactSprite" || slot.Element?.Texture.Source=="impact" || slot.Path?.Texture.Source=="impact")))
    selected.Add(("impact:"+entity.Id,new SpritePresentationSelection(entity.Visual.ImpactSpritePath,null,null,ImpactTexture:true),new[]{data.Id,"impact",entity.Id,data.Id+"_"+entity.Id+"_impact"}));
  var assetIds=data.VfxManifest.Slots.Select(slot=>slot.Element?.Texture??slot.Path?.Texture).Where(texture=>texture?.Source=="asset").Select(texture=>texture!.AssetId).ToHashSet(StringComparer.Ordinal);
  foreach(string assetId in assetIds) {
   var asset=data.VfxManifest.Assets?.SingleOrDefault(a=>a.Id==assetId)??throw new InvalidDataException("Missing authored VFX asset: "+assetId);
   selected.Add(("vfx:"+assetId,new SpritePresentationSelection(asset.SpritePath,null,null,ImpactTexture:true),new[]{data.VfxManifest.RecipeId,assetId}));
  }
  if(data.Accessory.Enabled || data.Armor.Enabled)
   selected.Add(("equip_overlay",new SpritePresentationSelection(data.Visual.EquipOverlayPath,null,null,ImpactTexture:true),new[]{data.Id,"equip_overlay","",data.Id+"_equip_overlay"}));
  var supplied=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
  foreach(string file in files) {
   string full=Path.GetFullPath(file);RejectSymlink(full);
   string name=GeneratedAssetSyncService.FileNameFromPath(full);
   if(name.Length==0||name!=Path.GetFileName(full)||!supplied.TryAdd(name,full))throw new InvalidDataException("Artwork files require unique exact PNG publication basenames");
  }
  var required=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
  foreach(var (_,selection,identity) in selected) {
   if(identity.Any(part=>part.Any(c=>!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c is '_' or '-' or '.' or ':'))))throw new NotSupportedException("Publication proof currently admits only ASCII letters/digits/underscore/hyphen/period/colon identities; other identity serialization is not certified");
   if(!selection.ImpactTexture){SpritePresentation.RequireRenderSize(selection.RenderSizePx);SpritePresentation.RequireForwardAngle(selection.ForwardAngleDegrees);}
   string alias=selection.Path.Trim();if(string.IsNullOrEmpty(alias)||alias!=Environment.ExpandEnvironmentVariables(alias)||alias.Replace('\\','/').Split('/').Any(p=>p is "." or ".."))throw new InvalidDataException("Unsafe/empty authored asset alias");
   string name=GeneratedAssetSyncService.FileNameFromPath(alias);if(name.Length==0||!supplied.ContainsKey(name))throw new FileNotFoundException("Missing explicit artwork file for selected publication: "+name);
   if(!string.Equals(Path.GetFileName(supplied[name]),name,StringComparison.Ordinal))throw new InvalidDataException("Selected/supplied publication basename must match exact case");
   required.Add(name);
   // RuntimeSpriteCache gives an existing raw local alias precedence; admit it only if explicitly supplied.
   if(File.Exists(alias)) {string full=Path.GetFullPath(alias);RejectSymlink(full);if(!string.Equals(full,supplied[name],StringComparison.Ordinal))throw new InvalidDataException("Existing raw artwork alias is outside explicitly supplied files: "+alias);}
  }
  if(required.Count!=supplied.Count)throw new InvalidDataException("Unused artwork files are not admitted; provide exactly the selected PNG publications");
  var receipts=new JsonArray();var hashes=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
  foreach(var pair in supplied) {
   var info=new FileInfo(pair.Value);if(!info.Exists||info.Length<33||info.Length>8*1024*1024)throw new InvalidDataException("Artwork PNG missing or exceeds8MiB: "+pair.Key);
   byte[] bytes=File.ReadAllBytes(pair.Value);if(!bytes.AsSpan(0,8).SequenceEqual(new byte[]{137,80,78,71,13,10,26,10}))throw new InvalidDataException("Artwork must be actual PNG bytes: "+pair.Key);
   foreach(var publication in selected.Where(x=>GeneratedAssetSyncService.FileNameFromPath(x.Selection.Path)==pair.Key)) {
    byte[] identity=Encoding.ASCII.GetBytes(JsonSerializer.Serialize(publication.Identity));
    using var digest=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);digest.AppendData(identity);digest.AppendData(new byte[]{0});digest.AppendData(bytes);
    string expected=(publication.Role.StartsWith("vfx:",StringComparison.Ordinal)?"infini_vfx_png_":"infini_asset_png_")+Convert.ToHexString(digest.GetHashAndReset()).ToLowerInvariant()+".png";
    if(!string.Equals(pair.Key,expected,StringComparison.Ordinal))throw new InvalidDataException("Artwork publication identity/content mismatch; custom logical asset IDs and non-publication filenames are not certified by this bounded mode: "+pair.Key);
   }
   if(System.Buffers.Binary.BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(8,4))!=13 || !bytes.AsSpan(12,4).SequenceEqual(new byte[]{73,72,68,82})) throw new InvalidDataException("Artwork PNG must start with canonical IHDR");
   uint width=System.Buffers.Binary.BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(16,4)),height=System.Buffers.Binary.BinaryPrimitives.ReadUInt32BigEndian(bytes.AsSpan(20,4));
   if(width==0||height==0||width>4096||height>4096||(ulong)width*height>16UL*1024*1024) throw new InvalidDataException("Artwork PNG dimensions exceed admission limit: positive dimensions <=4096 and <=16M pixels");
   string destination=Path.Combine(sync.CacheRoot,pair.Key);RejectSymlink(destination);File.WriteAllBytes(destination,bytes);string sha=Hash(File.ReadAllBytes(destination));hashes[pair.Key]=sha;
   receipts.Add(new JsonObject{["publicationFileName"]=pair.Key,["suppliedPath"]=pair.Value,["stagedPath"]=destination,["bytes"]=bytes.Length,["copiedBytesSha256"]=sha,["publicationVerified"]=true,["publicationAlgorithm"]="LocalGenerator visual_sprite_generation._runtime_publication_identity or _publish_vfx_png: compact ASCII identity JSON + NUL + exact PNG bytes",["publicationScope"]="Root/runtime/impact default logical asset IDs; VFX exact recipeId/assetId identity; safe ASCII identities only"});
  }
  typeof(InfiniCrafterLocalMod).GetProperty("Sprites")!.SetValue(null,cache);typeof(InfiniCrafterLocalMod).GetProperty("AssetSync")!.SetValue(null,sync);
  bool old=Main.dedServ;Main.dedServ=false;
  try {
   foreach(var group in selected.GroupBy(p=>p.Selection.Path,StringComparer.Ordinal)) {
    string alias=group.Key;string name=GeneratedAssetSyncService.FileNameFromPath(alias);Texture2D texture=cache.TryGet(alias)??throw new FileNotFoundException("Native RuntimeSpriteCache rejected selected PNG: "+alias);
    if(Hash(File.ReadAllBytes(supplied[name]))!=hashes[name])throw new IOException("Artwork source changed during native load: "+name);
    var pixels=new Color[checked(texture.Width*texture.Height)];texture.GetData(pixels);var rgba=new byte[pixels.Length*4];for(int i=0;i<pixels.Length;i++){rgba[i*4]=pixels[i].R;rgba[i*4+1]=pixels[i].G;rgba[i*4+2]=pixels[i].B;rgba[i*4+3]=pixels[i].A;}
    var receipt=receipts.First(x=>x!["publicationFileName"]!.GetValue<string>()==name)!;
    receipt["width"]=texture.Width;receipt["height"]=texture.Height;receipt["gpuPremultipliedRgbaSha256"]=Hash(rgba);
    var aliases=receipt["selectedAliases"] as JsonArray??new JsonArray();if(receipt["selectedAliases"] is null)receipt["selectedAliases"]=aliases;aliases.Add(JsonValue.Create(alias));
   }
  }catch {Dispose();throw;}finally{Main.dedServ=old;}
  Report=new JsonObject{["scope"]="Original authored PNG core, native held layer and separate inventory preview; not full PreDraw or Terraria world rendering",["descriptorMutated"]=false,["admissionLimits"]=new JsonObject{["maxFileBytes"]=8*1024*1024,["maxWidth"]=4096,["maxHeight"]=4096,["maxPixels"]=16*1024*1024},["assetReceipts"]=receipts,["entrypoints"]=Entrypoints(),["fullProjectilePreDrawExecuted"]=false,["missingFullPreDrawAsset"]="Terraria Content/Images/MagicPixel.xnb",["inventoryPreviewAnchor"]=PreviewAnchor()};geometryObserver=new WNativeVisualGeometry();EnableVisualObserver();BeginFrame();
 }
 static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
 static void RejectSymlink(string path) {for(FileSystemInfo? p=new FileInfo(path);p is not null;p=p is FileInfo file?file.Directory:((DirectoryInfo)p).Parent)if(p.LinkTarget is not null||(p.Exists&&(p.Attributes&FileAttributes.ReparsePoint)!=0))throw new InvalidDataException("Artwork symlink/reparse path is not admitted: "+p.FullName);}
 JsonArray Entrypoints()=>NativeVanillaEnabled?(drawVanillaProjectiles?new("Main.PlayerRenderer.DrawPlayers","PlayerDrawLayers.DrawPlayer_27_HeldItem","PlayerDrawLayers.DrawPlayer_RenderAllLayers","Main.DrawProj -> SpriteBatch.Draw"):new("Main.PlayerRenderer.DrawPlayers","PlayerDrawLayers.DrawPlayer_27_HeldItem","PlayerDrawLayers.DrawPlayer_RenderAllLayers")):nativePlayer?new("Main.PlayerRenderer.DrawPlayers","GeneratedItem.ModifyItemDraw","GeneratedHeldItemDrawLayer.Draw (native layer loader)","PlayerDrawLayers.DrawPlayer_RenderAllLayers","ProjectileLoader.PreDraw / GeneratedProjectile.PreDraw","ProjectileLoader.PostDraw","GeneratedItem.PreDrawInInventory"):new("GeneratedItem.PreDrawInInventory","GeneratedHeldItemDrawLayer.GetDefaultVisibility/Draw","DrawData.Draw","GeneratedProjectile.DrawAuthoredEntityVisual");
 static JsonObject PreviewAnchor()=>new(){["positionX"]=36,["positionY"]=36,["originX"]=24,["originY"]=24,["requestedFrameWidth"]=48,["requestedFrameHeight"]=48,["scope"]="Separate UI preview anchor; original hook determines actual authored PNG size"};
 public void BeginFrame(){heldTextures.Clear();equipmentLayers?.BeginFrame();Frame=new JsonObject{["visualReview"]=PlayerReview(),["projectileGeometry"]=new JsonArray(),["heldGeometry"]=new JsonArray(),["droppedItems"]=new JsonArray(),["unrenderedVanillaProjectiles"]=new JsonArray(),["vanillaProjectileDrawAttemptCount"]=0,["vanillaProjectileDrawAttempts"]=new JsonArray(),["equipmentOverlayDrawCount"]=0,["equipmentOverlayDrawData"]=new JsonArray(),["playerDrawCount"]=0,["playerRenderAllLayersCalls"]=0,["nativeProxyVetoCount"]=0,["nativeProxyDrawDataCount"]=0,["heldItemDrawCount"]=0,["projectileDrawCount"]=0,["inventoryPreviewDrawCount"]=0,["heldDrawData"]=new JsonArray(),["projectileIds"]=new JsonArray(),["projectileDraws"]=new JsonArray(),["entrypoints"]=Entrypoints(),["inventoryPreviewAnchor"]=PreviewAnchor()};}
 void Increment(string key,int amount=1)=>Frame[key]=Frame[key]!.GetValue<int>()+amount;
 public void DrawInventory() {
  if(NativeVanillaEnabled||owner.HeldItem.IsAir)return; // No selected item: no preview, never substitute artwork.
  Main.spriteBatch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,Main.Rasterizer);
  try{owner.HeldItem.ModItem!.PreDrawInInventory(Main.spriteBatch,new Vector2(36,36),new Rectangle(0,0,48,48),Color.White,Color.White,new Vector2(24),1);Increment("inventoryPreviewDrawCount");}finally{Main.spriteBatch.End();}
 }
 public void DrawHeld() {
  if(nativePlayer){
   if(owner.isLockedToATile)throw new NotSupportedException("Locked-to-tile player draw ordering is outside the ordinary player render pass");
   var active=Main.projectile.Where(p=>p.active).ToArray();Exception? drawError=null;
   EventHandler<System.Runtime.ExceptionServices.FirstChanceExceptionEventArgs> observe=(_,args)=>{drawError=args.Exception;};
   AppDomain.CurrentDomain.FirstChanceException+=observe;
   try{Main.PlayerRenderer.DrawPlayers(Main.Camera,new[]{owner});}
   finally{AppDomain.CurrentDomain.FirstChanceException-=observe;}
   if(active.Any(p=>!p.active))throw new InvalidOperationException("Native player rendering deactivated a projectile; swallowed draw errors cannot certify a successful gameplay run",drawError);
   Frame["playerDrawCount"]=1;return;
  }
  var draw=new PlayerDrawSet{drawPlayer=owner,ItemLocation=owner.itemLocation,DrawDataCache=new List<DrawData>()};if(!layer.GetDefaultVisibility(draw))return;
  object[] args={draw};typeof(GeneratedHeldItemDrawLayer).GetMethod("Draw",All)!.Invoke(layer,args);draw=(PlayerDrawSet)args[0];
  Main.spriteBatch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,Main.Rasterizer,null,Main.GameViewMatrix.TransformationMatrix);
  try{foreach(var entry in draw.DrawDataCache){entry.Draw(Main.spriteBatch);RecordHeld(entry);}}finally{Main.spriteBatch.End();}
 }
 void RecordHeld(DrawData entry){if(entry.texture is null)throw new InvalidOperationException("Native generated held draw has null texture");if(!nativePlayer)RecordHeldGeometry(entry);heldTextures.Add(entry.texture);Increment("heldItemDrawCount");Frame["heldDrawData"]!.AsArray().Add(new JsonObject{["positionX"]=entry.position.X,["positionY"]=entry.position.Y,["originX"]=entry.origin.X,["originY"]=entry.origin.Y,["scaleX"]=entry.scale.X,["scaleY"]=entry.scale.Y,["rotation"]=entry.rotation,["colorR"]=entry.color.R,["colorG"]=entry.color.G,["colorB"]=entry.color.B,["colorA"]=entry.color.A,["effects"]=entry.effect.ToString(),["textureWidth"]=entry.texture.Width,["textureHeight"]=entry.texture.Height});}
 public void DrawProjectiles() {
  Main.spriteBatch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,Main.Rasterizer,null,Main.GameViewMatrix.TransformationMatrix);
  try{foreach(var p in Main.projectile.Where(p=>p.active)) {
   if(nativePlayer && p.whoAmI==owner.heldProj)continue; // Native player layer owns this pass exactly once.
   if(p.hide)throw new NotSupportedException("Hidden or specially ordered projectile draw passes are not admitted");
   if(p.ModProjectile is not GeneratedProjectile){
    if(!NativeVanillaEnabled)throw new NotSupportedException("Only generated projectile authored core is supported");
    if(drawVanillaProjectiles){
     if(!WNativeVanillaProjectileAssets.Supports(p.type))throw new NotSupportedException("Native projectile draw type not admitted: "+p.type);
     var draws=WNativeVisualGeometry.Capture(()=>Main.instance.DrawProj(p.whoAmI));
     if(!p.active)throw new InvalidOperationException("Native projectile rendering deactivated a projectile; swallowed draw errors cannot certify a successful run");
     Increment("vanillaProjectileDrawAttemptCount");
     Frame["vanillaProjectileDrawAttempts"]!.AsArray().Add(new JsonObject{["nativeSlot"]=p.whoAmI,["nativeIdentity"]=p.identity,["nativeType"]=p.type,["spriteDrawCount"]=draws.Count,["entrypoint"]="Main.DrawProj (original)"});
     foreach(var node in draws){var row=node!.AsObject();row["kind"]="vanilla_projectile";row["nativeSlot"]=p.whoAmI;row["nativeIdentity"]=p.identity;row["nativeType"]=p.type;row["collider"]=WNativeVisualGeometry.Rect(p.Hitbox);Frame["projectileGeometry"]!.AsArray().Add(row.DeepClone());}
     if(draws.Count>0)RecordProjectile(p,"Main.DrawProj -> SpriteBatch.Draw (observed original native sprite submission)");
    }else Frame["unrenderedVanillaProjectiles"]!.AsArray().Add(new JsonObject{["slot"]=p.whoAmI,["nativeType"]=p.type,["reason"]="Native gameplay executes; projectile sprite pass not admitted in vanilla pose review"});
    continue;
   }
   Color color=Lighting.GetColor((int)p.Center.X/16,(int)p.Center.Y/16);if(nativePlayer){Report["fullProjectilePreDrawExecuted"]=true;if(ProjectileLoader.PreDraw(p,ref color))throw new InvalidOperationException("Generated full PreDraw unexpectedly requested vanilla fallback");ProjectileLoader.PostDraw(p,color);}else typeof(GeneratedProjectile).GetMethod("DrawAuthoredEntityVisual",All)!.Invoke(p.ModProjectile,new object[]{color});if(!nativePlayer)RecordProjectile(p,"GeneratedProjectile.DrawAuthoredEntityVisual");
  }}finally{Main.spriteBatch.End();}
 }
 void RecordProjectile(Projectile p,string entrypoint){
  Increment("projectileDrawCount");int id=projectileId(p);Frame["projectileIds"]!.AsArray().Add(JsonValue.Create(id));Frame["projectileDraws"]!.AsArray().Add(new JsonObject{["projectileId"]=id,["nativeSlot"]=p.whoAmI,["nativeIdentity"]=p.identity,["entrypoint"]=entrypoint});
 }
 public void Dispose(){visualObserver?.Dispose();geometryObserver?.Dispose();equipmentLayers?.Dispose();projectileObserver?.Dispose();heldObserver?.Dispose();playerObserver?.Dispose();proxyObserver?.Dispose();if(nativePlayer)typeof(PlayerDrawLayerLoader).GetMethod("Unload",All)!.Invoke(null,null);cache.Dispose();sync.Dispose();typeof(InfiniCrafterLocalMod).GetProperty("Sprites")!.SetValue(null,oldCache);typeof(InfiniCrafterLocalMod).GetProperty("AssetSync")!.SetValue(null,oldSync);}
}
