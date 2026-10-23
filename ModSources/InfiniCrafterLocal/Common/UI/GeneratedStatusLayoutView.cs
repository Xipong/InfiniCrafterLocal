#nullable enable
using System;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.UI;

internal static class GeneratedStatusLayoutView
{
    internal static Rectangle Cell(int index, int count, int screenWidth, int screenHeight,
        int xPercent, int yPercent, int desiredColumns, int scalePercent)
    {
        if (index < 0 || index >= count || screenWidth < 32 || screenHeight < 50) return Rectangle.Empty;
        float scale = Math.Clamp(scalePercent, 75, 150) / 100f;
        int cellWidth = Math.Max(1, (int)MathF.Ceiling(38 * scale));
        int cellHeight = Math.Max(1, (int)MathF.Ceiling(50 * scale));
        int maxColumns = Math.Max(1, screenWidth / cellWidth), maxRows = Math.Max(1, screenHeight / cellHeight);
        int columns = Math.Clamp(Math.Max(desiredColumns, (count + maxRows - 1) / maxRows), 1, maxColumns);
        int rows = Math.Min(maxRows, (count + columns - 1) / columns);
        if (index >= rows * columns) return Rectangle.Empty;
        int width = Math.Min(count, columns) * cellWidth, height = rows * cellHeight;
        int x = (int)(Math.Max(0, screenWidth - width) * Math.Clamp(xPercent, 0, 100) / 100d);
        int y = (int)(Math.Max(0, screenHeight - height) * Math.Clamp(yPercent, 0, 100) / 100d);
        int size = Math.Min(Math.Min(screenWidth, screenHeight), (int)MathF.Round(32 * scale));
        return new Rectangle(x + index % columns * cellWidth, y + index / columns * cellHeight, size, size);
    }
}
