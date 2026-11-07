using System;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using ReLogic.Graphics;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasHeaderUsesVisibleGlyphsAndInsetControls()
    {
        // Exercise the real native font metrics: line spacing includes unused
        // ascent/descent and is not the visible height of a short symbol.
        var font = new DynamicSpriteFont(0, 30, '?');
        font.SpriteCharacters.Add('А', new DynamicSpriteFont.SpriteCharacterData(null!, new(0, 0, 14, 18), new(0, 4, 14, 30), new(0, 14, 0)));
        font.SpriteCharacters.Add('×', new DynamicSpriteFont.SpriteCharacterData(null!, new(0, 0, 8, 7), new(0, 10, 8, 30), new(0, 8, 0)));
        font.SpriteCharacters.Add('?', new DynamicSpriteFont.SpriteCharacterData(null!, new(0, 0, 10, 16), new(0, 1, 10, 30), new(0, 10, 0)));
        foreach (var value in new[] { ("А", 4f, 22f), ("×", 10f, 17f), ("?", 1f, 17f), ("А×", 4f, 22f), ("А\n×", 4f, 47f) })
        foreach (float scale in new[] { .55f, .72f, .85f, 1f })
        {
            float offset = RecipeJournalUISystem.VisibleTextCenter(font, value.Item1) * scale;
            var box = new Rectangle(10, 22, 118, 26);
            float top = box.Center.Y - offset;
            Equal((float)box.Center.Y, top + (value.Item2 + value.Item3) * .5f * scale,
                "visible glyph ink is vertically centered, not unused line spacing");
        }
        font.SpriteCharacters.Add('z', new DynamicSpriteFont.SpriteCharacterData(null!, new(0, 0, 10, 0), new(0, -9, 10, 30), new(0, 10, 0)));
        foreach (string value in new[] { "", "   ", "Z", "z" })
            Equal(font.MeasureString(value).Y * .5f, RecipeJournalUISystem.VisibleTextCenter(font, value),
                "empty, whitespace, unsupported and zero-height glyphs retain safe font metrics");
        Equal(13f, RecipeJournalUISystem.VisibleTextCenter(font, "ZАz"),
            "invisible missing glyphs do not move the supported title glyph");
        foreach (int width in new[] { 320, 640, 1040 })
        {
            var book = new Rectangle(16, 16, width, 500);
            var header = RecipeJournalView.HeaderRow(book);
            var layout = RecipeJournalView.Bounds(width + 32, 532);
            var close = RecipeJournalView.BookControls(layout).Close;
            Equal(true, header.Top >= book.Top + 18 && header.Bottom <= book.Top + 48,
                "title occupies the visible leather band, below its irregular upper edge");
            Equal(header.Center.Y, close.Center.Y, "title and close share the same header baseline");
            Equal(true, layout.Book.Contains(close), "close hit area stays inside the book");
            Equal(layout.Book.Right - 35, close.Center.X, "existing close glyph sits beside the upper-right corner band");
        }
    }
}
