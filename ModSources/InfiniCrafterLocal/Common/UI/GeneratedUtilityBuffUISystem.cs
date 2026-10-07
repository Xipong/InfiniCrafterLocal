#nullable enable
using System;
using System.Collections.Generic;
using System.Linq.Expressions;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.GameInput;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class GeneratedUtilityBuffUISystem : ModSystem
{
    // Read the installed native map pass's frame-owned offset, not inputs that
    // Inventory can mutate later in the same frame. Bind once; no reflection in Draw.
    private static readonly Func<int> NativeInventoryTopOffset =
        Expression.Lambda<Func<int>>(Expression.Field(null, typeof(Main), "mH")).Compile();
    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        // Installed tML has no Vanilla: Buffs layer. Its native producers are
        // Resource Bars (HUD) and Inventory (equipment page 2); draw after both.
        int owner = layers.FindIndex(layer => layer.Name == "Vanilla: Inventory");
        if (owner < 0) return;
        layers.Insert(owner + 1, new LegacyGameInterfaceLayer(
            "InfiniCrafterLocal: Generated Utility Status", DrawStatuses, InterfaceScaleType.UI));
    }

    private static bool DrawStatuses()
    {
        if (Main.dedServ || Main.netMode == NetmodeID.Server || Main.gameMenu
            || Main.hideUI || Main.ingameOptionsWindow || Main.inFancyUI || Main.mapFullscreen)
            return true;
        Player player = Main.LocalPlayer;
        if (player is null || !player.active || (Main.playerInventory && Main.EquipPage != 2))
            return true;
        GeneratedUtilityBuffPresentation snapshot = player.GetModPlayer<InfiniCraftPlayer>()
            .CaptureGeneratedUtilityBuffPresentation();
        IReadOnlyList<GeneratedUtilityBuffStatus> statuses = GeneratedUtilityBuffStatusView.Build(
            snapshot, Language.ActiveCulture.CultureInfo);
        int append = GeneratedUtilityBuffStatusView.GetAppendIndex(player.buffType, Main.playerInventory);
        int inventoryOffset = Main.playerInventory ? NativeInventoryTopOffset() : 0;
        foreach (GeneratedUtilityBuffStatus status in statuses)
        {
            var asset = TextureAssets.Buff[status.IconBuffType];
            if (asset is null || !asset.IsLoaded) { append++; continue; }
            Texture2D texture = asset.Value;
            Point point = GeneratedUtilityBuffStatusView.IconPosition(append++, Main.playerInventory,
                Main.screenWidth, Main.screenHeight, inventoryOffset, Main.mapStyle);
            var bounds = new Rectangle(point.X, point.Y, texture.Width, texture.Height);
            bool hovered = !PlayerInput.IgnoreMouseInterface && bounds.Contains(Main.mouseX, Main.mouseY);
            Color color = Color.White * (hovered ? 1f : (Main.playerInventory ? 0.65f : 0.4f));
            // GameInterfaceLayer owns Begin/End and UIScaleMatrix. Borrow only the
            // native texture; DrawBuffIcon would read gameplay slots and allow removal.
            Main.spriteBatch.Draw(texture, point.ToVector2(), color);
            if (status.RemainingTicks > 2)
            {
                string duration = Lang.LocalizedDuration(new TimeSpan(0, 0, status.RemainingTicks / 60),
                    abbreviated: true, showAllAvailableUnits: false);
                Utils.DrawBorderString(Main.spriteBatch, duration,
                    new Vector2(point.X, point.Y + texture.Height), color, 0.8f);
            }
            if (!hovered) continue;
            player.mouseInterface = true;
            Main.hoverItemName = "";
            Main.HoverItem = new Item();
            // Same native buff hover path, with this adapter's own mechanical label.
            Main.instance.MouseText(status.Label, status.Tooltip);
        }
        return true;
    }
}
