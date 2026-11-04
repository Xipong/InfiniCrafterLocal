"""Malformed environment values must not crash actual configuration imports."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_bad_infini_env_values_fallback_instead_of_crashing() -> None:
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "LocalGenerator"),
        "INFINI_USE_LLM": "abc",
        "INFINI_LLM_MAX_TOKENS": "abc",
        "INFINI_SDCPP_WIDTH": "abc",
        "INFINI_SDCPP_HEIGHT": "abc",
        "INFINI_SDCPP_TIMEOUT": "abc",
        "INFINI_COMFYUI_HEIGHT": "abc",
        "INFINI_IMAGE_API_TIMEOUT": "abc",
        "INFINI_IMAGE_BACKEND": "off",
    })
    proc = subprocess.run(
        [sys.executable, "-c", "from infini_local.core.llm_config import LLM_MAX_TOKENS; from infini_local.core.images.config import SDCPP_HEIGHT, SDCPP_TIMEOUT; print(LLM_MAX_TOKENS, SDCPP_HEIGHT, SDCPP_TIMEOUT)"],
        cwd=ROOT / "LocalGenerator",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_retired_configuration_migrates_before_actual_bootstrap_with_exact_backup(tmp_path):
    import json
    from infini_local.core.env_file import FORMAT_HEADER, read_env_file

    config = tmp_path / "config.env"
    before = (b'\xef\xbb\xbf# old saved settings\r\nINFINI_LLM_REAUTHOR_TEMPERATURE=0.23\r\n'
              b'INFINI_LLM_FALLBACK_NETWORK_FAILS=3\r\n'
              b'INFINI_LLM_FALLBACK_API_KEY="synthetic-old-secret"\r\n'
              b'INFINI_OPENAI_COMPAT_IMAGE_MODEL=old-image-model\r\n'
              b'INFINI_IMAGE_BACKEND=disabled\r\n'
              b'INFINI_CUSTOM_EXTENSION=keep this\r\n')
    config.write_bytes(before)
    env = {key: value for key, value in os.environ.items() if not key.startswith("INFINI_")}
    env.update(PYTHONPATH=str(ROOT / "LocalGenerator"), INFINI_DATA_DIR=str(tmp_path))
    command = [sys.executable, "-c", '''
import json, os
from infini_local.core import config_bootstrap
from infini_local.core.config_validation import retired_config_errors
assert not retired_config_errors(os.environ)
assert os.environ["INFINI_LLM_POOL_2_API_KEY"] == "synthetic-old-secret"
print(json.dumps({key: os.environ[key] for key in (
    "INFINI_LLM_REPAIR_TEMPERATURE", "INFINI_LLM_NETWORK_ATTEMPTS",
    "INFINI_IMAGE_API_MODEL", "INFINI_IMAGE_BACKEND", "INFINI_CUSTOM_EXTENSION")}))
''']
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {
        "INFINI_LLM_REPAIR_TEMPERATURE": "0.23", "INFINI_LLM_NETWORK_ATTEMPTS": "3",
        "INFINI_IMAGE_API_MODEL": "old-image-model", "INFINI_IMAGE_BACKEND": "off",
        "INFINI_CUSTOM_EXTENSION": "keep this",
    }
    assert "synthetic-old-secret" not in result.stdout + result.stderr
    backups = list(tmp_path.glob("config.env.pre-migration-*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == before
    migrated = config.read_bytes()
    assert migrated.startswith(FORMAT_HEADER.encode())
    assert read_env_file(config)["INFINI_LLM_POOL_2_API_KEY"] == "synthetic-old-secret"
    assert (tmp_path / "cache").is_dir()
    repeated = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert repeated.returncode == 0, repeated.stderr
    assert config.read_bytes() == migrated
    assert list(tmp_path.glob("config.env.pre-migration-*.bak")) == backups
    assert backups[0].read_bytes() == before


def test_canonical_configuration_ignores_generic_provider_aliases(tmp_path):
    import json
    env = {key: value for key, value in os.environ.items() if not key.startswith("INFINI_")}
    env.update({
        "PYTHONPATH": str(ROOT / "LocalGenerator"), "INFINI_DATA_DIR": str(tmp_path), "INFINI_SKIP_CONFIG_FILE": "1",
        "OPENAI_BASE_URL": "https://obsolete.invalid/v1", "OPENAI_MODEL": "obsolete-model",
        "OPENAI_API_KEY": "unrelated-process-secret", "OPENROUTER_API_KEY": "unrelated-process-secret",
        "OPENROUTER_MODEL": "obsolete-model", "SDCPP_MODEL": "obsolete-file.gguf",
        "INFINI_LLM_NETWORK_ATTEMPTS": "3", "INFINI_LLM_REPAIR_TEMPERATURE": "0.23",
        "INFINI_OPENAI_COMPAT_MODEL": "chosen-model", "INFINI_IMAGE_API_MODEL": "chosen-image",
    })
    result = subprocess.run([sys.executable, "-c", '''
import json
from infini_local.core import llm_config as llm
from infini_local.core.images import config as image
from infini_local.pipelines.transport.profiles import configured_llm_pool
from infini_local.pipelines.author.request import _gameplay_repair_temperature
print(json.dumps([llm.LMSTUDIO_URL, llm.LMSTUDIO_MODEL, llm.OPENROUTER_API_KEY,
                  llm.OPENAI_COMPAT_API_KEY, llm.OPENAI_COMPAT_BASE_URL, image.IMAGE_API_KEY,
                  image.SDCPP_MODEL, llm.OPENAI_COMPAT_MODEL, image.IMAGE_API_MODEL,
                  llm.LLM_NETWORK_ATTEMPTS, _gameplay_repair_temperature(), configured_llm_pool()[0]["provider"]]))
'''], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == [
        "http://127.0.0.1:1234", "auto", "", "", "", "", "", "chosen-model", "chosen-image", 3, 0.23, "local"]


def test_settings_controller_startup_migrates_retired_keys_without_starting_generator(tmp_path, monkeypatch):
    from infini_local.core.config_validation import retired_config_errors
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_env import parse_env

    config = tmp_path / "config.env"
    before = (b'INFINI_LLM_FALLBACK_API_KEY=synthetic-old-secret\n'
              b'INFINI_CUSTOM_EXTENSION=keep\n')
    config.write_bytes(before)
    def forbidden_network(*args, **kwargs):
        raise AssertionError("network started")
    monkeypatch.setattr(SettingsController, "_fetch_health_snapshot", forbidden_network)
    controller = SettingsController(config_path=config)
    current = controller.collect()
    assert not retired_config_errors(current)
    assert current["INFINI_LLM_POOL_2_API_KEY"] == "synthetic-old-secret"
    assert current["INFINI_CUSTOM_EXTENSION"] == "keep"
    assert "INFINI_LLM_FALLBACK_API_KEY" not in current
    assert parse_env(config)["INFINI_LLM_POOL_2_API_KEY"] == "synthetic-old-secret"
    backups = list(tmp_path.glob("config.env.pre-migration-*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == before
    assert "synthetic-old-secret" not in controller.status
    assert controller.proc is None


def test_retired_image_backend_names_refuse_at_dispatch(tmp_path):
    import json
    aliases = ["stablediffusioncpp", "stable-diffusion.cpp", "stable_diffusion_cpp", "api_image",
               "openai_image", "openai_images", "openai_compat_image", "none", "disabled"]
    env = {key: value for key, value in os.environ.items() if not key.startswith("INFINI_")}
    env.update(PYTHONPATH=str(ROOT / "LocalGenerator"), INFINI_DATA_DIR=str(tmp_path), INFINI_SKIP_CONFIG_FILE="1")
    result = subprocess.run([sys.executable, "-c", '''
import importlib, json, os, sys
from infini_local.core.images import config
from infini_local.pipelines.images import stage
errors = []
def forbidden_io(*args, **kwargs):
    raise AssertionError("retired backend reached an image adapter")
for alias in json.loads(sys.argv[1]):
    # Inject after the migration boundary: dispatch itself must remain strict.
    stage.IMAGE_BACKEND = alias
    stage.IMAGE_BACKEND_CONFIG_ERROR = ""
    for name in ("generate_sdcpp", "generate_a1111", "generate_comfyui", "generate_image_api", "generate_openai_codex"):
        setattr(stage, name, forbidden_io)
    try:
        stage._generate_backend_variants({}, prompt="test", negative="", asset_id="test", canvas=32, role="item")
    except stage.ImageBackendConfigurationError as error:
        errors.append(str(error))
    else:
        raise AssertionError("retired backend was accepted")
print(json.dumps(errors))
''', json.dumps(aliases)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == [f"unsupported image backend: {alias}" for alias in aliases]


def test_skip_config_file_still_migrates_process_settings_without_touching_file(tmp_path):
    import json
    config = tmp_path / 'config.env'
    original = b'# deliberately invalid format\nINFINI_SECRET="malformed\n'
    config.write_bytes(original)
    env = {key: value for key, value in os.environ.items() if not key.startswith('INFINI_')}
    env.update(PYTHONPATH=str(ROOT / 'LocalGenerator'), INFINI_DATA_DIR=str(tmp_path),
               INFINI_SKIP_CONFIG_FILE='1', INFINI_LLM_REAUTHOR_TEMPERATURE='0.23',
               INFINI_IMAGE_BACKEND='disabled', INFINI_OPENAI_COMPAT_IMAGE_API_KEY='synthetic-process-secret')
    result = subprocess.run([sys.executable, '-c', '''
import json, os
from infini_local.core import llm_config
from infini_local.core.images import config as images
from infini_local.core import config_bootstrap
from infini_local.core.config_validation import retired_config_errors
assert not retired_config_errors(os.environ)
assert os.environ['INFINI_IMAGE_API_KEY'] == 'synthetic-process-secret'
print(json.dumps([os.environ['INFINI_LLM_REPAIR_TEMPERATURE'], images.IMAGE_BACKEND]))
'''], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == ['0.23', 'off']
    assert 'synthetic-process-secret' not in result.stdout + result.stderr
    assert config.read_bytes() == original
    assert not list(tmp_path.glob('config.env.pre-migration-*.bak'))
