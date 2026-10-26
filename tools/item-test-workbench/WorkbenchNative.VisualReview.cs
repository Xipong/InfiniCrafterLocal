using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;

internal sealed partial class WNativeArtwork
{
    readonly GeneratedItemData reviewData;
    readonly WNativeVisualGeometry geometryObserver;
    Hook? visualObserver;
    delegate void VisualOriginal(GeneratedProjectile self,Color color);
    delegate void VisualObserve(VisualOriginal orig,GeneratedProjectile self,Color color);
    Vector2 FrontHand()=>owner.RotatedRelativePoint(owner.GetFrontHandPosition(owner.compositeFrontArm.stretch,owner.compositeFrontArm.rotation),addGfxOffY:false);
    Vector2 RenderedFrontHand()=>owner.RotatedRelativePoint(owner.GetFrontHandPosition(owner.compositeFrontArm.stretch,owner.compositeFrontArm.rotation),addGfxOffY:true);
    JsonObject PlayerReview()=>new(){["nativeFrontHand"]=WNativeVisualGeometry.Point(FrontHand()),["nativeRenderedFrontHand"]=WNativeVisualGeometry.Point(RenderedFrontHand()),["compositeArmEnabled"]=owner.compositeFrontArm.enabled,["armStretch"]=owner.compositeFrontArm.stretch.ToString(),["armRotation"]=owner.compositeFrontArm.rotation,["handScope"]="Native GetFrontHandPosition; authoritative only when composite arm is enabled. For ordinary frame arms inspect native proxy and rendered pixels; do not auto-fail the distance.",["collider"]=WNativeVisualGeometry.Rect(owner.Hitbox),["direction"]=owner.direction,["gravityDirection"]=owner.gravDir,["velocity"]=WNativeVisualGeometry.Point(owner.velocity),["gfxOffY"]=owner.gfxOffY,["fullRotation"]=owner.fullRotation,["accessoryMount"]=reviewData.Visual.AccessoryMount,["itemAnimation"]=owner.itemAnimation,["itemTime"]=owner.itemTime,["controlUseItem"]=owner.controlUseItem,["channel"]=owner.channel,["visualVerdict"]="review_required",["scope"]="Draw execution/visibility is not aesthetic acceptance; authored reach can intentionally separate grip from hand."};
    void AddGripDistance(JsonObject row)
    {
        if(row["authoredGrip"] is not JsonObject grip)return;
        var point=new Vector2(grip["x"]!.GetValue<float>(),grip["y"]!.GetValue<float>());var delta=point-RenderedFrontHand();
        row["gripMinusGameplayFrontHand"]=WNativeVisualGeometry.Point(point-FrontHand());row["gripMinusRenderedFrontHand"]=WNativeVisualGeometry.Point(delta);row["gripDistancePx"]=owner.compositeFrontArm.enabled?delta.Length():null;row["diagnosticFrameArmGetterDistancePx"]=owner.compositeFrontArm.enabled?null:delta.Length();row["gripDistanceStatus"]=owner.compositeFrontArm.enabled?"measured_composite_hand":"not_authoritative_frame_arm: inspect native proxy and pixels";row["compositeHandAuthoritative"]=owner.compositeFrontArm.enabled;
    }
    void RecordHeldGeometry(DrawData entry)
    {
        var selected=SpritePresentation.Root(reviewData);Vector2? grip=selected.Grip is {} g?new Vector2((float)g.NormalizedX,(float)g.NormalizedY):null;
        var row=WNativeVisualGeometry.Describe(entry.texture,entry.position,entry.sourceRect,entry.color,entry.rotation,entry.origin,entry.scale,entry.effect,grip);
        row["kind"]="root_held_item";row["transformStage"]=nativePlayer?"DrawPlayer_RenderAllLayers: after native DrawPlayer_TransformDrawData":"partial held layer: no full player transform";AddGripDistance(row);Frame["heldGeometry"]!.AsArray().Add(row);
    }
    void EnableVisualObserver()
    {
        visualObserver=new Hook(typeof(GeneratedProjectile).GetMethod("DrawAuthoredEntityVisual",All)!,
            (VisualObserve)((orig,self,color)=>{
                var entity=(RuntimeEntitySpec?)typeof(GeneratedProjectile).GetField("_entity",All)!.GetValue(self);
                if(entity is null){orig(self,color);return;}
                var selected=SpritePresentation.Entity(reviewData,entity);Vector2? grip=selected.Grip is {} g?new Vector2((float)g.NormalizedX,(float)g.NormalizedY):null;
                var rows=WNativeVisualGeometry.Capture(()=>orig(self,color),grip);
                foreach(var node in rows){var row=node!.AsObject();row["kind"]="projectile";row["entityId"]=entity.Id;row["nativeSlot"]=self.Projectile.whoAmI;row["heldByNativePlayer"]=self.Projectile.whoAmI==owner.heldProj;row["frontHandAttachment"]=self.HasFrontHandAttachment;row["collider"]=WNativeVisualGeometry.Rect(self.Projectile.Hitbox);row["gfxOffY"]=self.Projectile.gfxOffY;row["attachmentOffset"]=WNativeVisualGeometry.Point(self.FrontHandAttachmentOffset);AddGripDistance(row);Frame["projectileGeometry"]!.AsArray().Add(row.DeepClone());}
            }));
    }
    public void DrawDroppedItems()
    {
        Main.spriteBatch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,Main.Rasterizer,null,Main.GameViewMatrix.TransformationMatrix);
        try{foreach(var item in Main.item.Where(i=>i is {active:true,stack:>0} && i.ModItem is GeneratedItem)){
            float rotation=0,scale=item.scale;bool fallback=false;
            var draws=WNativeVisualGeometry.Capture(()=>fallback=item.ModItem!.PreDrawInWorld(Main.spriteBatch,Color.White,Color.White,ref rotation,ref scale,item.whoAmI),supportY:item.Bottom.Y);
            if(fallback)throw new InvalidOperationException("Dropped generated item requested native fallback; artwork evidence unavailable");
            Frame["droppedItems"]!.AsArray().Add(new JsonObject{["authoredDrawOffset"]=WNativeVisualGeometry.Point(new Vector2(((GeneratedItem)item.ModItem).Data.Visual.DrawOffsetX,((GeneratedItem)item.ModItem).Data.Visual.DrawOffsetY)),["slot"]=item.whoAmI,["collider"]=WNativeVisualGeometry.Rect(item.Hitbox),["velocity"]=WNativeVisualGeometry.Point(item.velocity),["entrypoint"]="GeneratedItem.PreDrawInWorld",["lightingScope"]="Explicit zero rotation and neutral white diagnostic light, not complete Main.DrawItem treatment",["physicsScope"]="Drawn pose is before this tick world update; snapshot.world is after it. See droppedItemUpdateScope for explicit Item.UpdateItem execution or notRun; do not equate same-tick draw/snapshot positions",["supportScope"]="Collider bottom reference, not detected terrain contact",["draws"]=draws});
        }}finally{Main.spriteBatch.End();}
    }
}
