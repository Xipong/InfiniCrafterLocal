from __future__ import annotations

# Launcher. Real implementation lives in:
#   LocalGenerator/infini_local/desktop/settings_gui.py
from infini_local.desktop import settings_gui as _impl
from infini_local.desktop.settings_gui import main

if __name__ == "__main__":
    main()
else:
    import sys as _sys
    _sys.modules[__name__] = _impl
