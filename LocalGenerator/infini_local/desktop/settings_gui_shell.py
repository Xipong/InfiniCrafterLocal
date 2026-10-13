"""Sidebar, compact header and persistent page workspace. Page indices stay compatible."""
from __future__ import annotations

from dataclasses import dataclass
from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_widgets import ScrollFrame
from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX
from infini_local.desktop.settings_schema import PRESETS
from infini_local.desktop.settings_gui_theme import (
    APP_BG, CARD_BG, CARD_MUTED_BG, HEADER_BG, TEXT_FG, MUTED_FG,
    ACCENT_BG, ACCENT_SOFT_BG, BORDER_FG,
)


@dataclass(frozen=True)
class PageSpec:
    key: str
    index: int
    title: str
    subtitle: str
    group: str = "configure"


PAGE_SPECS = (
    PageSpec("operate", 0, "Запуск и состояние", "Твоё рабочее место", "operate"),
    PageSpec("providers", 1, "Текстовые модели", "Источник идей, свойств и описания предмета"),
    PageSpec("models", 2, "Параллельный крафт", "Дополнительные модели и независимые окна генерации"),
    PageSpec("images", 3, "Изображения", "Источник картинок и параметры генерации"),
    PageSpec("sprites", 4, "Обработка спрайтов", "Фон, края, уменьшение и палитра"),
    PageSpec("diagnostics", 5, "Диагностика", "Состояние сервера и подробный журнал", "operate"),
    PageSpec("multiplayer", 6, "Игра с друзьями", "Сетевое подключение и передача готовых предметов"),
    PageSpec("configure", 7, "Профили и сервер", "Профили настроек, адрес сервера и параметры крафта"),
)


