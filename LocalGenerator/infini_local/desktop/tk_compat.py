from __future__ import annotations


# AGENT MAP: Tkinter compatibility layer for desktop/settings_gui.py.
# Real Tk imports stay here; headless pytest imports get lightweight class shims
# that preserve isinstance/widget checks without requiring _tkinter.

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    TKINTER_AVAILABLE = True
    TKINTER_IMPORT_ERROR = ""
except Exception as _tkinter_import_error:
    # Headless Python installs on Linux often omit tkinter/_tkinter.  Contract
    # tests import this module for DEFAULTS/FIELD_ORDER/static helpers, so import
    # must degrade to lightweight headless shims instead of blocking the whole pytest run.
    TKINTER_AVAILABLE = False
    TKINTER_IMPORT_ERROR = f"{type(_tkinter_import_error).__name__}: {_tkinter_import_error}"
    class _TkHeadlessBase:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, _name):
            return self._noop

        def _noop(self, *args, **kwargs):
            return None

        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def grid_remove(self, *args, **kwargs):
            return None

        def configure(self, *args, **kwargs):
            return None

        config = configure

        def destroy(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def winfo_children(self, *args, **kwargs):
            return []

        def yview(self, *args, **kwargs):
            return None

        def xview(self, *args, **kwargs):
            return None

        def insert(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

        def see(self, *args, **kwargs):
            return None

        def yview_moveto(self, *args, **kwargs):
            return None

        def create_window(self, *args, **kwargs):
            return None

        def itemconfigure(self, *args, **kwargs):
            return None

        def bbox(self, *args, **kwargs):
            return (0, 0, 0, 0)

        def after(self, *args, **kwargs):
            return None

        def after_cancel(self, *args, **kwargs):
            return None

    class _TkHeadlessVar:
        def __init__(self, value=""):
            self._value = value

        def get(self):
            return self._value

        def set(self, value):
            self._value = value

    class _TkHeadless:
        Widget = _TkHeadlessBase
        Toplevel = _TkHeadlessBase
        Frame = _TkHeadlessBase
        Button = _TkHeadlessBase
        Label = _TkHeadlessBase
        Entry = _TkHeadlessBase
        Text = _TkHeadlessBase
        Canvas = _TkHeadlessBase
        Menu = _TkHeadlessBase
        Message = _TkHeadlessBase
        StringVar = _TkHeadlessVar
        BooleanVar = _TkHeadlessVar
        END = "end"
        LEFT = "left"
        RIGHT = "right"
        BOTH = "both"
        X = "x"
        Y = "y"
        WORD = "word"

        class Tk(_TkHeadlessBase):
            def mainloop(self, *args, **kwargs):
                return None

            def protocol(self, *args, **kwargs):
                return None

            def title(self, *args, **kwargs):
                return None

            def geometry(self, *args, **kwargs):
                return None

            def update(self, *args, **kwargs):
                return None

    class _TtkHeadless:
        Widget = _TkHeadlessBase
        Frame = _TkHeadlessBase
        Label = _TkHeadlessBase
        Button = _TkHeadlessBase
        Entry = _TkHeadlessBase
        Combobox = _TkHeadlessBase
        Checkbutton = _TkHeadlessBase
        Separator = _TkHeadlessBase
        Scrollbar = _TkHeadlessBase
        Notebook = _TkHeadlessBase
        LabelFrame = _TkHeadlessBase
        Style = _TkHeadlessBase

    class _HeadlessDialog:
        def askopenfilename(self, **kwargs):
            return ""

        def askdirectory(self, **kwargs):
            return ""

    class _HeadlessMessageBox:
        def showwarning(self, *args, **kwargs):
            return None

        def showinfo(self, *args, **kwargs):
            return None

        def showerror(self, *args, **kwargs):
            return None

        def askyesno(self, *args, **kwargs):
            return False

    tk = _TkHeadless()
    ttk = _TtkHeadless()
    filedialog = _HeadlessDialog()
    messagebox = _HeadlessMessageBox()

__all__ = [
    "TKINTER_AVAILABLE",
    "TKINTER_IMPORT_ERROR",
    "tk",
    "ttk",
    "filedialog",
    "messagebox",
]
