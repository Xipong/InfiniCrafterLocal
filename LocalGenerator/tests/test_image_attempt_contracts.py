"""Offline canonical image attempt contracts; no live services."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import os
import threading
import pytest
from PIL import Image, ImageDraw
from infini_local.pipelines import image_backend_pipeline as backend
from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.pipelines import visual_delivery_gate as delivery
from infini_local.pipelines import visual_asset_manifest as manifest
from infini_local.pipelines import pipeline_visual_config as config
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.services import asset_sync_service as sync
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.web.server_utility_routes import ServerUtilityRoutes
from tests.vfx_image_fixtures import HttpCapture, _data, _request, _existing_texture_data

R = Path(__file__).resolve().parents[2]

OUT = Path(os.environ.get('INFINI_IMAGE_OWNERSHIP_EVIDENCE_DIR', str(Path(tempfile.gettempdir()) / 'image-job-ownership-tests')))

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def record(name, value):
    path = OUT / 'observations' / (name + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

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
    # Use the real route methods and real stat/open/read, without starting HTTP.
    routes = object.__new__(ServerUtilityRoutes)
    routes.sprite_dir = root
    routes.world_recipes_dir = root / 'world-recipes'
    routes.asset_sync_service = sync
    handler = HttpCapture()
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
    monkeypatch.setattr(generation, 'VISUAL_ALLOW_PROCEDURAL_FALLBACK', False)
    monkeypatch.setattr(generation, 'VISUAL_STRICT_AI_AUTHORSHIP', True)
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
    record('overlap-' + kind + ('-distinct' if distinct_ids else '-same'), {'kind': kind, 'distinct_ids': distinct_ids, 'gate_capacity': 1, 'requests': requests, 'results': rows})
    assert [row['payload']['seed'] for row in requests] == [731, 731]
    assert all(result[3] == 'generated' for result in returned.values()), returned
    assert not list(root.glob('.infini_vfx_png_*.part'))
    assert generation.IMAGE_GENERATION_GATE._semaphore.acquire(blocking=False)
    generation.IMAGE_GENERATION_GATE._semaphore.release()
    assert all(row['http_code'] == row['sprite_code'] == 200 for row in rows.values())
    for name, row in rows.items():
        assert row['validated_sha256'] == row['http_sha256'] == row['returned_sha256'], f'{kind}: {name} received another invocation\'s PNG'
    assert returned['first'][0] != returned['second'][0]

def test_public_adapters_share_the_canonical_attempt_executor(offline, monkeypatch):
    executor = getattr(generation, '_execute_image_request', None)
    assert callable(executor), 'the duplicated lifecycles have no canonical executor'
    requests = []

    def capture(data, request):
        requests.append(request)
        return executor(data, request)

    monkeypatch.setattr(generation, '_execute_image_request', capture)
    for kind in ('item', 'entity', 'impact', 'equip_overlay', 'vfx_cutout', 'vfx_strip'):
        assert invoke(kind, 'shared_executor')[3] == 'generated'
    assert [request.processing_role for request in requests] == [
        'item', 'runtime:projectile', 'impact', 'equip_overlay', 'vfx_cutout', 'vfx_strip',
    ]
    import ast
    import inspect
    for adapter in (generation.maybe_generate_sprite, generation.generate_visual_asset):
        tree = ast.parse(inspect.getsource(adapter))
        assert not any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree))

def test_real_plan_body_impact_must_have_distinct_publications(offline, monkeypatch):
    root, requests = offline
    data = _existing_texture_data('impact')
    data['id'] = 'role_collision'
    orb = next(row for row in data['runtimeProgram']['entities'] if row['id'] == 'orb')
    orb['visual'].update(impactPrompt='one isolated impact fixture', impactNegativePrompt='UI, text, atlas')
    body = copy.deepcopy(orb)
    body['id'] = 'orb_impact'
    body['visual'] = {'role': 'projectile', 'assetMode': 'baked_sprite', 'prompt': 'one isolated amber body fixture', 'silhouette': 'round', 'visualIdentity': 'amber core'}
    data['runtimeProgram']['entities'].append(body)
    data['runtimeProgram']['bindings'].append({'id': 'secondary', 'input': 'alternate_use', 'role': 'secondary', 'usePolicy': {'action': {'kind': 'spawn_entity', 'targetId': 'orb_impact'}, 'stackCost': 0, 'contactDamage': False}})
    plan = build_visual_asset_plan(data)
    watched = []
    real_validator = generation.validate_processed_sprite

    def capture(path, role, **kwargs):
        report = real_validator(path, role, **kwargs)
        if role in {'impact', 'runtime:projectile'}:
            watched.append({'role': role, 'path': str(path), 'sha256': sha(Path(path).read_bytes()), 'validation_ok': report['ok']})
        return report

    monkeypatch.setattr(generation, 'validate_processed_sprite', capture)
    out = generation.maybe_generate_visual_assets(data)
    impact_visual = next(row for row in out['runtimeProgram']['entities'] if row['id'] == 'orb')['visual']
    body_visual = next(row for row in out['runtimeProgram']['entities'] if row['id'] == 'orb_impact')['visual']
    report = delivery.visual_delivery_report(out, check_backend_config=False)
    served = serve(root, impact_visual['impactSpritePath'])
    record('cross-role-body-impact', {
        'plan': plan, 'validated': watched, 'impact_path': impact_visual['impactSpritePath'],
        'body_path': body_visual['spritePath'], 'delivery_ok': report['ok'], 'delivery_problems': report['problems'],
        'http_code': served['code'], 'http_sha256': sha(served['raw']), 'http_headers': served['headers'],
        'requests': requests,
    })
    assert report['ok'], report['problems']
    assert len(watched) == 2 and all(row['validation_ok'] for row in watched), watched
    assert watched[0]['sha256'] != watched[1]['sha256']
    assert impact_visual['impactSpritePath'] != body_visual['spritePath'], 'two authored roles alias one publication name'
    assert sha(served['raw']) == watched[0]['sha256'], 'impact now serves body pixels'


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
    assert 'STRICT RETRY 1' in calls[1]['prompt']


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
    assert sync.is_complete_png_file(result[0])
    assert serve(root, result[0])['raw'] == Path(result[0]).read_bytes()


def test_legacy_non_io_projection_tail_still_recovers_warn_without_a_placeholder(offline, monkeypatch):
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
    assert sync.is_complete_png_file(result[0])
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
    assert len(evidence) == 5
    assert all(path.exists() and not path.is_relative_to(root) for path in evidence)
    for path in evidence:
        assert serve(root, path)['code'] == serve(root, path, 'sprite')['code'] == 404
    assert sync.runtime_asset_files(data) == [Path(result[0]).name]
    assert serve(root, result[0])['raw'] == Path(result[0]).read_bytes()

def test_old_cached_legacy_png_names_continue_serving_without_migration(offline):
    root, requests = offline
    old_path = root / 'old_recipe_orb_impact.png'
    old_bytes = png((10, 220, 70))
    old_path.write_bytes(old_bytes)
    result = invoke('impact', 'old_recipe_orb_impact')
    assert result[3] == 'generated' and Path(result[0]) != old_path
    assert old_path.read_bytes() == old_bytes
    assert serve(root, old_path)['code'] == 200
    assert serve(root, old_path)['raw'] == old_bytes
    assert serve(root, old_path, 'sprite')['raw'] == old_bytes

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
        expected = 'infini_asset_png_' + sha(identity + b'\0' + raw) + '.png'
        assert Path(result[0]).name == expected
        outcomes.append(result[0])
    assert len(set(outcomes)) == 3

@pytest.mark.parametrize('kind', ['vfx_cutout', 'vfx_strip'])
def test_vfx_publication_hash_stays_byte_identical_to_accepted_algorithm(offline, kind):
    root, requests = offline
    data = _data([_request('grain', layout='strip' if kind == 'vfx_strip' else 'cutout')])
    result = invoke(kind, 'ignored_vfx_id', data)
    assert result[3] == 'generated'
    raw = Path(result[0]).read_bytes()
    identity = json.dumps([data['vfxManifest']['recipeId'], 'grain'], ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    assert Path(result[0]).name == 'infini_vfx_png_' + sha(identity + b'\0' + raw) + '.png'

@pytest.mark.parametrize('save_stages', [False, True])
def test_logical_path_tokens_cannot_escape_the_private_output_owner(offline, monkeypatch, save_stages):
    root, requests = offline
    workspace = root.parent / 'private-invocation'
    workspace.mkdir()
    monkeypatch.setattr(generation, '_new_image_workspace', lambda: workspace)
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
    assert all(Path(row[key]).resolve().is_relative_to(workspace / 'attempt-0') for row in attempts for key in ('raw', 'final'))

def test_impact_publication_entity_identity_does_not_change_legacy_processing_topology(offline, monkeypatch):
    root, requests = offline
    data = _existing_texture_data('impact')
    orb = next(row for row in data['runtimeProgram']['entities'] if row['id'] == 'orb')
    orb['visual'].update(topology='multipart_separated', partCountMin=2, partCountMax=3)
    seen = []
    original_validate = generation.validate_processed_sprite

    def capture(path, role, **kwargs):
        if role == 'impact':
            seen.append(kwargs)
        return original_validate(path, role, **kwargs)

    monkeypatch.setattr(generation, 'validate_processed_sprite', capture)
    out = generation.maybe_generate_visual_assets(data)
    assert seen == [{'topology': '', 'part_count_min': 0, 'part_count_max': 0}], 'storage identity changed previously unauthored impact processing inputs'
    producer = next(row for row in out['runtimeProgram']['entities'] if row['id'] == 'orb')['visual']
    raw = Path(producer['impactSpritePath']).read_bytes()
    logical = next(row['assetId'] for row in build_visual_asset_plan(out) if row['role'] == 'impact:orb')
    identity = json.dumps([data['id'], 'impact', 'orb', logical], ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    assert Path(producer['impactSpritePath']).name == 'infini_asset_png_' + sha(identity + b'\0' + raw) + '.png'


IMAGE_ROLES = ("item", "entity", "impact", "equip_overlay", "vfx_cutout", "vfx_strip")
IO_CASES = (
    [(kind, "final_save", "processing") for kind in IMAGE_ROLES]
    + [("item", "stage:" + stage, "processing") for stage in
       ("00_raw", "10_sprite_keyer_fullres", "20_master_norm", "30_baked_final")]
    + [("item", "raw_write", "backend"), ("item", "refit_save", "processing")]
    + [(kind, "master", "processing") for kind in ("item", "entity", "vfx_cutout")]
    + [("item", "attempt_mkdir", "processing"), ("item", "metrics", "projection")]
    + [(kind, "trace", "projection") for kind in ("item", "entity")]
    + [(kind, fault, "publication") for kind in IMAGE_ROLES for fault in ("replace", "fsync", "mkstemp")]
    + [("item", "procedural_mkdir", "backend")]
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
    monkeypatch.setattr(generation, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    monkeypatch.setattr(generation, "VISUAL_STRICT_AI_AUTHORSHIP", False)
    calls = []
    if fault.startswith("stage:"):
        monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", True)
    if fault == "procedural_mkdir":
        monkeypatch.setattr(generation, "IMAGE_BACKEND", "procedural")
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
        else (Path, "mkdir") if fault in {"attempt_mkdir", "procedural_mkdir"}
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
            else name.startswith("attempt-") and (fault != "procedural_mkdir" or kwargs.get("parents")) if attribute == "mkdir"
            else args[2] == "sprite accepted" if fault == "trace"
            else kwargs.get("suffix") == ".part" if fault == "mkstemp"
            else True
        )
        if selected:
            calls.append((args, kwargs))
            if fault == "replace":
                assert Path(args[0]).suffix == ".part"
                assert sync.is_complete_png_file(args[0])
            raise PermissionError("offline owned " + fault + " denied")
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, attribute, denied)
    result = invoke(kind, "io_contract", data)
    assert calls, "fault never reached its production boundary"
    assert result[3] == "failed" and result[0] == result[1] == ""
    assert len(requests) == (0 if fault in {"attempt_mkdir", "procedural_mkdir"} else 1), "local I/O consumed quality retries or fallback"
    prefix = "item" if kind == "item" else "runtime:projectile" if kind == "entity" else "vfx:grain" if kind.startswith("vfx_") else kind
    assert data["debug"][prefix + "SpriteFailurePhase"] == phase
    if fault in {"attempt_mkdir", "procedural_mkdir"}:
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
