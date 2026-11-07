using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{


    private static void VisibleVanityCannotEmitWorldLight()
    {
        WithLighting((config, lights) => WithPlayer((player, _) => {
            using var actors = new NativeActorState();
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("ShapeEmissions", BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
            try {
                Terraria.Main.player[0]=player;player.whoAmI=0;player.active=true;player.dead=false;
                player.Center=new Vector2(160);config.PresentationLightMultiplier=1;
                foreach(bool armor in new[]{false,true}) {
                    system.OnWorldUnload();lights.Clear();MaterialClock(100);
                    for(int i=0;i<player.armor.Length;i++)player.armor[i]=new Item();
                    var data=GeneratedItemData.Placeholder();string entity=data.RuntimeProgram.ItemEntityId;
                    data.Accessory.Enabled=!armor;data.Accessory.LightStrength=.8f;data.Accessory.LightColorName="cyan";
                    data.Armor.Enabled=armor;data.Armor.Slot="head";data.Armor.LightStrength=.8f;data.Armor.LightColorName="cyan";
                    data.RuntimeProgram.Bindings=new[]{new RuntimeBindingSpec{Id="equip",Input=RuntimeInputKind.Equipped,
                        UsePolicy=new(){Action=new(){Kind=RuntimeBindingAction.EquipPassive,TargetId=entity}}}};
                    var shape=ExplicitShapeSlot();shape.EntityId=entity;shape.Event="periodic";shape.RepeatEvery=1;
                    data.VfxManifest.Slots=new[]{shape,LightManifest(entity,"periodic").Slots[0]};
                    var item=new Item{type=ItemID.Wood,stack=1,accessory=!armor,headSlot=armor?1:-1};
                    var generated=AttachItem(new GeneratedItem(),item,data);
                    int cosmetic=armor?10:13,functional=armor?0:3;player.armor[cosmetic]=item;
                    InfiniCrafterLocal.Common.Players.GeneratedEquipOverlayDrawLayerBase.EmitVisibleEquipmentVfx(player);
                    system.PostUpdateEverything();
                    Equal(0,lights.Count,"vanity never emits world illumination");Equal(1,queue.Count,"vanity retains current cosmetic shape");
                    MaterialClock(101);player.armor[cosmetic]=new Item();player.armor[functional]=item;
                    if(armor)generated.UpdateEquip(player);else generated.UpdateAccessory(player,false);
                    InfiniCrafterLocal.Common.Players.GeneratedEquipOverlayDrawLayerBase.EmitVisibleEquipmentVfx(player);
                    system.PostUpdateEverything();
                    Equal(2,lights.Count,"functional equipment owns gameplay and explicit native light");
                    Equal(2,queue.Count,"one new current shape per tick across functional and visible hooks");
                }
            } finally {system.OnWorldUnload();}
        }));
    }


    // Real held/equip hooks and visible-equipment entry point; CPU queues only.
    private static void ItemPeriodicPresentationHasOneWorldTickOwner()
    {
        WithLighting((config, lights) => WithPlayer((player, _) => {
            using var actors=new NativeActorState();var system=new InfiniDetachedVfxSystem();
            var queue=(System.Collections.IList)typeof(InfiniDetachedVfxSystem).GetField("ShapeEmissions",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
            try {
                system.OnWorldUnload();MaterialClock(100);player.active=true;player.dead=false;player.whoAmI=0;Terraria.Main.player[0]=player;
                player.Center=new Vector2(160);player.itemLocation=Vector2.Zero;player.selectedItem=0;
                var data=GeneratedItemData.Placeholder();string entity=data.RuntimeProgram.ItemEntityId;
                var shape=ExplicitShapeSlot();shape.EntityId=entity;shape.Event="periodic";shape.Anchor="tip";shape.RepeatEvery=1;shape.Duration=20;
                data.VfxManifest.Slots=new[]{shape,LightManifest(entity,"periodic").Slots[0]};
                var item=new Item{type=ItemID.Wood,stack=1};var generated=AttachItem(new GeneratedItem(),item,data);player.inventory[0]=item;
                void Hooks(){generated.HoldItem(player);generated.HoldItem(player);InfiniItemVfxRuntime.OnVisibleEquipment(player,data);system.PostUpdateEverything();}
                Hooks();Equal(1,queue.Count,"duplicate hooks produce one shape per slot/tick");Equal(1,lights.Count,"duplicate hooks produce one native light");
                Hooks();Equal(1,queue.Count,"same-tick update cannot duplicate shape");Equal(1,lights.Count,"same-tick light cannot duplicate");
                var first=queue[0]!;var frame=(VfxSourceFrame)first.GetType().GetField("Frame",TestInstance)!.GetValue(first)!;
                Equal(Vector2.Zero,frame.Position,"world zero is a valid frozen anchor");
                MaterialClock(101);player.itemLocation=new Vector2(180);Hooks();Equal(2,queue.Count,"next tick retains explicit lifetime overlap");
                Equal(frame,(VfxSourceFrame)first.GetType().GetField("Frame",TestInstance)!.GetValue(first)!,"world snapshot remains frozen");
                shape.Event="on_hit";shape.RepeatEvery=0;
                InfiniItemVfxRuntime.EmitAndSyncEvent(player,data,entity,"on_hit");InfiniItemVfxRuntime.EmitAndSyncEvent(player,data,entity,"on_hit");
                Equal(4,queue.Count,"two actual hit occurrences are not periodic duplicates");
                player.dead=true;MaterialClock(122);system.PostUpdateEverything();Equal(0,queue.Count,"dead source stops periodic emission and bounded worlds expire");
            } finally {system.OnWorldUnload();}
        }));
    }


    private static void ItemOutgoingVfxRejectsNonfinitePoint()
    {
        // Native inventory publication is independently exercised by FirstHeldItemEventPublishesTokenBeforeClaim.
        // This socket-free fixture observes the event stream, not Terraria socket buffers.
        using var equipmentPublication = PersistenceObserveNetworkSend((_, __) => { });
        WithLighting((config, lights) =>
        {
            var instance = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Instance")!;
            object? oldInstance = instance.GetValue(null);
            int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
            int reached = 0;
            Func<Mod, int, ModPacket> observe = (mod, capacity) =>
            {
                reached++;
                throw new InvalidOperationException("observed real packet allocation boundary");
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(Mod).GetMethod("GetPacket")!, observe);
            try
            {
                instance.SetValue(null, System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod)));
                Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 4;
                var player = new Player { active = true, whoAmI = 4 };
                var data = GeneratedItemData.Placeholder();
                data.VfxManifest = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnUse);
                var generated = new GeneratedItem();
                var item = new Item { type = ItemID.Wood, stack = 1 };
                AttachItem(generated, item, data);
                player.inventory[0] = item;
                foreach (bool explicitPoint in new[] { false, true })
                foreach (Vector2 point in new[] { new Vector2(float.NaN, 160), new Vector2(160, float.PositiveInfinity),
                    new Vector2(float.NegativeInfinity, 160), Vector2.Zero })
                {
                    player.Center = explicitPoint ? new Vector2(160f) : point;
                    reached = 0;
                    try { InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, data.RuntimeProgram.ItemEntityId,
                        RuntimeEventKind.OnUse, explicitPoint ? point : null); }
                    catch (InvalidOperationException ex) when (ex.Message == "observed real packet allocation boundary") { }
                    Equal(point == Vector2.Zero ? 1 : 0, reached,
                        "outgoing explicit/fallback coordinates validated before packet allocation; zero remains valid");
                }
            }
            finally { instance.SetValue(null, oldInstance); Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; }
        });
    }

    public static void ItemVfxEventPositionsRelayAndBudgets()
    {
        ItemOutgoingVfxRejectsNonfinitePoint();
        WithLighting((config, lights) =>
        {
            var oldDust = Terraria.Main.dust;
            var random = Terraria.Main.rand;
            var oldPlayer = Terraria.Main.player[4];
            bool menu = Terraria.Main.gameMenu, gen = WorldGen.gen;
            int max = Terraria.Main.maxDustToDraw, width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
            Vector2 screen = Terraria.Main.screenPosition;
            float count = Dust.dCount;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? previous = clock.GetValue(null);
            try
            {
                Terraria.Main.gameMenu = false; WorldGen.gen = false;
                Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenWidth = 800; Terraria.Main.screenHeight = 600;
                Terraria.Main.screenPosition = Vector2.Zero;
                Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 4;
                config.ParticleSpawnMultiplier = 1f; config.PresentationLightMultiplier = 1f;
                Terraria.Main.dust = new Dust[oldDust.Length];
                for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust { dustIndex = i };
                Dust.dCount = 0; Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
                InfiniItemVfxRuntime.ClearUseEventCaches(); clock.SetValue(null, 100u);
                var player = Terraria.Main.player[4] = new Player { whoAmI = 4, active = true, Center = new Vector2(160f) };
                var target = new NPC { active = true, Center = new Vector2(320f, 240f) };
                var data = GeneratedItemData.Placeholder();
                string entity = data.RuntimeProgram.ItemEntityId;
                data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Input = RuntimeInputKind.PrimaryUse,
                    UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true,
                        Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = entity } } } };
                var item = player.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1, useTime = 20 };
                var generated = new GeneratedItem();
                AttachItem(generated, item, data);
                var slot = new VfxSlotSpec { Id="event",EntityId=entity,Event="on_hit",Anchor="hitPoint",RendererKind="nativeDust",
                    Color=Rgb(255,255,255),StartTick=0,RepeatEvery=0,
                    Dust=new(){Type="GemDiamond",Count=8,Size=1,Spawn=new(){Shape="point"},AngularDistribution="even",DirectionFrame="source",
                        AngleOffsetRadians=0,SpreadRadians=MathF.Tau,SpeedMinPxPerTick=1,SpeedMaxPxPerTick=1,NativeAlpha=100,NoGravity=true}};
                data.VfxManifest.Slots = new[] { slot };
                data.VfxManifest.Budget.MaxParticlesPerTick = 32;
                data.VfxManifest.Budget.MaxParticlesTotal = 3;
                generated.OnHitNPC(player, target, new NPC.HitInfo(), 1);
                Equal(3, Terraria.Main.dust.Count(d => d.active), "event invocation owns its total allowance");
                foreach (Dust dust in Terraria.Main.dust.Where(d => d.active))
                    Equal(target.Center, dust.position, "real hit hook captures target center");
                slot.Event = RuntimeEventKind.OnCrit;
                generated.OnHitNPC(player, target, new NPC.HitInfo { Crit = true }, 1);
                Equal(6, Terraria.Main.dust.Count(d => d.active), "crit owns independent event allowance");
                data.VfxManifest.Budget.MaxParticlesTotal=0;
                generated.OnHitNPC(player,target,new NPC.HitInfo{Crit=true},1);
                Equal(6,Terraria.Main.dust.Count(d=>d.active),"explicit zero event allowance stays silent");

                // Retired v3 had no event occurrence and cannot distinguish two
                // genuine hits from a duplicate. Fail closed rather than guess.
                Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
                data.VfxManifest = LightManifest(entity, RuntimeEventKind.OnHit);
                lights.Clear();
                using (var oldPacket = new MemoryStream())
                {
                    using (var writer = new BinaryWriter(oldPacket, System.Text.Encoding.UTF8, true))
                    { writer.Write((byte)3); writer.Write((byte)4); writer.Write(data.Id); writer.Write(entity); writer.Write(RuntimeEventKind.OnHit); writer.Write(320f); writer.Write(240f); }
                    oldPacket.Position = 0;
                    InfiniItemVfxRuntime.HandleUseEventPacket(new BinaryReader(oldPacket), 4);
                }
                Equal(0, lights.Count, "retired identity-free event packet rejected");
            }
            finally
            {
                InfiniItemVfxRuntime.ClearUseEventCaches(); clock.SetValue(null, previous);
                Terraria.Main.dust = oldDust; Terraria.Main.rand = random; Terraria.Main.player[4] = oldPlayer;
                Terraria.Main.gameMenu = menu; WorldGen.gen = gen; Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local;
                Terraria.Main.maxDustToDraw = max; Terraria.Main.screenWidth = width; Terraria.Main.screenHeight = height;
                Terraria.Main.screenPosition = screen; Dust.dCount = count;
            }
        });
    }
}
