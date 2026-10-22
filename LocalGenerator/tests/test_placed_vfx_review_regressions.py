"""Locale and remaining source-policy regressions.

Scheduler delivery/deduplication/culling and actual mana tooltip rendering belong
to registered EngineRuntimeChecks, not private C# text/order snapshots.

These checks do not execute C#, create a graphics device or claim a game/MP run.
"""
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
VFX = ROOT / "ModSources/InfiniCrafterLocal/Common/VFX"


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
    # Actual rendered tooltip/sign is exercised by the registered native VFUI14 check.
    assert "native minimum" not in template and "минимума движка" not in template
    assert "PlacementUnsupported:" in source


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


def test_inactive_placed_source_filters_exact_selector_and_keeps_light_uncullable():
    visibility = (VFX / "InfiniDetachedVfxSystem.PlacedVisibility.cs").read_text(encoding="utf-8")
    predicate = visibility.split("internal static bool MayNeedPlacedVfxFrame", 1)[1].split("private static bool PlacedVfxInView", 1)[0]
    assert 'slot.RendererKind == "lightCue"' in predicate  # unchanged, uncullable light consumer
    assert "slot.PlacementBindingId != view.BindingId" in predicate
    assert "slot.EntityId != view.EntityId" in predicate
    assert "PlacedVfxInView(center,PlacedVfxReachRadius(slot))" in predicate
