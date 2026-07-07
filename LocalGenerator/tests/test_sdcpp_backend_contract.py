from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.services import sdcpp_backend


def _cfg(**overrides):
    values = dict(
        default_command_template="{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-method {sampler} {extra}",
        command_mode="safe_args",
        server_exe=r"C:\Games\sdcpp\sd-server.exe",
        model=r"C:\Games\sdcpp\models\z-image.gguf",
        vae=r"C:\Games\sdcpp\models\ae.safetensors",
        llm=r"C:\Games\sdcpp\models\qwen.gguf",
        lora_dir="",
        lora_prompt_tags="",
        host="127.0.0.1",
        port=7861,
        width=512,
        height=512,
        steps=8,
        cfg=1.0,
        sampler="euler",
        extra_args="-v --flow-shift 3",
        server_url="http://127.0.0.1:7861",
        health_paths=["/", "/health"],
        zimage_prompt_contract="auto",
        zimage_positive_only=True,
    )
    values.update(overrides)
    return sdcpp_backend.SdcppBackendConfig(**values)


def _check_backend_builds_safe_argv_without_template_bleed() -> None:
    cfg = _cfg(command_mode="safe_args")
    cmd, shell = sdcpp_backend.build_server_command(
        cfg,
        "{exe} --sampling-mOpenRouter + local Z-Image/sd.cppethod {sampler} {extra}",
    )

    assert shell is False
    assert isinstance(cmd, list)
    assert "--sampling-method" in cmd
    assert "euler" in cmd
    assert all("OpenRouter" not in part for part in cmd)
    assert "--vae" in cmd and cfg.vae in cmd
    assert "--llm" in cmd and cfg.llm in cmd


def _check_backend_repairs_known_bad_template_in_template_mode() -> None:
    cfg = _cfg(command_mode="template", vae="", llm="", extra_args="-v")
    cmd, shell = sdcpp_backend.build_server_command(
        cfg,
        "{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-mOpenRouter + local Z-Image/sd.cppethod {sampler} {extra}",
    )

    assert shell is True
    assert isinstance(cmd, str)
    assert "--sampling-method euler" in cmd
    assert "sampling-mOpenRouter" not in cmd


def _check_backend_zimage_payload_clears_negative_channel() -> None:
    payload = sdcpp_backend.server_payload(
        _cfg(),
        "subject",
        "scene, bad",
        512,
        512,
        123,
        "a1111",
        is_zimage=True,
        positive_only=True,
    )

    assert payload["prompt"] == "subject"
    assert payload["negative_prompt"] == ""
    assert payload["zimage_positive_only_prompt"] is True
    assert payload["zimage_prompt_contract"] == "auto"


def _check_backend_extracts_a1111_base64_response(tmp_path: Path) -> None:
    # Minimal valid PNG signature is enough for this contract test; the decoder only writes bytes.
    png = b"\x89PNG\r\n\x1a\n" + b"payload"
    raw = json.dumps({"images": [base64.b64encode(png).decode("ascii")]}).encode("utf-8")
    out = tmp_path / "sprite.png"

    ok = sdcpp_backend.extract_image_from_response(raw, "application/json", out)

    assert ok is True
    assert out.read_bytes() == png


def _check_backend_adds_lora_model_dir_and_prompt_tags() -> None:
    cfg = _cfg(lora_dir=r"C:\Games\sdcpp\loras", lora_prompt_tags="<lora:terraria_items:0.65>")

    cmd, shell = sdcpp_backend.build_server_command(cfg)
    payload = sdcpp_backend.server_payload(
        cfg,
        "a copper bow",
        "",
        512,
        512,
        42,
        "a1111",
        is_zimage=True,
        positive_only=True,
    )

    assert shell is False
    assert isinstance(cmd, list)
    assert "--lora-model-dir" in cmd
    assert r"C:\Games\sdcpp\loras" in cmd
    assert payload["prompt"].endswith("<lora:terraria_items:0.65>")


