"""Offline canonical image attempt contracts; no live services."""
from __future__ import annotations
from infini_local.core import asset_files

import copy
import hashlib
import io
import json
import re
from pathlib import Path
import threading
import pytest
from PIL import Image, ImageDraw
from infini_local.pipelines.images import backends as backend
from infini_local.pipelines.images import postprocess as post
from infini_local.pipelines.images import stage as generation
from infini_local.pipelines.visual import delivery
from infini_local.pipelines.images import manifest
from infini_local.core.images import config
from infini_local.pipelines.visual.assets import build_visual_asset_plan
from infini_local.services import asset_sync_service as sync
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.web import server_utility_routes as routes
from tests.generator.vfx_image_fixtures import HttpCapture, _data, _request, _existing_texture_data

def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def png(color, strip=False):
    image = Image.new('RGBA', (64, 64), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    if strip:
        draw.rectangle((0, 16, 63, 23), fill=(*color, 144))
    else:
        draw.ellipse((8, 8, 55, 55), fill=(*color, 255))
        draw.rectangle((28, 8, 35, 55), fill=(210, 130, 50, 255))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()

class Response(io.BytesIO):
    headers = {'Content-Type': 'image/png'}


def serve(root, path, route='asset'):
    # Real route and filesystem with scoped serving roots, no HTTP listener.
    handler = HttpCapture()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(routes, "SPRITE_DIR", root)
        patch.setattr(routes, "WORLD_RECIPES_DIR", root / "world-recipes")
        if route == 'asset':
            routes.get_asset(handler, '/get_asset?file=' + Path(path).name)
        else:
            routes.sprite_file(handler, '/sprite/' + Path(path).name)
    return {'code': handler.code, 'headers': handler.headers, 'raw': handler.wfile.getvalue()}

@pytest.fixture
def offline(monkeypatch, request, tmp_path):
    root = tmp_path / 'runtime' / request.node.name.replace('[', '-').replace(']', '')
    root.mkdir(parents=True, exist_ok=True)
    for module in (backend, post, generation, delivery, manifest):
        monkeypatch.setattr(module, 'SPRITE_DIR', root)
    for module in (delivery, manifest):
        monkeypatch.setattr(module, 'WORLD_RECIPES_DIR', root / 'world-recipes')
    monkeypatch.setattr(generation, 'IMAGE_BACKEND', 'sdcpp')
    monkeypatch.setattr(generation, 'IMAGE_BACKEND_CONFIG_ERROR', '')
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 0)
    monkeypatch.setattr(generation, 'VISUAL_ASSET_MODE', 'full')
    monkeypatch.setattr(generation, 'IMAGE_GENERATION_GATE', ImageRequestGate(1))
    monkeypatch.setattr(generation, 'generate_sdcpp', backend.generate_sdcpp)
    monkeypatch.setattr(backend, 'ensure_sdcpp_server', lambda: True)
    monkeypatch.setattr(backend, '_effective_sdcpp_lora_prompt_tags', lambda: '')
    monkeypatch.setattr(backend, 'GENERATE_VARIANTS', 1)
    monkeypatch.setattr(backend, 'SDCPP_SEED', 731)
    monkeypatch.setattr(backend, 'SDCPP_SERVER_TXT2IMG_PATHS', ['/sdapi/v1/txt2img'])
    monkeypatch.setattr(backend, 'SDCPP_SERVER_PAYLOAD_STYLE', 'a1111')
    monkeypatch.setattr(config, 'IMAGE_BACKEND', 'sdcpp')
    monkeypatch.setattr(config, 'IMAGE_BACKEND_RAW', 'sdcpp')
    monkeypatch.setattr(config, 'REMOVE_BG', True)
    monkeypatch.setattr(config, 'BG_COLOR', 'magenta')
    monkeypatch.setattr(delivery, 'VISUAL_REQUIRE_ITEM_SPRITE', True)
    requests = []

    def urlopen(req, **kwargs):
        payload = json.loads(req.data)
        requests.append({'thread': threading.current_thread().name, 'payload': payload})
        color = (30, 180, 210) if threading.current_thread().name == 'second' or 'impact fixture' in payload['prompt'] else (210, 100, 20)
        return Response(png(color, strip='preserve the full authored frame' in payload['prompt']))

    monkeypatch.setattr(backend, 'urlopen_no_redirect', urlopen)
    return root, requests

