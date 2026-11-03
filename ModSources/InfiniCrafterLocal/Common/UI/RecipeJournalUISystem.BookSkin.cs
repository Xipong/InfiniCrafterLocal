#nullable enable
using System;
using System.Collections.Generic;
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
    private static readonly Dictionary<Asset<Texture2D>, (Texture2D Source, Texture2D Prepared)> BookSkinTextures = new();

    internal static bool PrepareBookSkinPixels(Color[] pixels, string? extension)
    {
        // tML converts packaged PNGs through ImageIO.ToRaw: partial-alpha RGB is
        // retained verbatim, and RawImgReader uploads it unchanged. PngReader
        // already premultiplies, so only the known raw loader needs this step.
        if (!string.Equals(extension, ".rawimg", StringComparison.OrdinalIgnoreCase)) return false;
        for (int i = 0; i < pixels.Length; i++)
        {
            Color color = pixels[i];
            pixels[i] = new Color(color.R * color.A / 255, color.G * color.A / 255,
                color.B * color.A / 255, color.A);
        }
        return true;
    }

    private static Texture2D BookSkinTexture(Asset<Texture2D> asset)
    {
        Texture2D source = asset.Value;
        string? extension = asset.Source?.GetExtension(asset.Name);
        bool raw = string.Equals(extension, ".rawimg", StringComparison.OrdinalIgnoreCase);
        if (BookSkinTextures.TryGetValue(asset, out var cached))
        {
            if (raw && ReferenceEquals(cached.Source, source)) return cached.Prepared;
            cached.Prepared.Dispose();
            BookSkinTextures.Remove(asset);
        }
        if (!raw) return source;
        var pixels = new Color[checked(source.Width * source.Height)];
        source.GetData(pixels);
        PrepareBookSkinPixels(pixels, extension);
        // Never mutate the shared ModContent texture or premultiply it per draw.
        var prepared = new Texture2D(source.GraphicsDevice, source.Width, source.Height);
        try
        {
            prepared.SetData(pixels);
            BookSkinTextures.Add(asset, (source, prepared));
            return prepared;
        }
        catch { prepared.Dispose(); throw; }
    }

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
        foreach (var cached in BookSkinTextures.Values) cached.Prepared.Dispose();
        BookSkinTextures.Clear();
        _bookSkin = _wellSkin = _waxSkin = _bookmarkSkin = _foldSkin = null;
    }
    private static void DrawBook(SpriteBatch sb, Rectangle book)
    {
        if (_bookmarkSkin is not null && book.Width >= 260 && book.Height >= 240)
            sb.Draw(BookSkinTexture(_bookmarkSkin), new Rectangle(book.Center.X - 10, book.Bottom - 57, 20, Math.Min(74, Math.Max(0, Main.screenHeight - book.Bottom + 57))), Color.White);
        if (_bookSkin is null) return;
        Texture2D texture = BookSkinTexture(_bookSkin);
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
        if (texture is not null) sb.Draw(BookSkinTexture(texture), well, hover ? new Color(255, 241, 198) : Color.White);
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
            sb.Draw(BookSkinTexture(_foldSkin), new Rectangle(book.Right - 58, book.Bottom - 60, 40, 38), Color.White);
    }
}
