#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ObjectData;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    private static readonly HashSet<string> PlacedBodyAdmissionDiagnostics = new(StringComparer.Ordinal);

    public override void PostSetupContent()
    {
        if (!GeneratedPlacedBodyNativeAdapter.TryInstall(ShouldSuppressPlacedBody,null,out string reason))
            ReportPlacedBodyAdmissionFailure(reason);
    }

    public override void Unload()
    {
        try { GeneratedPlacedBodyNativeAdapter.Unload(); }
        finally { PlacedBodyAdmissionDiagnostics.Clear(); PlacedBodyViews.Clear(); }
    }

    private static void ReportPlacedBodyAdmissionFailure(string reason)
    {
        if (PlacedBodyAdmissionDiagnostics.Count >= 128 || !PlacedBodyAdmissionDiagnostics.Add(reason)) return;
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn(
            "[GeneratedPlacementLedger] placed PNG presentation refused before mutation: " + reason);
    }

    private static bool AdmitPlacedBodyNativeBoundary(RuntimePlacementSpec placement)
    {
        if (placement.PlacedBody is null) return true;
        if (!GeneratedPlacedBodyNativeAdapter.TryAdmitNative(placement.TileId,null,false,out string reason))
        { ReportPlacedBodyAdmissionFailure(reason); return false; }
        try
        {
            TileObjectData? data = TileObjectData.GetTileData(placement.TileId,placement.PlaceStyle);
            if (data is null) return !Main.tileFrameImportant[placement.TileId];
            PropertyInfo? alternates = typeof(TileObjectData).GetProperty("Alternates",BindingFlags.Instance|BindingFlags.NonPublic);
            if (alternates is null) throw new InvalidOperationException("native alternate metadata unavailable");
            var rows = alternates.GetValue(data) as List<TileObjectData>;
            if (rows is { Count: > MaxCellsPerGroup }) throw new InvalidOperationException("native alternate roster exceeds bounded admission");
            bool ProvedGeometry(TileObjectData candidate)
                => candidate.Width is > 0 and <= AuthorizationRadiusTiles
                && candidate.Height is > 0 and <= AuthorizationRadiusTiles
                && (long)candidate.Width*candidate.Height <= MaxCellsPerGroup
                && candidate.HookPostPlaceMyPlayer.hook is null && candidate.HookPostPlaceEveryone.hook is null;
            // Post-place hooks create independent TE/NPC/contents owners. This v1
            // supplies no actor certificate, so it does not pretend that a future
            // actor is absent simply because ByPosition is empty before placement.
            if (!ProvedGeometry(data) || rows is not null && rows.Exists(row => row is not null && !ProvedGeometry(row)))
                throw new InvalidOperationException("native post-place actor/callback or footprint outside certified bounded cell scope");
            return true;
        }
        catch (Exception e)
        { ReportPlacedBodyAdmissionFailure("unsupported placed-body boundary: " + e.Message); return false; }
    }
}