def invoke(kind, asset_id, data=None):
    data = data if data is not None else _data([_request('grain', layout='strip' if kind == 'vfx_strip' else 'cutout')])
    if kind == 'item':
        data['id'] = asset_id
        output = generation.maybe_generate_sprite(data)['visual']
        return output['spritePath'], output['spriteUrl'], output['spriteTechnicalScore'], output['spriteStatus']
    if kind.startswith('vfx_'):
        job = next(row for row in build_visual_asset_plan(data) if row['role'] == 'vfx:grain')
        return generation.generate_visual_asset(data, 'vfx:grain', job['prompt'], job['negativePrompt'], job['assetId'], 32, processing_role=kind)
    role = 'runtime:projectile' if kind == 'entity' else kind
    return generation.generate_visual_asset(data, role, 'one isolated amber round fixture with distinct core', 'UI, text, atlas', asset_id, 32, entity_id='orb' if kind == 'entity' else '')

@pytest.mark.parametrize('kind,distinct_ids', [
    ('item', False), ('entity', False), ('impact', False), ('equip_overlay', False),
    ('item', True), ('entity', True), ('impact', True), ('equip_overlay', True),
    ('vfx_cutout', False), ('vfx_strip', False),
])
def test_overlap_must_preserve_each_validated_png(offline, monkeypatch, kind, distinct_ids):
    root, requests = offline
    first_validated = threading.Event()
    second_done = threading.Event()
    validated = {}
    returned = {}
    errors = {}
    real_validator = generation.validate_processed_sprite

    def validation_barrier(path, role, **kwargs):
        result = real_validator(path, role, **kwargs)
        name = threading.current_thread().name
        assert result['ok'], result
        validated[name] = {'raw': Path(path).read_bytes(), 'report': result, 'path': str(path)}
        if name == 'first':
            first_validated.set()
            assert second_done.wait(15), 'second never completed'
        return result

    def call():
        name = threading.current_thread().name
        try:
            asset_id = 'ownership_probe' + ('_second' if name == 'second' and distinct_ids else '')
            returned[name] = invoke(kind, asset_id)
        except BaseException as error:
            errors[name] = repr(error)
        finally:
            if name == 'second':
                second_done.set()

    monkeypatch.setattr(generation, 'validate_processed_sprite', validation_barrier)
    first = threading.Thread(target=call, name='first')
    second = threading.Thread(target=call, name='second')
    first.start()
    try:
        assert first_validated.wait(15), errors
        second.start()
        second.join(15)
        assert not second.is_alive()
    finally:
        second_done.set()
        first.join(15)
    assert not first.is_alive() and not errors, errors
    assert validated['first']['raw'] != validated['second']['raw']
    rows = {}
    for name, result in returned.items():
        served = serve(root, result[0])
        sprite = serve(root, result[0], 'sprite')
        rows[name] = {
            'result': result, 'validation_ok': validated[name]['report']['ok'],
            'validated_sha256': sha(validated[name]['raw']),
            'returned_sha256': sha(Path(result[0]).read_bytes()),
            'http_code': served['code'], 'http_sha256': sha(served['raw']),
            'http_headers': served['headers'], 'sprite_code': sprite['code'],
            'sprite_sha256': sha(sprite['raw']),
        }
    assert [row['payload']['seed'] for row in requests] == [731, 731]
    assert all(result[3] == 'generated' for result in returned.values()), returned
    assert not list(root.glob('.infini_vfx_png_*.part'))
    assert generation.IMAGE_GENERATION_GATE._semaphore.acquire(blocking=False)
    generation.IMAGE_GENERATION_GATE._semaphore.release()
    assert all(row['http_code'] == row['sprite_code'] == 200 for row in rows.values())
    for name, row in rows.items():
        assert row['validated_sha256'] == row['http_sha256'] == row['returned_sha256'], f'{kind}: {name} received another invocation\'s PNG'
    assert returned['first'][0] != returned['second'][0]


@pytest.mark.parametrize('name', ['procedural', 'offline', 'none'])
def test_retired_image_backend_refuses_publication(offline, monkeypatch, name):
    root, requests = offline
    monkeypatch.setattr(generation, 'IMAGE_BACKEND', name)
    data = _data([])
    result = invoke('item', 'retired_backend', data)
    assert result == ('', '', 0.0, 'backend_config_error')
    assert data['debug']['imageBackendConfigError'] == f'unsupported image backend: {name}'
    assert not requests and not list(root.rglob('*.png'))


