from __future__ import annotations

from infini_local.pipelines import pipeline_visual_config as config


def test_codex_dispatch_writes_verified_png_and_preserves_authored_prompt(tmp_path, monkeypatch):
    import base64
    import contextlib
    import io
    import time
    from PIL import Image
    from infini_local.pipelines import image_backend_pipeline as backend, visual_sprite_generation as visual
    from infini_local.services import codex_auth as auth
    assert hasattr(backend, "generate_openai_codex"), "Codex is not connected to sprite dispatch"
    stream = io.BytesIO()
    Image.new("RGBA", (64, 64), (15, 120, 240, 255)).save(stream, format="PNG")
    calls, gate = [], []
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", time.time() + 3600)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    def post(url, payload, **kwargs):
        assert gate == ["entered"]
        calls.append((url, payload, kwargs))
        return {"data": [{"b64_json": base64.b64encode(stream.getvalue()).decode()}]}
    monkeypatch.setattr(auth, "post_json", post)
    monkeypatch.setattr(backend, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 1)
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    class Gate:
        @contextlib.contextmanager
        def slot(self):
            gate.append("entered")
            yield
            gate.append("exited")
    monkeypatch.setattr(visual, "IMAGE_GENERATION_GATE", Gate())
    for name in ("generate_image_api", "generate_sdcpp"):
        monkeypatch.setattr(visual, name, lambda *a: (_ for _ in ()).throw(AssertionError("unexpected fallback")))
    paths = visual._generate_backend_variants({}, prompt="Literal authored предмет", negative="no text", asset_id="test-item", canvas=32, role="item")
    assert gate == ["entered", "exited"]
    assert len(paths) == 1
    assert Image.open(paths[0]).format == "PNG"
    url, payload, options = calls[0]
    assert url == "https://chatgpt.com/backend-api/codex/images/generations"
    assert payload == {"model": "gpt-image-2", "prompt": "Literal authored предмет\n\nAvoid: no text", "n": 1, "quality": "medium", "size": "1024x1024", "background": "opaque"}
    assert options["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert options["headers"]["ChatGPT-Account-Id"] == credentials.account_id
    assert "response_format" not in payload


def test_codex_auth_error_is_not_retried_or_replaced_by_procedural(monkeypatch):
    from infini_local.pipelines import visual_sprite_generation as visual
    from infini_local.services.codex_auth import CodexError
    calls, fallbacks = [], []
    def fail(*args):
        calls.append(args)
        raise CodexError("OpenAI HTTP 429: quota reached")
    monkeypatch.setattr(visual, "generate_openai_codex", fail)
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(visual, "SPRITE_RETRIES", 3)
    monkeypatch.setattr(visual, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    monkeypatch.setattr(visual, "VISUAL_STRICT_AI_AUTHORSHIP", False)
    monkeypatch.setattr(visual, "normalize_asset_prompt", lambda data, role, prompt, canvas: prompt)
    monkeypatch.setattr(visual.visual_asset_pipeline, "generate_procedural_asset", lambda *a, **kw: fallbacks.append(True))
    data = {"id": "test", "visual": {"imagePrompt": "authored sprite"}}
    visual.maybe_generate_sprite(data)
    assert data["visual"]["spriteStatus"] == "failed"
    assert len(calls) == 1
    assert not fallbacks
    result = visual.generate_visual_asset({}, "entity_shot", "authored shot", "", "shot", 32)
    assert result[3] == "failed"
    assert len(calls) == 2
    assert not fallbacks


def test_codex_is_a_distinct_supported_subscription_backend():
    assert "openai_codex" in config.SUPPORTED_IMAGE_BACKENDS
    assert config.IMAGE_BACKEND_ALIASES.get("openai_codex", "openai_codex") != "image_api"
