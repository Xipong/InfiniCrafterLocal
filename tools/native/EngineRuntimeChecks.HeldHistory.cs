using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;

internal static partial class EngineRuntimeChecks
{
    private static void HeldHistoryFinalPoseAndFences()
    {
        using var actors=new NativeActorState();
        WithVfxGeometryQueue((batch,pixel,count,vertices,colors)=>{
            var savedPixel=Terraria.GameContent.TextureAssets.MagicPixel;
            try { Terraria.GameContent.TextureAssets.MagicPixel=CpuTextureAsset(pixel);
            const BindingFlags flags=BindingFlags.Static|BindingFlags.NonPublic;
            var owner=typeof(InfiniItemVfxRuntime);
            void Call(string name,params object?[] args)=>owner.GetMethod(name,flags)!.Invoke(null,args);
            Array States()=>(Array)owner.GetField("ItemHistories",flags)!.GetValue(null)!;
            object? State()=>States().GetValue(0);
            var player=new Player{active=true,whoAmI=0,itemAnimation=20};Terraria.Main.player[0]=player;Terraria.Main.dedServ=false;
            var data=GeneratedItemData.Placeholder();data.Visual.ForwardAngleDegrees=0;data.Visual.RenderSizePx=32;data.Visual.SpritePath="history-test.png";
            data.RuntimeProgram.ItemUse.HideUseGraphic=false;
            data.RuntimeProgram.ItemUse.Configured=true;data.RuntimeProgram.ItemUse.UseStyle="hold_up";data.Gameplay.UseStyleName="hold_up";
            data.RuntimeProgram.Bindings=new[]{new RuntimeBindingSpec{Id="history_use",Input=RuntimeInputKind.PrimaryUse,Role=RuntimeEntityRole.Primary,
                UsePolicy=new RuntimeBindingUsePolicySpec{Action=new RuntimeBindingActionSpec{Kind=RuntimeBindingAction.UseItemBody,TargetId=data.RuntimeProgram.ItemEntityId}}}};
            var trail=ExplicitTrail();trail.Source="tip";
            data.VfxManifest.Slots=new[]{new VfxSlotSpec{Id="held",EntityId=data.RuntimeProgram.ItemEntityId,Event="on_use",RendererKind="historyTrail",Layer="AfterPlayer",Blend="alpha",Anchor="self",Trail=trail}};
            var item=new Item{type=1,stack=1,useStyle=1};AttachItem(new GeneratedItem(),item,data);player.inventory[0]=item;
            void Begin()=>Call("BeginHeldHistory",player,data,data.RuntimeProgram.ItemEntityId);
            InfiniItemVfxRuntime.ClearUseEventCaches();Begin();Equal(true,State() is not null,"exact held on_use admits history");
            var draw=new DrawData(pixel,new Vector2(50,70),new Rectangle(0,0,20,10),Color.White,.7f,new Vector2(3,7),Vector2.One,SpriteEffects.None,0);
            draw.scale=new Vector2(2,3);Terraria.Main.screenPosition=new Vector2(100,200);
            foreach(var flip in new[]{SpriteEffects.None,SpriteEffects.FlipHorizontally,SpriteEffects.FlipVertically,SpriteEffects.FlipHorizontally|SpriteEffects.FlipVertically}) {
                draw.effect=flip;Vector2 local=new(20,5),mirrored=local;
                if((flip&SpriteEffects.FlipHorizontally)!=0)mirrored.X=0;
                if((flip&SpriteEffects.FlipVertically)!=0)mirrored.Y=5;
                Vector2 expected=draw.position+((mirrored-draw.origin)*draw.scale).RotatedBy(draw.rotation)+Terraria.Main.screenPosition;
                AssertVfxNear(expected,InfiniItemVfxRuntime.HeldHistoryPoint(draw,local),"final native scale/rotation/pivot/camera/flip captured");
            }
            var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",BindingFlags.Static|BindingFlags.NonPublic)!;
            var capture=owner.GetMethod("CaptureHeldHistory",flags)!;
            IList Samples()=>(IList)((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!)["held"]!;
            for(uint tick=1;tick<=40;tick++) {clock.SetValue(null,tick);capture.Invoke(null,new object[]{State()!,draw});capture.Invoke(null,new object[]{State()!,draw});}
            Equal(32,Samples().Count,"one sample per tick,32 retained despite duplicate draws");
            Begin();
            var set=new PlayerDrawSet{drawPlayer=player,heldItem=player.HeldItem,shadow=1,DrawDataCache=new List<DrawData>{draw}};
            InfiniItemVfxRuntime.RegisterHeldHistoryDraw(ref set,draw);
            object? Registered()=>State()!.GetType().GetField("Cache",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State());
            Equal(true,Registered() is null,"shadow does not register a live source");
            int bodyDraws=0;
            On_PlayerDrawLayers.orig_DrawPlayer_RenderAllLayers bodyOriginal=(ref PlayerDrawSet ignored)=>bodyDraws++;
            set.shadow=0;
            Call("DrawHeldHistory",bodyOriginal,set);
            Equal(1,bodyDraws,"missing registration preserves original player rendering");
            Equal(0,((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count,"missing draw never fabricates history");
            InfiniItemVfxRuntime.RegisterHeldHistoryDraw(ref set,draw);
            clock.SetValue(null,41u);Call("DrawHeldHistory",bodyOriginal,set);
            Equal(2,bodyDraws,"stale registration preserves original player renderer");
            Equal(0,((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count,"prior-tick reused cache cannot invent a current draw");
            draw.color=Color.Transparent;set.DrawDataCache[0]=draw;
            InfiniItemVfxRuntime.RegisterHeldHistoryDraw(ref set,draw);InfiniItemVfxRuntime.ResolveHeldHistoryDraw(ref set);Call("DrawHeldHistory",bodyOriginal,set);
            Equal(true,Registered() is null,"registration consumed exactly once even for invisible source");
            Equal(0,((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count,"transparent body adds no history");
            // Full pre-transform semantic witness, not texture/index coincidence.
            draw.color=Color.White;
            foreach(string mutation in new[]{"normal","insert","same_texture_other_pose","duplicate","removed","changed"}) {
                Begin();set.DrawDataCache=new List<DrawData>();
                InfiniItemVfxRuntime.RegisterHeldHistoryDraw(ref set,draw);
                var other=draw;other.position+=new Vector2(4,9);
                if(mutation is "insert" or "same_texture_other_pose")set.DrawDataCache.Add(other);
                if(mutation!="removed")set.DrawDataCache.Add(mutation=="changed"?other:draw);
                if(mutation=="duplicate")set.DrawDataCache.Add(draw);
                InfiniItemVfxRuntime.ResolveHeldHistoryDraw(ref set);
                Equal(0,((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count,"resolving only proves membership, never creates history");
                Call("DrawHeldHistory",bodyOriginal,set);
                bool expected=mutation is "normal" or "insert" or "same_texture_other_pose";
                Equal(expected?1:0,((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count,"pre-transform witness "+mutation);
            }
            // Only the exact immediate native clone source may contribute to this accepted use history.
            var oldClone=item.Clone();
            int CaptureClone(Item native)
            {
                Begin();set.heldItem=native;set.DrawDataCache=new List<DrawData>{draw};
                InfiniItemVfxRuntime.RegisterHeldHistoryDraw(ref set,draw);
                InfiniItemVfxRuntime.ResolveHeldHistoryDraw(ref set);Call("DrawHeldHistory",bodyOriginal,set);
                return ((IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count;
            }
            Equal(1,CaptureClone(oldClone),"fresh native clone captures actual draw for its source use");
            var twiceClone=oldClone.Clone();
            Equal(0,CaptureClone(twiceClone),"clone-of-clone cannot borrow ancestor history ownership");
            var replacement=data.CloneForItemInstance();replacement.Visual.RenderSizePx=48;
            var install=typeof(GeneratedItem).GetMethod("SetData",BindingFlags.Instance|BindingFlags.NonPublic,null,
                new[]{typeof(GeneratedItemData),typeof(bool),typeof(bool),typeof(bool)},null)!;
            install.Invoke(item.ModItem,new object[]{replacement,false,false,false});data=replacement;
            Equal(0,CaptureClone(oldClone),"stale same-ID clone cannot sample a new definition's use history");
            var freshClone=item.Clone();
            Equal(1,CaptureClone(freshClone),"new native clone captures new accepted definition history");
            install.Invoke(freshClone.ModItem,new object[]{((GeneratedItem)freshClone.ModItem).Data.CloneForItemInstance(),false,false,false});
            Equal(0,CaptureClone(freshClone),"SetData-cleared provenance cannot authorize prior source history");
            set.heldItem=item;Begin();

            int teleports=0;
            On_Player.orig_Teleport teleportOriginal=(Player p,Vector2 destination,int style,int extra)=>{
                Equal(true,State() is null,"teleport clears history before original executes");
                Equal(new Vector2(300,400),destination,"teleport destination preserved");Equal(2,style,"teleport style preserved");Equal(7,extra,"teleport extra info preserved");teleports++;
            };
            Call("TeleportHistory",teleportOriginal,player,new Vector2(300,400),2,7);
            Equal(1,teleports,"teleport original called exactly once");Begin();
            object first=State()!;Begin();Equal(false,ReferenceEquals(first,State()),"each real use occurrence starts fresh history");
            var empty=(IDictionary)State()!.GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!;
            Equal(0,empty.Count,"no preceding use history carried over");
            player.selectedItem=1;InfiniItemVfxRuntime.PruneHeldHistory();Equal(true,State() is null,"switch clears without drawing");
            player.selectedItem=0;Begin();player.dead=true;InfiniItemVfxRuntime.PruneHeldHistory();Equal(true,State() is null,"death clears without drawing");
            player.dead=false;Begin();player.itemAnimation=0;InfiniItemVfxRuntime.PruneHeldHistory();Equal(true,State() is null,"ended use clears");
            player.itemAnimation=20;Begin();data.Id+="changed";typeof(GeneratedItem).GetMethod("ApplyPresentationToken",BindingFlags.Instance|BindingFlags.NonPublic)!.Invoke(item.ModItem,new object[]{99L});
            InfiniItemVfxRuntime.PruneHeldHistory();Equal(true,State() is null,"identity generation fences samples");
            Terraria.Main.myPlayer=1;Terraria.Main.netMode=Terraria.ID.NetmodeID.MultiplayerClient;
            player.itemAnimation=20;Begin();InfiniItemVfxRuntime.PruneHeldHistory();
            Equal(true,State() is not null,"actual native remote animation owns visibility");
            player.itemAnimation=0;clock.SetValue(null,500u);InfiniItemVfxRuntime.PruneHeldHistory();
            Equal(true,State() is null,"unobserved remote use expires rather than inventing animation");
            Terraria.Main.myPlayer=0;Terraria.Main.netMode=Terraria.ID.NetmodeID.SinglePlayer;player.itemAnimation=20;Begin();
            Equal(true,State() is not null,"active history exists before unload");InfiniItemVfxRuntime.UnloadItemHistory();
            Equal(true,State() is null,"unload clears all held history");
            InfiniItemVfxRuntime.ClearUseEventCaches();
            } finally { Terraria.GameContent.TextureAssets.MagicPixel=savedPixel; }
        });
    }
}
