from __future__ import annotations

import importlib
import subprocess

tk_compat = importlib.import_module("infini_local.desktop.tk_compat")

tk = tk_compat.tk
ttk = tk_compat.ttk

from infini_local.desktop.settings_gui_theme import (
    CONFIG_PATH,
    EXAMPLE_PATH,
    APP_TITLE,
)


from infini_local.desktop.settings_schema import (
    DEFAULTS,
    PRESETS,
)


from infini_local.desktop.settings_env import parse_env

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
