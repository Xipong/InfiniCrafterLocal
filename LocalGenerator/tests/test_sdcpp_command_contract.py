from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.web import server
from infini_local.pipelines import image_backend_pipeline as IMAGE_BACKEND_PIPELINE
from infini_local.pipelines import pipeline_visual_config as visual_config
from infini_local.services import sdcpp_backend


def _expected_host_path(path: str) -> str:
    if os.name == "nt":
        return path
    return "/mnt/" + path[0].lower() + path[2:].replace("\\", "/")


def _check_sdcpp_safe_args_ignores_corrupt_command_template(monkeypatch) -> None:
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_COMMAND_MODE", "safe_args")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXE", r"C:\Games\sdcpp\sd-server.exe")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_MODEL", r"C:\Games\sdcpp\models\z-image.gguf")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_VAE", r"C:\Games\sdcpp\models\ae.safetensors")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LLM", r"C:\Games\sdcpp\models\qwen.gguf")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_DIR", r"C:\Games\sdcpp\loras")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_PROMPT_TAGS", "<lora:terraria:0.5>")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXTRA_ARGS", "-v --flow-shift 3")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SAMPLER", "euler")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_COMMAND_TEMPLATE", "{exe} --sampling-mOpenRouter + local Z-Image/sd.cppethod {sampler} {extra}")

    cmd, shell = IMAGE_BACKEND_PIPELINE.build_sdcpp_server_command()

    assert shell is False
    assert isinstance(cmd, list)
    assert "--sampling-method" in cmd
    assert "euler" in cmd
    assert all("OpenRouter" not in part for part in cmd)
    assert "--vae" in cmd and r"C:\Games\sdcpp\models\ae.safetensors" in cmd
    assert "--llm" in cmd and r"C:\Games\sdcpp\models\qwen.gguf" in cmd
    assert "--lora-model-dir" in cmd and r"C:\Games\sdcpp\loras" in cmd


def _check_sdcpp_safe_args_converts_only_exe_path_for_posix_subprocess(monkeypatch) -> None:
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_COMMAND_MODE", "safe_args")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXE", r"C:\Games\sdcpp\sd-server.exe")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_MODEL", r"C:\Games\sdcpp\models\z-image.gguf")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_VAE", r"C:\Games\sdcpp\models\ae.safetensors")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LLM", r"C:\Games\sdcpp\models\qwen.gguf")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_DIR", r"C:\Games\sdcpp\loras")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_PROMPT_TAGS", "<lora:terraria:0.5>")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXTRA_ARGS", "")

    cmd, shell = IMAGE_BACKEND_PIPELINE.build_sdcpp_server_command()

    assert shell is False
    assert isinstance(cmd, list)
    assert cmd[0] == _expected_host_path(r"C:\Games\sdcpp\sd-server.exe")
    assert r"C:\Games\sdcpp\models\z-image.gguf" in cmd
    assert r"C:\Games\sdcpp\models\ae.safetensors" in cmd
    assert r"C:\Games\sdcpp\models\qwen.gguf" in cmd
    assert r"C:\Games\sdcpp\loras" in cmd


def _check_sdcpp_template_mode_repairs_known_sampling_method_corruption(monkeypatch) -> None:
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_COMMAND_MODE", "template")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXE", r"C:\Games\sdcpp\sd-server.exe")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_MODEL", r"C:\Games\sdcpp\models\z-image.gguf")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_VAE", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LLM", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_DIR", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_PROMPT_TAGS", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXTRA_ARGS", "-v")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SAMPLER", "euler")
    monkeypatch.setattr(
        IMAGE_BACKEND_PIPELINE,
        "SDCPP_SERVER_COMMAND_TEMPLATE",
        "{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-mOpenRouter + local Z-Image/sd.cppethod {sampler} {extra}",
    )

    cmd, shell = IMAGE_BACKEND_PIPELINE.build_sdcpp_server_command()

    assert shell is True
    assert isinstance(cmd, str)
    assert "--sampling-method euler" in cmd
    assert "sampling-mOpenRouter" not in cmd


def _check_sdcpp_lora_file_tag_helper_and_prompt_suffix() -> None:
    from infini_local.services import sdcpp_backend

    assert sdcpp_backend.lora_tag_from_file(r"C:\Games\sdcpp\loras\terraria_items.safetensors", "0.55") == "<lora:terraria_items:0.55>"

    cfg = sdcpp_backend.SdcppBackendConfig(
        default_command_template=visual_config.SDCPP_DEFAULT_COMMAND_TEMPLATE,
        command_mode="safe_args",
        server_exe=r"C:\Games\sdcpp\sd-server.exe",
        model=r"C:\Games\sdcpp\models\z-image.gguf",
        vae="",
        llm="",
        lora_dir=r"C:\Games\sdcpp\loras",
        lora_prompt_tags="<lora:terraria_items:0.55>",
        host="127.0.0.1",
        port=7861,
        width=512,
        height=512,
        steps=8,
        cfg=1.0,
        sampler="euler",
        extra_args="",
        server_url="http://127.0.0.1:7861",
        health_paths=["/"],
        zimage_prompt_contract="auto",
        zimage_positive_only=True,
    )

    payload = sdcpp_backend.server_payload(
        cfg,
        "pixel art bow",
        "",
        512,
        512,
        42,
        "auto",
        is_zimage=True,
        positive_only=True,
    )
    assert payload["prompt"].endswith("<lora:terraria_items:0.55>")
    assert payload["prompt"].count("<lora:terraria_items:0.55>") == 1


