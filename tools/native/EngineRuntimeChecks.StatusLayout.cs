using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void QolStatusLayout()
    {
        foreach (var viewport in new[] { new Point(1920, 1080), new Point(320, 240), new Point(800, 600) })
        foreach (int scale in new[] { 75, 100, 150 })
        {
            var cells = new List<Rectangle>();
            for (int i = 0; i < 12; i++)
            {
                var cell = GeneratedStatusLayoutView.Cell(i, 12, viewport.X, viewport.Y, 100, 100, 1, scale);
                Equal(false, cell.IsEmpty, "status rows reflow instead of escaping screen");
                Equal(true, cell.Left >= 0 && cell.Top >= 0 && cell.Right <= viewport.X && cell.Bottom <= viewport.Y, "scaled cell stays inside UI viewport");
                foreach (var other in cells) Equal(false, cell.Intersects(other), "status icons never overlap after reflow");
                cells.Add(cell);
            }
        }
        Equal(Rectangle.Empty, GeneratedStatusLayoutView.Cell(0, 1, 10, 10, 0, 0, 1, 100), "impossible viewport suppresses the preview safely");
        Equal(new Point(0, 0), GeneratedStatusLayoutView.Cell(0, 3, 800, 600, 0, 0, 8, 100).Location, "zero anchors to top left");
    }
}
