using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateContour(VfxSlotSpec slot, bool fullNativeDraw)
    {
        if (!fullNativeDraw || slot.Geometry is not { Attachment: "world", RotationFrame: "world" } geometry
            || geometry.Contours.Any(node => node.Kind != "polyline")
            || geometry.Draws.Any(draw => draw.Op != "stroke" || draw.Join != "bevel" || draw.Cap != "butt"
                || draw.Mapping.Mode != "stretch" || draw.Material.Sampling != "point"
                || draw.Material.Texture.Source != "library" || draw.Material.Texture.AssetId != "solidPixel"))
            throw new NotSupportedException("contour proof requires full native draw, world/world polyline strokes, bevel/butt, stretch mapping and point-sampled solidPixel");
    }
}
