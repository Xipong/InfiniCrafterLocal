using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using Terraria;

// Observes the original SpriteBatch overload. Never substitutes a production pose.
internal sealed class WNativeVisualGeometry : IDisposable
{
    delegate void Original(SpriteBatch self,Texture2D texture,Vector2 position,Rectangle? source,Color color,float rotation,Vector2 origin,float scale,SpriteEffects effects,float depth);
    delegate void Observe(Original orig,SpriteBatch self,Texture2D texture,Vector2 position,Rectangle? source,Color color,float rotation,Vector2 origin,float scale,SpriteEffects effects,float depth);
    readonly Hook hook;
    static Action<Texture2D,Vector2,Rectangle?,Color,float,Vector2,Vector2,SpriteEffects>? sink;
    // Published artwork is immutable for the lifetime of this isolated renderer.
    static readonly Dictionary<Texture2D,Color[]> pixels=new();
    public WNativeVisualGeometry()
    {
        hook=new Hook(typeof(SpriteBatch).GetMethod("Draw",new[]{typeof(Texture2D),typeof(Vector2),typeof(Rectangle?),typeof(Color),typeof(float),typeof(Vector2),typeof(float),typeof(SpriteEffects),typeof(float)})!,
            (Observe)((orig,self,texture,position,source,color,rotation,origin,scale,effects,depth)=>{
                orig(self,texture,position,source,color,rotation,origin,scale,effects,depth);
                sink?.Invoke(texture,position,source,color,rotation,origin,new Vector2(scale),effects);
            }));
    }
    public static JsonArray Capture(Action action,Vector2? grip=null,float? supportY=null)
    {
        var rows=new JsonArray();var previous=sink;
        sink=(texture,position,source,color,rotation,origin,scale,effects)=>rows.Add(Describe(texture,position,source,color,rotation,origin,scale,effects,grip,supportY));
        try{action();}finally{sink=previous;}
        return rows;
    }
    public static JsonObject Point(Vector2 p)=>new(){["x"]=p.X,["y"]=p.Y};
    public static JsonObject Rect(Rectangle r)=>new(){["x"]=r.X,["y"]=r.Y,["width"]=r.Width,["height"]=r.Height};
    public static JsonObject Describe(Texture2D texture,Vector2 position,Rectangle? source,Color color,float rotation,Vector2 origin,Vector2 scale,SpriteEffects effects,Vector2? grip=null,float? supportY=null)
    {
        Rectangle frame=source??texture.Bounds;
        Vector2 World(float x,float y){if((effects&SpriteEffects.FlipHorizontally)!=0)x=frame.Width-x;if((effects&SpriteEffects.FlipVertically)!=0)y=frame.Height-y;return position+((new Vector2(x,y)-origin)*scale).RotatedBy(rotation)+Main.screenPosition;}
        var row=new JsonObject{["coordinateSpace"]="world px; observed SpriteBatch arguments before camera/view matrix",["position"]=Point(position+Main.screenPosition),["origin"]=Point(origin),["scale"]=Point(scale),["rotation"]=rotation,["effects"]=effects.ToString(),["textureWidth"]=texture.Width,["textureHeight"]=texture.Height,["source"]=Rect(frame),["opacity"]=color.A};
        if(grip is Vector2 uv)row["authoredGrip"]=Point(World(uv.X*frame.Width,uv.Y*frame.Height));
        if(supportY is null)return row; // Grip/collider review does not need expensive silhouette scans.
        if(!pixels.TryGetValue(texture,out var rgba)){rgba=new Color[texture.Width*texture.Height];texture.GetData(rgba);pixels.Add(texture,rgba);}
        // Full transformed opaque-pixel corners, not alpha AABB corners. Report an
        // envelope per world-pixel column; decoration is intentionally not classified.
        var contour=new SortedDictionary<int,float>();int opaque=0;
        for(int y=0;y<frame.Height;y++)for(int x=0;x<frame.Width;x++){
            if(rgba[(frame.Y+y)*texture.Width+frame.X+x].A<128)continue;opaque++;
            Vector2[] corners={World(x,y),World(x+1,y),World(x,y+1),World(x+1,y+1)};
            // Clockwise polygon, clipped against each world-column slab. A rotated
            // pixel's deepest corner cannot count as support in every column.
            corners=new[]{corners[0],corners[1],corners[3],corners[2]};
            float minX=corners.Min(p=>p.X),maxX=corners.Max(p=>p.X);
            if(!float.IsFinite(minX)||!float.IsFinite(maxX)||maxX-minX>16384||Math.Abs(minX)>10000000||Math.Abs(maxX)>10000000)
                throw new InvalidOperationException("Visual geometry outside bounded observer coordinates");
            int left=(int)Math.Floor(minX),right=(int)Math.Ceiling(maxX);
            for(int column=left;column<right;column++){
                float bottom=float.NegativeInfinity;
                for(int k=0;k<4;k++){
                    Vector2 a=corners[k],b=corners[(k+1)%4];
                    if(a.X>=column&&a.X<=column+1)bottom=Math.Max(bottom,a.Y);
                    foreach(float edge in new[]{(float)column,column+1f})if(a.X!=b.X && edge>=Math.Min(a.X,b.X)&&edge<=Math.Max(a.X,b.X))
                        bottom=Math.Max(bottom,a.Y+(b.Y-a.Y)*(edge-a.X)/(b.X-a.X));
                }
                if(float.IsFinite(bottom))contour[column]=contour.TryGetValue(column,out float old)?Math.Max(old,bottom):bottom;
            }
        }
        var columns=new JsonArray();foreach(var pair in contour)columns.Add(new JsonObject{["x"]=pair.Key,["bottomY"]=pair.Value,["gapToSupportPx"]=supportY is float floor?floor-pair.Value:null});
        row["supportContour"]=columns;row["opaquePixelCount"]=opaque;row["alphaThreshold"]=128;
        row["supportAssessment"]="review_required: exact column-slab silhouette envelope at alpha >=128 only; leaves, tilted ends and isolated pixels are not a structural base or aesthetic approval";
        if(supportY is float sy && contour.Count>0){var gaps=contour.Values.Select(v=>sy-v).OrderBy(v=>v).ToArray();row["supportY"]=sy;row["minimumGapPx"]=gaps[0];row["medianColumnGapPx"]=gaps[gaps.Length/2];row["contactColumnsWithin1Px"]=gaps.Count(g=>Math.Abs(g)<=1);row["contourColumns"]=gaps.Length;}
        return row;
    }
    public void Dispose(){hook.Dispose();sink=null;pixels.Clear();}
}
