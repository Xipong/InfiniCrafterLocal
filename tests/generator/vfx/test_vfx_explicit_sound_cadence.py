"""Sound cadence has one explicit contract in Director and saved wire."""
import copy

from infini_local.core.vfx.projection import _compile_manifest
from infini_local.core.vfx.validation import validate_vfx_director_output, validate_vfx_manifest_wire
from tests.generator.vfx.test_vfx_dependency_delivery_contracts import visual_data, authored_vfx


def test_periodic_sound_requires_explicit_positive_cadence_without_saved_automatic_branch():
    data = visual_data("no_asset")
    raw = authored_vfx("soundCue")
    assert validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = _compile_manifest(data, raw, "explicit-cadence")
    assert validate_vfx_manifest_wire(data)["ok"]
    for value in (0, None):
        invalid = copy.deepcopy(raw)
        invalid["slots"][0]["repeatEvery"] = value
        assert not validate_vfx_director_output(invalid, data)["ok"]
        data["vfxManifest"] = _compile_manifest(data, invalid, "no-auto-cadence")
        before = copy.deepcopy(data["vfxManifest"])
        report = validate_vfx_manifest_wire(data)
        assert not report["ok"]
        assert {error["path"] for error in report["errors"]} == {"$.vfxManifest.slots[0].repeatEvery"}
        assert data["vfxManifest"] == before
