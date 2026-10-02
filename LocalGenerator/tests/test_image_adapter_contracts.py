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
from infini_local.services import codex_auth, asset_sync_service
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
    monkeypatch.setattr(backend, 'urlopen_no_redirect', urlopen)
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

@pytest.mark.parametrize('key,content,expected_calls', [
    ('path', 'denied', 1), ('file', 'missing', 1),
    ('filename', 'directory', 1), ('output_path', 'denied', 1),
    ('path', 'readable', 1), ('file', 'malformed_then_valid', 2),
    ('path', 'malformed', 3),
])
def test_sdcpp_local_response_read_failure_never_retries_or_substitutes_art(
    offline, monkeypatch, tmp_path, key, content, expected_calls,
):
    root, _ = offline
    source = tmp_path / 'provider.png'
    raw = png((210, 100, 20))
    if content == 'directory':
        source.mkdir()
    elif content != 'missing':
        source.write_bytes(raw)
    read_bytes = Path.read_bytes

    def read(path):
        if path == source and content == 'denied':
            raise PermissionError(13, 'offline provider source read denied', str(path))
        return read_bytes(path)

    requests = []

    def response(req, **kwargs):
        requests.append(json.loads(req.data))
        if content == 'malformed' or content == 'malformed_then_valid' and len(requests) == 1:
            source.write_bytes(b'not an image: offline provider content')
        elif content == 'malformed_then_valid':
            source.write_bytes(raw)
        result = Response(json.dumps({key: str(source)}).encode('utf-8'))
        result.headers = {'Content-Type': 'application/json'}
        return result

    monkeypatch.setattr(Path, 'read_bytes', read)
    monkeypatch.setattr(backend, 'urlopen_no_redirect', response)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_PAYLOAD_STYLE', 'auto')
    monkeypatch.setattr(backend, 'zimage_positive_only_enabled', lambda: False)
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    terminal_io = content in {'denied', 'missing', 'directory'}
    monkeypatch.setattr(generation, 'VISUAL_ALLOW_PROCEDURAL_FALLBACK', terminal_io)
    monkeypatch.setattr(generation, 'VISUAL_STRICT_AI_AUTHORSHIP', not terminal_io)
    data = {'id': 'literal_local_response', 'visual': {
        'imagePrompt': 'one isolated amber ring fixture', 'negativePrompt': 'literal negative',
    }}
    result = generation.maybe_generate_sprite(data)
    assert len(requests) == expected_calls, 'local source I/O consumed transport/quality retry budget'
    assert all(row.get('seed') == 731 for row in requests)
    assert all(row.get('negative_prompt') == 'literal negative' for row in requests)
    if terminal_io:
        visual = result['visual']
        assert visual['spriteStatus'] == 'failed'
        assert visual['spritePath'] == visual['spriteUrl'] == visual['spriteRawPath'] == ''
        assert result['debug']['itemSpriteFailurePhase'] == 'backend'
        assert not list(root.glob('*.png'))
    elif content != 'malformed':
        assert result['visual']['spriteStatus'] == 'generated'
        assert asset_sync_service.is_complete_png_file(result['visual']['spritePath'])
        if expected_calls == 2:
            assert 'STRICT RETRY 1' in requests[1]['prompt']
    else:
        assert result['visual']['spriteStatus'] == 'failed'
    diagnostics = json.loads(result['debug']['itemSpriteDiagnostics'])
    assert not Path(diagnostics['directory']).is_relative_to(root)
    assert generation.IMAGE_GENERATION_GATE._semaphore.acquire(blocking=False)
    generation.IMAGE_GENERATION_GATE._semaphore.release()


