#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
namespace InfiniCrafterLocal.Common.VFX;
public sealed partial class InfiniDetachedVfxSystem
{
    private sealed record PathDesign(string TexturePath,string Layer,string Blend,float Alpha,string Source,string Anchor,int HistoryTicks,
        float MinDistance,float MaxSegment,float Width,string Domain,string Uv,float Repeat,float Scroll,
        VfxNumberRamp WidthRamp,VfxNumberRamp OpacityRamp,VfxColorRamp ColorRamp,int MaxDraw,int StartTick);
    private static PathDesign CopyPath(VfxTexturedPathSpec p,Color effect,float alpha,string blend,string path="",string layer="BeforeProjectiles",string anchor="self",int maxDraw=512,int startTick=0)
        =>new(path,layer,blend,alpha,p.Source,anchor,p.HistoryTicks,p.MinDistancePx,p.MaxSegmentLengthPx,p.WidthPx,p.ProfileDomain,
            p.UvMode,p.RepeatLengthPx,p.ScrollPxPerTick,VfxNumberRamp.Copy(p.WidthProfile),VfxNumberRamp.Copy(p.OpacityProfile),
            VfxColorRamp.Copy(p.ColorProfile,effect),maxDraw,startTick);
    private readonly record struct PathSample(Vector2 Position,ulong Tick);
    private sealed class MaterialPath {
        internal required VfxSourceBinding Binding;
        internal required PathDesign Design;
        internal required string SourceKey,SlotId;
        internal readonly List<PathSample> History=new();
        internal Vector2[] Geometry=Array.Empty<Vector2>();
        internal ulong FirstTick,SampleTick;
        internal int InitialAge;
    }
    private static readonly List<MaterialPath> MaterialPaths=new();
    internal static void RegisterMaterialPaths(GeneratedItemData data,string entityId,string sourceKey,VfxSourceBinding? binding)
    {
        if(Main.dedServ||binding is null||!binding.IsLive)return;
        foreach(var slot in data.VfxManifest.Slots) {
            if(slot.EntityId!=entityId||slot.Path is not {} path)continue;
            if(MaterialPaths.Any(p=>ReferenceEquals(p.Binding.Generation,binding.Generation)&&p.SlotId==slot.Id))continue;
            if(OwnedRecordCount>=MaxEmissions)return;
            string texture=ResolveMaterialTexture(data,entityId,path.Texture);if(string.IsNullOrEmpty(texture))continue;
            var effect=InfiniVfxRuntime.PresentationColor(data,InfiniVfxRuntime.LegacyPresentationColor(data.VfxManifest,Color.White));
            MaterialPaths.Add(new MaterialPath{Binding=binding,Design=CopyPath(path,effect,slot.Alpha,slot.Blend,texture,slot.Layer,slot.Anchor,data.VfxManifest.Budget.MaxDrawCalls,slot.StartTick),
                SourceKey=sourceKey,SlotId=slot.Id,FirstTick=Main.GameUpdateCount,InitialAge=binding.WorldAge});
        }
    }
    private static void UpdateMaterialPaths(ulong now)
    {
        foreach(var p in MaterialPaths) {
            p.SampleTick=now;
            if(p.Design.Source=="anchorHistory") {
                p.History.RemoveAll(s=>now<s.Tick||now-s.Tick>=(ulong)p.Design.HistoryTicks);
                if(!p.Binding.IsLive||now-p.FirstTick+(ulong)Math.Max(0,p.InitialAge)<(ulong)p.Design.StartTick||!p.Binding.TryFrame(p.Design.Anchor,out var frame))continue;
                if(p.History.Count>0&&Vector2.Distance(p.History[^1].Position,frame.Position)<p.Design.MinDistance)continue;
                if(p.History.Count>=32)p.History.RemoveAt(0);
                p.History.Add(new(frame.Position,now));
            }else {
                p.Geometry=Array.Empty<Vector2>();
                if(p.Binding.IsLive&&now-p.FirstTick+(ulong)Math.Max(0,p.InitialAge)>=(ulong)p.Design.StartTick&&p.Binding.TryGeometry(p.Design.Source,out var points))p.Geometry=points;
            }
        }
        MaterialPaths.RemoveAll(p=>!p.Binding.IsLive&&(p.Design.Source!="anchorHistory"||p.History.Count==0));
    }
    // Native adapter / headless geometric seam. Input is actual supplied geometry;
    // the pure builder does not invent body/source paths or touch world/gameplay.
    internal static VertexPositionColorTexture[] MaterialPathVertices(Vector2[] points,float[] ages,VfxTexturedPathSpec spec,
        Color capturedEffect,float alpha,string blend,ulong worldTick,Func<bool> spend)
        =>BuildMaterialPathMesh(points,ages,CopyPath(spec,capturedEffect,alpha,blend),worldTick,spend);
    private static VertexPositionColorTexture[] BuildMaterialPathMesh(Vector2[] input,float[] ages,PathDesign d,ulong worldTick,Func<bool> spend)
    {
        int cap=d.Source=="anchorHistory"?32:65;
        if(input.Length<2||input.Length>cap||input.Any(p=>!float.IsFinite(p.X)||!float.IsFinite(p.Y)))return Array.Empty<VertexPositionColorTexture>();
        var points=new List<Vector2>(input);var domains=new List<float>();
        var distances=new List<float>{0};float total=0;
        for(int i=1;i<points.Count;i++){total+=Vector2.Distance(points[i-1],points[i]);distances.Add(total);}
        if(!float.IsFinite(total)||total<=0)return Array.Empty<VertexPositionColorTexture>();
        if(d.Domain=="age") {
            if(ages.Length!=points.Count||ages.Any(a=>!float.IsFinite(a)))return Array.Empty<VertexPositionColorTexture>();
            domains.AddRange(ages.Select(a=>Math.Clamp(a,0,1)));
        }else {
            // A geometry length profile has a real middle knot. Add one point on
            // the original straight segment, never decimate any collision corner.
            if(d.Source!="anchorHistory")for(int i=1;i<points.Count;i++) {
                float middle=total*0.5f;
                if(distances[i-1]<middle&&distances[i]>middle&&distances[i]-distances[i-1]<=d.MaxSegment) {
                    float t=(middle-distances[i-1])/(distances[i]-distances[i-1]);
                    points.Insert(i,Vector2.Lerp(points[i-1],points[i],t));distances.Insert(i,middle);break;
                }
            }
            domains.AddRange(distances.Select(v=>v/total));
        }
        int count=points.Count;
        var halfWidth=new float[count];var color=new Color[count];var connected=new bool[count-1];var direction=new Vector2[count-1];
        double offset=d.Uv=="repeat"?worldTick*(double)d.Scroll/d.Repeat:0;offset-=Math.Floor(offset);
        var u=new float[count];
        for(int i=0;i<count;i++) {
            halfWidth[i]=d.Width*d.WidthRamp.At(domains[i])*0.5f;color[i]=d.ColorRamp.At(domains[i],d.Alpha*d.OpacityRamp.At(domains[i]),d.Blend);
            u[i]=d.Uv=="repeat"?distances[i]/d.Repeat+(float)offset:distances[i]/total;
        }
        int segments=0;
        for(int i=0;i<count-1;i++) {
            var delta=points[i+1]-points[i];float length=delta.Length();
            if(length<=0||length>d.MaxSegment||halfWidth[i]<=0&&halfWidth[i+1]<=0||color[i]==Color.Transparent&&color[i+1]==Color.Transparent)continue;
            if(!spend())break;
            connected[i]=true;direction[i]=delta/length;segments++;
        }
        if(segments==0)return Array.Empty<VertexPositionColorTexture>();
        var left=new VertexPositionColorTexture[count];var right=new VertexPositionColorTexture[count];
        for(int i=0;i<count;i++) {
            bool before=i>0&&connected[i-1],after=i<count-1&&connected[i];if(!before&&!after)continue;
            var tangent=before?direction[i-1]:direction[i];var normal=new Vector2(-tangent.Y,tangent.X);var section=normal*halfWidth[i];
            if(before&&after){var next=new Vector2(-direction[i].Y,direction[i].X);var sum=normal+next;
                if(sum.LengthSquared()>0.0001f){var miter=Vector2.Normalize(sum);section=miter*(halfWidth[i]/Math.Max(0.5f,Vector2.Dot(miter,normal)));}}
            left[i]=new(new Vector3(points[i]+section,0),color[i],new Vector2(u[i],0));right[i]=new(new Vector3(points[i]-section,0),color[i],new Vector2(u[i],1));
        }
        var mesh=new VertexPositionColorTexture[segments*6];int v=0;
        for(int i=0;i<count-1;i++)if(connected[i]) {
            mesh[v++]=left[i];mesh[v++]=right[i];mesh[v++]=left[i+1];mesh[v++]=left[i+1];mesh[v++]=right[i];mesh[v++]=right[i+1];
        }
        return mesh;
    }
    private static BasicEffect? MaterialPathEffect;
    private static void DrawMaterialPaths(string layer,GraphicsDevice device)
    {
        foreach(var p in MaterialPaths) {
            var d=p.Design;if(d.Layer!=layer)continue;
            var points=d.Source=="anchorHistory"?p.History.Select(s=>s.Position).ToArray():p.Geometry;
            if(points.Length<2)continue;
            var texture=InfiniCrafterLocalMod.Sprites.TryGet(d.TexturePath);if(texture is null)continue;
            var ages=p.History.Select(s=>(p.SampleTick-s.Tick)/(float)d.HistoryTicks).ToArray();
            var mesh=BuildMaterialPathMesh(points,ages,d,p.SampleTick,()=>TrySpendSourceDraw(p.SourceKey,d.MaxDraw,1));if(mesh.Length==0)continue;
            DrawMaterialPathMesh(device,texture,mesh,d.Uv=="repeat");
        }
    }
    internal static void DrawMaterialPathMesh(GraphicsDevice device,Texture2D texture,VertexPositionColorTexture[] vertices,bool repeat)
    {
        var blend=device.BlendState;var depth=device.DepthStencilState;var rasterizer=device.RasterizerState;
        var sampler=device.SamplerStates[0];var previousTexture=device.Textures[0];var buffers=device.GetVertexBuffers();var indices=device.Indices;
        try {
            if(MaterialPathEffect is null||MaterialPathEffect.IsDisposed)MaterialPathEffect=new BasicEffect(device){TextureEnabled=true,VertexColorEnabled=true,LightingEnabled=false};
            var effect=MaterialPathEffect;effect.Texture=texture;
            effect.World=Matrix.CreateTranslation(-Main.screenPosition.X,-Main.screenPosition.Y,0)*Main.GameViewMatrix.TransformationMatrix;
            effect.View=Matrix.Identity;effect.Projection=Matrix.CreateOrthographicOffCenter(0,device.Viewport.Width,device.Viewport.Height,0,0,1);
            device.BlendState=BlendState.AlphaBlend;device.DepthStencilState=DepthStencilState.None;device.RasterizerState=RasterizerState.CullNone;
            device.SamplerStates[0]=repeat?SamplerState.PointWrap:SamplerState.PointClamp;
            foreach(var pass in effect.CurrentTechnique.Passes){pass.Apply();device.DrawUserPrimitives(PrimitiveType.TriangleList,vertices,0,vertices.Length/3);}
        }finally {
            device.BlendState=blend;device.DepthStencilState=depth;device.RasterizerState=rasterizer;device.SamplerStates[0]=sampler;device.Textures[0]=previousTexture;
            device.SetVertexBuffers(buffers);device.Indices=indices;
        }
    }
}
