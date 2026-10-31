"""Fresh sound cadence is literal; stored automatic cadence remains readable."""
from __future__ import annotations

from infini_local.core import vfx_manifest as vfx
from tests.vfx_material_fixtures import _data


def test_sound_fresh_positive_cadence_saved_zero_is_not_rewritten():
    data = _data()
    item = data["runtimeProgram"]["itemEntityId"]
    assert {"entityId": item, "event": "periodic"} in vfx._allowed_pairs(data)
    raw = {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "sound", "entityId": item, "event": "periodic", "rendererKind": "soundCue",
        "anchor": "self", "repeatEvery": 10, "soundId": "Item1",
        "sound": {"volume": .5, "pitch": 0, "pitchVariance": 0},
    }]}
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    raw["slots"][0]["repeatEvery"] = 0
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "stored-sound")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"]["slots"][0]["repeatEvery"] == 0
    raw["slots"][0].update(repeatEvery=10, density=.3)
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