@pytest.mark.parametrize('kind,returned_url', [
    ('sdcpp', False), ('sdcpp', True), ('image_api', False), ('image_api', True),
    ('binary_get', False),
])
def test_image_dripping_body_deadline_releases_gate_without_retry_or_dev_art(
    offline, monkeypatch, kind, returned_url,
):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib import request as urlrequest
    from infini_local.core import http_io

    root, _ = offline
    raw = png((210, 100, 20))
    wire_calls, deadlines = [], []
    body_started = threading.Event()
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def reply(self, contents, ctype, drip):
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(contents)))
            self.end_headers()
            body_started.set()
            try:
                for index in range(0, len(contents), 8 if drip else len(contents)):
                    self.wfile.write(contents[index:index + (8 if drip else len(contents))])
                    self.wfile.flush()
                    if drip and stop.wait(0.01):
                        break
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            wire_calls.append(('POST', self.path, payload))
            healthy = 'healthy' in payload['prompt']
            if returned_url:
                image_url = f'http://127.0.0.1:{server.server_port}/' + ('healthy.png' if healthy else 'image.png')
                self.reply(json.dumps({'data': [{'url': image_url}]}).encode(), 'application/json', False)
            else:
                self.reply(raw, 'image/png', not healthy)

        def do_GET(self):
            wire_calls.append(('GET', self.path, None))
            self.reply(raw, 'image/png', not self.path.startswith('/healthy'))

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    # Restore real loopback HTTP, overriding only the offline fixture seam.
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    monkeypatch.setenv('no_proxy', '127.0.0.1')
    monkeypatch.setattr(backend.urlrequest, 'urlopen', urlrequest.build_opener(urlrequest.ProxyHandler({})).open)

    def real_open(req, *, deadline):
        deadlines.append(deadline)
        return http_io.urlopen_no_redirect(req, deadline=deadline)

    monkeypatch.setattr(backend, 'urlopen_no_redirect', real_open, raising=False)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_URL', url)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_REQUEST_TIMEOUT', 0.08)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_PAYLOAD_STYLE', 'auto')
    monkeypatch.setattr(backend, 'IMAGE_API_BASE_URL', url)
    monkeypatch.setattr(backend, 'IMAGE_API_KEY', 'offline-not-a-secret')
    monkeypatch.setattr(backend, 'IMAGE_API_PATH', '/images/generations')
    monkeypatch.setattr(backend, 'IMAGE_API_TIMEOUT', 0.08)
    monkeypatch.setattr(generation, 'IMAGE_BACKEND', kind)
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    monkeypatch.setattr(generation, 'VISUAL_ALLOW_PROCEDURAL_FALLBACK', True)
    monkeypatch.setattr(generation, 'VISUAL_STRICT_AI_AUTHORSHIP', False)
    try:
        started = time.monotonic()
        if kind == 'binary_get':
            with pytest.raises(http_io.HttpDeadlineExceeded):
                backend.http_binary_get(url + '/image.png', timeout=0.08)
        else:
            data = {'id': 'deadline_fixture', 'visual': {'imagePrompt': 'one isolated amber deadline fixture'}}
            result = generation.maybe_generate_sprite(data)
            visual = result['visual']
            assert visual['spriteStatus'] == 'failed', 'socket-idle timeout adopted a trickling image'
            assert visual['spritePath'] == visual['spriteUrl'] == visual['spriteRawPath'] == ''
            assert result['debug']['itemSpriteFailurePhase'] == 'backend'
            assert len([row for row in wire_calls if row[0] == 'POST']) == 1
            assert not list(root.glob('*.png'))
        elapsed = time.monotonic() - started
        assert body_started.is_set() and elapsed < 0.6
        assert deadlines and len(set(deadlines)) == 1, 'POST and returned-URL reads reset the logical image budget'
        assert generation.IMAGE_GENERATION_GATE._semaphore.acquire(blocking=False)
        generation.IMAGE_GENERATION_GATE._semaphore.release()
        # A real healthy sibling can still use the released admission slot.
        if kind == 'binary_get':
            assert backend.http_binary_get(url + '/healthy.png', timeout=1) == raw
        else:
            healthy = generation.maybe_generate_sprite({'id': 'healthy', 'visual': {'imagePrompt': 'one isolated healthy amber fixture'}})
            assert healthy['visual']['spriteStatus'] == 'generated'
            assert asset_sync_service.is_complete_png_file(healthy['visual']['spritePath'])
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
        assert not thread.is_alive()


