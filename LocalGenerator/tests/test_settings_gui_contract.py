from __future__ import annotations

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.desktop import settings_env, settings_gui, settings_schema
import infini_local.desktop.settings_sdcpp_args as settings_sdcpp_args


GUI_PATH = Path(settings_gui.__file__)
GUI_SOURCE = "\n".join(
    p.read_text(encoding="utf-8")
    for p in [
        GUI_PATH,
        GUI_PATH.with_name("settings_gui_ui.py"),
        GUI_PATH.with_name("settings_gui_image_args.py"),
        GUI_PATH.with_name("settings_gui_trace_state.py"),
        GUI_PATH.with_name("settings_gui_server_controls.py"),
    ]
)
SETTINGS_ENV_SOURCE = Path(settings_env.__file__).read_text(encoding="utf-8")
SETTINGS_SDCPP_ARGS_SOURCE = Path(settings_sdcpp_args.__file__).read_text(encoding="utf-8")


def _check_lora_folder_is_hidden_from_gui_rows_but_kept_for_hidden_env() -> None:
    assert 'self.row(parent, "LoRA folder"' not in GUI_SOURCE
    assert "LoRA folder скрыт" in GUI_SOURCE
    assert "INFINI_SDCPP_LORA_DIR" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_SDCPP_LORA_DIR"] == ""


def _check_sdcpp_option_help_is_visible_and_has_expanded_flags() -> None:
    assert "Что делают пресеты и флаги sd.cpp" in GUI_SOURCE
    labels = [name for name, _fragment, _help in settings_schema.SDCPP_EXTRA_FLAG_SPECS]
    assert "LoRA runtime" in labels
    assert "LoRA auto" in labels
    assert "Cache DBCache" in labels
    assert "Params disk" in labels
    assert len(labels) >= 12


def _check_schema_fields_and_image_profiles_are_reachable_from_gui() -> None:
    visible_rows = set(re.findall(r"self\.(?:row|text_row)\([^)]*?[\"'](INFINI_[A-Z0-9_]+)[\"']", GUI_SOURCE, flags=re.S))
    intentionally_hidden = {
        "INFINI_GUI_PIPELINE_PRESET",  # top-level preset combobox, not a normal row
        "INFINI_SDCPP_LORA_DIR",  # derived from the selected LoRA file
    }
    assert set(settings_schema.FIELD_ORDER) - intentionally_hidden == visible_rows
    assert all(profile in GUI_SOURCE for profile in settings_schema.SDCPP_EXTRA_PROFILES)


def _check_gui_extra_arg_helpers_replace_conflicting_value_flags() -> None:
    cur = settings_gui.SettingsGui._split_extra_for_gui("-v --rng cuda --flow-shift 3")
    frag = settings_gui.SettingsGui._split_extra_for_gui("--rng cpu")
    names = settings_gui.SettingsGui._extra_option_names(frag)
    out = settings_gui.SettingsGui._remove_extra_options(cur, names) + frag
    rendered = settings_gui.SettingsGui._join_extra_for_gui(out)
    assert "--rng cpu" in rendered
    assert "--rng cuda" not in rendered
    assert "--flow-shift 3" in rendered
    assert "from infini_local.desktop.settings_sdcpp_args import (" in GUI_SOURCE
    assert "def split_extra_for_gui" in SETTINGS_SDCPP_ARGS_SOURCE
    assert "def _split_extra_for_gui" not in GUI_SOURCE
    assert settings_gui.SettingsGui._split_extra_for_gui is settings_sdcpp_args.split_extra_for_gui


def _check_sdcpp_presets_use_measured_amd_placements_without_redundant_assignments() -> None:
    safe = settings_schema.SDCPP_EXTRA_PROFILES["zimage_amd_safe"]
    assert "--backend diffusion=vulkan0,vae=vulkan0,te=vulkan0" in safe
    assert "--params-backend te=cpu" in safe
    assert "--diffusion-conv-direct" in safe
    assert "--vae-conv-direct" in safe
    assert "--eager-load" in safe
    assert "runtime diffusion/VAE/TE на Vulkan" in GUI_SOURCE
    assert "параметры Qwen/TE в RAM" in GUI_SOURCE

    full_gpu = settings_schema.SDCPP_EXTRA_PROFILES["zimage_amd_full_gpu"]
    assert "--backend diffusion=vulkan0,vae=vulkan0,te=vulkan0" in full_gpu
    assert "--params-backend" not in full_gpu
    assert "--diffusion-conv-direct" in full_gpu
    assert "--vae-conv-direct" in full_gpu
    assert "--eager-load" in full_gpu

    normal_profiles = [
        "zimage_amd_low_vram",
        "zimage_cpu_compat",
    ]
    for name in normal_profiles:
        value = settings_schema.SDCPP_EXTRA_PROFILES[name]
        assert "--params-backend" not in value


def _check_flow_shift_help_explains_meaning_not_only_quality() -> None:
    flow_help = " ".join(desc for name, _fragment, desc in settings_schema.SDCPP_EXTRA_FLAG_SPECS if name.startswith("Flow"))
    assert "timestep" in flow_help
    assert "Flow/DiT" in flow_help
    assert "мяг" in flow_help


def _check_gui_health_identity_helpers_detect_other_copy_from_root() -> None:
    assert settings_gui.SettingsGui._norm_path_for_compare(r"D:\\A\\LocalGenerator") == settings_gui.SettingsGui._norm_path_for_compare(r"d:/a/LocalGenerator/")
    assert "serverRoot" in GUI_SOURCE
    assert "assetSync" in GUI_SOURCE
    assert "Port still busy" in GUI_SOURCE
    assert "_cleanup_old_helper_servers_before_start" in GUI_SOURCE
    assert "_health_looks_like_infini_helper" in GUI_SOURCE
    assert "/shutdown" in GUI_SOURCE


