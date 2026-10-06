from __future__ import annotations

import importlib.abc
import importlib.util
from pathlib import Path
import re
import sys
import json
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin

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
        for suffix in ("ENABLED", "PROVIDER", "BASE_URL", "API_KEY", "MODEL", "OPENROUTER_PROVIDER", "API_MODE")
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
    assert "generationActivity" in GUI_SOURCE
    assert "_health_looks_like_infini_helper" in GUI_SOURCE
    assert "/shutdown" in GUI_SOURCE


def _check_gui_trace_fetch_uses_health_identity_and_longer_timeout() -> None:
    assert "_fetch_health_snapshot(timeout=8, base_url=base_url)" in GUI_SOURCE
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


def _check_start_server_has_guarded_http_restart_contract() -> None:
    assert "server.py запущен" in GUI_SOURCE
    assert "GUI не будет убивать чужой процесс" in GUI_SOURCE
    assert "force_restart_server" in GUI_SOURCE
    assert "_shutdown_identity_is_safe" in GUI_SOURCE
    assert "_activity_restart_refusal" in GUI_SOURCE
    assert "self.proc.terminate(" not in GUI_SOURCE
    assert "self.proc.kill(" not in GUI_SOURCE
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


class _UiVar:
    """Strict UI-bound variable; a worker read or write is a test failure."""
    def __init__(self, value=""):
        self.value = value
        self.owner = threading.get_ident()

    def get(self):
        assert threading.get_ident() == self.owner, "worker read a Tk variable"
        return self.value

    def set(self, value):
        assert threading.get_ident() == self.owner, "worker wrote a Tk variable"
        self.value = value


class _GuiWorkflowHarness(SettingsGuiServerControlsMixin, settings_trace_state.SettingsGuiTraceStateMixin):
    """Real desktop callbacks with an explicit headless UI scheduling seam."""
    def __init__(self):
        self.vars = {}
        self.text_widgets = {}
        self.data = dict(settings_schema.DEFAULTS)
        self.radmin_enabled = _UiVar(False)
        self.status_var = _UiVar()
        self.applied_config_var = _UiVar("Runtime config not checked (partial non-secret projection).")
        self.trace_status_var = _UiVar()
        self.proc = None
        self.owner = threading.get_ident()
        self.jobs = {}
        self.serial = 0
        self.rendered = {}
        self.destroyed = False

    def after(self, _delay, callback):
        assert threading.get_ident() == self.owner, "worker scheduled Tk callback"
        self.serial += 1
        self.jobs[self.serial] = callback
        return self.serial

    def after_cancel(self, job):
        assert threading.get_ident() == self.owner
        self.jobs.pop(job, None)

    def drain_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            callbacks, self.jobs = self.jobs, {}
            for callback in callbacks.values():
                callback()
            time.sleep(0.005)
        assert predicate(), "worker result did not reach UI within test deadline"

    def _set_trace_text(self, key, content):
        assert threading.get_ident() == self.owner, "worker rendered Tk text"
        self.rendered[key] = content

    def _lora_dir_from_file(self, _filename):
        return ""

    def destroy(self):
        self.destroyed = True