@pytest.mark.parametrize('kind', ['item', 'entity', 'equip_overlay', 'vfx_cutout'])
def test_exhausted_provider_without_art_cannot_publish_a_replacement(offline, monkeypatch, kind):
    root, _ = offline
    calls = []

    def no_image(request, **kwargs):
        calls.append(json.loads(request.data))
        response = Response(b'{"images": []}')
        response.headers = {'Content-Type': 'application/json'}
        return response

    monkeypatch.setattr(backend, 'urlopen_no_redirect', no_image)
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 1)
    data = _data([_request('grain')])
    path, url, score, status = invoke(kind, 'missing_authored_art', data)
    assert (path, url, score, status) == ('', '', 0.0, 'failed')
    assert len(calls) == 2
    prefix = 'item' if kind == 'item' else 'runtime:projectile' if kind == 'entity' else 'vfx:grain' if kind.startswith('vfx_') else kind
    attempts = json.loads(data['debug'][prefix + 'SpriteValidation'])
    assert len(attempts) == 2 and all(row['category'] == 'no_image' for row in attempts)
    assert not list(root.rglob('*.png')), 'missing provider art was replaced with invented pixels'


@pytest.mark.parametrize('kind', ['item', 'vfx_strip'])
@pytest.mark.parametrize('content_fault', ['unidentified', 'truncated'])
def test_corrupt_provider_image_remains_a_bounded_quality_retry(offline, monkeypatch, kind, content_fault):
    root, requests = offline
    original_urlopen = backend.urlopen_no_redirect
    calls = []
    corrupt = b'not a PNG: provider content fault' if content_fault == 'unidentified' else png((210, 100, 20))[:60]
    if content_fault == 'truncated':
        from PIL import UnidentifiedImageError
        with pytest.raises(OSError) as caught:
            Image.open(io.BytesIO(corrupt)).convert('RGBA')
        assert not isinstance(caught.value, UnidentifiedImageError) and caught.value.errno is None

    def corrupt_then_valid(req, **kwargs):
        calls.append(json.loads(req.data))
        if len(calls) == 1:
            return Response(corrupt)
        return original_urlopen(req, **kwargs)

    monkeypatch.setattr(backend, 'urlopen_no_redirect', corrupt_then_valid)
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    result = invoke(kind, 'corrupt_quality')
    assert result[3] == 'generated' and Path(result[0]).exists()
    assert len(calls) == 2 and len(requests) == 1
    assert calls[0]['seed'] == calls[1]['seed'] == 731
    assert calls[1]['prompt'] != calls[0]['prompt']


def test_raw_provider_canvas_above_client_limit_still_processes_to_final_png(offline, monkeypatch):
    root, _ = offline
    with Image.open(io.BytesIO(png((210, 100, 20)))) as source:
        large = source.resize((1024, 1024), Image.Resampling.NEAREST)
    stream = io.BytesIO()
    large.save(stream, format='PNG')
    raw = stream.getvalue()
    monkeypatch.setattr(backend, 'urlopen_no_redirect', lambda *args, **kwargs: Response(raw))
    data = _data([])
    result = invoke('item', 'large_raw_canvas', data)
    assert result[3] == 'generated'
    with Image.open(data['visual']['spriteRawPath']) as source:
        assert source.size == (1024, 1024)
    assert Path(data['visual']['spriteRawPath']).read_bytes() == raw
    with Image.open(result[0]) as source:
        assert source.size == (32, 32)
    assert asset_files.is_complete_png_file(result[0])
    assert serve(root, result[0])['raw'] == Path(result[0]).read_bytes()


def test_non_io_projection_tail_still_recovers_source_art_with_warning(offline, monkeypatch):
    root, requests = offline
    original_trace = generation.trace_event
    data = _data([])

    def failed_accepted_trace(*args, **kwargs):
        if args[2] == 'sprite accepted':
            raise RuntimeError('offline non-IO accepted trace projection control')
        return original_trace(*args, **kwargs)

    monkeypatch.setattr(generation, 'trace_event', failed_accepted_trace)
    result = invoke('entity', 'trace_control', data)
    assert result[3] == 'generated_warn_invalid'
    assert len(requests) == 1
    assert asset_files.is_complete_png_file(result[0])
    attempts = json.loads(data['debug']['runtime:projectileSpriteValidation'])
    assert attempts[0]['validation']['ok'] and attempts[1]['phase'] == 'projection'
    assert data['debug']['runtime:projectileInvalidGeneratedUsedAsWarn']


