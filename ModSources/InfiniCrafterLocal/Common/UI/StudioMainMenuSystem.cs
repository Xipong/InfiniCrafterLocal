#nullable enable
using System;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using Terraria;
using Terraria.Audio;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class StudioMainMenuSystem : ModSystem
{
    private Asset<Texture2D>? _icon;
    private bool _mouseWasDown;
    internal static bool Visible(bool dedicated, bool menu, int mode) => !dedicated && menu && mode == 0;
    internal static Rectangle Bounds(int menuWidth) => new(menuWidth - 72, 20, 52, 52);

    public override void Load()
    {
        if (Main.dedServ) return;
        _icon = ModContent.Request<Texture2D>("InfiniCrafterLocal/Assets/InfiniCore");
        On_Main.DrawMenu += DrawMenu;
    }

    public override void Unload()
    {
        On_Main.DrawMenu -= DrawMenu;
        _icon = null; // ModContent owns this texture.
        _mouseWasDown = false;
        StudioBrowserAction.Reset();
    }

    private void DrawMenu(On_Main.orig_DrawMenu orig, Main self, GameTime time)
    {
        // Native DrawMenu consumes mouseLeftRelease and ends its sprite batch.
        // Capture the edge before it runs; do not modify native menu input.
        bool eligibleBefore = Visible(Main.dedServ, Main.gameMenu, Main.menuMode);
        bool pressed = eligibleBefore && Main.mouseLeft && !_mouseWasDown;
        _mouseWasDown = Main.mouseLeft;
        orig(self, time);
        if (!Visible(Main.dedServ, Main.gameMenu, Main.menuMode) || _icon is null) return;
        // PreDrawMenu -> PlayerInput.SetZoom_UI already converted width and mouse to UI coordinates.
        Rectangle bounds = Bounds(Main.screenWidth);
        Vector2 mouse = new(Main.mouseX, Main.mouseY);
        bool hovered = bounds.Contains(mouse.ToPoint());
        if (hovered && pressed && StudioBrowserAction.TryOpen())
            SoundEngine.PlaySound(SoundID.Item37); // Native reforge/anvil strike.
        Texture2D texture = _icon.Value;
        Rectangle frame = Main.itemAnimations[ModContent.ItemType<InfiniCore>()].GetFrame(texture);
        SpriteBatch batch = Main.spriteBatch;
        batch.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.PointClamp,
            DepthStencilState.None, RasterizerState.CullCounterClockwise, null, Main.UIScaleMatrix);
        try
        {
            float scale = Math.Min(bounds.Width / (float)frame.Width, bounds.Height / (float)frame.Height);
            batch.Draw(texture, bounds.Center.ToVector2(), frame, hovered ? Color.White : Color.LightGray,
                0f, frame.Size() / 2f, scale, SpriteEffects.None, 0f);
            Utils.DrawBorderString(batch, "IFC", new Vector2(bounds.Center.X, bounds.Bottom + 2), Color.White, 0.7f, 0.5f);
            if (hovered)
            {
                string text = StudioBrowserAction.Status ?? Language.GetTextValue("Mods.InfiniCrafterLocal.Studio.MenuOpen");
                Utils.DrawBorderString(batch, text, new Vector2(bounds.Right, bounds.Bottom + 26), Color.White, 0.7f, 1f);
                // The native cursor was drawn before this overlay; keep it visible above the icon.
                Main.DrawCursor(Main.DrawThickCursor(), false);
            }
        }
        finally { batch.End(); }
    }
}
