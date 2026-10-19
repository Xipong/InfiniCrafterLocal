#nullable enable
using System.Text.Json.Nodes;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

// Request-only native observations, never a placement selector or execution
// policy. Unknown native state layouts remain absent, not guessed from names.
internal static class NativeTileStateFacts
{
    internal static JsonObject? Capture(int? tileId, int? placeStyle)
    {
        if (tileId != TileID.Campfire || placeStyle != 0) return null;
        // Installed Wiring.ToggleCampFire derives a 3x2 origin from frameX%54
        // and frameY%36, considers top-left frameY<36 on, then shifts all cells
        // by +/-36. This describes state pixels, not Main.tileFrame animation.
        return new JsonObject {
            ["tileId"] = tileId, ["placeStyle"] = placeStyle,
            ["selector"] = "top_left_frame_y", ["onMin"] = 0, ["onMax"] = 35,
            ["offMin"] = 36, ["offMax"] = 71,
            ["provenance"] = "Terraria.Wiring.ToggleCampFire",
        };
    }
}
