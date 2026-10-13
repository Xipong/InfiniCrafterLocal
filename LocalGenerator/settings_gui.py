from __future__ import annotations

# Browser Studio launcher; imports retain the legacy desktop controller API.
# UI: infini_local/desktop/webui, bridge: infini_local/desktop/web_studio.py
from infini_local.desktop import settings_gui as _impl
from infini_local.desktop.settings_gui import main

if __name__ == "__main__":
    from infini_local.desktop.web_studio import main as studio_main
    studio_main()
else:
    import sys as _sys
    _sys.modules[__name__] = _impl
