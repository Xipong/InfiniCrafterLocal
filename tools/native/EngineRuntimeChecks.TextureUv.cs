using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

internal static partial class EngineRuntimeChecks
{
    private static void TextureUvActualQuadMatrixPreservesWorldGeometry()
    {
        WithVfxGeometryQueue((batch,texture,count,positions,colors)=>{
            var array=(Array)typeof(SpriteBatch).GetField("vertexInfo",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(batch)!;
            for(int turn=0;turn<4;turn++)for(int mirrors=0;mirrors<4;mirrors++)for(int body=0;body<4;body++) {
                var uv=new VfxTextureUv(turn,(mirrors&1)!=0,(mirrors&2)!=0);
                var effects=(SpriteEffects)body;int first=count();
                var position=new Vector2(130,85);var origin=new Vector2(-.4f,2.2f);var scale=new Vector2(9,4);float rotation=.37f;
                batch.Draw(texture,position,null,Color.White,rotation,origin,scale,effects,0);
                uv.Draw(batch,texture,position,Color.White,rotation,origin,scale,effects);
                Equal(first+2,count(),"UV transform adds exactly one quad");
                var originalPositions=positions(first);var transformedPositions=positions(first+1);
                var originalUv=CpuVertexValues<Vector2>(array.GetValue(first)!);var transformedUv=CpuVertexValues<Vector2>(array.GetValue(first+1)!);
                for(int i=0;i<4;i++) {
                    int j=Enumerable.Range(0,4).OrderBy(j=>Vector3.Distance(originalPositions[i],transformedPositions[j])).First();
                    Equal(true,Vector3.Distance(originalPositions[i],transformedPositions[j])<.001f,"world corner preserved for nonsquare/pivot/bodyflip");
                    var input=originalUv[i];
                    float u=(mirrors&1)!=0?1-input.X:input.X,v=(mirrors&2)!=0?1-input.Y:input.Y;
                    var expected=new[]{new Vector2(u,v),new Vector2(v,1-u),new Vector2(1-u,1-v),new Vector2(1-v,u)}[turn];
                    AssertVfxNear(expected,transformedUv[j],"independent D4 table at retained world corner");
                }
            }
        });
    }
    private static void TextureUvPathRepeatAndSnapshot()
    {
        var data=ParseMaterialElement(MaterialElementWire());var path=OwnerLinkSlot(data.VfxManifest.Slots[0]).Path!;
        path.OwnerAnchor="mountedCenter";path.Texture.Uv=new(){QuarterTurns=1,MirrorU=false,MirrorV=false};
        object design=LibraryInvoke("CopyPath",path,1f,"alpha","","BeforeProjectiles","self",512,0)!;
        path.Texture.Uv.QuarterTurns=0;
        var mesh=(VertexPositionColorTexture[])LibraryInvoke("BuildMaterialPathMesh",new[]{Vector2.Zero,new Vector2(96,0)},Array.Empty<float>(),design,3UL,(Func<bool>)(()=>true))!;
        Equal(true,mesh.Length>0,"UV path remains actual geometry");
        Equal(true,mesh.Any(v=>v.TextureCoordinate.Y<0),"repeat UV remains unbounded; no fract/clamp destroys tiling");
        Equal(true,mesh.All(v=>v.TextureCoordinate.X is 0 or 1),"quarter turn moves transverse axis to texture U");
        var saved=new VfxTextureSpec{Source="library",AssetId="star"};
        Equal(true,VfxTextureUv.Copy(saved.Uv)==default,"saved missing UV is exact identity");
        var json=System.Text.Json.JsonSerializer.Serialize(saved,new System.Text.Json.JsonSerializerOptions{PropertyNamingPolicy=System.Text.Json.JsonNamingPolicy.CamelCase});
        Equal(false,json.Contains("\"uv\""),"saved missing UV remains absent on wire");
        bool nullRejected=false;try {saved.Uv=null;}catch(System.IO.InvalidDataException){nullRejected=true;}
        Equal(true,nullRejected,"present null is not historical omission");
        saved.Uv=new(){QuarterTurns=4};bool rejected=false;
        try{saved.Validate();}catch(System.IO.InvalidDataException){rejected=true;}
        Equal(true,rejected,"invalid authored turn is never normalized to identity");
    }
}
