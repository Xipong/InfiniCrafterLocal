using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxShapeSpec FilledSector()=>new(){Kind="sector",Attachment="world",RotationFrame="world",ColorStart=new(){R=255,G=100,B=0},ColorEnd=new(){R=255,G=100,B=0},OpacityCurve="linear",OpacityStart=.5f,OpacityEnd=.5f,InnerRadiusStartPx=0,InnerRadiusEndPx=0,OuterRadiusStartPx=20,OuterRadiusEndPx=20,SweepRadians=MathF.Tau,Segments=16};
    private static void FilledSectorAdmission()
    {
        var slot=ExplicitShapeSlot();slot.Shape=FilledSector();
        var manifest=new VfxManifestSpec{RecipeId="sector",Slots=new[]{slot}};
        string json=manifest.ToJson();Equal(true,json.Length>0,"sector valid wire");
        Equal(json,VfxManifestSpec.FromJson(json).ToJson(),"sector exact roundtrip");
        void Reject(Action<JsonObject> change) {var root=JsonNode.Parse(json)!.AsObject();change(root["slots"]![0]!["shape"]!.AsObject());Equal(false,VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots,"invalid sector rejected");}
        Reject(s=>s["segments"]=2);Reject(s=>s["segments"]=65);Reject(s=>s["innerRadiusStartPx"]=21);Reject(s=>s["innerRadiusEndPx"]=21);
        Reject(s=>s["outerRadiusStartPx"]=null);Reject(s=>s.Remove("outerRadiusEndPx"));Reject(s=>s["widthPx"]=1);Reject(s=>s["radiusStartPx"]=1);
    }
    private static void FilledSectorMeshGeometry()
    {
        var frame=new VfxSourceFrame(new Vector2(100,200),Vector2.UnitY,Vector2.Zero);
        foreach(float sweep in new[]{MathF.Tau,-MathF.Tau,MathF.PI/2,-MathF.PI/2})foreach(float inner in new[]{0f,8f}) {
            var s=FilledSector();s.SweepRadians=sweep;s.InnerRadiusStartPx=s.InnerRadiusEndPx=inner;
            int spent=0;var mesh=InfiniDetachedVfxSystem.BuildSectorMesh(s,frame,0,10,"alpha",()=>{spent++;return true;});
            Equal(16,spent,"one budget unit per subdivision");Equal(16*(inner==0?3:6),mesh.Length,"fan has no degenerate second triangle");
            double area=0;
            for(int i=0;i<mesh.Length;i+=3) {
                var a=mesh[i+1].Position-mesh[i].Position;var b=mesh[i+2].Position-mesh[i].Position;
                double cross=a.X*b.Y-a.Y*b.X;Equal(true,cross>0,"both sweep directions keep positive winding");area+=cross*.5;
            }
            double expected=16*.5*(400-inner*inner)*Math.Sin(Math.Abs(sweep)/16);
            Equal(true,Math.Abs(area-expected)<.03,"triangles cover polygon area once, not overlapping fans");
            Equal(true,mesh.All(v=>v.Color.A is >=126 and <=128),"alpha exactly once");
            Equal(true,mesh.All(v=>v.TextureCoordinate==Vector2.Zero),"solid texel sampled independent of mesh UV");
        }
        var moving=FilledSector();moving.InnerRadiusEndPx=10;moving.OuterRadiusEndPx=40;moving.OffsetForwardPx=3;moving.OffsetSidePx=4;moving.RotationFrame="source";moving.RotationRadians=.3f;moving.RotationSpeedRadiansPerTick=.1f;
        var m=InfiniDetachedVfxSystem.BuildSectorMesh(moving,frame,5,10,"additive",()=>true);
        var origin=frame.Position+frame.Rotate(new Vector2(3,4));
        AssertVfxNear(origin+(MathF.PI/2+.8f).ToRotationVector2()*5,new Vector2(m[0].Position.X,m[0].Position.Y),"source rotation offsets spin and inner interpolation");
        Equal(true,m.All(v=>v.Color.A==0&&v.Color.R is >=126 and <=128),"additive retains opacity-scaled RGB");
        foreach(int silence in new[]{0,1,2,3}) {
            var s=FilledSector();if(silence==0)s.SweepRadians=0;if(silence==1)s.OuterRadiusStartPx=s.OuterRadiusEndPx=0;if(silence==2)s.InnerRadiusStartPx=s.InnerRadiusEndPx=20;if(silence==3)s.OpacityStart=s.OpacityEnd=0;
            Equal(0,InfiniDetachedVfxSystem.BuildSectorMesh(s,frame,0,10,"alpha",()=>throw new Exception("silent sector spent budget")).Length,"silent geometry");
        }
    }
    private static void FilledSectorSharedBudgetAndSpriteIsolation()
    {
        var system=new InfiniDetachedVfxSystem();system.OnWorldUnload();
        try {
            var s=FilledSector();s.InnerRadiusStartPx=s.InnerRadiusEndPx=8;
            var frame=new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero);
            Equal(true,InfiniDetachedVfxSystem.TrySpendSourceDraw("sector-budget",5,2),"other renderer consumes same source budget first");
            var mesh=InfiniDetachedVfxSystem.BuildSectorMesh(s,frame,0,10,"alpha",()=>InfiniDetachedVfxSystem.TrySpendSourceDraw("sector-budget",5,1));
            Equal(18,mesh.Length,"remaining three segments only");
            Equal(0,InfiniDetachedVfxSystem.BuildSectorMesh(s,frame,0,10,"alpha",()=>InfiniDetachedVfxSystem.TrySpendSourceDraw("sector-budget",5,1)).Length,"second instance cannot reset shared budget");
            WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
                InfiniDetachedVfxSystem.DrawExplicitShape(pixel,s,frame,0,10,"alpha",()=>throw new Exception("mesh shape entered sprite phase"));
                Equal(0,count(),"sector never queues sprite quads");
            });
        } finally {system.OnWorldUnload();}
    }
    private static void FilledSectorMeshPrecedesSpriteBatch()
    {
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            const BindingFlags flags=BindingFlags.NonPublic|BindingFlags.Static;
            var type=typeof(InfiniDetachedVfxSystem);var system=new InfiniDetachedVfxSystem();
            var oldPixel=Terraria.GameContent.TextureAssets.MagicPixel;var oldView=Terraria.Main.GameViewMatrix;bool oldServer=Terraria.Main.dedServ;
            int submissions=0;
            var began=typeof(SpriteBatch).GetField("beginCalled",BindingFlags.NonPublic|BindingFlags.Instance)!;
            Action<GraphicsDevice,Texture2D,VertexPositionColorTexture[],bool,bool> submit=(device,texture,mesh,repeat,linear)=>{
                Equal(false,(bool)began.GetValue(batch)!,"native triangles submitted outside active SpriteBatch");
                Equal(true,ReferenceEquals(pixel,texture),"native white texture reused");
                Equal(48,mesh.Length,"actual submitted disk fan");Equal(false,repeat,"solid sampler clamps");Equal(false,linear,"sector retains point sampling");submissions++;
            };
            using var hook=new MonoMod.RuntimeDetour.Hook(type.GetMethod("DrawMaterialPathMesh",flags)!,submit);
            try {
                batch.End();system.OnWorldUnload();Terraria.Main.dedServ=false;
                Terraria.GameContent.TextureAssets.MagicPixel=CpuTextureAsset(pixel);
                Terraria.Main.GameViewMatrix=new Terraria.Graphics.SpriteViewMatrix(null!);Terraria.Main.GameViewMatrix.SetViewportOverride(new Viewport(0,0,800,600));
                var data=GeneratedItemData.Placeholder();data.VfxManifest=new(){Budget=new(){MaxDrawCalls=64}};
                var sector=ExplicitShapeSlot();sector.Shape=FilledSector();
                var line=ExplicitShapeSlot();var frame=new VfxSourceFrame(Vector2.Zero,Vector2.UnitX,Vector2.Zero);
                Equal(true,InfiniDetachedVfxSystem.EnqueueShape(data,sector,"mesh-phase",frame,null),"enqueue sector");
                Equal(true,InfiniDetachedVfxSystem.EnqueueShape(data,line,"sprite-phase",frame,null),"enqueue sprite line");
                type.GetMethod("DrawLayer",flags)!.Invoke(null,new object[]{"AfterProjectiles"});
                Equal(1,submissions,"one native mesh submission");Equal(false,(bool)began.GetValue(batch)!,"layer closes its own sprite phase");
            } finally {system.OnWorldUnload();Terraria.GameContent.TextureAssets.MagicPixel=oldPixel;Terraria.Main.GameViewMatrix=oldView;Terraria.Main.dedServ=oldServer;}
        });
    }

}
