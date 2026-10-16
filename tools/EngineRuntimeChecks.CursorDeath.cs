using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using ReLogic.Content;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Execute the real native cursor owner, intercepting only its final ItemSlot
    // output. No GPU, game loop, user cache or saved item is involved.
    private static void CursorDeathRetiresGeneratedPreviewOnly()
    {
        using var actors = new NativeActorState();
        using var cache = new BorrowedSpriteCache();
        const BindingFlags statics = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        var target = typeof(Terraria.Main).GetMethod("DrawInterface_40_InteractItemIcon", TestInstance)!;
        var oldMain = Terraria.Main.instance;
        var oldAssets = TextureAssets.Item;
        bool oldHover = Terraria.Main.HoveringOverAnNPC;
        Item oldMouse = Terraria.Main.mouseItem;
        var fields = new[] { "_itemIconCacheTime", "_itemIconCacheSelectedItemID", "_itemIconCacheScreenPosition" }
            .Select(name => typeof(Terraria.Main).GetField(name, statics)!).ToArray();
        object?[] saved = fields.Select(field => field.GetValue(null)).ToArray();
        var main = (Terraria.Main)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Main));
        GC.SuppressFinalize(main);
        var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
        var data = GeneratedItemData.Placeholder();
        AttachItem(new GeneratedItem(), item, data);
        var player = new Player { active = true, selectedItem = 0 };
        player.inventory[0] = item;
        var draws = new List<Item>();
        var sample = ContentSamples.ItemsByType.GetValueOrDefault(item.type);
        var bridge = new GeneratedCursorItemPresentationSystem();
        try
        {
            typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, main);
            Terraria.Main.dedServ = false; Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            Terraria.Main.player[0] = player; Terraria.Main.mouseItem = new Item(); Terraria.Main.HoveringOverAnNPC = false;
            TextureAssets.Item = (Asset<Texture2D>[])oldAssets.Clone();
            TextureAssets.Item[item.type] = CpuTextureAsset(CpuTexture(32, 32));
            ContentSamples.ItemsByType[item.type] = new Item { type = item.type, stack = 1 };
            MethodInfo iconOutput = typeof(Terraria.UI.ItemSlot).GetMethods(statics).Single(m => m.Name == "DrawItemIcon" && m.GetParameters().Length == 7);
            using var output = new Hook(iconOutput,
                (Func<Item, int, SpriteBatch, Vector2, float, float, Color, float>)
                ((source, context, batch, position, scale, maximum, color) => { draws.Add(source); return scale; }));
            int Render(bool dead, bool enabled, int icon = 0, bool seed = true)
            {
                player.dead = dead; player.cursorItemIconEnabled = enabled; player.cursorItemIconID = icon;
                if (seed) Terraria.Main.ItemIconCacheUpdate(item.type);
                draws.Clear(); target.Invoke(main, null);
                Equal(icon, player.cursorItemIconID, "native cache swap restores icon ID");
                return draws.Count;
            }
            // Establish the native stale-cache producer before applying the mod hook.
            Equal(1, Render(dead: true, enabled: false), "native dead cache submits the type-wide placeholder");
            Equal(true, ReferenceEquals(ContentSamples.ItemsByType[item.type], draws.Single()), "native cache loses instance identity");
            bridge.Load();
            Equal(0, Render(dead: true, enabled: false), "dead generated cached preview must be absent");
            for (int frame = 0; frame < 3; frame++)
                Equal(0, Render(dead: true, enabled: false, seed: false), "stationary dead cache remains suppressed without reseeding");
            Equal(1, Render(dead: false, enabled: false, seed: false), "respawn resumes native cached preview without reseeding");
            Equal(0, Render(dead: true, enabled: true), "death retires active generated preview too");
            Equal(1, Render(dead: false, enabled: false), "live cached-preview behavior unchanged");
            Equal(1, Render(dead: false, enabled: true), "live selected preview unchanged");
            data.Visual.SpritePath = System.IO.Path.Combine(Terraria.Program.SavePath, "cursor_death_fixture.png");
            cache.Textures.Add(data.Visual.SpritePath, Activator.CreateInstance(cache.Record, CpuTexture(32, 32), 0f, 0L)!);
            Equal(1, Render(dead: false, enabled: true), "ready live selected preview submitted");
            Equal(true, ReferenceEquals(item, draws.Single()), "ready live preview retains exact generated instance");
            item.color = new Color(80, 100, 120);
            Equal(0, Render(dead: true, enabled: false), "dead tinted cache cannot reach static tint tail");
            Equal(1, Render(dead: false, enabled: true), "ready live tint stays in instance ItemSlot path");
            item.color = Color.Transparent;
            Equal(1, Render(dead: true, enabled: true, icon: item.type), "explicit foreign icon remains native-owned");
            player.inventory[0] = ContentSamples.ItemsByType[item.type];
            Equal(1, Render(dead: true, enabled: false), "ordinary native dead cache unchanged");
            player.inventory[0] = item;
            bridge.Unload();
            Equal(1, Render(dead: true, enabled: false), "unload restores native cache submission");
        }
        finally
        {
            bridge.Unload();
            for (int i = 0; i < fields.Length; i++) fields[i].SetValue(null, saved[i]);
            if (sample is null) ContentSamples.ItemsByType.Remove(item.type); else ContentSamples.ItemsByType[item.type] = sample;
            TextureAssets.Item = oldAssets; Terraria.Main.HoveringOverAnNPC = oldHover; Terraria.Main.mouseItem = oldMouse;
            typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, oldMain);
        }
    }
}
