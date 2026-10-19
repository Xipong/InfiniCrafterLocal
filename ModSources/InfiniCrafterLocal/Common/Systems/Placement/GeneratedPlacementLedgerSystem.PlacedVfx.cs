#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    // Cosmetic activation only. The retained group and authenticated view remain
    // the sole material/definition/witness owners. No new persistent state.
    private sealed class PlacedVfxBinding(PlacedBodyProjection projection) : VfxSourceBinding
    {
        private bool retired;
        private readonly object generation = new();
        internal readonly string SourceKey = "placed:" + Guid.NewGuid().ToString("N");
        internal override object Generation => generation;
        internal void Retire() => retired = true;
        internal override bool IsLive
        {
            get {
                if (!retired && !TryGetPlacedVfxFrame(projection,out _)) retired = true;
                return !retired;
            }
        }
        internal override bool TryFrame(string anchor,out VfxSourceFrame frame)
        {
            frame = default;
            return anchor == "self" && IsLive && TryGetPlacedVfxFrame(projection,out frame);
        }
    }

    private static bool TryGetPlacedVfxFrame(PlacedBodyProjection projection,out VfxSourceFrame frame)
    {
        frame = default;
        if (Main.dedServ || projection.View is not { Vfx: {} gate } view
            || !Groups.TryGetValue(view.GroupId,out PlacementGroup? group)
            || !ReferenceEquals(projection.Source,group) || projection.DefinitionJson != group.DefinitionJson
            || !PlacedBodyViews.TryGetValue(view.GroupId,out var current) || !ReferenceEquals(current,projection)
            || !GeneratedItemRegistryService.IsCurrentWorldData(view.Data) || !NativeChestProjectionLive(group)) return false;
        foreach (GeneratedPlacementKey cell in group.Cells)
            if (!WorldGen.InWorld(cell.X,cell.Y,1) || !Main.tile[cell.X,cell.Y].HasTile
                || Main.tile[cell.X,cell.Y].TileType != view.TileType) return false;
        int y = Main.tile[view.Footprint.X/16,view.Footprint.Y/16].TileFrameY;
        if (y < gate.MinFrameY || y > gate.MaxFrameY) return false;
        Vector2 center = new(view.Footprint.X + view.Footprint.Width*.5f,view.Footprint.Y + view.Footprint.Height*.5f);
        frame = new(center,Vector2.UnitX,Vector2.Zero) {SourceCenter=center};
        return true;
    }

    internal static IEnumerable<(GeneratedPlacedBodyView View,VfxSourceBinding Binding,string SourceKey)> ActivePlacedVfxSources()
    {
        if (Main.dedServ) yield break;
        // Cached by retained group and exact definition bytes; no per-tick JSON
        // parsing or texture readback. Late hydration uses the existing bounded queue.
        RefreshPlacedBodyViews();
        foreach (var projection in PlacedBodyViews.Values) {
            if (projection.Vfx is {} prior && !prior.IsLive) projection.Vfx = null;
            // Inactive particle-only sources may be culled before a cell walk.
            // Active bindings still validate offscreen to retire on/off changes.
            if (projection.Vfx is null && (projection.View is not { } candidate
                || !InfiniDetachedVfxSystem.MayNeedPlacedVfxFrame(candidate))) continue;
            if (!TryGetPlacedVfxFrame(projection,out _)) continue;
            var binding = projection.Vfx ??= new PlacedVfxBinding(projection);
            yield return (projection.View!,binding,binding.SourceKey);
        }
    }

    internal static void RetirePlacedVfxSources()
    {
        foreach (var projection in PlacedBodyViews.Values) {
            projection.Vfx?.Retire(); projection.Vfx = null;
        }
    }
}