def test_private_retained_raw_and_stages_are_not_served_or_rostered(offline, monkeypatch):
    root, requests = offline
    monkeypatch.setattr(post, 'SAVE_SPRITE_STAGES', True)
    data = _data([])
    for entity in data['runtimeProgram']['entities']:
        entity.get('visual', {}).pop('spritePath', None)
    result = invoke('item', 'private_diagnostics', data)
    assert result[3] == 'generated'
    diagnostics = json.loads(data['debug']['itemSpriteDiagnostics'])
    assert diagnostics['retention'] == 'retained_private'
    private = Path(diagnostics['directory'])
    raw = Path(data['visual']['spriteRawPath'])
    assert raw.exists() and raw.is_relative_to(private)
    evidence = [raw, *private.rglob('*_stage_*.png')]
    assert len(evidence) == 4  # The accepted final bake is referenced, never copied.
    assert all(path.exists() and path.is_relative_to(private) for path in evidence)
    assert not list(private.rglob("*_stage_30_baked_final.png"))
    for path in evidence:
        assert serve(root, path)['code'] == serve(root, path, 'sprite')['code'] == 404
    assert sync.runtime_asset_files(data) == [Path(result[0]).name]
    assert serve(root, result[0])['raw'] == Path(result[0]).read_bytes()


