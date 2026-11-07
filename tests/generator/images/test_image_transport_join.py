"""Authoritative IMAGE joins through real owners; only HTTP responses are synthetic."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from infini_local.pipelines.images import backends as backend
from infini_local.core.images import config
from infini_local.pipelines.images import postprocess as post
from infini_local.pipelines.images import stage as visual
from infini_local.services import codex_auth as auth
from infini_local.storage import trace_runtime as trace


class MemoryResponse(io.BytesIO):
    status = 200


@pytest.fixture
def recording(monkeypatch, tmp_path):
    # Drain the asynchronous writer before changing its test-owned destinations.
    assert trace.flush_codex_transport(timeout=5)
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "PROMPT_TRACE_FILE", tmp_path / "prompt_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(visual, "SPRITE_DIR", tmp_path / "sprites")
    monkeypatch.setattr(visual, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(visual, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 1)
    monkeypatch.setattr(config, "CODEX_IMAGE_MODEL", "fixture-model")
    monkeypatch.setattr(config, "CODEX_IMAGE_QUALITY", "low")
    monkeypatch.setattr(config, "CODEX_IMAGE_SIZE", "auto")
    monkeypatch.setattr(config, "CODEX_IMAGE_TIMEOUT", 3)
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    monkeypatch.setenv("INFINI_SPRITE_RETRIES", "1")
    credentials = auth.Credentials("fixture-access", "fixture-refresh", "fixture-account", 9999999999)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    buffer = io.BytesIO()
    image = Image.new("RGBA", (64, 64))
    image.paste((170, 90, 40, 255), (18, 8, 46, 56))
    image.save(buffer, format="PNG")
    png = buffer.getvalue()
    body = json.dumps({"data": [{"b64_json": base64.b64encode(png).decode()}]}).encode()
    sent = []

    def opened(req, *, deadline, on_open=None):
        if on_open is not None:
            on_open()
        sent.append((req.data, dict(req.header_items()), deadline))
        return MemoryResponse(body)

    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    yield {"root": tmp_path, "png": png, "body": body, "sent": sent}
    assert trace.flush_codex_transport(timeout=5)


def rows(recording):
    assert trace.flush_codex_transport(timeout=5), "transport writer did not drain"
    path = recording["root"] / "pipeline_trace.ndjson"
    return [row["payload"] for row in map(json.loads, path.read_text().splitlines())
            if row["kind"] == "codex_transport"]


def request(asset_id="literal-asset", role="vfx:literal-effect"):
    return visual._ImageRequest(
        logical_asset_id=asset_id, audit_role=role, processing_role="vfx_cutout",
        prompt="same authored fixture prompt", negative="avoid text", canvas=32,
        topology="", part_count_min=0, part_count_max=0,
        policy=visual._PublicationPolicy.REQUIRED_VFX, publication_identity=b"fixture",
    )


def execute(image_request):
    return visual._execute_image_request({"id": "fixture-recipe", "vfxManifest": {"recipeId": "fixture-recipe"}}, image_request)


def test_image_lifecycle_binds_logical_asset_actual_backend_attempt_and_audit_role(recording):
    image_request = request()
    result = execute(image_request)
    assert result.status == "generated", result
    assert Path(result.raw_path).read_bytes() == recording["png"]
    observations = rows(recording)
    assert observations
    expected_attempt = Path(result.raw_path).name.removesuffix("_raw_openai_codex_0.png")
    assert expected_attempt.startswith("infini_vfx_job_") and expected_attempt != image_request.logical_asset_id
    for row in observations:
        assert row.get("assetId") == image_request.logical_asset_id
        assert row.get("attemptId") == expected_attempt
        assert row.get("role") == image_request.audit_role
        assert row.get("attempt") == 0
    assert len({row["transportCallId"] for row in observations}) == 1
    events = list(map(json.loads, (recording["root"] / "events.ndjson").read_text().splitlines()))
    success = next(row["payload"] for row in events if row["message"] == "Codex OAuth generated sprite")
    assert success["transportCallId"] == observations[0]["transportCallId"]
    assert success["assetId"] == image_request.logical_asset_id
    assert success["attemptId"] == expected_attempt and success["spriteId"] == expected_attempt
    assert success["role"] == image_request.audit_role and success["variant"] == 0
    assert len(recording["sent"]) == 1
    assert json.loads(recording["sent"][0][0]) == {
        "model": "fixture-model", "prompt": "same authored fixture prompt\n\nAvoid: avoid text",
        "n": 1, "quality": "low", "size": "auto", "background": "transparent",
    }


@pytest.mark.parametrize("variants", [1, 3])
def test_each_variant_success_log_joins_observed_transport_without_replacing_outer_context(recording, monkeypatch, variants):
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", variants)
    observed, successes = [], []
    monkeypatch.setattr(backend, "log_event", lambda level, message, payload: successes.append(payload))
    join = {"assetId": "logical-asset", "attemptId": "stale-inherited-attempt",
            "attempt": 2, "role": "vfx:literal-effect", "logicalCallId": "fixture-logical",
            "leaseId": "fixture-lease"}
    output_dir = recording["root"] / "raw"
    with auth.generation_observations(join, observed.append):
        before = auth._GENERATION_OBSERVATIONS.get()
        paths = backend.generate_openai_codex("same authored fixture prompt", "avoid text", "actual-backend-attempt", output_dir=output_dir)
        assert auth._GENERATION_OBSERVATIONS.get() == before
    observations = rows(recording)
    assert len(paths) == len(successes) == variants
    assert all(Path(path).read_bytes() == recording["png"] for path in paths)
    assert len({row["transportCallId"] for row in observations}) == variants
    assert len(observed) == len(observations)
    for variant, success in enumerate(successes):
        group = [row for row in observations if row.get("variant") == variant]
        assert group, "HTTP transport must carry the variant before persistence"
        call_id = next(row["transportCallId"] for row in group if row["event"] == "request")
        assert {row["transportCallId"] for row in group} == {call_id}
        for row in [*group, success]:
            assert row["assetId"] == "logical-asset"
            assert row["attemptId"] == "actual-backend-attempt"
            assert row["role"] == "vfx:literal-effect"
            assert row["attempt"] == 2
            assert row["variant"] == variant
            assert row["logicalCallId"] == "fixture-logical"
            assert row["leaseId"] == "fixture-lease"
            assert row["transportCallId"] == call_id
        assert success["spriteId"] == "actual-backend-attempt" and success["path"] == paths[variant]
    assert all("artifact" not in row for row in observed), "callback receives metadata, not the raw body"
    assert "variant" not in join and join["attemptId"] == "stale-inherited-attempt"


@pytest.mark.parametrize("same_asset", [False, True])
@pytest.mark.parametrize("required_vfx", [False, True])
def test_concurrent_identical_prompts_keep_invocation_and_variant_joins_separate(recording, monkeypatch, same_asset, required_vfx):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Barrier, Lock
    from infini_local.services.sdcpp_service import ImageRequestGate

    # Exercise the real configured multi-lane admission owner, not the default
    # single-image gate (which intentionally serializes the opener barrier).
    monkeypatch.setattr(visual, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    barrier, lock = Barrier(2), Lock()
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 2)
    successes = []

    def opened(req, *, deadline, on_open=None):
        if on_open is not None:
            on_open()
        with lock:
            recording["sent"].append((req.data, dict(req.header_items()), deadline))
        barrier.wait(timeout=5)
        return MemoryResponse(recording["body"])

    def logged(level, message, payload):
        with lock:
            successes.append(payload)

    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    monkeypatch.setattr(backend, "log_event", logged)

    def call(index):
        asset_id = "shared-asset" if same_asset else f"literal-asset-{index}"
        image_request = request(asset_id=asset_id)
        if not required_vfx:
            image_request = replace(image_request, policy=visual._PublicationPolicy.RUNTIME_ASSET)
        return execute(image_request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(call, [1, 2]))
    assert all(result.status == "generated" for result in results), results
    assert all(Path(result.raw_path).read_bytes() == recording["png"] for result in results)
    assert len(recording["sent"]) == 4
    assert len({wire for wire, _, _ in recording["sent"]}) == 1
    observations = rows(recording)
    assert len({row["transportCallId"] for row in observations}) == 4
    actual_attempts = {Path(result.raw_path).name.removesuffix("_raw_openai_codex_0.png") for result in results}
    assert len(actual_attempts) == (1 if same_asset and not required_vfx else 2)
    assert len({result.raw_path for result in results}) == 2
    assert {row["attemptId"] for row in observations} == actual_attempts
    assert len(successes) == 4
    for success in successes:
        group = [row for row in observations if row["transportCallId"] == success["transportCallId"]]
        assert group
        assert all({key: row[key] for key in ("assetId", "attemptId", "attempt", "role", "variant")} ==
                   {key: success[key] for key in ("assetId", "attemptId", "attempt", "role", "variant")} for row in group)
    for attempt_id in actual_attempts:
        assert {row["variant"] for row in observations if row["attemptId"] == attempt_id} == {0, 1}


@pytest.mark.parametrize("outcome", ["recover", "exhaust", "terminal"])
def test_physical_retries_share_variant_join_without_multiplying_lifecycle_budget(recording, monkeypatch, outcome):
    from email.message import Message
    from urllib.error import HTTPError

    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 2)
    monkeypatch.setattr(visual, "SPRITE_RETRIES", 3)
    observed, successes = [], []
    monkeypatch.setattr(backend, "log_event", lambda level, message, payload: successes.append(payload))

    def opened(req, *, deadline, on_open=None):
        if on_open is not None:
            on_open()
        recording["sent"].append((req.data, dict(req.header_items()), deadline))
        if outcome != "recover" or len(recording["sent"]) == 1:
            status = 429 if outcome == "terminal" else 503
            raise HTTPError(req.full_url, status, "fixture rejected", Message(), MemoryResponse(b'{"error":{"message":"fixture rejected"}}'))
        return MemoryResponse(recording["body"])

    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    outer_join = {"logicalCallId": "fixture-logical", "leaseId": "fixture-lease", "assetId": "stale-outer-asset"}
    with auth.generation_observations(outer_join, observed.append):
        before = auth._GENERATION_OBSERVATIONS.get()
        result = execute(request())
        assert auth._GENERATION_OBSERVATIONS.get() == before
    observations = rows(recording)
    expected_posts = {"recover": 3, "exhaust": 2, "terminal": 1}[outcome]
    assert len(recording["sent"]) == expected_posts
    starts = [row for row in observations if row["event"] == "post_start"]
    assert len(starts) == expected_posts and all(row["networkStarted"] for row in starts)
    assert len(observed) == len(observations)
    assert all(row["assetId"] == "literal-asset" and row["role"] == "vfx:literal-effect" and
               row["attempt"] == 0 and row["logicalCallId"] == "fixture-logical" and
               row["leaseId"] == "fixture-lease" for row in observations)
    assert len({row["attemptId"] for row in observations}) == 1
    first_variant = [row for row in observations if row["variant"] == 0]
    assert len({row["transportCallId"] for row in first_variant}) == 1
    first_starts = [row for row in first_variant if row["event"] == "post_start"]
    expected_first = 1 if outcome == "terminal" else 2
    assert [row["physicalAttemptIndex"] for row in first_starts] == list(range(1, expected_first + 1))
    terminal = next(row for row in first_variant if row["event"] == "call_end")
    assert terminal["physicalAttemptCount"] == expected_first
    assert terminal["outcome"] == ("success" if outcome == "recover" else "failure")
    if outcome == "recover":
        assert result.status == "generated" and len(successes) == 2
        assert recording["sent"][0] == recording["sent"][1], "retry must retain bytes, headers and deadline"
        assert Path(result.raw_path).read_bytes() == recording["png"]
    else:
        assert result.status == "failed" and result.failure_phase == "backend"
        assert len(result.attempts) == 1 and successes == []
        assert {row["variant"] for row in observations} == {0}
        assert not list((recording["root"] / "sprites").glob("*.png"))


def test_semantic_retry_binds_actual_attempt_before_filename_truncation(recording, monkeypatch):
    monkeypatch.setattr(visual, "SPRITE_RETRIES", 1)
    buffer = io.BytesIO()
    Image.new("RGBA", (64, 64)).save(buffer, format="PNG")
    invalid_body = json.dumps({"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}).encode()
    successes = []
    monkeypatch.setattr(backend, "log_event", lambda level, message, payload: successes.append(payload))

    def opened(req, *, deadline, on_open=None):
        if on_open is not None:
            on_open()
        recording["sent"].append((req.data, dict(req.header_items()), deadline))
        return MemoryResponse(invalid_body if len(recording["sent"]) == 1 else recording["body"])

    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    asset_id = "literal-asset-" + "x" * 140
    image_request = visual._ImageRequest(
        logical_asset_id=asset_id, audit_role="runtime:child_projectile", processing_role="runtime:child_projectile",
        prompt="same authored fixture prompt", negative="avoid text", canvas=32,
        topology="", part_count_min=0, part_count_max=0,
        policy=visual._PublicationPolicy.RUNTIME_ASSET, publication_identity=b"fixture",
    )
    result = execute(image_request)
    assert result.status == "generated", result
    observations = rows(recording)
    assert len(recording["sent"]) == len(successes) == 2
    assert {row["attempt"] for row in observations} == {0, 1}
    for attempt, success in enumerate(successes):
        expected_attempt = asset_id if attempt == 0 else asset_id + "_retry1"
        group = [row for row in observations if row["attempt"] == attempt]
        assert {row["attemptId"] for row in [*group, success]} == {expected_attempt}
        assert {row["assetId"] for row in [*group, success]} == {asset_id}
        assert {row["role"] for row in [*group, success]} == {image_request.audit_role}
        assert len({row["transportCallId"] for row in group}) == 1
        assert success["transportCallId"] == group[0]["transportCallId"]
        assert expected_attempt not in Path(success["path"]).name, "join must not reconstruct the truncated filename"
    assert Path(result.raw_path).read_bytes() == recording["png"]


@pytest.mark.parametrize("mode", ["off", "observer_failure"])
def test_optional_observation_does_not_change_image_or_leak_context(recording, monkeypatch, mode):
    successes = []
    monkeypatch.setattr(backend, "log_event", lambda level, message, payload: successes.append(payload))
    if mode == "off":
        monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", False)
    def failed_observer(observation):
        raise RuntimeError("fixture metadata observer failed")
    inherited = {"recipeKey": "fixture-recipe"}
    with auth.generation_observations(inherited, failed_observer if mode == "observer_failure" else None):
        before = auth._GENERATION_OBSERVATIONS.get()
        result = execute(request())
        assert auth._GENERATION_OBSERVATIONS.get() == before
    assert result.status == "generated" and Path(result.raw_path).read_bytes() == recording["png"]
    assert len(recording["sent"]) == len(successes) == 1
    assert successes[0]["transportCallId"]
    assert successes[0]["recipeKey"] == "fixture-recipe"
    assert "assetId" not in inherited
    if mode == "off":
        assert trace.flush_codex_transport(timeout=5)
        assert not (recording["root"] / "pipeline_trace.ndjson").exists()
