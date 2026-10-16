#nullable enable
using System;
using System.Collections.Generic;
using System.Linq.Expressions;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
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
    private static Asset<Texture2D>? _exhaustionIcon;

    public override void Load()
    {
        if (!Main.dedServ)
            _exhaustionIcon = ModContent.Request<Texture2D>(GeneratedItemExhaustionStatusView.IconPath);
    }

    public override void Unload() => _exhaustionIcon = null; // ModContent owns disposal.

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
        InfiniCraftPlayer owner = player.GetModPlayer<InfiniCraftPlayer>();
        GeneratedUtilityBuffPresentation snapshot = owner.CaptureGeneratedUtilityBuffPresentation();
        IReadOnlyList<GeneratedUtilityBuffStatus> statuses = GeneratedUtilityBuffStatusView.Build(
            snapshot, Language.ActiveCulture.CultureInfo);
        IReadOnlyList<GeneratedItemExhaustionStatusRow> exhausted = GeneratedItemExhaustionStatusView.Build(
            owner.CaptureGeneratedItemExhaustion(), Language.ActiveCulture.CultureInfo);
        GeneratedMobilityCooldownStatus? mobility = GeneratedMobilityCooldownStatusView.Build(
            owner.GeneratedMobilityCooldownTicks, Language.ActiveCulture.CultureInfo);
        int append = GeneratedUtilityBuffStatusView.GetAppendIndex(player.buffType, Main.playerInventory);
        int inventoryOffset = Main.playerInventory ? NativeInventoryTopOffset() : 0;
        foreach (GeneratedUtilityBuffStatus status in statuses)
            DrawStatus(player, TextureAssets.Buff[status.IconBuffType], status.Label,
                status.Tooltip, status.RemainingTicks, append++, inventoryOffset);
        foreach (GeneratedItemExhaustionStatusRow status in exhausted)
            DrawStatus(player, _exhaustionIcon, status.Label,
                status.Tooltip, status.RemainingTicks, append++, inventoryOffset);
        if (mobility is not null)
            DrawStatus(player, TextureAssets.Buff[mobility.IconBuffType], mobility.Label,
                mobility.Tooltip, mobility.RemainingTicks, append++, inventoryOffset);
        return true;
    }

    // Shared native loading/drawing boundary: preserve the original utility rows,
    // alpha, duration/hover and native HUD/equipment geometry for appended rows.
    private static void DrawStatus(Player player, Asset<Texture2D>? asset, string label,
        string tooltip, int remainingTicks, int index, int inventoryOffset)
    {
        if (asset is null || !asset.IsLoaded) return;
        Texture2D texture = asset.Value;
        Point point = GeneratedUtilityBuffStatusView.IconPosition(index, Main.playerInventory,
            Main.screenWidth, Main.screenHeight, inventoryOffset, Main.mapStyle);
        var bounds = new Rectangle(point.X, point.Y, texture.Width, texture.Height);
        bool hovered = !PlayerInput.IgnoreMouseInterface && bounds.Contains(Main.mouseX, Main.mouseY);
        Color color = Color.White * (hovered ? 1f : (Main.playerInventory ? 0.65f : 0.4f));
        // GameInterfaceLayer owns Begin/End and UIScaleMatrix. No gameplay slots,
        // DrawBuffIcon, HasBuff gate, timer advancement or click-to-remove behavior.
        Main.spriteBatch.Draw(texture, point.ToVector2(), color);
        if (remainingTicks > 2)
        {
            string duration = Lang.LocalizedDuration(new TimeSpan(0, 0, remainingTicks / 60),
                abbreviated: true, showAllAvailableUnits: false);
            Utils.DrawBorderString(Main.spriteBatch, duration,
                new Vector2(point.X, point.Y + texture.Height), color, 0.8f);
        }
        if (!hovered) return;
        player.mouseInterface = true;
        Main.hoverItemName = "";
        Main.HoverItem = new Item();
        Main.instance.MouseText(label, tooltip);
    }
}
