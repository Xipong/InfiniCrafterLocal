"""Native forge component grammar: surfaces, section rails, controls and type."""
from __future__ import annotations

from infini_local.desktop.tk_compat import tk, ttk
from infini_local.desktop.settings_gui_theme import (
    APP_BG, CARD_BG, CARD_MUTED_BG, HEADER_BG, TEXT_FG, MUTED_FG,
    ACCENT_BG, ACCENT_HOVER_BG, ACCENT_SOFT_BG, ACCENT_FG,
    SUCCESS_SOFT_BG, SUCCESS_FG, DANGER_SOFT_BG, DANGER_FG,
    WARNING_SOFT_BG, WARNING_FG, BORDER_FG, BORDER_DARK_FG,
)


class ForgeComponentsMixin:
    def _configure_theme(self):
        from tkinter import font
        from infini_local.desktop.settings_gui_theme import resolve_ui_font
        self.ui_font_family = resolve_ui_font(font.families(self))
        self.configure(bg=APP_BG)
        self.option_add("*Font", (self.ui_font_family, 10))
        self.option_add("*Background", CARD_BG)
        self.option_add("*Foreground", TEXT_FG)
        self.option_add("*selectBackground", ACCENT_SOFT_BG)
        self.option_add("*selectForeground", TEXT_FG)
        self.option_add("*TCombobox*Listbox.background", CARD_BG)
        self.option_add("*TCombobox*Listbox.foreground", TEXT_FG)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=CARD_BG, foreground=TEXT_FG, font=(self.__dict__.get("ui_font_family", "Segoe UI"), 10))
        for name, bg in (("Infini", APP_BG), ("Toolbar", CARD_BG), ("Card", CARD_BG),
                         ("CardInner", CARD_BG), ("MutedCard", CARD_MUTED_BG), ("Header", HEADER_BG)):
            style.configure(name + ".TFrame", background=bg, relief="flat", borderwidth=0)
        for name, bg, size, weight, fg in (
            ("Section", CARD_BG, 12, "bold", TEXT_FG),
            ("FieldLabel", CARD_BG, 10, "normal", TEXT_FG),
            ("FieldLabelMuted", CARD_MUTED_BG, 10, "normal", TEXT_FG),
            ("Hint", CARD_BG, 9, "normal", MUTED_FG),
            ("HintMuted", CARD_MUTED_BG, 9, "normal", MUTED_FG),
        ):
            style.configure(name + ".TLabel", background=bg, foreground=fg, font=(self.__dict__.get("ui_font_family", "Segoe UI"), size, weight))
        style.configure("TLabel", background=CARD_BG, foreground=TEXT_FG)
        style.configure("TCheckbutton", padding=(0, 3), background=CARD_BG, foreground=TEXT_FG,
                        indicatorbackground=CARD_MUTED_BG, indicatorforeground=ACCENT_BG, bordercolor=BORDER_FG)
        style.map("TCheckbutton", background=[("active", CARD_BG)], foreground=[("disabled", MUTED_FG)],
                  indicatorbackground=[("selected", ACCENT_SOFT_BG), ("active", CARD_MUTED_BG)])
        style.configure("TEntry", padding=(8, 6), fieldbackground=CARD_MUTED_BG, foreground=TEXT_FG,
                        insertcolor=TEXT_FG, bordercolor=BORDER_DARK_FG, lightcolor=BORDER_DARK_FG, darkcolor=BORDER_DARK_FG)
        style.map("TEntry", bordercolor=[("focus", ACCENT_BG)], foreground=[("disabled", MUTED_FG)])
        style.configure("TCombobox", padding=(8, 6), fieldbackground=CARD_MUTED_BG,
                        foreground=TEXT_FG, arrowcolor=ACCENT_BG, bordercolor=BORDER_DARK_FG, lightcolor=BORDER_DARK_FG, darkcolor=BORDER_DARK_FG, borderwidth=1)
        style.map("TCombobox", fieldbackground=[("readonly", CARD_MUTED_BG), ("disabled", APP_BG)],
                  foreground=[("readonly", TEXT_FG), ("disabled", MUTED_FG)],
                  bordercolor=[("focus", ACCENT_BG), ("readonly", BORDER_DARK_FG)],
                  lightcolor=[("focus", ACCENT_BG), ("readonly", BORDER_DARK_FG)],
                  darkcolor=[("focus", ACCENT_BG), ("readonly", BORDER_DARK_FG)])
        style.configure("TButton", padding=(10, 6), background=CARD_BG, foreground=TEXT_FG, bordercolor=BORDER_FG, lightcolor=BORDER_FG, darkcolor=BORDER_FG)
        style.map("TButton", background=[("active", ACCENT_SOFT_BG)], foreground=[("disabled", MUTED_FG)])
        style.configure("TSeparator", background=BORDER_FG)
        for orientation in ("Vertical", "Horizontal"):
            style.configure(orientation + ".TScrollbar", background=BORDER_DARK_FG, troughcolor=APP_BG,
                arrowcolor=MUTED_FG, bordercolor=APP_BG, lightcolor=APP_BG, darkcolor=APP_BG,
                gripcount=0, arrowsize=12)
            style.map(orientation + ".TScrollbar", background=[("active", MUTED_FG)])
        style.configure("TLabelframe", background=CARD_BG, bordercolor=BORDER_FG)
        style.configure("TLabelframe.Label", background=CARD_BG, foreground=MUTED_FG)
        style.configure("TNotebook", background=APP_BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), background=CARD_BG, foreground=MUTED_FG)
        style.map("TNotebook.Tab", background=[("selected", ACCENT_SOFT_BG)], foreground=[("selected", ACCENT_BG)])
        style.configure("Hidden.TNotebook", background=APP_BG, borderwidth=0, bordercolor=APP_BG, lightcolor=APP_BG, darkcolor=APP_BG, tabmargins=(0, 0, 0, 0))
        style.layout("Hidden.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
        style.layout("Hidden.TNotebook.Tab", [])

    @staticmethod
    def _bg_of(parent, fallback=APP_BG):
        return str(getattr(parent, "_infini_bg", fallback) or fallback)

    @staticmethod
    def _as_tk_color_widget(widget, **kwargs):
        widget.configure(**kwargs)
        return widget

    def _surface(self, parent, bg=CARD_BG, **kwargs):
        frame = tk.Frame(parent, bg=bg, **kwargs)
        frame._infini_bg = bg
        return frame

    def _label(self, parent, text="", *, size=10, fg=TEXT_FG, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=self._bg_of(parent), fg=fg,
                        font=(self.__dict__.get("ui_font_family", "Segoe UI"), size, "bold" if bold else "normal"), anchor="w", **kwargs)

    def _modern_button(self, parent, text, command, variant="ghost", width=None):
        bg, fg, hover, border = {
            "primary": (ACCENT_BG, ACCENT_FG, ACCENT_HOVER_BG, ACCENT_BG),
            "soft": (ACCENT_SOFT_BG, ACCENT_BG, "#493428", BORDER_DARK_FG),
            "success": (SUCCESS_SOFT_BG, SUCCESS_FG, "#304338", BORDER_FG),
            "danger": (DANGER_SOFT_BG, DANGER_FG, "#4b3230", BORDER_FG),
            "dark": (HEADER_BG, TEXT_FG, CARD_BG, BORDER_FG),
            "ghost": (CARD_BG, TEXT_FG, "#2c3034", BORDER_FG),
        }.get(variant, (CARD_BG, TEXT_FG, "#2c3034", BORDER_FG))
        button = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                           activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=border, highlightcolor=ACCENT_BG,
                           padx=14, pady=8, width=width or 0, cursor="hand2",
                           font=(self.__dict__.get("ui_font_family", "Segoe UI"), 10, "bold" if variant == "primary" else "normal"))
        button.bind("<Enter>", lambda _e: button.configure(bg=hover), add="+")
        button.bind("<Leave>", lambda _e: button.configure(bg=bg), add="+")
        return button

    def _chip(self, parent, text, tone="neutral"):
        bg, fg = {"blue": (ACCENT_SOFT_BG, ACCENT_BG), "green": (SUCCESS_SOFT_BG, SUCCESS_FG),
                  "red": (DANGER_SOFT_BG, DANGER_FG), "amber": (WARNING_SOFT_BG, WARNING_FG)}.get(tone, (CARD_MUTED_BG, MUTED_FG))
        return tk.Label(parent, text=text, bg=bg, fg=fg, padx=9, pady=4, font=(self.__dict__.get("ui_font_family", "Segoe UI"), 9))

    def _card(self, parent, title=None, subtitle="", icon="", status=None):
        # A single-column workspace section, not a promotional card grid.
        outer = self._surface(parent, padx=14, pady=12)
        outer.pack(fill="x", padx=4, pady=(0, 12))
        if title:
            head = self._surface(outer)
            head.pack(fill="x", pady=(0, 7))
            rail = tk.Frame(head, bg=ACCENT_BG, width=3, height=19)
            rail.pack(side="left", padx=(0, 10))
            self._label(head, title, size=12, bold=True).pack(side="left")
            if status:
                self._chip(head, *status).pack(side="right")
        if subtitle:
            self._label(outer, subtitle, size=9, fg=MUTED_FG, justify="left", wraplength=830).pack(fill="x", pady=(0, 8))
        body = self._surface(outer)
        body._infini_card_outer = outer
        body.pack(fill="x")
        return body

    def _inline_card(self, parent, bg=CARD_MUTED_BG):
        frame = self._surface(parent, bg=bg, padx=12, pady=10)
        frame.pack(fill="x", padx=10, pady=6)
        return frame

    def _info_panel(self, parent, text, tone="blue"):
        bg, fg = {"green": (SUCCESS_SOFT_BG, SUCCESS_FG), "amber": (WARNING_SOFT_BG, WARNING_FG),
                  "red": (DANGER_SOFT_BG, DANGER_FG)}.get(tone, (ACCENT_SOFT_BG, MUTED_FG))
        panel = self._inline_card(parent, bg)
        kwargs = {"textvariable": text} if isinstance(text, tk.StringVar) else {"text": str(text)}
        label = tk.Label(panel, bg=bg, fg=fg, font=(self.__dict__.get("ui_font_family", "Segoe UI"), 9), anchor="w", justify="left", wraplength=790, **kwargs)
        label.pack(fill="x")
        return label
