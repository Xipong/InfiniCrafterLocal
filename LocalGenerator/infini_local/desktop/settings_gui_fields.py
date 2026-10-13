from __future__ import annotations

from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX
from infini_local.desktop.settings_schema import DEFAULTS, FIELD_HELP, OPTION_HELP, PRESETS, PRESET_HELP
from infini_local.desktop.settings_widgets import ToolTip
from infini_local.desktop.settings_gui_theme import APP_BG, CARD_BG, CARD_MUTED_BG, TEXT_FG, ACCENT_SOFT_BG, BORDER_DARK_FG

_BASIC_FIELDS = frozenset({
    "INFINI_HOST", "INFINI_PORT", "INFINI_LLM_PROVIDER", "INFINI_USE_LLM", "INFINI_PROMPT_STYLE",
    "INFINI_CODEX_LLM_MODEL", "INFINI_LLM_REASONING_MODE", "INFINI_LMSTUDIO_URL", "INFINI_LMSTUDIO_MODEL",
    "INFINI_OPENROUTER_API_KEY", "INFINI_OPENROUTER_MODEL", "INFINI_OPENROUTER_PROVIDER",
    "INFINI_OPENAI_COMPAT_BASE_URL", "INFINI_OPENAI_COMPAT_API_KEY", "INFINI_OPENAI_COMPAT_MODEL",
    "INFINI_IMAGE_BACKEND", "INFINI_CODEX_IMAGE_MODEL", "INFINI_CODEX_IMAGE_QUALITY", "INFINI_CODEX_IMAGE_SIZE",
    "INFINI_SDCPP_SERVER_EXE", "INFINI_SDCPP_MODEL", "INFINI_SDCPP_VAE", "INFINI_SDCPP_LLM",
    "INFINI_SDCPP_SERVER_AUTOSTART", "INFINI_SDCPP_LORA_FILE", "INFINI_SDCPP_LORA_WEIGHT",
    "INFINI_SDCPP_SERVER_URL", "INFINI_SDCPP_STEPS", "INFINI_SDCPP_CFG", "INFINI_SDCPP_SAMPLER",
    "INFINI_IMAGE_API_BASE_URL", "INFINI_IMAGE_API_KEY", "INFINI_IMAGE_API_MODEL", "INFINI_IMAGE_API_SIZE",
    "INFINI_A1111_URL", "INFINI_COMFYUI_URL", "INFINI_BG_COLOR", "INFINI_REMOVE_BG",
    "INFINI_SPRITE_DOWNSCALE_FILTER", "INFINI_MP_ASSET_TRANSPORT", "INFINI_TERRARIA_PORT",
    "INFINI_ASSET_PUBLIC_BASE_URL", "INFINI_MULTIDEV_CONCURRENCY", "INFINI_TRACE_PROMPTS",
})



