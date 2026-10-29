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
            AssertVfxNear(hand,GeneratedHeldItemDrawLayer.NativeGripLocation(owner,null,owner.itemLocation),
                "root native contact correction does not move projectile body or redefine reach");
        });
    }

    private static void HeldContactProjectionAndPacketAgree()
    {
        WithPlayer((player, _) => {
            var item = new Item { type = ItemID.WoodenSword, stack = 1, useStyle = ItemUseStyleID.Swing };
            var data = GeneratedItemData.Placeholder(); data.Id = "synthetic-contact";
            player.position = new Vector2(121,239); player.itemLocation = new Vector2(130,244);
            player.selectedItem = 0; player.inventory[0] = item;
            const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
            var build = typeof(GeneratedHeldItemDrawLayer).GetMethod("BuildLocalPayload",flags)!;
            var write = typeof(GeneratedHeldItemDrawLayer).GetMethod("WriteHeldItemPresentationPayload",flags)!;
            var read = typeof(GeneratedHeldItemDrawLayer).GetMethod("ReadHeldItemPresentationPayload",flags)!;
            foreach (int direction in new[] { -1, 1 }) foreach (float gravity in new[] { -1f, 1f })
            foreach (float rotation in new[] { -.9f, 0f, .8f })
            {
                player.direction = direction; player.gravDir = gravity;
                player.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, rotation);
                Vector2 hand = player.GetFrontHandPosition(player.compositeFrontArm.stretch,player.compositeFrontArm.rotation);
                Vector2 shift = new(7,-11);
                AssertVfxNear(hand+shift,GeneratedHeldItemDrawLayer.NativeGripLocation(player,item,player.itemLocation+shift),
                    "composite native hand keeps facing/gravity and draw-set shift");
                foreach (float fullRotation in new[] { -.6f, .4f })
                {
                    player.fullRotation=fullRotation;
                    // Match the installed native RotatedRelativePoint mount pivot:
                    // bottom minus half native mount offset and the four-pixel foot inset.
                    player.fullRotationOrigin=new Vector2(player.width*.5f,player.height-player.mount.PlayerOffset/2-4);
                    var draw=new PlayerDrawSet { drawPlayer=player, Position=player.position+shift,
                        rotation=fullRotation, rotationOrigin=player.fullRotationOrigin,
                        DustCache=new List<int>(), GoreCache=new List<int>(), DrawDataCache=new List<DrawData> {
                            new DrawData(null!,hand+shift-Terraria.Main.screenPosition,null,Color.White,0,Vector2.Zero,1,SpriteEffects.None,0)
                        }};
                    PlayerDrawLayers.DrawPlayer_TransformDrawData(ref draw);
                    AssertVfxNear(player.RotatedRelativePoint(hand,addGfxOffY:false)+shift-Terraria.Main.screenPosition,
                        draw.DrawDataCache[0].position,"native later transform applies full player rotation exactly once");
                }
                player.fullRotation=0;
                object payload = build.Invoke(null,new object[] {player,item,data,true})!;
                using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream);
                write.Invoke(null,new object[] {writer,payload}); stream.Position=0;
                using var reader = new BinaryReader(stream);
                object decoded = read.Invoke(null,new object[] {reader})!;
                float Field(string name) => (float)decoded.GetType().GetField(name)!.GetValue(decoded)!;
                AssertVfxNear(hand,player.position+new Vector2(Field("ItemLocationX"),Field("ItemLocationY")),
                    "remote contact is owner-relative, preserving native facing/gravity without world pinning");
                stream.Position=0; writer.Write(5); stream.Position=0;
                bool rejected=false;
                try { read.Invoke(null,new object[] {reader}); }
                catch(TargetInvocationException e) when(e.InnerException is InvalidDataException) { rejected=true; }
                Equal(true,rejected,"old world-contact packet cannot be interpreted as owner-relative data");
            }
            player.compositeFrontArm.enabled=false;
            AssertVfxNear(player.itemLocation,GeneratedHeldItemDrawLayer.NativeGripLocation(player,item,player.itemLocation),
                "ordinary swing/mining native pivot is unchanged");
        });
    }
}
