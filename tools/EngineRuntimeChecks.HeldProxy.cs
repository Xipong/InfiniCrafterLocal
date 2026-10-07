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
    private static void HeldProxyIsReplacedOnlyByReadyInstanceSprite()
    {
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
        var parent = PlayerDrawLayers.HeldItem; var child = new GeneratedHeldItemDrawLayer();
        var children = (IList)typeof(PlayerDrawLayer).GetProperty("ChildrenAfter", instance)!.GetValue(parent)!;
        var savedChildren = new List<object>(); foreach (object value in children) savedChildren.Add(value);
        object? savedCache = sprites.GetValue(null), savedLight = light.GetValue(null);
        var savedMain = Terraria.Main.instance; var savedAssets = TextureAssets.Item;
        bool savedServer = Terraria.Main.dedServ; int savedMode = Terraria.Main.netMode, savedPlayer = Terraria.Main.myPlayer;
        string path = System.IO.Path.Combine(Terraria.Program.SavePath, "held_proxy_cpu.png");
        var data = GeneratedItemData.Placeholder();
        data.Visual.SpritePath = path; data.Visual.RenderSizePx = 32;
        data.Gameplay.UseStyleName = "hold_up"; data.RuntimeProgram.ItemUse.UseStyle = "hold_up";
        var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
        var generated = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", instance)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
        data.ApplyToItem(item);
        var player = new Player { whoAmI = 0, active = true, selectedItem = 0, position = new Vector2(160, 160), itemAnimation = 8, itemAnimationMax = 24, heldProj = -1, direction = 1, gravDir = 1f };
        player.inventory[0] = item;
        var reset = typeof(PlayerDrawLayer).GetMethod("ResetVisibility", instance)!;
        var tree = typeof(PlayerDrawLayer).GetMethod("DrawWithTransformationAndChildren", instance)!;
        PlayerDrawSet Info(Item host) => new() { drawPlayer = player, heldItem = host, ItemLocation = new Vector2(180, 180), Position = player.position, DrawDataCache = new List<DrawData>() };
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
            children.Clear(); children.Add(child);
            textures.Add(path, Activator.CreateInstance(record, generatedTexture, 0f, 0L)!);
            string before = System.Text.Json.JsonSerializer.Serialize(data);
            Sequence(Render(item), "ready PNG replaces native proxy", generatedTexture);
            Equal(false, item.noUseGraphic, "draw keeps native literal flag");
            Equal(before, System.Text.Json.JsonSerializer.Serialize(data), "draw keeps definition unchanged");
            Sequence(Render(item, seed: true), "prior foreign and same-proxy records retained", foreignTexture, nativeTexture, generatedTexture);
            item.color = new Color(80, 100, 120);
            Sequence(Render(item), "native tint overlay is also replaced", generatedTexture); item.color = Color.Transparent;

            // Native Item.Clone creates the visualized Item and its distinct attached ModItem.
            Item visualized = item.Clone();
            Equal(false, ReferenceEquals(item, visualized), "visualized host really cloned");
            Equal(false, ReferenceEquals(generated, visualized.ModItem), "visualized ModItem is distinct");
            Equal(true, ReferenceEquals(visualized.ModItem!.Item, visualized), "cloned ModItem owns native host");
            Sequence(Render(visualized), "native visualized clone still replaced", generatedTexture);

            textures.Remove(path);
            Sequence(Render(item), "missing PNG preserves native fallback", nativeTexture);
            Equal(false, item.noUseGraphic, "missing PNG does not alter flag");
            textures.Add(path, Activator.CreateInstance(record, generatedTexture, 0f, 0L)!);
            player.itemAnimation = 0; item.holdStyle = 1;
            Sequence(Render(item), "idle native hold preserved", nativeTexture); item.holdStyle = 0; player.itemAnimation = 8;
            data.RuntimeProgram.ItemUse.HideUseGraphic = true; data.ApplyToItem(item);
            Sequence(Render(item), "authored hide still hides both");
            data.RuntimeProgram.ItemUse.HideUseGraphic = false; data.ApplyToItem(item);
            data.RuntimeProgram.ItemUse.ReleaseTiming = "immediate";
            Sequence(Render(item), "immediate hint retains existing native-only behavior", nativeTexture);
            data.RuntimeProgram.ItemUse.ReleaseTiming = "";
            player.dead = true; Sequence(Render(item), "dead remains empty"); player.dead = false;
            player.frozen = true; Sequence(Render(item), "frozen remains empty"); player.frozen = false;
            Sequence(Render(item, hideParent: true), "hidden parent still hides child");
            Sequence(Render(item, seed: true, shadow: true), "shadow does not erase prior records", foreignTexture, nativeTexture, generatedTexture);
            player.JustDroppedAnItem = true;
            Sequence(Render(item, seed: true), "no native submission does not erase prior records", foreignTexture, nativeTexture, generatedTexture); player.JustDroppedAnItem = false;

            // Real native producer dispatch preserves optional foreign draws, but not proxy overlays.
            var info = Info(item);
            ItemLoader.ModifyItemDraw(item, ref info, Entry(nativeTexture), Entry(foreignTexture), Entry(foreignTexture));
            Sequence(info, "optional foreign color and glow retained", foreignTexture, foreignTexture);
            info = Info(item);
            ItemLoader.ModifyItemDraw(item, ref info, Entry(foreignTexture), Entry(nativeTexture), null);
            Sequence(info, "foreign base keeps native producer bundle", foreignTexture, nativeTexture);
            info = Info(item);
            ItemLoader.ModifyItemDraw(item, ref info, Entry(nativeTexture), Entry(nativeTexture), Entry(nativeTexture));
            Sequence(info, "entire static proxy bundle suppressed");
        }
        finally
        {
            children.Clear(); foreach (object value in savedChildren) children.Add(value);
            typeof(PlayerDrawLayer).GetProperty("Visible", instance)!.SetValue(parent, true);
            textures.Clear(); sprites.SetValue(null, savedCache); light.SetValue(null, savedLight);
            TextureAssets.Item = savedAssets; typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, savedMain);
            Terraria.Main.dedServ = savedServer; Terraria.Main.netMode = savedMode; Terraria.Main.myPlayer = savedPlayer;
            cache.Dispose();
        }
    }
}
