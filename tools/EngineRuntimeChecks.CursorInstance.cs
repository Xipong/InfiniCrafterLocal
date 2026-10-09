using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
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
    // Baseline-compilable: new owner is activated only when present. Baseline reaches
    // the real cursor consumer and fails an output assertion, not a missing symbol.
    private static void CursorSourceShapeRefusesForeignSampleBeforeEmission()
    {
        const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
        Type owner = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedCursorItemPresentationSystem")
            ?? throw new InvalidOperationException("cursor presentation owner unavailable");
        MethodInfo patch = owner.GetMethod("PatchCursor", all)!;
        foreach (bool mutateTint in new[] { false, true })
        {
            using var native = Mono.Cecil.AssemblyDefinition.ReadAssembly(typeof(Terraria.Main).Assembly.Location);
            var method = native.MainModule.Types.Single(t => t.FullName == "Terraria.Main").Methods
                .Single(m => m.Name == "DrawInterface_40_InteractItemIcon");
            var source = mutateTint
                ? method.Body.Instructions.Last(i => i.Operand is Mono.Cecil.FieldReference f
                    && f.DeclaringType.FullName == "Terraria.GameContent.TextureAssets" && f.Name == "Item")
                : method.Body.Instructions.Single(i => i.Operand is Mono.Cecil.FieldReference f
                    && f.DeclaringType.FullName == "Terraria.ID.ContentSamples" && f.Name == "ItemsByType");
            var originalField = (Mono.Cecil.FieldReference)source.Operand;
            source.Operand = new Mono.Cecil.FieldReference(mutateTint ? "GlowMask" : "ForeignItemSamples",
                originalField.FieldType, originalField.DeclaringType);
            int before = method.Body.Instructions.Count;
            using var context = new MonoMod.Cil.ILContext(method);
            bool refused = false;
            try { patch.Invoke(null, new object[] { context }); }
            catch (TargetInvocationException error) when (error.InnerException is NotSupportedException) { refused = true; }
            Equal(true, refused, mutateTint ? "foreign final tint owner refused" : "foreign sample owner refused");
            Equal(before, method.Body.Instructions.Count, "foreign source refuses before partial emission");
        }
    }

    private static void GeneratedCursorUsesExactSelectedInstance()
    {
        const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
        T Shell<T>() where T : class { var x = (T)RuntimeHelpers.GetUninitializedObject(typeof(T)); GC.SuppressFinalize(x); return x; }
        Texture2D Texture(int w, int h) { var x = Shell<Texture2D>(); typeof(Texture2D).GetProperty("Width")!.SetValue(x, w); typeof(Texture2D).GetProperty("Height")!.SetValue(x, h); return x; }
        Asset<Texture2D> Asset(Texture2D x) { var a = Shell<Asset<Texture2D>>(); typeof(Asset<Texture2D>).GetField("ownValue", all)!.SetValue(a, x); typeof(Asset<Texture2D>).GetProperty("State")!.SetValue(a, AssetState.Loaded); return a; }
        var native = Texture(32, 32); var png = Texture(48, 48); var foreign = Texture(20, 20);
        var batch = Shell<SpriteBatch>();
        foreach (string n in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" }) {
            var f = typeof(SpriteBatch).GetField(n, all)!; f.SetValue(batch, Array.CreateInstance(f.FieldType.GetElementType()!, 32));
        }
        var count = typeof(SpriteBatch).GetField("numSprites", all)!;
        var queue = (Array)typeof(SpriteBatch).GetField("textureInfo", all)!.GetValue(batch)!;
        using var flush = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", all)!, (Action<SpriteBatch>)(_ => count.SetValue(batch, 0)));
        var cache = new RuntimeSpriteCache();
        var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", all)!.GetValue(cache)!;
        var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
        var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
        var light = typeof(Lighting).GetField("_activeEngine", all)!;
        var parent = PlayerDrawLayers.HeldItem; var child = new GeneratedHeldItemDrawLayer();
        var children = (IList)typeof(PlayerDrawLayer).GetProperty("ChildrenAfter", all)!.GetValue(parent)!;
        var oldChildren = new List<object>(); foreach (object x in children) oldChildren.Add(x);
        object? oldCache = sprites.GetValue(null), oldLight = light.GetValue(null);
        var oldMain = Terraria.Main.instance; var oldAssets = TextureAssets.Item; var oldPlayer = Terraria.Main.player[0];
        var oldBatch = Terraria.Main.spriteBatch; var oldMouseItem = Terraria.Main.mouseItem;
        bool oldServer = Terraria.Main.dedServ, oldHover = Terraria.Main.HoveringOverAnNPC;
        int oldMode = Terraria.Main.netMode, oldMyPlayer = Terraria.Main.myPlayer, oldMouseX = Terraria.Main.mouseX, oldMouseY = Terraria.Main.mouseY;
        float oldCursorScale = Terraria.Main.cursorScale;
        var cacheTime = typeof(Terraria.Main).GetField("_itemIconCacheTime", all)!; var oldCacheTime = cacheTime.GetValue(null);
        bool hadSample = ContentSamples.ItemsByType.TryGetValue(ItemID.WoodenSword, out Item? oldSample);
        bool hadForeign = ContentSamples.ItemsByType.TryGetValue(ItemID.CopperPickaxe, out Item? oldForeign);
        var savedFailures = new List<string>();
        ModSystem? owner = null;
        void Expect(bool good, string message) { if (!good) savedFailures.Add(message); }
        string path = System.IO.Path.Combine(Terraria.Program.SavePath, "cursor_selected_cpu.png");
        var data = GeneratedItemData.FromJson(System.IO.File.ReadAllText("tools/fixtures/current-world-1647275982-cursor.json"))
            ?? throw new InvalidOperationException("frozen current-world DTO rejected");
        var item = new Item(); item.SetDefaults(ItemID.WoodenSword);
        var g = new GeneratedItem(); typeof(ModType<Item>).GetProperty("Entity", all)!.SetValue(g, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, g); typeof(GeneratedItem).GetProperty("Data")!.SetValue(g, data);
        // Fixture-local asset declaration only; exact original DTO was parsed first.
        data.Visual.SpritePath = path; data.ApplyToItem(item);
        var p = new Player { whoAmI = 0, active = true, selectedItem = 0, position = new Vector2(160, 160), itemAnimation = 8, itemAnimationMax = 20, heldProj = -1, direction = 1, gravDir = 1f };
        p.inventory[0] = item; p.cursorItemIconEnabled = true; p.cursorItemIconText = "";
        var cursor = typeof(Terraria.Main).GetMethod("DrawInterface_40_InteractItemIcon", all)!;
        var tree = typeof(PlayerDrawLayer).GetMethod("DrawWithTransformationAndChildren", all)!;
        var reset = typeof(PlayerDrawLayer).GetMethod("ResetVisibility", all)!;
        void Cursor(string label, params Texture2D[] expected) {
            string before = data.ToJson();
            var fields = (item.noUseGraphic, item.damage, item.createTile, item.createWall, item.placeStyle, item.pick, item.scale, item.stack);
            count.SetValue(batch, 0); batch.Begin(); cursor.Invoke(Terraria.Main.instance, Array.Empty<object>());
            int n = (int)count.GetValue(batch)!; Expect(n == expected.Length, label + " count: " + n + " expected " + expected.Length);
            for (int i = 0; i < Math.Min(n, expected.Length); i++) Expect(ReferenceEquals(queue.GetValue(i), expected[i]), label + " texture/order " + i);
            batch.End();
            Expect(data.ToJson() == before, label + " keeps accepted definition");
            Expect(fields == (item.noUseGraphic, item.damage, item.createTile, item.createWall, item.placeStyle, item.pick, item.scale, item.stack), label + " keeps gameplay/parent snapshot fields");
        }
        void Held(string label, bool seed = false) {
            Item clone = item.Clone(); Expect(!ReferenceEquals(item, clone) && ReferenceEquals(clone.ModItem!.Item, clone), label + " real clone ownership");
            p.lastVisualizedSelectedItem = clone;
            var info = new PlayerDrawSet { drawPlayer = p, DrawDataCache = new List<DrawData>(), ItemLocation = new Vector2(180, 180), Position = p.position };
            object boxed = info; typeof(PlayerDrawSet).GetMethod("CopyBasicPlayerFields", all)!.Invoke(boxed, Array.Empty<object>()); info = (PlayerDrawSet)boxed;
            Expect(ReferenceEquals(info.heldItem, clone), label + " actual CopyBasicPlayerFields selects visualized clone");
            if (seed) info.DrawDataCache.Add(new DrawData(native, Vector2.Zero, native.Bounds, Color.White, 0f, Vector2.Zero, 1f, SpriteEffects.None, 0f));
            reset.Invoke(parent, new object[] { info }); object[] args = { info }; tree.Invoke(parent, args); info = (PlayerDrawSet)args[0];
            Expect(info.DrawDataCache.Count == (seed ? 2 : 1), label + " count");
            if (seed && info.DrawDataCache.Count > 0) Expect(ReferenceEquals(info.DrawDataCache[0].texture, native), label + " preserves earlier same texture");
            if (info.DrawDataCache.Count > 0) Expect(ReferenceEquals(info.DrawDataCache[^1].texture, png), label + " PNG");
        }
        try {
            typeof(Terraria.Main).GetField("instance", all)!.SetValue(null, Shell<Terraria.Main>());
            Terraria.Main.dedServ = false; Terraria.Main.netMode = 0; Terraria.Main.myPlayer = 0; Terraria.Main.player[0] = p;
            Terraria.Main.spriteBatch = batch; Terraria.Main.mouseItem = new Item(); Terraria.Main.mouseX = 200; Terraria.Main.mouseY = 200; Terraria.Main.cursorScale = 1f; Terraria.Main.HoveringOverAnNPC = false; cacheTime.SetValue(null, 0);
            TextureAssets.Item = (Asset<Texture2D>[])oldAssets.Clone(); TextureAssets.Item[24] = Asset(native); TextureAssets.Item[ItemID.CopperPickaxe] = Asset(foreign);
            ContentSamples.ItemsByType[24] = new Item(ItemID.WoodenSword); ContentSamples.ItemsByType[ItemID.CopperPickaxe] = new Item(ItemID.CopperPickaxe);
            light.SetValue(null, new Terraria.Graphics.Light.LightingEngine()); sprites.SetValue(null, cache); children.Clear(); children.Add(child);
            textures.Add(path, Activator.CreateInstance(record, png, 0f, 0L)!);
            var t = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedCursorItemPresentationSystem");
            if (t is not null) { owner = (ModSystem)Activator.CreateInstance(t)!; owner.Load(); }
            Held("primary swing real clone", seed: true);
            Cursor("dual-use hover", png);
            typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", all)!.Invoke(g, new object[] { data.RuntimeProgram.BindingForInput("alternate_use")! }); p.altFunctionUse = 2;
            Equal(215, item.createTile, "actual alternate projection is Campfire"); Held("alternate placement animation"); Cursor("alternate hover", png);
            item.color = new Color(80, 100, 120); Cursor("generated tint has two PNG passes, no native third", png, png); item.color = Color.Transparent;
            data.RuntimeProgram.ItemUse.HideUseGraphic = true; data.ApplyToItem(item); Cursor("authored held hide does not hide inventory cursor", png);
            data.RuntimeProgram.ItemUse.HideUseGraphic = false; data.ApplyToItem(item); Equal(false, item.noUseGraphic, "literal noUseGraphic retained");
            textures.Remove(path); Cursor("missing asset keeps native", native); textures.Add(path, Activator.CreateInstance(record, png, 0f, 0L)!);
            p.cursorItemIconID = ItemID.CopperPickaxe; Cursor("explicit foreign icon remains foreign", foreign);
            p.cursorItemIconID = ItemID.WoodenSword; Cursor("explicit same-type ID is not selected-instance authority", native); p.cursorItemIconID = 0;
            p.itemAnimation = 0; Cursor("idle hover still uses inventory PNG", png); p.itemAnimation = 8;
            p.inventory[0] = ContentSamples.ItemsByType[24]; Cursor("native selected item remains native", native); p.inventory[0] = item;
            // Nondual simple tool has the same proxy/sample cause; no identity/name router.
            data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Where(b => b.Input != "alternate_use").ToArray(); data.Gameplay.PickPower = 35; data.ApplyToItem(item); p.altFunctionUse = 0;
            Held("nondual simple tool swing"); Cursor("nondual simple tool hover", png);
            Expect(item.pick == 35 && !item.noUseGraphic, "tool gameplay and authored visibility unchanged");
        }
        finally {
            owner?.Unload(); children.Clear(); foreach (object x in oldChildren) children.Add(x); typeof(PlayerDrawLayer).GetProperty("Visible", all)!.SetValue(parent, true);
            textures.Clear(); sprites.SetValue(null, oldCache); light.SetValue(null, oldLight); TextureAssets.Item = oldAssets;
            typeof(Terraria.Main).GetField("instance", all)!.SetValue(null, oldMain); Terraria.Main.player[0] = oldPlayer; Terraria.Main.spriteBatch = oldBatch; Terraria.Main.mouseItem = oldMouseItem;
            Terraria.Main.dedServ = oldServer; Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldMyPlayer; Terraria.Main.mouseX = oldMouseX; Terraria.Main.mouseY = oldMouseY; Terraria.Main.cursorScale = oldCursorScale; Terraria.Main.HoveringOverAnNPC = oldHover; cacheTime.SetValue(null, oldCacheTime);
            if (hadSample) ContentSamples.ItemsByType[24] = oldSample!; else ContentSamples.ItemsByType.Remove(24);
            if (hadForeign) ContentSamples.ItemsByType[ItemID.CopperPickaxe] = oldForeign!; else ContentSamples.ItemsByType.Remove(ItemID.CopperPickaxe);
            cache.Dispose();
        }
        if (savedFailures.Count != 0) throw new InvalidOperationException(string.Join("\n", savedFailures));
    }
}
