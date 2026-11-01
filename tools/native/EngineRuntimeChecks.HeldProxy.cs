using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using Terraria;
using Terraria.DataStructures;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Actual native HeldItem tree and ItemLoader consumer; CPU texture/cache shells.
    // No registered mod, GPU pixels, content loading or world/player update loop.
    private static void HeldProxyIsReplacedOnlyByReadyInstanceSprite() => HeldProxyIsReplacedOnlyByReadyInstanceSprite(false);

    private static void HeldProxyIsReplacedOnlyByReadyInstanceSprite(bool delivered)
    {
        using var actorState = new NativeActorState();
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        const BindingFlags statics = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        T Shell<T>() where T : class { var value = (T)RuntimeHelpers.GetUninitializedObject(typeof(T)); GC.SuppressFinalize(value); return value; }
        Texture2D Texture() { var value = Shell<Texture2D>(); typeof(Texture2D).GetProperty("Width")!.SetValue(value, 32); typeof(Texture2D).GetProperty("Height")!.SetValue(value, 32); return value; }
        var nativeTexture = Texture(); var generatedTexture = Texture(); var foreignTexture = Texture();
        var asset = Shell<Asset<Texture2D>>();
        typeof(Asset<Texture2D>).GetField("ownValue", instance)!.SetValue(asset, nativeTexture);
        typeof(Asset<Texture2D>).GetProperty("State")!.SetValue(asset, AssetState.Loaded);
        var cache = new RuntimeSpriteCache();
        var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", instance)!.GetValue(cache)!;
        var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
        var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
        var light = typeof(Lighting).GetField("_activeEngine", statics)!;
        var parent = PlayerDrawLayers.HeldItem;
        var children = (IList)typeof(PlayerDrawLayer).GetProperty("ChildrenAfter", instance)!.GetValue(parent)!;
        var savedChildren = new List<object>(); foreach (object value in children) savedChildren.Add(value);
        object? savedCache = sprites.GetValue(null), savedLight = light.GetValue(null);
        var savedMain = Terraria.Main.instance; var savedAssets = TextureAssets.Item;

        string path = System.IO.Path.GetFullPath("held_proxy_cpu.png"); // Original path and clone filename resolve to the same cache key.
        var data = GeneratedItemData.Placeholder();data.Id="native_held_cpu";
        data.Visual.SpritePath = path; data.Visual.RenderSizePx = 32; data.Visual.ForwardAngleDegrees = 0;
        if (delivered) { data.SourceMode = "generated"; data.Visual.SpriteStatus = "generated"; }
        data.Gameplay.UseStyleName = "hold_up"; data.RuntimeProgram.ItemUse.UseStyle = "hold_up";
        data.RuntimeProgram.ItemUse.Configured=true;
        data.RuntimeProgram.Bindings=new[]{new RuntimeBindingSpec{Id="native_use",Input=RuntimeInputKind.PrimaryUse,Role=RuntimeEntityRole.Primary,
            UsePolicy=new RuntimeBindingUsePolicySpec{Action=new RuntimeBindingActionSpec{Kind=RuntimeBindingAction.UseItemBody,TargetId=data.RuntimeProgram.ItemEntityId}}}};
        _=data.CloneForItemInstance(); // Actual clones must start from an accepted executable fixture, never placeholder fallback.
        var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
        var generated = new GeneratedItem();
        AttachItem(generated, item, data);
        data.ApplyToItem(item);
        var player = new Player { whoAmI = 0, active = true, selectedItem = 0, position = new Vector2(160, 160), itemAnimation = 8, itemAnimationMax = 24, heldProj = -1, direction = 1, gravDir = 1f };
        player.inventory[0] = item;
        var reset = typeof(PlayerDrawLayer).GetMethod("ResetVisibility", instance)!;
        var tree = typeof(PlayerDrawLayer).GetMethod("DrawWithTransformationAndChildren", instance)!;
        PlayerDrawSet Info(Item host) => new() { drawPlayer = player, heldItem = host, ItemLocation = new Vector2(180, 180) + player.position - new Vector2(160, 160), Position = player.position, DrawDataCache = new List<DrawData>() };
        DrawData Entry(Texture2D texture) => new(texture, Vector2.Zero, texture.Bounds, Color.White, 0f, Vector2.Zero, 1f, SpriteEffects.None, 0f);
        PlayerDrawSet Render(Item host, bool seed = false, bool shadow = false, bool hideParent = false)
        {
            var info = Info(host);
            if (seed) { info.DrawDataCache.Add(Entry(foreignTexture)); info.DrawDataCache.Add(Entry(nativeTexture)); }
            if (shadow) info.shadow = 0.5f;
            reset.Invoke(parent, new object[] { info });
            if (hideParent) parent.Hide();
            object[] args = { info }; tree.Invoke(parent, args); return (PlayerDrawSet)args[0];
        }
        void Sequence(PlayerDrawSet info, string label, params Texture2D[] expected)
        {
            Equal(expected.Length, info.DrawDataCache.Count, label + " count");
            for (int i = 0; i < expected.Length; i++)
                Equal(true, ReferenceEquals(expected[i], info.DrawDataCache[i].texture), label + " texture/order " + i);
        }
        try
        {
            typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, Shell<Terraria.Main>());
            Terraria.Main.dedServ = false; Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            light.SetValue(null, new Terraria.Graphics.Light.LightingEngine()); sprites.SetValue(null, cache);
            TextureAssets.Item = (Asset<Texture2D>[])savedAssets.Clone(); TextureAssets.Item[item.type] = asset;
            children.Clear(); // No custom child draw participates in this native-owner test.
            textures.Add(path, Activator.CreateInstance(record, generatedTexture, 0f, 0L)!);
            string before = System.Text.Json.JsonSerializer.Serialize(data);
            Sequence(Render(item), "ready PNG replaces native proxy", generatedTexture);
            Equal(false, item.noUseGraphic, "draw keeps native literal flag");
            Equal(before, System.Text.Json.JsonSerializer.Serialize(data), "draw keeps definition unchanged");
            Sequence(Render(item, seed: true), "prior foreign and same-proxy records retained", foreignTexture, nativeTexture, generatedTexture);
            item.color = new Color(80, 100, 120);
            Sequence(Render(item), "native tint overlay is also replaced without deleting its pass", generatedTexture, generatedTexture); item.color = Color.Transparent;

            // Native Item.Clone creates the visualized Item and its distinct attached ModItem.
            Item visualized = item.Clone();
            Equal(false, ReferenceEquals(item, visualized), "visualized host really cloned");
            Equal(false, ReferenceEquals(generated, visualized.ModItem), "visualized ModItem is distinct");
            Equal(true, ReferenceEquals(visualized.ModItem!.Item, visualized), "cloned ModItem owns native host");
            Sequence(Render(visualized), "native visualized clone still replaced", generatedTexture);

            // The final native producer owns position, rotation, effects and tint.
            // Our hook changes only the instance artwork/canvas, never a hand pose.
            foreach(int style in new[]{ItemUseStyleID.Shoot,ItemUseStyleID.Swing,ItemUseStyleID.Thrust,ItemUseStyleID.HoldUp})
            foreach(int direction in new[]{-1,1}) foreach(float gravity in new[]{-1f,1f})
            foreach(float rotation in new[]{-.7f,0f,.9f}) {
                item.useStyle=style;player.direction=direction;player.gravDir=gravity;player.itemRotation=rotation;
                player.itemLocation=new Vector2(180,164);
                typeof(Item).GetProperty("ModItem")!.SetValue(item,null);
                PlayerDrawSet native;
                try {native=Render(item);} finally {typeof(Item).GetProperty("ModItem")!.SetValue(item,generated);}
                var actual=Render(item);
                Equal(1,native.DrawDataCache.Count,"native body actually submitted");
                Equal(1,actual.DrawDataCache.Count,"single generated body replaces native submission");
                var a=actual.DrawDataCache[0];var b=native.DrawDataCache[0];
                AssertVfxNear(b.position,a.position,"native position is not re-created by a custom pose engine");
                Equal(b.rotation,a.rotation,"native rotation preserved");Equal(b.effect,a.effect,"native flip preserved");
                Equal(b.color,a.color,"native tint preserved");Equal(b.shader,a.shader,"native shader preserved");
                Equal(true,ReferenceEquals(a.texture,generatedTexture),"instance texture selected");
                Equal(generatedTexture.Bounds,a.sourceRect!.Value,"full generated canvas selected");
                // Later native player transforms act on the same cached entry.
                actual.rotation=native.rotation=.37f;actual.rotationOrigin=native.rotationOrigin=new Vector2(10,20);
                actual.DustCache=native.DustCache=new List<int>();actual.GoreCache=native.GoreCache=new List<int>();
                PlayerDrawLayers.DrawPlayer_TransformDrawData(ref native);
                PlayerDrawLayers.DrawPlayer_TransformDrawData(ref actual);
                AssertVfxNear(native.DrawDataCache[0].position,actual.DrawDataCache[0].position,"native later transform applies once");
                Equal(native.DrawDataCache[0].rotation,actual.DrawDataCache[0].rotation,"later rotation stays native");
            }
            player.direction=1;player.gravDir=1;player.itemRotation=0;item.useStyle=ItemUseStyleID.HoldUp;
            var info=Info(item);
            ItemLoader.ModifyItemDraw(item,ref info,Entry(nativeTexture),Entry(nativeTexture),Entry(nativeTexture));
            Sequence(info,"native loader retains body/color/glow pass count with instance canvases",generatedTexture,generatedTexture,generatedTexture);
            info=Info(item);
            ItemLoader.ModifyItemDraw(item,ref info,Entry(foreignTexture),Entry(nativeTexture),null);
            Sequence(info,"foreign base bundle is not claimed",foreignTexture,nativeTexture);
            info=Info(item);
            ItemLoader.ModifyItemDraw(item,ref info,Entry(nativeTexture),Entry(foreignTexture),Entry(foreignTexture));
            Sequence(info,"foreign color and glow remain owned by their original producer",generatedTexture,foreignTexture,foreignTexture);

            // A native visualized clone keeps its own accepted art/calibration during a same-ID live replacement.
            var originalClone=item.Clone();
            var clonedOwner=(GeneratedItem)originalClone.ModItem;
            Equal(true,ReferenceEquals(data,clonedOwner.NativeHeldSourceData),"native clone records immediate accepted source");
            var cloneBefore=Render(originalClone);
            var replacement=data.CloneForItemInstance();replacement.Visual.SpritePath=path+".replacement.png";
            replacement.Visual.RenderSizePx=64;replacement.RuntimeProgram.ItemUse.UseStyle="swing";
            replacement.Gameplay.UseStyleName="swing";
            textures.Add(replacement.Visual.SpritePath,Activator.CreateInstance(record,foreignTexture,0f,0L)!);
            void Install(GeneratedItem target,GeneratedItemData accepted)=>typeof(GeneratedItem).GetMethod("SetData",instance,null,
                new[]{typeof(GeneratedItemData),typeof(bool),typeof(bool),typeof(bool)},null)!.Invoke(target,new object[]{accepted,false,false,false});
            Install(generated,replacement);
            var cloneAfter=Render(originalClone);
            Sequence(cloneAfter,"same-ID live replacement cannot lend its new PNG to old native pose",generatedTexture);
            Equal(cloneBefore.DrawDataCache[0],cloneAfter.DrawDataCache[0],"old native clone retains exact frame/pose/canvas scale");
            Equal(true,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(originalClone),out var cloneData),"old native clone remains visible");
            Equal(true,ReferenceEquals(clonedOwner.Data,cloneData),"actual native clone definition owns presentation");
            var nextClone=item.Clone();
            Sequence(Render(nextClone),"new native clone uses the new accepted artwork",foreignTexture);
            var twiceClone=originalClone.Clone();
            Equal(true,ReferenceEquals(clonedOwner.Data,((GeneratedItem)twiceClone.ModItem).NativeHeldSourceData),"clone of clone records immediate source, not ancestor");
            Equal(false,ReferenceEquals(data,((GeneratedItem)twiceClone.ModItem).NativeHeldSourceData),"clone lineage does not tunnel to original ancestor");
            Install((GeneratedItem)twiceClone.ModItem,clonedOwner.Data.CloneForItemInstance());
            Equal(true,((GeneratedItem)twiceClone.ModItem).NativeHeldSourceData is null,"explicit SetData clears native clone provenance");
            var resetClone=originalClone.Clone();((GeneratedItem)resetClone.ModItem).SetDefaults();
            Equal(true,((GeneratedItem)resetClone.ModItem).NativeHeldSourceData is null,"native SetDefaults clears clone provenance");
            var compactClone=originalClone.Clone();var compact=GeneratedItemData.Placeholder();compact.Id=data.Id;compact.SourceMode="player_save_ref";
            Install((GeneratedItem)compactClone.ModItem,compact);
            Equal(false,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(compactClone),out _),"compact native clone cannot borrow current live definition art");
            Install(generated,data);item.useStyle=ItemUseStyleID.HoldUp;
            textures.Remove(replacement.Visual.SpritePath);

            // Native remote animation is authoritative; no custom pose packet exists.
            Terraria.Main.player[0]=player;Terraria.Main.myPlayer=1;Terraria.Main.netMode=NetmodeID.MultiplayerClient;
            player.itemAnimation=0;
            Equal(false,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(item),out _),"no local animation means no remote held body");
            // Unlike the inert rendering fixture above, this explicitly has a usable binding.
            data.RuntimeProgram.ItemUse.Configured=true;
            data.RuntimeProgram.Bindings=new[]{new RuntimeBindingSpec{Id="native_use",Input=RuntimeInputKind.PrimaryUse,Role=RuntimeEntityRole.Primary,
                UsePolicy=new RuntimeBindingUsePolicySpec{Action=new RuntimeBindingActionSpec{Kind=RuntimeBindingAction.UseItemBody,TargetId=data.RuntimeProgram.ItemEntityId}}}};
            player.itemAnimation=0;player.itemAnimationMax=0;player.itemTime=0;player.reuseDelay=0;
            player.controlUseItem=true;player.releaseUseItem=true;item.useTime=20;item.useAnimation=20;
            // Native SummonItemCheck inspects every NPC slot, even for a non-summoning item.
            for(int i=0;i<Terraria.Main.npc.Length;i++)Terraria.Main.npc[i]=new NPC{whoAmI=i,active=false};
            // First native use still measures the prior empty visualized item before cloning current item at the end.
            TextureAssets.Item[0]=asset;
            player.ItemCheck();
            Equal(true,player.itemAnimation>0,"actual remote ItemCheck starts native animation from received controls");
            Equal(item.type,player.lastVisualizedSelectedItem.type,"native ItemCheck updates its actual visualized clone");
            Equal(data.Id,((GeneratedItem)player.lastVisualizedSelectedItem.ModItem).Data.Id,"native visualized clone preserves generated identity");
            Sequence(Render(player.lastVisualizedSelectedItem),"actual remote native animation submits the instance body",generatedTexture);
            player.controlUseItem=false;item.noUseGraphic=true;
            Equal(false,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(item),out _),"native noUseGraphic also owns remote visibility");item.noUseGraphic=false;
            Terraria.Main.myPlayer=0;Terraria.Main.netMode=NetmodeID.SinglePlayer; // Remaining registry hydration controls do not test network transport.
            var reference=GeneratedItemData.Placeholder();reference.Id=data.Id;reference.SourceMode="player_save_ref";reference.Visual=data.Visual;
            var registryProperty=typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
            object? oldRegistry=registryProperty.GetValue(null);
            using(var registry=new GeneratedItemRegistryService()) {
                try {
                    registryProperty.SetValue(null,registry);AttachItem(generated,item,reference);
                    Equal(false,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(item),out _),"compact reference without canonical data cannot draw");
                    GeneratedItemRegistryService.StampCurrentWorld(data);
                    var definitions=(IDictionary)registry.GetType().GetField("_byId",instance)!.GetValue(registry)!;definitions[data.Id]=data;
                    Equal(false,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(item),out _),"registry availability alone cannot lend art to a compact native snapshot");
                    GeneratedItemRegistryService.StampCurrentWorld(reference);MaterialClock(200);
                    typeof(GeneratedItem).GetMethod("EnsureRuntimeHydration",instance)!.Invoke(generated,new object?[]{player});
                    Equal(true,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(item),out var hydrated),"actual item hydration permits its accepted native snapshot");
                    Equal(true,ReferenceEquals(data,hydrated),"hydration installs exact accepted definition");
                    definitions.Remove(data.Id);Equal(true,GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(Info(item),out _),"already accepted native snapshot does not borrow registry state");
                } finally {registryProperty.SetValue(null,oldRegistry);AttachItem(generated,item,data);}
            }
            Terraria.Main.myPlayer=0;Terraria.Main.netMode=NetmodeID.SinglePlayer;
            textures.Remove(path);
            Sequence(Render(item),"missing image remains explicit inert diagnostic or absent",delivered?Array.Empty<Texture2D>():new[]{nativeTexture});
            Equal(false,item.noUseGraphic,"asset absence never mutates gameplay visibility");
            textures.Add(path,Activator.CreateInstance(record,generatedTexture,0f,0L)!);
            player.itemAnimation=0;item.holdStyle=1;
            Sequence(Render(item),"no animation cannot create a generated active body",delivered?Array.Empty<Texture2D>():new[]{nativeTexture});
            item.holdStyle=0;player.itemAnimation=8;
            item.noUseGraphic=true;Sequence(Render(item),"native noUseGraphic prevents hook submission");item.noUseGraphic=false;
            player.dead=true;Sequence(Render(item),"dead native player stays invisible");player.dead=false;
            player.frozen=true;Sequence(Render(item),"frozen native player stays invisible");player.frozen=false;
            typeof(Item).GetProperty("ModItem")!.SetValue(item,null);
            PlayerDrawSet nativeShadow;try{nativeShadow=Render(item,seed:true,shadow:true);}finally{typeof(Item).GetProperty("ModItem")!.SetValue(item,generated);}
            var generatedShadow=Render(item,seed:true,shadow:true);
            Equal(nativeShadow.DrawDataCache.Count,generatedShadow.DrawDataCache.Count,"native shadow visibility is not augmented by a second body layer");
            Equal(true,ReferenceEquals(generatedShadow.DrawDataCache[0].texture,foreignTexture),"shadow preserves prior foreign record");
            Equal(true,ReferenceEquals(generatedShadow.DrawDataCache[1].texture,nativeTexture),"shadow preserves prior same-proxy record");
            Sequence(Render(item,hideParent:true),"hidden native parent stays invisible");
            player.JustDroppedAnItem=true;
            Sequence(Render(item,seed:true),"no native submission preserves earlier records only",foreignTexture,nativeTexture);
            player.JustDroppedAnItem=false;
            Equal(true,ReferenceEquals(TextureAssets.Item[item.type],asset),"type-wide asset remains untouched");
        }

        finally
        {
            children.Clear(); foreach (object value in savedChildren) children.Add(value);
            typeof(PlayerDrawLayer).GetProperty("Visible", instance)!.SetValue(parent, true);
            textures.Clear(); sprites.SetValue(null, savedCache); light.SetValue(null, savedLight);
            TextureAssets.Item = savedAssets; typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, savedMain);

            cache.Dispose();
        }
    }
}
