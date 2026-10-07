#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.Systems;

internal sealed record GeneratedPlacedBodyView(string GroupId, string DefinitionHash,
    GeneratedItemData Data, RuntimePlacedBodySpec Body, Rectangle Footprint);

public sealed partial class GeneratedPlacementLedgerSystem
{
    // Derived read-only projection. The existing group/return ledger remains the
    // only authority; this cache cannot create or destroy a material claim.
    private sealed record PlacedBodyProjection(PlacementGroup Source, string DefinitionJson, GeneratedPlacedBodyView? View);
    private static readonly Dictionary<string, PlacedBodyProjection> PlacedBodyViews = new(StringComparer.Ordinal);

    internal static bool ShouldSuppressPlacedBody(int x, int y)
    {
        if (!Placements.TryGetValue(new(GeneratedPlacementLayer.Tile,x,y),out string? id)
            || !Groups.TryGetValue(id,out PlacementGroup? group) || group.PlacedBody is null)
            return false;
        try
        {
            var witness = group.PlacedBody;
            if (witness.GetInt("version") != PlacedBodyWitnessVersion) return false;
            string binding = witness.GetString("bindingId"), hash = witness.GetString("definitionHash");
            if (binding.Length == 0 || hash.Length != 64 || !hash.All(Uri.IsHexDigit) || !witness.ContainsKey("tileType")) return false;
            // Membership and lifecycle belong to the durable material ledger.
            // PNG/pose availability cannot change an already accepted presentation
            // choice. A failed pose stays explicitly pending/diagnosed, not native.
            // Paint, actuation and ordinary wired frames do not create new material.
            return WorldGen.InWorld(x,y,1) && Main.tile[x,y].HasTile
                && Main.tile[x,y].TileType == witness.GetInt("tileType");
        }
        catch { return false; }
    }

    private static void RefreshPlacedBodyViews()
    {
        foreach (string retired in PlacedBodyViews.Keys.Where(id => !Groups.ContainsKey(id)).ToArray())
            PlacedBodyViews.Remove(retired);
        foreach (PlacementGroup group in Groups.Values.Where(g => g.PlacedBody is not null && g.DefinitionJson.Length > 0))
        {
            if (PlacedBodyViews.TryGetValue(group.GroupId,out PlacedBodyProjection? prior)
                && ReferenceEquals(prior.Source,group) && prior.DefinitionJson == group.DefinitionJson) continue;
            // Version the derived cache by the actual retained group and exact
            // definition bytes. Record an invalid projection once, not per frame.
            PlacedBodyViews[group.GroupId] = new(group,group.DefinitionJson,null);
            try
            {
                var witness = group.PlacedBody!;
                GeneratedItemData? data = GeneratedItemData.FromJson(group.DefinitionJson);
                string hash = witness.GetString("definitionHash"), bindingId = witness.GetString("bindingId");
                if (data is null || data.Id != group.GeneratedItemId
                    || GeneratedItemRegistryService.DefinitionIdentity(data) != hash) continue;
                RuntimeBindingSpec? binding = data.RuntimeProgram.Bindings.SingleOrDefault(b => b.Id == bindingId);
                RuntimePlacedBodySpec? body = binding?.UsePolicy.Action.Placement?.PlacedBody;
                RuntimePlacementSpec? placement = binding?.UsePolicy.Action.Placement;
                if (body is null || binding!.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem
                    || placement!.TileId != witness.GetInt("tileType") || placement.PlaceStyle != witness.GetInt("nativeStyle")) continue;
                body.Validate();
                int x = witness.GetInt("originX"), y = witness.GetInt("originY");
                int width = witness.GetInt("width"), height = witness.GetInt("height");
                if (width < 1 || height < 1 || width > MaxCellsPerGroup || height > MaxCellsPerGroup
                    || (long)width * height != group.Cells.Count || !WorldGen.InWorld(x,y,1)
                    || (long)x+width-1 >= Main.maxTilesX-1 || (long)y+height-1 >= Main.maxTilesY-1
                    || group.Cells.Distinct().Count() != group.Cells.Count
                    || group.Cells.Any(cell => cell.Layer != GeneratedPlacementLayer.Tile
                        || cell.X < x || (long)cell.X >= (long)x+width || cell.Y < y || (long)cell.Y >= (long)y+height))
                {
                    global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn(
                        "[GeneratedPlacementLedger] placed_body_witness_geometry: projection declined; raw witness/material retained, group=" + group.GroupId);
                    continue;
                }
                PlacedBodyViews[group.GroupId] = new(group,group.DefinitionJson,new(group.GroupId,hash,data,body,new(x*16,y*16,width*16,height*16)));
            }
            catch { /* Invalid cosmetic projection leaves the durable group untouched. */ }
        }
    }

    internal static IEnumerable<GeneratedPlacedBodyView> VisiblePlacedBodies()
    {
        foreach (PlacedBodyProjection projection in PlacedBodyViews.Values)
        {
            if (projection.View is not GeneratedPlacedBodyView view
                || !Groups.TryGetValue(view.GroupId,out PlacementGroup? group)
                || !ReferenceEquals(projection.Source,group) || projection.DefinitionJson != group.DefinitionJson) continue;
            bool live = true;
            foreach (GeneratedPlacementKey cell in group.Cells)
                if (!ShouldSuppressPlacedBody(cell.X,cell.Y)) { live = false; break; }
            if (live) yield return view;
        }
    }
}
