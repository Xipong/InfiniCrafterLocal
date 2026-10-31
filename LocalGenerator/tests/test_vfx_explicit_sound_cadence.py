"""Fresh sound cadence is literal; stored automatic cadence remains readable."""
from __future__ import annotations

import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.surface as vfx_surface
import infini_local.core.vfx.validation as vfx_validation
from tests.vfx_material_fixtures import _data


def test_sound_fresh_positive_cadence_saved_zero_is_not_rewritten():
    data = _data()
    item = data["runtimeProgram"]["itemEntityId"]
    assert {"entityId": item, "event": "periodic"} in vfx_surface._allowed_pairs(data)
    raw = {"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "sound", "entityId": item, "event": "periodic", "rendererKind": "soundCue",
        "anchor": "self", "repeatEvery": 10, "soundId": "Item1",
        "sound": {"volume": .5, "pitch": 0, "pitchVariance": 0},
    }]}
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    raw["slots"][0]["repeatEvery"] = 0
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "stored-sound")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"]["slots"][0]["repeatEvery"] == 0
    raw["slots"][0].update(repeatEvery=10, density=.3)
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
