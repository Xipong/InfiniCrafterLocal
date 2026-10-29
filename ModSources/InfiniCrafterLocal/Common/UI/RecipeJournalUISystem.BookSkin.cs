#nullable enable
using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using Terraria.ModLoader;
using Terraria;

namespace InfiniCrafterLocal.Common.UI;

// One cached material set for the collection, recipe page, and genealogy map.
public sealed partial class RecipeJournalUISystem
{
    private static Asset<Texture2D>? _bookSkin, _wellSkin, _waxSkin, _bookmarkSkin, _foldSkin;
    private static void LoadBookSkin()
    {
        const string path = "InfiniCrafterLocal/Assets/UI/Lineage/";
        _bookSkin = ModContent.Request<Texture2D>(path + "BookFrame");
        _wellSkin = ModContent.Request<Texture2D>(path + "NodeWell");
        _waxSkin = ModContent.Request<Texture2D>(path + "WaxSeal");
        _bookmarkSkin = ModContent.Request<Texture2D>(path + "Bookmark");
        _foldSkin = ModContent.Request<Texture2D>(path + "PaperFold");
    }
    private static void UnloadBookSkin()
    {
        _bookSkin = _wellSkin = _waxSkin = _bookmarkSkin = _foldSkin = null;
    }
    private static void DrawBook(SpriteBatch sb, Rectangle book)
    {
        if (_bookmarkSkin is not null && book.Width >= 260 && book.Height >= 240)
            sb.Draw(_bookmarkSkin.Value, new Rectangle(book.Center.X - 10, book.Bottom - 57, 20, Math.Min(74, Math.Max(0, Main.screenHeight - book.Bottom + 57))), Color.White);
        if (_bookSkin is null) return;
        Texture2D texture = _bookSkin.Value;
        const int left = 48, right = 48, top = 56, bottom = 48;
        int dx = Math.Min(left, book.Width / 2), dy = Math.Min(top, book.Height / 2);
        int dr = Math.Min(right, book.Width - dx), db = Math.Min(bottom, book.Height - dy);
        // Nine draws, one authored continuous paper center: no stretched center fold.
        for (int y = 0; y < 3; y++)
        for (int x = 0; x < 3; x++)
        {
            int sx = x == 0 ? 0 : x == 1 ? left : texture.Width - right;
            int sy = y == 0 ? 0 : y == 1 ? top : texture.Height - bottom;
            int sw = x == 0 ? left : x == 1 ? texture.Width - left - right : right;
            int sh = y == 0 ? top : y == 1 ? texture.Height - top - bottom : bottom;
            var destination = new Rectangle(x == 0 ? book.X : x == 1 ? book.X + dx : book.Right - dr,
                y == 0 ? book.Y : y == 1 ? book.Y + dy : book.Bottom - db,
                x == 0 ? dx : x == 1 ? book.Width - dx - dr : dr,
                y == 0 ? dy : y == 1 ? book.Height - dy - db : db);
            if (destination.Width > 0 && destination.Height > 0)
                sb.Draw(texture, destination, new Rectangle(sx, sy, sw, sh), Color.White);
        }
    }
    private static void DrawBookWell(SpriteBatch sb, Rectangle well, bool root, bool hover)
    {
        var texture = root ? _waxSkin : _wellSkin;
        if (texture is not null) sb.Draw(texture.Value, well, hover ? new Color(255, 241, 198) : Color.White);
    }
    private static void DrawPaperSlip(SpriteBatch sb, Rectangle rect, bool focused = false)
    {
        // Translucent paper lets the single authored parchment remain continuous.
        Fill(sb, rect, new Color(255, 245, 214, focused ? 85 : 40));
        Fill(sb, new Rectangle(rect.X, rect.Bottom - 1, rect.Width, 1), focused ? Ink : Rule);
    }
    private static void DrawBookFold(SpriteBatch sb, Rectangle book)
    {
        if (_foldSkin is not null && book.Width >= 260 && book.Height >= 240)
            sb.Draw(_foldSkin.Value, new Rectangle(book.Right - 58, book.Bottom - 60, 40, 38), Color.White);
    }
}
