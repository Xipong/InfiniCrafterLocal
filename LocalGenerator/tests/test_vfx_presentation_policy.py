"""Model-facing presentation policy must match the actual image transport."""
import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import pipeline_visual_config as config


@pytest.mark.parametrize("keyed", [True, False])
@pytest.mark.parametrize("repair", [True, False])
def test_impact_prompt_distinguishes_final_alpha_from_raw_background(monkeypatch, keyed, repair):
    monkeypatch.setattr(config, "REMOVE_BG", keyed)
    monkeypatch.setattr(config, "BG_REMOVE_MODE", "sprite_keyer")
    monkeypatch.setattr(config, "BG_COLOR", "cyan")
    packet = vfx._prompt_packet({}, None, None)
    captured = {}

    def transport(_system, user, *_args, **_kwargs):
        captured.update(user)
        return {}

    vfx._request(transport, packet, repair_errors=[] if repair else None)
    slots = "slotsUpsert" if repair else "slots"
    rules = captured["outputSchema"]["properties"][slots]["items"]["properties"]["spritePrompt"].get("description", "")
    assert "final impact PNG" in rules
    assert "must request one dedicated transparent impact sprite" not in rules
    if keyed:
        assert "raw image" in rules and "rgb(0,255,255)" in rules
    else:
        assert "raw image" in rules and "transparent background" in rules
        assert "solid rgb" not in rules


def test_vfx_schema_is_honest_about_backend_particles_and_color():
    packet = vfx._prompt_packet({}, None, None)
    slot = packet["outputSchema"]["properties"]["slots"]["items"]["properties"]
    assert "Dust/FNA" in slot["backend"].get("description", "")
    particles = slot["particleSystemId"].get("description", "")
    assert "Terraria dust" in particles and "not" in particles and "ParticleLibrary" in particles
    assert "effectColor" in packet["runtimeSurface"].get("colorPolicy", "")
    assert "legacy" in packet["runtimeSurface"]["colorPolicy"]


def test_renderer_semantics_reach_director_and_repair():
    packet = vfx._prompt_packet({}, None, None)
    surface = packet["runtimeSurface"]
    descriptions = surface.get("rendererSemantics", {})
    assert set(descriptions) == set(surface["rendererKind"])
    assert "wave" in descriptions["wavyStrip"]
    assert "motes" in descriptions["orbitingMotes"]
    assert "120" in descriptions["ghostArc"]
    assert "tip" in descriptions["tipTrail"]
    captured = {}

    def transport(_system, user, *_args, **_kwargs):
        captured.update(user)
        return {}

    vfx._request(transport, packet, repair_errors=[])
    assert captured["runtimeSurfaceReadOnly"]["rendererSemantics"] == descriptions
