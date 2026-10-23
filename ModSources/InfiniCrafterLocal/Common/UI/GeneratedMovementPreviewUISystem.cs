#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.GameContent;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class GeneratedMovementPreviewUISystem : ModSystem
{
    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int index = layers.FindIndex(layer => layer.Name == "Vanilla: Mouse Text");
        if (index >= 0) layers.Insert(index, new LegacyGameInterfaceLayer("InfiniCrafterLocal: Movement Preview", Draw, InterfaceScaleType.Game));
    }
    private static bool Draw()
    {
        if (Main.gameMenu || !Main.hasFocus || Main.hideUI || Main.playerInventory || Main.mapFullscreen || Main.ingameOptionsWindow
            || Main.inFancyUI || Main.LocalPlayer is not { active: true, dead: false } player
            || player.mouseInterface || player.HeldItem.ModItem is not GeneratedItem item) return true;
        var binding = item.Data.RuntimeProgram.BindingForInput(Main.mouseRight ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.ApplyItemEffects) return true;
        var effects = item.Data.EffectsForBinding(binding);
        if (effects.MobilityMode != "blink_to_cursor") return true;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        var preview = owner.PreviewGeneratedBlink(effects, Main.MouseWorld);
        if (preview.Reason is "InvalidTarget" or "RangeMissing" or "Dead") return true;
        Vector2 point = preview.Destination - Main.screenPosition;
        Color color = preview.Allowed ? Color.LightGreen : Color.OrangeRed;
        var bounds = new Rectangle((int)point.X, (int)point.Y, player.width, player.height);
        var pixel = TextureAssets.MagicPixel.Value;
        Main.spriteBatch.Draw(pixel, new Rectangle(bounds.X, bounds.Y, bounds.Width, 2), color);
        Main.spriteBatch.Draw(pixel, new Rectangle(bounds.X, bounds.Bottom - 2, bounds.Width, 2), color);
        Main.spriteBatch.Draw(pixel, new Rectangle(bounds.X, bounds.Y, 2, bounds.Height), color);
        Main.spriteBatch.Draw(pixel, new Rectangle(bounds.Right - 2, bounds.Y, 2, bounds.Height), color);
        string key = preview.CooldownTicks > 0 ? "Cooldown" : preview.Reason.Length > 0 ? preview.Reason : preview.RangeLimited ? "RangeLimited" : "Ready";
        string label = Language.GetTextValue("Mods.InfiniCrafterLocal.MovementPreview." + key, (preview.CooldownTicks + 59) / 60);
        Vector2 labelPoint = new(Math.Clamp(point.X, 8, Math.Max(8, Main.screenWidth - 260)), Math.Clamp(point.Y - 24, 8, Math.Max(8, Main.screenHeight - 24)));
        Utils.DrawBorderString(Main.spriteBatch, label, labelPoint, color, .7f);
        return true;
    }
}
