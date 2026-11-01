"""Accepted PNGs survive failed siblings without bypassing their real validators."""
from collections import Counter
from contextlib import contextmanager
import copy
import errno
import json
from pathlib import Path
import threading

import pytest
from PIL import Image

from infini_local.pipelines.images import stage as generation
from infini_local.pipelines.images import backends as image_backends
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.storage.craft_progress import progress_path, track_progress
from tests.vfx_image_fixtures import _data, _existing_texture_data, _request, offline_backend  # noqa: F401


@pytest.fixture
def image_receipts(tmp_path):
    return tmp_path / "progress-world"


@contextmanager
def _accepted_visual(root):
    with track_progress(root, "image-test", {"test": "accepted-images"}) as progress:
        if not progress.restore()[0]:
            progress.accept("visual", {"id": "accepted-image-design"})
        yield progress


def _generate(data, root):
    # A new progress owner every time proves disk restoration, not only reuse of
    # a live in-memory object. The image implementation sees the real ContextVar.
    with _accepted_visual(root):
        return generation.maybe_generate_visual_assets(data)


def _receipt_count(root):
    return len(json.loads(progress_path(root, "image-test").read_text())["images"])


@pytest.mark.parametrize("capacity", [1, 2])
def test_retry_only_generates_the_failed_sibling(offline_backend, image_receipts, monkeypatch, capacity):
    original = _existing_texture_data("entity")
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(capacity))
    backend = generation.generate_sdcpp
    calls = Counter()

    def transport(prompt, negative, asset_id, *args, **kwargs):
        calls[asset_id] += 1
        if asset_id.endswith("_orb") and calls[asset_id] == 1:
            raise RuntimeError("offline sibling failure")
        return backend(prompt, negative, asset_id, *args, **kwargs)

    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    first = _generate(copy.deepcopy(original), image_receipts)
    item_path = first["visual"]["spritePath"]
    assert first["visual"]["spriteStatus"] == "generated"
    assert next(row for row in first["runtimeProgram"]["entities"] if row["id"] == "orb")["visual"]["spriteStatus"] == "failed"
    assert _receipt_count(image_receipts) == 1

    second = _generate(copy.deepcopy(original), image_receipts)
    assert second["visual"]["spritePath"] == item_path
    assert second["debug"]["itemSpriteCheckpoint"]["reused"] is True
    assert next(row for row in second["runtimeProgram"]["entities"] if row["id"] == "orb")["visual"]["spriteStatus"] == "generated"
    assert sorted(calls.values()) == [1, 2]
    assert _receipt_count(image_receipts) == 2


def test_visual_jobs_survive_vfx_failure_before_batch_join(offline_backend, image_receipts, monkeypatch):
    original = _existing_texture_data("entity")
    frozen = copy.deepcopy(original)
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    backend = generation.generate_sdcpp
    started = threading.Barrier(3)

    def transport(*args, **kwargs):
        started.wait(timeout=5)
        return backend(*args, **kwargs)

    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    with pytest.raises(RuntimeError, match="VFX failed"):
        with _accepted_visual(image_receipts):
            with generation.overlap_visual_images(original):
                started.wait(timeout=5)
                raise RuntimeError("VFX failed")
    assert original == frozen
    assert _receipt_count(image_receipts) == 2
    assert len(offline_backend[0]) == 2
    monkeypatch.setattr(generation, "generate_sdcpp", backend)
    resumed = _generate(copy.deepcopy(original), image_receipts)
    assert len(offline_backend[0]) == 2
    assert resumed["visual"]["spriteStatus"] == "generated"
    assert resumed["debug"]["itemSpriteCheckpoint"]["reused"] is True


@pytest.mark.parametrize("damage", ["missing", "broken", "changed-pixels"])
def test_missing_or_modified_png_is_regenerated(offline_backend, image_receipts, damage):
    original = _data([])
    first = _generate(copy.deepcopy(original), image_receipts)
    path = Path(first["visual"]["spritePath"])
    if damage == "missing":
        path.unlink()
    elif damage == "broken":
        path.write_bytes(b"incomplete PNG")
    else:
        with Image.open(path) as source:
            changed = source.convert("RGBA")
        point = next((x, y) for y in range(changed.height) for x in range(changed.width)
                     if changed.getpixel((x, y))[3] == 255)
        changed.putpixel(point, (31, 113, 221, 255))
        changed.save(path)
    resumed = _generate(copy.deepcopy(original), image_receipts)
    assert len(offline_backend[0]) == 2
    assert resumed["visual"]["spriteStatus"] == "generated"
    assert "itemSpriteCheckpoint" not in resumed["debug"]


@pytest.mark.parametrize("operation", ["lookup", "open", "read"])
@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EIO], ids=["permission", "io-error"])
def test_unreadable_png_preserves_progress_without_calling_the_provider(
    offline_backend, image_receipts, monkeypatch, operation, error_number,
):
    original = _data([])
    first = _generate(copy.deepcopy(original), image_receipts)
    target = Path(first["visual"]["spritePath"])
    checkpoint = progress_path(image_receipts, "image-test")
    before = checkpoint.read_bytes()
    fault = OSError(error_number, "accepted PNG temporarily unreadable", str(target))
    real_stat, real_open = Path.stat, Path.open

    def faulty_stat(path, *args, **kwargs):
        if path == target:
            raise fault
        return real_stat(path, *args, **kwargs)

    class FailedRead:
        def read(self, *_args, **_kwargs):
            raise fault

    @contextmanager
    def failed_read(path, *args, **kwargs):
        with real_open(path, *args, **kwargs):
            yield FailedRead()

    def faulty_open(path, *args, **kwargs):
        if path == target:
            if operation == "open":
                raise fault
            return failed_read(path, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat" if operation == "lookup" else "open",
                        faulty_stat if operation == "lookup" else faulty_open)
    with pytest.raises(OSError) as raised:
        _generate(copy.deepcopy(original), image_receipts)
    assert raised.value is fault
    assert len(offline_backend[0]) == 1
    assert checkpoint.read_bytes() == before


