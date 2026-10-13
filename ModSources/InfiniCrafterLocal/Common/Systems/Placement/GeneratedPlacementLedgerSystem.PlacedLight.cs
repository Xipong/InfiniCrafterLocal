#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    // Uses the same authenticated, footprint-checked group projection as PNG
    // presentation; never a second world ledger or held-item execution route.
    private static bool TryGetPlacedLight(PlacedBodyProjection projection, out Point position, out Vector3 color)
    {
        position = default; color = default;
        if (projection.View is not GeneratedPlacedBodyView view || view.Light is not RuntimePlacedLightSpec light
            || !Groups.TryGetValue(view.GroupId,out PlacementGroup? group)
            || !ReferenceEquals(projection.Source,group) || projection.DefinitionJson != group.DefinitionJson
            || !GeneratedItemRegistryService.IsCurrentWorldData(view.Data)) return false;
        foreach (GeneratedPlacementKey cell in group.Cells)
            if (!WorldGen.InWorld(cell.X,cell.Y,1) || !Main.tile[cell.X,cell.Y].HasTile
                || Main.tile[cell.X,cell.Y].TileType != view.TileType) return false;
        // One center cell per footprint, independent of visual pivots/heads or owner.
        position = new((view.Footprint.X + view.Footprint.Width / 2) / 16,
                       (view.Footprint.Y + view.Footprint.Height / 2) / 16);
        color = RuntimeColorPolicy.Resolve(light.Color,Color.Transparent).ToVector3() * (float)light.Strength;
        return true;
    }

    private static void EmitPlacedLights()
    {
        if (Main.dedServ) return;
        foreach (PlacedBodyProjection projection in PlacedBodyViews.Values)
            if (TryGetPlacedLight(projection,out Point position,out Vector3 color))
                Lighting.AddLight(position.X,position.Y,color.X,color.Y,color.Z);
    }
}
