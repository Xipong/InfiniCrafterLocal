using System;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

internal static partial class EngineRuntimeChecks
{
    private static void PlacedBodySubmitsOneExplicitFullFrameToNativeFna()
    {
        Type? renderer = typeof(RuntimePlacementSpec).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedPlacedBodyDrawSystem");
        Equal(true,renderer is not null,"placed full-frame PNG renderer exists");
        const BindingFlags flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
        var draw = renderer!.GetMethod("DrawBody", BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public)!;
        T Shell<T>() where T:class {var value=(T)RuntimeHelpers.GetUninitializedObject(typeof(T));GC.SuppressFinalize(value);return value;}
        var texture=Shell<Texture2D>();typeof(Texture2D).GetProperty("Width")!.SetValue(texture,64);typeof(Texture2D).GetProperty("Height")!.SetValue(texture,48);
        var batch=Shell<SpriteBatch>();
        foreach(string name in new[]{"vertexInfo","textureInfo","spriteInfos","sortedSpriteInfos"})
        {var field=typeof(SpriteBatch).GetField(name,flags)!;field.SetValue(batch,Array.CreateInstance(field.FieldType.GetElementType()!,16));}
        var count=typeof(SpriteBatch).GetField("numSprites",flags)!;
        using var flush=new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch",flags)!, (Action<SpriteBatch>)(self=>count.SetValue(self,0)));
        var body=new RuntimePlacedBodySpec{RenderSizePx=37,FootprintAnchorX=.25,FootprintAnchorY=1,ImagePivotX=.125,ImagePivotY=.75,OffsetXPx=-13,OffsetYPx=17,RotationDegrees=0,FlipX=true,FlipY=false};
        batch.Begin();
        try
        {
            draw.Invoke(null,new object[]{batch,texture,body,new Rectangle(640,640,16,16),Vector2.Zero,Color.White});
            Equal(1,(int)count.GetValue(batch)!,"one root PNG per explicit placement group");
            object quad=((Array)typeof(SpriteBatch).GetField("vertexInfo",flags)!.GetValue(batch)!).GetValue(0)!;
            var first=(Vector3)quad.GetType().GetField("Position0",flags)!.GetValue(quad)!;
            Equal(new Vector3(631-56*(37f/64),673-36*(37f/64),0),first,"explicit footprint anchor/pivot/offset, reflection about pivot and full-frame size");
            var second=(Vector3)quad.GetType().GetField("Position1",flags)!.GetValue(quad)!;
            Equal(37f,MathF.Abs(second.X-first.X),"longest complete PNG side is authored world extent");
            var uv0=(Vector2)quad.GetType().GetField("TextureCoordinate0",flags)!.GetValue(quad)!;
            Equal(1f,uv0.X,"explicit flip changes UV not semantic tile orientation");
            var rotationCases = new[] {
                (Body: new RuntimePlacedBodySpec { RenderSizePx=64,FootprintAnchorX=1,FootprintAnchorY=0,ImagePivotX=1,ImagePivotY=0,OffsetXPx=0,OffsetYPx=0,RotationDegrees=90,FlipX=false,FlipY=true }, First:new Vector3(702,573,0), Uv:new Vector2(0,1)),
                (Body: new RuntimePlacedBodySpec { RenderSizePx=64,FootprintAnchorX=0,FootprintAnchorY=1,ImagePivotX=0,ImagePivotY=1,OffsetXPx=5,OffsetYPx=-7,RotationDegrees=-90,FlipX=true,FlipY=true }, First:new Vector3(643,710,0), Uv:new Vector2(1,1))
            };
            foreach(var test in rotationCases)
            {
                int slot=(int)count.GetValue(batch)!;
                draw.Invoke(null,new object[]{batch,texture,test.Body,new Rectangle(640,640,16,16),new Vector2(2,3),Color.White});
                Equal(slot+1,(int)count.GetValue(batch)!,"one rotated full frame submitted");
                object rotated=((Array)typeof(SpriteBatch).GetField("vertexInfo",flags)!.GetValue(batch)!).GetValue(slot)!;
                var position=(Vector3)rotated.GetType().GetField("Position0",flags)!.GetValue(rotated)!;
                Equal(true,Vector3.Distance(position,test.First)<.0001f,"nonzero rotation, pivot endpoints, camera and vertical/both flips preserve authored geometry");
                Equal(test.Uv,(Vector2)rotated.GetType().GetField("TextureCoordinate0",flags)!.GetValue(rotated)!,"full-frame reflected UV endpoints");
            }
            var cull=renderer.GetMethod("IntersectsViewport",BindingFlags.Static|BindingFlags.NonPublic)!;
            var overhang=new RuntimePlacedBodySpec { RenderSizePx=64,FootprintAnchorX=0,FootprintAnchorY=0,ImagePivotX=0,ImagePivotY=0,OffsetXPx=0,OffsetYPx=0,RotationDegrees=0,FlipX=false,FlipY=false };
            Equal(true,(bool)cull.Invoke(null,new object[]{texture,overhang,new Rectangle(640,640,16,16),new Vector2(660,660),10,10})!,"PNG overhang visible while native footprint is outside viewport");
            Equal(false,(bool)cull.Invoke(null,new object[]{texture,rotationCases[0].Body,new Rectangle(640,640,16,16),new Vector2(660,650),10,10})!,"rotated full PNG culls by transformed image rather than tile footprint");
        }
        finally{batch.End();}
    }
}