def test_new_publication_identity_is_exact_structured_role_entity_recipe_and_bytes(offline):
    root, requests = offline
    data = _data([])
    data['id'] = 'Точный_Recipe'
    outcomes = []
    for role, entity in [('runtime:projectile', 'orb'), ('runtime:projectile', 'Orb'), ('impact', 'orb')]:
        result = generation.generate_visual_asset(data, role, 'one isolated round fixture', 'authored negative', 'same_logical_id', 32, entity_id=entity)
        assert result[3] == 'generated'
        raw = Path(result[0]).read_bytes()
        identity = json.dumps([data['id'], role, entity, 'same_logical_id'], ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
        scope = json.dumps([str(data.get('recipeMeta', {}).get('worldId') or 'unscoped'), data['id'], role], ensure_ascii=True, separators=(',', ':')).encode('ascii')
        label = re.sub(r'[^a-z0-9_-]+', '_', role.lower()).strip('_')[:24]
        expected = label + '--' + sha(scope + b'\0' + identity + b'\0' + raw) + '.png'
        assert Path(result[0]).name == expected
        outcomes.append(result[0])
    assert len(set(outcomes)) == 3

@pytest.mark.parametrize('kind', ['vfx_cutout', 'vfx_strip'])
def test_vfx_publication_preserves_identity_with_world_scoped_storage(offline, kind):
    root, requests = offline
    data = _data([_request('grain', layout='strip' if kind == 'vfx_strip' else 'cutout')])
    result = invoke(kind, 'ignored_vfx_id', data)
    assert result[3] == 'generated'
    raw = Path(result[0]).read_bytes()
    identity = json.dumps([data['vfxManifest']['recipeId'], 'grain'], ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    scope = json.dumps([str(data.get('recipeMeta', {}).get('worldId') or 'unscoped'), data['id'], 'vfx_grain'], ensure_ascii=True, separators=(',', ':')).encode('ascii')
    assert Path(result[0]).name == 'vfx_grain--' + sha(scope + b'\0' + identity + b'\0' + raw) + '.png'

@pytest.mark.parametrize('save_stages', [False, True])
def test_logical_path_tokens_cannot_escape_the_private_output_owner(offline, monkeypatch, save_stages):
    root, requests = offline
    workspace = root.parent / 'private-invocation'
    workspace.mkdir()
    monkeypatch.setattr(generation, '_new_image_workspace', lambda *args: workspace)
    monkeypatch.setattr(post, 'SAVE_SPRITE_STAGES', save_stages)
    victim = root.parent.parent / 'victim.png'
    victim.write_bytes(png((10, 90, 220)))
    previous = victim.read_bytes()
    original = generation._generate_backend_variants
    logical_ids = []

    def capture(data, **kwargs):
        logical_ids.append(kwargs['asset_id'])
        return original(data, **kwargs)

    monkeypatch.setattr(generation, '_generate_backend_variants', capture)
    data = _data([])
    result = invoke('item', '../../../victim', data)
    assert result[3] == 'generated'
    assert logical_ids == ['../../../victim'], 'storage isolation changed semantic backend identity'
    assert victim.read_bytes() == previous, 'logical identity escaped its owned output directory'
    attempts = json.loads(data['debug']['itemSpriteValidation'])
    assert all(Path(row['raw']).resolve().is_relative_to(workspace / 'attempt-0') for row in attempts)
    assert all(Path(row['final']) == Path(result[0]) for row in attempts)



IMAGE_ROLES = ("item", "entity", "impact", "equip_overlay", "vfx_cutout", "vfx_strip")
IO_CASES = (
    [(kind, "final_save", "processing") for kind in IMAGE_ROLES]
    + [("item", "stage:" + stage, "processing") for stage in
       ("00_raw", "10_sprite_keyer_fullres", "20_master_norm", "30_baked_final")]
    + [("item", "raw_write", "backend"), ("item", "refit_save", "processing")]
    + [(kind, "master", "processing") for kind in ("item", "entity", "vfx_cutout")]
    + [("item", "attempt_mkdir", "processing"), ("item", "metrics", "projection")]
    + [(kind, "trace", "projection") for kind in ("item", "entity")]
    # All roles share the atomic publisher. Exercise each filesystem failure on
    # item, plus publication failure/ownership projection through every role.
    + [("item", fault, "publication") for fault in ("replace", "fsync", "mkstemp")]
    + [(kind, "replace", "publication") for kind in IMAGE_ROLES if kind != "item"]
)

@pytest.mark.parametrize("kind,fault,phase", IO_CASES, ids=[kind + "-" + fault for kind, fault, _ in IO_CASES])
def test_local_io_is_terminal_and_owned(offline, monkeypatch, kind, fault, phase):
    root, requests = offline
    data = _data([_request("grain", layout="strip" if kind == "vfx_strip" else "cutout")])
    previous = invoke(kind, "io_contract", copy.deepcopy(data)) if phase == "publication" else None
    old_bytes = Path(previous[0]).read_bytes() if previous else None
    foreign_part = root / ".another-owner.part"
    if previous:
        foreign_part.write_bytes(b"another invocation owns this")
    requests.clear()
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 2)
    calls = []
    if fault.startswith("stage:"):
        monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", True)
    if fault == "refit_save":
        validate = generation.validate_processed_sprite
        def force_refit(path, role, **kwargs):
            report = validate(path, role, **kwargs)
            if not Path(path).name.endswith("_refit.png"):
                report.update(ok=False, reasons=["core_silhouette_too_small:12px<24px"])
                report["bboxStats"].update(core_bbox=[12, 12, 20, 20], spec={"marginPx": 1, "targetLongAxisPx": 28})
            return report
        monkeypatch.setattr(generation, "validate_processed_sprite", force_refit)
    owner, attribute = (
        (Image.Image, "save") if fault == "final_save" or fault == "refit_save" or fault.startswith("stage:")
        else (Path, "write_bytes") if fault == "raw_write"
        else (Path, "mkdir") if fault == "attempt_mkdir"
        else (post, "prepare_sprite_master") if fault == "master"
        else (generation, "attach_visual_soul_from_sprite") if fault == "metrics"
        else (generation, "trace_event") if fault == "trace"
        else (generation.tempfile, "mkstemp") if fault == "mkstemp"
        else (generation.os, fault)
    )
    original = getattr(owner, attribute)
    def denied(*args, **kwargs):
        destination = args[1] if attribute == "save" else args[0] if args else ""
        name = Path(destination).name if isinstance(destination, (str, Path)) else ""
        selected = (
            (name.endswith(".png") and "_raw_" not in name and "_stage_" not in name) if fault == "final_save"
            else name.endswith("_stage_" + fault.split(":", 1)[1] + ".png") if fault.startswith("stage:")
            else name.endswith("_refit.png") if fault == "refit_save"
            else "_raw_sdcpp_" in name if fault == "raw_write"
            else name.startswith("attempt-") if attribute == "mkdir"
            else args[2] == "sprite accepted" if fault == "trace"
            else kwargs.get("suffix") == ".part" if fault == "mkstemp"
            else True
        )
        if selected:
            calls.append((args, kwargs))
            if fault == "replace":
                assert Path(args[0]).suffix == ".part"
                assert asset_files.is_complete_png_file(args[0])
            raise PermissionError("offline owned " + fault + " denied")
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, attribute, denied)
    result = invoke(kind, "io_contract", data)
    assert calls, "fault never reached its production boundary"
    assert result[3] == "failed" and result[0] == result[1] == ""
    assert len(requests) == (0 if fault == "attempt_mkdir" else 1), "local I/O consumed quality retries"
    prefix = "item" if kind == "item" else "runtime:projectile" if kind == "entity" else "vfx:grain" if kind.startswith("vfx_") else kind
    assert data["debug"][prefix + "SpriteFailurePhase"] == phase
    if fault == "attempt_mkdir":
        assert len(calls) == 1
    if fault == "metrics":
        assert data["visual"]["spriteRawPath"] == ""
    if previous:
        assert Path(previous[0]).read_bytes() == old_bytes
        assert foreign_part.read_bytes() == b"another invocation owns this"
        assert list(root.glob("*.part")) == [foreign_part]
    else:
        assert not list(root.glob("*.part"))
        if fault == "final_save":
            assert not list(root.glob("infini_*_png_*.png"))