def _check_sdcpp_debug_snapshot_exposes_lora_file_fields() -> None:
    from infini_local.services import sdcpp_service

    state = sdcpp_service.SdcppServerState()
    snap = sdcpp_service.debug_snapshot(
        state=state,
        app_version="0.4.test",
        server_url="http://127.0.0.1:7861",
        server_autostart=True,
        show_console=True,
        server_exe="sd-server.exe",
        model="z.gguf",
        vae="ae.safetensors",
        llm="qwen.gguf",
        lora_dir=r"C:\Games\sdcpp\loras",
        lora_file=r"C:\Games\sdcpp\loras\terraria_items.safetensors",
        lora_weight="0.55",
        lora_prompt_tags="<lora:terraria_items:0.55>",
        command_mode="safe_args",
        command_template="",
        template_repair=("", False, ""),
        manual_extra_args="",
        effective_extra_args="--lora-model-dir C:/Games/sdcpp/loras",
        command="sd-server.exe ...",
        server_log_file="",
        server_is_alive=False,
        server_is_configured=True,
        tail_text_file=lambda _path, _chars: "",
        include_log_tail=False,
    )

    assert snap["loraFile"].endswith("terraria_items.safetensors")
    assert snap["loraWeight"] == "0.55"
    assert snap["loraPromptTags"] == "<lora:terraria_items:0.55>"


def _check_sdcpp_canonical_state_cleanup_and_health_snapshot() -> None:
    import infini_local.pipelines.pipeline_visual_config as pipeline_visual_config
    import infini_local.pipelines.image_backend_pipeline as image_backend_pipeline

    assert pipeline_visual_config.SDCPP_SERVER_STATE is image_backend_pipeline.SDCPP_SERVER_STATE
    assert not hasattr(server, "SDCPP_SERVER_STATE")
    assert server.cleanup_sdcpp_server_process is pipeline_visual_config.cleanup_sdcpp_server_process

    utility_routes = server._utility_routes()
    assert utility_routes.cleanup_for_shutdown is server.cleanup_sdcpp_server_process


def _check_sdcpp_health_reads_canonical_state_fields() -> None:
    import infini_local.pipelines.pipeline_visual_config as pipeline_visual_config

    state = pipeline_visual_config.SDCPP_SERVER_STATE
    old_last_command = state.last_command
    old_last_start_error = state.last_start_error
    old_last_exit = state.last_exit
    old_last_log_file = state.last_log_file

    try:
        state.last_command = "test canonical command"
        state.last_start_error = "test canonical start error"
        state.last_exit = {"returncode": 23, "signal": None}
        state.last_log_file = "/tmp/canonical-sdcpp.log"

        health = server._health_payload()

        assert health["sdcpp"]["lastCommand"] == "test canonical command"
        assert health["sdcpp"]["lastStartError"] == "test canonical start error"
        assert health["sdcpp"]["lastExit"] == {"returncode": 23, "signal": None}
        assert health["sdcpp"]["logFile"] == "/tmp/canonical-sdcpp.log"
    finally:
        state.last_command = old_last_command
        state.last_start_error = old_last_start_error
        state.last_exit = old_last_exit
        state.last_log_file = old_last_log_file


def _check_sdcpp_lora_file_overrides_stale_lora_dir(monkeypatch) -> None:
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_COMMAND_MODE", "safe_args")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXE", r"C:\Games\sdcpp\sd-server.exe")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_MODEL", r"C:\Games\sdcpp\models\z-image.gguf")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_VAE", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LLM", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_DIR", r"C:\stale\wrong_loras")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_LORA_PROMPT_TAGS", "<lora:terraria_items:0.55>")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SERVER_EXTRA_ARGS", "")
    monkeypatch.setattr(IMAGE_BACKEND_PIPELINE, "SDCPP_SAMPLER", "euler")
    # Simulate server startup normalization after reading INFINI_SDCPP_LORA_FILE.
    monkeypatch.setattr(
        IMAGE_BACKEND_PIPELINE,
        "SDCPP_LORA_DIR",
        sdcpp_backend.lora_dir_from_file(r"D:\Art\loras\terraria_items.safetensors"),
    )

    cmd, shell = IMAGE_BACKEND_PIPELINE.build_sdcpp_server_command()

    assert shell is False
    assert isinstance(cmd, list)
    assert "--lora-model-dir" in cmd
    assert r"D:\Art\loras" in cmd
    assert r"C:\stale\wrong_loras" not in cmd


# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
        '_check_sdcpp_safe_args_ignores_corrupt_command_template',
        '_check_sdcpp_safe_args_converts_only_exe_path_for_posix_subprocess',
        '_check_sdcpp_template_mode_repairs_known_sampling_method_corruption',
        '_check_sdcpp_lora_file_tag_helper_and_prompt_suffix',
        '_check_sdcpp_debug_snapshot_exposes_lora_file_fields',
        '_check_sdcpp_lora_file_overrides_stale_lora_dir',
        '_check_sdcpp_canonical_state_cleanup_and_health_snapshot',
        '_check_sdcpp_health_reads_canonical_state_fields',
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_sdcpp_command_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
