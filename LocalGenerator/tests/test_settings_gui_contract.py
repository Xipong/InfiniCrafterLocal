from __future__ import annotations

import importlib.abc
import importlib.util
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract_checks import literal_string_arguments
from infini_local.desktop import settings_env, settings_gui, settings_schema
import infini_local.desktop.settings_sdcpp_args as settings_sdcpp_args
import infini_local.desktop.settings_gui_trace_state as settings_trace_state


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


class _BlockTkinter(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):  # type: ignore[override]
        if fullname == "tkinter" or fullname.startswith("tkinter."):
            raise ModuleNotFoundError("No module named 'tkinter'")
        return None


def _check_settings_gui_imports_without_tkinter_installed() -> None:
    """Headless Python installs must import GUI helpers without tkinter/_tkinter."""
    module_path = GUI_PATH
    spec = importlib.util.spec_from_file_location("_infini_settings_gui_headless_probe", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    saved_tk_modules = {key: value for key, value in sys.modules.items() if key == "tkinter" or key.startswith("tkinter.")}
    saved_compat = {key: value for key, value in sys.modules.items() if key.endswith("desktop.tk_compat")}
    blocker = _BlockTkinter()
    try:
        for key in [*saved_tk_modules, *saved_compat]:
            sys.modules.pop(key, None)
        sys.meta_path.insert(0, blocker)
        spec.loader.exec_module(module)
    finally:
        if blocker in sys.meta_path:
            sys.meta_path.remove(blocker)
        for key in list(sys.modules):
            if key == "tkinter" or key.startswith("tkinter.") or key.endswith("desktop.tk_compat"):
                sys.modules.pop(key, None)
        sys.modules.update(saved_tk_modules)
        sys.modules.update(saved_compat)

    assert module.tk_compat.TKINTER_AVAILABLE is False
    assert "self.secret_entries: list[tk.Widget] = []" in GUI_PATH.read_text(encoding="utf-8")
    assert isinstance(module.tk.Tk(), module.tk.Widget)
    assert isinstance(module.ttk.Entry(), module.ttk.Widget)


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
    # Parsed from the module rather than regex-scraped: a call whose earlier
    # arguments contain a parenthesis (a label like "Label (advanced)", a nested
    # self._card(...), a bracketed hint) is invisible to a `[^)]*?` pattern, which
    # would report an exposed setting as missing.
    visible_rows = set(
        literal_string_arguments(
            GUI_SOURCE,
            ("row", "text_row", "check_row"),
            match=r"INFINI_[A-Z0-9_]+",
        )
    )
    dynamic_pool_rows = {
        f"INFINI_LLM_POOL_{slot}_{suffix}"
        for slot in (2, 3, 4)
        for suffix in ("ENABLED", "PROVIDER", "BASE_URL", "API_KEY", "MODEL", "API_MODE")
    }
    intentionally_hidden = {
        "INFINI_GUI_PIPELINE_PRESET",  # top-level preset combobox, not a normal row
        "INFINI_SDCPP_LORA_DIR",  # derived from the selected LoRA file
    }
    assert set(settings_schema.FIELD_ORDER) - intentionally_hidden - dynamic_pool_rows == visible_rows
    assert "for slot in (2, 3, 4):" in GUI_SOURCE
    assert all(f'_{suffix}"' in GUI_SOURCE for suffix in ("ENABLED", "PROVIDER", "BASE_URL", "API_KEY", "MODEL", "API_MODE"))
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
    assert settings_gui.SettingsGui._split_extra_for_gui is settings_sdcpp_args.split_extra_for_gui
    assert settings_gui.SettingsGui._remove_extra_options is settings_sdcpp_args.remove_extra_options


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
    compat_flux = "OpenAI-compatible + FLUX.2 Klein 4B hybrid"
    assert key in settings_schema.FIELD_ORDER
    assert key in settings_schema.DEFAULTS
    assert compat_flux in settings_schema.PRESETS
    assert settings_schema.PRESETS[compat_flux]["INFINI_LLM_PROVIDER"] == "openai_compat"
    assert settings_schema.PRESETS[compat_flux]["INFINI_LLM_REASONING_MODE"] == "prompt_light"
    assert "diffusion=rocm0,vae=vulkan0,te=rocm0" in settings_schema.PRESETS[compat_flux]["INFINI_SDCPP_SERVER_EXTRA_ARGS"]
    assert settings_schema.PRESETS[compat_flux]["INFINI_SDCPP_STEPS"] == "4"
    assert settings_schema.PRESETS[compat_flux]["INFINI_ZIMAGE_PROMPT_CONTRACT"] == "0"
    assert settings_gui.SettingsGui._pipeline_preset_from_config({
        key: "OpenRouter + local Z-Image/sd.cpp",
        "INFINI_LLM_PROVIDER": "openai_compat",
        "INFINI_IMAGE_BACKEND": "sdcpp",
        "INFINI_SDCPP_SERVER_EXE": r"C:\Games\sdcpp-hybrid-gfx1030-134c821\sd-server.exe",
        "INFINI_SDCPP_SERVER_EXTRA_ARGS": settings_schema.SDCPP_EXTRA_PROFILES["flux2_klein4b_rx6800xt_hybrid"],
        "INFINI_SDCPP_STEPS": "4",
    }) == compat_flux
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
    assert "INFINI_LLM_REAUTHOR_MODEL" not in settings_schema.FIELD_ORDER
    assert "INFINI_LLM_REAUTHOR_TEMPERATURE" in settings_schema.FIELD_ORDER
    assert "INFINI_VISUAL_DIRECTOR_TEMPERATURE" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_LLM_TEMPERATURE"] == "0.38"
    assert "INFINI_LLM_REAUTHOR_MODEL" not in settings_schema.DEFAULTS
    assert settings_schema.DEFAULTS["INFINI_LLM_REAUTHOR_TEMPERATURE"] == ""
    assert settings_schema.DEFAULTS["INFINI_VISUAL_DIRECTOR_TEMPERATURE"] == "0.42"
    fallback_heading = GUI_SOURCE.index('"04 · Fallback LLM"')
    fallback_last_row = GUI_SOURCE.index('"Fallback after transport fails"', fallback_heading)
    primary_heading = GUI_SOURCE.index('"05 · Генерация и reasoning"')
    planner_row = GUI_SOURCE.index('"Planner temperature"', primary_heading)
    repair_temperature_row = GUI_SOURCE.index('"Repair temperature"', planner_row)
    visual_row = GUI_SOURCE.index('"Visual temp"', repair_temperature_row)
    reasoning_row = GUI_SOURCE.index('"Reasoning mode"', visual_row)
    assert fallback_heading < fallback_last_row < primary_heading < planner_row < repair_temperature_row < visual_row < reasoning_row
    assert '"Repair model"' not in GUI_SOURCE
    assert "Это не sd.cpp temperature" in GUI_SOURCE


def _check_gui_exposes_critical_delivery_and_busy_wait_controls() -> None:
    assert "INFINI_COMBINE_BUSY_WAIT_SECONDS" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_COMBINE_BUSY_WAIT_SECONDS"] == "210"
    assert '"Combine busy wait", "INFINI_COMBINE_BUSY_WAIT_SECONDS"' in GUI_SOURCE
    assert "INFINI_VISUAL_REQUIRE_ITEM_SPRITE" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_VISUAL_REQUIRE_ITEM_SPRITE"] == "1"
    assert '"Require item sprite", "INFINI_VISUAL_REQUIRE_ITEM_SPRITE"' in GUI_SOURCE


def _check_gui_exposes_debug_attack_consumable_minimum_as_checkbox_and_amount() -> None:
    enabled = "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED"
    minimum = "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD"
    assert enabled in settings_schema.FIELD_ORDER
    assert minimum in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS[enabled] == "0"
    assert settings_schema.DEFAULTS[minimum] == "10"
    assert f'self.check_row(debug_card, "Включить минимум для атакующих расходников", "{enabled}"' in GUI_SOURCE
    assert f'"Минимум за один крафт", "{minimum}"' in GUI_SOURCE
    assert 'onvalue="1"' in GUI_SOURCE and 'offvalue="0"' in GUI_SOURCE
    assert f'set_field_enabled("{minimum}", attack_consumable_debug' in GUI_SOURCE
    gui_text = GUI_SOURCE.casefold()
    assert "consumable weapon и ammo" in gui_text
    assert "зелья и материалы не меняются" in gui_text

    example = (GUI_PATH.parents[2] / "config.example.env").read_text(encoding="utf-8")
    assert f"{enabled}=0" in example
    assert f"{minimum}=10" in example


def _check_gui_env_file_io_lives_in_settings_env(tmp_path: Path) -> None:
    assert settings_gui.parse_env is settings_env.parse_env
    assert settings_trace_state.parse_env is settings_env.parse_env
    assert settings_trace_state.write_env is settings_env.write_env
    path = tmp_path / "settings.env"
    settings_trace_state.write_env(path, {
        "INFINI_GUI_PIPELINE_PRESET": "OpenRouter + local Z-Image/sd.cpp",
        "INFINI_IMAGE_BACKEND": "sdcpp",
        "INFINI_MANUAL_KEY": "retained",
    })
    parsed = settings_gui.parse_env(path)
    assert parsed["INFINI_GUI_PIPELINE_PRESET"] == "OpenRouter + local Z-Image/sd.cpp"
    assert parsed["INFINI_IMAGE_BACKEND"] == "sdcpp"
    assert parsed["INFINI_MANUAL_KEY"] == "retained"

def _check_gui_lora_blank_weight_uses_safe_default_and_structured_transport_copy() -> None:
    tag = settings_gui.SettingsGui._lora_tag_from_file(r"C:\\Models\\pixel_art.safetensors", "")
    assert tag == "<lora:pixel_art:0.25>"
    assert "активная LoRA — через <lora:name:weight> в prompt" not in GUI_SOURCE
    assert "структурированный HTTP payload" in GUI_SOURCE


def _check_dead_image_role_flags_are_removed_and_shared_gpu_gate_is_real() -> None:
    root = GUI_PATH.parents[2]
    pipeline_config = (GUI_PATH.parents[1] / "pipelines" / "pipeline_visual_config.py").read_text(encoding="utf-8")
    image_gui = (GUI_PATH.parent / "settings_gui_ui.py").read_text(encoding="utf-8")
    image_args = (GUI_PATH.parent / "settings_gui_image_args.py").read_text(encoding="utf-8")
    config_env_path = GUI_PATH.parents[2] / "config.env"
    config_env = config_env_path.read_text(encoding="utf-8") if config_env_path.exists() else ""
    config_example = (GUI_PATH.parents[2] / "config.example.env").read_text(encoding="utf-8")
    registry = (root.parent / "contracts" / "config_registry.json").read_text(encoding="utf-8")
    dead = (
        "INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES",
        "INFINI_VISUAL_GENERATE_IMPACT_IMAGES",
        "INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES",
    )
    all_surfaces = "\n".join((GUI_SOURCE, image_gui, image_args, pipeline_config, config_env, config_example, registry))
    assert all(key not in all_surfaces for key in dead)

    gate = "INFINI_IMAGE_MAX_CONCURRENCY"
    assert gate in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS[gate] == "1"
    assert f'"Shared image concurrency", "{gate}"' in image_gui
    assert gate in pipeline_config
    if config_env_path.exists():
        assert f"{gate}=1" in config_env
    assert f"{gate}=1" in config_example
    assert gate in registry


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_settings_gui_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