def test_changed_entity_request_does_not_borrow_previous_image(offline_backend, image_receipts):
    original = _existing_texture_data("entity")
    _generate(copy.deepcopy(original), image_receipts)
    changed = copy.deepcopy(original)
    next(row for row in changed["runtimeProgram"]["entities"] if row["id"] == "orb")["visual"]["prompt"] = "one isolated blue crystal orb"
    resumed = _generate(changed, image_receipts)
    assert len(offline_backend[0]) == 3
    assert resumed["debug"]["itemSpriteCheckpoint"]["reused"] is True
    assert "runtime:projectileSpriteCheckpoint" not in resumed["debug"]


def test_vfx_ingredient_receipt_restores_the_exact_published_bytes(offline_backend, image_receipts):
    original = _data([_request(layout="strip")])
    first = _generate(copy.deepcopy(original), image_receipts)
    resumed = _generate(copy.deepcopy(original), image_receipts)
    assert len(offline_backend[0]) == 2
    assert first["vfxManifest"]["assets"] == resumed["vfxManifest"]["assets"]
    assert resumed["debug"]["vfx:grainSpriteCheckpoint"]["reused"] is True


def test_changed_pixel_settings_reject_previous_receipt(offline_backend, image_receipts, monkeypatch):
    original = _data([])
    _generate(copy.deepcopy(original), image_receipts)
    monkeypatch.setattr(generation.image_config, "SDCPP_SEED", 71)
    _generate(copy.deepcopy(original), image_receipts)
    assert len(offline_backend[0]) == 2


@pytest.mark.parametrize("environment,expected,batches", [
    ({}, {"width": 320, "height": 384, "batch_size": 2, "steps": 16, "cfg_scale": 5.5,
          "sampler_name": "Euler a"}, [2, 2, 1]),
    ({"WIDTH": "768", "HEIGHT": "1024", "BATCH_SIZE": "3", "STEPS": "23", "CFG": "2.75", "SAMPLER": "DPM++ 2M"},
     {"width": 768, "height": 1024, "batch_size": 3, "steps": 23, "cfg_scale": 2.75,
      "sampler_name": "DPM++ 2M"}, [3, 2]),
    ({"WIDTH": "99999", "HEIGHT": "1", "BATCH_SIZE": "999"},
     {"width": 2048, "height": 64, "batch_size": 16, "steps": 16, "cfg_scale": 5.5,
      "sampler_name": "Euler a"}, [5]),
], ids=["loaded-defaults", "environment-overrides", "bounds-and-remaining-variants"])
def test_a1111_receipt_identity_matches_the_real_payload_producer(monkeypatch, tmp_path, environment, expected, batches):
    for name in ("WIDTH", "HEIGHT", "BATCH_SIZE", "STEPS", "CFG", "SAMPLER"):
        monkeypatch.delenv("INFINI_A1111_" + name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv("INFINI_A1111_" + name, value)
    for name, value in {"A1111_WIDTH": 320, "A1111_HEIGHT": 384, "A1111_BATCH_SIZE": 2, "GENERATE_VARIANTS": 5}.items():
        monkeypatch.setattr(image_backends, name, value)
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "a1111")
    monkeypatch.setattr(generation.image_config, "GENERATE_VARIANTS", 5)
    payloads = []

    def capture(_url, payload, **_kwargs):
        payloads.append(copy.deepcopy(payload))
        return {"images": []}

    monkeypatch.setattr(image_backends, "http_json", capture)
    request = generation._ImageRequest(
        logical_asset_id="settings", audit_role="item", processing_role="item", prompt="literal item",
        negative="", canvas=32, topology="", part_count_min=0, part_count_max=0,
        policy=generation._PublicationPolicy.ITEM, publication_identity=b"settings",
    )
    identity = generation._image_request_identity({}, request)
    image_backends.generate_a1111(request.prompt, request.negative, request.logical_asset_id, output_dir=tmp_path)
    assert identity["settings"]["a1111Generation"] == expected
    assert [payload["batch_size"] for payload in payloads] == batches
    for payload in payloads:
        assert {name: payload[name] for name in expected if name != "batch_size"} == {
            name: value for name, value in expected.items() if name != "batch_size"
        }


def test_storage_failure_propagates_without_a_provider_retry(offline_backend, image_receipts, monkeypatch):
    def failed_write(*_args):
        raise OSError("progress disk unavailable")

    monkeypatch.setattr(generation, "save_image_result", failed_write)
    with pytest.raises(OSError, match="progress disk unavailable"):
        _generate(_data([]), image_receipts)
    assert len(offline_backend[0]) == 1


@pytest.mark.parametrize("disabled", ["no-scope", "off"])
def test_disabled_checkpoint_or_producer_cannot_restore_images(offline_backend, image_receipts, monkeypatch, disabled):
    original = _data([])
    _generate(copy.deepcopy(original), image_receipts)
    if disabled == "off":
        monkeypatch.setattr(generation, "IMAGE_BACKEND", "off")
        resumed = _generate(copy.deepcopy(original), image_receipts)
    else:
        resumed = generation.maybe_generate_visual_assets(copy.deepcopy(original))
    assert "itemSpriteCheckpoint" not in resumed["debug"]
    if disabled == "off":
        assert resumed["visual"]["spriteStatus"] == "prompt_only"
        assert not resumed["visual"]["spritePath"]
        assert len(offline_backend[0]) == 1
    else:
        assert len(offline_backend[0]) == 2
