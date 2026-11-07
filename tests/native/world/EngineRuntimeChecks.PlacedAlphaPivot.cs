#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static RuntimePlacedBodySpec AlphaBody(string? space, double px = .5, double py = 1,
        bool flipX = false, bool flipY = false, double rotation = 0)
    {
        var body = new RuntimePlacedBodySpec { RenderSizePx = 64, FootprintAnchorX = .5,
            FootprintAnchorY = 1, ImagePivotX = px, ImagePivotY = py, OffsetXPx = 3, OffsetYPx = -5,
            RotationDegrees = rotation, FlipX = flipX, FlipY = flipY };
        if (space is null) return body;
        var fields = JsonSerializer.SerializeToNode(body)!.AsObject();
        fields[nameof(RuntimePlacedBodySpec.PivotSpace)] = space;
        return fields.Deserialize<RuntimePlacedBodySpec>()!;
    }

    private static bool AlphaDraw(SpriteBatch batch, Texture2D texture, RuntimePlacedBodySpec body,
        Rectangle footprint, Vector2 camera, Rectangle? bounds)
    {
        var method = typeof(GeneratedPlacedBodyDrawSystem).GetMethod("DrawBody", PersistenceStatic)!;
        return (bool)method.Invoke(null, new object?[] { batch, texture, body, footprint, camera, Color.White, bounds })!;
    }

    private static Vector2 AlphaUvPoint(SpriteBatch batch, int index, Vector2 point)
    {
        object quad = ((Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!).GetValue(index)!;
        Vector3[] positions = CpuVertexValues<Vector3>(quad);
        Vector2[] uv = CpuVertexValues<Vector2>(quad);
        Equal(4, positions.Length, "actual FNA four positions"); Equal(4, uv.Length, "actual FNA paired UVs");
        Vector2 At(float u, float v)
        {
            int i = Array.FindIndex(uv, p => Math.Abs(p.X-u)<.001f && Math.Abs(p.Y-v)<.001f);
            Equal(true, i>=0, "whole uncropped PNG UV corner retained");
            return new Vector2(positions[i].X,positions[i].Y);
        }
        Vector2 origin = At(0,0);
        return origin + (At(1,0)-origin)*point.X + (At(0,1)-origin)*point.Y;
    }

    private static void PlacedAlphaPivotUsesFinalBoundsWithoutCropping()
    {
        WithVfxGeometryQueue((batch, _, count, positions, _) => {
            Texture2D texture = CpuTexture(64,64);
            Rectangle footprint = new(200,300,32,48), bounds = new(7,9,42,39);
            Vector2 camera = new(40,60), anchor = new(219,343); // anchor + offset - camera = (179,283)
            anchor -= camera;
            var body = AlphaBody("alpha_bounds"); string before = JsonSerializer.Serialize(body);
            int index = count();
            Equal(true, AlphaDraw(batch,texture,body,footprint,camera,bounds), "explicit known alpha body submits");
            Equal(index+1,count(),"one whole PNG quad");
            AssertVfxNear(anchor,AlphaUvPoint(batch,index,new Vector2(28f/64,48f/64)),"visible bottom edge contacts authored anchor");
            Equal(before,JsonSerializer.Serialize(body),"draw does not mutate DTO");
            Equal(true, Math.Abs(Vector3.Distance(positions(index)[0],positions(index)[3]))>0, "real FNA positions queued");

            foreach (bool fx in new[] {false,true}) foreach (bool fy in new[] {false,true})
            foreach (double angle in new[] {-73d,0d,118d})
            {
                body = AlphaBody("alpha_bounds",.23,.61,fx,fy,angle);
                before = JsonSerializer.Serialize(body); index = count();
                Equal(true,AlphaDraw(batch,texture,body,footprint,camera,bounds),"arbitrary bbox pivot draws");
                Vector2 pivot = new((float)(7+42*.23),(float)(9+39*.61));
                AssertVfxNear(anchor,AlphaUvPoint(batch,index,pivot/64),"arbitrary alpha pivot remains fixed through flips/rotation");
                Vector2 corner = -pivot;
                if (fx) corner.X = -corner.X; if (fy) corner.Y = -corner.Y;
                AssertVfxNear(anchor+corner.RotatedBy(angle*Math.PI/180),AlphaUvPoint(batch,index,Vector2.Zero),"whole frame geometry and rotation retained");
                Equal(before,JsonSerializer.Serialize(body),"arbitrary transform is read-only");
            }
            foreach (string? space in new string?[] {null,"frame"})
            {
                body=AlphaBody(space); index=count();
                Equal(true,AlphaDraw(batch,texture,body,footprint,camera,null),"frame semantics need no measured bounds");
                AssertVfxNear(anchor,AlphaUvPoint(batch,index,new Vector2(.5f,1)),"absent/frame uses full canvas bottom");
                AssertVfxNear(anchor-new Vector2(4,16),AlphaUvPoint(batch,index,new Vector2(28f/64,48f/64)),"frame-space transparent padding remains intentional");
            }
            foreach (Rectangle? unavailable in new Rectangle?[] {null,Rectangle.Empty,new Rectangle(0,0,0,10)})
            {
                index=count();
                Equal(false,AlphaDraw(batch,texture,AlphaBody("alpha_bounds"),footprint,camera,unavailable),"unknown/empty alpha bounds refuse, never frame fallback");
                Equal(index,count(),"refusal queues no custom body");
            }
            // Culling must use the same alpha pivot, including padding and rotation.
            var intersects=typeof(GeneratedPlacedBodyDrawSystem).GetMethod("IntersectsViewport",PersistenceStatic)!;
            object?[] cull={texture,AlphaBody("alpha_bounds"),new Rectangle(0,0,32,48),new Vector2(0,0),2,2};
            Equal(true,(bool)intersects.Invoke(null,cull.Append((object?)bounds).ToArray())!,"full frame intersects above alpha anchor");
            Equal(false,(bool)intersects.Invoke(null,cull.Append((object?)Rectangle.Empty).ToArray())!,"empty alpha basis is not viewport-visible");
        });
    }

    private static void PlacedAlphaCacheMeasuresOnceAndReturnsSelectedGeneration()
    {
        bool dedicated=Terraria.Main.dedServ; Terraria.Main.dedServ=false;
        var hooks=new List<MonoMod.RuntimeDetour.ILHook>();
        try
        {
            Texture2D texture=CpuTexture(8,6); int reads=0,uploads=0;
            var source=new Color[48]; source[2+8]=new Color(255,90,20,1); source[6+4*8]=new Color(100,80,60,255);
            SpriteGpuBoundaries(hooks.Add,(_,pixels)=>{reads++;Array.Copy(source,pixels,source.Length);},(_,pixels)=>{
                uploads++;
                if (uploads == 1) {
                    Equal((byte)1,pixels[10].A,"alpha=1 retained"); Equal((byte)1,pixels[10].R,"real premultiplication unchanged");
                } else Equal(true,pixels.All(pixel=>pixel == Color.Transparent),"second alpha-empty image stays transparent");
            },_=>throw new InvalidOperationException("CPU shell must not dispose"));
            var prepare=typeof(RuntimeSpriteCache).GetMethods(PersistenceStatic).Single(m=>m.Name=="PrepareTextureAndMeasureLocalForwardRadians");
            object?[] args={texture,null,null};
            float axis=(float)prepare.Invoke(null,args)!;
            Equal(1,reads,"one existing GetData"); Equal(1,uploads,"one existing SetData");
            Rectangle? measured=args[1] as Rectangle?;
            Equal(true,args[2] is Vector2[] hull && hull.Length > 0,"same one-read pixel pass measures dropped support hull");
            Equal((Rectangle?)new Rectangle(2,1,5,4),measured,"alpha>0 pixel EDGES from same premultiplication pass");
            var principal=typeof(RuntimeSpriteCache).GetMethod("MeasureLocalForwardRadians",PersistenceStatic)!;
            Equal((float)principal.Invoke(null,new object[]{source,8,6})!,axis,"PCA threshold/axis unchanged");
            Array.Clear(source,0,source.Length); prepare.Invoke(null,args);
            Equal((Rectangle?)Rectangle.Empty,args[1] as Rectangle?,"transparent loaded image is known empty, not full frame");

            using var cache=new BorrowedSpriteCache();
            string path=cache.Publish(Path.Combine(Terraria.Program.SavePath,"alpha-final-selected.png"));
            ConstructorInfo? loaded=cache.Record.GetConstructors().SingleOrDefault(c=>c.GetParameters().Length==4);
            Equal(true,loaded is not null,"real loaded-bounds record exists alongside retained 3arg unknown ctor");
            var query=typeof(RuntimeSpriteCache).GetMethods().SingleOrDefault(m=>m.Name=="TryGet"&&m.GetParameters().Length==3);
            Equal(true,query is not null,"texture and bounds returned from one selected generation");
            object?[] queryArgs={path,0f,null};
            cache.Textures[path]=loaded!.Invoke(new object?[]{texture,.7f,0L,new Rectangle(2,1,5,4)});
            Equal(true,ReferenceEquals(texture,query!.Invoke(cache.Cache,queryArgs)),"same selected texture");
            Equal(.7f,(float)queryArgs[1]!,"selected axis unchanged"); Equal((Rectangle?)new Rectangle(2,1,5,4),queryArgs[2] as Rectangle?,"matching selected bounds");
            var next=CpuTexture(8,6); cache.Textures[path]=loaded.Invoke(new object?[]{next,-.2f,1L,new Rectangle(1,3,2,2)});
            Equal(true,ReferenceEquals(next,query.Invoke(cache.Cache,queryArgs)),"new selected generation returned");
            Equal((Rectangle?)new Rectangle(1,3,2,2),queryArgs[2] as Rectangle?,"no stale prior-generation bounds");
            cache.Textures[path]=Activator.CreateInstance(cache.Record,texture,0f,2L)!;
            query.Invoke(cache.Cache,queryArgs); Equal(null,queryArgs[2],"3arg fixture ctor honestly means unknown bounds");
            Equal(2,reads,"hot cache did no additional pixel reads"); Equal(2,uploads,"hot cache did no uploads");
        }
        finally { foreach(var hook in hooks.AsEnumerable().Reverse())hook.Dispose(); Terraria.Main.dedServ=dedicated; }
    }

    private static void PlacedAlphaDtoKeepsOptionalClosedChoice()
    {
        var property=typeof(RuntimePlacedBodySpec).GetProperty("PivotSpace");
        Equal(true,property is not null,"optional PivotSpace is on real DTO");
        foreach(string? space in new string?[]{null,"frame","alpha_bounds"})
        {
            var body=AlphaBody(space); body.Validate();
            string json=JsonSerializer.Serialize(body,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});
            Equal(space is not null,json.Contains("pivotSpace"),"absent remains absent under ordinary serializer");
            var roundtrip=JsonSerializer.Deserialize<RuntimePlacedBodySpec>(json,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase})!;
            roundtrip.Validate(); Equal(space,property!.GetValue(roundtrip),"DTO roundtrip preserves exact selector");
        }
        foreach(string bad in new[]{"alpha","FRAME",""," alpha_bounds "})
        {
            bool refused=false;
            try { var body=AlphaBody(bad);body.Validate(); }
            catch(TargetInvocationException e) when(e.InnerException is InvalidDataException){refused=true;}
            catch(InvalidDataException){refused=true;}
            Equal(true,refused,"unknown selector is not normalized to frame");
        }
        string valid=JsonSerializer.Serialize(AlphaBody("frame"),new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});
        bool nullRefused=false;
        try { var body=JsonSerializer.Deserialize<RuntimePlacedBodySpec>(valid.Replace("\"frame\"","null"),new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});body!.Validate(); }
        catch(JsonException){nullRefused=true;} catch(InvalidDataException){nullRefused=true;}
        Equal(true,nullRefused,"explicit null is not omission");
        var authored = PlacedLedgerData("current_alpha_pivot");
        authored.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.PlacedBody = AlphaBody("alpha_bounds");
        var data = GeneratedItemData.FromJson(authored.ToNetworkJson())!;
        var selected = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.PlacedBody!;
        Equal("alpha_bounds", selected.PivotSpace, "authored alpha selector reaches strict current DTO");

        authored.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.PlacedBody = AlphaBody(null);
        string network = authored.ToNetworkJson(), saved = authored.ToJson();
        Equal(false, network.Contains("pivotSpace", StringComparison.OrdinalIgnoreCase), "current network preserves optional omission");
        Equal(false, saved.Contains("pivotSpace", StringComparison.OrdinalIgnoreCase), "current save preserves optional omission");
        string identity = GeneratedItemRegistryService.DefinitionIdentity(authored);
        foreach (string json in new[] { network, saved })
        {
            var roundtrip = GeneratedItemData.FromJson(json)!;
            Equal(null, roundtrip.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.PlacedBody!.PivotSpace,
                "current omitted selector does not acquire frame metadata");
            Equal(identity, GeneratedItemRegistryService.DefinitionIdentity(roundtrip), "current optional omission retains definition identity");
        }
    }

    private static void PlacedAlphaProjectionPreservesMaterialAndPhysics()
    {
        WithPlacedLedger((player,ledger)=>{
            Terraria.Main.netMode=NetmodeID.SinglePlayer;
            var data=PlacedLedgerData("alpha-placed-projection"); var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.PlacedBody=AlphaBody("alpha_bounds");
            var prop=typeof(RuntimePlacedBodySpec).GetProperty("PivotSpace"); Equal(true,prop is not null,"real DTO choice required");
            player.inventory[player.selectedItem]=ReviewItem(data).Item;
            var tile=Terraria.Main.tile[40,40];tile.HasTile=false;
            Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"explicit alpha authorizes same native placement");
            tile.HasTile=true;tile.TileType=TileID.Stone;
            Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"existing material ledger commits");
            ledger.PostUpdateEverything();
            object[] views=((System.Collections.IEnumerable)typeof(GeneratedPlacementLedgerSystem).GetMethod("VisiblePlacedBodies",PersistenceStatic)!.Invoke(null,null)!).Cast<object>().ToArray();
            Equal(1,views.Length,"real exact-ledger placed projection");
            var body=(RuntimePlacedBodySpec)views[0].GetType().GetProperty("Body")!.GetValue(views[0])!;
            Equal("alpha_bounds",(string)prop!.GetValue(body)!,"projection retains explicit alpha choice");
            // Compare the complete authoritative NBT state. The native gzip
            // witness in a network snapshot has a wall-clock header, so two
            // unchanged snapshots can have different transport bytes.
            string before=PersistenceRawBytes(PlacedLedgerSaved(ledger)); string definition=JsonSerializer.Serialize(data);
            int width=player.inventory[player.selectedItem].width,height=player.inventory[player.selectedItem].height;
            float scale=player.inventory[player.selectedItem].scale;
            WithVfxGeometryQueue((batch,_,count,positions,colors)=>{
                int index=count();
                Equal(false,AlphaDraw(batch,CpuTexture(64,64),body,new Rectangle(640,640,16,16),Vector2.Zero,Rectangle.Empty),"empty PNG refuses cosmetic draw only");
                Equal(index,count(),"empty refuses before queue submission");
            });
            Equal(before,PersistenceRawBytes(PlacedLedgerSaved(ledger)),"draw refusal preserves authoritative material ledger bytes");
            Equal(definition,JsonSerializer.Serialize(data),"definition unchanged");
            Equal(width,player.inventory[player.selectedItem].width,"item physics width unchanged");
            Equal(height,player.inventory[player.selectedItem].height,"item physics height unchanged");
            Equal(scale,player.inventory[player.selectedItem].scale,"item physics scale unchanged");
            Equal(true,tile.HasTile&&tile.TileType==TileID.Stone,"native tile unchanged");
            Equal(true,GeneratedPlacementLedgerSystem.HasLivePlacedBody(40,40),"failed explicit alpha draw never restores native body");
            var saved=PlacedLedgerSaved(ledger);ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));ledger.PostUpdateEverything();
            views=((System.Collections.IEnumerable)typeof(GeneratedPlacementLedgerSystem).GetMethod("VisiblePlacedBodies",PersistenceStatic)!.Invoke(null,null)!).Cast<object>().ToArray();
            Equal("alpha_bounds",(string)prop.GetValue(views.Single().GetType().GetProperty("Body")!.GetValue(views.Single()))!,"native save/load retains opt-in choice");
        });
    }
}