class SettingsShellMixin:
    page_specs = PAGE_SPECS

    def navigate(self, key):
        spec = next((page for page in self.page_specs if page.key == key), None)
        if spec is None:
            raise ValueError(f"Unknown desktop page: {key}")
        self._select_settings_tab(spec.index)

    def _select_settings_tab(self, index):
        # Public legacy index path remains valid for Codex account/catalog tests.
        try:
            self.tabs.select(index)
        except (AttributeError, RuntimeError, TypeError, tk.TclError):
            return
        self._paint_tab_navigation()
        if index not in (1, 3) or index in self.__dict__.get("_codex_auto_ping_tabs", set()):
            return
        from infini_local.services.codex_auth import auth_status
        if not auth_status().get("authenticated"):
            return
        field = "INFINI_LLM_PROVIDER" if index == 1 else "INFINI_IMAGE_BACKEND"
        if self._value(field) != "openai_codex":
            return
        seen = self.__dict__.setdefault("_codex_auto_ping_tabs", set())
        seen.add(index)
        if index == 1:
            self.refresh_codex_text_catalog()
        else:
            self.ping_codex_image_account()

    def _paint_tab_navigation(self):
        try:
            selected = self.tabs.index(self.tabs.select())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            selected = 0
        for index, button in enumerate(self.__dict__.get("tab_nav_buttons", [])):
            if button is None:
                continue
            active = index == selected
            button.configure(bg=ACCENT_SOFT_BG if active else HEADER_BG,
                fg=ACCENT_BG if active else MUTED_FG,
                activebackground=ACCENT_SOFT_BG, activeforeground=TEXT_FG,
                font=(self.__dict__.get("ui_font_family", "Segoe UI"), 10, "bold" if active else "normal"))
            self.nav_rails[index].configure(bg=ACCENT_BG if active else HEADER_BG)
        title = self.__dict__.get("page_title_var")
        if title is not None:
            spec = self.page_specs[selected]
            title.set(spec.title)
            self.page_subtitle_var.set(spec.subtitle)
            self.page_mode_var.set("РАБОТА" if spec.group == "operate" else "НАСТРОЙКА")
            for name in ("view_options", "workspace_toolbar"):
                widget = self.__dict__.get(name)
                if widget is not None:
                    self._set_packed_visible(widget, spec.key != "operate")

    def _build_tab_navigation(self, parent):
        self.tab_nav_buttons = [None] * len(self.page_specs)
        self.nav_rails = {}
        for heading, keys in (
            ("РАБОТА", ("operate", "diagnostics")),
            ("НАСТРОЙКА", ("providers", "images", "sprites", "models", "multiplayer", "configure")),
        ):
            self._label(parent, heading, size=9, fg=MUTED_FG, bold=True).pack(anchor="w", padx=18, pady=(22, 8))
            for key in keys:
                spec = next(page for page in self.page_specs if page.key == key)
                line = self._surface(parent, bg=HEADER_BG)
                line.pack(fill="x", padx=(10, 8), pady=2)
                rail = tk.Frame(line, width=3, bg=HEADER_BG)
                rail.pack(side="left", fill="y")
                button = tk.Button(line, text=spec.title, command=lambda key=key: self.navigate(key),
                    bg=HEADER_BG, fg=MUTED_FG, activebackground=ACCENT_SOFT_BG, activeforeground=TEXT_FG,
                    anchor="w", relief="flat", bd=0, padx=12, pady=10, highlightthickness=0,
                    font=(self.__dict__.get("ui_font_family", "Segoe UI"), 10), cursor="hand2")
                button.pack(side="left", fill="x", expand=True)
                self.tab_nav_buttons[spec.index] = button
                self.nav_rails[spec.index] = rail
                button.bind("<Return>", lambda _e, key=key: self.navigate(key), add="+")
        return parent

    def _build_profiles(self, parent):
        box = self._card(parent, "Профиль генерации", "Применение профиля меняет форму. Запись на диск — отдельное действие; ключи не входят в пользовательские профили.")
        row = self._surface(box)
        row.pack(fill="x", padx=10, pady=7)
        self.preset_var = tk.StringVar(value=self._pipeline_preset_from_config(self.data, self.user_presets))
        self.preset_combo = ttk.Combobox(row, textvariable=self.preset_var,
            values=[CUSTOM_PRESET, *PRESETS, *(USER_PRESET_PREFIX + name for name in self.user_presets)],
            state="readonly", width=44)
        self.preset_combo.pack(fill="x", expand=True)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda _e: self._show_preset_help(), add="+")
        self._attach_static_help(self.preset_combo, lambda: self._preset_help_text())
        bar = self._surface(box)
        bar.pack(fill="x", padx=10, pady=7)
        self._modern_button(bar, "Применить профиль", self.apply_preset, "soft").pack(side="left", padx=(0, 8))
        self._modern_button(bar, "Сохранить как…", self.save_profile_as).pack(side="left")
        self._modern_button(bar, "Открыть config.env", self.open_config).pack(side="right")
        self._build_configure(parent)

    def _build_activity(self, parent):
        box = self._card(parent, "Подтверждение настроек", "Проверяется только ограниченная часть настроек сервера. Ключи и пулы моделей не подтверждаются.")
        self._modern_button(box, "Проверить состояние", self._delayed_health_check).pack(anchor="w", padx=10, pady=(0, 8))
        self._label(box, textvariable=self.applied_config_var, fg=MUTED_FG, size=9, wraplength=810, justify="left").pack(fill="x", padx=10)
        self._label(box, textvariable=self.status_var, fg=TEXT_FG, size=9, wraplength=810, justify="left").pack(fill="x", padx=10, pady=(8, 0))
        box = self._card(parent, "Текущие запросы", "Снимок последней проверки. Обновление не запускает генерацию.")
        scroll = ttk.Scrollbar(box, orient="vertical")
        scroll.pack(side="right", fill="y")
        text = tk.Text(box, height=6, wrap="word", state="disabled", bg=CARD_MUTED_BG, fg=TEXT_FG,
            relief="flat", padx=10, pady=8, yscrollcommand=scroll.set, font=("Consolas", 9))
        text.pack(fill="x", expand=True)
        scroll.configure(command=text.yview)
        def render(*_args):
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("end", self.activity_var.get())
            text.configure(state="disabled")
        self.activity_var.trace_add("write", render)
        render()

    def _build_ui(self):
        self.page_title_var = tk.StringVar(value=self.page_specs[0].title)
        self.page_subtitle_var = tk.StringVar(value=self.page_specs[0].subtitle)
        self.page_mode_var = tk.StringVar(value="РАБОТА")
        self.context_help_var = tk.StringVar(value="")
        shell = self._surface(self, bg=APP_BG)
        shell.pack(fill="both", expand=True)
        sidebar = self._surface(shell, bg=HEADER_BG, width=222)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = self._surface(sidebar, bg=HEADER_BG, padx=18, pady=24)
        brand.pack(fill="x")
        self._label(brand, "IC / FORGE", size=19, fg=ACCENT_BG, bold=True).pack(anchor="w")
        self._label(brand, "InfiniCrafterLocal", size=10, fg=TEXT_FG).pack(anchor="w", pady=(7, 2))
        self._label(brand, "Мастерская предметов", size=9, fg=MUTED_FG).pack(anchor="w")
        tk.Frame(sidebar, height=1, bg=BORDER_FG).pack(fill="x", padx=18)
        self._build_tab_navigation(sidebar)
        foot = self._surface(sidebar, bg=HEADER_BG, padx=18, pady=20)
        foot.pack(side="bottom", fill="x")
        self._label(foot, "ЛОКАЛЬНАЯ МАСТЕРСКАЯ", fg=MUTED_FG, size=8, bold=True).pack(anchor="w")
        self._label(foot, "Твои модели. Твои предметы.", fg=MUTED_FG, size=9).pack(anchor="w", pady=(5, 0))
        main = self._surface(shell, bg=APP_BG)
        main.pack(side="left", fill="both", expand=True)
        header = self._surface(main, bg=APP_BG, padx=24, pady=17)
        header.pack(fill="x")
        self._modern_button(header, "Сохранить настройки", self.save, "primary").pack(side="right")
        self._label(header, textvariable=self.page_mode_var, fg=ACCENT_BG, size=8, bold=True).pack(anchor="w")
        self._label(header, textvariable=self.page_title_var, size=15, bold=True).pack(anchor="w", pady=(5, 0))
        tk.Frame(main, height=1, bg=BORDER_FG).pack(fill="x")
        footer = self._surface(main, bg=HEADER_BG, padx=22, pady=10)
        footer.pack(side="bottom", fill="x")
        # Friendly status stays short; the exact backend message remains in Diagnostics.
        self.footer_status = self._label(footer, "Состояние ещё не проверено", fg=MUTED_FG, size=9)
        self.footer_status.pack(side="left", fill="x", expand=True)
        self._modern_button(footer, "Диагностика", lambda: self.navigate("diagnostics")).pack(side="right")
        toolbar = self._surface(main, bg=APP_BG, padx=24, pady=9)
        toolbar.pack(fill="x")
        self.workspace_toolbar = toolbar
        self._label(toolbar, textvariable=self.page_subtitle_var, fg=MUTED_FG, size=9).pack(side="left", fill="x", expand=True)
        self._modern_button(toolbar, "Проверить настройки", self.validate_paths).pack(side="right", padx=(8, 0))
        # These are view preferences, not backend config and never wipe hidden values.
        view = self._surface(main, bg=CARD_BG, padx=24, pady=5)
        view.pack(fill="x", padx=24, pady=(0, 10))
        self.view_options = view
        ttk.Checkbutton(view, text="Расширенные параметры", variable=self.advanced_var, command=self._apply_view_mode).pack(side="left")
        ttk.Checkbutton(view, text="Показать ключи", variable=self.show_secrets, command=self._refresh_secret_entries).pack(side="right")
        workspace = self._surface(main, bg=APP_BG, padx=20)
        workspace.pack(fill="both", expand=True, pady=(0, 10))
        self.tabs = ttk.Notebook(workspace, style="Hidden.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        pages = [ScrollFrame(self.tabs, background=APP_BG) for _ in self.page_specs]
        self.pages = {spec.key: page for spec, page in zip(self.page_specs, pages)}
        for spec, page in zip(self.page_specs, pages):
            self.tabs.add(page, text=spec.title)
        self.general_tab, self.llm_tab, self.multidev_tab, self.image_tab, self.visual_tab, self.trace_tab = pages[:6]
        # Build once. Page changes only switch ownership/visibility; no config reload or loss.
        self._build_profiles(pages[7].inner)
        self._build_llm(pages[1].inner)
        self._build_multidev(pages[2].inner)
        self._build_image(pages[3].inner)
        self._build_visual(pages[4].inner)
        self._build_multiplayer(pages[6].inner)
        self._build_logging(pages[5].inner)
        self._build_activity(pages[5].inner)
        self._build_trace(pages[5].inner)
        self._build_operate(pages[0].inner)
        self.tabs.bind("<<NotebookTabChanged>>", lambda _e: self._paint_tab_navigation(), add="+")
        self.tabs.select(0)
        self._paint_tab_navigation()
        def update_summary(*args):
            self._refresh_operate_summary(*args)
            self.footer_status.configure(text=self.home_notice_var.get())
        for var in [self.status_var, self.applied_config_var, self.activity_var, *self.vars.values()]:
            var.trace_add("write", update_summary)
        self.bind("<Control-s>", lambda _e: self.save(), add="+")
