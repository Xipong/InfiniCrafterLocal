"""Offline ComfyUI workflow execution contracts; no model or live server calls."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from infini_local.pipelines.images import backends


class Clock:
    def __init__(self):
        self.elapsed = 0.0

    def monotonic(self):
        return 100.0 + self.elapsed

    def time(self):
        return 1000.0 + self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


def install_clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(backends, "time", SimpleNamespace(
        monotonic=clock.monotonic, time=clock.time, sleep=clock.sleep,
    ))
    return clock


@pytest.mark.parametrize("partial_output", [False, True])
def test_comfyui_failed_history_is_terminal_even_with_partial_outputs(monkeypatch, partial_output):
    clock = install_clock(monkeypatch)
    calls = []
    failed = {"pid": {
        "status": {"status_str": "error", "completed": False, "messages": [
            ["execution_error", {"node_id": "7", "exception_message": "fixture model failure"}],
        ]},
        "outputs": {"preview": {"images": [{"filename": "partial.png"}]}} if partial_output else {},
    }}

    def history(url, **kwargs):
        calls.append(url)
        return failed

    monkeypatch.setattr(backends, "http_get_json", history)
    with pytest.raises(RuntimeError, match="fixture model failure"):
        backends.poll_comfyui_history("pid", timeout=5)
    assert len(calls) == 1
    assert clock.elapsed == 0


def test_comfyui_completed_without_images_does_not_wait_for_timeout(monkeypatch):
    clock = install_clock(monkeypatch)
    monkeypatch.setattr(backends, "http_get_json", lambda *args, **kwargs: {"pid": {
        "status": {"status_str": "success", "completed": True, "messages": []},
        "outputs": {},
    }})
    with pytest.raises(RuntimeError, match="without image outputs"):
        backends.poll_comfyui_history("pid", timeout=5)
    assert clock.elapsed == 0


@pytest.mark.parametrize("blocking_poll", [False, True])
def test_comfyui_history_timeout_bounds_poll_and_sleep(monkeypatch, blocking_poll):
    clock = install_clock(monkeypatch)
    budgets = []
    monkeypatch.setattr(backends, "COMFYUI_POLL_INTERVAL", 5)

    def history(url, *, timeout):
        budgets.append(timeout)
        if blocking_poll:
            clock.sleep(timeout)
            raise TimeoutError("ordinary poll timeout")
        return {}

    monkeypatch.setattr(backends, "http_get_json", history)
    with pytest.raises(TimeoutError):
        backends.poll_comfyui_history("pid", timeout=1)
    assert budgets and all(0 < value <= 1 for value in budgets)
    assert clock.elapsed <= 1.001


@pytest.mark.parametrize("history", [
    {"pid": {"status": {"status_str": "success", "completed": True},
             "outputs": {"save": {"images": [{"filename": "complete.png"}]}}}},
    {"pid": {"outputs": {"save": {"images": [{"filename": "legacy.png"}]}}}},
])
def test_comfyui_completed_and_legacy_image_history_still_work(monkeypatch, history):
    monkeypatch.setattr(backends, "http_get_json", lambda *args, **kwargs: history)
    assert backends.poll_comfyui_history("pid", timeout=1) == history


def test_comfyui_workflow_interpolation_preserves_literal_prompt_tokens():
    mapping = {
        "{{PROMPT}}": "A brass label showing {{SEED}} and {{WIDTH}}",
        "{{NEGATIVE_PROMPT}}": "avoid the literal label {{WIDTH}}",
        "{{WIDTH}}": 512,
        "{{SEED}}": 123,
    }
    template = {"inputs": {
        "text": "Prefix: {{PROMPT}}. Negative: {{NEGATIVE_PROMPT}}",
        "seed": " {{SEED}} ",
        "unknown": "unchanged {{CUSTOM}}",
    }}
    result = backends.json_deep_replace(template, mapping)
    assert result["inputs"]["text"] == (
        "Prefix: A brass label showing {{SEED}} and {{WIDTH}}. "
        "Negative: avoid the literal label {{WIDTH}}"
    )
    assert result["inputs"]["seed"] == 123
    assert result["inputs"]["unknown"] == "unchanged {{CUSTOM}}"
    assert template["inputs"]["seed"] == " {{SEED}} "


def test_comfyui_variants_queue_independent_workflows_and_keep_every_image(tmp_path, monkeypatch):
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps({"sampler": {"inputs": {"seed": "{{SEED}}", "text": "{{PROMPT}}"}}}))
    monkeypatch.setattr(backends, "resolve_comfyui_workflow_path", lambda: workflow)
    monkeypatch.setattr(backends, "GENERATE_VARIANTS", 3)
    monkeypatch.setattr(backends, "COMFYUI_TRIGGER", "")
    seeds = iter([11, 22, 33])
    monkeypatch.setattr(backends.random, "randint", lambda *args: next(seeds))
    queued = []

    def queue(url, payload, **kwargs):
        queued.append(payload)
        return {"prompt_id": f"pid-{len(queued)}"}

    monkeypatch.setattr(backends, "http_json", queue)
    monkeypatch.setattr(backends, "poll_comfyui_history", lambda pid, *args: {pid: {"outputs": {
        "save": {"images": [{"filename": f"{pid}-0.png"}, {"filename": f"{pid}-1.png"}]},
    }}})

    def fetch(meta, path):
        path.write_bytes(meta["filename"].encode())
        return str(path)

    monkeypatch.setattr(backends, "fetch_comfyui_image", fetch)
    paths = backends.generate_comfyui("exact literal prompt", "", "variant-test", output_dir=tmp_path)
    assert len(queued) == 3
    assert [row["prompt"]["sampler"]["inputs"]["seed"] for row in queued] == [11, 22, 33]
    assert all(row["prompt"]["sampler"]["inputs"]["text"] == "exact literal prompt" for row in queued)
    assert len(set(paths)) == 6
    assert [Path(path).read_bytes() for path in paths] == [
        f"pid-{variant}-{image}.png".encode() for variant in range(1, 4) for image in range(2)
    ]


@pytest.mark.parametrize("explicit_kind", ["missing", "directory"])
def test_comfyui_explicit_workflow_does_not_select_an_unrelated_auto_template(tmp_path, monkeypatch, explicit_kind):
    state = tmp_path / "state"
    state.mkdir()
    auto = state / "auto.json"
    auto.write_text("{}")
    explicit = state / "selected.json"
    if explicit_kind == "directory":
        explicit.mkdir()
    monkeypatch.setattr(backends, "STATE_ROOT", state)
    monkeypatch.setattr(backends, "COMFYUI_WORKFLOW", "selected.json")
    monkeypatch.setattr(backends, "COMFYUI_WORKFLOW_NO_LORA", "auto.json")
    monkeypatch.setattr(backends, "COMFYUI_LORA_NAME", "")
    assert backends.resolve_comfyui_workflow_path() is None
    monkeypatch.setattr(backends, "http_json", lambda *args, **kwargs: pytest.fail("An unselected workflow was queued"))
    assert backends.generate_comfyui("literal", "", "missing-workflow", output_dir=tmp_path) == []
    if explicit_kind == "directory":
        explicit.rmdir()
    explicit.write_text("{}")
    assert backends.resolve_comfyui_workflow_path() == explicit


def test_comfyui_auto_workflow_still_uses_the_configured_template(tmp_path, monkeypatch):
    auto = tmp_path / "auto.json"
    auto.write_text("{}")
    monkeypatch.setattr(backends, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(backends, "COMFYUI_WORKFLOW", "auto")
    monkeypatch.setattr(backends, "COMFYUI_WORKFLOW_NO_LORA", "auto.json")
    monkeypatch.setattr(backends, "COMFYUI_LORA_NAME", "")
    assert backends.resolve_comfyui_workflow_path() == auto
