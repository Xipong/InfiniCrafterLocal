from __future__ import annotations

import webbrowser

from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    FIELD_HELP,
    OPTION_HELP,
    PRESETS,
    PRESET_HELP,
)
from infini_local.desktop.settings_widgets import ScrollFrame, ToolTip
from infini_local.desktop.settings_gui_theme import (
    APP_BG,
    CARD_BG,
    CARD_MUTED_BG,
    HEADER_BG,
    TEXT_FG,
    MUTED_FG,
    ACCENT_BG,
    ACCENT_HOVER_BG,
    ACCENT_SOFT_BG,
    ACCENT_FG,
    SUCCESS_BG,
    SUCCESS_SOFT_BG,
    SUCCESS_FG,
    DANGER_SOFT_BG,
    DANGER_FG,
    WARNING_SOFT_BG,
    WARNING_FG,
    BORDER_FG,
    BORDER_DARK_FG,
)


class SettingsGuiUiMixin:
    secret_entries: list[tk.Widget]

    def _attach_static_help(self, widget, text):
        ToolTip(widget, text)
        widget.bind("<Enter>", lambda _e: self.status_var.set(text() if callable(text) else str(text)), add="+")

    def _register_field_widgets(self, key: str, widgets: list[tk.Widget], hint: str | None = None, hint_label: ttk.Label | None = None):
        self.field_widgets.setdefault(key, []).extend([w for w in widgets if w is not None])
        self.field_base_hints[key] = hint or FIELD_HELP.get(key, "")
        if hint_label is not None:
            self.field_hint_labels[key] = hint_label
        for widget in widgets:
            if widget is None:
                continue
            ToolTip(widget, lambda key=key: self._field_help_text(key))
            widget.bind("<Enter>", lambda _e, key=key: self._show_field_help(key), add="+")

    def _field_help_text(self, key: str) -> str:
        parts: list[str] = []
        reason = self.field_disabled_reasons.get(key, "")
        if reason:
            parts.append("Сейчас неактивно: " + reason)
        base = FIELD_HELP.get(key) or self.field_base_hints.get(key, "")
        if base:
            parts.append(base)
        options = OPTION_HELP.get(key) or {}
        if options:
            cur = self.vars.get(key).get().strip() if key in self.vars else ""
            if cur and cur in options:
                parts.append(f"Текущее значение `{cur}`: {options[cur]}")
            rendered = "\n".join(f"• {value}: {desc}" for value, desc in options.items())
            parts.append("Варианты:\n" + rendered)
        return "\n\n".join(parts)

    def _show_field_help(self, key: str):
        text = self._field_help_text(key)
        if text:
            # Status bar is intentionally short; full text is in hover tooltip.
            first = text.split("\n", 1)[0]
            self.status_var.set(first[:220])

    def _preset_help_text(self) -> str:
        name = self.preset_var.get()
        text = PRESET_HELP.get(name, "")
        changes = PRESETS.get(name, {})
        if changes:
            rendered = "\n".join(f"• {k}={v}" for k, v in changes.items())
            return f"{name}\n\n{text}\n\nЧто изменит Apply pipeline:\n{rendered}"
        return text or name

    def _show_preset_help(self):
        self.status_var.set(PRESET_HELP.get(self.preset_var.get(), "Выбран pipeline preset. Нажми Apply pipeline, чтобы применить."))

    def _set_widget_enabled(self, widget, enabled: bool):
        try:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if enabled else "disabled")
                return
            if isinstance(widget, tk.Text):
                widget.configure(state="normal" if enabled else "disabled")
                return
            if isinstance(widget, ttk.Entry) or isinstance(widget, tk.Entry):
                widget.configure(state="normal" if enabled else "disabled")
                return
            if hasattr(widget, "state"):
                widget.state(["!disabled"] if enabled else ["disabled"])
                return
            widget.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _set_widgets_enabled(self, widgets: list[tk.Widget], enabled: bool):
        for widget in widgets:
            self._set_widget_enabled(widget, enabled)

    def _set_field_enabled(self, key: str, enabled: bool, reason: str = ""):
        self.field_disabled_reasons[key] = "" if enabled else reason
        self._set_widgets_enabled(self.field_widgets.get(key, []), enabled)
        hint_label = self.field_hint_labels.get(key)
        if hint_label is not None:
            base = self.field_base_hints.get(key, "")
            if enabled or not reason:
                hint_label.configure(text="   " + base if base else "")
            else:
                suffix = f"Неактивно: {reason}"
                hint_label.configure(text="   " + (base + "  —  " if base else "") + suffix)

    def _configure_theme(self):
        try:
            self.configure(bg=APP_BG)
            style = ttk.Style(self)
            try:
                # "clam" is old, but it allows ttk colors/padding to be predictable.
                # The visible chrome is drawn mostly with tk.Frame/tk.Button helpers below.
                style.theme_use("clam")
            except (AttributeError, RuntimeError, TypeError):
                pass
            style.configure("Infini.TFrame", background=APP_BG)
            style.configure("Toolbar.TFrame", background=CARD_BG)
            style.configure("Card.TFrame", background=CARD_BG, relief="flat", borderwidth=0)
            style.configure("CardInner.TFrame", background=CARD_BG, relief="flat", borderwidth=0)
            style.configure("MutedCard.TFrame", background=CARD_MUTED_BG, relief="flat", borderwidth=0)
            style.configure("Header.TFrame", background=HEADER_BG)
            style.configure("Header.TLabel", background=HEADER_BG, foreground="#f8fafc", font=("Segoe UI", 20, "bold"))
            style.configure("HeaderSub.TLabel", background=HEADER_BG, foreground="#cbd5e1", font=("Segoe UI", 9))
            style.configure("Section.TLabel", background=CARD_BG, foreground=TEXT_FG, font=("Segoe UI", 11, "bold"))
            style.configure("FieldLabel.TLabel", background=CARD_BG, foreground=TEXT_FG, font=("Segoe UI", 9, "bold"))
            style.configure("FieldLabelMuted.TLabel", background=CARD_MUTED_BG, foreground=TEXT_FG, font=("Segoe UI", 9, "bold"))
            style.configure("Hint.TLabel", background=CARD_BG, foreground=MUTED_FG, font=("Segoe UI", 8))
            style.configure("HintMuted.TLabel", background=CARD_MUTED_BG, foreground=MUTED_FG, font=("Segoe UI", 8))
            style.configure("Status.TLabel", background=CARD_BG, foreground=MUTED_FG, padding=(10, 7))
            style.configure("TNotebook", background=APP_BG, borderwidth=0, tabmargins=(0, 6, 0, 0))
            style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 9, "bold"), background="#eef2f7", foreground="#475569")
            style.map(
                "TNotebook.Tab",
                background=[("selected", CARD_BG), ("active", "#f8fafc")],
                foreground=[("selected", ACCENT_BG), ("active", TEXT_FG)],
            )
            style.configure("Accent.TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"))
            style.configure("Ghost.TButton", padding=(10, 6), font=("Segoe UI", 9))
            style.configure("TEntry", padding=(7, 5), fieldbackground="#ffffff", bordercolor=BORDER_DARK_FG, lightcolor=BORDER_DARK_FG, darkcolor=BORDER_DARK_FG)
            style.configure("TCombobox", padding=(7, 5), fieldbackground="#ffffff", bordercolor=BORDER_DARK_FG)
        except (AttributeError, RuntimeError, TypeError):
            # Headless/import smoke tests use no-op ttk shims. Styling is best-effort only.
            pass

    @staticmethod
    def _bg_of(parent, fallback: str = APP_BG) -> str:
        return str(getattr(parent, "_infini_bg", fallback) or fallback)

    @staticmethod
    def _as_tk_color_widget(widget, **kwargs):
        try:
            widget.configure(**kwargs)
        except (AttributeError, RuntimeError, TypeError):
            pass
        return widget

    def _modern_button(self, parent, text: str, command, variant: str = "ghost", width: int | None = None):
        """A small tk.Button skin because ttk buttons remain Windows-95-ish on some tML/dev boxes."""
        palette = {
            "primary": (ACCENT_BG, ACCENT_FG, ACCENT_HOVER_BG, ACCENT_BG),
            "success": (SUCCESS_SOFT_BG, SUCCESS_FG, "#bbf7d0", "#86efac"),
            "danger": (DANGER_SOFT_BG, DANGER_FG, "#fecaca", "#fca5a5"),
            "ghost": (CARD_BG, TEXT_FG, "#f8fafc", BORDER_DARK_FG),
            "soft": (ACCENT_SOFT_BG, ACCENT_BG, "#dbeafe", "#bfdbfe"),
            "dark": ("#152542", "#f8fafc", "#1e3a5f", "#334155"),
        }
        bg, fg, hover, border = palette.get(variant, palette["ghost"])
        try:
            btn = tk.Button(
                parent,
                text=text,
                command=command,
                bg=bg,
                fg=fg,
                activebackground=hover,
                activeforeground=fg,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=border,
                highlightcolor=border,
                padx=14,
                pady=7,
                width=width or 0,
                font=("Segoe UI", 9, "bold" if variant in {"primary", "soft"} else "normal"),
                cursor="hand2",
            )
            btn.bind("<Enter>", lambda _e, btn=btn, hover=hover: btn.configure(bg=hover), add="+")
            btn.bind("<Leave>", lambda _e, btn=btn, bg=bg: btn.configure(bg=bg), add="+")
            return btn
        except (AttributeError, RuntimeError, TypeError):
            return ttk.Button(parent, text=text, command=command, style="Accent.TButton" if variant == "primary" else "Ghost.TButton")

    def _chip(self, parent, text: str, tone: str = "neutral"):
        colors = {
            "neutral": ("#f1f5f9", "#334155", BORDER_FG),
            "blue": (ACCENT_SOFT_BG, ACCENT_BG, "#bfdbfe"),
            "green": (SUCCESS_SOFT_BG, SUCCESS_FG, "#bbf7d0"),
            "red": (DANGER_SOFT_BG, DANGER_FG, "#fecaca"),
            "amber": (WARNING_SOFT_BG, WARNING_FG, "#fde68a"),
        }
        bg, fg, border = colors.get(tone, colors["neutral"])
        try:
            label = tk.Label(
                parent,
                text=text,
                bg=bg,
                fg=fg,
                padx=10,
                pady=4,
                font=("Segoe UI", 8, "bold"),
                highlightthickness=1,
                highlightbackground=border,
            )
            label._infini_bg = bg
            return label
        except (AttributeError, RuntimeError, TypeError):
            return ttk.Label(parent, text=text)

    def _card(self, parent, title: str | None = None, subtitle: str = "", icon: str = "", status: tuple[str, str] | None = None):
        try:
            outer = tk.Frame(parent, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER_FG, bd=0)
            outer._infini_bg = CARD_BG
            outer.pack(fill="x", padx=10, pady=(8, 10))
            if title:
                head = tk.Frame(outer, bg=CARD_BG, padx=16, pady=12)
                head._infini_bg = CARD_BG
                head.pack(fill="x")
                left = tk.Frame(head, bg=CARD_BG)
                left._infini_bg = CARD_BG
                left.pack(side="left", fill="x", expand=True)
                title_line = tk.Frame(left, bg=CARD_BG)
                title_line._infini_bg = CARD_BG
                title_line.pack(anchor="w", fill="x")
                if icon:
                    tk.Label(title_line, text=icon, bg=CARD_BG, fg=ACCENT_BG, font=("Segoe UI Symbol", 14, "bold")).pack(side="left", padx=(0, 8))
                tk.Label(title_line, text=title, bg=CARD_BG, fg=TEXT_FG, font=("Segoe UI", 12, "bold")).pack(side="left")
                if subtitle:
                    tk.Label(left, text=subtitle, bg=CARD_BG, fg=MUTED_FG, font=("Segoe UI", 8), anchor="w", justify="left", wraplength=900).pack(anchor="w", pady=(4, 0))
                if status:
                    chip = self._chip(head, status[0], status[1])
                    chip.pack(side="right", padx=(12, 0))
            body = tk.Frame(outer, bg=CARD_BG, padx=4, pady=0)
            body._infini_bg = CARD_BG
            body.pack(fill="x")
            return body
        except (AttributeError, RuntimeError, TypeError):
            frame = ttk.Frame(parent, padding=(10, 8), style="Card.TFrame")
            frame.pack(fill="x", padx=10, pady=(8, 10))
            if title:
                ttk.Label(frame, text=((icon + "  ") if icon else "") + title, style="Section.TLabel").pack(anchor="w")
            return frame

    def _inline_card(self, parent, bg: str = CARD_MUTED_BG):
        try:
            frame = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER_FG, padx=12, pady=10)
            frame._infini_bg = bg
            frame.pack(fill="x", padx=12, pady=6)
            return frame
        except (AttributeError, RuntimeError, TypeError):
            frame = ttk.Frame(parent, padding=(10, 8), style="MutedCard.TFrame")
            frame.pack(fill="x", padx=12, pady=6)
            return frame

    def _info_panel(self, parent, text: str | tk.StringVar, tone: str = "blue"):
        bg = {"blue": ACCENT_SOFT_BG, "green": SUCCESS_SOFT_BG, "amber": WARNING_SOFT_BG, "red": DANGER_SOFT_BG}.get(tone, ACCENT_SOFT_BG)
        fg = {"blue": "#1e3a8a", "green": SUCCESS_FG, "amber": WARNING_FG, "red": DANGER_FG}.get(tone, "#1e3a8a")
        panel = self._inline_card(parent, bg=bg)
        try:
            tk.Label(panel, text="i", bg="#dbeafe" if tone == "blue" else bg, fg=fg, width=2, font=("Segoe UI", 10, "bold"), highlightthickness=1, highlightbackground="#bfdbfe").pack(side="left", padx=(0, 10), anchor="n")
            label_kwargs = dict(bg=bg, fg=fg, font=("Segoe UI", 8), justify="left", wraplength=880, anchor="w")
            if isinstance(text, tk.StringVar):
                lbl = tk.Label(panel, textvariable=text, **label_kwargs)
            else:
                lbl = tk.Label(panel, text=str(text), **label_kwargs)
            lbl.pack(side="left", fill="x", expand=True)
            return lbl
        except (AttributeError, RuntimeError, TypeError):
            if isinstance(text, tk.StringVar):
                return ttk.Label(panel, textvariable=text)
            return ttk.Label(panel, text=str(text))

    def _build_ui(self):
        shell = ttk.Frame(self, padding=(14, 12), style="Infini.TFrame")
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg=HEADER_BG, padx=18, pady=16, highlightthickness=1, highlightbackground="#102344")
        header._infini_bg = HEADER_BG
        header.pack(fill="x", pady=(0, 12))
        brand = tk.Frame(header, bg=HEADER_BG)
        brand._infini_bg = HEADER_BG
        logo = tk.Label(brand, text="⚡", bg=HEADER_BG, fg="#38bdf8", font=("Segoe UI Symbol", 28, "bold"))
        logo.pack(side="left", padx=(0, 14))
        header_text = tk.Frame(brand, bg=HEADER_BG)
        header_text._infini_bg = HEADER_BG
        header_text.pack(side="left", fill="x", expand=True)
        tk.Label(header_text, text="InfiniCrafterLocal", bg=HEADER_BG, fg="#f8fafc", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(
            header_text,
            text="Локальный генератор: LLM runtime, PNG, Radmin/LAN и debug-trace.",
            bg=HEADER_BG,
            fg="#cbd5e1",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        actions = tk.Frame(header, bg=HEADER_BG)
        actions._infini_bg = HEADER_BG
        actions.pack(side="right")
        for text, command, variant in [
            ("💾  Save", self.save, "primary"),
            ("▶  Start", self.start_server, "dark"),
            ("■  Stop", self.stop_server, "danger"),
            ("♥  Health", self.open_health, "success"),
            ("⚙  config.env", self.open_config, "dark"),
        ]:
            btn = self._modern_button(actions, text, command, variant=variant)
            btn.pack(side="left", padx=4)
        # Pack the fixed-width action group before the expandable brand so the
        # right-most config button is never clipped at the default window width.
        brand.pack(side="left", fill="x", expand=True)

        preset_bar = tk.Frame(shell, bg=CARD_BG, padx=16, pady=12, highlightthickness=1, highlightbackground=BORDER_FG)
        preset_bar._infini_bg = CARD_BG
        preset_bar.pack(fill="x", pady=(0, 12))
        preset_label = tk.Label(preset_bar, text="Pipeline preset", bg=CARD_BG, fg=TEXT_FG, font=("Segoe UI", 10, "bold"))
        preset_label.pack(side="left", padx=(0, 10))
        self.preset_var = tk.StringVar(value=self._pipeline_preset_from_config(self.data))
        preset_combo = ttk.Combobox(preset_bar, textvariable=self.preset_var, values=list(PRESETS), state="readonly", width=47)
        preset_combo.pack(side="left", padx=6, ipady=2)
        preset_combo.bind("<<ComboboxSelected>>", lambda _e: self._show_preset_help(), add="+")
        self._attach_static_help(preset_combo, lambda: self._preset_help_text())
        apply_btn = self._modern_button(preset_bar, "＋  Apply pipeline", self.apply_preset, variant="soft")
        apply_btn.pack(side="left", padx=(10, 16))
        self._attach_static_help(apply_btn, "Применить выбранный pipeline preset. После применения GUI заблокирует поля, которые не участвуют в выбранной связке.")
        guard_chip = self._chip(preset_bar, "runtime guarded", "blue")
        guard_chip.pack(side="right", padx=(8, 0))
        validate_btn = self._modern_button(preset_bar, "📁  Проверить пути", self.validate_paths, variant="ghost")
        validate_btn.pack(side="right", padx=(8, 0))
        self._attach_static_help(validate_btn, "Проверить активные пути/ключи для текущего provider/backend. Неактивные поля не считаются ошибкой.")
        secrets_btn = ttk.Checkbutton(preset_bar, text="Показать ключи", variable=self.show_secrets, command=self._refresh_secret_entries)
        secrets_btn.pack(side="right", padx=8)
        self._attach_static_help(secrets_btn, "Временно показать API keys вместо звёздочек.")
        # Repack the flexible left group after fixed right-side controls so Tk
        # reserves room for the full secrets/validate/status labels at 1040px.
        for widget in (preset_label, preset_combo, apply_btn):
            widget.pack_forget()
        preset_label.pack(side="left", padx=(0, 10))
        preset_combo.pack(side="left", padx=6, ipady=2)
        apply_btn.pack(side="left", padx=(10, 16))

        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True, pady=(0, 8))
        self.general_tab = ScrollFrame(self.tabs)
        self.llm_tab = ScrollFrame(self.tabs)
        self.image_tab = ScrollFrame(self.tabs)
        self.visual_tab = ScrollFrame(self.tabs)
        self.trace_tab = ttk.Frame(self.tabs, style="Infini.TFrame")
        self.tabs.add(self.general_tab, text="▣  1. Сервер / крафт")
        self.tabs.add(self.llm_tab, text="◉  2. LLM")
        self.tabs.add(self.image_tab, text="▧  3. Картинки")
        self.tabs.add(self.visual_tab, text="✦  4. VFX / качество")
        self.tabs.add(self.trace_tab, text="⌘  5. Trace / pipeline")

        self._build_general(self.general_tab.inner)
        self._build_llm(self.llm_tab.inner)
        self._build_image(self.image_tab.inner)
        self._build_visual(self.visual_tab.inner)
        self._build_trace(self.trace_tab)

        status_bar = tk.Frame(shell, bg=CARD_BG, padx=12, pady=8, highlightthickness=1, highlightbackground=BORDER_FG)
        status_bar._infini_bg = CARD_BG
        status_bar.pack(fill="x")
        tk.Label(status_bar, text="●", bg=CARD_BG, fg=SUCCESS_BG, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(status_bar, text="Готово", bg=CARD_BG, fg=TEXT_FG, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 12))
        tk.Label(status_bar, textvariable=self.status_var, bg=CARD_BG, fg=MUTED_FG, font=("Segoe UI", 9), anchor="w", justify="left").pack(side="left", fill="x", expand=True)

    def check_row(self, parent, label, key, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(12, 7), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            setattr(frame, "_infini_bg", bg)
        except (AttributeError, RuntimeError, TypeError):
            pass
        var = getattr(self, "_var")(key)
        widget = ttk.Checkbutton(
            frame,
            text=label,
            variable=var,
            onvalue="1",
            offvalue="0",
            command=getattr(self, "_refresh_visibility"),
        )
        widget.pack(side="left", anchor="w")
        hint_label = None
        if hint:
            hint_label = ttk.Label(frame, text="   " + hint, style=hint_style)
            hint_label.pack(side="left", fill="x", expand=True)
        self._register_field_widgets(key, [widget], hint, hint_label)
        return frame

    def row(self, parent, label, key, width=64, secret=False, browse=None, values=None, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        label_style = "FieldLabelMuted.TLabel" if bg == CARD_MUTED_BG else "FieldLabel.TLabel"
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(12, 7), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            frame._infini_bg = bg
        except (AttributeError, RuntimeError, TypeError):
            pass
        label_widget = ttk.Label(frame, text=label, width=26, style=label_style)
        label_widget.pack(side="left")
        var = self._var(key)
        if values:
            widget = ttk.Combobox(frame, textvariable=var, values=values, width=width, state="readonly")
            widget.bind("<<ComboboxSelected>>", lambda _e, key=key: (self._refresh_visibility(), self._show_field_help(key)), add="+")
        else:
            widget = ttk.Entry(frame, textvariable=var, width=width, show="*" if secret and not self.show_secrets.get() else "")
            if secret:
                self.secret_entries.append(widget)
        widget.pack(side="left", fill="x", expand=True, ipady=2)
        self._enable_edit_menu(widget)
        registered_widgets: list[tk.Widget] = [frame, label_widget, widget]
        if browse == "file":
            btn = self._modern_button(frame, "…", lambda: self.browse_file(key), variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        if browse == "model":
            btn = self._modern_button(frame, "…", lambda: self.browse_model(key), variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        if browse == "folder":
            btn = self._modern_button(frame, "…", lambda: self.browse_folder(key), variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        if browse == "lora_file":
            btn = self._modern_button(frame, "…", self.browse_lora_file, variant="ghost", width=3)
            btn.pack(side="left", padx=4)
            registered_widgets.append(btn)
        hint_label = None
        base_hint = hint or ""
        if base_hint:
            hint_label = ttk.Label(parent, text="   " + base_hint, style=hint_style)
            hint_label.pack(anchor="w", padx=16, pady=(0, 4))
            registered_widgets.append(hint_label)
        self._register_field_widgets(key, registered_widgets, base_hint, hint_label)
        return frame

    def text_row(self, parent, label, key, height=4, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        label_style = "FieldLabelMuted.TLabel" if bg == CARD_MUTED_BG else "FieldLabel.TLabel"
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(12, 7), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            frame._infini_bg = bg
        except (AttributeError, RuntimeError, TypeError):
            pass
        label_widget = ttk.Label(frame, text=label, width=26, style=label_style)
        label_widget.pack(side="left", anchor="n")
        text = tk.Text(frame, width=70, height=height, wrap="word", undo=True, relief="solid", bd=1, highlightthickness=1, highlightbackground=BORDER_DARK_FG, font=("Segoe UI", 9))
        text.insert("1.0", self.data.get(key, DEFAULTS.get(key, "")))
        text.pack(side="left", fill="x", expand=True)
        self.text_widgets[key] = text
        self._enable_edit_menu(text)
        hint_label = None
        base_hint = hint or ""
        registered_widgets: list[tk.Widget] = [frame, label_widget, text]
        if base_hint:
            hint_label = ttk.Label(parent, text="   " + base_hint, style=hint_style)
            hint_label.pack(anchor="w", padx=16, pady=(0, 4))
            registered_widgets.append(hint_label)
        self._register_field_widgets(key, registered_widgets, base_hint, hint_label)
        return frame

    def _enable_edit_menu(self, widget):
        # Right-click paste menu + keyboard shortcuts below. Needed because Tk on Windows
        # can miss Ctrl+V when the keyboard layout is Cyrillic.
        widget.bind("<Button-3>", lambda e: self._show_edit_menu(e), add="+")

    def _install_global_edit_shortcuts(self):
        for cls in ("Entry", "TEntry", "Text", "TCombobox"):
            self.bind_class(cls, "<Control-KeyPress>", self._handle_ctrl_edit_shortcut, add="+")
            self.bind_class(cls, "<Control-Shift-KeyPress-Insert>", lambda e: self._edit_event(e.widget, "paste"), add="+")
            self.bind_class(cls, "<Shift-KeyPress-Insert>", lambda e: self._edit_event(e.widget, "paste"), add="+")

    def _handle_ctrl_edit_shortcut(self, event):
        # keycode handles physical Ctrl+C/V/X/A even under RU layout.
        code = getattr(event, "keycode", 0)
        key = (getattr(event, "keysym", "") or "").lower()
        if code == 86 or key in {"v", "cyrillic_em"}:
            return self._edit_event(event.widget, "paste")
        if code == 67 or key in {"c", "cyrillic_es"}:
            return self._edit_event(event.widget, "copy")
        if code == 88 or key in {"x", "cyrillic_che"}:
            return self._edit_event(event.widget, "cut")
        if code == 65 or key in {"a", "cyrillic_ef"}:
            return self._edit_event(event.widget, "select_all")
        return None

    def _edit_event(self, widget, action):
        try:
            if action == "paste":
                widget.event_generate("<<Paste>>")
            elif action == "copy":
                widget.event_generate("<<Copy>>")
            elif action == "cut":
                widget.event_generate("<<Cut>>")
            elif action == "select_all":
                if isinstance(widget, tk.Text):
                    widget.tag_add("sel", "1.0", "end-1c")
                    widget.mark_set("insert", "end-1c")
                else:
                    widget.selection_range(0, "end")
                    widget.icursor("end")
            return "break"
        except Exception:
            return None

    def _show_edit_menu(self, event):
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Cut", command=lambda: self._edit_event(event.widget, "cut"))
        menu.add_command(label="Copy", command=lambda: self._edit_event(event.widget, "copy"))
        menu.add_command(label="Paste", command=lambda: self._edit_event(event.widget, "paste"))
        menu.add_separator()
        menu.add_command(label="Select all", command=lambda: self._edit_event(event.widget, "select_all"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _build_general(self, parent):
        server_card = self._card(
            parent,
            "Сервер и поведение крафта",
            "Локальный HTTP helper для tModLoader craft request. 127.0.0.1 — только для себя; 0.0.0.0 — LAN/Radmin.",
            icon="▣",
            status=("Ready", "green"),
        )
        self.row(server_card, "Host", "INFINI_HOST", hint="127.0.0.1 — только ты; 0.0.0.0 — принимать подключения из Radmin/LAN.")
        self.row(server_card, "Port", "INFINI_PORT", width=16)
        self.row(server_card, "Craft HTTP timeout", "INFINI_CRAFT_HTTP_TIMEOUT_SECONDS", width=16, hint="240 секунд: если крафт не готов, tModLoader попробует retry.")
        self.row(server_card, "Craft attempts", "INFINI_CRAFT_HTTP_ATTEMPTS", width=16)
        self.row(server_card, "Combine busy wait", "INFINI_COMBINE_BUSY_WAIT_SECONDS", width=16, hint="Сколько секунд параллельный /combine ждёт текущий craft/cache вместо немедленного busy response. Для обычной игры: 210.")

        debug_card = self._card(
            parent,
            "Debug: запас атакующих расходников",
            "Consumable weapon и ammo получают выбранный минимум. Зелья и материалы не меняются.\nLLM/prompt и canonical recipe не затрагиваются.",
            icon="⚒",
        )
        self.check_row(debug_card, "Включить минимум для атакующих расходников", "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED", hint="Применяется к delivery-копии fresh/cache-hit результата.")
        self.row(debug_card, "Минимум за один крафт", "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD", width=16, values=["2", "5", "10", "20", "25", "50", "99", "100", "250", "500", "999"], hint="Если authored craftYield/maxStack ниже, оба поднимаются до выбранного количества.")

        radmin_status = ("Local only", "green") if not self.radmin_enabled.get() else ("Radmin/LAN", "blue")
        radmin_card = self._card(
            parent,
            "Radmin / LAN — сетевой оверлей, не отдельный AI-режим",
            "Друзьям не нужен LocalGenerator для уже готовых предметов: они получают финальные JSON/PNG ассеты через мод.",
            icon="⌁",
            status=radmin_status,
        )
        net = ttk.Frame(radmin_card, padding=(12, 7), style="CardInner.TFrame")
        net.pack(fill="x")
        ttk.Checkbutton(net, text="Включить Radmin/LAN sharing поверх выбранного pipeline", variable=self.radmin_enabled, command=self.on_radmin_toggle).pack(side="left")
        self._modern_button(net, "Radmin: включить", self.apply_radmin_overlay, variant="soft").pack(side="left", padx=8)
        self._modern_button(net, "Local only", self.apply_local_overlay, variant="ghost").pack(side="left", padx=4)
        self.row(radmin_card, "Public asset URL", "INFINI_ASSET_PUBLIC_BASE_URL", hint="Для Radmin: http://26.x.x.x:5055. Это настройка поверх LMStudio/OpenRouter/Z-Image/Image API.")
        self.row(radmin_card, "Terraria port", "INFINI_TERRARIA_PORT", width=16, hint="Для друзей: Multiplayer → Join via IP → твой Radmin IP → этот порт. Обычно 7777.")
        connect = ttk.Frame(radmin_card, padding=(12, 6), style="CardInner.TFrame")
        connect.pack(fill="x")
        for text, command in [
            ("🌐  Auto Radmin URL", self.autofill_radmin_url),
            ("⧉  Copy friend guide", self.copy_radmin_friend_guide),
            ("↗  Open MP connect page", self.open_mp_connect_page),
        ]:
            self._modern_button(connect, text, command, variant="ghost").pack(side="left", padx=(0, 6))
        self.radmin_info_var = tk.StringVar(value=self._radmin_status_text())
        self._info_panel(radmin_card, self.radmin_info_var, tone="blue")

        trace_card = self._card(
            parent,
            "Trace / black box recorder",
            "Для отладки генерации: prompt trace, compact events tail и расследование проблемных предметов без изменения gameplay.",
            icon="⌘",
            status=("debug", "amber"),
        )
        self.row(trace_card, "Trace prompts", "INFINI_TRACE_PROMPTS", values=["1", "0"], hint="1 = сохранять LLM/image prompts и ответы в cache/prompt_trace.ndjson. Это debug, не gameplay state.")
        self.row(trace_card, "Trace prompt chars", "INFINI_TRACE_MAX_PROMPT_CHARS", width=16)
        self.row(trace_card, "Trace events tail", "INFINI_TRACE_EVENTS_TAIL", width=16)

    def _build_llm(self, parent):
        ttk.Label(parent, text="LLM: кто пишет контракт предмета", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self.row(parent, "Use LLM", "INFINI_USE_LLM", values=["1", "0"], hint="Главный переключатель LLM-авторинга. 0 допустим только для явных debug/dev сценариев.")
        self.row(parent, "Balance mode", "INFINI_BALANCE_MODE", values=["safety", "normalize", "report"])
        self.row(parent, "Deterministic dev fallback", "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK", values=["0", "1"], hint="Только для разработки: разрешает кодовый fallback, если LLM недоступна. В обычной игре оставлять 0.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        self.row(parent, "LLM provider", "INFINI_LLM_PROVIDER", values=["local", "openrouter", "openai_compat"], hint="OpenRouter может писать контракт, а картинки при этом могут идти локально через Z-Image.")
        self.row(parent, "LM Studio URL", "INFINI_LMSTUDIO_URL")
        self.row(parent, "LM Studio model", "INFINI_LMSTUDIO_MODEL")
        self.row(parent, "OpenRouter API key", "INFINI_OPENROUTER_API_KEY", secret=True)
        self.row(parent, "OpenRouter model", "INFINI_OPENROUTER_MODEL", hint="auto или slug модели с OpenRouter.")
        self.row(parent, "OpenRouter referer", "INFINI_OPENROUTER_HTTP_REFERER")
        self.row(parent, "OpenRouter title", "INFINI_OPENROUTER_APP_TITLE")
        self.row(parent, "Compat base URL", "INFINI_OPENAI_COMPAT_BASE_URL")
        self.row(parent, "Compat API key", "INFINI_OPENAI_COMPAT_API_KEY", secret=True)
        self.row(parent, "Compat model", "INFINI_OPENAI_COMPAT_MODEL")
        self.row(parent, "LLM 1 API mode", "INFINI_LLM_API_MODE", values=["auto", "responses", "chat_completions"], hint="auto сначала пробует /responses и запоминает поддержку; при отказе тот же self-contained packet идёт через /chat/completions.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Distributed item pool (optional)", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ttk.Label(parent, text="Один новый предмет закрепляется за одним profile на весь Planner → Visual → VFX; следующие предметы распределяются round-robin.", style="Hint.TLabel").pack(anchor="w", padx=14, pady=(0, 6))
        self.row(parent, "Provider failure cooldown", "INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS", hint="При отказе текущий stage идёт на следующий profile, а сломанный временно исключается из новых item leases.")
        for slot in (2, 3, 4):
            prefix = f"INFINI_LLM_POOL_{slot}"
            ttk.Label(parent, text=f"LLM {slot}", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(7, 0))
            self.row(parent, f"LLM {slot} enabled", f"{prefix}_ENABLED", values=["0", "1"])
            self.row(parent, f"LLM {slot} provider", f"{prefix}_PROVIDER", values=["local", "openrouter", "openai_compat"])
            self.row(parent, f"LLM {slot} base URL", f"{prefix}_BASE_URL", hint="Можно оставить пустым для стандартного OpenRouter URL или основного LM Studio URL.")
            self.row(parent, f"LLM {slot} API key", f"{prefix}_API_KEY", secret=True)
            self.row(parent, f"LLM {slot} model", f"{prefix}_MODEL", hint="Пустая модель не активируется даже при enabled=1.")
            self.row(parent, f"LLM {slot} API mode", f"{prefix}_API_MODE", values=["auto", "responses", "chat_completions"])
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Fallback LLM (optional)", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.row(parent, "Fallback provider", "INFINI_LLM_FALLBACK_PROVIDER", values=["", "local", "openrouter", "openai_compat"], hint="Пусто = использовать тот же провайдер, что и основной. Нужен только если хочешь при падении уйти на другой pipeline.")
        self.row(parent, "Fallback model", "INFINI_LLM_FALLBACK_MODEL", hint="Пусто = fallback выключен. Если основная модель умерла по бабкам/сети, сервер попробует эту модель.")
        self.row(parent, "Fallback base URL", "INFINI_LLM_FALLBACK_BASE_URL", hint="Пусто = взять base URL от fallback provider по умолчанию/из основных полей.")
        self.row(parent, "Fallback API key", "INFINI_LLM_FALLBACK_API_KEY", secret=True, hint="Пусто = использовать основной ключ выбранного fallback provider.")
        self.row(parent, "Fallback after transport fails", "INFINI_LLM_FALLBACK_NETWORK_FAILS", width=16, hint="Сколько сетевых/timeout падений подряд терпеть на основной модели, прежде чем уходить на fallback. По умолчанию 2.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Primary generation controls", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.row(parent, "Response format", "INFINI_LLM_RESPONSE_FORMAT", values=["auto", "json_schema", "json_object", "off"])
        self.row(parent, "Planner temperature", "INFINI_LLM_TEMPERATURE", width=16, hint="Температура основной LLM, которая пишет gameplay/runtime contract. 0.30-0.45: стабильнее; 0.55-0.75: разнообразнее, но выше риск мусора в контракте. Не относится к fallback-модели.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Scoped same-author repair (одна bounded попытка)", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ttk.Label(parent, text="Не verifier и не полный reauthor: после rejection Author role возвращает только разрешённые repair-поля; принятые concept/runtime domains сохраняются.", style="Hint.TLabel").pack(anchor="w", padx=14, pady=(0, 6))
        self.row(parent, "Repair temperature", "INFINI_LLM_REAUTHOR_TEMPERATURE", width=16, hint="Пусто = Planner temperature. Обычно 0.0-0.2 для bounded repair rejected domain.")
        self.row(parent, "Visual temp", "INFINI_VISUAL_DIRECTOR_TEMPERATURE", width=16, hint="Температура отдельного LLM Visual Director для image prompts/visual kit. Это не sd.cpp temperature и не fallback; на sampler не влияет.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="Output / reasoning", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.row(parent, "Max answer tokens", "INFINI_LLM_MAX_TOKENS", width=16, hint="Для OpenRouter free/cheap reasoning-моделей обычно 9000-12000, иначе reasoning съедает бюджет и JSON не успевает выйти.")
        self.row(parent, "Reasoning mode", "INFINI_LLM_REASONING_MODE", values=["off", "auto", "none", "minimal", "low", "medium", "high", "xhigh", "tokens", "prompt_light", "prompt_strong"], hint="OpenRouter: auto/effort/tokens через reasoning. Local LM Studio: API reasoning не шлём, prompt_* добавляет только внутренний чек без вывода reasoning.")
        self.row(parent, "Reasoning token budget", "INFINI_LLM_REASONING_MAX_TOKENS", width=16, hint="Используется при mode=tokens; OpenRouter мапит это на max_tokens/thinking_budget там, где модель поддерживает.")
        self.row(parent, "Hide reasoning output", "INFINI_LLM_REASONING_EXCLUDE", values=["1", "0"], hint="1 = reasoning используется, но не возвращается в message.content; меньше ломает JSON-парсер.")
        self.row(parent, "Local prompt reasoning", "INFINI_LLM_LOCAL_REASONING_PROMPT", values=["1", "0"], hint="Для локалок без API reasoning: разрешить короткий внутренний чек в system prompt. Цепочку мыслей выводить всё равно запрещено.")

    def _build_zimage_guide(self, parent):
        box = ttk.LabelFrame(parent, text="FLUX.2 / Z-Image / stable-diffusion.cpp — краткий гайд", padding=(10, 8))
        box.pack(fill="x", padx=10, pady=(6, 10))
        guide = (
            "1) Пути: укажи sd-server.exe, diffusion *.gguf, ae.safetensors и Qwen/LLM *.gguf. "
            "VAE/Qwen/LoRA не надо дублировать в extra args — GUI добавит --vae/--llm/--lora-model-dir сам.\n"
            "2) Текущий FLUX.2 Klein 4B preset: нажми FLUX hybrid. Diffusion+TE работают через ROCm, VAE через Vulkan, TE weights лежат в CPU RAM.\n"
            "3) Для Z-Image нажми AMD safe: runtime diffusion/VAE/TE на Vulkan, параметры Qwen/TE в RAM. Если VRAM душит/игра фризит: AMD low VRAM; для максимума скорости при достаточной VRAM: AMD full GPU.\n"
            "4) LoRA: выбери LoRA file и нажми Browse + use / Use selected LoRA. Отдельного поля folder нет: папка берётся из файла, а в prompt добавляется <lora:name:weight>.\n"
            "5) FLUX.2 Klein preset использует 4 / 1.0 / euler; Z-Image Turbo обычно 6-12 / 1.0 / euler.\n"
            "6) safe_args лучше template: меньше риска сломать --sampling-method или случайно вставить текст пресета в команду."
        )
        msg = tk.Message(box, text=guide, width=900, foreground="#444")
        msg.pack(fill="x", anchor="w")
        btns = ttk.Frame(box)
        btns.pack(fill="x", pady=(8, 0))
        docs = [
            ("Открыть sd.cpp GitHub", "https://github.com/leejet/stable-diffusion.cpp"),
            ("Backend docs", "https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/backend.md"),
            ("LoRA docs", "https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/lora.md"),
        ]
        for label, url in docs:
            b = ttk.Button(btns, text=label, command=lambda url=url: webbrowser.open(url))
            b.pack(side="left", padx=2)
            self._attach_static_help(b, url)

    def _build_image(self, parent):
        ttk.Label(parent, text="Image backend: кто рисует PNG", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self._build_zimage_guide(parent)
        self.row(parent, "Image backend", "INFINI_IMAGE_BACKEND", values=["sdcpp", "image_api", "off", "comfyui", "a1111"], hint="sdcpp = локальный FLUX.2/Z-Image через stable-diffusion.cpp; image_api = внешний API; off = без PNG.")
        self.row(parent, "sd-server.exe", "INFINI_SDCPP_SERVER_EXE", browse="file")
        self.row(parent, "ROCm hybrid runtime", "INFINI_SDCPP_ROCM_COMPAT_ROOT", browse="dir", hint="Папка sdcpp-hybrid-gfx1030. ROCm/HIP/rocBLAS env применяется только к дочернему sd-server.exe.")
        self.row(parent, "Diffusion model", "INFINI_SDCPP_MODEL", browse="model", hint="FLUX.2 Klein или Z-Image *.gguf.")
        self.row(parent, "VAE / AE", "INFINI_SDCPP_VAE", browse="model", hint="Обычно ae.safetensors. GUI сам добавит --vae, руками в extra args не надо.")
        self.row(parent, "Qwen / LLM", "INFINI_SDCPP_LLM", browse="model", hint="Text encoder/Qwen *.gguf. GUI сам добавит --llm, руками в extra args не надо.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        ttk.Label(parent, text="LoRA для Z-Image/sd.cpp", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        lora_note = ttk.Label(
            parent,
            text="   LoRA folder скрыт: GUI берёт папку из LoRA file, запускает sd.cpp с --lora-model-dir и передаёт LoRA через структурированный HTTP payload.",
            foreground="#666",
        )
        lora_note.pack(anchor="w", padx=10)
        ToolTip(lora_note, "HTTP server sd.cpp намеренно не исполняет <lora:...> из текста prompt. InfiniCrafter преобразует выбранный файл и вес в безопасное поле lora[] запроса.")
        self.row(parent, "LoRA file", "INFINI_SDCPP_LORA_FILE", browse="lora_file", hint="Выбери конкретный *.safetensors/*.ckpt/*.pt/*.pth. Имя файла и вес уйдут в структурированное поле lora[]; текстовый тег в модель не попадёт.")
        self.row(parent, "LoRA weight", "INFINI_SDCPP_LORA_WEIGHT", width=16, hint="Для FLUX.2 pixel-art LoRA начинай с 0.20-0.30; 0.45+ заметно меняет форму и может ухудшать identity.")
        self.text_row(parent, "LoRA prompt tags", "INFINI_SDCPP_LORA_PROMPT_TAGS", height=2, hint="Совместимый ввод <lora:name:weight>. Перед HTTP-вызовом теги удаляются из prompt и переводятся в lora[]; выбранный LoRA file задаёт точное имя файла.")
        self._build_lora_buttons(parent)
        self.row(parent, "sd.cpp URL", "INFINI_SDCPP_SERVER_URL")
        self.row(parent, "sd.cpp autostart", "INFINI_SDCPP_SERVER_AUTOSTART", values=["1", "0"])
        self.row(parent, "sd.cpp command mode", "INFINI_SDCPP_SERVER_COMMAND_MODE", values=["safe_args", "template"], hint="safe_args = рекомендуемый безопасный запуск без shell/template; template нужен только для нестандартного sd.cpp.")
        self.row(parent, "sd.cpp command", "INFINI_SDCPP_SERVER_COMMAND_TEMPLATE")
        self.text_row(parent, "sd.cpp extra args", "INFINI_SDCPP_SERVER_EXTRA_ARGS", height=4, hint="Только доп. флаги: -v, --diffusion-fa, --offload-to-cpu и т.п. VAE/Qwen лучше задавать полями выше.")
        self._build_sdcpp_extra_buttons(parent)
        self.row(parent, "sd.cpp show console", "INFINI_SDCPP_SERVER_SHOW_CONSOLE", values=["1", "0"], hint="1 = открыть отдельное окно sd-server.exe с живым логом. Полезно для отлова Z-Image крашей.")
        self.row(parent, "sd.cpp log file", "INFINI_SDCPP_SERVER_LOG_FILE", browse="file", hint="Если show console=0, stdout/stderr sd-server пишутся сюда. /sdcpp_debug покажет хвост.")
        self._build_sdcpp_debug_buttons(parent)
        self.row(parent, "sd width", "INFINI_SDCPP_WIDTH", width=16)
        self.row(parent, "sd height", "INFINI_SDCPP_HEIGHT", width=16)
        self.row(parent, "sd steps", "INFINI_SDCPP_STEPS", width=16)
        self.row(parent, "sd cfg", "INFINI_SDCPP_CFG", width=16)
        self.row(parent, "sd sampler", "INFINI_SDCPP_SAMPLER", width=24)
        self.row(parent, "sd seed", "INFINI_SDCPP_SEED", width=16, hint="-1 = случайный seed. Положительное число фиксирует результат для отладки.")
        self.row(parent, "Z-Image contract", "INFINI_ZIMAGE_PROMPT_CONTRACT", values=["auto", "1", "0"], hint="Обычно auto. Это внутренний маркер для Z-Image payload/prompt contract.")
        self.row(parent, "Positive-only prompt", "INFINI_ZIMAGE_POSITIVE_ONLY", values=["1", "0"], hint="Для Z-Image Turbo обычно 1: negative_prompt не используется, все запреты/техусловия в positive prompt.")
        self.row(parent, "Require item sprite", "INFINI_VISUAL_REQUIRE_ITEM_SPRITE", values=["1", "0"], hint="1 = не доставлять свежий craft без валидного item PNG. Основной product contract; выключать только для явной диагностики.")
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        self.row(parent, "Image API base", "INFINI_IMAGE_API_BASE_URL")
        self.row(parent, "Image API key", "INFINI_IMAGE_API_KEY", secret=True)
        self.row(parent, "Image API model", "INFINI_IMAGE_API_MODEL")
        self.row(parent, "Image API path", "INFINI_IMAGE_API_PATH")
        self.row(parent, "Image API size", "INFINI_IMAGE_API_SIZE", values=["512x512", "768x768", "1024x1024"])
        self.row(parent, "Image API timeout", "INFINI_IMAGE_API_TIMEOUT", width=16)
        ttk.Separator(parent).pack(fill="x", padx=10, pady=8)
        self.row(parent, "A1111 URL", "INFINI_A1111_URL")
        self.row(parent, "ComfyUI URL", "INFINI_COMFYUI_URL")

__all__ = ["SettingsGuiUiMixin"]
