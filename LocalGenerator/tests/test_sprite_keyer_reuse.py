"""Selected keyer reuse preserves pixels, scoring and final technical validation."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw
import pytest

from infini_local.core.images import config
from infini_local.pipelines.images import keyer, postprocess as post


@pytest.fixture(autouse=True)
def keyed_processing(monkeypatch):
    monkeypatch.setattr(config, 'BG_COLOR', 'magenta')
    monkeypatch.setattr(config, 'BG_REMOVE_MODE', 'sprite_keyer')
    monkeypatch.setattr(config, 'REMOVE_BG', True)
    monkeypatch.setattr(post, 'SAVE_SPRITE_STAGES', False)
    monkeypatch.setattr(post, 'log_event', lambda *_a, **_k: None)
    monkeypatch.setattr(keyer, 'log_event', lambda *_a, **_k: None)


def source(path, *, color=(240, 180, 30, 255), bounds=(8, 8, 56, 56)):
    image = Image.new('RGBA', (64, 64), (255, 0, 255, 255))
    ImageDraw.Draw(image).rectangle(bounds, fill=color)
    image.save(path)
    return str(path)


@pytest.mark.parametrize('role', ['item', 'runtime:child_projectile', 'impact', 'vfx_strip'])
@pytest.mark.parametrize('native_alpha', [False, True])
def test_selected_keyer_runs_once_and_matches_original_bake_and_metrics(tmp_path, monkeypatch, role, native_alpha):
    path = source(tmp_path / 'raw.png')
    if native_alpha:
        monkeypatch.setattr(config, 'BG_COLOR', 'transparent')
        image = Image.open(path).convert('RGBA')
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                if pixels[x, y][:3] == (255, 0, 255):
                    pixels[x, y] = (0, 0, 0, 0)
        image.save(path)
    calls = []
    original = post.apply_background_removal
    monkeypatch.setattr(post, 'apply_background_removal', lambda *a, **k: calls.append(1) or original(*a, **k))
    selected = post.pick_best_sprite([path], role, 32)
    before = selected.prepared.pixels.tobytes()
    reused = post.postprocess_sprite(path, 'reused', 32, role, output_dir=tmp_path, prepared=selected.prepared)
    assert len(calls) == 1
    baseline = post.postprocess_sprite(path, 'baseline', 32, role, output_dir=tmp_path)
    assert len(calls) == 2
    assert Path(reused).read_bytes() == Path(baseline).read_bytes()
    assert post.validate_processed_sprite(reused, role) == post.validate_processed_sprite(baseline, role)
    assert selected.prepared.pixels.tobytes() == before
    assert selected.score == post.pick_best_sprite([path], role, 32).score


@pytest.mark.parametrize('change', ['raw_bytes', 'role', 'config', 'decoded_pixels'])
def test_identity_mismatch_recomputes_instead_of_rejecting(tmp_path, monkeypatch, change):
    path = source(tmp_path / 'raw.png')
    selected = post.pick_best_sprite([path], 'item', 32)
    role = 'item'
    if change == 'raw_bytes':
        source(Path(path), color=(60, 180, 240, 255))
    elif change == 'role':
        role = 'runtime:child_projectile'
    elif change == 'config':
        monkeypatch.setattr(keyer, 'SPRITE_KEYER_SPILL_RADIUS', keyer.SPRITE_KEYER_SPILL_RADIUS + 1)
    else:
        from dataclasses import replace
        selected = post.SpriteSelection(path, selected.score, replace(selected.prepared, source_pixels_sha256='0' * 64))
    calls = []
    original = post.apply_background_removal
    monkeypatch.setattr(post, 'apply_background_removal', lambda *a, **k: calls.append(1) or original(*a, **k))
    actual = post.postprocess_sprite(path, 'actual', 32, role, output_dir=tmp_path, prepared=selected.prepared)
    assert len(calls) == 1
    expected = post.postprocess_sprite(path, 'expected', 32, role, output_dir=tmp_path)
    assert Path(actual).read_bytes() == Path(expected).read_bytes()


def test_retained_preparation_belongs_to_winner_not_last_candidate(tmp_path, monkeypatch):
    winner = source(tmp_path / 'winner.png')
    other = source(tmp_path / 'other.png', bounds=(31, 31, 33, 33))
    selected = post.pick_best_sprite([winner, other], 'item', 32)
    assert selected.path == winner
    assert selected.prepared.source_sha256 == hashlib.sha256(Path(winner).read_bytes()).hexdigest()
    baseline = post.postprocess_sprite(winner, 'baseline', 32, 'item', output_dir=tmp_path)
    monkeypatch.setattr(post, 'apply_background_removal', lambda *_a, **_k: pytest.fail('winner should reuse its own preparation'))
    reused = post.postprocess_sprite(winner, 'reused', 32, 'item', output_dir=tmp_path, prepared=selected.prepared)
    assert Path(reused).read_bytes() == Path(baseline).read_bytes()


def test_concurrent_selections_do_not_share_prepared_buffers(tmp_path):
    paths = [source(tmp_path / f'raw{i}.png', color=(40 + i * 50, 190, 40, 255)) for i in range(4)]
    def process(path):
        selected = post.pick_best_sprite([path], 'item', 32)
        retained = selected.prepared.pixels.tobytes()
        output = post.postprocess_sprite(path, Path(path).stem + '_final', 32, 'item', output_dir=tmp_path, prepared=selected.prepared)
        assert selected.prepared.pixels.tobytes() == retained
        return selected, Path(output).read_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(process, paths))
    assert len({id(selected.prepared.pixels) for selected, _ in results}) == 4
    assert len({pixels for _, pixels in results}) == 4
    for (selected, actual), path in zip(results, paths):
        baseline = post.postprocess_sprite(path, Path(path).stem + '_baseline', 32, 'item', output_dir=tmp_path)
        assert actual == Path(baseline).read_bytes()
