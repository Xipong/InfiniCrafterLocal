from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path


class _BlockTkinter(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):  # type: ignore[override]
        if fullname == "tkinter" or fullname.startswith("tkinter."):
            raise ModuleNotFoundError("No module named 'tkinter'")
        return None


def test_settings_gui_imports_without_tkinter_installed() -> None:
    """Contract: headless Python installs can run pytest without tkinter/_tkinter."""
    module_path = Path(__file__).resolve().parents[1] / "infini_local" / "desktop" / "settings_gui.py"
    spec = importlib.util.spec_from_file_location("_infini_settings_gui_headless_probe", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    saved_tk_modules = {k: v for k, v in sys.modules.items() if k == "tkinter" or k.startswith("tkinter.")}
    blocker = _BlockTkinter()
    try:
        for key in list(saved_tk_modules):
            sys.modules.pop(key, None)
        sys.meta_path.insert(0, blocker)
        spec.loader.exec_module(module)
    finally:
        try:
            sys.meta_path.remove(blocker)
        except ValueError:
            pass
        for key in list(sys.modules):
            if key == "tkinter" or key.startswith("tkinter."):
                sys.modules.pop(key, None)
        sys.modules.update(saved_tk_modules)

    assert module.TKINTER_AVAILABLE is False
    assert "INFINI_LLM_FALLBACK_MODEL" in module.FIELD_ORDER
    assert module.DEFAULTS["INFINI_LLM_FALLBACK_NETWORK_FAILS"] == "2"
    # The fallback exposes real class objects, so isinstance checks used by GUI
    # helper methods do not explode under headless pytest.
    assert isinstance(module.tk.Tk(), module.tk.Widget)
    assert isinstance(module.ttk.Entry(), module.ttk.Widget)
