from __future__ import annotations

from infini_local.desktop.tk_compat import tk, ttk


# AGENT MAP: small reusable Tk widgets for settings_gui.py.
# Keep generic widget mechanics here; app-specific layout/state remains in SettingsGui.

class ToolTip:
    """Small delayed tooltip for Tk/ttk widgets.

    `text` may be a string or a callable returning a string, so disabled-state reasons
    and current combobox values stay fresh while the GUI is open.
    """
    def __init__(self, widget, text, *, delay: int = 450, wraplength: int = 520):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Motion>", self._move, add="+")

    def _resolve_text(self) -> str:
        try:
            value = self.text() if callable(self.text) else self.text
        except Exception as e:
            value = f"Tooltip error: {e}"
        return str(value or "").strip()

    def _schedule(self, event=None):
        self._cancel()
        self._last_event = event
        self._after_id = self.widget.after(self.delay, lambda: self._show(self._last_event))

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self, event=None):
        self._cancel()
        text = self._resolve_text()
        if not text:
            return
        self._hide()
        x = (getattr(event, "x_root", 0) or self.widget.winfo_pointerx()) + 16
        y = (getattr(event, "y_root", 0) or self.widget.winfo_pointery()) + 18
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tip,
            text=text,
            justify="left",
            wraplength=self.wraplength,
            padx=9,
            pady=7,
            relief="solid",
            borderwidth=1,
            background="#ffffe8",
        )
        label.pack(ipadx=1)
        self._tip = tip

    def _move(self, event=None):
        # Do not chase the cursor every pixel while visible; that makes tooltips jittery.
        if self._tip is None:
            self._last_event = event

    def _hide(self, event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

class ScrollFrame(ttk.Frame):
    def __init__(self, master, *, background: str = "#f5f7fb"):
        super().__init__(master)
        self.configure(style="Infini.TFrame")
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, background=background)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.inner = ttk.Frame(self.canvas, style="Infini.TFrame")
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.inner_id, width=event.width)

    def _on_mousewheel(self, event):
        if self.winfo_toplevel().focus_get() is not None:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


__all__ = [
    "ToolTip",
    "ScrollFrame",
]
