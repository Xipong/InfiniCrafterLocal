"""Offline canonical image adapter contracts; no live services."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import time
import pytest
from infini_local.pipelines import image_backend_pipeline as backend
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.services import codex_auth
from PIL import Image, ImageDraw
from infini_local.pipelines import image_backend_pipeline, visual_delivery_gate, visual_sprite_generation
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from tests.test_image_attempt_contracts import Response, offline, png
from tests.vfx_image_fixtures import _data, _request, offline_backend

@pytest.fixture
def adapter_transport(offline, monkeypatch, tmp_path):
    root, sdcpp_requests = offline
    raw = png((220, 100, 20))
    b64 = base64.b64encode(raw).decode('ascii')
    requests = []
    monkeypatch.setattr(backend, 'GENERATE_VARIANTS', 2)
    monkeypatch.setattr(backend.random, 'randint', lambda low, high: 91023)
    monkeypatch.setattr(backend, 'IMAGE_API_BASE_URL', 'https://offline.invalid')
    monkeypatch.setattr(backend, 'IMAGE_API_KEY', 'offline-fixture-not-a-secret')
    workflow = tmp_path / 'workflow.json'
    workflow.write_text(json.dumps({'node': {'inputs': {
        'logical_id': '{{SPRITE_ID}}', 'seed': '{{SEED}}', 'text': '{{PROMPT}}',
        'negative': '{{NEGATIVE_PROMPT}}',
    }}}))
    monkeypatch.setattr(backend, 'resolve_comfyui_workflow_path', lambda: workflow)
    monkeypatch.setattr(backend, 'poll_comfyui_history', lambda *args: {
        'pid': {'outputs': {'save': {'images': [{'filename': 'remote-fixture.png'}]}}},
    })

    def http_json(url, payload, **kwargs):
        requests.append((url, payload))
        if url.endswith('/prompt'):
            return {'prompt_id': 'pid'}
        return {'images': [b64]}

    def urlopen(req, **kwargs):
        requests.append((req.full_url, json.loads(req.data) if req.data else {}))
        return Response(raw)

    monkeypatch.setattr(backend, 'http_json', http_json)
    monkeypatch.setattr(backend.urlrequest, 'urlopen', urlopen)
    monkeypatch.setattr(codex_auth, 'get_credentials', lambda: codex_auth.Credentials(
        'offline-access-not-real', 'offline-refresh-not-real', 'offline-account', time.time() + 3600,
    ))

    def codex_post(url, payload, **kwargs):
        requests.append((url, payload))
        return {'data': [{'b64_json': b64}]}

    monkeypatch.setattr(codex_auth, 'post_json', codex_post)
    return root, requests, raw

@pytest.mark.parametrize('name', ['sdcpp', 'a1111', 'comfyui', 'image_api', 'openai_codex'])
def test_every_real_adapter_writes_only_to_the_explicit_private_owner(adapter_transport, monkeypatch, tmp_path, name):
    root, requests, raw = adapter_transport
    private = tmp_path / 'owned-private'
    private.mkdir()
    monkeypatch.setattr(generation, 'IMAGE_BACKEND', name)
    paths = generation._generate_backend_variants(
        {}, prompt='Literal authored brass fixture', negative='literal authored negative',
        asset_id='owner_probe', canvas=32, role='item', output_dir=private,
    )
    assert paths and all(Path(path).parent == private for path in paths)
    assert all(Path(path).read_bytes() == raw for path in paths)
    assert not list(root.glob('*.png'))
    assert not list(root.glob('*.part'))
    assert requests
    if name == 'comfyui':
        queued = next(payload for url, payload in requests if url.endswith('/prompt'))
        inputs = queued['prompt']['node']['inputs']
        assert inputs['logical_id'] == 'owner_probe'
        assert inputs['seed'] == 91023
        assert inputs['negative'] == 'literal authored negative'
        assert inputs['text'].endswith('Literal authored brass fixture')
    elif name == 'sdcpp':
        assert [payload['seed'] for url, payload in requests] == [731, 732]
    elif name == 'openai_codex':
        assert all(payload['prompt'] == 'Literal authored brass fixture\n\nAvoid: literal authored negative' for url, payload in requests)

@pytest.mark.parametrize('name', ['sdcpp', 'a1111', 'comfyui', 'image_api', 'openai_codex'])
def test_each_adapter_surfaces_raw_filesystem_errors_as_terminal_local_io(adapter_transport, monkeypatch, tmp_path, name):
    root, requests, raw = adapter_transport
    original_write = Path.write_bytes

    def denied_raw(path, contents):
        if '_raw_' in path.name:
            raise PermissionError('offline raw disk fault')
        return original_write(path, contents)

    monkeypatch.setattr(Path, 'write_bytes', denied_raw)
    # Codex uses its own atomic writer, not Path.write_bytes.
    if name == 'openai_codex':
        def denied_replace(*args):
            raise PermissionError('offline Codex raw commit fault')
        monkeypatch.setattr(backend.visual_asset_pipeline, 'generate_procedural_asset', lambda *args, **kwargs: pytest.fail('unexpected fallback'))
        from infini_local.services import codex_image_backend
        monkeypatch.setattr(codex_image_backend.os, 'replace', denied_replace)
    monkeypatch.setattr(generation, 'IMAGE_BACKEND', name)
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    monkeypatch.setattr(generation, 'VISUAL_ALLOW_PROCEDURAL_FALLBACK', True)
    monkeypatch.setattr(generation, 'VISUAL_STRICT_AI_AUTHORSHIP', False)
    data = {'id': 'raw-owner-fault', 'visual': {'imagePrompt': 'one isolated brass round fixture'}}
    result = generation.maybe_generate_sprite(data)
    assert result['visual']['spriteStatus'] == 'failed'
    assert result['visual']['spritePath'] == result['visual']['spriteUrl'] == result['visual']['spriteRawPath'] == ''
    assert result['debug']['itemSpriteFailurePhase'] == 'backend'
    assert len([url for url, payload in requests if not url.endswith('/view?filename=remote-fixture.png&subfolder=&type=output')]) == 1
    assert not list(root.glob('*.png'))

@pytest.mark.parametrize('seed', [0, 731, -1])
def test_private_output_ownership_never_becomes_a_seed_input(adapter_transport, monkeypatch, tmp_path, seed):
    root, requests, raw = adapter_transport
    monkeypatch.setattr(backend, 'SDCPP_SEED', seed)
    one = tmp_path / 'private-one'
    two = tmp_path / 'private-two'
    one.mkdir()
    two.mkdir()
    for owner in (one, two):
        backend.generate_sdcpp('authored prompt', 'authored negative', 'same_logical_id', 32, output_dir=owner)
    assert [payload['seed'] for url, payload in requests] == ([seed, seed + 1] * 2 if seed >= 0 else [91023] * 4)
    assert [payload['prompt'] for url, payload in requests] == ['authored prompt'] * 4
    assert one != two and sorted(path.name for path in one.iterdir()) == sorted(path.name for path in two.iterdir())

@pytest.mark.parametrize('layout', ['cutout', 'strip'])
def test_vfx_comfy_placeholder_preserves_the_accepted_nonce_digest_calls(adapter_transport, monkeypatch, layout):
    import hashlib
    from types import SimpleNamespace
    from tests.vfx_image_fixtures import _data, _request
    from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
    root, requests, raw = adapter_transport
    nonce = '0123456789abcdef0123456789abcdef'
    monkeypatch.setattr(generation.uuid, 'uuid4', lambda: SimpleNamespace(hex=nonce))
    monkeypatch.setattr(generation, 'IMAGE_BACKEND', 'comfyui')
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 1)
    downloads = []

    def corrupt_then_valid(req, **kwargs):
        downloads.append(req.full_url)
        return Response(b'corrupt Comfy image content' if len(downloads) == 1 else raw)

    monkeypatch.setattr(backend.urlrequest, 'urlopen', corrupt_then_valid)
    data = _data([_request('grain', layout=layout)])
    job = next(row for row in build_visual_asset_plan(data) if row['role'] == 'vfx:grain')
    result = generation.generate_visual_asset(data, 'vfx:grain', job['prompt'], job['negativePrompt'], job['assetId'], 32, processing_role='vfx_' + layout)
    assert result[3] == 'generated'
    prompts = [payload['prompt']['node']['inputs'] for url, payload in requests if url.endswith('/prompt')]
    expected_ids = ['infini_vfx_job_' + hashlib.sha256(f"{job['assetId']}\0{nonce}\0{attempt}".encode('utf-8')).hexdigest() for attempt in range(2)]
    assert [row['logical_id'] for row in prompts] == expected_ids
    assert [row['seed'] for row in prompts] == [91023, 91023]
    assert all(row['negative'] == job['negativePrompt'] for row in prompts)
    assert prompts[0]['text'].endswith(generation.normalize_asset_prompt(data, 'vfx_' + layout, job['prompt'], 32))
    assert 'STRICT RETRY 1' in prompts[1]['text']
    assert len(downloads) == 2

@pytest.mark.parametrize("configured_seed", [0, 731])
def test_real_adapter_retry_keeps_raw_evidence_unique_and_configured_seeds(offline_backend, monkeypatch, tmp_path, configured_seed):
    """Execute the adapter/request decoder; urlopen returns authored offline bytes."""
    backend = image_backend_pipeline
    # Hydrate ordinary item/entity producers with the same offline fixture seam.
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request("band", layout="strip")]))
    requests = []
    all_raw_paths = []
    fixtures = [b"offline corrupt first-attempt PNG", b"offline corrupt second-attempt PNG"]
    image = Image.new("RGBA", (64, 64), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 16, 63, 23), fill=(210, 100, 20, 144))
    draw.rectangle((48, 16, 63, 23), fill=(30, 90, 210, 144))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    fixtures.append(stream.getvalue())

    class FixtureResponse(io.BytesIO):
        headers = {"Content-Type": "image/png"}

    def offline_urlopen(request, **kwargs):
        requests.append(json.loads(request.data))
        return FixtureResponse(fixtures[(len(requests) - 1) // 2])

    original_adapter = backend.generate_sdcpp

    def real_adapter(prompt, negative, asset_id, canvas, *, output_dir=None):
        paths = original_adapter(prompt, negative, asset_id, canvas, output_dir=output_dir)
        all_raw_paths.append([Path(path) for path in paths])
        return paths

    monkeypatch.setattr(backend, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(backend, "ensure_sdcpp_server", lambda: True)
    monkeypatch.setattr(backend, "_effective_sdcpp_lora_prompt_tags", lambda: "")
    monkeypatch.setattr(backend.urlrequest, "urlopen", offline_urlopen)
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 2)
    monkeypatch.setattr(backend, "SDCPP_SEED", configured_seed)
    monkeypatch.setattr(backend, "SDCPP_SERVER_TXT2IMG_PATHS", ["/sdapi/v1/txt2img"])
    monkeypatch.setattr(backend, "SDCPP_SERVER_PAYLOAD_STYLE", "a1111")
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", real_adapter)
    monkeypatch.setattr(visual_sprite_generation, "SPRITE_RETRIES", 2)
    job = next(row for row in build_visual_asset_plan(data) if row["role"] == "vfx:band")
    result = visual_sprite_generation.generate_visual_asset(
        data, "vfx:band", job["prompt"], job["negativePrompt"], job["assetId"], job["canvas"],
        processing_role="vfx_strip",
    )
    assert result[3] == "generated", data["debug"]
    assert len(requests) == 6 and len(all_raw_paths) == 3
    assert [row["seed"] for row in requests] == [configured_seed, configured_seed + 1] * 3
    attempts = json.loads(data["debug"]["vfx:bandSpriteValidation"])
    assert [row["attempt"] for row in attempts] == [0, 1, 2]
    assert attempts[-1]["validation"]["ok"]
    with Image.open(result[0]) as final:
        assert final.size == (32, 32)
        alpha = final.getchannel("A")
        assert alpha.getbbox() == (0, 8, 32, 12)
        assert alpha.getpixel((0, 8)) == alpha.getpixel((31, 11)) == 144
    flattened = [path for paths in all_raw_paths for path in paths]
    assert len({path.name.casefold() for path in flattened}) == 6, "retry raw filenames alias after the real adapter's 80-character stem projection"
    for index, paths in enumerate(all_raw_paths):
        assert all(path.read_bytes() == fixtures[index] for path in paths)
    data["vfxManifest"]["assets"][0].update(
        spritePath=result[0], spriteUrl=result[1], spriteTechnicalScore=result[2], spriteStatus=result[3],
    )
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report["ok"], report["problems"]
