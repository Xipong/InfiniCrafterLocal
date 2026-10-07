using System;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Real production DrawStatuses and FNA CPU queue. The two-tick control avoids
    // the font-only duration path; font/hover content is verified by status tests.
    // No GPU, native icon pixels, full interface loop or font-resource claim.
    private static void GeneratedUtilityStatusDrawsNativeIconIntoFnaQueue()
    {
        const BindingFlags instance = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
        const BindingFlags statics = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
        T Shell<T>() where T : class { var value = (T)RuntimeHelpers.GetUninitializedObject(typeof(T)); GC.SuppressFinalize(value); return value; }
        var texture = Shell<Texture2D>();
        typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 32);
        typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 32);
        var asset = Shell<Asset<Texture2D>>();
        typeof(Asset<Texture2D>).GetField("ownValue", instance)!.SetValue(asset, texture);
        typeof(Asset<Texture2D>).GetProperty("State")!.SetValue(asset, AssetState.Loaded);
        var batch = Shell<SpriteBatch>();
        foreach (string name in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
        {
            var field = typeof(SpriteBatch).GetField(name, instance)!;
            field.SetValue(batch, Array.CreateInstance(field.FieldType.GetElementType()!, 16));
        }
        var count = typeof(SpriteBatch).GetField("numSprites", instance)!;
        var savedMain = Terraria.Main.instance; var savedBatch = Terraria.Main.spriteBatch;
        var savedLanguage = Terraria.Localization.LanguageManager.Instance;
        var savedAssets = TextureAssets.Buff; var savedPlayer = Terraria.Main.player[0];
        bool savedServer = Terraria.Main.dedServ, savedMenu = Terraria.Main.gameMenu;
        bool savedHide = Terraria.Main.hideUI, savedInventory = Terraria.Main.playerInventory;
        bool savedOptions = Terraria.Main.ingameOptionsWindow, savedFancy = Terraria.Main.inFancyUI, savedMap = Terraria.Main.mapFullscreen;
        int savedLocal = Terraria.Main.myPlayer, savedMode = Terraria.Main.netMode;
        int savedMouseX = Terraria.Main.mouseX, savedMouseY = Terraria.Main.mouseY;
        int savedWidth = Terraria.Main.screenWidth, savedHeight = Terraria.Main.screenHeight;
        int savedEquip = Terraria.Main.EquipPage, savedMapStyle = Terraria.Main.mapStyle;
        bool savedMapEnabled = Terraria.Main.mapEnabled;
        var mapHeight = typeof(Terraria.Main).GetField("mH", statics)!;
        int savedMapHeight = (int)mapHeight.GetValue(null)!;
        using var flush = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!,
            (Action<SpriteBatch>)(self => count.SetValue(self, 0)));
        try
        {
            var manager = (Terraria.Localization.LanguageManager)Activator.CreateInstance(typeof(Terraria.Localization.LanguageManager), nonPublic: true)!;
            typeof(Terraria.Localization.LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager, Terraria.Localization.GameCulture.FromName("en-US"));
            Terraria.Localization.LanguageManager.Instance = manager;
            typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, Shell<Terraria.Main>());
            Terraria.Main.spriteBatch = batch; Terraria.Main.myPlayer = 0; Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.dedServ = Terraria.Main.gameMenu = Terraria.Main.hideUI = Terraria.Main.playerInventory = false;
            Terraria.Main.ingameOptionsWindow = Terraria.Main.inFancyUI = Terraria.Main.mapFullscreen = false;
            Terraria.Main.mouseX = Terraria.Main.mouseY = -100;
            TextureAssets.Buff = (Asset<Texture2D>[])savedAssets.Clone(); TextureAssets.Buff[BuffID.Featherfall] = asset;
            WithPlayer((player, generated) =>
            {
                Terraria.Main.player[0] = player; player.active = true; player.whoAmI = 0;
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, JumpBoost = 1.5f });
                var draw = typeof(GeneratedUtilityBuffUISystem).GetMethod("DrawStatuses", statics)!;
                batch.Begin();
                Equal(true, (bool)draw.Invoke(null, null)!, "actual status callback completes");
                Equal(1, (int)count.GetValue(batch)!, "one native borrowed icon queued");
                var textures = (Array)typeof(SpriteBatch).GetField("textureInfo", instance)!.GetValue(batch)!;
                Equal(true, ReferenceEquals(texture, textures.GetValue(0)), "actual Featherfall texture is selected");
                batch.End();
                Equal(false, player.HasBuff(BuffID.Featherfall), "draw cannot add vanilla buff mechanics");
                Equal(false, player.slowFall, "draw cannot enable slow fall");
                // The earlier native map pass owns mH; Inventory may change mapStyle
                // later in this same UI frame. Exercise both directions at the real
                // production draw/CPU vertex boundary without running either full UI.
                Terraria.Main.playerInventory = true; Terraria.Main.EquipPage = 2;
                Terraria.Main.mapEnabled = true;
                Terraria.Main.screenWidth = 800; Terraria.Main.screenHeight = 720;
                player.buffType[0] = player.buffType[1] = player.buffType[2] = player.buffType[3] = player.buffType[4] = BuffID.Ironskin;
                var vertices = typeof(SpriteBatch).GetField("vertexInfo", instance)!;
                var position = typeof(GeneratedUtilityBuffUISystem).Assembly
                    .GetType("InfiniCrafterLocal.Common.UI.GeneratedUtilityBuffStatusView")!
                    .GetMethod("IconPosition", statics)!;
                foreach ((int capturedOffset, int currentStyle) in new[] { (0, 1), (120, 0) })
                {
                    mapHeight.SetValue(null, capturedOffset); Terraria.Main.mapStyle = currentStyle;
                    batch.Begin();
                    try
                    {
                        Equal(true, (bool)draw.Invoke(null, null)!, "same-frame inventory status callback completes");
                        Equal(1, (int)count.GetValue(batch)!, "one appended inventory icon");
                        object quad = ((Array)vertices.GetValue(batch)!).GetValue(0)!;
                        var actual = (Vector3)quad.GetType().GetField("Position0", instance)!.GetValue(quad)!;
                        var expected = (Point)position.Invoke(null, new object[] { 5, true, 800, 720, capturedOffset, currentStyle })!;
                        Equal(new Vector3(expected.X, expected.Y, 0), actual,
                            "inventory retains earlier native mH and current row count after mapStyle toggle to " + currentStyle);
                    }
                    finally { batch.End(); }
                }
            });
        }
        finally
        {
            Terraria.Localization.LanguageManager.Instance = savedLanguage;
            TextureAssets.Buff = savedAssets; Terraria.Main.spriteBatch = savedBatch;
            typeof(Terraria.Main).GetField("instance", statics)!.SetValue(null, savedMain);
            Terraria.Main.player[0] = savedPlayer; Terraria.Main.myPlayer = savedLocal; Terraria.Main.netMode = savedMode;
            Terraria.Main.dedServ = savedServer; Terraria.Main.gameMenu = savedMenu; Terraria.Main.hideUI = savedHide;
            Terraria.Main.playerInventory = savedInventory; Terraria.Main.ingameOptionsWindow = savedOptions;
            Terraria.Main.inFancyUI = savedFancy; Terraria.Main.mapFullscreen = savedMap;
            Terraria.Main.mouseX = savedMouseX; Terraria.Main.mouseY = savedMouseY;
            Terraria.Main.screenWidth = savedWidth; Terraria.Main.screenHeight = savedHeight;
            Terraria.Main.EquipPage = savedEquip; Terraria.Main.mapStyle = savedMapStyle;
            Terraria.Main.mapEnabled = savedMapEnabled; mapHeight.SetValue(null, savedMapHeight);
        }
    }
}
