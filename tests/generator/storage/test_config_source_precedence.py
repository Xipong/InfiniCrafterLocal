"""Current file/process precedence and read-only startup behavior."""
from __future__ import annotations

import os
import pytest

from infini_local.core.env_file import FORMAT_HEADER, read_env_file
from infini_local.core.env_utils import load_env_file
from infini_local.core.config_validation import reject_retired_config
from infini_local.desktop.settings_controller import SettingsController


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", {"HOME": str(tmp_path), "USERPROFILE": str(tmp_path)})


@pytest.mark.parametrize("inherited", ["", "7"])
def test_process_setting_wins_file_but_studio_keeps_file_values(tmp_path, inherited):
    config = tmp_path / "config.env"
    original = (FORMAT_HEADER + '\nINFINI_LLM_NETWORK_ATTEMPTS="2"\nINFINI_IMAGE_API_KEY="file-secret"\n').encode()
    config.write_bytes(original)
    os.environ.update(INFINI_LLM_NETWORK_ATTEMPTS=inherited, INFINI_IMAGE_API_KEY="process-secret")
    for _ in range(2):
        load_env_file(config)
        assert os.environ["INFINI_LLM_NETWORK_ATTEMPTS"] == inherited
        assert os.environ["INFINI_IMAGE_API_KEY"] == "process-secret"
    app = SettingsController(config_path=config)
    assert app.values["INFINI_LLM_NETWORK_ATTEMPTS"] == "2"
    assert app.values["INFINI_IMAGE_API_KEY"] == "file-secret"
    assert config.read_bytes() == original
    assert list(tmp_path.iterdir()) == [config]
    app.save()
    assert read_env_file(config)["INFINI_IMAGE_API_KEY"] == "file-secret"


def test_absent_configuration_does_not_create_files_or_change_environment(tmp_path):
    before = dict(os.environ)
    load_env_file(tmp_path / "config.env")
    assert dict(os.environ) == before
    assert list(tmp_path.iterdir()) == []


def test_unversioned_configuration_refused_by_runtime_and_editor_without_rewrite(tmp_path):
    config = tmp_path / "config.env"
    original = b'INFINI_IMAGE_API_KEY="private-secret"\n'
    config.write_bytes(original)
    before = dict(os.environ)
    for read in (load_env_file, lambda path: SettingsController(config_path=path)):
        with pytest.raises(ValueError, match="format declaration") as error:
            read(config)
        assert "private-secret" not in str(error.value)
    assert config.read_bytes() == original
    assert dict(os.environ) == before
    assert list(tmp_path.iterdir()) == [config]


@pytest.mark.parametrize("key,value,replacement", [
    ("INFINI_LLM_FALLBACK_API_KEY", "retired-secret", "INFINI_LLM_POOL_2_API_KEY"),
    ("INFINI_PROJECTILE_ICON_TARGET_FILL", "0.84", None),
    ("INFINI_CHILD_ICON_TARGET_FILL", "0.72", None),
])
def test_retired_keys_are_refused_not_translated_or_persisted(tmp_path, key, value, replacement):
    config = tmp_path / "config.env"
    config.write_text(FORMAT_HEADER + f'\n{key}="{value}"\n')
    original = config.read_bytes()
    load_env_file(config)
    with pytest.raises(ValueError, match=key) as error:
        reject_retired_config(os.environ)
    assert value not in str(error.value)
    if replacement:
        assert replacement not in os.environ
    else:
        assert "remove this obsolete setting; no replacement" in str(error.value)
    assert config.read_bytes() == original
    assert list(tmp_path.iterdir()) == [config]
