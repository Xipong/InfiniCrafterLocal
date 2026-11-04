#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ObjectData;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    private static readonly HashSet<string> PlacedBodyAdmissionDiagnostics = new(StringComparer.Ordinal);
    private static bool _placedAdmissionFeedbackShown;
    private static ulong _placedAdmissionFeedbackTick;

    public override void PostSetupContent()
    {
        try { InstallNativeChestHooks(); }
        catch (Exception e) { ReportPlacedBodyAdmissionFailure("native chest source boundary unavailable: " + e.Message); }
    }

    public override void Unload()
    {
        try { UnloadNativeChestHooks(); }
        finally { ClearWorld(); PlacedBodyAdmissionDiagnostics.Clear(); _placedAdmissionFeedbackShown = false; }
    }

    private static void ReportPlacedBodyAdmissionFailure(string reason)
    {
        if (PlacedBodyAdmissionDiagnostics.Count >= 128 || !PlacedBodyAdmissionDiagnostics.Add(reason)) return;
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn(
            "[GeneratedPlacementLedger] placed presentation refused before mutation: " + reason);
    }

    private static void ShowPlacedBodyAdmissionFailure(RuntimePlacementSpec placement)
    {
        // Feedback only for this client's exact held definition. A remote peer,
        // same-ID copy or startup adapter failure must not post local chat text.
        if (Main.dedServ || Main.netMode == NetmodeID.Server || Main.gameMenu
            || Main.myPlayer < 0 || Main.myPlayer >= Main.maxPlayers
            || Main.player[Main.myPlayer] is not { active: true } player
            || player.HeldItem?.ModItem is not GeneratedItem generated
            || !generated.Data.RuntimeProgram.Bindings.Any(binding =>
                ReferenceEquals(binding.UsePolicy.Action.Placement, placement))) return;
        ulong now = Main.GameUpdateCount;
        if (_placedAdmissionFeedbackShown && now >= _placedAdmissionFeedbackTick
            && now - _placedAdmissionFeedbackTick < 120) return;
        _placedAdmissionFeedbackShown = true;
        _placedAdmissionFeedbackTick = now;
        Main.NewText(Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.PlacementUnsupported"));
    }

    private static bool AdmitPlacementBoundary(RuntimePlacementSpec placement)
    {
        if (placement.OwnedTile is not null)
        {
            try
            {
                placement.NormalizeAndValidate();
                return global::InfiniCrafterLocal.Content.Tiles.GeneratedOwnedTiles.Resolve(placement) >= 0;
            }
            catch (Exception e)
            { ReportPlacedBodyAdmissionFailure(e.Message); ShowPlacedBodyAdmissionFailure(placement); return false; }
        }
        // Native primitives retain native art. Never silently mask a rejected old
        // custom body with a parent's art or route a container to a generic tile.
        if (placement.PlacedBody is not null)
        { ReportPlacedBodyAdmissionFailure("native custom body retired; author place_object"); ShowPlacedBodyAdmissionFailure(placement); return false; }
        // Never route unsupported native chest styles through generic tile placement.
        if (IsNativeChestTile(placement.TileId)) return AdmitNativeChestMetadata(placement);
        if (placement.TileId < 0) return !placement.HasPlacedFootprint;
        try
        {
            TileObjectData? data = TileObjectData.GetTileData(placement.TileId,placement.PlaceStyle);
            if (data is null)
            {
                if (!Main.tileFrameImportant[placement.TileId]) return true;
                throw new InvalidOperationException("frame-important tile has no certified native geometry");
            }
            PropertyInfo? alternates = typeof(TileObjectData).GetProperty("Alternates",BindingFlags.Instance|BindingFlags.NonPublic);
            if (alternates is null) throw new InvalidOperationException("native alternate metadata unavailable");
            var rows = alternates.GetValue(data) as List<TileObjectData>;
            if (rows is { Count: > MaxCellsPerGroup }) throw new InvalidOperationException("native alternate roster exceeds bounded admission");
            bool ProvedGeometry(TileObjectData candidate)
                => candidate.Width is > 0 and <= AuthorizationRadiusTiles
                && candidate.Height is > 0 and <= AuthorizationRadiusTiles
                && (long)candidate.Width*candidate.Height <= MaxCellsPerGroup
                && candidate.HookPostPlaceMyPlayer.hook is null && candidate.HookPostPlaceEveryone.hook is null
                && candidate.HookPlaceOverride.hook is null && candidate.HookCheckIfCanPlace.hook is null;
            // Post-place hooks create independent TE/NPC/contents owners. This v1
            // supplies no actor certificate, so it does not pretend that a future
            // actor is absent simply because ByPosition is empty before placement.
            if (!ProvedGeometry(data) || rows is not null && rows.Exists(row => row is not null && !ProvedGeometry(row)))
                throw new InvalidOperationException("native post-place actor/callback or footprint outside certified bounded cell scope");
            return true;
        }
        catch (Exception e)
        { ReportPlacedBodyAdmissionFailure("unsupported placed-body boundary: " + e.Message); ShowPlacedBodyAdmissionFailure(placement); return false; }
    }
}
