"""The authored grip is forwarded literally to the actual image request prompt."""
import copy

from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt


def test_final_canvas_grip_reaches_item_image_prompt_without_touching_art():
    data = {"visual": {"grip": {"normalizedX": 0.123456789, "normalizedY": 0.8}}}
    before = copy.deepcopy(data)
    authored = "asymmetric brass handle, red crystal and translucent blue fin"
    text = normalize_asset_prompt(data, "item", authored, 64)
    assert authored in text
    assert '"normalizedX":0.123456789' in text
    assert '"normalizedY":0.8' in text
    assert "final canvas" in text and "upper-left" in text
    assert data == before


def test_grip_is_not_invented_or_applied_to_separate_entity_art():
    plain = normalize_asset_prompt({}, "item", "brass handle", 64)
    assert "normalizedX" not in plain
    data = {"visual": {"grip": {"normalizedX": 0.2, "normalizedY": 0.7}}}
    separate = normalize_asset_prompt(data, "runtime:projectile", "blue mote", 64)
    assert "normalizedX" not in separate


def test_grip_survives_real_generation_dispatch_with_long_authored_prompt(monkeypatch):
    from infini_local.pipelines import visual_sprite_generation as generation

    captured = []

    def backend(_data, **kwargs):
        captured.append(kwargs)
        return []  # observe the external boundary; no fabricated successful image

    monkeypatch.setattr(generation, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(generation, "_backend_configuration_error", lambda: "")
    monkeypatch.setattr(generation, "_generate_backend_variants", backend)
    data = {"visual": {"grip": {"normalizedX": 0.123456789, "normalizedY": 0.8}}}
    authored = "brass " * 230 + "red_tip"
    assert len(authored) <= 1400
    generation.generate_visual_asset(data, "item", authored, "", "grip_probe", 64)
    assert len(captured) == 1
    assert authored in captured[0]["prompt"]
    assert '"normalizedX":0.123456789' in captured[0]["prompt"]
    assert '"normalizedY":0.8' in captured[0]["prompt"]
