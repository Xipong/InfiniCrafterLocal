#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    private static void NotificationInputAndLocalization()
    {
        var system = new CraftNotificationUISystem();
        var mouse = (Terraria.Main.mouseLeft, Terraria.Main.mouseLeftRelease, Terraria.Main.mouseRight, Terraria.Main.mouseRightRelease, Terraria.Main.mouseX, Terraria.Main.mouseY);
        try
        {
            var box = CraftNotificationUISystem.NotificationBounds(800, 600, true);
            Equal(new Rectangle(190, 514, 420, 66), box, "input and draw share exact notification bounds");
            Terraria.Main.mouseX = box.Left - 1; Terraria.Main.mouseY = box.Center.Y;
            Terraria.Main.mouseLeft = Terraria.Main.mouseLeftRelease = Terraria.Main.mouseRight = Terraria.Main.mouseRightRelease = true;
            Equal(false, CraftNotificationUISystem.ReserveNotificationMouse(box, false), "click outside banner belongs to native inventory");
            Equal(true, Terraria.Main.mouseLeft && Terraria.Main.mouseRight, "outside buttons unchanged");
            Terraria.Main.mouseX = box.Center.X;
            Equal(false, CraftNotificationUISystem.ReserveNotificationMouse(box, true), "native interface-ignore guard keeps banner inert");
            Equal(true, CraftNotificationUISystem.ReserveNotificationMouse(box, false), "hovered banner reserves before native inventory");
            Equal(false, Terraria.Main.mouseLeft || Terraria.Main.mouseLeftRelease || Terraria.Main.mouseRight || Terraria.Main.mouseRightRelease,
                "both native click and hold paths are suppressed");
            Equal(false, CraftNotificationUISystem.ReserveNotificationMouse(box, false), "second reservation cannot replace original click");
            WithPlayer((player, _) => {
                using var actors = new NativeActorState();
                Terraria.Main.myPlayer = 0;
                Terraria.Main.player[0] = player; player.whoAmI = 0;
                var oldMouseItem = Terraria.Main.mouseItem;
                try
                {
                    player.inventory[0] = new Item(ItemID.Wood, 5); Terraria.Main.mouseItem = new Item();
                    ItemSlot.LeftClick(player.inventory, ItemSlot.Context.InventoryItem, 0);
                    ItemSlot.RightClick(player.inventory, ItemSlot.Context.InventoryItem, 0);
                    Equal(5, player.inventory[0].stack, "actual native slot cannot mutate behind notification");
                    Equal(true, Terraria.Main.mouseItem.IsAir, "native input phase leaves cursor empty");
                }
                finally { Terraria.Main.mouseItem = oldMouseItem; }
            });
            Equal(true, CraftNotificationUISystem.RestoreNotificationMouse(), "notification restores its original click after native phase");
            Equal(true, Terraria.Main.mouseLeft && Terraria.Main.mouseLeftRelease && Terraria.Main.mouseRight && Terraria.Main.mouseRightRelease,
                "notification receives exact captured buttons");
            Equal(false, CraftNotificationUISystem.RestoreNotificationMouse(), "reservation is consumed once");
            CraftNotificationUISystem.ReserveNotificationMouse(box, false);
            system.OnWorldUnload();
            Equal(true, Terraria.Main.mouseLeft && Terraria.Main.mouseRight, "world teardown restores reserved buttons");
            Equal(false, CraftNotificationUISystem.RestoreNotificationMouse(), "teardown leaves no stale reservation");
            CraftNotificationUISystem.ReserveNotificationMouse(box, false); system.Unload();
            Equal(true, Terraria.Main.mouseLeft && Terraria.Main.mouseRight, "mod teardown restores reserved buttons");
            var layers = new List<GameInterfaceLayer> {
                new LegacyGameInterfaceLayer("InfiniCrafterLocal: Station Modal Input", () => true),
                new LegacyGameInterfaceLayer("Vanilla: Inventory", () => true),
                new LegacyGameInterfaceLayer("InfiniCrafterLocal: Inventory Craft Station", () => true),
                new LegacyGameInterfaceLayer("Vanilla: Mouse Text", () => true),
            };
            system.ModifyInterfaceLayers(layers);
            Equal(true, layers.FindIndex(l => l.Name == "InfiniCrafterLocal: Notification Input") < layers.FindIndex(l => l.Name == "InfiniCrafterLocal: Station Modal Input"),
                "topmost notification reserves before station so nested restoration cannot click underlying station");
            Equal(true, layers.FindIndex(l => l.Name == "InfiniCrafterLocal: Craft Notifications") > layers.FindIndex(l => l.Name == "InfiniCrafterLocal: Inventory Craft Station"),
                "notification restores after underlying station");
        }
        finally
        {
            system.Unload();
            (Terraria.Main.mouseLeft, Terraria.Main.mouseLeftRelease, Terraria.Main.mouseRight, Terraria.Main.mouseRightRelease, Terraria.Main.mouseX, Terraria.Main.mouseY) = mouse;
        }
        WithForgePresentationLanguages(locale => {
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            string root = Environment.GetEnvironmentVariable("INFINI_FORGE_LOCALIZATION_DIR") ?? Path.Combine("ModSources", "InfiniCrafterLocal", "Localization");
            string filename = locale + "_Mods.InfiniCrafterLocal.CraftNotifications.hjson";
            Equal(true, Terraria.ModLoader.LocalizationLoader.TryGetCultureAndPrefixFromPath(filename, out _, out string? prefix), "native notification localization prefix");
            var texts = (Dictionary<string, LocalizedText>)typeof(LanguageManager).GetField("_localizedTexts", instance)!.GetValue(LanguageManager.Instance)!;
            using var json = JsonDocument.Parse(Hjson.HjsonValue.Load(Path.Combine(root, filename)).ToString());
            foreach (var row in json.RootElement.EnumerateObject())
            {
                string key = prefix + "." + row.Name;
                texts[key] = (LocalizedText)Activator.CreateInstance(typeof(LocalizedText), instance, null, new object[] { key, row.Value.GetString()! }, null)!;
            }
            foreach (var kind in new[] { InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded, InfiniCraftPlayer.CraftLaneOutcomeKind.Failed, InfiniCraftPlayer.CraftLaneOutcomeKind.Cancelled, InfiniCraftPlayer.CraftLaneOutcomeKind.TimedOut })
            {
                string label = CraftNotificationUISystem.OutcomeLabel(kind);
                Equal(false, label.StartsWith("Mods.", StringComparison.Ordinal), "every outcome has actual native lookup " + locale);
                if (locale == "ru-RU") Equal(false, label == kind.ToString(), "Russian outcome does not leak enum " + kind);
            }
            Equal(locale == "ru-RU" ? "Завершено" : "Completed", CraftNotificationUISystem.OutcomeLabel(InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded), "localized completion label");
            string title = CraftNotificationUISystem.Text("Title", 2, CraftNotificationUISystem.OutcomeLabel(InfiniCraftPlayer.CraftLaneOutcomeKind.Failed), 3);
            Equal(true, title.Contains(locale == "ru-RU" ? "Ошибка" : "Failed", StringComparison.Ordinal), "localized label reaches actual title");
        });
    }
}