@pytest.mark.parametrize('kind,raw_size', [
    ('item', (80, 112)),
    ('entity', (128, 80)),
    ('impact', (96, 144)),
    ('equip_overlay', (120, 120)),
])
def test_processing_fault_still_delivers_compact_alpha_png(offline, monkeypatch, kind, raw_size):
    """A valid generated image survives a broken master step without extra model calls."""
    root, _ = offline
    with Image.open(io.BytesIO(png((210, 100, 20)))) as source:
        expanded = source.resize(raw_size, Image.Resampling.NEAREST)
    stream = io.BytesIO()
    expanded.save(stream, format='PNG')
    raw_bytes = stream.getvalue()
    requests = []

    def provide(request, **kwargs):
        requests.append(request)
        return Response(raw_bytes)

    monkeypatch.setattr(backend, 'urlopen_no_redirect', provide)
    monkeypatch.setattr(post, 'prepare_sprite_master',
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('master broken')))
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 1)
    data = _data([])
    path, url, _score, status = invoke(kind, 'technical_bake_' + kind, data)

    assert status in {'generated', 'generated_warn_invalid'} and path and url
    assert len(requests) == 1, 'an already usable picture should not need another LLM/image request'
    with Image.open(path) as delivered:
        assert delivered.size == (32, 32)
        assert delivered.getchannel('A').getextrema()[0] == 0
    assert asset_files.is_complete_png_file(path)
    assert Path(path).read_bytes() != raw_bytes
    assert serve(root, path)['raw'] == Path(path).read_bytes(), 'friends receive the same final PNG'
    key = 'item' if kind == 'item' else 'runtime:projectile' if kind == 'entity' else kind
    receipt = json.loads(data['debug'][key + 'SpriteValidation'])
    assert len(receipt) == 1 and 'final_canvas_mismatch' not in receipt[0]['validation']['reasons']
    assert Path(receipt[0]['raw']).exists(), 'raw input remains a private diagnostic'


@pytest.mark.parametrize('target', [16, 48, 64, 96, 128])
def test_technical_downscale_respects_any_authored_final_canvas(offline, monkeypatch, target):
    """No special 512/1024 size branches: the exact selected canvas wins."""
    root, _ = offline
    source = root / 'transparent-source.png'
    image = Image.new('RGBA', (87, 135), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((5, 5, 81, 129), fill=(220, 115, 40, 255))
    image.save(source, format='PNG')
    monkeypatch.setattr(post, 'prepare_sprite_master',
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('master broken')))
    out = post.postprocess_sprite(str(source), 'final_' + str(target), target_size=target,
                                  role='item', output_dir=root)
    with Image.open(out) as delivered:
        assert delivered.size == (target, target)
        assert delivered.getchannel('A').getextrema()[0] == 0
    assert asset_files.is_complete_png_file(out)


