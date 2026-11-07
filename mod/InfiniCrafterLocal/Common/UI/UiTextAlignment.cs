#nullable enable
using System;
using Microsoft.Xna.Framework;
using ReLogic.Graphics;

namespace InfiniCrafterLocal.Common.UI;

internal static class UiTextAlignment
{
    // Extend the header's visible-height calculation with the native unrotated
    // DynamicSpriteFont draw advances/bearings. MeasureString remains the owner
    // of wrapping/fitting, not the center of the visible glyph rectangles.
    internal static Vector2 VisibleCenter(DynamicSpriteFont font, string text)
    {
        float x = 0, y = 0;
        float left = float.PositiveInfinity, top = float.PositiveInfinity;
        float right = float.NegativeInfinity, bottom = float.NegativeInfinity;
        bool first = true;
        foreach (char character in text)
        {
            if (character == '\r') continue;
            if (character == '\n') { x = 0; y += font.LineSpacing; first = true; continue; }
            var glyph = font.SpriteCharacters.TryGetValue(character, out var found) ? found : font.DefaultCharacterData;
            x += first ? Math.Max(glyph.Kerning.X, 0) : font.CharacterSpacing + glyph.Kerning.X;
            if (!char.IsWhiteSpace(character) && glyph.Glyph.Height > 0)
            {
                float gx = x + glyph.Padding.X, gy = y + glyph.Padding.Y;
                left = Math.Min(left, gx); right = Math.Max(right, gx + glyph.Glyph.Width);
                top = Math.Min(top, gy); bottom = Math.Max(bottom, gy + glyph.Glyph.Height);
            }
            x += glyph.Kerning.Y + glyph.Kerning.Z;
            first = false;
        }
        return float.IsPositiveInfinity(top) ? font.MeasureString(text) * .5f
            : new Vector2((left + right) * .5f, (top + bottom) * .5f);
    }

    internal static Vector2 CenteredPosition(DynamicSpriteFont font, string text, Rectangle target, float scale)
        => new Vector2(target.X + target.Width * .5f, target.Y + target.Height * .5f)
            - VisibleCenter(font, text) * scale;
}
