"""Offline user-preset persistence contracts; no Tk, providers or auth state."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from infini_local.desktop import settings_env, settings_schema


def test_snapshot_keeps_exact_string_settings_without_credentials():
    snapshot = getattr(settings_env, "user_preset_snapshot", None)
    assert callable(snapshot), "settings_env has no user-preset snapshot API"
    safe = {
        "INFINI_LLM_MAX_TOKENS": "12345",
        "INFINI_LLM_REASONING_MAX_TOKENS": "2500",
        "INFINI_VISUAL_DIRECTOR_MAX_TOKENS": "",
        "INFINI_max_tokens": "17",
        "INFINI_UNKNOWN_KNOB": "  exact\nЮникод # value  ",
        "INFINI_TOKENIZER_MODEL": "a/tokenizer",
        "INFINI_LLM_POOL_2_MODEL": "Provider/CaseSensitive",
    }
    secrets = {
        "INFINI_OPENROUTER_API_KEY": "FAKE-SECRET-CANARY",
        "INFINI_LLM_POOL_4_API_KEY": "FAKE-SECRET-CANARY",
        "INFINI_ACCESS_TOKEN": "FAKE-SECRET-CANARY",
        "INFINI_TOKEN": "FAKE-SECRET-CANARY",
        "INFINI_REFRESH_TOKEN": "FAKE-SECRET-CANARY",
        "INFINI_CLIENT_SECRET": "FAKE-SECRET-CANARY",
        "INFINI_PASSWORD": "FAKE-SECRET-CANARY",
        "INFINI_CREDENTIALS": "FAKE-SECRET-CANARY",
        "INFINI_CREDENTIAL": "FAKE-SECRET-CANARY",
    }
    data = {
        **safe, **secrets,
        "INFINI_GUI_PIPELINE_PRESET": "Мой: выбранный",
        "OPENAI_API_KEY": "FAKE-SECRET-CANARY",
        "UNRELATED": "not a setting",
        "INFINI_NONSTRING": 42,
        42: "not a string key",
    }
    before = dict(data)
    assert snapshot(data) == safe
    assert data == before, "snapshot mutated the GUI's current settings"


def test_named_profiles_roundtrip_and_update_without_losing_neighbors(tmp_path: Path):
    save = getattr(settings_env, "save_user_preset", None)
    load = getattr(settings_env, "load_user_presets", None)
    assert callable(save) and callable(load), "settings_env has no named user-preset persistence API"
    assert settings_env.CUSTOM_PRESET == "Custom"
    assert settings_env.USER_PRESET_PREFIX == "Мой: "
    path = tmp_path / "user-presets.json"
    # Names are literal JSON map keys, never paths to individual profile files.
    name = "../not-a-file.json"
    original = {
        "INFINI_LLM_PROVIDER": "openai_compat",
        "INFINI_LLM_MAX_TOKENS": "13579",
        "INFINI_SDCPP_SERVER_EXTRA_ARGS": "  --unknown='точно' --rng cpu  ",
        "INFINI_FUTURE_KNOB": "False",
        "INFINI_BG_COLOR": "transparent",
    }
    assert save(path, name, {**original, "INFINI_GUI_PIPELINE_PRESET": "Custom",
                            "INFINI_IMAGE_API_KEY": "FAKE-SECRET-CANARY"}) == {name: original}
    assert load(path) == {name: original}
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema": "infini.gui-user-presets.v1", "presets": {name: original},
    }
    neighbor = {"INFINI_LLM_MAX_TOKENS": "777", "INFINI_UNLISTED_NEIGHBOR": "keep"}
    save(path, "Сосед", neighbor)
    changed = {**original, "INFINI_LLM_MAX_TOKENS": "24680", "INFINI_BG_COLOR": "green"}
    expected = {name: changed, "Сосед": neighbor}
    assert save(path, name, changed) == expected
    assert load(path) == expected
    # A returned profile can be selected verbatim; no defaults/coercion are added.
    assert load(path)[name] == changed
    assert {child.name for child in tmp_path.iterdir()} == {path.name}


def test_missing_user_preset_file_loads_empty_without_creating_it(tmp_path: Path):
    load = getattr(settings_env, "load_user_presets", None)
    assert callable(load), "settings_env has no user-preset loader"
    path = tmp_path / "missing.json"
    assert load(path) == {}
    assert not path.exists()


@pytest.mark.parametrize("replace_fails", [False, True])
def test_atomic_save_publishes_complete_sibling_or_preserves_old_file(tmp_path: Path, monkeypatch, replace_fails):
    save = getattr(settings_env, "save_user_preset", None)
    assert callable(save), "settings_env has no atomic user-preset writer"
    path = tmp_path / "profiles.json"
    old = {"Old": {"INFINI_LLM_MAX_TOKENS": "1"}}
    save(path, "Old", old["Old"])
    original = path.read_bytes()
    expected = {**old, "New": {"INFINI_LLM_MAX_TOKENS": "2"}}
    replace = os.replace
    replacements = []

    def observe_replace(source, destination):
        source, destination = Path(source), Path(destination)
        assert destination == path
        assert source != path and source.parent == path.parent
        assert path.read_bytes() == original, "target was changed before atomic replacement"
        assert json.loads(source.read_text(encoding="utf-8")) == {
            "schema": "infini.gui-user-presets.v1", "presets": expected,
        }
        replacements.append(source)
        if replace_fails:
            raise OSError("fixture: atomic replace unavailable")
        return replace(source, destination)

    monkeypatch.setattr(os, "replace", observe_replace)
    if replace_fails:
        with pytest.raises(OSError, match="fixture"):
            save(path, "New", expected["New"])
        assert path.read_bytes() == original
    else:
        assert save(path, "New", expected["New"]) == expected
        assert settings_env.load_user_presets(path) == expected
    assert len(replacements) == 1, "save did not publish through atomic replacement"
    assert {child.name for child in tmp_path.iterdir()} == {path.name}, "temporary profile file leaked"


@pytest.mark.parametrize("malformed", [
    b'{"presets":',
    b'[]',
    b'{"schema":"other.v1","presets":{}}',
    b'{"schema":"infini.gui-user-presets.v1"}',
    b'{"schema":"infini.gui-user-presets.v1","presets":[]}',
    b'{"schema":"infini.gui-user-presets.v1","presets":{"Broken":[]}}',
    b'{"schema":"infini.gui-user-presets.v1","presets":{"Broken":{"INFINI_LLM_MAX_TOKENS":12}}}',
    b'{"schema":"infini.gui-user-presets.v1","presets":{"Custom":{}}}',
    b'{"schema":"infini.gui-user-presets.v1","presets":{"Same":{},"Same":{}}}',
])
def test_malformed_file_is_refused_without_overwriting_any_bytes(tmp_path: Path, malformed):
    path = tmp_path / "presets.json"
    path.write_bytes(malformed)
    with pytest.raises(ValueError):
        settings_env.load_user_presets(path)
    with pytest.raises(ValueError):
        settings_env.save_user_preset(path, "Valid", {"INFINI_LLM_MAX_TOKENS": "4"})
    assert path.read_bytes() == malformed
    assert {child.name for child in tmp_path.iterdir()} == {path.name}


@pytest.mark.parametrize("invalid_name", [
    "", " \t ", "x" * 81, None, 123, "Custom", " custom ",
    "Мой: уже отображаемое имя", "Мой:", "мОй: another", "bad\nname", "bad\x00name",
    *settings_schema.PRESETS,
])
def test_invalid_or_reserved_profile_names_are_refused(tmp_path: Path, invalid_name):
    path = tmp_path / "presets.json"
    with pytest.raises(ValueError):
        settings_env.save_user_preset(path, invalid_name, {"INFINI_UNKNOWN": "keep"})
    assert not path.exists(), "invalid name created a preset file"


def test_loaded_neighbors_are_sanitized_but_token_limits_and_bounded_names_survive(tmp_path: Path):
    path = tmp_path / "presets.json"
    safe = {"INFINI_LLM_MAX_TOKENS": "4321", "INFINI_FUTURE_TOKENS": "11"}
    path.write_text(json.dumps({
        "schema": "infini.gui-user-presets.v1",
        "presets": {"Existing": {**safe, "INFINI_AUTH_TOKEN": "FAKE-SECRET-CANARY",
                                  "INFINI_CLIENT_SECRET": "FAKE-SECRET-CANARY",
                                  "INFINI_GUI_PIPELINE_PRESET": "Custom"}},
    }), encoding="utf-8")
    original = path.read_bytes()
    assert settings_env.load_user_presets(path) == {"Existing": safe}
    assert path.read_bytes() == original, "load rewrote the user's preset file"
    name = "я" * 80
    expected = {"Existing": safe, name: {"INFINI_FUTURE_KNOB": "yes"}}
    assert settings_env.save_user_preset(path, name, expected[name]) == expected
    assert settings_env.load_user_presets(path) == expected
    assert "CANARY" not in path.read_text(encoding="utf-8"), "resave retained a neighbor's secret"
