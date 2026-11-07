from dataclasses import replace
from pathlib import Path
import sys

import pytest

from infini_local.services import sdcpp_backend
from tests.generator.images.test_flux_hybrid_profile_contract import _cfg


def portable(tmp_path):
    root = tmp_path / 'renamed portable runtime Юникод'
    (root / 'rocblas/library').mkdir(parents=True)
    for name in ('sd-server.exe', 'ggml-hip.dll', 'amdhip64_7.dll', 'rocblas.dll', 'rocblas/library/kernel.dat'):
        (root / name).write_bytes(b'synthetic layout only; never executed')
    return root


def test_known_portable_layout_adds_only_child_overlay_without_gpu_flags(tmp_path, monkeypatch):
    root = portable(tmp_path)
    monkeypatch.setattr(sys, 'platform', 'win32')
    config = replace(_cfg(root=''), server_exe=str(root / 'sd-server.exe'))
    base = {'PATH': 'original', 'UNCHANGED': 'yes'}
    result = sdcpp_backend.server_process_environment(config, base_env=base)
    assert result['ROCM_COMPAT_ROOT'] == str(root)
    assert result['HIP_PATH'] == result['ROCM_PATH'] == str(root)
    assert result['ROCBLAS_TENSILE_LIBPATH'] == str(root / 'rocblas/library')
    assert result['PATH'].startswith(str(root)) and result['PATH'].endswith('original')
    assert set(result) == set(base) | {'ROCM_COMPAT_ROOT', 'ROCM_PATH', 'HIP_PATH', 'ROCBLAS_TENSILE_LIBPATH'}
    assert base == {'PATH': 'original', 'UNCHANGED': 'yes'} and config.rocm_compat_root == ''
    assert config.extra_args == _cfg(root='').extra_args


@pytest.mark.parametrize('missing', ['sd-server.exe', 'ggml-hip.dll', 'amdhip64_7.dll', 'rocblas.dll', 'rocblas/library/kernel.dat'])
def test_incomplete_layout_never_guesses_environment(tmp_path, monkeypatch, missing):
    root = portable(tmp_path); (root / missing).unlink()
    monkeypatch.setattr(sys, 'platform', 'win32')
    base = {'PATH': 'original'}
    assert sdcpp_backend.server_process_environment(replace(_cfg(root=''), server_exe=str(root / 'sd-server.exe')), base_env=base) == base


@pytest.mark.parametrize('inherited', ['ROCM_COMPAT_ROOT', 'ROCM_PATH', 'HIP_PATH', 'ROCBLAS_TENSILE_LIBPATH'])
def test_inherited_setup_is_not_replaced_by_auto_but_explicit_root_wins(tmp_path, monkeypatch, inherited):
    root = portable(tmp_path); monkeypatch.setattr(sys, 'platform', 'win32')
    base = {'PATH': 'original', inherited: 'operator override'}
    config = replace(_cfg(root=''), server_exe=str(root / 'sd-server.exe'))
    assert sdcpp_backend.server_process_environment(config, base_env=base) == base
    chosen = str(tmp_path / 'explicit override')
    assert sdcpp_backend.server_process_environment(replace(config, rocm_compat_root=chosen), base_env=base)['ROCM_PATH'] == chosen


def test_non_windows_never_autodetects_and_symlink_layout_is_not_followed(tmp_path, monkeypatch):
    root = portable(tmp_path); config = replace(_cfg(root=''), server_exe=str(root / 'sd-server.exe'))
    base = {'PATH': 'original'}
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert sdcpp_backend.server_process_environment(config, base_env=base) == base
    monkeypatch.setattr(sys, 'platform', 'win32')
    dll = root / 'ggml-hip.dll'; dll.unlink(); dll.symlink_to(root / 'rocblas.dll')
    assert sdcpp_backend.server_process_environment(config, base_env=base) == base
