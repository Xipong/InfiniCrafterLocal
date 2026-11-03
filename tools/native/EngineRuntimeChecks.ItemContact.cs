using System;
using System.IO;
using System.Reflection;
using System.Collections.Generic;
using Microsoft.Xna.Framework.Graphics;
using Terraria.DataStructures;
using InfiniCrafterLocal.Content.Projectiles;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void HeldNativeOwnerRejectsRemovedPoseControls()
    {
        var data=RootCombatFixture(20,2,"ranged");
        var baseline=System.Text.Json.Nodes.JsonNode.Parse(data.ToJson())!;
        foreach(string field in new[]{"heldAlignment","releaseTiming"})
        foreach(string value in new[]{"null","false","1","{}","[]","\"grip\"","\"native_frame\""}) {
            var wire=baseline.DeepClone();wire["runtimeProgram"]!["itemUse"]![field]=System.Text.Json.Nodes.JsonNode.Parse(value);
            Equal(true,GeneratedItemData.FromJson(wire.ToJsonString()) is null,"removed pose control cannot silently select a native pose: "+field);
        }
        Equal(true,GeneratedItemData.FromJson(baseline.ToJsonString()) is not null,"ordinary native-owner DTO remains accepted");
    }

    private static void DroppedAlphaSupportTracksActualRotatedPixels()
    {
        const int width = 19, height = 23;
        var pixels = new Color[width * height];
        // Asymmetric sparse L, including alpha=1: rotating its bounding rectangle
        // would invent opaque corners and leave a visible gap at several angles.
        for (int y = 3; y < 17; y++) pixels[y * width + 4] = Color.White;
        for (int x = 4; x < 13; x++) pixels[16 * width + x] = Color.White;
        pixels[9 * width + 10] = new Color(1, 1, 1, 1);
        Vector2[] hull = SpritePresentation.MeasureAlphaHull(pixels, width, height);
        Equal(true, hull.Length < height * 4, "support is cached hull, not retained source pixels");
        Vector2 origin = new(width / 2f, height / 2f), bottom = new(103, 217);
        foreach (float angle in new[] { 0f, .37f, MathHelper.PiOver2, 2.2f, MathHelper.Pi, -1.1f })
        foreach (float scale in new[] { .25f, 1f, 2.5f })
        {
            Vector2 position = SpritePresentation.DroppedBodyPosition(bottom, origin, angle, scale, hull);
            float minX = float.PositiveInfinity, maxX = float.NegativeInfinity, maxY = float.NegativeInfinity;
            for (int y = 0; y < height; y++) for (int x = 0; x < width; x++)
            {
                if (pixels[y * width + x].A == 0) continue;
                foreach (Vector2 corner in new[] { new Vector2(x,y), new Vector2(x+1,y), new Vector2(x,y+1), new Vector2(x+1,y+1) })
                {
                    Vector2 point = position + ((corner-origin)*scale).RotatedBy(angle);
                    minX = Math.Min(minX, point.X); maxX = Math.Max(maxX, point.X); maxY = Math.Max(maxY, point.Y);
                }
            }
            AssertVfxNear(bottom, new Vector2((minX+maxX)*.5f,maxY), "actual alpha support is centered and touches native bottom at any angle/scale");
        }
        Equal(0, SpritePresentation.MeasureAlphaHull(new Color[4], 2, 2).Length, "empty alpha does not invent support");
        var full = new[] { Color.White, Color.White, Color.White, Color.White };
        AssertVfxNear(bottom-new Vector2(0,2), SpritePresentation.DroppedBodyPosition(bottom,new Vector2(1),0,2,
            SpritePresentation.MeasureAlphaHull(full,2,2)), "unrotated opaque frame keeps historical bottom anchor");
    }


    private static void HeldContactCorrectionDoesNotCancelAuthoredReach()
    {
        WithPlayer((owner, _) => {
            using var actors=new NativeActorState(); owner.direction=1; owner.active=true;
            owner.itemAnimation=owner.itemAnimationMax=60;
            var data=MotionDefinition("""
                {"aim":{"source":"initial","turnOwner":false},
                 "attachment":{"anchor":"front_hand","axisOffsetPx":8,"normalOffsetPx":0},
                 "armPose":{"durationTicks":20,"startStretch":"quarter","peakStretch":"full","endStretch":"quarter","peakProgress":0.4},
                 "reach":{"durationTicks":20,"startOffsetPx":0,"peakOffsetPx":32,"endOffsetPx":0,"peakProgress":0.4}}
                """);
            var (host,body)=MotionActor(data,owner,Vector2.Zero);
            for(int i=0;i<8;i++) host.AI();
            Vector2 hand=owner.GetFrontHandPosition(owner.compositeFrontArm.stretch,owner.compositeFrontArm.rotation);
            AssertVfxNear(hand+new Vector2(40,0),body.Center,"authored peak reach32 plus static attachment8 remains physical");
            var entity=data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            var selected=new SpritePresentationSelection("synthetic",64,0,new ItemGripSpec { NormalizedX=.1875,NormalizedY=.5 });
            Vector2 origin=GeneratedProjectile.MotionSpriteOrigin(entity,selected,64,64,1,SpriteEffects.None,0,Vector2.UnitX);
            Vector2 displayedGrip=body.Center+new Vector2(12,32)-origin;
            AssertVfxNear(hand+new Vector2(32,0),displayedGrip,"sprite projection cancels static offset only, never author's reach");
        });
    }

}
