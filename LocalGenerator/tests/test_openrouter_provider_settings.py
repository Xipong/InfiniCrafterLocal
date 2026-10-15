"""Offline settings controls for strict per-profile OpenRouter routing."""
from __future__ import annotations

import pytest

from infini_local.desktop import settings_env, settings_schema as schema
from infini_local.desktop.settings_fields import FIELDS, disabled_reasons

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


def test_pin_visibility_tracks_exact_profile_provider_without_erasing_values():
    values = dict(schema.DEFAULTS)
    values.update({MAIN: "Acme/region-a", FALLBACK: "chutes", POOL[0]: "novita"})
    values.update(INFINI_LLM_PROVIDER="openrouter", INFINI_LLM_POOL_2_ENABLED="1",
                      INFINI_LLM_POOL_2_PROVIDER="openrouter", INFINI_LLM_FALLBACK_PROVIDER="openrouter",
                      INFINI_LLM_FALLBACK_MODEL="owner/model")
    disabled = disabled_reasons(values, False)
    assert not disabled[MAIN] and not disabled[FALLBACK] and not disabled[POOL[0]]
    assert disabled[POOL[1]] and disabled[POOL[2]]
    values.update(INFINI_LLM_PROVIDER="local", INFINI_LLM_POOL_2_PROVIDER="openai_compat",
                      INFINI_LLM_FALLBACK_PROVIDER="local")
    disabled = disabled_reasons(values, False)
    assert disabled[MAIN] and disabled[FALLBACK] and disabled[POOL[0]]
    assert [values[key] for key in (MAIN, FALLBACK, POOL[0])] == ["Acme/region-a", "chutes", "novita"]
    values.update(INFINI_LLM_PROVIDER="openrouter", INFINI_LLM_FALLBACK_PROVIDER="")
    disabled = disabled_reasons(values, False)
    assert not disabled[FALLBACK]  # Empty fallback provider inherits the primary route.
    values["INFINI_LLM_FALLBACK_MODEL"] = ""
    disabled = disabled_reasons(values, False)
    assert disabled[FALLBACK]


def test_multidev_metadata_has_one_provider_pin_for_each_pool_profile():
    for key in POOL:
        fields = [field for field in FIELDS if field['key'] == key]
        assert len(fields) == 1
        assert not fields[0]['secret']
