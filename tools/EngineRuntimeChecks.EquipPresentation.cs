using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Real layer -> real DrawData -> installed player transform. Only the texture
    // is a CPU shell; no graphics device, asset generation, world or game loop.
    private static void EquipmentOverlayUsesPlayerDrawContract()
    {
        var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
        object? previous = sprites.GetValue(null);
        bool server = Terraria.Main.dedServ;
        Vector2 screen = Terraria.Main.screenPosition;
        var cache = new RuntimeSpriteCache();
        var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(cache)!;
        var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
        var drawMethod = typeof(GeneratedEquipOverlayDrawLayerBase).GetMethod("Draw", BindingFlags.Instance | BindingFlags.NonPublic)!;
        try
        {
            sprites.SetValue(null, cache);
            Terraria.Main.dedServ = false;
            Terraria.Main.screenPosition = new Vector2(33.25f, 47.75f);
            foreach (string slot in new[] { "head", "body", "legs", "accessory" })
            foreach (float grav in new[] { 1f, -1f })
            foreach (int direction in new[] { 1, -1 })
            foreach (int pixels in new[] { 8, 256, 1024 })
            {
                var texture = (Texture2D)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
                GC.SuppressFinalize(texture);
                typeof(Texture2D).GetProperty("Width")!.SetValue(texture, pixels);
                typeof(Texture2D).GetProperty("Height")!.SetValue(texture, pixels / 2);
                string path = System.IO.Path.Combine(Terraria.Program.SavePath, "equip_cpu.png");
                textures[path] = Activator.CreateInstance(record, texture, 0f, 0L)!;
                var player = new Player { active = true, position = new Vector2(200, 300), gravDir = grav, direction = direction,
                    fullRotation = 0.7f, headRotation = 0.2f, bodyRotation = -0.3f, legRotation = 0.4f,
                    headPosition = new Vector2(2, 3), bodyPosition = new Vector2(4, 5), legPosition = new Vector2(6, 7) };
                player.bodyFrame = player.legFrame = new Rectangle(0, 56, 40, 56);
                var item = EquipPresentationItem(slot);
                ((GeneratedItem)item.ModItem!).Data.Visual.EquipOverlayPath = path;
                int index = slot switch { "head" => 0, "body" => 1, "legs" => 2, _ => 3 };
                player.armor[index] = item;
                player.dye[3].dye = 43;
                var info = new PlayerDrawSet { drawPlayer = player, Position = new Vector2(210.5f, 320.5f),
                    headVect = new Vector2(20, 22.4f), bodyVect = new Vector2(20, 28), legVect = new Vector2(20, 42),
                    helmetOffset = new Vector2(1, 2), legsOffset = new Vector2(3, 4),
                    colorArmorHead = new Color(31, 41, 51, 61), colorArmorBody = new Color(71, 81, 91, 101), colorArmorLegs = new Color(111, 121, 131, 141),
                    cHead = 11, cBody = 22, cLegs = 33, rotation = 0.6f, rotationOrigin = new Vector2(9, 37),
                    playerEffect = (direction < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None) | (grav < 0 ? SpriteEffects.FlipVertically : SpriteEffects.None),
                    DrawDataCache = new List<DrawData>(), DustCache = new List<int>(), GoreCache = new List<int>() };
                GeneratedEquipOverlayDrawLayerBase layer = slot switch { "head" => new GeneratedEquipOverlayHeadDrawLayer(), "body" => new GeneratedEquipOverlayBodyDrawLayer(), "legs" => new GeneratedEquipOverlayLegsDrawLayer(), _ => new GeneratedEquipOverlayAccessoryDrawLayer() };
                object[] args = { info };
                drawMethod.Invoke(layer, args);
                info = (PlayerDrawSet)args[0];
                Equal(1, info.DrawDataCache.Count, "one loaded equipment overlay");
                DrawData actual = info.DrawDataCache[0];
                float rotation = slot switch { "head" => player.headRotation, "legs" => player.legRotation, _ => player.bodyRotation };
                Equal(rotation, actual.rotation, "part rotation only before vanilla transform");
                float target = slot switch { "head" => 25, "legs" => 27, "accessory" => 18, _ => 31 };
                Equal(Math.Min(target, pixels * 1.25f), actual.scale.X * pixels, "texture resolution cannot defeat target extent");
                Equal(slot switch { "head" => 11, "body" => 22, "legs" => 33, _ => 43 }, actual.shader, "exact armor/accessory dye index");
                Equal(slot switch { "head" => info.colorArmorHead, "legs" => info.colorArmorLegs, _ => info.colorArmorBody }, actual.color, "prepared armor tint retains immune alpha");
                Equal((int)info.playerEffect, (int)actual.effect, "facing/gravity effects preserved");
                Vector2 pivot = slot switch { "head" => info.headVect, "legs" => info.legVect, _ => info.bodyVect };
                Vector2 part = slot switch { "head" => player.headPosition + info.helmetOffset, "legs" => player.legPosition + info.legsOffset, _ => player.bodyPosition };
                Vector2 top = new Vector2((int)(info.Position.X - Terraria.Main.screenPosition.X - 20 + player.width / 2),
                    (int)(info.Position.Y - Terraria.Main.screenPosition.Y + player.height - 56 + 4));
                float offsetY = (slot switch { "head" => -19, "legs" => 14, "accessory" => 16, _ => -2 }) * grav;
                Vector2 centerInFrame = new Vector2(20, 56 - 4 - player.height * 0.5f + offsetY);
                Vector2 expected = top + part + pivot + Vector2.Transform(centerInFrame - pivot, Matrix.CreateRotationZ(rotation));
                NearEquip(expected, actual.position, "part anchor and local pivot");
                PlayerDrawLayers.DrawPlayer_TransformDrawData(ref info);
                actual = info.DrawDataCache[0];
                Vector2 globalPivot = info.Position - Terraria.Main.screenPosition + info.rotationOrigin;
                NearEquip(globalPivot + Vector2.Transform(expected - globalPivot, Matrix.CreateRotationZ(info.rotation)), actual.position, "installed transform applied once");
                Equal(rotation + info.rotation, actual.rotation, "no double fullRotation");
                // Shared renderer scaling belongs to the installed outer pass too.
                Vector2 scalePivot = info.Position + player.Size * new Vector2(0.5f, 1f) - Terraria.Main.screenPosition;
                Vector2 beforeScale = actual.position;
                float beforeScaleValue = actual.scale.X;
                PlayerDrawLayers.DrawPlayer_ScaleDrawData(ref info, 1.5f);
                NearEquip(scalePivot + (beforeScale - scalePivot) * 1.5f, info.DrawDataCache[0].position, "installed player scale applied once");
                Equal(beforeScaleValue * 1.5f, info.DrawDataCache[0].scale.X, "installed player scale retained");
                if (slot == "accessory")
                {
                    // Same dye cell serves functional and social partners. Compare
                    // the actual installed dye consumer, not a UI-relative index.
                    var dyeMethod = typeof(Player).GetMethod("UpdateItemDye", BindingFlags.Instance | BindingFlags.NonPublic)!;
                    for (int cell = 3; cell < 8; cell++)
                    foreach (bool social in new[] { false, true })
                    {
                        player.armor[index] = new Item();
                        int equipCell = cell + (social ? 10 : 0);
                        player.armor[equipCell] = item;
                        player.dye[cell].dye = cell * 7;
                        item.handOnSlot = 1;
                        dyeMethod.Invoke(player, new object[] { !social, false, item, player.dye[cell] });
                        info.DrawDataCache.Clear(); args[0] = info; drawMethod.Invoke(layer, args);
                        Equal(player.cHandOn, info.DrawDataCache[0].shader, $"installed dye consumer cell {cell}, social {social}");
                        player.armor[equipCell] = new Item();
                    }
                    player.armor[index] = item;
                    player.dye = Array.Empty<Item>();
                    info.DrawDataCache.Clear(); args[0] = info; drawMethod.Invoke(layer, args);
                    Equal(0, info.DrawDataCache[0].shader, "missing accessory dye never borrows chest dye");
                }
                foreach (string hidden in new[] { "invis", "dead", "inactive", "shadow" })
                {
                    info.DrawDataCache.Clear();
                    player.invis = hidden == "invis"; player.dead = hidden == "dead"; player.active = hidden != "inactive"; info.shadow = hidden == "shadow" ? 0.5f : 0;
                    args[0] = info; drawMethod.Invoke(layer, args);
                    Equal(0, info.DrawDataCache.Count, "hidden equipment: " + hidden);
                }
            }
        }
        finally { sprites.SetValue(null, previous); Terraria.Main.dedServ = server; Terraria.Main.screenPosition = screen; }
    }

    private static Item EquipPresentationItem(string slot)
    {
        var item = new Item { type = 1, stack = 1 };
        var generated = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
        generated.Data.Accessory.Enabled = slot == "accessory";
        generated.Data.Armor.Enabled = slot != "accessory";
        generated.Data.Armor.Slot = slot;
        if (slot == "head") item.headSlot = 1;
        if (slot == "body") item.bodySlot = 1;
        if (slot == "legs") item.legSlot = 1;
        return item;
    }

    private static void NearEquip(Vector2 expected, Vector2 actual, string message)
    {
        if (Vector2.Distance(expected, actual) > 0.0001f)
            throw new InvalidOperationException($"{message}: expected {expected}, actual {actual}");
    }

    private static void EquipmentOverlayUsesVanityAndSlotVisibility()
    {
        bool menu = Terraria.Main.gameMenu;
        int mode = Terraria.Main.GameMode;
        var collect = typeof(GeneratedEquipOverlayDrawLayerBase).GetMethod("CollectVisibleOverlays", BindingFlags.Static | BindingFlags.NonPublic)!;
        try
        {
            Terraria.Main.gameMenu = false;
            Terraria.Main.GameMode = 0;
            var player = new Player { active = true };
            int Count() => ((IList)collect.Invoke(null, new object[] { player })!).Count;
            player.armor[3] = EquipPresentationItem("accessory");
            player.hideVisibleAccessory[3] = true;
            Equal(0, Count(), "functional hide toggle");
            player.armor[13] = EquipPresentationItem("accessory");
            // Installed vanilla social-slot call does not take the functional hide flag.
            var visible = new Item { type = 1, stack = 1, handOnSlot = 1 };
            player.UpdateVisibleAccessories(visible, invisible: true, slot: 3);
            Equal(-1, player.handon, "vanilla hidden functional slot");
            player.UpdateVisibleAccessory(13, visible);
            Equal(1, player.handon, "vanilla social slot remains visible");
            Equal(1, Count(), "social overlay ignores functional hide toggle");
            player.armor[3] = player.armor[13] = new Item();
            foreach (int slot in new[] { 8, 9, 18, 19 })
            {
                player.armor[slot] = EquipPresentationItem("accessory");
                Equal(false, player.IsItemSlotUnlockedAndUsable(slot), "installed locked slot");
                Equal(0, Count(), "locked slot overlay suppressed");
                Terraria.Main.GameMode = 2; player.extraAccessory = true;
                Equal(true, player.IsItemSlotUnlockedAndUsable(slot), "installed unlocked slot");
                Equal(1, Count(), "unlocked slot overlay visible");
                Terraria.Main.GameMode = 0; player.extraAccessory = false; player.armor[slot] = new Item();
            }
            player.armor[0] = EquipPresentationItem("head");
            player.armor[10] = new Item { type = 1, stack = 1 }; // not a head equip
            Equal(1, Count(), "non-head social item cannot replace head");
            player.armor[10].headSlot = 2;
            Equal(0, Count(), "real vanilla social head replaces generated head");
            player.armor[10] = EquipPresentationItem("head");
            Equal(1, Count(), "generated social head selected once");
        }
        finally { Terraria.Main.gameMenu = menu; Terraria.Main.GameMode = mode; }
    }
}