def test_postprocess_without_alpha_cannot_smuggle_opaque_raw_background(offline, monkeypatch):
    """If no transparent stage exists, retry/failed is safer than a poster-card PNG."""
    root, requests = offline
    monkeypatch.setattr(post, 'apply_background_removal',
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('keyer unavailable')))
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 1)
    data = _data([])
    path, url, _score, status = invoke('item', 'opaque_background', data)
    assert (path, url, status) == ('', '', 'failed')
    assert len(requests) == 2, 'both bounded attempts remain available'
    assert not list(root.glob('infini_asset_png_*.png'))


def test_transient_unrecoverable_keying_retries_then_delivers_compact_png(offline, monkeypatch):
    """Real processing recovers on the next attempt when minimal bake cannot."""
    root, requests = offline
    original = generation.postprocess_sprite
    calls = []

    def processing_only_flaky(*args, **kwargs):
        # Selection also calls apply_background_removal; inject the failure
        # ONLY into the first real postprocess call, not candidate scoring.
        calls.append(True)
        if len(calls) == 1:
            # Exercise the cold processing path: a valid selected preparation
            # intentionally bypasses keying, whose failure this control injects.
            kwargs['prepared'] = None
            with monkeypatch.context() as patch:
                patch.setattr(post, 'apply_background_removal',
                              lambda *_a, **_k: (_ for _ in ()).throw(ValueError('temporary keyer failure')))
                return original(*args, **kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(generation, 'postprocess_sprite', processing_only_flaky)
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 1)
    data = _data([])
    path, url, _score, status = invoke('item', 'recovered_after_retry', data)
    assert len(requests) == len(calls) == 2
    assert status == 'generated' and path and url
    with Image.open(path) as delivered:
        assert delivered.size == (32, 32)
    assert asset_files.is_complete_png_file(path)
    assert serve(root, path)['raw'] == Path(path).read_bytes()
    receipt = json.loads(data['debug']['itemSpriteValidation'])
    assert len(receipt) == 2 and receipt[0]['phase'] == 'processing'
    assert receipt[1]['validation']['ok']


def test_failing_final_palette_step_still_delivers_from_finished_master(offline, monkeypatch):
    """When master succeeded, reuse it rather than downgrading to the raw source."""
    root, requests = offline
    monkeypatch.setattr(post, 'bake_sprite_from_master',
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('bake failed')))
    data = _data([])
    path, url, _score, status = invoke('item', 'master_recovery', data)
    assert status in {'generated', 'generated_warn_invalid'} and path and url
    assert len(requests) == 1
    with Image.open(path) as delivered:
        assert delivered.size == (32, 32)
    assert serve(root, path)['raw'] == Path(path).read_bytes()


def native_codex_responses(monkeypatch, alpha_values):
    """Actual Codex adapter, PNG writes and processing; replace only HTTP/auth."""
    import base64
    import time
    from infini_local.services import codex_auth

    monkeypatch.setattr(generation, 'IMAGE_BACKEND', 'openai_codex')
    monkeypatch.setattr(config, 'IMAGE_BACKEND', 'openai_codex')
    monkeypatch.setattr(config, 'IMAGE_BACKEND_RAW', 'openai_codex')
    monkeypatch.setattr(config, 'REMOVE_BG', False)
    monkeypatch.setattr(config, 'BG_COLOR', 'transparent')
    credentials = codex_auth.Credentials('offline-access-not-real', 'offline-refresh-not-real', 'offline-account', time.time() + 3600)
    monkeypatch.setattr(codex_auth, 'get_credentials', lambda: credentials)
    calls = []

    def respond(url, payload, **kwargs):
        assert url == 'https://chatgpt.com/backend-api/codex/images/generations'
        assert payload['background'] == 'transparent'
        alpha = alpha_values[len(calls)]
        image = Image.new('RGBA', (64, 64), (235, 235, 235, alpha))
        ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(130, 180, 50, 255 if alpha == 255 else 144))
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        calls.append({'payload': payload, 'raw': stream.getvalue()})
        return {'data': [{'b64_json': base64.b64encode(stream.getvalue()).decode()}]}

    monkeypatch.setattr(codex_auth, 'post_json', respond)
    return calls