class SettingsFieldsMixin:
    @staticmethod
    def _set_packed_visible(widget, visible: bool):
        if visible:
            if widget.winfo_manager() == "pack":
                return
            options = dict(getattr(widget, "_infini_pack_options", {}))
            siblings = list(widget.master.winfo_children())
            following = siblings[siblings.index(widget) + 1:]
            before = next((other for other in following if other.winfo_manager() == "pack"), None)
            if before is not None:
                options["before"] = before
            widget.pack(**options)
        elif widget.winfo_manager() == "pack":
            options = widget.pack_info()
            options.pop("in", None)
            widget._infini_pack_options = options
            widget.pack_forget()

    def _register_ui_section(self, body, field: str = "", choices: tuple[str, ...] = (), advanced: bool = False):
        outer = getattr(body, "_infini_card_outer", body)
        self.__dict__.setdefault("_ui_sections", []).append((outer, field, choices, advanced))

    def _apply_view_mode(self):
        advanced = bool(self.advanced_var.get())
        for key, widgets in self.field_widgets.items():
            if not widgets:
                continue
            basic = key in _BASIC_FIELDS or key.startswith("INFINI_LLM_POOL_")
            visible = (advanced or basic) and not self.field_disabled_reasons.get(key)
            self._set_packed_visible(self.__dict__.get("_field_rows", {}).get(key, widgets[0]), visible)
            hint = self.field_hint_labels.get(key)
            if hint is not None:
                self._set_packed_visible(hint, advanced and visible)
        for widget, field, choices, advanced_only in self.__dict__.get("_ui_sections", []):
            active = not field or self.vars[field].get() in choices
            self._set_packed_visible(widget, active and (advanced or not advanced_only))

    def _attach_static_help(self, widget, text):
        ToolTip(widget, text)

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
        # Help belongs to its own channel; never erase a server error on hover.
        hint = self.__dict__.get("context_help_var")
        if hint is not None:
            hint.set(self._field_help_text(key).split("\n", 1)[0][:180])

    def _preset_help_text(self) -> str:
        name = self.preset_var.get()
        text = PRESET_HELP.get(name, "")
        changes = PRESETS.get(name, {})
        if changes:
            rendered = "\n".join(f"• {k}={v}" for k, v in changes.items())
            return f"{name}\n\n{text}\n\nЧто изменит Apply pipeline:\n{rendered}"
        if name.startswith(USER_PRESET_PREFIX):
            return "Твой сохранённый профиль. «Применить» восстанавливает настройки; текущие ключи остаются. Для записи config.env нажми «Сохранить»."
        return text or ("Custom — текущие настройки изменены вручную. «Сохранить как…» создаёт отдельный именованный профиль." if name == CUSTOM_PRESET else name)

    def _show_preset_help(self):
        self.status_var.set(PRESET_HELP.get(self.preset_var.get(), "Выбран pipeline preset. Нажми Apply pipeline, чтобы применить."))

    def _set_widget_enabled(self, widget, enabled: bool):
        try:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=("normal" if getattr(widget, "_infini_editable", False) else "readonly") if enabled else "disabled")
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

    def row(self, parent, label, key, width=64, secret=False, browse=None, values=None, hint=None, editable=False):
        bg = self._bg_of(parent, CARD_BG)
        label_style = "FieldLabelMuted.TLabel" if bg == CARD_MUTED_BG else "FieldLabel.TLabel"
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(10, 4), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            frame._infini_bg = bg
        except (AttributeError, RuntimeError, TypeError):
            pass
        label_widget = ttk.Label(frame, text=label, width=24, style=label_style)
        label_widget.pack(side="left")
        var = self._var(key)
        if values:
            widget = ttk.Combobox(frame, textvariable=var, values=values, width=width, state="normal" if editable else "readonly")
            setattr(widget, "_infini_editable", editable)
            widget.bind("<<ComboboxSelected>>", lambda _e, key=key: (self._refresh_visibility(), self._show_field_help(key)), add="+")
        else:
            widget = ttk.Entry(frame, textvariable=var, width=width, show="*" if secret and not self.show_secrets.get() else "")
            if secret:
                self.secret_entries.append(widget)
        compact = width <= 20 and browse is None
        if compact:
            widget.pack(side="left", ipady=2)
        else:
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
            hint_label = ttk.Label(parent, text="   " + base_hint, style=hint_style, wraplength=740, justify="left")
            hint_label.pack(anchor="w", padx=16, pady=(0, 4))
            registered_widgets.append(hint_label)
        self._register_field_widgets(key, registered_widgets, base_hint, hint_label)
        return frame

    def check_row(self, parent, label, key, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(10, 4), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
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
        self.__dict__.setdefault("_field_rows", {})[key] = frame
        self._register_field_widgets(key, [widget], hint, hint_label)
        return frame

    def text_row(self, parent, label, key, height=4, hint=None):
        bg = self._bg_of(parent, CARD_BG)
        label_style = "FieldLabelMuted.TLabel" if bg == CARD_MUTED_BG else "FieldLabel.TLabel"
        hint_style = "HintMuted.TLabel" if bg == CARD_MUTED_BG else "Hint.TLabel"
        frame = ttk.Frame(parent, padding=(10, 4), style="CardInner.TFrame" if bg == CARD_BG else "MutedCard.TFrame")
        frame.pack(fill="x")
        try:
            frame._infini_bg = bg
        except (AttributeError, RuntimeError, TypeError):
            pass
        label_widget = ttk.Label(frame, text=label, width=24, style=label_style)
        label_widget.pack(side="left", anchor="n")
        text = tk.Text(frame, width=70, height=height, wrap="word", undo=True, bg=CARD_MUTED_BG, fg=TEXT_FG, insertbackground=TEXT_FG, selectbackground=ACCENT_SOFT_BG, relief="flat", bd=1, highlightthickness=1, highlightbackground=BORDER_DARK_FG, font=(self.__dict__.get("ui_font_family", "Segoe UI"), 9))
        text.insert("1.0", self.data.get(key, DEFAULTS.get(key, "")))
        text.pack(side="left", fill="x", expand=True)
        self.text_widgets[key] = text
        self._enable_edit_menu(text)
        hint_label = None
        base_hint = hint or ""
        registered_widgets: list[tk.Widget] = [frame, label_widget, text]
        if base_hint:
            hint_label = ttk.Label(parent, text="   " + base_hint, style=hint_style, wraplength=740, justify="left")
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
        menu.add_command(label="Вырезать", command=lambda: self._edit_event(event.widget, "cut"))
        menu.add_command(label="Копировать", command=lambda: self._edit_event(event.widget, "copy"))
        menu.add_command(label="Вставить", command=lambda: self._edit_event(event.widget, "paste"))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: self._edit_event(event.widget, "select_all"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