def _check_image_pipeline_derives_sdcpp_lora_tag_from_selected_file_when_prompt_tags_blank() -> None:
    from infini_local.pipelines import image_backend_pipeline as pipeline

    old_file = pipeline.SDCPP_LORA_FILE
    old_dir = pipeline.SDCPP_LORA_DIR
    old_weight = pipeline.SDCPP_LORA_WEIGHT
    old_tags = pipeline.SDCPP_LORA_PROMPT_TAGS
    try:
        pipeline.SDCPP_LORA_FILE = r"C:\Games\sdcpp\models\pixel_art_style_z_image_turbo.safetensors"
        pipeline.SDCPP_LORA_DIR = r"C:\Games\sdcpp\models"
        pipeline.SDCPP_LORA_WEIGHT = "0.70"
        pipeline.SDCPP_LORA_PROMPT_TAGS = ""

        cfg = pipeline._sdcpp_config()

        assert cfg.lora_prompt_tags == "<lora:pixel_art_style_z_image_turbo:0.70>"
    finally:
        pipeline.SDCPP_LORA_FILE = old_file
        pipeline.SDCPP_LORA_DIR = old_dir
        pipeline.SDCPP_LORA_WEIGHT = old_weight
        pipeline.SDCPP_LORA_PROMPT_TAGS = old_tags


def _check_backend_respects_manual_equals_flags_for_dedicated_paths():
    cfg = _cfg(
        vae=r"C:\Games\sdcpp\models\ae.safetensors",
        llm=r"C:\Games\sdcpp\models\Qwen.gguf",
        lora_dir=r"C:\Games\sdcpp\loras",
        extra_args='--vae=manual_ae.safetensors --llm=manual_qwen.gguf --lora-model-dir=manual_loras',
    )
    cmd, shell = sdcpp_backend.build_server_command(cfg)
    rendered = sdcpp_backend.stringify_cmd(cmd)
    assert rendered.count("--vae") == 1
    assert rendered.count("--llm") == 1
    assert rendered.count("--lora-model-dir") == 1
    assert "manual_ae.safetensors" in rendered
    assert "manual_qwen.gguf" in rendered
    assert "manual_loras" in rendered



def _check_backend_does_not_pass_inactive_lora_dir_without_tags() -> None:
    cfg = _cfg(lora_dir=r"C:\Games\sdcpp\loras", lora_prompt_tags="")

    cmd, shell = sdcpp_backend.build_server_command(cfg)
    rendered = sdcpp_backend.stringify_cmd(cmd)

    assert shell is False
    assert "--lora-model-dir" not in rendered


def _check_backend_appends_lora_tags_individually_without_duplicates() -> None:
    prompt = "pixel item <lora:already:0.4>"
    out = sdcpp_backend.append_lora_prompt_tags(prompt, "<lora:already:0.4> <lora:new_style:0.6>")

    assert out.count("<lora:already:0.4>") == 1
    assert out.endswith("<lora:new_style:0.6>")


def _check_extra_args_split_strips_helper_quotes_for_argv_mode() -> None:
    tokens = sdcpp_backend.split_extra_args('--cache-mode dbcache --cache-option "threshold=0.08,warmup=2"')

    assert tokens == ["--cache-mode", "dbcache", "--cache-option", "threshold=0.08,warmup=2"]

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_backend_builds_safe_argv_without_template_bleed',
    '_check_backend_repairs_known_bad_template_in_template_mode',
    '_check_backend_zimage_payload_clears_negative_channel',
    '_check_backend_extracts_a1111_base64_response',
    '_check_backend_adds_lora_model_dir_and_prompt_tags',
    '_check_image_pipeline_derives_sdcpp_lora_tag_from_selected_file_when_prompt_tags_blank',
    '_check_backend_respects_manual_equals_flags_for_dedicated_paths',
    '_check_backend_does_not_pass_inactive_lora_dir_without_tags',
    '_check_backend_appends_lora_tags_individually_without_duplicates',
    '_check_extra_args_split_strips_helper_quotes_for_argv_mode'
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


def test_sdcpp_backend_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