@pytest.mark.parametrize('background_alpha', [1, 2])
def test_codex_near_clear_field_delivers_first_attempt_without_quality_retry(offline, monkeypatch, background_alpha):
    root, _ = offline
    calls = native_codex_responses(monkeypatch, [background_alpha])
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    data = _data([])
    result = invoke('runtime:field', 'soft_field', data)
    assert result[3] == 'generated' and result[0]
    assert len(calls) == 1, 'near-clear native alpha spent another image request'
    attempts = json.loads(data['debug']['runtime:fieldSpriteValidation'])
    assert len(attempts) == 1 and attempts[0]['validation']['ok']
    assert Path(attempts[0]['raw']).read_bytes() == calls[0]['raw']
    assert serve(root, result[0])['raw'] == Path(result[0]).read_bytes()
    with Image.open(result[0]) as final:
        assert sum(final.getchannel('A').histogram()[1:255]) > 0


@pytest.mark.parametrize('kind,prefix', [('item', 'item'), ('runtime:field', 'runtime:field'), ('vfx_cutout', 'vfx:grain')])
def test_background_retry_uses_exact_reason_and_clears_current_error_on_success(offline, monkeypatch, kind, prefix):
    root, _ = offline
    calls = native_codex_responses(monkeypatch, [255, 0])
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    error_key = 'spriteError' if kind == 'item' else prefix + 'SpriteError'
    data = _data([_request('grain')])
    data['debug'] = {error_key: 'an error from a previous invocation'}
    result = invoke(kind, 'background_retry', data)
    assert result[3] == 'generated' and result[0]
    assert len(calls) == 2
    attempts = json.loads(data['debug'][prefix + 'SpriteValidation'])
    assert attempts[0]['phase'] == 'processing'
    assert attempts[0]['validation']['reasons'] == ['native_alpha_raw_background_opaque']
    assert Path(attempts[0]['raw']).read_bytes() == calls[0]['raw']
    assert 'empty transparent space around the authored subject' in calls[1]['payload']['prompt']
    assert attempts[1]['validation']['ok']
    assert error_key not in data['debug'], 'a successful retry retained an active SpriteError'
    assert prefix + 'SpriteFailurePhase' not in data['debug']
    assert 'RawSpriteBackgroundError' in attempts[0]['error'], 'historical evidence must remain'
    assert serve(root, result[0])['raw'] == Path(result[0]).read_bytes()


def test_visible_background_still_fails_with_bounded_targeted_codex_retry(offline, monkeypatch):
    root, _ = offline
    calls = native_codex_responses(monkeypatch, [128, 128])
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 1)
    data = _data([])
    result = invoke('runtime:field', 'visible_matte', data)
    assert result[3] == 'failed' and not result[0] and not result[1]
    assert len(calls) == 2
    attempts = json.loads(data['debug']['runtime:fieldSpriteValidation'])
    assert all(row['validation']['reasons'] == ['raw_background_not_removed'] for row in attempts)
    assert 'empty transparent space around the authored subject' in calls[1]['payload']['prompt']
    assert 'RawSpriteBackgroundError' in data['debug']['runtime:fieldSpriteError']
    assert not list(root.glob('infini_asset_png_*.png'))


def test_retry_diagnostic_does_not_leak_from_an_older_failed_attempt(offline, monkeypatch):
    calls = native_codex_responses(monkeypatch, [255, 0, 0])
    monkeypatch.setattr(generation, 'SPRITE_RETRIES', 2)
    process = generation.postprocess_sprite

    def second_attempt_error(path, asset_id, *args, **kwargs):
        if asset_id.endswith('_retry1'):
            raise RuntimeError('injected processing fault without a provider-content diagnosis')
        return process(path, asset_id, *args, **kwargs)

    monkeypatch.setattr(generation, 'postprocess_sprite', second_attempt_error)
    data = _data([])
    result = invoke('runtime:field', 'distinct_failures', data)
    assert result[3] == 'generated' and result[0]
    assert len(calls) == 3
    assert 'fix these technical issues' in calls[1]['payload']['prompt']
    assert 'fix these technical issues' not in calls[2]['payload']['prompt']
    attempts = json.loads(data['debug']['runtime:fieldSpriteValidation'])
    assert attempts[0]['validation']['reasons'] == ['native_alpha_raw_background_opaque']
    assert 'validation' not in attempts[1]
    assert attempts[2]['validation']['ok']
    assert 'runtime:fieldSpriteError' not in data['debug']
