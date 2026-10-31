"""Concrete previously supported dimensions remain directly authorable."""


def test_explicit_sprite_dimensions_retain_640px_legacy_impact_size():
    from infini_local.core import vfx_manifest as vfx
    from tests.vfx_material_fixtures import _data, _sprite
    data = _data()
    raw = _sprite(data)
    element = raw["slots"][0]["element"]
    element.update(widthPx=640, heightPx=640)
    for field in ("widthProfile", "heightProfile"):
        element[field].update(start=1, middle=1, end=1)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "640px-impact")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