@pytest.fixture
def gui_workflow(tmp_path, monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    root = tmp_path / "LocalGenerator"
    root.mkdir()
    config = root / "config.env"
    monkeypatch.setattr(settings_trace_state, "ROOT", root)
    monkeypatch.setattr(settings_trace_state, "CONFIG_PATH", config)
    monkeypatch.setattr(controls, "ROOT", root)
    monkeypatch.setattr(controls, "CONFIG_PATH", config)
    monkeypatch.delenv("INFINI_CACHE_DIR", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    return _GuiWorkflowHarness(), root, config


@pytest.mark.parametrize("saved,inherited,relative", [
    (None, None, "cache"),
    ("selected-cache", None, "selected-cache"),
    ("ABSOLUTE", None, "absolute-cache"),
    (None, "inherited-cache", "inherited-cache"),
    (None, "ABSOLUTE", "absolute-cache"),
    ("selected-cache", "inherited-cache", "selected-cache"),
    ("", "inherited-cache", "."),
])
def test_offline_trace_cache_root_matches_gui_launch_environment(gui_workflow, monkeypatch, saved, inherited, relative):
    gui, root, config = gui_workflow
    if saved is not None:
        config.write_text("INFINI_CACHE_DIR=" + (str(root / "absolute-cache") if saved == "ABSOLUTE" else saved) + "\n", encoding="utf-8")
    if inherited is not None:
        monkeypatch.setenv("INFINI_CACHE_DIR", str(root / "absolute-cache") if inherited == "ABSOLUTE" else inherited)
    selected = (root / relative).resolve()
    selected.mkdir(exist_ok=True)
    (selected / "events.ndjson").write_text('{"message":"selected"}\n', encoding="utf-8")
    launch_env = os.environ.copy()
    launch_env.update(gui.collect())
    launch_path = Path(launch_env.get("INFINI_CACHE_DIR", str(root / "cache")))
    if not launch_path.is_absolute():
        launch_path = root / launch_path
    assert launch_path.resolve() == selected
    snapshot = gui._load_local_trace_snapshot("offline")
    assert Path(snapshot["cacheDir"]).resolve() == selected
    assert snapshot["events"] == [{"message": "selected"}]


def test_trace_refresh_returns_while_worker_is_held_and_only_ui_renders(gui_workflow, monkeypatch):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def fetch(*args, **kwargs):
        calls.append((threading.get_ident(), args, kwargs))
        entered.set()
        assert release.wait(2), "test network hold expired"
        finished.set()
        return {"serverRoot": str(root), "cacheDir": "held-server-cache", "events": [{"message": "from-worker"}]}

    monkeypatch.setattr(gui, "_fetch_trace_snapshot", fetch)
    try:
        before = time.monotonic()
        gui.refresh_trace()
        elapsed = time.monotonic() - before
        assert elapsed < 0.2, "Refresh blocked the UI callback on network I/O"
        assert entered.wait(1)
        assert not gui.rendered, "trace rendered before the held worker returned"
        assert calls[0][0] != gui.owner
        release.set()
        assert finished.wait(1)
        gui.drain_until(lambda: "summary" in gui.rendered)
        assert "from-worker" in gui.rendered["events"]
    finally:
        release.set()


def test_overlapping_trace_refresh_has_one_worker_and_only_latest_pending_request(gui_workflow, monkeypatch):
    gui, root, _config = gui_workflow
    gui.vars["INFINI_PORT"] = _UiVar("5055")
    entered, release = threading.Event(), threading.Event()
    calls = []

    def fetch(*args, **kwargs):
        calls.append(kwargs["base_url"])
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return {"serverRoot": str(root), "cacheDir": calls[-1], "events": [{"message": calls[-1]}]}

    monkeypatch.setattr(gui, "_fetch_trace_snapshot", fetch)
    try:
        gui.refresh_trace()
        assert entered.wait(1)
        for port in range(5100, 5125):
            gui.vars["INFINI_PORT"].set(str(port))
            gui.refresh_trace()
        assert calls == ["http://127.0.0.1:5055"], "overlapping refresh spawned unbounded I/O workers"
        assert len(gui.jobs) == 1
        release.set()
        gui.drain_until(lambda: "5124" in gui.rendered.get("summary", ""))
        assert calls == ["http://127.0.0.1:5055", "http://127.0.0.1:5124"]
        assert not gui.jobs
    finally:
        release.set()


@pytest.mark.parametrize("action", ["cancel", "close"])
def test_trace_cancel_or_close_retires_held_and_pending_results(gui_workflow, monkeypatch, action):
    gui, root, _config = gui_workflow
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def fetch(*args, **kwargs):
        calls.append(kwargs["base_url"])
        entered.set()
        assert release.wait(3)
        finished.set()
        return {"serverRoot": str(root), "cacheDir": "stale", "events": [{"message": "stale"}]}

    monkeypatch.setattr(gui, "_fetch_trace_snapshot", fetch)
    try:
        gui.refresh_trace()
        assert entered.wait(1)
        gui.refresh_trace()  # pending request must be retired as well
        if action == "close":
            gui.on_close()
            assert gui.destroyed
            assert not gui.jobs, "close retained a Tk after callback"
        else:
            cancel = getattr(gui, "cancel_trace_refresh", None)
            assert callable(cancel), "trace refresh has no cancellation action"
            cancel()
            assert "cancel" in gui.trace_status_var.get().lower()
        release.set()
        assert finished.wait(1)
        if action == "cancel":
            gui.drain_until(lambda: not gui.jobs)
        else:
            for callback in list(gui.jobs.values()):
                callback()
        assert not gui.rendered
        assert len(calls) == 1
        assert not gui.__dict__.get("_gui_tasks", {})
    finally:
        release.set()


@pytest.mark.parametrize("online", [False, True])
def test_open_and_clear_use_selected_cache_and_preserve_recipes_pngs_and_other_roots(gui_workflow, monkeypatch, online):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    selected, other = root / "selected-cache", root / "cache"
    preserved = {}
    for cache in (selected, other):
        cache.mkdir()
        for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
            (cache / name).write_text('{"message":"' + cache.name + '"}\n', encoding="utf-8")
        (cache / "recipes").mkdir()
        (cache / "recipes" / "recipe.json").write_bytes(b'{"authoritative":true}')
        (cache / "sprite.png").write_bytes(b"PNG-fixture-bytes")
        (cache / "last_combine_failure.json").write_bytes(b'{"keepFailure":true}')
        for path in cache.rglob("*"):
            if path.is_file() and (cache == other or path.name not in {"events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"}):
                preserved[path] = path.read_bytes()
    opened, requests = [], []
    monkeypatch.setattr(settings_trace_state.webbrowser, "open", lambda uri: opened.append(uri))
    monkeypatch.setattr(settings_trace_state.os, "startfile", lambda path: opened.append(Path(path).as_uri()), raising=False)
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)

    def read_gui_json(url, **kwargs):
        requests.append(str(url))
        assert online and "/trace_clear" in str(url)
        for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
            settings_trace_state.trace_tools.clear_ndjson(selected / name)
        return {"ok": True, "cleared": [str(selected / name) for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")]}

    def health(*args, **kwargs):
        if not online:
            raise ConnectionRefusedError("offline fixture")
        return {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "cacheDir": str(selected)}

    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    monkeypatch.setattr(gui, "refresh_trace", lambda: None)
    monkeypatch.setattr(gui, "_read_gui_json", read_gui_json)
    gui.open_cache_folder()
    assert opened == [selected.as_uri()], "Open cache ignored selected launch root"
    gui.clear_trace_files()
    gui.drain_until(lambda: all((selected / name).read_bytes() == b"" for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")))
    assert all(path.read_bytes() == data for path, data in preserved.items())
    assert len(requests) == (1 if online else 0)


@contextmanager
def _gui_loopback_http(responses):
    """Synthetic diagnostic HTTP only, not the application's real server."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            response = responses.get(urlsplit(self.path).path, (404, {"ok": False}))
            if callable(response):
                response = response(self.path)
            code, value = response
            body = json.dumps(value).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


@pytest.mark.parametrize("identity", ["foreign-health", "unknown-health", "foreign-trace", "changed-pid", "matching"])
def test_real_trace_http_checks_both_health_and_trace_identity_off_ui_thread(gui_workflow, monkeypatch, identity):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    cache = root / "selected-cache"
    cache.mkdir()
    (cache / "events.ndjson").write_text('{"message":"local-fixture"}\n', encoding="utf-8")
    pid = os.getpid() + 1000
    health = {"ok": True, "serverRoot": str(root), "pid": pid}
    trace = {"ok": True, "serverRoot": str(root), "pid": pid, "cacheDir": "online-cache", "events": [{"message": "online-fixture"}]}
    if identity == "foreign-health":
        health["serverRoot"] = str(root.parent / "foreign")
    elif identity == "unknown-health":
        health.pop("serverRoot")
    elif identity == "foreign-trace":
        trace["serverRoot"] = str(root.parent / "foreign")
    elif identity == "changed-pid":
        trace["pid"] = pid + 1
    with _gui_loopback_http({"/health": (200, health), "/trace.json": (200, trace)}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.refresh_trace()
        gui.drain_until(lambda: "summary" in gui.rendered)
    if identity == "matching":
        assert "online-fixture" in gui.rendered["events"]
        assert "local" not in gui.trace_status_var.get().lower()
    else:
        assert "local-fixture" in gui.rendered["events"], "accepted a foreign or replaced server's trace"
        assert "online-fixture" not in gui.rendered["events"]
    assert len(requests) == (1 if identity in {"foreign-health", "unknown-health"} else 2)


def test_trace_clear_refuses_unknown_root_without_http_or_local_mutation(gui_workflow, monkeypatch):
    gui, root, _config = gui_workflow
    cache = root / "cache"
    cache.mkdir()
    trace_file = cache / "events.ndjson"
    trace_file.write_bytes(b'{"preserve":true}\n')
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    with _gui_loopback_http({"/health": (200, {"ok": True, "pid": os.getpid() + 1000}),
                            "/trace_clear": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.clear_trace_files()
        gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ["/health"], "cleared an unverified server"
    assert trace_file.read_bytes() == b'{"preserve":true}\n'
    assert "refused" in gui.trace_status_var.get().lower()


@pytest.mark.parametrize("activity", [
    {"active": 1, "waiting": 0, "accepting": True},
    {"active": 0, "waiting": 2, "accepting": True},
    {"active": 0, "waiting": 0, "accepting": False},
    None,
    {"active": "0", "waiting": 0, "accepting": True},
])
def test_safe_restart_does_not_save_shutdown_kill_or_spawn_busy_or_unknown_server(gui_workflow, monkeypatch, activity):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_IMAGE_BACKEND=off\n")
    original = config.read_bytes()
    actions = []

    class Owned:
        pid = os.getpid() + 1000
        def poll(self):
            return None
        def terminate(self):
            actions.append("terminate")
        def kill(self):
            actions.append("kill")
        def wait(self, **kwargs):
            return 0

    gui.proc = Owned()
    snap = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid}
    if activity is not None:
        snap["generationActivity"] = activity
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: snap)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn"))
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda *a, **k: actions.append("shutdown") or True)
    monkeypatch.setattr(gui, "_delayed_health_check", lambda *a, **k: None)
    monkeypatch.setattr(controls.messagebox, "showwarning", lambda *a, **k: None)
    gui.start_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert not actions, "safe restart interrupted occupied or unverifiable generation"
    assert config.read_bytes() == original, "busy restart saved before admission guard"
    assert any(word in gui.status_var.get().lower() for word in ("busy", "unknown", "accepting", "refused"))


@pytest.mark.parametrize("shutdown_code", [409, 200])
def test_safe_restart_uses_atomic_shutdown_and_never_falls_through_to_process_kill(gui_workflow, monkeypatch, shutdown_code):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_CACHE_DIR=saved-cache\nINFINI_IMAGE_BACKEND=off\n")
    original = config.read_bytes()
    actions = []
    pid = os.getpid() + 1000

    class Owned:
        def __init__(self):
            self.pid = pid
        def poll(self):
            return None
        def terminate(self):
            actions.append("terminate")
        def kill(self):
            actions.append("kill")
        def wait(self, **kwargs):
            return 0

    gui.proc = Owned()
    idle = {"ok": True, "serverRoot": str(root), "pid": pid,
            "effectiveConfig": gui._proposed_effective_config(),
            "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    stopped = [False]

    def health(_path):
        return (503, {"ok": False}) if stopped[0] else (200, idle)

    def shutdown(path):
        if shutdown_code == 409:
            return 409, {"ok": False, "status": "generator_busy", "generationActivity": {"active": 1, "waiting": 0, "accepting": True}}
        stopped[0] = True
        return 200, {"ok": True}

    # This test owns only acknowledgement -> launch, not a real helper lifetime.
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(gui, "_delayed_health_check", lambda *a, **k: None)
    monkeypatch.setattr(controls.messagebox, "showwarning", lambda *a, **k: None)
    def capture_launch(cmd, **kwargs):
        # Never retain inherited credentials in pytest assertion diagnostics.
        safe_env = {key: kwargs["env"].get(key) for key in ("INFINI_CACHE_DIR", "INFINI_IMAGE_BACKEND")}
        actions.append((cmd, {"cwd": kwargs["cwd"], "env": safe_env}))
        return Owned()

    monkeypatch.setattr(controls.subprocess, "Popen", capture_launch)
    monkeypatch.setenv("INFINI_CACHE_DIR", "inherited-cache")
    with _gui_loopback_http({"/health": health, "/shutdown": shutdown}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.start_server()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}), timeout=8)
    assert "terminate" not in actions and "kill" not in actions, "safe path bypassed atomic server refusal"
    assert any(path.startswith("/shutdown") for path in requests), "idle health alone is not an atomic restart guard"
    assert not any("force=1" in path for path in requests)
    if shutdown_code == 409:
        assert not actions
        assert config.read_bytes() == original
        assert "busy" in gui.status_var.get().lower()
    else:
        assert len(actions) == 1
        cmd, kwargs = actions[0]
        assert cmd[-1] == str(root / "server.py")
        assert kwargs["cwd"] == str(root)
        assert kwargs["env"]["INFINI_CACHE_DIR"] == "saved-cache"
        assert kwargs["env"]["INFINI_IMAGE_BACKEND"] == "off"
        assert "запущен" in gui.status_var.get()


@pytest.mark.parametrize("identity", ["foreign-root", "unknown-root", "caller-pid", "invalid-pid", "unrelated-service"])
def test_safe_restart_refuses_unverified_identity_before_shutdown_or_save(gui_workflow, monkeypatch, identity):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_IMAGE_BACKEND=off\n")
    original = config.read_bytes()
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    if identity == "foreign-root":
        snap["serverRoot"] = str(root.parent / "foreign")
    elif identity == "unknown-root":
        snap.pop("serverRoot")
    elif identity == "caller-pid":
        snap["pid"] = os.getpid()
    elif identity == "invalid-pid":
        snap["pid"] = "123"
    else:
        snap = {"ok": True, "service": "unrelated"}
    actions = []
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn"))
    with _gui_loopback_http({"/health": (200, snap), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.start_server()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ["/health"], "safe restart targeted an unverified/foreign/caller process"
    assert not actions
    assert config.read_bytes() == original


@pytest.mark.parametrize("confirmed,identity", [(False, "matching"), (True, "matching"), (True, "foreign"), (True, "caller")])
def test_force_restart_requires_confirmation_and_still_checks_root_and_caller_pid(gui_workflow, monkeypatch, confirmed, identity):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_IMAGE_BACKEND=off\n")
    original = config.read_bytes()
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "effectiveConfig": gui._proposed_effective_config(),
            "generationActivity": {"active": 1, "waiting": 1, "accepting": True}}
    if identity == "foreign":
        snap["serverRoot"] = str(root.parent / "foreign")
    if identity == "caller":
        snap["pid"] = os.getpid()
    confirmations, actions = [], []

    def ask(*args, **kwargs):
        assert threading.get_ident() == gui.owner
        confirmations.append(args)
        return confirmed

    monkeypatch.setattr(controls.messagebox, "askyesno", ask)
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn"))
    with _gui_loopback_http({"/health": (200, snap), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        force = getattr(gui, "force_restart_server", None)
        assert callable(force), "Force restart is not a separate explicit action"
        force()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert len(confirmations) == 1
    if confirmed and identity == "matching":
        assert requests == ["/health", "/shutdown?force=1"]
        assert actions == ["spawn"]
    else:
        assert requests == (["/health"] if confirmed else [])
        assert not actions
        assert config.read_bytes() == original


def test_stop_server_is_also_busy_aware_without_direct_terminate(gui_workflow, monkeypatch):
    gui, root, _config = gui_workflow
    actions = []
    class Owned:
        pid = os.getpid() + 1000
        def poll(self):
            return None
        def terminate(self):
            actions.append("terminate")
    gui.proc = Owned()
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: {
        "ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
        "generationActivity": {"active": 1, "waiting": 0, "accepting": True}})
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda *a, **k: actions.append("shutdown") or (True, ""))
    gui.stop_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert not actions
    assert "busy" in gui.status_var.get().lower()


class _TrackedUiVar(_UiVar):
    def __init__(self, value=""):
        super().__init__(value)
        self.callbacks = []

    def trace_add(self, mode, callback):
        self.callbacks.append(callback)

    def set(self, value):
        super().set(value)
        for callback in self.callbacks:
            callback()


def test_closed_port_guard_allows_native_windows_refusal_latency(gui_workflow, monkeypatch):
    import urllib.error
    gui, _root, _config = gui_workflow
    launches = []
    def delayed_refusal(timeout, **kwargs):
        if timeout <= 2.05:
            raise urllib.error.URLError(TimeoutError())
        raise urllib.error.URLError(ConnectionRefusedError(10061, "closed port"))
    monkeypatch.setattr(gui, "_fetch_health_snapshot", delayed_refusal)
    monkeypatch.setattr(gui, "_start_server_after_guard", lambda: launches.append(True))
    gui.start_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert launches == [True]


def test_shutdown_wait_allows_native_windows_refusal_latency(gui_workflow, monkeypatch):
    import urllib.error
    gui, _root, _config = gui_workflow
    def delayed_refusal(timeout, **kwargs):
        if timeout <= 2.05:
            raise urllib.error.URLError(TimeoutError())
        raise urllib.error.URLError(ConnectionRefusedError(10061, "closed port"))
    monkeypatch.setattr(gui, "_fetch_health_snapshot", delayed_refusal)
    assert gui._wait_until_helper_stops(timeout=4, base_url="http://127.0.0.1:5055") is True


def test_setting_edits_create_custom_without_writing_saved_config(gui_workflow):
    gui, _root, config = gui_workflow
    config.write_text("INFINI_CODEX_IMAGE_QUALITY=medium\n", encoding="utf-8")
    before = config.read_bytes()
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"] = _TrackedUiVar("medium")
    gui.preset_var = _UiVar("Мой: Обычный")
    gui._install_profile_tracking()
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"].set("high")
    assert gui.preset_var.get() == "Custom"
    assert config.read_bytes() == before
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"].set("medium")
    assert gui.preset_var.get() == "Мой: Обычный"


def test_gui_saves_named_profile_separately_and_restores_exact_settings(gui_workflow, monkeypatch):
    from infini_local.desktop.settings_env import load_user_presets
    from infini_local.desktop import settings_gui_trace_state
    gui, _root, config = gui_workflow
    config.write_text("INFINI_MANUAL_KNOB=disk\n", encoding="utf-8")
    before = config.read_bytes()
    gui.data["INFINI_MANUAL_KNOB"] = "keep"
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"] = _TrackedUiVar("high")
    gui.vars["INFINI_LLM_REASONING_MAX_TOKENS"] = _TrackedUiVar("7500")
    gui.vars["INFINI_OPENROUTER_API_KEY"] = _TrackedUiVar("test-only-credential")
    gui.preset_var = _UiVar("Custom")
    gui.user_presets = {}
    from types import SimpleNamespace
    gui.preset_combo = SimpleNamespace(configure=lambda **kwargs: None)
    gui._refresh_visibility = lambda: None
    gui._install_profile_tracking()
    monkeypatch.setattr(settings_gui_trace_state.simpledialog, "askstring", lambda *args, **kwargs: "Мой GPU")
    gui.save_profile_as()
    path = config.with_name("gui_user_presets.json")
    profiles = load_user_presets(path)
    assert gui.preset_var.get() == "Мой: Мой GPU"
    assert profiles["Мой GPU"]["INFINI_LLM_REASONING_MAX_TOKENS"] == "7500"
    assert profiles["Мой GPU"]["INFINI_MANUAL_KNOB"] == "keep"
    assert "INFINI_OPENROUTER_API_KEY" not in profiles["Мой GPU"]
    assert config.read_bytes() == before
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"].set("low")
    assert gui.preset_var.get() == "Custom"
    gui.preset_var.set("Мой: Мой GPU")
    gui.apply_preset()
    assert gui.vars["INFINI_CODEX_IMAGE_QUALITY"].get() == "high"
    assert gui.vars["INFINI_OPENROUTER_API_KEY"].get() == "test-only-credential"
    assert gui.preset_var.get() == "Мой: Мой GPU"
    assert config.read_bytes() == before
    assert gui.collect()["INFINI_MANUAL_KNOB"] == "keep"
    assert settings_gui.SettingsGui._pipeline_preset_from_config(
        {**profiles["Мой GPU"], "INFINI_GUI_PIPELINE_PRESET": "Мой: Мой GPU"}, profiles
    ) == "Мой: Мой GPU"


def test_simple_view_keeps_active_basics_and_preserves_hidden_values():
    from types import SimpleNamespace
    calls = {}
    fields = {key: [object()] for key in ("INFINI_CODEX_IMAGE_MODEL", "INFINI_SDCPP_MODEL", "INFINI_LLM_REASONING_MAX_TOKENS")}
    gui = SimpleNamespace(advanced_var=_UiVar(False), field_widgets=fields, field_hint_labels={},
                          field_disabled_reasons={"INFINI_SDCPP_MODEL": "Другой backend"}, _ui_sections=[])
    gui._set_packed_visible = lambda widget, visible: calls.update({widget: visible})
    settings_gui.SettingsGui._apply_view_mode(gui)
    assert calls[fields["INFINI_CODEX_IMAGE_MODEL"][0]] is True
    assert calls[fields["INFINI_SDCPP_MODEL"][0]] is False
    assert calls[fields["INFINI_LLM_REASONING_MAX_TOKENS"][0]] is False
    gui.advanced_var.set(True)
    settings_gui.SettingsGui._apply_view_mode(gui)
    assert all(calls[row[0]] for row in fields.values())


def test_codex_settings_do_not_display_an_unrelated_flux_preset():
    data = dict(settings_schema.DEFAULTS)
    data.update({"INFINI_GUI_PIPELINE_PRESET": "OpenAI-compatible + FLUX.2 Klein 4B hybrid",
                 "INFINI_LLM_PROVIDER": "openai_codex", "INFINI_IMAGE_BACKEND": "openai_codex"})
    assert settings_gui.SettingsGui._pipeline_preset_from_config(data) == "Custom"


def test_static_hover_help_does_not_replace_runtime_status(monkeypatch):
    from infini_local.desktop import settings_gui_ui as ui
    bindings = []
    class Widget:
        def bind(self, *args, **kwargs):
            bindings.append((args, kwargs))
    monkeypatch.setattr(ui, "ToolTip", lambda *args: None)
    gui = object.__new__(settings_gui.SettingsGui)
    gui.status_var = _UiVar("Server failed: useful diagnostic")
    gui._attach_static_help(Widget(), "Profile help\n" + "x" * 2000)
    for args, _kwargs in bindings:
        if args[0] == "<Enter>":
            args[1](None)
    assert gui.status_var.get() == "Server failed: useful diagnostic"


def test_loopback_gui_health_bypasses_system_proxy(monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    import urllib.request
    with _gui_loopback_http({"/health": (200, {"ok": True})}) as (base, requests):
        with _gui_loopback_http({"/health": (200, {"route": "proxy"})}) as (proxy, proxy_requests):
            monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": proxy})
            monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
            assert controls.SettingsGuiServerControlsMixin._read_gui_json(base + "/health", 2) == {"ok": True}
            assert requests == ["/health"]
            assert not proxy_requests
            assert controls.SettingsGuiServerControlsMixin._read_gui_json("http://provider.invalid/health", 2) == {"route": "proxy"}
            assert proxy_requests == ["http://provider.invalid/health"]


@pytest.mark.parametrize("owned", [False, True])
def test_start_on_refused_port_only_launches_when_no_owned_process_is_running(gui_workflow, monkeypatch, owned):
    from infini_local.desktop import settings_gui_server_controls as controls
    import socket
    gui, root, _config = gui_workflow
    calls = []
    class Owned:
        pid = os.getpid() + 1000
        def poll(self):
            return None
    gui.proc = Owned() if owned else None
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: calls.append("spawn") or Owned())
    # Reserve then close one ephemeral loopback port; no application is started.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    gui.vars["INFINI_PORT"] = _UiVar(str(port))
    gui.start_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert calls == ([] if owned else ["spawn"])


def test_overlapping_server_actions_do_not_queue_extra_shutdowns_or_block_ui(gui_workflow, monkeypatch):
    gui, root, _config = gui_workflow
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    reads = []
    def health(*args, **kwargs):
        reads.append(kwargs["base_url"])
        entered.set()
        assert release.wait(3)
        finished.set()
        return {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
                "generationActivity": {"active": 1, "waiting": 0, "accepting": True}}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    try:
        before = time.monotonic()
        gui.start_server()
        assert time.monotonic() - before < 0.2
        assert entered.wait(1)
        for _ in range(25):
            gui.start_server()
        release.set()
        assert finished.wait(1)
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
        assert len(reads) == 1, "repeated Start queued another restart after the initial guard"
        assert not gui.jobs
    finally:
        release.set()


def test_shutdown_wait_does_not_treat_http_error_or_timeout_as_port_free(gui_workflow, monkeypatch):
    gui, _root, _config = gui_workflow
    with _gui_loopback_http({"/health": (503, {"ok": False})}) as (base, requests):
        assert gui._wait_until_helper_stops(timeout=0.1, base_url=base) is False
        assert requests == ["/health"]
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    assert gui._wait_until_helper_stops(timeout=0.1, base_url="http://127.0.0.1:1") is False
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    assert gui._wait_until_helper_stops(timeout=0.1, base_url="http://127.0.0.1:1") is True


def _configure_applied_fixture(gui, root, config):
    config.write_text("\n".join((
        "INFINI_CACHE_DIR=selected-cache", "INFINI_WORLD_RECIPES_DIR=selected-worlds",
        "INFINI_IMAGE_BACKEND=off", "INFINI_LLM_PROVIDER=openrouter",
        "INFINI_OPENROUTER_MODEL=Provider/Model", "INFINI_OPENROUTER_PROVIDER=Exact-Slug",
        "INFINI_SDCPP_SERVER_AUTOSTART=0", "INFINI_OPENROUTER_API_KEY=FAKE-SAVED-SECRET-CANARY",
    )) + "\n", encoding="utf-8")
    return {"cacheDir": str((root / "selected-cache").resolve()),
            "worldRecipesDir": str((root / "selected-worlds").resolve()),
            "imageBackend": "off", "llmProvider": "openrouter", "llmModel": "Provider/Model",
            "openrouterProvider": "Exact-Slug", "sdcppAutostart": False}


def test_applied_config_health_is_async_partial_nonsecret_and_main_thread_only(gui_workflow, monkeypatch):
    gui, root, config = gui_workflow
    effective = _configure_applied_fixture(gui, root, config)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def health(*args, **kwargs):
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        return {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
                "effectiveConfig": {**effective, "unrelatedSecret": "FAKE-HEALTH-SECRET-CANARY"},
                "llmAuth": {"secret": "FAKE-AUTH-SECRET-CANARY"}}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    try:
        before = time.monotonic()
        gui._delayed_health_check()
        assert time.monotonic() - before < 0.2, "health confirmation blocked the UI callback"
        assert entered.wait(1)
        release.set()
        gui.drain_until(lambda: "matches" in gui.applied_config_var.get().lower())
        assert calls == [calls[0]] and calls[0] != gui.owner
        feedback = gui.applied_config_var.get()
        assert "partial" in feedback.lower()
        assert "secret" in feedback.lower()
        assert "CANARY" not in feedback
        assert "CANARY" not in gui.status_var.get()
        assert "CANARY" not in repr(gui.__dict__.get("_applied_config_ack", {}))
    finally:
        release.set()


def test_gui_has_no_legacy_pid_kill_fallback_reachable_from_restart():
    # Old helper cleanup itself could still bypass admission/identity fencing.
    controls_source = GUI_PATH.with_name("settings_gui_server_controls.py").read_text(encoding="utf-8")
    assert "def _cleanup_old_helper_servers_before_start" not in controls_source
    assert "def _terminate_pid" not in controls_source
    assert "self.proc.terminate(" not in controls_source
    assert "self.proc.kill(" not in controls_source


@pytest.mark.parametrize("changed", ["pin-after-save", "pin-during-health", "missing-projection", "foreign-root"])
def test_applied_feedback_never_confirms_unsaved_or_unacknowledged_launch_changes(gui_workflow, monkeypatch, changed):
    gui, root, config = gui_workflow
    effective = _configure_applied_fixture(gui, root, config)
    entered, release = threading.Event(), threading.Event()
    def health(*args, **kwargs):
        entered.set()
        if changed == "pin-during-health":
            assert release.wait(2)
        snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "effectiveConfig": effective}
        if changed == "missing-projection":
            snap.pop("effectiveConfig")
        if changed == "foreign-root":
            snap["serverRoot"] = str(root.parent / "foreign")
        return snap
    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    try:
        gui._delayed_health_check()
        assert entered.wait(1)
        if changed == "pin-during-health":
            gui.vars["INFINI_OPENROUTER_PROVIDER"] = _UiVar("exact-slug")  # case is significant
        release.set()
        gui.drain_until(lambda: "health-config" not in gui.__dict__.get("_gui_tasks", {}))
        if changed == "pin-after-save":
            assert "matches" in gui.applied_config_var.get().lower()
            gui.vars["INFINI_OPENROUTER_PROVIDER"] = _UiVar("exact-slug")
            gui.save()
        text = gui.applied_config_var.get().lower()
        assert "matches" not in text, "stale health acknowledgement hid a new launch mismatch"
        if changed.startswith("pin"):
            assert "openrouterprovider" in text
            assert "restart" in text
        else:
            assert "unconfirmed" in text
        assert "partial" in text
        assert "CANARY" not in gui.applied_config_var.get()
    finally:
        release.set()


@pytest.mark.parametrize("linked_name", ["prompt_trace.ndjson", "prompt_trace.ndjson.lock"])
def test_offline_clear_refuses_symlinked_trace_or_lock_before_touching_any_cache_bytes(gui_workflow, monkeypatch, linked_name):
    gui, root, _config = gui_workflow
    cache = root / "cache"
    cache.mkdir()
    for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
        (cache / name).write_bytes(b'{"keep":true}\n')
    foreign = root.parent / "foreign-sprite.png"
    foreign.write_bytes(b"preserved-foreign-PNG")
    linked = cache / linked_name
    linked.unlink(missing_ok=True)
    linked.symlink_to(foreign)
    originals = {path: path.read_bytes() for path in (foreign, cache / "events.ndjson", cache / "pipeline_trace.ndjson")}
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(gui, "refresh_trace", lambda: None)
    gui.clear_trace_files()
    gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert all(path.read_bytes() == value for path, value in originals.items()), "clear followed a trace/lock symlink or partially truncated the selected cache"
    assert "refused" in gui.trace_status_var.get().lower()


@pytest.mark.parametrize("identity", ["missing-pid", "invalid-pid", "caller-pid", "different-owned-pid"])
def test_applied_config_never_acknowledges_an_unverified_or_other_owned_process(gui_workflow, monkeypatch, identity):
    gui, root, config = gui_workflow
    effective = _configure_applied_fixture(gui, root, config)
    pid = os.getpid() + 1000
    class Owned:
        def __init__(self):
            self.pid = pid
        def poll(self):
            return None
    gui.proc = Owned()
    snap = {"ok": True, "serverRoot": str(root), "pid": pid, "effectiveConfig": effective}
    if identity == "missing-pid":
        snap.pop("pid")
    elif identity == "invalid-pid":
        snap["pid"] = str(pid)
    elif identity == "caller-pid":
        snap["pid"] = os.getpid()
    else:
        snap["pid"] = pid + 1
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: snap)
    gui._delayed_health_check()
    gui.drain_until(lambda: "health-config" not in gui.__dict__.get("_gui_tasks", {}))
    assert "unconfirmed" in gui.applied_config_var.get().lower()
    assert gui.__dict__.get("_applied_config_ack") is None


def test_successful_safe_stop_retires_runtime_config_ack(gui_workflow, monkeypatch):
    gui, root, config = gui_workflow
    effective = _configure_applied_fixture(gui, root, config)
    gui._applied_config_ack = {"baseUrl": gui._server_base_url(), "pid": os.getpid() + 1000, "effectiveConfig": effective}
    gui._update_applied_config_feedback()
    assert "matches" in gui.applied_config_var.get().lower()
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "effectiveConfig": effective,
              "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: health)
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda *a, **k: (True, ""))
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    gui.stop_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert gui.__dict__.get("_applied_config_ack") is None
    assert "matches" not in gui.applied_config_var.get().lower()
    assert "stopped" in gui.status_var.get().lower()


@pytest.mark.parametrize("secret,model,expected", [("", "Provider/Model", "local"), ("FAKE-INFER-CANARY", "auto", "local"), ("FAKE-INFER-CANARY", "Provider/Model", "openrouter")])
def test_gui_projection_handles_implicit_main_provider_without_retaining_secret(gui_workflow, monkeypatch, secret, model, expected):
    gui, _root, config = gui_workflow
    config.write_text(f"INFINI_LLM_PROVIDER=\nINFINI_OPENROUTER_API_KEY={secret}\nINFINI_OPENROUTER_MODEL={model}\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    projection = gui._proposed_effective_config()
    assert projection["llmProvider"] == expected
    assert "CANARY" not in repr(projection)


@pytest.mark.parametrize("provider,expected", [("", "local"), ("or", "openrouter"), ("openai-compat", "openai_compat"), ("lm_studio", "local")])
def test_gui_projection_preserves_declared_provider_aliases_without_false_restart_mismatch(gui_workflow, monkeypatch, provider, expected):
    gui, _root, config = gui_workflow
    config.write_text(f"INFINI_LLM_PROVIDER={provider}\n", encoding="utf-8")
    # Avoid importing runtime config/server or evaluating inherited credentials.
    monkeypatch.delenv("INFINI_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert gui._proposed_effective_config()["llmProvider"] == expected


def test_gui_projection_handles_all_canonical_backend_aliases_without_bootstrap_side_effects(gui_workflow):
    import ast
    gui, _root, config = gui_workflow
    owner = GUI_PATH.parents[1] / "pipelines" / "pipeline_visual_config.py"
    aliases = next(ast.literal_eval(node.value) for node in ast.parse(owner.read_text(encoding="utf-8")).body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "IMAGE_BACKEND_ALIASES" for target in node.targets))
    for raw, canonical in aliases.items():
        config.write_text(f"INFINI_IMAGE_BACKEND={raw}\n", encoding="utf-8")
        assert gui._proposed_effective_config()["imageBackend"] == canonical


@pytest.mark.skipif(os.name == "nt", reason="POSIX roots are case-sensitive; native Windows names are not")
def test_gui_root_identity_preserves_posix_case_and_does_not_accept_different_copy(gui_workflow):
    gui, root, _config = gui_workflow
    assert gui._health_matches_this_gui({"serverRoot": str(root)})
    assert not gui._health_matches_this_gui({"serverRoot": str(root.with_name(root.name.swapcase()))})
    assert gui._norm_path_for_compare(r"C:\\Copies\\LocalGenerator") == gui._norm_path_for_compare("c:/copies/localgenerator")


@pytest.mark.parametrize("reply", [{"ok": False}, {"ok": True}, {"ok": True, "cleared": []}])
def test_trace_clear_never_reports_partial_server_ack_as_success(gui_workflow, monkeypatch, reply):
    gui, root, _config = gui_workflow
    cache = root / "cache"
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "cacheDir": str(cache)}
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    refreshes = []
    monkeypatch.setattr(gui, "refresh_trace", lambda: refreshes.append(True))
    with _gui_loopback_http({"/health": (200, health), "/trace_clear": (200, reply)}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.clear_trace_files()
        gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ["/health", "/trace_clear"]
    assert "unavailable" in gui.trace_status_var.get().lower()
    assert not refreshes


@pytest.mark.parametrize("health_kind", ["forbidden", "timeout", "foreign", "different-cache"])
def test_trace_clear_refuses_unknown_or_different_live_target_instead_of_local_fallback(gui_workflow, monkeypatch, health_kind):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    cache = root / "selected-cache"
    cache.mkdir()
    trace_file = cache / "events.ndjson"
    trace_file.write_bytes(b'{"preserve":true}\n')
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    if health_kind == "timeout":
        monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
              "cacheDir": str(root / "other-live-cache")}
    if health_kind == "foreign":
        health["serverRoot"] = str(root.parent / "foreign")
    with _gui_loopback_http({"/health": (403 if health_kind == "forbidden" else 200, health),
                            "/trace_clear": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.clear_trace_files()
        gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ([] if health_kind == "timeout" else ["/health"])
    assert trace_file.read_bytes() == b'{"preserve":true}\n', "health refusal/unverifiable liveness cleared local cache"
    assert any(word in gui.trace_status_var.get().lower() for word in ("refused", "unavailable"))


def test_spawn_retires_old_applied_ack_and_schedules_main_loop_health_confirmation(gui_workflow, monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    effective = _configure_applied_fixture(gui, root, config)
    gui._applied_config_ack = {"baseUrl": gui._server_base_url(), "pid": 987654, "effectiveConfig": effective}
    gui._update_applied_config_feedback()
    assert "matches" in gui.applied_config_var.get().lower()
    class Owned:
        pid = os.getpid() + 1000
        def poll(self):
            return None
    calls = []
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: Owned())
    monkeypatch.setattr(gui, "_delayed_health_check", lambda: calls.append(threading.get_ident()))
    gui._start_server_after_guard()
    assert gui.__dict__.get("_applied_config_ack") is None, "new process retained old PID's config acknowledgement"
    assert "matches" not in gui.applied_config_var.get().lower()
    assert gui.jobs, "launch never schedules asynchronous runtime acknowledgement"
    gui.drain_until(lambda: bool(calls))
    assert calls == [gui.owner]


def test_close_cancels_scheduled_post_launch_health_callback(gui_workflow, monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, _root, _config = gui_workflow
    class Owned:
        pid = os.getpid() + 1000
        def poll(self):
            return None
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: Owned())
    gui._start_server_after_guard()
    assert gui.jobs, "native health callback was never scheduled"
    gui.on_close()
    assert not gui.jobs, "post-launch health after callback survived destroyed GUI"


@pytest.mark.parametrize("provider,model_key,model_value,inherited_key,inherited_model,expected_model", [
    ("local", "INFINI_LMSTUDIO_MODEL", "", "OPENAI_MODEL", "Inherited/Model", "Inherited/Model"),
    ("openrouter", "INFINI_OPENROUTER_MODEL", "", "OPENROUTER_MODEL", "Inherited/Model", "Inherited/Model"),
    ("openai_compat", "INFINI_OPENAI_COMPAT_MODEL", "", "OPENAI_MODEL", "Inherited/Model", "Inherited/Model"),
    ("local", "INFINI_LMSTUDIO_MODEL", "", "OPENAI_MODEL", "", "auto"),
    ("openai_codex", "INFINI_CODEX_LLM_MODEL", "", "OPENAI_MODEL", "Inherited/Model", ""),
])
def test_applied_projection_matches_runtime_main_model_fallback_and_inactive_pin(gui_workflow, monkeypatch, provider, model_key, model_value, inherited_key, inherited_model, expected_model):
    gui, _root, config = gui_workflow
    config.write_text(f"INFINI_LLM_PROVIDER={provider}\n{model_key}={model_value}\n"
                      "INFINI_OPENROUTER_PROVIDER=Exact-Slug\nINFINI_IMAGE_BACKEND=off\n", encoding="utf-8")
    monkeypatch.setenv(inherited_key, inherited_model)
    projected = gui._proposed_effective_config()
    assert projected["llmProvider"] == provider
    assert projected["llmModel"] == expected_model
    assert projected["openrouterProvider"] == ("Exact-Slug" if provider == "openrouter" else "")


@pytest.mark.parametrize("projection", [None, {}, {"sdcppAutostart": "0"}])
@pytest.mark.parametrize("force", [False, True])
def test_restart_refuses_unverifiable_applied_projection_without_any_destructive_fallback(gui_workflow, monkeypatch, projection, force):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_IMAGE_BACKEND=off\n")
    original = config.read_bytes()
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    if projection is not None:
        snap["effectiveConfig"] = projection
    actions = []
    monkeypatch.setattr(controls.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn"))
    with _gui_loopback_http({"/health": (200, snap), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        (gui.force_restart_server if force else gui.start_server)()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ["/health"], "unverifiable projection was treated as shutdown admission"
    assert not actions
    assert config.read_bytes() == original
    assert "projection" in gui.status_var.get().lower()


@pytest.mark.parametrize("endpoint", ["health", "shutdown"])
def test_gui_http_enforces_total_deadline_for_continuous_trickle(gui_workflow, endpoint):
    gui, _root, _config = gui_workflow
    class Trickle(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.03)  # every gap is shorter than the socket timeout
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        if endpoint == "health":
            with pytest.raises(TimeoutError):
                gui._fetch_health_snapshot(timeout=0.1, base_url=base_url)
        else:
            assert gui._try_http_shutdown_current_server(timeout=0.1, base_url=base_url)[0] is False
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


@pytest.mark.parametrize("preset_name", list(settings_schema.PRESETS))
def test_gui_base_and_pipeline_presets_make_box_resize_explicit(preset_name):
    resize = {
        "INFINI_SPRITE_DOWNSCALE_FILTER": "box",
        "INFINI_SPRITE_PREMULTIPLIED_RESIZE": "1",
    }
    for key, value in resize.items():
        assert settings_schema.DEFAULTS[key] == value
        assert settings_schema.PRESETS[preset_name][key] == value
    example_path = GUI_PATH.parents[2] / "config.example.env"
    example = settings_env.parse_env(example_path)
    active_lines = example_path.read_text(encoding="utf-8").splitlines()
    assert all(example[key] == value and f"{key}={value}" in active_lines for key, value in resize.items())


class _SpriteGuiHarness(settings_trace_state.SettingsGuiTraceStateMixin):
    """Recording UI seam: real callbacks without Tk, credentials or backend IO."""
    def __init__(self, **overrides):
        self.data = dict(settings_schema.DEFAULTS)
        self.data.update(overrides)
        self.vars = {key: _UiVar(value) for key, value in self.data.items()}
        self.preset_var = _UiVar(next(iter(settings_schema.PRESETS)))
        self.status_var = _UiVar()
        self.radmin_enabled = _UiVar("")
        self.field_widgets = {key: [] for key in self.vars}
        self.extra_arg_buttons = []
        self.sdcpp_debug_buttons = []
        self.field_state = {}

    def _refresh_secret_entries(self):
        pass

    def _set_widgets_enabled(self, _widgets, _enabled):
        pass

    def _set_field_enabled(self, key, enabled, reason=""):
        self.field_state[key] = (enabled, reason)


@pytest.mark.parametrize("filter_name,expected", [("", "box"), ("box", "box"), ("bilinear", "bilinear"), ("bicubic", "bicubic"), ("lanczos", "lanczos")])
def test_apply_pipeline_preserves_explicit_resize_choices(filter_name, expected):
    gui = _SpriteGuiHarness(INFINI_SPRITE_DOWNSCALE_FILTER=filter_name, INFINI_SPRITE_PREMULTIPLIED_RESIZE="0")
    gui.apply_preset()
    assert gui.vars["INFINI_SPRITE_DOWNSCALE_FILTER"].get() == expected
    assert gui.vars["INFINI_SPRITE_PREMULTIPLIED_RESIZE"].get() == "0"


@pytest.mark.parametrize("remove_bg,bg_color,bg_mode,backend,keyer", [
    ("1", "transparent", "sprite_keyer", "openai_codex", False),
    ("0", "transparent", "sprite_keyer", "image_api", False),
    ("0", "magenta", "sprite_keyer", "image_api", False),
    ("1", "magenta", "off", "image_api", False),
    ("1", "magenta", "none", "image_api", False),
    ("1", "magenta", "sprite_keyer", "sdcpp", True),
    ("1", "green", "chroma", "sdcpp", True),
    ("1", "greenscreen", "legacy-keyer", "sdcpp", True),
    ("1", "unsupported-token", "sprite_keyer", "sdcpp", True),
    ("1", "transparent", "sprite_keyer", "off", False),
])
def test_gui_native_alpha_disables_only_local_keyer_controls(remove_bg, bg_color, bg_mode, backend, keyer):
    gui = _SpriteGuiHarness(INFINI_REMOVE_BG=remove_bg, INFINI_BG_COLOR=bg_color,
                            INFINI_BG_REMOVE_MODE=bg_mode, INFINI_IMAGE_BACKEND=backend)
    before = {key: var.get() for key, var in gui.vars.items()}
    gui._refresh_visibility()
    for key in ("INFINI_CHROMA_TOLERANCE", "INFINI_SPRITE_KEYER_SPILL_RADIUS",
                "INFINI_SPRITE_KEYER_RESIDUE_STEPS", "INFINI_SPRITE_CHROMA_DEFRINGE"):
        enabled, reason = gui.field_state[key]
        assert enabled is keyer, key
        if backend != "off" and not keyer:
            assert "Модель запрашивается с alpha; локальный keyer не применяется" in reason
    assert gui.field_state["INFINI_ALPHA_THRESHOLD"][0] is (backend != "off")
    assert gui.field_state["INFINI_BG_COLOR"][0] is (backend != "off")
    assert gui.field_state["INFINI_BG_REMOVE_MODE"][0] is keyer
    if bg_color == "transparent":
        assert gui.field_state["INFINI_REMOVE_BG"][0] is False
    for key in ("INFINI_BG_COLOR", "INFINI_BG_REMOVE_MODE", "INFINI_REMOVE_BG", "INFINI_SPRITE_DOWNSCALE_FILTER"):
        assert gui.vars[key].get() == before[key], "visibility rewrote an explicit choice"


def test_gui_resize_reset_restores_box_without_changing_background():
    gui = _SpriteGuiHarness(INFINI_SPRITE_DOWNSCALE_FILTER="lanczos", INFINI_SPRITE_PREMULTIPLIED_RESIZE="0", INFINI_BG_COLOR="transparent")
    reset = getattr(settings_gui.SettingsGui, "reset_sprite_resize", None)
    assert callable(reset), "GUI has no explicit base resize reset"
    reset(gui)
    assert gui.vars["INFINI_SPRITE_DOWNSCALE_FILTER"].get() == "box"
    assert gui.vars["INFINI_SPRITE_PREMULTIPLIED_RESIZE"].get() == "1"
    assert gui.vars["INFINI_BG_COLOR"].get() == "transparent"
    assert "command=self.reset_sprite_resize" in GUI_SOURCE
    assert "alpha" in settings_schema.FIELD_HELP["INFINI_BG_COLOR"]
    assert "transparent" in settings_schema.FIELD_HELP["INFINI_REMOVE_BG"]
    assert "Модель запрашивается с alpha; локальный keyer не применяется" in settings_schema.OPTION_HELP["INFINI_BG_COLOR"]["transparent"]


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_settings_gui_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
