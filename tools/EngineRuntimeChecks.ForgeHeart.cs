using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Buffers.Binary;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ForgeHeartNameGradientPreservesNativeText()
    {
        const BindingFlags hidden = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var handlersField = typeof(Terraria.UI.Chat.ChatManager).GetField("_handlers", BindingFlags.Static | BindingFlags.NonPublic)!;
        object oldHandlers = handlersField.GetValue(null)!;
        float oldTime = Terraria.Main.GlobalTimeWrappedHourly;
        var core = new InfiniCore();
        var item = new Item { type = ItemID.FallenStar, stack = 1 };
        typeof(ModType<Item>).GetProperty("Entity", hidden)!.SetValue(core, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, core);
        TooltipLine Line(string mod, string name, string text) => (TooltipLine)Activator.CreateInstance(
            typeof(TooltipLine), hidden, null, new object[] { mod, name, text }, null)!;
        try
        {
            handlersField.SetValue(null, Activator.CreateInstance(oldHandlers.GetType()));
            Terraria.UI.Chat.ChatManager.Register<Terraria.GameContent.UI.Chat.ColorTagHandler>("c", "color");
            foreach (string name in new[] { "Сердце кузни", "Forge Heart", "Сердце кузни ✦", "Forge Hea\u0301rt" })
            {
                item.SetNameOverride(name);
                string[] phased = new string[3];
                int phaseIndex = 0;
                foreach (float time in new[] { 0f, 1f, 4f })
                {
                    Terraria.Main.GlobalTimeWrappedHourly = time;
                    var nativeName = Line("Terraria", "ItemName", name);
                    var description = Line("Terraria", "Tooltip0", "unchanged core description");
                    var foreignName = Line("OtherMod", "ItemName", "foreign name");
                    var lines = new List<TooltipLine> { description, nativeName, foreignName };
                    core.ModifyTooltips(lines);
                    Equal(true, nativeName.Text.StartsWith("[c/", StringComparison.Ordinal), "native name has gradient color tags");
                    var snippets = Terraria.UI.Chat.ChatManager.ParseMessage(nativeName.Text, Color.White);
                    var text = new System.Text.StringBuilder();
                    var colors = new HashSet<Color>();
                    foreach (var snippet in snippets) { text.Append(snippet.Text); colors.Add(snippet.Color); }
                    Equal(name, text.ToString(), "actual native parser preserves all localized Unicode glyphs");
                    Equal(true, colors.Count >= 3, "multiple simultaneous gradient colors, not uniform rarity tint");
                    Equal(name, item.Name, "saved item name stays plain");
                    Equal(1, item.stack, "tooltip does not change stack");
                    Equal("unchanged core description", description.Text, "description untouched");
                    Equal("foreign name", foreignName.Text, "other mod name untouched");
                    Equal(true, ReferenceEquals(description, lines[0]) && ReferenceEquals(nativeName, lines[1]) && ReferenceEquals(foreignName, lines[2]), "tooltip line order and identity preserved");
                    phased[phaseIndex++] = nativeName.Text;
                }
                Equal(false, phased[0] == phased[1], "gradient flows with native UI clock");
                Equal(phased[0], phased[2], "exact four-second color loop");
            }
            var tagged = Line("Terraria", "ItemName", "[c/ffdd77:Forge Heart]");
            core.ModifyTooltips(new List<TooltipLine> { tagged });
            Equal("[c/ffdd77:Forge Heart]", tagged.Text, "preexisting rich text is not nested or corrupted");
            core.ModifyTooltips(new List<TooltipLine>());
        }
        finally
        {
            Terraria.Main.GlobalTimeWrappedHourly = oldTime;
            handlersField.SetValue(null, oldHandlers);
        }
    }

    private static void ForgeHeartNativeAnimationUsesAtlas()
    {
        int type = ItemID.FallenStar;
        var core = new InfiniCore();
        var item = new Item { type = type, stack = 1 };
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)!.SetValue(core, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, core);
        var oldAnimations = Terraria.Main.itemAnimations;
        bool oldSoul = ItemID.Sets.AnimatesAsSoul[type];
        bool oldGravity = ItemID.Sets.ItemNoGravity[type];
        var registered = Terraria.Main.itemAnimationsRegistered;
        int[] oldRegistered = registered.ToArray();
        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
        GC.SuppressFinalize(texture);
        try
        {
            Terraria.Main.itemAnimations = new DrawAnimation[oldAnimations.Length];
            ItemID.Sets.AnimatesAsSoul[type] = false;
            core.SetStaticDefaults();
            Equal(true, Terraria.Main.itemAnimations[type] is DrawAnimationVertical, "core registers a real native vertical animation");
            var animation = (DrawAnimationVertical)Terraria.Main.itemAnimations[type];
            Equal(24, animation.FrameCount, "24 real shimmer phases");
            Equal(5, animation.TicksPerFrame, "2-second cycle at 60 world ticks");
            Equal(true, ItemID.Sets.AnimatesAsSoul[type], "native world and inventory animation enabled");
            Equal(oldGravity, ItemID.Sets.ItemNoGravity[type], "art does not change item gravity");
            Equal(true, registered.Contains(type), "native animation update roster contains item");
            byte[] png = File.ReadAllBytes("ModSources/InfiniCrafterLocal/Assets/InfiniCore.png");
            Equal(48, BinaryPrimitives.ReadInt32BigEndian(png.AsSpan(16, 4)), "atlas width");
            Equal(1200, BinaryPrimitives.ReadInt32BigEndian(png.AsSpan(20, 4)), "24 cells with 2px native row padding");
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 48);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 1200);
            for (int tick = 0; tick < 120; tick++)
            {
                Rectangle expected = new(0, (tick / 5) * 50, 48, 48);
                Equal(expected, animation.GetFrame(texture), "native frame at tick " + tick);
                Equal(expected, animation.GetFrame(texture, tick), "native overridden frame at tick " + tick);
                animation.Update();
            }
            Equal(0, animation.Frame, "loop returns exactly to first frame");
            Equal(0, animation.FrameCounter, "loop leaves no residual frame counter");
            core.SetDefaults();
            Equal(28, item.width, "collision width unchanged");
            Equal(28, item.height, "collision height unchanged");
            Equal(1, item.maxStack, "stack contract unchanged");
            Equal(false, item.consumable, "key not consumed");
            Equal(20, item.useTime, "use timing unchanged");
            Equal(20, item.useAnimation, "use animation unchanged");
        }
        finally
        {
            Terraria.Main.itemAnimations = oldAnimations;
            ItemID.Sets.AnimatesAsSoul[type] = oldSoul;
            ItemID.Sets.ItemNoGravity[type] = oldGravity;
            registered.Clear();
            registered.AddRange(oldRegistered);
        }
    }
}