@pytest.mark.parametrize('overall_timeout', [0.025, 0.6], ids=['whole-budget-expired', 'advisory-only-expired'])
def test_lora_catalog_subdeadline_does_not_cancel_remaining_image_budget(offline, monkeypatch, tmp_path, overall_timeout):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from infini_local.core import http_io

    raw = png((210, 100, 20))
    release, entered = threading.Event(), threading.Event()
    posts, outer_deadlines, post_deadlines = [], [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', '2')
            self.end_headers()
            entered.set()
            release.wait(2)
            try:
                self.wfile.write(b'[]')
            except OSError:
                pass

        def do_POST(self):
            posts.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
    worker.start()
    actual_catalog_get = backend.http_json_get

    def short_catalog(url, timeout, *, deadline):
        outer_deadlines.append(deadline)
        # Scale only the advisory 5s subbudget; actual socket/read/deadline code runs.
        return actual_catalog_get(url, timeout=min(timeout, 0.08), deadline=deadline)

    def open_request(req, *, deadline):
        if req.get_method() == 'POST':
            post_deadlines.append(deadline)
        return http_io.urlopen_no_redirect(req, deadline=deadline)

    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    monkeypatch.setenv('no_proxy', '127.0.0.1')
    monkeypatch.setattr(backend, 'http_json_get', short_catalog)
    monkeypatch.setattr(backend, 'urlopen_no_redirect', open_request)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_URL', f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setattr(backend, 'SDCPP_SERVER_REQUEST_TIMEOUT', overall_timeout)
    monkeypatch.setattr(backend, 'GENERATE_VARIANTS', 1)
    monkeypatch.setattr(backend, '_effective_sdcpp_lora_prompt_tags', lambda: '<lora:fixture:1>')
    private = tmp_path / 'private'
    private.mkdir()
    try:
        if overall_timeout < 0.08:
            with pytest.raises(http_io.HttpDeadlineExceeded):
                backend.generate_sdcpp_server('literal fixture', '', 'budget', output_dir=private)
            assert not posts and not list(private.iterdir())
        else:
            paths = backend.generate_sdcpp_server('literal fixture', '', 'budget', output_dir=private)
            assert len(posts) == len(paths) == 1
            assert Path(paths[0]).read_bytes() == raw
            assert post_deadlines == outer_deadlines, 'continuation must not reset the original image budget'
        assert entered.is_set()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(2)
        assert not worker.is_alive()


@pytest.mark.parametrize('kind,expected_calls', [('sdcpp', 3), ('image_api', 2)])
def test_image_negotiation_closes_rejected_http_response_bodies(offline, monkeypatch, kind, expected_calls):
    from urllib.error import HTTPError
    from email.message import Message

    errors = []

    def rejected(req, **kwargs):
        response = Response(b'explicit offline rejected provider body')
        code = 400 if kind == 'image_api' and not errors else 500
        error = HTTPError(req.full_url, code, 'offline response rejection', Message(), response)
        errors.append(error)  # Keep the exception alive: closure must not rely on GC.
        raise error

    monkeypatch.setattr(backend, 'urlopen_no_redirect', rejected)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_PAYLOAD_STYLE', 'auto')
    monkeypatch.setattr(backend, 'IMAGE_API_BASE_URL', 'https://offline.invalid')
    monkeypatch.setattr(backend, 'IMAGE_API_KEY', 'offline-fixture-not-a-secret')
    adapter = backend.generate_sdcpp_server if kind == 'sdcpp' else backend.generate_image_api
    assert adapter('literal prompt', 'literal negative', 'http_error_owner') == []
    assert len(errors) == expected_calls
    assert all(error.closed for error in errors), 'adapter leaked a rejected HTTP body across negotiation'


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

    monkeypatch.setattr(backend, 'urlopen_no_redirect', corrupt_then_valid)
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
    monkeypatch.setattr(backend, "urlopen_no_redirect", offline_urlopen)
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
