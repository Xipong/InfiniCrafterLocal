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


def test_retired_configuration_refuses_before_bootstrap_without_editing_saved_values(tmp_path):
    import json
    from infini_local.core.config_validation import RETIRED_CONFIG_REPLACEMENTS
    from infini_local.desktop.settings_env import write_env

    config = tmp_path / "config.env"
    old = {key: "synthetic-retired-value" for key in RETIRED_CONFIG_REPLACEMENTS}
    write_env(config, {**old, "INFINI_CUSTOM_EXTENSION": "keep this"})
    before = config.read_bytes()
    env = {key: value for key, value in os.environ.items() if not key.startswith("INFINI_")}
    env.update(PYTHONPATH=str(ROOT / "LocalGenerator"), INFINI_DATA_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", '''
import json
try:
    from infini_local.core import config_bootstrap
except ValueError as error:
    print(json.dumps(str(error)))
else:
    raise AssertionError("retired configuration was accepted")
'''], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    error = json.loads(result.stdout)
    assert all(key in error for key in old)
    assert "synthetic-retired-value" not in error
    assert config.read_bytes() == before
    assert not (tmp_path / "cache").exists()


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


def test_retired_settings_remain_editable_but_cannot_restart_generator(tmp_path, monkeypatch):
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_env import write_env, parse_env

    config = tmp_path / "config.env"
    old = {"INFINI_LLM_FALLBACK_API_KEY": "synthetic-old-secret", "INFINI_CUSTOM_EXTENSION": "keep"}
    write_env(config, old)
    before = config.read_bytes()
    controller = SettingsController(config_path=config)
    monkeypatch.setattr(controller, "_fetch_health_snapshot", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("network started")))
    result = controller.start_server()
    assert result["ok"] is False
    assert "INFINI_LLM_FALLBACK_API_KEY" in result["message"]
    assert "INFINI_LLM_POOL_2_API_KEY" in result["message"]
    assert "synthetic-old-secret" not in result["message"]
    assert config.read_bytes() == before
    assert all(parse_env(config)[key] == value for key, value in old.items())
    assert controller.collect()["INFINI_LLM_FALLBACK_API_KEY"] == "synthetic-old-secret"
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
    os.environ["INFINI_IMAGE_BACKEND"] = alias
    importlib.reload(config)
    importlib.reload(stage)
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
