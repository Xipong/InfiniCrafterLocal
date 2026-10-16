using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
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
    // Real tML PlayerFrame/EquipLoader/EquipTexture dispatch. Use in-range fixture
    // slots and restore the registry; no registered mod or loaded graphics device.
    private sealed class BorrowedEquipmentSlots : IDisposable
    {
        private readonly Dictionary<EquipType, Dictionary<int, EquipTexture>> registry =
            (Dictionary<EquipType, Dictionary<int, EquipTexture>>)typeof(EquipLoader)
                .GetField("equipTextures", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        private readonly List<(EquipType Type, EquipTexture? Prior)> saved = new();
        private readonly Dictionary<int, Dictionary<EquipType, int>> itemSlots =
            (Dictionary<int, Dictionary<EquipType, int>>)typeof(EquipLoader)
                .GetField("idToSlot", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        private readonly List<(int Type, Dictionary<EquipType, int>? Prior)> savedItemSlots = new();
        private readonly Item? savedAir = ContentSamples.ItemsByType.GetValueOrDefault(0);
        internal readonly Item[] Items = new Item[3];
        internal BorrowedEquipmentSlots()
        {
            ContentSamples.ItemsByType[0] = new Item();
            GeneratedItem[] proxies = { new GeneratedHeadArmor(), new GeneratedBodyArmor(), new GeneratedLegsArmor() };
            string[] slots = { "head", "body", "legs" };
            for (int i = 0; i < 3; i++)
            {
                var type = (EquipType)i;
                var item = Items[i] = new Item { type = i + 1, stack = 1, defense = 7 };
                var data = GeneratedItemData.Placeholder(); data.Id = "equipment-" + slots[i];
                data.Armor.Enabled = true; data.Armor.Slot = slots[i]; data.Armor.Defense = 7;
                AttachItem(proxies[i], item, data);
                itemSlots.TryGetValue(item.type, out var oldSlots); savedItemSlots.Add((item.type, oldSlots));
                itemSlots[item.type] = new Dictionary<EquipType, int> { [type] = 1 };
                // Exactly the loader path used by ModItem.SetupContent, including
                // AutoDefaults/EquipLoader.SetSlot before the generated SetDefaults.
                typeof(ItemLoader).GetMethod("SetDefaults", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { item, false });
                var texture = new EquipTexture();
                typeof(EquipTexture).GetProperty("Item")!.SetValue(texture, proxies[i]);
                typeof(EquipTexture).GetProperty("Type")!.SetValue(texture, type);
                typeof(EquipTexture).GetProperty("Slot")!.SetValue(texture, 1);
                registry[type].TryGetValue(1, out var prior); saved.Add((type, prior));
                registry[type][1] = texture;
            }
        }
        public void Dispose()
        {
            foreach (var (type, prior) in saved)
                if (prior is null) registry[type].Remove(1); else registry[type][1] = prior;
            foreach (var (type, prior) in savedItemSlots)
                if (prior is null) itemSlots.Remove(type); else itemSlots[type] = prior;
            if (savedAir is null) ContentSamples.ItemsByType.Remove(0); else ContentSamples.ItemsByType[0] = savedAir;
        }
    }

    private static void EquipmentNeutralCarrierUsesNativeDisplayedSelection()
    {
        using var actors = new NativeActorState(); using var slots = new BorrowedEquipmentSlots();
        var player = new Player { active = true, heldProj = -1, isDisplayDollOrInanimate = true };
        for (int i = 0; i < 3; i++) player.armor[i] = slots.Items[i];
        player.statDefense = new Player.DefenseStat(); player.statDefense += 21;
        player.cHead = 11; player.cBody = 12; player.cLegs = 13;
        player.PlayerFrame();
        Equal((0, 0, 0), (player.head, player.body, player.legs), "actual PlayerFrame selects neutral appearance");
        Equal((1, 1, 1), (slots.Items[0].headSlot, slots.Items[1].bodySlot, slots.Items[2].legSlot), "inventory equip routing unchanged");
        Equal(21, (int)player.statDefense, "visual hook cannot change gameplay defense");
        Equal((11, 12, 13), (player.cHead, player.cBody, player.cLegs), "armor overlay dye identities unchanged");
        Equal(7, slots.Items[1].defense, "item defense unchanged");
        var collect = typeof(GeneratedEquipOverlayDrawLayerBase).GetMethod("CollectVisibleOverlays", BindingFlags.Static | BindingFlags.NonPublic)!;
        int Count(Player p) => ((IList)collect.Invoke(null, new object[] { p })!).Count;
        Equal(3, Count(player), "all generated functional badges survive neutral appearance");
        var ordinary = new[] { new Item { type = 1, stack = 1, headSlot = 2 }, new Item { type = 1, stack = 1, bodySlot = 2 }, new Item { type = 1, stack = 1, legSlot = 2 } };
        for (int i = 0; i < 3; i++) player.armor[i + 10] = ordinary[i];
        player.PlayerFrame();
        Equal((2, 2, 2), (player.head, player.body, player.legs), "ordinary vanity wins over generated armor");
        Equal(0, Count(player), "ordinary vanity suppresses generated badges");
        for (int i = 0; i < 3; i++) { player.armor[i] = ordinary[i]; player.armor[i + 10] = slots.Items[i]; }
        player.PlayerFrame();
        Equal((0, 0, 0), (player.head, player.body, player.legs), "generated vanity neutralizes only its own displayed carriers");
        Equal(3, Count(player), "generated vanity badges stay visible over ordinary functional armor");
        var other = new Player { active = true, heldProj = -1, isDisplayDollOrInanimate = true };
        for (int i = 0; i < 3; i++) other.armor[i] = ordinary[i];
        other.PlayerFrame();
        Equal((2, 2, 2), (other.head, other.body, other.legs), "second player ordinary armor is independent");
        for (int i = 0; i < 3; i++) player.armor[i + 10] = new Item();
        player.PlayerFrame();
        Equal((2, 2, 2), (player.head, player.body, player.legs), "next frame restores newly displayed ordinary armor");
        slots.Items[1].ModItem!.EquipFrameEffects(player, EquipType.Head);
        slots.Items[1].ModItem!.EquipFrameEffects(player, EquipType.Body);
        Equal((2, 2, 2), (player.head, player.body, player.legs), "wrong type or different visual slot untouched");
    }

    private static void EquipmentAccessoryLayersKeepMountsDyesAndVisibility()
    {
        void Near(float expected, float actual, string label) => Equal(true, Math.Abs(expected - actual) < .001f, label + $" ({expected} vs {actual})");
        using var actors = new NativeActorState(); using var cache = new BorrowedSpriteCache();
        Terraria.Main.dedServ = false; Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var player = new Player { active = true, heldProj = -1, body = 1, position = new Vector2(160, 240) };
        string[] mounts = { "back", "chest", "orbit", "waist", "shoulder" };
        var textures = new Texture2D[mounts.Length];
        for (int i = 0; i < mounts.Length; i++)
        {
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, $"synthetic_mount_{i}.png");
            textures[i] = CpuTexture(64, 32);
            cache.Textures.Add(path, Activator.CreateInstance(cache.Record, textures[i], 0f, 0L)!);
            var data = GeneratedItemData.Placeholder(); data.Id = "synthetic-mount-" + i;
            data.Accessory.Enabled = true; data.Visual.AccessoryMount = mounts[i]; data.Visual.EquipOverlayPath = path;
            var item = new Item { type = 1, stack = 1 }; AttachItem(new GeneratedItem(), item, data);
            player.armor[i + 3] = item; player.dye[i + 3] = new Item { dye = i + 11 };
        }
        PlayerDrawLayer[] children = { new GeneratedEquipOverlayAccessoryDrawLayer(), new GeneratedEquipOverlayFrontAccessoryDrawLayer() };
        var parents = new[] { PlayerDrawLayers.Wings, PlayerDrawLayers.Torso, PlayerDrawLayers.OffhandAcc };
        var restore = new List<(IList Children, object[] Prior)>();
        var visible = parents.Select(p => (p, p.Visible)).ToArray();
        var reset = typeof(PlayerDrawLayer).GetMethod("ResetVisibility", TestInstance)!;
        var drawTree = typeof(PlayerDrawLayer).GetMethod("DrawWithTransformationAndChildren", TestInstance)!;
        var savedBody = TextureAssets.ArmorBody; var torsoTexture = CpuTexture(40, 1120);
        try
        {
            TextureAssets.ArmorBody = (Asset<Texture2D>[])savedBody.Clone(); TextureAssets.ArmorBody[1] = CpuTextureAsset(torsoTexture);
            foreach (var parent in parents)
            foreach (string name in new[] { "ChildrenBefore", "ChildrenAfter" })
            {
                var list = (IList)typeof(PlayerDrawLayer).GetProperty(name, TestInstance)!.GetValue(parent)!;
                restore.Add((list, list.Cast<object>().ToArray())); list.Clear();
            }
            foreach (var child in children)
            {
                var position = child.GetDefaultPosition();
                var parent = position is PlayerDrawLayer.AfterParent after ? after.Parent : ((PlayerDrawLayer.BeforeParent)position).Parent;
                var list = (IList)typeof(PlayerDrawLayer).GetProperty(position is PlayerDrawLayer.AfterParent ? "ChildrenAfter" : "ChildrenBefore", TestInstance)!.GetValue(parent)!;
                list.Add(child);
            }
            Equal(true, ReferenceEquals(PlayerDrawLayers.Wings, ((PlayerDrawLayer.AfterParent)children[0].GetDefaultPosition()).Parent), "back mounts remain behind native skin/torso");
            Equal(true, ReferenceEquals(PlayerDrawLayers.OffhandAcc, ((PlayerDrawLayer.BeforeParent)children[1].GetDefaultPosition()).Parent), "front mounts follow torso subtree before hands");
            PlayerDrawSet Render(float shadow = 0f, bool hideEntire = false)
            {
                var info = new PlayerDrawSet { drawPlayer = player, Position = player.position, DrawDataCache = new List<DrawData>(),
                    DustCache = new List<int>(), GoreCache = new List<int>(), bodyVect = new Vector2(20, 28), colorArmorBody = Color.White, bodyGlowMask = -1, armGlowMask = -1, armorHidesHands = true,
                    playerEffect = (player.direction < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None) | (player.gravDir < 0 ? SpriteEffects.FlipVertically : SpriteEffects.None), shadow = shadow, hideEntirePlayer = hideEntire };
                foreach (var parent in parents)
                {
                    reset.Invoke(parent, new object[] { info }); object[] args = { info }; drawTree.Invoke(parent, args); info = (PlayerDrawSet)args[0];
                }
                return info;
            }
            foreach (int direction in new[] { -1, 1 })
            foreach (float gravity in new[] { -1f, 1f })
            {
                player.direction = direction; player.gravDir = gravity; player.bodyRotation = .25f;
                var info = Render();
                Equal(6, info.DrawDataCache.Count, "five badges and native torso exactly once");
                Texture2D[] expected = { textures[0], textures[2], torsoTexture, textures[1], textures[3], textures[4] };
                for (int i = 0; i < expected.Length; i++) Equal(true, ReferenceEquals(expected[i], info.DrawDataCache[i].texture), "native layer submission order " + i);
                foreach (DrawData badge in info.DrawDataCache.Where(d => !ReferenceEquals(d.texture, torsoTexture)))
                {
                    int index = Array.IndexOf(textures, badge.texture);
                    Equal(index + 11, badge.shader, "per-slot dye retained"); Equal(info.playerEffect, badge.effect, "direction/gravity flips retained");
                    Near(.25f, badge.rotation, "local torso rotation retained"); Near(18f / 64f, badge.scale.X, "whole-texture pixel fit retained");
                }
                // Orbit occupies index 2 of the whole set, not index 1 of the rear subset.
                DrawData orbit = info.DrawDataCache[1];
                float angle = MathHelper.PiOver2 + 2 * MathHelper.TwoPi / 5;
                Vector2 expectedOffset = new Vector2(16, 0).RotatedBy(angle); expectedOffset.Y *= gravity;
                Vector2 frameTop = new((int)(player.position.X - Terraria.Main.screenPosition.X - 20 + player.width / 2), (int)(player.position.Y - Terraria.Main.screenPosition.Y + player.height - 56 + 4));
                Vector2 expectedCenter = frameTop + info.bodyVect + (new Vector2(20, 52 - player.height * .5f) + expectedOffset - info.bodyVect).RotatedBy(player.bodyRotation);
                Near(expectedCenter.X, orbit.position.X, "global accessory orbit ordinal X"); Near(expectedCenter.Y, orbit.position.Y, "global accessory orbit ordinal Y");
                var untransformed = info.DrawDataCache.ToArray();
                info.rotation = .4f; info.rotationOrigin = new Vector2(10, 21);
                PlayerDrawLayers.DrawPlayer_TransformDrawData(ref info);
                for (int i = 0; i < info.DrawDataCache.Count; i++)
                    Near(untransformed[i].rotation + .4f, info.DrawDataCache[i].rotation, "native final full rotation exactly once");
            }
            // A seated/mounted torso applies this native transform before its
            // child layers. Rear badges must follow the same body displacement.
            player.bodyRotation = 0f;
            var neutral = Render();
            // Render() sets zero offset; exercise the actual native subtree with
            // a nonzero offset instead of only comparing local geometry.
            var shifted = new PlayerDrawSet { drawPlayer = player, Position = player.position, DrawDataCache = new List<DrawData>(),
                bodyVect = new Vector2(20, 28), colorArmorBody = Color.White, torsoOffset = 7f };
            reset.Invoke(parents[0], new object[] { shifted });
            object[] shiftedArgs = { shifted }; drawTree.Invoke(parents[0], shiftedArgs); shifted = (PlayerDrawSet)shiftedArgs[0];
            foreach (var texture in new[] { textures[0], textures[2] })
            {
                Vector2 oldPosition = neutral.DrawDataCache.Single(d => ReferenceEquals(d.texture, texture)).position;
                Vector2 newPosition = shifted.DrawDataCache.Single(d => ReferenceEquals(d.texture, texture)).position;
                Near(oldPosition.Y + 7f, newPosition.Y, "rear accessory follows native torso offset");
            }
            Vector2 readyOrbit = Render().DrawDataCache.Single(d => ReferenceEquals(d.texture, textures[2])).position;
            string chestPath = ((GeneratedItem)player.armor[4].ModItem!).Data.Visual.EquipOverlayPath;
            object chestTexture = cache.Textures[chestPath]!; cache.Textures.Remove(chestPath);
            Equal(readyOrbit, Render().DrawDataCache.Single(d => ReferenceEquals(d.texture, textures[2])).position, "missing front asset does not reflow rear orbit");
            cache.Textures[chestPath] = chestTexture;
            player.armor[14] = new Item { type = ItemID.AvengerEmblem, stack = 1, accessory = true };
            Equal(true, Render().DrawDataCache.Any(d => ReferenceEquals(d.texture, textures[1])), "nonvisual social item cannot erase functional badge");
            player.armor[14] = new Item();
            player.hideVisibleAccessory[4] = true;
            Equal(false, Render().DrawDataCache.Any(d => ReferenceEquals(d.texture, textures[1])), "hidden functional front badge suppressed");
            player.armor[14] = player.armor[4];
            Equal(true, Render().DrawDataCache.Any(d => ReferenceEquals(d.texture, textures[1])), "social front badge survives functional hide");
            player.armor[14] = player.armor[6];
            Equal(false, Render().DrawDataCache.Any(d => ReferenceEquals(d.texture, textures[1])), "hidden functional badge stays hidden under a different social badge");
            Equal(2, Render().DrawDataCache.Count(d => ReferenceEquals(d.texture, textures[3])), "functional and social accessories contribute independently");
            Equal(true, Render().DrawDataCache.Any(d => ReferenceEquals(d.texture, textures[3]) && d.shader == 12), "social badge uses paired native dye");
            player.armor[14] = player.armor[4];
            player.armor[14].shieldSlot = 1;
            player.compositeBackArm.enabled = true;
            Equal(false, Render().DrawDataCache.Any(d => ReferenceEquals(d.texture, textures[1])), "native visual incompatibility refuses social badge");
            player.compositeBackArm.enabled = false; player.armor[14].shieldSlot = -1;
            Equal(false, Render(hideEntire: true).DrawDataCache.Any(d => textures.Contains(d.texture)), "native whole-player hiding suppresses front and rear badges");
            player.invis = true;
            Equal(false, Render().DrawDataCache.Any(d => textures.Contains(d.texture)), "invisible player has no badges"); player.invis = false;
            Equal(false, Render(shadow: .5f).DrawDataCache.Any(d => textures.Contains(d.texture)), "shadow pass has no duplicate badges");
            player.dead = true;
            Equal(false, Render().DrawDataCache.Any(d => textures.Contains(d.texture)), "dead player has no badges");
        }
        finally
        {
            TextureAssets.ArmorBody = savedBody;
            foreach (var row in restore) { row.Children.Clear(); foreach (object old in row.Prior) row.Children.Add(old); }
            foreach (var (parent, wasVisible) in visible) typeof(PlayerDrawLayer).GetProperty("Visible", TestInstance)!.SetValue(parent, wasVisible);
        }
    }

    private static void EquipmentCarrierSheetsCoverNativeFrames()
    {
        (int Width, int Height) Size(string suffix)
        {
            byte[] png = System.IO.File.ReadAllBytes(System.IO.Path.Combine("ModSources", "InfiniCrafterLocal", "Assets", "GeneratedItem_" + suffix + ".png"));
            return (System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(png.AsSpan(16, 4)), System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(png.AsSpan(20, 4)));
        }
        var body = Size("Body"); var head = Size("Head"); var legs = Size("Legs");
        Equal((360, 224), body, "modern body carrier composite dimensions");
        Equal((40, 1120), head, "head carrier native dimensions"); Equal(head, legs, "legs carrier native dimensions");
        var framing = (bool[])typeof(ArmorIDs.Body.Sets).GetField("UsesNewFramingCode", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        bool oldFraming = framing[1];
        try
        {
            framing[1] = true;
            foreach (int skin in new[] { 0, 4 })
            foreach (int frame in Enumerable.Range(0, 20))
            foreach (var stretch in Enum.GetValues<Player.CompositeArmStretchAmount>())
            {
                var player = new Player { body = 1, skinVariant = skin };
                player.bodyFrame.Y = player.bodyFrame.Height * frame; player.legFrame.Y = player.legFrame.Height * frame;
                player.SetCompositeArmFront(true, stretch, .65f); player.SetCompositeArmBack(true, stretch, -.4f);
                object info = new PlayerDrawSet { drawPlayer = player };
                typeof(PlayerDrawSet).GetMethod("CreateCompositeData", TestInstance)!.Invoke(info, null);
                var native = (PlayerDrawSet)info;
                foreach (Rectangle rect in new[] { native.compTorsoFrame, native.compFrontArmFrame, native.compBackArmFrame, native.compFrontShoulderFrame, native.compBackShoulderFrame })
                    Equal(true, rect.X >= 0 && rect.Y >= 0 && rect.Right <= body.Width && rect.Bottom <= body.Height, "native composite source stays in transparent sheet");
                Equal(true, player.bodyFrame.Right <= head.Width && player.bodyFrame.Bottom <= head.Height, "native head animation source in bounds");
                Equal(true, player.legFrame.Right <= legs.Width && player.legFrame.Bottom <= legs.Height, "native leg animation source in bounds");
            }
        }
        finally { framing[1] = oldFraming; }
    }

    private static void EquipmentNeutralBaseDrawsNativeClothesAndHair()
    {
        using var actors = new NativeActorState(); using var slots = new BorrowedEquipmentSlots();
        var savedPlayers = TextureAssets.Players; var savedHair = TextureAssets.PlayerHair;
        var savedHairAlt = TextureAssets.PlayerHairAlt; var savedHead = TextureAssets.ArmorHead;
        var savedLeg = TextureAssets.ArmorLeg; var savedBody = TextureAssets.ArmorBodyComposite;
        var savedMain = Terraria.Main.instance;
        try
        {
            var main = (Terraria.Main)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Main));
            GC.SuppressFinalize(main);
            typeof(Terraria.Main).GetField("instance", BindingFlags.Static | BindingFlags.Public)!.SetValue(null, main);
            TextureAssets.Players = new Asset<Texture2D>[16, 20];
            for (int i = 0; i < TextureAssets.Players.GetLength(0); i++)
                for (int j = 0; j < TextureAssets.Players.GetLength(1); j++)
                    TextureAssets.Players[i, j] = CpuTextureAsset(CpuTexture(360, 1120));
            TextureAssets.PlayerHair = (Asset<Texture2D>[])savedHair.Clone();
            TextureAssets.PlayerHairAlt = (Asset<Texture2D>[])savedHairAlt.Clone();
            TextureAssets.PlayerHair[0] = CpuTextureAsset(CpuTexture(40, 1120));
            TextureAssets.PlayerHairAlt[0] = CpuTextureAsset(CpuTexture(40, 1120));
            TextureAssets.ArmorHead = (Asset<Texture2D>[])savedHead.Clone();
            TextureAssets.ArmorLeg = (Asset<Texture2D>[])savedLeg.Clone();
            TextureAssets.ArmorBodyComposite = (Asset<Texture2D>[])savedBody.Clone();
            var carrier = CpuTexture(360, 1120);
            TextureAssets.ArmorHead[1] = TextureAssets.ArmorLeg[1] = TextureAssets.ArmorBodyComposite[1] = CpuTextureAsset(carrier);
            foreach (int skin in new[] { 0, 4 })
            foreach (int frame in new[] { 0, 5, 10, 19 })
            {
                var player = new Player { active = true, heldProj = -1, skinVariant = skin, hair = 0, isDisplayDollOrInanimate = true };
                for (int i = 0; i < 3; i++) player.armor[i] = slots.Items[i];
                player.PlayerFrame(); player.bodyFrame.Y = player.bodyFrame.Height * frame; player.legFrame.Y = player.legFrame.Height * frame;
                var info = new PlayerDrawSet();
                info.BoringSetup(player, new List<DrawData>(), new List<int>(), new List<int>(), player.position, 0f, 0f, Vector2.Zero);
                Equal(false, info.armorHidesHands, "native draw setup retains hands");
                Equal(false, info.armorHidesArms, "native draw setup retains arms");
                PlayerDrawLayers.DrawPlayer_12_Skin(ref info);
                PlayerDrawLayers.DrawPlayer_13_Leggings(ref info);
                PlayerDrawLayers.DrawPlayer_17_Torso(ref info);
                PlayerDrawLayers.DrawPlayer_21_Head(ref info);
                PlayerDrawLayers.DrawPlayer_28_ArmOverItem(ref info);
                Equal(true, info.DrawDataCache.Count >= 8, "native base body parts remain present");
                Equal(false, info.DrawDataCache.Any(d => ReferenceEquals(d.texture, carrier)), "no carrier samples after neutral hook");
                Equal(true, info.DrawDataCache.Any(d => ReferenceEquals(d.texture, TextureAssets.PlayerHair[0].Value)), "native hair retained");
                foreach (DrawData draw in info.DrawDataCache)
                    if (draw.sourceRect is Rectangle rect)
                        Equal(true, rect.X >= 0 && rect.Y >= 0 && rect.Right <= draw.texture.Width && rect.Bottom <= draw.texture.Height, "native base source rect is valid");
                Console.WriteLine($"  equipment native base skin={skin} frame={frame} draws={info.DrawDataCache.Count}");
            }
        }
        finally { typeof(Terraria.Main).GetField("instance", BindingFlags.Static | BindingFlags.Public)!.SetValue(null, savedMain); TextureAssets.Players = savedPlayers; TextureAssets.PlayerHair = savedHair; TextureAssets.PlayerHairAlt = savedHairAlt; TextureAssets.ArmorHead = savedHead; TextureAssets.ArmorLeg = savedLeg; TextureAssets.ArmorBodyComposite = savedBody; }
    }
}
