"""Offline settings controls for strict per-profile OpenRouter routing."""
from __future__ import annotations

import pytest

from infini_local.desktop import settings_env, settings_schema as schema
from infini_local.desktop.settings_gui_trace_state import SettingsGuiTraceStateMixin
from infini_local.desktop.settings_gui_ui import SettingsGuiUiMixin

MAIN = "INFINI_OPENROUTER_PROVIDER"
FALLBACK = "INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER"
POOL = [f"INFINI_LLM_POOL_{slot}_OPENROUTER_PROVIDER" for slot in (2, 3, 4)]


@pytest.mark.parametrize("key", [MAIN, FALLBACK, *POOL])
def test_routing_fields_default_to_auto_and_are_saved_in_normal_order(key):
    assert schema.DEFAULTS[key] == ""
    assert schema.FIELD_ORDER.count(key) == 1
    assert schema.FIELD_HELP[key]


def test_exact_provider_slugs_survive_save_reload_and_provider_switch(tmp_path):
    path = tmp_path / "config.env"
    values = dict(schema.DEFAULTS)
    expected = dict(zip([MAIN, FALLBACK, *POOL], ["Acme/region-a", "chutes", "deepinfra/turbo", "", "novita"]))
    values.update(expected)
    values.update(INFINI_LLM_PROVIDER="openai_compat", INFINI_OPENROUTER_MODEL="owner/model:free")
    settings_env.write_env(path, values)
    loaded = settings_env.parse_env(path)
    assert {key: loaded[key] for key in expected} == expected
    assert loaded["INFINI_OPENROUTER_MODEL"] == "owner/model:free"
    for key in expected:
        assert path.read_text().index(key + "=") < path.read_text().index("# ===== IMAGE =====")


class _FalseVar:
    def get(self):
        return False


class _Visibility(SettingsGuiTraceStateMixin):
    def __init__(self):
        self.values = dict(schema.DEFAULTS)
        self.field_widgets = {}
        self.extra_arg_buttons = []
        self.sdcpp_debug_buttons = []
        self.radmin_enabled = _FalseVar()
        self.vars = {}
        self.enabled = {}

    def _value(self, key, default=""):
        return self.values.get(key, default)

    def _set_field_enabled(self, key, enabled, reason=""):
        self.enabled[key] = enabled

    def _set_widgets_enabled(self, _widgets, _enabled):
        pass

    def _refresh_secret_entries(self):
        pass


def test_pin_visibility_tracks_exact_profile_provider_without_erasing_values():
    gui = _Visibility()
    gui.values.update({MAIN: "Acme/region-a", FALLBACK: "chutes", POOL[0]: "novita"})
    gui.values.update(INFINI_LLM_PROVIDER="openrouter", INFINI_LLM_POOL_2_ENABLED="1",
                      INFINI_LLM_POOL_2_PROVIDER="openrouter", INFINI_LLM_FALLBACK_PROVIDER="openrouter",
                      INFINI_LLM_FALLBACK_MODEL="owner/model")
    gui._refresh_visibility()
    assert gui.enabled[MAIN] and gui.enabled[FALLBACK] and gui.enabled[POOL[0]]
    assert not gui.enabled[POOL[1]] and not gui.enabled[POOL[2]]
    gui.values.update(INFINI_LLM_PROVIDER="local", INFINI_LLM_POOL_2_PROVIDER="openai_compat",
                      INFINI_LLM_FALLBACK_PROVIDER="local")
    gui._refresh_visibility()
    assert not gui.enabled[MAIN] and not gui.enabled[FALLBACK] and not gui.enabled[POOL[0]]
    assert [gui.values[key] for key in (MAIN, FALLBACK, POOL[0])] == ["Acme/region-a", "chutes", "novita"]
    gui.values.update(INFINI_LLM_PROVIDER="openrouter", INFINI_LLM_FALLBACK_PROVIDER="")
    gui._refresh_visibility()
    assert gui.enabled[FALLBACK]  # Empty fallback provider inherits the primary route.
    gui.values["INFINI_LLM_FALLBACK_MODEL"] = ""
    gui._refresh_visibility()
    assert not gui.enabled[FALLBACK]


def test_multidev_builder_creates_a_provider_pin_row_for_each_pool_profile():
    class Form(SettingsGuiUiMixin):
        def __init__(self):
            self.rows = []
        def _card(self, *_args, **_kwargs):
            return object()
        def _info_panel(self, *_args, **_kwargs):
            pass
        def row(self, _parent, _label, key, **kwargs):
            self.rows.append((key, kwargs))
    form = Form()
    SettingsGuiUiMixin._build_multidev(form, object())
    keys = [key for key, _ in form.rows]
    for key in POOL:
        assert keys.count(key) == 1
        assert not dict(form.rows)[key].get("secret", False)
