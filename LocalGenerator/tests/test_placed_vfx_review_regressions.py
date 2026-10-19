"""Static owner/locale regressions; native behavior is covered by EngineRuntimeChecks.

These checks do not execute C#, create a graphics device or claim a game/MP run.
"""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
VFX = ROOT / "ModSources/InfiniCrafterLocal/Common/VFX"


def test_periodic_registration_has_no_per_source_global_sweep():
    source = (VFX / "InfiniDetachedVfxSystem.Materials.cs").read_text(encoding="utf-8")
    register = source.split("internal static void RegisterPeriodicElements", 1)[1].split(
        "private static void UpdatePlacedSources", 1
    )[0]
    assert "PeriodicElements.RemoveAll" not in register
    assert "PeriodicElements.Any" not in register
    assert "PeriodicElements.TryGetValue(key,out var prior)" in register
    assert "if(prior.Binding.IsLive)continue;" in register
    assert "ReferenceEquals(x.Generation,y.Generation)" in source


def test_periodic_prune_precedes_placed_admission_once_per_tick():
    source = (VFX / "InfiniDetachedVfxSystem.Materials.cs").read_text(encoding="utf-8")
    update = source.split("private static void UpdateMaterials()", 1)[1].split(
        "private static void DrawMaterialSprites", 1
    )[0]
    assert source.count("PrunePeriodicElements();") == 1
    assert update.index("if(LastMaterialsTick==now)return") < update.index("PrunePeriodicElements();")
    assert update.index("PrunePeriodicElements();") < update.index("UpdatePlacedSources(now);")


def test_distant_placed_slots_do_not_reserve_periodic_capacity():
    source = (VFX / "InfiniDetachedVfxSystem.Materials.cs").read_text(encoding="utf-8")
    register = source.split("internal static void RegisterPeriodicElements", 1)[1].split(
        "private static void UpdatePlacedSources", 1
    )[0]
    assert register.index("!PlacedVfxInView") < register.index("PeriodicElements.Count>=MaxEmissions")
    assert "placementBindingId is null?null:PlacedVfxReachRadius(slot)" in register
    assert "e.PlacedReachRadius is not double radius || PlacedVfxInView" in source


def test_visibility_uses_authored_motion_size_and_existing_client_preference():
    source = (VFX / "InfiniDetachedVfxSystem.PlacedVisibility.cs").read_text(encoding="utf-8")
    for consumed in (
        "EnableScreenCulling", "slot.Duration", "SpeedMaxPxPerTick",
        "AccelerationXPxPerTickSquared", "AccelerationYPxPerTickSquared",
        "OffsetForwardPx", "OffsetSidePx", "WidthProfile", "HeightProfile",
        "EndScaleMultiplier", "Main.GameViewMatrix", "zoom.X", "zoom.Y",
    ):
        assert consumed in source
    assert "Retire(" not in source
    assert "Main.tile" not in source
    assert "ToNetworkJson" not in source


@pytest.mark.parametrize("locale", ["en-US", "ru-RU"])
def test_mana_tooltip_has_visible_percentage_units(locale):
    path = ROOT / f"ModSources/InfiniCrafterLocal/Localization/{locale}_Mods.InfiniCrafterLocal.hjson"
    source = path.read_text(encoding="utf-8")
    match = re.search(r'^\s*EquipmentManaCost:\s*"([^"\n]+)"', source, re.MULTILINE)
    assert match is not None
    template = match.group(1)
    assert "{1}%" in template
    assert "-5%" in template.format("Equipped", "-5")
    assert "+5%" not in template.format("Equipped", "-5")
    equipment = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.Tooltips.Equipment.cs").read_text(encoding="utf-8")
    assert 'if (manaReduction > 0f) Percent("ManaCost", "EquipmentManaCost", -manaReduction);' in equipment
    native = (ROOT / "tools/EngineRuntimeChecks.VideoUiBuffs.cs").read_text(encoding="utf-8")
    crystal_test = native.split("VFUI14CapturedCrystalUsesMultiplierNotFiveFlatMana()", 1)[1].split("VFUI17DistinctBuffsAggregateAndExpireInEitherOrder()", 1)[0]
    assert "host.ModifyTooltips(lines);" in crystal_test
    assert 'rendered.Contains("-5%",StringComparison.Ordinal)' in crystal_test
    assert "native minimum" not in template and "минимума движка" not in template
    assert "PlacementUnsupported:" in source


def test_native_scheduler_regressions_are_reachable_from_registered_check():
    native = (ROOT / "tools/EngineRuntimeChecks.PlacedVfx.cs").read_text(encoding="utf-8")
    registration = (ROOT / "tools/EngineRuntimeChecks.cs").read_text(encoding="utf-8")
    assert "PlacedVfxContinuousBurstBudgets)" in registration
    entry = native.split("private static void PlacedVfxContinuousBurstBudgets()", 1)[1].split(
        "private sealed class CountingPlacedVfxSource", 1
    )[0]
    assert "PlacedVfxRegistrationAndViewportRegressions();" in entry
    for behavior in ("i<600", "Enumerable.Range(0,96)", "retired.Live=false", "config.EnableScreenCulling=false"):
        assert behavior in native


def test_placement_feedback_is_local_bounded_and_does_not_relax_guard():
    source = (ROOT / "ModSources/InfiniCrafterLocal/Common/Systems/Placement/"
              "GeneratedPlacementLedgerSystem.PlacedBodyAdmission.cs").read_text(encoding="utf-8")
    feedback = source.split("private static void ShowPlacedBodyAdmissionFailure", 1)[1].split(
        "private static bool AdmitPlacedBodyNativeBoundary", 1
    )[0]
    for condition in ("Main.dedServ", "NetmodeID.Server", "Main.gameMenu", "ReferenceEquals(", "< 120"):
        assert condition in feedback
    assert "PlacementUnsupported" in feedback
    assert "HookPostPlaceMyPlayer.hook is null" in source
    assert "HookPostPlaceEveryone.hook is null" in source


def test_inactive_placed_source_broad_phase_precedes_tile_walk_and_keeps_existing_retirement():
    placement = (ROOT / "ModSources/InfiniCrafterLocal/Common/Systems/Placement/"
                 "GeneratedPlacementLedgerSystem.PlacedVfx.cs").read_text(encoding="utf-8")
    update = placement.split("internal static IEnumerable<", 1)[1].split("internal static void RetirePlacedVfxSources", 1)[0]
    assert update.index("projection.Vfx is {} prior && !prior.IsLive") < update.index("MayNeedPlacedVfxFrame(candidate)")
    assert update.index("MayNeedPlacedVfxFrame(candidate)") < update.index("TryGetPlacedVfxFrame(projection,out _)")
    visibility = (VFX / "InfiniDetachedVfxSystem.PlacedVisibility.cs").read_text(encoding="utf-8")
    predicate = visibility.split("internal static bool MayNeedPlacedVfxFrame", 1)[1].split("private static bool PlacedVfxInView", 1)[0]
    assert 'slot.RendererKind == "lightCue"' in predicate  # unchanged, uncullable light consumer
    assert "slot.PlacementBindingId != view.BindingId" in predicate
    assert "slot.EntityId != view.EntityId" in predicate
    assert "PlacedVfxInView(center,PlacedVfxReachRadius(slot))" in predicate
    native = (ROOT / "tools/EngineRuntimeChecks.PlacedVfx.cs").read_text(encoding="utf-8")
    assert "PlacedVfxInactiveLedgerBroadPhaseRetainsRetirement();" in native
    assert 'Equal(false,active.Binding.IsLive' in native
