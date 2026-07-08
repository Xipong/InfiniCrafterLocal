from __future__ import annotations

import os
import json
import re
import socket
import subprocess
import signal
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path, PureWindowsPath
from infini_local.desktop.tk_compat import (
    TKINTER_AVAILABLE,
    TKINTER_IMPORT_ERROR,
    filedialog,
    messagebox,
    tk,
    ttk,
)

from infini_local.desktop.settings_gui_theme import (
    ROOT,
    CONFIG_PATH,
    EXAMPLE_PATH,
    APP_TITLE,
    APP_BG,
    APP_PANEL_BG,
    CARD_BG,
    CARD_MUTED_BG,
    HEADER_BG,
    HEADER_BG_2,
    TEXT_FG,
    MUTED_FG,
    SOFT_FG,
    ACCENT_BG,
    ACCENT_HOVER_BG,
    ACCENT_SOFT_BG,
    ACCENT_FG,
    SUCCESS_BG,
    SUCCESS_SOFT_BG,
    SUCCESS_FG,
    DANGER_BG,
    DANGER_SOFT_BG,
    DANGER_FG,
    WARNING_SOFT_BG,
    WARNING_FG,
    BORDER_FG,
    BORDER_DARK_FG,
)


# Static settings schema/defaults/help live in settings_schema.py; this GUI
# module re-exports them for existing tests and callers.
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    FIELD_HELP,
    FIELD_ORDER,
    OPTION_HELP,
    PRESETS,
    PRESET_HELP,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    SDCPP_EXTRA_FLAG_SPECS,
    SDCPP_EXTRA_PROFILES,
    SDCPP_EXTRA_PROFILE_HELP,
    repair_sdcpp_command_template,
)


from infini_local.desktop.settings_env import (
    parse_env,
    quote_env_value,
    write_env,
)




from infini_local.desktop.settings_widgets import (
    ScrollFrame,
    ToolTip,
)
from infini_local.desktop.settings_sdcpp_args import (
    extra_option_names,
    join_extra_for_gui,
    remove_extra_options,
    split_extra_for_gui,
)

from infini_local.desktop.settings_gui_ui import SettingsGuiUiMixin
from infini_local.desktop.settings_gui_image_args import SettingsGuiImageArgsMixin
from infini_local.desktop.settings_gui_trace_state import SettingsGuiTraceStateMixin
from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin


class SettingsGui(SettingsGuiServerControlsMixin, SettingsGuiTraceStateMixin, SettingsGuiImageArgsMixin, SettingsGuiUiMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x760")
        self.minsize(900, 660)
        self._configure_theme()
        self.proc: subprocess.Popen | None = None
        self.data = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
        self.vars: dict[str, tk.StringVar] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.field_widgets: dict[str, list[tk.Widget]] = {}
        self.field_base_hints: dict[str, str] = {}
        self.field_hint_labels: dict[str, ttk.Label] = {}
        self.field_disabled_reasons: dict[str, str] = {}
        self.extra_arg_buttons: list[tk.Widget] = []
        self.sdcpp_debug_buttons: list[tk.Widget] = []
        self.show_secrets = tk.BooleanVar(value=False)
        self.radmin_enabled = tk.BooleanVar(value=(self.data.get("INFINI_HOST") == "0.0.0.0" or bool(self.data.get("INFINI_ASSET_PUBLIC_BASE_URL"))))
        self.status_var = tk.StringVar(value="Готово. Выбери pipeline preset, отдельно включи Radmin/LAN если нужен, нажми Save и Start.")
        self._build_ui()
        self._install_global_edit_shortcuts()
        self._refresh_visibility()

    def _var(self, key: str) -> tk.StringVar:
        v = tk.StringVar(value=self.data.get(key, DEFAULTS.get(key, "")))
        self.vars[key] = v
        return v

    @staticmethod
    def _pipeline_preset_from_config(data: dict[str, str]) -> str:
        saved = str(data.get("INFINI_GUI_PIPELINE_PRESET", "") or "").strip()
        if saved in PRESETS:
            return saved
        provider = str(data.get("INFINI_LLM_PROVIDER", "") or "").strip().lower()
        backend = str(data.get("INFINI_IMAGE_BACKEND", "") or "").strip().lower()
        if provider == "local" and backend == "sdcpp":
            return "Локалка: LM Studio + local Z-Image/sd.cpp"
        if provider == "openrouter" and backend == "sdcpp":
            return "OpenRouter + local Z-Image/sd.cpp"
        if provider == "openrouter" and backend == "image_api":
            return "OpenRouter + Image API"
        if provider == "openrouter" and backend in {"off", "none", "disabled", "0"}:
            return "API LLM only: без картинок"

        best_name = list(PRESETS)[0]
        best_score = -1
        for name, preset in PRESETS.items():
            score = sum(1 for key, value in preset.items() if str(data.get(key, "")).strip() == str(value).strip())
            if score > best_score:
                best_name, best_score = name, score
        return best_name








def main():
    app = SettingsGui()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
