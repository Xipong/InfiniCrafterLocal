from __future__ import annotations

from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_gui_theme import CARD_MUTED_BG, TEXT_FG, MUTED_FG

class DiagnosticsPageMixin:
    def _build_trace(self, parent):
        outer = ttk.Frame(parent, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Журнал генерации", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Чёрный ящик генерации: что отправили ЛЛМ, какие image prompts ушли в backend, что ответил sd.cpp, где отвалился step.",
            foreground=MUTED_FG,
        ).pack(anchor="w", pady=(2, 8))

        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Обновить", command=self.refresh_trace).pack(side="left", padx=2)
        ttk.Button(bar, text="Отменить", command=self.cancel_trace_refresh).pack(side="left", padx=2)
        ttk.Button(bar, text="Открыть в браузере", command=self.open_trace_page).pack(side="left", padx=2)
        ttk.Button(bar, text="JSON", command=self.open_trace_json).pack(side="left", padx=2)
        ttk.Button(bar, text="Папка", command=self.open_cache_folder).pack(side="left", padx=2)
        ttk.Button(bar, text="Очистить…", command=self.clear_trace_files).pack(side="left", padx=8)
        self.trace_status_var = tk.StringVar(value="Нажми Refresh trace. Если server.py не запущен, GUI покажет локальные cache/*.ndjson.")
        ttk.Label(outer, textvariable=self.trace_status_var, foreground=MUTED_FG).pack(anchor="w", pady=(0, 8))

        self.trace_views = ttk.Notebook(outer)
        self.trace_views.pack(fill="both", expand=True)
        self.trace_texts: dict[str, tk.Text] = {}
        for key, title in [
            ("summary", "Сводка"),
            ("prompts", "Промпты"),
            ("pipeline", "Этапы"),
            ("events", "События"),
            ("sdcpp", "sd.cpp"),
            ("failure", "Последняя ошибка"),
        ]:
            frame = ttk.Frame(self.trace_views)
            self.trace_views.add(frame, text=title)
            text = tk.Text(frame, height=12, wrap="word", undo=False, font=("Consolas", 9), bg=CARD_MUTED_BG, fg=TEXT_FG, insertbackground=TEXT_FG)
            scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            text.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            self._enable_edit_menu(text)
            self.trace_texts[key] = text
