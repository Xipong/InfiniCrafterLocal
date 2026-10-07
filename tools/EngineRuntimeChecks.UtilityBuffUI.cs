using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    // Reflection keeps this identical check compilable on the unmodified baseline:
    // its expected RED is the missing presentation adapter, not a compiler error.
    // CPU production seams only; no SpriteBatch/GPU/game-loop or socket claim.
    private static void GeneratedUtilityStatusUsesNativeIconsWithoutBuffMechanics()
    {
        Assembly product = typeof(InfiniCraftPlayer).Assembly;
        Type? view = product.GetType("InfiniCrafterLocal.Common.UI.GeneratedUtilityBuffStatusView");
        Equal(true, view is not null, "generated utility status adapter exists");
        Type? systemType = product.GetType("InfiniCrafterLocal.Common.UI.GeneratedUtilityBuffUISystem");
        Equal(true, systemType is not null, "generated utility interface system exists");
        const BindingFlags methods = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        MethodInfo build = view!.GetMethod("Build", methods)!;
        MethodInfo capture = typeof(InfiniCraftPlayer).GetMethod("CaptureGeneratedUtilityBuffPresentation", BindingFlags.Instance | BindingFlags.NonPublic)!;
        Equal(true, capture is not null, "read-only live presentation snapshot exists");
        object Get(object target, string name) => target.GetType().GetProperty(name)!.GetValue(target)!;
        object[] Statuses(object snapshot) => ((IEnumerable)build.Invoke(null, new object[] { snapshot, CultureInfo.InvariantCulture })!).Cast<object>().ToArray();
        object Snapshot(InfiniCraftPlayer generated) => capture!.Invoke(generated, null)!;
        object Status(object[] rows, string field) => rows.Single(row => Get(row, "Field").ToString() == field);
        string Tip(object row) => (string)Get(row, "Tooltip");
        int oldMode = Terraria.Main.netMode;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            WithPlayer((player, generated) =>
            {
                player.active = true;
                int[] beforeTypes = (int[])player.buffType.Clone(), beforeTimes = (int[])player.buffTime.Clone();
                var data = GeneratedItemData.Placeholder();
                data.Name = "exact accepted source";
                data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 360, JumpBoost = 1.5f };
                data.RuntimeProgram.ItemUse.Configured = true;
                data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
                    Id = "ui_use", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
                    UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = data.RuntimeProgram.ItemEntityId } },
                } };
                var item = new Item { type = ItemID.Gel, stack = 1 };
                var host = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, host);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
                data.ApplyToItem(item);
                // Names are not inputs to this mechanical presentation adapter.
                item.SetNameOverride("accepted Item.Name differs from DTO");
                host.UseItem(player);
                generated.PostUpdateEquips();
                Equal(1.5f, player.jumpSpeedBoost, "UI keeps exact authored jump boost");
                object savedSnapshot = Snapshot(generated);
                object[] rows = Statuses(savedSnapshot);
                Equal(1, rows.Length, "sole jump creates one UI status");
                object jump = Status(rows, "JumpBoost");
                Equal(BuffID.Featherfall, (int)Get(jump, "IconBuffType"), "jump borrows native Featherfall texture only");
                Equal("Generated jump boost", (string)Get(jump, "Label"), "own label, not Featherfall label");
                Equal(360, (int)Get(jump, "RemainingTicks"), "exact active duration");
                Equal(true, Tip(jump).Contains("+1.5 px/world tick") && Tip(jump).Contains("360 ticks (6 s)"), "hover actual jump and exact duration");
                object[] russian = ((IEnumerable)build.Invoke(null, new object[] { savedSnapshot, CultureInfo.GetCultureInfo("ru-RU") })!).Cast<object>().ToArray();
                object russianJump = Status(russian, "JumpBoost");
                Equal("Усиление прыжка", (string)Get(russianJump, "Label"), "Russian own status name");
                Equal(true, Tip(russianJump).Contains("+1,5 пикс./тик") && Tip(russianJump).Contains("6 с"), "Russian numeric effect and remaining duration");
                Equal(true, player.buffType.SequenceEqual(beforeTypes) && player.buffTime.SequenceEqual(beforeTimes), "no vanilla buffs were installed");
                Equal(false, player.slowFall, "Featherfall mechanics never applied");
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = 7f });
                object capped = Status(Statuses(Snapshot(generated)), "JumpBoost");
                Equal(true, Tip(capped).StartsWith("Current generated effect: +8 px/world tick", StringComparison.Ordinal), "canonical capped aggregate, not UI addition");
                Equal(true, Tip(capped).Contains("+7 px/world tick") && Tip(capped).Contains("60 ticks (1 s)"), "independent duration survives cap");
                Equal(360, (int)Get(jump, "RemainingTicks"), "snapshot does not alias refreshed storage");
                MethodInfo tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityBuff", BindingFlags.Instance | BindingFlags.NonPublic)!;
                for (int i = 0; i < 60; i++) tick.Invoke(generated, null);
                object afterExpiry = Status(Statuses(Snapshot(generated)), "JumpBoost");
                Equal(true, Tip(afterExpiry).StartsWith("Current generated effect: +1.5 px/world tick", StringComparison.Ordinal), "expired contribution no longer advertised");
                Equal(300, (int)Get(afterExpiry, "RemainingTicks"), "remaining live duration decremented");
                Equal(true, Tip(Status(Statuses(savedSnapshot), "JumpBoost")).Contains("360 ticks (6 s)"), "prior snapshot stays immutable after ticks");
                // Real native binary writer/reader seam retains current numeric state.
                using var stream = new MemoryStream();
                using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, leaveOpen: true))
                    typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(generated, new object[] { writer });
                stream.Position = 0;
                WithPlayer((_, receiver) => {
                    using var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, leaveOpen: true);
                    reader.ReadByte(); // Existing player-id envelope.
                    typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(receiver, new object[] { reader });
                    Equal(true, Tip(Status(Statuses(Snapshot(receiver)), "JumpBoost")).StartsWith("Current generated effect: +1.5 px/world tick", StringComparison.Ordinal), "network presentation retains actual numeric effect");
                    Equal(stream.Length, stream.Position, "existing utility state consumed completely");
                });
            });
            WithPlayer((player, generated) =>
            {
                player.active = true;
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60 });
                Equal(0, Statuses(Snapshot(generated)).Length, "neutral utility fields remain invisible");
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 90,
                    MiningSpeedMultiplier = MathF.BitIncrement(1f), EmitLightStrength = 0.5f, LightColorName = "cyan",
                    OreSenseRadiusTiles = 60, MovementSpeed = -0.25f, JumpBoost = 0.0005f, ManaRegen = 4, LifeRegen = 2 });
                object[] rows = Statuses(Snapshot(generated));
                Equal(7, rows.Length, "every active existing field has explicit UI mapping");
                foreach ((string field, int icon) in new[] {
                    ("MiningSpeedMultiplier", BuffID.Mining), ("EmitLightStrength", BuffID.Shine),
                    ("OreSenseRadiusTiles", BuffID.Spelunker), ("MovementSpeed", BuffID.Swiftness),
                    ("JumpBoost", BuffID.Featherfall), ("ManaRegen", BuffID.ManaRegeneration), ("LifeRegen", BuffID.Regeneration) })
                    Equal(icon, (int)Get(Status(rows, field), "IconBuffType"), field + " native icon");
                Equal(true, Tip(Status(rows, "MiningSpeedMultiplier")).Contains("1.0000001"), "no activity epsilon or display rounding to neutral");
                Equal(true, Tip(Status(rows, "MovementSpeed")).Contains("-0.25 moveSpeed factor"), "negative movement is reported literally");
                Equal(true, Tip(Status(rows, "EmitLightStrength")).Contains("0.5 RGB coefficient (cyan)"), "light strength and exact color token");
                Equal(true, Tip(Status(rows, "OreSenseRadiusTiles")).Contains("findTreasure = true") && !Tip(Status(rows, "OreSenseRadiusTiles")).Contains("60 tiles"), "ore flag does not invent runtime radius");
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 120, MovementSpeed = 0.25f });
                Equal(true, Tip(Status(Statuses(Snapshot(generated)), "MovementSpeed")).StartsWith("Current generated effect: +0 moveSpeed factor", StringComparison.Ordinal), "opposing contributions do not hide active field");
            });
            MethodInfo position = view.GetMethod("IconPosition", methods)!;
            MethodInfo append = view.GetMethod("GetAppendIndex", methods)!;
            Point Pos(int index, bool inventory, int height = 720, int mapStyle = 0) => (Point)position.Invoke(null, new object[] { index, inventory, 800, height, 0, mapStyle })!;
            Equal(new Point(32, 76), Pos(0, false), "native HUD grid origin");
            Equal(new Point(412, 76), Pos(10, false), "native HUD final first-row icon");
            Equal(new Point(32, 126), Pos(11, false), "native HUD wrapping row");
            Equal(new Point(716, 421), Pos(0, true), "native equipment buff grid origin");
            Equal(new Point(670, 421), Pos(5, true), "native equipment grid column wrapping");
            Equal(new Point(670, 421), Pos(3, true, 720, 1), "minimap changes native column height");
            Equal(4, (int)append.Invoke(null, new object[] { new[] { 1, 0, 0, 2 }, false })!, "HUD appends after highest occupied index, not count");
            Equal(2, (int)append.Invoke(null, new object[] { new[] { 1, 0, 0, 2 }, true })!, "equipment grid appends after compacted native count");
            var layers = new List<GameInterfaceLayer> {
                new LegacyGameInterfaceLayer("Vanilla: Resource Bars", () => true),
                new LegacyGameInterfaceLayer("Vanilla: Inventory", () => true),
                new LegacyGameInterfaceLayer("Vanilla: Mouse Text", () => true) };
            var system = (ModSystem)Activator.CreateInstance(systemType!)!;
            system.ModifyInterfaceLayers(layers);
            Equal("InfiniCrafterLocal: Generated Utility Status", layers[2].Name, "installed native owner precedes status layer");
            Equal((int)InterfaceScaleType.UI, (int)layers[2].ScaleType, "native UI scale owns drawing and input");
            var missingOwner = new List<GameInterfaceLayer> { new LegacyGameInterfaceLayer("Vanilla: Mouse Text", () => true) };
            system.ModifyInterfaceLayers(missingOwner);
            Equal(1, missingOwner.Count, "missing inspected owner does not guess another layer");
        }
        finally { Terraria.Main.netMode = oldMode; }
    }
}
