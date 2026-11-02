using System;
using System.IO;
using System.Collections;
using InfiniCrafterLocal.Common.Services;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Canonical packet/state controls. No socket, invented animation or pending geometry.
    private static void HeldHistoryRemotePendingOrdering()
    {
        using var actors=new NativeActorState();
        const BindingFlags statics=BindingFlags.Static|BindingFlags.NonPublic;
        var owner=typeof(InfiniItemVfxRuntime);
        var histories=(Array)owner.GetField("ItemHistories",statics)!.GetValue(null)!;
        bool HasHistory()=>histories.GetValue(0) is not null;
        int world=Terraria.Main.worldID;
        var clock=typeof(Terraria.Main).GetField("_gameUpdateCount",statics)!;
        try {
            Terraria.Main.worldID=17;Terraria.Main.netMode=NetmodeID.MultiplayerClient;Terraria.Main.myPlayer=1;Terraria.Main.dedServ=false;clock.SetValue(null,100u);
            var player=new Player{active=true,whoAmI=0,itemAnimation=0,direction=1};Terraria.Main.player[0]=player;
            var data=GeneratedItemData.Placeholder();data.Id="ordering-diagnostic";data.RecipeMeta.WorldScoped=true;data.RecipeMeta.WorldId="17";
            data.Visual.SpritePath="ordering-test.png";data.Visual.RenderSizePx=32;data.Visual.ForwardAngleDegrees=0;
            data.RuntimeProgram.ItemUse.HideUseGraphic=false;
            data.VfxManifest.Slots=new[]{new VfxSlotSpec{Id="history",EntityId=data.RuntimeProgram.ItemEntityId,Event="on_use",RendererKind="historyTrail",Layer="AfterPlayer",Blend="alpha",Anchor="self",Trail=ExplicitTrail()}};
            var item=new Item{type=1,stack=1,useStyle=ItemUseStyleID.Swing};var generated=AttachItem(new GeneratedItem(),item,data);player.inventory[0]=item;
            byte[] EventPacket(ulong occurrence=1,long? token=null) {
                var type=owner.GetNestedType("MaterialItemEvent",BindingFlags.NonPublic)!;
                object payload=Activator.CreateInstance(type,new object[]{0,token??generated.PresentationToken,occurrence,data.Id,data.RuntimeProgram.ItemEntityId,"on_use",player.Center,InfiniItemVfxSnapshot.Capture(player)})!;
                using var stream=new MemoryStream();using var writer=new BinaryWriter(stream);
                owner.GetMethod("WriteMaterialItemEvent",statics)!.Invoke(null,new object[]{writer,payload});return stream.ToArray();
            }
            void Event(ulong occurrence=1,long? token=null){using var reader=new BinaryReader(new MemoryStream(EventPacket(occurrence,token)));InfiniItemVfxRuntime.HandleUseEventPacket(reader,0);}
            void Reset(){InfiniItemVfxRuntime.ClearUseEventCaches();clock.SetValue(null,100u);player.itemAnimation=0;player.selectedItem=0;player.dead=false;}
            bool Visible()=>GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(new Terraria.DataStructures.PlayerDrawSet{drawPlayer=player,heldItem=player.HeldItem},out _);
            object State()=>histories.GetValue(0)!;
            int SampleSlots()=>((IDictionary)State().GetType().GetField("Samples",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!).Count;
            ulong UseTick()=>(ulong)State().GetType().GetField("UseTick",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(State())!;
            void Pending(){Equal(true,HasHistory(),"pending exact source remains");Equal(0,SampleSlots(),"pending source has no fabricated history");}
            void CaptureDrawData() {
                var texture=CpuTexture(2,3);
                var body=new Terraria.DataStructures.DrawData(texture,Vector2.Zero,null,Microsoft.Xna.Framework.Color.White,0,Vector2.Zero,1,Microsoft.Xna.Framework.Graphics.SpriteEffects.None,0);
                owner.GetMethod("CaptureHeldHistory",statics)!.Invoke(null,new object[]{State(),body});
                Equal(1,SampleSlots(),"first actual DrawData seam creates first captured history");
            }
            // Pure state-seam controls: positive animation is explicitly supplied here.
            // Full remote native ItemCheck initiation is tested separately by HeldProxy.
            Reset();player.itemAnimation=20;Event();InfiniItemVfxRuntime.PruneHeldHistory();Equal(true,Visible(),"native animation-first visible");Pending();
            Reset();Event();InfiniItemVfxRuntime.PruneHeldHistory();Pending();Equal(false,Visible(),"event alone cannot invent animation");
            var emptyDraw=new Terraria.DataStructures.PlayerDrawSet{drawPlayer=player,heldItem=player.HeldItem,DrawDataCache=new System.Collections.Generic.List<Terraria.DataStructures.DrawData>()};
            InfiniItemVfxRuntime.RegisterHeldHistoryDraw(ref emptyDraw,default);Pending();
            clock.SetValue(null,101u);player.itemAnimation=20;InfiniItemVfxRuntime.PruneHeldHistory();Pending();CaptureDrawData();
            clock.SetValue(null,155u);InfiniItemVfxRuntime.PruneHeldHistory();Equal(true,HasHistory(),"after capture actual native source owns lifetime");
            player.itemAnimation=0;InfiniItemVfxRuntime.PruneHeldHistory();Equal(false,HasHistory(),"native use end clears captured history");
            foreach(uint age in new uint[]{53,54,55}) {
                Reset();Event();clock.SetValue(null,100+age);player.itemAnimation=20;InfiniItemVfxRuntime.PruneHeldHistory();
                Equal(age<=54,HasHistory(),"bounded pending deadline age"+age);
            }
            Reset();Event();clock.SetValue(null,155u);InfiniItemVfxRuntime.PruneHeldHistory();Equal(false,HasHistory(),"unobserved use expires");
            player.itemAnimation=20;InfiniItemVfxRuntime.PruneHeldHistory();Equal(false,HasHistory(),"later animation cannot revive an expired use");
            Reset();Event();object first=State();clock.SetValue(null,102u);Event();Equal(true,ReferenceEquals(first,State()),"same accepted occurrence cannot refresh pending");
            Event(2,generated.PresentationToken+1);Equal(true,ReferenceEquals(first,State()),"wrong token cannot reset pending");
            clock.SetValue(null,103u);Event(3);object newest=State();Equal(false,ReferenceEquals(first,newest),"new accepted use replaces pending");Equal(103UL,UseTick(),"new use starts own bounded wait");
            clock.SetValue(null,104u);Event(1);Equal(true,ReferenceEquals(newest,State()),"already-seen old use cannot replace newer use");
            foreach(string retirement in new[]{"switch","death","rewind","teleport","unload"}) {
                Reset();Event();
                if(retirement=="switch")player.selectedItem=1;
                if(retirement=="death")player.dead=true;
                if(retirement=="rewind")clock.SetValue(null,99u);
                if(retirement=="teleport") {
                    int calls=0;On_Player.orig_Teleport original=(Player p,Vector2 v,int style,int extra)=>calls++;
                    owner.GetMethod("TeleportHistory",statics)!.Invoke(null,new object[]{original,player,Vector2.Zero,0,0});Equal(1,calls,"teleport original preserved");
                }
                if(retirement=="unload")InfiniItemVfxRuntime.UnloadItemHistory();
                InfiniItemVfxRuntime.PruneHeldHistory();Equal(false,HasHistory(),"pending retired: "+retirement);
            }
            Reset();player.itemAnimation=20;Event();InfiniItemVfxRuntime.PruneHeldHistory();
            Equal(true,HasHistory(),"native visible exact source owns history");
            var revised=GeneratedItemData.Placeholder();revised.Id=data.Id;revised.Visual=data.Visual;
            AttachItem(generated,item,revised);InfiniItemVfxRuntime.PruneHeldHistory();
            Equal(false,HasHistory(),"same-ID actual Data replacement clears without rebinding");AttachItem(generated,item,data);
            Reset();
        } finally {Terraria.Main.worldID=world;InfiniItemVfxRuntime.ClearUseEventCaches();}
    }
}
