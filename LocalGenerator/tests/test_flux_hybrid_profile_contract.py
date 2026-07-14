from __future__ import annotations

import os
from pathlib import PureWindowsPath

from infini_local.desktop import settings_schema
from infini_local.services import sdcpp_backend


def _cfg(*, root: str) -> sdcpp_backend.SdcppBackendConfig:
    return sdcpp_backend.SdcppBackendConfig(
        default_command_template=settings_schema.SDCPP_DEFAULT_COMMAND_TEMPLATE,
        command_mode="safe_args",
        server_exe=r"C:\Games\sdcpp-hybrid-gfx1030\sd-server.exe",
        model=r"C:\Games\sdcpp\models\Flux 2 4B\flux-2-klein-4b-Q8_0.gguf",
        vae=r"C:\Games\sdcpp\models\Flux 2 4B\ae.safetensors",
        llm=r"C:\Games\sdcpp\models\Flux 2 4B\Qwen3-4B-UD-Q5_K_XL.gguf",
        lora_dir="",
        lora_prompt_tags="",
        host="127.0.0.1",
        port=7861,
        width=512,
        height=512,
        steps=4,
        cfg=1.0,
        sampler="euler",
        extra_args=settings_schema.SDCPP_EXTRA_PROFILES["flux2_klein4b_rx6800xt_hybrid"],
        server_url="http://127.0.0.1:7861",
        health_paths=["/v1/models"],
        zimage_prompt_contract="0",
        zimage_positive_only=True,
        rocm_compat_root=root,
    )


def _contract_check_flux2_klein4b_hybrid_profile_matches_measured_winner() -> None:
    profile = settings_schema.SDCPP_EXTRA_PROFILES["flux2_klein4b_rx6800xt_hybrid"]
    assert "--backend diffusion=rocm0,vae=vulkan0,te=rocm0" in profile
    assert "--params-backend te=cpu" in profile
    assert "--rng cuda" in profile
    assert "--flow-shift 3" in profile
    assert "--eager-load" in profile
    assert "--diffusion-conv-direct" in profile
    assert "--vae-conv-direct" in profile
    assert "--diffusion-fa" not in profile

    preset = settings_schema.PRESETS["Локалка: LM Studio + FLUX.2 Klein 4B hybrid"]
    assert preset["INFINI_SDCPP_SERVER_EXE"] == r"C:\Games\sdcpp-hybrid-gfx1030\sd-server.exe"
    assert preset["INFINI_SDCPP_STEPS"] == "4"
    assert preset["INFINI_SDCPP_CFG"] == "1.0"
    assert preset["INFINI_SDCPP_SAMPLER"] == "euler"
    assert preset["INFINI_SDCPP_LORA_PROMPT_TAGS"] == ""
    assert preset["INFINI_ZIMAGE_PROMPT_CONTRACT"] == "0"


def _contract_check_rocm_compat_environment_is_scoped_to_sd_server_child() -> None:
    root = r"C:\Games\sdcpp-hybrid-gfx1030"
    base = {"PATH": r"C:\Windows\System32", "KEEP": "yes"}
    env = sdcpp_backend.server_process_environment(_cfg(root=root), base_env=base)

    expected_root = str(PureWindowsPath(root))
    assert env is not base
    assert env["KEEP"] == "yes"
    assert env["ROCM_COMPAT_ROOT"] == expected_root
    assert env["ROCM_PATH"] == expected_root
    assert env["HIP_PATH"] == expected_root
    assert env["ROCBLAS_TENSILE_LIBPATH"] == str(PureWindowsPath(root) / "rocblas" / "library")
    assert env["PATH"].startswith(expected_root + os.pathsep) or env["PATH"].startswith(expected_root + ";")
    assert "ROCM_COMPAT_ROOT" not in base


def _contract_check_no_rocm_root_returns_an_unmodified_environment_copy() -> None:
    base = {"PATH": "base", "KEEP": "yes"}
    env = sdcpp_backend.server_process_environment(_cfg(root=""), base_env=base)
    assert env == base
    assert env is not base


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_flux_hybrid_profile_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_flux2_klein4b_hybrid_profile_matches_measured_winner',
            '_contract_check_rocm_compat_environment_is_scoped_to_sd_server_child',
            '_contract_check_no_rocm_root_returns_an_unmodified_environment_copy',
        ),
    )