def _check_gui_trace_fetch_uses_health_identity_and_longer_timeout() -> None:
    assert "_fetch_health_snapshot(timeout=8)" in GUI_SOURCE
    assert "timeout=18" in GUI_SOURCE
    assert "другая копия" in GUI_SOURCE


def _check_pipeline_preset_is_saved_and_restored_from_config() -> None:
    key = "INFINI_GUI_PIPELINE_PRESET"
    assert key in settings_schema.FIELD_ORDER
    assert key in settings_schema.DEFAULTS
    assert settings_gui.SettingsGui._pipeline_preset_from_config({
        key: "OpenRouter + local Z-Image/sd.cpp",
        "INFINI_LLM_PROVIDER": "local",
        "INFINI_IMAGE_BACKEND": "off",
    }) == "OpenRouter + local Z-Image/sd.cpp"
    assert settings_gui.SettingsGui._pipeline_preset_from_config({
        "INFINI_LLM_PROVIDER": "openrouter",
        "INFINI_IMAGE_BACKEND": "sdcpp",
    }) == "OpenRouter + local Z-Image/sd.cpp"
    assert 'data["INFINI_GUI_PIPELINE_PRESET"] = self.preset_var.get().strip()' in GUI_SOURCE
    assert 'self.data["INFINI_GUI_PIPELINE_PRESET"] = preset_name' in GUI_SOURCE


def _check_start_server_has_safe_stale_process_cleanup_contract() -> None:
    assert "taskkill" in GUI_SOURCE
    assert "netstat" in GUI_SOURCE
    assert "server.py запущен" in GUI_SOURCE
    assert "GUI не будет убивать чужой процесс" in GUI_SOURCE
    assert settings_gui.SettingsGui._looks_like_infini_server_command(r"python D:\X\InfiniCrafterLocal\LocalGenerator\server.py")
    assert settings_gui.SettingsGui._looks_like_infini_server_command(r"python D:\X\LocalGenerator\server.py")
    assert not settings_gui.SettingsGui._looks_like_infini_server_command(r"C:\Games\sdcpp\sd-server.exe")
    assert settings_gui.SettingsGui._health_looks_like_infini_helper({"ok": True, "serverRoot": r"D:\X\LocalGenerator"})
    assert not settings_gui.SettingsGui._health_looks_like_infini_helper({"ok": True, "service": "unrelated"})


def _check_radmin_gui_has_auto_url_and_friend_guide_controls() -> None:
    assert "Auto Radmin URL" in GUI_SOURCE
    assert "Copy friend guide" in GUI_SOURCE
    assert "Open MP connect page" in GUI_SOURCE
    assert "INFINI_TERRARIA_PORT" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_TERRARIA_PORT"] == "7777"
    assert "_detect_ipv4_candidates" in GUI_SOURCE
    assert "_friend_guide_text" in GUI_SOURCE
    assert "/mp_connect" in GUI_SOURCE
    assert "0.0.0.0" in GUI_SOURCE


def _check_radmin_gui_friend_guide_says_clients_do_not_need_localgenerator_for_ready_items() -> None:
    assert "Тебе прилетают уже готовые предметы" in GUI_SOURCE
    assert "финальные PNG/JSON ассеты" in GUI_SOURCE


def _check_gui_exposes_llm_temperatures_not_zimage_temperature() -> None:
    assert "INFINI_LLM_TEMPERATURE" in settings_schema.FIELD_ORDER
    assert "INFINI_VISUAL_DIRECTOR_TEMPERATURE" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_LLM_TEMPERATURE"] == "0.38"
    assert settings_schema.DEFAULTS["INFINI_VISUAL_DIRECTOR_TEMPERATURE"] == "0.42"
    assert "Planner temperature" in GUI_SOURCE
    assert "Visual temp" in GUI_SOURCE
    assert "Это не sd.cpp temperature" in GUI_SOURCE


def _check_gui_env_file_io_lives_in_settings_env() -> None:
    assert "from infini_local.desktop.settings_env import" in GUI_SOURCE
    assert "def parse_env" not in GUI_SOURCE
    assert "def write_env" not in GUI_SOURCE
    assert "def parse_env" in SETTINGS_ENV_SOURCE
    assert "def write_env" in SETTINGS_ENV_SOURCE
    assert callable(settings_env.parse_env)
    assert callable(settings_env.write_env)

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_lora_folder_is_hidden_from_gui_rows_but_kept_for_hidden_env',
    '_check_sdcpp_option_help_is_visible_and_has_expanded_flags',
    '_check_schema_fields_and_image_profiles_are_reachable_from_gui',
    '_check_gui_extra_arg_helpers_replace_conflicting_value_flags',
    '_check_sdcpp_presets_use_measured_amd_placements_without_redundant_assignments',
    '_check_flow_shift_help_explains_meaning_not_only_quality',
    '_check_gui_health_identity_helpers_detect_other_copy_from_root',
    '_check_gui_trace_fetch_uses_health_identity_and_longer_timeout',
    '_check_pipeline_preset_is_saved_and_restored_from_config',
    '_check_start_server_has_safe_stale_process_cleanup_contract',
    '_check_radmin_gui_has_auto_url_and_friend_guide_controls',
    '_check_radmin_gui_friend_guide_says_clients_do_not_need_localgenerator_for_ready_items',
    '_check_gui_exposes_llm_temperatures_not_zimage_temperature',
    '_check_gui_env_file_io_lives_in_settings_env'
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


def test_settings_gui_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
