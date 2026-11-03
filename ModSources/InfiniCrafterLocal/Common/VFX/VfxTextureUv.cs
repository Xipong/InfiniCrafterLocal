#nullable enable
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

// Sampling-coordinate transform, not movement, grip inference or a rotated PNG cache.
internal readonly record struct VfxTextureUv(int QuarterTurns,bool MirrorU,bool MirrorV)
{
    internal static VfxTextureUv Copy(VfxUvTransformSpec? value)=>value is null?default:new(value.QuarterTurns,value.MirrorU,value.MirrorV);
    internal Vector2 Map(Vector2 uv)
    {
        if(MirrorU)uv.X=1-uv.X;if(MirrorV)uv.Y=1-uv.Y;
        return QuarterTurns switch {1=>new(uv.Y,1-uv.X),2=>new(1-uv.X,1-uv.Y),3=>new(1-uv.Y,uv.X),_=>uv};
    }
    internal void Draw(SpriteBatch batch,Texture2D texture,Vector2 position,Color color,float rotation,Vector2 origin,Vector2 scale,SpriteEffects effects)
    {
        if(this==default) {batch.Draw(texture,position,null,color,rotation,origin,scale,effects,0);return;}
        // Recover the original quad center BEFORE changing texture coordinates.
        // Even a non-central grip keeps exactly the same world rectangle/pivot.
        var center=position+(new Vector2(texture.Width*.5f-origin.X,texture.Height*.5f-origin.Y)*scale).RotatedBy(rotation);
        bool flipU=((effects&SpriteEffects.FlipHorizontally)!=0)^MirrorU;
        bool flipV=((effects&SpriteEffects.FlipVertically)!=0)^MirrorV;
        if((QuarterTurns&1)!=0) { (flipU,flipV)=(flipV,flipU);scale=new(texture.Height*scale.Y/texture.Width,texture.Width*scale.X/texture.Height); }
        var flips=(flipU?SpriteEffects.FlipHorizontally:SpriteEffects.None)|(flipV?SpriteEffects.FlipVertically:SpriteEffects.None);
        batch.Draw(texture,center,null,color,rotation+QuarterTurns*MathHelper.PiOver2,new Vector2(texture.Width,texture.Height)*.5f,scale,flips,0);
    }
}
