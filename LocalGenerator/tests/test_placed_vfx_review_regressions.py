"""Locale and remaining source-policy regressions.

Scheduler delivery/deduplication/culling and actual mana tooltip rendering belong
to registered EngineRuntimeChecks, not private C# text/order snapshots.

These checks do not execute C#, create a graphics device or claim a game/MP run.
"""
from pathlib import Path

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


def test_placement_feedback_is_local_bounded_and_does_not_relax_guard():
    for locale in ("en-US", "ru-RU"):
        localization = ROOT / f"ModSources/InfiniCrafterLocal/Localization/{locale}_Mods.InfiniCrafterLocal.hjson"
        assert "PlacementUnsupported:" in localization.read_text(encoding="utf-8")
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
